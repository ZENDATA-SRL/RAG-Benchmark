# Sprint 1 — Fondamenta: migrazione, ambiente, storage, registry

**Obiettivo.** Portare il codice già scritto a uno stato *eseguibile*: schema creato in Postgres da
Alembic, ambiente locale completo con un comando, storage oggetti utilizzabile, registry dei
componenti popolato con i due `builtin` che serviranno all'MVP.

**Perché prima di tutto.** Oggi esistono modelli ORM senza migrazioni e service senza HTTP: nulla è
verificabile. Questo sprint non aggiunge funzionalità di prodotto, rende osservabile quella già scritta.

**Esito verificabile.** `docker compose up -d && alembic upgrade head && uvicorn src.main:app` porta a
un'API che risponde su `/health` e su `/components`, con lo schema delle 45 tabelle in Postgres e i
componenti `parser/pypdf` e `chunker/recursive` registrati.

---

## Backlog

### 1.1 — Migrazione iniziale dello schema

`backend/alembic/versions/0001_initial_schema.py`

- Generare la migrazione con `alembic revision --autogenerate` e **rivederla a mano**: l'autogenerate
  non produce l'ordine di `CREATE TYPE` corretto e non vede gli unique index di appoggio alle FK composite.
- Verificare che siano presenti: gli 8 ENUM di `infrastructure/database/enums.py`, l'estensione
  `pgcrypto` (serve `gen_random_uuid()`), gli unique di appoggio
  `parsing_results (id, parsing_profile_id)` e `chunking_configurations (id, parsing_profile_id)`
  e le due FK composite di `chunk_results` (`DATA_MODEL.md` blocco 3).
- Controllare `downgrade()`: deve fare `DROP TYPE` dopo le tabelle.
- `alembic/env.py`: confermare che importi `src.infrastructure.database.models` così il `target_metadata`
  vede tutte le tabelle, e che legga `database_url` da `Settings` e non da `alembic.ini`.

**Nota.** I blocchi 5-7 (dataset, trasferimento, esperimenti) **non hanno ancora modelli ORM**: la
migrazione crea solo le ~23 tabelle dei blocchi 1-4. Le restanti arrivano con le milestone che le usano;
il riepilogo delle 45 tabelle di `DATA_MODEL.md` è la meta, non il contenuto di questa migrazione.

**Accettazione:** `alembic upgrade head` e `alembic downgrade base` su un database vuoto, due volte di
seguito, senza errori.

### 1.2 — Ambiente locale completo

`docker-compose.yml`, `.env.example`, `README.md` di root

- Servizi: `postgres`, `minio` (+ `minio-init` che crea il bucket), `temporal`, `temporal-ui`,
  `temporal-postgres`. Rimuovere `azurite` (sostituito da MinIO, assunzione 2 del README) e tenere
  `chromadb` commentato: serve dalla Milestone 3, non ora.
- Healthcheck su `postgres` e `temporal` e `depends_on: condition: service_healthy`, altrimenti il
  worker parte prima del server e fallisce in modo confuso.
- Allineare le credenziali di `docker-compose` al default di `Settings.database_url`: oggi divergono
  (`test/test/test_db` contro `postgres/password/rag-bench`), ed è una mezz'ora di debug garantita al
  primo che clona.
- `.env.example` con tutte le variabili e commenti; nessun segreto reale (RT-S01).

**Accettazione:** da repository pulito, `docker compose up -d` porta tutti i servizi `healthy`;
la UI di Temporal risponde su `localhost:8080`.

### 1.3 — Configurazione applicativa estesa

`backend/src/settings.py`

- Aggiungere: `storage_endpoint`, `storage_access_key`, `storage_secret_key`, `storage_bucket`,
  `storage_secure`; `temporal_host`, `temporal_namespace`; `max_upload_bytes`;
  `allowed_mime_types` (solo `application/pdf` in MVP).
- Le credenziali restano **fuori dal database**, lette da ambiente (RT-S01).

**Accettazione:** `get_settings()` valida un `.env` completo e fallisce con messaggio chiaro se manca
una variabile senza default.

### 1.4 — Astrazione dello storage oggetti

`backend/src/infrastructure/storage/__init__.py`, `base.py`, `s3.py`

- Protocol `ObjectStorage` con `put_stream(key, stream, content_type) -> str`,
  `get_stream(key)`, `put_bytes`, `get_bytes`, `exists(key)`, `build_uri(key)`.
- Implementazione S3-compatibile su `boto3` (nuova dipendenza, esplicitamente richiesta da questo task).
- Scrittura e lettura **in streaming**, senza caricare il file in memoria (RF-S12): è più facile farlo
  adesso che riscrivere l'upload quando arriverà il primo PDF da 200 MB.
- Convenzione delle chiavi, documentata nel modulo:
  `documents/{content_hash[:2]}/{content_hash}{ext}` e
  `parses/{parsing_profile_config_hash}/{content_hash}.json`.
  Deriva dal contenuto, quindi lo stesso file caricato due volte scrive la stessa chiave.
- Dipendenza FastAPI `StorageDep` in `backend/src/dependencies.py`, con client riusato per processo.

**Accettazione:** test di integrazione contro MinIO che scrive 10 MB in streaming, rilegge e confronta
lo sha-256.

### 1.5 — Registry dei componenti: livello applicativo

`backend/src/components/{repository,service,schemas,router,exceptions}.py`

- Repository: `get_by_type_and_key`, `list_by_type`, `get_version`, `list_versions`,
  `get_version_by_component_and_version`.
- Service:
  - `register_component(type, key, display_name)` — get-or-create su `(type, key)` (RF-R01).
  - `register_version(...)` — get-or-create su `(component_id, version)`; valida che
    `params_schema` sia un JSON Schema sintatticamente valido (RF-R02).
  - `validate_params(component_version_id, params)` — valida i parametri di un profilo contro lo
    schema dichiarato; è la funzione che lo Sprint 4 chiama prima di creare un profilo.
  - `mark_unavailable(version_id, reason)` — RF-R05: un componente non disponibile si esclude
    dichiarando il motivo, non facendo fallire l'operazione.
- Router: `GET /components`, `GET /components/{id}/versions`, `POST /components`,
  `POST /components/{id}/versions`. Il `GET` è ciò che alimenta i form dinamici della UI (RT-U01).
- Solo `runtime='builtin'` è ammesso in MVP: `runtime='http'` accettato a modello ma rifiutato dal
  service con errore esplicito, perché non c'è ancora il client che lo invochi (RF-R04).

**Dipendenza:** `jsonschema` per la validazione.

**Accettazione:** registrare due volte lo stesso componente non crea righe duplicate; parametri non
conformi allo schema producono `422` con il percorso del campo invalido.

### 1.6 — Contratti dei componenti builtin e seed del registry

`backend/src/components/builtin/__init__.py`, `parsers/pypdf.py`, `chunkers/recursive.py`,
`backend/src/components/registry_seed.py`

- Definire i due Protocol che lo Sprint 3 implementerà davvero:
  - `Parser.parse(stream, filename) -> ParseOutput` con `ParseOutput = {pages: [{page: int, text: str}], metadata: {}}`.
    Formato **serializzabile in JSON** perché va su object storage (RT-O02) e deve sopravvivere al riparse.
  - `Chunker.chunk(parse_output, params) -> list[ChunkPayload]` con
    `ChunkPayload = {text, modality, metadata: {page, ...}, text_normalized}` — le stesse chiavi che
    `ArtefactService.complete_chunk_result` già consuma.
- Registro in-process `BUILTIN_PARSERS` / `BUILTIN_CHUNKERS`, mappa `component.key -> implementazione`.
  È il punto in cui `builtin` significa "codice nel repository invocato in-process" (RF-R04).
- Seed idempotente, eseguito allo startup dell'app:
  - `parser/pypdf` v1, `params_schema` con `{extract_images: false}`, `capabilities: {formats: ["pdf"], modalities: ["text"]}`.
  - `chunker/recursive` v1, `params_schema` con `chunk_size`, `overlap`, `separators`,
    `strip_headers_footers` (RF-P03), `capabilities: {scope: "document"}` — `scope` è il campo che
    `ProfileService._assert_document_scope` già controlla.
- Il seed è idempotente perché usa il get-or-create di 1.5: rilanciare l'app non duplica nulla.

**Accettazione:** dopo due avvii consecutivi, `GET /components` restituisce esattamente due componenti
con una versione ciascuno.

### 1.7 — Fondazione HTTP e gestione errori

`backend/src/core/exceptions.py`, `backend/src/main.py`

- Eccezione base di dominio con `code`, `message`, `status_code`; le eccezioni già esistenti in
  `corpora/exceptions.py` e `pipelines/exceptions.py` ereditano da questa.
- Un solo exception handler registrato in `create_app()`: mappa le eccezioni di dominio in
  `{"code", "message", "details"}` con lo status dichiarato. Nessun `try/except HTTPException` nei router.
- Registrazione dei router in `create_app()` con prefisso `/api/v1`; CORS abilitato per l'origine della
  UI, letta da `Settings` (serve dallo Sprint 5, si predispone ora perché costa una riga).
- Logging strutturato in `core/logging.py` con `request_id` propagato: sarà l'unico strumento di debug
  quando i workflow inizieranno a fallire in modo asincrono.

**Accettazione:** un'eccezione di dominio sollevata in un service produce un JSON di errore coerente e
non uno stack trace 500.

### 1.8 — Impalcatura di test

`backend/tests/conftest.py`, `backend/tests/test_hashing.py`, `backend/tests/test_get_or_create.py`

- `pytest`, `pytest-asyncio`, `httpx` come dipendenze di sviluppo.
- Fixture: engine di test su database dedicato, transazione per test con rollback, `AsyncClient` sull'app.
- Primi test sulle due utility che tutto il resto assume corrette: le proprietà di `hashing`
  (ordine e duplicati irrilevanti per `composition_hash`, ordine delle chiavi irrilevante per
  `hash_json`, separatore NUL che distingue `("ab","c")` da `("a","bc")`) e la corsa concorrente di
  `get_or_create` (due writer sulla stessa chiave, una sola riga).

**Accettazione:** `pytest` verde in CI locale; i test non richiedono MinIO se marcati `integration`.

---

## Definition of Done

- [ ] Schema creato e distrutto da Alembic senza intervento manuale.
- [ ] `docker compose up -d` avvia Postgres, MinIO e Temporal `healthy`.
- [ ] Credenziali di compose, `.env.example` e default di `Settings` coerenti fra loro.
- [ ] Upload/download in streaming su MinIO verificato da test.
- [ ] `GET /api/v1/components` espone i due builtin con il loro JSON Schema.
- [ ] Errori di dominio serializzati in modo uniforme.
- [ ] `pytest` verde; README di root con le istruzioni di avvio.

## Requisiti coperti

RF-R01, RF-R02, RF-R03 (dichiarazione di `scope`), RF-R04 (solo `builtin`), RF-R05, RF-R06,
RF-S12 (streaming), RT-O02, RT-S01, RT-U01 (lato server).

## Rischi

| Rischio | Mitigazione |
|---|---|
| L'autogenerate di Alembic produce una migrazione incompleta sugli unique di appoggio e sulle FK composite | revisione manuale obbligatoria + test di `upgrade`/`downgrade` ripetuto |
| Il formato di `ParseOutput` scelto adesso vincola i parser futuri (Azure DI, Docling) | tenere `pages[].text` + `metadata` libero; un parser con layout ricco aggiunge chiavi senza rompere il chunker |
| La divergenza di credenziali fra compose e settings si ripresenta | un'unica fonte: `.env` usato sia da compose sia dall'app |

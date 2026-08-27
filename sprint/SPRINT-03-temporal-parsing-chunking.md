# Sprint 3 — Temporal, parsing pypdf, chunking

**Obiettivo.** Materializzare parsing e chunking **per documento** (RF-P10) su Temporal, con cache
content-addressed, idempotenza e resume, usando `pypdf` come parser e uno splitter ricorsivo come chunker.

**Perché ora.** È il passaggio 2 del flusso operativo e l'unico pezzo dell'MVP che richiede lavoro
asincrono vero: un PDF da 300 pagine non si parsa dentro una richiesta HTTP. Il livello dati è già
scritto (`ArtefactService`), qui si aggiunge l'esecuzione.

**Esito verificabile.** Lanciato `MaterializeChunksWorkflow` su un corpus di 10 PDF, la UI di Temporal
mostra 10 child workflow completati, `chunk_results` è `ready` per tutti e rilanciare lo stesso workflow
non riesegue nulla.

---

## Backlog

### 3.1 — Implementazione dei componenti builtin

`backend/src/components/builtin/parsers/pypdf.py`, `chunkers/recursive.py`

**Parser `pypdf`.**
- `parse(stream, filename) -> ParseOutput` con lo schema definito nello Sprint 1:
  `{"pages": [{"page": 1, "text": "..."}], "metadata": {"page_count": n, "producer": "..."}}`.
- Testo per pagina, non un'unica stringa: la pagina è il metadato di ancoraggio che il chunker propaga sui
  chunk e che la UI usa per mostrare *dove* si trova un chunk (RT-U04). Perderla qui significa non
  poterla recuperare a valle.
- Normalizzazione minima all'estrazione: de-sillabazione a fine riga, collasso degli spazi, virgolette
  tipografiche e legature ricondotte alla forma canonica (RT-M01). Serve già ora, perché sarà l'unica
  forma su cui il matching lessicale lavorerà in Milestone 6 e riparsare tutto per aggiungerla sarebbe
  costoso.
- PDF senza testo estraibile (scansione) → `PermanentParsingError` con motivo `no_extractable_text`:
  è un errore permanente, non si ritenta (RT-O06). L'OCR è fuori scope MVP.
- PDF corrotto o cifrato → `PermanentParsingError` con il motivo. Il documento risulta `failed`,
  gli altri proseguono.

**Chunker `recursive`.**
- `chunk(parse_output, params) -> list[ChunkPayload]` su `RecursiveCharacterTextSplitter`.
- Parametri: `chunk_size`, `overlap`, `separators`, `strip_headers_footers`.
- `strip_headers_footers` (RF-P03, **attivo di default** come da tabella dei rischi §10): euristica
  document-local — righe che si ripetono identiche in ≥60% delle pagine, in prima o ultima posizione,
  e righe che sembrano numerazione di pagina. Il 60% è un default da rendere parametro.
  Restare document-local non è un dettaglio: un filtro corpus-scoped violerebbe RF-P10 e il limite
  dichiarato del data model (`capabilities.scope = document`).
- Ogni chunk porta `metadata: {"page": n, "page_span": [start, end]}` e `text_normalized`.
- **Ordine deterministico**: i chunk escono in ordine di documento, perché `complete_chunk_result` assegna
  gli `ordinal` per posizione e l'identità di un chunk è `(documento, configurazione, posizione)`.
  Un chunker non deterministico romperebbe silenziosamente il gold della Milestone 4.

**Accettazione:** test golden su tre PDF di prova (prosa, tabella, multi-colonna) che verificano
determinismo — due esecuzioni, chunk identici — e propagazione della pagina.

### 3.2 — Impalcatura Temporal

`temporal/worker.py`, `temporal/client.py`, `temporal/config.py`, `temporal/task_queues.py`

- Client Temporal condiviso, costruito da `Settings` (`temporal_host`, `temporal_namespace`).
- Task queue separate per profilo di risorsa (RT-O03): `ingestion`, `parsing`, `chunking`.
  In MVP `parsing` e `chunking` possono girare sullo stesso worker, ma le queue vanno **distinte da subito**:
  separarle dopo significa cambiare gli id dei workflow già eseguiti.
- Worker con activity e workflow registrati, `graceful_shutdown_timeout` configurato.
- **Data converter con payload codec** che rifiuta payload oltre una soglia (es. 128 KB): è la guardia
  meccanica di RT-O02. Un giorno qualcuno passerà il testo di un PDF a un'activity, e deve fallire subito
  e in modo esplicito invece di far crescere la history di Temporal.
- Le activity accedono al database con la propria sessione (non quella di una request HTTP): factory di
  sessione dedicata, transazione per activity.
- Convenzione dei workflow id, in un unico modulo perché è l'infrastruttura di idempotenza (RT-O01):

  ```
  materialize-{chunking_configuration_id}-{documents_digest}
  process-doc-{document_id}-{chunking_configuration_id}
  ```

  `documents_digest` è `composition_hash(document_ids)`, già in `core/hashing.py`. Un id deterministico
  significa che Temporal stesso rifiuta il duplicato: l'idempotenza non è logica applicativa.

**Accettazione:** il worker si connette, la UI di Temporal lo mostra fra i poller delle tre queue;
un payload sopra soglia solleva un errore chiaro.

### 3.3 — Activity di parsing

`temporal/activities/parsing.py`

- `parse_document(document_id, parsing_profile_id) -> {parsing_result_id, status}`:
  1. `ArtefactService.claim_parsing_result` — se già `ready`, ritorna subito senza lavoro (RF-P07).
  2. Scarica il documento dallo storage in streaming.
  3. Risolve il parser dal registry builtin via `component.key`; valida i parametri contro `params_schema`.
  4. Esegue il parse, scrive il JSON su `parses/{config_hash}/{content_hash}.json`.
  5. `complete_parsing_result(output_uri=...)`.
- **Heartbeat per pagina** con l'indice raggiunto (RT-O04): su un PDF da 500 pagine è ciò che distingue un
  timeout da un progresso lento, e permette di riprendere a metà.
- Retry policy: `PermanentParsingError` in `non_retryable_error_types`; errori di rete/storage con backoff
  esponenziale (RT-O06).
- Su errore permanente: `fail_artefact(error=...)` e **ritorno normale**, non eccezione. Il workflow padre
  deve poter proseguire con gli altri documenti.

**Accettazione:** parsare due volte lo stesso documento con lo stesso profilo esegue `pypdf` una volta sola.

### 3.4 — Activity di chunking

`temporal/activities/chunking.py`

- `chunk_document(document_id, chunking_configuration_id, parsing_result_id) -> {chunk_result_id, chunk_count}`:
  1. `claim_chunk_result` — la validazione della coerenza fra parse in input e profilo dichiarato dalla
     configurazione è già dentro il service (`ParsingProfileMismatchError`).
  2. Legge il parse dallo storage.
  3. Risolve il chunker builtin, valida i parametri, esegue.
  4. `complete_chunk_result(chunks)`.
- **Ri-materializzazione**: se esiste già un `chunk_result` `failed`, ripulire i `chunks` orfani prima di
  riscrivere, altrimenti l'unique `(chunk_result_id, ordinal)` fa fallire il retry. È il caso limite che
  emerge solo in produzione, quindi va gestito ora e coperto da test.
- Chunk oltre una soglia di numerosità (es. 10.000 su un documento) → warning nel log, non errore:
  è un segnale di configurazione sbagliata, non un fallimento.

**Accettazione:** rilanciare il chunking di un documento fallito lo porta a `ready` senza violazioni di
unicità e con `chunk_count` corretto.

### 3.5 — `ProcessDocumentWorkflow`

`temporal/workflows/process_document.py`

- Firma `(document_id, chunking_configuration_id)`; risolve il `parsing_profile_id` dalla configurazione
  con un'activity di lettura (i workflow non toccano il DB direttamente).
- Sequenza: `parse` → `chunk`, come nel layout §5.2 dei requisiti.
- Se il parse è fallito in modo permanente, **non** eseguire il chunk e terminare con esito
  `{status: "failed", reason: ...}`: un workflow terminato con esito negativo è un dato, non un'anomalia.
- Timeout di activity generosi (parsing di PDF grandi) ma finiti; `heartbeat_timeout` coerente con la
  frequenza di heartbeat di 3.3.

**Accettazione:** un corpus con un PDF corrotto e nove validi produce nove `ready` e un `failed`.

### 3.6 — `MaterializeChunksWorkflow`

`temporal/workflows/materialize_chunks.py`

- Firma `(document_ids, chunking_configuration_id)` — **una lista di documenti, non uno snapshot**
  (§5.2 dei requisiti). È ciò che rende lo stesso workflow utile sia per l'anteprima su un file (RF-P08)
  sia per un corpus intero, e ciò che tiene il chunking indipendente dallo spazio di ricerca.
- Prima activity: `documents_needing_chunking` — già implementata in `ArtefactService`. È il motivo per cui
  aggiungere 50 documenti a un corpus costa il chunking di 50 e non di 250 (RF-C05).
- Child workflow per documento, **con concorrenza limitata** da parametro (default 5): un semaforo in
  workflow, non `asyncio.gather` su tutto, altrimenti 200 documenti saturano il worker.
- `continue_as_new` oltre N child completati (RT-O05), con soglia conservativa (es. 500).
- Activity finale di riepilogo che scrive lo stato denormalizzato per la UI (RT-O07): totale, completati,
  falliti, con il motivo per documento.
- Esito: `{total, ready, failed, skipped_cached, failures: [{document_id, error}]}`.

**Accettazione:** rilanciare il workflow con lo stesso `(document_ids, configuration)` viene rifiutato da
Temporal per workflow id duplicato — oppure, se il precedente è concluso, riparte e trova tutto in cache
e completa senza eseguire activity di parsing.

### 3.7 — Stato denormalizzato dell'avanzamento

`backend/src/pipelines/models.py` (+ migrazione), `service.py`

- Serve una riga per rappresentare "la materializzazione lanciata dall'utente", perché la UI deve
  mostrare l'avanzamento (RT-U05) senza interrogare Temporal a ogni polling.
  `chunk_results` da soli non bastano: non dicono *quale richiesta* li ha generati né quante ne mancano.
- Nuova tabella `materialization_runs`, coerente con le convenzioni del data model:

  | Campo | Tipo | Note |
  |---|---|---|
  | `id` | UUID PK | |
  | `chunking_configuration_id` | UUID FK | |
  | `corpus_id` | UUID FK, NULL | informativo, per la UI |
  | `workflow_id` | TEXT UNIQUE | id deterministico (RT-O01) |
  | `status` | artifact_status | riusa l'ENUM esistente |
  | `document_count` | INTEGER | |
  | `progress` | JSONB | `{ready, failed, cached, pending}` |
  | `started_at` / `finished_at` | TIMESTAMPTZ | |
  | `created_at` | TIMESTAMPTZ | |

- **Da proporre come aggiunta a `DATA_MODEL.md`**: è un'entità nuova rispetto alle 45 documentate, ed è
  la copia denormalizzata che RT-O07 prescrive per gli altri run (`import_runs`, `runs`, `index_builds`).
  Va aggiunta al documento, non introdotta di soppiatto.
- Le activity aggiornano `progress` in modo incrementale; lo stato autorevole resta Temporal.

**Accettazione:** durante un run su 20 documenti, `progress` cresce in modo monotono e a fine run
`ready + failed + cached == document_count`.

### 3.8 — Test

`backend/tests/test_builtin_parsers.py`, `test_builtin_chunkers.py`,
`temporal/tests/test_process_document.py`, `test_materialize_chunks.py`

- Parser: determinismo, propagazione pagina, PDF corrotto → errore permanente, PDF scansionato → errore
  permanente con motivo dedicato.
- Chunker: `chunk_size`/`overlap` rispettati, filtro header/footer su un PDF con intestazione ripetuta,
  determinismo.
- Workflow con `WorkflowEnvironment.start_time_skipping` e activity mockate: happy path, documento
  fallito che non blocca gli altri, secondo lancio che trova la cache.
- Test di integrazione end-to-end su un worker reale, marcato `integration`.

---

## Definition of Done

- [ ] `pypdf` e lo splitter ricorsivo registrati, invocabili e deterministici.
- [ ] Worker Temporal avviabile da `docker compose`, con tre task queue.
- [ ] Guardia sulla dimensione dei payload attiva.
- [ ] `MaterializeChunksWorkflow` idempotente, con concorrenza limitata e `continue_as_new`.
- [ ] Un documento fallito non interrompe il run e ne dichiara il motivo.
- [ ] `materialization_runs` popolata e `DATA_MODEL.md` aggiornato con la nuova entità.
- [ ] Test unitari e workflow verdi; integrazione verde in locale.

## Requisiti coperti

RF-P01, RF-P02, RF-P03, RF-P07, RF-P10, RF-R04 (`builtin` in-process),
RT-O01, RT-O02, RT-O03, RT-O04, RT-O05, RT-O06, RT-O07, RT-M01 (normalizzazione).

## Rischi

| Rischio | Mitigazione |
|---|---|
| `pypdf` estrae male PDF multi-colonna e tabelle | limite **dichiarato** dell'MVP, non un bug: è esattamente ciò che la piattaforma esiste per misurare (§3.1); il parser migliore arriva come nuovo adapter |
| Il filtro header/footer scarta contenuto legittimo | soglia parametrica, default 60%, e ispezione dei chunk (Sprint 4) come strumento di verifica prima di applicare a tutto il corpus |
| Chunk non deterministici invalidano il gold futuro | test di determinismo obbligatorio su ogni chunker registrato |
| History di Temporal gonfiata da payload grossi | payload codec con soglia rigida, riferimenti allo storage |

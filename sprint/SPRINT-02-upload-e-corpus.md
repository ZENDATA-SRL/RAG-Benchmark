# Sprint 2 — Upload manuale, documenti, corpus

**Obiettivo.** Portare un PDF dal disco dell'utente dentro la piattaforma: upload manuale,
deduplicazione per hash del contenuto, provenienza registrata, appartenenza a un corpus, tutto
esposto via API.

**Perché ora.** È il primo passo del flusso operativo (§8.1 dei requisiti) e l'input di tutto il resto:
senza documenti in Postgres e su object storage non c'è nulla da parsare.

**Perimetro dichiarato.** Solo sorgente `upload`. Nessuna enumerazione, nessuna navigazione,
nessuna ri-sincronizzazione: il file arriva in una richiesta HTTP. Questo rende il blocco 1 del data
model utilizzabile al 60% (`source_connections`, `import_runs`, `import_file_results`,
`document_provenances`) senza scrivere adapter.

**Esito verificabile.** `POST /api/v1/corpora/{id}/documents/upload` con tre PDF crea tre documenti,
li lega al corpus, li carica su MinIO; ricaricare gli stessi file restituisce
`skipped_duplicate` e non crea righe nuove.

---

## Backlog

### 2.1 — Connessione di upload e il suo import run

`backend/src/sources/{service,schemas,router,exceptions}.py`

- Al seed dello startup (accanto a quello dei componenti dello Sprint 1) creare una
  `SourceConnection` singleton di tipo `upload`, `auth_method='none'`, chiamata `Manual upload`.
  Serve perché la provenienza è obbligatoria (RF-S05) e perché il giorno in cui arriva S3 l'upload non
  sarà un caso speciale ma una connessione fra le altre.
- `ImportSelection` di comodo per l'upload (`paths: []`, `recursive: false`): un upload è una selezione
  degenere, e tenerlo dentro lo stesso modello significa che la UI di riepilogo import dello Sprint 5
  funzionerà anche per le sorgenti future senza modifiche.
- Service `UploadImportService`:
  - `open_run()` → crea un `ImportRun` in `running` (nessun `workflow_id`: l'upload è sincrono, non passa
    da Temporal — vedi nota sotto).
  - `record_file_result(run, source_uri, outcome, document_id, error_reason)`.
  - `close_run(run)` → aggrega `import_file_results` con `count_by_outcome` (già in repository) e scrive
    `counts` + `status` (`succeeded` / `partial` / `failed`), con `finished_at`.

**Nota di scelta.** L'upload manuale **non** usa Temporal: il file è già in memoria del server,
l'operazione dura il tempo di uno streaming su MinIO e la UI aspetta la risposta. Temporal serve per
lavoro lungo, ripartibile e con enumerazione remota — cioè dalla Milestone 2 (S3, SharePoint) e per il
parsing dello Sprint 3. Introdurlo qui aggiungerebbe latenza e complessità senza dare né retry utili né
resume. Se in futuro serve accodare upload molto grandi, il punto di innesto è `open_run`.

**Accettazione:** un upload da tre file produce un `ImportRun` con `counts = {imported: 3}` e status
`succeeded`.

### 2.2 — Service dei documenti con deduplicazione per contenuto

`backend/src/documents/{service,schemas,exceptions}.py`

- `DocumentService.ingest_upload(stream, filename, content_type, connection_id, original_uri)`:
  1. **Hash e store in un solo passaggio**: leggere lo stream a blocchi, aggiornare lo sha-256 e scrivere
     su un file temporaneo o direttamente su una chiave di staging; solo a hash noto si conosce la chiave
     finale, che dipende dal contenuto. Non caricare il file interamente in memoria (RF-S12).
  2. Rifiutare i MIME non in `allowed_mime_types` con outcome `skipped_unsupported`, **senza interrompere**
     il resto del batch (RF-S11).
  3. Rifiutare oltre `max_upload_bytes`.
  4. Get-or-create su `content_hash` (RF-S06): se il documento esiste, **non** riscrivere lo storage,
     restituire `(document, was_duplicate=True)`.
  5. Alla creazione: `status='fetching'` → scrittura → `status='stored'`; su errore `status='failed'` con
     `error` (RF-C04).
  6. Registrare sempre la provenienza (get-or-create su
     `(document_id, connection_id, original_uri)`, repository già presente): un duplicato **aggiunge una
     provenienza** al documento esistente, non un documento nuovo. È il senso di RF-S06.
- `ingest_upload_batch(files, ...)` → itera, isola i fallimenti per file, restituisce l'esito per file.

**Invariante da testare.** Lo stesso contenuto con due nomi diversi è **un** documento con due
provenienze; contenuti diversi con lo stesso nome sono due documenti.

**Nota sull'MVP.** La dedup per hash è già in `DocumentRepository.get_by_content_hash`: qui si aggiunge
solo l'orchestrazione. Vale la pena farla bene ora perché RF-S10 (file modificato = nuovo documento)
è la stessa logica vista da un altro lato, e sarà gratuita in Milestone 2.

**Accettazione:** caricare lo stesso PDF con due nomi crea 1 documento, 2 provenienze, e il secondo
esito è `skipped_duplicate`.

### 2.3 — Router dei documenti

`backend/src/documents/router.py`

- `POST /api/v1/documents/upload` — `multipart/form-data`, più file, campo opzionale `corpus_id`.
  Risposta: `{import_run_id, results: [{filename, outcome, document_id, error_reason}], counts}`.
- `GET /api/v1/documents` — lista paginata con filtro per `status`.
- `GET /api/v1/documents/{id}` — scheda con provenienze (RT-U06: da qui la UI risale all'originale).
- `GET /api/v1/documents/{id}/content` — download in streaming, per l'anteprima nativa della UI (RT-U04).
- Limite di dimensione applicato **prima** di leggere il corpo, non dopo.

**Accettazione:** upload da `curl` con tre file, di cui uno `.txt`, restituisce due `imported` e un
`skipped_unsupported`, e la richiesta ha esito `200` (RF-S11).

### 2.4 — Service e router dei corpus

`backend/src/corpora/{service,schemas,router}.py` (estende il `service.py` esistente)

- `CorpusService` (nuova classe, accanto a `CorpusSnapshotService` già presente):
  - `create`, `get`, `list`, `update`, `delete` (rifiutando l'eliminazione se esistono snapshot: RF-C05).
  - `add_documents(corpus_id, document_ids)` / `remove_document(...)` — repository già presente.
  - `progress(corpus_id)` → usa `count_by_status`, già implementato, per l'indicatore di RF-C04.
  - `set_document_metadata(document_id, metadata)` — RF-C02; i metadati stanno su `documents` perché
    sono proprietà del file, non dell'appartenenza.
- Router:
  - `POST /api/v1/corpora`, `GET /api/v1/corpora`, `GET /api/v1/corpora/{id}`, `PATCH`, `DELETE`.
  - `GET /api/v1/corpora/{id}/documents` — paginata, con filtro per status; usa `list_documents`.
  - `POST /api/v1/corpora/{id}/documents` — aggiunge documenti già esistenti.
  - `DELETE /api/v1/corpora/{id}/documents/{document_id}` — nella risposta dichiarare che gli snapshot
    esistenti restano validi (RF-C05); è un "rimuovi dal corpus", non un "elimina documento".
  - `POST /api/v1/corpora/{id}/documents/upload` — scorciatoia: upload + aggiunta al corpus in un atto.
    È l'endpoint che la UI userà davvero.

**Accettazione:** rimuovere un documento da un corpus non cancella il documento né tocca le righe di
`corpus_snapshot_documents`; il test lo verifica creando prima uno snapshot con il service esistente.

### 2.5 — Schemi Pydantic e paginazione condivisa

`backend/src/core/pagination.py`, `schemas.py` dei moduli toccati

- `Page[T]` con `items`, `total`, `limit`, `offset`: i repository accettano già `limit`/`offset`, manca
  il contratto di risposta.
- Separare rigorosamente `*Create`, `*Update`, `*Read`: gli `*Read` non espongono mai hash interni
  se non utili alla UI, ma **espongono sempre** `content_hash` sui documenti, perché è l'identità con cui
  l'utente riconosce un duplicato.
- Nessuna logica nei `schemas.py` (regola di progetto).

**Accettazione:** OpenAPI su `/docs` mostra tutti gli endpoint con esempi; nessun modello ORM appare
nelle risposte.

### 2.6 — Test

`backend/tests/test_documents_service.py`, `test_corpora_api.py`, `test_upload_dedup.py`

- Dedup: stesso contenuto, nomi diversi → 1 documento, 2 provenienze.
- MIME non supportato in un batch di tre → gli altri due passano.
- Corpus: aggiunta, rimozione, `progress` per status.
- Snapshot già esistente sopravvive alla rimozione dal corpus (RF-C05).
- Fallimento dello storage a metà upload → documento `failed` con `error` popolato, batch non interrotto.

---

## Definition of Done

- [ ] Un PDF caricato da `curl` è su MinIO, in `documents`, con provenienza e appartenenza al corpus.
- [ ] Ricaricarlo non duplica nulla e lo dichiara nel riepilogo dell'import run.
- [ ] Un file non supportato non fa fallire il batch.
- [ ] `GET /api/v1/corpora/{id}/documents` mostra stato per documento.
- [ ] Test dello sprint verdi; `/docs` navigabile.

## Requisiti coperti

RF-S01 (solo `upload`), RF-S05, RF-S06, RF-S07 (riepilogo; l'avanzamento in background arriva con
Temporal nello Sprint 3), RF-S11, RF-S12, RF-C01, RF-C02, RF-C04, RF-C05, RT-U06 (lato API).

## Rischi

| Rischio | Mitigazione |
|---|---|
| Serve l'hash per conoscere la chiave di storage, ma leggere lo stream due volte è inaccettabile su file grandi | hash incrementale durante la scrittura verso una chiave di staging, poi `copy` server-side alla chiave definitiva; documentare la scelta nel modulo |
| Un upload interrotto lascia un oggetto orfano su MinIO | il documento resta `failed` e la chiave è content-addressed, quindi un retry riscrive la stessa chiave; nessuna proliferazione |
| Metadati arbitrari su `documents` usati come discarica | schema libero ma documentato: i metadati saranno filtri di retrieval (RF-C02), non un campo note |

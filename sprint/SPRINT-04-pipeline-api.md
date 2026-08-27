# Sprint 4 — API della pipeline: profili, configurazioni, lancio, ispezione

**Obiettivo.** Esporre via HTTP tutto ciò che gli Sprint 1-3 hanno costruito: creare profili di parsing e
chunking, comporre la configurazione di chunking, lanciare la materializzazione, seguirne l'avanzamento,
ispezionare i chunk prodotti (RF-P08).

**Perché ora.** I service dei profili e degli artefatti esistono già e sono completi; i workflow esistono.
Manca solo il livello HTTP che li rende usabili — e senza di esso la UI dello Sprint 5 non ha nulla da
chiamare. È lo sprint con il minor rischio tecnico e il maggior guadagno di visibilità.

**Esito verificabile.** Uno script `curl` end-to-end: crea corpus → carica 3 PDF → crea profili →
crea configurazione → anteprima su 1 documento → materializza su tutti → segue l'avanzamento →
elenca i chunk con testo, pagina e metadati.

---

## Backlog

### 4.1 — API dei profili di pipeline

`backend/src/pipelines/{schemas,router}.py`

- `POST /api/v1/parsing-profiles`, `POST /api/v1/chunking-profiles` — chiamano
  `ProfileService.get_or_create_*`, già implementati.
- `GET` di lista e dettaglio per entrambi.
- **Prima di creare**, validare `params` contro il `params_schema` della versione di componente, usando
  `ComponentService.validate_params` dello Sprint 1: è la coppia server-side di RT-U01, senza la quale la
  validazione della UI è solo cosmetica.
- La risposta deve dichiarare se il profilo era **già esistente** (`created: true|false`): un utente che
  crea due volte lo stesso profilo con nomi diversi ottiene la stessa riga, e deve capire perché il nome
  che ha scritto non compare. È una conseguenza voluta di RF-P07 (il nome è escluso dall'hash), ma
  sorprende se non la si dichiara.
- `POST /api/v1/embedding-profiles` e `vector-store-profiles`: **non** in questo sprint. Il service esiste
  ma senza l'index build della Milestone 3 sarebbero endpoint che creano righe inerti.

**Accettazione:** creare due volte lo stesso profilo con nomi diversi restituisce lo stesso `id` con
`created: false`; parametri fuori schema danno `422` con il percorso del campo.

### 4.2 — API delle configurazioni di chunking

`backend/src/pipelines/router.py`

- `POST /api/v1/chunking-configurations` — `ChunkingConfigurationService.get_or_create`, già implementato.
- `GET /api/v1/chunking-configurations` — lista con i profili espansi: la UI deve poter mostrare
  "docling + recursive512" senza tre chiamate.
- `GET /api/v1/chunking-configurations/{id}/coverage?corpus_id=...` — per un corpus, quanti documenti
  hanno un `chunk_result` `ready`, quanti `failed`, quanti mancanti. È la query che risponde alla domanda
  che l'utente si pone davvero: *questa configurazione è pronta su questo corpus?*
  Si appoggia a `documents_needing_chunking`, già in `ArtefactService`.
- **Endpoint di comodo** `POST /api/v1/chunking-configurations/compose` che accetta i due profili per
  valore (componente + parametri) e fa tutti i get-or-create in un atto: è ciò che la UI usa quando
  l'utente compila un solo form. Riduce la UI a una chiamata e mantiene atomica la composizione.

**Accettazione:** `coverage` su un corpus a metà materializzato riporta i tre numeri corretti e la
somma pari al totale dei documenti del corpus.

### 4.3 — Lancio della materializzazione e avanzamento

`backend/src/pipelines/service.py` (nuovo `MaterializationService`), `router.py`

- `POST /api/v1/materializations`, corpo `{chunking_configuration_id, document_ids | corpus_id, concurrency?}`:
  1. Risolve i documenti: `document_ids` espliciti (anteprima su pochi file) **oppure** tutti quelli del
     corpus. Lo stesso endpoint serve RF-P08 e la materializzazione completa, come lo stesso workflow
     (§5.2).
  2. Rifiuta i documenti non in stato `stored`, dichiarando quali.
  3. Calcola il workflow id deterministico dello Sprint 3 e fa get-or-create su `materialization_runs`.
  4. Avvia il workflow con `start_workflow` idempotente: se l'id esiste già e sta girando, **restituisce il
     run esistente con `202`** invece di un errore. Doppio click sul pulsante non è un errore utente.
- `GET /api/v1/materializations/{id}` — stato denormalizzato: `status`, `progress`, `document_count`,
  `failures`.
- `GET /api/v1/materializations?corpus_id=&chunking_configuration_id=` — storico.
- `POST /api/v1/materializations/{id}/cancel` — cancellazione del workflow; lo stato passa a `failed`
  con motivo `cancelled`. Non è in RF per la materializzazione (RF-E08 riguarda gli esperimenti) ma
  costa poco e chi lancia un chunking su 200 file sbagliati lo cerca subito.
- **Polling, non WebSocket**: `GET` ogni 2 s dalla UI. Basta per RT-U05 e non introduce infrastruttura di
  push che andrebbe mantenuta. Se in futuro servisse, il punto di innesto è questo endpoint.

**Accettazione:** due `POST` identici in rapida successione producono un solo workflow e due risposte
`202` con lo stesso `id`.

### 4.4 — API di ispezione dei chunk (RF-P08)

`backend/src/pipelines/router.py`

- `GET /api/v1/documents/{document_id}/chunks?chunking_configuration_id=...` — chunk in ordine di
  `ordinal`, paginati, con `text`, `modality`, `metadata` (pagina inclusa), `ordinal`.
  Si appoggia a `ChunkRepository.list_by_chunk_result`, già implementato.
- `GET /api/v1/chunk-results?document_id=&chunking_configuration_id=` — stato dell'artefatto
  (`pending`/`running`/`ready`/`failed`) con `chunk_count` ed `error`. Lo stato di parsing e chunking
  **non** è una proprietà del documento ma dell'artefatto (§6.2): l'API deve rispecchiarlo, altrimenti la
  UI mostrerà uno stato che non esiste nel modello.
- `GET /api/v1/chunks/{id}` — dettaglio singolo, per il pannello laterale della UI.
- `GET /api/v1/documents/{document_id}/chunks/compare?configurations=id1,id2` — stessi chunk sotto due
  configurazioni, affiancati. Non è in RF per l'MVP, ma è **il** modo di rendere tangibile la tesi del
  progetto (§3.1: i parser differiscono proprio dove conta) e costa una query. Da tenere se lo sprint
  ha capienza, da tagliare per primo se non ce l'ha.

**Accettazione:** su un documento materializzato con due configurazioni diverse, i due elenchi differiscono
e ciascuno è ordinato e completo.

### 4.5 — Anteprima del parse

`backend/src/pipelines/router.py`

- `GET /api/v1/documents/{document_id}/parse?parsing_profile_id=...` — testo per pagina dal JSON su
  storage, paginato per pagina.
- Serve a diagnosticare il caso più frequente: "il chunking è strano" quasi sempre significa "il parse è
  strano". Senza questo endpoint l'utente non può distinguere i due stadi, e la piattaforma perde
  proprio la capacità diagnostica per cui esiste.

**Accettazione:** su un PDF di prova, il testo restituito per la pagina 3 corrisponde al contenuto reale.

### 4.6 — Script di verifica end-to-end

`scripts/mvp_smoke.sh` (o `scripts/mvp_smoke.py`)

- Esegue l'intero flusso via HTTP: corpus → upload → profili → configurazione → anteprima su 1 documento
  → materializzazione → polling fino a completamento → elenco dei chunk.
- Termina con un riepilogo leggibile e exit code diverso da zero al primo scostamento.
- È il criterio d'accettazione dell'MVP lato backend e il primo passo verso il test end-to-end dello
  Sprint 6.

**Accettazione:** lo script passa su un ambiente creato da zero.

### 4.7 — Test

`backend/tests/test_pipelines_api.py`, `test_materialization_api.py`

- Get-or-create dei profili via HTTP, con `created: false` al secondo tentativo.
- Validazione dei parametri contro `params_schema`.
- Doppio lancio idempotente della materializzazione.
- `coverage` con corpus parzialmente materializzato.
- Ispezione dei chunk: ordine, paginazione, filtro per configurazione.
- Client Temporal mockato nei test di API; il workflow reale è già coperto dallo Sprint 3.

---

## Definition of Done

- [ ] Flusso completo eseguibile da `curl`, senza toccare il database a mano.
- [ ] Profili e configurazioni deduplicati, con `created` dichiarato in risposta.
- [ ] Lancio idempotente e avanzamento leggibile in polling.
- [ ] Chunk e parse ispezionabili per documento e per configurazione.
- [ ] `scripts/mvp_smoke.sh` verde da ambiente pulito.
- [ ] OpenAPI completo su `/docs`.

## Requisiti coperti

RF-P01, RF-P02, RF-P08, RF-P09 (parte a monte: configurazione e materializzazione; snapshot e index build
restano alla Milestone 3), RF-P10, RF-C04, RT-O01, RT-O07, RT-U01 (validazione server), RT-U05 (dati per
l'avanzamento).

## Rischi

| Rischio | Mitigazione |
|---|---|
| L'utente non capisce perché il nome del suo profilo non compare (dedup per hash) | campo `created` in risposta e messaggio esplicito nella UI dello Sprint 5 |
| Il polling a 2 s su corpus grandi pesa sul DB | `progress` è una singola riga JSONB, non un aggregato; indice su `workflow_id` |
| L'endpoint `compose` nasconde troppa magia e diventa l'unico usato | tenere anche gli endpoint granulari e documentare `compose` come scorciatoia della UI |

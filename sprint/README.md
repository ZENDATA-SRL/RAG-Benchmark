# Piano di sprint — verso il primo MVP

Cartella di pianificazione agile. Un file per sprint, in ordine di esecuzione.

## Obiettivo dell'MVP

Un utente apre la UI, **carica manualmente** dei PDF, li raggruppa in un **corpus**, definisce una
**configurazione di chunking** (profilo di parsing + profilo di chunking), lancia la
**materializzazione** di parsing e chunking su Temporal, vede l'avanzamento e **ispeziona i chunk**
prodotti, anche su un singolo documento.

Traduzione in requisiti (`docs/REQUIREMENTS.md`): è la **Milestone 1** ridotta all'osso —
RF-S01 (solo `upload`), RF-S06, RF-S07, RF-S11, RF-C01, RF-C02, RF-C04, RF-C05,
RF-P01, RF-P02, RF-P03, RF-P07, RF-P08, RF-P10, RF-R01/R02/R04/R06 (solo `builtin`),
RT-O01/O02/O03/O06/O07, RT-U01, RT-U05.

## Fuori scope MVP (rimandato)

| Fuori scope | Rimandato a |
|---|---|
| Sorgenti filesystem / S3 / SharePoint, ri-sincronizzazione (RF-S03/S04/S09) | Milestone 2 |
| DOCX, parser Azure DI / Docling | post-MVP (nuovo adapter, nessun cambio di modello) |
| Embedding, vector store, snapshot di corpus, index build, retrieval (blocco 3 a valle) | Milestone 3 |
| QA set, gold, evidence link, trasferimento, esperimenti, Langfuse, leaderboard | Milestone 4-6 |
| Login, multi-tenancy, costi | v2 (§2.2 dei requisiti) |

Le tabelle di quei blocchi **esistono già** come modelli ORM e vengono migrate fin dallo Sprint 1:
non si toccano, ma non si scrive codice applicativo sopra.

## Stato di partenza (fine agosto)

Già in repository:

- `backend/src/infrastructure/database/`: `Base`, mixin di audit, ENUM PostgreSQL dei blocchi 1-4, engine/session async.
- Modelli ORM: `documents`, `sources`, `corpora`, `pipelines`, `components` (blocchi 1-4 del data model).
- Repository: `documents`, `sources`, `corpora`, `pipelines`.
- Service: `corpora` (snapshot get-or-create), `pipelines` (profili, configurazione di chunking, artefatti per documento, index build).
- `core/hashing.py` e `core/get_or_create.py`: content-addressing e get-or-create su savepoint.
- `main.py` con solo `/health`; Alembic configurato ma **`versions/` vuota**.
- `frontend/` e `temporal/` vuote; `docker-compose.yml` con Postgres, Azurite, ChromaDB.

Manca quindi tutto il livello HTTP (`router.py`, `schemas.py`), il service di documenti/sorgenti/componenti,
lo storage oggetti, l'implementazione dei componenti `builtin`, Temporal e la UI.

## Sprint

| # | File | Tema | Esito verificabile |
|---|---|---|---|
| 1 | [`SPRINT-01-fondamenta.md`](SPRINT-01-fondamenta.md) | Migrazione, ambiente locale, storage oggetti, registry componenti | `alembic upgrade head` crea lo schema; `docker compose up` avvia tutto; registry seedato |
| 2 | [`SPRINT-02-upload-e-corpus.md`](SPRINT-02-upload-e-corpus.md) | Upload manuale, documenti, corpus via API | `POST /documents/upload` deduplica per hash; corpus navigabile via API |
| 3 | [`SPRINT-03-temporal-parsing-chunking.md`](SPRINT-03-temporal-parsing-chunking.md) | Worker Temporal, parser pypdf, chunker, workflow per documento | `MaterializeChunksWorkflow` produce chunk idempotenti |
| 4 | [`SPRINT-04-pipeline-api.md`](SPRINT-04-pipeline-api.md) | API di profili, configurazioni, lancio e avanzamento, ispezione chunk | flusso completo eseguibile da `curl` |
| 5 | [`SPRINT-05-ui.md`](SPRINT-05-ui.md) | UI: corpus, upload, configurazione, avanzamento, chunk viewer | flusso completo eseguibile da browser |
| 6 | [`SPRINT-06-hardening-mvp.md`](SPRINT-06-hardening-mvp.md) | Test end-to-end, seed demo, documentazione, chiusura MVP | demo riproducibile da repo pulito |

**Assunzioni dichiarate** (le più piccole possibili, da confermare):

1. Uno sprint = **una settimana** di lavoro di uno sviluppatore; le stime sono in punti relativi, non in ore.
2. **Storage oggetti**: MinIO (S3-compatibile) come da RT-P02/§5.1, sostituendo Azurite in `docker-compose`. L'astrazione resta un'interfaccia, quindi il cambio è locale.
3. **UI**: React + TypeScript + Vite + Tailwind, form dinamici da JSON Schema con `@rjsf` (RT-U01). Nessun SSR: la UI è un client di un'API in rete privata.
4. **Chunker MVP**: `RecursiveCharacterTextSplitter` di `langchain-text-splitters`, già fra le dipendenze.
5. Nessun test suite preesistente: lo Sprint 1 introduce `pytest` + `pytest-asyncio` e i test crescono con ogni sprint.

## Convenzioni valide per tutti gli sprint

- Struttura dei moduli backend e direzione delle dipendenze come da `.cursor/rules/fastapi.mdc`: `router → service → repository → models`.
- Ogni entità content-addressed si crea **solo** con `get_or_create` sull'hash (RF-P07).
- I payload dei workflow contengono **riferimenti** allo storage, mai contenuti (RT-O02).
- Lo stato autorevole di avanzamento è in Temporal; il DB ne tiene una copia denormalizzata per la UI (RT-O07).
- Errori permanenti non si ritentano e non fanno fallire il resto del run (RT-O06).
- Definition of Done trasversale: codice + docstring in stile repository + test di livello adeguato + migrazione se il modello cambia + README aggiornato se cambia il modo di avviare il sistema.

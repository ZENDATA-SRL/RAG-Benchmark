# Sprint 6 — Hardening, demo riproducibile, chiusura MVP

**Obiettivo.** Trasformare "funziona sulla mia macchina" in "funziona da repository pulito": test
end-to-end, dati di esempio, documentazione, osservabilità minima, e il verdetto formale sull'MVP.

**Perché serve uno sprint dedicato.** Il flusso è completo alla fine dello Sprint 5, ma nessuno lo ha
ancora eseguito da zero su una macchina diversa, e i limiti dichiarati (pypdf sulle tabelle, filtro
header/footer) non sono ancora **misurati**. Chiudere qui evita che l'MVP diventi il fondamento non
verificato della Milestone 3.

**Esito verificabile.** `git clone && make up && make demo` porta a un browser con un corpus di esempio
già materializzato e chunk ispezionabili, e la CI esegue il test end-to-end su ogni push.

---

## Backlog

### 6.1 — Test end-to-end del flusso MVP

`e2e/test_mvp_flow.py` (pytest + httpx) e `frontend/e2e/mvp.spec.ts` (Playwright)

- Backend: promuovere `scripts/mvp_smoke.sh` dello Sprint 4 a test, con worker Temporal e MinIO reali,
  su database usa-e-getta. Asserzioni su: dedup, esiti per file, idempotenza del lancio, `chunk_count`,
  ordine degli `ordinal`, contenuto del primo e dell'ultimo chunk.
- Frontend: il test Playwright dello Sprint 5, esteso all'attesa reale del completamento.
- Casi negativi, che sono quelli che rompono in produzione:
  - PDF corrotto in un batch di dieci → nove `ready`, uno `failed` con motivo, run `partial`.
  - PDF scansionato senza testo → errore permanente, non ritentato (verificare che Temporal non abbia
    accumulato tentativi).
  - Worker riavviato a metà materializzazione → il run riprende e completa senza duplicare chunk.
    È il test che giustifica Temporal: se non passa, non stiamo ottenendo ciò per cui l'abbiamo introdotto.
  - Postgres non raggiungibile all'avvio → messaggio d'errore comprensibile, non traceback.

**Accettazione:** l'intera suite passa su un runner pulito, due volte di seguito.

### 6.2 — Dati di esempio e comando di demo

`scripts/seed_demo.py`, `samples/`, `Makefile`

- 5-8 PDF di esempio **con licenza compatibile**, scelti per coprire i casi che discriminano i parser
  (§3.1): prosa continua, tabella complessa, documento multi-colonna, documento con header/footer ripetuti,
  documento con indice.
- `make demo`: crea il corpus "Demo", carica i campioni, crea due configurazioni (`pypdf + recursive512` e
  `pypdf + recursive1024`), materializza entrambe. Due configurazioni e non una: è ciò che rende visibile
  in trenta secondi la tesi del progetto, cioè che la configurazione di chunking cambia il risultato.
- `Makefile` con `up`, `down`, `migrate`, `seed`, `demo`, `test`, `lint`, `logs`.

**Accettazione:** su una macchina senza il progetto, `make up && make migrate && make demo` porta a una UI
popolata in meno di cinque minuti.

### 6.3 — Misura dei limiti dichiarati

`docs/MVP_BASELINE.md`

- Eseguire i due chunking sui campioni e **registrare i numeri**: pagine estratte, caratteri per pagina,
  chunk prodotti, chunk provenienti da tabelle, righe scartate dal filtro header/footer, casi in cui il
  filtro ha scartato contenuto legittimo (controllo manuale sui campioni).
- Documentare con onestà cosa `pypdf` perde sulle tabelle. Non è un difetto da nascondere: è la baseline
  contro cui la Milestone 3+ misurerà i parser migliori, e l'Appendice A dei requisiti prevede
  esattamente questa misura come strumento ricorrente.
- Tarare il default del filtro header/footer sui dati raccolti anziché sul 60% ipotizzato nello Sprint 3.

**Accettazione:** il documento contiene numeri riproducibili dallo script, non impressioni.

### 6.4 — Osservabilità minima

`backend/src/core/logging.py`, `temporal/worker.py`

- Log strutturati JSON con correlazione: `request_id` lato API, `workflow_id` e `document_id` lato worker.
  Senza correlazione, diagnosticare "il chunking di quel file è fallito" richiede leggere tutto il log.
- `GET /api/v1/health/ready` che verifica Postgres, MinIO e Temporal e riporta lo stato per dipendenza;
  `/health` resta la liveness. La UI mostra già lo stato dei servizi nell'header (Sprint 5).
- **Nessun Langfuse in questo sprint**: entra con gli esperimenti (Milestone 5), dove ha senso. Introdurlo
  ora significherebbe tracciare parsing e chunking, che non sono ciò che Langfuse fa meglio (§5.3).
- Metriche di base nei log (durata del parse per documento, chunk al secondo): serviranno a dimensionare
  la concorrenza quando i corpora saranno grandi.

**Accettazione:** dato un `document_id` fallito, il log permette di ricostruire l'intera catena in una
query.

### 6.5 — Documentazione

`README.md` di root, `backend/README.md`, `frontend/README.md`, `temporal/README.md`,
`docs/ARCHITECTURE.md`

- README di root: cos'è il progetto, cosa fa **oggi** e cosa non fa ancora, avvio in cinque comandi,
  screenshot del flusso.
- `backend/README.md`: struttura dei moduli e direzione delle dipendenze, come aggiungere un componente
  `builtin` (è la domanda che riceverà chiunque voglia contribuire), come creare una migrazione.
- `temporal/README.md`: task queue, convenzione degli id, come rilanciare un workflow fallito.
- `frontend/README.md`: struttura, rigenerazione del client da OpenAPI.
- `docs/ARCHITECTURE.md`: diagramma dei componenti a runtime e mappa "requisito → dove è implementato",
  limitata a quanto realizzato.
- Riallineare `docs/DATA_MODEL.md`: aggiungere `materialization_runs` (Sprint 3) al riepilogo e
  annotare quali tabelle hanno un modello ORM e quali sono ancora solo progettate.

**Accettazione:** una persona esterna avvia il progetto seguendo solo il README.

### 6.6 — CI

`.github/workflows/ci.yml`

- Job backend: lint (`ruff`), `typecheck` (`mypy` sui moduli con annotazioni complete), `pytest` unitari,
  poi integrazione con Postgres/MinIO/Temporal come servizi.
- Job frontend: `lint`, `typecheck`, `vitest`, `build`.
- Job e2e: `docker compose` + Playwright, solo su `main` e sulle PR etichettate, perché è lento.
- Verifica che la migrazione sia coerente coi modelli: `alembic upgrade head` seguito da
  `alembic revision --autogenerate` che **non deve produrre differenze**. È il controllo che impedisce
  la deriva silenziosa fra ORM e schema, quella che si scopre sei mesi dopo in produzione.

**Accettazione:** CI verde su una PR di prova; il controllo di deriva fallisce se si aggiunge una colonna
senza migrazione.

### 6.7 — Revisione e consegna

- Rileggere la tabella "cosa costa lavoro umano" (§3.1) contro il codice: aggiungere documenti a un corpus
  e rimaterializzare deve costare **solo** il chunking dei nuovi. Verificarlo con un test dedicato, non a
  intuito: è l'invariante da cui dipende tutta l'economia del sistema, e la Milestone 4 la assume vera.
- Verificare che nessun `chunk_result` dipenda dallo snapshot (RF-P10) e che l'ordine dei chunk sia
  stabile fra esecuzioni: sono le due proprietà su cui il gold della Milestone 4 poggerà.
- Retrospettiva scritta: cosa ha richiesto più tempo del previsto, quali assunzioni del README si sono
  rivelate sbagliate, cosa va rivisto prima di aprire la Milestone 3.
- Aggiornare `docs/REQUIREMENTS.md` §9 con lo stato reale della Milestone 1.

---

## Definition of Done — e criteri di accettazione dell'MVP

- [ ] Da repository pulito: `make up && make migrate && make demo` funziona.
- [ ] Test end-to-end verde in CI, backend e frontend.
- [ ] Worker riavviato a metà run: il run completa senza duplicare chunk.
- [ ] Un documento fallito non interrompe il run e ne dichiara il motivo in UI.
- [ ] Aggiungere documenti a un corpus e rimaterializzare chunka **solo** i nuovi (verificato da test).
- [ ] Chunk deterministici fra esecuzioni.
- [ ] Baseline dei limiti di `pypdf` misurata e documentata.
- [ ] Nessuna credenziale nel database o nel repository (RT-S01).
- [ ] README che permette a un esterno di partire senza aiuto.

## Requisiti coperti

Consolidamento di tutti i requisiti degli Sprint 1-5, più RT-O06 (retry differenziate verificate),
RT-O07 (coerenza fra Temporal e copia denormalizzata), RT-S01.

## Rischi

| Rischio | Mitigazione |
|---|---|
| Lo sprint di hardening viene compresso per iniziare la Milestone 3 | i criteri di accettazione dell'MVP sono la porta d'ingresso della Milestone 3, non un contorno |
| Il test end-to-end è lento e viene disattivato | separare unitari (rapidi, sempre) da e2e (su `main` e PR etichettate) |
| I PDF di esempio hanno licenze incompatibili | usare documenti pubblici o generati per il progetto, con la fonte dichiarata in `samples/README.md` |

---

## Dopo l'MVP

L'ordine naturale, dato quanto costruito:

1. **Milestone 3 parziale — indicizzazione.** Snapshot di corpus (service già scritto), profili di
   embedding e vector store (service già scritti), `BuildIndexWorkflow`, ChromaDB già in compose.
   È lo sprint che sblocca il retrieval.
2. **Milestone 2 — sorgenti remote.** Filesystem e S3 come adapter: il modello dati e
   `IngestSourceSelectionWorkflow` non richiedono cambi, ed è per questo che l'upload è stato modellato
   come connessione fra le altre.
3. **Milestone 4 — authoring.** QA set, gold, evidence link: richiede i blocchi 5 del data model, che non
   hanno ancora modelli ORM, e riusa il navigatore di chunk dello Sprint 5 (RT-U03).

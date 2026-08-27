# Sprint 5 — UI: corpus, upload, configurazione, avanzamento, chunk viewer

**Obiettivo.** Rendere il flusso dell'MVP eseguibile da browser: creare un corpus, caricare PDF,
comporre una configurazione di chunking con form generati dallo schema, lanciare la materializzazione,
vederne l'avanzamento, ispezionare i chunk sul documento.

**Perché ora.** Il backend è completo e verificato da `curl`; la UI non deve inventare comportamenti, solo
esporli. Costruirla prima avrebbe significato indovinare i contratti.

**Stack** (assunzione 3 del README): React + TypeScript + Vite + Tailwind, TanStack Query per i dati,
React Router, `@rjsf/core` per i form da JSON Schema. Nessun SSR: è un client di un'API in rete privata.

**Esito verificabile.** Un utente che non ha mai visto il progetto completa il flusso senza leggere la
documentazione e senza usare il terminale.

---

## Backlog

### 5.1 — Impalcatura del frontend

`frontend/` (Vite scaffold)

- Progetto Vite + React + TS; Tailwind; ESLint + Prettier; script `dev`, `build`, `lint`, `typecheck`.
- Client API tipizzato **generato da OpenAPI** (`openapi-typescript` + un thin fetch wrapper): i tipi non
  si scrivono a mano, altrimenti divergeranno dal backend entro due sprint.
- TanStack Query con `queryClient` configurato; gestione centralizzata degli errori che legge il formato
  `{code, message, details}` dello Sprint 1.
- Layout applicativo: sidebar con Corpora / Configurazioni / Componenti, header con stato dei servizi.
- Dockerfile + servizio `frontend` in `docker-compose` (dev server con proxy verso l'API).

**Accettazione:** `npm run dev` serve la UI; `npm run typecheck` verde; il client generato compila.

### 5.2 — Corpus: elenco, creazione, dettaglio

`frontend/src/features/corpora/`

- Elenco corpus con conteggio documenti e barra di stato di acquisizione (RF-C04, da `progress`).
- Creazione e modifica (nome, descrizione).
- Dettaglio: tabella dei documenti con nome, dimensione, stato, data, e stato di **acquisizione** —
  non di parsing: lo stato di parsing esiste solo per configurazione (§6.2) e va mostrato altrove.
  Confondere i due nella UI è l'errore che porta gli utenti a chiedere "perché il documento è pronto ma i
  chunk no".
- Rimozione dal corpus con conferma che dichiara: *gli snapshot esistenti restano validi* (RF-C05).
- Scheda documento in pannello laterale: metadati, provenienze con link all'originale (RT-U06),
  hash del contenuto, azione "scarica".

**Accettazione:** creare un corpus, vederlo in elenco, aprirlo, rimuovere un documento e leggere
l'avviso corretto.

### 5.3 — Upload con drag & drop e riepilogo esplicito

`frontend/src/features/documents/UploadDialog.tsx`

- Drag & drop multi-file, con validazione locale di estensione e dimensione **prima** dell'invio.
- Avanzamento per file durante l'upload.
- Riepilogo finale che distingue i quattro esiti (RF-S07): importati, saltati come duplicati, saltati come
  non supportati, falliti con motivo. **I duplicati non sono errori** e vanno presentati come esito
  normale con il link al documento già esistente: è la cosa che l'utente fraintende più spesso.
- Un file non supportato non blocca gli altri, e la UI lo mostra chiaramente (RF-S11).

**Accettazione:** caricando 3 PDF + 1 TXT + 1 PDF duplicato, il riepilogo mostra 3 importati, 1 non
supportato, 1 duplicato con link.

### 5.4 — Registry dei componenti e form dinamici

`frontend/src/features/components/`, `frontend/src/components/SchemaForm.tsx`

- Pagina di sola lettura del registry: componenti per tipo, versioni, disponibilità con motivo (RF-R05).
- `SchemaForm`: wrapper su `@rjsf` che genera il form dal `params_schema` della versione selezionata
  (RT-U01). **Nessun campo hard-coded**: il giorno in cui si registra Docling, il suo form deve comparire
  senza toccare il frontend. È il test di questo componente.
- Widget personalizzati minimi (numero con slider per `chunk_size`, toggle per i booleani) e messaggi di
  validazione allineati a quelli del server.

**Accettazione:** registrando via API un componente fittizio con uno schema arbitrario, il suo form
appare correttamente senza modifiche al frontend.

### 5.5 — Composizione della configurazione di chunking

`frontend/src/features/configurations/ConfigurationWizard.tsx`

- Wizard in tre passi: **parser** (componente + versione + form) → **chunker** (idem) → **riepilogo**.
- Chiama `POST /chunking-configurations/compose` dello Sprint 4: un solo atto, tutti i get-or-create dietro.
- Se la configurazione esiste già, dirlo esplicitamente e proporre di usarla — non creare un doppione con
  nome diverso, che è impossibile per costruzione, e non mostrare un errore, che sarebbe falso.
- Elenco delle configurazioni con: nome, parser, chunker, parametri chiave, e **copertura sul corpus
  corrente** (da `coverage`): pronto / parziale / non materializzato.

**Accettazione:** creare due volte la stessa configurazione con nomi diversi porta alla stessa riga con un
messaggio comprensibile.

### 5.6 — Lancio della materializzazione e avanzamento in tempo reale

`frontend/src/features/materializations/`

- Dal dettaglio del corpus: pulsante **"Materializza chunk"** con scelta della configurazione e ambito
  (tutto il corpus / documenti selezionati).
- **Anteprima su un documento** come azione separata e ben visibile (RF-P08): è il percorso che i requisiti
  raccomandano — provare su tre file prima di applicare a duecento — e se è nascosto in un menù nessuno
  lo usa.
- Pannello di avanzamento con polling a 2 s (RT-U05): barra su `progress`, contatori
  ready / cached / failed / pending, elenco dei falliti con motivo per documento.
  Distinguere **`cached`** da **`ready`** ha un valore didattico preciso: mostra all'utente che
  rimaterializzare non ricalcola (RF-P07), che è la proprietà su cui poggia tutta l'economia del sistema.
- Pulsante di annullamento.
- Doppio click sul lancio non crea due run: la UI riceve lo stesso `id` e non deve trattarlo come errore.

**Accettazione:** lanciando su un corpus già materializzato, il pannello mostra tutti i documenti come
`cached` e termina in pochi secondi.

### 5.7 — Chunk viewer

`frontend/src/features/chunks/ChunkViewer.tsx`

- Vista a due pannelli: a sinistra il **PDF nativo** (`react-pdf`, RT-U04), a destra l'elenco dei chunk
  con testo, ordinale, pagina e metadati.
- Selezionando un chunk, il PDF salta alla sua pagina; selezionando una pagina, la lista scorre ai suoi
  chunk.
- Toggle fra testo grezzo e `text_normalized`.
- Vista del **parse** per pagina (endpoint 4.5), come tab accanto ai chunk: distinguere "il parser ha perso
  il contenuto" da "il chunker lo ha spezzato male" è la diagnosi che l'utente deve poter fare da solo.
- **Componente riusabile e isolato**: RT-U03 prescrive che la UI di annotazione (Milestone 4) e quella di
  trasferimento (Milestone 6) condividano lo stesso navigatore di chunk. Scriverlo ora con un'interfaccia
  pulita — `chunks`, `selectedId`, `onSelect`, `renderChunkActions` — evita di riscriverlo due volte.
  Non aggiungere selezione multipla né azioni di annotazione: fuori scope, ma lasciare il punto di innesto.
- Confronto affiancato fra due configurazioni, se l'endpoint 4.4 è stato realizzato.

**Accettazione:** su un PDF di 20 pagine, cliccare un chunk di pagina 7 porta il visualizzatore a pagina 7.

### 5.8 — Rifiniture e test

- Stati vuoti scritti (nessun corpus, nessun documento, nessuna configurazione) con l'azione successiva
  suggerita: sono le schermate che un nuovo utente vede per prime.
- Stati di caricamento con skeleton; toast per gli errori con il `code` del backend.
- Navigazione da tastiera nel chunk viewer (frecce su/giù fra i chunk): l'ispezione è un'attività
  ripetitiva e sarà annotazione in Milestone 4.
- Test: Vitest + React Testing Library sui componenti con logica (`SchemaForm`, riepilogo upload, pannello
  di avanzamento). Un test Playwright del flusso completo, che diventerà il test end-to-end dello Sprint 6.

---

## Definition of Done

- [ ] Flusso completo eseguibile da browser senza terminale.
- [ ] Form dei parametri generati dallo schema, non codificati (RT-U01), verificati con un componente fittizio.
- [ ] Riepilogo di upload con i quattro esiti distinti.
- [ ] Avanzamento in tempo reale con `cached` distinto da `ready`.
- [ ] Chunk viewer con PDF nativo e sincronizzazione pagina ↔ chunk.
- [ ] Navigatore di chunk isolato e riusabile (RT-U03).
- [ ] `typecheck` e test frontend verdi; UI servita da `docker compose`.

## Requisiti coperti

RF-S07, RF-S11, RF-C01, RF-C02, RF-C04, RF-C05, RF-P01, RF-P02, RF-P03, RF-P08,
RT-U01, RT-U03 (fondazione), RT-U04, RT-U05, RT-U06.

## Rischi

| Rischio | Mitigazione |
|---|---|
| Il chunk viewer scritto per l'MVP va riscritto per l'annotazione | interfaccia progettata ora per la selezione, con punti di innesto per le azioni; nessuna logica di annotazione dentro |
| I form da JSON Schema sono brutti o inusabili con schemi complessi | widget personalizzati sui pochi campi frequenti; il fallback generico resta accettabile |
| Il rendering di PDF grandi blocca il browser | `react-pdf` con rendering lazy per pagina e virtualizzazione della lista chunk |
| Il proxy Vite verso l'API divergerà dalla configurazione di produzione | un'unica variabile `VITE_API_BASE_URL`, nessun path hard-coded |

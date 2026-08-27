# Piattaforma di benchmarking per sistemi RAG e agenti Q&A

**Documento di requisiti e design — versione 1.2**

---

## 1. Contesto e obiettivo

La piattaforma consente di **confrontare in modo controllato configurazioni diverse di sistemi RAG e agenti Q&A** su corpora documentali propri, misurando sia la qualità del retrieval sia la correttezza delle risposte.

Il problema che risolve: oggi la scelta di parser, chunker, embedder, vector DB, strategia di retrieval e sistema agentico avviene per intuizione o con test ad hoc non riproducibili. La piattaforma trasforma questa scelta in una misura ripetibile.

### 1.1 Utenti target

| Ruolo | Cosa fa sulla piattaforma |
|---|---|
| **AI/ML engineer** | definisce configurazioni, lancia esperimenti, legge le leaderboard |
| **Domain expert** | annota i dataset di valutazione, verifica le risposte manualmente |
| **Sviluppatore di agenti** | registra il proprio agente come "fornitore di risposta" e ne misura le regressioni |

### 1.2 Caso d'uso guida

> Ho 200 capitolati tecnici su SharePoint. Voglio sapere se conviene Azure Document Intelligence o Docling, quale embedder usare, se il retrieval ibrido batte quello denso, e se il mio agente interno risponde meglio di una catena RAG semplice. Voglio numeri, non impressioni.

---

## 2. Perimetro della versione 1

### 2.1 Incluso

- Acquisizione documenti da **sorgenti multiple**: upload locale, filesystem, S3, SharePoint/OneDrive
- Formati **PDF e DOCX**
- Pipeline configurabile: parsing → chunking → embedding → indicizzazione
- Vector DB e retrieval **sempre forniti dalla piattaforma**
- Registry estensibile di componenti (parser, chunker, embedder, vector store, reranker, sistemi di risposta)
- Authoring di dataset Q&A da UI, con selezione dei chunk gold
- Import/export di dataset da file esterni
- Esperimenti di **puro retrieval** e di **Q&A end-to-end**
- Metriche di retrieval a due livelli (documento e chunk) e metriche di risposta (LLM-as-judge, verifica umana)
- Esecuzione asincrona su Temporal, osservabilità e valutazione su Langfuse
- Wizard di trasferimento dei dataset fra configurazioni di chunking

### 2.2 Escluso dalla v1

| Fuori scope | Nota di estendibilità |
|---|---|
| Multi-tenancy, login, autorizzazioni | configurazione via variabili d'ambiente; il modello dati non contiene tenant, va aggiunto come dimensione se servirà |
| Modello dei costi | additivo: si introduce un'entità di consumo senza toccare il resto |
| Tassonomia strutturata delle domande | assorbita da un campo di tag liberi; si promuove ad attributi tipizzati in seguito |
| Formati TXT, MD, XLSX, PPTX | richiede solo nuovi adapter di parsing, non cambi di modello |
| Conversazioni multi-turno | attributi di conversazione previsti fin da subito per non dover migrare |
| Retrieval fornito dall'esterno | scelta deliberata, vedi §3.2 |
| Runtime a container per i componenti | vedi §4.4; l'enumerazione dei runtime si estende senza migrazione |
| Chunker che deduplicano boilerplate sull'intero corpus | il chunking è per documento (RF-P10); un chunker corpus-scoped si ammette dichiarando la capability e perdendo il riuso cross-snapshot |
| Snapshot che combinano più corpus | uno snapshot appartiene a un corpus; per combinare aree si crea un corpus che referenzia gli stessi documenti, senza duplicarli |

---

## 3. Decisioni architetturali fondanti

Queste quattro decisioni condizionano tutto il resto e sono documentate con la motivazione perché sono costose da rovesciare.

### 3.1 Il gold dell'evidenza è ancorato alla configurazione di chunking

**Decisione.** Domande e risposte attese sono immutabili e condivise fra tutte le configurazioni. I **chunk gold** sono invece un legame separato, uno per ogni configurazione di chunking, creato o confermato **da un umano**.

**Motivazione empirica.** È stata misurata la portabilità del matching automatico per citazione testuale su un corpus reale (capitolati tecnici, paper, documentazione di gara), confrontando 8 parser:

| Tipo di contenuto | Tasso di ritrovamento | Score medio |
|---|---:|---:|
| prosa | 84,7% | 96,0 |
| numerico | 85,7% | 96,4 |
| **tabelle** | **49,3%** | **78,0** |
| **complessivo** | **80,2%** | |

Il fallimento non è uniforme: è **concentrato sulle tabelle e sui documenti multi-colonna**, cioè esattamente dove i parser si differenziano di più. Un matching automatico produrrebbe quindi errori silenziosi e sistematici proprio sulla variabile da misurare. Peggio: un parser che estrae male le tabelle otterrebbe un buon punteggio perché il suo gold su tabella non si risolverebbe e sparirebbe dal denominatore.

**Conseguenza.** Cambiare parser o chunker richiede un passaggio umano di conferma. Il matching automatico resta come **pre-selezione ordinata**, mai come decisione (§4.6).

**Corollario: cosa costa e cosa non costa.** La configurazione di chunking (la coppia profilo di parsing + profilo di chunking) è l'**unica** dimensione il cui cambiamento richiede lavoro umano. Tutto il resto è gratuito e deve restarlo:

| Operazione | Costo umano |
|---|---|
| cambiare embedder, vector store, top-k, strategia, reranker, sistema di risposta | nessuno |
| aggiungere o togliere documenti da un corpus | nessuno |
| restringere un esperimento a un sottoinsieme di documenti | nessuno |
| cambiare profilo di parsing o di chunking | conferme umane sui chunk gold (§4.6) |

Questa tabella è un vincolo di progetto, non una descrizione: gli artefatti di pipeline sono materializzati **per documento** (§6.3) proprio perché l'identità di un chunk non dipenda dall'insieme di documenti in cui viene indicizzato. Se dipendesse, aggiungere un documento a un corpus invaliderebbe il gold e la seconda riga della tabella sarebbe falsa.

### 3.2 Vector DB e retrieval sono sempre della piattaforma

**Decisione.** Gli agenti non portano il proprio retrieval: si connettono al tool di retrieval esposto dalla piattaforma.

**Motivazione.** Il tool è un endpoint interno, quindi **strumentato lato server**. Ogni chiamata viene catturata anche se l'agente è una black box che non dichiara nulla. Si ottiene la traccia reale del retrieval senza chiedere cooperazione al fornitore dell'agente, e si garantisce che tutte le varianti interroghino lo stesso indice.

### 3.3 Metriche a due livelli con ambito di confrontabilità esplicito

| Livello | Basato su | Confrontabile fra | Costo di preparazione |
|---|---|---|---|
| **Documento** | lista dei file gold | **tutte** le configurazioni di chunking, a parità di spazio di ricerca | quasi nullo |
| **Chunk** | legame confermato verso i chunk | solo dentro la stessa configurazione di chunking | richiede trasferimento |

Il livello documento è stabile per costruzione: l'identità del documento è il file, non il suo parse. È il ponte che consente confronti cross-parser anche senza aver trasferito il dataset.

A entrambi i livelli il confronto presuppone lo **stesso spazio di ricerca**: `recall@5` su 50 documenti e su 200 non sono la stessa misura, perché i distrattori fanno parte di ciò che si misura. Lo snapshot di corpus è quindi la seconda dimensione della confrontabilità (§6.7), ed è fissata dall'esperimento.

L'ambito di confrontabilità è **applicato nella UI come raggruppamento**, non come avviso testuale (§5.7). Un banner viene ignorato dopo la terza volta; un raggruppamento no.

### 3.4 Un solo modello di gold per authoring interno e import esterno

Entrambi i percorsi producono la stessa struttura, differendo solo per come ci arrivano:

| Percorso | Input dell'utente | Risoluzione |
|---|---|---|
| Authoring interno | selezione dei chunk in UI | diretta; citazione e documenti gold derivati automaticamente |
| Import esterno | riferimento al file + citazione testuale | risoluzione assistita con coda di revisione |

Un solo formato di gold, un solo motore di metriche, una sola UI di revisione.

---

## 4. Requisiti funzionali

### 4.1 Sorgenti documentali

La piattaforma deve poter attingere documenti da sistemi diversi senza che l'utente li scarichi manualmente. Le sorgenti sono un **tipo di componente pluggable** come gli altri.

| ID | Requisito |
|---|---|
| RF-S01 | Supportare almeno quattro tipi di sorgente: **upload diretto**, **filesystem locale o share di rete**, **S3 e compatibili** (MinIO, GCS via interfaccia S3), **SharePoint/OneDrive** successivamente |
| RF-S02 | Registrare **connessioni riusabili** a una sorgente (endpoint + credenziali, flusso oaut2.0) |
| RF-S03 | Navigare la sorgente da UI (cartelle, siti, librerie documentali) e selezionare cosa importare |
| RF-S04 | Selezionare per singolo file, per cartella con ricorsione opzionale, o tramite pattern di filtro su nome ed estensione |
| RF-S05 | Registrare la **provenienza** di ogni documento: connessione, percorso o URI originale, identificativo nativo, data di modifica alla sorgente |
| RF-S06 | Deduplicare per hash del contenuto **indipendentemente dalla sorgente**: lo stesso file preso da S3 e da SharePoint è un documento solo, con due provenienze |
| RF-S07 | Eseguire l'acquisizione in background con avanzamento visibile e riepilogo finale (importati, saltati come duplicati, falliti con motivo) |
| RF-S08 | Rendere l'acquisizione **idempotente**: rilanciare lo stesso import non duplica nulla e riprende solo i file mancanti o falliti |
| RF-S09 | Supportare la **ri-sincronizzazione** di una selezione: rilevare file nuovi, modificati e rimossi alla sorgente |
| RF-S10 | Un file modificato alla sorgente genera un **nuovo documento**, non una sovrascrittura: gli snapshot esistenti restano validi e riproducibili |
| RF-S11 | Escludere i formati non supportati con un avviso esplicito, senza interrompere l'import del resto |
| RF-S12 | Gestire file di grandi dimensioni con streaming verso lo storage oggetti, senza caricarli interamente in memoria |
| RF-S13 | Aggiungere un nuovo tipo di sorgente deve richiedere solo un adapter, senza modifiche a modello dati o UI |

**Nota su RF-S10.** L'immutabilità degli snapshot è ciò che rende gli esperimenti storici interpretabili. Se un capitolato viene aggiornato su SharePoint, il vecchio documento resta referenziato dagli snapshot che lo contenevano e la nuova versione entra in quelli successivi. Un esperimento eseguito a marzo continua a significare quello che significava a marzo.

**Nota su RF-S05.** La provenienza non è solo tracciabilità: quando un domain expert annota una domanda e vuole verificare l'originale, deve poter risalire al documento nel sistema di origine con un click.

### 4.2 Gestione del corpus

| ID | Requisito |
|---|---|
| RF-C01 | Organizzare i documenti acquisiti in **corpus**: raggruppamenti logici e **mutabili**, tipicamente per area organizzativa (es. "documenti reparto cyber", "reparto acquisti") |
| RF-C02 | Associare metadati arbitrari a ciascun documento, utilizzabili come filtri di retrieval |
| RF-C03 | Congelare una selezione di documenti di un corpus in uno **snapshot immutabile**; gli indici e gli esperimenti puntano allo snapshot, mai allo stato corrente del corpus |
| RF-C04 | Visualizzare lo stato di ingestion per documento con l'errore in caso di fallimento |
| RF-C05 | Aggiungere o rimuovere documenti da un corpus **senza invalidare** gli snapshot esistenti né i dataset di valutazione già annotati |
| RF-C06 | Selezionare quali documenti del corpus entrano nello snapshot: tutto il corpus o un sottoinsieme |
| RF-C07 | **Deduplicare gli snapshot per composizione**: selezionare gli stessi documenti dello stesso corpus riusa lo snapshot esistente anziché crearne uno nuovo |

**Nota su RF-C01/C03.** Corpus e snapshot hanno ruoli distinti e non ridondanti: il corpus è l'area organizzativa che evolve nel tempo (riceve documenti nuovi, ne perde altri), lo snapshot è la selezione congelata su cui una misura è stata effettuata. Quello che fa fede per i confronti sono gli snapshot; il corpus può cambiare liberamente.

**Motivazione RF-C05.** È il requisito che rende sostenibile la crescita del corpus. Se un nuovo snapshot generasse chunk con identità nuova, ogni arrivo di documenti costerebbe una ri-annotazione dei chunk gold, violando §3.1 dove si stabilisce che solo il cambio di parsing o chunking ha costo umano. Il modello dati lo garantisce materializzando gli artefatti per documento (§6.3).

**Motivazione RF-C07.** Lo snapshot entra nella regola di confrontabilità (§3.3). Senza deduplicazione, lanciare dieci volte la stessa configurazione produrrebbe dieci snapshot con la stessa composizione, e quindi dieci gruppi non confrontabili di esperimenti che sono in realtà lo stesso esperimento. La deduplicazione è per hash della composizione, quindi trasparente all'utente.

### 4.3 Configurazione della pipeline

| ID | Requisito |
|---|---|
| RF-P01 | Definire **profili di parsing** riusabili (componente + versione + parametri) |
| RF-P02 | Definire **profili di chunking** (strategia, dimensione, overlap, politica sulle immagini) |
| RF-P03 | Il chunker deve poter **filtrare header, footer e righe di indice**; è un parametro esposto del profilo |
| RF-P04 | Definire **profili di embedding**, con supporto a modelli testuali, di immagine e multi-vettore |
| RF-P05 | Definire **profili di vector store** (Pinecone, Qdrant, pgvector, …) con i parametri d'indice |
| RF-P06 | Definire **profili di retrieval**: top-k, candidati pre-rerank, strategia (denso/sparso/ibrido/multi-vettore), pesi di fusione, MMR, soglia di score, filtri sui metadati, trasformazioni della query (HyDE, multi-query, riscrittura), reranker, politica di composizione del contesto |
| RF-P07 | Materializzare gli artefatti di pipeline in modo **immutabile e content-addressed**, per riusarli fra esperimenti senza ricalcolo |
| RF-P08 | Ispezionare i chunk prodotti da una configurazione, con testo e metadati, **anche su un singolo documento** prima di applicarla a tutto il corpus |
| RF-P09 | Definire una **configurazione di popolamento del vector DB** come atto unico: selezione dei documenti (snapshot) × parsing × chunking × embedding × vector store; è l'unità che l'esperimento seleziona già pronta |
| RF-P10 | Parsing e chunking sono materializzati **per documento**: il risultato dipende dal documento e dalla configurazione, non dall'insieme in cui il documento viene indicizzato |

**Nota su RF-P07.** Se un esperimento varia solo il top-k, non deve ri-parsare né ri-embeddare nulla. Ogni stadio ha una chiave di cache derivata dall'hash della configurazione e dagli input.

**Motivazione RF-P10.** Chunkare è un'operazione document-local: si prende il parse di un file e lo si spezza, e il risultato non dipende da quali altri documenti stanno nell'insieme. Ancorare i chunk a uno snapshot avrebbe tre conseguenze indesiderate: il gold a livello chunk si invaliderebbe a ogni cambio di composizione del corpus (contro RF-C05 e §3.1); snapshot sovrapposti duplicherebbero lavoro e storage (contro RF-P07); due configurazioni di chunking identiche su snapshot diversi risulterebbero non confrontabili a livello chunk pur essendolo. Il caso in cui il chunking dipende davvero dal corpus — deduplica di boilerplate cross-documento — è escluso dalla v1 e governato da una capability dichiarata (RF-R03); il filtro di header/footer di RF-P03 è per-documento e non è un'eccezione.

**Nota su RF-P09.** È la risposta a una questione di prodotto oltre che di modello: se lo snapshot e la catena di materializzazione nascessero al lancio dell'esperimento, il primo lancio comprenderebbe parsing, chunking ed embedding di tutto il corpus e l'utente vedrebbe "l'esperimento" fermo per venti minuti. Rendendo la configurazione di popolamento un oggetto esplicito, l'esperimento diventa una scelta fra indici già costruiti. Grazie a RF-C07 e RF-P07 l'operazione è idempotente: ripetere la stessa scelta non ricostruisce nulla.

### 4.4 Registry dei componenti (estensibilità)

| ID | Requisito |
|---|---|
| RF-R01 | Registrare nuovi componenti di qualsiasi tipo senza modificare il codice della piattaforma |
| RF-R02 | Ogni versione di componente dichiara uno **schema JSON dei propri parametri**; la UI genera il form dinamicamente |
| RF-R03 | Ogni versione dichiara le proprie **capability** (modalità supportate, formati, capacità di dichiarare citazioni e, per i chunker, l'ambito di elaborazione `document` o `corpus`) |
| RF-R04 | Supportare due modalità di esecuzione: **`builtin`** (codice nel repository della piattaforma, invocato in-process) e **`http`** (servizio remoto invocato secondo il contratto) |
| RF-R05 | Un componente non disponibile (dipendenza mancante, servizio irraggiungibile, credenziale assente) si esclude dichiarando il motivo, senza far fallire l'operazione |
| RF-R06 | Versionare i componenti: la stessa chiave può avere più versioni attive contemporaneamente |

**Nota su RF-R04.** `builtin` copre i componenti che manteniamo noi (parser standard, chunker, retriever, embedder); aggiungerne uno richiede un deploy della piattaforma. `http` copre tutto ciò che è esterno — ed è il caso principale per gli agenti sviluppati internamente da altri team: il fornitore deploya dove vuole, con le proprie dipendenze e il proprio ciclo di rilascio, e la piattaforma non conosce nulla della sua implementazione. Questo isolamento delle dipendenze è il motivo per cui `http` è preferibile a un caricamento dinamico di plugin Python in-process.

**Contratto del fornitore di risposta.**

```
POST /answer
{
  "question": "...",
  "attachments": [...],            // opzionale, per domande multimodali
  "retrieval_endpoint": "https://.../retrieve",
  "retrieval_token": "...",        // scoped alla singola esecuzione
  "config": { ... },               // parametri validati contro lo schema dichiarato
  "run_context": { "execution_id": "...", "trace_id": "..." }
}
→
{
  "answer": "...",
  "refused": false,                // true se il sistema dichiara di non sapere
  "citations": [ { "chunk_id": "...", "score": 0.87 } ],   // opzionale ma raccomandato
  "usage": { "model": "...", "tokens_in": 0, "tokens_out": 0 },
  "timings": { "total_ms": 0 },
  "error": null
}
```

Le citazioni sono opzionali: senza di esse le metriche di retrieval si calcolano comunque sulla traccia server-side del tool, ma si perde la metrica di attribuzione.

### 4.5 Dataset di valutazione

| ID | Requisito |
|---|---|
| RF-D01 | Creare un QA set, **riusabile su qualunque snapshot** che contenga i suoi documenti gold |
| RF-D02 | Definire per ogni domanda: testo, risposta attesa, eventuali allegati, tag liberi, flag di risposta possibile |
| RF-D03 | Ammettere **più risposte accettabili** per domanda, con eventuale rubrica per il judge |
| RF-D04 | I **documenti gold sono una lista**, non un singolo documento |
| RF-D05 | Selezionare i chunk gold da UI navigando il documento chunk per chunk |
| RF-D06 | Derivare automaticamente documenti gold e citazione testuale dai chunk selezionati |
| RF-D07 | Distinguere evidenza **sufficiente** (basta da sola) da evidenza **di supporto** |
| RF-D08 | Congelare un QA set in uno snapshot immutabile prima dell'esecuzione |
| RF-D09 | Importare dataset da JSONL/CSV con riferimenti per nome file e citazione testuale |
| RF-D10 | Verificare in fase di import che ogni citazione esista nel documento indicato, segnalando i riferimenti irrisolti |
| RF-D11 | Esportare un dataset nello stesso formato accettato in import (simmetria per il ciclo esporta-correggi-reimporta) |
| RF-D12 | L'authoring non richiede uno snapshot di corpus: si annota navigando i documenti gold e i loro chunk nella configurazione di chunking scelta |

**Motivazione RF-D01/D12.** Per scrivere una domanda servono i documenti da leggere e i chunk da selezionare, entrambi disponibili per documento (RF-P10): l'annotazione tocca i due o tre file gold di quella domanda, non un insieme congelato. Legare il QA set a uno snapshot con un vincolo rigido lo renderebbe inutilizzabile appena il corpus si estende, reintroducendo il costo di ri-annotazione che §3.1 riserva al solo cambio di parsing o chunking. Il vincolo corretto è verificato al momento dell'esperimento (RF-E09): i documenti gold delle domande valutate devono essere contenuti nello snapshot indicizzato.

**Motivazione RF-D04.** Il corpus di prova ha mostrato boilerplate identico fra documenti diversi (per esempio `Allegato C` e `Allegato C.2`). Se la risposta sta in un paragrafo presente in tre allegati, tutti e tre sono gold validi e il recall deve considerare rilevante qualsiasi documento della lista.

### 4.6 Trasferimento fra configurazioni

| ID | Requisito |
|---|---|
| RF-T01 | Trasferire un QA set esistente su una nuova configurazione di parse + chunking, mantenendo domande e risposte **immutabili e referenziate**, non copiate |
| RF-T02 | Per ogni domanda, proporre i chunk candidati **ordinati per punteggio combinato** che integra tre segnali: similarità semantica, identità testuale, prossimità posizionale |
| RF-T03 | Restringere la ricerca dei candidati ai documenti gold della domanda |
| RF-T04 | **Pre-selezionare** solo i candidati con identità testuale quasi certa; proporre senza pre-selezionare quelli con alta similarità semantica ma bassa corrispondenza testuale; offrire ricerca full-text quando nessun candidato è plausibile |
| RF-T05 | Nessun legame entra nel dataset senza conferma umana esplicita |
| RF-T06 | Stati del legame: **da esaminare**, **confermato**, **non trovato** |
| RF-T07 | "Non trovato" è un esito valido e informativo: significa che l'evidenza non esiste nei chunk di quella configurazione |
| RF-T08 | Consentire il **trasferimento parziale**: si può lanciare un esperimento su un sottoinsieme trasferito |
| RF-T09 | Mostrare l'avanzamento del trasferimento e il **tetto teorico di recall** implicato dai "non trovato" |
| RF-T10 | Il trasferimento riguarda la coppia (parsing, chunking) e **non dipende da alcuno snapshot**: si può eseguire prima di costruire un indice, e il risultato vale per ogni snapshot successivo |

**Nota sui tre segnali (RF-T02).** I due metodi di matching falliscono in modo complementare, ed è questo che giustifica la combinazione:

| Segnale | Robusto a | Fragile a |
|---|---|---|
| **Similarità semantica** (embedding) | riformulazione, riordino, serializzazione diversa delle tabelle | forte differenza di lunghezza: l'embedding di un chunk grande diluisce una gold breve |
| **Identità testuale** (matching lessicale) | differenza di lunghezza | riformulazione, riordino, serializzazione diversa |
| **Prossimità posizionale** | disambigua contenuti ripetuti | riordinamenti strutturali profondi |

Il segnale semantico è ciò che recupera le tabelle, dove il matching lessicale crolla al 49%. Il segnale lessicale è ciò che autorizza la pre-selezione: una similarità coseno alta può indicare un passaggio *simile* (tre clausole con struttura analoga hanno embedding vicinissimi) e non lo *stesso* passaggio, quindi da sola non basta a confermare automaticamente. Il segnale posizionale è quasi gratuito e disambigua proprio il caso del boilerplate ripetuto.

**Nota sul rilevamento dell'assenza.** Una ricerca semantica su un insieme filtrato restituisce sempre qualcosa: se il parser ha perso una tabella, proporrà comunque candidati con punteggio decente. È il segnale lessicale basso a funzionare da **rilevatore di assenza**, e quindi a produrre l'esito "non trovato" — il dato con cui si scopre che una configurazione ha perso 12 evidenze su 150.

**Effetto pratico atteso.** Su ~150 domande il wizard trasforma 150 ricerche manuali in un numero elevato di conferme rapide più una minoranza di ricerche assistite. I casi difficili saranno prevalentemente tabelle: il fallimento del matcher è quindi il segnale diagnostico che quel parser ha perso quel contenuto.

### 4.7 Esperimenti

| ID | Requisito |
|---|---|
| RF-E01 | Definire un esperimento di tipo **puro retrieval** o **Q&A end-to-end** su uno snapshot di corpus e uno di QA set |
| RF-E02 | Definire più **varianti** come combinazione di indice × profilo di retrieval × sistema di risposta |
| RF-E03 | Generare automaticamente le varianti da una griglia di parametri |
| RF-E04 | Designare una variante come **baseline** per i confronti |
| RF-E05 | Configurare il numero di **ripetizioni** per domanda, per gestire il non determinismo di LLM e agenti |
| RF-E06 | Rilanciare un esperimento riprendendo da dove si era interrotto, senza ripetere il lavoro già completato |
| RF-E07 | Salvare uno **snapshot integrale della configurazione** al lancio, per la riproducibilità anche se i profili vengono modificati o cancellati |
| RF-E08 | Interrompere un run in corso |
| RF-E09 | Verificare alla creazione dell'esperimento che i **documenti gold** delle domande siano contenuti nello snapshot indicizzato; se non lo sono, offrire di allargare lo snapshot oppure escludere quelle domande dalle metriche di retrieval **dichiarandolo** |
| RF-E10 | Tutte le varianti di un esperimento devono usare indici costruiti sullo **stesso snapshot di corpus**: lo spazio di ricerca è parte della misura |

**Motivazione RF-E09.** Poiché lo snapshot può essere un sottoinsieme del corpus (RF-C06) e un QA set è riusabile su snapshot diversi (RF-D01), è possibile valutare domande i cui documenti gold non sono indicizzati. Quelle domande hanno recall strutturalmente 0 per un limite della selezione, non del retriever: contarle come fallimenti produce lo stesso errore di lettura che RF-V06 esiste per prevenire. Va distinto il recall 0 *legittimo* — il documento gold è nell'indice e il retriever non l'ha trovato — che è invece esattamente ciò che si vuole misurare.

**Motivazione RF-E10.** Senza questo vincolo si può costruire l'esperimento in cui una variante cerca fra 50 documenti e l'altra fra 200, e concludere che il secondo embedder è peggiore quando stava soltanto affrontando più distrattori.

### 4.8 Osservazione del retrieval

| ID | Requisito |
|---|---|
| RF-O01 | Registrare **ogni chiamata** al tool di retrieval come entità distinta, con indice progressivo e query effettiva |
| RF-O02 | Registrare per ogni chiamata gli hit con rank, score e stadio (denso, sparso, fuso, reranked, finale) |
| RF-O03 | Distinguere tre insiemi: **recuperato** (unione di tutte le chiamate), **in contesto** (passato all'LLM), **citato** (dichiarato dall'agente) |
| RF-O04 | Calcolare le metriche di retrieval su un ambito configurabile fra i tre |

**Motivazione RF-O01/O03.** Un agente agentico effettua più chiamate con query riformulate. Le tre nozioni rispondono a domande diverse: *l'indice conteneva l'evidenza?* (recuperato), *l'agente ha sprecato contesto?* (in contesto), *l'attribuzione è corretta?* (citato). Un fallimento con recall pari a 1 è un problema di generazione; con recall pari a 0 è un problema di retrieval. Senza questa separazione non si sa dove intervenire. Vedere le riformulazioni successive è inoltre uno degli strumenti di debug più utili sugli agenti.

### 4.9 Valutazione

| ID | Requisito |
|---|---|
| RF-V01 | Calcolare le metriche di retrieval a livello documento e, quando disponibile il legame, a livello chunk |
| RF-V02 | Valutare la correttezza delle risposte con **LLM-as-judge** configurabile |
| RF-V03 | Il judge è un componente **versionato** (modello + prompt + rubrica); cambiarlo non deve alterare i punteggi storici |
| RF-V04 | Supportare la **verifica umana** con code di annotazione |
| RF-V05 | Misurare l'accordo fra judge automatico e annotazione umana su un sottoinsieme di calibrazione |
| RF-V06 | Escludere dal denominatore delle metriche di retrieval le domande con evidenza "non trovata" o con documenti gold fuori dallo snapshot, **dichiarando il fatto e il motivo nel risultato** |
| RF-V07 | Mantenere le domande "non trovate" nelle metriche di risposta, dove un rifiuto corretto è il comportamento atteso |
| RF-V08 | Aggregare per run e variante con media, deviazione standard, mediana, p95 e intervallo di confidenza |
| RF-V09 | Aggregare per slice (tag, tipo di evidenza, documento, sorgente) |
| RF-V10 | Segnalare se la differenza fra due varianti è statisticamente significativa |

**Motivazione RF-V06.** Una metrica va sempre presentata come *recall@5 = 0,78 (su 142 domande su 153)*. Trattare le domande escluse come "nessun documento rilevante" penalizzerebbe il sistema per un limite dell'annotazione, e chi legge la dashboard trarrebbe conclusioni false sul proprio retriever.

**Motivazione RF-V10.** Con LLM non deterministici, un delta del 2% può essere rumore. Dichiarare un "vincitore" senza test di significatività è la modalità di fallimento più comune di queste piattaforme.

### 4.10 Presentazione dei risultati

| ID | Requisito |
|---|---|
| RF-L01 | Leaderboard delle varianti, **raggruppata per configurazione di chunking** |
| RF-L02 | Dentro un gruppo: tutte le metriche, incluse quelle a livello chunk |
| RF-L03 | Fra gruppi diversi: solo metriche a livello documento, con la ragione esplicitata |
| RF-L04 | Confronto affiancato di due varianti domanda per domanda |
| RF-L05 | Drill-down da una metrica aggregata alla singola esecuzione, con risposta, chunk recuperati e traccia |
| RF-L06 | Evidenziare le domande in cui le varianti divergono maggiormente (candidate all'ispezione manuale) |
| RF-L07 | Esportare i risultati in CSV |
| RF-L08 | Rendere visibile lo **snapshot di corpus** di ogni risultato e impedire il confronto implicito fra snapshot diversi |

---

## 5. Requisiti tecnici

### 5.1 Stack

| Livello | Tecnologia | Ruolo |
|---|---|---|
| Orchestrazione | **Temporal** | esecuzione asincrona, retry, resume, idempotenza |
| Osservabilità e valutazione | **Langfuse** | trace, span, dataset run, score dei judge, code di annotazione |
| Persistenza strutturata | **PostgreSQL** | entità, relazioni, aggregazioni, leaderboard |
| Persistenza vettoriale | Pinecone / Qdrant / pgvector | pluggable via profilo di vector store |
| Storage oggetti | S3-compatibile | documenti sorgente, output di parsing, payload voluminosi |

### 5.2 Orchestrazione — layout dei workflow

```
IngestSourceSelectionWorkflow(selection_id)
 ├─ activity: enumerate_source                    → elenco dei file da acquisire
 └─ IngestDocumentWorkflow(source_ref)            [child, parallelo, limitato]
     └─ activity: fetch_and_hash                  → dedup, upload su object storage

MaterializeChunksWorkflow(document_ids, chunking_configuration_id)
 └─ ProcessDocumentWorkflow(document_id, config)  [child per documento, parallelo]
     ├─ activity: parse    → parsing_result   [cache su document + parsing_profile]
     └─ activity: chunk    → chunk_result + chunks
                            [cache su document + chunking_configuration]

BuildIndexWorkflow(index_build_id)
 ├─ activity: resolve_chunks(snapshot, chunking_configuration)   → chunk da indicizzare
 ├─ activity: embed_batch(...)                    [task queue dedicata]
 └─ activity: upsert_to_store(...)

RunExperimentWorkflow(run_id)
 └─ RunVariantWorkflow(run_id, variant_id)        [child per variante]
     └─ AnswerQuestionWorkflow(...)               [child per domanda × ripetizione]
         ├─ activity: invoke_answer_system        → esecuzione, chiamate e hit di retrieval
         ├─ activity: compute_retrieval_metrics
         ├─ activity: push_trace_to_langfuse
         └─ activity: run_or_trigger_evals
     └─ activity: aggregate_metrics

TransferDatasetWorkflow(transfer_job_id)
 └─ activity: rank_candidates(question)           → candidati ordinati, in attesa di conferma
```

La creazione di una configurazione di popolamento (RF-P09) è la composizione di `MaterializeChunksWorkflow` e `BuildIndexWorkflow`, preceduta dai get-or-create di snapshot e configurazione di chunking. `MaterializeChunksWorkflow` prende un elenco di documenti e non uno snapshot, così lo stesso workflow serve l'anteprima su un singolo documento (RF-P08) e la materializzazione di un corpus intero.

| ID | Requisito |
|---|---|
| RT-O01 | Workflow ID deterministici: Temporal rifiuta i duplicati, garantendo idempotenza e resume senza logica applicativa |
| RT-O02 | I payload dei workflow contengono **riferimenti** allo storage, mai il contenuto dei documenti |
| RT-O03 | Task queue separate per profilo di risorsa (parsing, embedding, chiamate LLM, accesso alle sorgenti) |
| RT-O04 | Heartbeat con dettagli sulle activity lunghe (parsing di PDF grandi, batch di embedding, enumerazione di sorgenti estese) per riprendere a metà |
| RT-O05 | `continue_as_new` sui workflow con molti child |
| RT-O06 | Retry differenziate: errori transitori (rate limit, timeout, indisponibilità della sorgente) con backoff; errori permanenti (formato non supportato, schema invalido) non ritentati, l'unità di lavoro è marcata fallita e il run prosegue |
| RT-O07 | Lo stato autorevole di avanzamento è in Temporal; in database si mantiene una copia denormalizzata per la reattività della UI |

**Motivazione RT-O06.** Un run da 500 domande non deve interrompersi per una domanda malformata, né un import da 200 file per un PDF corrotto.

### 5.3 Osservabilità e valutazione — confine con Langfuse

| Cosa | Dove risiede | Motivo |
|---|---|---|
| Corpus, chunk, gold, esperimenti, varianti | PostgreSQL | struttura relazionale, join, riproducibilità |
| Trace, span, prompt, I/O per step | Langfuse | è ciò che fa meglio |
| Dataset e dataset run | Langfuse, con identificativi replicati in PostgreSQL | riuso di eval e code di annotazione |
| Score dei judge e annotazioni umane | Langfuse **+ copia in PostgreSQL** | serve il join per leaderboard e slicing |
| Metriche di retrieval | PostgreSQL (calcolate), pubblicate su Langfuse come score | logica proprietaria basata sui legami confermati |
| Aggregati e leaderboard | PostgreSQL | |

| ID | Requisito |
|---|---|
| RT-L01 | Un dataset Langfuse per QA set; il nome del dataset run identifica esperimento, variante e run |
| RT-L02 | I metadati della trace includono variante, indice, profilo di parsing e configurazione di chunking, per lo slicing anche dentro Langfuse |
| RT-L03 | Gli score prodotti da Langfuse sono replicati in PostgreSQL via webhook, con poller di riconciliazione come rete di sicurezza |
| RT-L04 | Span gerarchici per ogni chiamata di retrieval e generazione |

**Nota.** Il mirroring degli score è una duplicazione consapevole: interrogare l'API Langfuse a ogni caricamento della dashboard renderebbe la UI lenta e impedirebbe aggregazioni per profilo di parsing o per sorgente documentale.

**Da verificare prima dell'implementazione.** I nomi degli endpoint per i dataset run e la disponibilità dei webhook sugli score variano fra versioni di Langfuse; vanno confermati sulla documentazione della versione che si intende adottare.

### 5.4 Sicurezza e configurazione

| ID | Requisito |
|---|---|
| RT-S01 | Credenziali dei servizi esterni e delle sorgenti documentali da variabili d'ambiente; mai persistite in chiaro nel database |
| RT-S02 | Il token di retrieval passato agli agenti è **scoped alla singola esecuzione** e a scadenza breve |
| RT-S03 | Nessun sistema di login in v1; la piattaforma è assunta in rete privata |
| RT-S04 | Le connessioni alle sorgenti memorizzano solo un **riferimento** alla credenziale, non il suo valore |

### 5.5 Matching testuale e semantico (ruolo ausiliario)

Il matching **non decide** la rilevanza. Serve a tre scopi:

1. **Ordinare i candidati** nel wizard di trasferimento
2. **Ancorare durevolmente** l'evidenza: se il corpus viene riparsato integralmente, la citazione testuale è l'unica descrizione di *cosa* fosse l'evidenza, indipendente da qualsiasi identificativo
3. **Fornire contesto al judge**: l'evidenza attesa in forma testuale, indipendente dai chunk

| ID | Requisito |
|---|---|
| RT-M01 | Normalizzazione del testo prima del confronto lessicale: forma unicode canonica, legature, virgolette tipografiche, trattini, de-sillabazione a fine riga, separatori di tabella, collasso degli spazi |
| RT-M02 | Il segnale semantico usa l'embedder della configurazione **di destinazione**: embedding di modelli diversi non sono confrontabili |
| RT-M03 | La ricerca dei candidati è ristretta ai documenti gold, quindi il pool è piccolo e può essere ordinato integralmente senza fallback |
| RT-M04 | Le soglie delle fasce di confidenza e i pesi dei tre segnali sono configurabili e tarabili per corpus |

**Nota su RT-M03.** Filtrando per documento, i candidati sono decine o al più centinaia di chunk. Non serve una logica a due livelli (top-k e poi ricerca estesa): si ordina tutto il pool. Il vector DB serve a rendere veloce il primo passaggio, non a limitare l'insieme.

### 5.6 Prestazioni e scalabilità

| ID | Requisito |
|---|---|
| RT-P01 | Le entità di esecuzione crescono come domande × varianti × ripetizioni × top-k: prevedere il partizionamento fin dall'inizio |
| RT-P02 | I payload grezzi delle risposte sono archiviati su object storage oltre una soglia di dimensione |
| RT-P03 | Vista materializzata per la leaderboard, aggiornata a fine run |
| RT-P04 | Concorrenza configurabile per esperimento e per import, con rispetto dei rate limit di provider e sorgenti |

### 5.7 Interfaccia utente

| ID | Requisito |
|---|---|
| RT-U01 | I form dei parametri dei componenti e delle sorgenti sono **generati dallo schema dichiarato**, non codificati |
| RT-U02 | Il confronto fra varianti è raggruppato per configurazione di chunking; selezionare varianti di gruppi diversi **cambia la vista** (solo metriche documentali) invece di produrre un errore. Varianti su snapshot di corpus diversi non sono confrontabili: la UI le separa e ne dichiara il motivo |
| RT-U03 | La UI di annotazione e quella di trasferimento condividono lo stesso componente di navigazione dei chunk |
| RT-U04 | Visualizzazione del documento nativa per formato, con i chunk come unità selezionabili |
| RT-U05 | Indicatore di avanzamento in tempo reale per import, indicizzazione ed esperimenti |
| RT-U06 | Dalla scheda di un documento si può risalire all'originale nel sistema di provenienza |

---

## 6. Modello concettuale dei dati

Il modello si articola in sette blocchi. Le entità sono descritte per **ruolo e invarianti**; il dettaglio delle colonne è demandato alla fase implementativa.

### 6.1 Sorgenti e acquisizione

| Entità | Ruolo |
|---|---|
| **Connessione a sorgente** | configurazione riusabile verso un sistema documentale (tipo, endpoint, root, riferimento alla credenziale) |
| **Selezione di import** | cosa importare da una connessione: percorsi, filtri, ricorsione; è l'unità ri-sincronizzabile |
| **Esecuzione di import** | un passaggio di acquisizione, con esito per file e riepilogo |
| **Provenienza documento** | lega un documento alla connessione e all'URI originale; **relazione molti-a-molti**: lo stesso contenuto può provenire da più sorgenti |

### 6.2 Corpus e documenti

| Entità | Ruolo |
|---|---|
| **Documento** | il file, identificato per hash del contenuto; **l'identità non dipende dal parse** |
| **Corpus** | raggruppamento logico e **mutabile** di documenti (es. un'area organizzativa); evolve nel tempo |
| **Snapshot di corpus** | selezione immutabile e congelata di documenti del corpus; definisce lo **spazio di ricerca** di un indice ed è deduplicata per composizione |

**Invariante.** Un documento appartiene a uno o più snapshot ma non viene mai modificato. Un file aggiornato alla sorgente produce un nuovo documento.

**Invariante.** Il corpus è libero di cambiare: aggiungere o rimuovere documenti non altera gli snapshot esistenti né i dataset di valutazione già annotati. Quello che fa fede per i confronti sono gli snapshot su cui gli esperimenti sono stati eseguiti.

**Nota.** Lo stato di acquisizione (scaricato, hashato, salvato) è una proprietà del documento, non della sua appartenenza a un corpus. Lo stato di parsing e chunking non è una proprietà del documento perché esiste **per configurazione**: vive sull'artefatto corrispondente.

### 6.3 Pipeline

| Entità | Ruolo |
|---|---|
| **Profilo di parsing / chunking / embedding / vector store** | configurazioni riusabili, ciascuna con hash di configurazione |
| **Configurazione di chunking** | la coppia (profilo di parsing, profilo di chunking); è la **dimensione di confrontabilità** del gold a livello chunk |
| **Risultato di parsing** | output di un parser su **un documento**; chiave di cache: documento + profilo di parsing |
| **Risultato di chunking** | output di un chunker su **un documento**; chiave di cache: documento + configurazione di chunking |
| **Chunk** | unità indicizzabile, con testo, modalità e posizione; appartiene al risultato di chunking di un documento |
| **Build di indice** | la configurazione di popolamento del vector DB: snapshot × configurazione di chunking × embedding × vector store; identificata da un'impronta dell'intera catena |

**Invariante.** Ogni artefatto è immutabile e riusabile: variare un parametro a valle non invalida gli stadi a monte, e variare la composizione di uno snapshot non invalida i chunk dei documenti in comune.

**Invariante.** L'identità di un chunk dipende da (documento, configurazione di chunking, posizione) e da nient'altro. È ciò che rende gratuita la crescita del corpus (RF-C05) e che ancora il gold alla sola dimensione il cui cambiamento ha costo umano (§3.1).

**Nota.** L'insieme dei chunk indicizzati non è un'entità materializzata: è determinato dallo snapshot e dalla configurazione di chunking di una build di indice.

**Nota.** I vettori risiedono nel vector store esterno; il database mantiene solo il mapping e i metadati.

### 6.4 Componenti

| Entità | Ruolo |
|---|---|
| **Componente** | identità logica (tipo + chiave), per esempio `parser/azure_di` |
| **Versione di componente** | implementazione concreta: runtime (`builtin` o `http`), endpoint, schema dei parametri, capability |
| **Sistema di risposta** e sue versioni | caso particolare: identifica un fornitore di risposta con la sua configurazione |

### 6.5 Dataset di valutazione

Questa è la parte in cui si concretizza la decisione di §3.1.

| Entità | Ruolo | Ambito |
|---|---|---|
| **QA set** e suo **snapshot** | insieme di domande; lo snapshot è congelato prima dell'esecuzione | riusabile su qualunque snapshot di corpus che contenga i documenti gold |
| **Domanda** | testo, allegati, tag, flag di risposta possibile | **immutabile, condivisa** fra tutte le configurazioni |
| **Risposta attesa** | una o più risposte accettabili, con rubrica per il judge | condivisa |
| **Documento gold** | lista dei file che contengono la risposta | **stabile fra tutte le configurazioni** |
| **Citazione gold** | ancora testuale dell'evidenza | condivisa; **non usata per decidere la rilevanza** |
| **Legame di evidenza** | quali chunk contengono la risposta, con stato (da esaminare / confermato / non trovato) | **uno per configurazione di chunking** |
| **Chunk del legame** | i chunk specifici, con grado di rilevanza e flag di sufficienza | per configurazione |

**Invariante critica.** Un legame assente e uno con stato "non trovato" sono cose diverse: il primo significa *non ancora esaminato*, il secondo *verificato, l'evidenza non esiste in questa configurazione*. Solo il secondo consente di calcolare il tetto teorico di recall in modo interpretabile.

**Invariante.** Il legame di evidenza dipende dalla configurazione di chunking e **non** dallo spazio di ricerca: un gold confermato resta valido al variare di embedder, vector store e composizione dello snapshot. La copertura del gold da parte dello snapshot è una verifica separata, effettuata al momento dell'esperimento (RF-E09).

### 6.6 Trasferimento

| Entità | Ruolo |
|---|---|
| **Job di trasferimento** | da una configurazione di chunking a un'altra, per un QA set; traccia l'avanzamento |
| **Candidato** | chunk proposto per una domanda, con punteggio combinato, fascia di confidenza e flag di pre-selezione |

**Invariante.** I candidati sono **proposte**: nessuno diventa evidenza gold senza conferma umana.

**Nota.** Il trasferimento avviene fra configurazioni di chunking e non coinvolge alcuno snapshot: i candidati sono ristretti ai documenti gold della domanda, i cui chunk esistono per ogni configurazione indipendentemente da ciò che è indicizzato.

### 6.7 Esperimenti, esecuzione e valutazione

| Entità | Ruolo |
|---|---|
| **Esperimento** | tipo (retrieval o Q&A), snapshot di corpus e QA set, ripetizioni, ambito di calcolo del retrieval |
| **Variante** | indice × profilo di retrieval × versione del sistema di risposta |
| **Run** | una esecuzione dell'esperimento, con snapshot integrale della configurazione |
| **Esecuzione** | una domanda × variante × ripetizione; unità di idempotenza e di resume |
| **Chiamata di retrieval** | una invocazione del tool; un agente agentico ne produce N per esecuzione |
| **Hit di retrieval** | un chunk restituito, con rank, score, stadio e i flag di rilevanza calcolati ai due livelli |
| **Definizione di metrica** | chiave, famiglia (retrieval / risposta / efficienza), livello, direzione, aggregazione |
| **Valutatore** | deterministico, LLM-as-judge (versionato per prompt) o umano |
| **Valutazione** | il punteggio su una singola esecuzione, con flag di esclusione e motivo |
| **Annotazione umana** | verifica manuale, con annotatore ed eventuale commento |
| **Aggregato di metrica** | per run, variante, metrica e slice; include numerosità effettiva **e numerosità esclusa** |

**Invariante di confrontabilità.** La configurazione di chunking di una variante è derivabile dalla sua build di indice, e così lo spazio di ricerca. Il confronto ha due dimensioni:

- **dentro un esperimento** lo snapshot di corpus è fissato (RF-E10), quindi due varianti sono confrontabili a livello chunk **se e solo se** condividono la configurazione di chunking, e sempre a livello documento; è il caso normale;
- **fra esperimenti diversi** serve in più lo stesso snapshot di corpus, perché i distrattori fanno parte della misura.

La UI applica il vincolo come raggruppamento (RT-U02).

---

## 7. Metriche

### 7.1 Retrieval

| Metrica | Livello documento | Livello chunk |
|---|---|---|
| recall@k | sì | sì (con legame confermato) |
| precision@k | sì | sì |
| MRR | sì | sì |
| hit rate | sì | sì |
| nDCG@k | limitato | sì (usa la rilevanza graduata) |
| rank del primo rilevante | sì | sì |

Per gli esperimenti Q&A le metriche si calcolano sull'ambito indicato nell'esperimento:

- **recuperato** — unione degli hit di tutte le chiamate. *L'indice conteneva e ha restituito l'evidenza?*
- **in contesto** — ciò che è stato effettivamente passato all'LLM. *L'agente ha sprecato contesto?*
- **citato** — ciò che l'agente dichiara di aver usato. *L'attribuzione è corretta?*

### 7.2 Risposta

| Metrica | Valutatore |
|---|---|
| correttezza della risposta | LLM-as-judge con rubrica, o verifica umana |
| aderenza al contesto (faithfulness) | LLM-as-judge sul contesto recuperato |
| completezza | LLM-as-judge |
| accuratezza del rifiuto | deterministica, su domande senza risposta possibile |
| corrispondenza esatta o numerica | deterministica, su valore normalizzato |
| precisione e recall delle citazioni | deterministica, se il sistema dichiara le citazioni |

### 7.3 Efficienza

Latenza totale e per fase (p50, p95), time-to-first-token, numero di chiamate al retrieval, numero di tool call.

### 7.4 Robustezza

Varianza fra ripetizioni, tasso di errore, tasso di timeout.

---

## 8. Flussi operativi

### 8.1 Percorso completo

```
1. ACQUISIZIONE   connetti la sorgente (SharePoint, S3, disco, upload)
                  seleziona cosa importare -> documenti
                  raggruppa i documenti in un corpus (es. "reparto cyber")

2. PIPELINE       scegli profilo di parsing x profilo di chunking
                  -> configurazione di chunking
                  -> parse result + chunk result PER DOCUMENTO
                  ispeziona i chunk anche su un solo documento di prova

3. AUTHORING      scrivi domanda + risposta attesa
                  seleziona i chunk gold navigando il documento
                  -> documenti gold e citazione derivati automaticamente
                  -> legame di evidenza confermato (per configurazione di chunking)

4. FREEZE         snapshot del QA set: il dataset e' congelato

5. POPOLAMENTO    seleziona i documenti del corpus -> snapshot di corpus
                  scegli embedder x vector store -> indice
                  (snapshot e indice sono deduplicati: ripetere non ricostruisce)

6. ESPERIMENTI    varia embedder, vector db, top-k, strategia, reranker, agente
   LIBERI         -> NESSUN trasferimento necessario
                  -> tutte le metriche, confronti pienamente validi

7. IL CORPUS      arrivano 50 documenti nuovi -> nuovo snapshot
   CRESCE         -> chunking solo dei 50 nuovi, automatico
                  -> eval dataset ancora valido: NESSUNA conferma umana
                  -> confrontabile con i run precedenti solo a parita' di snapshot

8. CAMBIO PARSER  nuova configurazione di chunking -> job di trasferimento
   O CHUNKER      -> candidati ordinati -> conferme umane -> nuovi legami
                  -> verso le configurazioni precedenti restano confrontabili
                     solo le metriche documentali
```

**Punto chiave.** Il passaggio 8 è **raro e deliberato**, ed è l'unico con costo umano. Un utente sceglie il parser una volta e poi itera per settimane sui passaggi 5-7, che sono gratuiti.

**Ordine non vincolante.** I passaggi 2-3 e 5 sono indipendenti: si può popolare il vector DB prima di annotare, o annotare prima di indicizzare. L'unico vincolo è al passaggio 6, dove l'esperimento verifica che i documenti gold delle domande siano contenuti nello snapshot indicizzato (RF-E09).

### 8.2 Percorso rapido senza annotazione fine

Per il confronto fra parser diversi esiste un percorso a costo quasi nullo: annotare **solo i documenti gold** (un CSV di due colonne) e confrontare le configurazioni su recall, precision e MRR a livello documento. È una misura grossolana ma discrimina bene fra un parser che estrae correttamente e uno che perde metà del contenuto. Il gold a livello chunk diventa un raffinamento successivo, applicato solo alle domande in cui i sistemi divergono in modo sospetto.

---

## 9. Roadmap suggerita

### Milestone 1 — Acquisizione e fondamenta
Registry dei componenti, connettori per upload e filesystem, ingestion, corpus, parsing e chunking configurabili per documento, ispezione dei chunk. Workflow Temporal per l'acquisizione.

### Milestone 2 — Sorgenti remote
Connettori S3 e SharePoint, navigazione da UI, selezioni ri-sincronizzabili, deduplicazione cross-sorgente, provenienza.

### Milestone 3 — Indicizzazione e retrieval
Profili di embedding e vector store, snapshot di corpus deduplicati, configurazioni di popolamento del vector DB, tool di retrieval strumentato, esperimenti di puro retrieval con metriche a livello documento.

### Milestone 4 — Authoring
UI di annotazione con selezione dei chunk, legami di evidenza, import/export JSONL/CSV, metriche a livello chunk.

### Milestone 5 — Q&A end-to-end
Contratto del sistema di risposta, tracciamento multi-chiamata del retrieval, integrazione Langfuse, LLM-as-judge, verifica umana.

### Milestone 6 — Confronto e trasferimento
Leaderboard con raggruppamento, confronto affiancato, wizard di trasferimento con i tre segnali, test di significatività.

### Estensioni successive
Formati aggiuntivi (TXT, MD, XLSX, PPTX), sorgenti aggiuntive (Confluence, Google Drive, database documentali), modello dei costi, multi-tenancy e autenticazione, tassonomia strutturata delle domande, conversazioni multi-turno, gate di regressione per CI, runtime a container per componenti non fidati.

---

## 10. Rischi e punti aperti

| Rischio | Impatto | Mitigazione |
|---|---|---|
| Il costo umano del trasferimento scoraggia l'esplorazione di parser diversi | alto | candidati ordinati con tre segnali; trasferimento parziale; percorso rapido a livello documento |
| Confronti fra run su snapshot di corpus diversi letti come confronti validi | medio | snapshot deduplicati per composizione; snapshot fissato per esperimento; separazione e dichiarazione in leaderboard (RF-L08) |
| Selezione parziale dei documenti che esclude i gold di alcune domande | medio | verifica di copertura alla creazione dell'esperimento, con esclusione dichiarata anziché silenziosa (RF-E09) |
| L'annotazione è faticosa e i dataset restano vuoti | alto | UI di selezione dei chunk curata; import da file; generazione assistita delle domande |
| Credenziali delle sorgenti aziendali con permessi troppo ampi | medio | credenziali dedicate in sola lettura, ristrette alle librerie necessarie |
| Header, footer e indici inquinano i top-k di ogni domanda | medio | filtro nel profilo di chunking, attivo di default |
| Il judge LLM ha bias sistematici | medio | golden set di calibrazione; misura dell'accordo con l'annotazione umana |
| Le tabelle sono il punto debole di tutta la catena | medio | metriche sliceate per tag; il fallimento del matcher in trasferimento segnala il problema all'utente |
| Documenti aggiornati alla sorgente creano proliferazione di versioni | basso | ri-sincronizzazione esplicita e non automatica; visibilità delle versioni per documento |
| Deriva delle API Langfuse fra versioni | basso | verificare endpoint e webhook sulla versione adottata prima di implementare |
| Crescita quadratica delle entità di esecuzione | basso | partizionamento fin dall'inizio; archiviazione dei payload grezzi |

### Decisioni da prendere prima dell'implementazione

1. **Pesi e soglie dei tre segnali** nel wizard di trasferimento: da tarare sul corpus reale, non su valori di default.
2. **Ambito di retrieval predefinito** per gli esperimenti Q&A: *recuperato* è il più informativo sulla qualità dell'indice, *citato* sulla qualità dell'agente.
3. **Granularità della configurazione di chunking usata per l'annotazione**: chunk più fini rendono l'evidenza più precisa ma l'annotazione più laboriosa. La granularità scelta è il tetto di precisione di tutte le metriche a livello chunk, e cambiarla dopo comporta rifare l'annotazione.
4. **Se le citazioni dell'agente sono obbligatorie** nel contratto: opzionali riducono l'attrito di integrazione, obbligatorie sbloccano le metriche di attribuzione.
5. **Politica di ri-sincronizzazione**: manuale su richiesta, oppure schedulata per selezione.

---

## Appendice A — Nota metodologica sulla misura di portabilità

La decisione di §3.1 si basa su una misura condotta con uno strumento dedicato che confronta N parser su un corpus reale, campionando citazioni stratificate per tipo di contenuto e verificando se ciascuna è ritrovabile nell'output degli altri parser.

Lo strumento resta utile oltre questa decisione:

- **tarare le soglie** delle fasce di confidenza del wizard sul corpus specifico
- **valutare un nuovo parser** prima di integrarlo, verificando quanto diverge da quelli già in uso
- **stimare il costo di un trasferimento**: se il recovery previsto è alto, il wizard richiederà poche conferme manuali

Vale la pena rieseguirlo quando il corpus cambia in modo sostanziale o quando si valuta l'adozione di un parser di categoria diversa (per esempio LLM-based, per cui il matching per citazione è concettualmente inapplicabile perché il testo può essere riformulato anziché estratto).
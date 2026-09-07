# 🏆 Asta Fantacalcio

App per condurre dal vivo l'asta del fantacalcio (modalità **Classic**) con gli amici.

> **Nuovo qui?** Vai al **[QUICKSTART](QUICKSTART.md)**: sono venti minuti e non serve saper
> programmare. Questo README è il manuale completo, si legge dopo.
>
> Nella repo c'è il codice, non i dati: listone, statistiche e articoli te li procuri tu e li
> **carichi dall'app**. Vedi [I dati che devi procurarti](#i-dati-che-devi-procurarti).

I rilanci si fanno a voce, come sempre. L'app fa da **registro autoritativo**: dice chi è
il calciatore in asta, registra l'aggiudicazione, aggiorna crediti e listone e mostra tutto
in tempo reale sul telefono dei partecipanti — anche in una stanza senza wifi, perché ognuno
si collega con i propri dati.

Sei pagine, una barra di navigazione in alto:

| Pagina | Chi la vede | Cosa mostra |
|---|---|---|
| 🏆 **Tabellone** | tutti | Chi è in asta ora e la griglia delle squadre |
| 🔎 **Listone** | tutti | I calciatori ancora liberi, con ricerca |
| 📋 **Formazioni** | tutti | Moduli e probabili formazioni, con i già presi sbiaditi |
| 🧤 **Portieri** | tutti | Chi para, chi va preso in coppia e la griglia degli incroci |
| 📜 **Aggiudicazioni** | tutti | Tutte le vendite, filtrabili per squadra e ruolo |
| 🎛️ **Gestione asta** | solo tu, con password | La conduzione dell'asta |

Le prime cinque sono pubbliche: è il link che giri agli amici. La **Soundbar** non è una
pagina: sta nella barra laterale, che si apre con la freccia in alto a sinistra.
In cima a ognuna c'è il riquadro del calciatore in asta, **identico su tutte**: chi sta
consultando il listone non si perde la chiamata in corso, né deve ricercarla in un formato
diverso da pagina a pagina.

---

## Indice

- [I dati che devi procurarti](#i-dati-che-devi-procurarti)
- [Come funziona](#come-funziona)
- [Regole implementate](#regole-implementate)
- [Avvio in locale](#avvio-in-locale)
- [Deploy per la serata](#deploy-per-la-serata)
- [Checklist della serata](#checklist-della-serata)
- [Guida alla serata](#guida-alla-serata)
- [Export per fantacalcio.it](#export-per-fantacalcioit)
- [Struttura del progetto](#struttura-del-progetto)
- [Sviluppo e test](#sviluppo-e-test)
- [Aggiornare il listone](#aggiornare-il-listone) — dall'app o da terminale
- [Una demo pubblica](#una-demo-pubblica-con-calciatori-inventati) — dati finti, niente database
- [Problemi frequenti](#problemi-frequenti)
- [Licenza, e di chi sono i dati](#licenza-e-di-chi-sono-i-dati)

---

## I dati che devi procurarti

Nella repo non c'è nessun dato di gioco, e non è una dimenticanza: il listone e le
statistiche sono di fantacalcio.it, le fasce d'asta e le gerarchie in porta vengono dagli
articoli di chi le ha scritte, gli stemmi sono marchi dei club. Nessuna di queste cose è mia
da regalare. Il codice sì.

**Si caricano dall'app**, in *Gestione asta → **Listone***: trascini i file e basta. Niente
Python, niente terminale, niente commit — restano nel tuo database e non passano mai da
GitHub. E non devi averli tutti insieme: carica quello che hai, torna quando hai il resto.

| File | Cosa aggiunge | Dove si prende |
|---|---|---|
| **`Quotazioni_Fantacalcio_Stagione_AAAA_AA.xlsx`** | i calciatori e le quotazioni | <https://www.fantacalcio.it/quotazioni-fantacalcio>, formato **Excel**, con il tuo account |
| `Statistiche_Fantacalcio_Stagione_AAAA_AA.xlsx` | rendimenti dell'anno scorso | <https://www.fantacalcio.it/statistiche-serie-a> — c'è anche la versione *aggiuntive portieri*: se le carichi entrambe vince quella, che ha i gol subiti |
| `difensori.md` | fasce d'asta dei difensori | [guida all'asta, difensori](https://www.sosfanta.com/guida-asta-fantacalcio/guida-asta-fantacalcio-2026-2027-tutti-consigli-fasce-chi-prendere/2/) |
| `centrocampisti.md` | fasce d'asta dei centrocampisti | [guida all'asta, centrocampisti](https://www.sosfanta.com/guida-asta-fantacalcio/guida-asta-fantacalcio-2026-2027-tutti-consigli-fasce-chi-prendere/3/) |
| `attaccanti.md` | fasce d'asta degli attaccanti | [guida all'asta, attaccanti](https://www.sosfanta.com/guida-asta-fantacalcio/guida-asta-fantacalcio-2026-2027-tutti-consigli-fasce-chi-prendere/4/) |
| `portieri.md` | le gerarchie in porta | [tutti i portieri, gerarchie](https://www.sosfanta.com/consigli-fantacalcio/portieri/fantacalcio-asta-tutti-portieri-gerarchie-seriea-venti-squadre-campionato/) |
| `probabili_formazioni.md` | moduli e titolarità | [formazioni tipo](https://www.sosfanta.com/asta-fantacalcio/seriea-tutte-formazioni-tipo-fantacalcio-2026-2027-asta-consigli-chi-prendere/) |
| `rigoristi_*.md` | chi tira i rigori | [tutti i rigoristi](https://www.sosfanta.com/asta-fantacalcio/fantacalcio-asta-tutti-rigoristi-seriea-venti-squadre-campionato/) |
| `corner_e_punizioni_*.md` | chi batte i piazzati | [specialisti dei piazzati](https://www.sosfanta.com/asta-fantacalcio/serie-a-2026-2027-tiratori-punizioni-corner-specialisti-fantacalcio-asta/) |
| `infortunati.md` | chi è fuori e per quanto | [tabella indisponibili](https://www.sosfanta.com/indisponibili-e-squalificati/tabella-indisponibili-seriea-fantacalcio-asta-infortunati-tempi-recupero-squalificati-diffidati/) |
| `griglia_portieri_*.json` | la griglia delle coppie | l'originale è su <https://app.fantalab.it/griglia-portieri>, ma è un'immagine: vedi [La griglia delle coppie](#la-griglia-delle-coppie) |

**Solo il primo è obbligatorio.** Tutto il resto è in più, e l'app è fatta per reggerne
l'assenza: manca un file, sparisce quella colonna o quella pagina, e il resto funziona.

Gli indirizzi degli articoli **contengono la stagione**: fra un anno saranno altri. Se uno non
risponde più, cerca il titolo — la pagina cambia numero, non nome. Lo stesso elenco, coi link,
è dentro l'app sotto *Gestione asta → Listone → 🔗 Dove si scaricano*: è lì che serve davvero,
non qui.

Gli articoli vanno salvati come file di testo, e non c'è bisogno di farlo a mano:
[Obsidian Web Clipper](https://chromewebstore.google.com/detail/obsidian-web-clipper/cnjifjpddelmedmihgijeibhnjfabmlf)
è un'estensione che salva una pagina web **già in markdown**, che è esattamente il formato che
l'app si aspetta. Scarichi, rinomini come dice la tabella, trascini nel pannello.

I file si riconoscono **dal nome**, e prima di generare il pannello ti scrive cosa ha
riconosciuto e cosa ha ignorato: un nome sbagliato si vede lì, non a metà asta. Il formato
che ogni articolo deve avere è descritto in [Aggiornare il listone](#aggiornare-il-listone),
sezione per sezione — lo script si arrangia con la prosa, non serve ripulirla.

Restano fuori dal caricamento solo i **file media**, che vanno messi nella repo se li vuoi:
gli **stemmi** in `static/loghi/` — si scaricano da
<https://football-logos.cc/italy/serie-a/>, istruzioni nel suo [README](static/loghi/README.md)
— e gli **audio** della Soundbar in `static/audio/`, che si pescano per esempio da
<https://www.myinstants.com/en/index/it/> (idem). Senza, restano il nome scritto e nessuna
Soundbar.

## Come funziona

L'asta è un **log di eventi append-only**. Ogni azione dell'admin (lettera estratta,
calciatore aggiudicato, salto, correzione) diventa un evento; lo stato — rose, crediti,
listone residuo — è sempre *ricalcolato* dal log da una funzione pura.

```
eventi (append-only) ──build_state()──► stato ──► vista admin · vista utente · export CSV
```

Da questa scelta discendono gratuitamente quattro cose:

| Serve… | Come lo ottiene |
|---|---|
| Undo / redo | Disattiva l'ultimo evento (`active = false`), non cancella nulla |
| Correggere un errore vecchio | Un evento di correzione che ne riferisce un altro |
| Vista utente sincronizzata | Confronto della "versione" del log, `(seq massimo, eventi attivi)` |
| Audit di fine serata | Il log *è* il verbale dell'asta |

**Tolleranza ai guasti di rete.** L'admin applica ogni azione subito in locale e accoda la
scrittura sul database. Se la connessione cade, l'asta continua: compare un banner rosso con
il numero di operazioni in sospeso, che partono da sole appena la rete torna.

## Perché pagine e non schede

Con `st.tabs` Streamlit esegue e rinfresca il contenuto di **tutte** le schede a ogni giro: il
listone da 533 righe verrebbe ricostruito ogni due secondi anche a chi sta guardando il
tabellone, su rete dati e su otto telefoni. Con `st.navigation` gira solo la pagina aperta.

Ogni pagina si rinfresca alla velocità con cui cambia davvero: il tabellone ogni 2 secondi,
le aggiudicazioni ogni 10, il listone ogni 15 — quest'ultimo ha un campo di ricerca, e
ridisegnarlo di continuo farebbe perdere i caratteri mentre si scrive. Il riquadro del
calciatore in asta sta in un frammento suo a 3 secondi, così resta reattivo ovunque.

## Regole implementate

- **Asta separata per ruolo**, nell'ordine P → D → C → A. Il passaggio di fase è manuale ed
  è **bloccato finché il reparto non è completo per tutte le squadre**: dopo il cambio di fase
  quei calciatori non sarebbero più acquistabili. Accanto al pulsante è scritto chi manca
  ancora.
- **Due modalità di chiamata**, scelte in configurazione:
  - *chiamata libera* — l'admin cerca il calciatore per nome e lo aggiudica;
  - *lettera random* — l'app estrae una lettera e scorre i calciatori in ordine alfabetico.
    Si estrae **solo fra le lettere che hanno ancora almeno un calciatore disponibile** nel
    ruolo in corso, senza ripetizioni; l'elenco si azzera al cambio di ruolo.
- **I saltati restano nel listone.** Non vengono ripresentati nella stessa passata di lettera,
  ma restano acquistabili in chiamata manuale, e la lettera si può riaprire con un pulsante.
- **Controllo crediti con riserva di slot.** L'offerta massima di una squadra è
  `crediti_residui − (slot_ancora_da_riempire − 1)`: così ogni squadra riesce sempre a
  completare la rosa. Il limite è mostrato accanto a ogni squadra e l'inserimento oltre soglia
  viene bloccato.
- **Limiti di rosa e di reparto** (default 25: 3P, 8D, 8C, 6A), configurabili.
- **Undo/redo** illimitato *più* modifica o annullamento di qualsiasi aggiudicazione già
  registrata, anche vecchia, con ricalcolo automatico di crediti e listone.
- Una squadra che ha il reparto pieno o i crediti insufficienti **sparisce dal selettore**:
  restano solo quelle a cui il calciatore si può davvero assegnare.

## La griglia delle squadre

Sia l'admin sia gli spettatori vedono la stessa griglia: **una colonna per squadra**, con in
cima la card dei crediti e sotto i reparti P/D/C/A allineati in orizzontale, così si confronta
a colpo d'occhio chi ha speso cosa.

| Elemento | Significato |
|---|---|
| `427 cr` | Crediti ancora disponibili |
| Barra verde sotto i crediti | Quota di budget non ancora spesa |
| `max 417` | Offerta massima ammessa adesso (con la riserva di 1 credito per slot) |
| `rosa 14/25` | Calciatori in rosa sul totale |
| I quattro numeri colorati | **Slot ancora liberi** per reparto — a reparto completo lo zero è smorzato |
| `%` sulla barra del reparto | Quota del budget totale già investita in quel reparto |
| Slot pieno | Nome del calciatore e prezzo pagato |

L'unico colore che porta informazione è quello del reparto; tutto il resto eredita il tema di
Streamlit, così la griglia resta leggibile e il CSS sta in una trentina di righe.

Ogni barra di reparto si clicca per **chiudere o riaprire** la sezione.

Sul Tabellone il pulsantino *La mia squadra*, in alto a destra, colora la propria colonna — sfondo verde,
anello e badge `TU` — così la si trova subito in mezzo alle altre. Una volta scelta il menu
sparisce e resta solo il pulsantino con il nome, che si riapre per cambiarla. È una scelta
locale del telefono di chi guarda e non tocca l'asta, e **resta anche cambiando pagina**: il
menu vive solo qui, quindi la squadra scelta è conservata in una chiave sua invece che in
quella del menu, che Streamlit butterebbe appena si va sul Listone.

Sotto la griglia, a squadra scelta, compare il riquadro **Copertura squadra** con gli
**stemmi di tutti e venti i club di Serie A**: pallino verde dove si è comprato, **rosso sullo
zero** dei club ancora scoperti, e nel tooltip i nomi presi da lì. L'ordine è lo stesso della
pagina Portieri — dalla difesa meno battuta dell'anno scorso alla più battuta, neopromosse in
fondo — così i pallini rossi in testa alla fila sono i club buoni da cui non si è ancora
pescato, e la fila si legge uguale nelle due pagine.

## Avvio in locale

Serve solo per sviluppare: **per usare l'app non serve installare niente**, vedi il
[QUICKSTART](QUICKSTART.md).

Serve Python 3.11+. Non ce l'hai e non vuoi installarlo? Da GitHub, *Code → Codespaces →
Create*: apre nel browser un VS Code già pronto, con Python e le dipendenze installate.

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

```bash
.venv/bin/streamlit run app.py
```

L'app si apre su <http://localhost:8501>. Senza `database_url` parte in **modalità demo**:
funziona tutto, ma lo stato vive solo in memoria e gli spettatori non vedono nulla — va bene
per provare, non per la serata.

## Deploy per la serata

Servono due account gratuiti: **Supabase** (database) e **Streamlit Community Cloud** (hosting).

### 1. Database

1. Crea un progetto su [supabase.com](https://supabase.com).
2. Copia la stringa di connessione: pulsante verde **Connect**, in alto nella pagina del
   progetto → riquadro **Transaction pooler** (porta `6543`). Ha questa forma:

   ```
   postgresql://postgres.abcdefghijkl:[YOUR-PASSWORD]@aws-0-eu-central-1.pooler.supabase.com:6543/postgres
   ```

   > ⚠️ Usa il pooler, non la *Direct connection*: quest'ultima è solo IPv6 e Streamlit Cloud
   > non la raggiunge.

   Poi due modifiche, in quest'ordine:

   - **lo schema**: `postgresql://` → `postgresql+psycopg://`;
   - **la password**: sostituisci `[YOUR-PASSWORD]`, parentesi quadre comprese, con quella
     scelta creando il progetto (persa? *Settings → Database → Reset database password*).

   > ⚠️ Se la password contiene `@ : / ? # [ ] %` o spazi, l'URL si spezza e l'errore parla di
   > un host inesistente, non della password. Due strade: scegliere una password di sole
   > lettere e numeri (24 caratteri sono già abbondanti), oppure codificarla con
   > `python scripts/check_db.py --encode` e incollare quella.

3. Metti la stringa in `.streamlit/secrets.toml` e **verifica prima della serata**:

   ```bash
   python scripts/check_db.py
   ```

   Controlla schema, porta, password e segnaposto rimasti, poi si collega davvero. La
   password non compare mai nell'output, nemmeno negli errori.

### 2. App

1. Fai il push di questa repo su GitHub.
2. Su [share.streamlit.io](https://share.streamlit.io) crea l'app puntando a `app.py`.
3. In *Settings → Secrets* incolla:

   ```toml
   admin_password = "una-password-lunga"
   database_url = "postgresql+psycopg://postgres.xxxx:PASSWORD@aws-0-....pooler.supabase.com:6543/postgres"
   ```

4. **Rendi pubblica l'app.** Da un repo privato Streamlit la deploya *privata*: gli spettatori
   dovrebbero autenticarsi con Google ed essere invitati uno per uno via email. Pulsante
   **Share** in alto a destra (o *Settings → Sharing*) → **This app is public and searchable**.

   > ⚠️ Da quel momento l'unica difesa di *Gestione asta* è `admin_password`. Verifica che sia
   > davvero nei secrets del cloud: apri `…/admin` in una finestra anonima e controlla che
   > chieda la password. Se invece compare l'avviso giallo, il secret non c'è.

5. Le pagine dell'app stanno tutte sullo stesso indirizzo, con un percorso diverso.
   Se l'app è `https://asta-xyz.streamlit.app`:

   | Indirizzo | Pagina | Per chi |
   |---|---|---|
   | `https://asta-xyz.streamlit.app/` | Tabellone | **è questo il link da girare agli amici** |
   | `https://asta-xyz.streamlit.app/listone` | Listone | tutti |
   | `https://asta-xyz.streamlit.app/formazioni` | Formazioni | tutti |
   | `https://asta-xyz.streamlit.app/portieri` | Portieri | tutti |
   | `https://asta-xyz.streamlit.app/aggiudicazioni` | Aggiudicazioni | tutti |
   | `https://asta-xyz.streamlit.app/admin` | Gestione asta | te, con la password |

   Agli amici basta il primo: dalla barra in alto raggiungono le altre pagine. Nella barra
   vedranno anche **Gestione asta** — è normale, ci entra solo chi ha la password.

   Tienila aperta in una scheda tua e manda loro il link della radice.

### 3. Prova generale (fallo davvero, il giorno prima)

Configura un'asta finta, aggiudica due o tre calciatori, apri il link utente **dal telefono
in rete dati e in finestra anonima** — è l'unico modo di vedere l'app come la vedranno loro,
senza la tua sessione — e verifica che si aggiorni. Poi azzera l'asta dalla scheda *Export*.

## Checklist della serata

Da fare **mezz'ora prima**, in quest'ordine. Sono tre minuti, e coprono i due modi in cui
l'app può presentarsi addormentata proprio mentre arrivano gli amici.

| | Cosa | Perché |
|---|---|---|
| 1 | Apri il link pubblico e aspetta che carichi | Streamlit Cloud mette in pausa le app inattive: il primo che apre aspetta mezzo minuto. Meglio che sia tu |
| 2 | `python scripts/check_db.py` | Dice subito se l'URL è a posto e se il database risponde |
| 3 | Se il database non risponde: dashboard Supabase → *Restore project* | I progetti gratuiti vanno in pausa dopo 7 giorni di inattività |
| 4 | `python scripts/build_players.py --check` | Esce con 1 se il JSON committato non è allineato ai file in `data/raw/` — probabili formazioni e infortunati cambiano fino all'ultimo |
| 5 | Apri `/admin`, entra con la password, guarda che non ci sia il banner *Modalità demo* | Con quel banner gli spettatori non vedono niente |
| 6 | Apri il link pubblico **dal telefono in rete dati, in finestra anonima** | È l'unico modo di vederlo come lo vedranno loro |

Durante l'asta, l'unica cosa da tenere d'occhio è l'orologio in cima al Tabellone: finché
avanza, i numeri sono di adesso.

## Guida alla serata

1. **Impostazioni** → modalità, crediti, limiti, nomi delle squadre → *Salva*.
2. **Asta** → *Inizia con i Portieri*.
3. Per ogni calciatore: *Estrai lettera* (o cercalo a mano), leggi ad alta voce nome, ruolo e
   squadra dal riquadro verde, lascia che rilancino, poi scegli **squadra** e **prezzo** e
   premi *Aggiudica*. Oppure *Salta*.
4. Quando il reparto è completo: *Passa ai Difensori*, e così via.
5. Alla fine: *Chiudi l'asta* → **Export** → scarica il CSV.

Se sbagli, `↩️ Annulla` torna indietro di un passo. Per un errore vecchio usa
**Rose e correzioni**: si può spostare un calciatore di squadra, cambiarne il prezzo o
rimetterlo nel listone.

> 💾 Scarica il **backup JSON** dalla scheda Export almeno una volta a metà asta. Da quel file
> si ricostruisce l'asta esatta, operazioni annullate comprese. Oppure lascia che se lo scarichi
> da solo: vedi qui sotto.

## Backup automatici

Nelle **Impostazioni**, prima di iniziare, c'è la spunta *Abilita i download automatici del
backup* e accanto i momenti in cui farlo partire:

| Momento | Quando scatta |
|---|---|
| Perdita di connessione | Il database non risponde e le operazioni restano in coda nel browser |
| Fine portieri | Quando parte la fase dei difensori |
| Fine difensori | Quando parte la fase dei centrocampisti |
| Fine centrocampisti | Quando parte la fase degli attaccanti |
| Fine asta | Alla chiusura dell'asta |

Il file finisce nella cartella dei download dell'admin, con il nome del momento e l'ora
(`backup_fine_portieri_20260901_203346.json`), e si ricarica dalla scheda *Export* →
*Ripristina da backup*. Ogni momento scarica **una volta sola** per sessione del browser: se
riapri la pagina a metà asta non ti ritrovi i backup dei reparti già chiusi. La perdita di
connessione fa eccezione, nel senso giusto: rete tornata e ricaduta è un'altra caduta, e si
merita il suo file.

Due cose da sapere:

- il primo download può far comparire la richiesta del browser di **consentire i download
  automatici** dal sito: rispondi di sì, altrimenti i successivi vengono bloccati in silenzio;
- se a cadere è la connessione dell'admin, e non solo quella del database, l'app non è
  raggiungibile e non parte niente. Il backup automatico copre il database che non risponde,
  non il computer che resta senza rete.

La spunta è spenta di default: un file che si scarica da solo va chiesto, non subito.

## Export per fantacalcio.it

Un unico CSV con tutte le squadre, nel formato richiesto dal sito:

```csv
$,$,$
Dildersbrough,6884,120
Dildersbrough,5585,80
```

Prima riga letterale `$,$,$`, poi `nome_squadra,id_giocatore,crediti_spesi`, UTF-8 senza BOM,
terminatori LF. Il formato è verificato da un test che rigenera **byte per byte** il file
d'esempio della lega. È scaricabile anche a metà asta.

## Stemmi delle squadre

Accanto al calciatore in asta compare lo stemma del suo club, e il logo della Serie A fa da
filigrana nel riquadro. Gli stemmi sono file in [`static/loghi/`](static/loghi/), uno per
squadra, con il nome della squadra minuscolo e senza spazi (`como.svg`, `hellasverona.svg`).
Se un file manca non succede niente: resta il nome scritto.

Sono **file statici**, non immagini incorporate nell'HTML. È una scelta di peso, non di
eleganza: il tabellone è 26 KB di HTML che il browser riceve a ogni cambiamento, e portarsi
dietro venti immagini in base64 a ogni giro costerebbe rete dati a tutti gli spettatori. Così
il browser le scarica una volta sola e le tiene in cache, e nell'HTML resta un `<img>` di
poche decine di byte.

`scripts/optimize_crests.py` ripulisce gli SVG dai metadati e **aggiunge il `viewBox` quando
manca**: senza quello l'immagine non si ridimensiona. Le istruzioni complete stanno in
[`static/loghi/README.md`](static/loghi/README.md).

Un posto dove trovarli è <https://football-logos.cc/italy/serie-a/>. Sono i **marchi dei club**:
il sito non ne rivendica la proprietà e ne consente l'uso da tifosi, editoriale e non
commerciale — non su prodotti in vendita, e non in modo da far credere a una collaborazione
ufficiale. Un'asta fra amici sta dalla parte buona di quel confine.

## La Soundbar

Nella **barra laterale**, non su una pagina sua: si apre con la freccia in alto a sinistra da
qualunque pagina, e chiusa non occupa niente. Il tormentone si fa partire *mentre* si guarda il
tabellone o si cerca un calciatore — cambiare pagina per premere un pulsante e poi tornare
indietro vorrebbe dire non premerlo mai.

Un pulsante per ogni audio, divisi fra calciatori/allenatori e voci del gruppo, più un pulsante
che ne pesca uno a caso. Il titolo si ricava dal nome del file — la prima parola è chi parla e
diventa l'etichetta verde — quindi per aggiungerne uno basta lasciarlo nella cartella giusta:
le regole sono in [`static/audio/README.md`](static/audio/README.md).

Gli audio te li metti tu: un posto comodo dove pescarli è
<https://www.myinstants.com/en/index/it/>, che ha già i tormentoni italiani pronti da
scaricare. Nella repo non ce n'è nessuno.

Il suono parte **nel browser**, senza passare dal server: è l'unico modo perché sia immediato e
perché funzioni sul telefono, dove un'esecuzione automatica dopo un giro di rete verrebbe
bloccata. I file si scaricano solo alla pressione del pulsante, uno alla volta, e poi restano
in cache: chi non tocca la Soundbar non scarica nulla.

## Struttura del progetto

```
├── CLAUDE.md                  # istruzioni per un assistente AI che apre la repo
├── app.py                     # entrypoint Streamlit (le quattro pagine)
├── data/
│   ├── players_2026_27.json   # listone generato e committato (533 calciatori)
│   ├── griglia_portieri_*.json # la griglia delle coppie, trascritta dall'immagine
│   └── raw/                   # xlsx ufficiali, gerarchie dei piazzati, CSV d'esempio
├── scripts/build_players.py   # xlsx → json, con la sola libreria standard
├── scripts/genera_demo.py     # listone finto e asta a meta', per la vetrina pubblica
├── scripts/optimize_crests.py # ripulisce e alleggerisce gli SVG degli stemmi
├── static/loghi/              # stemmi di Serie A, serviti come file statici
├── static/audio/             # audio della Soundbar (calcio/ e amici/)
├── sql/schema.sql             # DDL della tabella del log eventi
├── src/asta/
│   ├── domain/                # logica pura, zero dipendenze esterne
│   │   ├── models.py          #   ruoli, calciatori, impostazioni, squadre
│   │   ├── events.py          #   tipi di evento, undo/redo
│   │   ├── reducer.py         #   log eventi → stato dell'asta
│   │   ├── rules.py           #   validazioni (crediti, slot, ruolo)
│   │   ├── letters.py         #   sorteggio lettere e coda alfabetica
│   │   └── export.py          #   CSV fantacalcio.it e backup JSON
│   ├── data/                  # listone su file, log eventi su Postgres
│   ├── ui/                    # pagine e componenti Streamlit
│   │   ├── board.py           #   griglia squadre (una colonna per squadra)
│   │   ├── crests.py          #   stemmi delle squadre di Serie A
│   │   ├── formations.py      #   probabili formazioni, con i presi sbiaditi
│   │   ├── keepers.py         #   gerarchie in porta e griglia delle coppie
│   │   ├── admin.py           #   conduzione, impostazioni, correzioni, export
│   │   ├── autobackup.py      #   backup che si scarica da solo nei momenti critici
│   │   └── viewer.py          #   le pagine pubbliche che si auto-aggiornano
│   ├── service.py             # coda di scritture con retry
│   └── config.py              # secrets e variabili d'ambiente
└── tests/                     # 354 test, nessuno richiede un database
```

Il **dominio non importa né Streamlit né SQLAlchemy**: è testabile in isolamento e
sopravvivrebbe a un cambio di interfaccia.

## Sviluppo e test

```bash
.venv/bin/pytest
```

```bash
.venv/bin/ruff check . && .venv/bin/mypy
```

Cosa coprono i test:

| File | Cosa verifica |
|---|---|
| `test_reducer.py` | Derivazione dello stato, determinismo, eventi disattivati |
| `test_rules.py` | Crediti al limite esatto della riserva, limiti di reparto, correzioni |
| `test_letters.py` | Estrazione senza ripetizioni, lettere vuote escluse, salti, riapertura |
| `test_undo.py` | Dopo `azione → undo` lo stato è *identico* a quello di prima |
| `test_export.py` | CSV byte-esatto rispetto al file d'esempio, backup e ripristino |
| `test_service.py` | Coda locale, retry, riallineamento col database |
| `test_autobackup.py` | Momenti in cui il backup parte da solo, pagina che fa il download |
| `test_simulation.py` | **Asta intera** a 8 squadre sul listone vero, con salti e correzioni |
| `test_app_ui.py` | L'app vera in headless: configura, estrae, aggiudica, annulla; e le tre pagine pubbliche |
| `test_board.py` | HTML della griglia: slot, percentuali, evidenziazione, sanificazione |
| `test_crests.py` | Risoluzione degli stemmi: nomi normalizzati, file mancanti, URL |
| `test_soundbar.py` | Titoli ricavati dai nomi dei file, cartelle, HTML dei pulsanti |
| `test_stats.py` | Join delle statistiche per Id con controllo dei nomi, voci per ruolo, tabella |
| `test_setpieces.py` | Lettura delle gerarchie dei piazzati, aggancio per nome, lettere colorate |
| `test_formations.py` | Lettura delle formazioni tipo, titolari e ballottaggi, pagina |
| `test_injuries.py` | Lettura della tabella indisponibili, giornata di rientro, ambulanza |
| `test_keepers.py` | Gerarchie in porta, simmetria della griglia trascritta, pagina |
| `test_tiers.py` | Lettura delle fasce, aggancio per reparto, colonna e filtro |
| `test_check_db.py` | Diagnosi dell'URL del database: segnaposto, schema, password da codificare |
| `test_players.py` | Il listone committato coincide **byte per byte** con l'xlsx ufficiale |

## Aggiornare il listone

Ci sono due strade, e danno **lo stesso identico listone** — c'è un test che lo verifica.

### Dall'app, senza toccare niente

*Gestione asta → Impostazioni → **Carica il listone***: trascini i file e basta. Niente
Python, niente terminale, niente commit: il listone finisce nel database, e da lì l'app lo
riprende a ogni riavvio. È la strada da usare se stai solo aggiornando i dati.

I file si riconoscono **dal nome** — gli stessi nomi che userebbe lo script — e prima di
generare il pannello scrive cosa ha riconosciuto e cosa ha ignorato, così un nome sbagliato
si vede subito invece che a metà asta con la colonna delle fasce vuota. L'unico obbligatorio
è `Quotazioni_*.xlsx`; tutto il resto è facoltativo.

> Il listone caricato dall'app **vince** su quello committato in `data/`. Per tornare al file
> basta azzerare la riga dalla tabella `auction_listone` del database.

### Dalla riga di comando, quando vuoi vedere le differenze

Lo script mostra **cosa cambia** rispetto al listone attuale — nuovi, usciti, quotazioni,
trasferimenti — e ha `--check` per la checklist della serata. Serve Python.

1. copia l'xlsx scaricato da fantacalcio.it in `data/raw/` (sia le *Quotazioni* sia, se le
   vuoi, le *Statistiche* della stagione precedente);
2. lancia lo script, senza argomenti:

```bash
python scripts/build_players.py
```

Trova da solo il listone più recente in `data/raw/`, stampa **cosa cambia** rispetto al JSON
attuale (nuovi, usciti, quotazioni e trasferimenti), scrive `data/players_2026_27.json` e
ricorda il comando per committarlo. Poi `git push`: Streamlit Cloud si aggiorna da solo.

| Comando | A cosa serve |
|---|---|
| `python scripts/build_players.py` | Rigenera il JSON mostrando le differenze |
| `python scripts/build_players.py --dry-run` | Mostra le differenze **senza** scrivere |
| `python scripts/build_players.py --check` | Esce con 1 se il JSON non è aggiornato |

Lo script legge l'Excel con la sola libreria standard, esclude il foglio *Ceduti*, verifica
che gli Id siano unici e fallisce subito se l'intestazione è cambiata.

Se in `data/raw/` ci sono più file che corrispondono allo stesso glob vince **l'ultimo in
ordine di nome** — i file ufficiali finiscono con la stagione, quindi di norma è la più
recente — e lo script scrive a schermo quale ha usato e quali ha ignorato. La data di
modifica sarebbe più intuitiva ma in una copia appena clonata è quella del checkout, e la
scelta cambierebbe da macchina a macchina: il JSON committato viene confrontato byte per byte
con quello rigenerato, quindi la regola deve dare lo stesso risultato ovunque. Tenere un solo
file per tipo resta comunque la cosa più semplice.

### Le statistiche della stagione precedente

Se in `data/raw/` c'è anche un `Statistiche_*.xlsx`, i rendimenti finiscono nel listone e
compaiono nel riquadro *in asta ora* e nella tabella del listone — mai con gli acronimi del
file. Dove basta un simbolo c'è il simbolo (⚽ gol, 👟 assist, 🟨 e 🟥 i cartellini), uguale
nei due posti, col nome per esteso nel tooltip. Gli **autogol** non ci sono né di qua né di
là: non hanno mai spostato un'offerta.

Le colonne del listone, nell'ordine in cui si leggono:

| | | |
|---|---|---|
| Calciatore · Squadra | chi è | |
| Fascia · Titolarità | quanto vale | `F1`, `T`/`B` |
| Partite a voto · Media voto · Fantamedia | com'è andato | |
| ⚽ · 👟 · Rigori calciati · 🟨 · 🟥 | cosa ha prodotto | gol e assist |
| Rigorista · Corner · Punizioni | cosa batte | `R`, `C`, `P` colorate |
| 🚑 | se è fuori | giornata di rientro |

Fuori restano il **ruolo** (c'è il filtro, ripeterlo su ogni riga è una colonna sprecata) e
**gol subiti, rigori parati, autogol**: i primi due riguardano i portieri, che hanno la loro
pagina, e gli autogol non hanno mai spostato un'offerta. I numeri restano numeri, quindi
cliccando l'intestazione la tabella si ordina — è il modo più rapido per trovare il migliore
ancora disponibile.

Il join è sull'`Id`, ma un Id riciclato fra due stagioni assegnerebbe in silenzio le
statistiche di un altro calciatore: per questo lo script **confronta anche i nomi** e si
ferma se più del 5% non corrisponde. Le differenze di sola iniziale (`El Azzouzi` →
`El Azzouzi O.`, che il listone aggiunge quando spuntano omonimi) sono ammesse.

Il file copre solo chi ha giocato in Serie A, quindi i nuovi acquisti e i giovani restano
senza: le celle sono vuote e la card lo dice esplicitamente. `--no-stats` genera il listone
senza rendimenti.

Dimenticarsene non è un rischio: `--check` è anche un test (`test_players.py`), quindi un
Excel aggiornato e un JSON vecchio fanno diventare rossa la suite — e la CI a ogni push.
L'asta stessa mostra in **Gestione asta → Impostazioni** quanti calciatori ha caricato e da quale
file, così un controllo prima di iniziare basta un'occhiata.

### Rigori, corner e punizioni

Chi batte i piazzati vale bonus, e all'asta vale crediti. Se in `data/raw/` ci sono i due
articoli in markdown — `rigoristi_*.md` e `corner_e_punizioni_*.md`, copiati dal sito — lo
script li legge e attacca al listone tre lettere:

| Lettera | Piazzato |
|---|---|
| **R** | Rigori |
| **C** | Corner |
| **P** | Punizioni |

**Rossa** se è il battitore designato, **gialla** se se li gioca con altri, **assente** se le
gerarchie non lo nominano — che è diverso dal dire «non li batte». Le lettere compaiono nel
riquadro *in asta ora* (con il nome del piazzato accanto) e in tre colonne del listone, subito
dopo la squadra. Sotto la lettera c'è un numero nascosto, quindi cliccando l'intestazione
**R** la tabella mette in cima i rigoristi designati.

Come si decide il colore:

- **rigori**: l'articolo ha un paragrafo *Primo* e uno *Note*. Un solo nome in *Primo* è un
  rigorista designato e diventa rosso; se in *Primo* ce ne sono due o tre se li contendono, e
  allora nessuno è sicuro. Le alternative delle *Note* sono sempre gialle;
- **corner e punizioni**: l'articolo elenca i battitori «da chi ha più possibilità di calciare
  a chi ne ha meno», quindi il primo della fila è rosso e gli altri gialli.

Sono regole meccaniche, e su qualche squadra sono più severe della prosa (il Como ha Da Cunha
davanti a Kean, ma sono due nomi e restano gialli). **La fonte è l'articolo**: se non sei
d'accordo, modifica il markdown — il grassetto è quello che conta per i rigori, l'ordine
dell'elenco per corner e punizioni — e rilancia lo script.

Qui non c'è nessun `Id` da usare per il join: gli articoli sono prosa. L'aggancio è per nome
**dentro la rosa della squadra**, che restringe il campo a una trentina di calciatori e regge
le differenze di grafia («Seba Esposito» → `Esposito Se.`, «Nico Paz» → `Paz N.`). Ogni nome
che non si aggancia viene stampato come `ATTENZIONE`, così non sparisce in silenzio: di
solito è uno svincolato che nel listone non c'è. `--no-set-pieces` genera il listone senza.

### Le fasce d'asta

Tre articoli, uno per reparto — `difensori*.md`, `centrocampisti*.md`, `attaccanti*.md` — che
aprono ogni fascia con una riga di nomi:

```
**F1** - Dimarco, Wesley, Bremer, Bastoni, Molina N., Pavlovic, Solet
```

La sigla finisce accanto al calciatore nel riquadro *in asta ora*, in azzurro e sulla stessa
riga delle altre (`F3 Fascia · T Titolare · R Rigori · C Corner · P Punizioni`), e in una
colonna del listone, dove c'è anche il **filtro per fascia**: il menu mostra le fasce del
reparto selezionato, perché i centrocampisti arrivano fino a `F8` e i difensori no.

L'ordine è quello dell'articolo, non quello alfabetico: le fasce jolly (`JF`) e le scommesse
(`FS`) stanno **infilate fra le altre**, quindi fra gli attaccanti `JF1` viene prima di `F5`.
Per questo sotto la sigla, nella colonna, c'è un numero che tiene la graduatoria: ordinando la
colonna vengono su le fasce alte, non le sigle in alfabeto.

L'aggancio è per nome **dentro il reparto** dell'articolo, che basta a togliere ogni
ambiguità: i due Esposito attaccanti hanno già nomi diversi nel listone (`Esposito F.P.` e
`Esposito Se.`) e `Martinez L.` non rischia di finire sul portiere dell'Inter. Tutti e 322 i
nomi si agganciano, e i portieri non hanno fasce: per loro c'è la pagina dedicata.

### Titolarità e probabili formazioni

Stessa storia con `probabili_formazioni*.md`, l'articolo con la formazione tipo delle venti
squadre. La riga della formazione è già strutturata dalla punteggiatura, e la punteggiatura
*è* il dato:

```
Carnesecchi; Zappacosta/Bellanova, Scalvini, ...; Kessié, Gaetano, ...
            ↑ punto e virgola: cambio reparto
                       ↑ barra: se lo giocano in due
                                  ↑ virgola: un altro posto in campo
```

Chi è solo nel suo posto è un titolare e prende una **T verde**; chi se lo gioca con un altro
prende una **B gialla**. Le lettere stanno accanto a R, C e P, nel riquadro *in asta ora* e
nella colonna `T/B` del listone — anche questa ordinabile, così in cima vengono i titolari.
Chi in formazione non compare (le riserve) non ha nessuna lettera.

Lo stesso file alimenta la pagina **📋 Formazioni**: una card per club, il **modulo** accanto
al nome, i reparti dal portiere all'attacco, i ballottaggi affiancati. Il modulo non si legge
dalla prosa — dove ogni squadra ne nomina due o tre fra provati e possibili — ma si conta dai
reparti della formazione tipo: è quindi sempre coerente con le righe che vedi sotto, anche
quando l'articolo a parole ne dice un altro (la Fiorentina è scritta 4-3-2-1 e raccontata
4-3-3). Chi è già stato aggiudicato resta scritto ma
**sbiadito e barrato**, col nome di chi l'ha preso e a quanto nel tooltip: serve riconoscerlo
a colpo d'occhio, non nasconderlo. La pagina si aggiorna da sola ogni dieci secondi.

`--no-lineups` genera il listone senza formazioni; senza il file la pagina lo dice e il resto
dell'app funziona uguale.

### Infortunati

Terzo articolo, `infortunati*.md`: la tabella degli indisponibili. Di ogni squadra si legge il
solo blocco `*Infortunati:*` — squalificati e diffidati valgono una giornata, un crociato
mezza stagione — e da ogni riga si prendono il nome e la **giornata di rientro prevista**
(«in dubbio per la 3a», «rientro previsto per la 6a»).

Chi è fuori porta un'🚑 **rossa con la giornata**: `🚑 4a` nel riquadro *in asta ora*, con il
referto per esteso nel tooltip, e la stessa cosa nella colonna 🚑 del listone. Ordinandola si
mette in fila chi rientra prima. Se l'articolo non dà una data resta l'ambulanza con un
trattino: che sia fuori è già l'informazione che serve.

La tabella è aggiornata in tempo reale sul sito, quindi conviene riscaricarla il giorno
dell'asta e rilanciare lo script: chi è rientrato sparisce da solo dal JSON.

### Portieri

`portieri*.md` porta le gerarchie in porta, e la pagina **🧤 Portieri** mostra per ogni
squadra **solo il titolare**: in diciotto squadre su venti il vice è un credito buttato. Il
secondo compare dove il posto è davvero in discussione, e sono due casi diversi:

- il *Primo* dell'articolo sono **due nomi separati dalla barra** — il Como, dove l'allenatore
  ha chiesto e ottenuto due titolari — e allora si mostrano tutti e due in giallo;
- la nota dice esplicitamente di prenderli entrambi o che la gerarchia è da definire
  (Inter, Lazio, Napoli): il titolare resta verde e sotto compare *Prendi anche…*.

Le frasi che fanno scattare l'avviso sono poche e testuali (`entrambi`, `la coppia`,
`gerarchia da definire`, `apertissima`): è una regola che si legge nell'articolo, non un
giudizio nostro. Il perché sta nel tooltip della targhetta *ballottaggio*.

Su ogni card ci sono anche i **gol subiti dalla squadra** nella stagione precedente, sommati
dai portieri nel file delle *Statistiche* (ognuno porta quelli presi mentre giocava lui). La
squadra è quella scritta lì, cioè quella dell'anno scorso: un portiere che ha cambiato maglia
non si porta i gol in quella nuova. Le **neopromosse** — Frosinone, Monza, Venezia — non hanno
il numero, perché in Serie A non hanno giocato e uno zero le farebbe sembrare le difese
migliori del campionato.

Le card sono ordinate **dalla difesa meno battuta alla più battuta** (Como 29, Roma 31, …,
Torino 63) e non alfabeticamente: all'asta la domanda è quale porta prende meno gol. Le
neopromosse, senza numero, chiudono la fila.

### I pararigori

Sotto le card c'è la striscia dei **pararigori**: chi ne ha parato almeno uno nella stagione
precedente, con almeno 10 partite a voto — sotto quella soglia un rigore parato è un caso, non
una dote — in fila orizzontale dal più bravo in giù. Stemma, quante ne ha parate e il nome; chi
è già stato aggiudicato è barrato come nelle card.

### La griglia delle coppie

Sotto i pararigori c'è la griglia: un numero per ogni incrocio fra due club, tanto più alto
quanto meglio i due portieri si completano (in verde le coppie migliori, da 89 in su, come
nell'originale). La griglia **si allarga con la finestra** (a schermo stretto scorre invece di schiacciarsi), e
**passando il mouse su una casella si accendono la riga e la colonna**, così l'incrocio non si
perde per strada su venti colonne. Nessun JavaScript: bastano `tr:hover` e
una regola `:has()` per colonna, e dentro `st.markdown` gli script non verrebbero comunque
eseguiti.

La griglia è l'unico dato dell'app **trascritto a mano**: la fonte è un'immagine, non un file
leggibile. La trascrizione però si controlla da sola, perché la griglia è simmetrica — ogni
coppia è stata scritta due volte, e le due scritture devono coincidere. Lo **stesso controllo
gira al caricamento**: una coppia che non combacia col suo speculare viene detta subito, coi
nomi delle due squadre. Senza quell'avviso l'unico segnale sarebbe un riquadro che non compare.

Il file si carica da *Gestione asta → Listone* come tutti gli altri, purché si chiami
`griglia_*.json`. Non entra nel listone — questa pagina la legge per conto suo — quindi
caricarla non cambia una virgola dei calciatori.

L'originale è su <https://app.fantalab.it/griglia-portieri>, ed è **un'immagine**: i 190 numeri
vanno ricopiati a mano, e la mia trascrizione non posso dartela perché quei numeri sono
l'analisi di qualcun altro. Quindi è probabile che tu non abbia questa griglia, ed è normale:
se manca, la sezione semplicemente non compare e le gerarchie in porta restano. Se te la vuoi
fare, la forma è questa:

```json
{
  "teams": ["Atalanta", "Bologna", "..."],
  "values": [[0, 7, 3], [7, 0, 5], [3, 5, 0]],
  "highlight_from": 89,
  "note": "una riga di spiegazione, mostrata sopra la griglia"
}
```

`values` dev'essere quadrata quanto `teams`, simmetrica, con la diagonale a zero. I nomi delle
squadre sono quelli del listone.

## Una demo pubblica, con calciatori inventati

L'app si puo' lasciare online come vetrina, ma **non con i dati veri**: un indirizzo pubblico
è una forma di distribuzione più diretta di una repo, non meno. E un'app senza listone non
mostra niente — si apre e c'è un pannello che chiede di caricare un file.

La terza strada è un listone **inventato**:

```bash
python scripts/genera_demo.py data
```

Scrive tre file: il listone (480 calciatori con nomi costruiti da sillabe, quotazioni e
statistiche verosimili, fasce, formazioni tipo, gerarchie in porta, rigoristi e infortunati),
la griglia delle coppie, e `demo_eventi.json` — un'asta portata a metà, con i portieri
completati e i difensori in corso.

Le squadre di Serie A restano quelle vere: nominarle in uno strumento da fantacalcio è uso
descrittivo, e così gli stemmi funzionano. **Non c'è un solo calciatore reale.**

Ogni aggiudicazione dell'asta finta passa da `validate_assignment`, la stessa funzione che
ferma l'admin quando sbaglia: il log della demo è legale per le regole dell'app, non per
quelle che si ricordava chi ha scritto il generatore.

Il generatore **si rifiuta di sovrascrivere** file già esistenti senza `--sovrascrivi`: puntarlo
per sbaglio su `data/` non ti cancella il listone vero.

### Niente database

La demo non ha bisogno di Supabase. Senza `database_url` l'app usa il repository in memoria,
e all'avvio `wiring._semina_la_demo` ci versa dentro `data/demo_eventi.json`.

Il rovescio della medaglia è anche il pregio: **la demo si ripara da sola**. Quello che
combina un visitatore resta finché vive il processo e sparisce al riavvio successivo — che su
Streamlit Cloud arriva a ogni push e dopo ogni dormita. Per un'asta vera sarebbe inaccettabile,
ed è esattamente il motivo per cui l'asta vera usa il database.

Due cose da sapere prima di pubblicarla:

- **il repository in memoria è condiviso da tutti i visitatori**, non uno per browser: vive in
  `cache_resource`, che è di processo. Metti comunque `admin_password`, o il primo che passa
  cambia la demo per tutti fino al riavvio;
- **Streamlit Cloud mette a dormire le app inattive**: chi apre il link dopo giorni aspetta
  mezzo minuto. È il primo commento che riceverai, tanto vale scriverlo accanto al link.

### Dirlo, che è finta

L'unico vero fraintendimento possibile è che qualcuno prenda quelle quotazioni sul serio, e un
avviso nel README non lo legge nessuno. C'è quindi un secret che scrive una riga **in cima a
ogni pagina**, prima della navigazione:

```toml
avviso = "Demo con calciatori di fantasia: le quotazioni non sono quelle vere."
```

Vuoto o assente non si vede e non occupa spazio. Non è nato solo per la demo: è il posto per
qualunque cosa vada detta a tutti senza toccare il codice — «si comincia alle 21», «asta
rinviata a giovedì».

### Il branch `demo`

I dati finti **non stanno su `main`**: "nella repo non c'è nessun dato" deve restare vero per
chi la clona. Stanno su un branch a parte, che è quello che punti su Streamlit Cloud:

```bash
git switch -c demo
python scripts/genera_demo.py data
printf '!data/players_2026_27.json\n!data/griglia_portieri_2026_27.json\n' >> .gitignore
git add -A && git commit -m "Dati della demo"
```

Poi su [share.streamlit.io](https://share.streamlit.io) crei una seconda app sulla stessa repo
scegliendo **branch `demo`**, e nei secrets metti solo `admin_password`. Nessun
`database_url`, nessun Supabase.

Quando `main` cambia, la demo si aggiorna con un `git merge main`.

Un'ultima cosa: **scrivi da qualche parte che è finta.** Una riga basta — «listone di
fantasia, i calciatori non esistono» — ed evita l'unico vero fraintendimento possibile, cioè
che qualcuno prenda quelle quotazioni sul serio.

## Problemi frequenti

| Sintomo | Causa e rimedio |
|---|---|
| Banner rosso "operazioni non salvate" | Rete assente. L'asta continua: premi *Riprova*, o aspetta. |
| "Modalità demo" in cima alla pagina admin | Manca `database_url` nei secrets: gli spettatori non vedono nulla. |
| Le pagine pubbliche non si aggiornano | Ricarica; verifica che admin e utenti puntino allo stesso `auction_id`. |
| `connection refused` / timeout su Supabase | Stai usando la connessione diretta IPv6: passa al *Transaction pooler* (porta 6543). |
| `failed to resolve host '...'` con un host che non c'entra nulla | La password ha caratteri speciali non codificati: `python scripts/check_db.py` te lo dice. |
| `password authentication failed` | Password sbagliata: *Settings → Database → Reset database password*. |
| L'app funzionava e ora il database non risponde | Progetto Supabase in pausa dopo 7 giorni di inattività: dal dashboard, *Restore project*. |
| Pagina bianca sotto il titolo, e l'orologio dice *«aggiornato alle mai»* | Streamlit Cloud non riesce a raggiungere il database, anche se dal tuo computer `python scripts/check_db.py` si collega. Da lì non si sblocca da solo: *Reboot app* dal dashboard di Streamlit Cloud. |
| `prepared statement "..." already exists` | Non dovrebbe più capitare: `_engine()` disattiva le prepared statement, che il pooler in modalità transazione non supporta. |
| Il pulsante *Passa ai…* è spento | Qualche squadra non ha ancora completato il reparto: accanto al pulsante c'è l'elenco. |
| Sono passato al ruolo dopo per sbaglio | `↩️ Annulla` riporta l'asta alla fase precedente. |
| Ho sbagliato un'aggiudicazione di dieci minuti fa | *Rose e correzioni* → scegli l'aggiudicazione → cambia squadra/prezzo o rimuovila. |

---

## Licenza, e di chi sono i dati

Il **codice** è sotto licenza [MIT](LICENSE): fanne quello che vuoi.

I **dati** no, e non sono nella repo apposta. Le quotazioni e le statistiche sono di
[fantacalcio.it](https://www.fantacalcio.it) e vanno scaricate dal loro sito, con le loro
condizioni. Le fasce d'asta, le probabili formazioni, le gerarchie in porta, gli infortunati
e i rigoristi si ricavano da articoli editoriali — nel mio caso quelli di
[SOS Fanta](https://www.sosfanta.com) — che restano di chi li ha scritti: l'app li legge dal
tuo computer e li tiene nel tuo database, non li ridistribuisce. Gli stemmi dei club sono
marchi dei rispettivi proprietari.

Questo progetto non è affiliato né a fantacalcio.it né a SOS Fanta né alla Lega Serie A.

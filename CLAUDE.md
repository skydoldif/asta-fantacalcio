# Istruzioni per un assistente AI

Questo file lo legge da solo un assistente (Claude Code e simili) quando apre la repo. Serve a
due persone diverse: **chi vuole solo mettere in piedi la sua asta** e non programma, e **chi
tocca il codice**. Le due metà sono separate, sotto.

Rispondi in italiano. Il codice, i commenti e i messaggi a schermo sono in italiano: mantieni
quella voce invece di scivolare nell'inglese a metà file.

---

## Se chi ti parla vuole solo far partire la sua asta

È il caso più probabile. Quella persona non conosce GitHub, non ha un terminale aperto e non
deve averne bisogno: **tutto si fa dal browser**. Il percorso guidato è in `QUICKSTART.md`
dove c'è, altrimenti nel README alla sezione *Deploy per la serata*: seguilo con loro un passo
alla volta, e non proporre scorciatoie da riga di comando.

Cosa devono procurarsi da soli, perché non è nella repo e non può esserci:

| Serve | Dove |
|---|---|
| Un account GitHub, uno Supabase, uno Streamlit | gratuiti tutti e tre |
| Il listone ufficiale, `Quotazioni_*.xlsx` — **l'unico obbligatorio** | <https://www.fantacalcio.it/quotazioni-fantacalcio> |
| Le statistiche dell'anno scorso | <https://www.fantacalcio.it/statistiche-serie-a> |
| Fasce d'asta, formazioni tipo, gerarchie in porta, rigoristi, piazzati, indisponibili | articoli di sosfanta.com |
| La griglia delle coppie di portieri | <https://app.fantalab.it/griglia-portieri> — è un'immagine, i numeri si ricopiano a mano |
| Gli stemmi delle squadre | <https://football-logos.cc/italy/serie-a/> |
| Gli audio della Soundbar | <https://www.myinstants.com/en/index/it/> |

**Gli indirizzi esatti degli articoli sono in `FONTI`, in `src/asta/ui/upload.py`**, e l'app li
mostra da sola sotto *Gestione asta → Listone → 🔗 Dove si scaricano*: mandali lì invece di
ricopiarli, così restano giusti anche quando cambia la stagione. Gli articoli si salvano in
markdown con l'estensione [Obsidian Web
Clipper](https://chromewebstore.google.com/detail/obsidian-web-clipper/cnjifjpddelmedmihgijeibhnjfabmlf),
che dà già il formato che l'app si aspetta.

Il listone **non si committa e non si genera da terminale**: si carica dall'app, da *Gestione
asta → Listone*, e finisce nel database. Anche a pezzi, in giorni diversi.

### Le quattro cose su cui si incagliano tutti

Sono trappole vere, già pagate. Se qualcosa non funziona, guarda prima qui.

1. **La stringa di connessione di Supabase.** Va presa dal riquadro *Transaction pooler*
   (porta `6543`), non dalla *Direct connection*: quella è solo IPv6 e Streamlit non la
   raggiunge. E `postgresql://` all'inizio va cambiato in `postgresql+psycopg://`.
2. **La password dentro l'indirizzo.** Se contiene `@ : / ? # [ ] %` o spazi, l'indirizzo si
   spezza e l'errore parla di un *host* inesistente, non della password — quindi si cerca nel
   posto sbagliato per un'ora. Rimedio più semplice: cambiarla in una di sole lettere e numeri
   da *Settings → Database → Reset database password*.
3. **La tabella non va creata a mano.** L'app la crea al primo avvio (`ensure_schema`). Se
   qualcuno propone di aprire l'SQL Editor, non serve.
4. **L'app va resa pubblica** dal pulsante *Share* di Streamlit, altrimenti ogni amico dovrebbe
   autenticarsi. La repo può restare privata: sono due cose separate.

`python scripts/check_db.py` diagnostica l'URL del database e dice in italiano cosa non va —
ma è per chi ha un terminale, non per il caso di sopra.

---

## Se chi ti parla tocca il codice

### Come si lancia e si verifica

```bash
pip install -e ".[dev]"
streamlit run app.py          # senza database parte in modalità demo, in memoria
pytest                        # tutta la suite
ruff check . && ruff format --check . && mypy
```

Prima di dire che una cosa è fatta: `pytest`, `ruff check .`, `ruff format --check .`, `mypy`.
Sono i quattro passi della CI, in quest'ordine.

**Molti test si saltano da soli** se in `data/` e `static/` non ci sono i dati veri, e lo
dicono nel motivo dello skip (vedi `tests/conftest.py`). Non è un guasto: i dati sono di
fantacalcio.it, di SOS Fanta e di chi ha fatto stemmi e audio, quindi ognuno si procura i suoi.
Il motore dell'asta — log, regole, undo, export, repository — gira sempre, su un listone finto,
ed è la maggioranza dei test. **Non aggirare uno skip committando dei dati.**

### Come è fatta

L'asta è un **log di eventi in sola aggiunta**, e lo stato si ricalcola ogni volta con una
funzione pura: `build_state(listone, events)`. Non c'è nessuno stato mutabile condiviso, e
l'annullamento non cancella niente — mette `active=False` sull'evento.

| Cartella | Regola |
|---|---|
| `src/asta/domain/` | logica pura. **Non importa mai Streamlit**, né niente di esterno. È l'unica parte con `mypy --strict`. |
| `src/asta/data/` | letture da disco e dal database. |
| `src/asta/ui/` | Streamlit. Sacrificabile: se un giorno l'interfaccia si rifà, il dominio resta. |
| `scripts/` | strumenti da riga di comando. Solo libreria standard e `asta.domain`, mai Streamlit. |

Il codice della riga di comando e quello del caricamento dall'app **non sono duplicati**:
`asta/ui/upload.py` scrive i file caricati in una cartella temporanea e chiama la stessa
`build_payload` dello script. C'è un test che verifica che le due strade diano un listone
identico byte per byte, ed è il test che non deve mai diventare rosso.

### La demo pubblica

`python scripts/genera_demo.py data` fabbrica un listone di calciatori **inventati** e
un'asta a metà, per lasciare online una vetrina senza pubblicare i dati di nessuno. Non serve
un database: senza `database_url` l'app usa il repository in memoria e all'avvio ci versa
`data/demo_eventi.json`, quindi la demo riparte dallo stesso punto a ogni riavvio.

Due cose da non dimenticare se te ne parlano: il generatore **si rifiuta di sovrascrivere**
file esistenti (puntarlo su `data/` non cancella il listone vero), e i dati finti vanno su un
branch a parte, non su `main`.

### Le trappole di Streamlit già pagate, in produzione

- **`st.cache_data` serializza** quello che restituisce. Sul log degli eventi ha fatto cadere
  l'app con `UnserializableReturnValueError`, e in locale non si vede perché `AppTest` gira
  senza runtime. Per gli oggetti condivisi si usa `st.cache_resource`.
- **`st.rerun()` butta via tutto quello che è stato appena disegnato.** Un `st.success()` prima
  di un rerun non lo vede nessuno: il messaggio va messo in `st.session_state` e mostrato al
  giro dopo.
- **Lo stato dei widget viene buttato via** quando la pagina che li disegna smette di essere
  disegnata (`st.navigation`). I filtri che devono sopravvivere al cambio pagina si tengono in
  una chiave di sessione **diversa** da quella del widget.
- **Il transaction pooler non supporta le prepared statement**: `prepare_threshold=None` nella
  connessione, o dopo qualche minuto di aggiornamenti automatici l'asta cade.
- **`connect_timeout` basso** (3 s): il pooler si risolve in più indirizzi e psycopg li prova a
  uno a uno; con l'attesa lunga la pagina resta bianca invece di mostrare l'ultimo stato noto.

### Cosa non fare mai

- **Non committare `.streamlit/secrets.toml`**, e non stamparne il contenuto. Lì dentro ci sono
  `admin_password` e `database_url`. Il file d'esempio è `.streamlit/secrets.toml.example`.
- **Non committare i dati**: listone, statistiche, articoli, stemmi, audio. Non sono nostri.
- **Non cambiare la forma degli eventi già scritti.** Il log è in sola aggiunta e ci sono aste
  vere dentro: un campo si aggiunge, non si rinomina.
- **Non far dipendere `domain/` da Streamlit**, nemmeno «per un attimo».

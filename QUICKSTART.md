# Da zero all'asta, in venti minuti

Non serve saper programmare, e non serve installare niente sul computer. Servono tre account
gratuiti — GitHub, Supabase, Streamlit — e il file del listone scaricato da fantacalcio.it.

Il [README](README.md) spiega tutto il resto: leggilo dopo, non serve adesso.

> **Se usi un assistente AI** (Claude Code o simili), aprigli questa cartella e digli
> «aiutami a mettere in piedi l'asta»: nella repo c'è un [CLAUDE.md](CLAUDE.md) che lo mette
> già al corrente di tutto, comprese le quattro cose su cui si incaglia chi parte da zero.

---

## 1. Fai una copia della repo · 2 minuti

In cima a questa pagina, **Use this template → Create a new repository**. Dagli un nome e
crea. Adesso è tua.

## 2. Crea il database · 5 minuti

Serve perché l'asta la vedano anche gli altri sui loro telefoni: qualcuno deve custodire
l'unica copia buona, e quel qualcuno è il database.

1. Vai su [supabase.com](https://supabase.com), crea un progetto. **Segnati la password** che
   scegli: serve fra un minuto.
2. Nella pagina del progetto, pulsante verde **Connect** in alto → riquadro
   **Transaction pooler** (porta `6543`). Copia la stringa.
3. Prendi la stringa e fai **due sostituzioni**:
   - all'inizio, `postgresql://` diventa `postgresql+psycopg://`
   - `[YOUR-PASSWORD]`, parentesi quadre comprese, diventa la password del punto 1

> ⚠️ **Usa il pooler, non la *Direct connection***: quella è solo IPv6 e Streamlit non la
> raggiunge.
>
> ⚠️ Se la password ha dentro `@ : / ? # [ ] %` o spazi, l'indirizzo si spezza e l'errore
> parlerà di un host che non esiste, non della password. Il modo più semplice per non
> pensarci: dal pannello di Supabase (*Settings → Database → Reset database password*)
> scegline una di sole lettere e numeri.

La tabella non devi crearla: l'app se la fa da sola al primo avvio.

## 3. Metti l'app online · 5 minuti

1. Vai su [share.streamlit.io](https://share.streamlit.io), **Create app**, e scegli la repo
   del punto 1. Il file da eseguire è `app.py`.
2. Prima di premere Deploy, apri **Advanced settings → Secrets** e incolla queste due righe,
   con i tuoi valori:

   ```toml
   admin_password = "scegli-una-password-lunga"
   database_url = "postgresql+psycopg://...la stringa del punto 2..."
   ```

3. Deploy. Il primo avvio prende un paio di minuti.
4. **Rendi pubblica l'app**: pulsante **Share** in alto a destra → *This app is public and
   searchable*. Senza, i tuoi amici dovrebbero autenticarsi uno per uno.

> La tua repo può restare privata: l'app è pubblica lo stesso, sono due cose separate.

## 4. Carica il listone · 3 minuti

Scarica il file delle **Quotazioni** da
<https://www.fantacalcio.it/quotazioni-fantacalcio> — formato **Excel**, e il nome che ti
propone (`Quotazioni_Fantacalcio_Stagione_….xlsx`) va già bene così com'è. Poi, nella tua app:

**Gestione asta → Listone** → trascina il file → *Genera il listone*.

Fatto: 500 e passa calciatori pronti.

Vuoi anche fasce d'asta, probabili formazioni e gerarchie in porta? Incolla ognuno di quegli
articoli in un file di testo, chiamalo come dice il
[README](README.md#i-dati-che-devi-procurarti), e trascina anche quelli. Le **statistiche**
dell'anno scorso si scaricano da <https://www.fantacalcio.it/statistiche-serie-a>. Sono tutti
facoltativi: senza, sparisce solo quella colonna.

**Non devi averli tutti adesso.** Torna in quella scheda quando vuoi e aggiungi quello che
ti manca: le quotazioni escono a luglio, le probabili formazioni la settimana prima
dell'asta. Quello che hai già caricato resta dov'è, e il listone si rigenera da solo.

## 5. Configura l'asta · 2 minuti

Sempre in **Impostazioni**: modalità, crediti, quanti calciatori per ruolo, i nomi delle
squadre. Poi *Salva*.

## 6. Fai una prova, sul serio

Aggiudica due o tre calciatori finti e apri il link pubblico **dal telefono, in rete dati e
in finestra anonima**: è l'unico modo di vedere l'app come la vedranno i tuoi amici. Poi
azzera l'asta dalla scheda *Export*.

---

## La sera dell'asta

Il link della radice è quello che giri nel gruppo. Tu tieni aperta `…/admin`.

La [checklist della serata](README.md#checklist-della-serata) nel README è mezz'ora prima e
sono tre minuti: coprono i due modi in cui l'app può presentarsi addormentata proprio mentre
arrivano gli amici.

Se qualcosa non torna, [Problemi frequenti](README.md#problemi-frequenti).

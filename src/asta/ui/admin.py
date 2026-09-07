"""Vista admin: l'unica che puo' modificare l'asta.

E' protetta da password (``admin_password`` nei secrets) e organizzata in
cinque schede: conduzione dell'asta, listone, impostazioni, rose e correzioni,
export.
"""

from __future__ import annotations

import hmac
from pathlib import Path

import pandas as pd
import streamlit as st
from scripts.build_players import XLSX_GLOB

from asta import config
from asta.data.players import listone_source
from asta.domain.events import EVENT_LABEL, EventType
from asta.domain.export import (
    backup_json,
    export_filename,
    restore_events,
    rosters_csv,
)
from asta.domain.letters import (
    current_player,
    draw_letter,
    eligible_letters,
    letter_queue,
    phase_exhausted,
    skipped_in_letter,
    upcoming,
)
from asta.domain.models import (
    BACKUP_TRIGGER_LABEL,
    DEFAULT_CREDITS,
    DEFAULT_ROLE_LIMITS,
    DEFAULT_ROSTER_SIZE,
    MODE_LABEL,
    ROLE_LABEL,
    ROLE_ORDER,
    BackupTrigger,
    Mode,
    Player,
    Role,
    Settings,
)
from asta.domain.reducer import AuctionState
from asta.domain.rules import (
    blocking_reason,
    max_bid,
    next_role,
    validate_assignment,
    validate_settings,
)
from asta.service import AuctionService
from asta.ui.autobackup import auto_backup
from asta.ui.board import teams_board
from asta.ui.components import (
    ROLE_EMOJI,
    phase_banner,
    player_card,
)
from asta.ui.upload import (
    DESTINAZIONI,
    FONTI,
    OBBLIGATORIO,
    Caselle,
    costruisci_da_caselle,
    etichette,
    sito,
    smista,
    unisci,
)
from asta.ui.wiring import (
    aggiorna_il_listone,
    get_listone,
    get_repository,
    get_service,
    listone_path,
)

#: Un pulsante Streamlit non si allunga in verticale da solo. La chiave passata
#: a ``st.container`` diventa una classe ``st-key-<chiave>`` nel DOM, quindi si
#: puo' agganciare senza dipendere dalle classi generate da Streamlit, che
#: cambiano a ogni versione.
_CSS = """
<style>
/* La colonna del pulsante diventa una colonna flex, e ogni livello fino al
   <button> si allunga: fra la colonna e il pulsante Streamlit infila un paio
   di wrapper che altrimenti restano alti quanto il loro contenuto. */
.st-key-riga_lettera [data-testid="stHorizontalBlock"]{align-items:stretch}
.st-key-riga_lettera [data-testid="stColumn"]:has(.st-key-riquadro_estrai),
.st-key-riga_lettera [data-testid="stColumn"]:has(.st-key-riquadro_estrai) > *,
.st-key-riga_lettera [data-testid="stLayoutWrapper"]:has(.st-key-riquadro_estrai),
.st-key-riquadro_estrai,
.st-key-riquadro_estrai > *,
.st-key-riquadro_estrai [data-testid="stVerticalBlock"],
.st-key-riquadro_estrai [data-testid="stElementContainer"],
.st-key-riquadro_estrai [data-testid="stButton"]{
  display:flex;flex-direction:column;flex:1 1 auto}
.st-key-riquadro_estrai button{flex:1 1 auto;width:100%}
</style>
"""

# --------------------------------------------------------------------- accesso


def _authenticated() -> bool:
    """Chiede la password dell'admin. Restituisce True se l'accesso e' concesso."""
    expected = config.admin_password()
    if not expected:
        st.warning(
            "Nessuna password admin configurata: chiunque abbia il link puo' "
            "gestire l'asta. Imposta `admin_password` nei secrets prima della serata."
        )
        return True
    if st.session_state.get("admin_ok"):
        return True

    st.subheader("🔒 Area amministratore")
    with st.form("login"):
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Entra", type="primary"):
            if hmac.compare_digest(password, expected):
                st.session_state["admin_ok"] = True
                st.rerun()
            else:
                st.error("Password errata.")
    return False


def render() -> None:
    """Disegna la pagina admin."""
    st.title("🎛️ Gestione asta")
    st.markdown(_CSS, unsafe_allow_html=True)
    if not _authenticated():
        return

    service = get_service()
    _sync_banner(service)
    state = service.state()
    auto_backup(service, state)

    asta, listone, impostazioni, rose, export = st.tabs(
        ["🎯 Asta", "📥 Listone", "⚙️ Impostazioni", "📋 Rose e correzioni", "📤 Export"]
    )
    with asta:
        _auction_tab(service, state)
    with listone:
        _listone_tab(service, state)
    with impostazioni:
        _settings_tab(service, state)
    with rose:
        _rosters_tab(service, state)
    with export:
        _export_tab(service, state)


def _sync_banner(service: AuctionService) -> None:
    """Mostra lo stato della sincronizzazione col database."""
    if config.demo_mode():
        st.warning(
            "**Modalita demo**: nessun database configurato, l'asta vive solo in memoria "
            "e gli spettatori non vedono nulla. Imposta `database_url` nei secrets."
        )
    if service.synced:
        return
    _sync_retry(service)


@st.fragment(run_every=5)
def _sync_retry(service: AuctionService) -> None:
    """Banner della coda, che ogni cinque secondi prova a svuotarla.

    Il frammento nasce solo quando c'e' qualcosa in sospeso: durante la
    conduzione normale non gira nulla, e il campo del prezzo non si ridisegna
    sotto le dita. Serve perche' la rete torna quando le pare, e spesso mentre
    l'admin sta fermo ad ascoltare i rilanci: senza questo, la coda resterebbe
    ferma fino al primo click.
    """
    service.flush()
    if service.synced:
        st.success("✅ Operazioni salvate sul database.")
        return
    col1, col2 = st.columns([4, 1])
    col1.error(
        f"⚠️ {len(service.pending)} operazioni non ancora salvate sul database. "
        f"L'asta puo' continuare: verranno inviate appena la rete torna. "
        f"({service.error})"
    )
    if col2.button("Riprova", width="stretch"):
        service.flush()
        st.rerun(scope="fragment")


# ------------------------------------------------------------------ scheda asta


def _auction_tab(service: AuctionService, state: AuctionState) -> None:
    """Conduzione dell'asta: chiamata, aggiudicazione, salto, undo."""
    if not state.started:
        st.info("Configura l'asta nella scheda **Impostazioni** per iniziare.")
        return

    _phase_controls(service, state)
    if state.current_role is None or state.closed:
        return

    st.divider()
    settings = state.settings
    assert settings is not None

    if settings.mode == Mode.LETTER:
        _letter_controls(service, state)
    player = current_player(state)
    if settings.mode is Mode.FREE or player is None:
        _free_call_controls(service, state)
        player = current_player(state)

    if player is None:
        st.info("Nessun calciatore in asta: estrai una lettera o chiamane uno.")
    else:
        player_card(player, prossimi=upcoming(state))
        _assign_controls(service, state, player)

    st.divider()
    _undo_controls(service)


def _phase_controls(service: AuctionService, state: AuctionState) -> None:
    """Avvio e avanzamento delle fasi per ruolo."""
    phase_banner(state)
    if state.closed:
        st.success("🏁 Asta conclusa. Scarica il CSV dalla scheda Export.")
        return

    if state.current_role is None:
        if st.button(f"▶️ Inizia con i {ROLE_LABEL[ROLE_ORDER[0]]}", type="primary"):
            service.record(EventType.ROLE_PHASE_STARTED, {"role": ROLE_ORDER[0].value})
            st.rerun()
        return

    successivo = next_role(state.current_role)
    incomplete = [
        name for name, team in state.teams.items() if team.slots_left(state.current_role) > 0
    ]
    col1, col2 = st.columns([3, 2])
    with col1:
        if incomplete:
            st.caption(
                "Si passa al reparto successivo solo a reparto completo. "
                "Mancano ancora: " + ", ".join(incomplete) + "."
            )
        else:
            st.caption("Tutte le squadre hanno completato il reparto.")
    with col2:
        # Finche' una squadra ha uno slot libero nel reparto in corso non si
        # avanza: dopo il cambio di fase quel calciatore non sarebbe piu'
        # acquistabile. Non ci si puo' incastrare: le impostazioni garantiscono
        # che il listone basti a riempire tutti gli slot, e se le lettere si
        # esauriscono con dei saltati ancora liberi compare la chiamata manuale,
        # che pesca fra tutti i disponibili del ruolo.
        if successivo is not None:
            if st.button(
                f"Passa ai {ROLE_LABEL[successivo]} ➡️",
                width="stretch",
                disabled=bool(incomplete),
            ):
                service.record(EventType.ROLE_PHASE_STARTED, {"role": successivo.value})
                st.rerun()
        elif st.button("🏁 Chiudi l'asta", width="stretch"):
            service.record(EventType.AUCTION_CLOSED, {})
            st.rerun()


def _letter_controls(service: AuctionService, state: AuctionState) -> None:
    """Estrazione della lettera e coda alfabetica."""
    assert state.current_role is not None
    ammissibili = eligible_letters(state)
    coda = letter_queue(state)

    with st.container(key="riga_lettera"):
        col_stato, col_estrai = st.columns([3, 2])
        with col_stato:
            if state.current_letter:
                st.metric("Lettera in corso", state.current_letter)
            st.caption("Lettere gia' uscite in questa fase")
            st.write(" ".join(f"`{c}`" for c in state.drawn_letters) or "_nessuna_")
            st.caption(f"Ancora estraibili: {len(ammissibili)}")
        # Il pulsante riempie la propria colonna in altezza (vedi _CSS): a
        # fianco della lettera in corso e' il bersaglio piu' facile da colpire
        # senza guardare, che e' quello che serve mentre si conduce l'asta.
        with col_estrai, st.container(key="riquadro_estrai"):
            if st.button(
                "🎲 Estrai lettera",
                type="primary" if not coda else "secondary",
                width="stretch",
                disabled=not ammissibili,
            ):
                drawn = draw_letter(state)
                if drawn is None:
                    st.warning("Non ci sono piu' lettere con calciatori disponibili.")
                else:
                    letter, seed = drawn
                    service.record(
                        EventType.LETTER_DRAWN,
                        {"role": state.current_role.value, "letter": letter, "seed": seed},
                    )
                    st.rerun()

    if coda:
        prossimi = ", ".join(p.name for p in coda[1:6])
        if prossimi:
            st.caption(f"In coda dopo questo: {prossimi}")
    elif state.current_letter:
        saltati = skipped_in_letter(state)
        if saltati:
            st.caption(
                f"Lettera {state.current_letter} esaurita. Saltati e ancora liberi: "
                + ", ".join(p.name for p in saltati)
            )
            if st.button(f"↩️ Riapri la lettera {state.current_letter}"):
                service.record(
                    EventType.LETTER_DRAWN,
                    {
                        "role": state.current_role.value,
                        "letter": state.current_letter,
                        "seed": 0,
                        "reopen": True,
                    },
                )
                st.rerun()
    if phase_exhausted(state):
        st.success("Fase completata: nessun altro calciatore da chiamare in questo ruolo.")


def _free_call_controls(service: AuctionService, state: AuctionState) -> None:
    """Chiamata manuale di un calciatore."""
    settings = state.settings
    assert settings is not None
    ruolo = state.current_role if settings.active_role_only else None
    disponibili = state.available(ruolo)
    if not disponibili:
        return

    etichetta = "Chiama un calciatore" if settings.mode == Mode.FREE else "Chiamata manuale"
    with st.container():
        scelto = st.selectbox(
            etichetta,
            options=disponibili,
            index=None,
            format_func=lambda p: p.label,
            placeholder="Scrivi il nome...",
            key="free_call",
        )
        if scelto is not None and state.nominated != scelto.id:
            service.record(EventType.PLAYER_NOMINATED, {"player_id": scelto.id})
            st.rerun()


def _assign_controls(service: AuctionService, state: AuctionState, player: Player) -> None:
    """Selettore squadra, prezzo e pulsanti Aggiudica / Salta."""
    settings = state.settings
    assert settings is not None

    # Restano solo le squadre che possono davvero prenderlo: reparto libero,
    # slot in rosa e crediti sufficienti almeno per il prezzo minimo.
    ammesse = [n for n in settings.teams if blocking_reason(state, player, n) is None]

    if not ammesse:
        st.error("Nessuna squadra puo' acquistare questo calciatore.")
        _skip_button(service, player)
        return

    # Tutto su una riga, allineato in basso: selettore e prezzo hanno
    # l'etichetta sopra, i pulsanti no, e cosi' i quattro comandi finiscono
    # sulla stessa linea.
    col_squadra, col_prezzo, col_ok, col_salta = st.columns(
        [3, 2, 2, 3], vertical_alignment="bottom"
    )
    with col_squadra:
        squadra = st.selectbox(
            "Aggiudicato a",
            ammesse,
            format_func=lambda t: f"{t} — max {max_bid(state, t)}",
            key=f"team_{player.id}",
        )
    tetto = max_bid(state, squadra)
    with col_prezzo:
        prezzo = st.number_input(
            "Prezzo",
            min_value=1,
            max_value=max(1, tetto),
            value=1,
            step=1,
            key=f"price_{player.id}",
        )
    with col_ok:
        if st.button("✅ Aggiudica", type="primary", width="stretch"):
            rejection = validate_assignment(state, player, squadra, int(prezzo))
            if rejection is not None:
                st.error(rejection.message)
            else:
                service.record(
                    EventType.PLAYER_ASSIGNED,
                    {"player_id": player.id, "team": squadra, "price": int(prezzo)},
                )
                st.rerun()
    with col_salta:
        _skip_button(service, player)


def _skip_button(service: AuctionService, player: Player) -> None:
    """Pulsante "salta": il calciatore resta nel listone."""
    if st.button("⏭️ Salta", width="stretch"):
        service.record(EventType.PLAYER_SKIPPED, {"player_id": player.id})
        st.rerun()


def _undo_controls(service: AuctionService) -> None:
    """Pulsanti di annulla e ripristina, con l'etichetta dell'operazione."""
    from asta.domain.events import redoable, undoable

    prossimo_undo = undoable(service.events)
    prossimo_redo = redoable(service.events)
    # Due mezze righe intere: sono i pulsanti che si cercano di fretta dopo un
    # errore, quindi tanto vale renderli i piu' grandi della pagina.
    col_undo, col_redo = st.columns(2)
    with col_undo:
        if st.button("↩️ Annulla", disabled=not service.can_undo, width="stretch"):
            service.undo()
            st.rerun()
        if prossimo_undo is not None:
            st.caption(f"Annulla: _{EVENT_LABEL[prossimo_undo.type]}_")
    with col_redo:
        if st.button("↪️ Ripristina", disabled=not service.can_redo, width="stretch"):
            service.redo()
            st.rerun()
        if prossimo_redo is not None:
            st.caption(f"Ripristina: _{EVENT_LABEL[prossimo_redo.type]}_")


# ----------------------------------------------------------- scheda impostazioni


def _listone_caricato(state: AuctionState) -> None:
    """Riga di controllo su quale listone e' in uso.

    Se il file venisse rigenerato male (o non venisse rigenerato affatto) il
    posto per accorgersene e' qui, non a meta' asta.
    """
    if not state.listone.players:
        st.info(
            "**Nessun listone caricato.** Trascina qui sotto il file delle quotazioni "
            "scaricato da fantacalcio.it e l'asta e' pronta. Gli articoli con fasce, "
            "formazioni e gerarchie in porta puoi aggiungerli adesso o mai."
        )
        return
    per_ruolo = " · ".join(f"{r.value} {len(state.listone.by_role(r))}" for r in ROLE_ORDER)
    # ``listone_path`` da' una stringa (e' la chiave delle memoizzazioni);
    # ``listone_source`` vuole un Path.
    percorso = listone_path()
    sorgente = listone_source(Path(percorso) if percorso else None)
    st.caption(
        f"📋 Listone: **{len(state.listone.players)}** calciatori ({per_ruolo})"
        + (f" — da `{sorgente}`" if sorgente else "")
    )


#: Estensioni accettate dal caricamento: i due Excel ufficiali, gli articoli
#: incollati in un file di testo e la griglia dei portieri, che e' un JSON.
FORMATI_LISTONE = ["xlsx", "md", "txt", "json"]

#: Chiave di sessione con l'esito dell'ultimo caricamento, da mostrare dopo
#: il rerun che altrimenti se lo porterebbe via.
ESITO_CARICAMENTO = "esito_caricamento_listone"


def _listone_tab(service: AuctionService, state: AuctionState) -> None:
    """Scheda del listone: cosa c'e' dentro, e come cambiarlo.

    Ha una scheda sua e non un riquadro dentro le impostazioni perche' sono
    due cose diverse: qui si prepara il materiale, di la' si decidono le
    regole della serata. E preparare il materiale non si fa in una volta
    sola - le quotazioni escono a luglio, le probabili formazioni la
    settimana prima - quindi questa pagina si riapre piu' volte.
    """
    esito = st.session_state.pop(ESITO_CARICAMENTO, None)
    if esito is not None:
        _mostra_esito(esito)

    _listone_caricato(state)

    if state.has_activity:
        st.warning(
            "L'asta e' gia' iniziata: il listone non si tocca piu'. Le aggiudicazioni "
            "gia' fatte puntano a questi calciatori, e cambiarli sotto renderebbe "
            "l'asta incoerente. Per ricominciare, azzera l'asta dalla scheda Export."
        )
        return

    caselle = _caselle_caricate()
    st.divider()
    _cosa_c_e_gia(caselle)
    _dove_si_scaricano(caselle)
    st.divider()
    _aggiungi_file(service, caselle)


def _caselle_caricate() -> Caselle:
    """I file gia' in archivio; vuoto se il database non risponde."""
    try:
        return get_repository().load_listone_files()
    except Exception:
        return {}


def _cosa_c_e_gia(caselle: Caselle) -> None:
    """Elenco delle caselle, piene e vuote, con il modo di svuotarle."""
    st.subheader("Cosa hai gia' caricato")
    nomi = etichette()
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Cosa": nomi[casella],
                    "File": caselle[casella][0] if casella in caselle else "—",
                    "": "✅"
                    if casella in caselle
                    else ("obbligatorio" if casella == OBBLIGATORIO else ""),
                }
                for casella in nomi
            ]
        ),
        hide_index=True,
        width="stretch",
    )

    togliibili = [c for c in caselle if c != OBBLIGATORIO]
    if not togliibili:
        return
    col1, col2 = st.columns([3, 1], vertical_alignment="bottom")
    quale = col1.selectbox(
        "Togli un file",
        togliibili,
        format_func=lambda c: f"{nomi[c]} — {caselle[c][0]}",
        index=None,
        placeholder="Scegli cosa togliere...",
        key="togli_casella",
    )
    if quale is not None and col2.button("🗑️ Togli", width="stretch"):
        get_repository().delete_listone_file(quale)
        _rigenera(dict(get_repository().load_listone_files()))


def _dove_si_scaricano(caselle: Caselle) -> None:
    """Dove si prende ognuno dei file, per quelli che ancora mancano.

    Sta subito sotto la tabella di cosa c'e' gia': prima vedi il buco, poi
    l'indirizzo per riempirlo. Chiuso di default, perche' a chi ha gia'
    caricato tutto non serve.

    Le righe gia' piene restano nell'elenco ma in fondo e senza enfasi: un
    file si rifa' anche a stagione iniziata - gli infortunati cambiano ogni
    settimana - quindi l'indirizzo deve restare raggiungibile.
    """
    ordine = sorted(DESTINAZIONI, key=lambda d: d[1] in caselle)
    with st.expander("🔗 Dove si scaricano"):
        st.markdown(
            "\n".join(
                # Il separatore e' un punto e non un trattino: due delle
                # etichette un trattino ce l'hanno gia' dentro.
                f"- {'✅ ' if destinazione in caselle else ''}**{etichetta}** · "
                f"[{sito(FONTI[destinazione])}]({FONTI[destinazione]})"
                for _, destinazione, etichetta in ordine
            )
        )
        st.caption(
            "Gli articoli si incollano in un file di testo, uno per riga di questo elenco. "
            "Per non farlo a mano c'e' [Obsidian Web Clipper]"
            "(https://chromewebstore.google.com/detail/obsidian-web-clipper/"
            "cnjifjpddelmedmihgijeibhnjfabmlf), che salva una pagina web gia' in markdown: "
            "e' esattamente il formato che l'app si aspetta. La griglia dei portieri e' "
            "un'immagine, quindi quella va ricopiata a mano."
        )
        st.caption(
            "Gli indirizzi degli articoli contengono la stagione: l'anno prossimo saranno "
            "altri. Se uno non risponde piu', cerca il titolo - la pagina cambia numero, "
            "non nome."
        )


def _aggiungi_file(service: AuctionService, caselle: Caselle) -> None:
    """Caricamento di file nuovi, che si sommano a quelli gia' presenti."""
    st.subheader("Aggiungi o sostituisci")
    st.caption(
        "Trascina qui i file e basta: non serve Python ne' il terminale. Puoi "
        "farlo in piu' volte - le quotazioni oggi, le probabili formazioni la "
        f"settimana prima dell'asta. L'unico indispensabile e' `{XLSX_GLOB}`, "
        "e ogni file si riconosce dal nome."
    )
    caricati = st.file_uploader(
        "File del listone",
        type=FORMATI_LISTONE,
        accept_multiple_files=True,
        key="upload_listone",
        label_visibility="collapsed",
    )
    if not caricati:
        return

    contenuti = {f.name: f.getvalue() for f in caricati}
    scelti, ignorati = smista(list(contenuti))
    nomi = etichette()
    # Cosa succedera' *prima* di premere: un nome sbagliato si vede qui, non
    # a meta' asta con la colonna delle fasce vuota.
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "File": nome,
                    "Riconosciuto come": nomi[dove],
                    "": "sostituisce" if dove in caselle else "nuovo",
                }
                for dove, nome in scelti.items()
            ]
            + [{"File": nome, "Riconosciuto come": "— ignorato", "": ""} for nome in ignorati]
        ),
        hide_index=True,
        width="stretch",
    )

    unite = unisci(caselle, contenuti)
    if OBBLIGATORIO not in unite:
        st.error(
            f"Manca il listone ufficiale: serve un file `{XLSX_GLOB}`, adesso o "
            "in un caricamento precedente."
        )
        return

    if st.button("⚙️ Genera il listone", type="primary"):
        _rigenera(unite, contenuti)


def _rigenera(caselle: Caselle, appena_caricati: dict[str, bytes] | None = None) -> None:
    """Ricostruisce il listone da tutte le caselle e lo salva.

    Si rigenera **sempre da capo**, da tutti i file: e' l'unico modo perche'
    caricare le statistiche il giorno dopo dia lo stesso listone che si
    otterrebbe caricando tutto insieme.
    """
    if OBBLIGATORIO not in caselle:
        st.error(f"Senza un file `{XLSX_GLOB}` non c'e' niente da generare.")
        return
    try:
        with st.spinner("Leggo i file e aggancio i nomi..."):
            payload, segnalazioni = costruisci_da_caselle(caselle)
            repo = get_repository()
            for casella, (nome, contenuto) in caselle.items():
                if appena_caricati is None or nome in appena_caricati:
                    repo.save_listone_file(casella, nome, contenuto)
            repo.save_listone(payload)
    except ValueError as exc:
        st.error(str(exc))
        return
    except Exception as exc:
        st.error(f"Non sono riuscito a leggere i file: {exc}")
        return

    aggiorna_il_listone(get_service())
    # L'esito passa dalla sessione perche' subito dopo c'e' un rerun, e il
    # rerun butta via tutto quello che si e' appena disegnato: scriverlo qui
    # vorrebbe dire non mostrarlo mai. Il rerun serve lo stesso, altrimenti
    # la pagina resterebbe quella di prima del caricamento.
    st.session_state[ESITO_CARICAMENTO] = {
        "count": payload["count"],
        "segnalazioni": segnalazioni,
    }
    st.rerun()


def _mostra_esito(esito: dict[str, object]) -> None:
    """Com'e' andato il caricamento, dopo il rerun che lo ha fatto sparire."""
    st.success(f"✅ Listone caricato: {esito['count']} calciatori.")
    segnalazioni = esito["segnalazioni"]
    assert isinstance(segnalazioni, list)
    if segnalazioni:
        # Non sono errori: sono nomi che lo script non ha saputo agganciare
        # con certezza, o una griglia che non torna, e si mostrano perche' li
        # giudichi tu. "Cose" e non "nomi": da quando c'e' anche la griglia,
        # non parlano piu' tutte di un calciatore.
        quante = len(segnalazioni)
        with st.expander(f"⚠️ {quante} cos{'a' if quante == 1 else 'e'} da controllare"):
            for riga in segnalazioni:
                st.write(f"- {riga}")


def _settings_tab(service: AuctionService, state: AuctionState) -> None:
    """Configurazione dell'asta, modificabile finche' non si e' iniziato."""
    corrente = state.settings
    _listone_caricato(state)
    bloccata = state.has_activity
    if bloccata:
        st.warning(
            "L'asta e' gia' iniziata: le impostazioni sono in sola lettura. "
            "Per cambiarle azzera l'asta dalla scheda Export."
        )

    default_teams = (
        "\n".join(corrente.teams) if corrente else "\n".join(f"Squadra {i}" for i in range(1, 9))
    )
    with st.form("settings"):
        col1, col2 = st.columns(2)
        with col1:
            modalita = st.radio(
                "Modalita di chiamata",
                list(Mode),
                format_func=lambda m: MODE_LABEL[m],
                index=list(Mode).index(corrente.mode) if corrente else 1,
                disabled=bloccata,
                key="set_mode",
            )
            crediti = st.number_input(
                "Crediti per squadra",
                min_value=1,
                max_value=100000,
                value=corrente.credits if corrente else DEFAULT_CREDITS,
                step=10,
                disabled=bloccata,
                key="set_credits",
            )
            rosa = st.number_input(
                "Calciatori in rosa",
                min_value=1,
                max_value=60,
                value=corrente.roster_size if corrente else DEFAULT_ROSTER_SIZE,
                disabled=bloccata,
                key="set_roster",
            )
            solo_ruolo = st.checkbox(
                "In chiamata libera accetta solo il ruolo in asta",
                value=corrente.active_role_only if corrente else True,
                disabled=bloccata,
                key="set_role_only",
            )
        with col2:
            st.caption("Limiti per ruolo")
            limiti = {}
            for role in ROLE_ORDER:
                limiti[role] = st.number_input(
                    f"{ROLE_EMOJI[role]} {ROLE_LABEL[role]}",
                    min_value=0,
                    max_value=30,
                    value=corrente.limit(role) if corrente else DEFAULT_ROLE_LIMITS[role],
                    key=f"limit_{role.value}",
                    disabled=bloccata,
                )
        nomi = st.text_area(
            "Squadre (una per riga)",
            value=default_teams,
            height=200,
            disabled=bloccata,
            key="set_teams",
        )

        st.divider()
        col3, col4 = st.columns(2)
        with col3:
            auto = st.checkbox(
                "💾 Abilita i download automatici del backup",
                value=corrente.auto_backup if corrente else False,
                disabled=bloccata,
                key="set_auto_backup",
            )
            st.caption(
                "Il backup JSON dell'asta viene scaricato da solo, sul computer "
                "dell'admin, nei momenti spuntati qui accanto. Senza questa spunta "
                "i momenti restano salvati ma non fa partire niente."
            )
        with col4:
            st.caption("Quando scaricarlo")
            momenti = {
                trigger: st.checkbox(
                    BACKUP_TRIGGER_LABEL[trigger],
                    value=(trigger in corrente.backup_triggers) if corrente else True,
                    disabled=bloccata,
                    key=f"set_backup_{trigger.value}",
                )
                for trigger in BackupTrigger
            }

        if st.form_submit_button("💾 Salva impostazioni", type="primary", disabled=bloccata):
            squadre = tuple(n.strip() for n in nomi.splitlines() if n.strip())
            nuove = Settings(
                teams=squadre,
                credits=int(crediti),
                roster_size=int(rosa),
                role_limits=tuple(limiti.items()),
                mode=modalita,
                active_role_only=solo_ruolo,
                auto_backup=auto,
                backup_triggers=tuple(t for t in BackupTrigger if momenti[t]),
            )
            errori = validate_settings(nuove, get_listone())
            if errori:
                for errore in errori:
                    st.error(errore)
            else:
                service.record(EventType.AUCTION_CONFIGURED, nuove.to_payload())
                st.success("Impostazioni salvate.")
                st.rerun()

    if corrente:
        totale = sum(corrente.limit(r) for r in ROLE_ORDER)
        st.caption(
            f"In gioco: {len(corrente.teams)} squadre × {corrente.credits} crediti · "
            f"rosa {totale} ("
            + ", ".join(f"{corrente.limit(r)}{r.value}" for r in ROLE_ORDER)
            + f") · {MODE_LABEL[corrente.mode]}"
        )
        st.caption("💾 Backup automatico: " + _riepilogo_backup(corrente))


def _riepilogo_backup(settings: Settings) -> str:
    """Riga che riassume quando parte il download automatico."""
    if not settings.auto_backup:
        return "spento."
    momenti = [BACKUP_TRIGGER_LABEL[t].lower() for t in settings.backup_triggers]
    if not momenti:
        return "acceso, ma senza nessun momento scelto."
    return ", ".join(momenti) + "."


# ------------------------------------------------------------- scheda rose


def _rosters_tab(service: AuctionService, state: AuctionState) -> None:
    """Rose complete e correzione di aggiudicazioni gia' registrate."""
    if not state.started:
        st.info("Configura l'asta per vedere le rose.")
        return

    teams_board(state)

    st.divider()
    st.subheader("Correggi un'aggiudicazione")
    vendite = state.sold()
    if not vendite:
        st.caption("Nessuna aggiudicazione da correggere.")
        return

    settings = state.settings
    assert settings is not None
    scelta = st.selectbox(
        "Aggiudicazione",
        options=[a for a, _ in vendite],
        format_func=lambda a: (
            f"{state.listone.get(a.player_id).name} → {a.team} ({a.price} crediti, {a.role.value})"
        ),
        index=None,
        placeholder="Scegli l'aggiudicazione da correggere...",
    )
    if scelta is None:
        return

    player = state.listone.get(scelta.player_id)
    col1, col2, col3 = st.columns([3, 2, 2])
    with col1:
        nuova_squadra = st.selectbox(
            "Squadra",
            list(settings.teams),
            index=list(settings.teams).index(scelta.team) if scelta.team in settings.teams else 0,
            key=f"fix_team_{scelta.event_seq}",
        )
    tetto = max_bid(state, nuova_squadra, ignore_seq=scelta.event_seq)
    with col2:
        nuovo_prezzo = st.number_input(
            "Prezzo",
            min_value=1,
            max_value=max(1, tetto),
            value=min(scelta.price, max(1, tetto)),
            key=f"fix_price_{scelta.event_seq}",
        )
    with col3:
        st.write("")
        if st.button("💾 Applica", type="primary", width="stretch"):
            rejection = validate_assignment(
                state, player, nuova_squadra, int(nuovo_prezzo), ignore_seq=scelta.event_seq
            )
            if rejection is not None:
                st.error(rejection.message)
            else:
                service.record(
                    EventType.ASSIGNMENT_UPDATED,
                    {
                        "target_seq": scelta.event_seq,
                        "team": nuova_squadra,
                        "price": int(nuovo_prezzo),
                    },
                )
                st.rerun()

    if st.button(f"🗑️ Annulla l'acquisto di {player.name} (torna nel listone)"):
        service.record(EventType.ASSIGNMENT_REMOVED, {"target_seq": scelta.event_seq})
        st.rerun()


# ------------------------------------------------------------- scheda export


def _export_tab(service: AuctionService, state: AuctionState) -> None:
    """Export per fantacalcio.it, backup, ripristino e azzeramento."""
    st.subheader("File per fantacalcio.it")
    incomplete = state.incomplete_teams()
    if incomplete:
        st.info("Rose non ancora complete: " + ", ".join(incomplete) + ".")
    st.download_button(
        "⬇️ Scarica il CSV delle rose",
        data=rosters_csv(state).encode("utf-8"),
        file_name=export_filename(),
        mime="text/csv",
        type="primary",
        disabled=not state.started,
    )
    st.caption("Formato `$,$,$` + `nome_squadra,id_giocatore,crediti`, come richiesto dal sito.")

    st.divider()
    st.subheader("Backup")
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "⬇️ Scarica il backup completo (JSON)",
            data=backup_json(service.events).encode("utf-8"),
            file_name=export_filename("backup_asta", "json"),
            mime="application/json",
            disabled=not service.events,
        )
        st.caption("Contiene tutto il log, anche le operazioni annullate.")
        if state.settings is not None:
            st.caption("Scaricato da solo: " + _riepilogo_backup(state.settings))
    with col2:
        caricato = st.file_uploader("Ripristina da backup", type="json")
        if caricato is not None and st.button("♻️ Ripristina"):
            try:
                service.restore(restore_events(caricato.getvalue().decode("utf-8")))
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.success("Asta ripristinata dal backup.")
                st.rerun()

    st.divider()
    st.subheader("Log operazioni")
    if service.events:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "#": e.seq,
                        "Operazione": EVENT_LABEL[e.type],
                        "Dettagli": _describe(e.payload, state),
                        "Valida": "✅" if e.active else "↩️ annullata",
                    }
                    for e in reversed(service.events)
                ]
            ),
            hide_index=True,
            width="stretch",
            height=300,
        )

    st.divider()
    with st.expander("⚠️ Azzera l'asta"):
        st.write("Cancella tutte le operazioni e riparte dalla configurazione.")
        conferma = st.checkbox("Confermo di voler cancellare l'asta")
        if st.button("Azzera", disabled=not conferma):
            service.reset()
            st.rerun()


def _describe(payload: dict[str, object], state: AuctionState) -> str:
    """Riassunto leggibile del payload di un evento, per il log operazioni."""
    parts: list[str] = []
    if (pid := payload.get("player_id")) is not None:
        try:
            parts.append(state.listone.get(int(pid)).name)  # type: ignore[arg-type]
        except (KeyError, TypeError, ValueError):
            parts.append(f"Id {pid}")
    if (team := payload.get("team")) is not None:
        parts.append(f"→ {team}")
    if (price := payload.get("price")) is not None:
        parts.append(f"{price} crediti")
    if (letter := payload.get("letter")) is not None:
        parts.append(f"lettera {letter}" + (" (riaperta)" if payload.get("reopen") else ""))
    if (role := payload.get("role")) is not None and "letter" not in payload:
        parts.append(ROLE_LABEL[Role(role)])  # type: ignore[arg-type]
    if (target := payload.get("target_seq")) is not None:
        parts.append(f"(operazione #{target})")
    if (teams := payload.get("teams")) is not None:
        parts.append(f"{len(teams)} squadre")  # type: ignore[arg-type]
    return " ".join(parts)

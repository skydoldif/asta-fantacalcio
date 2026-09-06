"""Pagine pubbliche: tabellone, aggiudicazioni, listone, formazioni e portieri.

Sono in sola lettura e pensate per il telefono, e le vede anche l'admin. Ognuna
sta su una pagina separata invece che in una scheda: con ``st.tabs`` Streamlit
esegue e rinfresca *tutte* le schede a ogni giro, quindi il listone da 518
righe verrebbe ricostruito ogni due secondi anche a chi sta guardando il
tabellone. Con ``st.navigation`` gira solo la pagina aperta.

In cima a ogni pagina c'e' il riquadro del calciatore in asta, sempre nella
stessa forma: chi consulta il listone non deve perdersi la chiamata in corso,
ne' doverla ricercare in un formato diverso.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import streamlit as st

from asta.data.keepers import cached_keeper_grid, cached_keepers
from asta.data.players import cached_lineups, cached_stats_season
from asta.domain.models import ROLE_LABEL, ROLE_ORDER
from asta.domain.reducer import AuctionState
from asta.ui.board import club_breakdown, my_team_picker, teams_board
from asta.ui.components import (
    listone_column_config,
    listone_display,
    listone_filters,
    listone_table,
    now_playing,
    phase_banner,
    sales_filters,
)
from asta.ui.formations import lineups_board
from asta.ui.keepers import (
    MIN_PARTITE_PARARIGORI,
    grid_board,
    keepers_board,
    penalty_savers_board,
)
from asta.ui.wiring import listone_path, viewer_state

_ATTESA = "L'asta non e' ancora stata configurata. Attendi l'amministratore."

#: L'ora si mostra a chi e' nella stanza, non al server: Streamlit Cloud gira
#: su UTC, e un orologio due ore indietro sembrerebbe un'app rotta.
FUSO = "Europe/Rome"


def _aggiornato() -> str:
    """Ora dell'ultima lettura riuscita, in formato ``21:14:32``.

    E' il segnale piu' economico che esista contro il guaio piu' comune della
    serata: la rete dati che salta, Streamlit che congela la pagina e chi
    guarda che continua a leggere numeri vecchi senza accorgersene. Se
    l'orologio non avanza, i numeri non sono di adesso.
    """
    istante = st.session_state.get("viewer_at")
    if istante is None:
        return "mai"
    try:
        fuso = ZoneInfo(FUSO)
    except (ZoneInfoNotFoundError, KeyError):
        fuso = None
    return datetime.fromtimestamp(istante, tz=fuso).strftime("%H:%M:%S")


def _orologio() -> None:
    """Didascalia con l'ora dell'ultimo aggiornamento."""
    st.caption(f"Aggiornato alle {_aggiornato()}.")


def _stato() -> AuctionState | None:
    """Stato corrente, o ``None`` se non c'e' ancora un'asta da mostrare.

    Si occupa anche del banner di connessione instabile, che serve su tutte
    le pagine allo stesso modo.
    """
    state = viewer_state()
    if error := st.session_state.get("viewer_error"):
        st.warning(f"Connessione instabile, dati non aggiornatissimi. ({error})")
        if not state.started:
            # Senza log in cache non si sa nemmeno se l'asta sia partita:
            # aggiungere "attendi l'amministratore" sarebbe inventarselo, e
            # manderebbe a cercare l'admin per un problema di rete.
            return None
    if not state.started:
        st.info(_ATTESA)
        return None
    return state


# ------------------------------------------------------------------ tabellone


def board_page() -> None:
    """Tabellone: calciatore in asta e griglia delle squadre."""
    # Titolo e selettore sulla stessa riga: sul telefono Streamlit impila le
    # colonne da solo, quindi non si perde niente sugli schermi stretti.
    # Titolo a sinistra e selettore spinto al bordo destro della pagina, dove
    # finisce anche la griglia.
    col_titolo, col_squadra = st.columns([2, 2], vertical_alignment="bottom")
    col_titolo.title("🏆 Tabellone")
    with col_squadra, st.container(horizontal=True, horizontal_alignment="right"):
        _my_team_section()
    _board_live()


def _my_team_section() -> None:
    """Selettore della propria squadra.

    Sta fuori dal frammento che si auto-aggiorna: un menu che si ridisegna ogni
    due secondi sarebbe scomodo da usare.
    """
    state = viewer_state()
    if state.started:
        my_team_picker(state)


@st.fragment(run_every=2)
def _board_live() -> None:
    # La didascalia sta qui dentro e non nella pagina: l'orologio deve
    # ridisegnarsi a ogni giro, altrimenti non direbbe niente.
    st.caption(f"Si aggiorna da solo, non serve ricaricare — aggiornato alle {_aggiornato()}.")
    state = _stato()
    if state is None:
        return

    phase_banner(state)
    now_playing(state)
    mia = st.session_state.get("my_team")
    teams_board(state, mia)
    club_breakdown(state, mia)


@st.fragment(run_every=3)
def _now_playing_live() -> None:
    """Solo il riquadro del calciatore in asta, cosi' resta reattivo.

    Sta in un frammento suo perche' le pagine che lo ospitano (listone e
    aggiudicazioni) si rinfrescano molto piu' di rado.
    """
    now_playing(viewer_state())
    _orologio()


# ------------------------------------------------------------ aggiudicazioni


def sales_page() -> None:
    """Tutte le aggiudicazioni, filtrabili per squadra e ruolo."""
    st.title("📜 Aggiudicazioni")
    _now_playing_live()
    _sales_live()


@st.fragment(run_every=10)
def _sales_live() -> None:
    """L'elenco cambia solo quando un calciatore viene aggiudicato, cioe' al
    massimo ogni mezzo minuto: rinfrescarlo piu' spesso ridisegnerebbe la
    tabella sotto le dita di chi sta usando i filtri, senza dire niente di
    nuovo."""
    state = _stato()
    if state is None:
        return

    vendite = sales_filters(state, key_prefix="sales")
    if vendite.empty:
        st.info("Nessuna aggiudicazione ancora registrata.")
        return

    col1, col2 = st.columns(2)
    col1.metric("Calciatori aggiudicati", len(vendite))
    col2.metric("Crediti spesi", int(vendite["Prezzo"].sum()))
    st.dataframe(vendite, hide_index=True, width="stretch", height=520)


# ---------------------------------------------------------------- formazioni


def formations_page() -> None:
    """Probabili formazioni, con i calciatori gia' presi sbiaditi."""
    st.title("📋 Probabili formazioni")
    _now_playing_live()
    st.caption(
        "Formazioni tipo e ballottaggi. Chi e' **sbiadito e barrato** e' gia' stato "
        "aggiudicato; in verde i titolari, in giallo chi si gioca il posto."
    )
    _formations_live()


@st.fragment(run_every=10)
def _formations_live() -> None:
    """Come le aggiudicazioni: cambia solo quando qualcuno viene acquistato."""
    state = _stato()
    if state is None:
        return
    formazioni = cached_lineups(listone_path())
    if not formazioni:
        st.info(
            "Le probabili formazioni non sono state caricate: manca il file "
            "`probabili_formazioni*.md` in `data/raw/`."
        )
        return
    lineups_board(formazioni, state)


# ------------------------------------------------------------------ portieri


def keepers_page() -> None:
    """Gerarchie in porta e griglia delle coppie."""
    st.title("🧤 Portieri")
    _now_playing_live()
    st.caption(
        "Il titolare di ogni squadra. Dove il posto e' in discussione c'e' anche il "
        "portiere da prendere con lui; chi e' **sbiadito e barrato** e' gia' stato aggiudicato."
    )
    _keepers_live()

    grid = cached_keeper_grid()
    if grid.teams:
        st.divider()
        st.subheader("Griglia delle coppie")
        st.caption(
            f"{grid.note} Passa il mouse su una casella: si accendono la riga e la colonna, "
            "cosi' l'incrocio non si perde per strada."
        )
        grid_board(grid)


@st.fragment(run_every=10)
def _keepers_live() -> None:
    """Come le formazioni: cambia solo quando un portiere viene acquistato."""
    state = _stato()
    if state is None:
        return
    gerarchie = cached_keepers(listone_path())
    if not gerarchie:
        st.info(
            "Le gerarchie in porta non sono state caricate: manca il file "
            "`portieri*.md` in `data/raw/`."
        )
        return
    keepers_board(gerarchie, state)

    stagione = cached_stats_season(listone_path())
    st.caption(
        f"🧤 **Pararigori** — chi ne ha parato almeno uno nella stagione "
        f"{stagione or 'precedente'}, con almeno {MIN_PARTITE_PARARIGORI} partite a voto."
    )
    penalty_savers_board(state)


# --------------------------------------------------------------------- listone


def listone_page() -> None:
    """Calciatori ancora liberi, con filtri di ricerca."""
    st.title("🔎 Listone")
    _now_playing_live()
    _listone_live()


@st.fragment(run_every=15)
def _listone_live() -> None:
    """Il listone si rinfresca di rado: ha i filtri, e un campo di ricerca che
    si ridisegna ogni due secondi perderebbe i caratteri mentre si scrive."""
    state = _stato()
    if state is None:
        return

    disponibili = listone_filters(state, key_prefix="viewer")
    rimanenti = {r: len(state.available(r)) for r in ROLE_ORDER}
    st.caption(
        f"{len(state.available())} calciatori liberi — "
        + " · ".join(f"{ROLE_LABEL[r]}: {n}" for r, n in rimanenti.items())
    )
    if not disponibili:
        st.info("Nessun calciatore trovato con questi filtri.")
        return

    stagione = cached_stats_season(listone_path())
    if stagione:
        st.caption(
            f"Rendimenti della stagione {stagione}: le celle vuote sono di chi non ha "
            "giocato in Serie A. Tocca l'intestazione di una colonna per ordinare."
        )
    st.dataframe(
        listone_display(listone_table(disponibili)),
        hide_index=True,
        width="stretch",
        height=460,
        column_config=listone_column_config(),
    )

"""Test dell'interfaccia con l'``AppTest`` di Streamlit.

Girano l'app vera in headless: configurazione, avvio fase, estrazione lettera,
aggiudicazione, undo ed export, piu' il riflesso di tutto questo sulla vista
utente. Servono a intercettare le rotture di interfaccia che i test di dominio
non vedono.
"""

from __future__ import annotations

import re
from unittest import mock

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from asta.domain.events import EventType
from asta.domain.letters import eligible_letters
from asta.domain.models import Role
from asta.service import AuctionService
from asta.ui.components import SENZA_DATI, SUFFISSO_MEMORIA
from asta.ui.wiring import get_service
from conftest import serve_il_listone, serve_l_audio

#: L'app carica il listone all'avvio: senza, qui non gira niente.
pytestmark = serve_il_listone

ADMIN_APP = "apps/admin_app.py"
BOARD_APP = "apps/board_app.py"
SALES_APP = "apps/sales_app.py"
LISTONE_APP = "apps/listone_app.py"
SOUNDBAR_APP = "apps/soundbar_app.py"
FORMATIONS_APP = "apps/formations_app.py"
KEEPERS_APP = "apps/keepers_app.py"


@pytest.fixture(autouse=True)
def shared_repo(monkeypatch):
    """Un repository in memoria condiviso da admin e vista utente.

    Ogni ``AppTest`` ha la sua ``st.cache_resource``, quindi senza questa
    sostituzione le due pagine non vedrebbero la stessa asta: nell'app vera
    e' il database Postgres a fare da collegamento.

    Le cache si svuotano prima e dopo ogni test: ci vivono il servizio
    dell'admin e il log della vista utente, entrambi indicizzati su chiavi
    (l'``auction_id``, la versione del log) che i test riproducono uguali uno
    dopo l'altro. Senza pulizia, l'asta di un test finirebbe dentro il
    successivo.
    """
    from asta.data.repository import InMemoryRepository
    from asta.ui import wiring

    st.cache_resource.clear()
    st.cache_data.clear()
    repo = InMemoryRepository()
    monkeypatch.setattr(wiring, "get_repository", lambda: repo)
    # I secrets della macchina non devono influenzare i test: con un
    # ``admin_password`` configurato in locale la pagina admin mostrerebbe il
    # form di login invece delle sue schede, e i test fallirebbero solo qui.
    from asta import config

    monkeypatch.setattr(config, "database_url", lambda: "")
    monkeypatch.setattr(config, "admin_password", lambda: "")
    yield repo
    st.cache_resource.clear()
    st.cache_data.clear()


def _servizio() -> AuctionService:
    """Il servizio dell'asta.

    Non sta piu' in ``session_state``: vive nella cache di processo, cosi' la
    coda delle scritture sopravvive al ricaricamento della pagina.
    """
    return get_service()


def _click(at: AppTest, label: str) -> AppTest:
    """Clicca il primo pulsante la cui etichetta contiene ``label``."""
    for button in at.button:
        if label in button.label:
            return button.click().run()
    raise AssertionError(
        f"Pulsante {label!r} non trovato. Presenti: {[b.label for b in at.button]}"
    )


def _has(at: AppTest, label: str) -> bool:
    return any(label in b.label for b in at.button)


def _configure(
    at: AppTest, teams: str = "Ajax\nBayern", credits: int = 100, roster: int = 4
) -> AppTest:
    """Compila e invia il form delle impostazioni."""
    at.text_area(key="set_teams").set_value(teams)
    at.number_input(key="set_credits").set_value(credits)
    at.number_input(key="set_roster").set_value(roster)
    for role, value in (("P", 1), ("D", 1), ("C", 1), ("A", 1)):
        at.number_input(key=f"limit_{role}").set_value(value)
    return _click(at, "Salva impostazioni")


@pytest.fixture
def admin() -> AppTest:
    at = AppTest.from_file(ADMIN_APP, default_timeout=60)
    at.run()
    assert not at.exception
    return at


# ------------------------------------------------------------------ avvio


def test_la_pagina_admin_si_apre_senza_errori(admin):
    assert not admin.exception
    # Listone, tabellone e aggiudicazioni vivono sulle pagine pubbliche:
    # qui resta solo quello che serve a condurre l'asta.
    assert [t.label for t in admin.tabs] == [
        "🎯 Asta",
        "⚙️ Impostazioni",
        "📋 Rose e correzioni",
        "📤 Export",
    ]
    assert any("Configura l'asta" in i.value for i in admin.info)


def test_le_impostazioni_dichiarano_il_listone_caricato(admin):
    # Controllo di sanita' prima di iniziare: quanti calciatori e da quale file.
    didascalie = " ".join(c.value for c in admin.caption)
    assert "533" in didascalie
    assert "Quotazioni_Fantacalcio_Stagione_2026_27.xlsx" in didascalie


def test_avviso_modalita_demo_senza_database(admin):
    assert any("Modalita demo" in w.value for w in admin.warning)


def test_impostazioni_non_valide_mostrano_errori(admin):
    at = _configure(admin, teams="Ajax\nBayern", credits=100, roster=25)
    assert any("somma dei limiti" in e.value for e in at.error)


def test_nomi_duplicati_bloccano_il_salvataggio(admin):
    at = _configure(admin, teams="Ajax\najax")
    assert any("duplicati" in e.value for e in at.error)


# ------------------------------------------------------------------ conduzione


def test_flusso_completo_configura_estrai_aggiudica(admin):
    at = _configure(admin)
    assert not at.error
    assert _has(at, "Inizia con i Portieri")

    at = _click(at, "Inizia con i Portieri")
    assert _has(at, "Estrai lettera")

    at = _click(at, "Estrai lettera")
    state = _servizio().state()
    assert state.current_letter is not None
    assert state.current_role.value == "P"

    # Il calciatore in asta e' mostrato con nome, ruolo e squadra.
    from asta.domain.letters import current_player

    player = current_player(state)
    assert player is not None
    markdown = " ".join(m.value for m in at.markdown)
    assert player.name in markdown
    assert player.team in markdown

    at = _click(at, "Aggiudica")
    state = _servizio().state()
    assert state.is_taken(player.id)
    assert state.teams["Ajax"].spent == 1
    assert state.teams["Ajax"].credits_left == 99


def test_salto_lascia_il_calciatore_nel_listone(admin):
    at = _click(_configure(admin), "Inizia con i Portieri")
    at = _click(at, "Estrai lettera")
    from asta.domain.letters import current_player

    player = current_player(_servizio().state())
    at = _click(at, "Salta")
    state = _servizio().state()
    assert not state.is_taken(player.id)
    assert player.id in state.skipped


def test_undo_dall_interfaccia(admin):
    at = _click(_configure(admin), "Inizia con i Portieri")
    at = _click(at, "Estrai lettera")
    at = _click(at, "Aggiudica")
    assert _servizio().state().assignments

    at = _click(at, "Annulla")
    assert _servizio().state().assignments == {}


def test_le_impostazioni_si_bloccano_a_asta_iniziata(admin):
    at = _click(_configure(admin), "Inizia con i Portieri")
    assert any("gia' iniziata" in w.value for w in at.warning)


def test_il_pulsante_di_avanzamento_fase_appare(admin):
    at = _click(_configure(admin), "Inizia con i Portieri")
    assert _has(at, "Passa ai Difensori")


def _bottone(at: AppTest, label: str):
    """Il primo pulsante la cui etichetta contiene ``label``."""
    for button in at.button:
        if label in button.label:
            return button
    raise AssertionError(f"Pulsante {label!r} non trovato")


def test_non_si_avanza_di_fase_a_reparto_incompleto(admin):
    """Dopo il cambio di fase i calciatori del reparto non sono piu' acquistabili."""
    at = _click(_configure(admin), "Inizia con i Portieri")
    assert _servizio().state().teams["Ajax"].slots_left(Role.P) == 1
    assert _bottone(at, "Passa ai Difensori").disabled is True


def test_a_reparto_completo_l_avanzamento_si_sblocca(admin):
    at = _click(_configure(admin), "Inizia con i Portieri")
    service = _servizio()
    # Un portiere a testa: il reparto e' completo per entrambe le squadre.
    # I calciatori si prendono dal listone vero, che e' quello che carica l'app.
    for player, squadra in zip(
        service.state().available(Role.P)[:2], ("Ajax", "Bayern"), strict=True
    ):
        service.record(
            EventType.PLAYER_ASSIGNED,
            {"player_id": player.id, "team": squadra, "price": 5},
        )
    at = at.run()

    # Il blocco guarda il reparto in corso, non la rosa intera
    # (quella resta incompleta: mancano difensori, centrocampisti e attaccanti).
    state = _servizio().state()
    assert all(t.slots_left(Role.P) == 0 for t in state.teams.values())
    assert state.incomplete_teams() == ("Ajax", "Bayern")
    assert _bottone(at, "Passa ai Difensori").disabled is False

    at = _click(at, "Passa ai Difensori")
    assert _servizio().state().current_role == Role.D


def _portieri_a_tutti(at: AppTest) -> AppTest:
    """Un portiere a testa: il reparto e' completo e si puo' cambiare fase."""
    service = _servizio()
    for player, squadra in zip(
        service.state().available(Role.P)[:2], ("Ajax", "Bayern"), strict=True
    ):
        service.record(
            EventType.PLAYER_ASSIGNED,
            {"player_id": player.id, "team": squadra, "price": 5},
        )
    return at.run()


def test_il_backup_si_scarica_da_solo_a_fine_reparto(admin):
    admin.checkbox(key="set_auto_backup").set_value(True)
    at = _portieri_a_tutti(_click(_configure(admin), "Inizia con i Portieri"))
    assert not at.get("iframe"), "durante il reparto non deve partire niente"

    at = _click(at, "Passa ai Difensori")
    srcdoc = " ".join(el.proto.srcdoc for el in at.get("iframe"))
    assert "backup_fine_portieri" in srcdoc
    assert "PLAYER_ASSIGNED" in srcdoc, "nel file ci deve essere il log dell'asta"

    # Parte una volta sola: al giro dopo l'iframe non c'e' piu'.
    assert not at.run().get("iframe")


def test_il_backup_parte_quando_il_database_non_risponde(admin, shared_repo, monkeypatch):
    admin.checkbox(key="set_auto_backup").set_value(True)
    at = _click(_configure(admin), "Inizia con i Portieri")
    service = _servizio()

    # La rete si stacca e si riattacca con questo interruttore: qui non si usa
    # ``monkeypatch.undo()`` perche' rimetterebbe a posto anche le sostituzioni
    # della fixture ``shared_repo``, che condivide lo stesso monkeypatch.
    scrittura = shared_repo.append
    rete = {"su": False}

    def append(event):
        if not rete["su"]:
            raise ConnectionError("rete assente")
        scrittura(event)

    monkeypatch.setattr(shared_repo, "append", append)

    def salta_uno() -> None:
        service.record(
            EventType.PLAYER_SKIPPED,
            {"player_id": service.state().available(Role.P)[0].id},
        )

    salta_uno()
    at = at.run()
    assert not service.synced
    assert "backup_offline" in " ".join(el.proto.srcdoc for el in at.get("iframe"))

    # Finche' la rete resta giu' non parte un file a ogni interazione.
    assert not at.run().get("iframe")

    # Rete tornata: la coda si svuota e non si scarica niente.
    rete["su"] = True
    service.flush()
    at = at.run()
    assert service.synced
    assert not at.get("iframe")

    # Seconda caduta: e' un altro momento, e si merita il suo backup.
    rete["su"] = False
    salta_uno()
    at = at.run()
    assert "backup_offline" in " ".join(el.proto.srcdoc for el in at.get("iframe"))


def test_senza_la_spunta_non_si_scarica_niente(admin):
    at = _portieri_a_tutti(_click(_configure(admin), "Inizia con i Portieri"))
    at = _click(at, "Passa ai Difensori")
    assert _servizio().state().current_role == Role.D
    assert not at.get("iframe")


# ------------------------------------------------------- coda e riconnessione


def _rete_giu(shared_repo, monkeypatch) -> dict[str, bool]:
    """Stacca la rete e restituisce l'interruttore per riattaccarla.

    Non si usa ``monkeypatch.undo()``: rimetterebbe a posto anche le
    sostituzioni della fixture ``shared_repo``, che condivide lo stesso
    monkeypatch.
    """
    scrittura = shared_repo.append
    rete = {"su": False}

    def append(event):
        if not rete["su"]:
            raise ConnectionError("rete assente")
        scrittura(event)

    monkeypatch.setattr(shared_repo, "append", append)
    return rete


def test_la_coda_sopravvive_al_ricaricamento_della_pagina(admin, shared_repo, monkeypatch):
    """Il difetto piu' pericoloso della serata, e il meno visibile.

    Con la rete giu' le aggiudicazioni restano in coda, applicate solo in
    locale. Ricaricare la pagina - la reazione naturale davanti a una
    schermata bloccata - apre una sessione nuova: se il servizio vivesse li',
    quelle aggiudicazioni sparirebbero senza un messaggio.
    """
    at = _click(_configure(admin), "Inizia con i Portieri")
    _rete_giu(shared_repo, monkeypatch)

    at = _click(_click(at, "Estrai lettera"), "Aggiudica")
    service = _servizio()
    assert not service.synced
    aggiudicazioni = service.state().assignments
    assert aggiudicazioni

    # Il ricaricamento: sessione nuova, stesso processo.
    ricaricata = AppTest.from_file(ADMIN_APP, default_timeout=60)
    ricaricata.run()

    assert not ricaricata.exception
    assert "service" not in ricaricata.session_state
    assert _servizio() is service
    assert _servizio().state().assignments == aggiudicazioni
    assert any("non ancora salvate" in e.value for e in ricaricata.error)


def test_la_coda_si_svuota_da_sola_quando_la_rete_torna(admin, shared_repo, monkeypatch):
    """Il banner ritenta da solo, senza aspettare un click.

    La rete torna quando le pare, spesso mentre l'admin sta fermo ad
    ascoltare i rilanci. Il banner vive in un frammento con ``run_every=5``:
    qui l'``AppTest`` non fa scattare il timer, ma la prova e' la stessa -
    lo svuotamento avviene nel disegno del banner e non dentro il pulsante.
    """
    at = _click(_configure(admin), "Inizia con i Portieri")
    rete = _rete_giu(shared_repo, monkeypatch)

    at = _click(_click(at, "Estrai lettera"), "Aggiudica")
    service = _servizio()
    assert not service.synced
    assert any("non ancora salvate" in e.value for e in at.error)

    rete["su"] = True
    at = at.run()  # nessun click: solo il giro successivo del frammento

    assert service.synced
    assert not any("non ancora salvate" in e.value for e in at.error)
    assert any("salvate sul database" in s.value for s in at.success)
    assert len(shared_repo.load()) == len(service.events)


def test_chi_non_ha_completato_il_reparto_e_scritto_a_schermo(admin):
    at = _click(_configure(admin), "Inizia con i Portieri")
    didascalie = " ".join(c.value for c in at.caption)
    assert "solo a reparto completo" in didascalie
    assert "Ajax" in didascalie and "Bayern" in didascalie


def test_download_csv_disponibile(admin):
    at = _configure(admin)
    labels = [d.label for d in at.get("download_button")]
    assert any("CSV" in label for label in labels)


# ------------------------------------------------------------------ vista utente


def _pagina(path: str) -> AppTest:
    at = AppTest.from_file(path, default_timeout=60)
    at.run()
    assert not at.exception
    return at


def _asta_avviata(admin: AppTest) -> AppTest:
    """Configura, avvia la fase portieri, aggiudica e lascia qualcuno in asta.

    La lettera viene sorteggiata davvero: se ne esce una con un solo portiere
    disponibile, dopo l'aggiudicazione non resta nessuno in asta. Senza il
    rilancio i test sul riquadro "in asta ora" passerebbero o meno a seconda
    del sorteggio.
    """
    at = _click(_configure(admin), "Inizia con i Portieri")
    at = _click(at, "Estrai lettera")
    at = _click(at, "Aggiudica")
    for _ in range(15):
        if _has(at, "Aggiudica"):
            return at
        at = _click(at, "Estrai lettera")
    raise AssertionError("nessun calciatore in asta dopo 15 lettere")


def test_il_tabellone_riflette_l_asta(admin):
    _asta_avviata(admin)

    board = _pagina(BOARD_APP)
    assert "Tabellone" in board.title[0].value
    assert not any("non e' ancora stata configurata" in i.value for i in board.info)
    # La griglia delle squadre mostra l'acquisto e i crediti aggiornati.
    html = " ".join(m.value for m in board.markdown)
    assert "Ajax" in html
    assert '<div class="tb-credits">99<small>' in html


def test_il_tabellone_evidenzia_la_squadra_scelta(admin):
    """Il menu sparisce dentro un popover; la card scelta si colora."""
    _asta_avviata(admin)

    board = _pagina(BOARD_APP)
    assert 'class="tb-card me"' not in " ".join(m.value for m in board.markdown)

    # Il menu non sta in pagina ma dentro un popover, che e' l'unica cosa in vista.
    popover = board.get("popover")[0]
    assert popover.proto.popover.label == "👤 La mia squadra"
    assert [sb.key for sb in popover.selectbox] == ["my_team_menu"]

    board.session_state["my_team"] = "Ajax"
    board.run()

    html = " ".join(m.value for m in board.markdown)
    assert html.count('class="tb-card me"') == 1
    assert ">TU</span>" in html
    # Il pulsantino ora porta il nome della squadra e resta l'unico modo di cambiarla.
    popover = board.get("popover")[0]
    assert popover.proto.popover.label == "🟢 Ajax"
    assert [sb.key for sb in popover.selectbox] == ["my_team_menu"]


def test_la_squadra_scelta_sopravvive_al_cambio_pagina(admin):
    """Regressione: cambiando pagina la squadra evidenziata si azzerava.

    Streamlit butta lo stato dei widget che in quel giro non ha disegnato, e
    il menu della squadra vive solo sul Tabellone: con una chiave sola bastava
    passare al Listone e tornare per ritrovarsi senza squadra. Ora la scelta
    sta in una chiave sua, che non e' quella del menu.
    """
    _asta_avviata(admin)
    board = _pagina(BOARD_APP)
    board.get("popover")[0].selectbox[0].select("Ajax").run()

    assert board.get("popover")[0].selectbox[0].key == "my_team_menu"
    assert board.session_state["my_team"] == "Ajax", "la scelta non sta nella chiave del menu"

    # Tornando sul Tabellone dopo un'altra pagina sopravvive solo quella
    # chiave: il menu deve ripescarsela da li'.
    ritorno = AppTest.from_file(BOARD_APP, default_timeout=60)
    ritorno.session_state["my_team"] = "Ajax"
    ritorno.run()

    assert not ritorno.exception
    assert ritorno.get("popover")[0].proto.popover.label == "🟢 Ajax"
    assert ritorno.get("popover")[0].selectbox[0].value == "Ajax"
    assert 'class="tb-card me"' in " ".join(m.value for m in ritorno.markdown)


def _orologio(at: AppTest) -> str:
    """La didascalia con l'ora dell'ultimo aggiornamento."""
    for caption in at.caption:
        if "aggiornato alle" in caption.value.lower():
            return caption.value
    raise AssertionError(f"Orologio non trovato fra: {[c.value for c in at.caption]}")


def test_il_tabellone_dice_a_che_ora_si_e_aggiornato(admin):
    _asta_avviata(admin)
    board = _pagina(BOARD_APP)
    assert re.search(r"\d\d:\d\d:\d\d", _orologio(board))


def test_l_orologio_si_ferma_quando_i_dati_non_arrivano(admin, shared_repo, monkeypatch):
    """Il guaio piu' comune della serata: la rete salta e chi guarda non lo sa.

    La pagina continua a disegnarsi con i numeri di prima; l'unica cosa che
    la tradisce e' l'ora, che deve restare quella dell'ultima lettura
    *riuscita* e non quella dell'ultimo disegno.
    """
    _asta_avviata(admin)
    board = _pagina(BOARD_APP)
    letto = board.session_state["viewer_at"]

    board = board.run()
    assert board.session_state["viewer_at"] > letto, "l'ora non avanza a rete buona"
    letto = board.session_state["viewer_at"]
    mostrata = _orologio(board)

    def version():
        raise ConnectionError("rete assente")

    monkeypatch.setattr(shared_repo, "version", version)
    board = board.run()

    assert board.session_state["viewer_at"] == letto
    assert _orologio(board) == mostrata
    assert any("Connessione instabile" in w.value for w in board.warning)


def test_durante_un_blackout_non_si_dice_che_l_asta_non_esiste(shared_repo, monkeypatch):
    """Chi apre l'app mentre il database tace vedeva due messaggi, di cui uno
    falso: "attendi l'amministratore" mandava a cercare l'admin per un
    problema di rete."""

    def version():
        raise ConnectionError("rete assente")

    monkeypatch.setattr(shared_repo, "version", version)
    board = _pagina(BOARD_APP)

    assert any("Connessione instabile" in w.value for w in board.warning)
    assert not any("Attendi l'amministratore" in i.value for i in board.info)


def test_il_log_si_legge_una_volta_sola_per_tutti(admin, shared_repo, monkeypatch):
    """Dieci telefoni collegati non sono dieci letture del log.

    La versione la chiede ognuno per conto suo: e' la query leggera, ed e'
    quella che decide quanto tardi arriva un'aggiudicazione sugli schermi.
    Il log invece si legge una volta per versione e lo condividono tutti.
    """
    _asta_avviata(admin)

    letture = {"n": 0}
    lettura = shared_repo.load

    def load():
        letture["n"] += 1
        return lettura()

    monkeypatch.setattr(shared_repo, "load", load)

    primo = _pagina(BOARD_APP)
    secondo = _pagina(BOARD_APP)

    assert not primo.exception and not secondo.exception
    assert letture["n"] == 1, "il log e' stato riletto per ogni spettatore"

    # Un'aggiudicazione in piu' cambia la versione: quella si rilegge, una volta.
    _click(_click(admin, "Estrai lettera"), "Aggiudica")
    _pagina(BOARD_APP)
    _pagina(BOARD_APP)
    assert letture["n"] == 2


def test_la_composizione_per_club_compare_solo_a_squadra_scelta(admin):
    _asta_avviata(admin)

    board = _pagina(BOARD_APP)
    assert 'class="cb"' not in " ".join(m.value for m in board.markdown)

    board.session_state["my_team"] = "Ajax"
    board.run()

    html = " ".join(m.value for m in board.markdown)
    # Ajax ha un solo calciatore: un pallino verde con "1", e i 19 club
    # da cui non ha ancora preso nessuno con lo zero rosso.
    assert 'class="cb-n">1</b>' in html
    assert html.count('class="cb-n zero">0</b>') == 19
    # Titolo e riga di riepilogo stanno dentro il riquadro, non fuori.
    assert "<div class='cb-titolo'>Copertura squadra</div>" in html
    assert "La rosa di <b>Ajax</b>: 1 calciatore da 1 club su 20" in html


def test_le_formazioni_sbiadiscono_chi_e_gia_stato_preso(admin):
    _asta_avviata(admin)
    service = _servizio()
    # Un titolare vero, non uno a caso: il portiere dell'Atalanta e' solo nel
    # suo posto in formazione, quindi in pagina deve passare da verde a barrato.
    titolare = next(p for p in service.listone.players if p.name == "Carnesecchi")
    assert titolare.starter is not None

    prima = " ".join(m.value for m in _pagina(FORMATIONS_APP).markdown)
    assert "pf-card" in prima, "la pagina disegna le squadre"
    assert 'class="pf-name t" title="Titolare">Carnesecchi' in prima

    service.record(
        EventType.PLAYER_ASSIGNED,
        {"player_id": titolare.id, "team": "Ajax", "price": 12},
    )
    dopo = " ".join(m.value for m in _pagina(FORMATIONS_APP).markdown)
    assert 'class="pf-name taken" title="Preso da Ajax per 12">Carnesecchi' in dopo


def test_la_pagina_portieri_mostra_gerarchie_e_griglia(admin):
    _asta_avviata(admin)
    portieri = _pagina(KEEPERS_APP)
    html = " ".join(m.value for m in portieri.markdown)

    assert html.count("gk-card") >= 20, "una card per squadra di Serie A"
    # Sotto le card, la striscia dei pararigori.
    assert 'class="gp-p-n"' in html
    # La griglia sta sotto, con le sue venti colonne e la riga che si accende.
    assert '<table class="gp">' in html
    assert ".gp tr:hover>*{background" in html


def test_le_formazioni_partono_anche_senza_asta():
    formazioni = _pagina(FORMATIONS_APP)
    assert not formazioni.exception
    assert any("non e' ancora stata configurata" in i.value for i in formazioni.info)


@serve_l_audio
def test_la_soundbar_sta_nella_barra_laterale():
    soundbar = _pagina(SOUNDBAR_APP)

    # Non e' piu' una pagina: sta nella barra laterale, cosi' si fa partire
    # un tormentone senza lasciare il tabellone.
    assert [h.value for h in soundbar.sidebar.get("subheader")] == ["🔊 Soundbar"]
    assert len(soundbar.sidebar.get("iframe")) == 1
    assert not [el for el in soundbar.get("iframe") if el not in soundbar.sidebar.get("iframe")]

    # Dentro l'iframe ci sono tutti i pulsanti e il dado, senza dipendere da
    # come Streamlit lo incornicia.
    from asta.ui.soundbar import load_sounds

    quanti = sum(len(gruppo) for _, gruppo in load_sounds())
    html = " ".join(el.proto.srcdoc for el in soundbar.sidebar.get("iframe"))
    assert html.count("data-i='") == quanti
    assert "sb-dado" in html


def test_il_riquadro_in_asta_non_mostra_i_numeri_del_listone(admin):
    _asta_avviata(admin)
    card = next(m.value for m in _pagina(BOARD_APP).markdown if "In asta ora" in m.value)

    # Quotazione, fantavalore e Id restano nel dominio ma non si mostrano.
    for parola in ("Quotazione", "Fantavalore", "Id "):
        assert parola not in card


def test_il_riquadro_in_asta_mostra_lo_stemma_del_club(admin):
    _asta_avviata(admin)
    card = next(m.value for m in _pagina(BOARD_APP).markdown if "In asta ora" in m.value)
    assert "app/static/loghi/" in card, "manca lo stemma del club"
    assert "serie-a.svg" in card, "manca la filigrana della lega"


def test_la_pagina_aggiudicazioni_elenca_le_vendite(admin):
    _asta_avviata(admin)

    sales = _pagina(SALES_APP)
    tabelle = [df.value for df in sales.dataframe]
    assert tabelle, "la tabella delle aggiudicazioni manca"
    assert "Ajax" in str(tabelle[0].values)
    assert [m.label for m in sales.metric] == ["Calciatori aggiudicati", "Crediti spesi"]


def test_il_listone_perde_i_calciatori_venduti(admin):
    _asta_avviata(admin)
    venduto = next(iter(_servizio().state().assignments.values()))
    nome = _servizio().state().listone.get(venduto.player_id).name

    listone = _pagina(LISTONE_APP)
    tabella = listone.dataframe[0].value
    assert nome not in str(tabella.values)
    # Id, quotazione e fantavalore restano nel dominio ma non si mostrano;
    # le statistiche compaiono per esteso, mai con gli acronimi del file.
    assert list(tabella.columns) == [
        "Ruolo",
        "Calciatore",
        "Squadra",
        "Fascia",
        "Titolarità",
        "Partite a voto",
        "Media voto",
        "Fantamedia",
        "⚽",
        "👟",
        "Rigori calciati",
        "🟨",
        "🟥",
        "Rigorista",
        "Corner",
        "Punizioni",
        "🚑",
    ]


def test_il_listone_si_filtra_per_titolarita(admin):
    """Con centottanta difensori liberi, "chi gioca?" e' la prima sfoltita."""
    _asta_avviata(admin)
    listone = _pagina(LISTONE_APP)
    menu = listone.selectbox(key="viewer_starting")
    assert menu.options == [
        "Tutte",
        "Titolare",
        "Ballottaggio",
        "Fuori dagli 11",
    ]
    tutti = len(listone.dataframe[0].value)

    listone = menu.select("Ballottaggio").run()
    ballottaggi = listone.dataframe[0].value["Titolarità"]
    assert not listone.exception
    assert 0 < len(ballottaggi) < tutti
    assert set(ballottaggi) == {1}, "in elenco c'e' qualcuno che non e' in ballottaggio"

    listone = listone.selectbox(key="viewer_starting").select("Titolare").run()
    assert set(listone.dataframe[0].value["Titolarità"]) == {2}

    # Chi le probabili formazioni non nominano: la cella resta vuota a
    # schermo, e sotto c'e' la sentinella che la manda in fondo agli ordini.
    listone = listone.selectbox(key="viewer_starting").select("Fuori dagli 11").run()
    assert set(listone.dataframe[0].value["Titolarità"]) == {SENZA_DATI}


def test_cercare_un_calciatore_inesistente_non_rompe_il_listone(admin):
    # Capita di continuo durante l'asta: si cerca uno gia' venduto, o si
    # sbaglia a scrivere il nome. La pagina deve restare in piedi.
    _asta_avviata(admin)
    listone = _pagina(LISTONE_APP)

    listone.text_input(key="viewer_q").set_value("Zzzznessuno").run()

    assert not listone.exception
    assert any("Nessun calciatore trovato" in i.value for i in listone.info)


def test_il_riquadro_in_asta_e_identico_su_tutte_le_pagine(admin):
    """Chi consulta listone o aggiudicazioni non deve perdersi la chiamata,
    ne' doverla ricercare in un formato diverso da pagina a pagina."""
    at = _click(_configure(admin), "Inizia con i Portieri")
    at = _click(at, "Estrai lettera")
    from asta.domain.letters import current_player

    in_asta = current_player(_servizio().state())
    assert in_asta is not None

    riquadri = {}
    for path in (BOARD_APP, LISTONE_APP, SALES_APP):
        blocchi = [m.value for m in _pagina(path).markdown if "In asta ora" in m.value]
        assert len(blocchi) == 1, path
        assert in_asta.name in blocchi[0], path
        riquadri[path] = blocchi[0]

    assert len(set(riquadri.values())) == 1, "il riquadro differisce fra le pagine"


def test_le_pagine_pubbliche_partono_anche_senza_asta():
    for path in (BOARD_APP, SALES_APP, LISTONE_APP):
        at = _pagina(path)
        assert any("non e' ancora stata configurata" in i.value for i in at.info), path


# ------------------------------------------- la coda dentro il riquadro verde


def _lettera_affollata(admin: AppTest) -> tuple[AppTest, list[str]]:
    """Asta avviata su una lettera con almeno due calciatori.

    L'estrazione e' casuale e questa prova ha bisogno di una coda: la lettera
    si sceglie qui e si impone scrivendo l'evento. Quale sia non conta, quindi
    si prende dal listone vero invece di fissarne una a mano - l'anno prossimo
    potrebbe restare senza portieri.
    """
    from asta.domain.letters import letter_queue

    at = _click(_configure(admin), "Inizia con i Portieri")
    stato = _servizio().state()
    lettera = next(c for c in eligible_letters(stato) if len(letter_queue(stato, c)) >= 2)
    _servizio().record(EventType.LETTER_DRAWN, {"role": Role.P.value, "letter": lettera, "seed": 1})
    at = at.run()
    return at, [p.name for p in letter_queue(_servizio().state())]


def _riquadro(at: AppTest) -> str:
    return next(m.value for m in at.markdown if "In asta ora" in m.value)


def test_la_coda_sta_dentro_il_riquadro_in_asta(admin):
    at, nomi = _lettera_affollata(admin)
    riquadro = _riquadro(at)
    assert 'class="ia-coda"' in riquadro
    # Tutta la coda, non i primi pochi: la colonna scorre.
    assert f"In coda · {len(nomi) - 1}" in riquadro
    assert all(nome in riquadro for nome in nomi[1:])


def test_la_coda_non_ripete_chi_e_in_asta_ora(admin):
    at, nomi = _lettera_affollata(admin)
    coda = _riquadro(at).split('class="ia-coda"')[1].split("</div></div>")[0]
    assert nomi[0] not in coda
    assert nomi[1] in coda


def test_senza_coda_la_colonna_sparisce(admin):
    """Ultimo della lettera: niente titolino "In coda" senza nomi sotto."""
    at, nomi = _lettera_affollata(admin)
    for _ in range(len(nomi) - 1):
        at = _click(at, "Salta")
    assert "ia-coda" not in _riquadro(at)


def test_la_coda_si_vede_anche_dalle_pagine_pubbliche(admin):
    """Il riquadro e' lo stesso ovunque: la coda non e' un privilegio dell'admin."""
    at, nomi = _lettera_affollata(admin)
    assert "ia-coda" in _riquadro(at)
    for path in (BOARD_APP, LISTONE_APP, SALES_APP):
        riquadro = _riquadro(_pagina(path))
        assert 'class="ia-coda"' in riquadro, path
        assert nomi[1] in riquadro, path


def _css_coda(at: AppTest) -> str:
    return next(m.value for m in at.markdown if ".ia-coda{" in m.value)


def test_la_coda_chiude_la_card_e_non_la_apre(admin):
    """Sul telefono rientra nel flusso: deve stare dopo le statistiche.

    Sul desktop e' in posizione assoluta e l'ordine nel documento non si
    vede, quindi il difetto si nota solo da telefono - dove la coda finiva
    sopra il nome da leggere a voce alta.
    """
    at, _ = _lettera_affollata(admin)
    riquadro = _riquadro(at)
    assert riquadro.index("In asta ora") < riquadro.index('class="ia-coda"')
    assert riquadro.index("Stagione") < riquadro.index('class="ia-coda"')


def test_sul_telefono_la_coda_si_corica_invece_di_sparire(admin):
    """Stretto si legge di traverso, non si nasconde."""
    at, _ = _lettera_affollata(admin)
    stretto = _css_coda(at).split("@media (max-width:640px)")[1]
    assert "display:none" not in stretto
    assert "position:static" in stretto
    assert "overflow-x:auto" in stretto


# --------------------------------------------------- filtri e cambio pagina


def _dopo_un_giro_altrove(path: str, prima: AppTest) -> AppTest:
    """Riapre una pagina come dopo essere andati altrove e tornati indietro.

    Le pagine pubbliche sono pagine vere, non schede: passando da una
    all'altra Streamlit ripulisce lo stato dei widget che non disegna piu',
    e i menu ripartono dalla loro voce di partenza. Quello che *non*
    appartiene a un widget invece resta, ed e' li' che i filtri si annotano:
    la pagina nuova eredita solo quello.
    """
    at = AppTest.from_file(path, default_timeout=60)
    for chiave in prima.session_state.filtered_state:
        if chiave.endswith(SUFFISSO_MEMORIA):
            at.session_state[chiave] = prima.session_state[chiave]
    at.run()
    assert not at.exception
    return at


def test_i_filtri_del_listone_sopravvivono_al_cambio_pagina(admin):
    """Il guaio vero dell'asta: un giro sul tabellone e si ricominciava da capo."""
    _asta_avviata(admin)
    listone = _pagina(LISTONE_APP)
    listone = listone.selectbox(key="viewer_role").select("Portieri").run()
    listone = listone.selectbox(key="viewer_starting").select("Titolare").run()
    listone = listone.text_input(key="viewer_q").set_value("a").run()
    portieri_titolari = len(listone.dataframe[0].value)
    assert portieri_titolari > 0

    listone = _dopo_un_giro_altrove(LISTONE_APP, listone)

    assert listone.selectbox(key="viewer_role").value == "Portieri"
    assert listone.selectbox(key="viewer_starting").value == "Titolare"
    assert listone.text_input(key="viewer_q").value == "a"
    assert len(listone.dataframe[0].value) == portieri_titolari
    assert set(listone.dataframe[0].value["Ruolo"]) == {1}, "sono rimasti solo i portieri"


def test_i_filtri_delle_aggiudicazioni_sopravvivono_al_cambio_pagina(admin):
    _asta_avviata(admin)
    vendite = _pagina(SALES_APP)
    vendite = vendite.selectbox(key="sales_team").select("Ajax").run()
    quante = len(vendite.dataframe[0].value)

    vendite = _dopo_un_giro_altrove(SALES_APP, vendite)

    assert vendite.selectbox(key="sales_team").value == "Ajax"
    assert len(vendite.dataframe[0].value) == quante


def test_una_fascia_che_non_esiste_piu_non_blocca_il_listone(admin):
    """Cambiando reparto le fasce cambiano: quella ricordata puo' sparire."""
    _asta_avviata(admin)
    listone = _pagina(LISTONE_APP)
    listone = listone.selectbox(key="viewer_role").select("Portieri").run()
    listone.session_state["viewer_tier" + SUFFISSO_MEMORIA] = "F1"  # fascia di un altro reparto

    listone = _dopo_un_giro_altrove(LISTONE_APP, listone)

    assert not listone.exception
    assert listone.selectbox(key="viewer_tier").value == "Tutte"


# ------------------------------------------- listone caricato dall'app


def test_senza_listone_l_app_non_si_schianta_e_dice_cosa_fare():
    """Chi apre l'app appena installata deve trovare il pannello, non un traceback."""
    from asta.ui import wiring

    wiring.dimentica_il_listone()
    with mock.patch.object(wiring, "load_listone", side_effect=FileNotFoundError("niente")):
        at = AppTest.from_file(ADMIN_APP, default_timeout=60)
        at.run()

    assert not at.exception
    assert any("Nessun listone caricato" in i.value for i in at.info)
    wiring.dimentica_il_listone()


@serve_il_listone
def test_il_listone_caricato_prende_il_posto_di_quello_nel_file(shared_repo):
    """Tutta la catena tranne il widget: database -> cache -> pagina.

    Il file caricato non passa da qui (ne' l'``AppTest`` ne' il browser
    sanno caricare file), ma quello che genera si': ``costruisci`` e'
    verificato in ``test_upload.py``, e da li' in poi comanda questo.
    """
    from asta.ui.wiring import dimentica_il_listone

    finto = {
        "source": "Quotazioni_finte.xlsx",
        "count": 2,
        "players": [
            {"id": 1, "role": "P", "name": "Uno", "team": "Ajax", "quotation": 1, "fvm": 1},
            {"id": 2, "role": "A", "name": "Due", "team": "Bayern", "quotation": 1, "fvm": 1},
        ],
    }
    shared_repo.save_listone(finto)
    dimentica_il_listone()

    at = AppTest.from_file(ADMIN_APP, default_timeout=60)
    at.run()
    assert not at.exception

    didascalie = " ".join(c.value for c in at.caption)
    assert "**2** calciatori" in didascalie, "mostra ancora il listone del file"
    assert "Quotazioni_finte.xlsx" in didascalie

    dimentica_il_listone()


@serve_il_listone
def test_dimenticare_il_listone_non_tocca_la_coda_dell_admin(shared_repo):
    """Svuotare le cache non deve portarsi via le aggiudicazioni in sospeso."""
    from asta.ui.wiring import dimentica_il_listone

    _asta_avviata(admin_app := AppTest.from_file(ADMIN_APP, default_timeout=60).run())
    assert admin_app is not None
    servizio = _servizio()
    quanti = len(servizio.events)

    dimentica_il_listone()

    assert _servizio() is servizio, "il servizio dell'admin e' stato ricostruito"
    assert len(_servizio().events) == quanti


@serve_il_listone
def test_il_listone_appena_caricato_si_vede_senza_riavviare_l_app(shared_repo):
    """Il difetto che rendeva il pulsante "Genera il listone" apparentemente morto.

    Il servizio dell'admin vive nella cache di processo e si tiene *dentro* il
    listone di quando e' nato. Svuotare le cache del listone non lo toccava:
    il caricamento andava a buon fine, il database aveva il listone nuovo, e
    la pagina continuava a mostrare quello vecchio. Da fuori sembrava che il
    pulsante non facesse niente.
    """
    from asta.ui.wiring import aggiorna_il_listone

    at = AppTest.from_file(ADMIN_APP, default_timeout=60)
    at.run()
    prima = len(_servizio().state().listone.players)

    shared_repo.save_listone(
        {
            "source": "Quotazioni_nuove.xlsx",
            "count": 2,
            "players": [
                {"id": 1, "role": "P", "name": "Uno", "team": "Ajax", "quotation": 1, "fvm": 1},
                {"id": 2, "role": "A", "name": "Due", "team": "Bayern", "quotation": 1, "fvm": 1},
            ],
        }
    )
    # Quello che fa il pulsante "Genera il listone" dopo aver salvato.
    aggiorna_il_listone(_servizio())
    at.run()

    assert not at.exception
    assert prima != 2, "la prova non direbbe niente se il listone fosse gia' di due"
    assert len(_servizio().state().listone.players) == 2, "il servizio ha ancora il listone vecchio"
    assert "**2** calciatori" in " ".join(c.value for c in at.caption)


@serve_il_listone
def test_l_esito_del_caricamento_sopravvive_al_rerun(shared_repo):
    """Il rerun butta via quello che si e' appena disegnato.

    Scrivere il "listone caricato" prima di ``st.rerun()`` vuol dire non
    mostrarlo mai: da fuori il pulsante sembra non fare niente. L'esito
    passa dalla sessione e si disegna al giro dopo.
    """
    from asta.ui.admin import ESITO_CARICAMENTO

    at = AppTest.from_file(ADMIN_APP, default_timeout=60)
    at.run()
    at.session_state[ESITO_CARICAMENTO] = {"count": 533, "segnalazioni": ["Tizio (Ajax)"]}
    at = at.run()

    assert not at.exception
    assert any("533 calciatori" in s.value for s in at.success)
    assert any("1 nomi da controllare" in e.label for e in at.expander)
    # Mostrato una volta sola: al giro dopo non deve ricomparire.
    assert not at.run().success

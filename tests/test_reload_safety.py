"""Regressione: l'asta deve reggere il ricaricamento dei moduli di Streamlit.

Streamlit ricarica i moduli quando cambia un sorgente, ma gli oggetti dentro
``st.cache_resource`` e ``st.session_state`` restano quelli costruiti con la
classe precedente. Si finisce cosi' con due classi ``Role`` distinte vive
insieme: il listone in cache usa la vecchia, la fase-ruolo appena ricalcolata
usa la nuova. Con un confronto ``is`` l'app rifiutava ogni calciatore
("Okoye e' un P: e' in corso l'asta dei portieri"); con ``==`` funziona,
perche' ``StrEnum`` confronta il valore.

Questi test ricreano quella situazione caricando una seconda copia di
``asta.domain.models`` sotto un altro nome.
"""

from __future__ import annotations

import importlib.util
import sys
from enum import StrEnum
from types import ModuleType

import pytest

import asta.domain.models as models
from asta.data.repository import InMemoryRepository
from asta.domain.events import Event, EventType, undoable
from asta.domain.models import Listone, Player, Role, Settings
from asta.domain.rules import role_progress, validate_assignment
from asta.service import AuctionService
from asta.ui.board import teams_board_html

MODULO_BIS = "asta_models_ricaricato"


@pytest.fixture(scope="module")
def modulo_bis() -> ModuleType:
    """Una seconda copia di ``asta.domain.models``, come dopo un hot reload."""
    spec = importlib.util.spec_from_file_location(MODULO_BIS, models.__file__)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    # I dataclass risolvono le annotazioni via sys.modules durante l'esecuzione.
    sys.modules[MODULO_BIS] = modulo
    spec.loader.exec_module(modulo)
    yield modulo
    sys.modules.pop(MODULO_BIS, None)


@pytest.fixture
def ruolo_vecchio(modulo_bis: ModuleType) -> Role:
    """``Role.P`` proveniente dalla classe "vecchia"."""
    return modulo_bis.Role.P


def test_la_premessa_del_test_e_valida(ruolo_vecchio):
    """Due membri uguali ma di classi diverse: e' esattamente il caso reale."""
    assert ruolo_vecchio is not Role.P
    assert ruolo_vecchio == Role.P
    assert hash(ruolo_vecchio) == hash(Role.P)


@pytest.fixture
def asta_mista(ruolo_vecchio):
    """Listone con la classe vecchia, impostazioni con quella nuova."""
    listone = Listone(
        players=(
            Player(id=6462, role=ruolo_vecchio, name="Okoye", team="Udinese", quotation=9, fvm=29),
            Player(id=6463, role=ruolo_vecchio, name="Okafor", team="Udinese", quotation=5, fvm=10),
        )
    )
    cfg = Settings(
        teams=("Squadra 1", "Squadra 2"), credits=100, roster_size=1, role_limits=((Role.P, 1),)
    )
    svc = AuctionService(repo=InMemoryRepository(), listone=listone)
    svc.record(EventType.AUCTION_CONFIGURED, cfg.to_payload())
    svc.record(EventType.ROLE_PHASE_STARTED, {"role": Role.P.value})
    return svc


def test_il_calciatore_del_ruolo_in_corso_e_acquistabile(asta_mista):
    """Il bug segnalato: nessuna squadra poteva comprare durante la sua fase."""
    state = asta_mista.state()
    assert validate_assignment(state, state.listone.get(6462), "Squadra 1", 5) is None


def test_il_listone_resta_filtrabile_per_ruolo(asta_mista):
    assert len(asta_mista.state().available(Role.P)) == 2


def test_i_conteggi_di_reparto_restano_giusti(asta_mista):
    asta_mista.record(
        EventType.PLAYER_ASSIGNED, {"player_id": 6462, "team": "Squadra 1", "price": 5}
    )
    state = asta_mista.state()
    team = state.teams["Squadra 1"]
    assert team.count(Role.P) == 1
    assert team.slots_left(Role.P) == 0
    assert role_progress(state, Role.P) == (1, 2)


def test_la_griglia_mostra_il_calciatore_nel_reparto_giusto(asta_mista):
    asta_mista.record(
        EventType.PLAYER_ASSIGNED, {"player_id": 6462, "team": "Squadra 1", "price": 7}
    )
    html = teams_board_html(asta_mista.state())
    assert "Okoye" in html
    # Finito nel reparto portieri, non in uno slot vuoto.
    assert '<div class="tb-slot full"' in html


def test_l_undo_riconosce_il_tipo_di_evento_dopo_il_reload():
    """Anche i tipi di evento vanno confrontati per valore, non per identita'."""

    class EventTypeBis(StrEnum):
        AUCTION_CONFIGURED = "AUCTION_CONFIGURED"

    log = [Event(seq=1, type=EventTypeBis.AUCTION_CONFIGURED)]  # type: ignore[arg-type]
    # La configurazione non e' annullabile, nemmeno arrivando da un'altra classe.
    assert undoable(log) is None

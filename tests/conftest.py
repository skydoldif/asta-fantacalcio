"""Fixture comuni ai test.

I test del dominio girano su un listone sintetico minuscolo (poche lettere,
pochi ruoli) cosi' gli scenari restano leggibili; alcuni test usano anche il
listone vero, per verificare che il file committato sia coerente.
"""

from __future__ import annotations

import pytest
from scripts.build_players import RAW_DIR, XLSX_GLOB

from asta.data.keepers import DEFAULT_GRID_PATH
from asta.data.players import DEFAULT_PLAYERS_PATH, load_listone
from asta.data.repository import InMemoryRepository
from asta.domain.events import EventType
from asta.domain.models import Listone, Mode, Player, Role, Settings
from asta.service import AuctionService
from asta.ui.crests import CRESTS_DIR
from asta.ui.soundbar import AUDIO_DIR


#: I dati veri non stanno nella repo - listone e quotazioni sono di
#: fantacalcio.it, le fasce e le gerarchie vengono dagli articoli, stemmi e
#: audio sono di chi li ha fatti - quindi ognuno si procura i suoi (il README
#: dice come). I test che li usano si saltano finche' non ci sono, e lo dicono.
#:
#: Quelli del motore dell'asta - log degli eventi, regole, undo, export,
#: repository - girano sempre: hanno il loro listone finto qui sotto e non
#: dipendono da nessun dato reale. Sono la maggioranza, ed e' voluto.
def _serve(esiste: bool, cosa: str, come: str):
    return pytest.mark.skipif(not esiste, reason=f"{cosa} non presente: {come}")


#: Ci sono i dati **veri**, non quelli di una demo.
#:
#: Il segnale non e' il JSON del listone ma l'Excel da cui nasce, e la
#: differenza si e' vista appena e' esistito il branch della demo: li'
#: ``data/players_*.json`` c'e', ma dentro ci sono calciatori inventati.
#: Guardando solo il JSON, tutti i test che affermano fatti del listone vero -
#: 533 calciatori, i gol subiti delle squadre di A, le fasce dei tre reparti -
#: partivano e cadevano. L'xlsx ufficiale una demo non ce l'ha mai.
_DATI_VERI = DEFAULT_PLAYERS_PATH.exists() and any(RAW_DIR.glob(XLSX_GLOB))

serve_il_listone = _serve(
    _DATI_VERI,
    "il listone vero",
    "vedi README, sezione 'I dati che devi procurarti'",
)
#: Anche qui serve quella **vera**: c'e' chi controlla che i valori stiano nel
#: range dell'originale e chi cerca una coppia per nome. Una griglia inventata
#: e' simmetrica come si deve, ma non e' quella.
serve_la_griglia = _serve(
    _DATI_VERI and DEFAULT_GRID_PATH.exists(),
    "la griglia dei portieri vera",
    "e' facoltativa, si trascrive a mano dall'articolo",
)
servono_gli_stemmi = _serve(
    any(CRESTS_DIR.glob("*.svg")), "gli stemmi", "sono facoltativi, vedi static/loghi/README.md"
)
serve_l_audio = _serve(
    any(AUDIO_DIR.rglob("*.mp3")) or any(AUDIO_DIR.rglob("*.m4a")),
    "l'audio della Soundbar",
    "e' facoltativo, vedi static/audio/README.md",
)


def make_player(pid: int, role: Role, name: str, team: str = "Testalonga") -> Player:
    """Crea un calciatore di prova."""
    return Player(id=pid, role=role, name=name, team=team, quotation=10, fvm=50)


@pytest.fixture
def listone() -> Listone:
    """Listone sintetico: 4 calciatori per ruolo su lettere controllate.

    Portieri: Abbiati, Amelia, Buffon, Consigli  -> lettere A (2), B, C
    Difensori: Bonucci, Cannavaro, Chiellini, Zambrotta
    Centrocampisti: Pirlo, Perrotta, Rui Costa, Totti
    Attaccanti: Del Piero, Inzaghi, Toni, Vieri
    """
    players = (
        make_player(101, Role.P, "Abbiati"),
        make_player(102, Role.P, "Amelia"),
        make_player(103, Role.P, "Buffon"),
        make_player(104, Role.P, "Consigli"),
        make_player(201, Role.D, "Bonucci"),
        make_player(202, Role.D, "Cannavaro"),
        make_player(203, Role.D, "Chiellini"),
        make_player(204, Role.D, "Zambrotta"),
        make_player(301, Role.C, "Pirlo"),
        make_player(302, Role.C, "Perrotta"),
        make_player(303, Role.C, "Rui Costa"),
        make_player(304, Role.C, "Totti"),
        make_player(401, Role.A, "Del Piero"),
        make_player(402, Role.A, "Inzaghi"),
        make_player(403, Role.A, "Toni"),
        make_player(404, Role.A, "Vieri"),
    )
    return Listone(players=players)


@pytest.fixture
def settings() -> Settings:
    """Asta di prova: 2 squadre, 100 crediti, rosa di 4 (1 per ruolo)."""
    return Settings(
        teams=("Ajax", "Bayern"),
        credits=100,
        roster_size=4,
        role_limits=((Role.P, 1), (Role.D, 1), (Role.C, 1), (Role.A, 1)),
        mode=Mode.LETTER,
    )


@pytest.fixture
def service(listone: Listone, settings: Settings) -> AuctionService:
    """Servizio gia' configurato, con la fase Portieri avviata."""
    svc = AuctionService(repo=InMemoryRepository(), listone=listone)
    svc.record(EventType.AUCTION_CONFIGURED, settings.to_payload())
    svc.record(EventType.ROLE_PHASE_STARTED, {"role": Role.P.value})
    return svc


@pytest.fixture(scope="session")
def real_listone() -> Listone:
    """Il listone vero, quello generato da scripts/build_players.py.

    Non e' nella repo: chi non se l'e' ancora costruito vede saltare i test
    che lo usano, invece di una catasta di FileNotFoundError.

    "Vero" vuol dire con l'xlsx ufficiale accanto, per la stessa ragione di
    :data:`serve_il_listone`: sul branch della demo il JSON c'e' ma i
    calciatori sono inventati, e un test che afferma fatti del listone vero
    non deve girarci sopra.
    """
    if not _DATI_VERI:
        pytest.skip("il listone vero non c'e': python scripts/build_players.py (vedi README)")
    return load_listone()

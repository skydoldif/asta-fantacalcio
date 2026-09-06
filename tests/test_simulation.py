"""Simulazione di un'asta completa sul listone vero.

E' il test che piu' assomiglia alla serata: 8 squadre, 500 crediti, rose
25 (3/8/8/6), modalita lettera random, con salti e correzioni in mezzo.
Verifica che l'asta arrivi in fondo senza incastrarsi e che gli invarianti
(crediti, slot, unicita' dei calciatori) reggano fino all'export.
"""

from __future__ import annotations

import random

import pytest

from asta.data.repository import InMemoryRepository
from asta.domain.events import EventType
from asta.domain.export import rosters_csv
from asta.domain.letters import draw_letter, letter_queue, phase_exhausted
from asta.domain.models import DEFAULT_ROLE_LIMITS, ROLE_ORDER, Mode, Settings
from asta.domain.rules import validate_assignment
from asta.service import AuctionService

SQUADRE = ("Aurora", "Bisonti", "Cobra", "Delfini", "Eagles", "Falchi", "Gufi", "Husky")


def simula(listone, seed: int, salta_ogni: int = 7) -> AuctionService:
    """Gioca un'asta intera in modalita lettera random."""
    rng = random.Random(seed)
    settings = Settings(
        teams=SQUADRE,
        credits=500,
        roster_size=25,
        role_limits=tuple(DEFAULT_ROLE_LIMITS.items()),
        mode=Mode.LETTER,
    )
    svc = AuctionService(repo=InMemoryRepository(), listone=listone)
    svc.record(EventType.AUCTION_CONFIGURED, settings.to_payload())

    chiamate = 0
    for role in ROLE_ORDER:
        svc.record(EventType.ROLE_PHASE_STARTED, {"role": role.value})
        for _ in range(5000):  # guardia contro i cicli infiniti
            state = svc.state()
            queue = letter_queue(state)
            if not queue:
                if phase_exhausted(state):
                    break
                drawn = draw_letter(state, seed=rng.randrange(2**31))
                if drawn is None:
                    break
                letter, letter_seed = drawn
                svc.record(
                    EventType.LETTER_DRAWN,
                    {"role": role.value, "letter": letter, "seed": letter_seed},
                )
                continue

            player = queue[0]
            chiamate += 1
            interessate = [t for t in SQUADRE if state.teams[t].slots_left(role) > 0]
            if not interessate:
                break
            if chiamate % salta_ogni == 0:
                svc.record(EventType.PLAYER_SKIPPED, {"player_id": player.id})
                continue

            squadra = min(interessate, key=lambda t: state.teams[t].size)
            tetto = min(state.teams[squadra].max_bid, 1 + player.quotation)
            prezzo = rng.randint(1, max(1, tetto))
            if validate_assignment(state, player, squadra, prezzo) is None:
                svc.record(
                    EventType.PLAYER_ASSIGNED,
                    {"player_id": player.id, "team": squadra, "price": prezzo},
                )
            else:
                svc.record(EventType.PLAYER_SKIPPED, {"player_id": player.id})
    return svc


@pytest.fixture(scope="module")
def asta(real_listone):
    return simula(real_listone, seed=2026)


def test_tutte_le_rose_sono_complete(asta):
    state = asta.state()
    assert state.incomplete_teams() == ()
    for squadra in SQUADRE:
        assert state.teams[squadra].size == 25


def test_limiti_di_ruolo_rispettati(asta):
    state = asta.state()
    for squadra in SQUADRE:
        team = state.teams[squadra]
        for role in ROLE_ORDER:
            assert team.count(role) == DEFAULT_ROLE_LIMITS[role]


def test_nessuna_squadra_sfora_i_crediti(asta):
    state = asta.state()
    for squadra in SQUADRE:
        assert 0 <= state.teams[squadra].spent <= 500


def test_nessun_calciatore_assegnato_due_volte(asta):
    state = asta.state()
    ids = [a.player_id for a in state.assignments.values()]
    assert len(ids) == len(set(ids)) == 8 * 25


def test_i_calciatori_venduti_spariscono_dal_listone(asta, real_listone):
    state = asta.state()
    assert len(state.available()) == len(real_listone.players) - 200


def test_ogni_calciatore_e_del_ruolo_giusto(asta):
    state = asta.state()
    for assignment in state.assignments.values():
        assert state.listone.get(assignment.player_id).role is assignment.role


def test_export_finale_ha_una_riga_per_calciatore(asta):
    righe = [r for r in rosters_csv(asta.state()).split("\n")[1:] if r]
    assert len(righe) == 200
    assert all(len(r.split(",")) == 3 for r in righe)


def test_undo_totale_riporta_l_asta_al_punto_di_partenza(asta, real_listone):
    """Annullare tutto deve riportare esattamente alla configurazione iniziale."""
    replay = AuctionService(repo=InMemoryRepository(), listone=real_listone)
    replay.restore([e for e in asta.events])
    while replay.can_undo:
        replay.undo()
    state = replay.state()
    assert state.assignments == {}
    assert state.current_role is None
    assert all(t.credits_left == 500 for t in state.teams.values())
    assert len(state.available()) == len(real_listone.players)


def test_simulazioni_con_semi_diversi_arrivano_comunque_in_fondo(real_listone):
    for seed in (1, 7):
        state = simula(real_listone, seed=seed).state()
        assert state.incomplete_teams() == ()

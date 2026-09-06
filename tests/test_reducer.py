"""Test del reducer: dallo stesso log deve uscire sempre lo stesso stato."""

from __future__ import annotations

from asta.domain.events import Event, EventType
from asta.domain.models import Role
from asta.domain.reducer import build_state


def test_asta_appena_configurata(service, settings):
    state = service.state()
    assert state.started
    assert set(state.teams) == set(settings.teams)
    assert state.current_role is Role.P
    assert state.teams["Ajax"].credits_left == 100
    assert len(state.available()) == 16


def test_aggiudicazione_aggiorna_crediti_rosa_e_listone(service):
    service.record(EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 25})
    state = service.state()
    ajax = state.teams["Ajax"]

    assert ajax.spent == 25
    assert ajax.credits_left == 75
    assert ajax.size == 1
    assert ajax.count(Role.P) == 1
    assert ajax.slots_left(Role.P) == 0
    assert state.is_taken(103)
    assert 103 not in {p.id for p in state.available()}
    assert state.teams["Bayern"].credits_left == 100


def test_calciatore_saltato_resta_disponibile(service):
    service.record(EventType.PLAYER_SKIPPED, {"player_id": 103})
    state = service.state()
    assert not state.is_taken(103)
    assert 103 in {p.id for p in state.available(Role.P)}
    assert 103 in state.skipped


def test_cambio_ruolo_azzera_lettere_e_salti(service):
    service.record(EventType.LETTER_DRAWN, {"letter": "A", "seed": 1})
    service.record(EventType.PLAYER_SKIPPED, {"player_id": 101})
    assert service.state().drawn_letters == ("A",)

    service.record(EventType.ROLE_PHASE_STARTED, {"role": Role.D.value})
    state = service.state()
    assert state.current_role is Role.D
    assert state.drawn_letters == ()
    assert state.skipped == frozenset()
    assert state.current_letter is None


def test_correzione_di_una_aggiudicazione_vecchia(service):
    first = service.record(
        EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 25}
    )
    service.record(EventType.ROLE_PHASE_STARTED, {"role": Role.D.value})
    service.record(EventType.PLAYER_ASSIGNED, {"player_id": 201, "team": "Ajax", "price": 10})
    # Ci si accorge solo ora che il portiere era andato al Bayern per 30.
    service.record(
        EventType.ASSIGNMENT_UPDATED,
        {"target_seq": first.seq, "team": "Bayern", "price": 30},
    )

    state = service.state()
    assert state.teams["Ajax"].spent == 10
    assert state.teams["Ajax"].count(Role.P) == 0
    assert state.teams["Bayern"].spent == 30
    assert state.assignment_of(103).team == "Bayern"


def test_rimozione_di_una_aggiudicazione_libera_il_calciatore(service):
    event = service.record(
        EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 25}
    )
    service.record(EventType.ASSIGNMENT_REMOVED, {"target_seq": event.seq})

    state = service.state()
    assert not state.is_taken(103)
    assert state.teams["Ajax"].credits_left == 100
    assert 103 in {p.id for p in state.available(Role.P)}


def test_il_reducer_e_deterministico_e_ignora_l_ordine_di_arrivo(service, listone):
    service.record(EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 25})
    shuffled = list(reversed(service.events))
    assert build_state(listone, shuffled) == service.state()


def test_gli_eventi_disattivati_non_contano(service, listone):
    event = service.record(
        EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 25}
    )
    log = [e.deactivated() if e.seq == event.seq else e for e in service.events]
    state = build_state(listone, log)
    assert not state.is_taken(103)


def test_evento_su_calciatore_inesistente_viene_ignorato(service, listone):
    log = [
        *service.events,
        Event(
            seq=99,
            type=EventType.PLAYER_ASSIGNED,
            payload={"player_id": 9999, "team": "Ajax", "price": 5},
        ),
    ]
    state = build_state(listone, log)
    assert state.teams["Ajax"].size == 0


def test_squadre_incomplete(service):
    assert set(service.state().incomplete_teams()) == {"Ajax", "Bayern"}

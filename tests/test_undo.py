"""Test di undo e redo.

La proprieta' cercata e' forte: dopo ``azione -> undo`` lo stato deve essere
strutturalmente identico a prima dell'azione.
"""

from __future__ import annotations

from asta.domain.events import EventType
from asta.domain.models import Role


def test_undo_ripristina_lo_stato_precedente(service):
    prima = service.state()
    service.record(EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 25})
    assert service.state() != prima

    service.undo()
    assert service.state() == prima


def test_undo_di_una_aggiudicazione_restituisce_crediti_e_calciatore(service):
    service.record(EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 25})
    service.undo()

    state = service.state()
    assert state.teams["Ajax"].credits_left == 100
    assert not state.is_taken(103)


def test_redo_riapplica_l_operazione(service):
    service.record(EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 25})
    dopo = service.state()
    service.undo()
    service.redo()
    assert service.state() == dopo


def test_undo_multipli_in_sequenza(service):
    service.record(EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 25})
    service.record(EventType.ROLE_PHASE_STARTED, {"role": Role.D.value})
    service.record(EventType.PLAYER_ASSIGNED, {"player_id": 201, "team": "Bayern", "price": 15})

    service.undo()
    service.undo()
    state = service.state()
    assert state.current_role is Role.P
    assert state.teams["Ajax"].spent == 25
    assert state.teams["Bayern"].spent == 0

    service.undo()
    assert service.state().teams["Ajax"].spent == 0


def test_la_configurazione_non_e_annullabile(service):
    while service.can_undo:
        service.undo()
    assert service.state().started
    assert service.undo() is None


def test_una_nuova_operazione_invalida_il_redo(service):
    service.record(EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 25})
    service.undo()
    assert service.can_redo

    service.record(EventType.PLAYER_ASSIGNED, {"player_id": 104, "team": "Ajax", "price": 5})
    assert not service.can_redo
    state = service.state()
    assert state.is_taken(104)
    assert not state.is_taken(103)


def test_undo_di_una_correzione(service):
    event = service.record(
        EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 25}
    )
    prima = service.state()
    service.record(
        EventType.ASSIGNMENT_UPDATED, {"target_seq": event.seq, "team": "Bayern", "price": 30}
    )
    service.undo()
    assert service.state() == prima


def test_undo_di_una_rimozione(service):
    event = service.record(
        EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 25}
    )
    prima = service.state()
    service.record(EventType.ASSIGNMENT_REMOVED, {"target_seq": event.seq})
    assert not service.state().is_taken(103)

    service.undo()
    assert service.state() == prima


def test_undo_di_un_salto(service):
    service.record(EventType.LETTER_DRAWN, {"letter": "A", "seed": 1})
    prima = service.state()
    service.record(EventType.PLAYER_SKIPPED, {"player_id": 101})
    service.undo()
    assert service.state() == prima


def test_gli_eventi_annullati_restano_nel_log(service):
    service.record(EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 25})
    n = len(service.events)
    service.undo()
    assert len(service.events) == n
    assert any(not e.active for e in service.events)

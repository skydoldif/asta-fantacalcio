"""Test del servizio: coda locale, retry, ricarica e ripristino."""

from __future__ import annotations

import pytest

from asta.data.repository import InMemoryRepository
from asta.domain.events import EventType
from asta.service import AuctionService


class RepoInstabile(InMemoryRepository):
    """Repository che simula la caduta della rete dati in stanza."""

    def __init__(self):
        super().__init__()
        self.offline = False

    def append(self, event):
        if self.offline:
            raise ConnectionError("rete assente")
        super().append(event)

    def set_active(self, seq, active):
        if self.offline:
            raise ConnectionError("rete assente")
        super().set_active(seq, active)

    def load(self):
        if self.offline:
            raise ConnectionError("rete assente")
        return super().load()


@pytest.fixture
def instabile(listone, settings):
    repo = RepoInstabile()
    svc = AuctionService(repo=repo, listone=listone)
    svc.record(EventType.AUCTION_CONFIGURED, settings.to_payload())
    svc.record(EventType.ROLE_PHASE_STARTED, {"role": "P"})
    return svc, repo


def test_le_scritture_arrivano_al_repository(service):
    service.record(EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 25})
    assert service.synced
    assert len(service.repo.load()) == len(service.events)


def test_offline_l_asta_continua_e_la_coda_cresce(instabile):
    svc, repo = instabile
    repo.offline = True

    svc.record(EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 25})

    assert not svc.synced
    assert len(svc.pending) == 1
    assert svc.error is not None
    # Lo stato locale e' comunque aggiornato: l'asta non si ferma.
    assert svc.state().teams["Ajax"].spent == 25


def test_al_ritorno_della_rete_la_coda_si_svuota_in_ordine(instabile):
    svc, repo = instabile
    repo.offline = True
    svc.record(EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 25})
    svc.record(EventType.PLAYER_SKIPPED, {"player_id": 104})
    svc.undo()
    assert len(svc.pending) == 3

    repo.offline = False
    assert svc.flush()
    assert svc.synced and svc.error is None
    assert [e.seq for e in repo.load()] == [e.seq for e in svc.events]
    assert repo.load()[-1].active is False


def test_reload_non_sovrascrive_operazioni_in_coda(instabile):
    svc, repo = instabile
    repo.offline = True
    svc.record(EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 25})
    repo.offline = False

    assert svc.reload() is False
    assert svc.state().teams["Ajax"].spent == 25


def test_reload_riallinea_con_il_database(service, listone):
    service.record(EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 25})
    altro = AuctionService(repo=service.repo, listone=listone)
    altro.bootstrap()
    assert altro.state() == service.state()


def test_errore_di_lettura_non_solleva(instabile):
    svc, repo = instabile
    repo.offline = True
    assert svc.reload() is False
    assert "non raggiungibile" in (svc.error or "")


def test_reset_azzera_tutto(service):
    service.record(EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 25})
    service.reset()
    assert service.events == []
    assert service.repo.load() == []
    assert not service.state().started


def test_restore_da_backup(service, listone):
    service.record(EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 25})
    snapshot = list(service.events)
    atteso = service.state()

    nuovo = AuctionService(repo=InMemoryRepository(), listone=listone)
    nuovo.restore(snapshot)
    assert nuovo.state() == atteso
    assert len(nuovo.repo.load()) == len(snapshot)


def test_i_seq_sono_progressivi_e_senza_buchi(service):
    for pid in (101, 102):
        service.record(EventType.PLAYER_SKIPPED, {"player_id": pid})
    assert [e.seq for e in service.events] == list(range(1, len(service.events) + 1))

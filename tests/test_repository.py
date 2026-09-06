"""Contratto dei repository, verificato su tutte e due le implementazioni.

I test girano sempre su :class:`InMemoryRepository` e, quando l'ambiente
espone ``ASTA_TEST_DATABASE_URL``, anche su :class:`PostgresRepository`. Senza
quella variabile il caso Postgres si salta: ``pytest`` in locale resta offline
e non chiede niente a nessuno.

Serve perche' il codice SQL e' l'unico che gira davvero la sera dell'asta, e
finora era anche l'unico senza un test: veniva provato a mano contro il
database vero, cioe' nel momento peggiore per scoprire un problema. In CI il
caso Postgres gira contro un container di servizio.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest

from asta.data.repository import AuctionRepository, InMemoryRepository, PostgresRepository
from asta.domain.events import Event, EventType

#: URL del database di prova. Vuoto: il caso Postgres si salta.
URL_PROVA = os.environ.get("ASTA_TEST_DATABASE_URL", "")


def evento(seq: int, active: bool = True) -> Event:
    return Event(seq=seq, type=EventType.PLAYER_SKIPPED, payload={"player_id": seq}, active=active)


@pytest.fixture
def memoria() -> InMemoryRepository:
    return InMemoryRepository()


@pytest.fixture
def postgres() -> Iterator[PostgresRepository]:
    """Repository Postgres su un'asta usa e getta, cancellata a fine test."""
    if not URL_PROVA:
        pytest.skip("ASTA_TEST_DATABASE_URL non impostata: niente prova su Postgres")
    from sqlalchemy import create_engine

    engine = create_engine(URL_PROVA, connect_args={"prepare_threshold": None})
    repo = PostgresRepository(engine, auction_id=f"test-{uuid.uuid4().hex[:8]}")
    repo.ensure_schema()
    yield repo
    repo.reset()
    engine.dispose()


@pytest.fixture(params=["memoria", "postgres"])
def repo(request: pytest.FixtureRequest) -> AuctionRepository:
    """Le due implementazioni, una per volta."""
    return request.getfixturevalue(request.param)  # type: ignore[no-any-return]


def test_append_e_load_ordinati(repo):
    repo.append(evento(2))
    repo.append(evento(1))
    assert [e.seq for e in repo.load()] == [1, 2]


def test_append_duplicato_e_innocuo(repo):
    """Un retry della coda di sincronizzazione non deve duplicare nulla."""
    repo.append(evento(1))
    repo.append(evento(1))
    assert len(repo.load()) == 1


def test_set_active(repo):
    repo.append(evento(1))
    repo.set_active(1, False)
    assert repo.load()[0].active is False
    repo.set_active(1, True)
    assert repo.load()[0].active is True


def test_version_cambia_con_append_e_con_undo(repo):
    assert repo.version() == (0, 0)
    repo.append(evento(1))
    v1 = repo.version()
    repo.append(evento(2))
    v2 = repo.version()
    assert v1 != v2
    repo.set_active(2, False)
    assert repo.version() != v2


def test_reset_svuota(repo):
    repo.append(evento(1))
    repo.reset()
    assert repo.load() == []


def test_replace_all(repo):
    repo.append(evento(1))
    repo.replace_all([evento(7), evento(8)])
    assert [e.seq for e in repo.load()] == [7, 8]


def test_replace_all_su_un_log_lungo(repo):
    """Il ripristino di meta' asta: deve arrivare intero, e in un colpo solo."""
    log = [evento(n) for n in range(1, 401)]
    repo.replace_all(log)
    letti = repo.load()
    assert [e.seq for e in letti] == [e.seq for e in log]


def test_il_payload_sopravvive_ad_accenti_e_apostrofi(repo):
    """I nomi delle squadre li scrivono gli amici, non un validatore."""
    payload = {"team": "L'Aquila d'Abruzzo", "nota": 'virgolette " e \\ barre', "price": 42}
    repo.append(Event(seq=1, type=EventType.PLAYER_ASSIGNED, payload=payload))
    assert repo.load()[0].payload == payload


def test_le_aste_non_si_mescolano(postgres):
    """Due ``auction_id`` sullo stesso database restano separate."""
    altra = PostgresRepository(postgres._engine, auction_id=f"test-{uuid.uuid4().hex[:8]}")
    postgres.append(evento(1))
    try:
        assert altra.load() == []
        assert altra.version() == (0, 0)
    finally:
        altra.reset()


def test_ensure_schema_e_idempotente(postgres):
    postgres.append(evento(1))
    postgres.ensure_schema()
    assert len(postgres.load()) == 1


def test_roundtrip_serializzazione():
    original = Event(
        seq=3, type=EventType.PLAYER_ASSIGNED, payload={"player_id": 1, "team": "Ajax", "price": 5}
    )
    assert Event.from_dict(original.to_dict()) == original

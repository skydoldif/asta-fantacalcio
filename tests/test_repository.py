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
    # ``reset`` cancella l'asta ma non il listone, ed e' voluto: azzerare
    # l'asta non deve costringere a ricaricarlo. Qui pero' si butta via
    # tutto, altrimenti ogni test lascerebbe la sua riga nel database.
    _cancella_listone(repo)
    engine.dispose()


def _cancella_listone(repo: PostgresRepository) -> None:
    from sqlalchemy import text

    with repo._engine.begin() as conn:  # type: ignore[attr-defined]
        for tabella in ("auction_listone", "auction_listone_file"):
            conn.execute(
                text(f"DELETE FROM {tabella} WHERE auction_id = :aid"),
                {"aid": repo._auction_id},
            )


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


# ------------------------------------------------------------------ listone


def test_senza_listone_caricato_si_ottiene_none(repo):
    """Chi non ha ancora caricato niente ricade sul file committato."""
    assert repo.load_listone() is None


def test_il_listone_fa_il_giro_intero(repo):
    payload = {
        "source": "Quotazioni_Fantacalcio_Stagione_2026_27.xlsx",
        "count": 2,
        # Accenti e apostrofi: il JSONB ci passa attraverso, ma e' il genere
        # di cosa che si scopre in produzione se non la si prova.
        "players": [
            {"id": 1, "role": "P", "name": "N'Dicka", "team": "Roma"},
            {"id": 2, "role": "A", "name": "Gonzalez N.", "team": "Atalanta"},
        ],
        "tiers": {"A": ["F1", "F2"]},
    }
    repo.save_listone(payload)
    assert repo.load_listone() == payload


def test_il_listone_nuovo_sostituisce_il_vecchio(repo):
    """Ce n'e' uno solo per asta: caricarne un altro non ne aggiunge una copia."""
    repo.save_listone({"count": 1, "players": [{"id": 1}]})
    repo.save_listone({"count": 2, "players": [{"id": 1}, {"id": 2}]})
    caricato = repo.load_listone()
    assert caricato is not None
    assert caricato["count"] == 2


def test_il_listone_non_e_un_evento_dell_asta(repo):
    """Caricarlo non tocca il log, e azzerare l'asta non lo porta via."""
    repo.save_listone({"count": 1, "players": [{"id": 1}]})
    repo.append(evento(1))
    assert len(repo.load()) == 1

    repo.reset()
    assert repo.load() == []
    assert repo.load_listone() is not None, "azzerando l'asta il listone resta"


# ------------------------------------------------- i file sorgente del listone


def test_senza_file_caricati_l_archivio_e_vuoto(repo):
    assert repo.load_listone_files() == {}


def test_un_file_fa_il_giro_intero_byte_per_byte(repo):
    """Sono byte di un Excel: se il giro li altera, il listone non si rigenera."""
    contenuto = bytes(range(256)) * 4
    repo.save_listone_file("xlsx_path", "Quotazioni_2026_27.xlsx", contenuto)
    assert repo.load_listone_files() == {"xlsx_path": ("Quotazioni_2026_27.xlsx", contenuto)}


def test_le_caselle_si_riempiono_una_per_volta(repo):
    """Il caso vero: le quotazioni oggi, le statistiche domani."""
    repo.save_listone_file("xlsx_path", "Quotazioni.xlsx", b"quotazioni")
    repo.save_listone_file("stats_path", "Statistiche.xlsx", b"statistiche")

    caselle = repo.load_listone_files()
    assert set(caselle) == {"xlsx_path", "stats_path"}
    assert caselle["xlsx_path"] == ("Quotazioni.xlsx", b"quotazioni")


def test_ricaricare_la_stessa_casella_sostituisce(repo):
    repo.save_listone_file("stats_path", "vecchie.xlsx", b"vecchio")
    repo.save_listone_file("stats_path", "nuove.xlsx", b"nuovo")

    caselle = repo.load_listone_files()
    assert len(caselle) == 1
    assert caselle["stats_path"] == ("nuove.xlsx", b"nuovo")


def test_una_casella_si_puo_svuotare(repo):
    repo.save_listone_file("stats_path", "Statistiche.xlsx", b"x")
    repo.delete_listone_file("stats_path")
    assert repo.load_listone_files() == {}
    # Svuotarne una gia' vuota non deve rompere niente.
    repo.delete_listone_file("stats_path")


def test_azzerare_l_asta_non_porta_via_i_file(repo):
    """Ricominciare l'asta non deve costringere a ricaricare il listone."""
    repo.save_listone_file("xlsx_path", "Quotazioni.xlsx", b"x")
    repo.append(evento(1))
    repo.reset()

    assert repo.load() == []
    assert set(repo.load_listone_files()) == {"xlsx_path"}


def test_i_file_sono_di_una_sola_asta(postgres):
    altra = PostgresRepository(postgres._engine, auction_id=f"test-{uuid.uuid4().hex[:8]}")
    postgres.save_listone_file("xlsx_path", "Quotazioni.xlsx", b"x")
    try:
        assert altra.load_listone_files() == {}
    finally:
        altra.reset()
        _cancella_listone(altra)


def test_il_listone_e_di_una_sola_asta(postgres):
    altra = PostgresRepository(postgres._engine, auction_id=f"test-{uuid.uuid4().hex[:8]}")
    postgres.save_listone({"count": 1, "players": [{"id": 1}]})
    try:
        assert altra.load_listone() is None
    finally:
        altra.reset()
        _cancella_listone(altra)


def test_ensure_schema_e_idempotente(postgres):
    postgres.append(evento(1))
    postgres.ensure_schema()
    assert len(postgres.load()) == 1


def test_roundtrip_serializzazione():
    original = Event(
        seq=3, type=EventType.PLAYER_ASSIGNED, payload={"player_id": 1, "team": "Ajax", "price": 5}
    )
    assert Event.from_dict(original.to_dict()) == original

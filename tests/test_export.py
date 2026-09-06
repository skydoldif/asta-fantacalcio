"""Test dell'export CSV per fantacalcio.it e del backup JSON."""

from __future__ import annotations

from pathlib import Path

import pytest

from asta.domain.events import EventType
from asta.domain.export import (
    CSV_HEADER,
    backup_json,
    export_filename,
    restore_events,
    rosters_csv,
)
from asta.domain.models import Role
from asta.domain.reducer import build_state

ESEMPIO = Path("data/raw/esempio_rosters.csv")


@pytest.fixture
def asta_completa(service):
    """Due squadre con un calciatore per ruolo."""
    coppie = [(Role.P, 103, 104), (Role.D, 201, 202), (Role.C, 301, 302), (Role.A, 401, 402)]
    for role, ajax_id, bayern_id in coppie:
        service.record(EventType.ROLE_PHASE_STARTED, {"role": role.value})
        service.record(
            EventType.PLAYER_ASSIGNED, {"player_id": ajax_id, "team": "Ajax", "price": 10}
        )
        service.record(
            EventType.PLAYER_ASSIGNED, {"player_id": bayern_id, "team": "Bayern", "price": 20}
        )
    return service


def test_intestazione_e_formato_righe(asta_completa):
    csv = rosters_csv(asta_completa.state())
    lines = csv.split("\n")

    assert lines[0] == CSV_HEADER == "$,$,$"
    assert csv.endswith("\n")
    righe = [line for line in lines[1:] if line]
    assert len(righe) == 8
    for riga in righe:
        squadra, player_id, prezzo = riga.split(",")
        assert squadra in {"Ajax", "Bayern"}
        assert player_id.isdigit()
        assert prezzo.isdigit()


def test_stesso_formato_del_file_di_esempio(asta_completa):
    atteso = ESEMPIO.read_bytes().decode("utf-8")
    prodotto = rosters_csv(asta_completa.state())

    # Stessa intestazione, stesso numero di campi, stessi terminatori LF.
    assert prodotto.split("\n")[0] == atteso.split("\n")[0]
    assert "\r" not in prodotto
    assert not prodotto.startswith("﻿")
    campi_attesi = {len(r.split(",")) for r in atteso.strip().split("\n")}
    campi_prodotti = {len(r.split(",")) for r in prodotto.strip().split("\n")}
    assert campi_prodotti == campi_attesi == {3}


def test_esempio_ricostruito_byte_per_byte(listone, settings):
    """Rigenera esattamente il file di esempio partendo da un log eventi."""
    from asta.data.repository import InMemoryRepository
    from asta.domain.models import Listone, Player, Settings
    from asta.service import AuctionService

    ids = [6884, 5585, 4964, 2816]
    finto_listone = Listone(
        players=tuple(
            Player(id=i, role=Role.A, name=f"G{n}", team="X", quotation=1, fvm=1)
            for n, i in enumerate(ids)
        )
    )
    cfg = Settings(teams=("Dildersbrough",), credits=100, roster_size=4, role_limits=((Role.A, 4),))
    svc = AuctionService(repo=InMemoryRepository(), listone=finto_listone)
    svc.record(EventType.AUCTION_CONFIGURED, cfg.to_payload())
    for i in ids:
        svc.record(EventType.PLAYER_ASSIGNED, {"player_id": i, "team": "Dildersbrough", "price": 0})

    prodotto = rosters_csv(svc.state())
    # L'ordine interno e' per nome (G0..G3), cioe' quello del file d'esempio.
    assert prodotto.encode("utf-8") == ESEMPIO.read_bytes()


def test_squadre_nell_ordine_di_configurazione(asta_completa):
    righe = [r for r in rosters_csv(asta_completa.state()).split("\n")[1:] if r]
    squadre = [r.split(",")[0] for r in righe]
    assert squadre == ["Ajax"] * 4 + ["Bayern"] * 4


def test_calciatori_ordinati_per_ruolo(asta_completa):
    righe = [r for r in rosters_csv(asta_completa.state()).split("\n")[1:] if r]
    ajax = [int(r.split(",")[1]) for r in righe if r.startswith("Ajax")]
    assert ajax == [103, 201, 301, 401]


def test_export_a_meta_asta(service):
    service.record(EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 25})
    righe = [r for r in rosters_csv(service.state()).split("\n")[1:] if r]
    assert righe == ["Ajax,103,25"]


def test_export_senza_configurazione(listone):
    assert rosters_csv(build_state(listone, [])) == "$,$,$\n"


def test_nome_file_con_timestamp():
    nome = export_filename()
    assert nome.startswith("rose_asta_") and nome.endswith(".csv")


def test_backup_e_ripristino_conservano_il_log(asta_completa):
    raw = backup_json(asta_completa.events)
    ripristinati = restore_events(raw)
    assert [e.to_dict() for e in ripristinati] == [
        e.to_dict() for e in sorted(asta_completa.events, key=lambda e: e.seq)
    ]


def test_backup_conserva_anche_gli_eventi_annullati(service):
    service.record(EventType.PLAYER_ASSIGNED, {"player_id": 103, "team": "Ajax", "price": 25})
    service.undo()
    ripristinati = restore_events(backup_json(service.events))
    assert any(not e.active for e in ripristinati)


def test_backup_non_valido():
    with pytest.raises(ValueError):
        restore_events("{}")

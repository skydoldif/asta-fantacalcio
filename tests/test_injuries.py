"""Test degli infortuni: lettura della tabella, aggancio, ambulanza a schermo.

L'articolo elenca indisponibili di tre tipi - infortunati, squalificati e
diffidati - ma all'asta pesa solo il primo: una squalifica dura una giornata,
un crociato mezza stagione.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from scripts.build_players import (
    RAW_DIR,
    find_injuries,
    merge_injuries,
    parse_injuries,
)

from asta.domain.models import Injury, Player, Role
from asta.ui.components import (
    COLONNA_INFORTUNIO,
    INJURY_COLOR,
    _colore_infortunio,
    _formatta_infortunio,
    badge_items,
    listone_display,
    listone_table,
)

TABELLA = find_injuries(RAW_DIR)


def _scrivi(tmp_path: Path, testo: str) -> Path:
    percorso = tmp_path / "infortunati_prova.md"
    percorso.write_text(testo, encoding="utf-8")
    return percorso


# ------------------------------------------------------------------ lettura


def test_nome_giornata_e_descrizione(tmp_path):
    md = _scrivi(
        tmp_path,
        "**BOLOGNA**\n\n*Infortunati:*\n\n"
        "**Orsolini** - Risentimento ai flessori, in dubbio per la 4a.\n\n"
        "*Squalificati:* -\n",
    )
    assert parse_injuries(md) == [
        ("BOLOGNA", "Orsolini", 4, "Risentimento ai flessori, in dubbio per la 4a")
    ]


def test_anche_il_rientro_previsto_e_una_giornata(tmp_path):
    md = _scrivi(
        tmp_path,
        "**NAPOLI**\n\n*Infortunati:*\n\n**Mctominay** - Aritmia, rientro previsto per la 6a.\n",
    )
    assert parse_injuries(md)[0][2] == 6


def test_senza_giornata_resta_solo_l_infortunio(tmp_path):
    md = _scrivi(tmp_path, "**INTER**\n\n*Infortunati:*\n\n**Spence** - Ritardo di condizione.\n")
    *_, giornata, nota = parse_injuries(md)[0]
    assert (giornata, nota) == (None, "Ritardo di condizione")


def test_squalificati_e_diffidati_non_contano(tmp_path):
    """Sono altre due liste nella stessa sezione, e non c'entrano con l'asta."""
    md = _scrivi(
        tmp_path,
        "**ROMA**\n\n*Infortunati:*\n\n**N'dicka** - Adduttore, in dubbio per la 3a.\n\n"
        "*Squalificati:*\n\n**Dybala** - Espulso.\n\n*Diffidati:*\n\n**Cristante** - Diffidato.\n",
    )
    assert [voce[1] for voce in parse_injuries(md)] == ["N'dicka"]


def test_una_squadra_senza_infortunati(tmp_path):
    md = _scrivi(tmp_path, "**MILAN**\n\n*Infortunati:* -\n\n*Squalificati:* -\n")
    assert parse_injuries(md) == []


# ------------------------------------------------------------------ aggancio


def _rosa(*nomi: str, team: str = "Bologna") -> list[dict]:
    return [{"id": i, "name": n, "team": team} for i, n in enumerate(nomi, start=1)]


def test_l_infortunio_finisce_sul_calciatore_giusto():
    players = _rosa("Orsolini", "Ferguson")
    fuori, sospetti = merge_injuries(players, [("BOLOGNA", "Orsolini", 4, "Flessori")])
    assert (fuori, sospetti) == (1, [])
    assert players[0]["injury"] == {"matchday": 4, "note": "Flessori"}
    assert players[1].get("injury") is None


def test_senza_giornata_il_campo_non_si_scrive():
    players = _rosa("Orsolini")
    merge_injuries(players, [("BOLOGNA", "Orsolini", None, "Da valutare")])
    assert players[0]["injury"] == {"note": "Da valutare"}


def test_un_nome_sconosciuto_viene_segnalato():
    players = _rosa("Orsolini")
    fuori, sospetti = merge_injuries(players, [("BOLOGNA", "Fantasma", 3, "Boh")])
    assert (fuori, sospetti) == (0, ["BOLOGNA: 'Fantasma' -> nessuno"])


def test_il_guarito_non_resta_infortunato():
    """La tabella e' aggiornata in tempo reale: chi rientra sparisce e basta."""
    players = _rosa("Orsolini")
    merge_injuries(players, [("BOLOGNA", "Orsolini", 4, "Flessori")])
    merge_injuries(players, [])
    assert players[0].get("injury") is None


# ------------------------------------------------------------- tabella vera


@pytest.mark.skipif(TABELLA is None, reason="tabella infortunati non presente")
def test_la_tabella_vera_si_aggancia_tutta(real_listone):
    players = [{"id": p.id, "name": p.name, "team": p.team} for p in real_listone.players]
    fuori, sospetti = merge_injuries(players, parse_injuries(TABELLA))
    assert sospetti == []
    assert fuori > 30


@pytest.mark.skipif(TABELLA is None, reason="tabella infortunati non presente")
def test_l_infortunio_arriva_fino_al_listone(real_listone):
    yildiz = next(p for p in real_listone.players if p.name == "Yildiz")
    assert yildiz.injury is not None
    assert yildiz.injury.matchday == 13
    assert "metatarso" in yildiz.injury.note
    assert next(p for p in real_listone.players if p.name == "Kean").injury is None


# ------------------------------------------------------------------ dominio


def test_l_infortunio_sopravvive_al_json():
    infortunio = Injury(matchday=6, note="Polpaccio")
    assert infortunio.to_payload() == {"matchday": 6, "note": "Polpaccio"}
    assert Injury.from_payload(infortunio.to_payload()) == infortunio


def test_l_etichetta_e_la_giornata_di_rientro():
    assert Injury(matchday=3).label == "3a"
    assert Injury().label == "—"


# ------------------------------------------------------------------ a schermo


def _player(**kwargs) -> Player:
    base = Player(id=1, role=Role.A, name="Yildiz", team="Juventus", quotation=20, fvm=100)
    return replace(base, **kwargs)


def test_l_ambulanza_viene_prima_di_tutto():
    infortunato = _player(injury=Injury(matchday=13, note="Metatarso"))
    lettera, giornata, titolo, colore = badge_items(infortunato)[0]
    assert (lettera, giornata, titolo, colore) == ("🚑", "13a", "Metatarso", INJURY_COLOR)
    assert badge_items(_player()) == []


def test_nel_listone_la_colonna_ordina_per_rientro():
    presto = _player(injury=Injury(matchday=3))
    tardi = replace(presto, id=2, name="Thuram K.", injury=Injury(matchday=17))
    ignota = replace(presto, id=3, name="Spence", injury=Injury(note="Ritardo di condizione"))
    sano = replace(presto, id=4, name="Kean", injury=None)

    tabella = listone_table((presto, tardi, ignota, sano))
    assert list(tabella[COLONNA_INFORTUNIO][:3]) == [3, 17, 0]
    assert tabella[COLONNA_INFORTUNIO].isna()[3], "chi sta bene non ha nessun valore"

    righe = listone_display(tabella).to_string().splitlines()[1:]
    assert [riga.split("Juventus")[1].split()[0] for riga in righe[:3]] == ["3a", "17a", "—"]
    assert righe[3].split()[-1] == "Juventus", "sul sano non c'e' niente dopo la squadra"


def test_la_cella_dell_infortunato_e_rossa():
    assert _formatta_infortunio(3) == "3a"
    assert _formatta_infortunio(-1) == ""
    assert _colore_infortunio(3) == f"color:{INJURY_COLOR};font-weight:700"
    assert _colore_infortunio(-1) == ""

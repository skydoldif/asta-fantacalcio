"""Test delle fasce d'asta: lettura degli articoli, aggancio, colonna e filtro.

Le fasce arrivano da tre articoli, uno per reparto. Non c'e' un Id e nemmeno
la squadra: l'aggancio e' per nome dentro il reparto, che basta a togliere
ogni ambiguita' (i due Esposito attaccanti hanno gia' nomi diversi nel
listone, e ``Martinez L.`` non rischia di finire sul portiere dell'Inter).
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from scripts.build_players import (
    RAW_DIR,
    find_tiers,
    merge_tiers,
    parse_tiers,
)

from asta.data.players import load_listone, load_tiers
from asta.domain.models import Player, Role, Tier
from asta.ui.components import (
    COLONNA_FASCIA,
    TIER_COLOR,
    _colore_fascia,
    _formatta_fascia,
    badge_items,
    fasce_disponibili,
    listone_display,
    listone_table,
    tier_code,
    tier_labels,
)
from conftest import serve_il_listone

ARTICOLI = find_tiers(RAW_DIR)


# ------------------------------------------------------------------ lettura


def test_una_fascia_e_una_riga_di_nomi(tmp_path):
    md = tmp_path / "attaccanti_prova.md"
    md.write_text(
        "**F1** - Malen, Martinez L., Ramos G.\n\nDonyell Malen ha stravolto...\n\n"
        "**JF1** - Castro S., Soulè\n\nSantiago Castro cambia status...\n",
        encoding="utf-8",
    )
    assert parse_tiers(md) == [
        ("F1", ["Malen", "Martinez L.", "Ramos G."]),
        ("JF1", ["Castro S.", "Soulè"]),
    ]


def test_l_ordine_e_quello_dell_articolo_non_quello_alfabetico(tmp_path):
    """Le jolly stanno infilate fra le altre: JF1 puo' valere piu' di F5."""
    md = tmp_path / "difensori_prova.md"
    md.write_text("**F3** - Bisseck\n\n**JF1** - Cambiaso\n\n**F4** - Hermoso\n", encoding="utf-8")
    assert [fascia for fascia, _ in parse_tiers(md)] == ["F3", "JF1", "F4"]


# ------------------------------------------------------------------ aggancio


def _rosa(*voci: tuple[str, str]) -> list[dict]:
    return [
        {"id": i, "name": n, "team": "Inter", "role": r} for i, (n, r) in enumerate(voci, start=1)
    ]


def test_la_fascia_arriva_col_suo_rango():
    players = _rosa(("Malen", "A"), ("Kean", "A"))
    con_fascia, sospetti = merge_tiers(players, {"A": [("F1", ["Malen"]), ("F2", ["Kean"])]})
    assert (con_fascia, sospetti) == (2, [])
    assert (players[0]["tier"], players[0]["tier_rank"]) == ("F1", 1)
    assert (players[1]["tier"], players[1]["tier_rank"]) == ("F2", 2)


def test_il_reparto_tiene_separati_gli_omonimi():
    """``Martinez L.`` e' l'attaccante, il portiere dell'Inter non si tocca."""
    players = _rosa(("Martinez Jo.", "P"), ("Martinez L.", "A"))
    merge_tiers(players, {"A": [("F1", ["Martinez L."])]})
    assert players[0].get("tier") is None
    assert players[1]["tier"] == "F1"


def test_un_nome_fuori_dal_listone_viene_segnalato():
    players = _rosa(("Malen", "A"))
    con_fascia, sospetti = merge_tiers(players, {"A": [("F1", ["Fantasma"])]})
    assert (con_fascia, sospetti) == (0, ["A F1: 'Fantasma' -> nessuno"])


def test_rigenerare_non_lascia_fasce_vecchie():
    players = _rosa(("Malen", "A"))
    merge_tiers(players, {"A": [("F1", ["Malen"])]})
    merge_tiers(players, {})
    assert players[0].get("tier") is None
    assert players[0].get("tier_rank") is None


# ----------------------------------------------------------- articoli veri


@pytest.mark.skipif(not ARTICOLI, reason="articoli delle fasce non presenti")
def test_gli_articoli_veri_si_agganciano_tutti(real_listone):
    players = [
        {"id": p.id, "name": p.name, "team": p.team, "role": p.role.value}
        for p in real_listone.players
    ]
    per_ruolo = {ruolo: parse_tiers(percorso) for ruolo, percorso in ARTICOLI.items()}
    con_fascia, sospetti = merge_tiers(players, per_ruolo)
    assert sospetti == []
    assert con_fascia > 300


@serve_il_listone
def test_le_fasce_committate_coprono_i_tre_reparti():
    listone = load_listone()
    per_ruolo: dict[Role, set[str]] = {}
    for player in listone.players:
        if player.tier is not None:
            per_ruolo.setdefault(player.role, set()).add(player.tier.label)
    assert set(per_ruolo) == {Role.D, Role.C, Role.A}, "i portieri non hanno fasce"
    assert per_ruolo[Role.C] >= {"F1", "F8", "JF4", "FS"}

    graduatorie = load_tiers()
    assert graduatorie[Role.D][:3] == ("F1", "F2", "F3")
    # Nei difensori la prima jolly viene dopo la terza fascia, non in fondo.
    assert graduatorie[Role.D].index("JF1") == 3


# ------------------------------------------------------------------ a schermo


def _player(**kwargs) -> Player:
    base = Player(id=1, role=Role.A, name="Malen", team="Roma", quotation=40, fvm=300)
    return replace(base, **kwargs)


def test_la_fascia_sta_nella_riga_dei_simboli():
    voci = badge_items(_player(tier=Tier(label="F1", rank=1)))
    assert voci[0] == ("F1", "Fascia", "Fascia d'asta F1", TIER_COLOR)
    assert badge_items(_player()) == []


@serve_il_listone
def test_la_colonna_si_ordina_per_graduatoria_non_per_sigla():
    """JF1 vale piu' di F5 fra gli attaccanti: la sigla da sola mentirebbe."""
    quinta = _player(tier=Tier(label="F5", rank=6))
    jolly = replace(quinta, id=2, name="Castro S.", tier=Tier(label="JF1", rank=5))
    tabella = listone_table((quinta, jolly))
    assert tabella[COLONNA_FASCIA][1] < tabella[COLONNA_FASCIA][0]

    righe = listone_display(tabella).to_string().splitlines()[1:]
    assert [riga.split("Roma")[1].split()[0] for riga in righe] == ["F5", "JF1"]


def test_la_cella_di_chi_non_ha_fascia_resta_vuota():
    sigle = tier_labels()
    assert _formatta_fascia(-1, sigle=sigle) == ""
    assert _formatta_fascia(None, sigle=sigle) == ""
    assert _colore_fascia(-1) == ""
    assert _colore_fascia(11) == f"color:{TIER_COLOR};font-weight:700"


@serve_il_listone
def test_il_codice_si_ritraduce_nella_sigla():
    sigle = tier_labels()
    codice = tier_code(Role.C, Tier(label="F1", rank=1))
    assert sigle[codice] == "F1"
    # Stesso rango, reparti diversi, sigle diverse: il codice li distingue.
    assert tier_code(Role.A, Tier(label="JF1", rank=5)) != tier_code(
        Role.D, Tier(label="F4", rank=5)
    )


# ------------------------------------------------------------------- filtro


@serve_il_listone
def test_il_menu_delle_fasce_segue_il_reparto():
    difensori = fasce_disponibili(Role.D)
    centrocampisti = fasce_disponibili(Role.C)
    assert difensori[:3] == ["F1", "F2", "F3"]
    assert "F8" in centrocampisti and "F8" not in difensori
    assert fasce_disponibili(Role.P) == [], "i portieri non hanno fasce"


@serve_il_listone
def test_senza_reparto_il_menu_le_mette_tutte_in_graduatoria():
    tutte = fasce_disponibili(None)
    assert tutte[0] == "F1"
    assert set(tutte) >= {"F1", "F8", "FS", "JF1", "JF4"}
    assert tutte.index("F1") < tutte.index("F5") < tutte.index("F8")

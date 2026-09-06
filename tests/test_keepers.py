"""Test dei portieri: gerarchie, griglia delle coppie e pagina.

La griglia e' l'unico dato dell'app trascritto a mano da un'immagine, quindi
qui c'e' anche il suo controllo: e' simmetrica per costruzione, e un numero
letto male romperebbe la simmetria.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.build_players import (
    RAW_DIR,
    find_keepers,
    find_stats,
    merge_keepers,
    parse_keepers,
    parse_stats,
    team_goals_conceded,
)

from asta.data.keepers import load_keeper_grid, load_keepers
from asta.domain.events import EventType
from asta.domain.models import KeeperGrid, KeeperRank, LineupSpot, PlayerStats, Role
from asta.ui.keepers import (
    MIN_PARTITE_PARARIGORI,
    grid_html,
    keeper_card_html,
    keepers_html,
    penalty_savers,
    penalty_savers_html,
    sorted_ranks,
)
from conftest import serve_il_listone, serve_la_griglia

ARTICOLO = find_keepers(RAW_DIR)


def _scrivi(tmp_path: Path, testo: str) -> Path:
    percorso = tmp_path / "portieri_prova.md"
    percorso.write_text(testo, encoding="utf-8")
    return percorso


# ------------------------------------------------------------------ lettura


def test_una_gerarchia_chiara_ha_un_titolare_e_basta(tmp_path):
    md = _scrivi(
        tmp_path,
        "🧤 **ROMA**\n\n*Primo*: **Svilar**\n\n*Secondo*: Gollini\n\n*Terzo*: De Marzi\n\n"
        "*Note*: Nessun dubbio sul titolarissimo.\n",
    )
    (squadra,) = parse_keepers(md)
    assert squadra["starters"] == ["Svilar"]
    assert squadra["risky"] is False
    assert squadra["backup"] is None
    assert squadra["note"] == "", "la nota si tiene solo dove il posto e' in discussione"


def test_due_nomi_nel_primo_sono_un_ballottaggio(tmp_path):
    md = _scrivi(
        tmp_path,
        "🧤 **COMO**\n\n*Primo*: **Butez/Sanchez**\n\n*Secondo*: Sanchez/Butez\n\n"
        "*Note*: La gerarchia e' apertissima.\n",
    )
    (squadra,) = parse_keepers(md)
    assert squadra["starters"] == ["Butez", "Sanchez"]
    assert squadra["risky"] is True
    assert squadra["backup"] is None, "il vice e' gia' fra i titolari"


def test_la_nota_che_dice_di_prenderli_entrambi_accende_il_vice(tmp_path):
    md = _scrivi(
        tmp_path,
        "🧤 **INTER**\n\n*Primo*: **Martinez**\n\n*Secondo*: Provedel\n\n"
        "*Note*: Al fantacalcio sono da prendere entrambi.\n",
    )
    (squadra,) = parse_keepers(md)
    assert (squadra["starters"], squadra["backup"], squadra["risky"]) == (
        ["Martinez"],
        "Provedel",
        True,
    )


# ------------------------------------------------------------------ aggancio


def _rosa(*voci: tuple[str, str], team: str = "Bologna") -> list[dict]:
    return [{"id": i, "name": n, "team": team, "role": r} for i, (n, r) in enumerate(voci, start=1)]


def test_il_vice_si_cerca_solo_fra_i_portieri():
    """Il Bologna ha un portiere Pessina e il Monza un centrocampista Pessina."""
    players = _rosa(("Skorupski", "P"), ("Pessina", "P"), ("Pessina", "C"))
    gerarchie, sospetti = merge_keepers(
        players,
        [
            {
                "team": "BOLOGNA",
                "starters": ["Skorupski"],
                "backup": "Pessina",
                "risky": True,
                "note": "",
            }
        ],
    )
    assert sospetti == []
    assert gerarchie[0]["backup"] == {"name": "Pessina", "id": 2}


def test_un_portiere_sconosciuto_viene_segnalato():
    players = _rosa(("Skorupski", "P"))
    gerarchie, sospetti = merge_keepers(
        players,
        [{"team": "BOLOGNA", "starters": ["Fantasma"], "backup": None, "risky": False, "note": ""}],
    )
    assert sospetti == ["BOLOGNA: 'Fantasma' -> nessuno"]
    assert gerarchie[0]["starters"] == [{"name": "Fantasma"}]


# ----------------------------------------------------------- articolo vero


@pytest.mark.skipif(ARTICOLO is None, reason="articolo portieri non presente")
def test_l_articolo_vero_si_aggancia_tutto(real_listone):
    players = [
        {"id": p.id, "name": p.name, "team": p.team, "role": p.role.value}
        for p in real_listone.players
    ]
    gerarchie, sospetti = merge_keepers(players, parse_keepers(ARTICOLO))
    assert sospetti == []
    assert len(gerarchie) == 20


@serve_il_listone
def test_le_gerarchie_committate_hanno_un_titolare_per_squadra():
    gerarchie = load_keepers()
    assert len(gerarchie) == 20
    assert all(rank.starters for rank in gerarchie)
    incerte = [rank.team for rank in gerarchie if rank.risky]
    # Poche e motivate: se diventassero dieci vorrebbe dire che la regola
    # sulle note ha cominciato a pescare frasi che non c'entrano.
    assert 0 < len(incerte) <= 6, incerte
    assert all(rank.note for rank in gerarchie if rank.risky)


# --------------------------------------------------------------- gol subiti


def test_i_gol_subiti_sono_quelli_dei_portieri_della_squadra():
    """Ogni portiere porta i gol presi mentre giocava lui: il totale e' la somma."""
    stats = {
        1: {"_team": "Como", "_role": "P", "goals_conceded": 20},
        2: {"_team": "Como", "_role": "P", "goals_conceded": 9},
        3: {"_team": "Como", "_role": "A", "goals_conceded": 0},
        4: {"_team": "Roma", "_role": "P", "goals_conceded": 31},
    }
    assert team_goals_conceded(stats) == {"Como": 29, "Roma": 31}


@pytest.mark.skipif(find_stats(RAW_DIR) is None, reason="statistiche non presenti")
def test_i_gol_subiti_veri_sono_venti_squadre_plausibili():
    subiti = team_goals_conceded(parse_stats(find_stats(RAW_DIR)))
    assert len(subiti) == 20
    assert all(20 <= n <= 90 for n in subiti.values()), subiti


@serve_il_listone
def test_le_neopromosse_restano_senza_gol_subiti():
    gerarchie = load_keepers()
    senza = {rank.team for rank in gerarchie if rank.conceded is None}
    # Sono in Serie A da quest'anno: in A non hanno mai giocato, e uno zero
    # le farebbe sembrare le difese migliori del campionato.
    assert senza == {"Frosinone", "Monza", "Venezia"}
    assert all(rank.conceded and rank.conceded > 0 for rank in gerarchie if rank.team not in senza)


@serve_il_listone
def test_le_carte_sono_in_ordine_di_gol_subiti():
    ordinate = sorted_ranks(load_keepers())
    numeri = [rank.conceded for rank in ordinate if rank.conceded is not None]
    assert numeri == sorted(numeri), "dalla difesa meno battuta alla piu' battuta"
    assert len(numeri) == 17
    assert [rank.team for rank in ordinate[-3:]] == ["Frosinone", "Monza", "Venezia"]
    assert ordinate[0].team == "Como"


def test_la_carta_mostra_i_gol_subiti(service):
    con = KeeperRank(team="Como", starters=(LineupSpot("Butez", None),), conceded=29)
    html = keeper_card_html(con, service.state())
    assert ">29 subiti<" in html
    assert 'title="Gol subiti dal Como nella stagione precedente"' in html

    neopromossa = KeeperRank(team="Monza", starters=(LineupSpot("Tornqvist", None),))
    assert "subiti" not in keeper_card_html(neopromossa, service.state())


# ------------------------------------------------------------------ griglia


@serve_la_griglia
def test_la_griglia_trascritta_e_simmetrica():
    """Controllo della trascrizione: 190 coppie lette due volte devono combaciare."""
    grid = load_keeper_grid()
    assert len(grid.teams) == 20
    assert len(grid.values) == 20
    for riga in grid.values:
        assert len(riga) == 20
    errori = [
        (grid.teams[i], grid.teams[j])
        for i in range(20)
        for j in range(i + 1, 20)
        if grid.value(i, j) != grid.value(j, i)
    ]
    assert errori == []


@serve_la_griglia
def test_la_diagonale_e_vuota_e_i_valori_sono_plausibili():
    grid = load_keeper_grid()
    assert all(grid.value(i, i) == 0 for i in range(20))
    valori = [grid.value(i, j) for i in range(20) for j in range(20) if i != j]
    assert min(valori) >= 60 and max(valori) <= 99


def test_le_squadre_della_griglia_sono_quelle_del_listone(real_listone):
    grid = load_keeper_grid()
    assert set(grid.teams) == {p.team for p in real_listone.players}


@serve_la_griglia
def test_la_griglia_si_allarga_con_la_finestra():
    """A larghezza fissa restava un francobollo su uno schermo grande."""
    html = grid_html(load_keeper_grid())
    assert ".gp{width:100%" in html
    assert "table-layout:fixed" in html
    # Sotto la soglia scorre nel suo contenitore invece di schiacciarsi.
    assert "min-width:660px" in html
    assert ".gp-wrap{overflow-x:auto" in html


@serve_la_griglia
def test_la_griglia_accende_riga_e_colonna_senza_javascript():
    grid = load_keeper_grid()
    html = grid_html(grid)
    assert "<script" not in html
    assert ".gp tr:hover>*{background" in html
    # Una regola :has() per ognuna delle 21 colonne, stemmi compresi.
    assert html.count(":nth-child(21):hover") == 1
    assert html.count(":hover) tr>*:nth-child") == 21


@serve_la_griglia
def test_la_griglia_evidenzia_le_coppie_migliori():
    grid = load_keeper_grid()
    html = grid_html(grid)
    assert html.count('class="cella hot"') == sum(
        1
        for i in range(20)
        for j in range(20)
        if i != j and grid.value(i, j) >= grid.highlight_from
    )
    assert 'title="Bologna + Inter: 92"' in html


def test_senza_griglia_non_si_disegna_niente():
    assert grid_html(KeeperGrid()) == ""


# --------------------------------------------------------------- pararigori


def _portiere(nome: str, parati: int, partite: int, pid: int = 100, team: str = "Ajax"):
    from dataclasses import replace as _replace

    from asta.domain.models import Player

    stats = PlayerStats(
        matches=partite,
        average=6.0,
        fanta_average=6.0,
        goals=0,
        goals_conceded=30,
        penalties_saved=parati,
        penalties_taken=0,
        assists=0,
        yellow_cards=0,
        red_cards=0,
        own_goals=0,
    )
    base = Player(id=pid, role=Role.P, name=nome, team=team, quotation=10, fvm=20, stats=stats)
    return _replace(base)


def test_i_pararigori_sono_in_ordine_di_rigori_parati():
    tre = _portiere("Montipo", parati=3, partite=35, pid=1)
    due = _portiere("Falcone", parati=2, partite=38, pid=2)
    uno = _portiere("Okoye", parati=1, partite=30, pid=3)
    assert [p.name for p in penalty_savers((uno, tre, due))] == ["Montipo", "Falcone", "Okoye"]


def test_a_parita_di_rigori_passa_avanti_chi_ha_giocato_di_piu():
    poche = _portiere("Milinkovic", parati=3, partite=27, pid=1)
    tante = _portiere("Montipo", parati=3, partite=35, pid=2)
    assert [p.name for p in penalty_savers((poche, tante))] == ["Montipo", "Milinkovic"]


def test_chi_ha_giocato_poco_resta_fuori():
    """Un rigore parato in tre presenze e' un caso, non una dote."""
    poche = _portiere("Meteora", parati=1, partite=MIN_PARTITE_PARARIGORI - 1, pid=1)
    giuste = _portiere("Okoye", parati=1, partite=MIN_PARTITE_PARARIGORI, pid=2)
    assert [p.name for p in penalty_savers((poche, giuste))] == ["Okoye"]


def test_chi_non_ne_ha_parati_non_compare():
    nessuno = _portiere("Skorupski", parati=0, partite=38, pid=1)
    assert penalty_savers((nessuno,)) == ()


def test_i_pararigori_veri_del_listone(real_listone):
    parate = penalty_savers(real_listone.players)
    assert parate, "qualcuno un rigore lo ha parato"
    assert all(p.role is Role.P for p in parate)
    assert all(p.stats and p.stats.penalties_saved >= 1 for p in parate)
    assert all(p.stats and p.stats.matches >= MIN_PARTITE_PARARIGORI for p in parate)
    numeri = [p.stats.penalties_saved for p in parate]  # type: ignore[union-attr]
    assert numeri == sorted(numeri, reverse=True)


def test_la_striscia_dei_pararigori_mostra_quanti_ne_ha_parati(service, listone):
    portiere = _portiere("Montipo", parati=3, partite=35, pid=listone.players[0].id)
    html = penalty_savers_html((portiere,), service.state())
    assert 'class="gp-p-n">3</b>' in html
    assert "Montipo" in html
    assert 'title="3 rigori parati in 35 partite a voto"' in html


def test_il_pararigori_gia_preso_e_barrato(service, listone):
    preso = listone.players[0]
    service.record(EventType.PLAYER_ASSIGNED, {"player_id": preso.id, "team": "Ajax", "price": 14})
    portiere = _portiere(preso.name, parati=1, partite=20, pid=preso.id)
    html = penalty_savers_html((portiere,), service.state())
    assert 'class="gp-p-nome taken"' in html
    assert "preso da Ajax per 14" in html


def test_senza_pararigori_non_si_disegna_niente(service):
    assert penalty_savers_html((), service.state()) == ""


# ------------------------------------------------------------------ pagina


def test_il_titolare_e_verde_e_il_ballottaggio_giallo(service, listone):
    portiere = next(p for p in listone.players if p.role.value == "P")
    secondo = [p for p in listone.players if p.role.value == "P"][1]

    sicuro = KeeperRank(team="Ajax", starters=(LineupSpot(portiere.name, portiere.id),))
    assert 'class="gk-name first"' in keeper_card_html(sicuro, service.state())

    diviso = KeeperRank(
        team="Ajax",
        starters=(LineupSpot(portiere.name, portiere.id), LineupSpot(secondo.name, secondo.id)),
        risky=True,
        note="Se lo giocano",
    )
    html = keeper_card_html(diviso, service.state())
    assert html.count('class="gk-name split"') == 2
    assert "gk-card risk" in html
    assert 'title="Se lo giocano"' in html


def test_il_vice_da_comprare_compare_solo_dove_serve(service, listone):
    portieri = [p for p in listone.players if p.role.value == "P"]
    con_vice = KeeperRank(
        team="Ajax",
        starters=(LineupSpot(portieri[0].name, portieri[0].id),),
        backup=LineupSpot(portieri[1].name, portieri[1].id),
        risky=True,
    )
    assert "Prendi anche" in keeper_card_html(con_vice, service.state())

    senza = KeeperRank(team="Ajax", starters=(LineupSpot(portieri[0].name, portieri[0].id),))
    assert "Prendi anche" not in keeper_card_html(senza, service.state())


def test_il_portiere_gia_preso_resta_leggibile_ma_barrato(service, listone):
    portiere = next(p for p in listone.players if p.role.value == "P")
    service.record(
        EventType.PLAYER_ASSIGNED,
        {"player_id": portiere.id, "team": "Ajax", "price": 9},
    )
    rank = KeeperRank(team="Ajax", starters=(LineupSpot(portiere.name, portiere.id),))
    html = keeper_card_html(rank, service.state())
    assert portiere.name in html
    assert 'class="gk-name taken" title="Preso da Ajax per 9"' in html


def test_senza_gerarchie_la_pagina_lo_dice(service):
    assert "Nessuna gerarchia disponibile" in keepers_html((), service.state())

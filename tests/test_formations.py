"""Test delle probabili formazioni: lettura dell'articolo, aggancio, pagina.

La formazione tipo e' una riga sola di prosa punteggiata, e la punteggiatura
e' la struttura: punto e virgola fra i reparti, virgola fra i posti in campo,
barra fra i due nomi che se lo giocano.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from scripts.build_players import (
    RAW_DIR,
    find_lineups,
    merge_lineups,
    parse_lineups,
)

from asta.data.keepers import conceded_by_team
from asta.data.players import load_lineups
from asta.domain.events import EventType
from asta.domain.models import (
    LineupSpot,
    Player,
    Role,
    Starting,
    TeamLineup,
)
from asta.ui.components import FUORI_FORMAZIONE, badge_items, filtra_titolarita
from asta.ui.formations import lineups_html, sorted_lineups, team_lineup_html
from conftest import serve_il_listone

ARTICOLO = find_lineups(RAW_DIR)


@pytest.fixture(scope="module")
def real_lineups() -> tuple[TeamLineup, ...]:
    """Le formazioni vere, quelle committate nel JSON del listone."""
    return load_lineups()


def _scrivi(tmp_path: Path, testo: str) -> Path:
    percorso = tmp_path / "probabili_formazioni_prova.md"
    percorso.write_text(testo, encoding="utf-8")
    return percorso


# ------------------------------------------------------------------ lettura


def test_la_punteggiatura_e_la_struttura(tmp_path):
    md = _scrivi(
        tmp_path,
        "**GENOA**\n\n*Formazione-tipo:* Bijlow; Marcandalli, Ostigard; Colombo.\n",
    )
    assert parse_lineups(md) == [
        ("GENOA", [[["Bijlow"]], [["Marcandalli"], ["Ostigard"]], [["Colombo"]]])
    ]


def test_la_barra_separa_i_due_del_ballottaggio(tmp_path):
    md = _scrivi(tmp_path, "**COMO**\n\n*Formazione-tipo:* Butez/Sanchez Ro.; Ramon.\n")
    assert parse_lineups(md) == [("COMO", [[["Butez", "Sanchez Ro."]], [["Ramon"]]])]


def test_il_punto_della_frase_non_si_mangia_l_iniziale(tmp_path):
    """L'articolo chiude con due punti quando l'ultimo nome ha l'iniziale."""
    md = _scrivi(tmp_path, "**MILAN**\n\n*Formazione-tipo:* Maignan; Ramos G..\n")
    assert parse_lineups(md) == [("MILAN", [[["Maignan"]], [["Ramos G."]]])]


# ------------------------------------------------------------------ aggancio


def _rosa(*nomi: str, team: str = "Genoa") -> list[dict]:
    return [{"id": i, "name": n, "team": team} for i, n in enumerate(nomi, start=1)]


def test_chi_e_solo_nel_suo_posto_e_titolare():
    players = _rosa("Bijlow", "Colombo")
    formazioni, titolari, sospetti = merge_lineups(
        players, [("GENOA", [[["Bijlow"]], [["Colombo"]]])]
    )
    assert (titolari, sospetti) == (2, [])
    assert [p["starter"] for p in players] == ["starter", "starter"]
    assert formazioni[0]["team"] == "Genoa", "il nome e' quello del listone"


def test_chi_se_lo_gioca_e_in_ballottaggio():
    players = _rosa("Mitaj", "Ellertsson")
    merge_lineups(players, [("GENOA", [[["Mitaj", "Ellertsson"]]])])
    assert [p["starter"] for p in players] == ["contested", "contested"]


def test_il_jolly_provato_in_due_posti_tiene_la_menzione_migliore():
    """Perrone e' in ballottaggio in un posto e titolare nell'altro."""
    players = _rosa("Perrone", "Milla", team="Como")
    merge_lineups(players, [("COMO", [[["Milla", "Perrone"], ["Perrone"]]])])
    assert players[0]["starter"] == "starter"
    assert players[1]["starter"] == "contested"


def test_un_nome_fuori_dal_listone_resta_scritto_ma_senza_id():
    players = _rosa("Bijlow")
    formazioni, titolari, sospetti = merge_lineups(
        players, [("GENOA", [[["Bijlow"]], [["Fantasma"]]])]
    )
    assert titolari == 1
    assert sospetti == ["GENOA: 'Fantasma' -> nessuno"]
    assert formazioni[0]["units"][1] == [[{"name": "Fantasma"}]]


def test_rigenerare_non_lascia_titolarita_vecchie():
    players = _rosa("Bijlow")
    merge_lineups(players, [("GENOA", [[["Bijlow"]]])])
    merge_lineups(players, [])
    assert players[0].get("starter") is None


# ------------------------------------------------------------ articolo vero


@pytest.mark.skipif(ARTICOLO is None, reason="articolo formazioni non presente")
def test_l_articolo_vero_si_aggancia_tutto(real_listone):
    """Ogni nome delle formazioni esiste nel listone: nessuna segnalazione."""
    players = [{"id": p.id, "name": p.name, "team": p.team} for p in real_listone.players]
    formazioni, titolari, sospetti = merge_lineups(players, parse_lineups(ARTICOLO))
    assert sospetti == []
    assert len(formazioni) == 20
    assert titolari > 250


@pytest.mark.skipif(ARTICOLO is None, reason="articolo formazioni non presente")
def test_la_titolarita_arriva_fino_al_listone(real_listone):
    carnesecchi = next(p for p in real_listone.players if p.name == "Carnesecchi")
    assert carnesecchi.starter is Starting.STARTER
    bellanova = next(p for p in real_listone.players if p.name == "Bellanova")
    assert bellanova.starter is Starting.CONTESTED
    # La riserva del portiere titolare non compare in formazione.
    assert next(p for p in real_listone.players if p.name == "Sportiello").starter is None


def test_il_filtro_divide_titolari_ballottaggi_e_panchinari(real_listone):
    """Le tre voci del menu coprono il listone senza sovrapporsi."""
    tutti = tuple(real_listone.players)
    titolari = filtra_titolarita(tutti, "Titolare")
    ballottaggi = filtra_titolarita(tutti, "Ballottaggio")
    fuori = filtra_titolarita(tutti, FUORI_FORMAZIONE)

    assert all(p.starter is Starting.STARTER for p in titolari)
    assert all(p.starter is Starting.CONTESTED for p in ballottaggi)
    assert all(p.starter is None for p in fuori)
    assert len(titolari) + len(ballottaggi) + len(fuori) == len(tutti)
    assert titolari and ballottaggi and fuori


def test_una_scelta_che_non_esiste_non_filtra_niente(real_listone):
    """Il menu parte da "Tutte", che non e' una titolarita'."""
    tutti = tuple(real_listone.players)
    assert filtra_titolarita(tutti, "Tutte") == tutti


# ------------------------------------------------------------------- modulo


def test_il_modulo_e_la_forma_della_formazione():
    """Non si legge dalla prosa: e' quanti posti ha ogni reparto dopo il portiere."""
    genoa = TeamLineup(
        team="Genoa",
        units=(
            ((LineupSpot("Bijlow"),),),
            tuple((LineupSpot(n),) for n in ("Marcandalli", "Ostigard", "Vasquez")),
            tuple((LineupSpot(n),) for n in ("Drameh", "Sow", "Frendrup", "Mitaj")),
            tuple((LineupSpot(n),) for n in ("Baldanzi", "Vitinha O.")),
            ((LineupSpot("Colombo"),),),
        ),
    )
    assert genoa.module == "3-4-2-1"


def test_senza_formazione_non_c_e_nessun_modulo():
    assert TeamLineup(team="Ajax").module == ""
    assert TeamLineup(team="Ajax", units=(((LineupSpot("Solo il portiere"),),),)).module == ""


@pytest.mark.skipif(ARTICOLO is None, reason="articolo formazioni non presente")
def test_i_moduli_veri_sono_moduli_da_undici(real_lineups):
    for formazione in real_lineups:
        numeri = [int(n) for n in formazione.module.split("-")]
        assert 3 <= len(numeri) <= 4, formazione.team
        assert sum(numeri) == 10, f"{formazione.team}: {formazione.module} piu' il portiere"


@pytest.mark.skipif(ARTICOLO is None, reason="articolo formazioni non presente")
def test_il_modulo_finisce_nell_intestazione_della_card(service, real_lineups):
    inter = next(f for f in real_lineups if f.team == "Inter")
    assert inter.module == "3-5-2"
    html = team_lineup_html(inter, service.state())
    assert '<span class="pf-mod" title="Modulo della formazione tipo">3-5-2</span>' in html


# ------------------------------------------------------------------ lettere


def _player(**kwargs) -> Player:
    base = Player(id=1, role=Role.P, name="Carnesecchi", team="Atalanta", quotation=10, fvm=20)
    return replace(base, **kwargs)


def test_la_maglia_viene_prima_dei_piazzati():
    lettere = [voce[0] for voce in badge_items(_player(starter=Starting.STARTER))]
    assert lettere == ["T"]
    assert badge_items(_player()) == []


def test_il_ballottaggio_e_una_b_gialla():
    lettera, nome, titolo, colore = badge_items(_player(starter=Starting.CONTESTED))[0]
    assert (lettera, nome) == ("B", "Ballottaggio")
    assert titolo == "Ballottaggio nella formazione tipo"
    assert colore == "#facc15"


# ------------------------------------------------------------------ pagina


def _formazione(*nomi_id: tuple[str, int | None]) -> tuple[TeamLineup, ...]:
    spots = tuple(LineupSpot(name=n, player_id=i) for n, i in nomi_id)
    return (TeamLineup(team="Ajax", units=((tuple(spots),),)),)


def test_chi_e_stato_preso_resta_leggibile_ma_barrato(service, listone):
    """Il nome non sparisce: serve riconoscerlo, non nasconderlo."""
    preso = listone.players[0]
    service.record(
        EventType.PLAYER_ASSIGNED,
        {"player_id": preso.id, "team": "Ajax", "price": 7},
    )
    state = service.state()

    html = lineups_html(_formazione((preso.name, preso.id)), state)
    assert preso.name in html
    assert "pf-name taken" in html
    assert 'title="Preso da Ajax per 7"' in html


def test_chi_e_libero_ha_il_colore_della_titolarita(service, listone):
    state = service.state()
    libero = listone.players[0]

    solo = lineups_html(_formazione((libero.name, libero.id)), state)
    assert 'class="pf-name t"' in solo

    doppio = lineups_html(
        _formazione((libero.name, libero.id), (listone.players[1].name, listone.players[1].id)),
        state,
    )
    assert doppio.count('class="pf-name b"') == 2
    assert "pf-vs" in doppio


def test_un_nome_senza_id_si_mostra_lo_stesso(service):
    html = lineups_html(_formazione(("Fantasma", None)), service.state())
    assert "Fantasma" in html
    assert "pf-name taken" not in html


def test_senza_formazioni_la_pagina_lo_dice(service):
    assert "Nessuna formazione disponibile" in lineups_html((), service.state())


# ------------------------------------------------------------------ ordine


@serve_il_listone
def test_le_card_sono_in_ordine_di_gol_subiti():
    """La stessa fila dei portieri e della copertura: si impara una volta sola."""
    ordinate = sorted_lineups(load_lineups())
    subiti = conceded_by_team()
    numeri = [subiti[f.team] for f in ordinate if f.team in subiti]
    assert numeri == sorted(numeri), "dalla difesa meno battuta alla piu' battuta"
    assert ordinate[0].team == "Como"
    assert [f.team for f in ordinate[-3:]] == ["Frosinone", "Monza", "Venezia"]


def test_le_neopromosse_chiudono_la_fila_e_non_la_aprono():
    """Uno zero al posto del dato mancante le farebbe sembrare le migliori difese."""
    formazioni = tuple(
        TeamLineup(team=club, units=(((LineupSpot(name=club, player_id=None),),),))
        for club in ("Torino", "Venezia", "Como")
    )
    ordinate = sorted_lineups(formazioni, {"Como": 29, "Torino": 63})
    assert [f.team for f in ordinate] == ["Como", "Torino", "Venezia"]


def test_la_pagina_disegna_le_card_nell_ordine_deciso(service):
    formazioni = tuple(
        TeamLineup(team=club, units=(((LineupSpot(name=f"Portiere {club}", player_id=None),),),))
        for club in ("Torino", "Como")
    )
    html = lineups_html(formazioni, service.state(), {"Como": 29, "Torino": 63})
    assert html.index("Portiere Como") < html.index("Portiere Torino")

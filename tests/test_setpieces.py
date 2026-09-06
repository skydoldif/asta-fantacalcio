"""Test dei calci piazzati: lettura degli articoli, aggancio al listone, resa.

Le gerarchie arrivano da due articoli in markdown, non da un export con gli
Id: il pezzo delicato e' quindi l'aggancio per nome dentro la rosa giusta, e
la regola con cui una menzione diventa rossa (battitore designato) o gialla
(se li gioca con altri).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from scripts.build_players import (
    RAW_DIR,
    find_penalties,
    find_set_pieces,
    merge_set_pieces,
    parse_penalties,
    parse_set_pieces,
)

from asta.domain.models import Confidence, Player, Role, SetPiece, SetPieces
from asta.ui.components import (
    SET_PIECE_COLOR,
    _colore_piazzato,
    _formatta_piazzato,
    listone_display,
    listone_table,
    set_piece_items,
)

RIGORISTI = find_penalties(RAW_DIR)
PIAZZATI = find_set_pieces(RAW_DIR)


def _scrivi(tmp_path: Path, nome: str, testo: str) -> Path:
    percorso = tmp_path / nome
    percorso.write_text(testo, encoding="utf-8")
    return percorso


# ------------------------------------------------------------------ rigoristi


def test_un_solo_nome_in_primo_e_un_rigorista_designato(tmp_path):
    md = _scrivi(
        tmp_path,
        "rigoristi_prova.md",
        "🎯 **BOLOGNA**\n\n*Primo*: Nessun dubbio, e' Riccardo **Orsolini**.\n",
    )
    assert parse_penalties(md) == [("BOLOGNA", "Orsolini", "penalty", "sure")]


def test_due_contendenti_in_primo_non_sono_sicuri(tmp_path):
    md = _scrivi(
        tmp_path,
        "rigoristi_prova.md",
        "🎯 **ATALANTA**\n\n*Primo*: **Kessié** se li contende con **Scamacca**.\n",
    )
    assert parse_penalties(md) == [
        ("ATALANTA", "Kessié", "penalty", "unsure"),
        ("ATALANTA", "Scamacca", "penalty", "unsure"),
    ]


def test_le_alternative_delle_note_sono_sempre_gialle(tmp_path):
    md = _scrivi(
        tmp_path,
        "rigoristi_prova.md",
        "🎯 **INTER**\n\n*Primo*: e' **Calhanoglu**.\n\n*Note*: dietro c'e' **Zielinski**.\n",
    )
    assert parse_penalties(md) == [
        ("INTER", "Calhanoglu", "penalty", "sure"),
        ("INTER", "Zielinski", "penalty", "unsure"),
    ]


def test_una_frase_enfatizzata_non_e_un_nome(tmp_path):
    """Nell'articolo vero il grassetto evidenzia anche le citazioni lunghe."""
    md = _scrivi(
        tmp_path,
        "rigoristi_prova.md",
        "🎯 **GENOA**\n\n*Primo*: si candida **Colombo**.\n\n"
        "*Note*: disse **Se vedo che Ostigard li batte meglio di tutti, li batte lui**.\n",
    )
    assert parse_penalties(md) == [("GENOA", "Colombo", "penalty", "sure")]


# ------------------------------------------------------- corner e punizioni


def test_il_primo_della_fila_batte_di_sicuro(tmp_path):
    md = _scrivi(
        tmp_path,
        "corner_e_punizioni_prova.md",
        "✅ **MILAN**\n\n*Punizioni*: Modric, Pulisic\n\n*Corner*: Modric, Bartesaghi\n",
    )
    assert parse_set_pieces(md) == [
        ("MILAN", "Modric", "free_kick", "sure"),
        ("MILAN", "Pulisic", "free_kick", "unsure"),
        ("MILAN", "Modric", "corner", "sure"),
        ("MILAN", "Bartesaghi", "corner", "unsure"),
    ]


def test_il_ballottaggio_con_la_barra_vale_per_tutti_e_due(tmp_path):
    md = _scrivi(
        tmp_path,
        "corner_e_punizioni_prova.md",
        "✅ **SASSUOLO**\n\n*Corner*: Berardi, Doig/Obrador\n",
    )
    assert [m[1] for m in parse_set_pieces(md)] == ["Berardi", "Doig", "Obrador"]


# ------------------------------------------------------------------ aggancio


def _rosa(*nomi: str, team: str = "Sassuolo") -> list[dict]:
    return [{"id": i, "name": n, "team": team} for i, n in enumerate(nomi, start=1)]


def test_il_nome_dell_articolo_trova_quello_del_listone():
    """Gli articoli scrivono "Seba Esposito", il listone "Esposito Se."."""
    players = _rosa("Esposito Se.", "Berardi")
    abbinati, sospetti = merge_set_pieces(
        players, [("SASSUOLO", "Seba Esposito", "corner", "unsure")]
    )
    assert (abbinati, sospetti) == (1, [])
    assert players[0]["set_pieces"] == {"corner": "unsure"}


def test_l_omonimo_di_un_altra_squadra_non_viene_toccato():
    players = _rosa("Esposito F.P.", team="Inter") + _rosa("Esposito Se.", team="Sassuolo")
    merge_set_pieces(players, [("SASSUOLO", "Seba Esposito", "corner", "sure")])
    assert players[0].get("set_pieces") is None
    assert players[1]["set_pieces"] == {"corner": "sure"}


def test_un_nome_che_non_esiste_viene_segnalato():
    """Capita con gli svincolati: nell'articolo ci sono, nel listone no."""
    players = _rosa("Vlasic", team="Torino")
    abbinati, sospetti = merge_set_pieces(
        players, [("TORINO", "Ricardo Rodriguez", "penalty", "unsure")]
    )
    assert abbinati == 0
    assert sospetti == ["TORINO: 'Ricardo Rodriguez' -> nessuno"]


def test_la_menzione_piu_sicura_vince():
    players = _rosa("Berardi")
    merge_set_pieces(
        players,
        [
            ("SASSUOLO", "Berardi", "penalty", "sure"),
            ("SASSUOLO", "Berardi", "penalty", "unsure"),
        ],
    )
    assert players[0]["set_pieces"] == {"penalty": "sure"}


def test_rigenerare_non_lascia_piazzati_vecchi():
    players = _rosa("Berardi")
    merge_set_pieces(players, [("SASSUOLO", "Berardi", "penalty", "sure")])
    merge_set_pieces(players, [])
    assert players[0].get("set_pieces") is None


# ------------------------------------------------------------ articoli veri


@pytest.mark.skipif(RIGORISTI is None, reason="articolo rigoristi non presente")
def test_i_rigoristi_veri_coprono_tutte_le_squadre():
    mentions = parse_penalties(RIGORISTI)
    squadre = {m[0] for m in mentions}
    assert len(squadre) == 20
    designati = {m[0] for m in mentions if m[3] == "sure"}
    # Non tutte le squadre hanno un rigorista designato: dove la gerarchia e'
    # aperta l'articolo mette due o tre nomi, e nessuno diventa rosso.
    assert 0 < len(designati) < 20


@pytest.mark.skipif(PIAZZATI is None, reason="articolo piazzati non presente")
def test_ogni_squadra_ha_un_battitore_designato_per_corner_e_punizioni():
    mentions = parse_set_pieces(PIAZZATI)
    for piazzato in ("corner", "free_kick"):
        sicuri = [m for m in mentions if m[2] == piazzato and m[3] == "sure"]
        assert len(sicuri) == 20, piazzato


@pytest.mark.skipif(RIGORISTI is None, reason="articolo rigoristi non presente")
def test_i_piazzati_del_listone_committato(real_listone):
    orsolini = next(p for p in real_listone.players if p.name == "Orsolini")
    assert orsolini.set_pieces == SetPieces(
        penalty=Confidence.SURE, corner=Confidence.SURE, free_kick=Confidence.SURE
    )
    # Kean e' arrivato al Como e i rigori se li gioca: giallo, non rosso.
    kean = next(p for p in real_listone.players if p.name == "Kean")
    assert kean.set_pieces == SetPieces(penalty=Confidence.UNSURE)
    # Chi non e' nominato da nessuna delle due gerarchie non ha nulla.
    portiere = next(p for p in real_listone.by_role(Role.P))
    assert portiere.set_pieces is None


# ------------------------------------------------------------------ dominio


def test_i_piazzati_sopravvivono_al_json():
    piazzati = SetPieces(penalty=Confidence.SURE, free_kick=Confidence.UNSURE)
    assert piazzati.to_payload() == {"penalty": "sure", "free_kick": "unsure"}
    assert SetPieces.from_payload(piazzati.to_payload()) == piazzati


def test_un_piazzato_sconosciuto_viene_ignorato():
    assert SetPieces.from_payload({"rimessa_laterale": "sure"}) == SetPieces()


def test_of_risponde_none_su_un_piazzato_che_non_batte():
    piazzati = SetPieces(corner=Confidence.SURE)
    assert piazzati.of(SetPiece.CORNER) is Confidence.SURE
    assert piazzati.of(SetPiece.PENALTY) is None


# ------------------------------------------------------------------ interfaccia


def test_le_lettere_prendono_il_colore_della_sicurezza():
    player = Player(
        id=1,
        role=Role.A,
        name="Dybala",
        team="Roma",
        quotation=20,
        fvm=100,
        set_pieces=SetPieces(penalty=Confidence.UNSURE, corner=Confidence.SURE),
    )
    assert set_piece_items(player) == [
        ("R", "Rigori", "Rigori: possibile", SET_PIECE_COLOR[Confidence.UNSURE]),
        ("C", "Corner", "Corner: sicuro", SET_PIECE_COLOR[Confidence.SURE]),
    ]
    assert set_piece_items(replace(player, set_pieces=None)) == []


def test_nel_listone_le_lettere_sono_ordinabili():
    """Sotto la lettera c'e' un numero: 2 il designato, 1 chi se li gioca."""
    sicuro = Player(
        id=1,
        role=Role.A,
        name="Berardi",
        team="Sassuolo",
        quotation=20,
        fvm=100,
        set_pieces=SetPieces(penalty=Confidence.SURE),
    )
    incerto = replace(
        sicuro, id=2, name="Laurientè", set_pieces=SetPieces(penalty=Confidence.UNSURE)
    )
    nessuno = replace(sicuro, id=3, name="Volpato", set_pieces=None)

    tabella = listone_table((sicuro, incerto, nessuno))
    # Nell'intestazione c'e' la parola, nella cella la lettera.
    assert list(tabella["Rigorista"][:2]) == [2, 1]
    assert tabella["Rigorista"].isna()[2], "chi non batte i rigori non ha un valore"

    # A schermo il numero sparisce e resta la lettera; chi non li batte non
    # ha nemmeno quella, e la riga finisce con la squadra.
    righe = listone_display(tabella).to_string().splitlines()[1:]
    assert [riga.split()[-1] for riga in righe] == ["R", "R", "Sassuolo"]


def test_la_cella_di_chi_non_batte_resta_vuota():
    assert _formatta_piazzato(2, lettera="R") == "R"
    assert _formatta_piazzato(-1, lettera="R") == ""
    assert _colore_piazzato(2) == f"color:{SET_PIECE_COLOR[Confidence.SURE]};font-weight:700"
    assert _colore_piazzato(-1) == ""

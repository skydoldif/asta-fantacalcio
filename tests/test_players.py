"""Test del listone e del parser dell'Excel ufficiale."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from scripts.build_players import (
    build_payload,
    candidati,
    describe_changes,
    find_sources,
    find_xlsx,
    initial,
    parse_listone,
    render_payload,
)
from scripts.build_players import sort_key as script_sort_key

from asta.domain.models import Role, sort_key


def _xlsx() -> Path | None:
    """Il listone ufficiale, se presente: lo cerca come fa lo script.

    Cosi' il controllo continua a valere anche se il file cambia nome (per
    esempio al listone definitivo di un'altra stagione).
    """
    try:
        return find_xlsx()
    except FileNotFoundError:
        return None


XLSX = _xlsx()


def test_listone_committato_e_completo(real_listone):
    # Sentinella: se il JSON venisse rigenerato da un file sbagliato (o
    # troncato) il numero cambierebbe. Va aggiornato quando cambia il listone.
    assert len(real_listone.players) == 533


def test_conteggio_per_ruolo(real_listone):
    counts = {r: len(real_listone.by_role(r)) for r in Role}
    assert counts == {Role.P: 65, Role.D: 188, Role.C: 193, Role.A: 87}


def test_id_unici(real_listone):
    ids = [p.id for p in real_listone.players]
    assert len(ids) == len(set(ids))


def test_ordine_alfabetico_dentro_ogni_ruolo(real_listone):
    for role in Role:
        keys = [p.key for p in real_listone.by_role(role)]
        assert keys == sorted(keys)


def test_ricerca_ignora_accenti_e_maiuscole(real_listone):
    assert real_listone.search("SVILAR")
    assert real_listone.search("inter", role=Role.P)


def test_get_solleva_keyerror_su_id_inesistente(real_listone):
    with pytest.raises(KeyError):
        real_listone.get(999999)


@pytest.mark.skipif(XLSX is None, reason="xlsx originale non presente")
def test_parser_esclude_i_ceduti():
    players = parse_listone(XLSX)
    assert len(players) == 533
    # I giocatori del foglio "Ceduti" non devono comparire.
    assert 5876 not in {p["id"] for p in players}  # Di Gregorio, ceduto


@pytest.mark.skipif(XLSX is None, reason="xlsx originale non presente")
def test_json_committato_allineato_allo_xlsx():
    """Rete di sicurezza: l'Excel cambia, il JSON no, e nessuno se ne accorge.

    E' il confronto byte per byte che fa ``build_players.py --check``: se
    diventa rosso basta rilanciare ``python scripts/build_players.py``.
    """
    atteso = render_payload(build_payload(XLSX, **find_sources())[0])
    attuale = Path("data/players_2026_27.json").read_text(encoding="utf-8")
    assert attuale == atteso, "Rigenera il JSON: python scripts/build_players.py"


def test_a_scegliere_il_file_e_il_nome_non_la_data(tmp_path):
    """Regressione: in CI le date dei file sono quelle del checkout.

    Con il solo ``mtime`` come criterio l'ordine cambiava da macchina a
    macchina: la CI sceglieva l'altro file delle statistiche e il confronto
    byte per byte col JSON committato falliva solo li'.
    """
    for nome, quando in (
        ("Statistiche_2024_25.xlsx", 1800000000),  # il piu' recente sul disco
        ("Statistiche_2026_27.xlsx", 1700000000),
        ("Statistiche_2025_26.xlsx", 1750000000),
    ):
        percorso = tmp_path / nome
        percorso.write_text("")
        os.utime(percorso, (quando, quando))

    assert [f.name for f in candidati(tmp_path, "Statistiche_*.xlsx")] == [
        "Statistiche_2026_27.xlsx",
        "Statistiche_2025_26.xlsx",
        "Statistiche_2024_25.xlsx",
    ]


@pytest.mark.skipif(XLSX is None, reason="xlsx originale non presente")
def test_lo_script_trova_da_solo_il_listone():
    # Senza argomenti lo script deve pescare il listone giusto, non le
    # statistiche o altri file appoggiati nella stessa cartella.
    assert find_xlsx().name.startswith("Quotazioni_")


def test_le_differenze_elencano_nuovi_usciti_e_modificati():
    def player(pid, name, quotation=10):
        return {
            "id": pid,
            "role": "P",
            "name": name,
            "team": "Inter",
            "quotation": quotation,
            "fvm": 1,
            "initial": name[0],
            "sort_key": name.upper(),
        }

    vecchio = {"source": "a.xlsx", "count": 2, "players": [player(1, "Uno"), player(2, "Due")]}
    nuovo = {
        "source": "b.xlsx",
        "count": 2,
        "players": [player(1, "Uno", quotation=15), player(3, "Tre")],
    }
    righe = "\n".join(describe_changes(vecchio, nuovo))

    assert "Nuovi (1): Tre" in righe
    assert "Usciti (1): Due" in righe
    assert "quotation 10 -> 15" in righe
    assert "a.xlsx -> b.xlsx" in righe


def test_nessuna_differenza_se_il_json_non_cambia(real_listone):
    payload = {"source": "a.xlsx", "count": 0, "players": []}
    assert describe_changes(payload, payload) == []


def test_chiave_di_ordinamento_condivisa_fra_script_e_app():
    # Se le due implementazioni divergessero, l'ordine alfabetico in app non
    # corrisponderebbe piu' a quello del listone generato.
    for name in ["D'Ambrosio", "Zalewski", "Martinez Jo.", "Perisic"]:
        assert sort_key(name) == script_sort_key(name)


def test_iniziale_normalizzata():
    assert initial("D'Ambrosio") == "D"
    assert initial("Ünal") == "U"

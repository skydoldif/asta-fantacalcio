"""Caricamento del listone dall'app, senza Python ne' terminale.

La prova che conta e' l'ultima: il listone generato dai file caricati deve
venire **identico** a quello che produce ``scripts/build_players.py`` dalla
riga di comando. Sono due strade per la stessa cosa, e se divergessero
qualcuno si ritroverebbe un'asta diversa a seconda di come l'ha preparata.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.build_players import RAW_DIR, build_payload, find_xlsx

from asta.data.players import DEFAULT_PLAYERS_PATH
from asta.ui.upload import OBBLIGATORIO, costruisci, etichette, smista
from conftest import serve_il_listone

QUOTAZIONI = "Quotazioni_Fantacalcio_Stagione_2026_27.xlsx"


# ------------------------------------------------------------------ smistamento


def test_ogni_file_va_al_suo_posto():
    scelti, ignorati = smista(
        [
            QUOTAZIONI,
            "Statistiche_Fantacalcio_Stagione_2025_26.xlsx",
            "difensori.md",
            "centrocampisti.md",
            "attaccanti.md",
            "probabili_formazioni.md",
            "portieri.md",
            "infortunati.md",
            "rigoristi_2026_27.md",
            "corner_e_punizioni_2026_27.md",
        ]
    )
    assert scelti[OBBLIGATORIO] == QUOTAZIONI
    assert scelti["tiers_D"] == "difensori.md"
    assert scelti["keepers_path"] == "portieri.md"
    assert ignorati == []
    # Ogni destinazione ha un nome leggibile: senza, il pannello mostrerebbe
    # all'admin le chiavi interne di build_payload.
    assert set(scelti) <= set(etichette())


def test_un_file_che_non_c_entra_viene_detto_non_ignorato_in_silenzio():
    """Un nome sbagliato deve vedersi subito, non a meta' asta."""
    scelti, ignorati = smista([QUOTAZIONI, "appunti.md", "foto.md"])
    assert scelti == {OBBLIGATORIO: QUOTAZIONI}
    assert ignorati == ["appunti.md", "foto.md"]


def test_fra_le_due_statistiche_vince_quella_coi_portieri():
    """Stessa regola della riga di comando: l'ultimo in ordine alfabetico.

    Non e' un dettaglio: il file "aggiuntive portieri" ha i gol subiti, che
    servono alla pagina delle gerarchie e all'ordine di tutte le altre.
    """
    scelti, _ = smista(
        [
            QUOTAZIONI,
            "Statistiche_Fantacalcio_Stagione_2025_26.xlsx",
            "Statistiche_Fantacalcio_Stagione_2025_26_aggiuntive_portieri.xlsx",
        ]
    )
    assert (
        scelti["stats_path"] == "Statistiche_Fantacalcio_Stagione_2025_26_aggiuntive_portieri.xlsx"
    )


def test_senza_il_listone_ufficiale_non_si_genera_niente():
    with pytest.raises(ValueError, match="listone ufficiale"):
        costruisci({"attaccanti.md": b"niente"})


def test_un_nome_di_file_non_puo_scrivere_fuori_dalla_cartella(tmp_path: Path):
    """Il nome arriva dal browser: un "../" ci scriverebbe dove gli pare."""
    with pytest.raises(ValueError, match="listone ufficiale"):
        costruisci({"../../Quotazioni_cattivo.xlsx": b"x"})


# ------------------------------------------------------------------ generazione


@serve_il_listone
def test_il_listone_generato_dall_app_e_quello_della_riga_di_comando():
    """La prova che le due strade non divergono."""
    files = {p.name: p.read_bytes() for p in RAW_DIR.iterdir() if p.suffix in {".xlsx", ".md"}}
    dall_app, _, _ = costruisci(files)

    import json

    committato = json.loads(DEFAULT_PLAYERS_PATH.read_text(encoding="utf-8"))
    assert dall_app == committato


@serve_il_listone
def test_col_solo_xlsx_si_ottiene_comunque_un_listone():
    """Gli articoli sono facoltativi: senza, restano solo i calciatori."""
    xlsx = find_xlsx(RAW_DIR)
    payload, _, scelti = costruisci({xlsx.name: xlsx.read_bytes()})

    assert scelti == {OBBLIGATORIO: xlsx.name}
    assert payload["count"] > 0
    assert payload["players"]
    for facoltativo in ("tiers", "lineups", "keepers", "stats_source"):
        assert facoltativo not in payload, f"{facoltativo} non doveva esserci"


@serve_il_listone
def test_le_segnalazioni_sono_quelle_dello_script():
    files = {p.name: p.read_bytes() for p in RAW_DIR.iterdir() if p.suffix in {".xlsx", ".md"}}
    _, dall_app, _ = costruisci(files)
    _, da_script = build_payload(
        find_xlsx(RAW_DIR),
        stats_path=RAW_DIR / "Statistiche_Fantacalcio_Stagione_2025_26_aggiuntive_portieri.xlsx",
        penalties_path=RAW_DIR / "rigoristi_2026_27.md",
        set_pieces_path=RAW_DIR / "corner_e_punizioni_2026_27.md",
        lineups_path=RAW_DIR / "probabili_formazioni.md",
        injuries_path=RAW_DIR / "infortunati.md",
        keepers_path=RAW_DIR / "portieri.md",
        tiers_paths={
            "D": RAW_DIR / "difensori.md",
            "C": RAW_DIR / "centrocampisti.md",
            "A": RAW_DIR / "attaccanti.md",
        },
    )
    assert dall_app == da_script

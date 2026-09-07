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
from asta.ui.upload import (
    OBBLIGATORIO,
    costruisci,
    costruisci_da_caselle,
    etichette,
    smista,
    unisci,
)
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


# --------------------------------------------------- caricamento a piu' riprese


def test_i_file_nuovi_si_sommano_a_quelli_vecchi():
    gia = {OBBLIGATORIO: (QUOTAZIONI, b"vecchio xlsx")}
    unite = unisci(gia, {"attaccanti.md": b"fasce"})

    assert unite[OBBLIGATORIO] == (QUOTAZIONI, b"vecchio xlsx"), "le quotazioni non si toccano"
    assert unite["tiers_A"] == ("attaccanti.md", b"fasce")


def test_un_file_nella_stessa_casella_prende_il_posto_del_vecchio():
    gia = {"tiers_A": ("attaccanti.md", b"vecchio")}
    unite = unisci(gia, {"attaccanti.md": b"nuovo"})

    assert unite["tiers_A"] == ("attaccanti.md", b"nuovo")
    assert len(unite) == 1, "non deve restare anche il vecchio"


def test_un_file_ignorato_non_sporca_le_caselle():
    gia = {OBBLIGATORIO: (QUOTAZIONI, b"x")}
    assert unisci(gia, {"appunti.md": b"niente"}) == gia


@serve_il_listone
def test_caricare_in_due_volte_da_lo_stesso_listone_di_una_volta_sola():
    """La proprieta' che rende sicuro il caricamento a pezzi.

    Chi carica le quotazioni oggi e tutto il resto domani deve ottenere
    esattamente il listone di chi ha caricato tutto insieme. Vale perche' si
    rigenera sempre da capo dall'insieme completo, invece di rattoppare
    quello gia' fatto.
    """
    tutti = {p.name: p.read_bytes() for p in RAW_DIR.iterdir() if p.suffix in {".xlsx", ".md"}}
    in_una_volta, _ = costruisci_da_caselle(unisci({}, tutti))

    xlsx = find_xlsx(RAW_DIR)
    primo_giorno = unisci({}, {xlsx.name: xlsx.read_bytes()})
    secondo_giorno = unisci(primo_giorno, {n: c for n, c in tutti.items() if n != xlsx.name})
    in_due_volte, _ = costruisci_da_caselle(secondo_giorno)

    assert in_due_volte == in_una_volta


@serve_il_listone
def test_il_primo_giorno_basta_il_solo_xlsx():
    xlsx = find_xlsx(RAW_DIR)
    caselle = unisci({}, {xlsx.name: xlsx.read_bytes()})
    payload, _ = costruisci_da_caselle(caselle)

    assert payload["count"] > 0
    assert "tiers" not in payload, "senza articoli non ci sono fasce"


def test_senza_il_listone_ufficiale_non_si_genera_nemmeno_a_pezzi():
    with pytest.raises(ValueError, match="listone ufficiale"):
        costruisci_da_caselle({"tiers_A": ("attaccanti.md", b"fasce")})

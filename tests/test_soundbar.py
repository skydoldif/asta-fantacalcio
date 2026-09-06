"""Test della Soundbar.

Il titolo dei pulsanti si ricava dal nome del file, quindi le regole di
formattazione sono la parte che vale la pena verificare: sbagliarle vuol dire
pulsanti con etichette storte davanti a tutti.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from asta.ui.soundbar import Sound, format_title, load_sounds, soundbar_html
from conftest import serve_l_audio

# ------------------------------------------------------------------ titoli


def test_la_prima_parola_e_chi_parla():
    assert format_title("allegri-buona-giornata") == ("Allegri", "Buona giornata")


def test_vale_anche_per_gli_amici():
    # Stessa regola nelle due cartelle: il nome davanti diventa l'etichetta.
    assert format_title("carlo-passa-la-palla") == ("Carlo", "Passa la palla")


def test_solo_l_iniziale_maiuscola():
    # "Passa La Palla" sembrerebbe il titolo di un giornale.
    _, frase = format_title("carlo-passa-la-palla")
    assert frase == "Passa la palla"


def test_una_parola_sola_non_ha_nessun_nome():
    # E' il modo per avere un pulsante senza etichetta verde.
    assert format_title("fischio") == (None, "Fischio")
    assert format_title("calciooooo") == (None, "Calciooooo")


def test_i_numeri_restano_come_sono():
    _, frase = format_title("adani-si-e-idratato-il-numero-10")
    assert frase == "Si e idratato il numero 10"


def test_anche_il_trattino_basso_separa():
    assert format_title("gattuso_sometimes_maybe") == ("Gattuso", "Sometimes maybe")


def test_etichetta_completa():
    suono = Sound(url="x", title="Buona giornata", speaker="Allegri")
    senza = Sound(url="x", title="Fischio", speaker=None)

    assert suono.label == "Allegri: Buona giornata"
    assert senza.label == "Fischio"


# ------------------------------------------------------------------ cartelle


@serve_l_audio
def test_gli_audio_veri_si_trovano():
    sezioni = dict(load_sounds())
    assert list(sezioni) == ["⚽ Calciatori e allenatori", "🎙️ Amici"]

    # Nessun elenco di titoli: le cartelle crescono a ogni tormentone nuovo, e
    # un test che li elenca uno per uno diventerebbe rosso a ogni file aggiunto.
    # Quello che deve restare vero e' la convenzione sui nomi dei file.
    for titolo, gruppo in sezioni.items():
        assert gruppo, f"nessun audio in {titolo}"
        for suono in gruppo:
            assert suono.label.strip(), f"{suono.url}: pulsante senza scritta"
            stem = suono.url.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            if "-" in stem or "_" in stem:
                assert suono.speaker, f"{suono.url}: la prima parola e' chi parla"
            else:
                assert suono.speaker is None, f"{suono.url}: una parola sola, nessun nome"


def test_gli_url_sono_relativi():
    # Come per gli stemmi: su Streamlit Cloud l'app non sta sulla radice.
    for _, gruppo in load_sounds():
        for suono in gruppo:
            assert suono.url.startswith("app/static/audio/")


def test_si_ignora_quello_che_non_e_audio(tmp_path: Path):
    (tmp_path / "calcio").mkdir()
    (tmp_path / "calcio" / ".DS_Store").write_bytes(b"x")
    (tmp_path / "calcio" / "note.txt").write_text("niente")
    (tmp_path / "calcio" / "allegri-ciao.mp3").write_bytes(b"x")

    sezioni = load_sounds(tmp_path)
    assert [s.label for _, gruppo in sezioni for s in gruppo] == ["Allegri: Ciao"]


def test_una_sezione_vuota_non_compare(tmp_path: Path):
    (tmp_path / "calcio").mkdir()
    (tmp_path / "amici").mkdir()
    (tmp_path / "amici" / "fischio.m4a").write_bytes(b"x")

    assert [titolo for titolo, _ in load_sounds(tmp_path)] == ["🎙️ Amici"]


def test_senza_cartelle_non_c_e_niente(tmp_path: Path):
    assert load_sounds(tmp_path) == []


# ------------------------------------------------------------------ pagina


@serve_l_audio
def test_l_html_contiene_tutti_gli_audio():
    sezioni = load_sounds()
    html = soundbar_html(sezioni)

    quanti = 0
    for _, gruppo in sezioni:
        for suono in gruppo:
            assert suono.url in html
            quanti += 1
    # Contato, non scritto a mano: le cartelle sono di chi usa l'app, e un
    # numero fisso qui diventerebbe rosso appena qualcuno aggiunge un file.
    assert html.count("data-i='") == quanti
    assert "sb-dado" in html, "manca il pulsante casuale"


def test_i_nomi_dei_file_finiscono_sanificati(tmp_path: Path):
    (tmp_path / "amici").mkdir()
    (tmp_path / "amici" / 'carlo-"onerror=x.m4a').write_bytes(b"x")

    html = soundbar_html(load_sounds(tmp_path))
    assert 'onerror=x"' not in html
    assert "&quot;" in html or "&#x27;" in html


def test_senza_audio_lo_dice():
    assert "Nessun audio" in soundbar_html([])


@pytest.mark.parametrize("cartella", ["calcio", "amici"])
@serve_l_audio
def test_le_cartelle_esistono_davvero(cartella: str):
    from asta.ui.soundbar import AUDIO_DIR

    assert (AUDIO_DIR / cartella).is_dir()

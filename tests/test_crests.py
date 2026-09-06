"""Test della risoluzione degli stemmi di Serie A."""

from __future__ import annotations

from pathlib import Path

import pytest

from asta.ui import crests


@pytest.fixture
def cartella(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Punta il modulo a una cartella di stemmi vuota e usa e getta."""
    monkeypatch.setattr(crests, "CRESTS_DIR", tmp_path)
    crests._index.cache_clear()
    yield tmp_path
    crests._index.cache_clear()


def test_stemma_presente(cartella):
    (cartella / "como.png").write_bytes(b"x")
    assert crests.crest_url("Como") == "app/static/loghi/como.png"


def test_gli_url_sono_relativi(cartella):
    """Mai con la barra iniziale.

    Su Streamlit Community Cloud l'app non sta sulla radice del dominio ma
    sotto ``/~/+/``: un percorso assoluto uscirebbe da quel prefisso e il
    proxy risponderebbe con l'HTML dell'app - stato 200, tipo text/html - che
    il browser disegna come immagine rotta. Le pagine hanno un percorso di un
    solo segmento, quindi la forma relativa si risolve bene da ognuna.
    """
    (cartella / "como.png").write_bytes(b"x")
    (cartella / "serie-a.svg").write_bytes(b"<svg/>")

    assert crests.crest_url("Como") == "app/static/loghi/como.png"
    assert not crests.crest_url("Como").startswith("/")
    assert not crests.league_logo_url().startswith("/")


def test_stemma_mancante(cartella):
    assert crests.crest_url("Inter") is None
    assert crests.crest_img("Inter") == ""


def test_cartella_assente(tmp_path, monkeypatch):
    monkeypatch.setattr(crests, "CRESTS_DIR", tmp_path / "non_esiste")
    crests._index.cache_clear()
    assert crests.crest_url("Como") is None
    crests._index.cache_clear()


def test_nome_normalizzato(cartella):
    """Spazi, accenti e maiuscole spariscono dal nome del file."""
    (cartella / "hellasverona.png").write_bytes(b"x")
    assert crests.crest_url("Hellas Verona") is not None
    assert crests.crest_url("HELLAS VERONA") is not None


def test_svg_preferito_al_png(cartella):
    (cartella / "como.png").write_bytes(b"x")
    (cartella / "como.svg").write_bytes(b"<svg/>")
    assert crests.crest_url("Como").endswith(".svg")


def test_estensioni_ignote_scartate(cartella):
    (cartella / "como.txt").write_bytes(b"x")
    assert crests.crest_url("Como") is None


def test_tag_img_con_dimensione(cartella):
    (cartella / "como.png").write_bytes(b"x")
    img = crests.crest_img("Como", size=40)
    assert 'src="app/static/loghi/como.png"' in img
    assert "height:40px" in img and "width:40px" in img


def test_alt_sanificato(cartella):
    (cartella / "comoquot.png").write_bytes(b"x")
    img = crests.crest_img('Como" onerror="x')
    assert "onerror=" not in img or "&quot;" in img


def test_logo_della_lega(cartella):
    (cartella / "serie-a.svg").write_bytes(b"<svg/>")
    assert crests.league_logo_url() == "app/static/loghi/serie-a.svg"


def test_logo_della_lega_assente(cartella):
    assert crests.league_logo_url() is None


def test_gli_stemmi_veri_ci_sono_tutti(real_listone):
    """Regressione: se qualcuno cancella o rinomina un file, si vede qui."""
    crests._index.cache_clear()
    mancanti = sorted({p.team for p in real_listone.players if crests.crest_url(p.team) is None})
    assert mancanti == []
    assert crests.league_logo_url() is not None


def test_tutte_le_squadre_del_listone_hanno_un_nome_file_valido(real_listone):
    """Il nome atteso non deve mai essere vuoto o ambiguo."""
    from asta.domain.models import sort_key

    attesi = {sort_key(p.team).lower() for p in real_listone.players}
    assert "" not in attesi
    assert len(attesi) == len({p.team for p in real_listone.players})

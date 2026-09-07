"""La demo pubblica: dati inventati e un'asta che riparte da sola.

Sono i test che girano **sempre**, anche in una copia senza nessun dato: il
generatore si fabbrica il suo listone da zero, ed e' esattamente il motivo per
cui esiste. Se questi cadono, la vetrina pubblica mostra un'app rotta a
chiunque passi.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import streamlit as st
from scripts.genera_demo import PARTECIPANTI, SQUADRE, genera
from streamlit.testing.v1 import AppTest

from asta.data.keepers import load_keeper_grid
from asta.data.players import load_listone
from asta.domain.export import restore_events
from asta.domain.letters import current_player
from asta.domain.models import Role
from asta.domain.reducer import build_state
from asta.ui import wiring
from asta.ui.upload import controlla_griglia


@pytest.fixture(scope="module")
def demo(tmp_path_factory) -> Path:
    """Una demo generata una volta sola per tutto il modulo."""
    destinazione = tmp_path_factory.mktemp("demo")
    genera(destinazione)
    return destinazione


@pytest.fixture(scope="module")
def stato(demo: Path):
    listone = load_listone(demo / "players_2026_27.json")
    eventi = restore_events((demo / "demo_eventi.json").read_text(encoding="utf-8"))
    return listone, eventi, build_state(listone, eventi)


# ------------------------------------------------------------------- il listone


def test_il_listone_finto_si_legge_come_quello_vero(stato):
    """Passa dal lettore di produzione, non da uno finto per l'occasione."""
    listone, _, _ = stato

    assert len(listone.players) == len(SQUADRE) * 24
    assert {p.team for p in listone.players} == set(SQUADRE)
    assert len({p.id for p in listone.players}) == len(listone.players)


def test_ogni_pagina_trova_qualcosa_da_mostrare(demo: Path, stato):
    """Una demo dove meta' delle sezioni sono vuote non e' una demo."""
    listone, _, _ = stato
    payload = json.loads((demo / "players_2026_27.json").read_text(encoding="utf-8"))

    assert len(payload["lineups"]) == len(SQUADRE), "pagina Formazioni"
    assert len(payload["keepers"]) == len(SQUADRE), "pagina Portieri"
    assert payload["tiers"]["A"], "colonna Fascia nel listone"
    assert any(p.set_pieces for p in listone.players), "rigoristi e piazzati"
    assert any(p.injury for p in listone.players), "ambulanza degli infortunati"
    assert any(p.starter for p in listone.players), "titolarita'"


def test_i_portieri_non_hanno_fasce(stato):
    """Come nel listone vero: per loro c'e' la pagina delle gerarchie."""
    listone, _, _ = stato

    assert not any(p.tier for p in listone.by_role(Role.P))
    assert all(p.tier for p in listone.by_role(Role.A))


def test_chi_costa_di_piu_e_anche_il_titolare(stato):
    """Le fonti finte devono concordare fra loro, o la demo sembra sbagliata."""
    listone, _, _ = stato
    for squadra in SQUADRE:
        attaccanti = sorted(
            (p for p in listone.by_role(Role.A) if p.team == squadra),
            key=lambda p: -p.quotation,
        )
        assert attaccanti[0].starter is not None, squadra
        assert attaccanti[0].quotation >= attaccanti[-1].quotation


# -------------------------------------------------------------------- la griglia


def test_la_griglia_della_demo_supera_il_controllo_del_caricamento(demo: Path):
    """Lo stesso controllo di simmetria che vedrebbe un admin caricandola."""
    contenuto = (demo / "griglia_portieri_2026_27.json").read_bytes()

    assert controlla_griglia(contenuto) == []
    assert load_keeper_grid(demo / "griglia_portieri_2026_27.json").teams == tuple(SQUADRE)


# --------------------------------------------------------------------- l'asta


def test_l_asta_di_esempio_e_a_meta_con_un_calciatore_in_asta(stato):
    """Chi apre la demo deve trovare il riquadro pieno, non un'attesa."""
    _, _, state = stato

    assert state.started and not state.closed
    assert state.current_role is Role.D, "i portieri finiti, i difensori in corso"
    assert current_player(state) is not None


def test_le_rose_rispettano_i_limiti_di_ruolo(stato):
    """Il log passa da ``validate_assignment``, quindi non puo' essere illegale."""
    _, _, state = stato
    assert set(state.teams) == set(PARTECIPANTI)
    for squadra in state.teams.values():
        assert squadra.count(Role.P) == 3, "la fase dei portieri e' chiusa"
        assert squadra.slots_left(Role.D) >= 0
        assert squadra.credits_left > 0


def test_c_e_anche_un_evento_annullato(stato):
    """L'undo non cancella: la demo lo fa vedere."""
    _, eventi, _ = stato
    assert any(not e.active for e in eventi)


# ---------------------------------------------------------------- il generatore


def test_lo_stesso_seme_da_gli_stessi_file(demo: Path, tmp_path: Path):
    """Rigenerare non deve sporcare il diff di ottanta righe."""
    altra = tmp_path / "altra"
    genera(altra)

    for nome in ("players_2026_27.json", "griglia_portieri_2026_27.json"):
        assert (altra / nome).read_bytes() == (demo / nome).read_bytes(), nome


def test_le_date_dell_asta_finta_sono_fisse(demo: Path, tmp_path: Path):
    """Prese dall'orologio, cambierebbero a ogni rigenerazione."""
    altra = tmp_path / "orologio"
    genera(altra)

    def quando(cartella: Path) -> list[str]:
        backup = json.loads((cartella / "demo_eventi.json").read_text(encoding="utf-8"))
        return [e["created_at"] for e in backup["events"]]

    assert quando(altra) == quando(demo)


def test_non_sovrascrive_niente_senza_permesso(tmp_path: Path):
    """La protezione che conta: lanciarlo su ``data/`` non deve cancellare il listone vero."""
    (tmp_path / "players_2026_27.json").write_text("il listone vero", encoding="utf-8")

    with pytest.raises(FileExistsError, match="esiste gia'"):
        genera(tmp_path)

    assert (tmp_path / "players_2026_27.json").read_text(encoding="utf-8") == "il listone vero"
    assert not (tmp_path / "demo_eventi.json").exists(), "non deve scrivere niente a meta'"


# ------------------------------------------------------------------- la semina


@pytest.fixture
def senza_cache():
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


def test_senza_database_la_demo_riparte_dall_asta_di_esempio(demo: Path, monkeypatch, senza_cache):
    """Il log in memoria nasce vuoto a ogni riavvio: qui viene seminato."""
    monkeypatch.setattr(wiring, "DEMO_EVENTI", demo / "demo_eventi.json")
    monkeypatch.setattr(wiring.config, "database_url", lambda: "")

    repo = wiring.get_repository()

    assert len(repo.load()) > 20
    assert repo.version()[0] > 0


def test_senza_file_di_esempio_si_parte_da_vuoto(tmp_path: Path, monkeypatch, senza_cache):
    """Il caso normale: chi installa l'app non ha nessuna demo da seminare."""
    monkeypatch.setattr(wiring, "DEMO_EVENTI", tmp_path / "non-esiste.json")
    monkeypatch.setattr(wiring.config, "database_url", lambda: "")

    assert wiring.get_repository().load() == []


def test_un_file_di_esempio_rovinato_non_fa_cadere_l_app(tmp_path: Path, monkeypatch, senza_cache):
    """Meglio un'asta vuota che una pagina che non si apre."""
    rovinato = tmp_path / "demo_eventi.json"
    rovinato.write_text("{ meta", encoding="utf-8")
    monkeypatch.setattr(wiring, "DEMO_EVENTI", rovinato)
    monkeypatch.setattr(wiring.config, "database_url", lambda: "")

    assert wiring.get_repository().load() == []


# ------------------------------------------------------------------- l'avviso


def test_l_avviso_dei_secrets_compare_in_cima(monkeypatch):
    """La riga che dice "e' finta": senza, resta solo il README, che non legge nessuno."""
    monkeypatch.setattr(wiring.config, "avviso", lambda: "Listone di fantasia.")
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=60)
    at.run()

    assert not at.exception
    assert any("Listone di fantasia." in i.value for i in at.info)


def test_senza_avviso_non_si_occupa_spazio(monkeypatch):
    monkeypatch.setattr(wiring.config, "avviso", lambda: "")
    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=60)
    at.run()

    assert not at.exception
    assert not any("fantasia" in i.value for i in at.info)

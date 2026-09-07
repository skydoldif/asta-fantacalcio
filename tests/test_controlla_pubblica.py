"""Il controllo da fare prima di pubblicare.

I test costruiscono repo git vere e ci committano dentro il guaio da trovare:
un controllo di sicurezza che non si prova su un caso sbagliato davvero non
serve a niente, perche' il giorno che serve nessuno se ne accorge.

Il caso che conta e' l'ultimo: un file **cancellato** resta nella storia, e
resta scaricabile da chiunque cloni. E' l'errore che non si vede guardando la
cartella, ed e' l'unico motivo per cui questo script esiste.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from scripts.controlla_pubblica import (
    buchi_nel_gitignore,
    controlla,
    file_di_altri,
    listoni_veri,
    perche_non_va_pubblicato,
)
from scripts.genera_demo import genera

LISTONE_VERO = {"source": "Quotazioni_Fantacalcio_Stagione_2026_27.xlsx", "count": 533}

#: Tutto quello che una repo pubblica puo' avere senza problemi.
GITIGNORE = """\
.streamlit/secrets.toml
data/raw/*.xlsx
data/raw/*.md
data/raw/*.png
data/players_*.json
data/griglia_*.json
static/loghi/*
!static/loghi/README.md
static/audio/*
!static/audio/README.md
"""


def _git(repo: Path, *argomenti: str) -> None:
    subprocess.run(["git", "-C", str(repo), *argomenti], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Una repo pubblica a posto: solo codice e un .gitignore che copre tutto."""
    cartella = tmp_path / "pubblica"
    cartella.mkdir()
    _git(cartella, "init", "-q", "-b", "main")
    _git(cartella, "config", "user.email", "prova@example.com")
    _git(cartella, "config", "user.name", "Prova")
    (cartella / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    (cartella / "app.py").write_text("print('ciao')\n", encoding="utf-8")
    _git(cartella, "add", "-A")
    _git(cartella, "commit", "-qm", "Il codice")
    return cartella


def _committa(repo: Path, percorso: str, contenuto: str, messaggio: str) -> None:
    """Aggiunge un file **forzando** il .gitignore, come farebbe una distrazione."""
    file = repo / percorso
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(contenuto, encoding="utf-8")
    _git(repo, "add", "-f", percorso)
    _git(repo, "commit", "-qm", messaggio)


# ------------------------------------------------------- riconoscere i file


@pytest.mark.parametrize(
    "percorso",
    [
        ".streamlit/secrets.toml",
        "data/raw/Quotazioni_Fantacalcio_Stagione_2026_27.xlsx",
        "data/raw/attaccanti.md",
        "data/raw/griglia_portieri_2026_27.png",
        "static/loghi/inter.svg",
        "static/audio/amici/gino-lava-la-gina.m4a",
    ],
)
def test_i_file_di_altri_si_riconoscono_dal_nome(percorso: str):
    assert perche_non_va_pubblicato(percorso) is not None, percorso


@pytest.mark.parametrize(
    "percorso",
    [
        "app.py",
        "README.md",
        "static/loghi/README.md",
        "static/audio/README.md",
        "data/raw/esempio_rosters.csv",
        "data/demo_eventi.json",
        "src/asta/domain/models.py",
    ],
)
def test_quello_che_e_nostro_passa(percorso: str):
    """L'elenco e' di cose da non pubblicare: tutto il resto deve passare."""
    assert perche_non_va_pubblicato(percorso) is None, percorso


# ------------------------------------------------------------- sulla repo


def test_una_repo_di_solo_codice_e_pulita(repo: Path):
    assert file_di_altri(repo) == []
    assert listoni_veri(repo) == ([], 0)
    assert buchi_nel_gitignore(repo) == []
    assert controlla(repo) == []


def test_il_listone_di_fantasia_puo_stare_nella_repo(repo: Path):
    """Sul branch della demo ci sta: e' il motivo per cui esiste il generatore."""
    genera(repo / "data")
    _git(repo, "add", "-f", "data")
    _git(repo, "commit", "-qm", "I dati della demo")

    problemi, controllate = listoni_veri(repo)

    assert problemi == []
    assert controllate == 2, "il listone e la griglia"
    assert controlla(repo) == []


def test_il_listone_vero_viene_beccato(repo: Path):
    _committa(repo, "data/players_2026_27.json", json.dumps(LISTONE_VERO), "Oops")

    problemi, _ = listoni_veri(repo)

    assert [p for p, _ in problemi] == ["data/players_2026_27.json"]
    assert controlla(repo)


def test_un_json_illeggibile_si_considera_vero(repo: Path):
    """Nel dubbio si blocca: e' l'errore giusto da fare, qui."""
    _committa(repo, "data/players_2026_27.json", "{ meta", "Oops")

    problemi, _ = listoni_veri(repo)

    assert problemi and "non si riesce a leggerlo" in problemi[0][1]


def test_un_xlsx_committato_viene_beccato(repo: Path):
    _committa(repo, "data/raw/Quotazioni_2026_27.xlsx", "PK finto", "Oops")

    assert [p for p, _ in file_di_altri(repo)] == ["data/raw/Quotazioni_2026_27.xlsx"]


def test_i_secrets_vengono_beccati_e_il_contenuto_non_si_stampa(repo: Path, capsys):
    """Un controllo che stampa la password che ha trovato e' peggio del guaio."""
    _committa(repo, ".streamlit/secrets.toml", 'admin_password = "segretissima"', "Oops")

    controlla(repo)
    uscita = capsys.readouterr().out

    assert "secrets.toml" in uscita
    assert "segretissima" not in uscita


# ------------------------------------------------- il caso che conta davvero


def test_un_file_cancellato_resta_nella_storia_e_viene_beccato(repo: Path):
    """L'errore che non si vede guardando la cartella.

    Chi clona scarica **tutti** i commit, non l'ultimo: togliere il file e
    committare non lo toglie da nessuna copia. E' l'unico motivo per cui
    questo script guarda ``--objects --all`` invece di fare un ``ls``.
    """
    _committa(repo, "data/raw/attaccanti.md", "l'articolo intero", "Oops")
    _git(repo, "rm", "-q", "data/raw/attaccanti.md")
    _git(repo, "commit", "-qm", "Tolto, credo")

    assert not (repo / "data/raw/attaccanti.md").exists(), "sparito dalla cartella"
    assert [p for p, _ in file_di_altri(repo)] == ["data/raw/attaccanti.md"], "ma non dalla storia"


def test_guarda_anche_i_branch_non_attivi(repo: Path):
    """La demo vive su un branch suo: un guaio li' e' un guaio pubblicato uguale."""
    _git(repo, "switch", "-q", "-c", "demo")
    _committa(repo, "static/loghi/inter.svg", "<svg/>", "Stemmi sulla demo")
    _git(repo, "switch", "-q", "main")

    assert [p for p, _ in file_di_altri(repo)] == ["static/loghi/inter.svg"]


def test_un_gitignore_bucato_si_vede_prima_del_danno(repo: Path):
    """Non guarda la storia ma il futuro: il prossimo `git add -A`."""
    (repo / ".gitignore").write_text("# niente\n", encoding="utf-8")

    scoperti = buchi_nel_gitignore(repo)

    assert ".streamlit/secrets.toml" in scoperti
    assert "static/loghi/inter.svg" in scoperti

"""Grida se nella repo pubblica e' finito qualcosa che non e' nostro.

    python scripts/controlla_pubblica.py ../fantacalcio-asta-pubblica

Da lanciare **prima** di rendere pubblica una repo, o di pubblicarne una nuova
versione. Il punto e' che ``git`` non dimentica: un file cancellato con un
commit resta scaricabile da chi clona, e accorgersene dopo vuol dire riscrivere
la storia e invalidare ogni copia gia' fatta. Un minuto adesso ne risparmia
un'ora dopo.

Guarda **ogni oggetto mai committato su ogni branch**, non solo lo stato
attuale, e controlla quattro cose:

1. che non ci sia nessun file che non e' nostro - gli Excel di fantacalcio.it,
   gli articoli, gli stemmi (marchi dei club), gli audio (voci di persone vere);
2. che non ci sia nessun ``secrets.toml``, mai;
3. che i listoni committati siano **quelli di fantasia** e non quello vero: sul
   branch della demo un ``data/players_*.json`` ci sta, ma solo se dentro ci
   sono i calciatori inventati da ``genera_demo.py``;
4. che il ``.gitignore`` copra ancora quello che deve, cosi' il prossimo
   ``git add -A`` non ci ricasca.

Non stampa mai il **contenuto** di niente: di un file trovato dice il percorso
e il commit, che e' quanto basta per andarlo a togliere.

Sulla repo privata fallisce di proposito, e non e' un guasto: li' i dati veri
ci stanno, ed e' per questo che quella repo non si pubblica.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.genera_demo import MARCA  # noqa: E402

#: Estensioni degli audio e delle immagini, per riconoscerli dal nome.
AUDIO = {".mp3", ".m4a", ".wav", ".ogg", ".opus"}
IMMAGINI = {".svg", ".png", ".webp", ".jpg", ".jpeg"}

#: Quanti file elencare prima di troncare. Un elenco di cinquanta righe non
#: si legge, e per capire che la repo non va pubblicata ne bastano poche.
PRIMI = 12

#: File di esempio su cui provare il .gitignore, uno per categoria.
#:
#: Non devono esistere: ``git check-ignore`` ragiona sul percorso, non sul
#: disco. Servono a chiedere "se domani ci finisse un file cosi', te ne
#: accorgeresti?".
ESEMPI_DA_IGNORARE = (
    ".streamlit/secrets.toml",
    "data/raw/Quotazioni_Fantacalcio_Stagione_2026_27.xlsx",
    "data/raw/attaccanti.md",
    "static/loghi/inter.svg",
    "static/audio/calcio/esempio.mp3",
)


def perche_non_va_pubblicato(percorso: str) -> str | None:
    """Perche' questo file non puo' stare in una repo pubblica, o ``None``."""
    p = PurePosixPath(percorso)
    suffisso = p.suffix.lower()
    if p.name == "secrets.toml":
        return "e' il file dei secrets: dentro ci sono admin_password e database_url"
    if suffisso in {".xlsx", ".xls"}:
        return "e' un Excel di fantacalcio.it (listone o statistiche)"
    if percorso.startswith("data/raw/") and suffisso == ".md":
        return "e' un articolo, di chi l'ha scritto"
    if percorso.startswith("data/raw/") and suffisso in IMMAGINI:
        return "e' l'immagine da cui si trascrive la griglia"
    if percorso.startswith("static/loghi/") and suffisso in IMMAGINI:
        return "e' uno stemma, e gli stemmi sono marchi dei club"
    if percorso.startswith("static/audio/") and suffisso in AUDIO:
        return "e' un audio della Soundbar: sono voci di persone vere"
    return None


def e_un_listone(percorso: str) -> bool:
    """True per i JSON che possono contenere dati di fantacalcio.it."""
    return percorso.endswith(".json") and (
        percorso.startswith("data/players_") or percorso.startswith("data/griglia_")
    )


def _git(repo: Path, *argomenti: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *argomenti],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def oggetti(repo: Path) -> list[tuple[str, str]]:
    """Ogni file mai committato su ogni branch: ``(sha, percorso)``.

    ``--objects --all`` guarda la storia intera, non lo stato attuale: e'
    tutta la differenza fra questo controllo e un ``ls``.
    """
    trovati = []
    for riga in _git(repo, "rev-list", "--objects", "--all").splitlines():
        sha, _, percorso = riga.partition(" ")
        if percorso:
            trovati.append((sha, percorso))
    return trovati


def dove_appare(repo: Path, percorso: str) -> str:
    """Il commit piu' recente che tocca quel file, per andarlo a cercare."""
    uscita = _git(repo, "log", "--all", "-1", "--format=%h %s", "--", percorso).strip()
    return uscita or "(commit ignoto)"


# ------------------------------------------------------------------ i controlli


def file_di_altri(repo: Path) -> list[tuple[str, str]]:
    """File che non sono nostri da pubblicare, in qualunque commit.

    Uno per **percorso**, non per versione: un file modificato dieci volte e'
    un problema solo, e ripeterlo dieci volte nasconderebbe gli altri.
    """
    problemi: dict[str, str] = {}
    for _, percorso in oggetti(repo):
        motivo = perche_non_va_pubblicato(percorso)
        if motivo:
            problemi[percorso] = motivo
    return sorted(problemi.items())


def listoni_veri(repo: Path) -> tuple[list[tuple[str, str]], int]:
    """Listoni e griglie committati che **non** sono di fantasia.

    Il segnale e' il campo ``source``, che ``genera_demo.py`` marca. Un file
    senza quella parola si considera vero, cioe' da non pubblicare: nel dubbio
    e' l'errore giusto da fare.

    Guarda **ogni versione** di ogni file - basta un commit vecchio col
    listone vero perche' resti scaricabile - ma ne riporta una per percorso,
    che e' il file da togliere.

    Returns:
        I problemi come ``(percorso, cosa c'era scritto in source)``, e quante
        versioni sono state aperte in tutto.
    """
    problemi: dict[str, str] = {}
    controllate = 0
    for sha, percorso in sorted(set(oggetti(repo))):
        if not e_un_listone(percorso):
            continue
        controllate += 1
        try:
            payload = json.loads(_git(repo, "cat-file", "blob", sha))
            sorgente = str(payload.get("source", ""))
        except (subprocess.CalledProcessError, ValueError):
            problemi.setdefault(percorso, "non si riesce a leggerlo, quindi non si sa cos'e'")
            continue
        if MARCA not in sorgente.lower():
            problemi.setdefault(percorso, f"source: {sorgente!r}")
    return sorted(problemi.items()), controllate


def buchi_nel_gitignore(repo: Path) -> list[str]:
    """Percorsi che il ``.gitignore`` dovrebbe coprire e non copre.

    Non guarda la storia ma il futuro: sono i file che il prossimo
    ``git add -A`` si porterebbe dentro senza che nessuno se ne accorga.
    """
    scoperti = []
    for esempio in ESEMPI_DA_IGNORARE:
        ignorato = subprocess.run(
            ["git", "-C", str(repo), "check-ignore", "-q", esempio],
            capture_output=True,
        )
        if ignorato.returncode != 0:
            scoperti.append(esempio)
    return scoperti


# -------------------------------------------------------------------- il report


def controlla(repo: Path) -> list[str]:
    """Esegue i quattro controlli e stampa il resoconto. Torna i problemi."""
    branch = [r for r in _git(repo, "branch", "--format=%(refname:short)").splitlines() if r]
    commit = _git(repo, "rev-list", "--all", "--count").strip()
    print(f"Controllo {repo.name}: {commit} commit su {len(branch)} branch ({', '.join(branch)}).")
    print()

    problemi: list[str] = []

    altrui = file_di_altri(repo)
    if altrui:
        problemi += [f"{percorso}: {motivo}" for percorso, motivo in altrui]
        print(f"  ❌ {len(altrui)} file che non sono tuoi da pubblicare:")
        for percorso, motivo in altrui[:PRIMI]:
            print(f"      {percorso}")
            print(f"        {motivo}, visto in {dove_appare(repo, percorso)}")
        if len(altrui) > PRIMI:
            print(f"      ...e altri {len(altrui) - PRIMI}.")
    else:
        print("  ✅ Nessun file di altri, in nessun commit")

    veri, controllate = listoni_veri(repo)
    if veri:
        problemi += [f"{percorso}: {dettaglio}" for percorso, dettaglio in veri]
        print(f"  ❌ {len(veri)} listoni che non sono di fantasia:")
        for percorso, dettaglio in veri[:PRIMI]:
            print(f"      {percorso}")
            print(f"        {dettaglio}, visto in {dove_appare(repo, percorso)}")
        if len(veri) > PRIMI:
            print(f"      ...e altri {len(veri) - PRIMI}.")
    elif controllate:
        print(f"  ✅ Le {controllate} versioni di listone committate sono tutte di fantasia")
    else:
        print("  ✅ Nessun listone committato")

    buchi = buchi_nel_gitignore(repo)
    if buchi:
        problemi += [f"il .gitignore non copre {b}" for b in buchi]
        print("  ❌ Il .gitignore ha dei buchi, il prossimo `git add -A` ci ricasca:")
        for esempio in buchi:
            print(f"      {esempio}")
    else:
        print("  ✅ Il .gitignore copre dati, media e secrets")

    print()
    if problemi:
        print("NON pubblicare cosi'. Un file cancellato con un commit resta comunque")
        print("scaricabile da chi clona: va tolto dalla storia, non dall'ultima versione.")
    else:
        print("Si puo' pubblicare.")
    return problemi


def main(argv: list[str] | None = None) -> int:
    argomenti = argv if argv is not None else sys.argv[1:]
    if len(argomenti) > 1:
        print(__doc__)
        return 2

    repo = Path(argomenti[0] if argomenti else ROOT).expanduser().resolve()
    if not (repo / ".git").is_dir():
        print(f"{repo} non sembra una repo git.")
        return 2
    try:
        return 1 if controlla(repo) else 0
    except subprocess.CalledProcessError as exc:
        print(f"git si e' lamentato: {exc.stderr or exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Stemmi delle squadre di Serie A.

Gli stemmi sono file in ``static/loghi/``, serviti da Streamlit come file
statici e quindi messi in cache dal browser: nell'HTML resta solo un ``<img>``
di poche decine di byte. E' la ragione per cui non sono incorporati come data
URI: il tabellone viene rispedito al browser a ogni cambiamento, e portarsi
dietro le immagini a ogni giro costerebbe rete dati a tutti gli spettatori.

Il nome del file e' il nome della squadra normalizzato (``sort_key`` in
minuscolo), cosi' "Hellas Verona" diventa ``hellasverona.png``. Se il file
manca non viene disegnato nulla: il nome della squadra e' comunque scritto
accanto.

Gli URL sono **relativi** (``app/static/...``, senza barra iniziale). In locale
l'app sta sulla radice e le due forme si equivalgono, ma su Streamlit Community
Cloud vive sotto ``/~/+/``: un percorso assoluto uscirebbe da quel prefisso e
il proxy risponderebbe con l'HTML dell'app - stato 200, tipo ``text/html`` -
che il browser mostra come immagine rotta. Le pagine hanno tutte un percorso di
un solo segmento (``/listone``, ``/admin``), quindi la forma relativa si
risolve correttamente da ognuna.
"""

from __future__ import annotations

from functools import lru_cache
from html import escape
from pathlib import Path

from asta.domain.models import sort_key

#: Cartella degli stemmi, servita da Streamlit sotto ``app/static/``.
CRESTS_DIR = Path(__file__).resolve().parents[3] / "static" / "loghi"

#: Estensioni riconosciute, in ordine di preferenza a parita' di nome.
SUPPORTED = (".svg", ".png", ".webp", ".jpg", ".jpeg")

#: Logo della lega. Non e' una squadra: si richiede per nome, non dall'indice.
LEAGUE_LOGO = "serie-a.svg"


@lru_cache(maxsize=1)
def _index() -> dict[str, str]:
    """Mappa ``nome normalizzato -> nome del file``.

    Letta una volta sola: gli stemmi sono file committati nella repo e non
    cambiano mentre l'app gira.
    """
    if not CRESTS_DIR.is_dir():
        return {}
    trovati: dict[str, str] = {}
    for estensione in SUPPORTED:
        for percorso in sorted(CRESTS_DIR.glob(f"*{estensione}")):
            trovati.setdefault(percorso.stem.lower(), percorso.name)
    return trovati


def crest_url(team: str) -> str | None:
    """URL dello stemma di una squadra, oppure ``None`` se non c'e' il file.

    Relativo, per la ragione spiegata in cima al modulo: su Streamlit Cloud
    l'app non sta sulla radice del dominio.
    """
    nome = _index().get(sort_key(team).lower())
    return f"app/static/loghi/{nome}" if nome else None


def crest_img(team: str, size: int = 28) -> str:
    """Tag ``<img>`` dello stemma, o stringa vuota se lo stemma manca.

    Args:
        team: nome della squadra di Serie A.
        size: lato dell'immagine in pixel.
    """
    url = crest_url(team)
    if url is None:
        return ""
    return (
        f'<img src="{url}" alt="{escape(team)}" '
        f'style="height:{size}px;width:{size}px;object-fit:contain;'
        f'vertical-align:middle;margin-right:7px">'
    )


def league_logo_url() -> str | None:
    """URL del logo della lega, o ``None`` se il file non c'e'."""
    if not (CRESTS_DIR / LEAGUE_LOGO).is_file():
        return None
    return f"app/static/loghi/{LEAGUE_LOGO}"

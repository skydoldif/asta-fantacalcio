"""Dati dei portieri: gerarchie di squadra e griglia delle coppie.

Le gerarchie arrivano dallo stesso JSON del listone, generato da
``scripts/build_players.py`` a partire dall'articolo in ``data/raw/``.

La griglia no: e' un'immagine, e i suoi numeri sono stati **trascritti a mano**
in ``data/griglia_portieri_2026_27.json``. La trascrizione si controlla da
sola, perche' la griglia e' simmetrica: ``test_keepers.py`` verifica che ogni
valore combaci col suo speculare, e un numero letto male lo farebbe cadere.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from asta.data.players import DEFAULT_PLAYERS_PATH
from asta.domain.models import KeeperGrid, KeeperRank

#: Percorso di default della griglia, relativo alla radice della repo.
DEFAULT_GRID_PATH = Path(__file__).resolve().parents[3] / "data" / "griglia_portieri_2026_27.json"


def load_keepers(path: Path | None = None) -> tuple[KeeperRank, ...]:
    """Legge le gerarchie in porta dal JSON del listone.

    Sono facoltative: senza l'articolo in ``data/raw/`` il JSON non le contiene
    e la pagina lo dice, invece di rompersi.
    """
    target = path or DEFAULT_PLAYERS_PATH
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        return tuple(KeeperRank.from_payload(g) for g in raw.get("keepers") or ())
    except (OSError, KeyError, TypeError, ValueError):
        return ()


def load_keeper_grid(path: Path | None = None) -> KeeperGrid:
    """Legge la griglia delle coppie di portieri.

    Restituisce una griglia vuota se il file manca o non si legge: la pagina
    mostra comunque le gerarchie, che sono la parte che serve all'asta.
    """
    target = path or DEFAULT_GRID_PATH
    try:
        return KeeperGrid.from_payload(json.loads(target.read_text(encoding="utf-8")))
    except (OSError, KeyError, TypeError, ValueError):
        return KeeperGrid()


@lru_cache(maxsize=4)
def cached_keepers(path: str | None = None) -> tuple[KeeperRank, ...]:
    """Versione memoizzata di :func:`load_keepers`."""
    return load_keepers(Path(path) if path else None)


def conceded_by_team(path: str | None = None) -> dict[str, int]:
    """Gol subiti l'anno scorso, per squadra di Serie A.

    Le neopromosse non ci sono: in Serie A non hanno giocato. Chi ordina con
    questi numeri le mette in fondo invece di dar loro uno zero, che le
    farebbe sembrare le difese migliori del campionato.
    """
    return {rank.team: rank.conceded for rank in cached_keepers(path) if rank.conceded is not None}


@lru_cache(maxsize=4)
def cached_keeper_grid(path: str | None = None) -> KeeperGrid:
    """Versione memoizzata di :func:`load_keeper_grid`."""
    return load_keeper_grid(Path(path) if path else None)

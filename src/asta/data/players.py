"""Caricamento del listone dal JSON generato da ``scripts/build_players.py``."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from asta.domain.models import (
    Injury,
    Listone,
    Player,
    PlayerStats,
    Role,
    SetPieces,
    Starting,
    TeamLineup,
    Tier,
)

#: Percorso di default del listone, relativo alla radice della repo.
DEFAULT_PLAYERS_PATH = Path(__file__).resolve().parents[3] / "data" / "players_2026_27.json"


def load_listone(path: Path | None = None) -> Listone:
    """Legge il listone da disco.

    Args:
        path: percorso del JSON; se omesso usa :data:`DEFAULT_PLAYERS_PATH`.

    Returns:
        Il listone completo, ordinato per ruolo e nome.

    Raises:
        FileNotFoundError: se il file non esiste (va rigenerato con
            ``python scripts/build_players.py``).
        ValueError: se il contenuto non ha la struttura attesa.
    """
    target = path or DEFAULT_PLAYERS_PATH
    if not target.exists():
        raise FileNotFoundError(
            f"Listone non trovato in {target}. Rigeneralo con:\n  python scripts/build_players.py"
        )
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        players = tuple(
            Player(
                id=int(p["id"]),
                role=Role(p["role"]),
                name=str(p["name"]),
                team=str(p["team"]),
                quotation=int(p.get("quotation", 0)),
                fvm=int(p.get("fvm", 0)),
                stats=PlayerStats.from_payload(p["stats"]) if p.get("stats") else None,
                set_pieces=(
                    SetPieces.from_payload(p["set_pieces"]) if p.get("set_pieces") else None
                ),
                starter=Starting(p["starter"]) if p.get("starter") else None,
                injury=Injury.from_payload(p["injury"]) if p.get("injury") else None,
                tier=(Tier.from_payload(p["tier"], p.get("tier_rank")) if p.get("tier") else None),
            )
            for p in raw["players"]
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Listone malformato in {target}: {exc}") from exc

    ids = [p.id for p in players]
    if len(ids) != len(set(ids)):
        raise ValueError("Il listone contiene Id duplicati")
    return Listone(players=players)


def listone_source(path: Path | None = None) -> str:
    """Nome dell'Excel da cui e' stato generato il listone (vuoto se ignoto).

    Serve solo a mostrare in Admin da quale file arrivano i calciatori: e' il
    controllo di un secondo prima di far partire l'asta.
    """
    target = path or DEFAULT_PLAYERS_PATH
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        return str(raw.get("source", ""))
    except (OSError, ValueError):
        return ""


def stats_season(path: Path | None = None) -> str:
    """Stagione delle statistiche in formato ``2025/26``, vuota se assenti.

    Si ricava dal nome del file sorgente registrato nel JSON, cosi' l'etichetta
    mostrata in app segue il file senza doverla aggiornare a mano.
    """
    target = path or DEFAULT_PLAYERS_PATH
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        source = str(raw.get("stats_source", ""))
    except (OSError, ValueError):
        return ""
    match = re.search(r"(\d{4})[_-](\d{2})", source)
    return f"{match.group(1)}/{match.group(2)}" if match else ""


def load_tiers(path: Path | None = None) -> dict[Role, tuple[str, ...]]:
    """Le fasce di ogni reparto, in ordine di graduatoria.

    Servono al menu del filtro nel listone: l'ordine e' quello dell'articolo,
    non quello alfabetico.
    """
    target = path or DEFAULT_PLAYERS_PATH
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        return {
            Role(ruolo): tuple(str(f) for f in fasce)
            for ruolo, fasce in (raw.get("tiers") or {}).items()
        }
    except (OSError, KeyError, TypeError, ValueError):
        return {}


def load_lineups(path: Path | None = None) -> tuple[TeamLineup, ...]:
    """Legge le probabili formazioni dallo stesso JSON del listone.

    Sono facoltative: senza l'articolo in ``data/raw/`` il JSON non le contiene
    e la pagina delle formazioni lo dice, invece di rompersi.
    """
    target = path or DEFAULT_PLAYERS_PATH
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        return tuple(TeamLineup.from_payload(t) for t in raw.get("lineups") or ())
    except (OSError, KeyError, TypeError, ValueError):
        return ()


@lru_cache(maxsize=4)
def cached_listone(path: str | None = None) -> Listone:
    """Versione memoizzata di :func:`load_listone` (il listone non cambia mai)."""
    return load_listone(Path(path) if path else None)


@lru_cache(maxsize=4)
def cached_tiers(path: str | None = None) -> dict[Role, tuple[str, ...]]:
    """Versione memoizzata di :func:`load_tiers`."""
    return load_tiers(Path(path) if path else None)


@lru_cache(maxsize=4)
def cached_stats_season(path: str | None = None) -> str:
    """Versione memoizzata di :func:`stats_season`.

    Listone e portieri la chiamano a ogni aggiornamento automatico: senza
    memoizzazione ogni spettatore rileggerebbe e ricostruirebbe il JSON del
    listone solo per ricavarne il nome di una stagione.
    """
    return stats_season(Path(path) if path else None)


@lru_cache(maxsize=4)
def cached_lineups(path: str | None = None) -> tuple[TeamLineup, ...]:
    """Versione memoizzata di :func:`load_lineups`.

    La pagina delle formazioni si rinfresca da sola ogni dieci secondi: senza
    memoizzazione rileggerebbe e ricostruirebbe il JSON a ogni giro, per ogni
    spettatore collegato.
    """
    return load_lineups(Path(path) if path else None)

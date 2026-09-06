"""Export delle rose nel formato accettato da fantacalcio.it.

Il file d'esempio fornito dalla lega ha questa forma esatta::

    $,$,$
    Dildersbrough,6884,0
    Dildersbrough,5585,0

cioe' una prima riga letterale ``$,$,$`` seguita da righe
``nome_squadra,id_giocatore,crediti_spesi``, in UTF-8 senza BOM e con
terminatori di riga LF.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from asta.domain.events import Event
from asta.domain.models import ROLE_ORDER
from asta.domain.reducer import AuctionState

#: Prima riga del CSV, richiesta dall'importatore di fantacalcio.it.
CSV_HEADER = "$,$,$"
#: Terminatore di riga: LF, come nel file d'esempio.
LINE_TERMINATOR = "\n"


def rosters_csv(state: AuctionState) -> str:
    """Genera il CSV di tutte le rose.

    Le squadre seguono l'ordine di configurazione e, al loro interno, i
    calciatori sono ordinati per ruolo (P, D, C, A) e poi alfabeticamente:
    l'importatore non ne tiene conto, ma rende il file leggibile a occhio.

    Args:
        state: stato dell'asta (anche a meta' asta).

    Returns:
        Il contenuto del file, gia' terminato da un a capo.
    """
    settings = state.settings
    lines = [CSV_HEADER]
    if settings is None:
        return LINE_TERMINATOR.join(lines) + LINE_TERMINATOR

    by_id = state.listone.by_id
    role_rank = {role: i for i, role in enumerate(ROLE_ORDER)}
    for name in settings.teams:
        team = state.teams.get(name)
        if team is None:
            continue
        rows = sorted(
            team.assignments,
            key=lambda a: (role_rank.get(a.role, 99), by_id[a.player_id].key),
        )
        lines.extend(f"{name},{a.player_id},{a.price}" for a in rows)
    return LINE_TERMINATOR.join(lines) + LINE_TERMINATOR


def export_filename(prefix: str = "rose_asta", extension: str = "csv") -> str:
    """Nome file con timestamp, per non sovrascrivere export precedenti."""
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{stamp}.{extension}"


def backup_json(events: list[Event]) -> str:
    """Serializza l'intero log eventi.

    E' la rete di sicurezza dell'asta: da questo file si ricostruisce lo stato
    esatto, compresi gli eventi annullati con l'undo.
    """
    payload = {
        "version": 1,
        "exported_at": datetime.now(UTC).isoformat(),
        "events": [e.to_dict() for e in sorted(events, key=lambda e: e.seq)],
    }
    return json.dumps(payload, ensure_ascii=False, indent=1) + "\n"


def restore_events(raw: str) -> list[Event]:
    """Ricostruisce il log eventi da un backup prodotto da :func:`backup_json`.

    Raises:
        ValueError: se il file non e' un backup valido.
    """
    try:
        data = json.loads(raw)
        return [Event.from_dict(item) for item in data["events"]]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Backup non valido: {exc}") from exc

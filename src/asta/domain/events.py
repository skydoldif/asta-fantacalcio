"""Eventi dell'asta.

L'asta e' un log append-only: ogni azione dell'admin diventa un evento, e lo
stato si ottiene ripiegando il log. L'undo non cancella nulla, disattiva
l'ultimo evento attivo (``active = False``); il redo lo riattiva.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    """Tipi di evento ammessi nel log."""

    #: Impostazioni dell'asta; e' sempre il primo evento.
    AUCTION_CONFIGURED = "AUCTION_CONFIGURED"
    #: Inizio della fase di un ruolo; azzera lettere estratte e salti.
    ROLE_PHASE_STARTED = "ROLE_PHASE_STARTED"
    #: Lettera estratta (o riaperta manualmente) per il ruolo in corso.
    LETTER_DRAWN = "LETTER_DRAWN"
    #: Calciatore chiamato in modalita libera.
    PLAYER_NOMINATED = "PLAYER_NOMINATED"
    #: Calciatore aggiudicato a una squadra.
    PLAYER_ASSIGNED = "PLAYER_ASSIGNED"
    #: Calciatore saltato: resta disponibile nel listone.
    PLAYER_SKIPPED = "PLAYER_SKIPPED"
    #: Correzione di un'aggiudicazione gia' registrata.
    ASSIGNMENT_UPDATED = "ASSIGNMENT_UPDATED"
    #: Annullamento di un'aggiudicazione gia' registrata.
    ASSIGNMENT_REMOVED = "ASSIGNMENT_REMOVED"
    #: Asta dichiarata conclusa.
    AUCTION_CLOSED = "AUCTION_CLOSED"


#: Descrizioni brevi mostrate nel log operazioni dell'admin.
EVENT_LABEL: dict[EventType, str] = {
    EventType.AUCTION_CONFIGURED: "Asta configurata",
    EventType.ROLE_PHASE_STARTED: "Inizio fase",
    EventType.LETTER_DRAWN: "Lettera estratta",
    EventType.PLAYER_NOMINATED: "Calciatore chiamato",
    EventType.PLAYER_ASSIGNED: "Aggiudicato",
    EventType.PLAYER_SKIPPED: "Saltato",
    EventType.ASSIGNMENT_UPDATED: "Aggiudicazione corretta",
    EventType.ASSIGNMENT_REMOVED: "Aggiudicazione annullata",
    EventType.AUCTION_CLOSED: "Asta chiusa",
}


@dataclass(frozen=True, slots=True)
class Event:
    """Un evento del log.

    Attributes:
        seq: Numero progressivo, unico per asta. E' anche l'identita' a cui si
            riferiscono ``ASSIGNMENT_UPDATED`` e ``ASSIGNMENT_REMOVED``.
        type: Tipo di evento.
        payload: Dati specifici del tipo, serializzabili in JSON.
        active: ``False`` se annullato con l'undo. Gli eventi inattivi restano
            nel log per poter fare redo e per l'audit.
        created_at: Momento in cui l'evento e' stato creato.
    """

    seq: int
    type: EventType
    payload: dict[str, Any] = field(default_factory=dict)
    active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def deactivated(self) -> Event:
        """Copia dell'evento marcata come annullata."""
        return replace(self, active=False)

    def reactivated(self) -> Event:
        """Copia dell'evento marcata come di nuovo valida."""
        return replace(self, active=True)

    def to_dict(self) -> dict[str, Any]:
        """Forma serializzabile (usata dal backup JSON)."""
        return {
            "seq": self.seq,
            "type": self.type.value,
            "payload": self.payload,
            "active": self.active,
            "created_at": self.created_at.isoformat(),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Event:
        """Inverso di :meth:`to_dict`."""
        raw_date = data.get("created_at")
        created = (
            datetime.fromisoformat(raw_date)
            if isinstance(raw_date, str)
            else raw_date or datetime.now(UTC)
        )
        return Event(
            seq=int(data["seq"]),
            type=EventType(data["type"]),
            payload=dict(data.get("payload") or {}),
            active=bool(data.get("active", True)),
            created_at=created,
        )


def next_seq(events: list[Event]) -> int:
    """Prossimo ``seq`` libero (gli eventi inattivi occupano comunque il posto)."""
    return max((e.seq for e in events), default=0) + 1


def undoable(events: list[Event]) -> Event | None:
    """Ultimo evento annullabile, oppure ``None``.

    La configurazione dell'asta non e' annullabile: si modifica dalla pagina
    Impostazioni finche' l'asta non e' iniziata.
    """
    for event in sorted(events, key=lambda e: e.seq, reverse=True):
        if event.active and event.type != EventType.AUCTION_CONFIGURED:
            return event
    return None


def redoable(events: list[Event]) -> Event | None:
    """Evento ripristinabile con il redo, oppure ``None``.

    E' l'ultimo evento del log solo se e' inattivo: qualsiasi nuova operazione
    registrata dopo un undo invalida la coda di redo.
    """
    if not events:
        return None
    last = max(events, key=lambda e: e.seq)
    return None if last.active else last

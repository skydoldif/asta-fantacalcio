"""Orchestrazione fra UI, log eventi e persistenza.

Il servizio applica ogni azione *ottimisticamente* in memoria e accoda la
scrittura sul database. Se la rete cade a meta' asta l'admin continua a
lavorare: le operazioni in sospeso vengono ritentate a ogni interazione e con
il pulsante "Sincronizza". Lo scrittore e' uno solo (l'admin), quindi non
esistono conflitti da risolvere: la chiave primaria ``(auction_id, seq)``
rende innocuo anche un retry duplicato.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from asta.data.repository import AuctionRepository
from asta.domain.events import Event, EventType, next_seq, redoable, undoable
from asta.domain.models import Listone
from asta.domain.reducer import AuctionState, build_state


@dataclass(frozen=True, slots=True)
class PendingOp:
    """Scrittura non ancora confermata dal database."""

    #: ``"append"`` per un nuovo evento, ``"active"`` per un undo/redo.
    kind: str
    event: Event | None = None
    seq: int | None = None
    active: bool = True


@dataclass
class AuctionService:
    """Stato dell'asta lato admin, con sincronizzazione tollerante ai guasti."""

    repo: AuctionRepository
    listone: Listone
    events: list[Event] = field(default_factory=list)
    pending: list[PendingOp] = field(default_factory=list)
    #: Ultimo errore di sincronizzazione, gia' pronto per il banner.
    error: str | None = None
    loaded: bool = False

    # ------------------------------------------------------------------ lettura

    def state(self) -> AuctionState:
        """Stato corrente derivato dal log locale."""
        return build_state(self.listone, self.events)

    @property
    def synced(self) -> bool:
        """True se non ci sono scritture in sospeso."""
        return not self.pending

    def bootstrap(self) -> None:
        """Carica il log dal database al primo utilizzo."""
        if not self.loaded:
            self.reload()

    def reload(self) -> bool:
        """Ricarica il log dal database.

        Non fa nulla se ci sono scritture in sospeso: la verita' piu' aggiornata
        e' quella locale, e sovrascriverla perderebbe le operazioni in coda.

        Returns:
            True se il log e' stato effettivamente ricaricato.
        """
        if self.pending:
            return False
        try:
            self.events = self.repo.load()
            self.loaded = True
            self.error = None
            return True
        except Exception as exc:
            self.error = f"Database non raggiungibile: {exc}"
            return False

    # ------------------------------------------------------------------ scrittura

    def record(self, event_type: EventType, payload: dict[str, Any] | None = None) -> Event:
        """Registra un nuovo evento: subito in locale, poi verso il database.

        Args:
            event_type: tipo di evento.
            payload: dati dell'evento (devono essere serializzabili in JSON).

        Returns:
            L'evento appena creato, con il suo ``seq``.
        """
        event = Event(seq=next_seq(self.events), type=event_type, payload=dict(payload or {}))
        self.events.append(event)
        self.pending.append(PendingOp(kind="append", event=event))
        self.flush()
        return event

    def undo(self) -> Event | None:
        """Annulla l'ultima operazione annullabile.

        Returns:
            L'evento annullato, oppure ``None`` se non c'era nulla da annullare.
        """
        target = undoable(self.events)
        if target is None:
            return None
        self._set_active(target.seq, False)
        return target

    def redo(self) -> Event | None:
        """Ripristina l'ultima operazione annullata.

        Returns:
            L'evento ripristinato, oppure ``None`` se il redo non e' possibile.
        """
        target = redoable(self.events)
        if target is None:
            return None
        self._set_active(target.seq, True)
        return target

    @property
    def can_undo(self) -> bool:
        return undoable(self.events) is not None

    @property
    def can_redo(self) -> bool:
        return redoable(self.events) is not None

    def _set_active(self, seq: int, active: bool) -> None:
        self.events = [
            (e.reactivated() if active else e.deactivated()) if e.seq == seq else e
            for e in self.events
        ]
        self.pending.append(PendingOp(kind="active", seq=seq, active=active))
        self.flush()

    # ------------------------------------------------------------------ sincronizzazione

    def flush(self) -> bool:
        """Prova a scaricare la coda sul database.

        Le operazioni vengono applicate in ordine e rimosse dalla coda solo se
        vanno a buon fine; al primo errore ci si ferma e si riprova dopo.

        Returns:
            True se la coda e' vuota al termine.
        """
        while self.pending:
            op = self.pending[0]
            try:
                if op.kind == "append" and op.event is not None:
                    self.repo.append(op.event)
                elif op.kind == "active" and op.seq is not None:
                    self.repo.set_active(op.seq, op.active)
            except Exception as exc:
                self.error = f"Sincronizzazione non riuscita: {exc}"
                return False
            self.pending.pop(0)
        self.error = None
        return True

    # ------------------------------------------------------------------ manutenzione

    def reset(self) -> None:
        """Cancella l'asta e riparte da zero."""
        self.repo.reset()
        self.events = []
        self.pending = []
        self.error = None
        self.loaded = True

    def restore(self, events: list[Event]) -> None:
        """Sostituisce il log con quello di un backup."""
        self.repo.replace_all(events)
        self.events = sorted(events, key=lambda e: e.seq)
        self.pending = []
        self.error = None
        self.loaded = True

"""Riduzione del log eventi nello stato corrente dell'asta.

:func:`build_state` e' una funzione pura: stessi eventi, stesso stato. E' il
cuore dell'app, e da questo dipendono undo/redo, correzioni, vista utente ed
export senza alcun codice dedicato.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from asta.domain.events import Event, EventType
from asta.domain.models import (
    Assignment,
    Listone,
    Player,
    Role,
    Settings,
    TeamState,
)


@dataclass
class AuctionState:
    """Fotografia dell'asta ricostruita dal log eventi."""

    listone: Listone
    settings: Settings | None = None
    #: Aggiudicazioni valide, indicizzate per ``seq`` dell'evento che le ha create.
    assignments: dict[int, Assignment] = field(default_factory=dict)
    #: Ruolo la cui fase e' in corso.
    current_role: Role | None = None
    #: Lettere gia' estratte nella fase corrente (azzerate al cambio ruolo).
    drawn_letters: tuple[str, ...] = ()
    #: Lettera attualmente in scorrimento.
    current_letter: str | None = None
    #: Calciatori saltati nella fase corrente: restano nel listone ma non
    #: vengono ripresentati nella stessa passata di lettera.
    skipped: frozenset[int] = frozenset()
    #: Calciatore chiamato in modalita libera e non ancora risolto.
    nominated: int | None = None
    closed: bool = False
    #: Ultimo ``seq`` presente nel log. E' contabilita' del log, non stato
    #: dell'asta: due stati identici raggiunti per strade diverse (per
    #: esempio prima e dopo un undo) devono risultare uguali.
    last_seq: int = field(default=0, compare=False)
    #: Squadre, nell'ordine di configurazione.
    teams: dict[str, TeamState] = field(default_factory=dict)
    #: Id dei calciatori gia' aggiudicati.
    taken: frozenset[int] = frozenset()

    @property
    def started(self) -> bool:
        """True se l'asta e' configurata."""
        return self.settings is not None

    @property
    def has_activity(self) -> bool:
        """True se e' gia' successo qualcosa oltre alla configurazione.

        Finche' e' False le impostazioni sono ancora modificabili.
        """
        return bool(self.assignments) or self.current_role is not None

    def team(self, name: str) -> TeamState:
        """Stato di una squadra.

        Raises:
            KeyError: se la squadra non e' fra quelle configurate.
        """
        return self.teams[name]

    def is_taken(self, player_id: int) -> bool:
        """True se il calciatore e' gia' stato aggiudicato."""
        return player_id in self.taken

    def assignment_of(self, player_id: int) -> Assignment | None:
        """Aggiudicazione di un calciatore, se esiste."""
        for a in self.assignments.values():
            if a.player_id == player_id:
                return a
        return None

    def available(self, role: Role | None = None) -> tuple[Player, ...]:
        """Calciatori ancora disponibili, in ordine alfabetico.

        Args:
            role: se indicato, filtra su quel ruolo.
        """
        pool = self.listone.by_role(role) if role else self.listone.players
        return tuple(p for p in pool if p.id not in self.taken)

    def sold(self) -> tuple[tuple[Assignment, Player], ...]:
        """Aggiudicazioni in ordine cronologico, con il relativo calciatore."""
        by_id = self.listone.by_id
        return tuple(
            (a, by_id[a.player_id])
            for a in sorted(self.assignments.values(), key=lambda a: a.event_seq)
        )

    def incomplete_teams(self) -> tuple[str, ...]:
        """Squadre con la rosa non ancora completa."""
        return tuple(name for name, t in self.teams.items() if not t.is_complete)


def _rebuild_teams(settings: Settings, assignments: dict[int, Assignment]) -> dict[str, TeamState]:
    """Ricostruisce le squadre a partire dalle aggiudicazioni valide."""
    grouped: dict[str, list[Assignment]] = {name: [] for name in settings.teams}
    for assignment in sorted(assignments.values(), key=lambda a: a.event_seq):
        # Un'aggiudicazione verso una squadra sconosciuta puo' esistere solo se
        # le impostazioni sono state alterate a mano: la si ignora anziche'
        # far crollare l'asta in corso.
        grouped.setdefault(assignment.team, []).append(assignment)
    return {
        name: TeamState(name=name, settings=settings, assignments=tuple(items))
        for name, items in grouped.items()
    }


def build_state(listone: Listone, events: list[Event]) -> AuctionState:
    """Ripiega il log eventi nello stato corrente.

    Gli eventi disattivati dall'undo vengono ignorati; l'ordine e' quello dei
    ``seq`` crescenti, indipendentemente da come arrivano dal database.

    Args:
        listone: il listone completo dei calciatori.
        events: log eventi, anche non ordinato.

    Returns:
        Lo stato derivato, con squadre e disponibilita' gia' calcolate.
    """
    state = AuctionState(listone=listone)
    by_id = listone.by_id

    ordered = sorted(events, key=lambda e: e.seq)
    state.last_seq = max((e.seq for e in ordered), default=0)

    for event in ordered:
        if not event.active:
            continue
        payload = event.payload
        match event.type:
            case EventType.AUCTION_CONFIGURED:
                state.settings = Settings.from_payload(payload)

            case EventType.ROLE_PHASE_STARTED:
                state.current_role = Role(payload["role"])
                state.drawn_letters = ()
                state.current_letter = None
                state.skipped = frozenset()
                state.nominated = None

            case EventType.LETTER_DRAWN:
                letter = str(payload["letter"])
                state.current_letter = letter
                if letter not in state.drawn_letters:
                    state.drawn_letters = (*state.drawn_letters, letter)
                if payload.get("reopen"):
                    # Riapertura manuale: i salti su quella lettera decadono.
                    state.skipped = frozenset(
                        pid
                        for pid in state.skipped
                        if pid in by_id and by_id[pid].initial != letter
                    )
                state.nominated = None

            case EventType.PLAYER_NOMINATED:
                state.nominated = int(payload["player_id"])

            case EventType.PLAYER_ASSIGNED:
                player_id = int(payload["player_id"])
                player = by_id.get(player_id)
                if player is None:
                    continue
                state.assignments[event.seq] = Assignment(
                    event_seq=event.seq,
                    player_id=player_id,
                    team=str(payload["team"]),
                    price=int(payload["price"]),
                    role=player.role,
                )
                state.skipped -= {player_id}
                state.nominated = None

            case EventType.PLAYER_SKIPPED:
                state.skipped |= {int(payload["player_id"])}
                state.nominated = None

            case EventType.ASSIGNMENT_UPDATED:
                target = int(payload["target_seq"])
                existing = state.assignments.get(target)
                if existing is not None:
                    state.assignments[target] = replace(
                        existing,
                        team=str(payload.get("team", existing.team)),
                        price=int(payload.get("price", existing.price)),
                    )

            case EventType.ASSIGNMENT_REMOVED:
                state.assignments.pop(int(payload["target_seq"]), None)

            case EventType.AUCTION_CLOSED:
                state.closed = True

    state.taken = frozenset(a.player_id for a in state.assignments.values())
    if state.settings is not None:
        state.teams = _rebuild_teams(state.settings, state.assignments)
    return state

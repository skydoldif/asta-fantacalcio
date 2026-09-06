"""Regole di validazione dell'asta.

Ogni inserimento passa da :func:`validate_assignment`, che restituisce ``None``
se l'operazione e' lecita oppure una :class:`Rejection` con un messaggio gia'
pronto da mostrare in italiano all'admin.
"""

from __future__ import annotations

from dataclasses import dataclass

from asta.domain.models import (
    MIN_PRICE,
    ROLE_LABEL,
    ROLE_ORDER,
    Assignment,
    Listone,
    Player,
    Role,
    Settings,
    TeamState,
)
from asta.domain.reducer import AuctionState


@dataclass(frozen=True, slots=True)
class Rejection:
    """Motivo per cui un'operazione non e' ammessa."""

    code: str
    message: str


def team_state_without(state: AuctionState, team_name: str, ignore_seq: int | None) -> TeamState:
    """Stato di una squadra come se una data aggiudicazione non esistesse.

    Serve per validare una *correzione*: quando si sposta un calciatore o se ne
    cambia il prezzo, i crediti e gli slot gia' occupati da quella stessa
    aggiudicazione non devono contare contro il nuovo valore.
    """
    settings = state.settings
    assert settings is not None, "asta non configurata"
    current = state.teams.get(team_name)
    assignments: tuple[Assignment, ...] = current.assignments if current else ()
    if ignore_seq is not None:
        assignments = tuple(a for a in assignments if a.event_seq != ignore_seq)
    return TeamState(name=team_name, settings=settings, assignments=assignments)


def max_bid(state: AuctionState, team_name: str, ignore_seq: int | None = None) -> int:
    """Offerta massima ammessa per una squadra, riservando 1 credito per slot."""
    return team_state_without(state, team_name, ignore_seq).max_bid


def validate_assignment(
    state: AuctionState,
    player: Player,
    team_name: str,
    price: int,
    ignore_seq: int | None = None,
) -> Rejection | None:
    """Verifica che un calciatore possa essere aggiudicato a una squadra.

    Controlli, nell'ordine in cui conviene mostrarli all'admin:

    1. asta configurata e squadra esistente;
    2. il ruolo del calciatore coincide con la fase in corso;
    3. il calciatore non e' gia' stato aggiudicato a qualcun altro;
    4. la squadra ha slot liberi nel reparto e in rosa;
    5. il prezzo e' almeno ``MIN_PRICE``;
    6. il prezzo non supera l'offerta massima (crediti residui meno 1 credito
       riservato per ogni altro slot ancora da riempire).

    Args:
        state: stato corrente dell'asta.
        player: calciatore da aggiudicare.
        team_name: squadra acquirente.
        price: prezzo di aggiudicazione.
        ignore_seq: ``seq`` di un'aggiudicazione da ignorare nel calcolo,
            usato quando si sta correggendo quella stessa aggiudicazione.

    Returns:
        ``None`` se l'operazione e' lecita, altrimenti la :class:`Rejection`
        con il motivo del rifiuto.
    """
    settings = state.settings
    if settings is None:
        return Rejection("not_configured", "L'asta non e' ancora stata configurata.")
    if team_name not in state.teams:
        return Rejection("unknown_team", f"Squadra sconosciuta: {team_name}.")

    if (
        state.current_role is not None
        and settings.active_role_only
        and player.role != state.current_role
    ):
        return Rejection(
            "wrong_role",
            f"{player.name} e' un {player.role.value}: "
            f"e' in corso l'asta dei {ROLE_LABEL[state.current_role].lower()}.",
        )

    existing = state.assignment_of(player.id)
    if existing is not None and existing.event_seq != ignore_seq:
        return Rejection(
            "already_sold",
            f"{player.name} e' gia' stato aggiudicato a {existing.team} "
            f"per {existing.price} crediti.",
        )

    team = team_state_without(state, team_name, ignore_seq)

    if team.roster_slots_left <= 0:
        return Rejection(
            "roster_full",
            f"{team_name} ha gia' la rosa completa ({settings.roster_size} calciatori).",
        )
    if team.slots_left(player.role) <= 0:
        return Rejection(
            "role_full",
            f"{team_name} ha gia' {settings.limit(player.role)} {ROLE_LABEL[player.role].lower()}.",
        )
    if price < MIN_PRICE:
        return Rejection("price_too_low", f"Il prezzo minimo e' {MIN_PRICE} credito.")

    if price > team.credits_left:
        return Rejection(
            "no_credits",
            f"{team_name} ha solo {team.credits_left} crediti residui.",
        )
    if price > team.max_bid:
        return Rejection(
            "reserve",
            f"{team_name} puo' offrire al massimo {team.max_bid}: "
            f"ha {team.credits_left} crediti e {team.roster_slots_left} slot da riempire "
            f"(serve 1 credito per ciascuno).",
        )
    return None


def blocking_reason(
    state: AuctionState, player: Player, team_name: str, ignore_seq: int | None = None
) -> str | None:
    """Motivo per cui una squadra non puo' *in nessun caso* prendere il calciatore.

    A differenza di :func:`validate_assignment` non guarda il prezzo: serve a
    disabilitare la squadra nel selettore dell'admin spiegando il perche'.
    """
    rejection = validate_assignment(state, player, team_name, MIN_PRICE, ignore_seq)
    return rejection.message if rejection else None


def validate_settings(settings: Settings, listone: Listone) -> list[str]:
    """Controlla la coerenza delle impostazioni d'asta.

    Returns:
        Lista di errori in italiano; vuota se le impostazioni sono valide.
    """
    errors: list[str] = []
    names = [t.strip() for t in settings.teams]

    if len(names) < 2:
        errors.append("Servono almeno 2 squadre.")
    if any(not n for n in names):
        errors.append("Ogni squadra deve avere un nome.")
    lowered = [n.lower() for n in names if n]
    duplicates = sorted({n for n in lowered if lowered.count(n) > 1})
    if duplicates:
        errors.append("Nomi di squadra duplicati: " + ", ".join(duplicates) + ".")
    if any("," in n or "\n" in n for n in names):
        errors.append(
            "I nomi delle squadre non possono contenere virgole o a capo "
            "(romperebbero il CSV per fantacalcio.it)."
        )

    if settings.credits < settings.roster_size:
        errors.append(
            f"Con {settings.credits} crediti non si riesce a comprare "
            f"{settings.roster_size} calciatori (serve almeno 1 credito ciascuno)."
        )
    if settings.roster_size < 1:
        errors.append("La rosa deve contenere almeno 1 calciatore.")

    total = sum(settings.limit(r) for r in ROLE_ORDER)
    if total != settings.roster_size:
        errors.append(
            f"La somma dei limiti per ruolo e' {total} ma la rosa e' di "
            f"{settings.roster_size} calciatori."
        )
    for role in ROLE_ORDER:
        if settings.limit(role) < 0:
            errors.append(f"Il limite dei {ROLE_LABEL[role].lower()} non puo' essere negativo.")

    # Il listone deve bastare per tutte le squadre, altrimenti l'asta si
    # incaglia a meta' dell'ultimo reparto.
    for role in ROLE_ORDER:
        needed = settings.limit(role) * len(names)
        available = len(listone.by_role(role))
        if needed > available:
            errors.append(
                f"Servono {needed} {ROLE_LABEL[role].lower()} ma il listone ne ha {available}: "
                f"riduci il limite o il numero di squadre."
            )
    return errors


def role_progress(state: AuctionState, role: Role) -> tuple[int, int]:
    """Avanzamento di una fase: ``(slot riempiti, slot totali)``."""
    settings = state.settings
    if settings is None:
        return (0, 0)
    filled = sum(1 for a in state.assignments.values() if a.role == role)
    return (filled, settings.limit(role) * len(settings.teams))


def next_role(current: Role | None) -> Role | None:
    """Ruolo successivo nell'ordine P, D, C, A. ``None`` se l'asta e' finita."""
    if current is None:
        return ROLE_ORDER[0]
    index = ROLE_ORDER.index(current)
    return ROLE_ORDER[index + 1] if index + 1 < len(ROLE_ORDER) else None

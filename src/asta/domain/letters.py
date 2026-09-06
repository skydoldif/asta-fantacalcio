"""Modalita "lettera random": sorteggio e scorrimento alfabetico.

Regole implementate:

* si estrae solo fra le lettere che hanno ancora *almeno un calciatore
  disponibile* nel ruolo in asta, cosi' a fine fase non escono lettere vuote;
* una lettera gia' uscita non viene riestratta;
* l'elenco delle lettere uscite si azzera al cambio di ruolo (gestito dal
  reducer sull'evento ``ROLE_PHASE_STARTED``);
* i calciatori della lettera scorrono in ordine alfabetico; chi viene saltato
  resta nel listone ma non viene ripresentato nella stessa passata.
"""

from __future__ import annotations

import random

from asta.domain.models import Player, Role
from asta.domain.reducer import AuctionState


def available_initials(state: AuctionState, role: Role) -> set[str]:
    """Iniziali che hanno ancora almeno un calciatore disponibile nel ruolo."""
    return {p.initial for p in state.available(role)}


def eligible_letters(state: AuctionState) -> tuple[str, ...]:
    """Lettere ancora estraibili nella fase corrente, in ordine alfabetico."""
    if state.current_role is None:
        return ()
    already = set(state.drawn_letters)
    return tuple(sorted(available_initials(state, state.current_role) - already))


def draw_letter(state: AuctionState, seed: int | None = None) -> tuple[str, int] | None:
    """Estrae una lettera fra quelle ammissibili.

    Args:
        state: stato corrente.
        seed: seme del generatore. Se ``None`` ne viene creato uno casuale.
            Viene restituito e salvato nell'evento, cosi' il replay del log
            riproduce esattamente la stessa estrazione.

    Returns:
        La coppia ``(lettera, seme)``, oppure ``None`` se non ci sono piu'
        lettere con calciatori disponibili (la fase e' finita).
    """
    candidates = eligible_letters(state)
    if not candidates:
        return None
    if seed is None:
        seed = random.SystemRandom().randrange(2**31)
    letter = random.Random(seed).choice(list(candidates))
    return letter, seed


def letter_queue(state: AuctionState, letter: str | None = None) -> tuple[Player, ...]:
    """Calciatori ancora da chiamare per una lettera, in ordine alfabetico.

    Esclude chi e' gia' stato aggiudicato e chi e' stato saltato nella fase
    corrente. I saltati restano comunque disponibili nel listone e possono
    essere ripresi con :func:`asta.domain.letters.reopenable` o in chiamata
    libera.
    """
    target = letter or state.current_letter
    if target is None or state.current_role is None:
        return ()
    return tuple(
        p
        for p in state.available(state.current_role)
        if p.initial == target and p.id not in state.skipped
    )


def upcoming(state: AuctionState) -> tuple[Player, ...]:
    """I prossimi della lettera in corso, escluso quello in asta adesso.

    E' la coda alfabetica meno la testa, ma il calciatore in asta puo' non
    essere in testa - dopo una chiamata manuale puo' essere di un'altra
    lettera, o non essere in coda affatto - quindi si toglie per Id invece
    che per posizione.

    In chiamata libera non c'e' nessuna lettera in corso e la coda e' vuota:
    la funzione restituisce ``()`` da sola, senza bisogno di controllare la
    modalita' dell'asta.
    """
    corrente = current_player(state)
    return tuple(p for p in letter_queue(state) if corrente is None or p.id != corrente.id)


def skipped_in_letter(state: AuctionState, letter: str | None = None) -> tuple[Player, ...]:
    """Calciatori saltati in una lettera, ancora liberi e recuperabili."""
    target = letter or state.current_letter
    if target is None or state.current_role is None:
        return ()
    return tuple(
        p
        for p in state.available(state.current_role)
        if p.initial == target and p.id in state.skipped
    )


def current_player(state: AuctionState) -> Player | None:
    """Calciatore attualmente in asta.

    In modalita lettera e' il primo della coda; in chiamata libera e' quello
    chiamato dall'admin e non ancora risolto.
    """
    if state.nominated is not None and not state.is_taken(state.nominated):
        return state.listone.by_id.get(state.nominated)
    queue = letter_queue(state)
    return queue[0] if queue else None


def letter_exhausted(state: AuctionState) -> bool:
    """True se la lettera corrente non ha piu' calciatori da chiamare."""
    return state.current_letter is not None and not letter_queue(state)


def phase_exhausted(state: AuctionState) -> bool:
    """True se nel ruolo in corso non ci sono piu' lettere ne' calciatori."""
    return not eligible_letters(state) and not letter_queue(state)

"""Probabili formazioni: chi scenderebbe in campo, e chi e' gia' stato preso.

Una card per club - con il modulo accanto al nome - i reparti nell'ordine
in cui li scrive l'articolo (dal portiere all'attacco) e i ballottaggi
affiancati nello stesso posto. Chi e'
gia' stato aggiudicato resta scritto - serve riconoscerlo - ma sbiadito e
barrato: quello che si cerca guardando questa pagina e' chi e' ancora libero.

I club sono in fila per gol subiti l'anno scorso, come nella pagina dei
portieri e nella copertura del tabellone: la stessa fila nelle tre pagine si
impara una volta sola, e chi cerca un difensore parte da dove ha senso partire.

L'HTML si costruisce con funzioni pure (``lineups_html``), cosi' si puo'
verificare senza far girare Streamlit.
"""

from __future__ import annotations

from collections.abc import Mapping
from html import escape

import streamlit as st

from asta.data.keepers import conceded_by_team
from asta.domain.models import STARTING_LABEL, LineupSpot, Starting, TeamLineup
from asta.domain.reducer import AuctionState
from asta.ui.crests import crest_url

_CSS = """
<style>
.pf{display:grid;gap:10px;grid-template-columns:repeat(auto-fill,minmax(250px,1fr))}
.pf-card{border:1px solid rgba(128,128,128,.35);border-radius:8px;padding:8px 10px}
.pf-head{display:flex;align-items:center;gap:6px;margin-bottom:6px}
.pf-head img{height:22px;width:22px;object-fit:contain}
.pf-club{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.03em}
.pf-mod{margin-left:auto;font-size:11px;font-weight:700;opacity:.55;
  font-variant-numeric:tabular-nums;white-space:nowrap}
.pf-unit{display:flex;flex-wrap:wrap;gap:4px;padding:3px 0;
  border-top:1px solid rgba(128,128,128,.18)}
.pf-unit:first-of-type{border-top:none}
.pf-slot{display:inline-flex;align-items:center;gap:3px;font-size:12px;line-height:1.35}
.pf-slot+.pf-slot::before{content:"·";opacity:.35;margin-right:2px}
.pf-name{white-space:nowrap}
.pf-name.t{color:#4ade80}
.pf-name.b{color:#facc15}
.pf-name.taken{opacity:.34;text-decoration:line-through;color:inherit}
.pf-vs{opacity:.4;font-size:11px}
.pf-empty{opacity:.6;font-size:13px}
</style>
"""


def _spot_html(spot: LineupSpot, state: AuctionState, contested: bool) -> str:
    """Un nome della formazione, con lo stato che ha nell'asta.

    Il nome mostrato e' quello del listone quando il calciatore si aggancia:
    e' quello che l'admin chiama a voce e che compare in tutte le altre
    pagine. Se non si aggancia resta il nome dell'articolo, senza colore: di
    lui non sappiamo nemmeno se e' astabile.
    """
    if spot.player_id is None:
        return f'<span class="pf-name">{escape(spot.name)}</span>'

    try:
        player = state.listone.get(spot.player_id)
    except KeyError:
        return f'<span class="pf-name">{escape(spot.name)}</span>'

    classe = "b" if contested else "t"
    titolo = STARTING_LABEL[Starting.CONTESTED if contested else Starting.STARTER]
    assegnazione = state.assignment_of(player.id)
    if assegnazione is not None:
        classe = "taken"
        titolo = f"Preso da {assegnazione.team} per {assegnazione.price}"
    return f'<span class="pf-name {classe}" title="{escape(titolo)}">{escape(player.name)}</span>'


def _slot_html(slot: tuple[LineupSpot, ...], state: AuctionState) -> str:
    """Un posto in campo: un nome, oppure due separati dalla barra."""
    contested = len(slot) > 1
    nomi = '<span class="pf-vs">/</span>'.join(_spot_html(spot, state, contested) for spot in slot)
    return f'<span class="pf-slot">{nomi}</span>'


def team_lineup_html(lineup: TeamLineup, state: AuctionState) -> str:
    """Card di una squadra: stemma, nome, modulo e i reparti uno sotto l'altro.

    Il modulo sta all'altro capo dell'intestazione, allineato a destra: serve
    a capire al volo quanti difensori e quante punte gioca quella squadra,
    ma non deve rubare l'occhio al nome.
    """
    url = crest_url(lineup.team)
    stemma = f'<img src="{url}" alt="">' if url else ""
    modulo = (
        f'<span class="pf-mod" title="Modulo della formazione tipo">{lineup.module}</span>'
        if lineup.module
        else ""
    )
    reparti = "".join(
        '<div class="pf-unit">' + "".join(_slot_html(slot, state) for slot in unit) + "</div>"
        for unit in lineup.units
    )
    return (
        '<div class="pf-card">'
        f'<div class="pf-head">{stemma}'
        f'<span class="pf-club">{escape(lineup.team)}</span>{modulo}</div>'
        f"{reparti}</div>"
    )


def sorted_lineups(
    lineups: tuple[TeamLineup, ...], conceded: Mapping[str, int] | None = None
) -> tuple[TeamLineup, ...]:
    """Formazioni ordinate dalla difesa meno battuta alla piu' battuta.

    E' la stessa chiave dei portieri e della copertura sul tabellone. Le
    neopromosse chiudono la fila: in Serie A non hanno giocato, e dare loro
    uno zero le farebbe sembrare le difese migliori del campionato.

    Args:
        lineups: le formazioni da ordinare.
        conceded: gol subiti per club; se omesso li legge dal listone.
    """
    subiti = dict(conceded) if conceded is not None else conceded_by_team()
    return tuple(
        sorted(
            lineups,
            key=lambda lineup: (
                lineup.team not in subiti,
                subiti.get(lineup.team, 0),
                lineup.team,
            ),
        )
    )


def lineups_html(
    lineups: tuple[TeamLineup, ...],
    state: AuctionState,
    conceded: Mapping[str, int] | None = None,
) -> str:
    """HTML di tutte le formazioni.

    Pura a meno dei gol subiti, che arrivano dal JSON committato.
    """
    if not lineups:
        return f'{_CSS}<div class="pf-empty">Nessuna formazione disponibile.</div>'
    cards = "".join(team_lineup_html(lineup, state) for lineup in sorted_lineups(lineups, conceded))
    return f'{_CSS}<div class="pf">{cards}</div>'


def lineups_board(lineups: tuple[TeamLineup, ...], state: AuctionState) -> None:
    """Disegna le formazioni nella pagina."""
    st.markdown(lineups_html(lineups, state), unsafe_allow_html=True)

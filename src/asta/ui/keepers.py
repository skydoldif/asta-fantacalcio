"""Pagina dei portieri: chi gioca, chi va comprato in coppia e la griglia.

Due blocchi. Sopra le gerarchie: per ogni squadra il titolare e basta, perche'
in diciotto squadre su venti il vice e' un credito buttato; dove invece il
posto e' in discussione compare anche il portiere da prendere per non restare
scoperti.

Sotto la griglia delle coppie: un numero per ogni incrocio fra due club, tanto
piu' alto quanto meglio i due portieri si completano. E' larga venti colonne,
quindi passando il mouse su una casella si accendono la riga e la colonna: e'
l'unico modo per non perdere l'incrocio a meta' strada. Il tutto senza una
riga di JavaScript - ``:has()`` basta e avanza - perche' ``st.markdown`` gli
script non li esegue.
"""

from __future__ import annotations

from html import escape

import streamlit as st

from asta.domain.models import KeeperGrid, KeeperRank, LineupSpot, Player, Role
from asta.domain.reducer import AuctionState
from asta.ui.crests import crest_url

_CSS = """
<style>
.gk{display:grid;gap:10px;grid-template-columns:repeat(auto-fill,minmax(215px,1fr));
  margin-bottom:6px}
.gk-card{border:1px solid rgba(128,128,128,.35);border-radius:8px;padding:8px 10px}
.gk-card.risk{border-color:rgba(250,204,21,.55);background:rgba(250,204,21,.06)}
.gk-head{display:flex;align-items:center;gap:6px;margin-bottom:5px}
.gk-head img{height:22px;width:22px;object-fit:contain}
.gk-club{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.03em}
.gk-gs{margin-left:auto;font-size:11px;font-weight:700;opacity:.55;
  font-variant-numeric:tabular-nums;white-space:nowrap}
.gk-warn{font-size:11px;font-weight:700;color:#facc15;margin-left:6px}
.gk-line{font-size:13px;line-height:1.5}
.gk-name{font-weight:600}
.gk-name.first{color:#4ade80}
.gk-name.split{color:#facc15}
.gk-name.taken{opacity:.34;text-decoration:line-through;color:inherit}
.gk-vs{opacity:.4;margin:0 3px}
.gk-also{font-size:12px;opacity:.75}
.gk-also b{color:#facc15}
.gp-para{display:flex;flex-wrap:wrap;gap:10px;margin:2px 0 6px}
.gp-p{display:flex;flex-direction:column;align-items:center;width:88px}
.gp-p-logo{position:relative;height:38px;width:38px;display:flex;align-items:center;
  justify-content:center}
.gp-p-logo img{max-height:38px;max-width:38px;object-fit:contain}
.gp-p-n{position:absolute;right:-6px;bottom:-4px;min-width:17px;height:17px;padding:0 3px;
  border-radius:9px;background:#4ade80;color:#111418;font-size:11px;font-weight:800;
  line-height:17px;text-align:center}
.gp-p-nome{margin-top:4px;font-size:11px;font-weight:600;text-align:center;line-height:1.15;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:88px}
.gp-p-nome.taken{opacity:.34;text-decoration:line-through}
.gp-p-team{font-size:10px;opacity:.55}
</style>
"""


def _name_html(spot: LineupSpot, state: AuctionState, classe: str) -> str:
    """Un portiere: verde o giallo se libero, barrato se gia' aggiudicato."""
    if spot.player_id is None:
        return f'<span class="gk-name">{escape(spot.name)}</span>'
    try:
        player = state.listone.get(spot.player_id)
    except KeyError:
        return f'<span class="gk-name">{escape(spot.name)}</span>'

    assegnazione = state.assignment_of(player.id)
    if assegnazione is not None:
        titolo = f"Preso da {assegnazione.team} per {assegnazione.price}"
        return f'<span class="gk-name taken" title="{escape(titolo)}">{escape(player.name)}</span>'
    return f'<span class="gk-name {classe}">{escape(player.name)}</span>'


def keeper_card_html(rank: KeeperRank, state: AuctionState) -> str:
    """Card di una squadra: il titolare, i gol subiti e il vice dove serve."""
    url = crest_url(rank.team)
    stemma = f'<img src="{url}" alt="">' if url else ""
    diviso = len(rank.starters) > 1
    titolari = '<span class="gk-vs">/</span>'.join(
        _name_html(spot, state, "split" if diviso else "first") for spot in rank.starters
    )
    anche = (
        f'<div class="gk-also">Prendi anche <b>{_name_html(rank.backup, state, "split")}</b></div>'
        if rank.backup is not None
        else ""
    )
    avviso = (
        f'<span class="gk-warn" title="{escape(rank.note)}">ballottaggio</span>'
        if rank.risky
        else ""
    )
    return (
        f'<div class="gk-card{" risk" if rank.risky else ""}">'
        f'<div class="gk-head">{stemma}<span class="gk-club">{escape(rank.team)}</span>'
        f"{_conceded_html(rank)}</div>"
        f'<div class="gk-line">{titolari}{avviso}</div>{anche}</div>'
    )


def _conceded_html(rank: KeeperRank) -> str:
    """Gol subiti l'anno scorso, in testa alla card. Vuoto per le neopromosse."""
    if rank.conceded is None:
        return ""
    titolo = f"Gol subiti dal {rank.team} nella stagione precedente"
    return f'<span class="gk-gs" title="{escape(titolo)}">{rank.conceded} subiti</span>'


def sorted_ranks(ranks: tuple[KeeperRank, ...]) -> tuple[KeeperRank, ...]:
    """Gerarchie ordinate dalla difesa meno battuta alla piu' battuta.

    All'asta interessa quale porta si e' presa meno gol, non che l'Atalanta
    venga prima dell'Udinese. Le neopromosse chiudono la fila: non hanno un
    numero, e inventarne uno sarebbe peggio che lasciarle in fondo.
    """
    return tuple(sorted(ranks, key=lambda r: (r.conceded is None, r.conceded or 0, r.team)))


def keepers_html(ranks: tuple[KeeperRank, ...], state: AuctionState) -> str:
    """HTML delle gerarchie in porta. Funzione pura: non disegna nulla."""
    if not ranks:
        return f'{_CSS}<div class="gk-empty">Nessuna gerarchia disponibile.</div>'
    cards = "".join(keeper_card_html(rank, state) for rank in sorted_ranks(ranks))
    return f'{_CSS}<div class="gk">{cards}</div>'


def keepers_board(ranks: tuple[KeeperRank, ...], state: AuctionState) -> None:
    """Disegna le gerarchie nella pagina."""
    st.markdown(keepers_html(ranks, state), unsafe_allow_html=True)


# --------------------------------------------------------------- la griglia

#: Colonne della griglia: la prima e' quella degli stemmi di riga.
_COLONNE = 21

_CSS_GRID = (
    """
<style>
.gp-wrap{overflow-x:auto;padding-bottom:6px}
/* La griglia occupa tutta la larghezza disponibile e divide lo spazio fra le
   colonne (table-layout:fixed), invece di fermarsi alla misura del contenuto.
   Il min-width la tiene leggibile: sotto quella soglia scorre nel suo
   contenitore invece di schiacciarsi. */
.gp{width:100%;min-width:660px;table-layout:fixed;
  border-collapse:separate;border-spacing:2px;font-size:11px}
.gp tr>*:first-child{width:34px}
.gp th,.gp td{padding:3px 4px;text-align:center;border-radius:5px;
  background:rgba(128,128,128,.07)}
.gp th img{height:20px;width:20px;object-fit:contain;display:block;margin:auto}
.gp td{font-variant-numeric:tabular-nums;color:#e6e6e6}
.gp td.hot{color:#a3e635;font-weight:700}
.gp td.self{background:transparent}
/* La riga si accende da sola, la colonna ha bisogno di :has(): niente
   JavaScript, che dentro st.markdown non verrebbe comunque eseguito. */
.gp tr:hover>*{background:rgba(255,255,255,.1)}
"""
    + "".join(
        f".gp:has(tr>*:nth-child({n}):hover) tr>*:nth-child({n})"
        "{background:rgba(255,255,255,.1)}\n"
        for n in range(1, _COLONNE + 1)
    )
    + """.gp td:hover{background:rgba(74,222,128,.32)!important;color:#fff}
</style>
"""
)


def _crest_th(team: str) -> str:
    """Intestazione con lo stemma; il nome resta nel tooltip."""
    url = crest_url(team)
    dentro = f'<img src="{url}" alt="{escape(team)}">' if url else escape(team[:3].upper())
    return f'<th title="{escape(team)}">{dentro}</th>'


def grid_html(grid: KeeperGrid) -> str:
    """La griglia delle coppie di portieri. Funzione pura: non disegna nulla."""
    if not grid.teams:
        return ""
    testa = "".join(_crest_th(team) for team in grid.teams)
    righe = []
    for i, team in enumerate(grid.teams):
        celle = []
        for j, altra in enumerate(grid.teams):
            if i == j:
                celle.append('<td class="self"></td>')
                continue
            valore = grid.value(i, j)
            classe = " hot" if valore >= grid.highlight_from > 0 else ""
            titolo = f"{team} + {altra}: {valore}"
            celle.append(f'<td class="cella{classe}" title="{escape(titolo)}">{valore}</td>')
        righe.append(f"<tr>{_crest_th(team)}{''.join(celle)}</tr>")
    return (
        f'{_CSS_GRID}<div class="gp-wrap"><table class="gp">'
        f"<tr><th></th>{testa}</tr>{''.join(righe)}</table></div>"
    )


def grid_board(grid: KeeperGrid) -> None:
    """Disegna la griglia nella pagina."""
    st.markdown(grid_html(grid), unsafe_allow_html=True)


# ------------------------------------------------------- i pararigori

#: Partite a voto sotto le quali un rigore parato non dice niente: uno su due
#: e' fortuna, uno su trenta e' una caratteristica.
MIN_PARTITE_PARARIGORI = 10


def penalty_savers(
    players: tuple[Player, ...], min_matches: int = MIN_PARTITE_PARARIGORI
) -> tuple[Player, ...]:
    """Portieri che hanno parato almeno un rigore, dal migliore in giu'.

    Si contano solo quelli con abbastanza partite alle spalle: un rigore
    parato in tre presenze e' un caso, non una dote. A parita' di rigori
    passa avanti chi ha giocato di piu'.
    """
    parate = [
        p
        for p in players
        if p.role == Role.P
        and p.stats is not None
        and p.stats.matches >= min_matches
        and p.stats.penalties_saved > 0
    ]
    return tuple(
        sorted(
            parate,
            key=lambda p: (-p.stats.penalties_saved, -p.stats.matches, p.key),  # type: ignore[union-attr]
        )
    )


def _saver_html(player: Player, state: AuctionState) -> str:
    """Una casella: stemma, quanti rigori ha parato e il nome sotto."""
    assert player.stats is not None
    url = crest_url(player.team)
    stemma = f'<img src="{url}" alt="">' if url else ""
    preso = state.assignment_of(player.id)
    quanti = player.stats.penalties_saved
    titolo = (
        f"{quanti} {'rigore parato' if quanti == 1 else 'rigori parati'} "
        f"in {player.stats.matches} partite a voto"
    )
    if preso is not None:
        titolo += f" - preso da {preso.team} per {preso.price}"
    return (
        f'<div class="gp-p" title="{escape(titolo)}">'
        f'<div class="gp-p-logo">{stemma}'
        f'<b class="gp-p-n">{quanti}</b></div>'
        f'<div class="gp-p-nome{" taken" if preso is not None else ""}">'
        f"{escape(player.name)}</div>"
        f'<div class="gp-p-team">{escape(player.team)}</div></div>'
    )


def penalty_savers_html(players: tuple[Player, ...], state: AuctionState) -> str:
    """Striscia orizzontale dei pararigori. Funzione pura: non disegna nulla."""
    parate = penalty_savers(players)
    if not parate:
        return ""
    caselle = "".join(_saver_html(p, state) for p in parate)
    return f'{_CSS}<div class="gp-para">{caselle}</div>'


def penalty_savers_board(state: AuctionState) -> None:
    """Disegna la striscia dei pararigori sotto le gerarchie."""
    html = penalty_savers_html(state.listone.players, state)
    if html:
        st.markdown(html, unsafe_allow_html=True)

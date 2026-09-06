"""Griglia delle squadre: una colonna per squadra, reparti allineati in orizzontale.

E' la vista principale sia per l'admin sia per gli spettatori. La struttura e'
una sola CSS grid in ordine "row-major" — prima tutte le card, poi tutte le
sezioni P, poi le D, e cosi' via — cosi' le barre dei reparti restano allineate
fra le squadre qualunque sia il contenuto delle celle.

Lo stile e' volutamente minimo: colori solo dove portano informazione (il
reparto), tutto il resto eredita il tema di Streamlit. Ogni sezione e' un
``<details>``: si apre e si chiude senza JavaScript.

Nomi di squadre e calciatori sono in maiuscolo grassetto, ma solo via CSS: nel
markup restano com'e' scritto nel listone, cosi' il tooltip mostra il nome
vero anche quando la colonna e' troppo stretta e va in ellissi.
"""

from __future__ import annotations

from collections.abc import Mapping
from html import escape

import streamlit as st

from asta.data.keepers import conceded_by_team
from asta.domain.models import ROLE_LABEL, ROLE_ORDER, Role
from asta.domain.reducer import AuctionState
from asta.ui.crests import crest_url
from asta.ui.wiring import listone_path

#: Un colore per reparto, chiaro quanto basta per reggere il testo scuro sopra.
ROLE_COLOR: dict[Role, str] = {
    Role.P: "#fb923c",
    Role.D: "#4ade80",
    Role.C: "#60a5fa",
    Role.A: "#f87171",
}

_CSS = """
<style>
.tb-wrap{overflow-x:auto;padding-bottom:8px}
.tb{display:grid;gap:8px;align-items:start}
.tb-card{border:1px solid rgba(128,128,128,.35);border-radius:8px;padding:8px 10px}
.tb-card.me{border-color:#4ade80;background:rgba(74,222,128,.12);
  box-shadow:0 0 0 2px rgba(74,222,128,.32)}
.tb-card.me .tb-name{color:#4ade80}
.tb-name{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tb-me{display:inline-block;background:#4ade80;color:#111418;border-radius:4px;
  padding:0 4px;margin-right:4px;font-size:9.5px;font-weight:800;letter-spacing:.04em;
  vertical-align:1px}
.tb-credits{font-size:20px;font-weight:700;line-height:1.2;margin-top:2px}
.tb-credits small{font-size:11px;font-weight:600;opacity:.55;margin-left:3px}
.tb-bar{height:3px;border-radius:2px;background:rgba(128,128,128,.3);margin:5px 0 6px}
.tb-bar i{display:block;height:100%;border-radius:2px;background:#22c55e}
.tb-line{display:flex;justify-content:space-between;font-size:11px;opacity:.7}
.tb-line b{opacity:1}
.tb-left{display:flex;justify-content:space-between;margin-top:5px;font-size:12.5px;font-weight:700}
.tb-left i{font-style:normal}
.tb-sec>summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:6px;
  padding:3px 8px;border-radius:6px;font-size:11px;font-weight:700;color:#111418}
.tb-sec>summary::-webkit-details-marker{display:none}
.tb-sec>summary::after{content:"\\25B4";font-size:9px;opacity:.65}
.tb-sec:not([open])>summary::after{content:"\\25BE"}
.tb-pct{margin-left:auto;font-weight:600}
.tb-slots{display:flex;flex-direction:column;gap:3px;margin-top:3px}
.tb-slot{height:25px;border:1px solid rgba(128,128,128,.25);border-radius:5px}
.tb-slot.full{display:flex;align-items:center;justify-content:space-between;gap:6px;
  padding:0 7px;font-size:11px;border-left-width:3px}
.tb-slot.full em{font-style:normal;font-weight:700;text-transform:uppercase;
  letter-spacing:.02em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tb-slot.full b{flex:0 0 auto}
.tb-empty{padding:14px;text-align:center;opacity:.6}
</style>
"""


def _card(state: AuctionState, name: str, is_me: bool) -> str:
    """Card riassuntiva di una squadra: crediti, offerta massima, rosa, slot liberi."""
    team = state.teams[name]
    settings = team.settings
    ratio = team.credits_left / settings.credits if settings.credits else 0.0
    marker = '<span class="tb-me">TU</span>' if is_me else ""
    # Slot ancora liberi per reparto. Lo zero di un reparto completo va
    # smorzato, altrimenti a colpo d'occhio sembra un numero da leggere.
    left = "".join(
        f'<i style="color:{ROLE_COLOR[r] if team.slots_left(r) else "rgba(128,128,128,.6)"}">'
        f"{team.slots_left(r)}</i>"
        for r in ROLE_ORDER
    )
    return (
        f'<div class="tb-card{" me" if is_me else ""}">'
        f'<div class="tb-name" title="{escape(name)}">{marker}{escape(name)}</div>'
        f'<div class="tb-credits">{team.credits_left}<small>cr</small></div>'
        f'<div class="tb-bar"><i style="width:{max(0.0, min(1.0, ratio)) * 100:.1f}%"></i></div>'
        f'<div class="tb-line"><span>max <b>{team.max_bid}</b></span>'
        f"<span>rosa <b>{team.size}</b>/{settings.roster_size}</span></div>"
        f'<div class="tb-left">{left}</div>'
        "</div>"
    )


def _section(state: AuctionState, name: str, role: Role) -> str:
    """Reparto di una squadra: barra colorata e slot, pieni o vuoti."""
    team = state.teams[name]
    by_id = state.listone.by_id
    color = ROLE_COLOR[role]

    taken = sorted(
        (a for a in team.assignments if a.role == role),
        key=lambda a: (-a.price, by_id[a.player_id].key),
    )
    # La percentuale e' la quota di budget investita nel reparto: e' il dato
    # che serve a occhio durante l'asta ("quanto ho gia' speso in difesa?").
    spent = sum(a.price for a in taken)
    quota = round(spent / team.settings.credits * 100) if team.settings.credits else 0

    slots = "".join(
        f'<div class="tb-slot full" style="border-left-color:{color}">'
        f'<em title="{escape(by_id[a.player_id].name)}">{escape(by_id[a.player_id].name)}</em>'
        f"<b>{a.price}</b></div>"
        for a in taken
    )
    slots += '<div class="tb-slot"></div>' * max(0, team.slots_left(role))

    return (
        '<details class="tb-sec" open>'
        f'<summary style="background:{color}" '
        f'title="{ROLE_LABEL[role]}: {spent} crediti su {team.settings.credits}">'
        f'<span>{role.value}</span><span class="tb-pct">{quota}%</span></summary>'
        f'<div class="tb-slots">{slots}</div>'
        "</details>"
    )


def teams_board_html(state: AuctionState, highlight: str | None = None) -> str:
    """Costruisce l'HTML della griglia delle squadre.

    Args:
        state: stato corrente dell'asta.
        highlight: squadra da evidenziare come "la mia".

    Returns:
        L'HTML completo, CSS incluso. Funzione pura: e' testabile senza Streamlit.
    """
    if state.settings is None or not state.teams:
        return _CSS + '<div class="tb-empty">Nessuna squadra.</div>'

    names = [n for n in state.settings.teams if n in state.teams]
    names += [n for n in state.teams if n not in names]

    cells = [_card(state, n, n == highlight) for n in names]
    for role in ROLE_ORDER:
        cells += [_section(state, n, role) for n in names]

    columns = f"repeat({len(names)},minmax(140px,1fr))"
    return (
        f"{_CSS}<div class='tb-wrap'>"
        f"<div class='tb' style='grid-template-columns:{columns}'>{''.join(cells)}</div>"
        "</div>"
    )


def teams_board(state: AuctionState, highlight: str | None = None) -> None:
    """Disegna la griglia delle squadre."""
    st.markdown(teams_board_html(state, highlight), unsafe_allow_html=True)


_CSS_CLUB = """
<style>
.cb-box{border:1px solid rgba(128,128,128,.35);border-radius:8px;padding:8px 10px;
  margin:2px 0 6px}
.cb-titolo{font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.06em;
  opacity:.85}
.cb-sub{font-size:12px;opacity:.6;margin:1px 0 7px}
.cb{display:flex;flex-wrap:wrap;gap:10px}
.cb-item{display:flex;flex-direction:column;align-items:center;width:62px}
.cb-logo{position:relative;height:38px;width:38px;display:flex;align-items:center;
  justify-content:center}
.cb-logo img{max-height:38px;max-width:38px;object-fit:contain}
.cb-sigla{font-size:13px;font-weight:800;opacity:.75}
.cb-n{position:absolute;right:-6px;bottom:-4px;min-width:17px;height:17px;padding:0 3px;
  border-radius:9px;background:#4ade80;color:#111418;font-size:11px;font-weight:800;
  line-height:17px;text-align:center}
.cb-n.zero{background:#f87171}
.cb-nome{margin-top:4px;font-size:10px;opacity:.7;text-align:center;line-height:1.15;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:62px}
</style>
"""


def club_counts(state: AuctionState, team_name: str) -> dict[str, list[str]]:
    """Calciatori di una squadra raggruppati per club di Serie A.

    Returns:
        ``{club: [nomi]}``; vuoto se la squadra non esiste o non ha ancora
        aggiudicazioni.
    """
    if state.settings is None or team_name not in state.teams:
        return {}
    per_club: dict[str, list[str]] = {}
    for assegnazione in state.teams[team_name].assignments:
        try:
            player = state.listone.get(assegnazione.player_id)
        except KeyError:  # calciatore non piu' nel listone: non e' il posto per morire
            continue
        per_club.setdefault(player.team, []).append(player.name)
    return per_club


#: Titolo del riquadro della copertura. Non e' un'intestazione di sezione:
#: e' un'etichetta, e come tale sta dentro il riquadro che descrive.
TITOLO_COPERTURA = "Copertura squadra"


def club_breakdown_html(
    state: AuctionState, team_name: str, conceded: Mapping[str, int] | None = None
) -> str:
    """HTML dei club di provenienza dei calciatori di una squadra.

    Uno stemma per club, con il numero di calciatori presi da quel club e i
    loro nomi nel tooltip. L'ordine e' quello dei portieri - dalla difesa meno
    battuta dell'anno scorso alla piu' battuta, neopromosse in fondo - cosi'
    la fila e' sempre la stessa nelle due pagine e si legge come una
    graduatoria: i pallini a zero in testa sono i club buoni da cui non si e'
    ancora preso nessuno.

    Tutto dentro un riquadro con la sua etichetta in alto: sul tabellone, sotto
    la griglia delle squadre, senza un bordo sembrerebbe la coda di quella.

    Args:
        state: stato dell'asta.
        team_name: la squadra di cui mostrare la rosa.
        conceded: gol subiti per club; se omesso li legge dal listone.

    Funzione pura (a meno dei gol subiti, che arrivano dal JSON committato).
    """
    if state.settings is None or team_name not in state.teams:
        return ""

    subiti = dict(conceded) if conceded is not None else conceded_by_team(listone_path())
    per_club = club_counts(state, team_name)
    # Ci sono tutti e venti i club, non solo quelli gia' pescati: i pallini
    # rossi dicono dove non si e' ancora preso nessuno, che e' un'informazione
    # utile quanto quella opposta.
    completo = {club: per_club.get(club, []) for club in _club_del_listone(state)}
    ordinati = sorted(completo.items(), key=lambda voce: _ordine_club(voce[0], subiti))
    tiles = "".join(_club_tile(club, nomi, subiti.get(club)) for club, nomi in ordinati)
    return (
        f"{_CSS_CLUB}<div class='cb-box'>"
        f"<div class='cb-titolo'>{escape(TITOLO_COPERTURA)}</div>"
        f"<div class='cb-sub'>{_riga_copertura(state, team_name)}</div>"
        f"<div class='cb'>{tiles}</div></div>"
    )


def _riga_copertura(state: AuctionState, team_name: str) -> str:
    """Riga sotto il titolo: quanti calciatori, da quanti club."""
    per_club = club_counts(state, team_name)
    calciatori = sum(len(nomi) for nomi in per_club.values())
    nome = escape(team_name)
    if calciatori == 0:
        return f"<b>{nome}</b> non ha ancora calciatori: tutti i club sono a zero."
    quanti = f"{calciatori} calciatore" if calciatori == 1 else f"{calciatori} calciatori"
    return (
        f"La rosa di <b>{nome}</b>: {quanti} da {len(per_club)} club "
        f"su {len(_club_del_listone(state))}"
    )


def _club_del_listone(state: AuctionState) -> tuple[str, ...]:
    """I club di Serie A presenti nel listone, in ordine alfabetico."""
    return tuple(sorted({player.team for player in state.listone.players}))


def _ordine_club(club: str, subiti: Mapping[str, int]) -> tuple[bool, int, str]:
    """Chiave d'ordinamento dei club: gol subiti crescenti, senza dati in fondo.

    E' la stessa dei portieri. Le neopromosse non hanno un numero e chiudono
    la fila: uno zero le metterebbe in testa come migliori difese.
    """
    return (club not in subiti, subiti.get(club, 0), club)


def _club_tile(club: str, nomi: list[str], subiti: int | None = None) -> str:
    """Una casella: stemma, numero di calciatori e nome del club.

    Il pallino e' verde se da quel club si e' preso qualcuno, rosso se e'
    ancora a zero. I gol subiti finiscono nel tooltip: sono il motivo per cui
    quel club sta in quel punto della fila.
    """
    url = crest_url(club)
    logo = (
        f'<img src="{url}" alt="{escape(club)}">'
        if url
        else f'<span class="cb-sigla">{escape(club[:3].upper())}</span>'
    )
    quanti = ", ".join(sorted(nomi)) if nomi else "nessun calciatore"
    coda = f" - {subiti} gol subiti l'anno scorso" if subiti is not None else ""
    titolo = escape(f"{club}: {quanti}{coda}")
    classe = "cb-n" if nomi else "cb-n zero"
    return (
        f'<span class="cb-item" title="{titolo}">'
        f'<span class="cb-logo">{logo}<b class="{classe}">{len(nomi)}</b></span>'
        f'<span class="cb-nome">{escape(club)}</span>'
        "</span>"
    )


def club_breakdown(state: AuctionState, team_name: str | None) -> None:
    """Disegna la composizione della propria rosa per club di Serie A.

    Compare solo a squadra scelta: e' la risposta alla domanda "da dove viene
    la mia rosa", che senza una squadra selezionata non ha senso.
    """
    if not team_name:
        return
    st.markdown(club_breakdown_html(state, team_name), unsafe_allow_html=True)


#: Chiave di sessione con la squadra scelta da chi guarda.
MY_TEAM = "my_team"


def _widget_key(key: str) -> str:
    """Chiave del menu, diversa da quella dove la scelta viene conservata."""
    return f"{key}_menu"


def _ricorda_squadra(key: str) -> None:
    """Copia la scelta del menu nella chiave che sopravvive al cambio pagina."""
    st.session_state[key] = st.session_state.get(_widget_key(key))


def my_team_picker(state: AuctionState, key: str = MY_TEAM) -> str | None:
    """Selettore "la mia squadra", per evidenziare la propria colonna.

    Sta dentro un popover: una volta scelta la squadra il menu sparisce e resta
    solo un pulsantino con il nome, che si riapre per cambiarla. Durante l'asta
    lo si tocca una volta sola, e sul telefono ogni riga in meno sopra il
    tabellone conta.

    La scelta resta nella sessione del browser di chi guarda e non tocca l'asta.
    Il menu e la scelta hanno due chiavi diverse apposta: Streamlit dimentica
    lo stato dei widget che in quel giro non ha disegnato, e il menu esiste
    solo sul Tabellone. Con una chiave sola, passare al Listone e tornare
    indietro cancellava la squadra; cosi' invece il menu si ripesca la scelta
    da dove e' rimasta.
    """
    if state.settings is None:
        return None
    scelta = st.session_state.get(key)
    squadre = list(state.settings.teams)
    if _widget_key(key) not in st.session_state and scelta in squadre:
        st.session_state[_widget_key(key)] = scelta

    with st.popover(
        f"🟢 {scelta}" if scelta else "👤 La mia squadra",
        help="Evidenzia la tua colonna nel tabellone",
        # Larghezza esplicita: a "content" il pulsante dentro una riga flex
        # viene misurato qualche pixel piu' stretto del testo e l'etichetta va
        # in ellissi; a "stretch" seguirebbe la colonna e andrebbe a capo.
        width=190,
    ):
        st.selectbox(
            "La mia squadra",
            options=squadre,
            index=None,
            placeholder="Nessuna squadra evidenziata",
            key=_widget_key(key),
            on_change=_ricorda_squadra,
            args=(key,),
        )
    return st.session_state.get(key)

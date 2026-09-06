"""Componenti di interfaccia condivisi fra vista admin e vista utente."""

from __future__ import annotations

from functools import partial
from html import escape

import pandas as pd
import streamlit as st
from pandas.io.formats.style import Styler

from asta.data.players import cached_tiers, stats_season
from asta.domain.letters import current_player, upcoming
from asta.domain.models import (
    CONFIDENCE_LABEL,
    INJURY_EMOJI,
    ROLE_LABEL,
    ROLE_LABEL_SINGULAR,
    ROLE_ORDER,
    SET_PIECE_LABEL,
    SET_PIECE_SHORT,
    SET_PIECES_ALL,
    STARTING_LABEL,
    STARTING_SHORT,
    STAT_LABEL,
    STAT_SHORT,
    STATS_BY_ROLE,
    STATS_EXTRA,
    Confidence,
    Injury,
    Player,
    PlayerStats,
    Role,
    SetPiece,
    Starting,
    Tier,
)
from asta.domain.reducer import AuctionState
from asta.domain.rules import role_progress
from asta.ui.crests import crest_img, league_logo_url
from asta.ui.wiring import listone_path

#: Colore per ruolo, usato nelle etichette.
ROLE_EMOJI: dict[Role, str] = {Role.P: "🧤", Role.D: "🛡️", Role.C: "⚙️", Role.A: "⚽"}

#: Rosso per chi batte di sicuro, giallo per chi se li gioca con altri. Sono
#: le due tinte che tutti leggono senza spiegazioni, anche a distanza.
SET_PIECE_COLOR: dict[Confidence, str] = {
    Confidence.SURE: "#ef4444",
    Confidence.UNSURE: "#facc15",
}

#: Valore numerico dietro la lettera nel listone: la colonna resta ordinabile,
#: e ordinandola in discesa vengono su prima i battitori designati.
SET_PIECE_VALUE: dict[Confidence, int] = {Confidence.SURE: 2, Confidence.UNSURE: 1}

#: Intestazione della prima colonna del listone. Nelle celle resta l'emoji,
#: la stessa del riquadro verde e della barra della fase.
COLONNA_RUOLO = "Ruolo"

#: Numero dietro la cella del ruolo: la posizione in :data:`ROLE_ORDER`.
#: Ordinando in crescente la tabella segue l'ordine dell'asta - portieri,
#: difensori, centrocampisti, attaccanti - invece dell'alfabeto delle sigle,
#: che metterebbe gli attaccanti per primi.
ROLE_VALUE: dict[Role, int] = {role: posto for posto, role in enumerate(ROLE_ORDER, start=1)}

#: Verde chi la maglia ce l'ha, giallo chi se la jugoca con un altro. Stesso
#: giallo dei piazzati: e' sempre "non e' detto".
STARTING_COLOR: dict[Starting, str] = {
    Starting.STARTER: "#4ade80",
    Starting.CONTESTED: "#facc15",
}

STARTING_VALUE: dict[Starting, int] = {Starting.STARTER: 2, Starting.CONTESTED: 1}

#: Intestazione della colonna della titolarita' nel listone; nelle celle
#: restano la T e la B.
COLONNA_TITOLARITA = "Titolarità"


#: Rosso come i cartellini: un infortunio e' la cosa che cambia di piu' quanto
#: vale un calciatore all'asta, e va vista prima di tutto il resto.
INJURY_COLOR = "#ef4444"

#: Colonna dell'infortunio nel listone: l'ambulanza in testata, la giornata
#: di rientro nelle celle.
COLONNA_INFORTUNIO = INJURY_EMOJI

#: Valore dietro la cella quando la giornata di rientro non si sa: sotto ogni
#: giornata vera, sopra la sentinella di "nessun infortunio".
INFORTUNIO_SENZA_DATA = 0


#: Azzurro per la fascia: non e' un allarme (rosso) ne' un dubbio (giallo),
#: e' l'inquadramento del calciatore.
TIER_COLOR = "#60a5fa"

#: Intestazione della colonna della fascia nel listone.
COLONNA_FASCIA = "Fascia"

#: Statistiche che finiscono nel listone, nell'ordine in cui si leggono. Gol
#: subiti, rigori parati e autogol restano fuori: i primi due riguardano i
#: portieri, che hanno la loro pagina, e gli autogol sono una curiosita' che
#: non ha mai spostato un'offerta.
STATS_LISTONE: tuple[str, ...] = (
    "matches",
    "average",
    "fanta_average",
    "goals",
    "assists",
    "penalties_taken",
    "yellow_cards",
    "red_cards",
)

#: Intestazioni delle colonne dei piazzati: per esteso, mentre nelle celle
#: resta la lettera colorata.
COLONNA_PIAZZATO: dict[SetPiece, str] = {
    SetPiece.PENALTY: "Rigorista",
    SetPiece.CORNER: "Corner",
    SetPiece.FREE_KICK: "Punizioni",
}


def tier_code(role: Role, tier: Tier) -> int:
    """Numero che sta dietro la cella della fascia.

    Serve a ordinare la colonna per **graduatoria** e non per sigla: le fasce
    jolly e le scommesse sono infilate fra le altre, quindi F5 puo' valere piu'
    di JF1 in un reparto e meno nell'altro. Il ruolo entra nelle unita' cosi'
    che ogni codice si possa ritradurre nella sua sigla, e ordinando si va per
    rango prima e per reparto poi.
    """
    return tier.rank * 10 + ROLE_ORDER.index(role)


def tier_labels() -> dict[int, str]:
    """``{codice: sigla}``, costruita dalle graduatorie del listone."""
    return {
        tier_code(role, Tier(label=label, rank=rank)): label
        for role, fasce in cached_tiers(listone_path()).items()
        for rank, label in enumerate(fasce, start=1)
    }


def tier_item(player: Player) -> list[tuple[str, str, str, str]]:
    """La voce della fascia d'asta, vuota per chi non ne ha una."""
    if player.tier is None:
        return []
    return [(player.tier.label, "Fascia", f"Fascia d'asta {player.tier.label}", TIER_COLOR)]


def injury_item(player: Player) -> list[tuple[str, str, str, str]]:
    """La voce dell'infortunio: ambulanza e giornata di rientro prevista."""
    if player.injury is None:
        return []
    return [
        (
            INJURY_EMOJI,
            player.injury.label,
            player.injury.note or "Indisponibile",
            INJURY_COLOR,
        )
    ]


def starting_item(player: Player) -> list[tuple[str, str, str, str]]:
    """La quaterna della titolarita', vuota se non e' nella formazione tipo."""
    if player.starter is None:
        return []
    etichetta = STARTING_LABEL[player.starter]
    return [
        (
            STARTING_SHORT[player.starter],
            etichetta,
            f"{etichetta} nella formazione tipo",
            STARTING_COLOR[player.starter],
        )
    ]


def set_piece_items(player: Player) -> list[tuple[str, str, str, str]]:
    """Quaterne ``(lettera, nome, spiegazione, colore)`` dei piazzati che batte.

    Vuota per chi le gerarchie non nominano: nel riquadro non compare nulla,
    che e' diverso dal dire "non li batte".
    """
    if player.set_pieces is None:
        return []
    return [
        (
            SET_PIECE_SHORT[piece],
            SET_PIECE_LABEL[piece],
            f"{SET_PIECE_LABEL[piece]}: {CONFIDENCE_LABEL[livello]}",
            SET_PIECE_COLOR[livello],
        )
        for piece, livello in player.set_pieces.items()
    ]


def badge_items(player: Player) -> list[tuple[str, str, str, str]]:
    """I simboli del calciatore: infermeria, fascia, maglia, piazzati."""
    return injury_item(player) + tier_item(player) + starting_item(player) + set_piece_items(player)


def _badges_html(player: Player) -> str:
    """Riga delle lettere dentro la card: colorata la lettera, non la scritta."""
    voci = badge_items(player)
    if not voci:
        return ""
    chip = (
        '<span title="{titolo}" style="background:rgba(255,255,255,.08);'
        'border-radius:.4rem;padding:.1rem .45rem;white-space:nowrap">'
        '<b style="color:{colore}">{lettera}</b> '
        '<span style="opacity:.75">{nome}</span></span>'
    )
    chips = "".join(
        chip.format(lettera=lettera, nome=nome, titolo=titolo, colore=colore)
        for lettera, nome, titolo, colore in voci
    )
    return (
        '<div style="display:flex;flex-wrap:wrap;gap:.35rem;margin-top:.6rem;'
        f'font-size:.85rem">{chips}</div>'
    )


def format_stat(field: str, value: float | int) -> str:
    """Numero pronto da leggere: le medie con la virgola, il resto intero."""
    if isinstance(value, float) and field in {"average", "fanta_average"}:
        return f"{value:.2f}".replace(".", ",")
    return str(int(value))


def stat_items(player: Player) -> list[tuple[str, str, str]]:
    """Terne ``(etichetta, nome per esteso, valore)`` da mostrare.

    Le voci dipendono dal ruolo - un portiere si giudica sui gol subiti, un
    attaccante sui gol fatti - e ci sono tutte, zeri compresi: un attaccante
    senza assist e' un'informazione tanto quanto uno con dieci. I cartellini
    si mostrano col simbolo; il nome per esteso resta come tooltip.
    """
    stats = player.stats
    if stats is None:
        return []
    campi = [*STATS_BY_ROLE[player.role], *STATS_EXTRA]
    return [
        (STAT_SHORT.get(c, STAT_LABEL[c]), STAT_LABEL[c], format_stat(c, getattr(stats, c)))
        for c in campi
    ]


def _stats_html(player: Player) -> str:
    """Riga di statistiche dentro la card, o una nota se non ne ha."""
    stagione = stats_season()
    titolo = f"Stagione {stagione}" if stagione else "Stagione precedente"
    if player.stats is None:
        return (
            f'<div style="opacity:.5;font-size:.8rem;margin-top:.5rem">'
            f"{titolo}: nessuna presenza in Serie A</div>"
        )
    if not player.stats.played:
        return (
            f'<div style="opacity:.5;font-size:.8rem;margin-top:.5rem">'
            f"{titolo}: nessuna partita a voto</div>"
        )
    chip = (
        '<span title="{titolo}" style="background:rgba(255,255,255,.08);'
        'border-radius:.4rem;padding:.1rem .45rem;white-space:nowrap">'
        '<span style="opacity:.7">{label}</span> <b>{value}</b></span>'
    )
    chips = "".join(
        chip.format(label=label, titolo=titolo, value=value)
        for label, titolo, value in stat_items(player)
    )
    return (
        f'<div style="opacity:.55;font-size:.72rem;margin-top:.6rem;'
        f'text-transform:uppercase;letter-spacing:.06em">{titolo}</div>'
        f'<div style="display:flex;flex-wrap:wrap;gap:.35rem;margin-top:.25rem;'
        f'font-size:.85rem">{chips}</div>'
    )


#: La coda dentro la card: incolonnata a destra, fra il bordo del testo e la
#: filigrana del logo. ``top``/``bottom`` invece di un'altezza fissa perche'
#: e' la card a decidere quanto spazio c'e' - e ne ha di piu' quando il
#: calciatore ha fascia, infortunio e statistiche - mentre ``overflow-y``
#: fa scorrere quello che non ci sta invece di allungare il riquadro.
#:
#: Il logo e' alto 78px con un viewBox 45.71x70.92, cioe' largo una
#: cinquantina: ``right`` lo scavalca e lascia un po' d'aria.
#:
#: Sotto i 640px la colonna non ci sta: la card e' larga un dito e mezzo, e il
#: nome da leggere a voce alta viene prima di tutto il resto. Invece di
#: sparire si corica - stessa marcatura, altre regole - e diventa una striscia
#: sotto le statistiche che si scorre col dito da destra a sinistra. Sul
#: telefono e' il gesto naturale, e cosi' la card cresce di una riga sola
#: invece che di sette.
_CSS_CODA = """
<style>
.ia-coda{position:absolute;right:5.5rem;top:.9rem;bottom:.9rem;max-width:38%;
  display:flex;flex-direction:column;align-items:flex-end;text-align:right}
.ia-coda-t{flex:none;font-size:.62rem;text-transform:uppercase;
  letter-spacing:.08em;opacity:.5;margin-bottom:.15rem;white-space:nowrap}
.ia-coda-l{flex:1 1 auto;min-height:0;overflow-y:auto;scrollbar-width:thin}
.ia-coda-n{font-size:.8rem;line-height:1.5;opacity:.72;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.ia-coda-n:first-child{opacity:1;font-weight:600}
@media (max-width:640px){
  .ia-coda{position:static;right:auto;top:auto;bottom:auto;max-width:none;
    align-items:stretch;text-align:left;margin-top:.6rem}
  .ia-coda-l{flex:none;display:flex;gap:.5rem;
    overflow-x:auto;overflow-y:hidden;-webkit-overflow-scrolling:touch}
  .ia-coda-n{flex:none;overflow:visible}
  .ia-coda-n+.ia-coda-n::before{content:"·";opacity:.4;margin-right:.5rem}
}
</style>
"""


def _coda_html(prossimi: tuple[Player, ...]) -> str:
    """La colonnina dei prossimi in asta, dentro la card e a destra.

    Sta in fondo alla card e non in cima: sul desktop e' in posizione
    assoluta e l'ordine nel documento non conta, ma sul telefono si corica
    e torna nel flusso - li' deve venire dopo le statistiche, non prima
    del nome.

    Vuota non si disegna affatto: un titolino "in coda" senza nomi sotto
    direbbe il contrario di quello che sta succedendo.
    """
    if not prossimi:
        return ""
    nomi = "".join(f'<div class="ia-coda-n">{escape(p.name)}</div>' for p in prossimi)
    return (
        f'<div class="ia-coda"><div class="ia-coda-t">In coda · {len(prossimi)}</div>'
        f'<div class="ia-coda-l">{nomi}</div></div>'
    )


def player_card(
    player: Player, *, title: str = "In asta ora", prossimi: tuple[Player, ...] = ()
) -> None:
    """Riquadro grande con nome, ruolo e squadra del calciatore.

    E' la risposta alla domanda "chi stiamo chiamando?": va letta a voce alta,
    quindi il nome e' il primo elemento e in grande.

    Args:
        player: il calciatore in asta.
        title: etichetta in alto a sinistra.
        prossimi: i successivi della lettera, incolonnati a destra. La domanda
            che viene subito dopo - "e poi?" - trova risposta senza uscire dal
            riquadro. In chiamata libera non ce ne sono e la colonna sparisce.
    """
    # Il logo della lega fa da filigrana: sta in posizione assoluta, quindi
    # non ruba spazio verticale alla card.
    lega = league_logo_url()
    filigrana = (
        f'<img src="{lega}" alt="" aria-hidden="true" style="position:absolute;'
        f"right:1.25rem;top:50%;transform:translateY(-50%);height:78px;"
        f'opacity:.14;pointer-events:none">'
        if lega
        else ""
    )
    # Il CSS va in un elemento suo: infilato in cima al blocco indentato qui
    # sotto ne azzererebbe il rientro comune, e markdown leggerebbe le righe
    # della card come un blocco di codice invece che come HTML.
    st.markdown(_CSS_CODA, unsafe_allow_html=True)
    st.markdown(
        f"""
        <div style="position:relative;overflow:hidden;
                    border:1px solid rgba(255,255,255,.2);border-radius:.75rem;
                    padding:1rem 1.25rem;margin:.25rem 0 1rem 0;
                    background:rgba(0,200,83,.08)">
          {filigrana}
          <div style="opacity:.7;font-size:.8rem;text-transform:uppercase;
                      letter-spacing:.08em">{title}</div>
          <div style="font-size:2rem;font-weight:700;line-height:1.2">{player.name}</div>
          <div style="font-size:1.05rem;opacity:.9">
            {crest_img(player.team)}{ROLE_EMOJI[player.role]}
            {ROLE_LABEL_SINGULAR[player.role]}
            &nbsp;·&nbsp; <b>{player.team}</b>
          </div>
          {_badges_html(player)}
          {_stats_html(player)}
          {_coda_html(prossimi)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def phase_banner(state: AuctionState) -> None:
    """Riga di stato con la fase in corso e il suo avanzamento."""
    if state.current_role is None:
        st.info("Asta non ancora avviata.")
        return
    filled, total = role_progress(state, state.current_role)
    label = ROLE_LABEL[state.current_role]
    st.progress(
        filled / total if total else 0.0,
        text=f"{ROLE_EMOJI[state.current_role]} Fase **{label}** — {filled}/{total} slot assegnati",
    )


#: Colonne del listone, nell'ordine in cui si leggono.
COLONNE_LISTONE: list[str] = [
    # Il ruolo apre la fila: e' la prima cosa che si guarda di un calciatore,
    # e senza filtro attivo la tabella li mescola tutti.
    COLONNA_RUOLO,
    "Calciatore",
    "Squadra",
    # Prima chi e' e quanto vale, poi com'e' andato, poi cosa batte, e in
    # fondo l'infermeria.
    COLONNA_FASCIA,
    COLONNA_TITOLARITA,
    *(STAT_SHORT.get(campo, STAT_LABEL[campo]) for campo in STATS_LISTONE),
    *(COLONNA_PIAZZATO[piece] for piece in SET_PIECES_ALL),
    COLONNA_INFORTUNIO,
]


def listone_table(players: tuple[Player, ...]) -> pd.DataFrame:
    """Listone in forma tabellare, con i rendimenti della stagione precedente.

    Ci sono tutte le statistiche, anche quelle che per un ruolo valgono sempre
    zero: la tabella si consulta dal computer, dove le colonne in piu' costano
    poco, e cosi' nessun dato resta nascosto a seconda del filtro attivo.

    Le colonne restano numeriche anche quando un calciatore non ha statistiche
    (cella vuota): cosi' l'ordinamento della tabella continua a funzionare, ed
    e' il modo piu' rapido per vedere chi e' il migliore ancora disponibile.
    """
    campi = STATS_LISTONE
    righe = []
    for p in players:
        riga: dict[str, object] = {
            COLONNA_RUOLO: ROLE_VALUE[p.role],
            "Calciatore": p.name,
            "Squadra": p.team,
        }
        riga[COLONNA_FASCIA] = tier_code(p.role, p.tier) if p.tier else None
        riga[COLONNA_TITOLARITA] = STARTING_VALUE[p.starter] if p.starter else None
        for campo in campi:
            riga[_intestazione(campo)] = _valore_statistica(p.stats, campo)
        for piece in SET_PIECES_ALL:
            riga[COLONNA_PIAZZATO[piece]] = _valore_piazzato(p, piece)
        riga[COLONNA_INFORTUNIO] = _valore_infortunio(p.injury)
        righe.append(riga)

    # Le colonne si dichiarano sempre, anche senza righe: con una ricerca
    # senza risultati un DataFrame vuoto non avrebbe colonne, e il resto
    # della funzione cercherebbe di convertirne una che non esiste.
    tabella = pd.DataFrame(righe, columns=COLONNE_LISTONE)
    # Senza il tipo intero "nullable" pandas trasformerebbe le colonne con
    # qualche cella vuota in float: 16 partite diventerebbero 16.0.
    for campo in campi:
        if campo not in {"average", "fanta_average"}:
            colonna = _intestazione(campo)
            tabella[colonna] = tabella[colonna].astype("Int64")
    extra = (
        COLONNA_RUOLO,
        COLONNA_FASCIA,
        COLONNA_INFORTUNIO,
        COLONNA_TITOLARITA,
        *(COLONNA_PIAZZATO[p] for p in SET_PIECES_ALL),
    )
    for colonna in extra:
        tabella[colonna] = tabella[colonna].astype("Int64")
    return tabella


def _valore_infortunio(injury: Injury | None) -> int | None:
    """Giornata di rientro, in forma ordinabile: chi torna prima viene prima."""
    if injury is None:
        return None
    return injury.matchday if injury.matchday is not None else INFORTUNIO_SENZA_DATA


def _valore_piazzato(player: Player, piece: SetPiece) -> int | None:
    """Quanto e' sicuro che batta quel piazzato, in forma ordinabile."""
    if player.set_pieces is None:
        return None
    livello = player.set_pieces.of(piece)
    return SET_PIECE_VALUE[livello] if livello is not None else None


def _intestazione(campo: str) -> str:
    """Testata della colonna: simbolo dove c'e', nome per esteso per il resto.

    E' la stessa etichetta che va nel riquadro del calciatore, cosi' un gol e'
    sempre un pallone, in tabella come nella card.
    """
    return STAT_SHORT.get(campo, STAT_LABEL[campo])


def listone_column_config() -> dict[str, object]:
    """Didascalie delle colonne statistiche del listone.

    Ogni colonna porta il nome per esteso come tooltip dell'intestazione:
    serve soprattutto a 🟨 e 🟥, che nella testata stanno in poco spazio ma
    vanno comunque spiegati. La formattazione dei numeri la fa
    :func:`listone_display`.
    """
    colonne: dict[str, object] = {
        COLONNA_RUOLO: st.column_config.Column(
            help="Ruolo: ordinando si va per fase d'asta, dai portieri agli attaccanti"
        ),
        COLONNA_FASCIA: st.column_config.Column(
            help="Fascia d'asta del reparto: ordinando vengono prima le piu' alte"
        ),
        COLONNA_INFORTUNIO: st.column_config.Column(
            help="Infortunato: la giornata per cui e' previsto il rientro"
        ),
        COLONNA_TITOLARITA: st.column_config.Column(
            help="Formazione tipo: T verde titolare, B gialla in ballottaggio"
        ),
    }
    colonne |= {
        COLONNA_PIAZZATO[piece]: st.column_config.Column(
            help=f"{SET_PIECE_LABEL[piece]}: rosso battitore designato, giallo se li gioca"
        )
        for piece in SET_PIECES_ALL
    }
    colonne.update(
        {
            _intestazione(campo): st.column_config.NumberColumn(help=STAT_LABEL[campo])
            for campo in STATS_LISTONE
        }
    )
    return colonne


#: Valore usato al posto delle statistiche mancanti nella tabella mostrata a
#: schermo. Streamlit scrive "None" in ogni cella nulla, e trenta righe di
#: "None" coprirebbero i dati veri: la sentinella viene resa come cella vuota
#: dal formattatore, e l'ordinamento resta numerico (finisce in fondo, dove
#: deve stare chi non ha giocato).
SENZA_DATI = -1


def _formatta_cella(valore: object, decimali: bool) -> str:
    """Valore di una cella statistica: vuoto se il dato non c'e'."""
    if valore is None or valore is pd.NA or valore != valore or valore == SENZA_DATI:
        return ""
    numero = float(valore)  # type: ignore[arg-type]
    return f"{numero:.2f}".replace(".", ",") if decimali else f"{int(numero)}"


def _formatta_piazzato(valore: object, lettera: str) -> str:
    """Cella di un piazzato: la lettera per chi lo batte, vuoto per gli altri."""
    return lettera if valore in SET_PIECE_VALUE.values() else ""


def _formatta_ruolo(valore: object) -> str:
    """Cella del ruolo: l'emoji, la stessa che il calciatore ha nel riquadro verde."""
    for role, atteso in ROLE_VALUE.items():
        if valore == atteso:
            return ROLE_EMOJI[role]
    return ""


def _formatta_titolarita(valore: object) -> str:
    """Cella della titolarita': ``T`` per il titolare, ``B`` per il ballottaggio."""
    for livello, atteso in STARTING_VALUE.items():
        if valore == atteso:
            return STARTING_SHORT[livello]
    return ""


def _formatta_fascia(valore: object, sigle: dict[int, str]) -> str:
    """Cella della fascia: la sigla, vuota per chi non e' in graduatoria.

    Il valore arriva dal DataFrame, quindi e' un intero di numpy o la cella
    vuota di pandas: si converte a mano invece di fidarsi del tipo.
    """
    try:
        codice = int(valore)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return ""
    return sigle.get(codice, "")


def _colore_fascia(valore: object) -> str:
    """CSS della cella: azzurro su chi ha una fascia."""
    return "" if valore == SENZA_DATI or valore is None else f"color:{TIER_COLOR};font-weight:700"


def _formatta_infortunio(valore: object) -> str:
    """Cella dell'infortunio: la giornata di rientro, vuota per chi sta bene."""
    if valore == SENZA_DATI or valore is None:
        return ""
    if valore == INFORTUNIO_SENZA_DATA:
        return "—"
    return f"{int(valore)}a"  # type: ignore[arg-type]


def _colore_infortunio(valore: object) -> str:
    """CSS della cella: rosso su chi e' fuori, niente sugli altri."""
    if valore == SENZA_DATI or valore is None:
        return ""
    return f"color:{INJURY_COLOR};font-weight:700"


def _colore_piazzato(valore: object) -> str:
    """CSS della cella: la lettera prende il colore della sua sicurezza."""
    for livello, atteso in SET_PIECE_VALUE.items():
        if valore == atteso:
            return f"color:{SET_PIECE_COLOR[livello]};font-weight:700"
    return ""


def _colore_titolarita(valore: object) -> str:
    """CSS della cella: verde il titolare, giallo il ballottaggio."""
    for livello, atteso in STARTING_VALUE.items():
        if valore == atteso:
            return f"color:{STARTING_COLOR[livello]};font-weight:700"
    return ""


def listone_display(tabella: pd.DataFrame) -> Styler:
    """Versione da mostrare della tabella: celle vuote e virgola decimale.

    Il DataFrame resta numerico sotto, quindi cliccando l'intestazione la
    tabella si ordina per valore: e' cosi' che si trova il migliore ancora
    disponibile. Vale anche per i piazzati, dove il numero nascosto sotto la
    lettera mette in cima i battitori designati.
    """
    vista = tabella.copy()
    formati: dict[str, object] = {}
    for campo in STATS_LISTONE:
        colonna = _intestazione(campo)
        if colonna not in vista:
            continue
        decimali = campo in {"average", "fanta_average"}
        vista[colonna] = vista[colonna].fillna(SENZA_DATI)
        formati[colonna] = partial(_formatta_cella, decimali=decimali)

    piazzati = [
        COLONNA_PIAZZATO[piece] for piece in SET_PIECES_ALL if COLONNA_PIAZZATO[piece] in vista
    ]
    for piece in SET_PIECES_ALL:
        colonna = COLONNA_PIAZZATO[piece]
        if colonna not in vista:
            continue
        vista[colonna] = vista[colonna].fillna(SENZA_DATI)
        # Nell'intestazione c'e' la parola, nella cella la lettera colorata.
        formati[colonna] = partial(_formatta_piazzato, lettera=SET_PIECE_SHORT[piece])
    if COLONNA_RUOLO in vista:
        # Nessun fillna: il ruolo di un calciatore c'e' sempre.
        formati[COLONNA_RUOLO] = _formatta_ruolo
    if COLONNA_TITOLARITA in vista:
        vista[COLONNA_TITOLARITA] = vista[COLONNA_TITOLARITA].fillna(SENZA_DATI)
        formati[COLONNA_TITOLARITA] = _formatta_titolarita
    if COLONNA_INFORTUNIO in vista:
        vista[COLONNA_INFORTUNIO] = vista[COLONNA_INFORTUNIO].fillna(SENZA_DATI)
        formati[COLONNA_INFORTUNIO] = _formatta_infortunio
    if COLONNA_FASCIA in vista:
        vista[COLONNA_FASCIA] = vista[COLONNA_FASCIA].fillna(SENZA_DATI)
        formati[COLONNA_FASCIA] = partial(_formatta_fascia, sigle=tier_labels())

    stile = vista.style.format(formati)
    if piazzati:
        stile = stile.map(_colore_piazzato, subset=piazzati)
    if COLONNA_TITOLARITA in vista:
        stile = stile.map(_colore_titolarita, subset=[COLONNA_TITOLARITA])
    if COLONNA_INFORTUNIO in vista:
        stile = stile.map(_colore_infortunio, subset=[COLONNA_INFORTUNIO])
    if COLONNA_FASCIA in vista:
        stile = stile.map(_colore_fascia, subset=[COLONNA_FASCIA])
    return stile


def _valore_statistica(stats: PlayerStats | None, campo: str) -> float | int | None:
    """Valore grezzo per la tabella; ``None`` per chi non ha giocato."""
    if stats is None or not stats.played:
        return None
    value = getattr(stats, campo)
    return float(value) if isinstance(value, float) else int(value)


def fasce_disponibili(role: Role | None) -> list[str]:
    """Sigle delle fasce da mettere nel menu, in ordine di graduatoria.

    Con un reparto scelto sono le sue e basta; senza, sono tutte quelle che
    esistono, ordinate per rango medio - cosi' F1 resta in cima e le fasce
    piu' basse in fondo anche mescolando i reparti.
    """
    per_ruolo = cached_tiers(listone_path())
    if role is not None:
        return list(per_ruolo.get(role, ()))
    ranghi: dict[str, list[int]] = {}
    for fasce in per_ruolo.values():
        for rank, label in enumerate(fasce, start=1):
            ranghi.setdefault(label, []).append(rank)
    return sorted(ranghi, key=lambda label: (sum(ranghi[label]) / len(ranghi[label]), label))


#: Voce del menu della titolarita' per chi le probabili formazioni non
#: nominano: ne' titolare ne' in ballottaggio. Corta perche' il menu sta
#: in una colonna su quattro, e piu' lunga di cosi' verrebbe tagliata.
FUORI_FORMAZIONE = "Fuori dagli 11"

#: Le voci del menu, nell'ordine in cui si guardano: prima chi gioca.
TITOLARITA_SCELTE = [STARTING_LABEL[s] for s in Starting] + [FUORI_FORMAZIONE]


def filtra_titolarita(players: tuple[Player, ...], scelta: str) -> tuple[Player, ...]:
    """Tiene solo i calciatori con quella titolarita'.

    Args:
        players: calciatori da filtrare.
        scelta: una voce di :data:`TITOLARITA_SCELTE`, o qualsiasi altra cosa
            per non filtrare niente.
    """
    if scelta == FUORI_FORMAZIONE:
        return tuple(p for p in players if p.starter is None)
    voluta = next((s for s in Starting if STARTING_LABEL[s] == scelta), None)
    if voluta is None:
        return players
    return tuple(p for p in players if p.starter == voluta)


#: Suffisso della copia di un filtro fuori dallo stato dei widget.
#:
#: Streamlit butta via lo stato di un widget appena la pagina che lo contiene
#: smette di disegnarlo, e le pagine pubbliche sono pagine vere (una per
#: ``st.navigation``), non schede. Risultato: chi filtrava il listone,
#: andava a vedere il tabellone e tornava indietro ritrovava tutti i menu su
#: "Tutte" e la ricerca vuota. Successo davvero, durante l'asta.
#:
#: La copia sta sotto una chiave che non appartiene a nessun widget, quindi
#: nessuno la ripulisce, e al rientro fa da valore di partenza. Streamlit
#: ignora il valore di partenza quando la chiave del widget c'e' gia', cioe'
#: durante il normale andirivieni sulla stessa pagina: comanda sempre quello
#: che si e' scelto per ultimo.
SUFFISSO_MEMORIA = "_scelto"


def _menu_persistente(etichetta: str, opzioni: list[str], key: str, **kwargs: object) -> str:
    """``st.selectbox`` che si ricorda la scelta anche cambiando pagina.

    Se la scelta di prima non e' piu' fra le opzioni - le fasce cambiano col
    reparto - si riparte dalla prima voce, che e' sempre quella che non
    filtra niente.
    """
    memoria = key + SUFFISSO_MEMORIA
    scelta = st.session_state.get(memoria)
    posto = opzioni.index(scelta) if scelta in opzioni else 0
    valore = st.selectbox(etichetta, opzioni, index=posto, key=key, **kwargs)  # type: ignore[arg-type]
    st.session_state[memoria] = valore
    return str(valore)


def _testo_persistente(etichetta: str, key: str, **kwargs: object) -> str:
    """``st.text_input`` che si ricorda quello che c'e' scritto, come sopra."""
    memoria = key + SUFFISSO_MEMORIA
    valore = st.text_input(
        etichetta,
        value=st.session_state.get(memoria, ""),
        key=key,
        **kwargs,  # type: ignore[arg-type]
    )
    st.session_state[memoria] = valore
    return str(valore)


def listone_filters(state: AuctionState, key_prefix: str) -> tuple[Player, ...]:
    """Filtri su ruolo, fascia, titolarita', squadra e nome; i disponibili."""
    # Nello stesso ordine delle colonne della tabella, cosi' il filtro e la
    # colonna che governa si guardano nello stesso punto.
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        role_label = _menu_persistente(
            "Ruolo",
            ["Tutti", *[ROLE_LABEL[r] for r in ROLE_ORDER]],
            f"{key_prefix}_role",
        )
    role = next((r for r in ROLE_ORDER if ROLE_LABEL[r] == role_label), None)
    with col2:
        # Il menu delle fasce segue il reparto scelto: quelle dei difensori
        # non arrivano fino a F8, quelle dei centrocampisti si'.
        fascia = _menu_persistente(
            "Fascia", ["Tutte", *fasce_disponibili(role)], f"{key_prefix}_tier"
        )
    with col3:
        titolarita = _menu_persistente(
            "Titolarità", ["Tutte", *TITOLARITA_SCELTE], f"{key_prefix}_starting"
        )
    with col4:
        squadre = sorted({p.team for p in state.listone.players})
        squadra = _menu_persistente("Squadra di A", ["Tutte", *squadre], f"{key_prefix}_team")
    query = _testo_persistente("Cerca calciatore", f"{key_prefix}_q", placeholder="Nome...")

    players = state.available(role)
    if fascia != "Tutte":
        players = tuple(p for p in players if p.tier is not None and p.tier.label == fascia)
    if titolarita != "Tutte":
        players = filtra_titolarita(players, titolarita)
    if squadra != "Tutte":
        players = tuple(p for p in players if p.team == squadra)
    if query:
        matches = {p.id for p in state.listone.search(query)}
        players = tuple(p for p in players if p.id in matches)
    return players


COLONNE_VENDITE = ["Calciatore", "Ruolo", "Squadra di A", "Aggiudicato a", "Prezzo"]


def sales_table(state: AuctionState, limit: int | None = None) -> pd.DataFrame:
    """Aggiudicazioni dalla piu' recente.

    Args:
        state: stato dell'asta.
        limit: se indicato, tiene solo le prime ``limit`` righe.
    """
    rows = [
        {
            "Calciatore": player.name,
            "Ruolo": player.role.value,
            "Squadra di A": player.team,
            "Aggiudicato a": assignment.team,
            "Prezzo": assignment.price,
        }
        for assignment, player in reversed(state.sold())
    ]
    if limit is not None:
        rows = rows[:limit]
    return pd.DataFrame(rows, columns=COLONNE_VENDITE)


def sales_filters(state: AuctionState, key_prefix: str) -> pd.DataFrame:
    """Filtri su squadra e ruolo; restituisce le aggiudicazioni corrispondenti."""
    col1, col2 = st.columns(2)
    with col1:
        squadre = list(state.settings.teams) if state.settings else []
        squadra = _menu_persistente("Squadra", ["Tutte", *squadre], f"{key_prefix}_team")
    with col2:
        role_label = _menu_persistente(
            "Ruolo",
            ["Tutti", *[ROLE_LABEL[r] for r in ROLE_ORDER]],
            f"{key_prefix}_role",
        )

    vendite = sales_table(state)
    if squadra != "Tutte":
        vendite = vendite[vendite["Aggiudicato a"] == squadra]
    role = next((r for r in ROLE_ORDER if ROLE_LABEL[r] == role_label), None)
    if role is not None:
        vendite = vendite[vendite["Ruolo"] == role.value]
    return vendite


def now_playing(state: AuctionState) -> None:
    """Riquadro del calciatore in asta.

    E' identico su tutte le pagine pubbliche: e' l'informazione che si legge a
    voce alta in stanza, e cambiarle forma da una pagina all'altra
    costringerebbe a ricercarla ogni volta.
    """
    if not state.started:
        return
    if state.closed:
        st.success("🏁 Asta conclusa.")
        return
    player = current_player(state)
    if player is None:
        st.info("Nessun calciatore in asta in questo momento.")
        return
    player_card(player, prossimi=upcoming(state))

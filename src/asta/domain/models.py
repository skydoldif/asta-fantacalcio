"""Tipi di base dell'asta: ruoli, calciatori, impostazioni, squadre, stato."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Role(StrEnum):
    """Ruolo Classic di un calciatore.

    I ruoli si confrontano sempre con ``==``, mai con ``is``. Streamlit
    ricarica i moduli quando cambia un sorgente, ma gli oggetti dentro
    ``st.cache_resource`` e ``st.session_state`` restano quelli costruiti con
    la classe precedente: due membri "uguali" possono appartenere a due classi
    diverse e ``is`` fallirebbe. Essendo una ``StrEnum``, ``==`` confronta il
    valore e regge il confronto fra classi diverse (come gia' fanno hash e
    lookup nei dizionari).
    """

    P = "P"
    D = "D"
    C = "C"
    A = "A"


#: Ordine in cui si svolgono le fasi dell'asta.
ROLE_ORDER: tuple[Role, ...] = (Role.P, Role.D, Role.C, Role.A)

ROLE_LABEL: dict[Role, str] = {
    Role.P: "Portieri",
    Role.D: "Difensori",
    Role.C: "Centrocampisti",
    Role.A: "Attaccanti",
}

ROLE_LABEL_SINGULAR: dict[Role, str] = {
    Role.P: "Portiere",
    Role.D: "Difensore",
    Role.C: "Centrocampista",
    Role.A: "Attaccante",
}

#: Limiti di rosa di default (3 portieri, 8 difensori, 8 centrocampisti, 6 attaccanti).
DEFAULT_ROLE_LIMITS: dict[Role, int] = {Role.P: 3, Role.D: 8, Role.C: 8, Role.A: 6}
DEFAULT_ROSTER_SIZE = 25
DEFAULT_CREDITS = 500
MIN_PRICE = 1


class Mode(StrEnum):
    """Modalita di chiamata dei calciatori."""

    #: L'admin digita il nome del calciatore chiamato a voce.
    FREE = "free"
    #: L'app estrae una lettera e scorre i calciatori in ordine alfabetico.
    LETTER = "letter"


MODE_LABEL: dict[Mode, str] = {
    Mode.FREE: "Chiamata libera",
    Mode.LETTER: "Lettera random",
}


class BackupTrigger(StrEnum):
    """Momenti in cui l'app puo' scaricare da sola il backup dell'asta."""

    #: Il database non risponde: le operazioni vivono solo nel browser
    #: dell'admin, ed e' il momento in cui perderle costerebbe di piu'.
    OFFLINE = "offline"
    #: Fine della fase di un reparto, cioe' quando parte quella successiva.
    END_P = "end_P"
    END_D = "end_D"
    END_C = "end_C"
    #: Asta dichiarata conclusa: coincide con la fine degli attaccanti.
    END_AUCTION = "end_auction"


BACKUP_TRIGGER_LABEL: dict[BackupTrigger, str] = {
    BackupTrigger.OFFLINE: "Perdita di connessione",
    BackupTrigger.END_P: "Fine portieri",
    BackupTrigger.END_D: "Fine difensori",
    BackupTrigger.END_C: "Fine centrocampisti",
    BackupTrigger.END_AUCTION: "Fine asta",
}

#: Pezzo di nome del file scaricato, uno per momento.
BACKUP_TRIGGER_SLUG: dict[BackupTrigger, str] = {
    BackupTrigger.OFFLINE: "offline",
    BackupTrigger.END_P: "fine_portieri",
    BackupTrigger.END_D: "fine_difensori",
    BackupTrigger.END_C: "fine_centrocampisti",
    BackupTrigger.END_AUCTION: "fine_asta",
}

#: Fine della fase di un ruolo -> momento corrispondente. Gli attaccanti non
#: ci sono: la loro fase finisce con l'asta, che ha gia' il suo momento.
END_OF_PHASE: dict[Role, BackupTrigger] = {
    Role.P: BackupTrigger.END_P,
    Role.D: BackupTrigger.END_D,
    Role.C: BackupTrigger.END_C,
}

#: Momenti spuntati di default: chi accende l'opzione li vuole tutti.
DEFAULT_BACKUP_TRIGGERS: tuple[BackupTrigger, ...] = tuple(BackupTrigger)


def sort_key(name: str) -> str:
    """Chiave di ordinamento insensibile ad accenti, apostrofi e spazi.

    Deve restare identica a quella usata da ``scripts/build_players.py``,
    altrimenti l'ordine alfabetico in app divergerebbe da quello del listone.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return "".join(c for c in stripped.upper() if c.isalnum())


@dataclass(frozen=True, slots=True)
class PlayerStats:
    """Rendimento di un calciatore nella stagione precedente.

    Arrivano dal file *Statistiche* di fantacalcio.it, che copre solo chi ha
    giocato in Serie A: i nuovi acquisti e i giovani non ne hanno, quindi
    :attr:`Player.stats` puo' essere ``None``.
    """

    matches: int
    """Partite a voto."""
    average: float
    """Media voto."""
    fanta_average: float
    """Fantamedia."""
    goals: int
    """Gol fatti."""
    goals_conceded: int
    """Gol subiti."""
    penalties_saved: int
    """Rigori parati."""
    penalties_taken: int
    """Rigori calciati."""
    assists: int
    """Assist."""
    yellow_cards: int
    """Ammonizioni."""
    red_cards: int
    """Espulsioni."""
    own_goals: int
    """Autogol."""

    @property
    def played(self) -> bool:
        """False per chi ha una riga di statistiche ma nessuna partita a voto."""
        return self.matches > 0

    def to_payload(self) -> dict[str, Any]:
        """Forma serializzabile, usata dal JSON del listone."""
        return {
            "matches": self.matches,
            "average": self.average,
            "fanta_average": self.fanta_average,
            "goals": self.goals,
            "goals_conceded": self.goals_conceded,
            "penalties_saved": self.penalties_saved,
            "penalties_taken": self.penalties_taken,
            "assists": self.assists,
            "yellow_cards": self.yellow_cards,
            "red_cards": self.red_cards,
            "own_goals": self.own_goals,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> PlayerStats:
        """Ricostruisce le statistiche dal JSON del listone."""
        return cls(
            matches=int(payload["matches"]),
            average=float(payload["average"]),
            fanta_average=float(payload["fanta_average"]),
            goals=int(payload["goals"]),
            goals_conceded=int(payload["goals_conceded"]),
            penalties_saved=int(payload["penalties_saved"]),
            penalties_taken=int(payload["penalties_taken"]),
            assists=int(payload["assists"]),
            yellow_cards=int(payload["yellow_cards"]),
            red_cards=int(payload["red_cards"]),
            own_goals=int(payload["own_goals"]),
        )


#: Etichette per esteso: nell'app non si mostrano mai gli acronimi del file.
STAT_LABEL: dict[str, str] = {
    "matches": "Partite a voto",
    "average": "Media voto",
    "fanta_average": "Fantamedia",
    "goals": "Gol fatti",
    "goals_conceded": "Gol subiti",
    "penalties_saved": "Rigori parati",
    "penalties_taken": "Rigori calciati",
    "assists": "Assist",
    "yellow_cards": "Ammonizioni",
    "red_cards": "Espulsioni",
    "own_goals": "Autogol",
}

#: Statistiche mostrate per ruolo, nell'ordine in cui hanno senso leggerle.
#: Un portiere si giudica sui gol subiti, un attaccante sui gol fatti.
STATS_BY_ROLE: dict[Role, tuple[str, ...]] = {
    Role.P: ("matches", "average", "fanta_average", "goals_conceded", "penalties_saved"),
    Role.D: ("matches", "average", "fanta_average", "goals", "assists"),
    Role.C: ("matches", "average", "fanta_average", "goals", "assists"),
    Role.A: ("matches", "average", "fanta_average", "goals", "assists"),
}

#: Statistiche mostrate nel riquadro dopo quelle principali, sempre, anche
#: quando valgono zero: uno zero e' un'informazione (nessun cartellino).
#: Gli autogol restano fuori: non hanno mai spostato un'offerta, e in una
#: riga che si legge a voce alta ogni voce in meno e' una voce guadagnata.
STATS_EXTRA: tuple[str, ...] = (
    "penalties_taken",
    "yellow_cards",
    "red_cards",
)

#: Tutte le statistiche, nell'ordine in cui si incolonnano nel listone:
#: prima il rendimento generale, poi il contributo offensivo, poi i numeri da
#: portiere, infine i cartellini. Nel listone ci sono tutte perche' la si
#: guarda dal computer, dove lo spazio non manca.
STATS_ALL: tuple[str, ...] = (
    "matches",
    "average",
    "fanta_average",
    "goals",
    "assists",
    "goals_conceded",
    "penalties_saved",
    "penalties_taken",
    "yellow_cards",
    "red_cards",
    "own_goals",
)

#: Simboli al posto del nome, dove si leggono a colpo d'occhio
#: meglio della parola. Il nome per esteso resta in :data:`STAT_LABEL` e viene
#: usato come tooltip.
STAT_SHORT: dict[str, str] = {
    "goals": "⚽",
    "assists": "👟",
    "yellow_cards": "🟨",
    "red_cards": "🟥",
}


class SetPiece(StrEnum):
    """Un tipo di calcio piazzato.

    Il valore e' anche il nome del campo in :class:`SetPieces`, cosi' si passa
    dall'uno all'altro senza tabelle di conversione.
    """

    PENALTY = "penalty"
    CORNER = "corner"
    FREE_KICK = "free_kick"


#: Ordine in cui si mostrano: rigori, corner, punizioni.
SET_PIECES_ALL: tuple[SetPiece, ...] = tuple(SetPiece)

#: La lettera che finisce sul riquadro e nel listone.
SET_PIECE_SHORT: dict[SetPiece, str] = {
    SetPiece.PENALTY: "R",
    SetPiece.CORNER: "C",
    SetPiece.FREE_KICK: "P",
}

SET_PIECE_LABEL: dict[SetPiece, str] = {
    SetPiece.PENALTY: "Rigori",
    SetPiece.CORNER: "Corner",
    SetPiece.FREE_KICK: "Punizioni",
}


class Confidence(StrEnum):
    """Quanto e' sicuro che un calciatore batta quel piazzato."""

    #: Le fonti non gli mettono davanti nessuno: rosso.
    SURE = "sure"
    #: E' in gerarchia ma se li gioca con altri, o e' un'alternativa: giallo.
    UNSURE = "unsure"


CONFIDENCE_LABEL: dict[Confidence, str] = {
    Confidence.SURE: "sicuro",
    Confidence.UNSURE: "possibile",
}


@dataclass(frozen=True, slots=True)
class SetPieces:
    """Piazzati battuti da un calciatore, con il grado di sicurezza.

    ``None`` su un campo significa che le gerarchie non lo nominano per quel
    piazzato: nell'app non compare nulla, che e' diverso da "non li batte".
    """

    penalty: Confidence | None = None
    corner: Confidence | None = None
    free_kick: Confidence | None = None

    def of(self, piece: SetPiece) -> Confidence | None:
        """Sicurezza su un piazzato, ``None`` se non e' fra i battitori."""
        value: Confidence | None = getattr(self, piece.value)
        return value

    def items(self) -> tuple[tuple[SetPiece, Confidence], ...]:
        """Solo i piazzati che batte, nell'ordine di :data:`SET_PIECES_ALL`."""
        return tuple(
            (piece, livello) for piece in SET_PIECES_ALL if (livello := self.of(piece)) is not None
        )

    def to_payload(self) -> dict[str, Any]:
        """Forma serializzabile: i campi vuoti non si scrivono nemmeno."""
        return {piece.value: livello.value for piece, livello in self.items()}

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> SetPieces:
        """Ricostruisce i piazzati dal JSON del listone, ignorando l'ignoto."""
        letti = {
            piece.value: Confidence(payload[piece.value])
            for piece in SET_PIECES_ALL
            if payload.get(piece.value)
        }
        return cls(**letti)


@dataclass(frozen=True, slots=True)
class Injury:
    """Un calciatore indisponibile, con la giornata di rientro prevista.

    ``matchday`` e' la giornata per cui l'articolo lo da' "in dubbio": manca
    quando non se ne sa la data, e in quel caso resta comunque l'informazione
    che conta, cioe' che adesso e' fuori.
    """

    matchday: int | None = None
    note: str = ""

    @property
    def label(self) -> str:
        """Etichetta breve: la giornata di rientro, o un trattino se ignota."""
        return f"{self.matchday}a" if self.matchday is not None else "—"

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.matchday is not None:
            payload["matchday"] = self.matchday
        payload["note"] = self.note
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> Injury:
        grezzo = payload.get("matchday")
        return cls(matchday=int(grezzo) if grezzo else None, note=str(payload.get("note", "")))


#: Emoji dell'infortunio: fa da intestazione nel listone e da simbolo nel
#: riquadro, come 🟨 e 🟥 per i cartellini.
INJURY_EMOJI = "🚑"


@dataclass(frozen=True, slots=True)
class Tier:
    """La fascia d'asta di un calciatore.

    ``rank`` e' la posizione nella graduatoria del reparto, contata
    dall'articolo: le fasce jolly (``JF``) e le scommesse (``FS``) stanno
    infilate fra le altre, quindi l'ordine delle sigle in alfabeto non
    direbbe niente. Con il rango la tabella si ordina come la graduatoria.
    """

    label: str
    rank: int = 0

    @classmethod
    def from_payload(cls, label: Any, rank: Any) -> Tier:
        return cls(label=str(label), rank=int(rank) if rank else 0)


class Starting(StrEnum):
    """Quanto e' probabile che un calciatore scenda in campo dall'inizio."""

    #: Nel suo posto in formazione non ha nessuno davanti: verde.
    STARTER = "starter"
    #: Se lo gioca con un altro nello stesso posto: giallo.
    CONTESTED = "contested"


STARTING_SHORT: dict[Starting, str] = {Starting.STARTER: "T", Starting.CONTESTED: "B"}

STARTING_LABEL: dict[Starting, str] = {
    Starting.STARTER: "Titolare",
    Starting.CONTESTED: "Ballottaggio",
}


@dataclass(frozen=True, slots=True)
class Player:
    """Un calciatore del listone."""

    id: int
    role: Role
    name: str
    team: str
    quotation: int
    fvm: int
    stats: PlayerStats | None = None
    #: Piazzati che batte, ``None`` se le gerarchie non lo nominano mai.
    set_pieces: SetPieces | None = None
    #: Titolarita', ``None`` se non compare nella formazione tipo.
    starter: Starting | None = None
    #: Infortunio in corso, ``None`` se e' disponibile.
    injury: Injury | None = None
    #: Fascia d'asta, ``None`` per chi gli articoli non elencano (i portieri
    #: non ne hanno affatto: per loro c'e' la pagina delle gerarchie).
    tier: Tier | None = None

    @property
    def initial(self) -> str:
        """Lettera usata per il sorteggio."""
        key = sort_key(self.name)
        return key[0] if key else "#"

    @property
    def key(self) -> str:
        """Chiave di ordinamento alfabetico."""
        return sort_key(self.name)

    @property
    def label(self) -> str:
        """Etichetta compatta ``Nome (Ruolo, Squadra)`` per i menu dell'admin."""
        return f"{self.name} ({self.role.value}, {self.team})"


@dataclass(frozen=True, slots=True)
class Listone:
    """Il listone completo, con gli indici precalcolati usati di continuo.

    Gli indici sono costruiti una volta sola alla creazione: durante l'asta
    ``by_id`` e ``by_role`` vengono interrogati a ogni rerun di Streamlit.
    """

    players: tuple[Player, ...]
    by_id: dict[int, Player] = field(init=False, repr=False, compare=False)
    _by_role: dict[Role, tuple[Player, ...]] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        index = {p.id: p for p in self.players}
        grouped = {
            role: tuple(sorted((p for p in self.players if p.role == role), key=lambda p: p.key))
            for role in ROLE_ORDER
        }
        # Il dataclass e' frozen: gli indici derivati si scrivono cosi'.
        object.__setattr__(self, "by_id", index)
        object.__setattr__(self, "_by_role", grouped)

    def get(self, player_id: int) -> Player:
        """Restituisce un calciatore per Id.

        Raises:
            KeyError: se l'Id non esiste nel listone.
        """
        try:
            return self.by_id[player_id]
        except KeyError:
            raise KeyError(f"Calciatore {player_id} assente dal listone") from None

    def by_role(self, role: Role) -> tuple[Player, ...]:
        """Calciatori di un ruolo, in ordine alfabetico."""
        return self._by_role.get(role, ())

    def search(self, query: str, role: Role | None = None) -> tuple[Player, ...]:
        """Cerca per nome o squadra, ignorando accenti e maiuscole."""
        needle = sort_key(query)
        pool = self.by_role(role) if role else self.players
        if not needle:
            return tuple(pool)
        return tuple(p for p in pool if needle in p.key or needle in sort_key(p.team))


def _read_triggers(raw: Any) -> tuple[BackupTrigger, ...]:
    """Momenti letti da un payload, scartando quelli che non riconosciamo.

    Un backup scritto da una versione futura non deve impedire di riaprire
    l'asta: i momenti sconosciuti spariscono e basta. L'ordine e' sempre
    quello dell'enum, cosi' due impostazioni uguali restano uguali.
    """
    if raw is None:
        return DEFAULT_BACKUP_TRIGGERS
    scelti = {str(v) for v in raw}
    return tuple(t for t in BackupTrigger if t.value in scelti)


@dataclass(frozen=True, slots=True)
class Settings:
    """Configurazione dell'asta, decisa prima di iniziare."""

    teams: tuple[str, ...]
    credits: int = DEFAULT_CREDITS
    roster_size: int = DEFAULT_ROSTER_SIZE
    role_limits: tuple[tuple[Role, int], ...] = tuple(DEFAULT_ROLE_LIMITS.items())
    mode: Mode = Mode.LETTER
    #: In chiamata libera, consenti solo calciatori del ruolo in asta.
    active_role_only: bool = True
    #: Scarica da solo il backup JSON nei momenti scelti in
    #: :attr:`backup_triggers`. Spento di default: un download che parte da
    #: solo va chiesto, non subito.
    auto_backup: bool = False
    #: Momenti in cui far partire il download automatico.
    backup_triggers: tuple[BackupTrigger, ...] = DEFAULT_BACKUP_TRIGGERS

    def backs_up(self, trigger: BackupTrigger) -> bool:
        """True se in quel momento il backup deve partire da solo."""
        return self.auto_backup and trigger in self.backup_triggers

    @property
    def limits(self) -> dict[Role, int]:
        """Limiti per ruolo come dizionario."""
        return dict(self.role_limits)

    def limit(self, role: Role) -> int:
        return self.limits.get(role, 0)

    def to_payload(self) -> dict[str, Any]:
        """Serializza le impostazioni per il payload di un evento."""
        return {
            "teams": list(self.teams),
            "credits": self.credits,
            "roster_size": self.roster_size,
            "role_limits": {r.value: n for r, n in self.role_limits},
            "mode": self.mode.value,
            "active_role_only": self.active_role_only,
            "auto_backup": self.auto_backup,
            "backup_triggers": [t.value for t in self.backup_triggers],
        }

    @staticmethod
    def from_payload(payload: Mapping[str, Any]) -> Settings:
        """Ricostruisce le impostazioni da un payload di evento.

        Tollerante: un payload incompleto ricade sui valori di default anziche'
        far fallire la ricostruzione dell'asta.
        """
        raw_limits: Mapping[str, Any] = payload.get("role_limits") or {}
        limits = tuple((Role(key), int(value)) for key, value in raw_limits.items())
        return Settings(
            teams=tuple(str(t) for t in (payload.get("teams") or [])),
            credits=int(payload.get("credits", DEFAULT_CREDITS)),
            roster_size=int(payload.get("roster_size", DEFAULT_ROSTER_SIZE)),
            role_limits=limits or tuple(DEFAULT_ROLE_LIMITS.items()),
            mode=Mode(str(payload.get("mode", Mode.LETTER.value))),
            active_role_only=bool(payload.get("active_role_only", True)),
            auto_backup=bool(payload.get("auto_backup", False)),
            backup_triggers=_read_triggers(payload.get("backup_triggers")),
        )


@dataclass(frozen=True, slots=True)
class Assignment:
    """Un calciatore aggiudicato a una squadra."""

    #: ``seq`` dell'evento PLAYER_ASSIGNED che l'ha creata: e' l'identita'
    #: stabile su cui agiscono modifica e rimozione.
    event_seq: int
    player_id: int
    team: str
    price: int
    role: Role


@dataclass(frozen=True, slots=True)
class TeamState:
    """Situazione di una squadra: rosa, crediti, slot."""

    name: str
    settings: Settings
    assignments: tuple[Assignment, ...] = field(default_factory=tuple)

    @property
    def spent(self) -> int:
        """Crediti gia' spesi."""
        return sum(a.price for a in self.assignments)

    @property
    def credits_left(self) -> int:
        """Crediti ancora disponibili."""
        return self.settings.credits - self.spent

    @property
    def size(self) -> int:
        """Calciatori attualmente in rosa."""
        return len(self.assignments)

    def count(self, role: Role) -> int:
        """Calciatori in rosa per un ruolo."""
        return sum(1 for a in self.assignments if a.role == role)

    def slots_left(self, role: Role) -> int:
        """Slot ancora liberi per un ruolo."""
        return self.settings.limit(role) - self.count(role)

    @property
    def roster_slots_left(self) -> int:
        """Slot ancora liberi in rosa."""
        return self.settings.roster_size - self.size

    @property
    def max_bid(self) -> int:
        """Offerta massima ammessa, riservando 1 credito per ogni slot residuo.

        Con 10 crediti e 3 slot da riempire si puo' offrire al massimo 8, cosi'
        restano 1+1 crediti per gli ultimi due calciatori. Se la rosa e' piena
        vale 0.
        """
        if self.roster_slots_left <= 0:
            return 0
        return self.credits_left - (self.roster_slots_left - 1)

    def max_bid_for(self, role: Role) -> int:
        """Offerta massima per uno specifico ruolo (0 se il reparto e' pieno)."""
        if self.slots_left(role) <= 0:
            return 0
        return self.max_bid

    @property
    def is_complete(self) -> bool:
        """True se la rosa e' completa in ogni reparto."""
        return all(self.slots_left(r) <= 0 for r in ROLE_ORDER) and self.roster_slots_left <= 0


@dataclass(frozen=True, slots=True)
class LineupSpot:
    """Un nome nella formazione tipo.

    ``player_id`` manca quando il nome dell'articolo non si aggancia a nessun
    calciatore del listone: capita con chi il listone non ce l'ha proprio. Il
    nome si mostra lo stesso, ma di lui non si sa se e' stato acquistato.

    Lo usano allo stesso modo la formazione tipo e le gerarchie in porta.
    """

    name: str
    player_id: int | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> LineupSpot:
        grezzo = payload.get("id")
        return cls(name=str(payload["name"]), player_id=int(grezzo) if grezzo else None)


#: Un posto in campo: un nome solo, oppure due in ballottaggio.
LineupSlot = tuple[LineupSpot, ...]
#: Un reparto: i posti in campo, da destra a sinistra come li scrive l'articolo.
LineupUnit = tuple[LineupSlot, ...]


@dataclass(frozen=True, slots=True)
class TeamLineup:
    """La formazione tipo di una squadra di Serie A.

    I reparti sono quelli separati dai punti e virgola nell'articolo: quanti
    sono dipende dal modulo, quindi non hanno un nome (un 3-4-2-1 ne ha quattro,
    un 4-3-3 anche, un 3-4-1-2 cinque). Si mostrano nell'ordine in cui sono
    scritti, dal portiere all'attacco.
    """

    team: str
    units: tuple[LineupUnit, ...] = ()

    @property
    def spots(self) -> tuple[LineupSpot, ...]:
        """Tutti i nomi della formazione, in ordine."""
        return tuple(spot for unit in self.units for slot in unit for spot in slot)

    @property
    def module(self) -> str:
        """Il modulo, contato dai reparti: ``4-3-3``, ``3-4-2-1``...

        Non c'e' bisogno di leggerlo dalla prosa dell'articolo, dove ogni
        squadra ne nomina due o tre fra provati e possibili: il modulo *e'*
        la forma della formazione tipo, cioe' quanti posti ha ogni reparto
        dopo il portiere.
        """
        return "-".join(str(len(unit)) for unit in self.units[1:])

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> TeamLineup:
        return cls(
            team=str(payload["team"]),
            units=tuple(
                tuple(tuple(LineupSpot.from_payload(spot) for spot in slot) for slot in unit)
                for unit in payload.get("units") or ()
            ),
        )


@dataclass(frozen=True, slots=True)
class KeeperRank:
    """La gerarchia in porta di una squadra.

    ``starters`` ha due nomi quando i portieri si giocano il posto davvero (il
    Como, dove l'allenatore ha chiesto due titolari); ``backup`` c'e' solo dove
    conviene comprare anche il vice, cioe' dove l'articolo lo dice. Nelle altre
    diciotto squadre il titolare e' uno e basta, e il vice sarebbe un credito
    buttato.
    """

    team: str
    starters: tuple[LineupSpot, ...] = ()
    backup: LineupSpot | None = None
    risky: bool = False
    note: str = ""
    #: Gol subiti dalla squadra nella stagione precedente. ``None`` per le
    #: neopromosse, che in Serie A non hanno giocato: mettere uno zero le
    #: farebbe sembrare le migliori difese del campionato.
    conceded: int | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> KeeperRank:
        vice = payload.get("backup")
        subiti = payload.get("conceded")
        return cls(
            team=str(payload["team"]),
            starters=tuple(LineupSpot.from_payload(s) for s in payload.get("starters") or ()),
            backup=LineupSpot.from_payload(vice) if vice else None,
            risky=bool(payload.get("risky")),
            note=str(payload.get("note", "")),
            conceded=int(subiti) if subiti is not None else None,
        )


@dataclass(frozen=True, slots=True)
class KeeperGrid:
    """La griglia delle coppie di portieri: un numero per ogni coppia di club.

    E' simmetrica e ha la diagonale vuota (una squadra con se stessa non e' una
    coppia). ``highlight_from`` e' la soglia da cui la griglia originale
    evidenzia il numero.
    """

    teams: tuple[str, ...] = ()
    values: tuple[tuple[int, ...], ...] = ()
    highlight_from: int = 0
    note: str = ""

    def value(self, row: int, col: int) -> int:
        """Valore della coppia, ``0`` sulla diagonale."""
        return self.values[row][col]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> KeeperGrid:
        return cls(
            teams=tuple(str(t) for t in payload.get("teams") or ()),
            values=tuple(tuple(int(v) for v in riga) for riga in payload.get("values") or ()),
            highlight_from=int(payload.get("highlight_from", 0)),
            note=str(payload.get("note", "")),
        )

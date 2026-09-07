"""Genera i dati di una demo pubblica: listone, griglia e un'asta a meta'.

    python scripts/genera_demo.py data

A cosa serve. L'app si puo' lasciare online come vetrina, ma **non con i dati
veri**: il listone e le statistiche sono di fantacalcio.it, le fasce e le
gerarchie vengono dagli articoli di chi le ha scritte, e un indirizzo pubblico
e' una forma di distribuzione piu' diretta di una repo, non meno. Un'app senza
listone pero' non mostra niente: si apre e c'e' un pannello che chiede di
caricare un file.

Da qui esce la terza strada: **calciatori inventati**. Nomi costruiti a tavolino
da sillabe, quotazioni e statistiche verosimili ma finte, fasce e formazioni
coerenti con quelle. Le squadre restano quelle vere - nominare l'Atalanta in uno
strumento da fantacalcio e' uso descrittivo, e cosi' gli stemmi funzionano - ma
non c'e' un solo calciatore reale, quindi non c'e' niente che appartenga a
qualcun altro.

Cosa scrive:

- ``players_2026_27.json``      il listone, dove l'app lo cerca gia' oggi
- ``griglia_portieri_2026_27.json``  la griglia delle coppie, simmetrica
- ``demo_eventi.json``          un'asta portata a meta', da cui la demo riparte

L'ultimo e' il pezzo che fa la differenza: senza database l'asta vive in memoria
e nasce vuota a ogni riavvio, quindi la demo direbbe "l'asta non e' ancora stata
configurata". Con quel file, ``wiring.get_repository`` la semina all'avvio - e
la demo **si ripara da sola**: qualunque cosa combini un visitatore sparisce al
riavvio successivo.

Il generatore e' deterministico: stesso seme, stessi file - comprese le date
dell'asta finta, che sono fissate e non prese dall'orologio. L'unica riga che
si muove a ogni rigenerazione e' ``exported_at`` del backup, che e' un campo
del formato e non nostro.
"""

from __future__ import annotations

import json
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from asta.data.players import load_listone  # noqa: E402
from asta.domain.events import Event, EventType  # noqa: E402
from asta.domain.export import backup_json  # noqa: E402
from asta.domain.models import (  # noqa: E402
    DEFAULT_CREDITS,
    DEFAULT_ROLE_LIMITS,
    DEFAULT_ROSTER_SIZE,
    Listone,
    Mode,
    Player,
    Role,
    Settings,
    sort_key,
)
from asta.domain.reducer import build_state  # noqa: E402
from asta.domain.rules import max_bid, validate_assignment  # noqa: E402

#: Il seme. Cambiarlo da' una demo diversa, non una demo migliore.
SEME = 2027

#: Quando si e' svolta l'asta finta. Fisso e non ``now()``: cosi' rigenerare i
#: file non sposta ottanta date nel diff. Una sera di fine agosto, che e'
#: quando le aste si fanno davvero.
QUANDO = datetime(2026, 8, 28, 20, 30, tzinfo=UTC)

#: Le squadre vere: i nomi sono uso descrittivo, e gli stemmi in
#: ``static/loghi/`` sono nominati cosi'.
SQUADRE = (
    "Atalanta",
    "Bologna",
    "Cagliari",
    "Como",
    "Fiorentina",
    "Frosinone",
    "Genoa",
    "Inter",
    "Juventus",
    "Lazio",
    "Lecce",
    "Milan",
    "Monza",
    "Napoli",
    "Parma",
    "Roma",
    "Sassuolo",
    "Torino",
    "Udinese",
    "Venezia",
)

#: I nomi si costruiscono da sillabe. Devono suonare plausibili e non essere
#: nessuno: 24 x 24 fa 576 combinazioni, piu' delle 480 che servono.
PREFISSI = (
    "Bar", "Bre", "Cal", "Cor", "Dal", "Dor", "Fen", "Gri", "Lus", "Mar", "Neb", "Ors",
    "Pav", "Qui", "Rol", "Sav", "Tor", "Ubi", "Val", "Zan", "Mel", "Nar", "Sel", "Ver",
)  # fmt: skip
SUFFISSI = (
    "betti", "cchi", "daro", "fani", "gori", "lini", "melli", "nesi", "ozzi", "pardi",
    "retti", "sini", "tani", "ussi", "valdi", "zeri", "bruni", "chesi", "dotti", "faro",
    "gnoli", "lucci", "moni", "rassi",
)  # fmt: skip

#: Quanti calciatori per squadra, ruolo per ruolo. Fa 24 x 20 = 480.
ROSA = {Role.P: 3, Role.D: 8, Role.C: 8, Role.A: 5}

#: Le fasce, dalla piu' cara alla piu' economica. Sono le stesse etichette
#: degli articoli veri, perche' sono etichette, non contenuto.
FASCE = ("F1", "F2", "F3", "F4", "F5", "F6", "F7")

#: Quotazione tipica del migliore e del peggiore di ogni ruolo.
QUOTAZIONI = {Role.P: (18, 1), Role.D: (22, 1), Role.C: (32, 1), Role.A: (40, 1)}

#: I moduli che la demo distribuisce fra le squadre.
MODULI = ((3, 4, 3), (4, 3, 3), (3, 5, 2), (4, 4, 2))

#: Le squadre dell'asta di esempio. Nomi di fantasia anche questi: la demo non
#: e' la lega di nessuno.
PARTECIPANTI = (
    "Real Panchina",
    "Atletico Divano",
    "Borussia Merenda",
    "Deportivo Rinvio",
    "Sporting Ammonito",
    "Union Fuorigioco",
    "Bayer Contropiede",
    "Olympique Recupero",
)


# --------------------------------------------------------------------- listone


def _nomi(rng: random.Random, quanti: int) -> list[str]:
    """Cognomi inventati, tutti diversi."""
    tutti = [p + s for p in PREFISSI for s in SUFFISSI]
    rng.shuffle(tutti)
    if quanti > len(tutti):
        raise ValueError(f"Servono {quanti} nomi ma le combinazioni sono {len(tutti)}.")
    return tutti[:quanti]


def _statistiche(rng: random.Random, role: Role, forza: float) -> dict[str, Any]:
    """Rendimenti verosimili: chi costa di piu' ha giocato di piu' e meglio.

    ``forza`` va da 0 (l'ultimo del reparto) a 1 (il primo).
    """
    partite = int(rng.triangular(2, 38, 6 + 30 * forza))
    media = round(rng.uniform(5.3, 5.6) + forza * rng.uniform(0.2, 0.9), 2)
    gol = 0
    if role is Role.A:
        gol = int(rng.triangular(0, 24, 2 + 16 * forza))
    elif role is Role.C:
        gol = int(rng.triangular(0, 12, 1 + 6 * forza))
    elif role is Role.D:
        gol = int(rng.triangular(0, 6, 3 * forza))
    assist = int(rng.triangular(0, 12, 1 + 6 * forza)) if role is not Role.P else 0
    subiti = int(rng.triangular(10, 70, 55 - 25 * forza)) if role is Role.P else 0
    parati = int(rng.triangular(0, 5, 2 * forza)) if role is Role.P else 0
    bonus = gol * 3 + assist - (subiti / max(partite, 1) if role is Role.P else 0)
    return {
        "matches": partite,
        "average": media,
        "fanta_average": round(media + bonus / max(partite, 1), 2),
        "goals": gol,
        "goals_conceded": subiti,
        "penalties_saved": parati,
        "penalties_taken": int(rng.triangular(0, 9, 5 * forza)) if role is Role.A else 0,
        "assists": assist,
        "yellow_cards": int(rng.triangular(0, 12, 3)),
        "red_cards": 1 if rng.random() < 0.06 else 0,
        "own_goals": 1 if rng.random() < 0.04 else 0,
    }


def _calciatori(rng: random.Random) -> list[dict[str, Any]]:
    """Il listone: venti squadre, ventiquattro calciatori l'una."""
    quanti = len(SQUADRE) * sum(ROSA.values())
    nomi = iter(_nomi(rng, quanti))
    giocatori: list[dict[str, Any]] = []
    identificativo = 1000

    for squadra in SQUADRE:
        for role, quantita in ROSA.items():
            alto, basso = QUOTAZIONI[role]
            for posto in range(quantita):
                # Il primo del reparto e' il piu' forte, l'ultimo il piu'
                # debole: cosi' fasce, titolarita' e quotazioni concordano.
                forza = 1 - posto / max(quantita - 1, 1)
                identificativo += 1
                nome = next(nomi)
                giocatore: dict[str, Any] = {
                    "id": identificativo,
                    "role": role.value,
                    "name": nome,
                    "team": squadra,
                    "quotation": max(basso, round(basso + (alto - basso) * forza**1.6)),
                    "fvm": max(1, round((basso + (alto - basso) * forza**1.6) * 2.6)),
                    "initial": sort_key(nome)[0],
                    "sort_key": sort_key(nome),
                    "stats": _statistiche(rng, role, forza),
                }
                if posto == 0:
                    giocatore["starter"] = "starter"
                elif posto == 1 and role is not Role.P:
                    giocatore["starter"] = "starter" if rng.random() < 0.7 else "contested"
                elif posto < quantita // 2:
                    giocatore["starter"] = "starter" if rng.random() < 0.4 else "contested"
                # I portieri non hanno fasce: per loro c'e' la pagina delle
                # gerarchie, com'e' nel listone vero.
                if role is not Role.P:
                    indice = min(int(posto / quantita * len(FASCE)), len(FASCE) - 1)
                    giocatore["tier"] = FASCE[indice]
                    giocatore["tier_rank"] = indice + 1
                giocatori.append(giocatore)
    _piazzati(rng, giocatori)
    _infortuni(rng, giocatori)
    return giocatori


def _piazzati(rng: random.Random, giocatori: list[dict[str, Any]]) -> None:
    """Rigoristi, corner e punizioni: uno o due per squadra, non di piu'."""
    for squadra in SQUADRE:
        candidati = [
            g
            for g in giocatori
            if g["team"] == squadra and g["role"] in {"C", "A"} and g.get("starter") == "starter"
        ]
        if not candidati:
            continue
        rigorista = candidati[0]
        rigorista["set_pieces"] = {"penalty": "sure" if rng.random() < 0.7 else "unsure"}
        if len(candidati) > 1:
            battitore = candidati[1]
            battitore["set_pieces"] = {
                "corner": "sure" if rng.random() < 0.6 else "unsure",
                "free_kick": "sure" if rng.random() < 0.5 else "unsure",
            }


def _infortuni(rng: random.Random, giocatori: list[dict[str, Any]]) -> None:
    """Qualche indisponibile, con la giornata di rientro."""
    motivi = (
        "Lesione di primo grado al bicipite femorale, rientro previsto",
        "Distorsione alla caviglia destra, in dubbio",
        "Affaticamento muscolare, out precauzionalmente",
        "Squalifica per somma di ammonizioni",
        "Problema al pube, valutazioni in corso",
    )
    for giocatore in giocatori:
        if rng.random() < 0.05:
            giocatore["injury"] = {
                "matchday": rng.randint(2, 14),
                "note": rng.choice(motivi),
            }


def _formazioni(rng: random.Random, giocatori: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Le formazioni tipo, nella forma che la pagina Formazioni si aspetta.

    Ogni squadra e' una lista di reparti; ogni reparto una lista di caselle;
    ogni casella i candidati per quel posto - due quando il posto e' conteso.
    """
    formazioni = []
    for indice, squadra in enumerate(SQUADRE):
        modulo = MODULI[indice % len(MODULI)]
        reparti = []
        for role, posti in zip((Role.D, Role.C, Role.A), modulo, strict=True):
            disponibili = [
                {"name": g["name"], "id": g["id"]}
                for g in giocatori
                if g["team"] == squadra and g["role"] == role.value
            ]
            caselle = []
            preso = 0
            for _ in range(posti):
                # Ogni tanto due nomi sullo stesso posto: e' il caso che la
                # pagina disegna in colonna, e senza non si vedrebbe mai.
                quanti = 2 if rng.random() < 0.25 and preso + 2 <= len(disponibili) else 1
                caselle.append(disponibili[preso : preso + quanti])
                preso += quanti
            reparti.append(caselle)
        portiere = next(
            {"name": g["name"], "id": g["id"]}
            for g in giocatori
            if g["team"] == squadra and g["role"] == "P"
        )
        formazioni.append({"team": squadra, "units": [[[portiere]], *reparti]})
    return formazioni


def _gerarchie(rng: random.Random, giocatori: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Chi para, e dove il posto e' in discussione."""
    note_sicure = (
        "Titolare senza discussioni, alle spalle nessuno che lo insidi.",
        "Confermato dopo una stagione da protagonista: si prende senza pensarci.",
    )
    note_rischiose = (
        "Ballottaggio aperto per tutto il precampionato: da prendere in coppia.",
        "L'allenatore non si e' sbilanciato, i due se la giocano fino a settembre.",
    )
    gerarchie = []
    for squadra in SQUADRE:
        portieri = [g for g in giocatori if g["team"] == squadra and g["role"] == "P"]
        rischio = rng.random() < 0.35
        gerarchie.append(
            {
                "team": squadra,
                "starters": [{"name": portieri[0]["name"], "id": portieri[0]["id"]}],
                "backup": (
                    {"name": portieri[1]["name"], "id": portieri[1]["id"]} if rischio else None
                ),
                "risky": rischio,
                "note": rng.choice(note_rischiose if rischio else note_sicure),
                "conceded": portieri[0]["stats"]["goals_conceded"],
            }
        )
    return gerarchie


def costruisci_listone(rng: random.Random) -> dict[str, Any]:
    """Il listone finto, nella stessa forma di quello di ``build_players``."""
    giocatori = _calciatori(rng)
    return {
        "source": "listone-demo (calciatori inventati)",
        "count": len(giocatori),
        "stats_source": "statistiche-demo",
        "with_stats": len(giocatori),
        "set_pieces_sources": ["piazzati-demo"],
        "with_set_pieces": sum(1 for g in giocatori if g.get("set_pieces")),
        "lineups_source": "formazioni-demo",
        "with_starter": sum(1 for g in giocatori if g.get("starter")),
        "lineups": _formazioni(rng, giocatori),
        "injuries_source": "indisponibili-demo",
        "with_injury": sum(1 for g in giocatori if g.get("injury")),
        "keepers_source": "gerarchie-demo",
        "keepers": _gerarchie(rng, giocatori),
        "tiers_sources": ["fasce-demo"],
        "with_tier": sum(1 for g in giocatori if g.get("tier")),
        "tiers": {ruolo: list(FASCE) for ruolo in ("D", "C", "A")},
        "players": giocatori,
    }


# --------------------------------------------------------------------- griglia


def costruisci_griglia(rng: random.Random) -> dict[str, Any]:
    """La griglia delle coppie: simmetrica, diagonale a zero.

    La simmetria non e' un vezzo: e' l'invariante che il caricamento controlla
    e che ``test_keepers`` verifica. Una griglia storta qui darebbe un avviso
    nella demo, che e' l'ultimo posto dove lo vogliamo.
    """
    lato = len(SQUADRE)
    valori = [[0] * lato for _ in range(lato)]
    for i in range(lato):
        for j in range(i + 1, lato):
            valori[i][j] = valori[j][i] = rng.randint(60, 99)
    return {
        "source": "griglia-demo",
        "note": "Griglia di esempio: i numeri sono inventati come i calciatori.",
        "highlight_from": 89,
        "teams": list(SQUADRE),
        "values": valori,
    }


# ------------------------------------------------------------------ l'asta finta


def costruisci_eventi(rng: random.Random, listone: Listone) -> list[Event]:
    """Un'asta portata a meta': i portieri finiti, i difensori in corso.

    Ogni aggiudicazione passa da ``validate_assignment``, la stessa funzione che
    ferma l'admin quando sbaglia: cosi' il log della demo e' legale per le
    regole dell'app, non per quelle che si ricorda chi scrive il generatore. Se
    nessuna squadra puo' prendersi un calciatore, viene saltato.

    Si ferma **subito dopo una lettera estratta**, senza aggiudicare: cosi' chi
    apre la demo trova il riquadro "in asta ora" pieno invece di un'attesa.
    """
    momento = QUANDO
    eventi: list[Event] = []

    def aggiungi(tipo: EventType, dati: dict[str, Any]) -> None:
        nonlocal momento
        momento += timedelta(seconds=rng.randint(20, 90))
        eventi.append(Event(seq=len(eventi) + 1, type=tipo, payload=dati, created_at=momento))

    impostazioni = Settings(
        teams=PARTECIPANTI,
        credits=DEFAULT_CREDITS,
        roster_size=DEFAULT_ROSTER_SIZE,
        role_limits=tuple(DEFAULT_ROLE_LIMITS.items()),
        mode=Mode.LETTER,
    )
    aggiungi(EventType.AUCTION_CONFIGURED, impostazioni.to_payload())

    def aggiudica(player: Player) -> bool:
        """Prova a darlo a chi ne ha meno, poi a chi ha piu' crediti."""
        stato = build_state(listone, eventi)
        candidate = sorted(
            stato.teams.values(),
            key=lambda squadra: (squadra.count(player.role), -squadra.credits_left),
        )
        for squadra in candidate:
            prezzo = max(
                1,
                min(
                    max_bid(stato, squadra.name),
                    round(player.quotation * rng.uniform(0.8, 1.9)),
                ),
            )
            if validate_assignment(stato, player, squadra.name, prezzo) is None:
                aggiungi(
                    EventType.PLAYER_ASSIGNED,
                    {"player_id": player.id, "team": squadra.name, "price": prezzo},
                )
                return True
        return False

    def pieno(role: Role) -> bool:
        stato = build_state(listone, eventi)
        return all(squadra.slots_left(role) == 0 for squadra in stato.teams.values())

    def fase(role: Role, fino_a_riempire: bool, lettere_prima_di_fermarsi: int = 0) -> None:
        aggiungi(EventType.ROLE_PHASE_STARTED, {"role": role.value})
        lettere = sorted({p.initial for p in listone.by_role(role)})
        rng.shuffle(lettere)
        for numero, lettera in enumerate(lettere, start=1):
            aggiungi(
                EventType.LETTER_DRAWN,
                {"role": role.value, "letter": lettera, "seed": rng.randint(1, 10**6)},
            )
            if not fino_a_riempire and numero > lettere_prima_di_fermarsi:
                # L'ultima lettera resta aperta: e' il calciatore in asta.
                return
            in_lettera = [p for p in listone.by_role(role) if p.initial == lettera]
            for player in sorted(in_lettera, key=lambda p: (-p.quotation, p.key)):
                if rng.random() < 0.12:
                    aggiungi(EventType.PLAYER_SKIPPED, {"player_id": player.id})
                    continue
                aggiudica(player)
            if fino_a_riempire and pieno(role):
                return

    fase(Role.P, fino_a_riempire=True)
    fase(Role.D, fino_a_riempire=False, lettere_prima_di_fermarsi=3)

    # Un'aggiudicazione annullata con l'undo: il log tiene traccia anche di
    # quello che e' stato disfatto, e la pagina delle correzioni lo mostra.
    for evento in reversed(eventi):
        if evento.type is EventType.PLAYER_ASSIGNED:
            eventi[evento.seq - 1] = evento.deactivated()
            break
    return eventi


# ----------------------------------------------------------------------- scrittura


def _scrivi(percorso: Path, contenuto: str) -> None:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(contenuto, encoding="utf-8")


#: I tre file che compongono la demo.
FILE = ("players_2026_27.json", "griglia_portieri_2026_27.json", "demo_eventi.json")


def genera(destinazione: Path, sovrascrivi: bool = False, seme: int = SEME) -> list[Path]:
    """Scrive i tre file della demo e restituisce i percorsi.

    I controlli sull'esistenza si fanno **tutti prima** di scrivere: meglio non
    fare niente che lasciare una demo a meta' - e soprattutto meglio non
    sovrascrivere il listone vero a meta' strada.
    """
    percorsi = [destinazione / nome for nome in FILE]
    if not sovrascrivi:
        for percorso in percorsi:
            if percorso.exists():
                raise FileExistsError(
                    f"{percorso} esiste gia'. Non lo tocco: se e' il listone vero lo "
                    "perderesti. Usa --sovrascrivi se sei sicuro."
                )

    rng = random.Random(seme)
    _scrivi(percorsi[0], json.dumps(costruisci_listone(rng), ensure_ascii=False, indent=1) + "\n")
    _scrivi(percorsi[1], json.dumps(costruisci_griglia(rng), ensure_ascii=False, indent=1) + "\n")
    # Riletto col lettore vero, non riusato dalla memoria: se il payload
    # generato non fosse valido, si scopre qui e non davanti al primo
    # visitatore.
    eventi = costruisci_eventi(rng, load_listone(percorsi[0]))
    _scrivi(percorsi[2], backup_json(eventi))
    return percorsi


def _riassunto(destinazione: Path) -> str:
    """Cosa e' venuto fuori, controllato ripiegando davvero il log."""
    from asta.domain.export import restore_events

    listone = load_listone(destinazione / "players_2026_27.json")
    eventi = restore_events((destinazione / "demo_eventi.json").read_text(encoding="utf-8"))
    stato = build_state(listone, eventi)
    venduti = len(stato.taken)
    return (
        f"{len(listone.players)} calciatori in {len(SQUADRE)} squadre, "
        f"{len(eventi)} eventi, {venduti} aggiudicazioni fra "
        f"{len(PARTECIPANTI)} partecipanti."
    )


def main(argv: list[str] | None = None) -> int:
    argomenti = list(argv if argv is not None else sys.argv[1:])
    sovrascrivi = "--sovrascrivi" in argomenti
    percorsi = [a for a in argomenti if not a.startswith("-")]
    if len(percorsi) != 1:
        print(__doc__)
        return 2

    destinazione = Path(percorsi[0]).expanduser().resolve()
    try:
        scritti = genera(destinazione, sovrascrivi=sovrascrivi)
    except FileExistsError as exc:
        print(exc)
        return 1

    print(f"Scritti in {destinazione}:")
    for percorso in scritti:
        print(f"  {percorso.name}")
    print(_riassunto(destinazione))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Converte il listone ufficiale (.xlsx) nel JSON usato dall'app.

Il file Excel di fantacalcio.it viene letto con la sola libreria standard
(``zipfile`` + ``xml.etree``): un .xlsx e' uno zip di XML, quindi non serve
installare openpyxl/pandas per questo passaggio. Il JSON prodotto viene
committato nella repo, cosi' l'app in produzione non deve mai toccare l'Excel.

Uso normale (nessun argomento: trova da solo il listone in ``data/raw/``)::

    python scripts/build_players.py            # mostra le differenze e scrive
    python scripts/build_players.py --dry-run  # mostra e basta
    python scripts/build_players.py --check    # esce con 1 se il JSON e' vecchio

``--check`` e' anche un test (``tests/test_players.py``): se qualcuno aggiorna
l'Excel e dimentica di rigenerare il JSON, la suite diventa rossa invece di
scoprirlo la sera dell'asta.

Il foglio ``Ceduti`` (giocatori usciti dalla Serie A) viene ignorato: quei
calciatori non sono astabili.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

#: Intestazione attesa del listone. Se cambia, meglio fallire subito che
#: importare dati disallineati.
EXPECTED_HEADER = [
    "Id",
    "R",
    "RM",
    "Nome",
    "Squadra",
    "Qt.A",
    "Qt.I",
    "Diff.",
    "Qt.A M",
    "Qt.I M",
    "Diff.M",
    "FVM",
    "FVM M",
]

#: Intestazione attesa del file delle statistiche. ``R+`` e ``R-`` esistono ma
#: non servono: sono rigori a favore/contro gia' contati altrove.
EXPECTED_STATS_HEADER = [
    "Id",
    "R",
    "Rm",
    "Nome",
    "Squadra",
    "Pv",
    "Mv",
    "Fm",
    "Gf",
    "Gs",
    "Rp",
    "Rc",
    "R+",
    "R-",
    "Ass",
    "Amm",
    "Esp",
    "Au",
]

#: Colonna del file statistiche -> campo di ``PlayerStats``.
STATS_FIELDS = {
    "Pv": "matches",
    "Mv": "average",
    "Fm": "fanta_average",
    "Gf": "goals",
    "Gs": "goals_conceded",
    "Rp": "penalties_saved",
    "Rc": "penalties_taken",
    "Ass": "assists",
    "Amm": "yellow_cards",
    "Esp": "red_cards",
    "Au": "own_goals",
}

#: Campi con la virgola: media voto e fantamedia.
STATS_FLOATS = {"average", "fanta_average"}

VALID_ROLES = {"P", "D", "C", "A"}


def sort_key(name: str) -> str:
    """Chiave di ordinamento alfabetico robusta ad accenti e apostrofi.

    ``Zalewski`` e ``Zaleski``, ``D'Ambrosio`` e ``Dambrosio`` devono finire
    dove un umano se li aspetta, quindi si normalizza in NFKD, si rimuovono i
    diacritici e si tengono solo i caratteri alfanumerici.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return "".join(c for c in stripped.upper() if c.isalnum())


def initial(name: str) -> str:
    """Lettera iniziale usata per il sorteggio (A-Z, senza accenti)."""
    key = sort_key(name)
    return key[0] if key else "#"


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    """Tabella delle stringhe condivise dell'xlsx (le celle testuali vi puntano)."""
    try:
        raw = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(raw)
    return ["".join(t.text or "" for t in si.iter(NS + "t")) for si in root]


def _sheet_paths(zf: zipfile.ZipFile) -> dict[str, str]:
    """Mappa ``nome foglio -> path interno allo zip``."""
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rel_ns = "{http://schemas.openxmlformats.org/package/2006/relationships}"
    rid_to_target = {
        rel.get("Id"): rel.get("Target", "") for rel in rels.iter(rel_ns + "Relationship")
    }
    r_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    out: dict[str, str] = {}
    for sheet in workbook.iter(NS + "sheet"):
        target = rid_to_target.get(sheet.get(r_ns + "id", ""), "")
        name = sheet.get("name")
        if name and target:
            out[name] = "xl/" + target.lstrip("/")
    return out


def _rows(zf: zipfile.ZipFile, path: str, strings: list[str]) -> list[list[str]]:
    """Legge un foglio come lista di righe di stringhe."""
    root = ET.fromstring(zf.read(path))
    rows: list[list[str]] = []
    for row in root.iter(NS + "row"):
        values: list[str] = []
        for cell in row.iter(NS + "c"):
            v = cell.find(NS + "v")
            if v is None or v.text is None:
                values.append("")
            elif cell.get("t") == "s":
                values.append(strings[int(v.text)])
            else:
                values.append(v.text)
        rows.append(values)
    return rows


def parse_listone(xlsx_path: Path) -> list[dict[str, Any]]:
    """Estrae i calciatori astabili dal listone.

    Returns:
        Lista di dizionari ordinata per ruolo (P, D, C, A) e poi per nome.

    Raises:
        ValueError: se l'intestazione non corrisponde a quella attesa, se un
            Id e' duplicato o se un ruolo non e' fra P/D/C/A.
    """
    with zipfile.ZipFile(xlsx_path) as zf:
        strings = _shared_strings(zf)
        paths = _sheet_paths(zf)
        if "Tutti" not in paths:
            raise ValueError(f"Foglio 'Tutti' assente in {xlsx_path.name}")
        rows = _rows(zf, paths["Tutti"], strings)
        ceduti_ids: set[str] = set()
        if "Ceduti" in paths:
            ceduti_ids = {r[0] for r in _rows(zf, paths["Ceduti"], strings)[2:] if r and r[0]}

    # Riga 0 = titolo del listone, riga 1 = intestazione, dalla 2 i giocatori.
    header = rows[1][: len(EXPECTED_HEADER)]
    if header != EXPECTED_HEADER:
        raise ValueError(f"Intestazione inattesa: {header}")

    players: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in rows[2:]:
        if not row or not row[0]:
            continue
        if row[0] in ceduti_ids:
            continue
        role = row[1]
        if role not in VALID_ROLES:
            raise ValueError(f"Ruolo non valido '{role}' per il giocatore {row[3]!r}")
        pid = int(row[0])
        if pid in seen:
            raise ValueError(f"Id duplicato nel listone: {pid}")
        seen.add(pid)
        players.append(
            {
                "id": pid,
                "role": role,
                "name": row[3],
                "team": row[4],
                "quotation": int(row[5] or 0),
                "fvm": int(row[11] or 0),
                "initial": initial(row[3]),
                "sort_key": sort_key(row[3]),
            }
        )

    role_order = {"P": 0, "D": 1, "C": 2, "A": 3}
    players.sort(key=lambda p: (role_order[p["role"]], p["sort_key"]))
    return players


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
DEFAULT_OUT = ROOT / "data" / "players_2026_27.json"

#: I listoni ufficiali si chiamano tutti ``Quotazioni_Fantacalcio_...``; il
#: glob evita di pescare per sbaglio le statistiche o altri file nella cartella.
XLSX_GLOB = "Quotazioni_*.xlsx"

#: Le statistiche della stagione precedente, facoltative: senza il file l'app
#: funziona lo stesso, semplicemente non mostra i rendimenti.
STATS_GLOB = "Statistiche_*.xlsx"

#: Le gerarchie dei calci piazzati, anch'esse facoltative. Sono due articoli
#: in markdown copiati dal web: il primo sui rigoristi, il secondo su corner e
#: punizioni. Vedi :func:`parse_penalties` per come vengono letti.
PENALTIES_GLOB = "rigoristi_*.md"
SET_PIECES_GLOB = "corner_e_punizioni_*.md"

#: Le probabili formazioni, sempre facoltative: un altro articolo copiato dal
#: web, con la formazione tipo di ogni squadra e i ballottaggi.
LINEUPS_GLOB = "probabili_formazioni*.md"

#: Gli indisponibili, anch'essi facoltativi: la tabella degli infortunati con
#: la giornata di rientro prevista.
INJURIES_GLOB = "infortunati*.md"

#: Le gerarchie in porta: primo, secondo e terzo portiere di ogni squadra.
KEEPERS_GLOB = "portieri*.md"

#: Le fasce d'asta, un articolo per reparto. I portieri non ce l'hanno: per
#: loro c'e' gia' la pagina con le gerarchie.
TIERS_GLOBS: dict[str, str] = {
    "D": "difensori*.md",
    "C": "centrocampisti*.md",
    "A": "attaccanti*.md",
}

#: Frasi con cui l'articolo dice che il posto non e' assegnato e che al
#: fantacalcio conviene prendere anche il vice. Sono poche e testuali di
#: proposito: e' una regola che si legge, non un giudizio nostro.
KEEPER_RISK_HINTS = (
    "entrambi",
    "la coppia",
    "gerarchia da definire",
    "apertissima",
)

#: Un nome trovato nelle gerarchie: ``(squadra, nome, piazzato, sicurezza)``.
Mention = tuple[str, str, str, str]

#: Oltre questo numero di parole un grassetto non e' un nome ma una frase
#: enfatizzata ("**Se li proviamo e io decido che li batte Ostigard...**").
MAX_PAROLE_NOME = 3


def candidati(raw_dir: Path, glob: str) -> list[Path]:
    """File che corrispondono a un glob, dall'ultimo al primo in ordine di nome.

    I nomi ufficiali finiscono con la stagione (``..._2026_27.xlsx``), quindi
    l'ordine alfabetico inverso mette davanti la piu' recente.

    La data di modifica sarebbe piu' intuitiva ma non e' riproducibile: in una
    copia appena clonata le date sono quelle del checkout, cioe' un ordine che
    cambia da macchina a macchina. Il JSON committato viene confrontato byte
    per byte con quello che si rigenera qui, e con due file che corrispondono
    allo stesso glob il confronto diventava verde in locale e rosso in CI.
    """
    return sorted(raw_dir.glob(glob), key=lambda f: f.name.casefold(), reverse=True)


def find_xlsx(raw_dir: Path = RAW_DIR) -> Path:
    """Trova il listone da convertire dentro ``raw_dir``.

    Con piu' di un candidato vince l'ultimo in ordine di nome, che per i file
    ufficiali vuol dire la stagione piu' recente: al cambio di listone si
    lascia cadere il file nuovo nella cartella e non si tocca altro.

    Raises:
        FileNotFoundError: se nella cartella non c'e' nessun listone.
    """
    candidates = candidati(raw_dir, XLSX_GLOB)
    if not candidates:
        raise FileNotFoundError(
            f"Nessun listone trovato in {raw_dir}/ (cerco {XLSX_GLOB}).\n"
            f"Copia li' l'xlsx scaricato da fantacalcio.it e rilancia."
        )
    return candidates[0]


def build_payload(
    xlsx_path: Path,
    stats_path: Path | None = None,
    penalties_path: Path | None = None,
    set_pieces_path: Path | None = None,
    lineups_path: Path | None = None,
    injuries_path: Path | None = None,
    keepers_path: Path | None = None,
    tiers_paths: dict[str, Path] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Contenuto completo del JSON: listone, statistiche, piazzati, formazioni.

    Args:
        xlsx_path: il listone ufficiale.
        stats_path: le statistiche della stagione precedente; facoltative.
        penalties_path: l'articolo sui rigoristi; facoltativo.
        set_pieces_path: l'articolo su corner e punizioni; facoltativo.
        lineups_path: l'articolo delle probabili formazioni; facoltativo.
        injuries_path: la tabella degli indisponibili; facoltativa.
        keepers_path: le gerarchie dei portieri; facoltative.
        tiers_paths: gli articoli delle fasce, uno per reparto; facoltativi.

    Returns:
        Il payload da scrivere e le eventuali segnalazioni sui nomi.
    """
    players = parse_listone(xlsx_path)
    payload: dict[str, Any] = {"source": xlsx_path.name, "count": len(players)}
    sospetti: list[str] = []
    subiti: dict[str, int] = {}
    if stats_path is not None:
        statistiche = parse_stats(stats_path)
        abbinati, sospetti = merge_stats(players, statistiche)
        payload["stats_source"] = stats_path.name
        payload["with_stats"] = abbinati
        subiti = team_goals_conceded(statistiche)

    mentions: list[Mention] = []
    sorgenti: list[str] = []
    if penalties_path is not None:
        mentions += parse_penalties(penalties_path)
        sorgenti.append(penalties_path.name)
    if set_pieces_path is not None:
        mentions += parse_set_pieces(set_pieces_path)
        sorgenti.append(set_pieces_path.name)
    if sorgenti:
        battitori, dubbi = merge_set_pieces(players, mentions)
        payload["set_pieces_sources"] = sorgenti
        payload["with_set_pieces"] = battitori
        sospetti += dubbi

    if lineups_path is not None:
        formazioni, titolari, dubbi = merge_lineups(players, parse_lineups(lineups_path))
        payload["lineups_source"] = lineups_path.name
        payload["with_starter"] = titolari
        payload["lineups"] = formazioni
        sospetti += dubbi

    if injuries_path is not None:
        fuori, dubbi = merge_injuries(players, parse_injuries(injuries_path))
        payload["injuries_source"] = injuries_path.name
        payload["with_injury"] = fuori
        sospetti += dubbi

    if keepers_path is not None:
        gerarchie, dubbi = merge_keepers(players, parse_keepers(keepers_path), subiti)
        payload["keepers_source"] = keepers_path.name
        payload["keepers"] = gerarchie
        sospetti += dubbi

    if tiers_paths:
        per_ruolo = {ruolo: parse_tiers(percorso) for ruolo, percorso in tiers_paths.items()}
        con_fascia, dubbi = merge_tiers(players, per_ruolo)
        payload["tiers_sources"] = [p.name for p in tiers_paths.values()]
        payload["with_tier"] = con_fascia
        # La graduatoria di ogni reparto, nell'ordine dell'articolo: serve
        # all'app per ordinare e per il menu del filtro.
        payload["tiers"] = {ruolo: [f for f, _ in fasce] for ruolo, fasce in per_ruolo.items()}
        sospetti += dubbi

    payload["players"] = players
    return payload, sospetti


def render_payload(payload: dict[str, Any]) -> str:
    """Serializza il JSON esattamente come viene scritto su disco."""
    return json.dumps(payload, ensure_ascii=False, indent=1) + "\n"


def _by_id(payload: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {int(p["id"]): p for p in payload["players"]}


def describe_changes(old: dict[str, Any] | None, new: dict[str, Any]) -> list[str]:
    """Righe leggibili con le differenze fra il JSON attuale e quello nuovo.

    Serve a rispondere alla domanda che ci si fa davvero quando arriva il
    listone definitivo: *cos'e' cambiato?* Una lista vuota significa nessuna
    differenza.
    """
    if old is None:
        return [f"Primo listone: {new['count']} calciatori."]

    vecchi, nuovi = _by_id(old), _by_id(new)
    aggiunti = [nuovi[i] for i in nuovi.keys() - vecchi.keys()]
    rimossi = [vecchi[i] for i in vecchi.keys() - nuovi.keys()]
    campi = ("name", "team", "role", "quotation", "fvm")
    modificati = [
        (vecchi[i], nuovi[i])
        for i in vecchi.keys() & nuovi.keys()
        if any(vecchi[i].get(c) != nuovi[i].get(c) for c in campi)
    ]

    con_stat_prima = sum(1 for p in vecchi.values() if p.get("stats"))
    con_stat_dopo = sum(1 for p in nuovi.values() if p.get("stats"))
    stat_cambiate = sum(
        1 for i in vecchi.keys() & nuovi.keys() if vecchi[i].get("stats") != nuovi[i].get("stats")
    )
    piazzati_prima = sum(1 for p in vecchi.values() if p.get("set_pieces"))
    piazzati_dopo = sum(1 for p in nuovi.values() if p.get("set_pieces"))
    piazzati_cambiati = sum(
        1
        for i in vecchi.keys() & nuovi.keys()
        if vecchi[i].get("set_pieces") != nuovi[i].get("set_pieces")
    )

    righe: list[str] = []
    if old.get("source") != new.get("source"):
        righe.append(f"Sorgente: {old.get('source')} -> {new.get('source')}")
    if old.get("stats_source") != new.get("stats_source"):
        righe.append(
            f"Statistiche: {old.get('stats_source') or 'nessuna'} -> "
            f"{new.get('stats_source') or 'nessuna'}"
        )
    if con_stat_prima != con_stat_dopo or stat_cambiate:
        righe.append(
            f"Rendimenti: {con_stat_prima} -> {con_stat_dopo} calciatori "
            f"({stat_cambiate} righe cambiate)"
        )
    if old.get("set_pieces_sources") != new.get("set_pieces_sources"):
        righe.append(
            f"Piazzati: {', '.join(old.get('set_pieces_sources') or ['nessuno'])} -> "
            f"{', '.join(new.get('set_pieces_sources') or ['nessuno'])}"
        )
    if old.get("injuries_source") != new.get("injuries_source") or sum(
        1 for i in vecchi.keys() & nuovi.keys() if vecchi[i].get("injury") != nuovi[i].get("injury")
    ):
        righe.append(
            f"Infortuni: {sum(1 for p in vecchi.values() if p.get('injury'))} -> "
            f"{sum(1 for p in nuovi.values() if p.get('injury'))} indisponibili"
        )
    con_fascia_prima = sum(1 for p in vecchi.values() if p.get("tier"))
    con_fascia_dopo = sum(1 for p in nuovi.values() if p.get("tier"))
    fasce_cambiate = sum(
        1 for i in vecchi.keys() & nuovi.keys() if vecchi[i].get("tier") != nuovi[i].get("tier")
    )
    if con_fascia_prima != con_fascia_dopo or fasce_cambiate:
        righe.append(
            f"Fasce: {con_fascia_prima} -> {con_fascia_dopo} calciatori "
            f"({fasce_cambiate} righe cambiate)"
        )
    if old.get("keepers") != new.get("keepers"):
        incerte = sum(1 for g in new.get("keepers") or [] if g["risky"])
        righe.append(
            f"Portieri: {len(new.get('keepers') or [])} gerarchie, {incerte} in discussione"
        )
    if old.get("lineups_source") != new.get("lineups_source"):
        righe.append(
            f"Formazioni: {old.get('lineups_source') or 'nessuna'} -> "
            f"{new.get('lineups_source') or 'nessuna'}"
        )
    if old.get("lineups") != new.get("lineups"):
        righe.append(
            f"Titolari: {sum(1 for p in vecchi.values() if p.get('starter'))} -> "
            f"{sum(1 for p in nuovi.values() if p.get('starter'))} calciatori"
        )
    if piazzati_prima != piazzati_dopo or piazzati_cambiati:
        righe.append(
            f"Battitori: {piazzati_prima} -> {piazzati_dopo} calciatori "
            f"({piazzati_cambiati} righe cambiate)"
        )
    for etichetta, gruppo in (("Nuovi", aggiunti), ("Usciti", rimossi)):
        if gruppo:
            gruppo.sort(key=lambda p: (p["role"], p["sort_key"]))
            righe.append(f"{etichetta} ({len(gruppo)}): " + _elenco(gruppo))
    if modificati:
        righe.append(f"Modificati ({len(modificati)}):")
    for prima, dopo in sorted(modificati, key=lambda c: (c[1]["role"], c[1]["sort_key"])):
        for campo in campi:
            if prima.get(campo) != dopo.get(campo):
                righe.append(
                    f"  {dopo['name']} ({dopo['team']}): "
                    f"{campo} {prima.get(campo)} -> {dopo.get(campo)}"
                )
    return righe


def _elenco(players: list[dict[str, Any]], limite: int = 12) -> str:
    """Nomi separati da virgola, troncati per non allagare il terminale."""
    nomi = [f"{p['name']} ({p['role']}, {p['team']})" for p in players[:limite]]
    resto = len(players) - limite
    return ", ".join(nomi) + (f" e altri {resto}" if resto > 0 else "")


def _relativo(path: Path) -> str:
    """Path accorciato alla radice della repo, quando ci sta dentro."""
    return str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)


def _conteggi(payload: dict[str, Any]) -> str:
    counts: dict[str, int] = {}
    for p in payload["players"]:
        counts[p["role"]] = counts.get(p["role"], 0) + 1
    return "  ".join(f"{r}: {counts.get(r, 0)}" for r in "PDCA")


def parse_stats(xlsx_path: Path) -> dict[int, dict[str, Any]]:
    """Estrae le statistiche della stagione precedente, indicizzate per Id.

    Il file copre solo chi ha giocato in Serie A, quindi contiene meno
    calciatori del listone (e anche parecchi che dal listone sono usciti).

    Raises:
        ValueError: se l'intestazione non e' quella attesa.
    """
    with zipfile.ZipFile(xlsx_path) as zf:
        strings = _shared_strings(zf)
        paths = _sheet_paths(zf)
        if "Tutti" not in paths:
            raise ValueError(f"Foglio 'Tutti' assente in {xlsx_path.name}")
        rows = _rows(zf, paths["Tutti"], strings)

    header = rows[1][: len(EXPECTED_STATS_HEADER)]
    if header != EXPECTED_STATS_HEADER:
        raise ValueError(f"Intestazione statistiche inattesa: {header}")
    col = {name: i for i, name in enumerate(header)}

    out: dict[int, dict[str, Any]] = {}
    for row in rows[2:]:
        if not row or not row[0]:
            continue
        record: dict[str, Any] = {
            "_name": row[col["Nome"]],
            "_team": row[col["Squadra"]],
            "_role": row[col["R"]],
        }
        for colonna, campo in STATS_FIELDS.items():
            raw = row[col[colonna]] if col[colonna] < len(row) else ""
            record[campo] = float(raw or 0) if campo in STATS_FLOATS else int(float(raw or 0))
        out[int(row[0])] = record
    return out


def team_goals_conceded(stats: dict[int, dict[str, Any]]) -> dict[str, int]:
    """Gol subiti da ogni squadra nella stagione delle statistiche.

    Si sommano i gol subiti dai suoi portieri: ognuno porta quelli presi
    mentre giocava lui, quindi il totale della squadra e' la loro somma. La
    squadra e' quella scritta nel file delle statistiche, cioe' quella
    dell'anno scorso: un portiere che ha cambiato maglia non deve portarsi i
    gol nella squadra nuova.

    Le neopromosse non compaiono: in Serie A non hanno giocato.
    """
    subiti: dict[str, int] = {}
    for record in stats.values():
        if record.get("_role") != "P":
            continue
        subiti[record["_team"]] = subiti.get(record["_team"], 0) + int(record["goals_conceded"])
    return subiti


def merge_stats(
    players: list[dict[str, Any]], stats: dict[int, dict[str, Any]]
) -> tuple[int, list[str]]:
    """Attacca le statistiche ai calciatori del listone, controllando i nomi.

    Il join e' sull'Id, ma un Id riciclato fra due stagioni assegnerebbe in
    silenzio le statistiche sbagliate: per questo si confrontano anche i nomi.
    Sono ammesse le differenze di iniziale (``El Azzouzi`` -> ``El Azzouzi
    O.``), che il listone aggiunge quando compaiono omonimi.

    Returns:
        Quanti calciatori hanno ricevuto le statistiche e la lista dei nomi
        sospetti.

    Raises:
        ValueError: se i nomi discordi sono piu' del 5%, segno che il file
            delle statistiche non e' quello di questo listone.
    """
    abbinati = 0
    sospetti: list[str] = []
    for player in players:
        record = stats.get(player["id"])
        if record is None:
            player.pop("stats", None)
            continue
        atteso, trovato = sort_key(player["name"]), sort_key(record["_name"])
        if not (atteso.startswith(trovato) or trovato.startswith(atteso)):
            sospetti.append(
                f"Id {player['id']}: listone {player['name']!r} != statistiche {record['_name']!r}"
            )
        player["stats"] = {k: v for k, v in record.items() if not k.startswith("_")}
        abbinati += 1

    if abbinati and len(sospetti) > abbinati * 0.05:
        raise ValueError(
            f"{len(sospetti)} nomi su {abbinati} non corrispondono: "
            f"il file delle statistiche non sembra riferito a questo listone.\n  "
            + "\n  ".join(sospetti[:10])
        )
    return abbinati, sospetti


# --------------------------------------------------------------- piazzati


def _sezioni(testo: str, marcatore: str) -> list[tuple[str, str]]:
    """Spezza l'articolo in ``(squadra, corpo)``.

    Ogni squadra apre con una riga tipo ``🎯 **ATALANTA**``: il marcatore
    cambia da un articolo all'altro, il resto no.
    """
    pezzi = re.split(rf"^{marcatore} \*\*(.+?)\*\*\s*$", testo, flags=re.M)[1:]
    return list(zip(pezzi[0::2], pezzi[1::2], strict=True))


def _paragrafo(corpo: str, etichetta: str) -> str:
    """Testo del paragrafo ``*Etichetta*: ...``, vuoto se non c'e'."""
    trovato = re.search(rf"^\*{etichetta}\*:(.*?)(?=^\*|\Z)", corpo, flags=re.M | re.S)
    return trovato.group(1) if trovato else ""


def _nomi_in_grassetto(testo: str) -> list[str]:
    """Nomi evidenziati in un paragrafo.

    L'articolo mette in grassetto i nomi che contano davvero e lascia in tondo
    quelli citati di sfuggita ("occhio a Ferguson"): il grassetto e' quindi il
    filtro migliore che abbiamo, e anche il piu' onesto. Le frasi enfatizzate
    si riconoscono dalla lunghezza e vengono scartate.
    """
    grassetti = (g.strip() for g in re.findall(r"\*\*(.+?)\*\*", testo))
    return [g for g in grassetti if 0 < len(g.split()) <= MAX_PAROLE_NOME]


def parse_penalties(md_path: Path) -> list[Mention]:
    """Legge le gerarchie dei rigoristi dall'articolo in markdown.

    Ogni squadra ha un paragrafo *Primo* (chi li batte) e uno *Note* (le
    alternative). Un solo nome in *Primo* vuol dire rigorista designato, e
    diventa ``sure``; se in *Primo* ce ne sono due o tre se li contendono, e
    allora nessuno e' sicuro. Le alternative sono sempre ``unsure``.
    """
    mentions: list[Mention] = []
    for team, corpo in _sezioni(md_path.read_text(encoding="utf-8"), "🎯"):
        primi = _nomi_in_grassetto(_paragrafo(corpo, "Primo"))
        sicurezza = "sure" if len(set(primi)) == 1 else "unsure"
        mentions += [(team, nome, "penalty", sicurezza) for nome in primi]
        mentions += [
            (team, nome, "penalty", "unsure")
            for nome in _nomi_in_grassetto(_paragrafo(corpo, "Note"))
        ]
    return mentions


def parse_set_pieces(md_path: Path) -> list[Mention]:
    """Legge le gerarchie di corner e punizioni dall'articolo in markdown.

    Qui i battitori sono gia' in elenco (``*Punizioni*: Tizio, Caio, ...``) e
    l'articolo dichiara di ordinarli "da chi ha piu' possibilita' di calciare
    a chi ne ha meno": il primo della fila e' ``sure``, gli altri ``unsure``.
    """
    campi = {"Punizioni": "free_kick", "Corner": "corner"}
    mentions: list[Mention] = []
    for team, corpo in _sezioni(md_path.read_text(encoding="utf-8"), "✅"):
        for etichetta, piazzato in campi.items():
            riga = re.search(rf"^\*{etichetta}\*:(.*)$", corpo, flags=re.M)
            if riga is None:
                continue
            # La barra separa i ballottaggi ("Doig/Obrador"): valgono entrambi.
            nomi = [n.strip() for pezzo in riga.group(1).split(",") for n in pezzo.split("/")]
            nomi = [n for n in nomi if n]
            mentions += [
                (team, nome, piazzato, "sure" if i == 0 else "unsure")
                for i, nome in enumerate(nomi)
            ]
    return mentions


def _tokens(name: str) -> list[str]:
    """Parole di un nome, senza accenti e punteggiatura."""
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return "".join(c if c.isalnum() else " " for c in stripped.upper()).split()


def _candidati(nome: str, rosa: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Calciatori della rosa compatibili con un nome scritto nell'articolo.

    Gli articoli usano il nome che si dice in tv ("Seba Esposito", "Ricardo
    Rodriguez"), il listone quello che ci sta in colonna ("Esposito S."): il
    confronto e' quindi sulle parole, non sulla stringa intera.
    """
    cercate = _tokens(nome)
    if not cercate:
        return []
    esatti = [p for p in rosa if _tokens(p["name"]) == cercate]
    if esatti:
        return esatti
    contenuti = [
        p
        for p in rosa
        if set(cercate) <= set(_tokens(p["name"])) or set(_tokens(p["name"])) <= set(cercate)
    ]
    if contenuti:
        return contenuti
    # Ultimo tentativo: il cognome del listone (prima parola) compare nel nome
    # dell'articolo. Prende "Esposito S." partendo da "Seba Esposito".
    return [p for p in rosa if _tokens(p["name"])[:1] and _tokens(p["name"])[0] in cercate]


def merge_set_pieces(
    players: list[dict[str, Any]], mentions: list[Mention]
) -> tuple[int, list[str]]:
    """Attacca i piazzati ai calciatori del listone, per nome e squadra.

    Qui l'Id non c'e' - gli articoli sono prosa, non un export - quindi il
    join e' sul nome dentro la rosa della squadra, che restringe il campo a
    una trentina di calciatori e rende le omonimie improbabili. Ogni nome che
    non si aggancia viene segnalato invece di sparire in silenzio: quasi
    sempre e' uno svincolato che nel listone non c'e'.

    Returns:
        Quanti calciatori hanno ricevuto almeno un piazzato e le segnalazioni.
    """
    rose: dict[str, list[dict[str, Any]]] = {}
    for player in players:
        player.pop("set_pieces", None)
        rose.setdefault(" ".join(_tokens(player["team"])), []).append(player)

    sospetti: list[str] = []
    for team, nome, piazzato, sicurezza in mentions:
        rosa = rose.get(" ".join(_tokens(team)))
        if rosa is None:
            sospetti.append(f"{team}: squadra assente dal listone")
            continue
        trovati = _candidati(nome, rosa)
        if len(trovati) != 1:
            quali = ", ".join(p["name"] for p in trovati) or "nessuno"
            sospetti.append(f"{team}: {nome!r} -> {quali}")
            continue
        piazzati = trovati[0].setdefault("set_pieces", {})
        # Un nome puo' comparire due volte (primo rigorista e alternativa in
        # una nota): vince la menzione piu' sicura.
        if piazzati.get(piazzato) != "sure":
            piazzati[piazzato] = sicurezza

    # Ordine fisso delle chiavi: il JSON e' committato, e un diff che cambia
    # solo per l'ordine in cui sono stati letti gli articoli e' rumore.
    ordine = ("penalty", "corner", "free_kick")
    for player in players:
        if trovati_piazzati := player.get("set_pieces"):
            player["set_pieces"] = {k: trovati_piazzati[k] for k in ordine if k in trovati_piazzati}
    return sum(1 for p in players if p.get("set_pieces")), sospetti


# ---------------------------------------------------------- formazioni


def parse_lineups(md_path: Path) -> list[tuple[str, list[list[list[str]]]]]:
    """Legge le formazioni tipo dall'articolo in markdown.

    La riga della formazione e' gia' strutturata dalla punteggiatura::

        Carnesecchi; Zappacosta/Bellanova, Scalvini, ...; Kessie', ...

    Il punto e virgola separa i reparti, la virgola i posti in campo, la barra
    i due nomi in ballottaggio per lo stesso posto. Il punto finale della frase
    si toglie: gli altri appartengono ai nomi (``Kristensen T.``).

    Returns:
        Per ogni squadra, i reparti; ogni reparto e' una lista di posti, e ogni
        posto la lista dei nomi che se lo giocano.
    """
    testo = md_path.read_text(encoding="utf-8")
    squadre: list[tuple[str, list[list[list[str]]]]] = []
    for team, corpo in _sezioni_maiuscole(testo):
        riga = re.search(r"^\*Formazione-tipo:\*(.*)$", corpo, flags=re.M)
        if riga is None:
            continue
        testo_riga = riga.group(1).strip().removesuffix(".")
        reparti = [
            [
                [nome.strip() for nome in posto.split("/") if nome.strip()]
                for posto in reparto.split(",")
                if posto.strip()
            ]
            for reparto in testo_riga.split(";")
            if reparto.strip()
        ]
        squadre.append((team, reparti))
    return squadre


def _sezioni_maiuscole(testo: str) -> list[tuple[str, str]]:
    """Spezza l'articolo delle formazioni in ``(squadra, corpo)``.

    Qui le squadre non hanno un'emoji davanti: aprono una riga fatta solo dal
    nome in grassetto e tutto maiuscolo.
    """
    pezzi = re.split(r"^\*\*([A-Z][A-Z' ]+)\*\*\s*$", testo, flags=re.M)[1:]
    return list(zip(pezzi[0::2], pezzi[1::2], strict=True))


def merge_lineups(
    players: list[dict[str, Any]], squadre: list[tuple[str, list[list[list[str]]]]]
) -> tuple[list[dict[str, Any]], int, list[str]]:
    """Aggancia le formazioni al listone e segna chi e' titolare.

    Un nome da solo nel suo posto e' un titolare, due nomi separati dalla barra
    sono un ballottaggio. Chi compare in due posti diversi (capita: un jolly
    provato in mezzo e sulla fascia) si tiene la menzione migliore.

    Returns:
        Le formazioni pronte per il JSON, quanti calciatori hanno una
        titolarita' e le segnalazioni sui nomi non agganciati.
    """
    rose: dict[str, list[dict[str, Any]]] = {}
    for player in players:
        player.pop("starter", None)
        rose.setdefault(" ".join(_tokens(player["team"])), []).append(player)

    formazioni: list[dict[str, Any]] = []
    sospetti: list[str] = []
    for team, reparti in squadre:
        rosa = rose.get(" ".join(_tokens(team)), [])
        if not rosa:
            sospetti.append(f"{team}: squadra assente dal listone")
        etichetta = rosa[0]["team"] if rosa else team.title()
        reparti_json: list[list[list[dict[str, Any]]]] = []
        for reparto in reparti:
            posti: list[list[dict[str, Any]]] = []
            for posto in reparto:
                titolarita = "starter" if len(posto) == 1 else "contested"
                nomi: list[dict[str, Any]] = []
                for nome in posto:
                    trovati = _candidati(nome, rosa)
                    if len(trovati) != 1:
                        quali = ", ".join(p["name"] for p in trovati) or "nessuno"
                        sospetti.append(f"{team}: {nome!r} -> {quali}")
                        nomi.append({"name": nome})
                        continue
                    player = trovati[0]
                    if player.get("starter") != "starter":
                        player["starter"] = titolarita
                    nomi.append({"name": nome, "id": player["id"]})
                posti.append(nomi)
            reparti_json.append(posti)
        formazioni.append({"team": etichetta, "units": reparti_json})

    return formazioni, sum(1 for p in players if p.get("starter")), sospetti


# ---------------------------------------------------------- infortuni


def parse_injuries(md_path: Path) -> list[tuple[str, str, int | None, str]]:
    """Legge la tabella degli indisponibili.

    Di ogni squadra interessa il solo blocco ``*Infortunati:*``: squalificati e
    diffidati riguardano una giornata sola, mentre un infortunio cambia quanto
    vale un calciatore all'asta. Ogni riga e' ``**Nome** - descrizione, in
    dubbio per la 3a.``; quando manca la giornata resta l'infortunio senza
    data, che e' comunque l'informazione principale.

    Returns:
        Quaterne ``(squadra, nome, giornata, descrizione)``.
    """
    fuori: list[tuple[str, str, int | None, str]] = []
    for team, corpo in _sezioni_maiuscole(md_path.read_text(encoding="utf-8")):
        # Il blocco finisce dove ne comincia un altro (*Squalificati:*) oppure
        # dove finisce la sezione della squadra: senza il secondo caso una
        # tabella che elenca solo gli infortunati non verrebbe letta.
        blocco = re.search(r"^\*Infortunati:\*(.*?)(?=^\*[A-Z]|\Z)", corpo, flags=re.M | re.S)
        if blocco is None:
            continue
        for riga in re.finditer(r"^\*\*(.+?)\*\*\s*[-–]\s*(.+)$", blocco.group(1), flags=re.M):
            nome, descrizione = riga.group(1).strip(), riga.group(2).strip().rstrip(".")
            giornata = re.search(r"per la (\d+)a\b", descrizione)
            fuori.append((team, nome, int(giornata.group(1)) if giornata else None, descrizione))
    return fuori


def merge_injuries(
    players: list[dict[str, Any]], fuori: list[tuple[str, str, int | None, str]]
) -> tuple[int, list[str]]:
    """Attacca gli infortuni ai calciatori del listone, per nome e squadra.

    Returns:
        Quanti calciatori risultano infortunati e le segnalazioni sui nomi.
    """
    rose: dict[str, list[dict[str, Any]]] = {}
    for player in players:
        player.pop("injury", None)
        rose.setdefault(" ".join(_tokens(player["team"])), []).append(player)

    sospetti: list[str] = []
    for team, nome, giornata, descrizione in fuori:
        rosa = rose.get(" ".join(_tokens(team)))
        if rosa is None:
            sospetti.append(f"{team}: squadra assente dal listone")
            continue
        trovati = _candidati(nome, rosa)
        if len(trovati) != 1:
            quali = ", ".join(p["name"] for p in trovati) or "nessuno"
            sospetti.append(f"{team}: {nome!r} -> {quali}")
            continue
        infortunio: dict[str, Any] = {"note": descrizione}
        if giornata is not None:
            infortunio = {"matchday": giornata, **infortunio}
        trovati[0]["injury"] = infortunio
    return sum(1 for p in players if p.get("injury")), sospetti


# ------------------------------------------------------------ portieri


def parse_keepers(md_path: Path) -> list[dict[str, Any]]:
    """Legge le gerarchie in porta.

    Ogni squadra ha *Primo*, *Secondo*, *Terzo* e una nota. Il posto e' in
    discussione quando il primo sono due nomi separati dalla barra (il Como,
    dove l'allenatore ha chiesto due titolari) oppure quando la nota dice di
    prendere tutti e due: in quei casi il vice serve davvero, negli altri e'
    un credito buttato.

    Returns:
        Per ogni squadra ``{"team", "starters", "backup", "risky", "note"}``,
        con i nomi ancora come li scrive l'articolo.
    """
    squadre: list[dict[str, Any]] = []
    for team, corpo in _sezioni(md_path.read_text(encoding="utf-8"), "🧤"):
        primo = _nomi_portieri(_paragrafo(corpo, "Primo"))
        if not primo:
            continue
        secondo = _nomi_portieri(_paragrafo(corpo, "Secondo"))
        nota = " ".join(_paragrafo(corpo, "Note").split())
        incerto = len(primo) > 1 or any(hint in nota.lower() for hint in KEEPER_RISK_HINTS)
        # Il vice si mostra solo se serve, e solo se non e' gia' fra i titolari
        # (il secondo del Como e' il primo scritto al contrario).
        vice = next((n for n in secondo if n not in primo), None)
        squadre.append(
            {
                "team": team,
                "starters": primo,
                "backup": vice if incerto else None,
                "risky": incerto,
                # La nota si tiene solo dove serve: spiega perche' il posto e'
                # in discussione, e sulle diciotto gerarchie chiare non
                # aggiunge niente che non dica gia' il nome del titolare.
                "note": nota if incerto else "",
            }
        )
    return squadre


def _nomi_portieri(paragrafo: str) -> list[str]:
    """Nomi di un paragrafo delle gerarchie, senza grassetti ne' barre."""
    testo = paragrafo.replace("**", "").strip().rstrip(".")
    return [nome.strip() for nome in testo.split("/") if nome.strip()]


def merge_keepers(
    players: list[dict[str, Any]],
    squadre: list[dict[str, Any]],
    conceded: dict[str, int] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Aggancia le gerarchie in porta al listone.

    Args:
        players: il listone.
        squadre: le gerarchie lette dall'articolo.
        conceded: gol subiti l'anno scorso, per squadra. Le neopromosse non
            ci sono e restano senza.

    Returns:
        Le gerarchie pronte per il JSON e le segnalazioni sui nomi.
    """
    subiti = {" ".join(_tokens(t)): n for t, n in (conceded or {}).items()}
    rose: dict[str, list[dict[str, Any]]] = {}
    for player in players:
        rose.setdefault(" ".join(_tokens(player["team"])), []).append(player)

    gerarchie: list[dict[str, Any]] = []
    sospetti: list[str] = []

    def riferimento(nome: str, rosa: list[dict[str, Any]], team: str) -> dict[str, Any]:
        trovati = _candidati(nome, rosa)
        if len(trovati) != 1:
            quali = ", ".join(p["name"] for p in trovati) or "nessuno"
            sospetti.append(f"{team}: {nome!r} -> {quali}")
            return {"name": nome}
        return {"name": nome, "id": trovati[0]["id"]}

    for squadra in squadre:
        team = squadra["team"]
        chiave = " ".join(_tokens(team))
        rosa = rose.get(chiave, [])
        if not rosa:
            sospetti.append(f"{team}: squadra assente dal listone")
        # Solo i portieri: in rosa c'e' anche il Pessina centrocampista.
        portieri = [p for p in rosa if p["role"] == "P"]
        gerarchia: dict[str, Any] = {
            "team": rosa[0]["team"] if rosa else team.title(),
            "starters": [riferimento(n, portieri, team) for n in squadra["starters"]],
            "backup": (
                riferimento(squadra["backup"], portieri, team) if squadra["backup"] else None
            ),
            "risky": squadra["risky"],
            "note": squadra["note"],
        }
        if chiave in subiti:
            gerarchia["conceded"] = subiti[chiave]
        gerarchie.append(gerarchia)
    return gerarchie, sospetti


# --------------------------------------------------------------- fasce


def parse_tiers(md_path: Path) -> list[tuple[str, list[str]]]:
    """Legge le fasce d'asta di un reparto.

    Ogni fascia apre una riga fatta cosi'::

        **F1** - Dimarco, Wesley, Bremer, Bastoni, ...

    e sotto ha i commenti sui singoli calciatori, che qui non servono. Le
    fasce si restituiscono **nell'ordine in cui compaiono**, che e' la
    graduatoria: le jolly (``JF``) e le scommesse (``FS``) sono infilate fra
    le altre, quindi l'ordine alfabetico delle sigle non c'entra niente.

    Returns:
        Coppie ``(fascia, nomi)`` in ordine di graduatoria.
    """
    testo = md_path.read_text(encoding="utf-8")
    fasce: list[tuple[str, list[str]]] = []
    for riga in re.finditer(r"^\*\*([A-Z]+\d*)\*\*\s*[-–]\s*(.+)$", testo, flags=re.M):
        nomi = [nome.strip() for nome in riga.group(2).split(",") if nome.strip()]
        if nomi:
            fasce.append((riga.group(1), nomi))
    return fasce


def merge_tiers(
    players: list[dict[str, Any]], per_ruolo: dict[str, list[tuple[str, list[str]]]]
) -> tuple[int, list[str]]:
    """Attacca le fasce ai calciatori del listone, per nome dentro il reparto.

    Il reparto e' l'articolo da cui arriva il nome, e restringe abbastanza da
    togliere ogni ambiguita': i due Esposito attaccanti si distinguono da soli
    (``Esposito F.P.`` e ``Esposito Se.``), e ``Martinez L.`` non rischia di
    finire sul portiere dell'Inter.

    Returns:
        Quanti calciatori hanno una fascia e le segnalazioni sui nomi.
    """
    reparti: dict[str, list[dict[str, Any]]] = {}
    for player in players:
        player.pop("tier", None)
        player.pop("tier_rank", None)
        reparti.setdefault(player["role"], []).append(player)

    sospetti: list[str] = []
    for ruolo, fasce in per_ruolo.items():
        rosa = reparti.get(ruolo, [])
        for posizione, (fascia, nomi) in enumerate(fasce, start=1):
            for nome in nomi:
                trovati = _candidati(nome, rosa)
                if len(trovati) != 1:
                    quali = ", ".join(f"{p['name']} ({p['team']})" for p in trovati) or "nessuno"
                    sospetti.append(f"{ruolo} {fascia}: {nome!r} -> {quali}")
                    continue
                trovati[0]["tier"] = fascia
                trovati[0]["tier_rank"] = posizione
    return sum(1 for p in players if p.get("tier")), sospetti


def find_tiers(raw_dir: Path = RAW_DIR) -> dict[str, Path]:
    """Trova gli articoli delle fasce presenti in ``raw_dir``, uno per reparto."""
    trovati = {}
    for ruolo, glob in TIERS_GLOBS.items():
        percorso = _piu_recente(raw_dir, glob)
        if percorso is not None:
            trovati[ruolo] = percorso
    return trovati


def find_keepers(raw_dir: Path = RAW_DIR) -> Path | None:
    """Trova le gerarchie dei portieri in ``raw_dir``, se ci sono."""
    return _piu_recente(raw_dir, KEEPERS_GLOB)


def find_injuries(raw_dir: Path = RAW_DIR) -> Path | None:
    """Trova la tabella degli indisponibili in ``raw_dir``, se c'e'."""
    return _piu_recente(raw_dir, INJURIES_GLOB)


def find_sources(raw_dir: Path = RAW_DIR) -> dict[str, Path | None]:
    """Tutti i file facoltativi che arricchiscono il listone, trovati da soli.

    Serve a tenere una lista sola: il JSON committato viene confrontato byte
    per byte con quello che si rigenera, e prima che questa funzione esistesse
    bastava aggiungere una sorgente e scordarsi di passarla da una parte per
    far diventare rosso un test senza capire perche'.
    """
    return {
        "stats_path": find_stats(raw_dir),
        "penalties_path": find_penalties(raw_dir),
        "set_pieces_path": find_set_pieces(raw_dir),
        "lineups_path": find_lineups(raw_dir),
        "injuries_path": find_injuries(raw_dir),
        "keepers_path": find_keepers(raw_dir),
        "tiers_paths": find_tiers(raw_dir),
    }


def find_lineups(raw_dir: Path = RAW_DIR) -> Path | None:
    """Trova l'articolo delle probabili formazioni in ``raw_dir``, se c'e'."""
    return _piu_recente(raw_dir, LINEUPS_GLOB)


def find_penalties(raw_dir: Path = RAW_DIR) -> Path | None:
    """Trova l'articolo sui rigoristi in ``raw_dir``, se c'e'."""
    return _piu_recente(raw_dir, PENALTIES_GLOB)


def find_set_pieces(raw_dir: Path = RAW_DIR) -> Path | None:
    """Trova l'articolo su corner e punizioni in ``raw_dir``, se c'e'."""
    return _piu_recente(raw_dir, SET_PIECES_GLOB)


def _piu_recente(raw_dir: Path, glob: str) -> Path | None:
    candidates = candidati(raw_dir, glob)
    return candidates[0] if candidates else None


def find_stats(raw_dir: Path = RAW_DIR) -> Path | None:
    """Trova il file delle statistiche in ``raw_dir``, se c'e' (e' facoltativo)."""
    return _piu_recente(raw_dir, STATS_GLOB)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--xlsx", type=Path, help=f"default: il piu' recente {XLSX_GLOB} in data/raw/"
    )
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help=f"default: {DEFAULT_OUT.name}"
    )
    parser.add_argument("--stats", type=Path, help=f"default: il piu' recente {STATS_GLOB}")
    parser.add_argument(
        "--no-stats", action="store_true", help="genera il listone senza i rendimenti"
    )
    parser.add_argument("--penalties", type=Path, help=f"default: il piu' recente {PENALTIES_GLOB}")
    parser.add_argument(
        "--set-pieces", type=Path, help=f"default: il piu' recente {SET_PIECES_GLOB}"
    )
    parser.add_argument(
        "--no-set-pieces", action="store_true", help="genera il listone senza i calci piazzati"
    )
    parser.add_argument("--lineups", type=Path, help=f"default: il piu' recente {LINEUPS_GLOB}")
    parser.add_argument(
        "--no-lineups", action="store_true", help="genera il listone senza le formazioni"
    )
    parser.add_argument("--injuries", type=Path, help=f"default: il piu' recente {INJURIES_GLOB}")
    parser.add_argument(
        "--no-injuries", action="store_true", help="genera il listone senza gli infortuni"
    )
    parser.add_argument("--keepers", type=Path, help=f"default: il piu' recente {KEEPERS_GLOB}")
    parser.add_argument(
        "--no-keepers", action="store_true", help="genera il listone senza le gerarchie in porta"
    )
    parser.add_argument(
        "--no-tiers", action="store_true", help="genera il listone senza le fasce d'asta"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="mostra le differenze senza scrivere"
    )
    parser.add_argument(
        "--check", action="store_true", help="esce con 1 se il JSON non e' aggiornato"
    )
    args = parser.parse_args(argv)

    xlsx = args.xlsx or find_xlsx()
    stats = args.stats or (None if args.no_stats else find_stats())
    rigoristi = args.penalties or (None if args.no_set_pieces else find_penalties())
    piazzati = args.set_pieces or (None if args.no_set_pieces else find_set_pieces())
    formazioni = args.lineups or (None if args.no_lineups else find_lineups())
    infortuni = args.injuries or (None if args.no_injuries else find_injuries())
    portieri = args.keepers or (None if args.no_keepers else find_keepers())
    fasce = {} if args.no_tiers else find_tiers()
    nuovo, sospetti = build_payload(
        xlsx, stats, rigoristi, piazzati, formazioni, infortuni, portieri, fasce
    )
    vecchio: dict[str, Any] | None = None
    if args.out.exists():
        vecchio = json.loads(args.out.read_text(encoding="utf-8"))

    aggiornato = vecchio is not None and render_payload(vecchio) == render_payload(nuovo)
    print(f"Listone:  {_relativo(xlsx)}")
    print(f"JSON:     {_relativo(args.out)}")
    print(f"Totale:   {nuovo['count']} calciatori   ({_conteggi(nuovo)})")
    if stats is not None:
        senza = nuovo["count"] - int(nuovo["with_stats"])
        print(
            f"Stat.:    {_relativo(stats)} -> {nuovo['with_stats']} abbinati per Id, "
            f"{senza} senza (mai giocato in Serie A)"
        )
    else:
        print("Stat.:    nessun file Statistiche_*.xlsx in data/raw/")
    if "set_pieces_sources" in nuovo:
        print(
            f"Piazzati: {', '.join(nuovo['set_pieces_sources'])} -> "
            f"{nuovo['with_set_pieces']} calciatori battono almeno un piazzato"
        )
    else:
        print(f"Piazzati: nessun file {PENALTIES_GLOB} o {SET_PIECES_GLOB} in data/raw/")
    if "lineups_source" in nuovo:
        print(
            f"Formaz.:  {nuovo['lineups_source']} -> {len(nuovo['lineups'])} squadre, "
            f"{nuovo['with_starter']} calciatori titolari o in ballottaggio"
        )
    else:
        print(f"Formaz.:  nessun file {LINEUPS_GLOB} in data/raw/")
    if "injuries_source" in nuovo:
        print(f"Infort.:  {nuovo['injuries_source']} -> {nuovo['with_injury']} indisponibili")
    else:
        print(f"Infort.:  nessun file {INJURIES_GLOB} in data/raw/")
    if "tiers_sources" in nuovo:
        elenco = ", ".join(nuovo["tiers_sources"])
        print(f"Fasce:    {elenco} -> {nuovo['with_tier']} calciatori con una fascia")
    else:
        print("Fasce:    nessun articolo delle fasce in data/raw/")
    if "keepers_source" in nuovo:
        incerte = sum(1 for g in nuovo["keepers"] if g["risky"])
        neopromosse = [g["team"] for g in nuovo["keepers"] if "conceded" not in g]
        print(
            f"Portieri: {nuovo['keepers_source']} -> {len(nuovo['keepers'])} gerarchie, "
            f"{incerte} con il posto in discussione"
        )
        if neopromosse:
            print(f"          senza gol subiti (neopromosse): {', '.join(neopromosse)}")
    else:
        print(f"Portieri: nessun file {KEEPERS_GLOB} in data/raw/")
    globs = (
        (XLSX_GLOB, xlsx),
        (STATS_GLOB, stats),
        (PENALTIES_GLOB, rigoristi),
        (LINEUPS_GLOB, formazioni),
        (INJURIES_GLOB, infortuni),
        (KEEPERS_GLOB, portieri),
        *((glob, fasce.get(ruolo)) for ruolo, glob in TIERS_GLOBS.items()),
    )
    for glob, scelto in globs:
        altri = [f.name for f in candidati(RAW_DIR, glob) if scelto and f != scelto]
        if altri:
            print(
                f"  ATTENZIONE  in data/raw/ ci sono piu' file {glob}: uso "
                f"{scelto.name if scelto else '-'}, ignoro {', '.join(altri)}"
            )
    for riga in sospetti:
        print(f"  ATTENZIONE  {riga}")

    if args.check:
        if aggiornato:
            print("\nIl JSON e' allineato all'Excel.")
            return 0
        print("\nIl JSON NON e' allineato all'Excel:")
        for riga in describe_changes(vecchio, nuovo):
            print("  " + riga)
        print("\nRigeneralo con:  python scripts/build_players.py")
        return 1

    if aggiornato:
        print("\nNessuna differenza: il JSON era gia' aggiornato.")
        return 0

    print("\nDifferenze rispetto al JSON attuale:")
    for riga in describe_changes(vecchio, nuovo):
        print("  " + riga)

    if args.dry_run:
        print("\n--dry-run: non ho scritto nulla.")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_payload(nuovo), encoding="utf-8")
    print(f"\nScritto {args.out.name}. Ricordati di committarlo:")
    files = (
        args.out,
        xlsx,
        stats,
        rigoristi,
        piazzati,
        formazioni,
        infortuni,
        portieri,
        *fasce.values(),
    )
    sorgenti = " ".join(_relativo(f) for f in files if f is not None)
    print(f"  git add {sorgenti}")
    print("  git commit -m 'Aggiorna il listone'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

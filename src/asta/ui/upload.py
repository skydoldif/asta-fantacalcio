"""Caricamento del listone dall'app, senza Python ne' terminale.

Il listone si e' sempre generato con ``python scripts/build_players.py``, che
legge i file da ``data/raw/`` e scrive un JSON da committare. Funziona benissimo
per chi programma, ed e' un muro per chiunque altro: servono Python installato,
un terminale, git e un push. Qui gli stessi file si trascinano nella pagina e il
listone finisce nel database, dove l'app lo trova al prossimo giro.

La logica di lettura non e' duplicata: ``build_payload`` prende dei percorsi e
restituisce il dizionario gia' pronto, quindi basta scrivere i file caricati in
una cartella temporanea e chiamarla. Il lettore dell'Excel usa solo la libreria
standard, quindi non serve installare niente in piu'.

Ogni file va al suo posto **in base al nome**, con gli stessi glob della riga di
comando: cosi' le due strade restano intercambiabili e chi ha gia' i file sul
disco non deve rinominarli. Il pannello scrive a schermo cosa ha riconosciuto e
cosa ha ignorato, che e' l'unico modo perche' un nome sbagliato si veda subito
invece che a meta' asta.
"""

from __future__ import annotations

import tempfile
from collections.abc import Mapping, Sequence
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from scripts import build_players as bp

#: Glob -> (argomento di ``build_payload``, etichetta per l'admin).
#:
#: L'ordine e' quello in cui le voci compaiono a schermo: prima le due
#: obbligatorie o quasi, poi gli articoli.
DESTINAZIONI: tuple[tuple[str, str, str], ...] = (
    (bp.XLSX_GLOB, "xlsx_path", "Listone ufficiale"),
    (bp.STATS_GLOB, "stats_path", "Statistiche stagione precedente"),
    (bp.TIERS_GLOBS["D"], "tiers_D", "Fasce d'asta — difensori"),
    (bp.TIERS_GLOBS["C"], "tiers_C", "Fasce d'asta — centrocampisti"),
    (bp.TIERS_GLOBS["A"], "tiers_A", "Fasce d'asta — attaccanti"),
    (bp.LINEUPS_GLOB, "lineups_path", "Probabili formazioni"),
    (bp.KEEPERS_GLOB, "keepers_path", "Gerarchie in porta"),
    (bp.INJURIES_GLOB, "injuries_path", "Infortunati"),
    (bp.PENALTIES_GLOB, "penalties_path", "Rigoristi"),
    (bp.SET_PIECES_GLOB, "set_pieces_path", "Corner e punizioni"),
)

#: Il nome del file che serve per forza. Senza, non c'e' listone.
OBBLIGATORIO = "xlsx_path"


def smista(nomi: Sequence[str]) -> tuple[dict[str, str], list[str]]:
    """Decide che ruolo ha ogni file caricato, guardandone il nome.

    Args:
        nomi: i nomi dei file caricati.

    Returns:
        La coppia ``(destinazione -> nome del file, nomi non riconosciuti)``.

    Quando piu' file finiscono nella stessa casella vince **l'ultimo in ordine
    alfabetico**, la stessa regola della riga di comando: i file ufficiali
    finiscono con la stagione, e delle due statistiche vince quella con le
    colonne aggiuntive dei portieri, che sono quelle che servono alla pagina
    delle gerarchie.
    """
    scelti: dict[str, str] = {}
    usati: set[str] = set()
    for glob, destinazione, _ in DESTINAZIONI:
        candidati = sorted(n for n in nomi if fnmatch(n, glob))
        if candidati:
            scelti[destinazione] = candidati[-1]
            usati.update(candidati)
    return scelti, [n for n in nomi if n not in usati]


def etichette() -> dict[str, str]:
    """Destinazione -> nome leggibile, per scriverlo a schermo."""
    return {destinazione: etichetta for _, destinazione, etichetta in DESTINAZIONI}


#: I file gia' caricati: ``casella -> (nome del file, contenuto)``.
Caselle = dict[str, tuple[str, bytes]]


def unisci(gia_presenti: Mapping[str, tuple[str, bytes]], nuovi: Mapping[str, bytes]) -> Caselle:
    """Mette i file appena caricati sopra quelli gia' in archivio.

    Chi carica le quotazioni oggi e le statistiche domani non deve ricaricare
    tutto: le caselle non toccate restano quelle di prima, e il listone si
    rigenera comunque dall'insieme completo. Un file nuovo nella stessa
    casella prende il posto del vecchio.

    Args:
        gia_presenti: quello che c'e' in archivio.
        nuovi: i file appena caricati, ``nome -> contenuto``.

    Returns:
        Le caselle risultanti.
    """
    scelti, _ = smista(list(nuovi))
    unite: Caselle = dict(gia_presenti)
    for casella, nome in scelti.items():
        unite[casella] = (nome, nuovi[nome])
    return unite


def costruisci_da_caselle(
    caselle: Mapping[str, tuple[str, bytes]],
) -> tuple[dict[str, Any], list[str]]:
    """Genera il listone da file gia' smistati.

    Returns:
        Il listone da salvare e i nomi che lo script non ha saputo agganciare
        con sicurezza.

    Raises:
        ValueError: se manca il listone ufficiale, l'unico indispensabile.
    """
    if OBBLIGATORIO not in caselle:
        raise ValueError(
            f"Manca il listone ufficiale (un file `{bp.XLSX_GLOB}`): senza quello "
            "non c'e' niente da generare."
        )

    with tempfile.TemporaryDirectory(prefix="listone-") as cartella:
        radice = Path(cartella)
        percorsi: dict[str, Path] = {}
        for casella, (nome, contenuto) in caselle.items():
            # ``Path(nome).name`` e non ``nome``: il nome arriva dal browser, e
            # un "../" ci scriverebbe fuori dalla cartella temporanea.
            percorso = radice / Path(nome).name
            percorso.write_bytes(contenuto)
            percorsi[casella] = percorso

        fasce = {
            ruolo: percorsi[f"tiers_{ruolo}"] for ruolo in "DCA" if f"tiers_{ruolo}" in percorsi
        }
        argomenti = {k: v for k, v in percorsi.items() if not k.startswith("tiers_")}
        return bp.build_payload(tiers_paths=fasce or None, **argomenti)


def costruisci(files: Mapping[str, bytes]) -> tuple[dict[str, Any], list[str], dict[str, str]]:
    """Genera il listone da un caricamento unico, smistando per nome.

    Args:
        files: nome del file -> contenuto.

    Returns:
        ``(payload, segnalazioni, smistamento)``: il listone da salvare, i nomi
        dubbi, e cosa ha fatto di ogni file.

    Raises:
        ValueError: se manca il listone ufficiale.
    """
    caselle = unisci({}, files)
    payload, segnalazioni = costruisci_da_caselle(caselle)
    return payload, segnalazioni, {c: nome for c, (nome, _) in caselle.items()}

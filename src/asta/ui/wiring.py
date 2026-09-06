"""Costruzione delle dipendenze condivise dell'app Streamlit.

Sta tutto in cache, condiviso da tutte le sessioni del processo: engine,
repository, listone, il servizio dell'admin con la sua coda di scritture e il
log letto per la vista utente. In ``st.session_state`` resta solo quello che
riguarda davvero il singolo browser - l'ora dell'ultima lettura riuscita e la
versione che ha visto - perche' la sessione muore quando la pagina si ricarica,
e ricaricare la pagina e' la prima cosa che si fa quando la rete fa i capricci.
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any

import streamlit as st

from asta import config
from asta.data.keepers import cached_keeper_grid, cached_keepers
from asta.data.players import (
    cached_lineups,
    cached_listone,
    cached_stats_season,
    cached_tiers,
    load_listone,
)
from asta.data.repository import AuctionRepository, InMemoryRepository, PostgresRepository
from asta.domain.events import Event
from asta.domain.models import Listone
from asta.domain.reducer import AuctionState, build_state
from asta.service import AuctionService


@st.cache_resource(show_spinner=False)
def _listone_scaricato(auction_id: str) -> str | None:
    """Materializza su disco il listone caricato dall'admin, e ne da' il percorso.

    ``None`` quando nel database non c'e' niente: si ricade sul JSON
    committato nella repo, che e' come funzionava prima e come continua a
    funzionare per chi il listone se lo genera da sé.

    Perche' un file e non il dizionario in memoria: *tutti* i lettori del
    listone - fasce, formazioni, gerarchie in porta, stagione delle
    statistiche - prendono gia' un percorso facoltativo ed hanno la loro
    memoizzazione su quello. Passando un percorso si cambia una riga per
    lettore invece di riscriverli tutti, e le loro cache continuano a
    funzionare senza saperne niente.

    Il file sta nella cartella temporanea, che su Streamlit Cloud si azzera a
    ogni riavvio: e' voluto. La copia buona e' quella nel database, e a ogni
    riavvio si riscrive da li'.
    """
    payload = get_repository().load_listone()
    if payload is None:
        return None
    percorso = Path(tempfile.gettempdir()) / f"listone-{auction_id}.json"
    percorso.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return str(percorso)


def listone_path() -> str | None:
    """Da dove leggere il listone: il database se ce l'ha, altrimenti il file.

    Da passare a tutti i ``cached_*`` di :mod:`asta.data`, che con ``None``
    ricadono sul JSON committato.
    """
    try:
        return _listone_scaricato(config.auction_id())
    except Exception:
        # Database irraggiungibile all'avvio: meglio il listone committato
        # (se c'e') che una pagina bianca.
        return None


def get_listone() -> Listone:
    """Il listone, caricato una volta sola per processo.

    Se non c'e' ne' nel database ne' fra i file, torna un listone **vuoto**
    invece di sollevare: chi apre l'app appena installata deve trovarci il
    pannello per caricarlo, non un traceback. Con zero calciatori l'asta non
    puo' partire comunque - le impostazioni si rifiutano di validare - quindi
    non si nasconde nessun guaio, si dice solo la cosa giusta.
    """
    percorso = listone_path()
    return cached_listone(percorso) if percorso else _listone_committato()


@st.cache_resource(show_spinner=False)
def _listone_committato() -> Listone:
    try:
        return load_listone()
    except FileNotFoundError:
        return Listone(players=())


def dimentica_il_listone() -> None:
    """Butta via ogni copia in cache del listone, dopo che ne e' stato caricato uno nuovo.

    Sono cache diverse in posti diversi - una di Streamlit, quattro
    ``lru_cache`` dentro ``asta.data`` - e vanno svuotate tutte insieme,
    altrimenti si finisce con le fasce del listone vecchio sopra i
    calciatori di quello nuovo.

    Il servizio dell'admin non si tocca: dentro ha la coda delle scritture in
    sospeso, e buttarla via perderebbe delle aggiudicazioni. Ma il listone se
    lo tiene in pancia, quindi chi carica un listone nuovo deve usare
    :func:`aggiorna_il_listone`, non questa.
    """
    _listone_scaricato.clear()
    _listone_committato.clear()
    for memoizzata in (cached_listone, cached_tiers, cached_lineups, cached_stats_season):
        memoizzata.cache_clear()
    cached_keepers.cache_clear()
    cached_keeper_grid.cache_clear()


def aggiorna_il_listone(service: AuctionService) -> None:
    """Da usare dopo che e' stato caricato un listone nuovo.

    Svuota le cache **e** rimette il listone nuovo dentro al servizio
    dell'admin, che se lo tiene in pancia da quando e' nato e vive in una
    cache che non si puo' ricostruire senza perdere la coda delle scritture.

    Senza questa seconda parte il caricamento andava a buon fine, il database
    aveva il listone nuovo, e la pagina continuava a mostrare quello vecchio:
    da fuori sembrava che il pulsante non facesse niente.
    """
    dimentica_il_listone()
    service.listone = get_listone()


#: Secondi di attesa per aprire una connessione, prima di rinunciare.
#:
#: Basso di proposito. Il pooler di Supabase si risolve in piu' indirizzi e
#: psycopg li prova a uno a uno: con dieci secondi ciascuno, un database
#: irraggiungibile teneva appesa ogni lettura per oltre mezzo minuto, e la
#: pagina restava **bianca** invece di mostrare l'ultimo stato noto con
#: l'avviso di connessione. Visto succedere in produzione. Meglio rinunciare
#: presto e dire che i dati sono vecchi, che far finta di caricare.
CONNECT_TIMEOUT = 3


@st.cache_resource(show_spinner=False)
def _engine(url: str) -> Any:
    """Engine SQLAlchemy con ping preventivo.

    ``pool_pre_ping`` evita l'errore "server closed the connection" tipico dopo
    una pausa dell'asta, ``pool_recycle`` chiude le connessioni che il pooler di
    Supabase ha gia' abbandonato.

    ``prepare_threshold=None`` spegne le prepared statement di psycopg 3: il
    *transaction pooler* di Supabase (porta 6543) non le supporta, e senza
    questa riga la query di aggiornamento della vista utente - che gira ogni
    due secondi e supererebbe subito la soglia - fallirebbe a meta' asta.
    """
    from sqlalchemy import create_engine

    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=3,
        max_overflow=2,
        connect_args={"connect_timeout": CONNECT_TIMEOUT, "prepare_threshold": None},
    )


@st.cache_resource(show_spinner=False)
def get_repository() -> AuctionRepository:
    """Repository condiviso fra admin e spettatori.

    Senza ``database_url`` si ricade su un repository in memoria: l'asta vive
    finche' vive il processo, utile solo per provare l'app.
    """
    url = config.database_url()
    if not url:
        return InMemoryRepository()
    repo = PostgresRepository(_engine(url), auction_id=config.auction_id())
    repo.ensure_schema()
    return repo


@st.cache_resource(show_spinner=False)
def _service(auction_id: str) -> AuctionService:
    """Il servizio dell'admin, uno per asta e per processo.

    Vive nella cache e non in ``st.session_state`` per una ragione sola: la
    coda delle scritture in sospeso deve sopravvivere al *ricaricamento della
    pagina*. Quando la rete cade le aggiudicazioni restano in ``pending``,
    applicate solo in locale; se a quel punto l'admin ricarica - la reazione
    naturale davanti a una schermata bloccata - con la sessione se ne
    andrebbero anche loro, in silenzio.

    Due schede admin aperte condividono la stessa coda, ed e' quello che
    vogliamo: lo scrittore e' uno solo, e la coda deve essere una sola.

    Args:
        auction_id: chiave della cache. Cambiare asta da' un servizio nuovo.
    """
    service = AuctionService(repo=get_repository(), listone=get_listone())
    service.bootstrap()
    return service


def get_service() -> AuctionService:
    """Servizio dell'admin, condiviso da tutte le sue schede."""
    service = _service(config.auction_id())
    # Il primo bootstrap puo' essere caduto insieme alla rete: si riprova
    # finche' il log non e' stato letto almeno una volta.
    if not service.loaded:
        service.reload()
    return service


@st.cache_resource(show_spinner=False, max_entries=4)
def _events_at(version: tuple[int, int]) -> list[Event]:
    """Il log a una certa versione, letto una volta per tutti.

    La cache e' di processo, non di sessione: senza, dieci telefoni collegati
    sarebbero dieci ``load()`` per ogni aggiudicazione, tutti con lo stesso
    risultato. La chiave e' la versione del log, quindi la lettura si ripete
    solo quando c'e' davvero qualcosa di nuovo.

    **``cache_resource`` e non ``cache_data``**, anche se questi sono dati:
    ``cache_data`` serializza il valore di ritorno, e in produzione il log ha
    fatto cadere l'app con ``UnserializableReturnValueError``. Non si vede in
    locale perche' l'``AppTest`` gira senza runtime e la serializzazione non
    avviene nemmeno. Qui non serve: la lista non viene mai modificata - gli
    :class:`Event` sono congelati e :func:`build_state` ordina in una copia -
    quindi condividere lo stesso oggetto fra le sessioni e' sicuro, e per
    giunta risparmia la copia a ogni lettura.
    """
    return get_repository().load()


def _ultimi_eventi_noti() -> list[Event]:
    """Il log dell'ultima versione vista, per tirare avanti quando la rete cade."""
    version = st.session_state.get("viewer_version")
    if version is None:
        return []
    try:
        return _events_at(version)
    except Exception:
        # La versione c'era ma la cache non ce l'ha piu': senza database non
        # si puo' rileggere, e si mostra quel poco che si sa.
        return []


def viewer_state() -> AuctionState:
    """Stato per la vista utente, ricaricato solo quando il log cambia.

    Ogni ciclo di aggiornamento interroga soltanto la "versione" del log
    (``(seq massimo, eventi attivi)``): il log completo viene riletto solo se
    e' effettivamente cambiato qualcosa. La versione resta una query vera a
    ogni giro - e' quella che decide quanto tardi arriva un'aggiudicazione
    sui telefoni - mentre la lettura pesante si condivide.
    """
    listone = get_listone()
    try:
        version = get_repository().version()
    except Exception as exc:
        st.session_state["viewer_error"] = str(exc)
        return build_state(listone, _ultimi_eventi_noti())

    st.session_state["viewer_error"] = None
    st.session_state["viewer_version"] = version
    # L'ora dell'ultima lettura *riuscita*: la pagina la mostra, e se si ferma
    # chi guarda sa di stare leggendo numeri vecchi.
    st.session_state["viewer_at"] = time.time()
    return build_state(listone, _events_at(version))

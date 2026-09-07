"""Test delle dipendenze condivise: engine, cache e stato della vista utente."""

from __future__ import annotations

import json
from typing import Any

import pytest
import sqlalchemy
import streamlit as st
from streamlit.runtime.caching.cache_type import CacheType

from asta.data.keepers import cached_keeper_grid
from asta.ui import wiring
from asta.ui.upload import GRIGLIA

URL_FINTA = "postgresql+psycopg://utente:segreto@localhost:6543/db"


@pytest.fixture
def argomenti_engine(monkeypatch) -> dict[str, Any]:
    """Cattura come viene costruito l'engine, senza costruirlo davvero."""
    catturati: dict[str, Any] = {}

    def create_engine(url: str, **kwargs: Any) -> object:
        catturati.update(kwargs, url=url)
        return object()

    monkeypatch.setattr(sqlalchemy, "create_engine", create_engine)
    st.cache_resource.clear()
    wiring._engine(URL_FINTA)
    yield catturati
    st.cache_resource.clear()


def test_l_engine_rinuncia_presto_a_connettersi(argomenti_engine):
    """Il caso visto in produzione: il database non risponde.

    Il pooler si risolve in piu' indirizzi e psycopg li prova a uno a uno.
    Con un'attesa lunga ogni lettura resta appesa per oltre mezzo minuto e la
    pagina non arriva nemmeno a disegnarsi: niente dati vecchi, niente
    avviso, solo una schermata bianca. Meglio rinunciare in fretta.
    """
    assert argomenti_engine["connect_args"]["connect_timeout"] <= 4


def test_le_prepared_statement_restano_spente(argomenti_engine):
    """Il transaction pooler di Supabase non le supporta: senza questa riga
    la vista utente cadrebbe dopo qualche minuto di aggiornamenti."""
    assert argomenti_engine["connect_args"]["prepare_threshold"] is None


def test_il_ping_preventivo_resta_acceso(argomenti_engine):
    """Dopo una pausa dell'asta la connessione in pool e' spesso gia' morta."""
    assert argomenti_engine["pool_pre_ping"] is True


def test_il_log_non_passa_dalla_cache_che_serializza():
    """Regressione: in produzione l'app cadeva appena disegnava il tabellone.

    ``st.cache_data`` serializza quello che restituisce, e sul log ha alzato
    ``UnserializableReturnValueError``. Non si vede in locale, perche'
    l'``AppTest`` gira senza runtime e la serializzazione non avviene: per
    questo il controllo e' sulla scelta della cache, non su un comportamento.
    """
    assert wiring._events_at._info.cache_type is CacheType.RESOURCE


# ------------------------------------------------------- griglia dei portieri


class _RepoConGriglia:
    """Archivio finto: ha in casa solo la griglia."""

    def __init__(self, contenuto: bytes) -> None:
        self.contenuto = contenuto

    def load_listone_files(self) -> dict[str, tuple[str, bytes]]:
        return {GRIGLIA: ("griglia_portieri_2026_27.json", self.contenuto)}


@pytest.fixture
def senza_cache():
    st.cache_resource.clear()
    cached_keeper_grid.cache_clear()
    yield
    st.cache_resource.clear()
    cached_keeper_grid.cache_clear()


def test_la_griglia_caricata_dall_admin_arriva_alla_pagina(monkeypatch, senza_cache):
    """L'ultimo dato che si poteva mettere solo committandolo nella repo.

    Chi installa l'app da zero non ha nessun file in ``data/``: se la griglia
    non passasse dall'archivio, la pagina Portieri resterebbe senza per sempre.
    """
    griglia = {
        "teams": ["Atalanta", "Bologna"],
        "values": [[0, 7], [7, 0]],
        "highlight_from": 5,
        "note": "dall'archivio",
    }
    monkeypatch.setattr(
        wiring, "get_repository", lambda: _RepoConGriglia(json.dumps(griglia).encode("utf-8"))
    )

    percorso = wiring.griglia_path()

    assert percorso is not None
    assert cached_keeper_grid(percorso).teams == ("Atalanta", "Bologna")


def test_senza_griglia_in_archivio_si_ricade_sul_file(monkeypatch, senza_cache):
    """La repo di chi la griglia se l'e' trascritta continua a funzionare."""

    class _Vuoto:
        def load_listone_files(self) -> dict[str, tuple[str, bytes]]:
            return {}

    monkeypatch.setattr(wiring, "get_repository", _Vuoto)

    assert wiring.griglia_path() is None


def test_un_database_muto_non_fa_cadere_la_pagina_portieri(monkeypatch, senza_cache):
    """Stessa scelta del listone: meglio senza griglia che una pagina bianca."""

    class _Muto:
        def load_listone_files(self) -> dict[str, tuple[str, bytes]]:
            raise RuntimeError("connessione persa")

    monkeypatch.setattr(wiring, "get_repository", _Muto)

    assert wiring.griglia_path() is None

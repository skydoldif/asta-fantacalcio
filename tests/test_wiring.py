"""Test delle dipendenze condivise: engine, cache e stato della vista utente."""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy
import streamlit as st
from streamlit.runtime.caching.cache_type import CacheType

from asta.ui import wiring

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

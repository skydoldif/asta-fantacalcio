"""Configurazione dell'app, letta dai secrets di Streamlit o dall'ambiente.

In locale si puo' usare ``.streamlit/secrets.toml`` (vedi il file
``.streamlit/secrets.toml.example``) oppure le variabili d'ambiente
``ASTA_DATABASE_URL``, ``ASTA_ADMIN_PASSWORD``, ``ASTA_PUBLIC_URL``,
``ASTA_AUCTION_ID``, ``ASTA_AVVISO``.

Senza ``database_url`` l'app parte comunque in **modalita demo**: lo stato vive
nella memoria del processo e sparisce a ogni riavvio. Utile per provare e per
una vetrina pubblica, inutilizzabile per l'asta vera.
"""

from __future__ import annotations

import os


def _secret(key: str, default: str = "") -> str:
    """Legge un valore dai secrets di Streamlit, con fallback su ambiente."""
    try:
        import streamlit as st

        value = st.secrets.get(key)  # type: ignore[union-attr]
        if value:
            return str(value)
    except Exception:
        pass
    return os.environ.get(f"ASTA_{key.upper()}", default)


def database_url() -> str:
    """Stringa di connessione Postgres; vuota in modalita demo."""
    return _secret("database_url")


def admin_password() -> str:
    """Password della vista Admin; vuota disattiva la protezione (solo in locale)."""
    return _secret("admin_password")


def avviso() -> str:
    """Riga da mostrare in cima a tutte le pagine; vuota non mostra niente.

    Nata per la demo pubblica, dove serve dire a chiare lettere che i
    calciatori sono inventati - altrimenti l'unico vero fraintendimento
    possibile e' che qualcuno prenda quelle quotazioni sul serio, e un avviso
    nel README non lo legge nessuno. Vale per qualunque cosa vada detta a
    tutti senza toccare il codice: "si comincia alle 21", "asta rinviata".
    """
    return _secret("avviso")


def auction_id() -> str:
    """Identificativo dell'asta sul database."""
    return _secret("auction_id", "main") or "main"


def demo_mode() -> bool:
    """True se non e' configurato alcun database."""
    return not database_url()

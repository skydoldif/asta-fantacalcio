"""Logica d'asta pura: nessuna dipendenza da Streamlit, dal DB o dall'I/O.

Tutto lo stato dell'asta e' derivato da un log di eventi append-only
(:mod:`asta.domain.events`) tramite un reducer puro
(:func:`asta.domain.reducer.build_state`). Questo rende banali l'undo, la
correzione di errori vecchi e la sincronizzazione della vista utente.
"""

"""Test del download automatico del backup.

La parte utile e' pura: quali momenti sono scattati, dato lo stato dell'asta e
lo stato della sincronizzazione. Il pezzo di Streamlit (una comparsa di
``st.iframe``) e' verificato in ``test_app_ui.py``.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from asta.data.repository import InMemoryRepository
from asta.domain.events import EventType
from asta.domain.models import (
    DEFAULT_BACKUP_TRIGGERS,
    BackupTrigger,
    Listone,
    Role,
    Settings,
)
from asta.domain.reducer import AuctionState
from asta.service import AuctionService
from asta.ui.autobackup import download_html, fired_triggers, phase_over


@pytest.fixture
def acceso(settings: Settings) -> Settings:
    """Impostazioni con il download automatico acceso su tutti i momenti."""
    return replace(settings, auto_backup=True)


def _stato(listone: Listone, settings: Settings, *fasi: Role, chiusa: bool = False):
    """Stato di un'asta configurata a cui sono state avviate certe fasi."""
    svc = AuctionService(repo=InMemoryRepository(), listone=listone)
    svc.record(EventType.AUCTION_CONFIGURED, settings.to_payload())
    for role in fasi:
        svc.record(EventType.ROLE_PHASE_STARTED, {"role": role.value})
    if chiusa:
        svc.record(EventType.AUCTION_CLOSED, {})
    return svc.state()


# ------------------------------------------------------------------ momenti


def test_senza_impostazioni_non_scatta_niente(listone):
    assert fired_triggers(AuctionState(listone=listone), synced=True) == ()


def test_con_l_opzione_spenta_non_scatta_niente(listone, settings):
    stato = _stato(listone, settings, Role.P, Role.D)
    assert settings.auto_backup is False
    assert fired_triggers(stato, synced=True) == ()


def test_la_fine_dei_portieri_scatta_quando_iniziano_i_difensori(listone, acceso):
    in_corso = _stato(listone, acceso, Role.P)
    assert fired_triggers(in_corso, synced=True) == ()

    dopo = _stato(listone, acceso, Role.P, Role.D)
    assert fired_triggers(dopo, synced=True) == (BackupTrigger.END_P,)


def test_i_reparti_chiusi_restano_scattati(listone, acceso):
    stato = _stato(listone, acceso, Role.P, Role.D, Role.C, Role.A)
    assert fired_triggers(stato, synced=True) == (
        BackupTrigger.END_P,
        BackupTrigger.END_D,
        BackupTrigger.END_C,
    )


def test_la_chiusura_dell_asta_aggiunge_il_suo_momento(listone, acceso):
    stato = _stato(listone, acceso, Role.P, Role.D, Role.C, Role.A, chiusa=True)
    assert BackupTrigger.END_AUCTION in fired_triggers(stato, synced=True)


def test_i_momenti_non_spuntati_non_scattano(listone, acceso):
    solo_fine = replace(acceso, backup_triggers=(BackupTrigger.END_AUCTION,))
    stato = _stato(listone, solo_fine, Role.P, Role.D)
    assert fired_triggers(stato, synced=True) == ()

    chiusa = _stato(listone, solo_fine, Role.P, Role.D, chiusa=True)
    assert fired_triggers(chiusa, synced=True) == (BackupTrigger.END_AUCTION,)


def test_la_coda_non_vuota_e_una_perdita_di_connessione(listone, acceso):
    stato = _stato(listone, acceso, Role.P)
    assert fired_triggers(stato, synced=False) == (BackupTrigger.OFFLINE,)
    assert fired_triggers(stato, synced=True) == ()


def test_una_fase_e_finita_solo_quando_ne_inizia_una_dopo(listone, acceso):
    stato = _stato(listone, acceso, Role.P, Role.D)
    assert phase_over(stato, Role.P) is True
    assert phase_over(stato, Role.D) is False
    assert phase_over(stato, Role.A) is False

    # A asta chiusa sono finite tutte, attaccanti compresi.
    chiusa = _stato(listone, acceso, Role.P, chiusa=True)
    assert phase_over(chiusa, Role.A) is True

    # Prima di iniziare non e' finita nessuna.
    ferma = _stato(listone, acceso)
    assert phase_over(ferma, Role.P) is False


# ------------------------------------------------------------- impostazioni


def test_le_impostazioni_conservano_i_momenti(acceso):
    scelti = (BackupTrigger.OFFLINE, BackupTrigger.END_AUCTION)
    originali = replace(acceso, backup_triggers=scelti)
    assert Settings.from_payload(originali.to_payload()) == originali


def test_un_asta_vecchia_senza_la_chiave_prende_i_default(settings):
    payload = settings.to_payload()
    del payload["auto_backup"]
    del payload["backup_triggers"]
    ripristinate = Settings.from_payload(payload)
    assert ripristinate.auto_backup is False
    assert ripristinate.backup_triggers == DEFAULT_BACKUP_TRIGGERS


def test_un_momento_sconosciuto_viene_scartato(acceso):
    payload = acceso.to_payload()
    payload["backup_triggers"] = ["end_P", "meta_secondo_tempo"]
    assert Settings.from_payload(payload).backup_triggers == (BackupTrigger.END_P,)


def test_nessun_momento_spegne_il_backup(acceso):
    muto = replace(acceso, backup_triggers=())
    assert all(not muto.backs_up(t) for t in BackupTrigger)


# ------------------------------------------------------------------ pagina


def test_la_pagina_fa_partire_il_download_col_nome_giusto():
    html = download_html("backup_fine_portieri_20260901.json", '{"events": []}')
    assert "backup_fine_portieri_20260901.json" in html
    assert "a.click()" in html


def test_il_link_non_passa_dal_body():
    """Regressione: lo script gira che il ``<body>`` non c'e' ancora.

    Il componente e' solo uno ``<script>``, quindi parte mentre la pagina e'
    ancora in ``<head>``: con ``document.body.appendChild`` il browser
    lanciava un TypeError e il file non veniva scaricato. Il test lo vede,
    la console del browser no.
    """
    html = download_html("backup.json", "{}")
    assert "document.body" not in html
    assert "document.documentElement.appendChild(a)" in html


def test_il_json_non_puo_chiudere_lo_script():
    """Una squadra chiamata ``</script>`` non deve spezzare la pagina."""
    html = download_html("backup.json", '{"teams": ["</script><b>ciao"]}')
    assert html.count("</script>") == 1
    assert "<\\/script>" in html

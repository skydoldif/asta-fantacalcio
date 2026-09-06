"""Test del controllo sull'URL del database.

``controlla`` e' una funzione pura: si verifica senza toccare nessun database.
Copre gli sbagli veri fatti durante la configurazione, non casi immaginari.
"""

from __future__ import annotations

from scripts.check_db import controlla, nascondi

BUONO = "postgresql+psycopg://postgres.abcdefgh:Segreta123@aws-0-eu-central-1.pooler.supabase.com:6543/postgres"


def test_un_url_corretto_non_ha_rilievi():
    assert controlla(BUONO) == []


def test_riconosce_i_segnaposto_del_readme():
    problemi = " ".join(controlla(BUONO.replace("abcdefgh", "xxxx")))
    assert "xxxx" in problemi
    assert "Connect" in problemi


def test_riconosce_lo_schema_senza_psycopg():
    problemi = " ".join(controlla(BUONO.replace("postgresql+psycopg://", "postgresql://")))
    assert "+psycopg" in problemi


def test_riconosce_la_password_con_caratteri_speciali():
    # Con un '@' non codificato l'URL si spezza e l'host diventa un pezzo di
    # password: e' esattamente il messaggio d'errore che arriva da psycopg.
    problemi = " ".join(controlla(BUONO.replace("Segreta123", "Segreta@123")))
    assert "vanno codificati (@)" in problemi


def test_una_password_gia_codificata_va_bene():
    # '%40' e' un '@' gia' codificato: segnalarlo manderebbe su una pista falsa.
    assert controlla(BUONO.replace("Segreta123", "Segreta%40123")) == []


def test_riconosce_i_due_punti_nella_password():
    problemi = " ".join(controlla(BUONO.replace("Segreta123", "Segreta:123")))
    assert "vanno codificati" in problemi


def test_riconosce_la_connessione_diretta_ipv6():
    diretto = "postgresql+psycopg://postgres:Segreta123@db.abcdefgh.supabase.co:5432/postgres"
    problemi = " ".join(controlla(diretto))
    assert "IPv6" in problemi
    assert "Transaction pooler" in problemi


def test_la_password_non_finisce_mai_nei_messaggi():
    assert "Segreta123" not in nascondi(f"connessione a {BUONO} fallita")
    assert "***" in nascondi(f"connessione a {BUONO} fallita")

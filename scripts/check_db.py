"""Verifica la connessione al database prima della serata.

Legge ``database_url`` da ``.streamlit/secrets.toml`` (o dalla variabile
d'ambiente ``ASTA_DATABASE_URL``), controlla i punti in cui ci si sbaglia di
solito e prova a collegarsi davvero.

La password non viene mai stampata: nei messaggi d'errore viene sostituita da
``***``, cosi' l'output si puo' incollare a chiunque senza pensarci.

Uso::

    python scripts/check_db.py             # controlla e prova a connettersi
    python scripts/check_db.py --encode    # codifica una password per l'URL
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SECRETS = ROOT / ".streamlit" / "secrets.toml"

#: Pezzi degli esempi del README: se sopravvivono, l'URL non e' stato copiato
#: dal pannello di Supabase ma modificato a mano a partire dall'esempio.
SEGNAPOSTO = ("xxxx", "PASSWORD", "YOUR-PASSWORD", "[YOUR", "USER:", "la-tua-app")

#: Caratteri che in un URL hanno un significato loro: se compaiono nella
#: password vanno codificati, altrimenti la stringa viene letta storta.
DA_CODIFICARE = "@:/?#[]% "


def nascondi(testo: object) -> str:
    """Sostituisce la password in qualsiasi messaggio prima di stamparlo."""
    return re.sub(r"://[^@\s]+@", "://***@", str(testo))


def leggi_url() -> str | None:
    """URL del database dai secrets locali o dall'ambiente."""
    if url := os.environ.get("ASTA_DATABASE_URL"):
        return url
    if not SECRETS.is_file():
        return None
    match = re.search(r'^\s*database_url\s*=\s*"(.*)"\s*$', SECRETS.read_text(), re.M)
    return match.group(1) if match else None


def controlla(url: str) -> list[str]:
    """Problemi trovati nell'URL, in italiano e con il rimedio."""
    problemi: list[str] = []

    if rimasti := [s for s in SEGNAPOSTO if s in url]:
        problemi.append(
            f"Nell'URL c'e' ancora {', '.join(repr(s) for s in rimasti)}: e' un pezzo "
            "dell'esempio del README. Copia la stringa vera dal pulsante Connect di Supabase."
        )

    if not url.startswith("postgresql+psycopg://"):
        problemi.append(
            "L'URL deve iniziare con 'postgresql+psycopg://'. Supabase la da' come "
            "'postgresql://': aggiungi '+psycopg' subito dopo 'postgresql'."
        )

    try:
        pezzi = urlsplit(url)
        host, porta = pezzi.hostname, pezzi.port
    except ValueError as exc:
        problemi.append(f"L'URL non e' interpretabile ({exc}): controlla la password.")
        return problemi

    problemi += _controlla_password(url)

    if host and "supabase" not in host and not problemi:
        problemi.append(
            f"L'host risulta essere '{host}', che non e' un indirizzo di Supabase: "
            "ricopia la stringa dal pulsante Connect."
        )
    if porta == 5432 and host and "pooler" not in host:
        problemi.append(
            "Stai usando la connessione diretta (porta 5432, host db.*.supabase.co): e' "
            "solo IPv6 e da Streamlit Cloud non si raggiunge. Usa il Transaction pooler."
        )
    return problemi


def _controlla_password(url: str) -> list[str]:
    """Segnala i caratteri della password che vanno codificati.

    Un solo '@' separa le credenziali dall'host: se ce n'e' un altro dentro la
    password, ogni libreria taglia l'URL in un punto diverso e l'errore che ne
    esce parla di un host inesistente, non della password. E' lo sbaglio piu'
    comune e il piu' difficile da riconoscere.
    """
    if "://" not in url:
        return []
    autorita = url.split("://", 1)[1].split("/", 1)[0]
    if "@" not in autorita:
        return []
    credenziali = autorita.rsplit("@", 1)[0]
    password = credenziali.split(":", 1)[1] if ":" in credenziali else ""

    sospetti = {c for c in DA_CODIFICARE if c in password and c != "%"}
    if re.search(r"%(?![0-9A-Fa-f]{2})", password):
        sospetti.add("%")
    if not sospetti:
        return []
    elenco = " ".join(sorted(sospetti)).replace(" ", "  ").strip() or "spazio"
    return [
        f"La password contiene caratteri che nell'URL vanno codificati ({elenco}). "
        "Ricavane la versione codificata con 'python scripts/check_db.py --encode' "
        "e incolla quella, oppure cambia password in Supabase scegliendone una di "
        "sole lettere e numeri."
    ]


def prova_connessione(url: str) -> int:
    """Si collega davvero e riassume cosa ha trovato."""
    try:
        from sqlalchemy import create_engine, text
    except ImportError:
        print("SQLAlchemy non installato: 'pip install -e .[dev]'")
        return 1

    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10, "prepare_threshold": None},
    )
    try:
        with engine.connect() as conn:
            versione = conn.execute(text("SHOW server_version")).scalar()
            tabella = conn.execute(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_name = 'auction_event'"
                )
            ).scalar()
            eventi = (
                conn.execute(text("SELECT count(*) FROM auction_event")).scalar() if tabella else 0
            )
    except Exception as exc:  # la diagnosi vale piu' del traceback
        print(f"✗ Connessione fallita: {type(exc).__name__}")
        print(f"  {nascondi(exc)[:400]}")
        print("\nCause piu' frequenti:")
        print("  · password sbagliata → Supabase: Settings → Database → Reset database password")
        print("  · progetto in pausa  → il dashboard mostra 'Restore project'")
        print("  · connessione diretta invece del pooler → usa la porta 6543")
        return 1

    print(f"✓ Connesso a Postgres {versione}")
    if tabella:
        print(f"✓ Tabella auction_event presente, {eventi} eventi registrati")
    else:
        print("· Tabella auction_event assente: la crea l'app al primo avvio.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--encode",
        action="store_true",
        help="chiede la password e la stampa codificata per l'URL",
    )
    args = parser.parse_args(argv)

    if args.encode:
        password = getpass.getpass("Password del database (non viene mostrata): ")
        print("\nIncollala nell'URL cosi' com'e' qui sotto:\n")
        print(quote(password, safe=""))
        return 0

    url = leggi_url()
    if not url:
        print(f"Nessun 'database_url' in {SECRETS.relative_to(ROOT)}.")
        print("Copialo da Supabase → Connect → Transaction pooler.")
        return 1

    pezzi = urlsplit(url.replace("postgresql+psycopg://", "postgresql://"))
    print(f"Host:  {pezzi.hostname}")
    print(f"Porta: {pezzi.port}")

    if problemi := controlla(url):
        for problema in problemi:
            print(f"\n✗ {problema}")
        return 1

    return prova_connessione(url)


if __name__ == "__main__":
    sys.exit(main())

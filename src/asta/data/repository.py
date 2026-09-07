"""Persistenza del log eventi.

Due implementazioni della stessa interfaccia:

* :class:`PostgresRepository` per l'asta vera (stato condiviso fra admin e
  spettatori);
* :class:`InMemoryRepository` per i test e per provare l'app senza database.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Protocol

from asta.domain.events import Event, EventType

#: Identificativo dell'asta in corso. Cambiarlo equivale a partire da zero
#: mantenendo lo storico della precedente.
DEFAULT_AUCTION_ID = "main"


class AuctionRepository(Protocol):
    """Interfaccia di persistenza del log eventi."""

    def load(self) -> list[Event]:
        """Tutti gli eventi dell'asta, ordinati per ``seq``."""
        ...

    def append(self, event: Event) -> None:
        """Aggiunge un evento. Se ``seq`` esiste gia', l'operazione e' innocua."""
        ...

    def set_active(self, seq: int, active: bool) -> None:
        """Attiva/disattiva un evento (undo e redo)."""
        ...

    def version(self) -> tuple[int, int]:
        """Firma leggera dello stato: ``(seq massimo, eventi attivi)``.

        La vista utente la interroga ogni pochi secondi e ricarica il log solo
        quando cambia.
        """
        ...

    def reset(self) -> None:
        """Cancella l'asta corrente."""
        ...

    def replace_all(self, events: list[Event]) -> None:
        """Sostituisce il log (ripristino da backup)."""
        ...

    def load_listone(self) -> dict[str, Any] | None:
        """Il listone caricato dall'admin, o ``None`` se non ne ha mai caricati.

        Sta nel database e non in un file committato perche' altrimenti per
        cambiare listone servirebbero Python, un terminale e un push: la
        strada che perde per via chiunque non programmi. Cosi' invece si
        carica l'xlsx dall'app e basta.
        """
        ...

    def save_listone(self, payload: dict[str, Any]) -> None:
        """Sostituisce il listone. Ce n'e' uno solo per asta."""
        ...

    def load_listone_files(self) -> dict[str, tuple[str, bytes]]:
        """I file da cui e' stato generato il listone: ``casella -> (nome, contenuto)``.

        Si tengono da parte perche' il listone si costruisce **tutto insieme**,
        da tutti i file, ma non e' detto che arrivino tutti insieme: uno carica
        le quotazioni oggi e le statistiche domani. Rigenerare ogni volta
        dall'insieme completo da' lo stesso risultato di un caricamento unico,
        mentre rattoppare il listone gia' fatto no.
        """
        ...

    def save_listone_file(self, casella: str, nome: str, contenuto: bytes) -> None:
        """Mette un file nella sua casella, al posto di quello che c'era."""
        ...

    def delete_listone_file(self, casella: str) -> None:
        """Toglie il file da una casella. Innocuo se era gia' vuota."""
        ...


class InMemoryRepository:
    """Repository in memoria, thread-safe. Usato dai test e in modalita demo."""

    def __init__(self, events: list[Event] | None = None) -> None:
        self._events: dict[int, Event] = {e.seq: e for e in (events or [])}
        self._listone: dict[str, Any] | None = None
        self._listone_files: dict[str, tuple[str, bytes]] = {}
        self._lock = threading.Lock()

    def load(self) -> list[Event]:
        with self._lock:
            return sorted(self._events.values(), key=lambda e: e.seq)

    def append(self, event: Event) -> None:
        with self._lock:
            self._events.setdefault(event.seq, event)

    def set_active(self, seq: int, active: bool) -> None:
        with self._lock:
            existing = self._events.get(seq)
            if existing is not None:
                self._events[seq] = existing.reactivated() if active else existing.deactivated()

    def version(self) -> tuple[int, int]:
        with self._lock:
            if not self._events:
                return (0, 0)
            return (
                max(self._events),
                sum(1 for e in self._events.values() if e.active),
            )

    def reset(self) -> None:
        with self._lock:
            self._events.clear()

    def replace_all(self, events: list[Event]) -> None:
        with self._lock:
            self._events = {e.seq: e for e in events}

    def load_listone(self) -> dict[str, Any] | None:
        with self._lock:
            return self._listone

    def save_listone(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._listone = payload

    def load_listone_files(self) -> dict[str, tuple[str, bytes]]:
        with self._lock:
            return dict(self._listone_files)

    def save_listone_file(self, casella: str, nome: str, contenuto: bytes) -> None:
        with self._lock:
            self._listone_files[casella] = (nome, contenuto)

    def delete_listone_file(self, casella: str) -> None:
        with self._lock:
            self._listone_files.pop(casella, None)


class PostgresRepository:
    """Repository su Postgres (Supabase, Neon, o qualsiasi altro).

    Args:
        engine: engine SQLAlchemy gia' configurato.
        auction_id: consente piu' aste sullo stesso database.
    """

    def __init__(self, engine: object, auction_id: str = DEFAULT_AUCTION_ID) -> None:
        self._engine = engine
        self._auction_id = auction_id

    # L'import di SQLAlchemy resta locale ai metodi cosi' il modulo si puo'
    # importare (e testare) anche dove SQLAlchemy non e' installato.
    def _sql(self, statement: str):  # type: ignore[no-untyped-def]
        from sqlalchemy import text

        return text(statement)

    def ensure_schema(self) -> None:
        """Crea la tabella se manca. Idempotente."""
        ddl = """
            CREATE TABLE IF NOT EXISTS auction_event (
                auction_id  TEXT        NOT NULL,
                seq         INTEGER     NOT NULL,
                type        TEXT        NOT NULL,
                payload     JSONB       NOT NULL DEFAULT '{}'::jsonb,
                active      BOOLEAN     NOT NULL DEFAULT TRUE,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (auction_id, seq)
            )
        """
        # Il listone sta in una riga sola per asta: e' un documento, non
        # qualcosa su cui si fanno query. Una tabella a parte e non una
        # colonna degli eventi perche' non e' un evento dell'asta - si
        # carica prima che l'asta cominci, e cambiarlo non e' un'operazione
        # da annullare.
        ddl_listone = """
            CREATE TABLE IF NOT EXISTS auction_listone (
                auction_id  TEXT        NOT NULL PRIMARY KEY,
                payload     JSONB       NOT NULL,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """
        # I file sorgente, uno per casella: caricarne uno nuovo prende il
        # posto del vecchio, e il listone si rigenera sempre da tutti.
        ddl_files = """
            CREATE TABLE IF NOT EXISTS auction_listone_file (
                auction_id  TEXT        NOT NULL,
                slot        TEXT        NOT NULL,
                filename    TEXT        NOT NULL,
                content     BYTEA       NOT NULL,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (auction_id, slot)
            )
        """
        with self._engine.begin() as conn:  # type: ignore[attr-defined]
            conn.execute(self._sql(ddl))
            conn.execute(self._sql(ddl_listone))
            conn.execute(self._sql(ddl_files))

    def load_listone(self) -> dict[str, Any] | None:
        query = "SELECT payload FROM auction_listone WHERE auction_id = :aid"
        with self._engine.connect() as conn:  # type: ignore[attr-defined]
            riga = conn.execute(self._sql(query), {"aid": self._auction_id}).first()
        if riga is None:
            return None
        payload = riga[0]
        # psycopg restituisce gia' un dict dal JSONB; con altri driver puo'
        # arrivare la stringa.
        return json.loads(payload) if isinstance(payload, str) else dict(payload)

    def save_listone(self, payload: dict[str, Any]) -> None:
        query = """
            INSERT INTO auction_listone (auction_id, payload)
            VALUES (:aid, CAST(:payload AS JSONB))
            ON CONFLICT (auction_id) DO UPDATE
                SET payload = EXCLUDED.payload, created_at = NOW()
        """
        with self._engine.begin() as conn:  # type: ignore[attr-defined]
            conn.execute(
                self._sql(query),
                {"aid": self._auction_id, "payload": json.dumps(payload, ensure_ascii=False)},
            )

    def load_listone_files(self) -> dict[str, tuple[str, bytes]]:
        query = "SELECT slot, filename, content FROM auction_listone_file WHERE auction_id = :aid"
        with self._engine.connect() as conn:  # type: ignore[attr-defined]
            righe = conn.execute(self._sql(query), {"aid": self._auction_id}).fetchall()
        return {r[0]: (r[1], bytes(r[2])) for r in righe}

    def save_listone_file(self, casella: str, nome: str, contenuto: bytes) -> None:
        query = """
            INSERT INTO auction_listone_file (auction_id, slot, filename, content)
            VALUES (:aid, :slot, :nome, :contenuto)
            ON CONFLICT (auction_id, slot) DO UPDATE
                SET filename = EXCLUDED.filename,
                    content = EXCLUDED.content,
                    created_at = NOW()
        """
        with self._engine.begin() as conn:  # type: ignore[attr-defined]
            conn.execute(
                self._sql(query),
                {
                    "aid": self._auction_id,
                    "slot": casella,
                    "nome": nome,
                    "contenuto": contenuto,
                },
            )

    def delete_listone_file(self, casella: str) -> None:
        query = "DELETE FROM auction_listone_file WHERE auction_id = :aid AND slot = :slot"
        with self._engine.begin() as conn:  # type: ignore[attr-defined]
            conn.execute(self._sql(query), {"aid": self._auction_id, "slot": casella})

    def load(self) -> list[Event]:
        query = """
            SELECT seq, type, payload, active, created_at
            FROM auction_event WHERE auction_id = :aid ORDER BY seq
        """
        with self._engine.connect() as conn:  # type: ignore[attr-defined]
            rows = conn.execute(self._sql(query), {"aid": self._auction_id}).fetchall()
        return [
            Event(
                seq=int(r[0]),
                type=EventType(r[1]),
                payload=r[2] if isinstance(r[2], dict) else json.loads(r[2] or "{}"),
                active=bool(r[3]),
                created_at=r[4],
            )
            for r in rows
        ]

    def append(self, event: Event) -> None:
        query = """
            INSERT INTO auction_event (auction_id, seq, type, payload, active, created_at)
            VALUES (:aid, :seq, :type, CAST(:payload AS JSONB), :active, :created_at)
            ON CONFLICT (auction_id, seq) DO NOTHING
        """
        with self._engine.begin() as conn:  # type: ignore[attr-defined]
            conn.execute(
                self._sql(query),
                {
                    "aid": self._auction_id,
                    "seq": event.seq,
                    "type": event.type.value,
                    "payload": json.dumps(event.payload, ensure_ascii=False),
                    "active": event.active,
                    "created_at": event.created_at,
                },
            )

    def set_active(self, seq: int, active: bool) -> None:
        query = """
            UPDATE auction_event SET active = :active
            WHERE auction_id = :aid AND seq = :seq
        """
        with self._engine.begin() as conn:  # type: ignore[attr-defined]
            conn.execute(self._sql(query), {"aid": self._auction_id, "seq": seq, "active": active})

    def version(self) -> tuple[int, int]:
        query = """
            SELECT COALESCE(MAX(seq), 0), COUNT(*) FILTER (WHERE active)
            FROM auction_event WHERE auction_id = :aid
        """
        with self._engine.connect() as conn:  # type: ignore[attr-defined]
            row = conn.execute(self._sql(query), {"aid": self._auction_id}).one()
        return (int(row[0]), int(row[1]))

    def reset(self) -> None:
        with self._engine.begin() as conn:  # type: ignore[attr-defined]
            conn.execute(
                self._sql("DELETE FROM auction_event WHERE auction_id = :aid"),
                {"aid": self._auction_id},
            )

    def replace_all(self, events: list[Event]) -> None:
        """Sostituisce il log in una transazione sola.

        Un ``append`` per evento sarebbe un round-trip per evento: ripristinare
        meta' asta da un backup sono centinaia di viaggi verso il database,
        proprio quando la rete non ne vuole sapere - che e' il motivo per cui
        si sta ripristinando. Cosi' invece o arriva tutto o non arriva niente.
        """
        query = """
            INSERT INTO auction_event (auction_id, seq, type, payload, active, created_at)
            VALUES (:aid, :seq, :type, CAST(:payload AS JSONB), :active, :created_at)
            ON CONFLICT (auction_id, seq) DO NOTHING
        """
        righe = [
            {
                "aid": self._auction_id,
                "seq": event.seq,
                "type": event.type.value,
                "payload": json.dumps(event.payload, ensure_ascii=False),
                "active": event.active,
                "created_at": event.created_at,
            }
            for event in events
        ]
        with self._engine.begin() as conn:  # type: ignore[attr-defined]
            conn.execute(
                self._sql("DELETE FROM auction_event WHERE auction_id = :aid"),
                {"aid": self._auction_id},
            )
            if righe:
                conn.execute(self._sql(query), righe)

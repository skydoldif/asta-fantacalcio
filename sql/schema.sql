-- Schema del log eventi dell'asta.
--
-- Una sola tabella: l'asta e' un log append-only e tutto lo stato (rose,
-- crediti, listone residuo) viene derivato in Python dal reducer. La colonna
-- "active" serve all'undo/redo: gli eventi annullati restano in tabella.
--
-- Da eseguire una volta sul database Postgres (es. SQL Editor di Supabase).

CREATE TABLE IF NOT EXISTS auction_event (
    auction_id  TEXT        NOT NULL,
    seq         INTEGER     NOT NULL,
    type        TEXT        NOT NULL,
    payload     JSONB       NOT NULL DEFAULT '{}'::jsonb,
    active      BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- La chiave primaria composta e' anche la protezione contro i doppioni
    -- generati da un retry della coda di sincronizzazione.
    PRIMARY KEY (auction_id, seq)
);

CREATE INDEX IF NOT EXISTS auction_event_by_auction ON auction_event (auction_id, seq);

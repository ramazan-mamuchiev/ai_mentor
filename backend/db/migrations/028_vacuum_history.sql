CREATE TABLE IF NOT EXISTS vacuum_history (
    id SERIAL PRIMARY KEY,
    table_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    duration_ms FLOAT,
    size_before_bytes BIGINT,
    size_after_bytes BIGINT,
    dead_tuples_before BIGINT,
    live_tuples BIGINT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_vacuum_history_table ON vacuum_history(table_name);
CREATE INDEX IF NOT EXISTS idx_vacuum_history_started ON vacuum_history(started_at);

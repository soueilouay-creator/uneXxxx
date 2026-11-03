-- uneXpected v8 additive migration.
-- Apply only after testing on an isolated Neon branch and confirming schema version 1.
BEGIN;

CREATE TABLE IF NOT EXISTS idempotency_claims (
    idempotency_key TEXT PRIMARY KEY,
    request_hash TEXT NOT NULL,
    task_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('running', 'completed', 'failed')),
    result_json TEXT,
    created_at DOUBLE PRECISION NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_idempotency_claims_state_updated
    ON idempotency_claims(state, updated_at);

INSERT INTO schema_migrations(version, name, applied_at)
VALUES (2, '002_idempotency_claims.sql', EXTRACT(EPOCH FROM clock_timestamp()))
ON CONFLICT(version) DO NOTHING;

COMMIT;

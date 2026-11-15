-- Additive approval-execution intent ledger for uneXpected v8.
-- Existing tasks, events, memories, approvals and workflow checkpoints are not modified.
BEGIN;

CREATE TABLE IF NOT EXISTS approval_execution_intents (
    intent_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL UNIQUE,
    request_hash TEXT NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    action_digest TEXT NOT NULL CHECK (action_digest ~ '^[0-9a-f]{64}$'),
    permission TEXT NOT NULL CHECK (length(btrim(permission)) > 0),
    workflow_id TEXT,
    stage_key TEXT,
    state TEXT NOT NULL CHECK (state IN (
        'prepared', 'awaiting_approval', 'approved', 'enqueued', 'completed', 'blocked'
    )),
    revision BIGINT NOT NULL DEFAULT 0 CHECK (revision >= 0),
    created_at DOUBLE PRECISION NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL,
    CHECK ((workflow_id IS NULL) = (stage_key IS NULL)),
    CHECK (workflow_id IS NULL OR length(btrim(workflow_id)) > 0),
    CHECK (stage_key IS NULL OR length(btrim(stage_key)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_approval_execution_intents_state_updated
    ON approval_execution_intents(state, updated_at);

INSERT INTO schema_migrations(version, name, applied_at)
VALUES (5, '005_approval_execution_intents.sql', EXTRACT(EPOCH FROM clock_timestamp()))
ON CONFLICT(version) DO NOTHING;

COMMIT;

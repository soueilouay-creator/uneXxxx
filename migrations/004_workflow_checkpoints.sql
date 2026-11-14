-- Additive durable workflow checkpoint ledger for uneXpected v8.
-- This migration creates new tables only; it does not rewrite existing task,
-- event, memory, approval, creator or user records.
BEGIN;

CREATE TABLE IF NOT EXISTS workflow_checkpoints (
    workflow_id TEXT PRIMARY KEY,
    request_hash TEXT NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    checkpoint_version INTEGER NOT NULL CHECK (checkpoint_version > 0),
    revision BIGINT NOT NULL DEFAULT 0 CHECK (revision >= 0),
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'interrupted', 'blocked')),
    current_stage TEXT,
    state_json TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_workflow_checkpoints_status_updated
    ON workflow_checkpoints(status, updated_at);

CREATE TABLE IF NOT EXISTS workflow_stage_checkpoints (
    workflow_id TEXT NOT NULL REFERENCES workflow_checkpoints(workflow_id) ON DELETE RESTRICT,
    stage_key TEXT NOT NULL,
    stage_index INTEGER NOT NULL CHECK (stage_index > 0),
    request_hash TEXT NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    status TEXT NOT NULL CHECK (status IN ('started', 'completed', 'interrupted', 'failed')),
    attempt_token TEXT NOT NULL,
    task_id TEXT,
    result_json TEXT,
    created_at DOUBLE PRECISION NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (workflow_id, stage_key),
    UNIQUE (workflow_id, stage_index)
);
CREATE INDEX IF NOT EXISTS idx_workflow_stage_checkpoints_status_updated
    ON workflow_stage_checkpoints(status, updated_at);

INSERT INTO schema_migrations(version, name, applied_at)
VALUES (4, '004_workflow_checkpoints.sql', EXTRACT(EPOCH FROM clock_timestamp()))
ON CONFLICT(version) DO NOTHING;

COMMIT;

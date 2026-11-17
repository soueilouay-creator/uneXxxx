-- Additive immutable binding between a workflow stage and its prepared approval execution.
-- Existing workflow checkpoints, tasks, events, memory and approval records are unchanged.
BEGIN;

CREATE TABLE IF NOT EXISTS workflow_stage_approval_intents (
    workflow_id TEXT NOT NULL REFERENCES workflow_checkpoints(workflow_id) ON DELETE RESTRICT,
    stage_key TEXT NOT NULL CHECK (length(btrim(stage_key)) > 0),
    stage_request_hash TEXT NOT NULL CHECK (stage_request_hash ~ '^[0-9a-f]{64}$'),
    execution_id TEXT NOT NULL UNIQUE
        REFERENCES approval_execution_intents(intent_id) ON DELETE RESTRICT,
    task_id TEXT NOT NULL UNIQUE,
    action_digest TEXT NOT NULL CHECK (action_digest ~ '^[0-9a-f]{64}$'),
    permission TEXT NOT NULL CHECK (length(btrim(permission)) > 0),
    approval_id TEXT UNIQUE,
    state TEXT NOT NULL CHECK (state IN ('awaiting_approval', 'approved', 'enqueued', 'completed', 'blocked')),
    revision BIGINT NOT NULL DEFAULT 0 CHECK (revision >= 0),
    created_at DOUBLE PRECISION NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (workflow_id, stage_key)
);

CREATE INDEX IF NOT EXISTS idx_workflow_stage_approval_state_updated
    ON workflow_stage_approval_intents(state, updated_at);

INSERT INTO schema_migrations(version, name, applied_at)
VALUES (7, '007_workflow_stage_approval_intents.sql', EXTRACT(EPOCH FROM clock_timestamp()))
ON CONFLICT(version) DO NOTHING;

COMMIT;

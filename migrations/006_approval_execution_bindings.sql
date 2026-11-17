-- Additive exact-execution binding for one-use approvals.
-- Existing consumed_approvals rows are preserved unchanged and remain unbound.
BEGIN;

CREATE TABLE IF NOT EXISTS approval_execution_bindings (
    approval_id TEXT PRIMARY KEY
        REFERENCES consumed_approvals(approval_id) ON DELETE RESTRICT,
    action_digest TEXT NOT NULL CHECK (action_digest ~ '^[0-9a-f]{64}$'),
    permission TEXT NOT NULL CHECK (length(btrim(permission)) > 0),
    execution_id TEXT NOT NULL UNIQUE,
    task_id TEXT NOT NULL UNIQUE,
    workflow_id TEXT,
    stage_key TEXT,
    consumed_at DOUBLE PRECISION NOT NULL,
    CHECK ((workflow_id IS NULL) = (stage_key IS NULL)),
    CHECK (workflow_id IS NULL OR length(btrim(workflow_id)) > 0),
    CHECK (stage_key IS NULL OR length(btrim(stage_key)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_approval_execution_bindings_task
    ON approval_execution_bindings(task_id);

INSERT INTO schema_migrations(version, name, applied_at)
VALUES (6, '006_approval_execution_bindings.sql', EXTRACT(EPOCH FROM clock_timestamp()))
ON CONFLICT(version) DO NOTHING;

COMMIT;

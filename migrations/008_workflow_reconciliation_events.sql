-- Additive append-only audit ledger for operator-attributed manual-review blocks.
-- Existing workflow, task, approval, memory and event rows are not rewritten.
BEGIN;

CREATE TABLE IF NOT EXISTS workflow_reconciliation_events (
    reconciliation_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    stage_key TEXT NOT NULL,
    checkpoint_revision_before BIGINT NOT NULL CHECK (checkpoint_revision_before >= 0),
    checkpoint_revision_after BIGINT NOT NULL
        CHECK (checkpoint_revision_after = checkpoint_revision_before + 1),
    stage_index INTEGER NOT NULL CHECK (stage_index > 0),
    stage_request_hash TEXT NOT NULL CHECK (stage_request_hash ~ '^[0-9a-f]{64}$'),
    attempt_token_sha256 TEXT NOT NULL CHECK (attempt_token_sha256 ~ '^[0-9a-f]{64}$'),
    stage_status_before TEXT NOT NULL CHECK (stage_status_before = 'started'),
    stage_status_after TEXT NOT NULL CHECK (stage_status_after = 'interrupted'),
    operator_id TEXT NOT NULL CHECK (length(btrim(operator_id)) > 0),
    reason_code TEXT NOT NULL CHECK (reason_code IN (
        'uncertain_external_effect', 'evidence_conflict', 'operator_hold'
    )),
    evidence_ref TEXT NOT NULL CHECK (length(btrim(evidence_ref)) > 0),
    evidence_sha256 TEXT NOT NULL CHECK (evidence_sha256 ~ '^[0-9a-f]{64}$'),
    disposition TEXT NOT NULL CHECK (disposition = 'blocked_for_manual_review'),
    created_at DOUBLE PRECISION NOT NULL,
    UNIQUE (workflow_id, stage_key, checkpoint_revision_before),
    FOREIGN KEY (workflow_id, stage_key)
        REFERENCES workflow_stage_checkpoints(workflow_id, stage_key) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_workflow_reconciliation_events_workflow_created
    ON workflow_reconciliation_events(workflow_id, created_at);

CREATE OR REPLACE FUNCTION reject_workflow_reconciliation_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'workflow_reconciliation_events is append-only';
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'workflow_reconciliation_events_no_update'
          AND tgrelid = 'workflow_reconciliation_events'::regclass
    ) THEN
        CREATE TRIGGER workflow_reconciliation_events_no_update
        BEFORE UPDATE ON workflow_reconciliation_events
        FOR EACH ROW EXECUTE FUNCTION reject_workflow_reconciliation_event_mutation();
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'workflow_reconciliation_events_no_delete'
          AND tgrelid = 'workflow_reconciliation_events'::regclass
    ) THEN
        CREATE TRIGGER workflow_reconciliation_events_no_delete
        BEFORE DELETE ON workflow_reconciliation_events
        FOR EACH ROW EXECUTE FUNCTION reject_workflow_reconciliation_event_mutation();
    END IF;
END;
$$;

INSERT INTO schema_migrations(version, name, applied_at)
VALUES (8, '008_workflow_reconciliation_events.sql', EXTRACT(EPOCH FROM clock_timestamp()))
ON CONFLICT(version) DO NOTHING;

COMMIT;

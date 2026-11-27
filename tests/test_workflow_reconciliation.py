from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from unexpected_runtime.recovery_inspection import inspect_workflow_recovery
from unexpected_runtime.storage import StateStore
from unexpected_runtime.workflow_reconciliation import attempt_token_sha256
from unexpected_runtime.postgres_storage import PostgresStateStore


class SQLiteWorkflowReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "state.sqlite3"
        self.store = StateStore(self.path)
        self.workflow_id = "workflow-" + uuid.uuid4().hex
        self.stage_key = "0001:plan"
        self.stage_hash = "b" * 64
        self.attempt_token = "private-attempt-token-" + uuid.uuid4().hex
        self.store.set_memory("orchestrator", "reconciliation-preservation", {"keep": True})
        self.store.create_workflow_checkpoint(
            self.workflow_id, "a" * 64, 1,
            {"request": {"objective": "synthetic reconciliation fixture"}, "completed_stages": []},
        )
        self.store.begin_workflow_stage(
            self.workflow_id, self.stage_key, 1, self.stage_hash, self.attempt_token
        )

    def _request(self, **overrides):
        values = {
            "reconciliation_id": "reconcile-" + uuid.uuid4().hex,
            "workflow_id": self.workflow_id,
            "stage_key": self.stage_key,
            "expected_checkpoint_revision": 0,
            "expected_stage_index": 1,
            "expected_stage_request_hash": self.stage_hash,
            "expected_attempt_token_sha256": attempt_token_sha256(self.attempt_token),
            "operator_id": "operator:synthetic-reviewer",
            "reason_code": "uncertain_external_effect",
            "evidence_ref": "incident:fixture-001",
            "evidence_sha256": "c" * 64,
        }
        values.update(overrides)
        return values

    def test_blocks_started_stage_and_reads_back_immutable_audit(self):
        result = self.store.record_workflow_reconciliation_block(**self._request())
        self.assertTrue(result["recorded"])
        self.assertFalse(result["idempotent_replay"])
        self.assertEqual(result["checkpoint"], {"status": "blocked", "revision": 1})

        checkpoint = self.store.get_workflow_checkpoint(self.workflow_id)
        stage = self.store.list_workflow_stages(self.workflow_id)[0]
        events = self.store.list_workflow_reconciliation_events(self.workflow_id)
        self.assertEqual(checkpoint["status"], "blocked")
        self.assertEqual(checkpoint["revision"], 1)
        self.assertEqual(stage["status"], "interrupted")
        self.assertEqual(stage["attempt_token"], self.attempt_token)
        self.assertEqual(stage["result"], None)
        self.assertFalse(self.store.complete_workflow_stage(
            self.workflow_id, self.stage_key, self.attempt_token, None, {"late": True}
        ))

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["stage_status_before"], "started")
        self.assertEqual(event["stage_status_after"], "interrupted")
        self.assertEqual(event["checkpoint_revision_before"], 0)
        self.assertEqual(event["checkpoint_revision_after"], 1)
        self.assertEqual(event["attempt_token_sha256"], attempt_token_sha256(self.attempt_token))
        self.assertNotIn(self.attempt_token, json.dumps(event))

        reopened = StateStore(self.path)
        self.assertEqual(reopened.list_workflow_reconciliation_events(self.workflow_id), events)
        self.assertEqual(
            reopened.get_memory("orchestrator", "reconciliation-preservation"),
            {"keep": True},
        )

    def test_inspection_exposes_only_stage_fingerprints_not_attempt_token(self):
        report = inspect_workflow_recovery(self.store, self.workflow_id)
        stage = report["stages"][0]
        self.assertEqual(stage["stage_request_hash"], self.stage_hash)
        self.assertEqual(stage["attempt_token_sha256"], attempt_token_sha256(self.attempt_token))
        self.assertNotIn(self.attempt_token, json.dumps(report))

    def test_same_event_id_is_idempotent_but_cannot_be_rebound(self):
        request = self._request(reconciliation_id="reconcile-idempotent")
        first = self.store.record_workflow_reconciliation_block(**request)
        second = self.store.record_workflow_reconciliation_block(**request)
        self.assertTrue(first["recorded"])
        self.assertTrue(second["idempotent_replay"])
        self.assertEqual(self.store.get_workflow_checkpoint(self.workflow_id)["revision"], 1)
        self.assertEqual(len(self.store.list_workflow_reconciliation_events(self.workflow_id)), 1)
        with self.assertRaises(ValueError):
            self.store.record_workflow_reconciliation_block(
                **{**request, "evidence_ref": "incident:different"}
            )

    def test_stale_revision_and_mismatched_stage_fingerprints_do_not_write(self):
        stale = self.store.record_workflow_reconciliation_block(
            **self._request(reconciliation_id="reconcile-stale", expected_checkpoint_revision=4)
        )
        bad_attempt = self.store.record_workflow_reconciliation_block(
            **self._request(reconciliation_id="reconcile-bad-attempt", expected_attempt_token_sha256="d" * 64)
        )
        bad_request = self.store.record_workflow_reconciliation_block(
            **self._request(reconciliation_id="reconcile-bad-request", expected_stage_request_hash="e" * 64)
        )
        self.assertFalse(stale["recorded"])
        self.assertFalse(bad_attempt["recorded"])
        self.assertFalse(bad_request["recorded"])
        self.assertEqual(self.store.get_workflow_checkpoint(self.workflow_id)["status"], "running")
        self.assertEqual(self.store.list_workflow_stages(self.workflow_id)[0]["status"], "started")
        self.assertEqual(self.store.list_workflow_reconciliation_events(self.workflow_id), [])

    def test_event_insert_failure_rolls_back_stage_and_checkpoint_together(self):
        with self.store._session() as connection:
            connection.execute(
                "CREATE TRIGGER fail_reconciliation_insert BEFORE INSERT ON workflow_reconciliation_events "
                "BEGIN SELECT RAISE(ABORT,'synthetic audit insert failure'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.record_workflow_reconciliation_block(**self._request())
        self.assertEqual(self.store.get_workflow_checkpoint(self.workflow_id)["status"], "running")
        self.assertEqual(self.store.get_workflow_checkpoint(self.workflow_id)["revision"], 0)
        self.assertEqual(self.store.list_workflow_stages(self.workflow_id)[0]["status"], "started")
        self.assertEqual(self.store.list_workflow_reconciliation_events(self.workflow_id), [])

    def test_audit_event_rejects_update_and_delete(self):
        self.store.record_workflow_reconciliation_block(**self._request())
        event_id = self.store.list_workflow_reconciliation_events(self.workflow_id)[0]["reconciliation_id"]
        with self.assertRaises(sqlite3.IntegrityError):
            with self.store._session() as connection:
                connection.execute(
                    "UPDATE workflow_reconciliation_events SET operator_id='changed' WHERE reconciliation_id=?",
                    (event_id,),
                )
        with self.assertRaises(sqlite3.IntegrityError):
            with self.store._session() as connection:
                connection.execute(
                    "DELETE FROM workflow_reconciliation_events WHERE reconciliation_id=?",
                    (event_id,),
                )
        self.assertEqual(len(self.store.list_workflow_reconciliation_events(self.workflow_id)), 1)

    def test_concurrent_operators_have_one_compare_and_set_winner(self):
        barrier = threading.Barrier(12)
        def attempt(index):
            store = StateStore(self.path)
            barrier.wait(timeout=10)
            return store.record_workflow_reconciliation_block(**self._request(
                reconciliation_id=f"reconcile-race-{index}"
            ))
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(attempt, range(12)))
        self.assertEqual(sum(bool(item["recorded"]) for item in results), 1)
        self.assertEqual(sum(not item["recorded"] for item in results), 11)
        self.assertEqual(len(self.store.list_workflow_reconciliation_events(self.workflow_id)), 1)
        self.assertEqual(self.store.get_workflow_checkpoint(self.workflow_id)["status"], "blocked")
        self.assertEqual(self.store.list_workflow_stages(self.workflow_id)[0]["status"], "interrupted")


class PostgresWorkflowReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ.get("TEST_POSTGRES_DSN")
        if not cls.dsn:
            raise unittest.SkipTest("TEST_POSTGRES_DSN is not configured.")

    def setUp(self):
        self.store = PostgresStateStore(self.dsn)
        self.workflow_id = "workflow-" + uuid.uuid4().hex
        self.stage_key = "0001:plan"
        self.stage_hash = "b" * 64
        self.attempt_token = "private-postgres-attempt-" + uuid.uuid4().hex
        self.store.create_workflow_checkpoint(
            self.workflow_id, "a" * 64, 1,
            {"request": {"objective": "synthetic PostgreSQL reconciliation fixture"}, "completed_stages": []},
        )
        self.store.begin_workflow_stage(
            self.workflow_id, self.stage_key, 1, self.stage_hash, self.attempt_token
        )

    def _request(self, **overrides):
        values = {
            "reconciliation_id": "reconcile-" + uuid.uuid4().hex,
            "workflow_id": self.workflow_id,
            "stage_key": self.stage_key,
            "expected_checkpoint_revision": 0,
            "expected_stage_index": 1,
            "expected_stage_request_hash": self.stage_hash,
            "expected_attempt_token_sha256": attempt_token_sha256(self.attempt_token),
            "operator_id": "operator:postgres-reviewer",
            "reason_code": "uncertain_external_effect",
            "evidence_ref": "incident:postgres-fixture-001",
            "evidence_sha256": "c" * 64,
        }
        values.update(overrides)
        return values

    def test_postgres_transition_is_atomic_and_readable_after_reopen(self):
        result = self.store.record_workflow_reconciliation_block(**self._request())
        self.assertTrue(result["recorded"])
        reopened = PostgresStateStore(self.dsn)
        checkpoint = reopened.get_workflow_checkpoint(self.workflow_id)
        stage = reopened.list_workflow_stages(self.workflow_id)[0]
        events = reopened.list_workflow_reconciliation_events(self.workflow_id)
        self.assertEqual(checkpoint["status"], "blocked")
        self.assertEqual(checkpoint["revision"], 1)
        self.assertEqual(stage["status"], "interrupted")
        self.assertEqual(stage["attempt_token"], self.attempt_token)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["disposition"], "blocked_for_manual_review")
        self.assertNotIn(self.attempt_token, json.dumps(events[0]))
        self.assertFalse(reopened.complete_workflow_stage(
            self.workflow_id, self.stage_key, self.attempt_token, None, {"late": True}
        ))

    def test_postgres_same_event_id_is_idempotent_and_stale_revision_is_rejected(self):
        request = self._request(reconciliation_id="reconcile-pg-idempotent-" + uuid.uuid4().hex)
        first = self.store.record_workflow_reconciliation_block(**request)
        second = self.store.record_workflow_reconciliation_block(**request)
        stale = self.store.record_workflow_reconciliation_block(**self._request(
            reconciliation_id="reconcile-pg-stale-" + uuid.uuid4().hex,
            expected_checkpoint_revision=4,
        ))
        bad_attempt = self.store.record_workflow_reconciliation_block(**self._request(
            reconciliation_id="reconcile-pg-bad-attempt-" + uuid.uuid4().hex,
            expected_attempt_token_sha256="d" * 64,
        ))
        self.assertTrue(first["recorded"])
        self.assertTrue(second["idempotent_replay"])
        self.assertFalse(stale["recorded"])
        self.assertFalse(bad_attempt["recorded"])
        self.assertEqual(len(self.store.list_workflow_reconciliation_events(self.workflow_id)), 1)

    def test_postgres_concurrent_connections_have_one_compare_and_set_winner(self):
        barrier = threading.Barrier(12)
        def attempt(index):
            store = PostgresStateStore(self.dsn)
            barrier.wait(timeout=10)
            return store.record_workflow_reconciliation_block(**self._request(
                reconciliation_id=f"reconcile-pg-race-{uuid.uuid4().hex}-{index}"
            ))
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(attempt, range(12)))
        self.assertEqual(sum(bool(item["recorded"]) for item in results), 1)
        self.assertEqual(sum(not item["recorded"] for item in results), 11)
        self.assertEqual(len(self.store.list_workflow_reconciliation_events(self.workflow_id)), 1)
        self.assertEqual(self.store.get_workflow_checkpoint(self.workflow_id)["status"], "blocked")
        self.assertEqual(self.store.list_workflow_stages(self.workflow_id)[0]["status"], "interrupted")

    def test_postgres_audit_insert_failure_rolls_back_stage_and_checkpoint(self):
        suffix = uuid.uuid4().hex
        trigger_name = "fail_reconciliation_insert_" + suffix
        function_name = "fail_reconciliation_insert_fn_" + suffix
        with self.store._session() as connection:
            connection.execute(
                f"CREATE FUNCTION {function_name}() RETURNS trigger LANGUAGE plpgsql "
                "AS $ BEGIN RAISE EXCEPTION 'synthetic audit insert failure'; END; $"
            )
            connection.execute(
                f"CREATE TRIGGER {trigger_name} BEFORE INSERT ON workflow_reconciliation_events "
                f"FOR EACH ROW WHEN (NEW.workflow_id = '{self.workflow_id}') "
                f"EXECUTE FUNCTION {function_name}()"
            )
        try:
            with self.assertRaises(Exception):
                self.store.record_workflow_reconciliation_block(**self._request())
        finally:
            with self.store._session() as connection:
                connection.execute(
                    f"DROP TRIGGER {trigger_name} ON workflow_reconciliation_events"
                )
                connection.execute(f"DROP FUNCTION {function_name}()")
        self.assertEqual(self.store.get_workflow_checkpoint(self.workflow_id)["status"], "running")
        self.assertEqual(self.store.get_workflow_checkpoint(self.workflow_id)["revision"], 0)
        self.assertEqual(self.store.list_workflow_stages(self.workflow_id)[0]["status"], "started")
        self.assertEqual(self.store.list_workflow_reconciliation_events(self.workflow_id), [])

    def test_postgres_audit_event_rejects_update_and_delete(self):
        self.store.record_workflow_reconciliation_block(**self._request())
        event_id = self.store.list_workflow_reconciliation_events(self.workflow_id)[0]["reconciliation_id"]
        with self.assertRaises(Exception):
            with self.store._session() as connection:
                connection.execute(
                    "UPDATE workflow_reconciliation_events SET operator_id='changed' WHERE reconciliation_id=%s",
                    (event_id,),
                )
        with self.assertRaises(Exception):
            with self.store._session() as connection:
                connection.execute(
                    "DELETE FROM workflow_reconciliation_events WHERE reconciliation_id=%s",
                    (event_id,),
                )
        self.assertEqual(len(self.store.list_workflow_reconciliation_events(self.workflow_id)), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)

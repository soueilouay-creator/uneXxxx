from __future__ import annotations

import os
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor

from unexpected_runtime.postgres_approval_ledger import PostgresApprovalLedger
from unexpected_runtime.approvals import GitHubPullRequestApprovalVerifier
from unexpected_runtime.models import ApprovalExecutionBinding


class Cursor:
    def __init__(self, row):
        self.row = row
    def fetchone(self):
        return self.row


class SharedLedgerDB:
    def __init__(self):
        self.lock = threading.RLock()
        self.consumed = {}
        self.bindings = {}
        self.sql = []
        self.fail = False
        self.fail_binding = False

    def connect(self):
        return FakeConnection(self)


class FakeConnection:
    def __init__(self, db):
        self.db = db
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.pending_consumed = None
        self.pending_binding = None
        self.lock_held = False

    def execute(self, sql, params):
        self.db.sql.append(sql)
        if self.db.fail:
            raise RuntimeError("simulated database outage")
        if sql.startswith("INSERT INTO consumed_approvals"):
            self.db.lock.acquire()
            self.lock_held = True
            approval_id, digest, consumed_at = params
            if approval_id in self.db.consumed:
                return Cursor(None)
            self.pending_consumed = (approval_id, digest, consumed_at)
            return Cursor({"approval_id": approval_id})
        if sql.startswith("INSERT INTO approval_execution_bindings"):
            if self.db.fail_binding:
                raise RuntimeError("simulated binding-table failure")
            approval_id, digest, permission, execution_id, task_id, workflow_id, stage_key, consumed_at = params
            if approval_id in self.db.bindings:
                return Cursor(None)
            if any(row["execution_id"] == execution_id or row["task_id"] == task_id
                   for row in self.db.bindings.values()):
                return Cursor(None)
            self.pending_binding = {
                "approval_id": approval_id, "action_digest": digest, "permission": permission,
                "execution_id": execution_id, "task_id": task_id,
                "workflow_id": workflow_id, "stage_key": stage_key, "consumed_at": consumed_at,
            }
            return Cursor({"approval_id": approval_id})
        if sql.startswith("SELECT approval_id,action_digest,permission,execution_id,task_id,workflow_id,stage_key,consumed_at FROM approval_execution_bindings"):
            approval_id = params[0]
            with self.db.lock:
                row = self.db.bindings.get(approval_id)
                return Cursor(dict(row) if row else None)
        raise AssertionError("Unexpected SQL in fake Postgres test: " + sql)

    def commit(self):
        if self.pending_consumed:
            approval_id, digest, consumed_at = self.pending_consumed
            self.db.consumed[approval_id] = {"action_digest": digest, "consumed_at": consumed_at}
        if self.pending_binding:
            self.db.bindings[self.pending_binding["approval_id"]] = dict(self.pending_binding)
        self.committed = True
        self._release()

    def rollback(self):
        self.rolled_back = True
        self.pending_consumed = None
        self.pending_binding = None
        self._release()

    def _release(self):
        if self.lock_held:
            self.lock_held = False
            self.db.lock.release()

    def close(self):
        if self.lock_held:
            self._release()
        self.closed = True


class PostgresApprovalLedgerTests(unittest.TestCase):
    def setUp(self):
        self.db = SharedLedgerDB()
        self.ledger = PostgresApprovalLedger(
            "postgresql://unit-test.invalid/db",
            connect_factory=self.db.connect,
        )

    def test_consumes_approval_once_and_binds_exact_digest(self):
        digest = "a" * 64
        self.assertTrue(self.ledger.consume_once("github-pr:17:proposal", digest))
        self.assertFalse(self.ledger.consume_once("github-pr:17:proposal", digest))
        self.assertFalse(self.ledger.consume_once("github-pr:17:proposal", "b" * 64))
        self.assertEqual(self.db.consumed["github-pr:17:proposal"]["action_digest"], digest)
        self.assertIn("ON CONFLICT(approval_id) DO NOTHING RETURNING approval_id", self.db.sql[0])

    def test_concurrent_duplicate_consumption_has_exactly_one_winner(self):
        digest = "c" * 64
        with ThreadPoolExecutor(max_workers=16) as pool:
            results = list(pool.map(
                lambda _: self.ledger.consume_once("github-pr:18:single-use", digest),
                range(32),
            ))
        self.assertEqual(sum(results), 1)

    def test_invalid_input_fails_closed_without_database_call(self):
        self.assertFalse(self.ledger.consume_once("", "a" * 64))
        self.assertFalse(self.ledger.consume_once("approval", "short"))
        self.assertEqual(self.db.sql, [])

    def test_database_error_is_not_converted_to_approval_success(self):
        self.db.fail = True
        with self.assertRaises(RuntimeError):
            self.ledger.consume_once("github-pr:19:db-down", "d" * 64)

    def test_github_verifier_delegates_consumption_to_injected_postgres_ledger(self):
        class Ledger:
            def __init__(self):
                self.calls = []
            def consume_once(self, approval_id, action_digest):
                self.calls.append((approval_id, action_digest))
                return True
        ledger = Ledger()
        verifier = GitHubPullRequestApprovalVerifier(
            repository="owner/repo",
            token="github-read-only-token",
            trusted_reviewers=("reviewer",),
            ledger=ledger,
        )
        self.assertTrue(verifier._consume_once("github-pr:20:proposal", "e" * 64))
        self.assertEqual(ledger.calls, [("github-pr:20:proposal", "e" * 64)])

    def test_bound_consumption_persists_exact_binding(self):
        binding = ApprovalExecutionBinding("exec-A", "task-A", "workflow-A", "0001:execute")
        approval_id = "github-pr:21:bound"
        digest = "f" * 64
        self.assertTrue(self.ledger.consume_once_bound(approval_id, digest, "repo_write", binding))
        self.assertEqual(
            self.ledger.get_consumed_binding(approval_id),
            {
                "approval_id": approval_id, "action_digest": digest, "permission": "repo_write",
                **binding.to_dict(), "consumed_at": self.db.bindings[approval_id]["consumed_at"],
            },
        )
        self.assertFalse(self.ledger.consume_once_bound(approval_id, digest, "repo_write", binding))

    def test_bound_consumption_is_single_winner_under_concurrency(self):
        binding = ApprovalExecutionBinding("exec-race", "task-race")
        with ThreadPoolExecutor(max_workers=16) as pool:
            results = list(pool.map(
                lambda _: self.ledger.consume_once_bound(
                    "github-pr:22:race", "a" * 64, "repo_write", binding
                ),
                range(32),
            ))
        self.assertEqual(sum(results), 1)
        self.assertIsNotNone(self.ledger.get_consumed_binding("github-pr:22:race"))

    def test_execution_and_task_ownership_are_unique_across_approvals(self):
        first = ApprovalExecutionBinding("exec-unique", "task-unique")
        self.assertTrue(self.ledger.consume_once_bound("github-pr:23:first", "b" * 64, "repo_write", first))
        second = ApprovalExecutionBinding("exec-other", "task-unique")
        self.assertFalse(self.ledger.consume_once_bound("github-pr:23:second", "c" * 64, "repo_write", second))
        third = ApprovalExecutionBinding("exec-unique", "task-other")
        self.assertFalse(self.ledger.consume_once_bound("github-pr:23:third", "d" * 64, "repo_write", third))
        self.assertNotIn("github-pr:23:second", self.db.consumed)
        self.assertNotIn("github-pr:23:third", self.db.consumed)

    def test_binding_insert_failure_rolls_back_consumed_approval(self):
        self.db.fail_binding = True
        with self.assertRaises(RuntimeError):
            self.ledger.consume_once_bound(
                "github-pr:24:rollback", "e" * 64, "repo_write",
                ApprovalExecutionBinding("exec-rollback", "task-rollback"),
            )
        self.assertNotIn("github-pr:24:rollback", self.db.consumed)
        self.assertNotIn("github-pr:24:rollback", self.db.bindings)

    def test_legacy_unbound_consumption_is_retained_without_binding(self):
        approval_id = "github-pr:25:legacy"
        digest = "9" * 64
        self.assertTrue(self.ledger.consume_once(approval_id, digest))
        self.assertIsNone(self.ledger.get_consumed_binding(approval_id))
        self.assertFalse(self.ledger.consume_once_bound(
            approval_id, digest, "repo_write", ApprovalExecutionBinding("exec-legacy", "task-legacy")
        ))
        self.assertEqual(self.db.consumed[approval_id]["action_digest"], digest)

    def test_rejects_non_postgres_dsn(self):
        with self.assertRaises(ValueError):
            PostgresApprovalLedger("sqlite:///not-postgres")


POSTGRES_DSN = os.getenv("TEST_POSTGRES_DSN")


@unittest.skipUnless(POSTGRES_DSN, "TEST_POSTGRES_DSN is provided only by ephemeral PostgreSQL CI")
class PostgresApprovalLedgerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.ledger = PostgresApprovalLedger(POSTGRES_DSN)
        self.prefix = "approval-bind-" + uuid.uuid4().hex

    def test_bound_consumption_survives_independent_connections_and_conflict_rolls_back(self):
        approval_id = self.prefix + "-first"
        digest = "a" * 64
        binding = ApprovalExecutionBinding(self.prefix + "-execution", self.prefix + "-task")
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(
                lambda _: self.ledger.consume_once_bound(approval_id, digest, "repo_write", binding),
                range(24),
            ))
        self.assertEqual(sum(results), 1)
        persisted = self.ledger.get_consumed_binding(approval_id)
        self.assertEqual(persisted["execution_id"], binding.execution_id)
        self.assertEqual(persisted["task_id"], binding.task_id)

        conflict_approval = self.prefix + "-conflict"
        conflicting = ApprovalExecutionBinding(self.prefix + "-other-execution", binding.task_id)
        self.assertFalse(self.ledger.consume_once_bound(
            conflict_approval, "b" * 64, "repo_write", conflicting
        ))
        # A binding uniqueness conflict rolls back the preceding one-use insert.
        rebound = ApprovalExecutionBinding(self.prefix + "-rebound-execution", self.prefix + "-new-task")
        self.assertTrue(self.ledger.consume_once_bound(
            conflict_approval, "b" * 64, "repo_write", rebound
        ))

    def test_legacy_consumed_row_has_no_binding_and_cannot_be_bound_later(self):
        approval_id = self.prefix + "-legacy"
        digest = "c" * 64
        self.assertTrue(self.ledger.consume_once(approval_id, digest))
        self.assertIsNone(self.ledger.get_consumed_binding(approval_id))
        self.assertFalse(self.ledger.consume_once_bound(
            approval_id, digest, "repo_write",
            ApprovalExecutionBinding(self.prefix + "-late", self.prefix + "-late-task"),
        ))


if __name__ == "__main__":
    unittest.main(verbosity=2)

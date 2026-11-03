from __future__ import annotations

import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

from unexpected_runtime.postgres_approval_ledger import PostgresApprovalLedger
from unexpected_runtime.approvals import GitHubPullRequestApprovalVerifier


class Cursor:
    def __init__(self, row):
        self.row = row
    def fetchone(self):
        return self.row


class SharedLedgerDB:
    def __init__(self):
        self.lock = threading.Lock()
        self.consumed = {}
        self.sql = []
        self.fail = False

    def connect(self):
        return FakeConnection(self)


class FakeConnection:
    def __init__(self, db):
        self.db = db
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def execute(self, sql, params):
        self.db.sql.append(sql)
        if self.db.fail:
            raise RuntimeError("simulated database outage")
        approval_id, digest = params
        with self.db.lock:
            if approval_id in self.db.consumed:
                return Cursor(None)
            self.db.consumed[approval_id] = digest
            return Cursor({"approval_id": approval_id})

    def commit(self):
        self.committed = True
    def rollback(self):
        self.rolled_back = True
    def close(self):
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
        self.assertEqual(self.db.consumed["github-pr:17:proposal"], digest)
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

    def test_rejects_non_postgres_dsn(self):
        with self.assertRaises(ValueError):
            PostgresApprovalLedger("sqlite:///not-postgres")


if __name__ == "__main__":
    unittest.main(verbosity=2)

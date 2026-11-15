from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from unexpected_runtime.postgres_storage import PostgresStateStore
from unexpected_runtime.storage import StateStore
from unexpected_runtime.models import TaskRequest


def intent_values(*, intent_id=None, task_id=None, request_hash="a" * 64, action_digest="b" * 64, permission="repo_write", workflow_id=None, stage_key=None):
    return {
        "intent_id": intent_id or "intent-" + uuid.uuid4().hex,
        "task_id": task_id or "task-" + uuid.uuid4().hex,
        "request_hash": request_hash,
        "action_digest": action_digest,
        "permission": permission,
        "workflow_id": workflow_id,
        "stage_key": stage_key,
    }


class ApprovalExecutionIntentStoreContract:
    def create(self, **overrides):
        return self.store.create_approval_execution_intent(**intent_values(**overrides))

    def test_create_read_and_reopen_preserve_the_same_intent(self):
        values = intent_values()
        created = self.store.create_approval_execution_intent(**values)
        self.assertEqual(created["intent_id"], values["intent_id"])
        self.assertEqual(created["task_id"], values["task_id"])
        self.assertEqual(created["request_hash"], values["request_hash"])
        self.assertEqual(created["action_digest"], values["action_digest"])
        self.assertEqual(created["permission"], values["permission"])
        self.assertIsNone(created["workflow_id"])
        self.assertIsNone(created["stage_key"])
        self.assertEqual(created["state"], "prepared")
        self.assertEqual(created["revision"], 0)
        reopened = self.reopen_store()
        self.assertEqual(reopened.get_approval_execution_intent(values["intent_id"]), created)


    def test_intent_operations_preserve_existing_task_event_and_memory_records(self):
        request = TaskRequest.create(
            "orchestrator", "Preserve existing state during approval intent storage",
            inputs={"preservation_fixture": True},
        )
        self.store.enqueue(request)
        self.store.set_memory("orchestrator", "approval-intent-preservation", {"keep": "memory"})
        self.store.log_event(
            "approval_intent_preservation", request.task_id, "orchestrator", {"keep": "event"}
        )
        before_task = self.store.get_task(request.task_id)
        before_events = self.store.list_task_events(request.task_id, limit=20)
        before_memory = self.store.get_memory("orchestrator", "approval-intent-preservation")

        created = self.create()
        self.assertEqual(created["state"], "prepared")
        self.assertTrue(self.store.transition_approval_execution_intent(
            created["intent_id"], "prepared", "awaiting_approval", 0
        ))

        reopened = self.reopen_store()
        self.assertEqual(reopened.get_task(request.task_id), before_task)
        self.assertEqual(reopened.list_task_events(request.task_id, limit=20), before_events)
        self.assertEqual(
            reopened.get_memory("orchestrator", "approval-intent-preservation"), before_memory
        )
        self.assertEqual(
            reopened.get_approval_execution_intent(created["intent_id"])["state"], "awaiting_approval"
        )

    def test_identical_create_is_idempotent_and_does_not_reset_state(self):
        values = intent_values()
        self.store.create_approval_execution_intent(**values)
        self.assertTrue(self.store.transition_approval_execution_intent(
            values["intent_id"], "prepared", "awaiting_approval", 0
        ))
        repeated = self.store.create_approval_execution_intent(**values)
        self.assertEqual(repeated["state"], "awaiting_approval")
        self.assertEqual(repeated["revision"], 1)

    def test_reusing_intent_id_with_changed_identity_is_rejected_without_mutation(self):
        values = intent_values()
        original = self.store.create_approval_execution_intent(**values)
        changed = dict(values, action_digest="c" * 64)
        with self.assertRaises(ValueError):
            self.store.create_approval_execution_intent(**changed)
        self.assertEqual(self.store.get_approval_execution_intent(values["intent_id"]), original)

    def test_one_task_id_cannot_be_owned_by_two_intents(self):
        task_id = "single-task-" + uuid.uuid4().hex
        first = intent_values(task_id=task_id)
        self.store.create_approval_execution_intent(**first)
        second = intent_values(task_id=task_id)
        with self.assertRaises(ValueError):
            self.store.create_approval_execution_intent(**second)
        self.assertEqual(self.store.get_approval_execution_intent(first["intent_id"])["task_id"], task_id)
        self.assertIsNone(self.store.get_approval_execution_intent(second["intent_id"]))

    def test_workflow_id_and_stage_key_must_be_supplied_together(self):
        with self.assertRaises(ValueError):
            self.create(workflow_id="workflow-only")
        with self.assertRaises(ValueError):
            self.create(stage_key="0001:execute")

    def test_hashes_and_permission_are_validated(self):
        values = intent_values(request_hash="not-a-digest")
        with self.assertRaises(ValueError):
            self.store.create_approval_execution_intent(**values)
        values = intent_values(permission="")
        with self.assertRaises(ValueError):
            self.store.create_approval_execution_intent(**values)

    def test_transitions_use_expected_state_and_revision(self):
        created = self.create()
        intent_id = created["intent_id"]
        self.assertTrue(self.store.transition_approval_execution_intent(
            intent_id, "prepared", "awaiting_approval", 0
        ))
        self.assertFalse(self.store.transition_approval_execution_intent(
            intent_id, "prepared", "approved", 0
        ))
        current = self.store.get_approval_execution_intent(intent_id)
        self.assertEqual(current["state"], "awaiting_approval")
        self.assertEqual(current["revision"], 1)
        with self.assertRaises(ValueError):
            self.store.transition_approval_execution_intent(
                intent_id, "awaiting_approval", "prepared", 1
            )
        self.assertTrue(self.store.transition_approval_execution_intent(
            intent_id, "awaiting_approval", "approved", 1
        ))
        self.assertTrue(self.store.transition_approval_execution_intent(
            intent_id, "approved", "enqueued", 2
        ))
        self.assertTrue(self.store.transition_approval_execution_intent(
            intent_id, "enqueued", "completed", 3
        ))
        with self.assertRaises(ValueError):
            self.store.transition_approval_execution_intent(
                intent_id, "completed", "prepared", 4
            )
        final = self.store.get_approval_execution_intent(intent_id)
        self.assertEqual(final["state"], "completed")
        self.assertEqual(final["revision"], 4)

    def test_concurrent_state_transition_has_exactly_one_winner(self):
        created = self.create()
        intent_id = created["intent_id"]
        def transition(_):
            return self.store.transition_approval_execution_intent(
                intent_id, "prepared", "awaiting_approval", 0
            )
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(transition, range(2)))
        self.assertEqual(sum(results), 1)
        current = self.store.get_approval_execution_intent(intent_id)
        self.assertEqual(current["state"], "awaiting_approval")
        self.assertEqual(current["revision"], 1)


class SQLiteApprovalExecutionIntentTests(unittest.TestCase, ApprovalExecutionIntentStoreContract):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.directory.name) / "state.sqlite3"
        self.store = StateStore(self.database_path)

    def tearDown(self):
        self.directory.cleanup()

    def reopen_store(self):
        return StateStore(self.database_path)


    def test_opening_legacy_sqlite_database_adds_intent_table_without_rewriting_rows(self):
        legacy_path = Path(self.directory.name) / "legacy.sqlite3"
        with sqlite3.connect(legacy_path) as connection:
            connection.executescript("""
                CREATE TABLE tasks(
                    task_id TEXT PRIMARY KEY,agent_id TEXT NOT NULL,status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,result_json TEXT,created_at REAL NOT NULL,updated_at REAL NOT NULL
                );
                CREATE TABLE events(
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,ts REAL NOT NULL,task_id TEXT,
                    agent_id TEXT,event_type TEXT NOT NULL,payload_json TEXT NOT NULL
                );
                CREATE TABLE agent_memory(
                    agent_id TEXT NOT NULL,key TEXT NOT NULL,value_json TEXT NOT NULL,
                    updated_at REAL NOT NULL,PRIMARY KEY(agent_id,key)
                );
            """)
            connection.execute(
                "INSERT INTO tasks VALUES(?,?,?,?,?,?,?)",
                ("legacy-task", "orchestrator", "completed", '{"legacy":true}', '{"ok":true}', 10.0, 11.0),
            )
            connection.execute(
                "INSERT INTO events(ts,task_id,agent_id,event_type,payload_json) VALUES(?,?,?,?,?)",
                (12.0, "legacy-task", "orchestrator", "legacy_event", '{"retained":true}'),
            )
            connection.execute(
                "INSERT INTO agent_memory VALUES(?,?,?,?)",
                ("orchestrator", "legacy-memory", '{"retained":"yes"}', 13.0),
            )

        upgraded = StateStore(legacy_path)
        original_task = upgraded.get_task("legacy-task")
        original_events = upgraded.list_task_events("legacy-task", limit=20)
        original_memory = upgraded.get_memory("orchestrator", "legacy-memory")
        values = intent_values(intent_id="legacy-intent", task_id="legacy-intent-task")
        intent = upgraded.create_approval_execution_intent(**values)

        reopened = StateStore(legacy_path)
        self.assertEqual(reopened.get_task("legacy-task"), original_task)
        self.assertEqual(reopened.list_task_events("legacy-task", limit=20), original_events)
        self.assertEqual(reopened.get_memory("orchestrator", "legacy-memory"), original_memory)
        self.assertEqual(reopened.get_approval_execution_intent("legacy-intent"), intent)


POSTGRES_DSN = os.getenv("TEST_POSTGRES_DSN")


@unittest.skipUnless(POSTGRES_DSN, "TEST_POSTGRES_DSN is provided only by ephemeral PostgreSQL CI")
class PostgresApprovalExecutionIntentTests(unittest.TestCase, ApprovalExecutionIntentStoreContract):
    def setUp(self):
        self.store = PostgresStateStore(POSTGRES_DSN)

    def tearDown(self):
        self.store.close()

    def reopen_store(self):
        return PostgresStateStore(POSTGRES_DSN)


if __name__ == "__main__":
    unittest.main(verbosity=2)

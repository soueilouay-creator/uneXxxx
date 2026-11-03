from __future__ import annotations

import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from unexpected_runtime.coordinator import Coordinator
from unexpected_runtime.providers import ProviderRouter, DeterministicMockProvider
from unexpected_runtime.storage import StateStore


class BlockingProvider:
    name = "test-blocking-provider"
    configured = True
    verified = False
    retry_safe = False
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = 0
    def generate(self, **kwargs):
        self.calls += 1
        self.started.set()
        self.release.wait(timeout=5)
        return "single execution completed"


class IdempotencyClaimTests(unittest.TestCase):
    def test_sqlite_claim_has_one_concurrent_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StateStore(tmp + "/state.sqlite3")
            def claim(index):
                return store.claim_idempotency("same-key", "a" * 64, "task-" + str(index))
            with ThreadPoolExecutor(max_workers=12) as pool:
                results = list(pool.map(claim, range(24)))
            self.assertEqual(sum(item["state"] == "claimed" for item in results), 1)
            self.assertEqual(sum(item["state"] == "running" for item in results), 23)

    def test_claim_rejects_key_reuse_with_different_request_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StateStore(tmp + "/state.sqlite3")
            first = store.claim_idempotency("same-key", "a" * 64, "task-a")
            self.assertEqual(first["state"], "claimed")
            with self.assertRaises(ValueError):
                store.claim_idempotency("same-key", "b" * 64, "task-b")

    def test_completed_claim_replays_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StateStore(tmp + "/state.sqlite3")
            store.claim_idempotency("same-key", "a" * 64, "task-a")
            result = {"task_id": "task-a", "status": "completed", "output": "ok"}
            self.assertTrue(store.complete_idempotency("same-key", "task-a", result))
            replay = store.claim_idempotency("same-key", "a" * 64, "task-b")
            self.assertEqual(replay["state"], "completed")
            self.assertEqual(replay["result"], result)

    def test_expired_running_claim_can_be_recovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = StateStore(tmp + "/state.sqlite3")
            store.claim_idempotency("same-key", "a" * 64, "task-old")
            time.sleep(0.01)
            recovered = store.claim_idempotency("same-key", "a" * 64, "task-new", lease_seconds=0)
            self.assertEqual(recovered, {"state": "claimed", "task_id": "task-new"})

    def test_coordinator_executes_concurrent_duplicate_only_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = BlockingProvider()
            router = ProviderRouter({"mock": DeterministicMockProvider(), "test": provider}, default_route="test")
            coordinator = Coordinator(state_dir=tmp, provider=router, max_workers=2, max_retries=0)
            try:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    first = pool.submit(coordinator.invoke, "orchestrator", "one task", idempotency_key="dedupe-key")
                    self.assertTrue(provider.started.wait(timeout=2))
                    second = coordinator.invoke("orchestrator", "one task", idempotency_key="dedupe-key")
                    self.assertEqual(second.status, "in_progress")
                    provider.release.set()
                    completed = first.result(timeout=5)
                self.assertEqual(completed.status, "completed")
                self.assertEqual(provider.calls, 1)
                replay = coordinator.invoke("orchestrator", "one task", idempotency_key="dedupe-key")
                self.assertTrue(replay.idempotent_replay)
                self.assertEqual(replay.output, "single execution completed")
            finally:
                provider.release.set()
                coordinator.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)

from __future__ import annotations

import os
import unittest
import uuid

from unexpected_runtime.creator_studio import CreatorStudioService, CreatorStudioConflict, ENGINE_COMMIT
from unexpected_runtime.postgres_storage import PostgresStateStore


@unittest.skipUnless(os.getenv("TEST_POSTGRES_DSN"), "CI PostgreSQL service is required")
class PostgresCreatorStudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = PostgresStateStore(os.environ["TEST_POSTGRES_DSN"])
        if not cls.store.creator_schema_ready():
            raise RuntimeError("PostgreSQL migration 003 is required.")
        cls.service = CreatorStudioService(cls.store)

    def test_project_versions_render_job_and_idempotency_persist(self):
        suffix = uuid.uuid4().hex
        project = self.service.create_project(
            {
                "title": "CI Creator " + suffix[:8],
                "topic": "PostgreSQL persistence contract",
                "language": "English",
                "channel_profile": {
                    "youtube": {"format": "shorts", "aspect_ratio": "9:16"},
                    "tiktok": {"format": "vertical", "aspect_ratio": "9:16"},
                },
            },
            actor="postgres-ci",
        )
        self.assertEqual(project["status"], "idea")
        self.assertEqual(self.service.get_project(project["project_id"]), project)
        first = self.service.save_version(
            project["project_id"], "treatment",
            {"hook": "A real persisted PostgreSQL Creator Studio record."},
            parent_version_id=None, actor="postgres-ci",
        )
        second = self.service.save_version(
            project["project_id"], "storyboard",
            {"scenes": [{"id": "scene-01", "duration_seconds": 8}]},
            parent_version_id=first["version_id"], actor="postgres-ci",
        )
        self.assertEqual((first["version_no"], second["version_no"]), (1, 2))
        self.assertEqual(second["parent_version_id"], first["version_id"])
        self.assertEqual(
            [v["version_id"] for v in self.service.list_versions(project["project_id"])],
            [first["version_id"], second["version_id"]],
        )
        transition = self.service.transition_project(
            project["project_id"], "idea", "researching", "postgres-ci",
            {"reason": "verify compare-and-set in PostgreSQL"},
        )
        self.assertEqual(transition["status"], "researching")
        with self.assertRaises(CreatorStudioConflict):
            self.service.transition_project(
                project["project_id"], "idea", "researching", "postgres-ci",
                {"reason": "stale compare-and-set must fail"},
            )
        request = {
            "project_id": project["project_id"],
            "version_id": second["version_id"],
            "engine_commit": ENGINE_COMMIT,
            "style_id": "whiteboard",
            "idempotency_key": "pg-render-" + suffix,
            "resource_limits": {"cpu_seconds": 60, "memory_mb": 512, "wall_time_seconds": 90},
            "request": {"profile": "youtube_shorts"},
        }
        created = self.service.create_render_job(request)
        replay = self.service.create_render_job(request)
        self.assertEqual(created["job_id"], replay["job_id"])
        self.assertEqual(created["status"], "blocked")
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(self.service.get_render_job(created["job_id"])["request_hash"], created["request_hash"])
        with self.assertRaises(CreatorStudioConflict):
            self.service.create_render_job({**request, "style_id": "woodcut"})


if __name__ == "__main__":
    unittest.main(verbosity=2)

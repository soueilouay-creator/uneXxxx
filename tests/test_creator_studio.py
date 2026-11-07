from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from unexpected_runtime.creator_studio import (
    CreatorStudioService,
    CreatorStudioError,
    CreatorStudioConflict,
    CreatorStudioNotFound,
)
from unexpected_runtime.storage import StateStore


class MemoryArtifactStore:
    def __init__(self):
        self.objects = {}

    def put(self, storage_key: str, content: bytes):
        if storage_key in self.objects:
            raise ValueError("Storage key already exists.")
        self.objects[storage_key] = bytes(content)
        return storage_key


class CreatorStudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = StateStore(Path(self.temp.name) / "creator.sqlite3")
        self.artifacts = MemoryArtifactStore()
        self.service = CreatorStudioService(self.store, artifact_store=self.artifacts)

    def tearDown(self):
        self.temp.cleanup()

    def create_project(self):
        return self.service.create_project({
            "title": "The Missing Part",
            "topic": "Why a small spare part can stop a production line",
            "channel_profile": {
                "youtube": {"format": "shorts", "aspect_ratio": "9:16"},
                "tiktok": {"format": "vertical", "aspect_ratio": "9:16"},
            },
            "language": "English",
        }, actor="owner")

    def test_project_create_read_and_bounded_list(self):
        project = self.create_project()
        self.assertEqual(project["status"], "idea")
        self.assertEqual(project["title"], "The Missing Part")
        self.assertEqual(self.service.get_project(project["project_id"]), project)
        self.assertEqual([p["project_id"] for p in self.service.list_projects(limit=5)],
                         [project["project_id"]])

    def test_versions_are_immutable_numbered_and_project_scoped(self):
        project = self.create_project()
        first = self.service.save_version(
            project["project_id"], "brief", {"topic": "stockout"},
            parent_version_id=None, actor="owner",
        )
        second = self.service.save_version(
            project["project_id"], "treatment", {"hook": "A $2 part stops a $20k line"},
            parent_version_id=first["version_id"], actor="owner",
        )
        self.assertEqual((first["version_no"], second["version_no"]), (1, 2))
        self.assertEqual(second["parent_version_id"], first["version_id"])
        versions = self.service.list_versions(project["project_id"])
        self.assertEqual([v["version_id"] for v in versions],
                         [first["version_id"], second["version_id"]])
        self.assertEqual(first["content"], {"topic": "stockout"})
        with self.assertRaises(CreatorStudioNotFound):
            self.service.save_version("missing-project", "brief", {"topic": "x"},
                                      parent_version_id=None, actor="owner")

    def test_project_lifecycle_uses_allowed_edges_and_compare_and_set(self):
        project = self.create_project()
        updated = self.service.transition_project(
            project["project_id"], "idea", "researching",
            actor="owner", evidence={"reason": "source collection started"},
        )
        self.assertEqual(updated["status"], "researching")
        with self.assertRaises(CreatorStudioConflict):
            self.service.transition_project(
                project["project_id"], "idea", "researching",
                actor="owner", evidence={"reason": "stale update"},
            )
        with self.assertRaises(CreatorStudioError):
            self.service.transition_project(
                project["project_id"], "researching", "published",
                actor="owner", evidence={"reason": "must not skip QA and approval"},
            )

    def test_asset_checksum_is_verified_before_storage_or_registration(self):
        project = self.create_project()
        version = self.service.save_version(
            project["project_id"], "storyboard", {"frames": []},
            parent_version_id=None, actor="owner",
        )
        content = b"synthetic storyboard bytes"
        digest = hashlib.sha256(content).hexdigest()
        asset = {
            "project_id": project["project_id"],
            "version_id": version["version_id"],
            "kind": "storyboard_image",
            "storage_key": f"projects/{project['project_id']}/storyboard.png",
            "sha256": digest,
            "byte_size": len(content),
            "mime_type": "image/png",
            "provenance": {"origin": "synthetic_test"},
            "license": {"status": "original"},
            "qa_status": "pending",
        }
        with self.assertRaises(CreatorStudioError):
            self.service.register_asset({**asset, "sha256": "0" * 64}, content_bytes=content)
        self.assertEqual(self.artifacts.objects, {})
        stored = self.service.register_asset(asset, content_bytes=content)
        self.assertEqual(stored["sha256"], digest)
        self.assertEqual(self.artifacts.objects[asset["storage_key"]], content)

    def test_story_film_requires_longform_project_and_allows_hour_wall_limit(self):
        project = self.service.create_project({
            "title": "The Moonbound Vow",
            "topic": "An original paranormal romance fantasy",
            "language": "English",
            "channel_profile": {"youtube": {"format": "longform", "aspect_ratio": "16:9"}},
        }, actor="owner")
        version = self.service.save_version(project["project_id"], "treatment",
            {"script": "A moonlit promise."}, parent_version_id=None, actor="owner")
        request = {
            "project_id": project["project_id"], "version_id": version["version_id"],
            "engine_commit": "5c05490cc55dfb54f8f4c333f0f0e79cb6500564",
            "style_id": "illustrated-story", "idempotency_key": "story-film-render-001",
            "resource_limits": {"cpu_seconds": 600, "memory_mb": 4096, "wall_time_seconds": 3600},
            "request": {"profile": "youtube_longform", "render_mode": "story_film"},
        }
        job = self.service.create_render_job(request)
        self.assertEqual(job["resource_limits"]["wall_time_seconds"], 3600)
        with self.assertRaises(CreatorStudioError):
            self.service.create_render_job({**request, "idempotency_key": "wrong-profile-001",
                "request": {"profile": "youtube_shorts", "render_mode": "story_film"}})

    def test_render_job_idempotency_and_missing_renderer_fail_closed(self):
        project = self.create_project()
        version = self.service.save_version(
            project["project_id"], "source_bundle", {"entrypoint": "index.html"},
            parent_version_id=None, actor="owner",
        )
        request = {
            "project_id": project["project_id"],
            "version_id": version["version_id"],
            "engine_commit": "5c05490cc55dfb54f8f4c333f0f0e79cb6500564",
            "style_id": "paper-cut",
            "idempotency_key": "render-once-001",
            "resource_limits": {"cpu_seconds": 60, "memory_mb": 512, "wall_time_seconds": 90},
            "request": {"target": "test-only"},
        }
        first = self.service.create_render_job(request)
        replay = self.service.create_render_job(request)
        self.assertEqual(first["job_id"], replay["job_id"])
        self.assertEqual(first["status"], "blocked")
        self.assertEqual(first["result_manifest"]["code"], "renderer_unavailable")
        changed = {**request, "style_id": "woodcut"}
        with self.assertRaises(CreatorStudioConflict):
            self.service.create_render_job(changed)
        self.assertEqual(self.service.get_render_job(first["job_id"])["job_id"], first["job_id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

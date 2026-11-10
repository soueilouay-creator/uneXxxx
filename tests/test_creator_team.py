from __future__ import annotations

import unittest
from types import SimpleNamespace

from unexpected_runtime.creator_team import CreatorTeamError, CreatorTeamRunner, STAGES


class FakeLocalProvider:
    local = True


class FakeRouter:
    def resolve(self, route=None):
        if route != "local":
            raise ValueError("not local")
        return FakeLocalProvider()


class FakeStore:
    def __init__(self):
        self.events = []
    def log_event(self, event_type, task_id=None, agent_id=None, payload=None):
        self.events.append((event_type, task_id, agent_id, payload or {}))


class FakeStudio:
    def __init__(self):
        self.project = {
            "project_id": "project-123",
            "title": "An Original Story",
            "topic": "A mysterious signal",
            "language": "English",
            "channel_profile": {"youtube": {"format": "shorts", "aspect_ratio": "9:16"}},
        }
        self.versions = []
        self.counter = 0
    def get_project(self, project_id):
        if project_id != self.project["project_id"]:
            raise ValueError("missing")
        return self.project
    def list_versions(self, project_id):
        return list(self.versions)
    def save_version(self, project_id, kind, content, parent_version_id, actor):
        self.counter += 1
        item = {
            "version_id": f"version-{self.counter}",
            "version_no": self.counter,
            "kind": kind,
            "content": content,
            "parent_version_id": parent_version_id,
            "actor": actor,
        }
        self.versions.append(item)
        return item


class FakeCoordinator:
    def __init__(self, fail_at=None):
        self.provider = FakeRouter()
        self.creator_studio = FakeStudio()
        self.store = FakeStore()
        self.calls = []
        self.fail_at = fail_at
        self.local_media_pipeline = None
    def invoke(self, agent_id, objective, inputs, **kwargs):
        self.calls.append((agent_id, objective, inputs, kwargs))
        if self.fail_at == agent_id:
            return SimpleNamespace(status="failed", task_id="failed-task", output="")
        return SimpleNamespace(status="completed", task_id=f"task-{len(self.calls)}",
                               output=f"Completed by {agent_id}")



class FakeLocalMediaPipeline:
    def __init__(self, ready=True):
        self.ready = ready
        self.preflight_calls = 0
        self.produce_calls = []

    def preflight(self, *, probe_service=False):
        self.preflight_calls += 1
        return {"ready": self.ready, "external_ai_api": "disabled",
                "probe_service": probe_service}

    def produce(self, project_id, project, storyboard_output, voice_output):
        self.produce_calls.append((project_id, storyboard_output, voice_output))
        return {"status": "completed", "video_rendered": True, "qa_passed": True,
                "external_ai_api": "disabled", "publishing_performed": False,
                "render": {"path": "master.mp4", "qa": {"status": "passed"}}}


class CreatorTeamTests(unittest.TestCase):
    def test_creator_team_uses_existing_roles_and_local_provider_for_every_stage(self):
        coordinator = FakeCoordinator()
        result = CreatorTeamRunner(coordinator).run("project-123")
        self.assertEqual(result["status"], "production_package_ready")
        self.assertEqual(result["provider_route"], "local")
        self.assertFalse(result["video_rendered"])
        self.assertEqual([call[0] for call in coordinator.calls], [stage["agent_id"] for stage in STAGES])
        self.assertTrue(all(call[3]["provider_route"] == "local" for call in coordinator.calls))
        self.assertEqual(len(coordinator.creator_studio.versions), len(STAGES))

    def test_creator_team_resumes_saved_stages_without_invoking_them_again(self):
        coordinator = FakeCoordinator()
        runner = CreatorTeamRunner(coordinator)
        first = runner.run("project-123")
        self.assertEqual(len(coordinator.calls), len(STAGES))
        second = runner.run("project-123")
        self.assertEqual(len(coordinator.calls), len(STAGES))
        self.assertTrue(all(stage["status"] == "reused" for stage in second["stages"]))
        self.assertEqual(first["stage_count"], second["stage_count"])

    def test_creator_team_stops_and_records_a_blocked_stage(self):
        coordinator = FakeCoordinator(fail_at="media-producer")
        with self.assertRaises(CreatorTeamError):
            CreatorTeamRunner(coordinator).run("project-123")
        self.assertEqual(len(coordinator.creator_studio.versions), 2)
        event_types = [event[0] for event in coordinator.store.events]
        self.assertIn("creator_team_stage_blocked", event_types)

    def test_creator_team_rejects_mock_or_non_local_provider(self):
        coordinator = FakeCoordinator()
        coordinator.provider = object()
        with self.assertRaises(CreatorTeamError):
            CreatorTeamRunner(coordinator).run("project-123")

    def test_creator_team_defines_only_canonical_uneXpected_roles(self):
        self.assertEqual(
            [stage["agent_id"] for stage in STAGES],
            ["research-scout", "creative-director", "media-producer", "voice-agent", "marketing-seo", "code-reviewer"],
        )


    def test_creator_team_invokes_ready_local_media_pipeline_and_persists_qa(self):
        coordinator = FakeCoordinator()
        media = FakeLocalMediaPipeline(ready=True)
        coordinator.local_media_pipeline = media
        result = CreatorTeamRunner(coordinator).run("project-123")
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["video_rendered"])
        self.assertTrue(result["qa_passed"])
        self.assertFalse(result["publishing_performed"])
        self.assertEqual(media.preflight_calls, 1)
        self.assertEqual(len(media.produce_calls), 1)
        self.assertEqual(len(coordinator.creator_studio.versions), len(STAGES) + 1)
        saved = coordinator.creator_studio.versions[-1]
        self.assertEqual(saved["kind"], "qa_report")
        self.assertEqual(saved["content"]["media_result"]["render"]["qa"]["status"], "passed")

    def test_creator_team_does_not_render_when_local_media_preflight_is_blocked(self):
        coordinator = FakeCoordinator()
        media = FakeLocalMediaPipeline(ready=False)
        coordinator.local_media_pipeline = media
        result = CreatorTeamRunner(coordinator).run("project-123")
        self.assertEqual(result["status"], "production_package_ready")
        self.assertFalse(result["video_rendered"])
        self.assertFalse(result["qa_passed"])
        self.assertEqual(media.preflight_calls, 1)
        self.assertEqual(media.produce_calls, [])
        self.assertEqual(result["media_result"]["status"], "blocked")
        self.assertFalse(result["publishing_performed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

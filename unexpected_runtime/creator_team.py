from __future__ import annotations

from typing import Any


class CreatorTeamError(RuntimeError):
    """A local Creator Team stage was blocked or could not be resumed safely."""


STAGES = (
    {
        "stage_id": "local_research",
        "agent_id": "research-scout",
        "version_kind": "research",
        "objective": "Prepare a grounded research pack using only source material explicitly supplied in this project. This machine is offline. Do not browse, invent citations, or imply unsupported facts are verified. Return claims, supplied evidence, unknowns, and sources still needed.",
    },
    {
        "stage_id": "creative_direction",
        "agent_id": "creative-director",
        "version_kind": "brief",
        "objective": "Create the original creative brief: audience promise, concept, hook, emotional arc, tone, style direction, and ending. Preserve factual uncertainty from the local research pack. Do not imitate copyrighted scripts, characters, or creator branding.",
    },
    {
        "stage_id": "production_storyboard",
        "agent_id": "media-producer",
        "version_kind": "storyboard",
        "objective": "Turn the approved creative direction into a production package: narration script, timed scene list, original visual prompts, shot/motion directions, continuity guide, caption plan, and local model tasks. Clearly identify assets that still need local generation; do not claim they exist.",
    },
    {
        "stage_id": "voice_and_sound",
        "agent_id": "voice-agent",
        "version_kind": "narration",
        "objective": "Prepare the narration performance sheet: final spoken text, pronunciation notes, pacing, emotion, character voice notes, subtitle segmentation, and local sound/music brief. Do not claim audio has been synthesized.",
    },
    {
        "stage_id": "platform_package",
        "agent_id": "marketing-seo",
        "version_kind": "platform_package",
        "objective": "Prepare separate YouTube and TikTok titles, descriptions, captions, hashtags, thumbnail direction, and derivative notes. Do not upload, schedule, or claim publication.",
    },
    {
        "stage_id": "production_review",
        "agent_id": "code-reviewer",
        "version_kind": "qa_report",
        "objective": "Review the complete production package for internal consistency, originality, claim grounding, production feasibility, local-only compliance, missing assets, and QA acceptance criteria. Return PASS only for the planning package; do not claim that a video has rendered or passed encoded-media QA.",
    },
)


class CreatorTeamRunner:
    """Sequential, resumable Creator Studio workflow over existing uneXpected role IDs."""

    def __init__(self, coordinator):
        self.coordinator = coordinator

    def _require_local_provider(self):
        provider = getattr(self.coordinator, "provider", None)
        if not hasattr(provider, "resolve"):
            raise CreatorTeamError("Creator Team requires the local provider router.")
        try:
            selected = provider.resolve("local")
        except Exception:
            raise CreatorTeamError("Local model route is unavailable; no cloud or mock fallback is permitted.") from None
        if not bool(getattr(selected, "local", False)):
            raise CreatorTeamError("The configured local route is not marked as a loopback-only provider.")
        return selected

    @staticmethod
    def _stage_versions(versions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}
        for version in versions:
            content = version.get("content")
            marker = content.get("local_creator_team") if isinstance(content, dict) else None
            stage_id = marker.get("stage_id") if isinstance(marker, dict) else None
            if isinstance(stage_id, str):
                found[stage_id] = version
        return found

    @staticmethod
    def _previous_outputs(versions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        outputs = []
        for version in versions:
            content = version.get("content")
            marker = content.get("local_creator_team") if isinstance(content, dict) else None
            if not isinstance(marker, dict):
                continue
            outputs.append({
                "stage_id": marker.get("stage_id"),
                "role_id": marker.get("role_id"),
                "output": content.get("output", ""),
            })
        return outputs

    def run(self, project_id: str, *, actor: str = "local-creator-team", resume: bool = True) -> dict[str, Any]:
        if not isinstance(project_id, str) or not project_id.strip():
            raise CreatorTeamError("A Creator Studio project ID is required.")
        self._require_local_provider()
        studio = self.coordinator.creator_studio
        project = studio.get_project(project_id)
        versions = studio.list_versions(project_id)
        completed = self._stage_versions(versions) if resume else {}
        stage_results: list[dict[str, Any]] = []

        self.coordinator.store.log_event("creator_team_started", None, "orchestrator", {
            "project_id": project_id, "stage_count": len(STAGES), "provider_route": "local",
            "resume": bool(resume),
        })

        for stage in STAGES:
            stage_id = stage["stage_id"]
            existing = completed.get(stage_id)
            if existing:
                marker = existing["content"]["local_creator_team"]
                stage_results.append({
                    "stage_id": stage_id, "role_id": stage["agent_id"],
                    "version_id": existing.get("version_id"), "task_id": marker.get("task_id"),
                    "status": "reused",
                })
                continue

            self.coordinator.store.log_event("creator_team_stage_started", None, stage["agent_id"], {
                "project_id": project_id, "stage_id": stage_id, "provider_route": "local",
            })
            previous = self._previous_outputs(versions)
            inputs = {
                "project": {
                    "project_id": project_id,
                    "title": project.get("title"),
                    "topic": project.get("topic"),
                    "language": project.get("language"),
                    "channel_profile": project.get("channel_profile"),
                },
                "local_only_policy": {
                    "network": "disabled",
                    "provider_route": "local",
                    "cloud_fallback": False,
                    "publishing": "disabled",
                },
                "previous_stage_outputs": previous[-6:],
                "delivery_rule": "Return structured, original planning output. Never claim an image, voice track, soundtrack or video exists until a local model has actually produced and verified that file.",
            }
            idempotency_key = f"creator-team:{project_id}:{stage_id}"
            try:
                result = self.coordinator.invoke(
                    stage["agent_id"],
                    stage["objective"],
                    inputs,
                    deadline_seconds=180.0,
                    max_steps=4,
                    idempotency_key=idempotency_key,
                    provider_route="local",
                )
            except Exception as exc:
                self.coordinator.store.log_event("creator_team_stage_blocked", None, stage["agent_id"], {
                    "project_id": project_id, "stage_id": stage_id, "error_type": type(exc).__name__,
                })
                raise CreatorTeamError(f"Creator Team stage {stage_id} could not run ({type(exc).__name__}).") from None
            if getattr(result, "status", None) != "completed":
                self.coordinator.store.log_event("creator_team_stage_blocked", getattr(result, "task_id", None),
                    stage["agent_id"], {"project_id": project_id, "stage_id": stage_id,
                    "result_status": getattr(result, "status", "unknown")})
                raise CreatorTeamError(f"Creator Team stage {stage_id} is blocked; its task remains available for diagnosis.")
            output = getattr(result, "output", "")
            if not isinstance(output, str) or not output.strip():
                raise CreatorTeamError(f"Creator Team stage {stage_id} returned no usable output.")

            latest_versions = studio.list_versions(project_id)
            parent_version_id = latest_versions[-1]["version_id"] if latest_versions else None
            version = studio.save_version(
                project_id,
                stage["version_kind"],
                {
                    "local_creator_team": {
                        "stage_id": stage_id,
                        "role_id": stage["agent_id"],
                        "task_id": getattr(result, "task_id", None),
                        "provider_route": "local",
                        "status": "completed",
                    },
                    "output": output,
                },
                parent_version_id=parent_version_id,
                actor=actor,
            )
            versions = studio.list_versions(project_id)
            completed[stage_id] = version
            stage_results.append({
                "stage_id": stage_id, "role_id": stage["agent_id"],
                "version_id": version.get("version_id"), "task_id": getattr(result, "task_id", None),
                "status": "completed",
            })
            self.coordinator.store.log_event("creator_team_stage_completed", getattr(result, "task_id", None),
                stage["agent_id"], {"project_id": project_id, "stage_id": stage_id,
                "version_id": version.get("version_id"), "provider_route": "local"})

        self.coordinator.store.log_event("creator_team_completed", None, "orchestrator", {
            "project_id": project_id, "stage_count": len(stage_results),
            "provider_route": "local", "video_rendered": False, "publishing_performed": False,
        })
        return {
            "status": "production_package_ready",
            "project_id": project_id,
            "provider_route": "local",
            "stages": stage_results,
            "stage_count": len(stage_results),
            "video_rendered": False,
            "publishing_performed": False,
            "next_capability": "local_asset_generation_and_rendering",
        }


__all__ = ["CreatorTeamRunner", "CreatorTeamError", "STAGES"]

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import hashlib
import json
import re


class SkillRegistryError(RuntimeError):
    """A local workflow-skill manifest or pinned source failed validation."""


@dataclass(frozen=True)
class SkillResource:
    path: str
    sha256: str
    kind: str


@dataclass(frozen=True)
class SkillSpec:
    id: str
    version: str
    path: str
    sha256: str
    agent_ids: tuple[str, ...]
    trigger_terms: tuple[str, ...]
    source_ref: str
    status: str
    invocation_mode: str = "automatic"
    description: str = ""
    allowed_tools: tuple[str, ...] = ()
    resources: tuple[SkillResource, ...] = ()

    def public_dict(self) -> dict:
        return {
            "id": self.id,
            "version": self.version,
            "description": self.description,
            "agent_ids": list(self.agent_ids),
            "trigger_terms": list(self.trigger_terms),
            "invocation_mode": self.invocation_mode,
            "allowed_tools": list(self.allowed_tools),
            "resources": [
                {"path": item.path, "sha256": item.sha256, "kind": item.kind}
                for item in self.resources
            ],
            "source_ref": self.source_ref,
            "sha256": self.sha256,
            "status": self.status,
        }


class SkillRegistry:
    """Loads only reviewed, local, hash-pinned Skill bundles.

    Manifest v1 remains supported. Manifest v2 adds invocation modes, declared
    tool scope and hash-pinned reference/script/asset files. Only the main
    SKILL.md and reference text are added to model context. Scripts are never
    executed and assets are never passed to a model by this registry.
    """

    SUPPORTED_SCHEMAS = {1, 2}
    INVOCATION_MODES = {"automatic", "user_invocable", "always_apply"}
    RESOURCE_KINDS = {"reference", "script", "asset"}
    MAX_RESOURCES_PER_SKILL = 32
    MAX_RESOURCE_BYTES = 256 * 1024
    MAX_CONTEXT_BYTES = 64 * 1024
    MAX_REQUESTED_SKILLS = 4
    MAX_APPLIED_SKILLS = 8
    _TOOL_ID = re.compile(r"[a-z0-9][a-z0-9._:-]{0,127}")

    def __init__(self, package_root: Path, skills: list[SkillSpec]):
        self.package_root = package_root.resolve()
        self._skills = tuple(skills)
        self._by_id = {skill.id: skill for skill in skills}
        if len(self._by_id) != len(skills):
            raise SkillRegistryError("Duplicate skill IDs in skill manifest.")

    @classmethod
    def load(
        cls,
        manifest_path: str | Path | None = None,
        package_root: str | Path | None = None,
    ) -> "SkillRegistry":
        root = Path(package_root) if package_root is not None else Path(__file__).resolve().parent.parent
        root = root.resolve()
        manifest = Path(manifest_path) if manifest_path is not None else root / "skill_manifest.json"
        if not manifest.is_absolute():
            manifest = (root / manifest).resolve()
        try:
            manifest.resolve().relative_to(root)
        except ValueError as exc:
            raise SkillRegistryError("Skill manifest must reside inside the package root.") from exc
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SkillRegistryError(f"Cannot read skill manifest: {type(exc).__name__}.") from None

        schema_version = data.get("schema_version") if isinstance(data, dict) else None
        if schema_version not in cls.SUPPORTED_SCHEMAS or not isinstance(data.get("skills"), list):
            raise SkillRegistryError("Unsupported or malformed skill manifest schema.")

        skills: list[SkillSpec] = []
        for raw in data["skills"]:
            try:
                if not isinstance(raw, dict):
                    raise TypeError("skill record must be an object")
                agent_ids_raw = raw["agent_ids"]
                trigger_terms_raw = raw.get("trigger_terms", [])
                allowed_tools_raw = raw.get("allowed_tools", [])
                resources_raw = raw.get("resources", []) if schema_version == 2 else []
                if (not isinstance(agent_ids_raw, list) or not isinstance(trigger_terms_raw, list)
                        or not isinstance(allowed_tools_raw, list)
                        or any(not isinstance(item, str) for item in agent_ids_raw + trigger_terms_raw + allowed_tools_raw)):
                    raise TypeError("agent_ids, trigger_terms and allowed_tools must be string lists")
                if not isinstance(resources_raw, list) or len(resources_raw) > cls.MAX_RESOURCES_PER_SKILL:
                    raise ValueError("invalid resource list")
                resources = []
                for resource in resources_raw:
                    if not isinstance(resource, dict):
                        raise TypeError("resource record must be an object")
                    if any(not isinstance(resource.get(key), str) for key in ("path", "sha256", "kind")):
                        raise TypeError("resource path, sha256 and kind must be strings")
                    resources.append(SkillResource(
                        path=resource["path"],
                        sha256=resource["sha256"].lower(),
                        kind=resource["kind"],
                    ))
                string_fields = ("id", "version", "path", "sha256", "source_ref", "status")
                if any(not isinstance(raw.get(key), str) for key in string_fields):
                    raise TypeError("skill identity, path, hash and source fields must be strings")
                invocation_mode = raw.get("invocation_mode", "automatic")
                description = raw.get("description", "")
                if not isinstance(invocation_mode, str) or not isinstance(description, str):
                    raise TypeError("invocation_mode and description must be strings")
                skill = SkillSpec(
                    id=raw["id"],
                    version=raw["version"],
                    path=raw["path"],
                    sha256=raw["sha256"].lower(),
                    agent_ids=tuple(agent_ids_raw),
                    trigger_terms=tuple(term.lower() for term in trigger_terms_raw),
                    source_ref=raw["source_ref"],
                    status=raw["status"],
                    invocation_mode=invocation_mode,
                    description=description,
                    allowed_tools=tuple(allowed_tools_raw),
                    resources=tuple(resources),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise SkillRegistryError(f"Malformed skill record: {type(exc).__name__}.") from None

            if (
                not skill.id or not skill.version or not skill.agent_ids
                or len(set(skill.agent_ids)) != len(skill.agent_ids)
                or any(not agent.strip() for agent in skill.agent_ids)
                or not skill.source_ref or skill.status != "active"
                or not re.fullmatch(r"[0-9a-f]{64}", skill.sha256)
                or skill.invocation_mode not in cls.INVOCATION_MODES
                or (skill.invocation_mode == "automatic" and not skill.trigger_terms)
                or any(not term.strip() for term in skill.trigger_terms)
                or any(not cls._TOOL_ID.fullmatch(tool) for tool in skill.allowed_tools)
                or len(set(skill.allowed_tools)) != len(skill.allowed_tools)
            ):
                raise SkillRegistryError(f"Invalid or inactive skill record: {skill.id!r}.")

            main_path = cls._safe_path(root, skill.path)
            cls._verify_path(root, skill.path, skill.sha256, skill.id)
            seen_paths = {main_path}
            for resource in skill.resources:
                if (
                    resource.kind not in cls.RESOURCE_KINDS
                    or not re.fullmatch(r"[0-9a-f]{64}", resource.sha256)
                ):
                    raise SkillRegistryError(f"Invalid resource metadata in skill: {skill.id}.")
                resource_path = cls._safe_path(root, resource.path)
                if resource_path in seen_paths:
                    raise SkillRegistryError(f"Duplicate resource path in skill: {skill.id}.")
                seen_paths.add(resource_path)
                cls._verify_path(root, resource.path, resource.sha256, skill.id)
            skills.append(skill)
        return cls(root, skills)

    @staticmethod
    def _safe_path(root: Path, relative: str) -> Path:
        path = (root / relative).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError as exc:
            raise SkillRegistryError(f"Skill path escapes package root: {relative!r}.") from exc
        return path

    @classmethod
    def _read_verified_bytes(cls, root: Path, relative: str, expected_sha256: str, skill_id: str) -> bytes:
        path = cls._safe_path(root, relative)
        if not path.is_file():
            raise SkillRegistryError(f"Skill bundle file is missing: {relative!r}.")
        try:
            with path.open("rb") as source:
                data = source.read(cls.MAX_RESOURCE_BYTES + 1)
            if len(data) > cls.MAX_RESOURCE_BYTES:
                raise SkillRegistryError(f"Skill bundle file exceeds the size limit: {relative!r}.")
        except OSError as exc:
            raise SkillRegistryError(f"Cannot read skill bundle file: {type(exc).__name__}.") from None
        if hashlib.sha256(data).hexdigest() != expected_sha256:
            raise SkillRegistryError(f"Skill bundle hash mismatch: {skill_id} ({relative}).")
        return data

    @classmethod
    def _verify_path(cls, root: Path, relative: str, expected_sha256: str, skill_id: str) -> None:
        cls._read_verified_bytes(root, relative, expected_sha256, skill_id)

    def get(self, skill_id: str) -> SkillSpec:
        skill = self._by_id.get(skill_id)
        if skill is None:
            raise SkillRegistryError(f"Unknown skill: {skill_id}.")
        return skill

    def validate_requested(self, agent_id: str, requested_skill_ids: Iterable[str] = ()) -> tuple[str, ...]:
        if requested_skill_ids is None:
            requested = ()
        elif isinstance(requested_skill_ids, (str, bytes)):
            raise SkillRegistryError("requested_skill_ids must be a sequence of skill ID strings.")
        else:
            try:
                requested = tuple(requested_skill_ids)
            except TypeError:
                raise SkillRegistryError("requested_skill_ids must be a sequence of skill ID strings.") from None
        if any(not isinstance(skill_id, str) or not skill_id.strip() for skill_id in requested):
            raise SkillRegistryError("Skill IDs must be non-empty strings.")
        if len(requested) > self.MAX_REQUESTED_SKILLS:
            raise SkillRegistryError(f"At most {self.MAX_REQUESTED_SKILLS} user-invoked skills may be selected.")
        if len(set(requested)) != len(requested):
            raise SkillRegistryError("Duplicate skill IDs are not allowed.")
        for skill_id in requested:
            skill = self._by_id.get(skill_id)
            if skill is None or skill.status != "active":
                raise SkillRegistryError(f"Unknown or inactive skill: {skill_id}.")
            if agent_id not in skill.agent_ids:
                raise SkillRegistryError(f"Skill is not mapped to role: {agent_id}.")
            if skill.invocation_mode != "user_invocable":
                raise SkillRegistryError(f"Skill is not user-invocable: {skill_id}.")
        return requested

    def resolve_all(
        self,
        agent_id: str,
        objective: str,
        requested_skill_ids: Iterable[str] = (),
    ) -> list[SkillSpec]:
        requested = self.validate_requested(agent_id, requested_skill_ids)
        normalized_objective = re.sub(r"[^a-z0-9]+", " ", objective.lower()).strip()
        objective_text = f" {normalized_objective} "
        selected: list[SkillSpec] = []
        for skill in self._skills:
            if skill.status != "active" or agent_id not in skill.agent_ids:
                continue
            if skill.invocation_mode == "always_apply":
                selected.append(skill)
                continue
            if skill.invocation_mode != "automatic":
                continue
            if any(
                f" {re.sub(r'[^a-z0-9]+', ' ', term.lower()).strip()} " in objective_text
                for term in skill.trigger_terms
            ):
                selected.append(skill)
        for skill_id in requested:
            skill = self._by_id[skill_id]
            if skill not in selected:
                selected.append(skill)
        if len(selected) > self.MAX_APPLIED_SKILLS:
            raise SkillRegistryError(f"Skill selection exceeds the {self.MAX_APPLIED_SKILLS}-skill context limit.")
        return selected

    def resolve(self, agent_id: str, objective: str) -> SkillSpec | None:
        """Backward-compatible helper returning the first applicable skill."""
        selected = self.resolve_all(agent_id, objective)
        return selected[0] if selected else None

    def read_context(self, skill: SkillSpec) -> str:
        registered = self._by_id.get(skill.id)
        if registered != skill:
            raise SkillRegistryError(f"Skill is not part of this registry: {skill.id}.")
        main = self._read_verified_bytes(self.package_root, skill.path, skill.sha256, skill.id)
        try:
            main_text = main.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SkillRegistryError(f"Cannot decode skill source: {type(exc).__name__}.") from None

        chunks = [main_text]
        context_bytes = len(main)
        for resource in skill.resources:
            data = self._read_verified_bytes(self.package_root, resource.path, resource.sha256, skill.id)
            if resource.kind == "reference":
                try:
                    reference = data.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise SkillRegistryError(f"Cannot decode Skill reference: {type(exc).__name__}.") from None
                context_bytes += len(data)
                if context_bytes > self.MAX_CONTEXT_BYTES:
                    raise SkillRegistryError(f"Skill context exceeds {self.MAX_CONTEXT_BYTES} bytes: {skill.id}.")
                chunks.append(f"\n\n---\nVerified reference: {resource.path}\n\n{reference}")
        if context_bytes > self.MAX_CONTEXT_BYTES:
            raise SkillRegistryError(f"Skill context exceeds {self.MAX_CONTEXT_BYTES} bytes: {skill.id}.")
        if skill.allowed_tools:
            chunks.append(
                "\n\nDeclared tool scope (metadata only): "
                + ", ".join(skill.allowed_tools)
                + ". This declaration does not install, authorize, or execute tools; "
                  "runtime capability and approval checks remain authoritative."
            )
        if any(item.kind in {"script", "asset"} for item in skill.resources):
            chunks.append(
                "\n\nBundle boundary: script and asset files were hash-verified as inert resources. "
                "Their contents were not added to model context and no script was executed."
            )
        return "\n".join(chunks)

    def list(self) -> list[SkillSpec]:
        return list(self._skills)

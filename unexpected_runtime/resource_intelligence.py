from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


VALID_ADOPTION_STATES = {
    "discovered", "triaged", "verified", "approved", "integrated", "rejected", "deprecated"
}
VALID_LICENSE_STATES = {"not_reviewed", "verified", "not_applicable"}
VALID_MAINTENANCE_STATES = {"not_assessed", "active", "stale", "archived", "unknown"}
VALID_SECURITY_STATES = {"not_reviewed", "passed", "accepted_risk", "failed"}


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string.")
    return value.strip()


def _require_url(value: Any, field: str) -> str:
    url = _require_text(value, field)
    parsed = urlsplit(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ValueError(f"{field} must be an absolute HTTP(S) URL.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{field} must not contain embedded credentials.")
    return url


class ResourceRegistry:
    """Read-only, provenance-aware registry of curated research references."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else (
            Path(__file__).resolve().parent / "data" / "resource_catalog.json"
        )
        try:
            self.document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Resource catalog could not be read ({type(exc).__name__}).") from None
        self.sources: list[dict[str, Any]] = []
        self.resources: list[dict[str, Any]] = []
        self._validate_document()

    def _validate_document(self) -> None:
        doc = self.document
        if not isinstance(doc, dict) or doc.get("schema_version") != 1:
            raise ValueError("Resource catalog schema_version must be 1.")
        _require_text(doc.get("catalog_id"), "catalog_id")
        _require_text(doc.get("updated_at"), "updated_at")
        _require_text(doc.get("policy"), "policy")

        sources = doc.get("sources")
        resources = doc.get("resources")
        if not isinstance(sources, list) or not sources:
            raise ValueError("Resource catalog must contain a non-empty sources list.")
        if not isinstance(resources, list):
            raise ValueError("Resource catalog resources must be a list.")

        source_ids: set[str] = set()
        source_urls: set[str] = set()
        source_by_id: dict[str, dict[str, Any]] = {}
        for source in sources:
            if not isinstance(source, dict):
                raise ValueError("Each source record must be an object.")
            source_id = _require_text(source.get("id"), "source.id")
            if source_id in source_ids:
                raise ValueError(f"duplicate source id: {source_id}")
            source_ids.add(source_id)
            canonical_url = _require_url(source.get("canonical_url"), "source.canonical_url")
            if canonical_url in source_urls:
                raise ValueError(f"duplicate source canonical URL: {canonical_url}")
            source_urls.add(canonical_url)
            _require_text(source.get("name"), f"source[{source_id}].name")
            _require_text(source.get("kind"), f"source[{source_id}].kind")
            license_data = source.get("license")
            if not isinstance(license_data, dict):
                raise ValueError(f"source[{source_id}].license must be an object.")
            license_status = license_data.get("status")
            if license_status not in VALID_LICENSE_STATES:
                raise ValueError(f"source[{source_id}] has unsupported license status.")
            if license_status == "verified":
                _require_text(license_data.get("identifier"), f"source[{source_id}].license.identifier")
                _require_url(license_data.get("evidence_url"), f"source[{source_id}].license.evidence_url")
            source_by_id[source_id] = source
        self.sources = [copy.deepcopy(item) for item in sources]

        resource_ids: set[str] = set()
        resource_urls: set[str] = set()
        for resource in resources:
            if not isinstance(resource, dict):
                raise ValueError("Each resource record must be an object.")
            resource_id = _require_text(resource.get("id"), "resource.id")
            if resource_id in resource_ids:
                raise ValueError(f"duplicate resource id: {resource_id}")
            resource_ids.add(resource_id)
            canonical_url = _require_url(resource.get("canonical_url"), f"resource[{resource_id}].canonical_url")
            if canonical_url in resource_urls:
                raise ValueError(f"duplicate canonical URL: {canonical_url}")
            resource_urls.add(canonical_url)
            for field in ("name", "kind", "category", "reviewed_at", "expected_benefit",
                          "integration_surface", "cost_model", "maintenance_status", "adoption_status"):
                _require_text(resource.get(field), f"resource[{resource_id}].{field}")

            source_id = _require_text(resource.get("source_id"), f"resource[{resource_id}].source_id")
            source = source_by_id.get(source_id)
            if source is None:
                raise ValueError(f"resource[{resource_id}] references unknown source: {source_id}")
            source_list_url = _require_url(resource.get("source_list_url"), f"resource[{resource_id}].source_list_url")
            if source_list_url != source["canonical_url"]:
                raise ValueError(f"resource[{resource_id}].source_list_url does not match its source record.")

            adoption = resource["adoption_status"]
            if adoption not in VALID_ADOPTION_STATES:
                raise ValueError(f"resource[{resource_id}] has unsupported adoption status: {adoption}")
            license_data = resource.get("license")
            if not isinstance(license_data, dict) or license_data.get("status") not in VALID_LICENSE_STATES:
                raise ValueError(f"resource[{resource_id}].license must have an explicit valid status.")
            maintenance = resource.get("maintenance_status")
            if maintenance not in VALID_MAINTENANCE_STATES:
                raise ValueError(f"resource[{resource_id}] has unsupported maintenance status.")
            security = resource.get("security_review")
            if not isinstance(security, dict) or security.get("status") not in VALID_SECURITY_STATES:
                raise ValueError(f"resource[{resource_id}].security_review must have an explicit valid status.")

            for field in ("dependencies", "evidence_urls", "benchmark_ids", "integration_test_refs"):
                if not isinstance(resource.get(field), list) or any(not isinstance(value, str) for value in resource[field]):
                    raise ValueError(f"resource[{resource_id}].{field} must be a list of strings.")
            if adoption == "integrated" and not resource.get("approval_ref"):
                raise ValueError(f"resource[{resource_id}] integrated status requires a prior approved state and approval_ref.")
            if adoption in {"verified", "approved", "integrated"}:
                if license_data.get("status") != "verified":
                    raise ValueError(f"resource[{resource_id}] requires resource-specific license evidence before verified status.")
                _require_text(license_data.get("identifier"), f"resource[{resource_id}].license.identifier")
                _require_url(license_data.get("evidence_url"), f"resource[{resource_id}].license.evidence_url")
                if maintenance not in {"active", "stale", "archived"}:
                    raise ValueError(f"resource[{resource_id}] requires assessed maintenance before verified status.")
                _require_url(resource.get("maintenance_evidence_url"), f"resource[{resource_id}].maintenance_evidence_url")
                if security.get("status") not in {"passed", "accepted_risk"}:
                    raise ValueError(f"resource[{resource_id}] requires a completed security review before verified status.")
                _require_url(security.get("evidence_url"), f"resource[{resource_id}].security_review.evidence_url")
                _require_text(security.get("reviewed_at"), f"resource[{resource_id}].security_review.reviewed_at")
                if not resource["evidence_urls"]:
                    raise ValueError(f"resource[{resource_id}] requires evidence_urls before verified status.")
            if adoption in {"approved", "integrated"}:
                _require_text(resource.get("approval_ref"), f"resource[{resource_id}].approval_ref")
            if adoption == "integrated" and not resource["integration_test_refs"]:
                raise ValueError(f"resource[{resource_id}] requires integration test evidence before integrated status.")

        self.resources = [copy.deepcopy(item) for item in resources]

    def validate(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for item in self.resources:
            status = item["adoption_status"]
            counts[status] = counts.get(status, 0) + 1
        return {
            "valid": True,
            "catalog_id": self.document["catalog_id"],
            "updated_at": self.document["updated_at"],
            "source_count": len(self.sources),
            "resource_count": len(self.resources),
            "adoption_counts": counts,
            "policy": "discovery-only; no installation or authorization implied",
        }

    def list_resources(self, category: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        items = self.resources
        if category is not None:
            items = [item for item in items if item["category"] == category]
        if status is not None:
            items = [item for item in items if item["adoption_status"] == status]
        return copy.deepcopy(sorted(items, key=lambda item: (item["category"], item["id"])))

    def summary(self) -> dict[str, Any]:
        return self.validate()

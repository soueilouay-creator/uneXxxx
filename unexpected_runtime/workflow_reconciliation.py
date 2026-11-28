from __future__ import annotations

import hashlib
import re
from typing import Any


REASON_CODES = frozenset({
    "uncertain_external_effect",
    "evidence_conflict",
    "operator_hold",
})

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_OPERATOR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")
_EVIDENCE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def attempt_token_sha256(value: Any) -> str:
    """Return a non-secret fingerprint for matching a persisted stage attempt."""
    if not isinstance(value, str) or not value:
        raise ValueError("attempt token must be a non-empty string.")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def validate_reconciliation_block_request(
    *,
    reconciliation_id: str,
    workflow_id: str,
    stage_key: str,
    expected_checkpoint_revision: int,
    expected_stage_index: int,
    expected_stage_request_hash: str,
    expected_attempt_token_sha256: str,
    operator_id: str,
    reason_code: str,
    evidence_ref: str,
    evidence_sha256: str,
) -> dict[str, Any]:
    """Validate an operator-attributed, non-replay manual-review block request.

    Evidence content is never accepted here. evidence_ref must be an opaque,
    non-secret ASCII reference; evidence_sha256 binds the separately retained
    evidence without copying it into the operational database.
    """
    for field, value in (
        ("reconciliation_id", reconciliation_id),
        ("workflow_id", workflow_id),
        ("stage_key", stage_key),
    ):
        if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
            raise ValueError(f"{field} must be a bounded identifier.")

    if (isinstance(expected_checkpoint_revision, bool)
            or not isinstance(expected_checkpoint_revision, int)
            or expected_checkpoint_revision < 0):
        raise ValueError("expected_checkpoint_revision must be a non-negative integer.")
    if (isinstance(expected_stage_index, bool)
            or not isinstance(expected_stage_index, int)
            or expected_stage_index < 1):
        raise ValueError("expected_stage_index must be a positive integer.")

    for field, value in (
        ("expected_stage_request_hash", expected_stage_request_hash),
        ("expected_attempt_token_sha256", expected_attempt_token_sha256),
        ("evidence_sha256", evidence_sha256),
    ):
        if not isinstance(value, str) or not _SHA256.fullmatch(value):
            raise ValueError(f"{field} must be a lowercase SHA-256 digest.")

    if not isinstance(operator_id, str) or not _OPERATOR.fullmatch(operator_id):
        raise ValueError("operator_id must be a bounded non-secret identifier.")
    if reason_code not in REASON_CODES:
        raise ValueError("reason_code is not an allowed manual-review reason.")
    if not isinstance(evidence_ref, str) or not _EVIDENCE_REF.fullmatch(evidence_ref):
        raise ValueError("evidence_ref must be an opaque reference without query or fragment data.")

    return {
        "reconciliation_id": reconciliation_id,
        "workflow_id": workflow_id,
        "stage_key": stage_key,
        "checkpoint_revision_before": expected_checkpoint_revision,
        "stage_index": expected_stage_index,
        "stage_request_hash": expected_stage_request_hash,
        "attempt_token_sha256": expected_attempt_token_sha256,
        "stage_status_before": "started",
        "stage_status_after": "interrupted",
        "operator_id": operator_id,
        "reason_code": reason_code,
        "evidence_ref": evidence_ref,
        "evidence_sha256": evidence_sha256,
        "disposition": "blocked_for_manual_review",
    }


def reconciliation_event_matches(existing: dict[str, Any], requested: dict[str, Any]) -> bool:
    """Idempotency requires the same immutable identity and evidence binding."""
    return all(existing.get(key) == value for key, value in requested.items())

from __future__ import annotations

import base64
import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from unexpected_runtime.approvals import GitHubPullRequestApprovalVerifier, canonical_action_digest
from unexpected_runtime.models import ApprovalContext, ApprovalExecutionBinding


REPOSITORY = "owner/repo"
REVIEWER = "independent-admin"
HEAD_SHA = "a" * 40
PR_NUMBER = 42


def iso(minutes_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat().replace("+00:00", "Z")


class ApprovalGithubFixture:
    def __init__(self, binding: ApprovalExecutionBinding | None):
        action_details = {
            "action": "agent.invoke",
            "required_permissions": ["repo_write"],
            "target": "fixture:release-1",
        }
        if binding is not None:
            action_details["execution_binding"] = binding.to_dict()
        digest = canonical_action_digest(action_details)
        request = {
            "schema": "uneXpected.approval-request/v1",
            "proposal_id": "proposal-001",
            "repository": REPOSITORY,
            "permission": "repo_write",
            "action_details": action_details,
            "action_digest": digest,
            "requested_by": "owner",
            "created_at": iso(5),
        }
        encoded = base64.b64encode(json.dumps(request).encode()).decode()
        prefix = f"/repos/{REPOSITORY}"
        self.responses = {
            f"{prefix}/pulls/{PR_NUMBER}": {
                "state": "open",
                "draft": False,
                "created_at": iso(6),
                "user": {"login": "github-actions[bot]"},
                "head": {"sha": HEAD_SHA, "ref": "approval-requests/proposal-001",
                         "repo": {"full_name": REPOSITORY}},
                "base": {"ref": "main", "repo": {"full_name": REPOSITORY}},
            },
            f"{prefix}/contents/approvals/requests/proposal-001.json?ref={HEAD_SHA}": {
                "encoding": "base64", "content": encoded,
            },
            f"{prefix}/pulls/{PR_NUMBER}/reviews?per_page=100&page=1": [{
                "state": "APPROVED", "commit_id": HEAD_SHA, "submitted_at": iso(1),
                "user": {"login": REVIEWER},
            }],
            f"{prefix}/collaborators/{REVIEWER}/permission": {"permission": "admin"},
        }

    def get_json(self, path: str):
        return self.responses[path]


def approval(digest: str) -> ApprovalContext:
    return ApprovalContext(
        approval_id=f"github-pr:{PR_NUMBER}:proposal-001",
        approver=REVIEWER,
        approved_permissions=frozenset({"repo_write"}),
        rationale="Approved exact immutable action request",
        action_digest=digest,
    )


class BrokenBoundLedger:
    def consume_once_bound(self, *args, **kwargs):
        raise RuntimeError("simulated durable ledger outage")

    def get_consumed_binding(self, approval_id: str):
        raise RuntimeError("simulated durable ledger outage")


class ApprovalExecutionBindingSQLiteTests(unittest.TestCase):
    def make_verifier(self, directory, fixture, ledger=None):
        return GitHubPullRequestApprovalVerifier(
            repository=REPOSITORY,
            token="test-read-only-token",
            trusted_reviewers=(REVIEWER,),
            base_branch="main",
            max_age_seconds=3600,
            ledger_path=Path(directory) / "approval-ledger.sqlite3",
            transport=fixture.get_json,
            ledger=ledger,
        )

    def test_bound_approval_is_consumed_and_read_back_with_exact_identity(self):
        binding = ApprovalExecutionBinding("exec-A", "task-A", "workflow-A", "0001:execute")
        fixture = ApprovalGithubFixture(binding)
        digest = canonical_action_digest({
            "action": "agent.invoke",
            "required_permissions": ["repo_write"],
            "target": "fixture:release-1",
            "execution_binding": binding.to_dict(),
        })
        with tempfile.TemporaryDirectory() as directory:
            verifier = self.make_verifier(directory, fixture)
            self.assertTrue(verifier.verify_bound(approval(digest), "repo_write", digest, binding))
            row = verifier.get_consumed_binding(f"github-pr:{PR_NUMBER}:proposal-001")
            self.assertEqual(
                {key: value for key, value in row.items() if key != "consumed_at"},
                {
                    "approval_id": f"github-pr:{PR_NUMBER}:proposal-001",
                    "action_digest": digest,
                    "permission": "repo_write",
                    **binding.to_dict(),
                },
            )
            self.assertIsInstance(row["consumed_at"], float)

    def test_one_approval_cannot_be_rebound_to_another_execution_or_task(self):
        binding = ApprovalExecutionBinding("exec-A", "task-A")
        fixture = ApprovalGithubFixture(binding)
        details = {
            "action": "agent.invoke", "required_permissions": ["repo_write"],
            "target": "fixture:release-1", "execution_binding": binding.to_dict(),
        }
        digest = canonical_action_digest(details)
        with tempfile.TemporaryDirectory() as directory:
            verifier = self.make_verifier(directory, fixture)
            self.assertTrue(verifier.verify_bound(approval(digest), "repo_write", digest, binding))
            for other in (
                ApprovalExecutionBinding("exec-B", "task-A"),
                ApprovalExecutionBinding("exec-A", "task-B"),
            ):
                self.assertFalse(verifier.verify_bound(approval(digest), "repo_write", digest, other))

    def test_binding_must_match_immutable_workflow_and_stage_identity(self):
        binding = ApprovalExecutionBinding("exec-A", "task-A", "workflow-A", "0001:execute")
        fixture = ApprovalGithubFixture(binding)
        details = {
            "action": "agent.invoke", "required_permissions": ["repo_write"],
            "target": "fixture:release-1", "execution_binding": binding.to_dict(),
        }
        digest = canonical_action_digest(details)
        with tempfile.TemporaryDirectory() as directory:
            verifier = self.make_verifier(directory, fixture)
            mismatches = (
                ApprovalExecutionBinding("exec-A", "task-A", "workflow-B", "0001:execute"),
                ApprovalExecutionBinding("exec-A", "task-A", "workflow-A", "0002:execute"),
            )
            for other in mismatches:
                self.assertFalse(verifier.verify_bound(approval(digest), "repo_write", digest, other))

    def test_changed_action_digest_is_denied(self):
        binding = ApprovalExecutionBinding("exec-A", "task-A")
        fixture = ApprovalGithubFixture(binding)
        details = {
            "action": "agent.invoke", "required_permissions": ["repo_write"],
            "target": "fixture:release-1", "execution_binding": binding.to_dict(),
        }
        digest = canonical_action_digest(details)
        with tempfile.TemporaryDirectory() as directory:
            verifier = self.make_verifier(directory, fixture)
            self.assertFalse(verifier.verify_bound(approval("b" * 64), "repo_write", "b" * 64, binding))

    def test_concurrent_bound_consumption_has_exactly_one_winner(self):
        binding = ApprovalExecutionBinding("exec-race", "task-race")
        fixture = ApprovalGithubFixture(binding)
        details = {
            "action": "agent.invoke", "required_permissions": ["repo_write"],
            "target": "fixture:release-1", "execution_binding": binding.to_dict(),
        }
        digest = canonical_action_digest(details)
        with tempfile.TemporaryDirectory() as directory:
            verifier = self.make_verifier(directory, fixture)
            with ThreadPoolExecutor(max_workers=12) as pool:
                results = list(pool.map(
                    lambda _: verifier.verify_bound(approval(digest), "repo_write", digest, binding),
                    range(24),
                ))
            self.assertEqual(sum(results), 1)

    def test_ledger_failure_denies_bound_approval(self):
        binding = ApprovalExecutionBinding("exec-A", "task-A")
        fixture = ApprovalGithubFixture(binding)
        details = {
            "action": "agent.invoke", "required_permissions": ["repo_write"],
            "target": "fixture:release-1", "execution_binding": binding.to_dict(),
        }
        digest = canonical_action_digest(details)
        with tempfile.TemporaryDirectory() as directory:
            verifier = self.make_verifier(directory, fixture, BrokenBoundLedger())
            self.assertFalse(verifier.verify_bound(approval(digest), "repo_write", digest, binding))

    def test_legacy_unbound_consumed_approval_is_retained_without_binding(self):
        fixture = ApprovalGithubFixture(None)
        details = {
            "action": "agent.invoke", "required_permissions": ["repo_write"],
            "target": "fixture:release-1",
        }
        digest = canonical_action_digest(details)
        approval_id = f"github-pr:{PR_NUMBER}:proposal-001"
        with tempfile.TemporaryDirectory() as directory:
            verifier = self.make_verifier(directory, fixture)
            self.assertTrue(verifier.verify(approval(digest), "repo_write", digest))
            self.assertIsNone(verifier.get_consumed_binding(approval_id))
            connection = sqlite3.connect(Path(directory) / "approval-ledger.sqlite3")
            try:
                row = connection.execute(
                    "SELECT action_digest FROM consumed_approvals WHERE approval_id=?", (approval_id,)
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(row, (digest,))


if __name__ == "__main__":
    unittest.main(verbosity=2)

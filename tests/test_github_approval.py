from __future__ import annotations

import base64
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from unexpected_runtime.approvals import GitHubPullRequestApprovalVerifier, canonical_action_digest
from unexpected_runtime.models import ApprovalContext
from unexpected_runtime.coordinator import Coordinator
from unexpected_runtime.providers import DeterministicMockProvider

REPOSITORY = "soueilouay-creator/uneXpected-"
REQUESTER = "soueilouay-creator"
REVIEWER = "independent-admin"
HEAD_SHA = "a" * 40
ACTION_DETAILS = {"action": "agent.invoke", "required_permissions": ["repo_write"], "target": "fixture:release-1"}
DIGEST = canonical_action_digest(ACTION_DETAILS)
ROOT = Path(__file__).resolve().parents[1]


def iso(delta: timedelta = timedelta(0)) -> str:
    return (datetime.now(timezone.utc) + delta).isoformat().replace("+00:00", "Z")


class FakeGitHub:
    def __init__(self, *, state="open", review_state="APPROVED", review_commit=HEAD_SHA,
                 reviewer=REVIEWER, requested_by=REQUESTER, permission="admin", body_digest=DIGEST,
                 base_ref="main", head_repo=REPOSITORY, response_override=None):
        request_document = {
            "schema": "uneXpected.approval-request/v1",
            "proposal_id": "proposal-001",
            "repository": REPOSITORY,
            "permission": "repo_write",
            "action_details": ACTION_DETAILS,
            "action_digest": body_digest,
            "requested_by": requested_by,
            "created_at": iso(timedelta(minutes=-5)),
        }
        encoded = base64.b64encode(json.dumps(request_document).encode()).decode()
        self.responses = {
            "/repos/soueilouay-creator/uneXpected-/pulls/42": {
                "state": state,
                "draft": False,
                "created_at": iso(timedelta(minutes=-6)),
                "user": {"login": "github-actions[bot]"},
                "head": {"sha": HEAD_SHA, "ref": "approval-requests/proposal-001", "repo": {"full_name": head_repo}},
                "base": {"ref": base_ref, "repo": {"full_name": REPOSITORY}},
            },
            f"/repos/soueilouay-creator/uneXpected-/contents/approvals/requests/proposal-001.json?ref={HEAD_SHA}": {
                "encoding": "base64", "content": encoded,
            },
            "/repos/soueilouay-creator/uneXpected-/pulls/42/reviews?per_page=100&page=1": [
                {"state": review_state, "commit_id": review_commit,
                 "submitted_at": iso(timedelta(minutes=-1)), "user": {"login": reviewer}}
            ],
            f"/repos/soueilouay-creator/uneXpected-/collaborators/{reviewer}/permission": {
                "permission": permission,
            },
        }
        if response_override:
            self.responses.update(response_override)
        self.calls = []

    def get_json(self, path):
        self.calls.append(path)
        if path not in self.responses:
            raise RuntimeError("unexpected path")
        return self.responses[path]


def context(*, approver=REVIEWER, permission="repo_write", digest=DIGEST):
    return ApprovalContext(
        approval_id="github-pr:42:proposal-001",
        approver=approver,
        approved_permissions=frozenset({permission}),
        rationale="Approved through protected GitHub review",
        action_digest=digest,
    )


class GitHubApprovalVerifierTests(unittest.TestCase):
    def make_verifier(self, directory, fake, *, trusted=(REVIEWER,)):
        return GitHubPullRequestApprovalVerifier(
            repository=REPOSITORY,
            token="test-read-only-token",
            trusted_reviewers=trusted,
            base_branch="main",
            max_age_seconds=3600,
            ledger_path=Path(directory) / "used-approvals.sqlite3",
            transport=fake.get_json,
        )

    def test_accepts_current_approval_from_trusted_admin_for_exact_request(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = FakeGitHub()
            verifier = self.make_verifier(directory, fake)
            self.assertTrue(verifier.verify(context(), "repo_write", DIGEST))
            self.assertEqual(len(fake.calls), 4)

    def test_denies_approval_when_requester_is_same_as_approver(self):
        with tempfile.TemporaryDirectory() as directory:
            self_approval = self.make_verifier(
                directory, FakeGitHub(reviewer=REQUESTER), trusted=(REQUESTER,)
            )
            self.assertFalse(self_approval.verify(context(approver=REQUESTER), "repo_write", DIGEST))

    def test_denies_request_created_by_an_identity_other_than_repository_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = FakeGitHub(requested_by="someone-else")
            verifier = self.make_verifier(directory, fake)
            self.assertFalse(verifier.verify(context(), "repo_write", DIGEST))

    def test_denies_reuse_after_successful_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            verifier = self.make_verifier(directory, FakeGitHub())
            self.assertTrue(verifier.verify(context(), "repo_write", DIGEST))
            self.assertFalse(verifier.verify(context(), "repo_write", DIGEST))

    def test_denies_untrusted_identity_even_when_pr_has_valid_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            verifier = self.make_verifier(directory, FakeGitHub(), trusted=("someone-else",))
            self.assertFalse(verifier.verify(context(), "repo_write", DIGEST))

    def test_denies_non_admin_reviewer(self):
        with tempfile.TemporaryDirectory() as directory:
            verifier = self.make_verifier(directory, FakeGitHub(permission="write"))
            self.assertFalse(verifier.verify(context(), "repo_write", DIGEST))

    def test_denies_review_on_previous_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            verifier = self.make_verifier(directory, FakeGitHub(review_commit="c" * 40))
            self.assertFalse(verifier.verify(context(), "repo_write", DIGEST))

    def test_denies_tampered_action_details_even_when_digest_field_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = FakeGitHub()
            key = f"/repos/soueilouay-creator/uneXpected-/contents/approvals/requests/proposal-001.json?ref={HEAD_SHA}"
            doc = json.loads(base64.b64decode(fake.responses[key]["content"]))
            doc["action_details"]["target"] = "fixture:other-target"
            fake.responses[key]["content"] = base64.b64encode(json.dumps(doc).encode()).decode()
            verifier = self.make_verifier(directory, fake)
            self.assertFalse(verifier.verify(context(), "repo_write", DIGEST))

    def test_denies_request_document_missing_permission_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = FakeGitHub()
            key = f"/repos/soueilouay-creator/uneXpected-/contents/approvals/requests/proposal-001.json?ref={HEAD_SHA}"
            doc = json.loads(base64.b64decode(fake.responses[key]["content"]))
            doc["action_details"]["required_permissions"] = []
            # Recompute digest so this specifically tests the permission-scope check.
            doc["action_digest"] = canonical_action_digest(doc["action_details"])
            fake.responses[key]["content"] = base64.b64encode(json.dumps(doc).encode()).decode()
            verifier = self.make_verifier(directory, fake)
            altered_context = context(digest=doc["action_digest"])
            self.assertFalse(verifier.verify(altered_context, "repo_write", doc["action_digest"]))

    def test_denies_changed_request_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            verifier = self.make_verifier(directory, FakeGitHub(body_digest="e" * 64))
            self.assertFalse(verifier.verify(context(), "repo_write", DIGEST))

    def test_denies_closed_or_wrong_base_pull_request(self):
        with tempfile.TemporaryDirectory() as directory:
            closed = self.make_verifier(directory, FakeGitHub(state="closed"))
            self.assertFalse(closed.verify(context(), "repo_write", DIGEST))
        with tempfile.TemporaryDirectory() as directory:
            wrong_base = self.make_verifier(directory, FakeGitHub(base_ref="release"))
            self.assertFalse(wrong_base.verify(context(), "repo_write", DIGEST))


    def test_denies_non_workflow_authored_pr_and_unexpected_head_branch(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = FakeGitHub()
            fake.responses["/repos/soueilouay-creator/uneXpected-/pulls/42"]["user"] = {"login": "maintainer"}
            verifier = self.make_verifier(directory, fake)
            self.assertFalse(verifier.verify(context(), "repo_write", DIGEST))
        with tempfile.TemporaryDirectory() as directory:
            fake = FakeGitHub()
            fake.responses["/repos/soueilouay-creator/uneXpected-/pulls/42"]["head"]["ref"] = "feature/unrelated"
            verifier = self.make_verifier(directory, fake)
            self.assertFalse(verifier.verify(context(), "repo_write", DIGEST))

    def test_denies_fork_head_and_self_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            fork = self.make_verifier(directory, FakeGitHub(head_repo="attacker/fork"))
            self.assertFalse(fork.verify(context(), "repo_write", DIGEST))
        with tempfile.TemporaryDirectory() as directory:
            self_approval = FakeGitHub()
            self_approval.responses["/repos/soueilouay-creator/uneXpected-/pulls/42"]["user"] = {"login": REVIEWER}
            verifier = self.make_verifier(directory, self_approval)
            self.assertFalse(verifier.verify(context(), "repo_write", DIGEST))

    def test_denies_stale_request_and_changes_requested_review(self):
        with tempfile.TemporaryDirectory() as directory:
            stale_doc = {
                "schema": "uneXpected.approval-request/v1", "proposal_id": "proposal-001",
                "repository": REPOSITORY, "permission": "repo_write", "action_digest": DIGEST,
                "requested_by": REQUESTER, "created_at": iso(timedelta(days=-3)),
            }
            key = f"/repos/soueilouay-creator/uneXpected-/contents/approvals/requests/proposal-001.json?ref={HEAD_SHA}"
            encoded = base64.b64encode(json.dumps(stale_doc).encode()).decode()
            stale = self.make_verifier(directory, FakeGitHub(response_override={key: {"encoding": "base64", "content": encoded}}))
            self.assertFalse(stale.verify(context(), "repo_write", DIGEST))
        with tempfile.TemporaryDirectory() as directory:
            changes = self.make_verifier(directory, FakeGitHub(review_state="CHANGES_REQUESTED"))
            self.assertFalse(changes.verify(context(), "repo_write", DIGEST))

    def test_denies_when_context_claim_does_not_match_verified_reviewer(self):
        with tempfile.TemporaryDirectory() as directory:
            verifier = self.make_verifier(directory, FakeGitHub())
            self.assertFalse(verifier.verify(context(approver="attacker"), "repo_write", DIGEST))

    def test_denies_api_errors_and_missing_or_malformed_config(self):
        with tempfile.TemporaryDirectory() as directory:
            class Broken:
                def get_json(self, path):
                    raise OSError("offline")
            verifier = self.make_verifier(directory, Broken())
            self.assertFalse(verifier.verify(context(), "repo_write", DIGEST))
            unconfigured = GitHubPullRequestApprovalVerifier(
                repository=REPOSITORY, token="", trusted_reviewers=(REVIEWER,), ledger_path=Path(directory) / "x.db")
            self.assertFalse(unconfigured.verify(context(), "repo_write", DIGEST))

    def test_latest_trusted_review_must_be_approval_on_current_head(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = FakeGitHub()
            reviews_path = "/repos/soueilouay-creator/uneXpected-/pulls/42/reviews?per_page=100&page=1"
            fake.responses[reviews_path].append({
                "state": "COMMENTED", "commit_id": HEAD_SHA,
                "submitted_at": iso(timedelta(seconds=-30)), "user": {"login": REVIEWER},
            })
            verifier = self.make_verifier(directory, fake)
            self.assertFalse(verifier.verify(context(), "repo_write", DIGEST))

    def test_later_comment_from_another_trusted_admin_invalidates_earlier_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = FakeGitHub()
            reviews_path = "/repos/soueilouay-creator/uneXpected-/pulls/42/reviews?per_page=100&page=1"
            fake.responses[reviews_path].append({
                "state": "COMMENTED", "commit_id": HEAD_SHA,
                "submitted_at": iso(timedelta(seconds=-30)), "user": {"login": "second-admin"},
            })
            verifier = self.make_verifier(directory, fake, trusted=(REVIEWER, "second-admin"))
            self.assertFalse(verifier.verify(context(), "repo_write", DIGEST))

    def test_request_workflow_is_manual_owner_gated_and_not_a_deploy_workflow(self):
        workflow = (ROOT / ".github" / "workflows" / "request-approval.yml").read_text()
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("github.actor == 'soueilouay-creator'", workflow)
        self.assertIn("pull-requests: write", workflow)
        self.assertIn("action_digest:", workflow)
        self.assertIn("vars.UNEXPECTED_APPROVAL_REVIEWER", workflow)
        self.assertIn("reviewer.lower() == os.environ['GH_ACTOR'].lower()", workflow)
        self.assertIn("'reviewers': [reviewer]", workflow)
        self.assertIn("/git/ref/heads/main", workflow)
        self.assertNotIn("workflow_run:", workflow)
        self.assertNotIn("render deploy", workflow.lower())

    def test_coordinator_loads_configured_github_verifier_from_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {
                "UNEXPECTED_GITHUB_APPROVAL_TOKEN": "read-only-token",
                "UNEXPECTED_GITHUB_APPROVAL_REPOSITORY": REPOSITORY,
                "UNEXPECTED_GITHUB_APPROVAL_ALLOWED_REPOSITORIES": REPOSITORY,
                "UNEXPECTED_GITHUB_APPROVAL_TRUSTED_REVIEWERS": REVIEWER,
                "UNEXPECTED_GITHUB_APPROVAL_BASE_BRANCH": "main",
                "UNEXPECTED_GITHUB_APPROVAL_MAX_AGE_SECONDS": "3600",
                "UNEXPECTED_APPROVAL_LEDGER_PATH": str(Path(directory) / "approvals.sqlite3"),
                "UNEXPECTED_STATE_DIR": directory,
            }
            with patch.dict(os.environ, env, clear=True):
                coordinator = Coordinator(manifest_path=ROOT / "agent_manifest.json",
                                          state_dir=directory, provider=DeterministicMockProvider())
                try:
                    self.assertIsInstance(coordinator.approval_verifier, GitHubPullRequestApprovalVerifier)
                    self.assertEqual(coordinator.status()["approval_verifier"], "github-pr-review")
                finally:
                    coordinator.close()

    def test_coordinator_fails_closed_when_repository_is_not_allowlisted(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {
                "UNEXPECTED_GITHUB_APPROVAL_TOKEN": "read-only-token",
                "UNEXPECTED_GITHUB_APPROVAL_REPOSITORY": REPOSITORY,
                "UNEXPECTED_GITHUB_APPROVAL_ALLOWED_REPOSITORIES": "another-owner/another-repo",
                "UNEXPECTED_GITHUB_APPROVAL_TRUSTED_REVIEWERS": REVIEWER,
                "UNEXPECTED_GITHUB_APPROVAL_BASE_BRANCH": "main",
                "UNEXPECTED_APPROVAL_LEDGER_PATH": str(Path(directory) / "approvals.sqlite3"),
                "UNEXPECTED_STATE_DIR": directory,
            }
            with patch.dict(os.environ, env, clear=True):
                coordinator = Coordinator(
                    manifest_path=ROOT / "agent_manifest.json", state_dir=directory,
                    provider=DeterministicMockProvider(),
                )
                try:
                    self.assertIsNone(coordinator.approval_verifier)
                    self.assertEqual(
                        coordinator.status()["approval_verifier"],
                        "not configured (privileged actions fail closed)",
                    )
                finally:
                    coordinator.close()

    def test_coordinator_defaults_approval_ledger_to_runtime_state_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {
                "UNEXPECTED_GITHUB_APPROVAL_TOKEN": "read-only-token",
                "UNEXPECTED_GITHUB_APPROVAL_REPOSITORY": REPOSITORY,
                "UNEXPECTED_GITHUB_APPROVAL_ALLOWED_REPOSITORIES": REPOSITORY,
                "UNEXPECTED_GITHUB_APPROVAL_TRUSTED_REVIEWERS": REVIEWER,
                "UNEXPECTED_GITHUB_APPROVAL_BASE_BRANCH": "main",
                "UNEXPECTED_STATE_DIR": directory,
            }
            with patch.dict(os.environ, env, clear=True):
                coordinator = Coordinator(
                    manifest_path=ROOT / "agent_manifest.json", state_dir=directory,
                    provider=DeterministicMockProvider(),
                )
                try:
                    self.assertIsInstance(coordinator.approval_verifier, GitHubPullRequestApprovalVerifier)
                    self.assertEqual(coordinator.approval_verifier.ledger_path,
                                     Path(directory) / "approval-ledger.sqlite3")
                finally:
                    coordinator.close()

    def test_coordinator_reports_privileged_actions_fail_closed_without_token(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {}, clear=True):
                coordinator = Coordinator(manifest_path=ROOT / "agent_manifest.json",
                                          state_dir=directory, provider=DeterministicMockProvider())
                try:
                    self.assertIsNone(coordinator.approval_verifier)
                    self.assertEqual(coordinator.status()["approval_verifier"],
                                     "not configured (privileged actions fail closed)")
                finally:
                    coordinator.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)

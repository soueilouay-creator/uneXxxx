import tempfile
import unittest
from pathlib import Path

from unexpected_runtime.approvals import canonical_action_digest
from unexpected_runtime.coordinator import Coordinator
from unexpected_runtime.models import ApprovalContext, PermissionDenied, TaskRequest
from unexpected_runtime.permissions import PermissionPolicy
from unexpected_runtime.providers import DeterministicMockProvider

ROOT = Path(__file__).resolve().parents[1]


class TestHostApprovalVerifier:
    def verify(self, approval, permission, action_digest):
        return (approval.approval_id == 'host-issued-approval-1'
                and approval.approver == 'verified-host-user'
                and approval.action_digest == action_digest
                and permission in approval.approved_permissions)


def make_approval(policy, permission, action_details, *, approval_id='host-issued-approval-1',
                  approver='verified-host-user', scopes=None):
    return ApprovalContext(approval_id, approver, frozenset(scopes or {permission}),
                           'Approved by test host trust adapter',
                           action_digest=policy.approval_digest(action_details))


class ApprovalBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.spec = type('Spec', (), {'id': 'orchestrator', 'allowed_permissions': ('read_context',)})()
        self.details = {'action': 'repo.publish', 'target': 'fixture:release-1',
                        'required_permissions': ['publish']}

    def test_digest_is_stable_and_changes_with_action_details(self):
        original = canonical_action_digest(self.details)
        self.assertEqual(original, canonical_action_digest(dict(self.details)))
        self.assertNotEqual(original, canonical_action_digest({**self.details, 'target': 'fixture:release-2'}))

    def test_caller_asserted_approval_is_denied_without_host_verifier(self):
        policy = PermissionPolicy()
        forged = ApprovalContext('invented', 'claimed-human', frozenset({'publish'}), 'approved',
                                 action_digest=policy.approval_digest(self.details))
        with self.assertRaises(PermissionDenied):
            policy.authorize(self.spec, 'publish', forged, action_details=self.details)

    def test_valid_trusted_approval_is_bound_to_exact_action(self):
        policy = PermissionPolicy(TestHostApprovalVerifier())
        approval = make_approval(policy, 'publish', self.details)
        policy.authorize(self.spec, 'publish', approval, action_details=self.details)
        changed = {**self.details, 'target': 'fixture:changed'}
        with self.assertRaises(PermissionDenied):
            policy.authorize(self.spec, 'publish', approval, action_details=changed)

    def test_approval_for_another_permission_is_denied(self):
        policy = PermissionPolicy(TestHostApprovalVerifier())
        approval = make_approval(policy, 'publish', self.details)
        with self.assertRaises(PermissionDenied):
            policy.authorize(self.spec, 'repo_write', approval, action_details=self.details)

    def test_invalid_host_identity_is_denied_even_with_matching_digest(self):
        policy = PermissionPolicy(TestHostApprovalVerifier())
        approval = make_approval(policy, 'publish', self.details, approval_id='invented')
        with self.assertRaises(PermissionDenied):
            policy.authorize(self.spec, 'publish', approval, action_details=self.details)

    def test_privileged_durable_queue_request_is_denied_without_revalidated_host_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            coordinator = Coordinator(manifest_path=ROOT / 'agent_manifest.json', state_dir=tmp,
                                      provider=DeterministicMockProvider(), approval_verifier=TestHostApprovalVerifier())
            try:
                request = TaskRequest.create('orchestrator', 'Queued publish request',
                                             required_permissions=('publish',))
                with self.assertRaises(PermissionDenied):
                    coordinator.enqueue(request)
            finally:
                coordinator.close()

    def test_coordinator_accepts_an_explicit_host_verifier(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = DeterministicMockProvider()
            coordinator = Coordinator(manifest_path=ROOT / 'agent_manifest.json', state_dir=tmp,
                                      provider=provider, approval_verifier=TestHostApprovalVerifier())
            try:
                objective = 'Simulation of an externally gated publish action'
                details = Coordinator.invoke_action_details('orchestrator', objective,
                                                              required_permissions=('publish',))
                approval = make_approval(coordinator.permissions, 'publish', details)
                result = coordinator.invoke('orchestrator', objective,
                                            required_permissions=('publish',), approval=approval)
                self.assertEqual(result.status, 'completed')
                self.assertEqual(provider.calls, 1)
            finally:
                coordinator.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)

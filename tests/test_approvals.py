import tempfile
import unittest
from pathlib import Path

from unexpected_runtime.approvals import canonical_action_digest
from unexpected_runtime.coordinator import Coordinator
from unexpected_runtime.models import ApprovalContext, ApprovalExecutionBinding, PermissionDenied, TaskRequest
from unexpected_runtime.permissions import PermissionPolicy
from unexpected_runtime.providers import DeterministicMockProvider

ROOT = Path(__file__).resolve().parents[1]


class TestHostApprovalVerifier:
    def __init__(self):
        self.bindings = {}

    def verify(self, approval, permission, action_digest):
        return (approval.approval_id == 'host-issued-approval-1'
                and approval.approver == 'verified-host-user'
                and approval.action_digest == action_digest
                and permission in approval.approved_permissions)

    def verify_bound(self, approval, permission, action_digest, binding):
        if not isinstance(binding, ApprovalExecutionBinding) or not self.verify(approval, permission, action_digest):
            return False
        self.bindings[approval.approval_id] = {
            "approval_id": approval.approval_id, "action_digest": action_digest,
            "permission": permission, **binding.to_dict(), "consumed_at": 1.0,
        }
        return True

    def get_consumed_binding(self, approval_id):
        return self.bindings.get(approval_id)


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

    def test_prepare_invoke_allocates_identity_without_queue_or_provider_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = DeterministicMockProvider()
            coordinator = Coordinator(manifest_path=ROOT / 'agent_manifest.json', state_dir=tmp,
                                      provider=provider, approval_verifier=TestHostApprovalVerifier())
            try:
                prepared = coordinator.prepare_invoke(
                    'orchestrator', 'Simulation of an externally gated publish action',
                    required_permissions=('publish',), inputs={'target': 'fixture:release-1'},
                )
                stored = coordinator.store.get_approval_execution_intent(prepared['execution_id'])
                self.assertEqual(stored['state'], 'awaiting_approval')
                self.assertEqual(stored['task_id'], prepared['task_id'])
                self.assertEqual(stored['action_digest'], prepared['action_digest'])
                self.assertIsNone(coordinator.store.get_task(prepared['task_id']))
                self.assertEqual(coordinator.store.list_tasks(), [])
                self.assertEqual(provider.calls, 0)
                self.assertEqual(prepared['action_details']['execution_binding']['task_id'], prepared['task_id'])
            finally:
                coordinator.close()

    def test_privileged_invoke_requires_exact_prepared_intent_and_one_use_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = DeterministicMockProvider()
            coordinator = Coordinator(manifest_path=ROOT / 'agent_manifest.json', state_dir=tmp,
                                      provider=provider, approval_verifier=TestHostApprovalVerifier())
            try:
                objective = 'Simulation of an externally gated publish action'
                prepared = coordinator.prepare_invoke(
                    'orchestrator', objective, required_permissions=('publish',),
                    inputs={'target': 'fixture:release-1'},
                )
                details = prepared['action_details']
                approval = make_approval(coordinator.permissions, 'publish', details)
                with self.assertRaises(PermissionDenied):
                    coordinator.invoke('orchestrator', objective, required_permissions=('publish',),
                                       inputs={'target': 'fixture:other'}, execution_id=prepared['execution_id'],
                                       approval=approval)
                forged = make_approval(coordinator.permissions, 'publish', details, approver='attacker')
                with self.assertRaises(PermissionDenied):
                    coordinator.invoke('orchestrator', objective, required_permissions=('publish',),
                                       inputs={'target': 'fixture:release-1'}, execution_id=prepared['execution_id'],
                                       approval=forged)
                result = coordinator.invoke(
                    'orchestrator', objective, required_permissions=('publish',),
                    inputs={'target': 'fixture:release-1'}, execution_id=prepared['execution_id'],
                    approval=approval,
                )
                self.assertEqual(result.status, 'completed')
                self.assertEqual(result.task_id, prepared['task_id'])
                task = coordinator.store.get_task(prepared['task_id'])
                self.assertEqual(task['status'], 'completed')
                payload = __import__('json').loads(task['payload_json'])
                self.assertEqual(payload['execution_id'], prepared['execution_id'])
                self.assertEqual(payload['approval_reference'], approval.approval_id)
                self.assertEqual(coordinator.store.get_approval_execution_intent(prepared['execution_id'])['state'], 'completed')
                self.assertEqual(provider.calls, 1)
                with self.assertRaises(PermissionDenied):
                    coordinator.invoke('orchestrator', objective, required_permissions=('publish',),
                                       inputs={'target': 'fixture:release-1'}, execution_id=prepared['execution_id'],
                                       approval=approval)
                self.assertEqual(provider.calls, 1)
            finally:
                coordinator.close()

    def test_privileged_invoke_without_execution_intent_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            coordinator = Coordinator(manifest_path=ROOT / 'agent_manifest.json', state_dir=tmp,
                                      provider=DeterministicMockProvider(), approval_verifier=TestHostApprovalVerifier())
            try:
                objective = 'Unprepared publish request'
                details = Coordinator.invoke_action_details('orchestrator', objective,
                                                              required_permissions=('publish',))
                approval = make_approval(coordinator.permissions, 'publish', details)
                with self.assertRaises(PermissionDenied):
                    coordinator.invoke('orchestrator', objective, required_permissions=('publish',), approval=approval)
            finally:
                coordinator.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)

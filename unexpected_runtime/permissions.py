from __future__ import annotations

from typing import Any

from .approvals import ApprovalVerifier, canonical_action_digest
from .models import ApprovalContext, PermissionDenied

PRIVILEGED = {
    'email_send', 'publish', 'repo_write', 'delete', 'deploy', 'trade', 'payment',
    'account_change', 'external_write', 'schedule_background', 'modify_policy',
    'modify_permissions', 'change_provider', 'install_external_tool', 'approve_knowledge',
}


class PermissionPolicy:
    """Enforces role scopes and host-verified, action-bound approvals."""

    def __init__(self, approval_verifier: ApprovalVerifier | None = None):
        self.approval_verifier = approval_verifier

    @staticmethod
    def approval_digest(action_details: dict[str, Any]) -> str:
        return canonical_action_digest(action_details)

    def authorize(self, spec, permission: str, approval: ApprovalContext | None = None,
                  *, action_details: dict[str, Any] | None = None) -> None:
        if permission in PRIVILEGED:
            if (not isinstance(approval, ApprovalContext) or not approval.approval_id or not approval.approver
                    or permission not in approval.approved_permissions or not approval.action_digest
                    or self.approval_verifier is None or action_details is None):
                raise PermissionDenied(f'Permission denied: {permission} requires a trusted, action-bound host approval.')
            try:
                expected_digest = self.approval_digest(action_details)
                valid_binding = approval.action_digest == expected_digest
                trusted = valid_binding and bool(self.approval_verifier.verify(approval, permission, expected_digest))
            except Exception:
                trusted = False
            if not trusted:
                raise PermissionDenied(f'Permission denied: {permission} approval is invalid, untrusted, or bound to another action.')
            return
        if permission not in spec.allowed_permissions:
            raise PermissionDenied(f'Permission denied: {spec.id} is not allowed scope {permission}.')

    @staticmethod
    def capability_status() -> dict[str, str]:
        return {'provider.chat': 'available (mock by default; real adapter unconfigured)',
                'local.state.sqlite': 'available on local host',
                'collaboration.handoff': 'available in local runtime',
                'web.read': 'not wired into this runtime',
                'browser.actions': 'not configured', 'email': 'not configured', 'payments': 'not configured',
                'trading': 'not configured', 'publishing': 'not configured', 'repository.write': 'not configured',
                'deployment': 'not configured', 'background.scheduler': 'not configured', 'notifications': 'not configured'}

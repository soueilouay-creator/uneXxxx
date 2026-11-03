from __future__ import annotations

from typing import Any
import hashlib
import json
import uuid

from .models import EvaluationReport, ImprovementRejected, PermissionDenied

PROTECTED_FIELDS = {'safety_policy', 'permissions', 'provider', 'model', 'external_tools', 'credentials', 'consequential_code'}


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


class ImprovementGovernor:
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.store = coordinator.store
        self.registry = coordinator.registry

    def record_outcome(self, agent_id: str, task_id: str | None, success: bool, feedback: str,
                       provenance: list[str] | None = None):
        self.registry.get(agent_id)
        return self.store.record_outcome(agent_id, task_id, success, feedback, provenance or [])

    def set_baseline(self, agent_id: str, report: EvaluationReport):
        spec = self.registry.get(agent_id)
        if not report.evaluation_valid:
            raise ImprovementRejected('Baseline evaluation is incomplete or invalid; required checks, counts, provider mode and rubric must be fixed.')
        if not report.critical_pass:
            raise ImprovementRejected('Baseline cannot be accepted with failed critical checks.')
        if report.noncritical_total < 1:
            raise ImprovementRejected('Baseline requires measured noncritical checks; skipped tests are not passes.')
        active = self.store.active_version(agent_id, spec.version, spec.instruction)
        evidence = {'active_version': active['version'],
                    'active_instruction_sha256': _digest(active['instruction']),
                    'report_sha256': _digest(report.to_dict()),
                    'benchmark_id': report.benchmark_id, 'scenario_ids': list(report.scenario_ids)}
        self.store.set_baseline(agent_id, report.benchmark_id, report.to_dict(),
                                active_version=evidence['active_version'],
                                instruction_sha256=evidence['active_instruction_sha256'],
                                report_sha256=evidence['report_sha256'])
        self.store.log_event('baseline_recorded', agent_id=agent_id, payload=evidence)

    def propose(self, agent_id: str, candidate_instruction: str, changes: str, benchmark_id: str,
                protected_fields: list[str] | None = None):
        spec = self.registry.get(agent_id)
        active = self.store.active_version(agent_id, spec.version, spec.instruction)
        if not candidate_instruction.strip() or not changes.strip():
            raise ValueError('Candidate instruction and change rationale are required.')
        baseline_data = self.store.get_baseline(agent_id, benchmark_id)
        if not baseline_data:
            raise ImprovementRejected('Retrieve/record a fixed baseline before proposing a change.')
        baseline_report = EvaluationReport.from_dict(baseline_data)
        if not baseline_report.evaluation_valid or not baseline_report.critical_pass:
            raise ImprovementRejected('Proposal baseline must contain a complete, valid evaluation context.')
        evaluation_context = baseline_report.evaluation_context()
        fields = set(protected_fields or [])
        text_for_scan = (changes + ' ' + candidate_instruction).lower()
        protected_signals = ('safety policy', 'permission', 'provider', 'model', 'external tool', 'credential',
                             'trade', 'payment', 'publish', 'deploy', 'delete', 'account change', 'consequential code')
        protected = bool(fields & PROTECTED_FIELDS) or any(signal in text_for_scan for signal in protected_signals)
        candidate_version = self._next_patch(active['version'])
        proposal = {'proposal_id': str(uuid.uuid4()), 'agent_id': agent_id, 'base_version': active['version'],
                    'candidate_version': candidate_version, 'candidate_instruction': candidate_instruction,
                    'changes': changes, 'protected_change': protected, 'protected_fields': sorted(fields),
                    'benchmark_id': benchmark_id, 'status': 'pending', 'evaluation': None,
                    'evaluation_context': evaluation_context}
        self.store.save_proposal(proposal)
        return proposal['proposal_id']

    def _protected_permissions(self, proposal: dict[str, Any]) -> tuple[str, ...]:
        fields = set(proposal.get('protected_fields', []))
        text = (proposal.get('changes', '') + ' ' + proposal.get('candidate_instruction', '')).lower()
        permissions: set[str] = set()
        if 'safety_policy' in fields or 'safety policy' in text:
            permissions.add('modify_policy')
        if 'permissions' in fields or 'permission' in text:
            permissions.add('modify_permissions')
        if (fields & {'provider', 'model', 'credentials'} or any(term in text for term in ('provider', 'credential'))
                or 'change model' in text or 'switch model' in text or 'provider model' in text):
            permissions.add('change_provider')
        if 'external_tools' in fields or 'external tool' in text:
            permissions.add('install_external_tool')
        if 'consequential_code' in fields or 'consequential code' in text:
            permissions.add('modify_policy')
        if not permissions:
            permissions.add('modify_policy')
        return tuple(sorted(permissions))

    def promotion_action_details(self, proposal_id: str, candidate: EvaluationReport) -> dict[str, Any]:
        proposal = self.store.get_proposal(proposal_id)
        if not proposal:
            raise ValueError('Unknown improvement proposal.')
        base = self.store.get_baseline(proposal['agent_id'], proposal['benchmark_id'])
        if not base:
            raise ImprovementRejected('Baseline is missing; no promotion.')
        baseline_evidence = self.store.get_baseline_evidence(proposal['agent_id'], proposal['benchmark_id'])
        if not baseline_evidence or not baseline_evidence.get('report_sha256') or not baseline_evidence.get('instruction_sha256'):
            raise ImprovementRejected('Baseline evidence is incomplete; no promotion.')
        required = self._protected_permissions(proposal) if proposal['protected_change'] else ()
        return {
            'action': 'improvement.promote',
            'proposal_id': proposal['proposal_id'],
            'agent_id': proposal['agent_id'],
            'base_version': proposal['base_version'],
            'candidate_version': proposal['candidate_version'],
            'candidate_instruction_sha256': _digest(proposal['candidate_instruction']),
            'change_summary_sha256': _digest(proposal['changes']),
            'benchmark_id': proposal['benchmark_id'],
            'baseline_active_version': baseline_evidence['active_version'],
            'baseline_instruction_sha256': baseline_evidence['instruction_sha256'],
            'baseline_report_sha256': baseline_evidence['report_sha256'],
            'evaluation_context': proposal.get('evaluation_context', {}),
            'scenario_ids': list(candidate.scenario_ids),
            'candidate_report_sha256': _digest(candidate.to_dict()),
            'required_permissions': list(required),
        }

    def evaluate_and_promote(self, proposal_id: str, candidate: EvaluationReport, approval=None):
        proposal = self.store.get_proposal(proposal_id)
        if not proposal:
            raise ValueError('Unknown improvement proposal.')
        if proposal['status'] != 'pending':
            raise ImprovementRejected('Only pending proposals can be evaluated; this proposal is already terminal.')
        base = self.store.get_baseline(proposal['agent_id'], proposal['benchmark_id'])
        if not base:
            raise ImprovementRejected('Baseline is missing; no promotion.')
        baseline = EvaluationReport.from_dict(base)
        baseline_evidence = self.store.get_baseline_evidence(proposal['agent_id'], proposal['benchmark_id']) or {}
        active = self.store.active_version(proposal['agent_id'], self.registry.get(proposal['agent_id']).version,
                                           self.registry.get(proposal['agent_id']).instruction)
        reasons: list[str] = []
        if (not baseline_evidence.get('active_version') or not baseline_evidence.get('instruction_sha256')
                or not baseline_evidence.get('report_sha256')):
            reasons.append('baseline evidence is incomplete')
        elif (proposal['base_version'] != baseline_evidence['active_version']
              or active['version'] != baseline_evidence['active_version']
              or _digest(active['instruction']) != baseline_evidence['instruction_sha256']):
            reasons.append('baseline is stale because the active version or instruction changed after baseline capture')
        if (not baseline.evaluation_valid or not candidate.evaluation_valid
                or baseline.evaluation_context() != proposal.get('evaluation_context', {})
                or candidate.evaluation_context() != proposal.get('evaluation_context', {})):
            reasons.append('baseline/candidate evaluation context is incomplete or differs (provider mode, scenario IDs, acceptance checks or rubric)')
        if candidate.benchmark_id != baseline.benchmark_id or candidate.scenario_ids != baseline.scenario_ids:
            reasons.append('baseline/candidate benchmark or scenario IDs differ')
        if not candidate.critical_pass:
            reasons.append('one or more critical checks failed')
        if candidate.noncritical_total < 1 or candidate.noncritical_rate < 0.90:
            reasons.append('noncritical pass rate is below 90% or unmeasured')
        if candidate.score <= baseline.score:
            reasons.append('candidate score did not improve over baseline')
        approval_verified = None
        approval_status = 'not_required' if not proposal['protected_change'] else 'not_evaluated'
        required_permissions = self._protected_permissions(proposal) if proposal['protected_change'] else ()
        if proposal['protected_change'] and len(required_permissions) > 1:
            reasons.append('the one-use approval verifier supports one privileged permission per action; split the change into separately approved actions')
        if proposal['protected_change'] and not reasons:
            approval_verified = False
            approval_status = 'rejected'
            details = self.promotion_action_details(proposal_id, candidate)
            try:
                spec = self.registry.get(proposal['agent_id'])
                for permission in required_permissions:
                    self.coordinator.permissions.authorize(spec, permission, approval, action_details=details)
                approval_verified = True
                approval_status = 'verified'
            except PermissionDenied:
                approval_verified = False
                reasons.append('protected change lacks a valid host-authenticated, action-bound approval')
        report = {'baseline': baseline.to_dict(), 'candidate': candidate.to_dict(),
                  'baseline_active_version': baseline_evidence.get('active_version'),
                  'baseline_instruction_sha256': baseline_evidence.get('instruction_sha256'),
                  'baseline_report_sha256': baseline_evidence.get('report_sha256'),
                  'candidate_instruction_sha256': _digest(proposal['candidate_instruction']),
                  'candidate_report_sha256': _digest(candidate.to_dict()),
                  'benchmark_id': candidate.benchmark_id, 'scenario_ids': list(candidate.scenario_ids),
                  'decision': 'rejected' if reasons else 'promoted', 'reasons': reasons,
                  'approval_verified': approval_verified, 'approval_status': approval_status,
                  'approval_permissions': list(required_permissions)}
        if reasons:
            self.store.update_proposal(proposal_id, 'rejected', report)
            return report
        self.store.promote_version(proposal['agent_id'], proposal['candidate_version'],
                                   proposal['candidate_instruction'], proposal['changes'])
        self.store.update_proposal(proposal_id, 'promoted', report)
        return report

    def rollback_action_details(self, agent_id: str, target_version: str, reason: str) -> dict[str, Any]:
        spec = self.registry.get(agent_id)
        active = self.store.active_version(agent_id, spec.version, spec.instruction)
        return {'action': 'improvement.rollback', 'agent_id': agent_id,
                'current_version': active['version'], 'target_version': target_version,
                'reason_sha256': _digest(reason), 'required_permissions': ['modify_policy']}

    def rollback(self, agent_id: str, target_version: str, reason: str, approval=None):
        spec = self.registry.get(agent_id)
        details = self.rollback_action_details(agent_id, target_version, reason)
        try:
            self.coordinator.permissions.authorize(spec, 'modify_policy', approval, action_details=details)
        except PermissionDenied as exc:
            raise ImprovementRejected('Rollback of active instructions requires a trusted, action-bound human approval.') from exc
        self.store.rollback_version(agent_id, target_version, reason)
        return self.store.active_version(agent_id, spec.version, spec.instruction)

    @staticmethod
    def _next_patch(version: str) -> str:
        parts = version.split('.')
        if len(parts) != 3 or not all(part.isdigit() for part in parts):
            raise ValueError('Agent version must be semantic x.y.z.')
        return f'{parts[0]}.{parts[1]}.{int(parts[2]) + 1}'

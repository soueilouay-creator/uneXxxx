from __future__ import annotations
from dataclasses import dataclass, field
from threading import Event
from typing import Any
import time, uuid, math

class RuntimeErrorBase(Exception): pass
class UnknownAgent(RuntimeErrorBase): pass
class PermissionDenied(RuntimeErrorBase): pass
class CycleLimitError(RuntimeErrorBase): pass
class BudgetExceeded(RuntimeErrorBase): pass
class DeadlineExceeded(RuntimeErrorBase): pass
class Cancelled(RuntimeErrorBase): pass
class ImprovementRejected(RuntimeErrorBase): pass

@dataclass(frozen=True)
class TaskRequest:
    task_id: str
    agent_id: str
    objective: str
    inputs: dict[str, Any] = field(default_factory=dict)
    required_permissions: tuple[str, ...] = ()
    deadline_seconds: float = 30.0
    max_steps: int = 6
    idempotency_key: str | None = None
    source_refs: tuple[str, ...] = ()
    provider_route: str | None = None
    requested_skill_ids: tuple[str, ...] = ()
    parent_task_id: str | None = None
    created_at: float = field(default_factory=time.time)

    @classmethod
    def create(cls, agent_id: str, objective: str, **kwargs: Any) -> 'TaskRequest':
        return cls(task_id=kwargs.pop('task_id', str(uuid.uuid4())), agent_id=agent_id, objective=objective, **kwargs)

@dataclass(frozen=True)
class AgentMessage:
    protocol_version: str
    message_id: str
    task_id: str
    sender_agent_id: str
    recipient_agent_id: str
    objective: str
    payload: dict[str, Any]
    provenance: tuple[str, ...] = ()
    requested_permissions: tuple[str, ...] = ('collaborate',)
    depth: int = 1

@dataclass
class TaskResult:
    task_id: str
    agent_id: str
    status: str
    output: str = ''
    provenance: tuple[str, ...] = ()
    attempts: int = 0
    error: str | None = None
    idempotent_replay: bool = False
    started_at: float | None = None
    finished_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {'task_id':self.task_id,'agent_id':self.agent_id,'status':self.status,'output':self.output,
                'provenance':list(self.provenance),'attempts':self.attempts,'error':self.error,
                'idempotent_replay':self.idempotent_replay,'started_at':self.started_at,'finished_at':self.finished_at}
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'TaskResult':
        return cls(task_id=d['task_id'],agent_id=d['agent_id'],status=d['status'],output=d.get('output',''),
                   provenance=tuple(d.get('provenance',[])),attempts=d.get('attempts',0),error=d.get('error'),
                   idempotent_replay=d.get('idempotent_replay',False),started_at=d.get('started_at'),finished_at=d.get('finished_at'))

@dataclass(frozen=True)
class ApprovalContext:
    approval_id: str
    approver: str
    approved_permissions: frozenset[str]
    rationale: str
    created_at: float = field(default_factory=time.time)
    action_digest: str = ''

class CancellationToken:
    def __init__(self) -> None: self._event = Event()
    def cancel(self) -> None: self._event.set()
    @property
    def cancelled(self) -> bool: return self._event.is_set()

@dataclass(frozen=True)
class EvaluationReport:
    benchmark_id: str
    scenario_ids: tuple[str, ...]
    score: float
    critical_checks: dict[str, bool]
    noncritical_passed: int
    noncritical_total: int
    notes: str = ''
    required_critical_check_ids: tuple[str, ...] = ()
    acceptance_check_ids: tuple[str, ...] = ()
    provider_mode: str = ''
    rubric_id: str = ''
    skipped_checks: tuple[str, ...] = ()

    @property
    def evaluation_valid(self) -> bool:
        if not isinstance(self.critical_checks, dict):
            return False
        required = tuple(self.required_critical_check_ids)
        accepted = tuple(self.acceptance_check_ids)
        try:
            score = float(self.score)
        except (TypeError, ValueError, OverflowError):
            return False
        return bool(
            self.benchmark_id
            and self.scenario_ids
            and len(set(self.scenario_ids)) == len(self.scenario_ids)
            and required
            and len(set(required)) == len(required)
            and accepted
            and len(set(accepted)) == len(accepted)
            and set(required).issubset(set(accepted))
            and set(self.critical_checks) == set(required)
            and all(isinstance(key, str) and key for key in accepted)
            and all(value is True or value is False for value in self.critical_checks.values())
            and not isinstance(self.score, bool)
            and math.isfinite(score)
            and 0.0 <= score <= 1.0
            and not isinstance(self.noncritical_passed, bool)
            and isinstance(self.noncritical_passed, int)
            and not isinstance(self.noncritical_total, bool)
            and isinstance(self.noncritical_total, int)
            and self.noncritical_total == len(set(accepted) - set(required))
            and 0 <= self.noncritical_passed <= self.noncritical_total
            and bool(self.provider_mode)
            and bool(self.rubric_id)
            and not self.skipped_checks
        )

    @property
    def noncritical_rate(self) -> float:
        if not self.evaluation_valid or self.noncritical_total <= 0:
            return 0.0
        return self.noncritical_passed / self.noncritical_total

    @property
    def critical_pass(self) -> bool:
        return self.evaluation_valid and all(value is True for value in self.critical_checks.values())

    def evaluation_context(self) -> dict[str, Any]:
        return {
            'benchmark_id': self.benchmark_id,
            'scenario_ids': list(self.scenario_ids),
            'required_critical_check_ids': list(self.required_critical_check_ids),
            'acceptance_check_ids': list(self.acceptance_check_ids),
            'provider_mode': self.provider_mode,
            'rubric_id': self.rubric_id,
            'skipped_checks': list(self.skipped_checks),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.evaluation_context(),
            'score': self.score,
            'critical_checks': dict(self.critical_checks),
            'noncritical_passed': self.noncritical_passed,
            'noncritical_total': self.noncritical_total,
            'notes': self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> 'EvaluationReport':
        return cls(
            d['benchmark_id'], tuple(d['scenario_ids']), d['score'],
            dict(d['critical_checks']), d['noncritical_passed'],
            d['noncritical_total'], d.get('notes', ''),
            tuple(d.get('required_critical_check_ids', ())),
            tuple(d.get('acceptance_check_ids', ())),
            str(d.get('provider_mode', '')), str(d.get('rubric_id', '')),
            tuple(d.get('skipped_checks', ())),
        )

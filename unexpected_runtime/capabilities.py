from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Callable
import re
import time

from .storage import StateStore


class CapabilityRegistryError(RuntimeError):
    """A capability record or lifecycle transition is invalid or unverified."""


@dataclass(frozen=True)
class CapabilityRecord:
    capability_id: str
    name: str
    category: str
    purpose: str
    source_url: str
    source_publisher: str
    discovered_at: float
    verified_at: float | None
    evidence_refs: tuple[str, ...]
    reviewer: str | None
    adapter_type: str
    provider: str | None
    required_permissions: tuple[str, ...]
    dependencies: tuple[str, ...]
    cost_notes: str
    risk_notes: str
    data_access: tuple[str, ...]
    version: str
    content_sha256: str
    status: str = 'discovered'

    def __post_init__(self) -> None:
        required = (self.capability_id, self.name, self.category, self.purpose,
                    self.source_url, self.source_publisher, self.adapter_type, self.version)
        if any(not str(value).strip() for value in required):
            raise CapabilityRegistryError('Capability identity, purpose, source and adapter metadata are required.')
        if self.discovered_at <= 0:
            raise CapabilityRegistryError('Capability discovery timestamp must be positive.')
        if not re.fullmatch(r'[0-9a-f]{64}', self.content_sha256.lower()):
            raise CapabilityRegistryError('Capability content_sha256 must be a 64-character SHA-256 digest.')
        if self.status not in {'discovered', 'reviewed', 'installed', 'enabled', 'disabled', 'revoked'}:
            raise CapabilityRegistryError(f'Unsupported capability status: {self.status}.')

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ('evidence_refs', 'required_permissions', 'dependencies', 'data_access'):
            data[key] = list(data[key])
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'CapabilityRecord':
        values = dict(data)
        for key in ('evidence_refs', 'required_permissions', 'dependencies', 'data_access'):
            values[key] = tuple(values.get(key, ()))
        return cls(**values)


class CapabilityRegistry:
    """A metadata-only, provenance-aware registry backed by the runtime StateStore."""

    _TRANSITIONS = {
        'discovered': {'reviewed', 'revoked'},
        'reviewed': {'installed', 'disabled', 'revoked'},
        'installed': {'enabled', 'disabled', 'revoked'},
        'enabled': {'disabled', 'revoked'},
        'disabled': {'installed', 'revoked'},
        'revoked': set(),
    }

    def __init__(self, store: StateStore, adapter_verifier: Callable[[CapabilityRecord], bool] | None = None):
        self.store = store
        self.adapter_verifier = adapter_verifier

    def register(self, record: CapabilityRecord) -> CapabilityRecord:
        if not isinstance(record, CapabilityRecord) or record.status != 'discovered':
            raise CapabilityRegistryError('New capability records must be CapabilityRecord instances in discovered state.')
        try:
            self.store.save_capability(record.to_dict())
        except Exception as exc:
            if 'unique' in str(exc).lower() or 'primary key' in str(exc).lower():
                raise CapabilityRegistryError(f'Capability already exists: {record.capability_id}.') from None
            raise
        self.store.log_event('capability_discovered', agent_id=None,
                             payload={'capability_id': record.capability_id, 'source_url': record.source_url,
                                      'source_publisher': record.source_publisher,
                                      'content_sha256': record.content_sha256})
        return record

    def get(self, capability_id: str) -> CapabilityRecord:
        data = self.store.get_capability(capability_id)
        if data is None:
            raise CapabilityRegistryError(f'Unknown capability: {capability_id}.')
        return CapabilityRecord.from_dict(data)

    def list(self, status: str | None = None) -> list[CapabilityRecord]:
        return [CapabilityRecord.from_dict(item) for item in self.store.list_capabilities(status)]

    def transition(self, capability_id: str, target_status: str, *, reviewer: str | None = None,
                   reason: str, approval=None) -> CapabilityRecord:
        current = self.get(capability_id)
        if not reason.strip():
            raise CapabilityRegistryError('A lifecycle transition requires a reason.')
        if target_status not in self._TRANSITIONS.get(current.status, set()):
            raise CapabilityRegistryError(f'Invalid capability transition: {current.status} -> {target_status}.')
        if target_status == 'reviewed' and not (reviewer and reviewer.strip()):
            raise CapabilityRegistryError('A reviewer identity is required to mark a capability reviewed.')
        if target_status == 'enabled':
            if self.adapter_verifier is None or not self.adapter_verifier(current):
                raise CapabilityRegistryError('Capability cannot be enabled without a registered, verified adapter.')
        updated = replace(current, status=target_status,
                          reviewer=reviewer or current.reviewer,
                          verified_at=(time.time() if target_status == 'reviewed' else current.verified_at))
        if not self.store.update_capability(updated.to_dict(), expected_status=current.status):
            raise CapabilityRegistryError(f'Capability changed concurrently: {capability_id}.')
        self.store.log_event('capability_status_changed', payload={
            'capability_id': capability_id, 'from_status': current.status, 'to_status': target_status,
            'reviewer': reviewer, 'reason': reason, 'adapter_type': current.adapter_type,
            'provider': current.provider,
        })
        return updated

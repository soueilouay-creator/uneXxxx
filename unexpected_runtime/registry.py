from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
from .models import UnknownAgent

@dataclass(frozen=True)
class AgentSpec:
    id: str
    name: str
    version: str
    status: str
    objective: str
    capability_label: str
    runtime_capabilities: tuple[str,...]
    required_or_optional_capabilities: tuple[str,...]
    allowed_permissions: tuple[str,...]
    memory_namespace: str
    handoff_targets: tuple[str,...]
    instruction: str
    acceptance_tests: tuple[str,...]
    security_limits: str
    provenance: dict[str,Any]

class AgentRegistry:
    def __init__(self, agents: list[AgentSpec], source_manifest: dict[str,Any] | None = None):
        self._agents={a.id:a for a in agents}; self.source_manifest=source_manifest or {}
        if len(self._agents)!=len(agents): raise ValueError('Duplicate agent IDs in registry')
        for a in agents:
            if not a.id or not a.objective or not a.instruction or not a.acceptance_tests:
                raise ValueError(f'Incomplete agent spec: {a.id!r}')
        for a in agents:
            unknown=set(a.handoff_targets)-set(self._agents)
            if unknown: raise ValueError(f'{a.id} has unknown handoff targets: {sorted(unknown)}')
    @classmethod
    def load(cls, path: str | Path | None = None) -> 'AgentRegistry':
        if path is None: path=Path(__file__).resolve().parent.parent/'agent_manifest.json'
        data=json.loads(Path(path).read_text(encoding='utf-8'))
        agents=[]
        for x in data['agents']:
            agents.append(AgentSpec(id=x['id'],name=x['name'],version=x['version'],status=x['status'],objective=x['objective'],
              capability_label=x['capability_label'],runtime_capabilities=tuple(x['runtime_capabilities']),
              required_or_optional_capabilities=tuple(x['required_or_optional_capabilities']),
              allowed_permissions=tuple(x['allowed_permissions']),memory_namespace=x['memory_namespace'],
              handoff_targets=tuple(x['handoff_targets']),instruction=x['instruction'],acceptance_tests=tuple(x['acceptance_tests']),
              security_limits=x['security_limits'],provenance=x['provenance']))
        return cls(agents,data.get('source_manifest',{}))
    def get(self, agent_id: str) -> AgentSpec:
        try: return self._agents[agent_id]
        except KeyError as e: raise UnknownAgent(f'Unknown agent ID: {agent_id}') from e
    def list(self) -> list[AgentSpec]: return sorted(self._agents.values(),key=lambda a:a.id)
    def __len__(self) -> int: return len(self._agents)
    @property
    def ids(self) -> tuple[str,...]: return tuple(sorted(self._agents))

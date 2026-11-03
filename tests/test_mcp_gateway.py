import hashlib
import tempfile
import time
import unittest
from pathlib import Path

from unexpected_runtime.capabilities import CapabilityRecord, CapabilityRegistry
from unexpected_runtime.coordinator import Coordinator
from unexpected_runtime.mcp_gateway import MCPToolDescriptor, MCPToolError, MCPToolGateway
from unexpected_runtime.models import PermissionDenied
from unexpected_runtime.permissions import PermissionPolicy
from unexpected_runtime.registry import AgentRegistry
from unexpected_runtime.storage import StateStore


class FakeMCPAdapter:
    def __init__(self, descriptor, output=None):
        self.descriptor = descriptor
        self.output = output if output is not None else {"ok": True}
        self.calls = []
    def describe(self):
        return (self.descriptor,)
    def call(self, tool_id, arguments, context):
        self.calls.append((tool_id, dict(arguments), context))
        return self.output


class SlowMCPAdapter(FakeMCPAdapter):
    def call(self, tool_id, arguments, context):
        self.calls.append((tool_id, dict(arguments), context))
        time.sleep(0.2)
        return self.output


class MCPGatewayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = StateStore(self.root / "state.sqlite3")
        self.agents = AgentRegistry.load(Path(__file__).resolve().parents[1] / "agent_manifest.json")
        self.permissions = PermissionPolicy()
        self.capabilities = CapabilityRegistry(self.store)
        self.gateway = MCPToolGateway(
            store=self.store,
            capabilities=self.capabilities,
            permissions=self.permissions,
            agent_registry=self.agents,
        )
        self.digest = hashlib.sha256(b"reviewed adapter bundle").hexdigest()
        self.descriptor = MCPToolDescriptor(
            tool_id="mcp.public.read",
            capability_id="mcp.test-server",
            name="Read public status",
            description="Read a public status value.",
            source_url="https://example.test/mcp",
            source_publisher="Example Publisher",
            version="1.0.0",
            content_sha256=self.digest,
            allowed_agent_ids=("maintenance-engineer",),
            required_permissions=("collaborate",),
            data_access=("public-status",),
            max_argument_bytes=1024,
            max_result_bytes=2048,
            timeout_seconds=2.0,
        )
        self.record = CapabilityRecord(
            capability_id="mcp.test-server",
            name="Example MCP adapter",
            category="integration",
            purpose="Read public status metadata.",
            source_url="https://example.test/mcp",
            source_publisher="Example Publisher",
            discovered_at=1761900000.0,
            verified_at=None,
            evidence_refs=("test:source",),
            reviewer=None,
            adapter_type="mcp",
            provider="example",
            required_permissions=("collaborate",),
            dependencies=(),
            cost_notes="Deterministic in-process test adapter.",
            risk_notes="Public read-only data.",
            data_access=("public-status",),
            version="1.0.0",
            content_sha256=self.digest,
            status="discovered",
        )
        self.capabilities.register(self.record)
        self.capabilities.transition(
            self.record.capability_id, "reviewed", reviewer="owner", reason="Reviewed test adapter provenance."
        )
        self.capabilities.transition(
            self.record.capability_id, "installed", reason="Staged in-process adapter for testing."
        )
        self.adapter = FakeMCPAdapter(self.descriptor)
        self.gateway.register_adapter(self.record.capability_id, self.adapter)

    def tearDown(self):
        self.gateway.close()
        self.temp.cleanup()

    def enable(self):
        return self.capabilities.transition(
            self.record.capability_id, "enabled", reason="Owner enabled reviewed adapter."
        )

    def test_unenabled_capability_is_rejected_before_adapter_call(self):
        with self.assertRaises(MCPToolError):
            self.gateway.call(
                agent_id="maintenance-engineer",
                task_id="task-1",
                tool_id="mcp.public.read",
                arguments={"resource": "line-1"},
            )
        self.assertEqual(self.adapter.calls, [])

    def test_verified_enabled_adapter_executes_with_bounded_context_and_audit(self):
        self.enable()
        result = self.gateway.call(
            agent_id="maintenance-engineer",
            task_id="task-2",
            tool_id="mcp.public.read",
            arguments={"resource": "line-1"},
        )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(self.adapter.calls), 1)
        events = self.store.events(100)
        event_types = {row["event_type"] for row in events}
        self.assertIn("mcp_tool_call_started", event_types)
        self.assertIn("mcp_tool_call_completed", event_types)
        serialized = str(events)
        self.assertNotIn("line-1", serialized)

    def test_role_scope_is_checked_before_adapter_invocation(self):
        self.enable()
        with self.assertRaises(PermissionDenied):
            self.gateway.call(
                agent_id="coding-engineer",
                task_id="task-3",
                tool_id="mcp.public.read",
                arguments={},
            )
        self.assertEqual(self.adapter.calls, [])

    def test_oversized_arguments_and_results_fail_closed(self):
        self.enable()
        with self.assertRaises(MCPToolError):
            self.gateway.call(
                agent_id="maintenance-engineer",
                task_id="task-4",
                tool_id="mcp.public.read",
                arguments={"value": "x" * 2048},
            )
        self.adapter.output = {"value": "x" * 4096}
        with self.assertRaises(MCPToolError):
            self.gateway.call(
                agent_id="maintenance-engineer",
                task_id="task-5",
                tool_id="mcp.public.read",
                arguments={},
            )
        self.assertEqual(len(self.adapter.calls), 1)

    def test_privileged_mcp_tools_remain_disabled_until_durable_approval_is_verified(self):
        record = CapabilityRecord(
            capability_id="mcp.email-server",
            name="Email MCP adapter",
            category="integration",
            purpose="Send an email.",
            source_url="https://example.test/mcp",
            source_publisher="Example Publisher",
            discovered_at=1761900001.0,
            verified_at=None,
            evidence_refs=("test:source",),
            reviewer=None,
            adapter_type="mcp",
            provider="example",
            required_permissions=("email_send",),
            dependencies=(),
            cost_notes="Test only.",
            risk_notes="Privileged external message.",
            data_access=("email",),
            version="1.0.0",
            content_sha256=self.digest,
            status="discovered",
        )
        self.capabilities.register(record)
        self.capabilities.transition(record.capability_id, "reviewed", reviewer="owner", reason="Reviewed.")
        self.capabilities.transition(record.capability_id, "installed", reason="Staged.")
        descriptor = MCPToolDescriptor(
            tool_id="mcp.email.send",
            capability_id=record.capability_id,
            name="Send email",
            description="Send an externally visible email.",
            source_url=record.source_url,
            source_publisher=record.source_publisher,
            version=record.version,
            content_sha256=self.digest,
            allowed_agent_ids=("maintenance-engineer",),
            required_permissions=("email_send",),
            data_access=("email",),
        )
        adapter = FakeMCPAdapter(descriptor)
        with self.assertRaises(MCPToolError):
            self.gateway.register_adapter(record.capability_id, adapter)
        self.assertEqual(adapter.calls, [])

    def test_timeout_is_cancellable_and_never_automatically_retried(self):
        record = CapabilityRecord(
            capability_id="mcp.slow-server",
            name="Slow MCP adapter",
            category="integration",
            purpose="Test a bounded timeout.",
            source_url="https://example.test/mcp",
            source_publisher="Example Publisher",
            discovered_at=1761900002.0,
            verified_at=None,
            evidence_refs=("test:source",),
            reviewer=None,
            adapter_type="mcp",
            provider="example",
            required_permissions=("collaborate",),
            dependencies=(),
            cost_notes="Test only.",
            risk_notes="Read-only.",
            data_access=("public-status",),
            version="1.0.0",
            content_sha256=self.digest,
            status="discovered",
        )
        self.capabilities.register(record)
        self.capabilities.transition(record.capability_id, "reviewed", reviewer="owner", reason="Reviewed.")
        self.capabilities.transition(record.capability_id, "installed", reason="Staged.")
        descriptor = MCPToolDescriptor(
            tool_id="mcp.slow.read",
            capability_id=record.capability_id,
            name="Slow read",
            description="Read a public status value slowly.",
            source_url=record.source_url,
            source_publisher=record.source_publisher,
            version=record.version,
            content_sha256=self.digest,
            allowed_agent_ids=("maintenance-engineer",),
            required_permissions=("collaborate",),
            data_access=("public-status",),
            timeout_seconds=0.1,
        )
        adapter = SlowMCPAdapter(descriptor)
        self.gateway.register_adapter(record.capability_id, adapter)
        self.capabilities.transition(record.capability_id, "enabled", reason="Owner enabled adapter.")
        with self.assertRaises(MCPToolError):
            self.gateway.call(
                agent_id="maintenance-engineer", task_id="task-slow",
                tool_id="mcp.slow.read", arguments={},
            )
        self.assertEqual(len(adapter.calls), 1)
        self.assertTrue(adapter.calls[0][2].cancelled)

    def test_adapter_provenance_mismatch_is_rejected(self):
        wrong = MCPToolDescriptor(
            tool_id="mcp.wrong",
            capability_id="mcp.test-server",
            name="Wrong source",
            description="Wrong adapter source.",
            source_url="https://attacker.test/mcp",
            source_publisher="Untrusted",
            version="1.0.0",
            content_sha256=self.digest,
            allowed_agent_ids=("maintenance-engineer",),
            required_permissions=("collaborate",),
            data_access=("public-status",),
        )
        with self.assertRaises(MCPToolError):
            self.gateway.register_adapter(
                self.record.capability_id, FakeMCPAdapter(wrong)
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)

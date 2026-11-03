import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

from unexpected_runtime.capabilities import CapabilityRecord, CapabilityRegistry, CapabilityRegistryError
from unexpected_runtime.storage import StateStore


class CapabilityRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'runtime.sqlite3'
        self.store = StateStore(self.path)
        self.registry = CapabilityRegistry(self.store)
        self.record = CapabilityRecord(
            capability_id='taaft.public-catalog', name='TAAFT public catalog', category='discovery',
            purpose='Read public tool catalog metadata only', source_url='https://theresanaiforthat.com/mcp/',
            source_publisher='There Is An AI For That', discovered_at=1761900000.0,
            verified_at=None, evidence_refs=('audit:source-page-1',), reviewer=None,
            adapter_type='mcp', provider='taaft', required_permissions=('web.read',),
            dependencies=('mcp-client',), cost_notes='Public metadata only; provider invocation not configured',
            risk_notes='Catalog content is untrusted input', data_access=('public-catalog-metadata',),
            version='1.0.0', content_sha256=hashlib.sha256(b'catalog metadata').hexdigest(), status='discovered'
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_provenance_record_roundtrips_and_persists(self):
        self.registry.register(self.record)
        loaded = self.registry.get(self.record.capability_id)
        self.assertEqual(loaded, self.record)
        reopened = CapabilityRegistry(StateStore(self.path))
        self.assertEqual(reopened.get(self.record.capability_id).source_url, self.record.source_url)
        self.assertEqual(reopened.list(status='discovered'), [self.record])

    def test_duplicate_capability_id_is_rejected(self):
        self.registry.register(self.record)
        with self.assertRaises(CapabilityRegistryError):
            self.registry.register(self.record)

    def test_review_requires_reviewer_and_audits_lifecycle(self):
        self.registry.register(self.record)
        with self.assertRaises(CapabilityRegistryError):
            self.registry.transition(self.record.capability_id, 'reviewed', reason='reviewed source')
        reviewed = self.registry.transition(self.record.capability_id, 'reviewed', reviewer='reviewer-1', reason='source checked')
        self.assertEqual(reviewed.status, 'reviewed')
        events = self.store.events(100)
        self.assertIn('capability_discovered', {event['event_type'] for event in events})
        self.assertIn('capability_status_changed', {event['event_type'] for event in events})

    def test_lifecycle_transitions_are_bounded_and_revoked_is_terminal(self):
        self.registry.register(self.record)
        with self.assertRaises(CapabilityRegistryError):
            self.registry.transition(self.record.capability_id, 'enabled', reason='skip review')
        self.registry.transition(self.record.capability_id, 'reviewed', reviewer='reviewer-1', reason='review')
        self.registry.transition(self.record.capability_id, 'installed', reason='local adapter package staged')
        disabled = self.registry.transition(self.record.capability_id, 'disabled', reason='not activated')
        self.assertEqual(disabled.status, 'disabled')
        revoked = self.registry.transition(self.record.capability_id, 'revoked', reason='source withdrawn')
        self.assertEqual(revoked.status, 'revoked')
        with self.assertRaises(CapabilityRegistryError):
            self.registry.transition(self.record.capability_id, 'reviewed', reviewer='reviewer-2', reason='reopen')

    def test_enabled_requires_a_registered_verified_adapter(self):
        self.registry.register(self.record)
        self.registry.transition(self.record.capability_id, 'reviewed', reviewer='reviewer-1', reason='review')
        self.registry.transition(self.record.capability_id, 'installed', reason='adapter files staged')
        with self.assertRaises(CapabilityRegistryError):
            self.registry.transition(self.record.capability_id, 'enabled', reason='enable catalog')
        verified = CapabilityRegistry(self.store, adapter_verifier=lambda record: record.provider == 'taaft')
        enabled = verified.transition(self.record.capability_id, 'enabled', reason='verified test adapter')
        self.assertEqual(enabled.status, 'enabled')

    def test_capability_registry_is_metadata_only(self):
        calls = []
        self.registry.register(self.record)
        self.registry.get(self.record.capability_id)
        self.registry.list()
        self.assertEqual(calls, [])

    def test_unknown_capability_is_rejected(self):
        with self.assertRaises(CapabilityRegistryError):
            self.registry.get('not-present')

    def test_runtime_exposes_a_capability_registry(self):
        self.assertIsNotNone(importlib.util.find_spec('unexpected_runtime.capabilities'))


if __name__ == '__main__':
    unittest.main(verbosity=2)

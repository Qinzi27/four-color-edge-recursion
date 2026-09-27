"""Contract checks for retaining failures and separating production from audit."""

from copy import deepcopy
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

from scripts import validate_quaternary_order_probe as probe
from scripts.validate_global_restart import export_geometries


class OrderProbeRunnerTests(unittest.TestCase):
    """Use a tiny frame fixture, never the new experimental populations."""

    def test_inventory_covers_declared_final_and_prefix_scopes(self):
        inventory = probe.inventories()
        self.assertEqual(len(inventory['reroot']['records']), 28)
        self.assertEqual(len(inventory['support']['records']), 16)
        self.assertEqual(len(inventory['support']['cases']), 12)
        self.assertEqual(sum(len(h['prefix_keys']) for h in inventory['support']['histories']), 32)
        self.assertEqual(inventory['support']['generation']['orientations_degrees'], [0, 180])

    def test_source_set_independent_of_unrelated_imports(self):
        before = probe.sources()
        with patch.dict(sys.modules, {'unrelated_fake': SimpleNamespace(__file__=str(probe.ROOT / 'not-a-source.py'))}):
            self.assertEqual(before, probe.sources())

    def test_export_failure_is_retained_without_scenarios(self):
        original = {'key': 'raw-key', 'document': {'strokes': []}}
        exported = {'key': 'raw-key', 'status': 'geometry_error', 'errors': ['precision']}
        row = probe.inspect_record('reroot', original, exported)
        self.assertEqual(row['original'], original)
        self.assertEqual(row['export'], exported)
        self.assertEqual(row['error'], ['precision'])
        self.assertEqual(row['scenarios'], [])
        with patch.object(probe, 'solve_low_color', side_effect=AssertionError('must not run')):
            self.assertEqual(probe.run_record(row, probe.RESOURCES)['runs'], [])

    def test_independent_geometry_failure_retained(self):
        original = {'key': 'k', 'document': {'strokes': []}}
        exported = {'key': 'k', 'status': 'geometry_ok', 'geometry': {}}
        with patch.object(probe, 'adapt_exported_geometry', side_effect=ValueError('bad contact')):
            row = probe.inspect_record('reroot', original, exported)
        self.assertEqual(row['eligibility'], 'geometry_audit_error')
        self.assertEqual(row['error'], 'bad contact')

    def test_export_key_mismatch_rejected(self):
        with self.assertRaisesRegex(AssertionError, 'reordered'):
            probe.inspect_record('reroot', {'key': 'a'}, {'key': 'b'})

    def tiny_row(self):
        """A one-stroke map provides a real small auditor binding fixture."""
        document = {'frame': {'width': 900, 'height': 600},
                    'strokes': [{'a': [450, 0], 'b': [450, 600]}]}
        exported = export_geometries([{'key': 'tiny', 'document': document}])[0]
        geometry = exported['geometry']
        return {'family': 'support', 'key': 'tiny', 'eligibility': 'ready',
                'original': {'document': document}, 'export': exported, 'role_mapping': None,
                'scenarios': probe.standard_scenarios(geometry, {'extra_scenarios': []})}

    def test_both_producers_finish_before_posterior_oracles(self):
        order = []
        original_solve, original_audit = probe.solve_low_color, probe.audit_low_color

        def producer(*args, **kwargs):
            order.append('produce')
            return original_solve(*args, **kwargs)

        def auditor(*args, **kwargs):
            order.append('audit')
            return original_audit(*args, **kwargs)

        with patch.object(probe, 'solve_low_color', side_effect=producer), patch.object(
                probe, 'audit_low_color', side_effect=auditor):
            row = probe.run_record(self.tiny_row(), probe.RESOURCES)
        self.assertEqual(order, ['produce', 'produce', 'audit', 'audit'])
        self.assertEqual([r['execution'] for r in row['runs']], ['audited', 'audited'])
        for run in row['runs']:
            checked = probe.check_certificates(run['adapted']['contact_document'],
                                               run['result'], run['audit'], probe.RESOURCES)
            self.assertGreater(checked['oracle_records'], 0)
            corrupted = deepcopy(run['audit'])
            corrupted['oracle_records'][0]['input']['edges'] = []
            with self.assertRaises(AssertionError):
                probe.check_certificates(run['adapted']['contact_document'], run['result'],
                                          corrupted, probe.RESOURCES)

    def test_producer_error_does_not_drop_other_mode_or_claim_pass(self):
        with patch.object(probe, 'solve_low_color', side_effect=RuntimeError('resource interruption')):
            row = probe.run_record(self.tiny_row(), probe.RESOURCES)
        self.assertEqual(len(row['runs']), 2)
        self.assertTrue(all(r['execution'] == 'producer_error' for r in row['runs']))
        self.assertTrue(all('audit' not in r for r in row['runs']))


if __name__ == '__main__':
    unittest.main()

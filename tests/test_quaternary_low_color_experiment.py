"""Check declared coverage and failure retention, not just successful colors."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts.validate_global_restart import digest, export_geometries
from scripts.validate_quaternary_low_color import (
    PRIMARY, LEGACY, compact_run, inventory, run_record, summarize,
)


class LowColorExperimentTests(unittest.TestCase):
    """Prevent selective inputs, hidden rescue and collapsed result categories."""

    def test_complete_inventory_and_known_overlap(self):
        """All old inputs and all sixteen new histories survive selection."""
        data = inventory()
        self.assertEqual(len(data['records']), 4272)
        self.assertEqual(sum(row['new_geometry'] for row in data['records']), 128)
        self.assertEqual(len(data['histories']), 4112)
        self.assertEqual(sum(len(h['prefix_keys']) for h in data['histories']), 28816)
        keys = {row['key'] for row in data['records']}
        self.assertTrue(all(set(h['prefix_keys']) <= keys for h in data['histories']))
        self.assertEqual(sum(len(row.get('scenarios', [])) if 'scenarios' in row else 2
                             for row in data['records']), 8546)
        self.assertFalse(any(s['id'] == 'archived-complete-certificate'
                             for r in data['records'] for s in r.get('scenarios', [])))

    @staticmethod
    def empty_scene():
        """Build one genuine geometric scene with the main single anchor."""
        drawing = {'frame': {'width': 900, 'height': 600}, 'strokes': []}
        geometry = export_geometries([{'key': 'empty-frame', 'document': drawing}])[0]['geometry']
        side = next(i for i in range(len(geometry['faces'])) if i != geometry['outerFace'])
        row = {'key': 'empty-frame', 'document': drawing, 'geometry': geometry,
               'geometry_sha256': digest(geometry), 'new_geometry': False, 'families': ['test'],
               'scenarios': [{'id': PRIMARY, 'anchors': {f'S{side}': 1}}]}
        limits = {'assignment_limit': 262144, 'node_limit': 200000,
                  'decision_limit': 128, 'probe_limit': 512}
        return row, limits

    def test_both_producers_finish_before_first_oracle_audit(self):
        """Auditing cannot furnish either policy's color choices."""
        from scripts.quaternary_low_color import solve_low_color
        from scripts.audit_quaternary_low_color import audit_low_color
        order = []

        def produce(*args, **kwargs):
            order.append('produce')
            return solve_low_color(*args, **kwargs)

        def audit(*args, **kwargs):
            order.append('audit')
            return audit_low_color(*args, **kwargs)

        with patch('scripts.quaternary_low_color.solve_low_color', side_effect=produce), \
             patch('scripts.audit_quaternary_low_color.audit_low_color', side_effect=audit):
            result = run_record(self.empty_scene())
        self.assertNotIn('failed', result)
        self.assertEqual(order, ['produce', 'produce', 'audit', 'audit'])
        self.assertEqual([compact_run(r)['status'] for r in result['runs']], ['solved', 'solved'])

    def test_audit_failure_retains_both_producer_results(self):
        """The first rejected audit still preserves every completed candidate."""
        with patch('scripts.audit_quaternary_low_color.audit_low_color',
                   side_effect=AssertionError('deliberate audit failure')):
            failed = run_record(self.empty_scene())
        self.assertTrue(failed['failed'])
        self.assertEqual(set(failed['candidates']), {'plain', 'guarded'})
        self.assertEqual(failed['error'], 'deliberate audit failure')
        self.assertIn('geometry', failed['input'])

    def test_comparison_separates_unsat_initialization_from_repair(self):
        """An already impossible input is not an algorithmic repair failure."""
        result = run_record(self.empty_scene())
        row = {k: v for k, v in result.items() if k != 'runs'}
        row['runs'] = [compact_run(r) for r in result['runs']]
        for run in row['runs']:
            run['initial_oracle_status'] = 'unsat'
        summary = summarize([row], {'histories': []})
        self.assertEqual(summary['scopes']['all']['paired_completion'][PRIMARY],
                         {'initialization_not_verified_sat': 1})

    def test_second_adapter_failure_has_no_stale_first_scene(self):
        """An adapter exception must name the current scene and clear old data."""
        from scripts.quaternary_geometry_adapter import adapt_exported_geometry
        row, limits = self.empty_scene()
        row['scenarios'].append({'id': LEGACY, 'anchors': {'S0': 1, 'S1': 2}})
        calls = 0

        def adapt(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValueError('second scene adapter failure')
            return adapt_exported_geometry(*args, **kwargs)

        with patch('scripts.validate_quaternary_low_color.adapt_exported_geometry', side_effect=adapt):
            result = run_record((row, limits))
        self.assertTrue(result['failed'])
        self.assertEqual(result['current'], {'scenario': LEGACY, 'stage': 'adapt'})
        self.assertIsNone(result['adapted'])
        self.assertEqual(result['candidates'], {})
        self.assertEqual(len(result['completed_runs']), 2)


if __name__ == '__main__':
    unittest.main()

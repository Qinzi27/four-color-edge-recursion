"""Exercise diagnostic coverage and proof binding without reading formal cases."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import quaternary_conditional_diamond_gap_check as gaps
from scripts.quaternary_logical_neq_low_color import solve_logical_contacts
from scripts import quaternary_odd_wheel_gap_check as previous_gaps
from scripts.quaternary_logical_neq_pair_scan import scan_pairs
from scripts.validate_global_restart import write_report
from tests.test_quaternary_logical_neq_pair_scan import triangular_bipyramid


class ConditionalDiamondGapTests(unittest.TestCase):
    """The fixture intentionally omits wrapper learning; it is not a corpus result."""

    @classmethod
    def setUpClass(cls):
        """Create complete saved synthetic negative trials in an isolated directory."""
        cls.directory = TemporaryDirectory(dir=gaps.ROOT / 'outputs')
        cls.path = Path(cls.directory.name) / 'source.json'
        raw = triangular_bipyramid()
        scan = scan_pairs(raw, solve_logical_contacts(raw, decision_limit=0))
        write_report(cls.path, {'row': {'key': 'fixture', 'runs': [
            {'scenario': 'fixture', 'execution': 'checked', 'scan': scan}]}})
        targets = []
        for state in scan['states']:
            for i, target in enumerate(state['targets']):
                if target['status'] == 'unsupported':
                    conditional = target['conditional']
                    targets.append({'scenario': 'fixture', 'state_index': state['state_index'],
                        'phase': state['phase'], 'target_index': i, 'sides': target['sides'],
                        'symbols': target['symbols'], 'old_status': conditional['status'],
                        'input_sha256': gaps.digest(conditional['input']),
                        'old_outcome_sha256': gaps.digest(conditional['outcome'])})
        cls.inventory = {'groups': [{'key': 'fixture', 'reference': {
            'path': cls.path.relative_to(gaps.ROOT).as_posix(),
            'sha256': gaps.checksum(cls.path)}, 'targets': targets}]}
        # Construct the previous-policy evidence on this tiny fixture only.
        old = previous_gaps.run_gaps(cls.inventory)
        baseline_path = Path(cls.directory.name) / 'baseline.json'
        write_report(baseline_path, {'result': old})
        cls.inventory['baseline_reference'] = {
            'path': baseline_path.relative_to(gaps.ROOT).as_posix(),
            'sha256': gaps.checksum(baseline_path)}
        for item, row in zip(targets, old['rows']):
            item['baseline_status'] = row['outcome']['status']
            item['baseline_outcome_sha256'] = gaps.digest(row['outcome'])
        cls.result = gaps.run_gaps(cls.inventory)

    @classmethod
    def tearDownClass(cls):
        """Remove only this test's temporary evidence directory."""
        cls.directory.cleanup()

    def test_old_refutations_remain_and_checks_do_not_search_or_propagate(self):
        with patch.object(gaps, 'propagate_diamond_contacts', side_effect=AssertionError('rerun')), \
                patch('scripts.exact_extendibility_oracle.solve_exact', side_effect=AssertionError('search')):
            result = gaps.check_saved_gaps(self.inventory, self.result)
        self.assertTrue(result['complete'])
        self.assertEqual(result['counts']['checked'], 12)
        self.assertEqual(result['counts']['new_conflict'], 12)
        self.assertEqual(result['counts']['regressions'], 0)

    def test_omitted_target_is_not_a_complete_diagnostic(self):
        changed = deepcopy(self.result)
        changed['rows'].pop()
        changed['summary'] = gaps.summarize(changed['rows'])
        with self.assertRaises(AssertionError):
            gaps.check_saved_gaps(self.inventory, changed)

    def test_status_or_binary_base_tampering_is_rejected(self):
        for field, value in [('status', 'solved'), ('base_status', 'underdetermined'), ('model', 'wrong')]:
            changed = deepcopy(self.result)
            changed['rows'][0]['outcome'][field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                gaps.check_saved_gaps(self.inventory, changed)

    def test_old_trial_binding_prevents_switching_hypotheses(self):
        changed = deepcopy(self.inventory)
        changed['groups'][0]['targets'][0]['symbols'] = [1, 1]
        with self.assertRaises(AssertionError):
            gaps.run_gaps(changed)

    def test_propagator_error_is_saved_as_incomplete(self):
        with patch.object(gaps, 'propagate_diamond_contacts', side_effect=RuntimeError('fixture failure')):
            result = gaps.run_gaps(self.inventory)
        checked = gaps.check_saved_gaps(self.inventory, result)
        self.assertFalse(checked['complete'])
        self.assertEqual(checked['counts']['errors'], 12)

    def test_false_summary_is_rejected_even_with_valid_evidence(self):
        changed = deepcopy(self.result)
        changed['summary']['counts']['repaired'] = 999
        with self.assertRaises(AssertionError):
            gaps.check_saved_gaps(self.inventory, changed)

    def test_work_metrics_include_every_internal_round(self):
        """A projected final round alone must not undercount repeated propagation."""
        wheel = {'wheel_check': {'certificate': None, 'statistics': {'edges_examined': 7}}}
        check = {'certificates': [{'pair': ['u', 'v']}], 'statistics': {'pairs_examined': 6}}
        outcome = {'conditional_eq': {'equal_names': [['u', 'v']], 'rounds': [
            {'outcome': wheel, 'diamond_check': check},
            {'outcome': wheel, 'diamond_check': None}]}}
        values = gaps.phase_metrics(outcome)
        self.assertEqual(values['propagation_rounds'], 2)
        self.assertEqual(values['wheel_edges_examined'], 14)
        self.assertEqual(values['diamond_certificates'], 1)
        self.assertEqual(values['conditional_eq_pairs'], 1)


if __name__ == '__main__':
    unittest.main()

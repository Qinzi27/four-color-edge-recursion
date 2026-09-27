"""Check paired experiment bookkeeping with tiny and synthetic cases only."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts import validate_quaternary_triangle_eq as experiment


class TriangleEqExperimentTests(unittest.TestCase):
    """Future geometric holdouts are not run by the comparison unit fixtures."""

    def tiny_row(self):
        """A small raw triangle checks producer/auditor sequencing cheaply."""
        raw = {'sides': ['a', 'b', 'c'], 'anchors': {'a': 1}, 'lines': [
            {'id': str(i), 'kind': 'separator', 'left': a, 'right': b}
            for i, (a, b) in enumerate([('a', 'b'), ('b', 'c'), ('a', 'c')])]}
        return experiment.classify({'key': 'tiny', 'kind': 'abstract', 'document': raw})

    def test_both_producers_finish_before_either_audit(self):
        order = []
        functions = {name: getattr(experiment, name) for name in (
            'solve_low_color', 'solve_triangle_eq', 'audit_low_color', 'audit_triangle_eq')}

        def record(name):
            """Record actual helper invocation, while retaining real validation."""
            def wrapped(*args, **kwargs):
                order.append(name)
                return functions[name](*args, **kwargs)
            return wrapped

        with patch.multiple(experiment, **{name: record(name) for name in functions}):
            row = experiment.run_record(self.tiny_row())
        self.assertEqual(order, list(functions))
        self.assertEqual([r['execution'] for r in row['runs']], ['audited', 'audited'])
        self.assertEqual(experiment.comparison(*row['runs']), 'both_success')
        self.assertEqual(experiment.underlying(row['runs'][0]), experiment.underlying(row['runs'][1]))

    def test_producer_failure_retains_other_policy_and_raw_case(self):
        with patch.object(experiment, 'solve_triangle_eq', side_effect=RuntimeError('interrupted')):
            row = experiment.run_record(self.tiny_row())
        self.assertEqual(len(row['runs']), 2)
        self.assertEqual(row['runs'][0]['execution'], 'audited')
        self.assertEqual(row['runs'][1]['execution'], 'producer_error')
        self.assertIn('raw_document', row['runs'][1])
        self.assertEqual(experiment.comparison(*row['runs']), 'unresolved_or_initial_unsat')

    def test_unknown_and_unsafe_are_not_success_from_terminal_status(self):
        entry = experiment.run_record(self.tiny_row())['runs'][0]
        altered = deepcopy(entry)
        altered['audit']['oracle_unknown'] = 1
        self.assertEqual(experiment.quality(altered), 'unknown')
        self.assertEqual(experiment.comparison(entry, altered), 'unresolved_or_initial_unsat')
        altered = deepcopy(entry)
        altered['audit']['commitment_counts']['unsafe'] = 1
        self.assertEqual(experiment.quality(altered), 'unsafe')
        self.assertEqual(experiment.comparison(entry, altered), 'regression')
        self.assertEqual(experiment.comparison(altered, entry), 'repair')

    def test_geometry_exclusion_retained_without_producer_call(self):
        raw = {'key': 'bad', 'kind': 'geometry', 'document': {'strokes': []}}
        exported = {'key': 'bad', 'status': 'geometry_error', 'errors': ['precision']}
        row = experiment.classify(raw, exported)
        self.assertEqual(row['eligibility'], 'geometry_error')
        self.assertEqual(row['error'], ['precision'])
        with patch.object(experiment, 'solve_low_color', side_effect=AssertionError('unexpected')):
            self.assertEqual(experiment.run_record(row)['runs'], [])

    def test_prior_exclusion_cannot_be_silently_reclassified(self):
        prior = {'eligibility': 'geometry_audit_error', 'error': 'bad contact',
                 'export': {'key': 'prior', 'status': 'geometry_ok', 'geometry': {}}}
        raw = {'key': 'prior', 'kind': 'geometry', 'document': {}, 'prior_record': prior}
        row = experiment.classify(raw, prior['export'])
        self.assertEqual(row['eligibility'], 'geometry_audit_error')
        with self.assertRaises(AssertionError):
            experiment.classify(raw, {'key': 'prior', 'status': 'geometry_error'})


if __name__ == '__main__':
    unittest.main()

"""Test the new wrapper's boundary without using future geometric holdouts."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts.quaternary_low_color import solve_low_color
from scripts.quaternary_triangle_eq_low_color import solve_triangle_eq


class TriangleEqualityWrapperTests(unittest.TestCase):
    """Use small raw fixtures; the regression experiment runs after freezing."""

    def triangle(self):
        """A triangle has no pair of distinct common-triangle apices."""
        return {'sides': ['a', 'b', 'c'], 'anchors': {'a': 1}, 'lines': [
            {'id': str(i), 'left': a, 'right': b, 'kind': 'separator'}
            for i, (a, b) in enumerate([('a', 'b'), ('b', 'c'), ('a', 'c')])]}

    def test_no_certificate_means_identical_underlying_behavior(self):
        raw = self.triangle()
        found = solve_triangle_eq(raw)
        self.assertEqual(found['learning']['equal_names'], [])
        self.assertEqual(found['augmented_input'], raw)
        self.assertEqual(found['run'], solve_low_color(raw, probe=True))

    def test_learning_keeps_raw_document_and_face_identities(self):
        raw = self.triangle()
        raw['sides'].extend(['d', 'e'])
        for side in ('d', 'e'):
            for rim in ('a', 'b', 'c'):
                raw['lines'].append({'id': side + rim, 'left': side, 'right': rim, 'kind': 'separator'})
        original = deepcopy(raw)
        found = solve_triangle_eq(raw)
        self.assertEqual(raw, original)
        self.assertEqual(found['original_input'], original)
        self.assertEqual(found['augmented_input']['equal_names'], [['d', 'e']])
        self.assertEqual(found['augmented_input']['sides'], raw['sides'])
        self.assertNotIn('equal_names', raw)
        self.assertEqual(found['run']['status'], 'solved')
        self.assertEqual(found['run']['colors']['d'], found['run']['colors']['e'])

    def test_no_oracle_call_in_production(self):
        with patch('scripts.exact_extendibility_oracle.solve_exact', side_effect=AssertionError('oracle leak')):
            found = solve_triangle_eq(self.triangle(), decision_limit=0)
        self.assertEqual(found['run']['status'], 'incomplete')
        self.assertFalse(found['oracle_feedback_to_producer'])

    def test_external_domains_and_equalities_stay_outside_raw_scope(self):
        for field, value in [('states', {'a': '0111'}), ('equal_names', [['a', 'b']])]:
            raw = self.triangle()
            raw[field] = value
            with self.assertRaises(ValueError):
                solve_triangle_eq(raw)


if __name__ == '__main__':
    unittest.main()

"""Adversarial physical-edge, conditional-class and round-binding controls."""

from copy import deepcopy
from itertools import combinations
import unittest
from unittest.mock import patch

from scripts.check_quaternary_triangle_saturation import (
    audit_saturation_contacts, check_triangle_saturations,
)
from scripts.quaternary_triangle_saturation import find_triangle_saturations
from scripts.quaternary_triangle_saturation_contacts import propagate_saturation_contacts
from scripts.scan_low_color_obstruction_states import digest


def triangle_document():
    """A raw K4 with the three neighbors restricted to colors 2,3,4."""
    sides = ['T', 'A', 'B', 'C']
    return {'sides': sides, 'states': {side: '0111' for side in sides[1:]},
            'lines': [{'id': str(i), 'left': a, 'right': b, 'kind': 'separator'}
                      for i, (a, b) in enumerate(combinations(sides, 2))]}


def split_triangle_document():
    """Literal witnesses can use distinct members of an audited EQ class."""
    raw = triangle_document()
    raw['sides'] += ['U', 'D']
    raw['states']['D'] = '0111'
    raw['equal_names'] = [['T', 'U'], ['A', 'D']]
    raw['lines'][0].update(left='U', right='D')
    raw['lines'][3].update(left='D')
    return raw


class TriangleSaturationCheckerTests(unittest.TestCase):
    """Hash rebinding alone cannot validate false mathematical premises."""

    def setUp(self):
        self.raw = triangle_document()
        self.domains = [[1, 2, 3, 4], [2, 3, 4], [2, 3, 4], [2, 3, 4]]
        self.equal = []
        self.evidence = find_triangle_saturations(self.raw, self.domains, self.equal)

    def check(self, evidence=None, raw=None, domains=None, equal=None):
        """Bind default fixtures while permitting deliberately empty EQ lists."""
        return check_triangle_saturations(self.raw if raw is None else raw,
            self.domains if domains is None else domains,
            self.equal if equal is None else equal,
            self.evidence if evidence is None else evidence)

    def test_three_color_triangle_deletes_exactly_other_target_candidates(self):
        checked = self.check()
        self.assertEqual(checked['certificates_checked'], 1)
        self.assertEqual(checked['removed_candidates_checked'], 3)
        self.assertEqual(self.evidence['certificates'][0]['removed_colors'], [2, 3, 4])

    def test_class_members_supply_physical_edges_without_becoming_new_faces(self):
        raw = split_triangle_document()
        domains = self.domains + [[1, 2, 3, 4], [2, 3, 4]]
        evidence = find_triangle_saturations(raw, domains, raw['equal_names'])
        checked = self.check(evidence, raw, domains, raw['equal_names'])
        self.assertEqual(evidence['classes'], [['T', 'U'], ['A', 'D'], ['B'], ['C']])
        self.assertEqual(checked['certificates_checked'], 1)
        self.assertIn(['U', 'D'], evidence['certificates'][0]['edges'])

    def test_hashes_bind_raw_document_domains_and_exact_eq_list(self):
        for field in ('raw_document_sha256', 'domains_sha256', 'equal_names_sha256'):
            altered = deepcopy(self.evidence)
            altered[field] = '0' * 64
            with self.subTest(field=field), self.assertRaises(AssertionError):
                self.check(altered)

    def test_omission_duplicate_target_and_invented_class_are_rejected(self):
        for change in (lambda e: e['certificates'].clear(),
                       lambda e: e['certificates'].append(deepcopy(e['certificates'][0])),
                       lambda e: e['classes'][0].append('A'),
                       lambda e: e['classes'].reverse()):
            altered = deepcopy(self.evidence)
            change(altered)
            altered['statistics']['certificates_found'] = len(altered['certificates'])
            altered['statistics']['physical_witness_edges'] = 6 * len(altered['certificates'])
            with self.assertRaises(AssertionError):
                self.check(altered)

    def test_all_six_physical_edges_required_despite_neq_or_point_contact(self):
        for number in range(6):
            raw = deepcopy(self.raw)
            line = raw['lines'].pop(number)
            raw['different_names'] = [[line['left'], line['right']]]
            raw['point_contacts'] = [{'sides': [line['left'], line['right']]}]
            altered = deepcopy(self.evidence)
            altered['raw_document_sha256'] = digest(raw)
            with self.subTest(number=number), self.assertRaisesRegex(AssertionError, 'real separator'):
                self.check(altered, raw)

    def test_edge_witness_order_classes_and_literal_identity_are_checked(self):
        for edges in (self.evidence['certificates'][0]['edges'][1:],
                      [['A', 'T']] * 6,
                      [['unknown', 'B']] * 6):
            altered = deepcopy(self.evidence)
            altered['certificates'][0]['edges'] = edges
            with self.assertRaises(AssertionError):
                self.check(altered)

    def test_certificate_palette_target_triangle_and_removals_strict(self):
        for key, value in [('excluded_color', True), ('excluded_color', 1.0),
                           ('excluded_color', 2), ('target', 'missing'),
                           ('triangle', ['A', 'A', 'C']), ('triangle', ['C', 'B', 'A']),
                           ('triangle', ['T', 'B', 'C']), ('removed_colors', [2, 3]),
                           ('removed_colors', [True, 3, 4]), ('removed_colors', [4, 3, 2])]:
            altered = deepcopy(self.evidence)
            altered['certificates'][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(AssertionError):
                self.check(altered)

    def test_literal_domains_and_counters_reject_boolean_and_out_of_range(self):
        for values in ([True, 2, 3], [3, 2, 4], [2, 2, 4], [2, 3, 5]):
            domains = deepcopy(self.domains)
            domains[1] = values
            with self.assertRaises(AssertionError):
                self.check(domains=domains)
        for key in self.evidence['statistics']:
            for value in (True, -1, 1.5, 10 ** 8):
                altered = deepcopy(self.evidence)
                altered['statistics'][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(AssertionError):
                    self.check(altered)

    def test_eq_domain_consistency_and_internal_physical_edges_required(self):
        for equal in ([['T', 'A']], [['A', 'B']], [['A', 'missing']], ['A']):
            with self.assertRaises(AssertionError):
                self.check(equal=equal)

    def test_four_color_or_already_forced_target_has_checked_absence(self):
        for domains in ([[1, 2, 3, 4]] * 4, [[1]] + self.domains[1:]):
            evidence = find_triangle_saturations(self.raw, domains, [])
            self.assertTrue(self.check(evidence, domains=domains)['absence_checked'])

    def test_saved_replay_imports_no_detector_propagation_or_search(self):
        outcome = propagate_saturation_contacts(self.raw)
        with patch('scripts.quaternary_triangle_saturation.find_triangle_saturations',
                   side_effect=RuntimeError('detector')), patch(
                       'scripts.quaternary_triangle_saturation_contacts.propagate_diamond_contacts',
                       side_effect=RuntimeError('propagation')):
            self.assertTrue(self.check()['passed'])
            self.assertEqual(audit_saturation_contacts(self.raw, outcome)['triangle_saturation']['round_count'], 2)

    def test_rounds_bind_domains_even_after_rehashing_certificate(self):
        outcome = propagate_saturation_contacts(self.raw)
        row = outcome['triangle_saturation']['rounds'][0]
        row['outcome']['domains'][1] = [2, 3]
        row['triangle_check']['domains_sha256'] = digest(row['outcome']['domains'])
        with self.assertRaises(AssertionError):
            audit_saturation_contacts(self.raw, outcome)

    def test_only_exact_candidate_batch_can_enter_next_round(self):
        for mutate in (lambda d: d['states'].__setitem__('T', '1111'),
                       lambda d: d.setdefault('anchors', {}).__setitem__('T', 1),
                       lambda d: d.setdefault('equal_names', []).append(['T', 'A']),
                       lambda d: d['lines'].pop(),
                       lambda d: d['states'].__setitem__('A', '0100')):
            outcome = propagate_saturation_contacts(self.raw)
            mutate(outcome['triangle_saturation']['rounds'][1]['document'])
            with self.assertRaisesRegex(AssertionError, 'input mutation'):
                audit_saturation_contacts(self.raw, outcome)

    def test_round_omission_repetition_summary_and_extra_fields_fail(self):
        for mutate in (lambda c: c['rounds'].pop(),
                       lambda c: c['rounds'].append(deepcopy(c['rounds'][-1])),
                       lambda c: c['removed_candidates'].clear(),
                       lambda c: c.__setitem__('oracle_trusted', True)):
            outcome = propagate_saturation_contacts(self.raw)
            mutate(outcome['triangle_saturation'])
            with self.assertRaises(AssertionError):
                audit_saturation_contacts(self.raw, outcome)

    def test_projection_and_original_input_binding(self):
        for key, value in [('status', 'conflict'), ('original_input', {}),
                           ('trace', [{'fake': True}]), ('oracle_hint', True)]:
            outcome = propagate_saturation_contacts(self.raw)
            outcome[key] = value
            with self.subTest(key=key), self.assertRaises(AssertionError):
                audit_saturation_contacts(self.raw, outcome)

    def test_terminal_round_requires_no_certificate(self):
        raw = {'sides': ['T'], 'lines': [], 'anchors': {'T': 1}}
        outcome = propagate_saturation_contacts(raw)
        self.assertEqual(audit_saturation_contacts(raw, outcome)['status'], 'solved')
        outcome['triangle_saturation']['rounds'][0]['triangle_check'] = self.evidence
        with self.assertRaisesRegex(AssertionError, 'terminal'):
            audit_saturation_contacts(raw, outcome)

    def test_trace_total_covers_all_nested_wheel_rounds(self):
        outcome = propagate_saturation_contacts(self.raw)
        audit = audit_saturation_contacts(self.raw, outcome)
        expected = sum(len(inner['outcome']['trace']) for outer in outcome['triangle_saturation']['rounds']
                       for inner in outer['outcome']['conditional_eq']['rounds'])
        self.assertEqual(audit['trace_steps_checked'], expected)
        self.assertEqual(outcome['original_input'], self.raw)
        self.assertNotIn('T', self.raw['states'])


if __name__ == '__main__':
    unittest.main()

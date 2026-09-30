"""Adversarial tests for physical odd-wheel witnesses and domain provenance."""

from copy import deepcopy
from itertools import product
import unittest
from unittest.mock import patch

from scripts.check_quaternary_odd_wheel import audit_wheel_contacts, check_odd_wheel
from scripts.quaternary_logical_neq_contacts import propagate_logical_contacts
from scripts.quaternary_odd_wheel import find_odd_wheel
from scripts.quaternary_odd_wheel_contacts import propagate_wheel_contacts
from scripts.scan_low_color_obstruction_states import digest


def wheel_document(length=5, restricted=True):
    """A real wheel, optionally with every vertex confined to names 1,2,3."""
    sides = ['hub'] + [f'r{i}' for i in range(length)]
    pairs = [('hub', f'r{i}') for i in range(length)]
    pairs += [(f'r{i}', f'r{(i + 1) % length}') for i in range(length)]
    document = {'sides': sides, 'lines': [
        {'id': f'e{i}', 'left': a, 'right': b, 'kind': 'separator'}
        for i, (a, b) in enumerate(pairs)]}
    if restricted:
        document['states'] = {side: '1110' for side in sides}
    return document


class OddWheelCheckTests(unittest.TestCase):
    """Saved witness checks must not rely on detector choices or search."""

    def setUp(self):
        self.document = wheel_document()
        self.domains = [[1, 2, 3] for _ in self.document['sides']]
        self.evidence = find_odd_wheel(self.document, self.domains)

    def test_odd_rim_witness_is_checked_without_detector(self):
        with patch('scripts.quaternary_odd_wheel.find_odd_wheel', side_effect=RuntimeError('detector')):
            checked = check_odd_wheel(self.document, self.domains, self.evidence)
        self.assertTrue(checked['certificate_checked'])

    def test_valid_rotation_and_reverse_are_accepted(self):
        for rim in (['r2', 'r3', 'r4', 'r0', 'r1'], ['r0', 'r4', 'r3', 'r2', 'r1']):
            altered = deepcopy(self.evidence)
            altered['certificate']['rim'] = rim
            self.assertTrue(check_odd_wheel(self.document, self.domains, altered)['found'])

    def test_literal_finite_assignments_confirm_triangle_and_five_rim_conflicts(self):
        for length in (3, 5):
            document = wheel_document(length)
            positions = {side: i for i, side in enumerate(document['sides'])}
            for excluded in (1, 2, 3, 4):
                names = [color for color in range(1, 5) if color != excluded]
                domains = [names[:] for _ in document['sides']]
                evidence = find_odd_wheel(document, domains)
                check_odd_wheel(document, domains, evidence)
                legal = [values for values in product(*domains) if all(
                    values[positions[line['left']]] != values[positions[line['right']]]
                    for line in document['lines'])]
                self.assertEqual(legal, [])

    def test_even_rim_and_four_color_control_have_checked_absence(self):
        for document, domains in ((wheel_document(4), [[1, 2, 3]] * 5),
                                  (wheel_document(), [[1, 2, 3, 4]] * 6)):
            evidence = find_odd_wheel(document, domains)
            self.assertIsNone(evidence['certificate'])
            self.assertTrue(check_odd_wheel(document, domains, evidence)['absence_checked'])

    def test_omitted_wheel_is_rejected_by_independent_bipartiteness(self):
        altered = deepcopy(self.evidence)
        altered['certificate'] = None
        altered['statistics']['odd_cycles_found'] = 0
        with self.assertRaisesRegex(AssertionError, 'omitted'):
            check_odd_wheel(self.document, self.domains, altered)

    def test_missing_spoke_and_rim_are_not_replaced_by_logical_or_point_contacts(self):
        for line_index in (0, 5):
            altered = deepcopy(self.document)
            missing = altered['lines'].pop(line_index)
            altered['different_names'] = [[missing['left'], missing['right']]]
            altered['point_contacts'] = [{'sides': [missing['left'], missing['right']]}]
            altered['lines'].append({'id': 'bridge', 'left': 'hub', 'right': 'hub', 'kind': 'bridge'})
            evidence = deepcopy(self.evidence)
            evidence['raw_document_sha256'] = digest(altered)
            with self.subTest(line_index=line_index), self.assertRaisesRegex(AssertionError, 'real separator'):
                check_odd_wheel(altered, self.domains, evidence)

    def test_no_common_palette_rejects_witness(self):
        for index in (0, 3):
            domains = deepcopy(self.domains)
            domains[index].append(4)
            evidence = deepcopy(self.evidence)
            evidence['domains_sha256'] = digest(domains)
            with self.assertRaisesRegex(AssertionError, 'excluded color'):
                check_odd_wheel(self.document, domains, evidence)

    def test_malformed_rim_center_color_and_schema_are_rejected(self):
        changes = [('rim', ['r0', 'r1', 'r2', 'r3']), ('rim', ['r0', 'r1', 'r0']),
                   ('rim', ['hub', 'r0', 'r1']), ('rim', ['r0', 'r1', 'unknown']),
                   ('center', 'unknown'), ('excluded_color', True), ('excluded_color', 4.0),
                   ('excluded_color', 0)]
        for name, value in changes:
            evidence = deepcopy(self.evidence)
            evidence['certificate'][name] = value
            with self.subTest(name=name, value=value), self.assertRaises(AssertionError):
                check_odd_wheel(self.document, self.domains, evidence)
        evidence = deepcopy(self.evidence)
        evidence['certificate']['logical_edge'] = True
        with self.assertRaises(AssertionError):
            check_odd_wheel(self.document, self.domains, evidence)

    def test_hashes_literal_domains_and_telemetry_are_checked(self):
        for key in ('raw_document_sha256', 'domains_sha256'):
            evidence = deepcopy(self.evidence)
            evidence[key] = '0' * 64
            with self.assertRaises(AssertionError):
                check_odd_wheel(self.document, self.domains, evidence)
        for values in ([True, 2, 3], [3, 2, 1], [1, 1, 2], [1, 2, 5]):
            domains = deepcopy(self.domains)
            domains[0] = values
            with self.assertRaises(AssertionError):
                check_odd_wheel(self.document, domains, self.evidence)
        for value in (True, -1, 1.0):
            evidence = deepcopy(self.evidence)
            evidence['statistics']['edges_examined'] = value
            with self.assertRaises(AssertionError):
                check_odd_wheel(self.document, self.domains, evidence)

    def test_contact_trace_precedes_wheel_proof(self):
        outcome = propagate_wheel_contacts(self.document)
        self.assertEqual(outcome['base_status'], 'underdetermined')
        self.assertEqual(outcome['status'], 'conflict')
        self.assertEqual(audit_wheel_contacts(self.document, outcome)['status'], 'conflict')
        altered = deepcopy(outcome)
        altered['domains'][0] = [1, 2]
        altered['wheel_check']['domains_sha256'] = digest(altered['domains'])
        with self.assertRaisesRegex(AssertionError, 'diagonal'):
            audit_wheel_contacts(self.document, altered)

    def test_status_only_changes_require_the_bound_witness(self):
        outcome = propagate_wheel_contacts(self.document)
        for mutation in (lambda item: item.__setitem__('status', 'underdetermined'),
                         lambda item: item.__setitem__('base_status', 'conflict'),
                         lambda item: item.__setitem__('wheel_check', None)):
            altered = deepcopy(outcome)
            mutation(altered)
            with self.assertRaises(AssertionError):
                audit_wheel_contacts(self.document, altered)

    def test_solved_and_base_conflict_must_skip_detector(self):
        for raw in ({'sides': ['a'], 'lines': [], 'anchors': {'a': 2}},
                    {'sides': ['a', 'b'], 'anchors': {'a': 1, 'b': 1},
                     'lines': [{'id': 'e', 'left': 'a', 'right': 'b', 'kind': 'separator'}]}):
            outcome = propagate_wheel_contacts(raw)
            self.assertIsNone(outcome['wheel_check'])
            audit_wheel_contacts(raw, outcome)
            altered = deepcopy(outcome)
            altered['wheel_check'] = self.evidence
            with self.assertRaises(AssertionError):
                audit_wheel_contacts(raw, altered)

    def test_four_color_satisfiable_wheel_cannot_be_claimed_conflict(self):
        raw = wheel_document(restricted=False)
        outcome = propagate_wheel_contacts(raw)
        self.assertEqual(outcome['status'], 'underdetermined')
        outcome['status'] = 'conflict'
        with self.assertRaisesRegex(AssertionError, 'status'):
            audit_wheel_contacts(raw, outcome)

    def test_contact_base_fields_equal_frozen_propagator(self):
        outcome = propagate_wheel_contacts(self.document)
        restored = deepcopy(outcome)
        restored['status'] = restored.pop('base_status')
        restored.pop('wheel_check')
        restored['model'] = 'quaternary-logical-neq-contact-relations-v1'
        self.assertEqual(restored, propagate_logical_contacts(self.document))


if __name__ == '__main__':
    unittest.main()

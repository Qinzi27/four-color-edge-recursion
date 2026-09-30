"""Adversarial certificate and local-equality round binding controls."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts.check_quaternary_conditional_diamond import (
    audit_diamond_contacts, check_conditional_diamonds,
)
from scripts.quaternary_conditional_diamond import find_conditional_diamonds
from scripts.quaternary_conditional_diamond_contacts import propagate_diamond_contacts
from scripts.quaternary_odd_wheel_contacts import propagate_wheel_contacts
from scripts.scan_low_color_obstruction_states import digest


def diamond_document(restricted=True):
    """Two triangles on a common real edge, with optional common palette."""
    sides = ['u', 'v', 'a', 'b']
    edges = [('a', 'b'), ('a', 'u'), ('a', 'v'), ('b', 'u'), ('b', 'v')]
    raw = {'sides': sides, 'lines': [{'id': str(i), 'left': a, 'right': b,
                                    'kind': 'separator'} for i, (a, b) in enumerate(edges)]}
    if restricted:
        raw['states'] = {side: '1110' for side in sides}
    return raw


class ConditionalDiamondCheckTests(unittest.TestCase):
    """An accepted certificate must bind real edges and independently replayed domains."""

    def setUp(self):
        self.raw = diamond_document()
        self.base = propagate_wheel_contacts(self.raw)
        self.domains, self.relations = self.base['domains'], self.base['relations']
        self.evidence = find_conditional_diamonds(self.raw, self.domains, self.relations)

    def check(self, evidence=None, raw=None, domains=None, relations=None):
        return check_conditional_diamonds(raw or self.raw, domains or self.domains,
                                         relations or self.relations, evidence or self.evidence)

    def test_saved_checker_never_calls_detector_or_propagation(self):
        outcome = propagate_diamond_contacts(self.raw)
        with patch('scripts.quaternary_conditional_diamond.find_conditional_diamonds',
                   side_effect=RuntimeError('detector')), patch(
                       'scripts.quaternary_conditional_diamond_contacts.propagate_wheel_contacts',
                       side_effect=RuntimeError('propagation')):
            self.assertEqual(self.check()['certificates_checked'], 1)
            self.assertEqual(audit_diamond_contacts(self.raw, outcome)['conditional_eq']['round_count'], 2)

    def test_all_hashes_are_bound(self):
        for field in ('raw_document_sha256', 'domains_sha256', 'relations_sha256'):
            changed = deepcopy(self.evidence)
            changed[field] = '0' * 64
            with self.subTest(field=field), self.assertRaises(AssertionError):
                self.check(changed)

    def test_omission_duplicate_and_reversed_pair_are_rejected(self):
        for certificates in ([], self.evidence['certificates'] * 2,
                             [{**self.evidence['certificates'][0], 'pair': ['v', 'u']}]):
            changed = deepcopy(self.evidence)
            changed['certificates'] = certificates
            changed['statistics']['certificates_found'] = len(certificates)
            with self.assertRaises(AssertionError):
                self.check(changed)

    def test_missing_physical_edge_cannot_be_replaced_by_logical_or_point_contact(self):
        for index in (0, 1, 4):
            raw = deepcopy(self.raw)
            line = raw['lines'].pop(index)
            raw['different_names'] = [[line['left'], line['right']]]
            raw['point_contacts'] = [{'sides': [line['left'], line['right']]}]
            changed = deepcopy(self.evidence)
            changed['raw_document_sha256'] = digest(raw)
            with self.assertRaisesRegex(AssertionError, 'real separator'):
                self.check(changed, raw=raw)

    def test_literal_four_distinct_vertices_and_color_are_required(self):
        for field, value in [('pair', ['u', 'u']), ('edge', ['a', 'u']),
                             ('edge', ['b', 'a']), ('pair', ['unknown', 'v']),
                             ('excluded_color', True), ('excluded_color', 4.0),
                             ('excluded_color', 0)]:
            changed = deepcopy(self.evidence)
            changed['certificates'][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(AssertionError):
                self.check(changed)

    def test_common_domain_exclusion_is_required(self):
        changed = deepcopy(self.evidence)
        changed['certificates'][0]['excluded_color'] = 1
        with self.assertRaisesRegex(AssertionError, 'excluded color'):
            self.check(changed)

    def test_matrix_literal_width_diagonal_transpose_and_domain_containment(self):
        for i, j, value in [(0, 1, True), (0, 1, 65536), (0, 1, -1),
                            (0, 0, 0), (0, 1, 1), (0, 1, 65535)]:
            relations = deepcopy(self.relations)
            relations[i][j] = value
            changed = deepcopy(self.evidence)
            changed['relations_sha256'] = digest(relations)
            with self.subTest(i=i, j=j, value=value), self.assertRaises(AssertionError):
                self.check(changed, relations=relations)

    def test_domain_literals_and_telemetry_are_strict(self):
        for values in ([True, 2, 3], [3, 2, 1], [1, 1, 3], [1, 2, 5]):
            domains = deepcopy(self.domains)
            domains[0] = values
            with self.assertRaises(AssertionError):
                self.check(domains=domains)
        for value in (True, -1, 1.0, 10 ** 12):
            changed = deepcopy(self.evidence)
            changed['statistics']['common_edges_examined'] = value
            with self.assertRaises(AssertionError):
                self.check(changed)

    def test_four_color_and_already_equal_pair_have_verified_absence(self):
        for raw in (diamond_document(False), {**self.raw, 'equal_names': [['u', 'v']]}):
            base = propagate_wheel_contacts(raw)
            evidence = find_conditional_diamonds(raw, base['domains'], base['relations'])
            self.assertTrue(check_conditional_diamonds(raw, base['domains'], base['relations'],
                                                       evidence)['absence_checked'])

    def test_domains_require_trace_provenance_even_if_hashes_are_rewritten(self):
        outcome = propagate_diamond_contacts(self.raw)
        outcome['conditional_eq']['rounds'][0]['outcome']['domains'][0] = [1, 2]
        round_ = outcome['conditional_eq']['rounds'][0]
        round_['diamond_check']['domains_sha256'] = digest(round_['outcome']['domains'])
        with self.assertRaises(AssertionError):
            audit_diamond_contacts(self.raw, outcome)

    def test_complete_eq_batch_must_be_applied_without_other_mutations(self):
        for mutation in (lambda row: row['document'].__setitem__('equal_names', []),
                         lambda row: row['document'].setdefault('anchors', {}).__setitem__('u', 1),
                         lambda row: row['document']['states'].__setitem__('a', '1100'),
                         lambda row: row['document']['lines'].pop()):
            outcome = propagate_diamond_contacts(self.raw)
            mutation(outcome['conditional_eq']['rounds'][1])
            with self.assertRaisesRegex(AssertionError, 'input mutation'):
                audit_diamond_contacts(self.raw, outcome)

    def test_round_omission_early_stop_repeat_and_extra_fields_fail(self):
        for mutation in (lambda c: c['rounds'].pop(),
                         lambda c: c['rounds'].append(deepcopy(c['rounds'][-1])),
                         lambda c: c['equal_names'].clear(),
                         lambda c: c.__setitem__('trusted', True)):
            outcome = propagate_diamond_contacts(self.raw)
            mutation(outcome['conditional_eq'])
            with self.assertRaises(AssertionError):
                audit_diamond_contacts(self.raw, outcome)

    def test_final_projection_binds_every_field_and_original_input(self):
        for field, value in [('status', 'conflict'), ('original_input', {}), ('trace', [{'fake': True}]),
                             ('oracle_hint', True)]:
            outcome = propagate_diamond_contacts(self.raw)
            outcome[field] = value
            with self.assertRaises(AssertionError):
                audit_diamond_contacts(self.raw, outcome)

    def test_terminal_round_has_no_diamond_evidence_and_no_continuation(self):
        raw = {'sides': ['a'], 'lines': [], 'anchors': {'a': 1}}
        outcome = propagate_diamond_contacts(raw)
        self.assertEqual(audit_diamond_contacts(raw, outcome)['status'], 'solved')
        outcome['conditional_eq']['rounds'][0]['diamond_check'] = self.evidence
        with self.assertRaisesRegex(AssertionError, 'terminal'):
            audit_diamond_contacts(raw, outcome)

    def test_closure_trace_counts_cover_all_internal_rounds(self):
        outcome = propagate_diamond_contacts(self.raw)
        audit = audit_diamond_contacts(self.raw, outcome)
        self.assertEqual(audit['trace_steps_checked'], sum(
            len(row['outcome']['trace']) for row in outcome['conditional_eq']['rounds']))
        self.assertEqual(outcome['original_input'], self.raw)
        self.assertNotIn('equal_names', self.raw)


if __name__ == '__main__':
    unittest.main()

"""Adversarial raw/learned-boundary checks for the logical-NEQ pipeline."""

from copy import deepcopy
from itertools import combinations
import unittest
from unittest.mock import patch

from scripts.audit_quaternary_logical_neq import (
    audit_logical_contacts, audit_logical_neq, check_logical_neq_artifacts,
    verify_logical_inequalities,
)
from scripts.exact_extendibility_oracle import solve_exact, verify_exact_result
from scripts.quaternary_bipyramid_inputs import base_drawing
from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.quaternary_logical_neq import learn_logical_inequalities
from scripts.quaternary_logical_neq_contacts import propagate_logical_contacts
from scripts.quaternary_logical_neq_low_color import solve_logical_neq
from scripts.validate_global_restart import export_geometries

RESOURCES = {'decision_limit': 128, 'probe_limit': 8192,
             'assignment_limit': 262144, 'node_limit': 200000}


def positive_document():
    """Known six-side calibration: v=u, w=a, and the nonedge v-w is NEQ."""
    sides = ['u', 'a', 'b', 'c', 'v', 'w']
    pairs = list(combinations(range(4), 2)) + [(4, 1), (4, 2), (4, 3), (5, 0), (5, 2), (5, 3)]
    return {'sides': sides, 'anchors': {'u': 1}, 'lines': [
        {'id': f'E{i}', 'left': sides[a], 'right': sides[b], 'kind': 'separator'}
        for i, (a, b) in enumerate(pairs)]}


def small_document():
    """An anchored edge requires exactly one guarded commitment."""
    return {'sides': ['A', 'B'], 'anchors': {'A': 1},
            'lines': [{'id': 'E', 'left': 'A', 'right': 'B', 'kind': 'separator'}]}


class LogicalNeqAuditTests(unittest.TestCase):
    """Independent phase replay and certificates must reject altered evidence."""

    @classmethod
    def setUpClass(cls):
        """Cache small existing controls, including a genuine geometric drawing."""
        cls.raw = positive_document()
        cls.envelope = solve_logical_neq(cls.raw)
        cls.audit = audit_logical_neq(cls.raw, cls.envelope)
        cls.small = small_document()
        cls.small_envelope = solve_logical_neq(cls.small)
        cls.small_audit = audit_logical_neq(cls.small, cls.small_envelope)
        cls.drawing = base_drawing()
        cls.geometry = export_geometries([{'key': 'known-unit', 'document': cls.drawing}])[0]['geometry']
        cls.adapted = adapt_exported_geometry(cls.geometry, anchors={'S0': 1}, drawing=cls.drawing)

    def check(self, envelope=None, audit=None, resources=None):
        """Use the same frozen-style paired resource contract in each replay."""
        return check_logical_neq_artifacts(self.raw, envelope or self.envelope,
                                           audit or self.audit, resources or RESOURCES)

    def test_raw_graph_and_all_solutions_are_preserved(self):
        """The learned relation is separate from the physical line inventory."""
        self.assertIn(['v', 'w'], self.envelope['learning']['inequalities']['different_names'])
        self.assertEqual(self.envelope['augmented_input']['lines'], self.raw['lines'])
        self.assertEqual(self.audit['full_enumeration']['initial_legal_assignments'], 6)
        self.assertEqual(self.audit['commitment_counts']['unsafe'], 0)
        self.assertTrue(self.check()['passed'])
        for phase in self.envelope['run']['phases']:
            self.assertEqual(phase['document']['different_names'], self.envelope['augmented_input']['different_names'])
            self.assertEqual(phase['document']['lines'], self.raw['lines'])
        self.assertEqual(self.audit['logical_neq_check']['physical_edges_added'], 0)

    def test_geometry_adapter_binds_only_original_real_edges(self):
        """Small legal geometry can complete and replay with logical premises separate."""
        raw = self.adapted['contact_document']
        envelope = solve_logical_neq(raw, geometry=self.geometry)
        audit = audit_logical_neq(raw, envelope, geometry=self.geometry, adapted=self.adapted)
        checked = check_logical_neq_artifacts(raw, envelope, audit, RESOURCES,
                                              geometry=self.geometry, adapted=self.adapted)
        self.assertTrue(checked['passed'])
        self.assertEqual(envelope['augmented_input']['lines'], raw['lines'])
        bad = deepcopy(self.adapted)
        bad['contact_document'] = envelope['augmented_input']
        with self.assertRaises(AssertionError):
            audit_logical_neq(raw, envelope, geometry=self.geometry, adapted=bad)

    def test_saved_checker_runs_no_producer_search_or_propagation(self):
        """All stored literal traces and query certificates suffice for replay."""
        with patch('scripts.quaternary_logical_neq_low_color.solve_logical_neq', side_effect=AssertionError('producer')), \
                patch('scripts.quaternary_logical_neq_contacts.propagate_logical_contacts', side_effect=AssertionError('propagate')), \
                patch('scripts.quaternary_logical_neq.learn_logical_inequalities', side_effect=AssertionError('learner')), \
                patch('scripts.audit_quaternary_logical_neq.solve_exact', side_effect=AssertionError('oracle')), \
                patch('fourcolor.structural_name_relations.refute_same_name', side_effect=AssertionError('refuter')):
            checked = self.check()
        self.assertEqual(checked['producer_runs'], 0)
        self.assertEqual(checked['oracle_searches'], 0)

    def test_all_nonedge_query_coverage_order_and_statistics_are_checked(self):
        """Even omitted inconclusive queries invalidate declared full coverage."""
        for mutation in (lambda item: item['queries'].pop(), lambda item: item['queries'].reverse(),
                         lambda item: item['stats'].__setitem__('eligible_pairs', 0),
                         lambda item: item['different_names'].clear()):
            bad = deepcopy(self.envelope['learning']['inequalities'])
            mutation(bad)
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                verify_logical_inequalities(self.raw, bad)

    def test_false_positive_proof_is_rejected_before_any_oracle(self):
        """A graph implication must have a valid raw-edge contradiction certificate."""
        bad = deepcopy(self.envelope)
        proof = next(row['result'] for row in bad['learning']['inequalities']['queries']
                     if row['result']['status'] == 'proved_different')
        proof['contradiction'] = None
        with patch('scripts.audit_quaternary_logical_neq.solve_exact', side_effect=RuntimeError('oracle')), \
                self.assertRaises(AssertionError):
            audit_logical_neq(self.raw, bad)

    def test_raw_input_hash_and_boolean_proof_id_are_checked(self):
        """Literal IDs cannot use Python's bool/int equality shortcut."""
        for mutation in (lambda item: item.__setitem__('raw_document_sha256', '0' * 64),
                         lambda item: item['queries'][0]['result'].__setitem__('schema_version', True),
                         lambda item: item['queries'][0]['result'].__setitem__('anchors', {'u': 1})):
            bad = deepcopy(self.envelope['learning']['inequalities'])
            mutation(bad)
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                verify_logical_inequalities(self.raw, bad)

    def test_anchor_changes_do_not_change_the_graph_proof(self):
        """Actual colors keep their values; graph refutation does not normalize anchors."""
        raw = deepcopy(self.raw)
        raw['anchors']['u'] = 4
        learned = learn_logical_inequalities(raw)
        self.assertEqual(learned['queries'], self.envelope['learning']['inequalities']['queries'])
        self.assertNotEqual(learned['raw_document_sha256'],
                            self.envelope['learning']['inequalities']['raw_document_sha256'])
        envelope = solve_logical_neq(raw)
        self.assertEqual(envelope['run']['colors']['u'], 4)
        audit_logical_neq(raw, envelope)

    def test_extra_raw_oracle_anchor_is_rejected_even_with_valid_certificate(self):
        """Inferred v=u is not an actual initial commitment."""
        bad = deepcopy(self.audit)
        record = bad['oracle_records'][bad['initial_oracle_index']]
        raw = record['input']
        fixed = {0: 1, 4: 1}
        result = solve_exact(raw['n'], raw['edges'], fixed, node_limit=200000)
        record.update(input={**raw, 'anchors': [[0, 1], [4, 1]]}, result=result,
                      verification=verify_exact_result(raw['n'], raw['edges'], fixed, result))
        with self.assertRaisesRegex(AssertionError, 'commitment binding'):
            self.check(audit=bad)

    def test_oracle_graph_and_extra_logical_premises_are_rejected(self):
        """No learned NEQ or EQ is an exact-oracle input premise."""
        for mutation in (lambda item: item['input']['edges'].append([4, 5]),
                         lambda item: item['input'].__setitem__('different_names', [['v', 'w']]),
                         lambda item: item['input'].__setitem__('n', True)):
            bad = deepcopy(self.audit)
            mutation(bad['oracle_records'][0])
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                self.check(audit=bad)

    def test_phase_cannot_drop_a_persistent_logical_relation(self):
        """A locally valid replacement trace cannot alter the declared learned input."""
        bad = deepcopy(self.envelope)
        phase = bad['run']['phases'][1]
        phase['document'].pop('different_names')
        phase['outcome'] = propagate_logical_contacts(phase['document'])
        with self.assertRaisesRegex(AssertionError, 'trial assumptions'):
            audit_logical_neq(self.raw, bad)

    def test_logical_field_has_independent_shape_and_echo_validation(self):
        """A self-NEQ, unknown identity, unknown field or mismatched echo is invalid."""
        raw = {**small_document(), 'different_names': [['A', 'B']]}
        outcome = propagate_logical_contacts(raw)
        audit_logical_contacts(raw, outcome)
        for mutation in (lambda item: item.__setitem__('different_names', [['A', 'A']]),
                         lambda item: item.__setitem__('different_names', [['A', 'X']]),
                         lambda item: item.__setitem__('unexplained_field', [])):
            bad = deepcopy(raw)
            mutation(bad)
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                audit_logical_contacts(bad, outcome)
        bad = deepcopy(outcome)
        bad['different_names'] = []
        with self.assertRaisesRegex(AssertionError, 'NEQ echo'):
            audit_logical_contacts(raw, bad)

    def test_unknown_and_resource_stops_remain_separate_from_integrity(self):
        """UNKNOWN is neither safe nor UNSAT, and incomplete runs may be well audited."""
        audit = audit_logical_neq(self.small, self.small_envelope, node_limit=0)
        self.assertEqual(audit['commitment_counts']['unknown'], 1)
        check_logical_neq_artifacts(self.small, self.small_envelope, audit, {**RESOURCES, 'node_limit': 0})
        for field in ('decision_limit', 'probe_limit'):
            envelope = solve_logical_neq(self.small, **{field: 0})
            audit = audit_logical_neq(self.small, envelope)
            self.assertEqual(envelope['run']['status'], 'incomplete')
            check_logical_neq_artifacts(self.small, envelope, audit, {**RESOURCES, field: 0})
            envelope['run']['status'] = 'solved'
            with self.assertRaises(AssertionError):
                check_logical_neq_artifacts(self.small, envelope, audit, {**RESOURCES, field: 0})

    def test_false_saved_summary_or_budget_is_rejected(self):
        """Recomputed preservation and resource values bind saved measurements."""
        bad = deepcopy(self.audit)
        bad['full_enumeration']['initial_legal_assignments'] += 1
        with self.assertRaises(AssertionError):
            self.check(audit=bad)
        with self.assertRaises(AssertionError):
            self.check(resources={**RESOURCES, 'probe_limit': 512})

    def test_bridge_and_point_contact_do_not_create_neq(self):
        """Physical contact categories remain distinct even in the learner's inventory."""
        raw = {'sides': ['A', 'B'], 'lines': [{'id': 'bridge', 'left': 'A', 'right': 'A', 'kind': 'bridge'}],
               'point_contacts': [{'sides': ['A', 'B']}]}
        learned = learn_logical_inequalities(raw)
        self.assertEqual(learned['different_names'], [])
        self.assertEqual(learned['stats']['eligible_pairs'], 1)
        self.assertTrue(verify_logical_inequalities(raw, learned)['passed'])

    def test_raw_supplied_relations_and_domains_are_rejected(self):
        """Only independently learned logical premises may enter the new envelope."""
        for field, value in (('states', {'A': '3000'}), ('equal_names', [['A', 'B']]), ('different_names', [])):
            with self.subTest(field=field), self.assertRaises(AssertionError):
                audit_logical_neq({**self.small, field: value}, {})


if __name__ == '__main__':
    unittest.main()

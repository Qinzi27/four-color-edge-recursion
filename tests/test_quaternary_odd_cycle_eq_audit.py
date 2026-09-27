"""Odd-cycle-EQ evidence must stay separate from original exact constraints."""

from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.audit_lifted_bipyramid import lifted_document
from scripts.audit_quaternary_geometry import audit_bounded_contacts
from scripts.audit_quaternary_odd_cycle_eq import audit_odd_cycle_eq, check_odd_cycle_eq_artifacts
from scripts.exact_extendibility_oracle import solve_exact, verify_exact_result
from scripts.quaternary_bipyramid_inputs import base_drawing
from scripts.quaternary_contact_model import propagate_contacts
from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.quaternary_odd_cycle_eq_low_color import solve_odd_cycle_eq
from scripts.validate_global_restart import export_geometries


RESOURCES = {'decision_limit': 128, 'probe_limit': 512,
             'assignment_limit': 262144, 'node_limit': 200000}


def small_document():
    """A motif-free raw control requires one low-name commitment."""
    return {'sides': ['S0', 'S1'], 'lines': [
        {'id': 'E0', 'left': 'S0', 'right': 'S1', 'kind': 'separator'}],
        'anchors': {'S0': 1}}


def pentagonal_bipyramid():
    """A common C5 forces apex equality without any common triangle.

    This seven-vertex abstract fixture tests only the raw contact submodule;
    it does not claim a mother-line history or a particular drawing.
    """
    ring = ['B' + str(i) for i in range(5)]
    pairs = [(ring[i], ring[(i + 1) % 5]) for i in range(5)]
    pairs += [(apex, side) for apex in ('A', 'E') for side in ring]
    return {'sides': ['A', 'E', *ring], 'anchors': {'A': 1},
            'lines': [{'id': 'L' + str(i), 'left': a, 'right': b,
                       'kind': 'separator'} for i, (a, b) in enumerate(pairs)]}


class OddCycleEqAuditTests(unittest.TestCase):
    """Use existing fixtures only; do not select future geometric inputs."""

    @classmethod
    def setUpClass(cls):
        """Cache the known lifted diagnostic and a previously frozen real map."""
        cls.raw = lifted_document()
        cls.envelope = solve_odd_cycle_eq(cls.raw)
        cls.audit = audit_odd_cycle_eq(cls.raw, cls.envelope)
        cls.c5_raw = pentagonal_bipyramid()
        cls.c5_envelope = solve_odd_cycle_eq(cls.c5_raw)
        cls.c5_audit = audit_odd_cycle_eq(cls.c5_raw, cls.c5_envelope)
        cls.drawing = base_drawing()
        cls.geometry = export_geometries([{'key': 'bare', 'document': cls.drawing}])[0]['geometry']
        cls.adapted = adapt_exported_geometry(cls.geometry, anchors={'S0': 1}, drawing=cls.drawing)

    def test_c5_keeps_all_raw_colorings_without_adding_inferred_anchor(self):
        """The inferred E=1 is checked against raw solutions, not supplied to them."""
        envelope, audit = self.c5_envelope, self.c5_audit
        self.assertEqual(envelope['learning']['equal_names'], [['A', 'E']])
        self.assertEqual(len(envelope['learning']['certificates'][0]['cycle']), 5)
        self.assertEqual(envelope['run']['phases'][0]['outcome']['domains'][1], [1])
        self.assertEqual(audit['full_enumeration']['literal_assignments_checked'], 4 ** 6)
        # E must equal anchored A, leaving proper three-colorings of C5:
        # (3 - 1)^5 - (3 - 1) = 30 literal assignments with no symmetry quotient.
        self.assertEqual(audit['full_enumeration']['initial_legal_assignments'], 30)
        self.assertEqual(audit['commitment_counts']['unsafe'], 0)
        self.assertEqual(audit['commitment_counts']['unknown'], 0)
        self.assertEqual(envelope['run']['status'], 'solved')
        for record in audit['oracle_records']:
            self.assertEqual(set(record['input']), {'n', 'edges', 'anchors'})
            self.assertFalse(any(side == 1 for side, _ in record['input']['anchors']))
        checked = check_odd_cycle_eq_artifacts(self.c5_raw, envelope, audit, RESOURCES)
        self.assertEqual(checked['odd_cycle_eq_check']['certificate_count'], 1)
        self.assertTrue(checked['passed'])

    def test_c5_missing_or_false_cycle_rejected_before_oracle(self):
        """Non-triangle certificates must prove the full original common odd cycle."""
        for mutate in (
            lambda item: item['learning']['certificates'].clear(),
            lambda item: item['learning']['certificates'][0]['cycle'].pop(),
            lambda item: item['learning']['certificates'][0]['cycle'].__setitem__(0, 'A'),
            lambda item: item['learning']['equal_names'].clear(),
        ):
            bad = deepcopy(self.c5_envelope)
            mutate(bad)
            with self.subTest(mutate=mutate), \
                    patch('scripts.audit_quaternary_odd_cycle_eq.solve_exact',
                          side_effect=RuntimeError('oracle called')), \
                    self.assertRaises((AssertionError, ValueError)):
                audit_odd_cycle_eq(self.c5_raw, bad)
            with self.assertRaises((AssertionError, ValueError)):
                check_odd_cycle_eq_artifacts(self.c5_raw, bad, self.c5_audit, RESOURCES)

    def test_c5_valid_exact_certificate_cannot_include_inferred_singleton(self):
        """Even a true inferred E=1 is not an actual commitment at initialization."""
        audit = deepcopy(self.c5_audit)
        record = audit['oracle_records'][audit['initial_oracle_index']]
        n, edges, fixed = record['input']['n'], record['input']['edges'], {0: 1, 1: 1}
        evidence = solve_exact(n, edges, fixed, node_limit=RESOURCES['node_limit'])
        self.assertEqual(evidence['status'], 'sat')
        record.update(input={'n': n, 'edges': edges, 'anchors': [[0, 1], [1, 1]]},
                      result=evidence,
                      verification=verify_exact_result(n, edges, fixed, evidence))
        with self.assertRaisesRegex(AssertionError, 'commitment binding'):
            check_odd_cycle_eq_artifacts(self.c5_raw, self.c5_envelope, audit, RESOURCES)

    def test_known_diagnostic_is_fixed_without_adding_oracle_premises(self):
        """The known abstract error is repaired, with raw 216-solution coverage."""
        self.assertEqual(self.envelope['run']['status'], 'solved')
        self.assertEqual(self.envelope['run']['colors']['A'], 2)
        self.assertEqual(self.envelope['run']['colors']['E'], 2)
        self.assertEqual(self.audit['commitment_counts']['unsafe'], 0)
        self.assertEqual(self.audit['full_enumeration']['initial_legal_assignments'], 216)
        self.assertEqual(self.audit['full_enumeration']['literal_assignments_checked'], 262144)
        raw_edges = {tuple(sorted((self.raw['sides'].index(line['left']),
                                  self.raw['sides'].index(line['right'])))) for line in self.raw['lines']}
        for record in self.audit['oracle_records']:
            self.assertEqual(set(record['input']), {'n', 'edges', 'anchors'})
            self.assertEqual({tuple(pair) for pair in record['input']['edges']}, raw_edges)
        self.assertTrue(check_odd_cycle_eq_artifacts(self.raw, self.envelope, self.audit, RESOURCES)['passed'])

    def test_no_motif_keeps_empty_learning_and_raw_input_identical(self):
        """Absence of structural evidence adds no supplied equality field."""
        raw = small_document()
        result = solve_odd_cycle_eq(raw)
        audit = audit_odd_cycle_eq(raw, result)
        self.assertEqual(result['learning']['equal_names'], [])
        self.assertEqual(result['augmented_input'], raw)
        self.assertEqual(audit['commitment_counts']['safe'], 1)
        self.assertTrue(check_odd_cycle_eq_artifacts(raw, result, audit, RESOURCES)['passed'])

    def test_real_geometry_is_bound_to_raw_contacts(self):
        """The learned relation never replaces the original geometric adapter."""
        raw = self.adapted['contact_document']
        envelope = solve_odd_cycle_eq(raw, geometry=self.geometry)
        self.assertTrue(envelope['learning']['equal_names'])
        audit = audit_odd_cycle_eq(raw, envelope, geometry=self.geometry, adapted=self.adapted)
        self.assertTrue(check_odd_cycle_eq_artifacts(raw, envelope, audit, RESOURCES,
                        geometry=self.geometry, adapted=self.adapted)['passed'])
        bad_adapter = deepcopy(self.adapted)
        bad_adapter['contact_document'] = envelope['augmented_input']
        with self.assertRaisesRegex(AssertionError, 'adapter'):
            audit_odd_cycle_eq(raw, envelope, geometry=self.geometry, adapted=bad_adapter)

    def test_oracle_is_post_producer_and_receives_no_learned_relation(self):
        """No exact search is available while the producer constructs its run."""
        with patch('scripts.exact_extendibility_oracle.solve_exact', side_effect=AssertionError('early oracle')), \
                patch('scripts.audit_quaternary_odd_cycle_eq.solve_exact', side_effect=AssertionError('early oracle')), \
                patch('scripts.audit_quaternary_low_color.solve_exact', side_effect=AssertionError('early oracle')):
            envelope = solve_odd_cycle_eq(small_document())
        calls = []

        def inspect(n, edges, fixed, *, node_limit):
            """Record only the independent raw solver's public arguments."""
            calls.append((n, deepcopy(edges), deepcopy(fixed)))
            return solve_exact(n, edges, fixed, node_limit=node_limit)

        with patch('scripts.audit_quaternary_odd_cycle_eq.solve_exact', side_effect=inspect):
            audit_odd_cycle_eq(small_document(), envelope)
        self.assertEqual(calls, [(2, [(0, 1)], {0: 1}), (2, [(0, 1)], {0: 1, 1: 2})])

    def test_saved_checker_never_runs_producer_propagation_or_oracle_search(self):
        """Stored traces and witnesses suffice for independent artifact replay."""
        with patch('scripts.quaternary_odd_cycle_eq_low_color.solve_odd_cycle_eq', side_effect=AssertionError('producer')), \
                patch('scripts.quaternary_low_color.propagate_contacts', side_effect=AssertionError('propagation')), \
                patch('scripts.audit_quaternary_odd_cycle_eq.solve_exact', side_effect=AssertionError('search')), \
                patch('scripts.exact_extendibility_oracle.solve_exact', side_effect=AssertionError('search')):
            checked = check_odd_cycle_eq_artifacts(self.raw, self.envelope, self.audit, RESOURCES)
        self.assertEqual(checked['producer_runs'], 0)
        self.assertEqual(checked['oracle_searches'], 0)

    def test_forged_or_missing_learning_rejected_before_oracle(self):
        """Unproved equalities cannot enter via certificates or the augmentation."""
        for mutate in (
            lambda item: item['learning']['equal_names'].append(['Z', 'P']),
            lambda item: item['learning']['certificates'][0]['cycle'].__setitem__(0, 'Z'),
            lambda item: item['learning'].__setitem__('raw_document_sha256', '0' * 64),
            lambda item: item['augmented_input'].pop('equal_names'),
        ):
            bad = deepcopy(self.envelope)
            mutate(bad)
            with self.subTest(mutate=mutate), \
                    patch('scripts.audit_quaternary_odd_cycle_eq.solve_exact', side_effect=RuntimeError('oracle called')), \
                    self.assertRaises((AssertionError, ValueError)):
                audit_odd_cycle_eq(self.raw, bad)

    def test_phase_cannot_withdraw_a_certified_equality(self):
        """A locally valid new trace still cannot silently change EQ premises."""
        bad = deepcopy(self.envelope)
        phase = bad['run']['phases'][1]
        phase['document'].pop('equal_names')
        phase['outcome'] = propagate_contacts(phase['document'])
        with self.assertRaisesRegex(AssertionError, 'trial assumptions'):
            audit_odd_cycle_eq(self.raw, bad)
        saved = deepcopy(self.audit)
        saved['phase_audits'][1] = audit_bounded_contacts(phase['document'], phase['outcome'])
        with self.assertRaises(AssertionError):
            check_odd_cycle_eq_artifacts(self.raw, bad, saved, RESOURCES)

    def test_saved_oracle_graph_and_extra_input_premises_are_rejected(self):
        """Each certificate must be for exactly the original NEQ graph."""
        for mutate in (
            lambda row: row['input']['edges'].pop(),
            lambda row: row['input'].__setitem__('equal_names', [['A', 'E']]),
            lambda row: row['input'].__setitem__('n', True),
        ):
            bad = deepcopy(self.audit)
            mutate(bad['oracle_records'][0])
            with self.subTest(mutate=mutate), self.assertRaises(AssertionError):
                check_odd_cycle_eq_artifacts(self.raw, self.envelope, bad, RESOURCES)

    def test_valid_certificate_with_extra_anchor_still_fails_commitment_binding(self):
        """A valid solution to a stronger problem cannot certify the raw prefix."""
        raw = small_document()
        envelope = solve_odd_cycle_eq(raw)
        audit = audit_odd_cycle_eq(raw, envelope)
        fixed, edges = {0: 1, 1: 3}, [(0, 1)]
        evidence = solve_exact(2, edges, fixed, node_limit=RESOURCES['node_limit'])
        audit['oracle_records'][0] = {
            'input': {'n': 2, 'edges': [[0, 1]], 'anchors': [[0, 1], [1, 3]]},
            'result': evidence, 'verification': verify_exact_result(2, edges, fixed, evidence)}
        with self.assertRaisesRegex(AssertionError, 'commitment binding'):
            check_odd_cycle_eq_artifacts(raw, envelope, audit, RESOURCES)

    def test_saved_enumeration_counts_are_recomputed(self):
        """The replay verifies assignment coverage, not just a passed flag."""
        bad = deepcopy(self.audit)
        bad['full_enumeration']['initial_legal_assignments'] += 1
        with self.assertRaisesRegex(AssertionError, 'raw enumeration differs'):
            check_odd_cycle_eq_artifacts(self.raw, self.envelope, bad, RESOURCES)

    def test_saved_initial_phase_cannot_be_relabeled_as_trial(self):
        """The initial persistent state is not an uncommitted trial."""
        raw = small_document()
        envelope = solve_odd_cycle_eq(raw)
        audit = audit_odd_cycle_eq(raw, envelope)
        for kind in ('trial', 'unknown'):
            bad = deepcopy(envelope)
            bad['run']['phases'][0]['kind'] = kind
            with self.subTest(kind=kind), self.assertRaisesRegex(AssertionError, 'initial phase'):
                check_odd_cycle_eq_artifacts(raw, bad, audit, RESOURCES)

    def test_unknown_cannot_be_counted_as_safe(self):
        """A zero exact-search budget remains unknown even if enumeration runs."""
        raw = small_document()
        envelope = solve_odd_cycle_eq(raw)
        audit = audit_odd_cycle_eq(raw, envelope, node_limit=0)
        resources = {**RESOURCES, 'node_limit': 0}
        self.assertEqual(audit['commitment_counts']['unknown'], 1)
        self.assertEqual(audit['commitment_counts']['safe'], 0)
        self.assertEqual(audit['oracle_unknown'], 2)
        check_odd_cycle_eq_artifacts(raw, envelope, audit, resources)
        audit['commitment_counts'].update(unknown=0, safe=1)
        with self.assertRaisesRegex(AssertionError, 'commitment totals'):
            check_odd_cycle_eq_artifacts(raw, envelope, audit, resources)

    def test_old_real_rejection_preserves_raw_prefix_and_unknown_status(self):
        """Rejection removes a trial anchor, never a raw exact-solver solution."""
        path = Path(__file__).resolve().parents[1] / 'examples/quaternary-real-regressions-2026-09-21.json'
        case = json.loads(path.read_text(encoding='utf-8'))['cases'][0]
        geometry = export_geometries([{'key': 'old', 'document': case['drawing']}])[0]['geometry']
        adapted = adapt_exported_geometry(geometry, anchors=case['anchors'], drawing=case['drawing'])
        raw = adapted['contact_document']
        envelope = solve_odd_cycle_eq(raw, geometry=geometry, probe_limit=1)
        self.assertEqual(envelope['run']['events'][0]['kind'], 'reject')
        for node_limit in (0, RESOURCES['node_limit']):
            audit = audit_odd_cycle_eq(raw, envelope, geometry=geometry, adapted=adapted, node_limit=node_limit)
            resources = {**RESOURCES, 'probe_limit': 1, 'node_limit': node_limit}
            checked = check_odd_cycle_eq_artifacts(raw, envelope, audit, resources,
                                                 geometry=geometry, adapted=adapted)
            self.assertTrue(checked['passed'])
            step = audit['steps'][0]
            self.assertEqual(step['before_oracle_index'], step['after_oracle_index'])
            self.assertEqual(step['extendibility'], 'refuted')
            self.assertEqual(audit['rejection_counts'],
                             {'exact_unsat': int(node_limit > 0), 'unknown': int(node_limit == 0)})

    def test_limits_are_inclusive_and_resource_stops_remain_incomplete(self):
        """Exhaustive coverage thresholds and production limits are bound."""
        raw = small_document()
        for limit in (3, 4):
            envelope = solve_odd_cycle_eq(raw)
            audit = audit_odd_cycle_eq(raw, envelope, assignment_limit=limit)
            self.assertEqual(audit['full_enumeration']['status'], 'run' if limit == 4 else 'not_run')
            check_odd_cycle_eq_artifacts(raw, envelope, audit, {**RESOURCES, 'assignment_limit': limit})
        for field in ('decision_limit', 'probe_limit'):
            envelope = solve_odd_cycle_eq(raw, **{field: 0})
            audit = audit_odd_cycle_eq(raw, envelope)
            resources = {**RESOURCES, field: 0}
            self.assertEqual(envelope['run']['status'], 'incomplete')
            check_odd_cycle_eq_artifacts(raw, envelope, audit, resources)
            envelope['run']['status'] = 'solved'
            with self.assertRaisesRegex((AssertionError, ValueError), 'resource stop mislabeled'):
                check_odd_cycle_eq_artifacts(raw, envelope, audit, resources)

    def test_original_external_states_and_eq_are_rejected(self):
        """This version does not admit caller-imposed candidate sets or EQ."""
        for field, value in (('states', {'S1': '0111'}), ('equal_names', [['S0', 'S1']])):
            raw = {**small_document(), field: value}
            with self.assertRaisesRegex(AssertionError, 'states/EQ unsupported'):
                audit_odd_cycle_eq(raw, {})


if __name__ == '__main__':
    unittest.main()

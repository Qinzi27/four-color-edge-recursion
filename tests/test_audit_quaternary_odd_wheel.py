"""End-to-end certificate, raw-oracle and state-transition audit controls."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts.audit_quaternary_odd_wheel import audit_odd_wheel, check_odd_wheel_artifacts
from scripts.audit_quaternary_low_color import _preserved
from scripts.exact_extendibility_oracle import solve_exact, verify_exact_result
from scripts.quaternary_bipyramid_inputs import base_drawing
from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.quaternary_logical_neq_low_color import solve_logical_neq
from scripts.quaternary_odd_wheel_low_color import solve_odd_wheel
from scripts.validate_global_restart import export_geometries
from tests.test_check_quaternary_odd_wheel import wheel_document


RESOURCES = {'decision_limit': 128, 'probe_limit': 8192,
             'assignment_limit': 262144, 'node_limit': 200000}


def conditional_wheel_document():
    """An abstract guarded-choice fixture, with no claimed plane realization.

    Two anchors equal 1. Choosing a third key equal to 1 confines every wheel
    vertex to 2,3,4. Each key touches just its assigned subset of the wheel.
    """
    raw = wheel_document(restricted=False)
    raw['sides'] = ['x', 'y', 'z'] + raw['sides']
    raw['anchors'] = {'x': 1, 'y': 1}
    for index, side in enumerate(['hub', 'r0', 'r1', 'r2', 'r3', 'r4']):
        raw['lines'].append({'id': f'a{index}', 'left': ['x', 'y', 'z'][index % 3],
                             'right': side, 'kind': 'separator'})
    return raw


class OddWheelAuditTests(unittest.TestCase):
    """A wheel-based rejection must have independently verified raw evidence."""

    @classmethod
    def setUpClass(cls):
        cls.raw = conditional_wheel_document()
        cls.envelope = solve_odd_wheel(cls.raw)
        cls.audit = audit_odd_wheel(cls.raw, cls.envelope)
        cls.small = {'sides': ['A', 'B'], 'anchors': {'A': 1},
                     'lines': [{'id': 'E', 'left': 'A', 'right': 'B', 'kind': 'separator'}]}
        cls.small_envelope = solve_odd_wheel(cls.small)
        cls.small_audit = audit_odd_wheel(cls.small, cls.small_envelope)

    def check(self, envelope=None, audit=None, resources=None):
        return check_odd_wheel_artifacts(self.raw, envelope or self.envelope,
                                        audit or self.audit, resources or RESOURCES)

    def test_new_rule_rejects_a_real_low_color_trial_then_completes(self):
        old = solve_logical_neq(self.raw)
        self.assertEqual(old['run']['events'][0]['kind'], 'commit')
        self.assertEqual(old['run']['status'], 'conflict')
        event = self.envelope['run']['events'][0]
        self.assertEqual((event['kind'], event['side'], event['symbol']), ('reject', 'z', 1))
        phase = self.envelope['run']['phases'][event['trial_phase']]
        self.assertEqual(phase['outcome']['base_status'], 'underdetermined')
        self.assertIsNotNone(phase['outcome']['wheel_check']['certificate'])
        self.assertEqual(self.envelope['run']['status'], 'solved')
        self.assertEqual(self.audit['commitment_counts']['unsafe'], 0)
        self.assertEqual(self.audit['rejection_counts'], {'exact_unsat': 1, 'unknown': 0})
        self.assertTrue(self.check()['passed'])

    def test_rejected_trial_has_raw_unsat_and_post_rejection_keeps_raw_sat(self):
        step = self.audit['steps'][0]
        records = self.audit['oracle_records']
        self.assertEqual(records[step['before_oracle_index']]['result']['status'], 'sat')
        self.assertEqual(records[step['trial_oracle_index']]['result']['status'], 'unsat')
        self.assertEqual(records[step['after_oracle_index']]['result']['status'], 'sat')
        self.assertEqual(records[step['after_oracle_index']]['input']['anchors'], [[0, 1], [1, 1]])
        phase = self.envelope['run']['phases'][step['after_phase']]
        self.assertNotIn('z', phase['document']['anchors'])
        self.assertIn('z', phase['document']['states'])

    def test_saved_replay_uses_no_producer_detector_propagation_or_search(self):
        with patch('scripts.quaternary_odd_wheel_low_color.solve_odd_wheel', side_effect=RuntimeError('producer')), \
                patch('scripts.quaternary_odd_wheel_contacts.propagate_wheel_contacts', side_effect=RuntimeError('propagate')), \
                patch('scripts.quaternary_odd_wheel.find_odd_wheel', side_effect=RuntimeError('detector')), \
                patch('scripts.audit_quaternary_odd_wheel.solve_exact', side_effect=RuntimeError('search')):
            checked = self.check()
        self.assertEqual(checked['producer_runs'], 0)
        self.assertEqual(checked['oracle_searches'], 0)

    def test_false_certificate_or_omitted_certificate_fails_before_exact_search(self):
        for value in (None, {'center': 'z', 'rim': ['r0', 'r1', 'r2'], 'excluded_color': 1}):
            altered = deepcopy(self.envelope)
            altered['run']['phases'][1]['outcome']['wheel_check']['certificate'] = value
            with patch('scripts.audit_quaternary_odd_wheel.solve_exact', side_effect=RuntimeError('search')), \
                    self.assertRaises(AssertionError):
                audit_odd_wheel(self.raw, altered)

    def test_wheel_status_cannot_change_without_trace_and_certificate(self):
        altered = deepcopy(self.envelope)
        altered['run']['phases'][1]['outcome']['status'] = 'underdetermined'
        with self.assertRaisesRegex(AssertionError, 'wheel status'):
            audit_odd_wheel(self.raw, altered)

    def test_rejected_trial_cannot_be_committed_or_retained_as_an_anchor(self):
        for mutate in (lambda item: item['run']['events'][0].__setitem__('kind', 'commit'),
                       lambda item: item['run']['phases'][2]['document']['anchors'].__setitem__('z', 1)):
            altered = deepcopy(self.envelope)
            mutate(altered)
            with self.assertRaises((AssertionError, ValueError)):
                self.check(envelope=altered)

    def test_wheel_domain_premises_cannot_enter_raw_oracle(self):
        altered = deepcopy(self.audit)
        record = altered['oracle_records'][altered['initial_oracle_index']]
        raw = record['input']
        fixed = {0: 1, 1: 1, 2: 3}
        proof = solve_exact(raw['n'], raw['edges'], fixed, node_limit=200000)
        record.update(input={**raw, 'anchors': [[i, value] for i, value in sorted(fixed.items())]},
                      result=proof, verification=verify_exact_result(raw['n'], raw['edges'], fixed, proof))
        with self.assertRaisesRegex(AssertionError, 'commitment binding'):
            self.check(audit=altered)
        altered = deepcopy(self.audit)
        altered['oracle_records'][0]['input']['wheel_certificate'] = self.envelope['run']['phases'][1]['outcome']['wheel_check']
        with self.assertRaisesRegex(AssertionError, 'extra oracle'):
            self.check(audit=altered)

    def test_conflict_status_rejects_even_an_unchanged_sat_matrix(self):
        # A status-only wheel conflict must not evade the inherited preservation
        # check merely because it leaves every domain and pair bit untouched.
        outcome = deepcopy(self.small_envelope['run']['phases'][0]['outcome'])
        outcome['status'] = 'conflict'
        with self.assertRaisesRegex(AssertionError, 'raw complete solution'):
            _preserved(outcome, [[1, 2]])

    def test_saved_phase_summary_and_certificate_are_bound(self):
        altered = deepcopy(self.audit)
        altered['phase_audits'][1]['wheel_check']['found'] = False
        with self.assertRaises(AssertionError):
            self.check(audit=altered)
        altered = deepcopy(self.audit)
        altered['full_enumeration']['initial_legal_assignments'] += 1
        with self.assertRaises(AssertionError):
            self.check(audit=altered)

    def test_unknown_exact_queries_are_never_declared_safe_or_unsat(self):
        audit = audit_odd_wheel(self.raw, self.envelope, node_limit=0)
        self.assertEqual(audit['commitment_counts']['safe'], 0)
        self.assertGreater(audit['commitment_counts']['unknown'], 0)
        self.assertEqual(audit['rejection_counts'], {'exact_unsat': 0, 'unknown': 1})
        self.check(audit=audit, resources={**RESOURCES, 'node_limit': 0})

    def test_resource_stop_remains_incomplete_and_replayable(self):
        for field in ('decision_limit', 'probe_limit'):
            envelope = solve_odd_wheel(self.small, **{field: 0})
            audit = audit_odd_wheel(self.small, envelope)
            self.assertEqual(envelope['run']['status'], 'incomplete')
            check_odd_wheel_artifacts(self.small, envelope, audit, {**RESOURCES, field: 0})

    def test_geometric_scheduler_and_adapter_still_bind_raw_input(self):
        drawing = base_drawing()
        geometry = export_geometries([{'key': 'wheel-unit', 'document': drawing}])[0]['geometry']
        adapted = adapt_exported_geometry(geometry, anchors={'S0': 1}, drawing=drawing)
        raw = adapted['contact_document']
        envelope = solve_odd_wheel(raw, geometry=geometry)
        audit = audit_odd_wheel(raw, envelope, geometry=geometry, adapted=adapted)
        self.assertTrue(check_odd_wheel_artifacts(raw, envelope, audit, RESOURCES,
                                                 geometry=geometry, adapted=adapted)['passed'])
        self.assertEqual(envelope['augmented_input']['lines'], raw['lines'])

    def test_supplied_raw_states_relations_and_old_policies_are_rejected(self):
        for field, value in (('states', {'x': '3000'}), ('equal_names', [['x', 'y']]),
                             ('different_names', [])):
            with self.assertRaises(AssertionError):
                audit_odd_wheel({**self.raw, field: value}, {})
        altered = deepcopy(self.envelope)
        altered['policy'] = 'quaternary-low-color-logical-neq-v1'
        with self.assertRaises(AssertionError):
            audit_odd_wheel(self.raw, altered)


if __name__ == '__main__':
    unittest.main()

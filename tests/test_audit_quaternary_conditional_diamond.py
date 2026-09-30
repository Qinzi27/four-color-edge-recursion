"""End-to-end certificate, raw-oracle and state-transition audit controls."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts.audit_quaternary_conditional_diamond import audit_conditional_diamond, check_conditional_diamond_artifacts
from scripts.audit_quaternary_low_color import _preserved
from scripts.exact_extendibility_oracle import solve_exact, verify_exact_result
from scripts.quaternary_bipyramid_inputs import base_drawing
from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.quaternary_logical_neq_low_color import solve_logical_neq
from scripts.quaternary_conditional_diamond_low_color import solve_conditional_diamond
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


def conditional_diamond_document():
    """A raw-edge full-producer fixture; no plane realization is claimed.

    The common triangle C-D-E forces U=X in four colors, while X-V proves
    U differs from V. Three independent anchors restrict U,V,A. Choosing
    P=1 restricts B too, and the three-color diamond around A-B forces U=V.
    Splitting the three anchors is essential: their equality is conditional,
    not a raw graph theorem that would forbid P's low color in preprocessing.
    """
    sides = ['H', 'J', 'K', 'P', 'U', 'V', 'A', 'B', 'X', 'C', 'D', 'E']
    edges = [('A', 'B'), ('A', 'U'), ('A', 'V'), ('B', 'U'), ('B', 'V'),
             ('H', 'U'), ('J', 'V'), ('K', 'A'), ('P', 'B'),
             ('C', 'D'), ('D', 'E'), ('E', 'C'), ('X', 'V')]
    edges.extend((side, color) for side in ['U', 'X'] for color in ['C', 'D', 'E'])
    return {'sides': sides, 'anchors': {'H': 1, 'J': 1, 'K': 1},
            'lines': [{'id': str(i), 'left': a, 'right': b, 'kind': 'separator'}
                      for i, (a, b) in enumerate(edges)]}


class ConditionalDiamondAuditTests(unittest.TestCase):
    """A wheel-based rejection must have independently verified raw evidence."""

    @classmethod
    def setUpClass(cls):
        cls.raw = conditional_wheel_document()
        cls.envelope = solve_conditional_diamond(cls.raw)
        cls.audit = audit_conditional_diamond(cls.raw, cls.envelope)
        cls.small = {'sides': ['A', 'B'], 'anchors': {'A': 1},
                     'lines': [{'id': 'E', 'left': 'A', 'right': 'B', 'kind': 'separator'}]}
        cls.small_envelope = solve_conditional_diamond(cls.small)
        cls.small_audit = audit_conditional_diamond(cls.small, cls.small_envelope)

    def check(self, envelope=None, audit=None, resources=None):
        return check_conditional_diamond_artifacts(self.raw, envelope or self.envelope,
                                        audit or self.audit, resources or RESOURCES)

    def test_inherited_wheel_rejection_still_completes(self):
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
        with patch('scripts.quaternary_conditional_diamond_low_color.solve_conditional_diamond', side_effect=RuntimeError('producer')), \
                patch('scripts.quaternary_conditional_diamond_contacts.propagate_diamond_contacts', side_effect=RuntimeError('propagate')), \
                patch('scripts.quaternary_conditional_diamond.find_conditional_diamonds', side_effect=RuntimeError('detector')), \
                patch('scripts.audit_quaternary_conditional_diamond.solve_exact', side_effect=RuntimeError('search')):
            checked = self.check()
        self.assertEqual(checked['producer_runs'], 0)
        self.assertEqual(checked['oracle_searches'], 0)

    def test_false_certificate_or_omitted_certificate_fails_before_exact_search(self):
        for value in (None, {'center': 'z', 'rim': ['r0', 'r1', 'r2'], 'excluded_color': 1}):
            altered = deepcopy(self.envelope)
            altered['run']['phases'][1]['outcome']['conditional_eq']['rounds'][0]['outcome']['wheel_check']['certificate'] = value
            with patch('scripts.audit_quaternary_conditional_diamond.solve_exact', side_effect=RuntimeError('search')), \
                    self.assertRaises(AssertionError):
                audit_conditional_diamond(self.raw, altered)

    def test_wheel_status_cannot_change_without_trace_and_certificate(self):
        altered = deepcopy(self.envelope)
        altered['run']['phases'][1]['outcome']['status'] = 'underdetermined'
        with self.assertRaisesRegex(AssertionError, 'projection'):
            audit_conditional_diamond(self.raw, altered)

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
        altered['oracle_records'][0]['input']['wheel_certificate'] = self.envelope['run']['phases'][1]['outcome']['conditional_eq']['rounds'][0]['outcome']['wheel_check']
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
        altered['phase_audits'][1]['conditional_eq']['rounds'][0]['wheel_audit']['wheel_check']['found'] = False
        with self.assertRaises(AssertionError):
            self.check(audit=altered)
        altered = deepcopy(self.audit)
        altered['full_enumeration']['initial_legal_assignments'] += 1
        with self.assertRaises(AssertionError):
            self.check(audit=altered)

    def test_unknown_exact_queries_are_never_declared_safe_or_unsat(self):
        audit = audit_conditional_diamond(self.raw, self.envelope, node_limit=0)
        self.assertEqual(audit['commitment_counts']['safe'], 0)
        self.assertGreater(audit['commitment_counts']['unknown'], 0)
        self.assertEqual(audit['rejection_counts'], {'exact_unsat': 0, 'unknown': 1})
        self.check(audit=audit, resources={**RESOURCES, 'node_limit': 0})

    def test_resource_stop_remains_incomplete_and_replayable(self):
        for field in ('decision_limit', 'probe_limit'):
            envelope = solve_conditional_diamond(self.small, **{field: 0})
            audit = audit_conditional_diamond(self.small, envelope)
            self.assertEqual(envelope['run']['status'], 'incomplete')
            check_conditional_diamond_artifacts(self.small, envelope, audit, {**RESOURCES, field: 0})

    def test_geometric_scheduler_and_adapter_still_bind_raw_input(self):
        drawing = base_drawing()
        geometry = export_geometries([{'key': 'wheel-unit', 'document': drawing}])[0]['geometry']
        adapted = adapt_exported_geometry(geometry, anchors={'S0': 1}, drawing=drawing)
        raw = adapted['contact_document']
        envelope = solve_conditional_diamond(raw, geometry=geometry)
        audit = audit_conditional_diamond(raw, envelope, geometry=geometry, adapted=adapted)
        self.assertTrue(check_conditional_diamond_artifacts(raw, envelope, audit, RESOURCES,
                                                 geometry=geometry, adapted=adapted)['passed'])
        self.assertEqual(envelope['augmented_input']['lines'], raw['lines'])

    def test_supplied_raw_states_relations_and_old_policies_are_rejected(self):
        for field, value in (('states', {'x': '3000'}), ('equal_names', [['x', 'y']]),
                             ('different_names', [])):
            with self.assertRaises(AssertionError):
                audit_conditional_diamond({**self.raw, field: value}, {})
        altered = deepcopy(self.envelope)
        altered['policy'] = 'quaternary-low-color-logical-neq-v1'
        with self.assertRaises(AssertionError):
            audit_conditional_diamond(self.raw, altered)


class FullConditionalDiamondAuditTests(unittest.TestCase):
    """An actual conditional-EQ rejection survives the complete outer audit."""

    @classmethod
    def setUpClass(cls):
        cls.raw = conditional_diamond_document()
        cls.envelope = solve_conditional_diamond(cls.raw)
        cls.audit = audit_conditional_diamond(cls.raw, cls.envelope)

    def check(self, envelope=None, audit=None, resources=None):
        return check_conditional_diamond_artifacts(self.raw, envelope or self.envelope,
                                                   audit or self.audit, resources or RESOURCES)

    def test_real_diamond_rejects_before_old_version_unsafe_commitment(self):
        old = solve_odd_wheel(self.raw)
        self.assertEqual(old['run']['events'][0]['kind'], 'commit')
        self.assertEqual(old['run']['status'], 'conflict')
        run = self.envelope['run']
        self.assertEqual((run['events'][0]['kind'], run['events'][0]['side'],
                          run['events'][0]['symbol']), ('reject', 'P', 1))
        trial = run['phases'][run['events'][0]['trial_phase']]['outcome']
        self.assertEqual(trial['conditional_eq']['equal_names'], [['U', 'V']])
        self.assertEqual([r['outcome']['status'] for r in trial['conditional_eq']['rounds']],
                         ['underdetermined', 'conflict'])
        self.assertEqual(run['status'], 'solved')
        self.assertEqual(self.audit['rejection_counts'], {'exact_unsat': 1, 'unknown': 0})
        self.assertEqual(self.audit['commitment_counts']['unsafe'], 0)
        self.assertEqual(self.audit['full_enumeration']['status'], 'run')
        self.assertTrue(self.check()['passed'])

    def test_rejected_trial_local_eq_does_not_leak_to_persistent_phase(self):
        run = self.envelope['run']
        event = run['events'][0]
        next_document = run['phases'][event['after_phase']]['document']
        self.assertNotIn(['U', 'V'], next_document.get('equal_names', []))
        self.assertNotIn('P', next_document['anchors'])
        self.assertIn('P', next_document['states'])
        altered = deepcopy(self.envelope)
        altered['run']['phases'][event['after_phase']]['document'].setdefault(
            'equal_names', []).append(['U', 'V'])
        with self.assertRaises(AssertionError):
            self.check(envelope=altered)

    def test_every_internal_round_preserves_raw_solutions_and_counts_its_trace(self):
        phases = self.envelope['run']['phases']
        expected_steps = sum(len(row['outcome']['trace']) for phase in phases
                             for row in phase['outcome']['conditional_eq']['rounds'])
        self.assertEqual(self.audit['trace_steps_checked'], expected_steps)
        self.assertEqual(self.audit['full_enumeration']['phase_checks'], len(phases))
        self.assertGreater(self.audit['full_enumeration']['legal_assignments_preserved'], 0)

    def test_saved_replay_has_no_search_or_production(self):
        with patch('scripts.audit_quaternary_conditional_diamond.solve_exact',
                   side_effect=RuntimeError('search')), patch(
                       'scripts.quaternary_conditional_diamond_contacts.propagate_diamond_contacts',
                       side_effect=RuntimeError('production')), patch(
                           'scripts.quaternary_conditional_diamond.find_conditional_diamonds',
                           side_effect=RuntimeError('detector')):
            self.assertEqual(self.check()['oracle_searches'], 0)

    def test_counterfeit_eq_rejected_before_oracle_query(self):
        altered = deepcopy(self.envelope)
        proof = altered['run']['phases'][1]['outcome']['conditional_eq']['rounds'][0]['diamond_check']
        proof['certificates'][0]['excluded_color'] = 2
        with patch('scripts.audit_quaternary_conditional_diamond.solve_exact',
                   side_effect=RuntimeError('search')), self.assertRaises(AssertionError):
            audit_conditional_diamond(self.raw, altered)

    def test_conditional_eq_never_enters_oracle_premises(self):
        altered = deepcopy(self.audit)
        altered['oracle_records'][0]['input']['equal_names'] = [['U', 'V']]
        with self.assertRaisesRegex(AssertionError, 'extra oracle'):
            self.check(audit=altered)
        # Bind exact raw premises to original anchors and actual choices, not
        # inferred singleton domains or a rejected P=1 trial's local EQ.
        step = self.audit['steps'][0]
        records = self.audit['oracle_records']
        self.assertEqual([records[step[k]]['result']['status'] for k in
                          ['before_oracle_index', 'trial_oracle_index', 'after_oracle_index']],
                         ['sat', 'unsat', 'sat'])

    def test_unknown_trial_remains_unknown_with_valid_structural_rejection(self):
        audit = audit_conditional_diamond(self.raw, self.envelope, assignment_limit=0, node_limit=0)
        self.assertEqual(audit['rejection_counts'], {'exact_unsat': 0, 'unknown': 1})
        self.assertEqual(audit['commitment_counts']['safe'], 0)
        self.assertGreater(audit['commitment_counts']['unknown'], 0)
        self.check(audit=audit, resources={**RESOURCES, 'assignment_limit': 0, 'node_limit': 0})


if __name__ == '__main__':
    unittest.main()

"""Whole-producer rejection, raw-oracle separation and nested preservation tests."""

from copy import deepcopy
from itertools import combinations
import unittest
from unittest.mock import patch

from scripts.audit_quaternary_triangle_saturation import (
    _preserved_all_rounds, audit_triangle_saturation, check_triangle_saturation_artifacts,
)
from scripts.exact_extendibility_oracle import solve_exact, verify_exact_result
from scripts.quaternary_conditional_diamond_low_color import solve_conditional_diamond
from scripts.quaternary_triangle_saturation_low_color import solve_triangle_saturation


RESOURCES = {'decision_limit': 128, 'probe_limit': 8192,
             'assignment_limit': 262144, 'node_limit': 200000}


def raw_saturation_trial_document():
    """Two joined K4s produce an actual low-color rejection; abstract only.

    H=J=1 restrict A,B,D,E. P=1 would additionally restrict C,F. Both
    triangles would fill 2,3,4 and force adjacent T,U to 1, a contradiction.
    P=2 has a complete raw coloring. No plane realization is claimed here.
    """
    sides = ['H', 'J', 'P', 'T', 'U', 'A', 'B', 'C', 'D', 'E', 'F']
    edges = list(combinations(['T', 'A', 'B', 'C'], 2))
    edges += list(combinations(['U', 'D', 'E', 'F'], 2))
    edges += [('T', 'U'), ('H', 'A'), ('J', 'B'), ('H', 'D'), ('J', 'E'),
              ('P', 'C'), ('P', 'F')]
    return {'sides': sides, 'anchors': {'H': 1, 'J': 1},
            'lines': [{'id': str(i), 'left': a, 'right': b, 'kind': 'separator'}
                      for i, (a, b) in enumerate(edges)]}


class TriangleSaturationAuditTests(unittest.TestCase):
    """Production choices and every nested inference have independent evidence."""

    @classmethod
    def setUpClass(cls):
        cls.raw = raw_saturation_trial_document()
        cls.envelope = solve_triangle_saturation(cls.raw)
        cls.audit = audit_triangle_saturation(cls.raw, cls.envelope)
        cls.small = {'sides': ['A', 'B'], 'anchors': {'A': 1},
                     'lines': [{'id': 'E', 'left': 'A', 'right': 'B', 'kind': 'separator'}]}
        cls.small_envelope = solve_triangle_saturation(cls.small)
        cls.small_audit = audit_triangle_saturation(cls.small, cls.small_envelope)

    def check(self, envelope=None, audit=None, resources=None):
        """Replay saved literal proofs without executing the producer or oracle."""
        return check_triangle_saturation_artifacts(self.raw,
            self.envelope if envelope is None else envelope,
            self.audit if audit is None else audit,
            RESOURCES if resources is None else resources)

    def test_actual_low_color_rejection_precedes_next_color_and_completes(self):
        old = solve_conditional_diamond(self.raw)
        self.assertEqual(old['run']['events'][0]['kind'], 'commit')
        self.assertEqual(old['run']['events'][0]['symbol'], 1)
        run = self.envelope['run']
        self.assertEqual([(e['kind'], e['side'], e['symbol']) for e in run['events'][:2]],
                         [('reject', 'P', 1), ('commit', 'P', 2)])
        trial = run['phases'][run['events'][0]['trial_phase']]['outcome']
        self.assertEqual(trial['triangle_saturation']['rounds'][0]['outcome']['status'], 'underdetermined')
        self.assertEqual(trial['status'], 'conflict')
        self.assertTrue(trial['triangle_saturation']['removed_candidates'])
        self.assertEqual(run['status'], 'solved')
        self.assertEqual(self.audit['commitment_counts']['unsafe'], 0)
        self.assertEqual(self.audit['rejection_counts'], {'exact_unsat': 1, 'unknown': 0})
        self.assertTrue(self.check()['passed'])

    def test_before_and_after_rejection_are_raw_sat_with_raw_unsat_trial(self):
        step = self.audit['steps'][0]
        records = self.audit['oracle_records']
        self.assertEqual([records[step[k]]['result']['status'] for k in
            ('before_oracle_index', 'trial_oracle_index', 'after_oracle_index')], ['sat', 'unsat', 'sat'])
        self.assertEqual(records[step['after_oracle_index']]['input']['anchors'], [[0, 1], [1, 1]])
        next_document = self.envelope['run']['phases'][step['after_phase']]['document']
        self.assertNotIn('P', next_document['anchors'])
        self.assertEqual(next_document['states'], {'P': '0111'})
        self.assertFalse(next_document.get('equal_names'))

    def test_trial_restrictions_and_eq_cannot_leak_to_persistent_document(self):
        step = self.audit['steps'][0]
        for mutate in (lambda d: d['anchors'].__setitem__('P', 1),
                       lambda d: d['states'].__setitem__('T', '2000'),
                       lambda d: d.setdefault('equal_names', []).append(['T', 'U'])):
            altered = deepcopy(self.envelope)
            mutate(altered['run']['phases'][step['after_phase']]['document'])
            with self.assertRaises(AssertionError):
                self.check(envelope=altered)

    def test_saved_replay_has_no_search_detector_or_producer(self):
        with patch('scripts.audit_quaternary_triangle_saturation.solve_exact',
                   side_effect=RuntimeError('search')), patch(
                       'scripts.quaternary_triangle_saturation_low_color.solve_triangle_saturation',
                       side_effect=RuntimeError('producer')), patch(
                           'scripts.quaternary_triangle_saturation_contacts.propagate_saturation_contacts',
                           side_effect=RuntimeError('propagation')), patch(
                               'scripts.quaternary_triangle_saturation.find_triangle_saturations',
                               side_effect=RuntimeError('detector')):
            result = self.check()
        self.assertEqual(result['producer_runs'], 0)
        self.assertEqual(result['oracle_searches'], 0)

    def test_counterfeit_triangle_is_rejected_before_oracle_search(self):
        altered = deepcopy(self.envelope)
        trial = altered['run']['phases'][altered['run']['events'][0]['trial_phase']]['outcome']
        certificate = trial['triangle_saturation']['rounds'][0]['triangle_check']['certificates'][0]
        certificate['excluded_color'] = 2
        with patch('scripts.audit_quaternary_triangle_saturation.solve_exact',
                   side_effect=RuntimeError('search')), self.assertRaises(AssertionError):
            audit_triangle_saturation(self.raw, altered)

    def test_rejection_cannot_be_mislabeled_commit(self):
        altered = deepcopy(self.envelope)
        altered['run']['events'][0]['kind'] = 'commit'
        with self.assertRaises((AssertionError, ValueError)):
            self.check(envelope=altered)

    def test_candidate_domains_eq_or_triangle_proofs_never_enter_raw_oracle(self):
        for key, value in [('states', {'T': '2000'}), ('equal_names', [['T', 'U']]),
                           ('domains', [[1]]), ('triangle_saturation', {'trusted': True})]:
            altered = deepcopy(self.audit)
            altered['oracle_records'][0]['input'][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(AssertionError, 'extra oracle'):
                self.check(audit=altered)

    def test_valid_exact_proof_with_extra_inferred_anchor_is_rejected(self):
        altered = deepcopy(self.audit)
        record = altered['oracle_records'][altered['initial_oracle_index']]
        raw = record['input']
        fixed = {0: 1, 1: 1, 3: 1}
        proof = solve_exact(raw['n'], raw['edges'], fixed, node_limit=200000)
        record.update(input={**raw, 'anchors': [[i, v] for i, v in sorted(fixed.items())]},
                      result=proof, verification=verify_exact_result(raw['n'], raw['edges'], fixed, proof))
        with self.assertRaisesRegex(AssertionError, 'commitment binding'):
            self.check(audit=altered)

    def test_saved_audit_trace_and_enumeration_counts_are_bound(self):
        for mutate in (lambda a: a['phase_audits'][0]['triangle_saturation'].__setitem__('round_count', 0),
                       lambda a: a.__setitem__('trace_steps_checked', 0),
                       lambda a: a['full_enumeration'].__setitem__('initial_legal_assignments', 0)):
            altered = deepcopy(self.audit)
            mutate(altered)
            with self.assertRaises(AssertionError):
                self.check(audit=altered)

    def test_each_outer_and_inner_saved_outcome_preserves_the_raw_witness(self):
        original = self.small_envelope['run']['phases'][0]['outcome']
        for level in ('top', 'diamond', 'wheel'):
            outcome = deepcopy(original)
            selected = outcome
            if level != 'top':
                selected = selected['triangle_saturation']['rounds'][0]['outcome']
            if level == 'wheel':
                selected = selected['conditional_eq']['rounds'][0]['outcome']
            selected['status'] = 'conflict'
            with self.subTest(level=level), self.assertRaisesRegex(AssertionError, 'raw complete solution'):
                _preserved_all_rounds(outcome, [[1, 2]])

    def test_trace_work_sums_every_nested_wheel_round(self):
        phases = self.envelope['run']['phases']
        expected = sum(len(inner['outcome']['trace']) for phase in phases
                       for outer in phase['outcome']['triangle_saturation']['rounds']
                       for inner in outer['outcome']['conditional_eq']['rounds'])
        self.assertEqual(self.audit['trace_steps_checked'], expected)
        self.assertEqual(self.audit['full_enumeration']['phase_checks'], len(phases))
        self.assertGreater(self.audit['full_enumeration']['legal_assignments_preserved'], 0)

    def test_oracle_resource_unknown_never_becomes_safe_or_unsat(self):
        audit = audit_triangle_saturation(self.raw, self.envelope, assignment_limit=0, node_limit=0)
        self.assertEqual(audit['rejection_counts'], {'exact_unsat': 0, 'unknown': 1})
        self.assertEqual(audit['commitment_counts']['safe'], 0)
        self.assertGreater(audit['commitment_counts']['unknown'], 0)
        self.check(audit=audit, resources={**RESOURCES, 'assignment_limit': 0, 'node_limit': 0})

    def test_zero_producer_budget_remains_incomplete_with_saved_replay(self):
        for name in ('decision_limit', 'probe_limit'):
            envelope = solve_triangle_saturation(self.raw, **{name: 0})
            audit = audit_triangle_saturation(self.raw, envelope)
            self.assertEqual(envelope['run']['status'], 'incomplete')
            self.assertEqual(envelope['run']['events'], [])
            self.check(envelope, audit, {**RESOURCES, name: 0})


if __name__ == '__main__':
    unittest.main()

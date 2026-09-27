"""Candidate support must not be confused with actual commitment safety."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts.audit_lifted_bipyramid import lifted_document
from scripts.quaternary_candidate_scan import candidate_inventory, scan_candidates
from scripts.quaternary_low_color import solve_low_color
from scripts.quaternary_odd_cycle_eq_low_color import solve_odd_cycle_eq


def contact_document(sides, pairs=(), anchors=None):
    """Construct tiny raw adjacency fixtures without inferred input restrictions."""
    return {'sides': list(sides), 'lines': [
        {'id': 'L' + str(number), 'left': first, 'right': second, 'kind': 'separator'}
        for number, (first, second) in enumerate(pairs)], 'anchors': dict(anchors or {})}


def pentagonal_bipyramid():
    """An anchored common C5 derives the second apex without committing it."""
    ring = ['R' + str(i) for i in range(5)]
    pairs = [(ring[i], ring[(i + 1) % 5]) for i in range(5)]
    pairs += [(apex, side) for apex in ('A', 'E') for side in ring]
    return contact_document(['A', 'E', *ring], pairs, {'A': 1})


class CandidateScanTests(unittest.TestCase):
    """Only declared tiny or preexisting development diagnostics are produced."""

    @classmethod
    def setUpClass(cls):
        """Cache one known unsafe baseline rather than running archived families."""
        cls.raw = lifted_document()
        cls.saved_run = solve_low_color(cls.raw)
        cls.scan = scan_candidates(cls.raw, cls.saved_run)
        cls.c5 = pentagonal_bipyramid()
        cls.c5_envelope = solve_odd_cycle_eq(cls.c5)
        cls.c5_scan = scan_candidates(cls.c5, cls.c5_envelope['run'])

    def test_committed_trials_are_persistent_but_rejected_trials_are_not(self):
        """A phase's trial label does not decide whether its commitments survive."""
        inventory = self.scan['inventory']
        expected = [0] + [event['after_phase'] for event in self.saved_run['events']]
        self.assertEqual([state['phase'] for state in inventory['states']], expected)
        self.assertEqual(expected, [0, 1, 2, 3, 4, 6])
        self.assertEqual(self.saved_run['phases'][1]['kind'], 'trial')
        rejected = self.saved_run['events'][-1]
        self.assertNotIn(rejected['trial_phase'], expected)
        self.assertEqual(inventory['states'][-2]['anchors'], inventory['states'][-1]['anchors'])
        self.assertNotIn(self.raw['sides'].index(rejected['side']),
                         dict(inventory['states'][-1]['anchors']))

    def test_known_unsafe_choice_is_separate_from_unselected_unsupported_candidates(self):
        """The earlier latent A=1 option is not an earlier actual wrong choice."""
        states = self.scan['states']
        early = next(target for target in states[0]['targets']
                     if (target['side'], target['symbol']) == ('A', 1))
        actual = next(target for target in states[3]['targets']
                      if (target['side'], target['symbol']) == ('A', 1))
        self.assertEqual((early['status'], early['category'], early['action']),
                         ('unsupported', 'other_side_min', 'not_selected'))
        self.assertEqual((actual['status'], actual['category'], actual['action']),
                         ('unsupported', 'scheduled_min', 'actual_commit'))
        self.assertEqual(actual['conditional']['status'], 'conditional_inconclusive')
        self.assertEqual(actual['conditional']['outcome']['status'], 'underdetermined')
        self.assertTrue(actual['conditional']['trace_audit']['passed'])
        self.assertEqual(self.scan['summary']['action_counts']['actual_commit']['unsupported'], 1)

    def test_conditional_refutation_and_inconclusive_gap_are_reported_separately(self):
        """Retained candidates can fail a trial or survive the same local filter."""
        targets = [target for state in self.scan['states'] for target in state['targets']
                   if target['status'] == 'unsupported']
        self.assertEqual(len(targets), 14)
        self.assertEqual(self.scan['summary']['conditional_counts'],
                         {'conditional_refuted': 10, 'conditional_inconclusive': 4})
        for target in targets:
            diagnostic = target['conditional']
            expected = ('conditional_refuted' if diagnostic['outcome']['status'] == 'conflict'
                        else 'conditional_inconclusive')
            self.assertEqual(diagnostic['status'], expected)
            self.assertTrue(diagnostic['trace_audit']['passed'])

    def test_already_unsatisfiable_prefix_is_never_counted_as_a_new_unsupported_choice(self):
        """The one earlier wrong commitment must not become 23 additional errors."""
        for state in self.scan['states'][4:]:
            self.assertEqual(self.scan['oracle_records'][state['base_oracle_index']]['result']['status'],
                             'unsat')
            self.assertTrue(all(target['status'] == 'preexisting_unsat' for target in state['targets']))
            self.assertTrue(all(target['conditional'] is None for target in state['targets']))
        self.assertEqual(self.scan['summary']['target_status_counts']['preexisting_unsat'], 23)

    def test_oracle_never_receives_learned_equality_or_inferred_singleton(self):
        """The common-C5 theorem is producer input, not an exact oracle premise."""
        self.assertEqual(self.c5_envelope['learning']['equal_names'], [['A', 'E']])
        self.assertEqual(self.c5_envelope['run']['phases'][0]['outcome']['domains'][1], [1])
        self.assertEqual(self.c5_scan['states'][0]['anchors'], [[0, 1]])
        self.assertEqual(self.c5_scan['summary']['target_status_counts']['unsupported'], 0)
        for record in self.c5_scan['oracle_records']:
            self.assertEqual(set(record['input']), {'n', 'edges', 'anchors'})
            self.assertNotIn(1, dict(record['input']['anchors']))
        for state in self.c5_scan['states']:
            fixed = dict(state['anchors'])
            self.assertEqual(dict(self.c5_scan['oracle_records'][state['base_oracle_index']]['input']['anchors']), fixed)
            for target in state['targets']:
                record = self.c5_scan['oracle_records'][target['candidate_oracle_index']]
                self.assertEqual(dict(record['input']['anchors']),
                                 {**fixed, target['side_index']: target['symbol']})

    def test_original_separator_edges_exclude_bridges_and_point_contacts(self):
        """Contact metadata does not become extra inequality constraints."""
        raw = contact_document(['A', 'B', 'C'], [('A', 'B'), ('B', 'C')], {'A': 1})
        raw['lines'].append({'id': 'bridge', 'left': 'C', 'right': 'C', 'kind': 'bridge'})
        raw['point_contacts'] = [{'sides': ['A', 'C']}]
        scan = scan_candidates(raw, solve_low_color(raw))
        self.assertTrue(all(record['input']['edges'] == [[0, 1], [1, 2]]
                            for record in scan['oracle_records']))

    def test_c4_wheel_wrong_boundary_is_an_unsatisfiable_initialization(self):
        """A proper four-color rim can still leave its center no available name."""
        ring = ['A', 'B', 'C', 'D']
        pairs = [(ring[i], ring[(i + 1) % 4]) for i in range(4)]
        pairs += [('H', side) for side in ring]
        raw = contact_document([*ring, 'H'], pairs, dict(zip(ring, (1, 2, 3, 4))))
        run = solve_low_color(raw)
        scan = scan_candidates(raw, run)
        self.assertEqual(run['status'], 'conflict')
        self.assertEqual(scan['summary']['base_status_counts'], {'sat': 0, 'unsat': 1, 'unknown': 0})
        self.assertEqual(scan['summary']['target_status_counts']['unsupported'], 0)
        # The same graph does extend a two-name rim; this is a boundary failure.
        good = contact_document([*ring, 'H'], pairs, dict(zip(ring, (1, 2, 1, 2))))
        good_scan = scan_candidates(good, solve_low_color(good))
        self.assertEqual(good_scan['summary']['target_status_counts']['unsupported'], 0)
        self.assertEqual(good_scan['summary']['base_status_counts']['unsat'], 0)

    def test_zero_node_budget_keeps_all_queries_unknown_without_conditional_diagnosis(self):
        """A budget failure is neither evidence of support nor a contradiction."""
        with patch('scripts.quaternary_candidate_scan.propagate_contacts',
                   side_effect=AssertionError('conditional propagation should not run')):
            scan = scan_candidates(self.c5, self.c5_envelope['run'], node_limit=0)
        self.assertEqual(scan['summary']['target_status_counts']['unknown'], scan['summary']['target_count'])
        self.assertTrue(all(record['result']['status'] == 'unknown'
                            and record['verification']['conclusive'] is False
                            for record in scan['oracle_records']))

    def test_unknown_base_remains_unknown_even_with_sat_children(self):
        """Per-query caps may decide a child sooner than its unanchored base."""
        raw = contact_document(['A', 'B'])
        scan = scan_candidates(raw, solve_low_color(raw, decision_limit=0), node_limit=2)
        self.assertEqual(scan['oracle_records'][scan['states'][0]['base_oracle_index']]['result']['status'],
                         'unknown')
        self.assertTrue(all(scan['oracle_records'][target['candidate_oracle_index']]['result']['status'] == 'sat'
                            for target in scan['states'][0]['targets']))
        self.assertEqual(scan['summary']['target_status_counts']['unknown'], 8)

    def test_actual_commit_query_is_cached_as_next_persistent_base(self):
        """Reusing identical raw commitments avoids redundant exact searches."""
        first, after = self.c5_scan['states'][:2]
        actual = next(target for target in first['targets'] if target['action'] == 'actual_commit')
        self.assertEqual(actual['candidate_oracle_index'], after['base_oracle_index'])
        signatures = [tuple(tuple(pair) for pair in record['input']['anchors'])
                      for record in self.c5_scan['oracle_records']]
        self.assertEqual(len(signatures), len(set(signatures)))

    def test_solved_final_state_is_kept_without_new_targets(self):
        """The final certificate remains bound even after all choices disappear."""
        state = self.c5_scan['states'][-1]
        self.assertEqual(state['propagation_status'], 'solved')
        self.assertEqual(state['targets'], [])
        self.assertIsNone(state['next_event_index'])
        self.assertEqual(state['phase'], self.c5_envelope['run']['final_phase'])

    def test_resource_limited_final_state_has_no_invented_scheduled_choice(self):
        """No actual next event means the scanner must not guess a future one."""
        raw = contact_document(['A', 'B'])
        inventory = candidate_inventory(raw, solve_low_color(raw, decision_limit=0))
        targets = inventory['states'][0]['targets']
        self.assertEqual(len(targets), 8)
        self.assertEqual({target['category'] for target in targets}, {'other_side_min', 'other_side_other'})
        self.assertTrue(all(target['action'] == 'not_selected' for target in targets))

    def test_inventory_runs_neither_oracle_nor_propagation_and_preserves_inputs(self):
        """Manifest preparation can freeze targets before any exact experiment."""
        before_raw, before_run = deepcopy(self.raw), deepcopy(self.saved_run)
        with patch('scripts.quaternary_candidate_scan.solve_exact', side_effect=AssertionError('oracle called')), \
                patch('scripts.quaternary_candidate_scan.propagate_contacts',
                      side_effect=AssertionError('propagation called')):
            inventory = candidate_inventory(self.raw, self.saved_run)
        self.assertEqual(inventory, self.scan['inventory'])
        self.assertEqual(self.raw, before_raw)
        self.assertEqual(self.saved_run, before_run)

    def test_broken_phase_chain_and_injected_anchor_are_rejected(self):
        """Saved references cannot silently replace the actual reached states."""
        for mutation in (
            lambda run: run['events'][1].__setitem__('before_phase', 0),
            lambda run: run['events'][0].__setitem__('after_phase', 2),
            lambda run: run['phases'][0]['document']['anchors'].__setitem__('E', 1),
            lambda run: run['phases'].append(deepcopy(run['phases'][0])),
            lambda run: run.__setitem__('final_phase', 0),
        ):
            damaged = deepcopy(self.saved_run)
            mutation(damaged)
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                candidate_inventory(self.raw, damaged)

    def test_external_raw_domains_or_equalities_and_bad_caps_are_rejected(self):
        """The exact oracle contract cannot silently relax new raw constraints."""
        for key, value in (('states', {'Z': '3000'}), ('equal_names', [['A', 'E']])):
            raw = deepcopy(self.raw)
            raw[key] = value
            with self.subTest(key=key), self.assertRaises(AssertionError):
                candidate_inventory(raw, self.saved_run)
        for cap in (True, -1, 0.5):
            with self.subTest(cap=cap), self.assertRaises(AssertionError):
                scan_candidates(self.raw, self.saved_run, node_limit=cap)


if __name__ == '__main__':
    unittest.main()

"""Joint support tests use tiny diagnostics, never the frozen production corpus."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts.audit_lifted_bipyramid import lifted_document
from scripts.quaternary_logical_neq_pair_scan import pair_inventory, scan_pairs
from scripts.quaternary_logical_neq_low_color import solve_logical_contacts, solve_logical_neq
from tests.test_quaternary_logical_neq import six_side_fixture
from tests.test_quaternary_logical_neq_candidate_scan import contact_document, pentagonal_bipyramid


def triangular_bipyramid():
    """Without wrapper learning, A/E differ locally but must agree globally.

    This diagnostic intentionally uses the inner propagator before the existing
    common-triangle learning pass. It is not a failure of the frozen wrapper.
    """
    return contact_document(['A', 'B', 'C', 'D', 'E'], [
        ('B', 'C'), ('B', 'D'), ('C', 'D'), ('A', 'B'), ('A', 'C'),
        ('A', 'D'), ('E', 'B'), ('E', 'C'), ('E', 'D')])


class LogicalNEQPairScanTests(unittest.TestCase):
    """Test exact pair scope, independent raw premises and saved diagnostics."""

    @classmethod
    def setUpClass(cls):
        """Cache two declared development fixtures without production scanning."""
        cls.raw = triangular_bipyramid()
        cls.saved_run = solve_logical_contacts(cls.raw, decision_limit=0)
        cls.scan = scan_pairs(cls.raw, cls.saved_run)
        cls.lifted = lifted_document()
        cls.lifted_run = solve_logical_contacts(cls.lifted, decision_limit=0)
        cls.lifted_scan = scan_pairs(cls.lifted, cls.lifted_run)

    def test_joint_unsat_can_have_two_individually_supported_endpoints(self):
        """Different apex names each extend alone but cannot extend together."""
        bad = [target for target in self.scan['states'][0]['targets']
               if target['status'] == 'unsupported']
        self.assertEqual(len(bad), 12)
        for target in bad:
            self.assertEqual(target['sides'], ['A', 'E'])
            self.assertNotEqual(*target['symbols'])
            self.assertEqual(target['single_support'], 'both_supported')
            self.assertEqual([self.scan['oracle_records'][i]['result']['status']
                              for i in target['single_oracle_indices']], ['sat', 'sat'])
            self.assertEqual(target['conditional']['status'], 'conditional_refuted')
            self.assertTrue(target['conditional']['trace_audit']['passed'])

    def test_already_unsupported_single_is_not_called_a_pure_pair_obstruction(self):
        """A known unary defect must stay distinguishable from joint support."""
        singles = [target for target in self.lifted_scan['states'][0]['targets']
                   if target['single_support'] == 'has_unsupported_single']
        self.assertTrue(singles)
        for target in singles:
            self.assertIn('unsat', [self.lifted_scan['oracle_records'][i]['result']['status']
                                    for i in target['single_oracle_indices']])

    def test_relation_targets_are_not_the_cartesian_product_of_domains(self):
        """Physical edge diagonal choices stay excluded from pair obligations."""
        state = self.scan['inventory']['states'][0]
        self.assertEqual(state['eligible_side_pair_count'], 10)
        self.assertEqual(state['cartesian_target_count'], 160)
        self.assertEqual(len(state['targets']), 124)
        self.assertFalse(any(t['sides'] == ['A', 'B'] and t['symbols'] == [1, 1]
                             for t in state['targets']))
        self.assertTrue(any(t['sides'] == ['A', 'E'] and t['symbols'] == [1, 1]
                            for t in state['targets']))
        self.assertTrue(all(t['side_indices'][0] < t['side_indices'][1] for t in state['targets']))

    def test_directional_matrix_bit_maps_to_the_ordered_pair(self):
        """R[A,B](1,2) and R[B,A](2,1) describe one retained target."""
        raw = contact_document(['A', 'B'])
        run = solve_logical_contacts(raw, decision_limit=0)
        matrix = run['phases'][0]['outcome']['relations']
        matrix[0][1], matrix[1][0] = 1 << 1, 1 << 4
        targets = pair_inventory(raw, run)['states'][0]['targets']
        self.assertEqual([target['symbols'] for target in targets], [[1, 2]])
        matrix[1][0] = 1 << 1
        with self.assertRaises(AssertionError):
            pair_inventory(raw, run)

    def test_matrix_rejects_boolean_overwidth_nondiagonal_and_domain_mismatch(self):
        """No malformed matrix can silently shrink the predeclared inventory."""
        for change in (
            lambda m: m[0].__setitem__(0, True),
            lambda m: m[0].__setitem__(0, 65536),
            lambda m: m[0].__setitem__(0, 2),
            lambda m: m[0].__setitem__(0, 1),
            lambda m: m.pop(),
        ):
            run = deepcopy(self.saved_run)
            change(run['phases'][0]['outcome']['relations'])
            with self.subTest(change=change), self.assertRaises(AssertionError):
                pair_inventory(self.raw, run)

    def test_relations_may_not_reintroduce_values_outside_a_domain(self):
        """Transpose-consistent matrix values still cannot exceed endpoints."""
        raw = contact_document(['A', 'B'], anchors={'A': 1})
        run = solve_logical_contacts(raw, decision_limit=0)
        matrix = run['phases'][0]['outcome']['relations']
        matrix[0][1] |= 1 << 4
        matrix[1][0] |= 1 << 1
        with self.assertRaises(AssertionError):
            pair_inventory(raw, run)

    def test_derived_singleton_and_explicit_anchor_are_both_excluded(self):
        """The oracle never receives a derived singleton as an actual anchor."""
        raw = pentagonal_bipyramid()
        run = solve_logical_neq(raw)['run']
        scan = scan_pairs(raw, run)
        self.assertEqual(run['phases'][0]['outcome']['domains'][:2], [[1], [1]])
        for state in scan['states']:
            self.assertNotIn(1, dict(state['anchors']))
            self.assertTrue(all(0 not in t['side_indices'] and 1 not in t['side_indices']
                                for t in state['targets']))
        self.assertTrue(all(1 not in dict(record['input']['anchors'])
                            for record in scan['oracle_records']))

    def test_exact_pair_and_single_premises_bind_raw_edges_and_actual_anchors(self):
        """No saved local domain or relation is an exact-query premise."""
        for state in self.lifted_scan['states']:
            fixed = dict(state['anchors'])
            base = self.lifted_scan['oracle_records'][state['base_oracle_index']]
            self.assertEqual(dict(base['input']['anchors']), fixed)
            for target in state['targets']:
                record = self.lifted_scan['oracle_records'][target['pair_oracle_index']]
                hypotheses = dict(zip(target['side_indices'], target['symbols']))
                self.assertEqual(dict(record['input']['anchors']), {**fixed, **hypotheses})
                if target['single_oracle_indices'] is not None:
                    for vertex, color, ref in zip(target['side_indices'], target['symbols'],
                                                  target['single_oracle_indices']):
                        self.assertEqual(dict(self.lifted_scan['oracle_records'][ref]['input']['anchors']),
                                         {**fixed, vertex: color})
        self.assertTrue(all(set(record['input']) == {'n', 'edges', 'anchors'}
                            for record in self.lifted_scan['oracle_records']))

    def test_no_extra_endpoint_queries_for_supported_pairs(self):
        """Single support is only diagnosed after a proved unsupported pair."""
        good = [target for target in self.scan['states'][0]['targets']
                if target['status'] == 'supported']
        self.assertEqual(len(good), 112)
        self.assertTrue(all(target['single_support'] is None
                            and target['single_oracle_indices'] is None
                            and target['conditional'] is None for target in good))

    def test_endpoint_and_pair_queries_are_cached_without_duplicate_signatures(self):
        """Repeated endpoints and later prefixes share exact evidence only."""
        records = self.scan['oracle_records']
        signatures = [tuple(tuple(pair) for pair in record['input']['anchors']) for record in records]
        self.assertEqual(len(signatures), len(set(signatures)))
        self.assertEqual(len(records), 133)

    def test_zero_budget_remains_unknown_without_conditional_propagation(self):
        """Exhaustion is neither a pair obstruction nor a passed target."""
        with patch('scripts.quaternary_logical_neq_pair_scan.propagate_logical_contacts',
                   side_effect=AssertionError('unexpected diagnostic')):
            scan = scan_pairs(self.raw, self.saved_run, node_limit=0)
        self.assertEqual(scan['summary']['target_status_counts']['unknown'], 124)
        self.assertTrue(all(t['single_support'] is None for t in scan['states'][0]['targets']))

    def test_unknown_base_does_not_become_supported_from_a_sat_child(self):
        """Two fully fixed colors may finish before their unresolved base."""
        raw = contact_document(['A', 'B'])
        run = solve_logical_contacts(raw, decision_limit=0)
        scan = scan_pairs(raw, run, node_limit=1)
        self.assertEqual(scan['oracle_records'][scan['states'][0]['base_oracle_index']]['result']['status'],
                         'unknown')
        self.assertTrue(all(scan['oracle_records'][t['pair_oracle_index']]['result']['status'] == 'sat'
                            for t in scan['states'][0]['targets']))
        self.assertEqual(scan['summary']['target_status_counts']['unknown'], 16)

    def test_categories_use_local_minima_without_implying_a_scheduled_pair(self):
        """Minimum-name preference and actual one-face action are distinct."""
        raw = contact_document(['A', 'B'])
        run = solve_logical_contacts(raw)
        targets = pair_inventory(raw, run)['states'][0]['targets']
        self.assertEqual(sum(t['category'] == 'both_min' for t in targets), 1)
        self.assertEqual(sum(t['category'] == 'one_min' for t in targets), 6)
        self.assertEqual(sum(t['category'] == 'neither_min' for t in targets), 9)
        included = [t for t in targets if t['next_action'] == 'includes_next_commit']
        self.assertEqual(len(included), 4)
        self.assertTrue(all(t['symbols'][0] == 1 for t in included))
        self.assertNotIn('actual_commit', self.scan['summary'])
        self.assertNotIn('action_counts', self.scan['summary'])

    def test_resource_limited_phase_has_no_invented_next_choice(self):
        """A scan does not guess which unexecuted choice the producer would take."""
        self.assertTrue(all(t['next_action'] == 'not_next_choice'
                            for t in self.scan['states'][0]['targets']))

    def test_persistent_rejection_and_preexisting_unsat_remain_distinct(self):
        """A rejected trial is excluded and a bad base is not a new pair defect."""
        run = solve_logical_contacts(self.lifted)
        scan = scan_pairs(self.lifted, run)
        expected = [0] + [event['after_phase'] for event in run['events']]
        self.assertEqual([state['phase'] for state in scan['states']], expected)
        self.assertEqual(expected, [0, 1, 2, 3, 4, 6])
        rejected = run['events'][-1]
        self.assertNotIn(rejected['trial_phase'], expected)
        before, after = scan['states'][-2:]
        self.assertEqual(before['anchors'], after['anchors'])
        marked = [target for target in before['targets']
                  if target['next_action'] == 'includes_next_reject']
        self.assertEqual(len(marked), 6)
        for state in (before, after):
            self.assertTrue(all(target['status'] == 'preexisting_unsat'
                                and target['conditional'] is None
                                and target['single_oracle_indices'] is None
                                and target['single_support'] is None for target in state['targets']))

    def test_conditional_refutation_and_inconclusive_are_counted_separately(self):
        """A failed exact pair can survive the diagnostic propagation rules."""
        counts = self.lifted_scan['summary']['conditional_counts']
        self.assertGreater(counts['conditional_refuted'], 0)
        self.assertGreater(counts['conditional_inconclusive'], 0)
        self.assertEqual(sum(counts.values()),
                         self.lifted_scan['summary']['target_status_counts']['unsupported'])

    def test_single_remaining_unresolved_face_has_no_pair_target(self):
        """One unresolved domain is a unary issue outside the paired scope."""
        raw = contact_document(['A', 'B'], anchors={'A': 1})
        run = solve_logical_contacts(raw, decision_limit=0)
        scan = scan_pairs(raw, run)
        self.assertEqual(scan['summary']['target_count'], 0)
        self.assertEqual(scan['summary']['no_target_state_count'], 1)
        self.assertEqual(scan['summary']['oracle_record_count'], 1)

    def test_inventory_preserves_inputs_and_calls_no_search_or_propagation(self):
        """Target freezing happens before the offline experiment begins."""
        raw, run = deepcopy(self.raw), deepcopy(self.saved_run)
        with patch('scripts.quaternary_logical_neq_pair_scan.solve_exact',
                   side_effect=AssertionError('search called')), \
                patch('scripts.quaternary_logical_neq_pair_scan.propagate_logical_contacts',
                      side_effect=AssertionError('propagation called')):
            inventory = pair_inventory(raw, run)
        self.assertEqual(inventory, self.scan['inventory'])
        self.assertEqual(raw, self.raw)
        self.assertEqual(run, self.saved_run)

    def test_physical_oracle_excludes_logical_edges_bridges_and_point_contacts(self):
        """Stored contact geometry is not permission to inject extra edges."""
        raw = six_side_fixture()
        raw['lines'].append({'id': 'bridge', 'left': 'A', 'right': 'A', 'kind': 'bridge'})
        raw['point_contacts'] = [{'sides': ['X', 'E']}]
        run = solve_logical_neq(raw)['run']
        scan = scan_pairs(raw, run)
        expected = sorted({tuple(sorted((raw['sides'].index(line['left']),
                                         raw['sides'].index(line['right']))))
                           for line in raw['lines'] if line['kind'] == 'separator'})
        self.assertNotIn((4, 5), expected)
        self.assertTrue(all(record['input']['edges'] == [list(pair) for pair in expected]
                            for record in scan['oracle_records']))

    def test_conditional_double_hypothesis_keeps_learned_fields(self):
        """A separate fully anchored component supplies a valid logical NEQ."""
        raw = deepcopy(self.raw)
        extra = six_side_fixture()
        raw['sides'].extend('F_' + side for side in extra['sides'])
        raw['lines'].extend({'id': 'F_' + line['id'], 'left': 'F_' + line['left'],
                             'right': 'F_' + line['right'], 'kind': line['kind']}
                            for line in extra['lines'])
        raw['anchors'].update(dict(zip(['F_A', 'F_B', 'F_C', 'F_D', 'F_X', 'F_E'],
                                       [1, 2, 3, 4, 1, 2])))
        augmented = deepcopy(raw)
        augmented['different_names'] = [['F_X', 'F_E']]
        augmented['equal_names'] = [['F_A', 'F_X']]
        run = solve_logical_contacts(augmented, decision_limit=0)
        scan = scan_pairs(raw, run)
        diagnostics = [(target, target['conditional']) for target in scan['states'][0]['targets']
                       if target['conditional'] is not None]
        self.assertEqual(len(diagnostics), 12)
        for target, evidence in diagnostics:
            self.assertEqual(evidence['input']['different_names'], [['F_X', 'F_E']])
            self.assertEqual(evidence['input']['equal_names'], [['F_A', 'F_X']])
            self.assertEqual(evidence['input']['anchors'],
                             {**raw['anchors'], **dict(zip(target['sides'], target['symbols']))})
            self.assertTrue(evidence['trace_audit']['passed'])

    def test_bad_caps_raw_restrictions_and_broken_persistent_chain_are_rejected(self):
        """The pair extension retains the frozen scanner's provenance checks."""
        for cap in (True, -1, 0.5):
            with self.subTest(cap=cap), self.assertRaises(AssertionError):
                scan_pairs(self.raw, self.saved_run, node_limit=cap)
        for key, value in (('states', {'A': '1000'}), ('equal_names', [['A', 'E']]),
                           ('different_names', [])):
            raw = deepcopy(self.raw)
            raw[key] = value
            with self.subTest(key=key), self.assertRaises(AssertionError):
                pair_inventory(raw, self.saved_run)
        run = solve_logical_contacts(self.raw)
        run['events'][0]['after_phase'] += 1
        with self.assertRaises(AssertionError):
            pair_inventory(self.raw, run)


if __name__ == '__main__':
    unittest.main()

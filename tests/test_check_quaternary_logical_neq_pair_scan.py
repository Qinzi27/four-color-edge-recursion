"""Reject forged joint support while replaying no producer or exact search."""

import ast
from copy import deepcopy
from itertools import combinations
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.audit_lifted_bipyramid import lifted_document
from scripts.check_quaternary_logical_neq_pair_scan import check_pair_scan
from scripts.exact_extendibility_oracle import solve_exact, verify_exact_result
from scripts.quaternary_logical_neq_contacts import propagate_logical_contacts
from scripts.quaternary_logical_neq_low_color import solve_logical_contacts, solve_logical_neq
from scripts.quaternary_logical_neq_pair_scan import scan_pairs


def path_document():
    """Asymmetric endpoint domains expose accidentally transposed mask bits."""
    return {'sides': ['A', 'B', 'C'], 'anchors': {'A': 1}, 'lines': [
        {'id': 'AB', 'left': 'A', 'right': 'B', 'kind': 'separator'},
        {'id': 'BC', 'left': 'B', 'right': 'C', 'kind': 'separator'}]}


def bipyramid_document():
    """Known inner-loop control: unequal apex colors individually have support.

    Learned EQ is intentionally omitted for this checker unit fixture. This
    is not a failure of the full frozen logical-NEQ wrapper under experiment.
    """
    sides = ['A', 'B', 'C', 'D', 'E']
    edges = ['BC', 'BD', 'CD', 'AB', 'AC', 'AD', 'EB', 'EC', 'ED']
    return {'sides': sides, 'anchors': {}, 'lines': [
        {'id': edge, 'left': edge[0], 'right': edge[1], 'kind': 'separator'}
        for edge in edges]}


def learned_document():
    """The known six-face control has a proved but nonphysical v/w NEQ."""
    sides = ['u', 'a', 'b', 'c', 'v', 'w']
    edges = list(combinations(range(4), 2)) + [
        (4, 1), (4, 2), (4, 3), (5, 0), (5, 2), (5, 3)]
    return {'sides': sides, 'anchors': {'u': 1}, 'lines': [
        {'id': 'E' + str(k), 'left': sides[i], 'right': sides[j], 'kind': 'separator'}
        for k, (i, j) in enumerate(edges)]}


class CheckLogicalNeqPairScanTests(unittest.TestCase):
    """Use valid saved certificates, then alter one scientific obligation."""

    @classmethod
    def setUpClass(cls):
        """Produce small unit controls once, before checker isolation patches."""
        cls.raw = path_document()
        cls.saved_run = solve_logical_neq(cls.raw)['run']
        cls.scan = scan_pairs(cls.raw, cls.saved_run)
        cls.bp_raw = bipyramid_document()
        cls.bp_run = solve_logical_contacts(cls.bp_raw, decision_limit=0)
        cls.bp_scan = scan_pairs(cls.bp_raw, cls.bp_run)
        cls.lifted_raw = lifted_document()
        cls.lifted_run = solve_logical_contacts(cls.lifted_raw, decision_limit=0)
        cls.lifted_scan = scan_pairs(cls.lifted_raw, cls.lifted_run)
        cls.learned_raw = learned_document()
        cls.learned_run = solve_logical_neq(cls.learned_raw)['run']
        cls.learned_scan = scan_pairs(cls.learned_raw, cls.learned_run)

    def unsupported(self, scan):
        """Locate the first explicitly proved unsupported saved pair."""
        return next(target for state in scan['states'] for target in state['targets']
                    if target['status'] == 'unsupported')

    def assert_rejected(self, raw, run, scan):
        """Both independent audit assertion and schema value failures reject."""
        with self.assertRaises((AssertionError, ValueError)):
            check_pair_scan(raw, run, scan)

    def test_complete_retained_pairs_and_next_choice_membership(self):
        """Only nine of the twelve domain combinations satisfy the B/C relation."""
        checked = check_pair_scan(self.raw, self.saved_run, self.scan)
        self.assertTrue(checked['passed'])
        summary = checked['summary']
        self.assertEqual(summary['target_count'], 9)
        self.assertEqual(summary['cartesian_target_count'], 12)
        self.assertEqual(summary['eligible_side_pair_count'], 1)
        self.assertEqual(summary['next_action_counts']['includes_next_commit']['supported'], 3)
        self.assertGreater(summary['no_target_state_count'], 0)
        self.assertTrue(all(target['side_indices'] == [1, 2]
                            for target in self.scan['states'][0]['targets']))

    def test_genuine_joint_obstruction_has_two_independent_single_witnesses(self):
        """Twelve incompatible apex pairs survive the inner binary closure."""
        checked = check_pair_scan(self.bp_raw, self.bp_run, self.bp_scan)
        self.assertEqual(checked['summary']['target_status_counts']['unsupported'], 12)
        self.assertEqual(checked['summary']['single_support_counts']['both_supported'], 12)
        self.assertEqual(checked['single_endpoint_queries_checked'], 24)
        self.assertEqual(checked['conditional_probes_checked'], 12)
        self.assertEqual(checked['summary']['conditional_counts']['conditional_refuted'], 12)
        self.assertEqual(checked['summary']['next_action_counts']['not_next_choice']['unsupported'], 12)

    def test_bad_single_is_not_mislabeled_as_pure_pair_obstruction(self):
        """A diagnostic already unsupported at one endpoint keeps that category."""
        checked = check_pair_scan(self.lifted_raw, self.lifted_run, self.lifted_scan)
        self.assertGreater(checked['summary']['single_support_counts']['has_unsupported_single'], 0)
        bad = deepcopy(self.lifted_scan)
        target = next(target for state in bad['states'] for target in state['targets']
                      if target['single_support'] == 'has_unsupported_single')
        target['single_support'] = 'both_supported'
        self.assert_rejected(self.lifted_raw, self.lifted_run, bad)

    def test_rejected_trials_and_preexisting_unsat_are_not_new_joint_failures(self):
        """The known old inner control checks excluded trials and failed bases."""
        run = solve_logical_contacts(self.lifted_raw)
        scan = scan_pairs(self.lifted_raw, run)
        checked = check_pair_scan(self.lifted_raw, run, scan)
        self.assertGreater(checked['summary']['target_status_counts']['preexisting_unsat'], 0)
        self.assertGreater(checked['summary']['conditional_counts']['conditional_inconclusive'], 0)
        persistent = {state['phase'] for state in scan['states']}
        rejected = [event for event in run['events'] if event['kind'] == 'reject']
        self.assertTrue(rejected)
        for event in rejected:
            self.assertNotIn(event['trial_phase'], persistent)
            self.assertIn(event['after_phase'], persistent)
        target = next(target for state in scan['states'] for target in state['targets']
                      if target['status'] == 'preexisting_unsat')
        target['status'] = 'unsupported'
        self.assert_rejected(self.lifted_raw, run, scan)

    def test_conditional_replay_preserves_logical_neq_without_adding_oracle_edge(self):
        """A redundant logical pair tests the language boundary, not the learner."""
        augmented = {**deepcopy(self.bp_raw), 'different_names': [['B', 'C']]}
        run = solve_logical_contacts(augmented, decision_limit=0)
        scan = scan_pairs(self.bp_raw, run)
        checked = check_pair_scan(self.bp_raw, run, scan)
        self.assertEqual(checked['conditional_probes_checked'], 12)
        target = self.unsupported(scan)
        self.assertEqual(target['conditional']['input']['different_names'], [['B', 'C']])
        self.assertTrue(all(set(record['input']) == {'n', 'edges', 'anchors'}
                            for record in scan['oracle_records']))
        target['conditional']['outcome']['different_names'] = []
        with self.assertRaisesRegex(AssertionError, 'logical NEQ echo'):
            check_pair_scan(self.bp_raw, run, scan)

    def test_cartesian_product_fake_pair_is_rejected(self):
        """Deleting a relation bit is not undone by inventing a Cartesian target."""
        for section in ('inventory', 'states'):
            bad = deepcopy(self.scan)
            states = bad['inventory']['states'] if section == 'inventory' else bad['states']
            item = deepcopy(states[0]['targets'][0])
            item['symbols'] = [2, 2]
            states[0]['targets'].append(item)
            with self.subTest(section=section):
                self.assert_rejected(self.raw, self.saved_run, bad)

    def test_reversed_endpoint_colors_and_boolean_indices_are_rejected(self):
        """The asymmetric valid B=2,C=1 pair is not B=1,C=2."""
        for field, value in (('symbols', [1, 2]), ('side_indices', [2, 1]),
                             ('side_indices', [True, 2]), ('sides', ['C', 'B'])):
            bad = deepcopy(self.scan)
            bad['states'][0]['targets'][0][field] = value
            with self.subTest(field=field, value=value):
                self.assert_rejected(self.raw, self.saved_run, bad)

    def test_matrix_types_transpose_domain_and_diagonal_are_checked(self):
        """A valid target list cannot hide a structurally invalid final matrix."""
        for mutation in ('boolean', 'transpose', 'diagonal', 'outside_domain'):
            bad_run = deepcopy(self.saved_run)
            matrix = bad_run['phases'][0]['outcome']['relations']
            if mutation == 'boolean':
                matrix[1][2] = True
            elif mutation == 'transpose':
                matrix[1][2] ^= 1 << 4
            elif mutation == 'diagonal':
                matrix[1][1] ^= 1
            else:
                # Add a transposition-consistent pair B=1,C=2 outside B's domain.
                matrix[1][2] |= 1 << 1
                matrix[2][1] |= 1 << 4
            with self.subTest(mutation=mutation):
                self.assert_rejected(self.raw, bad_run, self.scan)

    def test_deleted_target_state_or_inventory_is_rejected(self):
        """Every persistent state and every allowed pair is an obligation."""
        for mutation in ('target', 'inventory_target', 'state', 'duplicate_state'):
            bad = deepcopy(self.scan)
            if mutation == 'target':
                bad['states'][0]['targets'].pop()
            elif mutation == 'inventory_target':
                bad['inventory']['states'][0]['targets'].pop()
            elif mutation == 'state':
                bad['states'].pop()
            else:
                bad['states'].append(deepcopy(bad['states'][-1]))
            with self.subTest(mutation=mutation):
                self.assert_rejected(self.raw, self.saved_run, bad)

    def test_category_or_next_commit_membership_cannot_be_relabelled(self):
        """A pair containing a future single commitment is still not jointly chosen."""
        for field, value in (('category', 'neither_min'), ('next_action', 'not_next_choice')):
            bad = deepcopy(self.scan)
            bad['states'][0]['targets'][0][field] = value
            with self.subTest(field=field):
                self.assert_rejected(self.raw, self.saved_run, bad)

    def test_one_endpoint_witness_cannot_replace_joint_certificate(self):
        """Both individual SAT claims coexist with a joint UNSAT claim."""
        bad = deepcopy(self.bp_scan)
        target = self.unsupported(bad)
        target['pair_oracle_index'] = target['single_oracle_indices'][0]
        with self.assertRaisesRegex(ValueError, 'pair/single binding'):
            check_pair_scan(self.bp_raw, self.bp_run, bad)

    def test_joint_certificate_cannot_replace_single_diagnosis(self):
        """A jointly UNSAT query says nothing about the separately fixed endpoint."""
        bad = deepcopy(self.bp_scan)
        target = self.unsupported(bad)
        target['single_oracle_indices'][0] = target['pair_oracle_index']
        with self.assertRaisesRegex(ValueError, 'pair/single binding'):
            check_pair_scan(self.bp_raw, self.bp_run, bad)

    def test_all_unsupported_diagnostics_are_required(self):
        """Both single queries and the double-assumption probe must be saved."""
        for field, value in (('single_oracle_indices', None), ('single_oracle_indices', [0]),
                             ('single_support', None), ('conditional', None)):
            bad = deepcopy(self.bp_scan)
            self.unsupported(bad)[field] = value
            with self.subTest(field=field, value=value):
                self.assert_rejected(self.bp_raw, self.bp_run, bad)

    def test_conditional_input_requires_both_target_anchors(self):
        """A genuine one-endpoint trace does not certify this joint diagnostic."""
        bad = deepcopy(self.bp_scan)
        target = self.unsupported(bad)
        target['conditional']['input']['anchors'].pop(target['sides'][1])
        with self.assertRaisesRegex(ValueError, 'conditional persistent phase and pair premise'):
            check_pair_scan(self.bp_raw, self.bp_run, bad)

    def test_conditional_trace_or_refutation_label_cannot_be_forged(self):
        """Local refutation status is independently replayed from the saved trace."""
        for mutation in ('trace', 'label', 'audit'):
            bad = deepcopy(self.bp_scan)
            diagnostic = self.unsupported(bad)['conditional']
            if mutation == 'trace':
                diagnostic['outcome']['trace'][0]['after'] ^= 1
            elif mutation == 'label':
                diagnostic['status'] = 'conditional_inconclusive'
            else:
                diagnostic['trace_audit']['trace_steps_checked'] = 0
            with self.subTest(mutation=mutation):
                self.assert_rejected(self.bp_raw, self.bp_run, bad)

    def test_supported_pair_has_no_fake_unsupported_diagnostic(self):
        """The diagnostic-only fields have explicit None values on supported rows."""
        for field, value in (('single_oracle_indices', [0, 1]),
                             ('single_support', 'both_supported'), ('conditional', {})):
            bad = deepcopy(self.scan)
            bad['states'][0]['targets'][0][field] = value
            with self.subTest(field=field):
                self.assert_rejected(self.raw, self.saved_run, bad)

    def test_raw_neq_and_no_extra_premises_are_enforced(self):
        """Logical rules, inferred words, and false side counts cannot aid the oracle."""
        mutations = [lambda data: data['edges'].clear(),
                     lambda data: data.update(different_names=[['B', 'C']]),
                     lambda data: data.update(equal_names=[['B', 'C']]),
                     lambda data: data.update(states={'B': '0200'}),
                     lambda data: data.update(n=True)]
        for number, mutate in enumerate(mutations):
            bad = deepcopy(self.scan)
            mutate(bad['oracle_records'][0]['input'])
            with self.subTest(number=number):
                self.assert_rejected(self.raw, self.saved_run, bad)

    def test_learned_neq_cannot_be_inserted_as_a_physical_edge(self):
        """Even a valid certificate with a true learned edge has the wrong input."""
        self.assertIn(['v', 'w'], self.learned_run['original_input']['different_names'])
        self.assertTrue(check_pair_scan(self.learned_raw, self.learned_run, self.learned_scan)['passed'])
        bad = deepcopy(self.learned_scan)
        record = bad['oracle_records'][0]
        data = record['input']
        self.assertNotIn([4, 5], data['edges'])
        data['edges'] = sorted(data['edges'] + [[4, 5]])
        fixed = dict(data['anchors'])
        result = solve_exact(data['n'], data['edges'], fixed, node_limit=bad['node_limit'])
        record.update(result=result, verification=verify_exact_result(
            data['n'], data['edges'], fixed, result))
        with self.assertRaisesRegex(ValueError, 'original separator edges'):
            check_pair_scan(self.learned_raw, self.learned_run, bad)

    def test_extra_inferred_anchor_cannot_strengthen_base(self):
        """A valid stronger SAT query is still not the base's raw premise."""
        bad = deepcopy(self.learned_scan)
        record = bad['oracle_records'][bad['states'][0]['base_oracle_index']]
        data, fixed = record['input'], dict(record['input']['anchors'])
        fixed[4] = 1  # The wrapper derives v=u=1; only u is an actual initial anchor.
        data['anchors'] = [list(pair) for pair in sorted(fixed.items())]
        result = solve_exact(data['n'], data['edges'], fixed, node_limit=bad['node_limit'])
        record.update(result=result, verification=verify_exact_result(
            data['n'], data['edges'], fixed, result))
        self.assert_rejected(self.learned_raw, self.learned_run, bad)

    def test_duplicate_or_unused_query_is_rejected(self):
        """Query cache accounting covers all exact certificates in the artifact."""
        for mutation in ('duplicate', 'unused'):
            bad = deepcopy(self.scan)
            if mutation == 'duplicate':
                bad['oracle_records'].append(deepcopy(bad['oracle_records'][0]))
            else:
                edges, fixed = [[0, 1], [1, 2]], {}
                result = solve_exact(3, edges, fixed, node_limit=bad['node_limit'])
                bad['oracle_records'].append({'input': {'n': 3, 'edges': edges, 'anchors': []},
                                              'result': result, 'verification': verify_exact_result(
                                                  3, edges, fixed, result)})
            with self.subTest(mutation=mutation):
                self.assert_rejected(self.raw, self.saved_run, bad)

    def test_unknown_is_not_joint_unsat(self):
        """Zero-node exact queries remain unresolved and trigger no diagnosis."""
        scan = scan_pairs(self.raw, self.saved_run, node_limit=0)
        checked = check_pair_scan(self.raw, self.saved_run, scan, node_limit=0)
        self.assertEqual(checked['summary']['target_status_counts']['unknown'], 9)
        self.assertEqual(checked['conditional_probes_checked'], 0)
        scan['states'][0]['targets'][0]['status'] = 'unsupported'
        with self.assertRaisesRegex(ValueError, 'pair support classification'):
            check_pair_scan(self.raw, self.saved_run, scan, node_limit=0)

    def test_unknown_base_is_not_promoted_by_a_sat_pair(self):
        """Fewer free variables can make a child conclusive before its base."""
        raw = {'sides': ['A', 'B'], 'lines': []}
        run = solve_logical_contacts(raw, decision_limit=0)
        scan = scan_pairs(raw, run, node_limit=1)
        checked = check_pair_scan(raw, run, scan, node_limit=1)
        self.assertEqual(checked['summary']['base_status_counts']['unknown'], 1)
        self.assertEqual(checked['summary']['target_status_counts']['unknown'], 16)
        self.assertTrue(all(scan['oracle_records'][target['pair_oracle_index']]['result']['status']
                            == 'sat' for target in scan['states'][0]['targets']))

    def test_node_limit_saved_verification_and_false_witness_are_checked(self):
        """Saved labels and numerical limits cannot replace certificate validity."""
        for mutation in ('cap', 'verification', 'witness'):
            bad = deepcopy(self.scan)
            record = bad['oracle_records'][0]
            if mutation == 'cap':
                record['result']['node_limit'] = 1
            elif mutation == 'verification':
                record['verification']['passed'] = False
            else:
                record['result']['witness'] = [1, 1, 1]
            with self.subTest(mutation=mutation):
                self.assert_rejected(self.raw, self.saved_run, bad)

    def test_event_history_changes_are_rejected(self):
        """The old independent traversal still binds the actual one-face chain."""
        for mutation in ('phase', 'commitment', 'kind', 'guard'):
            bad = deepcopy(self.saved_run)
            if mutation == 'phase':
                bad['events'][0]['after_phase'] = 0
            elif mutation == 'commitment':
                bad['phases'][1]['document']['anchors']['B'] = 3
            elif mutation == 'kind':
                bad['events'][0]['kind'] = 'reject'
            else:
                bad['probe'] = False
            with self.subTest(mutation=mutation):
                self.assert_rejected(self.raw, bad, self.scan)

    def test_summary_and_offline_mode_are_checked(self):
        """Independent recount includes Cartesian denominator and single support."""
        for field, value in (('target_count', 0), ('cartesian_target_count', 0),
                             ('eligible_side_pair_count', True),
                             ('single_support_counts', {})):
            bad = deepcopy(self.scan)
            bad['summary'][field] = value
            with self.subTest(field=field):
                self.assert_rejected(self.raw, self.saved_run, bad)
        bad = deepcopy(self.scan)
        bad['oracle_feedback_to_producer'] = True
        self.assert_rejected(self.raw, self.saved_run, bad)

    def test_saved_checker_calls_no_search_producer_propagator_or_pair_inventory(self):
        """Independence holds even when unsupported pair probes need trace replay."""
        forbidden = AssertionError('checker performed a forbidden recomputation')
        with patch('scripts.quaternary_logical_neq_pair_scan.pair_inventory', side_effect=forbidden), \
                patch('scripts.quaternary_logical_neq_candidate_scan.candidate_inventory', side_effect=forbidden), \
                patch('scripts.quaternary_logical_neq_pair_scan.solve_exact', side_effect=forbidden), \
                patch('scripts.exact_extendibility_oracle.solve_exact', side_effect=forbidden), \
                patch('scripts.audit_quaternary_logical_neq.solve_exact', side_effect=forbidden), \
                patch('scripts.quaternary_logical_neq_pair_scan.propagate_logical_contacts', side_effect=forbidden), \
                patch('scripts.quaternary_logical_neq_contacts.propagate_logical_contacts', side_effect=forbidden), \
                patch('scripts.quaternary_logical_neq_low_color.solve_logical_contacts', side_effect=forbidden):
            checked = check_pair_scan(self.bp_raw, self.bp_run, self.bp_scan)
        self.assertEqual(checked['producer_runs'], 0)
        self.assertEqual(checked['oracle_searches'], 0)
        self.assertEqual(checked['propagation_runs'], 0)

    def test_checker_imports_no_new_pair_scanner(self):
        """Inventory reconstruction must not accidentally share new scanner code."""
        path = Path(__file__).resolve().parents[1] / 'scripts' / 'check_quaternary_logical_neq_pair_scan.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        self.assertFalse(any('quaternary_logical_neq_pair_scan' in (node.module or '')
                             for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)))


if __name__ == '__main__':
    unittest.main()

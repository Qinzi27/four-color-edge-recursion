"""Saved candidate evidence must cover actual prefixes and exact raw premises."""

from copy import deepcopy
import ast
from itertools import combinations
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.audit_lifted_bipyramid import lifted_document
from scripts.audit_quaternary_logical_neq import audit_logical_contacts
from scripts.check_quaternary_logical_neq_candidate_scan import check_candidate_scan
from scripts.exact_extendibility_oracle import solve_exact, verify_exact_result
from scripts.quaternary_logical_neq_candidate_scan import scan_candidates
from scripts.quaternary_logical_neq_contacts import propagate_logical_contacts
from scripts.quaternary_logical_neq_low_color import solve_logical_contacts, solve_logical_neq


def small_document():
    """A two-face raw contact has three supported choices after A=1."""
    return {'sides': ['A', 'B'], 'anchors': {'A': 1}, 'lines': [
        {'id': 'E0', 'left': 'A', 'right': 'B', 'kind': 'separator'}]}


def c5_document():
    """Use the established abstract odd-cycle diagnostic, not a new holdout."""
    ring = ['B' + str(i) for i in range(5)]
    edges = [(ring[i], ring[(i + 1) % 5]) for i in range(5)]
    edges += [(apex, side) for apex in ('A', 'E') for side in ring]
    return {'sides': ['A', 'E', *ring], 'anchors': {'A': 1}, 'lines': [
        {'id': 'L' + str(i), 'left': a, 'right': b, 'kind': 'separator'}
        for i, (a, b) in enumerate(edges)]}


def positive_document():
    """The known six-face control forces v=u, w=a, hence nonadjacent v!=w."""
    sides = ['u', 'a', 'b', 'c', 'v', 'w']
    pairs = list(combinations(range(4), 2)) + [
        (4, 1), (4, 2), (4, 3), (5, 0), (5, 2), (5, 3)]
    return {'sides': sides, 'anchors': {'u': 1}, 'lines': [
        {'id': 'E' + str(i), 'left': sides[a], 'right': sides[b], 'kind': 'separator'}
        for i, (a, b) in enumerate(pairs)]}


class CheckLogicalNeqCandidateScanTests(unittest.TestCase):
    """Recompute no oracle search when accepting or rejecting saved artifacts."""

    @classmethod
    def setUpClass(cls):
        """Use old inner-loop controls; full-envelope proof checks belong to the runner.

        C5 and lifted controls intentionally omit learned pairs so that known
        conditional-refutation, inconclusive and preexisting-UNSAT branches
        remain testable. They are not new wrapper-version experimental cases.
        """
        cls.raw = small_document()
        cls.small_run = solve_logical_contacts(cls.raw)
        cls.scan = scan_candidates(cls.raw, cls.small_run)
        cls.c5_raw = c5_document()
        cls.c5_run = solve_logical_contacts(cls.c5_raw)
        cls.c5_scan = scan_candidates(cls.c5_raw, cls.c5_run)
        cls.odd_run = solve_logical_neq(cls.c5_raw)['run']
        cls.odd_scan = scan_candidates(cls.c5_raw, cls.odd_run)
        cls.lifted_raw = lifted_document()
        cls.lifted_run = solve_logical_contacts(cls.lifted_raw)
        cls.lifted_scan = scan_candidates(cls.lifted_raw, cls.lifted_run)
        cls.positive_raw = positive_document()
        cls.positive_run = solve_logical_neq(cls.positive_raw)['run']
        cls.positive_scan = scan_candidates(cls.positive_raw, cls.positive_run)

    def test_simple_complete_coverage_and_actual_action_counts(self):
        """Initial and committed-trial states both belong to the inventory."""
        checked = check_candidate_scan(self.raw, self.small_run, self.scan)
        self.assertTrue(checked['passed'])
        self.assertEqual(checked['persistent_states_checked'], 2)
        self.assertEqual(checked['target_count'], 3)
        self.assertEqual(checked['oracle_records'], 4)
        self.assertEqual(checked['summary']['action_counts']['actual_commit']['supported'], 1)
        self.assertEqual(checked['summary']['action_counts']['not_selected']['supported'], 2)
        self.assertEqual(checked['summary']['no_target_state_count'], 1)
        self.assertEqual(self.small_run['phases'][self.scan['states'][1]['phase']]['kind'], 'trial')

    def test_rejection_trial_excluded_but_post_rejection_state_included(self):
        """The known diagnostic distinguishes nonpersistent rejection from commitment."""
        checked = check_candidate_scan(self.lifted_raw, self.lifted_run, self.lifted_scan)
        rejected = [event for event in self.lifted_run['events'] if event['kind'] == 'reject']
        self.assertTrue(rejected)
        phases = {state['phase'] for state in self.lifted_scan['states']}
        for event in rejected:
            self.assertNotIn(event['trial_phase'], phases)
            self.assertIn(event['after_phase'], phases)
        self.assertGreater(checked['summary']['target_status_counts']['preexisting_unsat'], 0)
        self.assertGreater(checked['summary']['conditional_counts']['conditional_inconclusive'], 0)

    def test_conditional_refutation_is_replayed_without_updating_producer(self):
        """Candidates omitted by EQ in a later version are valid old-rule diagnostics."""
        before = deepcopy(self.c5_run)
        checked = check_candidate_scan(self.c5_raw, self.c5_run, self.c5_scan)
        self.assertGreater(checked['conditional_probes_checked'], 0)
        self.assertGreater(checked['summary']['conditional_counts']['conditional_refuted'], 0)
        self.assertEqual(before, self.c5_run)

    def test_missing_inventory_or_saved_target_is_rejected(self):
        """Deleting one bad-looking target cannot improve the reported support rate."""
        for section in ('inventory', 'states'):
            bad = deepcopy(self.scan)
            states = bad['inventory']['states'] if section == 'inventory' else bad['states']
            states[0]['targets'].pop()
            with self.subTest(section=section), self.assertRaises((AssertionError, ValueError)):
                check_candidate_scan(self.raw, self.small_run, bad)

    def test_missing_or_duplicate_persistent_state_is_rejected(self):
        """Every after-phase is counted exactly once, including terminal states."""
        for mutation in ('drop', 'duplicate'):
            bad = deepcopy(self.scan)
            if mutation == 'drop':
                bad['states'].pop()
            else:
                bad['states'].append(deepcopy(bad['states'][-1]))
            with self.subTest(mutation=mutation), self.assertRaises((AssertionError, ValueError)):
                check_candidate_scan(self.raw, self.small_run, bad)

    def test_category_and_actual_action_cannot_be_relabelled(self):
        """An off-schedule candidate and the next actual low-color action stay distinct."""
        for field, value in (('category', 'other_side_min'), ('action', 'not_selected'),
                             ('symbol', 3), ('side_index', True)):
            bad = deepcopy(self.scan)
            bad['states'][0]['targets'][0][field] = value
            with self.subTest(field=field), self.assertRaises((AssertionError, ValueError)):
                check_candidate_scan(self.raw, self.small_run, bad)

    def test_valid_extra_inferred_anchor_certificate_is_rejected(self):
        """Even a true inferred E=1 must not become an oracle premise."""
        bad = deepcopy(self.odd_scan)
        reference = bad['states'][0]['base_oracle_index']
        record = bad['oracle_records'][reference]
        n, edges = record['input']['n'], record['input']['edges']
        fixed = dict(record['input']['anchors'])
        self.assertNotIn(1, fixed)
        fixed[1] = 1
        evidence = solve_exact(n, edges, fixed, node_limit=bad['node_limit'])
        self.assertEqual(evidence['status'], 'sat')
        record.update(input={'n': n, 'edges': edges, 'anchors': [list(p) for p in sorted(fixed.items())]},
                      result=evidence, verification=verify_exact_result(n, edges, fixed, evidence))
        with self.assertRaisesRegex(ValueError, 'commitment and candidate binding'):
            check_candidate_scan(self.c5_raw, self.odd_run, bad)

    def test_raw_neq_graph_and_extra_oracle_premises_are_bound(self):
        """An oracle cannot silently use the augmented graph or supplied state words."""
        mutations = (
            lambda data: data['edges'].clear(),
            lambda data: data.update(equal_names=[['A', 'B']]),
            lambda data: data.update(different_names=[['A', 'B']]),
            lambda data: data.update(states={'B': '0200'}),
            lambda data: data.update(n=True),
        )
        for mutate in mutations:
            bad = deepcopy(self.scan)
            mutate(bad['oracle_records'][0]['input'])
            with self.subTest(mutate=mutate), self.assertRaises((AssertionError, ValueError)):
                check_candidate_scan(self.raw, self.small_run, bad)

    def test_reference_must_name_exact_candidate_premises(self):
        """A valid neighboring candidate witness cannot stand for this target."""
        bad = deepcopy(self.scan)
        targets = bad['states'][0]['targets']
        targets[0]['candidate_oracle_index'] = targets[1]['candidate_oracle_index']
        with self.assertRaisesRegex(ValueError, 'commitment and candidate binding'):
            check_candidate_scan(self.raw, self.small_run, bad)

    def test_unused_unique_oracle_record_is_rejected(self):
        """Hidden extra searches cannot disappear from the declared query inventory."""
        bad = deepcopy(self.scan)
        n, edges, fixed = 2, [[0, 1]], {}
        evidence = solve_exact(n, edges, fixed, node_limit=bad['node_limit'])
        bad['oracle_records'].append({'input': {'n': n, 'edges': edges, 'anchors': []},
                                      'result': evidence,
                                      'verification': verify_exact_result(n, edges, fixed, evidence)})
        with self.assertRaisesRegex(ValueError, 'unused'):
            check_candidate_scan(self.raw, self.small_run, bad)

    def test_duplicate_query_record_is_rejected(self):
        """Query deduplication is verified rather than trusted as telemetry."""
        bad = deepcopy(self.scan)
        bad['oracle_records'].append(deepcopy(bad['oracle_records'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicate exact query'):
            check_candidate_scan(self.raw, self.small_run, bad)

    def test_valid_but_different_conditional_probe_is_rejected(self):
        """A sound proof under another candidate is not evidence for this one."""
        bad = deepcopy(self.c5_scan)
        target = next(target for state in bad['states'] for target in state['targets']
                      if target['status'] == 'unsupported')
        conditional = target['conditional']
        proposal = deepcopy(conditional['input'])
        proposal['anchors'][target['side']] = next(color for color in (2, 3, 4)
                                                 if color != target['symbol'])
        outcome = propagate_logical_contacts(proposal)
        conditional.update(input=proposal, outcome=outcome,
                           trace_audit=audit_logical_contacts(proposal, outcome))
        with self.assertRaisesRegex(ValueError, 'conditional persistent phase'):
            check_candidate_scan(self.c5_raw, self.c5_run, bad)

    def test_conditional_trace_and_classification_cannot_be_forged(self):
        """Unsupported exact evidence is separate from a replayable local refutation."""
        for mutation in ('drop_probe', 'wrong_status', 'bad_trace'):
            bad = deepcopy(self.c5_scan)
            target = next(target for state in bad['states'] for target in state['targets']
                          if target['status'] == 'unsupported')
            if mutation == 'drop_probe':
                target['conditional'] = None
            elif mutation == 'wrong_status':
                target['conditional']['status'] = 'conditional_inconclusive'
            else:
                target['conditional']['outcome']['trace'][0]['after'] ^= 1
            with self.subTest(mutation=mutation), self.assertRaises((AssertionError, ValueError)):
                check_candidate_scan(self.c5_raw, self.c5_run, bad)

    def test_unknown_is_not_an_unsupported_candidate(self):
        """A zero-node budget validates an undecided schema, never an UNSAT claim."""
        scan = scan_candidates(self.raw, self.small_run, node_limit=0)
        checked = check_candidate_scan(self.raw, self.small_run, scan, node_limit=0)
        self.assertEqual(checked['summary']['target_status_counts']['unknown'], 3)
        self.assertEqual(checked['summary']['target_status_counts']['unsupported'], 0)
        self.assertEqual(checked['conditional_probes_checked'], 0)
        scan['states'][0]['targets'][0]['status'] = 'unsupported'
        with self.assertRaisesRegex(ValueError, 'support classification'):
            check_candidate_scan(self.raw, self.small_run, scan, node_limit=0)

    def test_preexisting_unsat_is_not_a_new_unsupported_target(self):
        """An already failed prefix cannot be counted as a candidate-caused failure."""
        bad = deepcopy(self.lifted_scan)
        target = next(target for state in bad['states'] for target in state['targets']
                      if target['status'] == 'preexisting_unsat')
        target['status'] = 'unsupported'
        with self.assertRaisesRegex(ValueError, 'support classification'):
            check_candidate_scan(self.lifted_raw, self.lifted_run, bad)

    def test_unknown_base_stays_unknown_even_when_child_is_sat(self):
        """A shorter child search cannot establish the unproved prefix classification."""
        raw = {'sides': ['A', 'B'], 'lines': []}
        run = solve_logical_contacts(raw, decision_limit=0)
        scan = scan_candidates(raw, run, node_limit=2)
        base = scan['oracle_records'][scan['states'][0]['base_oracle_index']]['result']
        self.assertEqual(base['status'], 'unknown')
        self.assertTrue(all(scan['oracle_records'][target['candidate_oracle_index']]['result']['status']
                            == 'sat' for target in scan['states'][0]['targets']))
        checked = check_candidate_scan(raw, run, scan, node_limit=2)
        self.assertEqual(checked['summary']['target_status_counts']['unknown'], 8)
        scan['states'][0]['targets'][0]['status'] = 'supported'
        with self.assertRaisesRegex(ValueError, 'support classification'):
            check_candidate_scan(raw, run, scan, node_limit=2)

    def test_resource_limited_final_state_has_no_predicted_actual_action(self):
        """A stopped run's unresolved targets are all off-schedule observations."""
        run = solve_logical_contacts(self.raw, decision_limit=0)
        scan = scan_candidates(self.raw, run)
        checked = check_candidate_scan(self.raw, run, scan)
        self.assertEqual(checked['persistent_states_checked'], 1)
        self.assertEqual(checked['summary']['action_counts']['actual_commit']['supported'], 0)
        self.assertEqual(checked['summary']['category_counts']['other_side_min']['supported'], 1)
        self.assertEqual(checked['summary']['category_counts']['other_side_other']['supported'], 2)

    def test_saved_checker_calls_no_search_producer_or_propagator(self):
        """Literal trace and exact-certificate replay suffice, including bad candidates."""
        forbidden = AssertionError('saved checker attempted recomputation')
        with patch('scripts.quaternary_logical_neq_candidate_scan.solve_exact', side_effect=forbidden), \
                patch('scripts.exact_extendibility_oracle.solve_exact', side_effect=forbidden), \
                patch('scripts.audit_quaternary_logical_neq.solve_exact', side_effect=forbidden), \
                patch('scripts.quaternary_logical_neq_candidate_scan.propagate_logical_contacts', side_effect=forbidden), \
                patch('scripts.quaternary_logical_neq_contacts.propagate_logical_contacts', side_effect=forbidden), \
                patch('scripts.quaternary_logical_neq_low_color.propagate_logical_contacts', side_effect=forbidden), \
                patch('scripts.quaternary_logical_neq_low_color.solve_logical_contacts', side_effect=forbidden):
            checked = check_candidate_scan(self.c5_raw, self.c5_run, self.c5_scan)
        self.assertEqual(checked['producer_runs'], 0)
        self.assertEqual(checked['oracle_searches'], 0)
        self.assertEqual(checked['propagation_runs'], 0)

    def test_summary_and_premise_modes_cannot_be_forged(self):
        """Aggregate success labels and offline mode are independently enforced."""
        mutations = (
            lambda bad: bad['summary'].__setitem__('target_count', 0),
            lambda bad: bad.__setitem__('oracle_feedback_to_producer', True),
            lambda bad: bad.__setitem__('node_limit', 1),
            lambda bad: bad.__setitem__('schema_version', True),
        )
        for mutate in mutations:
            bad = deepcopy(self.scan)
            mutate(bad)
            with self.subTest(mutate=mutate), self.assertRaises((AssertionError, ValueError)):
                check_candidate_scan(self.raw, self.small_run, bad)

    def test_persistent_phase_or_commitment_tampering_is_rejected(self):
        """Inventory checks do not trust the producer's after-phase labels blindly."""
        for mutate in (
            lambda run: run['events'][0].__setitem__('after_phase', 0),
            lambda run: run['phases'][1]['document']['anchors'].__setitem__('B', 3),
            lambda run: run['events'][0].__setitem__('before_phase', True),
            lambda run: run['events'][0].__setitem__('kind', 'reject'),
        ):
            bad = deepcopy(self.small_run)
            mutate(bad)
            with self.subTest(mutate=mutate), self.assertRaises((AssertionError, ValueError)):
                check_candidate_scan(self.raw, bad, self.scan)

    def test_learned_neq_is_kept_logical_and_absent_from_exact_premises(self):
        """A certified nonedge stays a relation even when the oracle would agree."""
        run = self.positive_run
        self.assertIn(['v', 'w'], run['original_input']['different_names'])
        self.assertEqual(run['original_input']['lines'], self.positive_raw['lines'])
        self.assertTrue(check_candidate_scan(self.positive_raw, run, self.positive_scan)['passed'])
        for record in self.positive_scan['oracle_records']:
            self.assertNotIn([4, 5], record['input']['edges'])
            self.assertEqual(set(record['input']), {'n', 'edges', 'anchors'})
        # This alternative certificate is true but its physical graph is wrong.
        bad = deepcopy(self.positive_scan)
        record = bad['oracle_records'][0]
        data = record['input']
        data['edges'] = sorted(data['edges'] + [[4, 5]])
        fixed = dict(data['anchors'])
        result = solve_exact(data['n'], data['edges'], fixed, node_limit=bad['node_limit'])
        record.update(result=result, verification=verify_exact_result(
            data['n'], data['edges'], fixed, result))
        with self.assertRaisesRegex(ValueError, 'original separator edges'):
            check_candidate_scan(self.positive_raw, run, bad)

    def test_logical_relation_cannot_disappear_between_persistent_phases(self):
        """Even an independently replayable weaker trace is not this run's input."""
        bad = deepcopy(self.positive_run)
        phase = bad['phases'][1]
        phase['document'].pop('different_names')
        phase['outcome'] = propagate_logical_contacts(phase['document'])
        with self.assertRaisesRegex(ValueError, 'trial phase assumptions'):
            check_candidate_scan(self.positive_raw, bad, self.positive_scan)

    def test_raw_supplied_constraints_are_rejected_and_empty_old_fields_survive(self):
        """Historical empty containers remain legal; no supplied logic gains authority."""
        raw = {**small_document(), 'states': {}, 'equal_names': []}
        run = solve_logical_neq(raw)['run']
        scan = scan_candidates(raw, run)
        self.assertTrue(check_candidate_scan(raw, run, scan)['passed'])
        for extra in ({'states': {'B': '0111'}}, {'equal_names': [['A', 'B']]},
                      {'different_names': []}, {'different_names': [['A', 'B']]}):
            with self.subTest(extra=extra), self.assertRaises((AssertionError, ValueError)):
                check_candidate_scan({**self.raw, **extra}, self.small_run, self.scan)

    def test_changed_physical_lines_or_unguarded_policy_are_rejected(self):
        """The wrapper-specific scan cannot admit a renamed older producer."""
        for change in ('line', 'probe', 'policy'):
            bad = deepcopy(self.positive_run)
            if change == 'line':
                bad['original_input']['lines'].append(
                    {'id': 'fake', 'left': 'v', 'right': 'w', 'kind': 'separator'})
            elif change == 'probe':
                bad['probe'] = False
            else:
                bad['policy'] = 'quaternary-low-color-conditional-propagation-v1'
            with self.subTest(change=change), self.assertRaises((AssertionError, ValueError)):
                check_candidate_scan(self.positive_raw, bad, self.positive_scan)

    def test_bridges_and_point_contacts_never_enter_oracle_edges(self):
        """Same-face bridges and vertex-only touches impose no different-color edge."""
        raw = {'sides': ['A', 'B'], 'anchors': {'A': 1},
               'lines': [{'id': 'bridge', 'left': 'A', 'right': 'A', 'kind': 'bridge'}],
               'point_contacts': [{'sides': ['A', 'B']}]}
        run = solve_logical_neq(raw)['run']
        scan = scan_candidates(raw, run)
        checked = check_candidate_scan(raw, run, scan)
        self.assertEqual(checked['summary']['target_status_counts']['unsupported'], 0)
        self.assertTrue(all(record['input']['edges'] == [] for record in scan['oracle_records']))

    def test_checker_imports_no_scanner_and_rebuilds_inventory_without_it(self):
        """The checker owns its state traversal rather than importing producer inventory."""
        path = Path(__file__).resolve().parents[1] / 'scripts' / 'check_quaternary_logical_neq_candidate_scan.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        self.assertFalse(any('quaternary_logical_neq_candidate_scan' in (node.module or '')
                             for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)))
        with patch('scripts.quaternary_logical_neq_candidate_scan.candidate_inventory',
                   side_effect=AssertionError('shared state reconstruction')):
            checked = check_candidate_scan(self.positive_raw, self.positive_run, self.positive_scan)
        self.assertTrue(checked['passed'])

    def test_conditional_probe_replays_with_preserved_logical_neq_field(self):
        """An inner-loop control exercises conditional replay with logical metadata.

        The redundant pair is already a physical edge. This is deliberately a
        contact-language control, not a claim that the wrapper learner emits it.
        """
        augmented = {**deepcopy(self.c5_raw), 'different_names': [['B0', 'B1']]}
        run = solve_logical_contacts(augmented)
        scan = scan_candidates(self.c5_raw, run)
        checked = check_candidate_scan(self.c5_raw, run, scan)
        self.assertGreater(checked['conditional_probes_checked'], 0)
        target = next(target for state in scan['states'] for target in state['targets']
                      if target['status'] == 'unsupported')
        self.assertEqual(target['conditional']['input']['different_names'], [['B0', 'B1']])
        bad = deepcopy(scan)
        target = next(target for state in bad['states'] for target in state['targets']
                      if target['status'] == 'unsupported')
        # Echo-only tampering is caught by the independent logical trace auditor.
        target['conditional']['outcome']['different_names'] = []
        with self.assertRaisesRegex(AssertionError, 'logical NEQ echo'):
            check_candidate_scan(self.c5_raw, run, bad)


if __name__ == '__main__':
    unittest.main()


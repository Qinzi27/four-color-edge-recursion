"""Tamper tests for independent, resumable raw support evidence replay."""

import ast
from copy import deepcopy
from itertools import combinations
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import check_quaternary_triangle_saturation_support_scan as checker
from scripts.exact_extendibility_oracle import solve_exact, verify_exact_result
from scripts.quaternary_triangle_saturation_low_color import solve_saturation_contacts
from scripts.quaternary_triangle_saturation_support_scan import scan_support, support_inventory
from tests.test_check_quaternary_logical_neq_pair_scan import path_document, bipyramid_document
from tests.test_quaternary_triangle_saturation_contacts import raw_saturation_trial_document


def evidence_sources(scan):
    """Small synthetic archives retain exact bodies and explicit source identities."""
    pools = []
    for plural, singular in (('oracle_records', 'record'), ('conditional_records', 'conditional')):
        pools.append([{'source': {'checkpoint_sha256': 'unit-synthetic', 'kind': singular, 'index': i},
                       singular: {k: deepcopy(v) for k, v in record.items() if k != 'origin'}}
                      for i, record in enumerate(scan[plural])])
    return pools


class CheckTriangleSaturationSupportScanTests(unittest.TestCase):
    """Small abstract controls are not new formal geometry experiment inputs."""

    @classmethod
    def setUpClass(cls):
        """Generate tiny valid artifacts once before isolation/tampering checks."""
        cls.raw = path_document()
        cls.saved_run = solve_saturation_contacts(cls.raw)
        cls.scan = scan_support(cls.raw, cls.saved_run)
        cls.bp_raw = bipyramid_document()
        cls.bp_run = solve_saturation_contacts(cls.bp_raw, decision_limit=0)
        cls.bp_scan = scan_support(cls.bp_raw, cls.bp_run)
        cls.oracle_sources, cls.conditional_sources = evidence_sources(cls.bp_scan)
        cls.reused = scan_support(cls.bp_raw, cls.bp_run,
                                  oracle_sources=cls.oracle_sources,
                                  conditional_sources=cls.conditional_sources)

    def rejected(self, scan, *, raw=None, run=None, **kwargs):
        """Assertion and schema failures both reject scientific evidence."""
        with self.assertRaises((AssertionError, ValueError)):
            checker.check_support_scan(raw or self.raw, run or self.saved_run, scan, **kwargs)

    def first_pair_gap(self, scan):
        """Return a genuine joint obstruction, not a merely unchosen pair."""
        return next(t for s in scan['states'] for t in s['pair_targets'] if t['status'] == 'unsupported')

    def test_complete_inventory_and_independent_reconstruction(self):
        """Domains enumerate unary targets; matrix bits restrict binary targets."""
        checked = checker.check_support_scan(self.raw, self.saved_run, self.scan)
        self.assertTrue(checked['passed'])
        self.assertEqual(checker.support_inventory(self.raw, self.saved_run), support_inventory(self.raw, self.saved_run))
        self.assertEqual(checked['pair_targets_checked'], 9)
        self.assertEqual(checked['summary']['cartesian_target_count'], 12)
        self.assertEqual(checked['summary']['pair']['next_action_counts']['includes_next_commit']['supported'], 3)
        self.assertGreater(checked['summary']['no_pair_target_state_count'], 0)

    def test_joint_obstruction_retains_two_single_witnesses(self):
        """The two apices are individually free but cannot receive unequal colors."""
        checked = checker.check_support_scan(self.bp_raw, self.bp_run, self.bp_scan)
        self.assertEqual(checked['summary']['pair']['status_counts']['unsupported'], 12)
        self.assertEqual(checked['summary']['pair']['single_support_counts']['both_supported'], 12)
        self.assertEqual(checked['summary']['single']['status_counts']['unsupported'], 0)
        self.assertEqual(checked['conditional_records_checked'], 12)
        self.assertEqual(checked['single_endpoint_queries_checked'], 24)

    def test_reuse_binds_full_sources_and_replays_each_unique_record_once(self):
        """More obligation references never multiply expensive certificate replays."""
        with (patch.object(checker, 'verify_exact_result', wraps=verify_exact_result) as exact,
              patch.object(checker, 'audit_saturation_contacts', wraps=checker.audit_saturation_contacts) as audits):
            checked = checker.check_support_scan(self.bp_raw, self.bp_run, self.reused,
                oracle_sources=self.oracle_sources, conditional_sources=self.conditional_sources)
        self.assertEqual(exact.call_count, len(self.reused['oracle_records']))
        self.assertEqual(audits.call_count, len(self.reused['conditional_records']))
        self.assertEqual(checked['summary']['oracle_origin_counts']['new'], 0)
        self.assertEqual(checked['summary']['conditional_origin_counts']['new'], 0)

    def test_missing_false_or_relabelled_reuse_origin_is_rejected(self):
        """Content reuse is tracked separately from a newly computed result."""
        for name in ('oracle_records', 'conditional_records'):
            for origin in (None, {'checkpoint_sha256': 'wrong'}, True):
                bad = deepcopy(self.reused)
                bad[name][0]['origin'] = origin
                with self.subTest(name=name, origin=origin):
                    self.rejected(bad, raw=self.bp_raw, run=self.bp_run,
                                  oracle_sources=self.oracle_sources, conditional_sources=self.conditional_sources)

    def test_absent_source_cannot_claim_reuse_and_present_source_cannot_claim_new(self):
        """A provenance locator alone is not the archived result body."""
        self.rejected(self.reused, raw=self.bp_raw, run=self.bp_run)
        self.rejected(self.bp_scan, raw=self.bp_raw, run=self.bp_run,
                      oracle_sources=self.oracle_sources, conditional_sources=self.conditional_sources)

    def test_first_matching_source_is_deterministic(self):
        """An otherwise equivalent later locator cannot change the frozen reuse choice."""
        sources = deepcopy(self.oracle_sources)
        duplicate = deepcopy(sources[0])
        duplicate['source']['index'] = 'later-equivalent'
        sources.append(duplicate)
        checked = checker.check_support_scan(self.bp_raw, self.bp_run, self.reused,
                    oracle_sources=sources, conditional_sources=self.conditional_sources)
        self.assertTrue(checked['passed'])
        bad = deepcopy(self.reused)
        bad['oracle_records'][0]['origin'] = duplicate['source']
        self.rejected(bad, raw=self.bp_raw, run=self.bp_run,
                      oracle_sources=sources, conditional_sources=self.conditional_sources)

    def test_ambiguous_locator_and_changed_source_evidence_are_rejected(self):
        """Identical locator text cannot bind two different archived query bodies."""
        sources = deepcopy(self.oracle_sources)
        duplicate = deepcopy(sources[1])
        duplicate['source'] = deepcopy(sources[0]['source'])
        sources.append(duplicate)
        self.rejected(self.reused, raw=self.bp_raw, run=self.bp_run,
                      oracle_sources=sources, conditional_sources=self.conditional_sources)
        sources = deepcopy(self.oracle_sources)
        sources[0]['record']['result']['nodes'] += 1
        self.rejected(self.reused, raw=self.bp_raw, run=self.bp_run,
                      oracle_sources=sources, conditional_sources=self.conditional_sources)

    def test_unused_source_pool_is_allowed_but_unused_saved_evidence_is_not(self):
        """Historical pool coverage is not confused with current scan coverage."""
        sources = deepcopy(self.oracle_sources)
        sources.append({'source': {'unused': 1}, 'record': deepcopy(evidence_sources(self.scan)[0][0]['record'])})
        checked = checker.check_support_scan(self.bp_raw, self.bp_run, self.reused,
                    oracle_sources=sources, conditional_sources=self.conditional_sources)
        self.assertTrue(checked['passed'])
        bad = deepcopy(self.scan)
        result = solve_exact(3, [(0, 1), (1, 2)], {}, node_limit=200000)
        bad['oracle_records'].append({'input': {'n': 3, 'edges': [[0, 1], [1, 2]], 'anchors': []},
                                     'result': result, 'verification': verify_exact_result(
                                         3, [(0, 1), (1, 2)], {}, result), 'origin': None})
        self.rejected(bad)

    def test_missing_extra_or_duplicate_obligations_are_rejected(self):
        """Coverage is checked against an independently rebuilt ordered inventory."""
        for field in ('single_targets', 'pair_targets'):
            for section in ('states', 'inventory'):
                for operation in ('drop', 'duplicate'):
                    bad = deepcopy(self.scan)
                    states = bad['states'] if section == 'states' else bad['inventory']['states']
                    if operation == 'drop':
                        states[0][field].pop()
                    else:
                        states[0][field].append(deepcopy(states[0][field][0]))
                    with self.subTest(field=field, section=section, operation=operation):
                        self.rejected(bad)
        bad = deepcopy(self.scan)
        bad['states'].pop()
        self.rejected(bad)

    def test_false_target_direction_category_and_boolean_identity_are_rejected(self):
        """Asymmetric B/C domains make direction mistakes observably different."""
        for field, value in (('symbols', [1, 2]), ('side_indices', [2, 1]),
                             ('side_indices', [True, 2]), ('sides', ['C', 'B']),
                             ('category', 'neither_min'), ('next_action', 'not_next_choice')):
            bad = deepcopy(self.scan)
            bad['states'][0]['pair_targets'][0][field] = value
            with self.subTest(field=field):
                self.rejected(bad)
        for field, value in (('side_index', True), ('symbol', True), ('action', 'not_selected')):
            bad = deepcopy(self.scan)
            bad['states'][0]['single_targets'][0][field] = value
            self.rejected(bad)

    def test_matrix_schema_direction_domain_and_state_hash_are_checked(self):
        """Same final coloring does not validate altered intermediate relations."""
        for mutation in ('boolean', 'transpose', 'diagonal', 'outside', 'hash'):
            run, scan = deepcopy(self.saved_run), deepcopy(self.scan)
            matrix = run['phases'][0]['outcome']['relations']
            if mutation == 'boolean':
                matrix[1][2] = True
            elif mutation == 'transpose':
                matrix[1][2] ^= 1 << 4
            elif mutation == 'diagonal':
                matrix[1][1] ^= 1
            elif mutation == 'outside':
                matrix[1][2] |= 1 << 1
                matrix[2][1] |= 1 << 4
            else:
                scan['states'][0]['relations_sha256'] = 'same-final-colors'
            with self.subTest(mutation=mutation):
                self.rejected(scan, run=run)

    def test_raw_oracle_premises_forbid_logical_edges_and_extra_restrictions(self):
        """Even true derived restrictions would query a different raw problem."""
        for field, value in (('edges', []), ('n', True), ('equal_names', []),
                             ('different_names', [['B', 'C']]), ('states', {'B': '0200'})):
            bad = deepcopy(self.scan)
            bad['oracle_records'][0]['input'][field] = value
            self.rejected(bad)

    def test_extra_anchor_cannot_strengthen_a_valid_raw_base_witness(self):
        """A genuine certificate for stronger premises cannot replace this base."""
        bad = deepcopy(self.scan)
        record = bad['oracle_records'][bad['states'][0]['base_oracle_index']]
        data = record['input']
        fixed = {0: 1, 2: 1}
        data['anchors'] = [[0, 1], [2, 1]]
        result = solve_exact(data['n'], data['edges'], fixed, node_limit=200000)
        record.update(result=result, verification=verify_exact_result(data['n'], data['edges'], fixed, result))
        self.rejected(bad)

    def test_one_endpoint_certificate_cannot_replace_joint_query_or_reverse(self):
        """Unary SAT and binary UNSAT coexist, so references must remain precise."""
        bad = deepcopy(self.bp_scan)
        target = self.first_pair_gap(bad)
        target['pair_oracle_index'] = target['single_oracle_indices'][0]
        self.rejected(bad, raw=self.bp_raw, run=self.bp_run)
        bad = deepcopy(self.bp_scan)
        target = self.first_pair_gap(bad)
        target['single_oracle_indices'][0] = target['pair_oracle_index']
        self.rejected(bad, raw=self.bp_raw, run=self.bp_run)

    def test_missing_endpoint_diagnosis_or_condition_is_rejected(self):
        """All proved unsupported pairs retain raw unary and structural diagnoses."""
        for field, value in (('conditional_index', None), ('single_oracle_indices', None),
                             ('single_oracle_indices', [0]), ('single_support', 'unknown_single')):
            bad = deepcopy(self.bp_scan)
            self.first_pair_gap(bad)[field] = value
            self.rejected(bad, raw=self.bp_raw, run=self.bp_run)

    def test_conditional_trace_input_status_and_audit_are_bound(self):
        """Stored refutation labels cannot replace an independently replayed trace."""
        for mutation in ('input', 'outcome', 'status', 'audit'):
            bad = deepcopy(self.bp_scan)
            conditional = bad['conditional_records'][0]
            if mutation == 'input':
                conditional['input']['anchors'].clear()
            elif mutation == 'outcome':
                conditional['outcome']['triangle_saturation']['rounds'].clear()
            elif mutation == 'status':
                conditional['status'] = 'conditional_inconclusive'
            else:
                conditional['trace_audit']['trace_steps_checked'] = 0
            with self.subTest(mutation=mutation):
                self.rejected(bad, raw=self.bp_raw, run=self.bp_run)

    def test_duplicate_query_or_conditional_evidence_is_rejected(self):
        """Each exact/conditional input has one saved record, however many uses."""
        for field in ('oracle_records', 'conditional_records'):
            bad = deepcopy(self.bp_scan)
            bad[field].append(deepcopy(bad[field][0]))
            self.rejected(bad, raw=self.bp_raw, run=self.bp_run)

    def test_supported_targets_do_not_receive_failure_diagnostics(self):
        """Conditional and endpoint fields are reserved for proven unsupported rows."""
        for field, value in (('single_oracle_indices', [0, 1]), ('single_support', 'both_supported'),
                             ('conditional_index', 0)):
            bad = deepcopy(self.scan)
            bad['states'][0]['pair_targets'][0][field] = value
            self.rejected(bad)
        bad = deepcopy(self.scan)
        bad['states'][0]['single_targets'][0]['conditional_index'] = 0
        self.rejected(bad)

    def test_unknown_base_is_not_promoted_by_a_conclusive_child(self):
        """All-fixed children can be SAT within one node while their base is UNKNOWN."""
        raw = {'sides': ['A', 'B'], 'lines': []}
        run = solve_saturation_contacts(raw, decision_limit=0)
        scan = scan_support(raw, run, node_limit=1)
        checked = checker.check_support_scan(raw, run, scan, node_limit=1)
        self.assertEqual(checked['summary']['base_status_counts']['unknown'], 1)
        self.assertEqual(checked['summary']['pair']['status_counts']['unknown'], 16)
        self.assertTrue(all(scan['oracle_records'][t['pair_oracle_index']]['result']['status'] == 'sat'
                            for t in scan['states'][0]['pair_targets']))
        scan['states'][0]['pair_targets'][0]['status'] = 'supported'
        self.rejected(scan, raw=raw, run=run, node_limit=1)

    def test_zero_budget_unknown_does_not_trigger_propagation(self):
        """Resource exhaustion remains explicit, never an inferred contradiction."""
        scan = scan_support(self.raw, self.saved_run, node_limit=0)
        checked = checker.check_support_scan(self.raw, self.saved_run, scan, node_limit=0)
        self.assertGreater(checked['summary']['single']['status_counts']['unknown'], 0)
        self.assertGreater(checked['summary']['pair']['status_counts']['unknown'], 0)
        self.assertEqual(checked['conditional_records_checked'], 0)

    def test_preexisting_unsat_is_not_reported_as_a_new_unsafe_candidate(self):
        """Abstract K5 tests classification, not geometric realizability."""
        sides = list('ABCDE')
        raw = {'sides': sides, 'lines': [{'id': str(k), 'left': a, 'right': b, 'kind': 'separator'}
                                      for k, (a, b) in enumerate(combinations(sides, 2))]}
        run = solve_saturation_contacts(raw, decision_limit=0)
        scan = scan_support(raw, run)
        checked = checker.check_support_scan(raw, run, scan)
        self.assertEqual(checked['summary']['base_status_counts']['unsat'], 1)
        self.assertEqual(checked['summary']['single']['status_counts']['preexisting_unsat'], 20)
        self.assertEqual(checked['summary']['pair']['status_counts']['preexisting_unsat'], 120)
        self.assertEqual(checked['conditional_records_checked'], 0)

    def test_rejected_trials_are_excluded_but_post_rejection_state_is_bound(self):
        """A genuine raw fixture checks the chain without a full costly scan."""
        raw = raw_saturation_trial_document()
        run = solve_saturation_contacts(raw, probe_limit=1)
        inventory = checker.support_inventory(raw, run)
        reject = run['events'][0]
        self.assertEqual(reject['kind'], 'reject')
        phases = [state['phase'] for state in inventory['states']]
        self.assertNotIn(reject['trial_phase'], phases)
        self.assertIn(reject['after_phase'], phases)
        self.assertEqual(inventory['states'][0]['anchors'], inventory['states'][1]['anchors'])
        bad = deepcopy(run)
        bad['phases'][reject['after_phase']]['document']['anchors']['P'] = 1
        with self.assertRaises((AssertionError, ValueError)):
            checker.support_inventory(raw, bad)

    def test_event_chain_and_policy_cannot_be_relabelled(self):
        """Counts and final colors do not substitute for actual prefix history."""
        for mutation in ('phase', 'anchors', 'kind', 'guard', 'policy'):
            run = deepcopy(self.saved_run)
            if mutation == 'phase':
                run['events'][0]['after_phase'] = 0
            elif mutation == 'anchors':
                run['phases'][1]['document']['anchors']['B'] = 3
            elif mutation == 'kind':
                run['events'][0]['kind'] = 'reject'
            elif mutation == 'guard':
                run['probe'] = False
            else:
                run['policy'] = 'quaternary-low-color-logical-neq-conditional-v1'
            self.rejected(self.scan, run=run)

    def test_saved_certificate_witness_budget_verification_and_summary_are_checked(self):
        """Explicit labels, counters and limits cannot validate a false witness."""
        for mutation in ('witness', 'budget', 'verification', 'summary', 'feedback'):
            bad = deepcopy(self.scan)
            if mutation == 'witness':
                bad['oracle_records'][0]['result']['witness'] = [1, 1, 1]
            elif mutation == 'budget':
                bad['oracle_records'][0]['result']['node_limit'] = 1
            elif mutation == 'verification':
                bad['oracle_records'][0]['verification']['passed'] = False
            elif mutation == 'summary':
                bad['summary']['single']['target_count'] = 0
            else:
                bad['oracle_feedback_to_producer'] = True
            self.rejected(bad)

    def test_saved_check_calls_no_producer_propagator_or_search(self):
        """The saved check remains executable with all generating paths disabled."""
        names = [
            'scripts.exact_extendibility_oracle.solve_exact',
            'scripts.quaternary_triangle_saturation_support_scan.scan_support',
            'scripts.quaternary_triangle_saturation_support_scan.support_inventory',
            'scripts.quaternary_triangle_saturation_support_scan.solve_exact',
            'scripts.quaternary_triangle_saturation_support_scan.propagate_saturation_contacts',
            'scripts.quaternary_triangle_saturation_contacts.propagate_saturation_contacts',
            'scripts.quaternary_triangle_saturation_low_color.solve_triangle_saturation',
            'scripts.quaternary_triangle_saturation_low_color.solve_saturation_contacts',
        ]
        from contextlib import ExitStack
        with ExitStack() as stack:
            for name in names:
                stack.enter_context(patch(name, side_effect=AssertionError('forbidden generating call')))
            checked = checker.check_support_scan(self.bp_raw, self.bp_run, self.reused,
                oracle_sources=self.oracle_sources, conditional_sources=self.conditional_sources)
        self.assertEqual([checked[k] for k in ('producer_runs', 'oracle_searches', 'propagation_runs')], [0, 0, 0])

    def test_checker_does_not_import_the_producer_inventory_or_searcher(self):
        """Import-level independence prevents accidental scanner self-verification."""
        source = Path(checker.__file__).read_text(encoding='utf-8')
        tree = ast.parse(source)
        imported = [node.module or '' for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertFalse(any(name.endswith('quaternary_triangle_saturation_support_scan') for name in imported))
        names = [alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names]
        self.assertNotIn('solve_exact', names)
        self.assertNotIn('propagate_saturation_contacts', names)


if __name__ == '__main__':
    unittest.main()

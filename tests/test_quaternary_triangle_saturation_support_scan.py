"""Synthetic support/reuse calibration, separate from the frozen map corpus."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts.exact_extendibility_oracle import verify_exact_result
from scripts.quaternary_triangle_saturation_low_color import (
    solve_saturation_contacts, solve_triangle_saturation,
)
from scripts.quaternary_triangle_saturation_support_scan import scan_support, support_inventory
from tests.test_quaternary_logical_neq_candidate_scan import contact_document, pentagonal_bipyramid
from tests.test_quaternary_logical_neq_pair_scan import triangular_bipyramid


def oracle_sources(scan, label='saved'):
    """Turn a synthetic completed census into provenance-marked source records."""
    return [{'source': {'fixture': label, 'record_index': i},
             'record': {k: deepcopy(v) for k, v in record.items() if k != 'origin'}}
            for i, record in enumerate(scan['oracle_records'])]


def conditional_sources(scan, label='saved'):
    """Save conditional input/outcome/audit without pretending it is production."""
    return [{'source': {'fixture': label, 'conditional_index': i},
             'conditional': {k: deepcopy(v) for k, v in record.items() if k != 'origin'}}
            for i, record in enumerate(scan['conditional_records'])]


class TriangleSaturationSupportScanTests(unittest.TestCase):
    """A reused certificate must answer exactly the newly enumerated question."""

    @classmethod
    def setUpClass(cls):
        """Calibrate a small joint obstruction without running a formal input."""
        cls.raw = triangular_bipyramid()
        # Deliberately omit wrapper learning to retain the diagnostic A/E gap.
        # This is not a failure claim about the frozen wrapper population.
        cls.saved_run = solve_saturation_contacts(cls.raw, decision_limit=0)
        cls.scan = scan_support(cls.raw, cls.saved_run)
        cls.oracles = oracle_sources(cls.scan)
        cls.conditionals = conditional_sources(cls.scan)

    def test_inventory_contains_single_and_matrix_allowed_pair_obligations(self):
        """Four colors per side do not make physical same-color pairs allowed."""
        state = self.scan['inventory']['states'][0]
        self.assertEqual(len(state['single_targets']), 20)
        self.assertEqual(len(state['pair_targets']), 124)
        self.assertEqual(state['eligible_side_pair_count'], 10)
        self.assertEqual(state['cartesian_target_count'], 160)
        self.assertFalse(any(t['sides'] == ['A', 'B'] and t['symbols'] == [1, 1]
                             for t in state['pair_targets']))
        self.assertTrue(all(t['side_indices'][0] < t['side_indices'][1]
                            for t in state['pair_targets']))

    def test_joint_obstruction_is_separate_from_supported_single_endpoints(self):
        """Different apex colors extend alone but not as a conjunction."""
        summary = self.scan['summary']
        self.assertEqual(summary['single']['status_counts']['supported'], 20)
        self.assertEqual(summary['pair']['status_counts']['unsupported'], 12)
        self.assertEqual(summary['pair']['single_support_counts']['both_supported'], 12)
        self.assertEqual(summary['conditional_status_counts']['conditional_refuted'], 12)
        self.assertEqual(summary['oracle_record_count'], 145)

    def test_reuse_skips_search_and_propagation_and_keeps_origins(self):
        """Both exact and conditional sources are replayed, not regenerated."""
        with patch('scripts.quaternary_triangle_saturation_support_scan.solve_exact',
                   side_effect=AssertionError('unexpected new search')), \
             patch('scripts.quaternary_triangle_saturation_support_scan.propagate_saturation_contacts',
                   side_effect=AssertionError('unexpected propagation')):
            scan = scan_support(self.raw, self.saved_run, oracle_sources=self.oracles,
                                conditional_sources=self.conditionals)
        self.assertEqual(scan['summary']['oracle_origin_counts'], {'new': 0, 'reused': 145})
        self.assertEqual(scan['summary']['conditional_origin_counts'], {'new': 0, 'reused': 12})
        self.assertEqual(scan['states'], self.scan['states'])
        self.assertTrue(all(r['origin'] is not None for r in scan['oracle_records']))

    def test_only_missing_query_invokes_fresh_search(self):
        """One removed archived record causes exactly one new raw query."""
        from scripts.exact_extendibility_oracle import solve_exact
        with patch('scripts.quaternary_triangle_saturation_support_scan.solve_exact', wraps=solve_exact) as solve:
            scan = scan_support(self.raw, self.saved_run, oracle_sources=self.oracles[1:],
                                conditional_sources=self.conditionals)
        self.assertEqual(solve.call_count, 1)
        self.assertEqual(scan['summary']['oracle_origin_counts'], {'new': 1, 'reused': 144})

    def test_each_used_unique_exact_certificate_is_verified_once(self):
        """Base, singleton and pair references share the scene cache."""
        with patch('scripts.quaternary_triangle_saturation_support_scan.verify_exact_result',
                   wraps=verify_exact_result) as verify:
            scan = scan_support(self.raw, self.saved_run, oracle_sources=self.oracles,
                                conditional_sources=self.conditionals)
        self.assertEqual(verify.call_count, len(scan['oracle_records']))
        signatures = [str(r['input']) for r in scan['oracle_records']]
        self.assertEqual(len(signatures), len(set(signatures)))

    def test_first_matching_source_determines_origin(self):
        """Production/unary/pair pool priority remains deterministic."""
        later = oracle_sources(self.scan, label='later')
        scan = scan_support(self.raw, self.saved_run, oracle_sources=[*self.oracles, *later],
                            conditional_sources=self.conditionals)
        self.assertTrue(all(r['origin']['fixture'] == 'saved' for r in scan['oracle_records']))

    def test_unused_bad_certificate_is_not_replayed(self):
        """Only referenced source bodies receive mathematical verification."""
        unused = deepcopy(self.oracles[0])
        unused['source'] = {'fixture': 'unrelated'}
        unused['record']['input']['n'] = 99
        unused['record']['result'] = {'malformed': True}
        scan = scan_support(self.raw, self.saved_run, oracle_sources=[unused, *self.oracles],
                            conditional_sources=self.conditionals)
        self.assertEqual(scan['summary']['oracle_origin_counts']['new'], 0)

    def test_duplicate_locator_with_different_body_is_rejected(self):
        """An origin cannot ambiguously identify two archived certificates."""
        duplicate = deepcopy(self.oracles[0])
        duplicate['record']['input']['n'] = 99
        with self.assertRaises(AssertionError):
            scan_support(self.raw, self.saved_run, oracle_sources=[*self.oracles, duplicate])

    def test_used_invalid_sat_witness_is_rejected(self):
        """Copying a prior support label cannot bypass witness verification."""
        sources = deepcopy(self.oracles)
        sources[0]['record']['result']['witness'] = [1] * len(self.raw['sides'])
        with self.assertRaises((ValueError, AssertionError)):
            scan_support(self.raw, self.saved_run, oracle_sources=sources)

    def test_used_verification_metadata_is_rechecked(self):
        """A valid result with falsely saved verification is still rejected."""
        sources = deepcopy(self.oracles)
        sources[0]['record']['verification']['passed'] = False
        with self.assertRaises(AssertionError):
            scan_support(self.raw, self.saved_run, oracle_sources=sources)

    def test_wrong_query_premises_do_not_hit_cache(self):
        """A stronger anchor premise cannot support the unchanged base query."""
        from scripts.exact_extendibility_oracle import solve_exact
        sources = deepcopy(self.oracles)
        # All five vertices fixed is outside this state's base/single/pair
        # queries. It must remain unused, however tempting its saved SAT label.
        sources[0]['record']['input']['anchors'] = [[i, 1] for i in range(5)]
        with patch('scripts.quaternary_triangle_saturation_support_scan.solve_exact', wraps=solve_exact) as solve:
            scan_support(self.raw, self.saved_run, oracle_sources=sources,
                         conditional_sources=self.conditionals)
        self.assertEqual(solve.call_count, 1)

    def test_source_node_budget_must_match_requested_budget(self):
        """Resource provenance is not silently normalized during reuse."""
        with self.assertRaises(AssertionError):
            scan_support(self.raw, self.saved_run, node_limit=1, oracle_sources=self.oracles)

    def test_conditional_source_status_and_audit_are_rechecked(self):
        """Only a saved proof on the complete current input can be reused."""
        for field, value in (('status', 'conditional_inconclusive'), ('trace_audit', {'passed': False})):
            sources = deepcopy(self.conditionals)
            sources[0]['conditional'][field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                scan_support(self.raw, self.saved_run, oracle_sources=self.oracles,
                             conditional_sources=sources)

    def test_changed_relation_reenumerates_targets_but_reuses_raw_queries(self):
        """State differences stay visible while identical original queries reuse."""
        run = deepcopy(self.saved_run)
        matrix = run['phases'][0]['outcome']['relations']
        matrix[0][4] &= ~(1 << 1)
        matrix[4][0] &= ~(1 << 4)
        with patch('scripts.quaternary_triangle_saturation_support_scan.solve_exact',
                   side_effect=AssertionError('unexpected new search')):
            scan = scan_support(self.raw, run, oracle_sources=self.oracles,
                                conditional_sources=self.conditionals)
        old = self.scan['inventory']['states'][0]
        new = scan['inventory']['states'][0]
        self.assertNotEqual(new['relations_sha256'], old['relations_sha256'])
        self.assertEqual(len(new['pair_targets']), len(old['pair_targets']) - 1)

    def test_directional_color_bits_and_matrix_validation(self):
        """Transposing faces also transposes colors; malformed bits fail closed."""
        raw = contact_document(['A', 'B'])
        run = solve_saturation_contacts(raw, decision_limit=0)
        matrix = run['phases'][0]['outcome']['relations']
        matrix[0][1], matrix[1][0] = 1 << 1, 1 << 4
        self.assertEqual([t['symbols'] for t in support_inventory(raw, run)['states'][0]['pair_targets']],
                         [[1, 2]])
        matrix[1][0] = 1 << 1
        with self.assertRaises(AssertionError):
            support_inventory(raw, run)

    def test_derived_singletons_are_not_exact_commitments(self):
        """A learned common-cycle equality cannot become an oracle premise."""
        raw = pentagonal_bipyramid()
        run = solve_triangle_saturation(raw)['run']
        scan = scan_support(raw, run)
        self.assertEqual(run['phases'][0]['outcome']['domains'][1], [1])
        self.assertTrue(all(1 not in dict(s['anchors']) for s in scan['states']))
        self.assertTrue(all(1 not in dict(r['input']['anchors']) for r in scan['oracle_records']))
        self.assertTrue(all(set(r['input']) == {'n', 'edges', 'anchors'} for r in scan['oracle_records']))

    def test_committed_trials_are_persistent_and_terminal_base_is_kept(self):
        """A trial label does not make an actual commitment disappear."""
        raw = contact_document(['A', 'B'])
        run = solve_saturation_contacts(raw)
        scan = scan_support(raw, run)
        self.assertEqual([s['phase'] for s in scan['states']],
                         [0] + [e['after_phase'] for e in run['events']])
        self.assertEqual(scan['summary']['no_single_target_state_count'], 1)
        self.assertEqual(scan['summary']['base_status_counts']['sat'], 3)
        self.assertEqual(run['phases'][1]['kind'], 'trial')

    def test_zero_budget_unknown_is_not_a_negative_or_a_conditional_probe(self):
        """Exhaustion cannot justify a contradiction or a successful support."""
        with patch('scripts.quaternary_triangle_saturation_support_scan.propagate_saturation_contacts',
                   side_effect=AssertionError('unexpected diagnostic')):
            scan = scan_support(self.raw, self.saved_run, node_limit=0)
        self.assertEqual(scan['summary']['single']['status_counts']['unknown'], 20)
        self.assertEqual(scan['summary']['pair']['status_counts']['unknown'], 124)
        self.assertEqual(scan['conditional_records'], [])

    def test_unknown_base_stays_unknown_when_pair_child_is_sat(self):
        """A small search budget may finish a fully fixed child before its base."""
        raw = contact_document(['A', 'B'])
        run = solve_saturation_contacts(raw, decision_limit=0)
        scan = scan_support(raw, run, node_limit=1)
        self.assertEqual(scan['summary']['base_status_counts']['unknown'], 1)
        self.assertEqual(scan['summary']['pair']['status_counts']['unknown'], 16)
        self.assertTrue(all(scan['oracle_records'][t['pair_oracle_index']]['result']['status'] == 'sat'
                            for t in scan['states'][0]['pair_targets']))

    def test_progress_is_state_scoped_and_inputs_are_immutable(self):
        """Progress supports a long runner without mutating frozen data."""
        before = deepcopy((self.raw, self.saved_run, self.oracles, self.conditionals))
        updates = []
        scan_support(self.raw, self.saved_run, oracle_sources=self.oracles,
                     conditional_sources=self.conditionals, progress=updates.append)
        self.assertEqual(before, (self.raw, self.saved_run, self.oracles, self.conditionals))
        self.assertEqual(updates[0]['kind'], 'state_complete')
        self.assertEqual(updates[0]['state_count'], 1)

    def test_wrong_policy_and_boolean_limits_are_rejected(self):
        """Old labels and boolean aliases cannot stand in for the frozen version."""
        run = deepcopy(self.saved_run)
        run['policy'] = 'quaternary-low-color-logical-neq-conditional-v1'
        with self.assertRaises(AssertionError):
            support_inventory(self.raw, run)
        with self.assertRaises(AssertionError):
            scan_support(self.raw, self.saved_run, node_limit=True)


if __name__ == '__main__':
    unittest.main()

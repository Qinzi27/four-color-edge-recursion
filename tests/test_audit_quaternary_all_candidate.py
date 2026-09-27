"""Coverage, raw-premise and resource mutation tests for full-candidate audits."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts.audit_quaternary_all_candidate import audit_all_candidates, check_all_candidate_artifacts
from scripts.exact_extendibility_oracle import solve_exact, verify_exact_result
from scripts.quaternary_all_candidate_low_color import solve_all_candidate_low_color
from scripts.quaternary_contact_model import propagate_contacts
from tests.test_quaternary_odd_cycle_eq_audit import pentagonal_bipyramid, small_document


RESOURCES = {'decision_limit': 128, 'probe_limit': 8192,
             'assignment_limit': 262144, 'node_limit': 200000}


def clique_document(n, anchored=False):
    """Nonplanar K5 is an explicit abstract negative audit fixture, not geometry."""
    sides = ['V' + str(i) for i in range(n)]
    pairs = [(a, b) for i, a in enumerate(sides) for b in sides[i + 1:]]
    return {'sides': sides, 'anchors': {sides[0]: 1} if anchored else {},
            'lines': [{'id': 'E' + str(i), 'left': a, 'right': b, 'kind': 'separator'}
                      for i, (a, b) in enumerate(pairs)]}


class AllCandidateAuditTests(unittest.TestCase):
    """Each mutation must fail through independent evidence reconstruction."""

    @classmethod
    def setUpClass(cls):
        """Small preexisting fixtures exercise probes, equality and rejection."""
        cls.raw = small_document()
        cls.envelope = solve_all_candidate_low_color(cls.raw)
        cls.audit = audit_all_candidates(cls.raw, cls.envelope)
        cls.eq_raw = pentagonal_bipyramid()
        cls.eq_envelope = solve_all_candidate_low_color(cls.eq_raw)
        cls.eq_audit = audit_all_candidates(cls.eq_raw, cls.eq_envelope)
        cls.bad_raw = clique_document(5, anchored=True)
        cls.bad_envelope = solve_all_candidate_low_color(cls.bad_raw, probe_limit=1)
        cls.bad_audit = audit_all_candidates(cls.bad_raw, cls.bad_envelope)

    def checked(self, envelope=None, audit=None, resources=None):
        """Replay the cached two-face control with optional corruption."""
        return check_all_candidate_artifacts(self.raw, envelope or self.envelope,
                                              audit or self.audit, resources or RESOURCES)

    def test_complete_inventory_and_cached_commit_are_counted_separately(self):
        """All three names are probed, while the lowest cached trial is committed."""
        run = self.envelope['run']
        self.assertEqual([(e['kind'], e['symbol']) for e in run['events']],
                         [('probe', 2), ('probe', 3), ('probe', 4), ('commit', 2)])
        self.assertEqual(run['probes'], 3)
        self.assertEqual(run['choices'], 1)
        self.assertEqual(run['final_phase'], 1)
        self.assertEqual(self.audit['probe_counts']['supported'], 3)
        self.assertEqual(self.audit['commitment_counts']['safe'], 1)
        self.assertEqual(len(self.audit['oracle_records']), 4)
        self.assertTrue(self.checked()['passed'])

    def test_checker_never_calls_producer_propagation_or_search(self):
        """Saved trace replay does not request any new solution or propagation."""
        with patch('scripts.quaternary_all_candidate_low_color.solve_all_candidate_low_color',
                   side_effect=AssertionError('producer')), \
                patch('scripts.quaternary_all_candidate_low_color.propagate_contacts',
                      side_effect=AssertionError('propagation')), \
                patch('scripts.quaternary_contact_model.propagate_contacts',
                      side_effect=AssertionError('propagation')), \
                patch('scripts.audit_quaternary_all_candidate.solve_exact',
                      side_effect=AssertionError('oracle')), \
                patch('scripts.exact_extendibility_oracle.solve_exact',
                      side_effect=AssertionError('oracle')):
            checked = self.checked()
        self.assertEqual(checked['producer_runs'], 0)
        self.assertEqual(checked['oracle_searches'], 0)
        self.assertEqual(checked['propagation_runs'], 0)

    def test_incomplete_sweep_cannot_commit(self):
        """Omitting a surviving nonselected candidate invalidates the commitment."""
        bad = deepcopy(self.envelope)
        bad['run']['events'].pop(2)
        with self.assertRaises(AssertionError):
            self.checked(envelope=bad)

    def test_probe_order_is_reconstructed(self):
        """A complete set of probes in an undeclared order is rejected."""
        bad = deepcopy(self.envelope)
        bad['run']['events'][0], bad['run']['events'][1] = bad['run']['events'][1], bad['run']['events'][0]
        with self.assertRaisesRegex(AssertionError, 'sweep order'):
            self.checked(envelope=bad)

    def test_commit_must_reuse_selected_cached_trial(self):
        """A different surviving trial does not justify the lowest-name commitment."""
        bad = deepcopy(self.envelope)
        bad['run']['events'][-1]['trial_phase'] = 2
        with self.assertRaisesRegex(AssertionError, 'reuse the selected trial'):
            self.checked(envelope=bad)

    def test_surviving_probe_cannot_change_persistent_state(self):
        """Probe outcomes remain hypothetical even when they contain full colorings."""
        bad = deepcopy(self.envelope)
        bad['run']['events'][0]['after_phase'] = 1
        with self.assertRaisesRegex(AssertionError, 'persistent phase'):
            self.checked(envelope=bad)

    def test_probe_cannot_have_commitment_selection_metadata(self):
        """The mother-side scheduler is consulted only for the final commitment."""
        bad = deepcopy(self.envelope)
        bad['run']['events'][0]['selection'] = deepcopy(bad['run']['events'][-1]['selection'])
        with self.assertRaisesRegex(AssertionError, 'scheduler metadata'):
            self.checked(envelope=bad)

    def test_all_candidate_and_sweep_counters_are_bound(self):
        """Telemetry cannot conceal uncounted trials or incomplete sweeps."""
        for field in ('probes', 'choices', 'rejections', 'sweeps_started', 'sweeps_completed'):
            bad = deepcopy(self.envelope)
            bad['run'][field] += 1
            with self.subTest(field=field), self.assertRaises(AssertionError):
                self.checked(envelope=bad)

    def test_trial_input_cannot_add_other_anchors(self):
        """Even a locally replayable phase must use exactly the permitted assumptions."""
        bad = deepcopy(self.eq_envelope)
        phase = bad['run']['phases'][1]
        phase['document']['anchors']['E'] = 1
        phase['outcome'] = propagate_contacts(phase['document'])
        with self.assertRaisesRegex(AssertionError, 'trial assumptions'):
            audit_all_candidates(self.eq_raw, bad)

    def test_learning_is_verified_before_any_new_oracle_query(self):
        """The raw common odd-cycle certificate is a required theorem premise."""
        bad = deepcopy(self.eq_envelope)
        bad['learning']['certificates'].clear()
        with patch('scripts.audit_quaternary_all_candidate.solve_exact', side_effect=RuntimeError('oracle')), \
                self.assertRaises((AssertionError, ValueError)):
            audit_all_candidates(self.eq_raw, bad)

    def test_raw_oracle_does_not_fix_inferred_equality_singletons(self):
        """Only initial anchors, current commitments and the one target enter queries."""
        self.assertEqual(self.eq_envelope['learning']['equal_names'], [['A', 'E']])
        for record in self.eq_audit['oracle_records']:
            self.assertEqual(set(record['input']), {'n', 'edges', 'anchors'})
            self.assertNotIn(1, dict(record['input']['anchors']))
        self.assertEqual(self.eq_audit['full_enumeration']['initial_legal_assignments'], 30)
        self.assertTrue(check_all_candidate_artifacts(self.eq_raw, self.eq_envelope,
                                                     self.eq_audit, RESOURCES)['passed'])

    def test_valid_certificate_with_an_extra_raw_anchor_is_rejected(self):
        """Correct answers to stronger queries are not evidence for the raw prefix."""
        bad = deepcopy(self.audit)
        fixed, edges = {0: 1, 1: 3}, [(0, 1)]
        result = solve_exact(2, edges, fixed, node_limit=200000)
        bad['oracle_records'][0] = {'input': {'n': 2, 'edges': [[0, 1]], 'anchors': [[0, 1], [1, 3]]},
                                    'result': result, 'verification': verify_exact_result(2, edges, fixed, result)}
        with self.assertRaisesRegex(AssertionError, 'commitment binding'):
            self.checked(audit=bad)

    def test_original_edges_extra_premises_and_boolean_ids_are_rejected(self):
        """Strict JSON binding checks all raw solver premises and their types."""
        for mutation in (lambda row: row['input']['edges'].clear(),
                         lambda row: row['input'].__setitem__('states', {}),
                         lambda row: row['input'].__setitem__('n', True),
                         lambda row: row['input']['anchors'][0].__setitem__(1, True)):
            bad = deepcopy(self.audit)
            mutation(bad['oracle_records'][0])
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                self.checked(audit=bad)

    def test_oracle_record_order_duplicates_and_unused_records_are_rejected(self):
        """First-use order makes cache accounting independently reproducible."""
        for mutation in (lambda rows: rows.reverse(), lambda rows: rows.append(deepcopy(rows[0])),
                         lambda rows: rows.pop()):
            bad = deepcopy(self.audit)
            mutation(bad['oracle_records'])
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                self.checked(audit=bad)

    def test_unknown_is_not_supported_or_safe(self):
        """Zero search budget remains unknown even when small enumeration completes."""
        audit = audit_all_candidates(self.raw, self.envelope, node_limit=0)
        resources = {**RESOURCES, 'node_limit': 0}
        self.assertEqual(audit['probe_counts']['unknown'], 3)
        self.assertEqual(audit['commitment_counts']['unknown'], 1)
        self.checked(audit=audit, resources=resources)
        audit['commitment_counts'].update(unknown=0, safe=1)
        with self.assertRaises(AssertionError):
            self.checked(audit=audit, resources=resources)

    def test_rejection_has_no_new_raw_anchor_and_conflict_precedes_budget_stop(self):
        """A proved persistent conflict takes priority over an exhausted trial cap."""
        run, audit = self.bad_envelope['run'], self.bad_audit
        self.assertEqual(run['events'][0]['kind'], 'reject')
        self.assertEqual(run['status'], 'conflict')
        self.assertEqual(run['sweeps_started'], 1)
        self.assertEqual(audit['steps'][0]['before_oracle_index'], audit['steps'][0]['after_oracle_index'])
        self.assertEqual(audit['rejection_counts'], {'exact_unsat': 1, 'unknown': 0})
        check_all_candidate_artifacts(self.bad_raw, self.bad_envelope, audit, {**RESOURCES, 'probe_limit': 1})

    def test_rejection_cannot_be_recorded_as_surviving_probe(self):
        """A literal trace conflict requires immediate rejection and fresh propagation."""
        bad = deepcopy(self.bad_envelope)
        bad['run']['events'][0]['kind'] = 'probe'
        with self.assertRaisesRegex(AssertionError, 'immediately reject'):
            audit_all_candidates(self.bad_raw, bad)

    def test_budget_edges_allow_final_cached_commit_but_not_partial_commit(self):
        """The third and final probe may authorize one commitment at no extra call."""
        for limit, expected in ((0, 'incomplete'), (2, 'incomplete'), (3, 'solved')):
            envelope = solve_all_candidate_low_color(self.raw, probe_limit=limit)
            audit = audit_all_candidates(self.raw, envelope)
            self.assertEqual(envelope['run']['status'], expected)
            self.assertEqual(envelope['run']['choices'], int(limit == 3))
            self.checked(envelope, audit, {**RESOURCES, 'probe_limit': limit})

    def test_decision_limit_precedes_empty_sweep_and_terminal_status_precedes_caps(self):
        """No scan begins at zero decision budget; an already solved input stays solved."""
        envelope = solve_all_candidate_low_color(self.raw, decision_limit=0, probe_limit=0)
        audit = audit_all_candidates(self.raw, envelope)
        self.assertEqual(envelope['run']['sweeps_started'], 0)
        self.assertEqual(envelope['run']['reason'], 'decision-limit-exhausted')
        self.checked(envelope, audit, {**RESOURCES, 'decision_limit': 0, 'probe_limit': 0})
        raw = {'sides': ['A'], 'lines': [], 'anchors': {'A': 1}}
        envelope = solve_all_candidate_low_color(raw, decision_limit=0, probe_limit=0)
        audit = audit_all_candidates(raw, envelope)
        self.assertEqual(envelope['run']['status'], 'solved')
        check_all_candidate_artifacts(raw, envelope, audit,
                                     {**RESOURCES, 'decision_limit': 0, 'probe_limit': 0})

    def test_budget_status_phase_audit_and_enumeration_tampering_are_rejected(self):
        """Saved summaries and resource identities are reconstructed, not trusted."""
        for mutation in (lambda audit: audit['phase_audits'][0].__setitem__('passed', False),
                         lambda audit: audit['full_enumeration'].__setitem__('phase_checks', 0),
                         lambda audit: audit['oracle_records'][0]['result'].__setitem__('node_limit', 1),
                         lambda audit: audit['steps'][0].__setitem__('trial_status', 'unsat')):
            bad = deepcopy(self.audit)
            mutation(bad)
            with self.subTest(mutation=mutation), self.assertRaises((AssertionError, ValueError)):
                self.checked(audit=bad)
        with self.assertRaisesRegex(AssertionError, 'producer limits'):
            self.checked(resources={**RESOURCES, 'probe_limit': 512})

    def test_raw_external_restrictions_and_original_phase_mutations_are_rejected(self):
        """The formal raw-entry scope excludes caller-supplied candidate sets or EQ."""
        for field, value in (('states', {'S1': '0111'}), ('equal_names', [['S0', 'S1']])):
            with self.assertRaisesRegex(AssertionError, 'states/EQ unsupported'):
                audit_all_candidates({**self.raw, field: value}, {})
        bad = deepcopy(self.envelope)
        bad['run']['phases'][0]['kind'] = 'trial'
        with self.assertRaisesRegex(AssertionError, 'initial phase'):
            self.checked(envelope=bad)


if __name__ == '__main__':
    unittest.main()

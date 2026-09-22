"""Small independent-evidence checks, without running the formal populations."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts.check_quaternary_reachability import literal_solutions, check_projections, external_domain_control
from scripts.quaternary_bipyramid_inputs import build_targeted_inventory, identify_bipyramid
from scripts.quaternary_contact_model import propagate_contacts
from scripts.quaternary_low_color import solve_low_color
from scripts.validate_global_restart import export_geometries


class ReachabilityEvidenceTests(unittest.TestCase):
    """Detect ignored raw constraints and invented propagation deletions."""

    def test_domains_anchors_and_commitments_are_distinct(self):
        """All three restrictions must be respected by direct enumeration."""
        document = {'sides': ['A', 'B'], 'lines': [
            {'id': 'E0', 'left': 'A', 'right': 'B', 'kind': 'separator'}],
            'anchors': {'A': 1}, 'states': {'B': '0110'}}
        self.assertEqual(literal_solutions(document), [{'A': 1, 'B': 2}, {'A': 1, 'B': 3}])
        self.assertEqual(literal_solutions(document, {'B': 3}), [{'A': 1, 'B': 3}])
        self.assertEqual(literal_solutions(document, {'B': 4}), [])

    def test_projection_audit_rejects_unsound_output(self):
        """A valid raw coloring must survive both unary and pair projections."""
        document = {'sides': ['A', 'B'], 'lines': [], 'anchors': {}, 'states': {}}
        outcome = propagate_contacts(document)
        solutions = literal_solutions(document)
        check_projections(outcome, solutions)
        outcome['relations'][0][1] = 0
        with self.assertRaisesRegex(AssertionError, 'binary'):
            check_projections(outcome, solutions)

    def test_literal_equalities_are_constraints_without_merging_sides(self):
        """Logical same-name statements constrain both distinct side identities."""
        document = {'sides': ['A', 'B'], 'lines': [], 'equal_names': [['A', 'B']]}
        self.assertEqual(literal_solutions(document), [{'A': c, 'B': c} for c in (1, 2, 3, 4)])
        self.assertEqual(literal_solutions(document, {'A': 1, 'B': 2}), [])


class ExternalDomainTransitionTests(unittest.TestCase):
    """Tampering must fail even when individual propagation phases are valid."""

    @classmethod
    def setUpClass(cls):
        """Export one fixed old fixture only; do not run either formal population."""
        row = build_targeted_inventory()['records'][63]
        exported = export_geometries([row])[0]
        if exported['status'] != 'geometry_ok':
            raise AssertionError('test geometry export failed')
        cls.drawing = row['document']
        cls.geometry = exported['geometry']
        cls.mapping = identify_bipyramid(cls.geometry)
        cls.resources = {'decision_limit': 128, 'probe_limit': 512}

    def check_control(self, resources=None):
        """Run the complete external-domain audit on the fixed five-face map."""
        return external_domain_control(self.geometry, self.drawing, self.mapping,
                                       self.resources if resources is None else resources)

    def tampered_control(self, mutate):
        """Alter only the recorded result after the authentic producer finishes."""
        def produce(*args, **kwargs):
            result = solve_low_color(*args, **kwargs)
            mutate(result)
            return result
        with patch('scripts.check_quaternary_reachability.solve_low_color', side_effect=produce):
            return self.check_control()

    def test_external_fixture_retains_six_to_zero_local_control(self):
        """A failed arbitrary trial and the actual mother schedule stay separate."""
        result = self.check_control()
        self.assertEqual([len(row['solutions']) for row in result['local_checks']], [6, 0])
        self.assertEqual(result['transition_audit'], 'exact_phase_documents_complete_coverage_and_final_binding')
        self.assertIn('shared_mother_peer_selector', result['schedule_audit'])

    def test_budget_stop_is_checked_without_invented_commitments(self):
        """Stopping before any choice is incomplete, with one persistent phase."""
        result = self.check_control({'decision_limit': 0, 'probe_limit': 512})
        self.assertEqual(result['mother_schedule_run']['status'], 'incomplete')
        self.assertEqual(result['event_solution_counts'], [])

    def test_changed_original_input_is_rejected(self):
        """The reported producer input must be exactly the constructed domains."""
        with self.assertRaisesRegex(AssertionError, 'original input'):
            self.tampered_control(lambda result: result['original_input'].update(states={}))

    def test_valid_but_unreferenced_phase_is_rejected(self):
        """Trace validity alone cannot authorize an unreferenced extra phase."""
        with self.assertRaisesRegex(AssertionError, 'unreferenced'):
            self.tampered_control(lambda result: result['phases'].append(deepcopy(result['phases'][0])))

    def test_commit_after_phase_must_be_accepted_trial(self):
        """A commit cannot point back to its pre-commit phase."""
        with self.assertRaisesRegex(AssertionError, 'after_phase'):
            self.tampered_control(lambda result: result['events'][0].update(after_phase=0))

    def test_schedule_metadata_is_checked(self):
        """Mother scheduling metadata is compared with the shared audit helper."""
        with self.assertRaisesRegex(AssertionError, 'selection metadata'):
            self.tampered_control(lambda result: result['events'][0]['selection'].update(reason='invented'))

    def test_unresolved_trial_cannot_claim_complete_witness(self):
        """Lack of contradiction remains inconclusive until all colors exist."""
        with self.assertRaisesRegex(AssertionError, 'overstates evidence'):
            self.tampered_control(lambda result: result['events'][0].update(extension_claim='complete-witness'))

    def test_final_result_is_bound_to_last_phase(self):
        """Valid saved phases cannot justify a different exported final coloring."""
        with self.assertRaisesRegex(AssertionError, 'final output'):
            self.tampered_control(lambda result: result.update(colors=None))

    def test_event_telemetry_is_recomputed(self):
        """Reported choices are counted from accepted events, not trusted fields."""
        with self.assertRaisesRegex(AssertionError, 'telemetry'):
            self.tampered_control(lambda result: result.update(choices=0))


if __name__ == '__main__':
    unittest.main()

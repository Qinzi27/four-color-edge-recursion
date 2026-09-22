"""Reject tampered persisted traces and certificates on a tiny raw fixture."""

from copy import deepcopy
import unittest

from scripts.audit_quaternary_low_color import audit_low_color
from scripts.check_quaternary_reachability_artifacts import check_certificates, same
from scripts.quaternary_low_color import solve_low_color


class ReachabilityArtifactTests(unittest.TestCase):
    """Tests generate a tiny fixture; the artifact checker itself never solves."""

    def setUp(self):
        self.document = {'sides': ['A', 'B'], 'lines': [
            {'id': 'E0', 'left': 'A', 'right': 'B', 'kind': 'separator'}],
            'anchors': {'A': 1}, 'states': {}}
        self.result = solve_low_color(self.document)
        self.audit = audit_low_color(self.document, self.result)
        self.resources = {'decision_limit': 128, 'probe_limit': 512,
                          'assignment_limit': 262144, 'node_limit': 200000}

    def test_saved_certificate_and_transition(self):
        """A stored raw SAT witness and its actual low-color commitment verify."""
        checked = check_certificates(self.document, self.result, self.audit, self.resources)
        self.assertEqual(checked['oracle_statuses'], {'sat': 2})
        self.assertEqual(checked['unsafe_commitments'], 0)

    def test_tampered_oracle_anchor_is_rejected(self):
        """A valid certificate cannot be silently reassigned to another state."""
        audit = deepcopy(self.audit)
        audit['steps'][0]['trial_oracle_index'] = audit['initial_oracle_index']
        with self.assertRaisesRegex(AssertionError, 'commitment binding'):
            check_certificates(self.document, self.result, audit, self.resources)

    def test_hidden_trial_restriction_is_rejected(self):
        """No unrecorded external domain may appear during a trial."""
        result = deepcopy(self.result)
        result['phases'][1]['document']['states'] = {'B': '0200'}
        with self.assertRaises((AssertionError, ValueError)):
            check_certificates(self.document, result, self.audit, self.resources)

    def test_boolean_is_not_integer_evidence(self):
        """JSON evidence identities require literal types, not Python equality."""
        with self.assertRaises(AssertionError):
            same({'side': True}, {'side': 1}, 'literal evidence differs')


if __name__ == '__main__':
    unittest.main()

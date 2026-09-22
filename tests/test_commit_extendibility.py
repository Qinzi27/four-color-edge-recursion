"""Audit reachable decisions, including a known first fatal old-v2 choice."""

from copy import deepcopy
import unittest

from fourcolor.structural_restart import restart_structural_names
from scripts.audit_commit_extendibility import (
    audit_candidate, check_retained_solutions, literal_solutions, verify_inventory,
)
from scripts.exhaustive_rectangular_histories import build_inventory
from tests.test_structural_restart import failure_geometry


class CommitExtendibilityTests(unittest.TestCase):
    """The oracle diagnoses the candidate after it has finished, without rescue."""

    @classmethod
    def setUpClass(cls):
        cls.geometry = failure_geometry()

    def test_first_reachable_old_failure_has_sat_and_unsat_evidence(self):
        candidate = restart_structural_names(self.geometry, structural=False)
        frozen = deepcopy(candidate)
        audit = audit_candidate(self.geometry, candidate, assignment_limit=0)
        self.assertEqual(candidate, frozen)
        self.assertEqual(audit["initialization_status"], "sat")
        bad = audit["first_bad_commitment"]
        self.assertIsNotNone(bad)
        self.assertEqual(bad["event_index"], 0)
        self.assertEqual((bad["proposal"]["side"], bad["proposal"]["symbol"]), (10, 2))
        self.assertEqual(bad["after_exact"]["status"], "unsat")
        self.assertEqual(len(bad["before_witness"]), 19)

    def test_current_repaired_path_retains_exact_extensions(self):
        candidate = restart_structural_names(self.geometry)
        audit = audit_candidate(self.geometry, candidate, assignment_limit=0)
        self.assertEqual(audit["candidate_status"], "solved")
        self.assertIsNone(audit["first_bad_commitment"])
        self.assertTrue(all(s["oracle"]["status"] == "sat" for s in audit["states"]))
        self.assertEqual(audit["soundness"]["status"], "not_enumerated")

    def test_literal_enumeration_never_calls_cap_exhaustion_a_proof(self):
        solutions, assignments = literal_solutions(3, [(0, 1), (1, 2)], {0: 1}, 16)
        self.assertEqual(assignments, 16)
        self.assertEqual(len(solutions), 9)
        self.assertEqual(literal_solutions(3, [], {0: 1}, 15), (None, 16))

    def test_exact_soundness_check_rejects_lost_unary_and_pair_values(self):
        good = {"domains": [[1], [2, 3, 4]], "relations": [[65535] * 2 for _ in range(2)]}
        solutions = [[1, 2], [1, 3], [1, 4]]
        self.assertEqual(check_retained_solutions(solutions, {0: 1}, good), 3)
        for target in ("unary", "pair"):
            bad = deepcopy(good)
            if target == "unary":
                bad["domains"][1].remove(3)
            else:
                bad["relations"][0][1] &= ~(1 << 2)
            with self.subTest(target=target), self.assertRaises(AssertionError):
                check_retained_solutions(solutions, {0: 1}, bad)

    def test_omitted_input_cannot_keep_an_exhaustive_claim(self):
        manifest = {"policy": "mother-peer-structural-reuse-v1",
                    "scope": {"family": "guillotine", "width": 2, "height": 2, "max_cuts": 2},
                    "resources": {"history_limit": 100}, "inventory": build_inventory(2, 2, 2, 100)}
        self.assertTrue(verify_inventory(manifest))
        manifest["inventory"]["records"].pop()
        with self.assertRaises(AssertionError):
            verify_inventory(manifest)


if __name__ == "__main__":
    unittest.main()

"""Challenge the independent geometry, cost, and budget diagnostics."""

from copy import deepcopy
import json
import unittest

from fourcolor.kempe_reconfiguration import search_kempe_repairs
from scripts.validate_kempe_progress import (
    ARCHIVE, ROOT, audit_path, budget_profile, degeneracy_certificate,
    independent_budget_lower_bound, small_path_oracle,
)
from scripts.validate_kempe_split import make_problem
from scripts.validate_renaming import audit_record


class ProgressValidationTests(unittest.TestCase):
    """Use a preexisting three-step geometric counterexample, not a mock graph."""

    @classmethod
    def setUpClass(cls):
        """Reconstruct the hard case once for independent certificate attacks."""
        archive = json.loads((ROOT / ARCHIVE).read_text(encoding="utf-8"))
        cls.row = next(r for r in archive["records"] if r["seed"] == 20260927)
        cls.checked = audit_record(cls.row)
        cls.problem = make_problem(cls.row, cls.checked)
        cls.path = search_kempe_repairs(**cls.problem)

    def test_hard_path_matches_old_integer_oracle(self):
        """The prior component generator confirms depth, targets, and path costs."""
        audit = audit_path(self.row, self.checked, self.problem, self.path)
        oracle = small_path_oracle(self.row, self.checked, self.problem, 6)
        self.assertEqual(audit["replayed_steps"], 3)
        self.assertEqual(oracle["shortest_steps"], 3)
        self.assertEqual(oracle["target_layer_candidate_count"],
                         self.path["target_layer_candidate_count"])
        selected = self.path["selected"]
        self.assertEqual(oracle["best_cumulative_record_weight"],
                         (selected["cumulative_changed_record_count"],
                          selected["cumulative_changed_weight"]))

    def test_rejects_false_record_cost(self):
        """A numerically corrupted certificate must not pass geometric replay."""
        altered = deepcopy(self.path)
        altered["selected"]["steps"][0]["changed_record_count"] += 1
        with self.assertRaises(AssertionError):
            audit_path(self.row, self.checked, self.problem, altered)

    def test_rejects_partial_component(self):
        """Deleting a reported component member invalidates the swap witness."""
        altered = deepcopy(self.path)
        altered["selected"]["steps"][0]["component"] = ()
        with self.assertRaises(AssertionError):
            audit_path(self.row, self.checked, self.problem, altered)

    def test_rejects_net_record_identity_tampering(self):
        """Even equal-sized invented record sets cannot replace actual shores."""
        altered = deepcopy(self.path)
        ids = list(altered["selected"]["net_changed_record_ids"])
        ids[0] = "not-a-real-edge"
        altered["selected"]["net_changed_record_ids"] = ids
        with self.assertRaises(AssertionError):
            audit_path(self.row, self.checked, self.problem, altered)

    def test_minimum_is_not_claimed_after_unknown_lower_budgets(self):
        """A resource cutoff supplies no lower-bound certificate."""
        limited = budget_profile(self.problem, 2, 1)
        self.assertIsNone(limited["minimum_old_side_changes"])
        self.assertFalse(limited["minimum_certified"])
        exact = budget_profile(self.problem, 2, 200000)
        self.assertTrue(exact["minimum_certified"])
        self.assertEqual(exact["minimum_old_side_changes"], 2)

    def test_degeneracy_certificate_includes_lower_bound(self):
        """A triangle with a leaf has exact degeneracy two despite degree three."""
        problem = {"initial": {"a": 0, "b": 1, "c": 2, "d": 1},
                   "edges": [("a", "b"), ("b", "c"), ("a", "c"), ("a", "d")]}
        certificate = degeneracy_certificate(problem)
        self.assertEqual(certificate["degeneracy"], 2)
        self.assertEqual(set(certificate["lower_bound_core"]), {"a", "b", "c"})

    def test_subset_oracle_rejects_inflated_minimum(self):
        """Independent subset enumeration detects a falsely claimed lower bound."""
        actual = independent_budget_lower_bound(self.problem, 2)
        self.assertGreater(actual["assignments_checked"], 0)
        with self.assertRaises(AssertionError):
            independent_budget_lower_bound(self.problem, 3)

    def test_subset_oracle_rejects_unsupported_weight_scope(self):
        """Weighted objectives must not silently use the unit-cost proof."""
        altered = deepcopy(self.problem)
        old = next(v for v in altered["weights"] if altered["weights"][v] == 1)
        altered["weights"][old] = 2
        with self.assertRaises(AssertionError):
            independent_budget_lower_bound(altered, 2)


if __name__ == "__main__":
    unittest.main()

"""Adversarial checks for geometry-bound continuous-history certificates."""

from copy import deepcopy
import unittest

from fourcolor.kempe_history_policy import replay_kempe_history
from fourcolor.triangle_chain_family import build_staggered_strip
from fourcolor.triangle_chain_replay import replay_staggered_history
from scripts.validate_kempe_history_continuation import (
    audit_control_prefix, audit_history, audit_repair_geometry, summarize,
)


class ContinuationCertificateTests(unittest.TestCase):
    """Check real integration and reject locally plausible, unrelated evidence."""

    @classmethod
    def setUpClass(cls):
        """Reuse one small actual history, leaving mutations isolated per test."""
        cls.family = build_staggered_strip(1)
        cls.record = replay_kempe_history(cls.family)
        cls.control = replay_staggered_history(cls.family, policy="forest")
        cls.repair = next(e for e in cls.record["trace"] if "repair_problem" in e)

    def test_complete_history_has_independent_cost_certificate(self):
        """The endpoint oracle confirms a reached final cut, not a planted state."""
        row = audit_history(self.family, deepcopy(self.record), self.control)
        self.assertEqual(row["status"], "completed")
        self.assertTrue(row["final_initial_comparison"]["matches_up_to_permutation"])
        self.assertEqual(row["final_split_cost_audit"]["quotient"]["minimum_cost"], 2)
        result = summarize([row])
        self.assertEqual(result["completed"], 1)
        self.assertEqual(result["by_m"][0]["final_cut_actual_costs"], [2])

    def test_wrong_geometry_is_rejected_before_candidate_audit(self):
        """A graph coloring certificate must refer to the actual rectangle boxes."""
        entry = deepcopy(self.repair)
        vertex = next(iter(entry["repair_boxes"]))
        entry["repair_boxes"][vertex][0] -= 1
        with self.assertRaises(AssertionError):
            audit_repair_geometry(self.family, entry)

    def test_wrong_inherited_color_and_cost_are_rejected(self):
        """Do not import the blocked policy's diagnostic fifth name or free old sides."""
        for field in ("initial", "weights"):
            entry = deepcopy(self.repair)
            vertex = next(v for v, w in entry["repair_problem"]["weights"].items() if w)
            entry["repair_problem"][field][vertex] = 0
            with self.subTest(field=field), self.assertRaises(AssertionError):
                audit_repair_geometry(self.family, entry)

    def test_dropped_or_duplicate_edges_are_rejected(self):
        """An easier abstract repair graph cannot substitute for the geometric graph."""
        for duplicate in (False, True):
            entry = deepcopy(self.repair)
            edges = entry["repair_problem"]["edges"]
            edges.append(edges[0]) if duplicate else edges.pop()
            with self.subTest(duplicate=duplicate), self.assertRaises(AssertionError):
                audit_repair_geometry(self.family, entry)

    def test_legal_candidate_cannot_hide_a_different_commit(self):
        """The actual post-cut state must be the selected literal swap target."""
        entry = deepcopy(self.repair)
        entry["after"]["rectangles"][0]["color"] = 0
        with self.assertRaises(AssertionError):
            audit_repair_geometry(self.family, entry)

    def test_control_prefix_and_history_identity_are_enforced(self):
        """A better final score does not justify changing the baseline prefix."""
        for field in ("prefix", "inherit"):
            record = deepcopy(self.record)
            if field == "prefix":
                record["trace"][0]["method"] = "unreported_new_policy"
            else:
                record["inherit"] = "right"
            with self.subTest(field=field), self.assertRaises(AssertionError):
                audit_control_prefix(record, self.control)


if __name__ == "__main__":
    unittest.main()

"""Adversarial checks of cost certificates, separate from the search cores."""

from copy import deepcopy
import unittest

from fourcolor.apex_triangle_cost import apex_triangle_cost_table
from fourcolor.kempe_split import single_kempe_split
from fourcolor.recoloring_boundary import recoloring_boundary_table
from fourcolor.triangle_chain_family import build_staggered_strip
from scripts.validate_recoloring_obstructions import (
    audit_family_certificate, audit_family_kempe, audit_quotient,
    diagnose, remove_edge, remove_old_vertex,
)


class RecoloringObstructionAuditTests(unittest.TestCase):
    """Tampering must not turn an incomplete or inconsistent record into proof."""

    def setUp(self):
        """Use a genuine small split with a known exact lower bound."""
        self.family = build_staggered_strip(1)
        self.problem = self.family["problem"]
        self.quotient = apex_triangle_cost_table(
            self.problem["edges"], self.problem["initial"], self.problem["daughters"],
            apex="r", weights=self.problem["weights"])

    def test_direct_table_agrees_with_independent_quotient_audit(self):
        """All sixteen boundary pairs, including impossible ones, are checked."""
        table = recoloring_boundary_table(**self.problem)
        self.assertTrue(audit_quotient(self.problem, self.quotient, table)["direct_table_compared"])
        self.assertEqual(self.quotient["minimum_cost"], 2)
        self.assertEqual(self.quotient["target_count"], 6)

    def test_missing_duplicate_or_mislabeled_rows_are_rejected(self):
        """Coverage and daughter-color semantics cannot be inferred from a few rows."""
        for mutation in ("missing", "duplicate", "wrong_witness"):
            bad = deepcopy(self.quotient)
            valid = [row for row in bad["rows"] if row["witness"]]
            if mutation == "missing":
                bad["rows"].pop()
            elif mutation == "duplicate":
                valid[0]["pair"] = valid[1]["pair"]
            else:
                valid[0]["witness"] = valid[1]["witness"]
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                audit_quotient(self.problem, bad)

    def test_false_counts_costs_and_status_are_rejected(self):
        """Neither aggregate labels nor per-row exactness are trusted."""
        for key, value in (("target_count", 999), ("minimum_cost", 999),
                           ("counts_complete", False)):
            bad = deepcopy(self.quotient)
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(AssertionError):
                audit_quotient(self.problem, bad)
        bad = deepcopy(self.quotient)
        next(row for row in bad["rows"] if row["witness"])["optimal_target_count"] = 99
        with self.assertRaises(AssertionError):
            audit_quotient(self.problem, bad)

    def test_unsupported_equalities_and_literal_costs_are_rejected(self):
        """Shared-edge witnesses require real edges; class costs retain color IDs."""
        bad = deepcopy(self.quotient)
        bad["equality_witnesses"][0]["shared_edge"] = ("v-3", "v5")
        with self.assertRaises(AssertionError):
            audit_quotient(self.problem, bad)
        bad = deepcopy(self.quotient)
        bad["class_color_costs"][0][1] += 1
        with self.assertRaises(AssertionError):
            audit_quotient(self.problem, bad)

    def test_protected_sides_cannot_be_deleted(self):
        """Abstract relaxations preserve the anchored split question."""
        for side in ["r", "v0", "v2"]:
            with self.assertRaises(AssertionError):
                remove_old_vertex(self.problem, side)
        relaxed = remove_edge(self.problem, ["r", "v0"])
        self.assertEqual(diagnose(relaxed)["minimum_cost"], 0)
        self.assertEqual(len(self.problem["initial"]), 10)

    def test_family_formula_is_bound_to_actual_targets(self):
        """A correct geometry cannot validate arbitrary attached formula fields."""
        self.assertTrue(audit_family_certificate(self.family, self.quotient)["passed"])
        bad = deepcopy(self.family)
        bad["certificate"]["targets"][0]["changed_old_sides"] += 1
        with self.assertRaises(AssertionError):
            audit_family_certificate(bad, self.quotient)

    def test_kempe_component_and_net_cost_are_independently_replayed(self):
        """A partial component cannot masquerade as a legal Kempe exchange."""
        result = single_kempe_split(**self.problem)
        self.assertEqual(audit_family_kempe(self.family, result)["minimum_kempe_steps"], 1)
        bad = deepcopy(result)
        bad["candidates"][0]["component"] = bad["candidates"][0]["component"][:-1]
        with self.assertRaises(AssertionError):
            audit_family_kempe(self.family, bad)


if __name__ == "__main__":
    unittest.main()

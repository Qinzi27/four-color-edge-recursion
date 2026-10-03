"""Use six synthetic calibrations; reserve the 1,512-case census for freeze."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts import check_triangle_saturation_rule_soundness as rule


class TriangleSaturationFiniteRuleTests(unittest.TestCase):
    """Check empty, K4, relaxed, vacuous, and explicit-EQ lifted cases."""

    @classmethod
    def setUpClass(cls):
        """Evaluate only six named cases, never the formal complete inventory."""
        by_id = {record["id"]: record for record in rule.rule_inventory()}
        ids = ["saturation-mask-00-omit-1", "saturation-mask-3f-omit-1",
               "saturation-mask-3f-relax-a-omit-1", "saturation-mask-3f-four-colors",
               "saturation-mask-3f-all-triple-omit-1", "saturation-eq-lift-5-omit-1"]
        cls.records = [by_id[key] for key in ids]
        cls.report = rule._report(cls.records, rule._evaluate(cls.records))

    def check_small(self, report):
        """Bind saved replay to the six synthetic calibration cases only."""
        with patch.object(rule, "rule_inventory", return_value=self.records):
            return rule.check_saved_rule_soundness(report)

    def test_full_declaration_without_discovery(self):
        """Count every declared literal case without evaluating the new rule."""
        with patch.object(rule, "find_triangle_saturations", side_effect=AssertionError("detector")):
            records = rule.rule_inventory()
        self.assertEqual(len(records), 1512)
        self.assertEqual(len({record["id"] for record in records}), 1512)
        self.assertEqual(len({rule._digest(record["document"]) for record in records}), 72)
        self.assertEqual(sum(len(record["document"]["sides"]) == 4 for record in records), 1344)
        self.assertEqual(sum(len(record["document"]["sides"]) == 5 for record in records), 168)
        self.assertEqual({record["edge_mask"] for record in records if record["edge_mask"] is not None},
                         set(range(64)))
        self.assertEqual({record["endpoint_mask"] for record in records if record["endpoint_mask"] is not None},
                         set(range(8)))
        self.assertEqual(sum(record["domain_pattern"] == "triangle-triple-target-full" for record in records), 288)
        self.assertEqual(sum(4 ** len(record["document"]["sides"]) for record in records), 516096)
        self.assertEqual(sum(rule._domain_product_size(record["domains"]) for record in records), 260448)

    def test_effective_deletions_and_vacuity_separate(self):
        """A K4 in three colors cannot inflate counts of effective deletions."""
        empty, full, relaxed, four_colors, vacuous, lifted = self.report["per_case"]
        self.assertEqual(empty["domain_legal_assignments"], 108)
        self.assertEqual(full["domain_legal_assignments"], 6)
        self.assertEqual(full["certificates"], 1)
        self.assertEqual(full["nonvacuous_literal_deletions"], 3)
        self.assertEqual(full["vacuous_literal_deletions"], 0)
        self.assertEqual({(check["side"], check["color"]) for check in full["deletion_checks"]},
                         {("t", 2), ("t", 3), ("t", 4)})
        for row in (empty, relaxed, four_colors):
            self.assertEqual(row["certificates"], 0)
            self.assertFalse(row["domain_unsat"])
            self.assertTrue(all(check["support_witness"] is not None for check in row["nonreported_literal_checks"]))
        self.assertTrue(vacuous["domain_unsat"])
        self.assertEqual(vacuous["certificates"], 4)
        self.assertEqual(vacuous["vacuous_literal_deletions"], 12)
        self.assertEqual(vacuous["nonvacuous_literal_deletions"], 0)
        self.assertIsNotNone(vacuous["raw_four_color_witness"])
        self.assertEqual(lifted["certificates"], 1)
        self.assertEqual(lifted["nonvacuous_literal_deletions"], 6)

    def test_lifted_case_enumerates_literal_original_constraints(self):
        """The 1,024-tuple denominator includes assignments violating t0=t1."""
        lifted = self.report["per_case"][-1]
        self.assertEqual(lifted["literal_assignments_checked"], 1024)
        self.assertEqual(lifted["domain_assignment_universe"], 432)
        self.assertEqual(lifted["raw_legal_assignments"], 24)
        self.assertEqual(lifted["domain_legal_assignments"], 6)
        self.assertEqual(lifted["domain_legal_witness"][-2:], [1, 1])
        document = self.records[-1]["document"]
        for side in ("t0", "t1"):
            incident = [line for line in document["lines"] if side in (line["left"], line["right"])]
            self.assertLess(len(incident), 3)
        self.assertEqual(lifted["evidence"]["classes"][-1], ["t0", "t1"])
        self.assertFalse(self.report["scope"]["quotient_assignment_enumeration_substituted"])

    def test_saved_replay_uses_no_detector_or_search(self):
        """Literal enumeration and independent evidence coverage are sufficient."""
        with patch.object(rule, "find_triangle_saturations", side_effect=AssertionError("detector")), \
                patch("scripts.exact_extendibility_oracle.solve_exact", side_effect=AssertionError("oracle")):
            checked = self.check_small(self.report)
        self.assertTrue(checked["passed"])
        self.assertEqual(checked["positive_certificates_checked"], 6)
        self.assertEqual(checked["literal_deletions_checked"], 21)
        self.assertEqual(checked["detector_runs"], 0)
        self.assertEqual(checked["oracle_searches"], 0)

    def test_saved_counts_witnesses_and_types_bound(self):
        """A success flag cannot conceal omitted cases or modified literal truth."""
        mutations = [
            lambda report: report.__setitem__("case_assignment_pairs", 256),
            lambda report: report.__setitem__("passed", 1),
            lambda report: report["per_case"][1].__setitem__("nonvacuous_literal_deletions", 4),
            lambda report: report["per_case"][4].__setitem__("domain_unsat", False),
            lambda report: report["per_case"][0]["domain_legal_witness"].__setitem__(0, 1),
            lambda report: report["per_case"][0]["nonreported_literal_checks"][0]["support_witness"].__setitem__(0, 1),
            lambda report: report["per_case"].pop(),
        ]
        for mutate in mutations:
            altered = deepcopy(self.report)
            mutate(altered)
            with self.subTest(mutation=mutate), self.assertRaises((AssertionError, ValueError)):
                self.check_small(altered)

    def test_saved_certificates_and_omissions_bound(self):
        """Targets, witness contacts, EQ classes, and deletion colors are checked."""
        mutations = [
            lambda report: report["per_case"][1]["evidence"]["certificates"][0].__setitem__("excluded_color", 2),
            lambda report: report["per_case"][1]["evidence"]["certificates"][0].__setitem__("target", "a"),
            lambda report: report["per_case"][1]["evidence"]["certificates"].clear(),
            lambda report: report["per_case"][1]["evidence"]["certificates"][0]["removed_colors"].pop(),
            lambda report: report["per_case"][-1]["evidence"]["classes"][-1].pop(),
            lambda report: report["per_case"][-1]["evidence"].__setitem__("equal_names_sha256", "0" * 64),
        ]
        for mutate in mutations:
            altered = deepcopy(self.report)
            mutate(altered)
            with self.subTest(mutation=mutate), self.assertRaises((AssertionError, ValueError)):
                self.check_small(altered)


if __name__ == "__main__":
    unittest.main()

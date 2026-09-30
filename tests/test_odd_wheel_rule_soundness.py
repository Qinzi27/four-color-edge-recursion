"""Small prefreeze controls; the full 4,124-case census is a formal experiment."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts import check_odd_wheel_rule_soundness as rule


class OddWheelFiniteRuleTests(unittest.TestCase):
    """Check declaration coverage and saved literal evidence on four controls."""

    @classmethod
    def setUpClass(cls):
        """Use empty, full, even and one relaxed-vertex cases for calibration."""
        inventory = rule.rule_inventory()
        cls.records = [inventory[0], inventory[4092], inventory[4096], inventory[4097]]
        cls.report = rule._report(cls.records, rule._evaluate(cls.records))

    def check_small(self, report):
        """Replay only the four calibration controls in unit tests."""
        with patch.object(rule, "rule_inventory", return_value=self.records):
            return rule.check_saved_rule_soundness(report)

    def test_complete_inventory_without_detector_or_oracle(self):
        """All masks and every excluded color remain in canonical order."""
        with patch.object(rule, "find_odd_wheel", side_effect=AssertionError("detector")):
            records = rule.rule_inventory()
        self.assertEqual(len(records), 4124)
        self.assertEqual([(r["edge_mask"], r["excluded_color"]) for r in records[:4096]],
                         [(mask, color) for mask in range(1024) for color in range(1, 5)])
        self.assertEqual(len({rule._digest(r["document"]) for r in records}), 1025)
        self.assertEqual(len({r["id"] for r in records}), 4124)
        self.assertEqual(sum(r["family"] == "even-rim-control" for r in records), 4)
        self.assertEqual(sum(r["family"] == "one-vertex-relaxed-control" for r in records), 24)
        self.assertEqual(sum(4 ** len(r["document"]["sides"]) for r in records), 16941056)
        self.assertTrue(all(set(r["document"]) == {"sides", "lines"} for r in records))

    def test_full_wheel_nonvacuous_and_controls_have_literal_witnesses(self):
        """A raw four-color witness survives despite impossible restricted domains."""
        empty, full, even, relaxed = self.report["per_case"]
        self.assertEqual(empty["domain_legal_assignments"], 3 ** 6)
        self.assertEqual(empty["domain_legal_witness"], [2] * 6)
        self.assertTrue(full["conflict_certified"])
        self.assertEqual(full["domain_legal_assignments"], 0)
        self.assertIsNotNone(full["raw_four_color_witness"])
        for row in (empty, even, relaxed):
            self.assertFalse(row["conflict_certified"])
            self.assertIsNotNone(row["domain_legal_witness"])
            self.assertFalse(row["missed_domain_unsat"])

    def test_saved_check_never_calls_detector_or_search(self):
        """Saved certificate/absence checks and literal loops are sufficient."""
        with patch.object(rule, "find_odd_wheel", side_effect=AssertionError("detector")), \
                patch("scripts.exact_extendibility_oracle.solve_exact", side_effect=AssertionError("oracle")):
            checked = self.check_small(self.report)
        self.assertTrue(checked["passed"])
        self.assertEqual(checked["detector_runs"], 0)
        self.assertEqual(checked["positive_certificates_checked"], 1)
        self.assertEqual(checked["absence_checks"], 3)

    def test_report_witness_hash_and_count_mutations_rejected(self):
        """Neither a passed flag nor amended totals replace the full evidence."""
        mutations = [
            lambda r: r.__setitem__("case_assignment_pairs", 1),
            lambda r: r["per_case"][0]["domain_legal_witness"].__setitem__(0, 1),
            lambda r: r["per_case"][1].__setitem__("domain_legal_assignments", 1),
            lambda r: r["per_case"][1].__setitem__("evidence_sha256", "0" * 64),
            lambda r: r["per_case"][1]["raw_four_color_witness"].__setitem__(0, 4),
            lambda r: r["per_case"].pop(),
            lambda r: r.__setitem__("passed", 1),
        ]
        for mutate in mutations:
            altered = deepcopy(self.report)
            mutate(altered)
            with self.subTest(mutation=mutate), self.assertRaises((AssertionError, ValueError)):
                self.check_small(altered)

    def test_wrong_domain_or_structural_certificate_is_rejected(self):
        """A saved proof must bind the domains and a real physical odd rim."""
        mutations = [
            lambda r: r["per_case"][1]["evidence"].__setitem__("domains_sha256", "f" * 64),
            lambda r: r["per_case"][1]["evidence"]["certificate"].__setitem__("excluded_color", 2),
            lambda r: r["per_case"][1]["evidence"]["certificate"]["rim"].pop(),
            lambda r: r["per_case"][0]["evidence"].__setitem__("certificate", deepcopy(self.report["per_case"][1]["evidence"]["certificate"])),
        ]
        for mutate in mutations:
            altered = deepcopy(self.report)
            mutate(altered)
            with self.subTest(mutation=mutate), self.assertRaises((AssertionError, ValueError)):
                self.check_small(altered)

    def test_each_single_edge_removal_is_present_with_all_four_domains(self):
        """The main exhaustive declaration includes every minimal missing-edge control."""
        rows = rule.rule_inventory()
        for bit in range(10):
            mask = 1023 ^ (1 << bit)
            selected = [r for r in rows[:4096] if r["edge_mask"] == mask]
            self.assertEqual(len(selected), 4)
            self.assertTrue(all(len(r["document"]["lines"]) == 9 for r in selected))


if __name__ == "__main__":
    unittest.main()

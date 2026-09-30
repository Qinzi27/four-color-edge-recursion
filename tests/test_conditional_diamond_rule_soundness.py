"""Tiny prefreeze calibration; the 1,344-case census is reserved for the run."""

from copy import deepcopy
from itertools import combinations
import unittest
from unittest.mock import patch

from scripts import check_conditional_diamond_rule_soundness as rule


class ConditionalDiamondFiniteRuleTests(unittest.TestCase):
    """Use only empty, diamond, K4, relaxed, and full-domain calibration cases."""

    @classmethod
    def setUpClass(cls):
        """Five declared controls are sufficient to check the evidence schema."""
        by_id = {record["id"]: record for record in rule.rule_inventory()}
        ids = ["diamond-mask-00-omit-1", "diamond-mask-1f-omit-1",
               "diamond-mask-3f-omit-1", "diamond-mask-1f-relax-a-omit-1",
               "diamond-mask-1f-four-colors"]
        cls.records = [by_id[key] for key in ids]
        cls.report = rule._report(cls.records, rule._evaluate(cls.records))

    def check_small(self, report):
        """Bind saved replay to only the five calibration cases."""
        with patch.object(rule, "rule_inventory", return_value=self.records):
            return rule.check_saved_rule_soundness(report)

    def test_full_declaration_is_coordinate_free_and_search_free(self):
        """Count all labeled masks/domain controls without evaluating the rule."""
        with patch.object(rule, "find_conditional_diamonds", side_effect=AssertionError("detector")):
            records = rule.rule_inventory()
        self.assertEqual(len(records), 1344)
        self.assertEqual(len({record["id"] for record in records}), 1344)
        self.assertEqual(len({rule._digest(record["document"]) for record in records}), 64)
        self.assertEqual({record["edge_mask"] for record in records}, set(range(64)))
        self.assertEqual(sum(record["family"] == "all-four-vertex-simple-graphs-common-triple"
                             for record in records), 256)
        self.assertEqual(sum(record["family"] == "one-vertex-relaxed-control" for record in records), 1024)
        self.assertEqual(sum(record["family"] == "all-four-color-control" for record in records), 64)
        self.assertEqual(sum(4 ** len(record["document"]["sides"]) for record in records), 344064)
        self.assertEqual(sum(rule._domain_product_size(record["domains"]) for record in records), 147712)

    def test_initial_matrix_exact_literal_semantics(self):
        """No path consistency or learned equality is hidden in initial matrices."""
        for record in self.records:
            edges = {frozenset((line["left"], line["right"])) for line in record["document"]["lines"]}
            for i, first_side in enumerate(rule.SIDES):
                for j, second_side in enumerate(rule.SIDES):
                    for first in range(1, 5):
                        for second in range(1, 5):
                            present = bool(record["relations"][i][j] & (1 << (4 * (first - 1) + second - 1)))
                            allowed = first in record["domains"][i] and second in record["domains"][j]
                            allowed = allowed and (i != j or first == second)
                            allowed = allowed and (frozenset((first_side, second_side)) not in edges or first != second)
                            self.assertEqual(present, allowed)

    def test_nonvacuous_diamond_and_vacuous_k4_are_separate(self):
        """A domain-unsatisfiable complete graph cannot inflate effective EQ count."""
        empty, diamond, full, relaxed, four_colors = self.report["per_case"]
        self.assertEqual(empty["domain_legal_assignments"], 81)
        self.assertEqual(diamond["certified_equalities"], 1)
        self.assertEqual(diamond["domain_legal_assignments"], 6)
        self.assertEqual(diamond["equality_checks"], [{"pair": ["u", "v"],
                         "legal_assignments_checked": 6, "violations": 0, "vacuous_domain_unsat": False}])
        self.assertEqual(full["certified_equalities"], 6)
        self.assertEqual(full["vacuous_equalities"], 6)
        self.assertEqual(full["nonvacuous_equalities"], 0)
        self.assertTrue(full["domain_unsat"])
        self.assertIsNotNone(full["raw_four_color_witness"])
        for row in (empty, relaxed, four_colors):
            self.assertEqual(row["certified_equalities"], 0)
            self.assertFalse(row["domain_unsat"])
            self.assertEqual(len(row["nonreported_pair_checks"]), 6)
            self.assertTrue(all(check["unequal_witness"] is not None for check in row["nonreported_pair_checks"]))

    def test_saved_replay_never_discovers_or_searches(self):
        """Only literal enumeration and the independent certificate checker run."""
        with patch.object(rule, "find_conditional_diamonds", side_effect=AssertionError("detector")), \
                patch("scripts.exact_extendibility_oracle.solve_exact", side_effect=AssertionError("oracle")):
            checked = self.check_small(self.report)
        self.assertTrue(checked["passed"])
        self.assertEqual(checked["positive_certificates_checked"], 7)
        self.assertEqual(checked["detector_runs"], 0)
        self.assertEqual(checked["oracle_searches"], 0)

    def test_saved_count_witness_and_type_mutations_rejected(self):
        """Passed flags and modified totals cannot replace full evidence replay."""
        mutations = [
            lambda report: report.__setitem__("case_assignment_pairs", 2),
            lambda report: report.__setitem__("passed", 1),
            lambda report: report["per_case"][1].__setitem__("nonvacuous_equalities", 2),
            lambda report: report["per_case"][2].__setitem__("domain_unsat", False),
            lambda report: report["per_case"][0]["domain_legal_witness"].__setitem__(0, 1),
            lambda report: report["per_case"][0]["nonreported_pair_checks"][0]["unequal_witness"].__setitem__(0, 1),
            lambda report: report["per_case"].pop(),
        ]
        for mutate in mutations:
            altered = deepcopy(self.report)
            mutate(altered)
            with self.subTest(mutation=mutate), self.assertRaises((AssertionError, ValueError)):
                self.check_small(altered)

    def test_saved_certificate_and_omission_mutations_rejected(self):
        """Pattern identity, common color, and full certificate coverage are bound."""
        mutations = [
            lambda report: report["per_case"][1]["evidence"]["certificates"][0].__setitem__("excluded_color", 2),
            lambda report: report["per_case"][1]["evidence"]["certificates"][0].__setitem__("pair", ["a", "u"]),
            lambda report: report["per_case"][1]["evidence"]["certificates"].clear(),
            lambda report: report["per_case"][1]["evidence"].__setitem__("relations_sha256", "0" * 64),
        ]
        for mutate in mutations:
            altered = deepcopy(self.report)
            mutate(altered)
            with self.subTest(mutation=mutate), self.assertRaises((AssertionError, ValueError)):
                self.check_small(altered)


if __name__ == "__main__":
    unittest.main()

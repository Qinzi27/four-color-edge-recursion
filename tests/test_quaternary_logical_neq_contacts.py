"""Literal logical-NEQ propagation without synthetic physical line records."""

from copy import deepcopy
from itertools import combinations, product
import unittest

from scripts.quaternary_contact_model import propagate_contacts
from scripts.quaternary_logical_neq_contacts import MODEL, propagate_logical_contacts
from tests.test_quaternary_logical_neq import document


class LogicalContactsTests(unittest.TestCase):
    """The extended language changes only declared logical binary constraints."""

    def test_no_logical_neq_keeps_old_propagation_evidence_except_version_and_echo(self):
        raw = document(["A", "B", "C"], [("A", "B")], anchors={"A": 1}, equal_names=[["B", "C"]])
        old, new = propagate_contacts(raw), propagate_logical_contacts(raw)
        self.assertEqual(new["model"], MODEL)
        self.assertEqual(new.pop("different_names"), [])
        for field in ("model", "scope"):
            old.pop(field)
            new.pop(field)
        self.assertEqual(new, old)

    def test_logical_inequality_filters_colors_without_creating_a_line(self):
        raw = document(["A", "B"], anchors={"A": 1}, different_names=[["A", "B"]])
        result = propagate_logical_contacts(raw)
        self.assertEqual(result["lines"], [])
        self.assertEqual(result["name_states"]["B"]["quaternary"], "0111")
        self.assertEqual(result["different_names"], [["A", "B"]])
        self.assertEqual(result["status"], "underdetermined")
        self.assertIsNone(result["colors"])
        self.assertEqual(result["choices"], 0)

    def test_point_contact_and_bridge_do_not_mean_inequality(self):
        raw = document(["A", "B"], anchors={"A": 1}, point_contacts=[{"sides": ["A", "B"]}])
        raw["lines"] = [{"id": "dangling", "kind": "bridge", "left": "A", "right": "A"}]
        initial = propagate_logical_contacts(raw)
        self.assertEqual(initial["domains"][1], [1, 2, 3, 4])
        raw["different_names"] = [["A", "B"]]
        result = propagate_logical_contacts(raw)
        self.assertEqual(result["domains"][1], [2, 3, 4])
        self.assertEqual(len(result["lines"]), 1)
        self.assertEqual(result["lines"][0]["kind"], "bridge")
        self.assertEqual(result["point_contacts"], raw["point_contacts"])

    def test_eq_and_logical_neq_remain_distinct_and_conflicting_premises_fail(self):
        result = propagate_logical_contacts(document(["A", "B"],
                    equal_names=[["A", "B"]], different_names=[["A", "B"]]))
        self.assertEqual(result["status"], "conflict")
        self.assertIsNone(result["colors"])
        self.assertEqual(result["lines"], [])

    def test_distinct_known_pair_schema_is_strict(self):
        for value in (None, "AB", [("A", "B")], [["A"]], [["A", "A"]],
                      [["A", "unknown"]], [["A", True]], [["A", "B", "C"]]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                propagate_logical_contacts(document(["A", "B", "C"], different_names=value))
        with self.assertRaises(ValueError):
            propagate_logical_contacts({"sides": ["A"], "lines": [], "extra": []})

    def test_reversed_and_duplicate_pairs_keep_literal_echo_and_identical_relations(self):
        raw = document(["A", "B"], different_names=[["A", "B"]])
        expected = propagate_logical_contacts(raw)
        raw["different_names"] = [["B", "A"], ["A", "B"], ["A", "B"]]
        result = propagate_logical_contacts(raw)
        self.assertEqual(result["relations"], expected["relations"])
        self.assertEqual(result["different_names"], raw["different_names"])

    def test_solved_colors_check_logical_neq_and_preserve_anchor_provenance(self):
        raw = document(["A", "B", "C"], anchors={"A": 1}, states={"B": "0300"},
                       equal_names=[["A", "C"]], different_names=[["B", "C"]])
        result = propagate_logical_contacts(raw)
        self.assertEqual(result["status"], "solved")
        self.assertEqual(result["colors"], {"A": 1, "B": 2, "C": 1})
        self.assertEqual(result["name_states"]["C"]["quaternary"], "2000")
        self.assertEqual(result["explicit_anchor_sources"]["C"], [])
        self.assertEqual(result["explicit_anchor_sources"]["B"], [{"source": "states", "name": 2}])

    def test_logical_neq_derived_singleton_never_becomes_an_explicit_anchor(self):
        raw = document(["A", "B", "C", "D"], anchors={"A": 1, "B": 2, "C": 3},
                       different_names=[[side, "D"] for side in ("A", "B", "C")])
        result = propagate_logical_contacts(raw)
        self.assertEqual(result["name_states"]["D"]["quaternary"], "0002")
        self.assertEqual(result["colors"]["D"], 4)
        self.assertEqual(result["explicit_anchor_sources"]["D"], [])
        self.assertNotIn("D", result["original_input"]["anchors"])
        self.assertEqual(result["lines"], [])

    def test_small_literal_graphs_preserve_all_original_legal_assignments(self):
        sides = ["A", "B", "C"]
        possible = list(combinations(sides, 2))
        for mask in range(8):
            logical = [list(pair) for i, pair in enumerate(possible) if mask & (1 << i)]
            raw = document(sides, [("A", "B")], anchors={"A": 1}, different_names=logical)
            result = propagate_logical_contacts(raw)
            count = 0
            for values in product((1, 2, 3, 4), repeat=3):
                colors = dict(zip(sides, values))
                if colors["A"] != 1 or colors["A"] == colors["B"]:
                    continue
                if any(colors[a] == colors[b] for a, b in logical):
                    continue
                count += 1
                self.assertNotEqual(result["status"], "conflict")
                for i, a in enumerate(values):
                    self.assertIn(a, result["domains"][i])
                    for j, b in enumerate(values):
                        self.assertTrue(result["relations"][i][j] & (1 << (4 * (a - 1) + b - 1)))
            self.assertGreater(count, 0)

    def test_input_and_echo_do_not_alias_each_other(self):
        raw = document(["A", "B"], different_names=[["A", "B"]])
        original = deepcopy(raw)
        result = propagate_logical_contacts(raw)
        result["different_names"][0][0] = "changed"
        result["original_input"]["different_names"][0][0] = "elsewhere"
        self.assertEqual(raw, original)


if __name__ == "__main__":
    unittest.main()

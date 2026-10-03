"""Round chaining and scope controls for saturation's conditional unary facts."""

from copy import deepcopy
from itertools import combinations
import unittest
from unittest.mock import patch

from scripts.quaternary_conditional_diamond_contacts import propagate_diamond_contacts
from scripts.quaternary_triangle_saturation_contacts import (
    MODEL, VERSION, propagate_saturation_contacts,
)
from tests.test_quaternary_triangle_saturation import (
    lifted_document, make_document, triangle_document,
)


def chain_document():
    """T=1 removes X=1, enabling a second independent triangle to force W=1."""
    return make_document(["A", "B", "C", "T", "X", "Y", "Z", "W"],
                         list(combinations(["A", "B", "C", "T"], 2)) + [("T", "X")]
                         + list(combinations(["X", "Y", "Z", "W"], 2)),
                         states={s: "0111" for s in ["A", "B", "C", "Y", "Z"]})


def saturation_trial_document():
    """An inner-policy fixture where P=1 activates two incompatible saturations.

    This fixture's declared domains are unit-test premises. The next helper
    replaces them with actual anchors and physical edges for a raw-policy test.
    """
    edges = (list(combinations(["A", "B", "C", "T"], 2))
             + list(combinations(["D", "E", "F", "U"], 2))
             + [("T", "U"), ("P", "C"), ("P", "F")])
    return make_document(["P", "A", "B", "C", "T", "D", "E", "F", "U"], edges,
                         states={s: "0111" for s in ["A", "B", "D", "E"]})


def raw_saturation_trial_document():
    """Use only literal anchor/edge premises to realize the same rejected P=1."""
    raw = saturation_trial_document()
    raw.pop("states")
    raw["sides"] = ["H", "J", "P", "T", "U", "A", "B", "C", "D", "E", "F"]
    raw["anchors"] = {"H": 1, "J": 1}
    for i, (a, b) in enumerate([("H", "A"), ("J", "B"), ("H", "D"), ("J", "E")]):
        raw["lines"].append({"id": f"anchor{i}", "left": a, "right": b, "kind": "separator"})
    return raw


class TriangleSaturationContactTests(unittest.TestCase):
    """Each local domain reduction must preserve all other original input fields."""

    def test_triangle_batch_sets_derived_singleton_not_anchor(self):
        raw = triangle_document(states={s: "0111" for s in ["A", "B", "C"]})
        before = deepcopy(raw)
        result = propagate_saturation_contacts(raw)
        self.assertEqual(result["model"], MODEL)
        self.assertEqual(result["triangle_saturation"]["version"], VERSION)
        self.assertEqual(result["triangle_saturation"]["removed_candidates"], [["T", 2], ["T", 3], ["T", 4]])
        rounds = result["triangle_saturation"]["rounds"]
        self.assertEqual(len(rounds), 2)
        self.assertEqual(rounds[1]["document"]["states"]["T"], "2000")
        self.assertNotIn("anchors", rounds[1]["document"])
        self.assertFalse(result["name_states"]["T"]["anchored"])
        self.assertEqual(raw, before)

    def test_multiround_chain_rechecks_domains_and_preserves_all_nonstate_fields(self):
        raw = chain_document()
        result = propagate_saturation_contacts(raw)
        rounds = result["triangle_saturation"]["rounds"]
        self.assertEqual(len(rounds), 3)
        self.assertEqual([c["target"] for c in rounds[0]["triangle_check"]["certificates"]], ["T"])
        self.assertEqual([c["target"] for c in rounds[1]["triangle_check"]["certificates"]], ["W"])
        self.assertEqual(rounds[2]["triangle_check"]["certificates"], [])
        self.assertEqual(rounds[0]["outcome"]["domains"][4], [1, 2, 3, 4])
        self.assertEqual(rounds[1]["outcome"]["domains"][4], [2, 3, 4])
        for row in rounds:
            self.assertEqual(row["outcome"], propagate_diamond_contacts(row["document"]))
            self.assertEqual(row["document"]["lines"], raw["lines"])
            self.assertNotIn("equal_names", row["document"])

    def test_explicit_eq_class_transports_witness_without_carrying_a_new_physical_edge(self):
        raw = lifted_document(states={s: "0111" for s in ["A", "B", "C"]}, equal_names=[["T", "T2"]])
        result = propagate_saturation_contacts(raw)
        self.assertEqual(result["domains"][:2], [[1], [1]])
        self.assertEqual(result["triangle_saturation"]["removed_candidates"], [["T", 2], ["T", 3], ["T", 4]])
        self.assertEqual(len(result["lines"]), 6)
        self.assertEqual(result["triangle_saturation"]["rounds"][1]["document"]["equal_names"], [["T", "T2"]])

    def test_nested_diamond_equality_is_recomputed_and_never_exported_as_next_root_eq(self):
        # U=V is derived inside diamond closure; disjoint triangle still needs saturation.
        raw = triangle_document(states={s: "0111" for s in ["A", "B", "C"]})
        raw["sides"] += ["U", "V", "X", "Y"]
        for i, (a, b) in enumerate([("U", "X"), ("U", "Y"), ("V", "X"), ("V", "Y"), ("X", "Y")]):
            raw["lines"].append({"id": f"diamond{i}", "left": a, "right": b, "kind": "separator"})
        raw["states"].update({s: "0111" for s in ["U", "V", "X", "Y"]})
        result = propagate_saturation_contacts(raw)
        for row in result["triangle_saturation"]["rounds"]:
            self.assertNotIn("equal_names", row["document"])
            self.assertIn(["U", "V"], row["outcome"]["equal_names"])
            self.assertEqual(len(row["outcome"]["conditional_eq"]["rounds"]), 2)

    def test_top_projection_is_final_diamond_outcome_with_only_explicit_additions(self):
        raw = chain_document()
        result = propagate_saturation_contacts(raw)
        rounds = result["triangle_saturation"]["rounds"]
        projected = deepcopy(result)
        projected.pop("triangle_saturation")
        projected["model"] = rounds[-1]["outcome"]["model"]
        projected["original_input"] = rounds[-1]["document"]
        self.assertEqual(projected, rounds[-1]["outcome"])
        self.assertEqual(result["original_input"], raw)

    def test_separate_calls_do_not_inherit_triangle_domains(self):
        raw = triangle_document(states={s: "0111" for s in ["A", "B", "C"]})
        restricted = propagate_saturation_contacts(raw)
        unrestricted = propagate_saturation_contacts(triangle_document())
        self.assertEqual(restricted["domains"][0], [1])
        self.assertEqual(unrestricted["domains"][0], [1, 2, 3, 4])
        restricted["triangle_saturation"]["rounds"][0]["document"]["lines"].clear()
        self.assertEqual(len(raw["lines"]), 6)

    def test_terminal_outcomes_skip_detection_and_invalid_input_fails(self):
        for raw in (make_document(["A"], anchors={"A": 1}), make_document(["A"], states={"A": "0000"})):
            with patch("scripts.quaternary_triangle_saturation_contacts.find_triangle_saturations",
                       side_effect=AssertionError("terminal detector")):
                result = propagate_saturation_contacts(raw)
            self.assertEqual(len(result["triangle_saturation"]["rounds"]), 1)
            self.assertIsNone(result["triangle_saturation"]["rounds"][0]["triangle_check"])
        for bad in (None, make_document(["A"], anchors={"A": True})):
            with self.assertRaises(ValueError):
                propagate_saturation_contacts(bad)

    def test_repeated_or_empty_detector_deletion_cannot_create_an_unbounded_loop(self):
        raw = triangle_document(states={s: "0111" for s in ["A", "B", "C"]})
        for removed in ([], [2, 2], [2, 3, 4]):
            evidence = {"certificates": [{"target": "T", "removed_colors": removed}]}
            with patch("scripts.quaternary_triangle_saturation_contacts.find_triangle_saturations", return_value=evidence):
                with self.assertRaisesRegex(ValueError, "bounded progress"):
                    propagate_saturation_contacts(raw)


if __name__ == "__main__":
    unittest.main()

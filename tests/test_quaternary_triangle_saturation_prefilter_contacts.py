"""Check complete closure equivalence and external optimized-work accounting."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts.quaternary_triangle_saturation_contacts import propagate_saturation_contacts
from scripts.quaternary_triangle_saturation_prefilter_contacts import (
    IMPLEMENTATION_VERSION, MODEL, VERSION, propagate_prefilter_contacts,
)
from tests.test_quaternary_triangle_saturation import (
    lifted_document, make_document, triangle_document,
)
from tests.test_quaternary_triangle_saturation_contacts import chain_document


def assert_work_matches_checks(test, checks, work):
    """Bind each work row to its literal check and reconcile both counters.

    The old trace counters are retained reference work. Only external telemetry
    records actual enumeration; their sum identity does not equate their cost.
    """
    test.assertEqual(len(work), len(checks))
    for check, row in zip(checks, work):
        test.assertEqual(row["implementation"], "quaternary-triangle-saturation-prefilter-v1")
        for field in ("raw_document_sha256", "domains_sha256", "equal_names_sha256"):
            test.assertEqual(row[field], check[field])
        statistics = row["statistics"]
        test.assertEqual(statistics["triangles_enumerated"] + statistics["triangles_skipped"],
                         check["statistics"]["triangles_examined"])
        test.assertLessEqual(statistics["skipped_palette_checks"],
                             statistics["eligible_palette_checks"])
        test.assertTrue(all(type(value) is int and value >= 0 for value in statistics.values()))


class TriangleSaturationPrefilterContactTests(unittest.TestCase):
    """Use only synthetic inputs until the formal experiment freeze exists."""

    def test_full_nested_outputs_equal_for_unrestricted_restricted_lifted_and_chained_inputs(self):
        fixtures = [triangle_document(),
                    triangle_document(states={s: "0111" for s in ["A", "B", "C"]}),
                    lifted_document(states={s: "0111" for s in ["A", "B", "C"]},
                                    equal_names=[["T", "T2"]]),
                    chain_document()]
        for raw in fixtures:
            with self.subTest(raw=raw):
                before, work = deepcopy(raw), []
                old = propagate_saturation_contacts(raw)
                new = propagate_prefilter_contacts(raw, work_log=work)
                self.assertEqual(new, old)
                self.assertEqual(raw, before)
                self.assertEqual(new["model"], MODEL)
                self.assertEqual(new["triangle_saturation"]["version"], VERSION)
                self.assertNotEqual(IMPLEMENTATION_VERSION, VERSION)
                checks = [row["triangle_check"] for row in new["triangle_saturation"]["rounds"]
                          if row["triangle_check"] is not None]
                assert_work_matches_checks(self, checks, work)

    def test_nested_diamond_and_second_triangle_retain_all_local_premises(self):
        raw = chain_document()
        raw["sides"] += ["D", "E", "F", "G"]
        for i, (a, b) in enumerate([("D", "F"), ("D", "G"), ("E", "F"),
                                   ("E", "G"), ("F", "G")]):
            raw["lines"].append({"id": f"nested{i}", "left": a, "right": b,
                                 "kind": "separator"})
        raw["states"].update({side: "0111" for side in ["D", "E", "F", "G"]})
        work = []
        result = propagate_prefilter_contacts(raw, work_log=work)
        self.assertEqual(result, propagate_saturation_contacts(raw))
        rounds = result["triangle_saturation"]["rounds"]
        self.assertEqual(len(rounds), 3)
        for row in rounds:
            self.assertNotIn("equal_names", row["document"])
            self.assertIn(["D", "E"], row["outcome"]["equal_names"])
            self.assertEqual(len(row["outcome"]["conditional_eq"]["rounds"]), 2)
        assert_work_matches_checks(self, [row["triangle_check"] for row in rounds], work)

    def test_terminal_closure_has_no_detector_work_and_invalid_inputs_still_reject(self):
        for raw in (make_document(["A"], anchors={"A": 1}),
                    make_document(["A"], states={"A": "0000"})):
            work = []
            with patch("scripts.quaternary_triangle_saturation_prefilter_contacts.find_triangle_saturations_prefilter",
                       side_effect=AssertionError("terminal detector")):
                result = propagate_prefilter_contacts(raw, work_log=work)
            self.assertEqual(result, propagate_saturation_contacts(raw))
            self.assertEqual(work, [])
        for raw in (None, make_document(["A"], anchors={"A": True})):
            with self.assertRaises(ValueError):
                propagate_prefilter_contacts(raw)

    def test_terminal_outcomes_validate_optional_work_log_before_skipping_detection(self):
        for raw in (make_document(["A"], anchors={"A": 1}),
                    make_document(["A"], states={"A": "0000"})):
            for invalid in ({}, (), False, 0):
                with self.subTest(raw=raw, work_log=invalid):
                    with self.assertRaisesRegex(ValueError, "work_log must be a list or None"):
                        propagate_prefilter_contacts(raw, work_log=invalid)

    def test_existing_work_rows_are_preserved_and_calls_have_no_semantic_state(self):
        raw = triangle_document(states={s: "0111" for s in ["A", "B", "C"]})
        marker = {"caller": "existing"}
        work = [marker]
        with_log = propagate_prefilter_contacts(raw, work_log=work)
        self.assertIs(work[0], marker)
        self.assertEqual(with_log, propagate_prefilter_contacts(raw))
        unrestricted = triangle_document()
        self.assertEqual(propagate_prefilter_contacts(unrestricted),
                         propagate_saturation_contacts(unrestricted))
        with_log["triangle_saturation"]["rounds"][0]["document"]["lines"].clear()
        self.assertEqual(len(raw["lines"]), 6)

    def test_bounded_progress_guards_survive_the_implementation_change(self):
        raw = triangle_document(states={s: "0111" for s in ["A", "B", "C"]})
        for removed in ([], [2, 2], [2, 3, 4]):
            evidence = {"certificates": [{"target": "T", "removed_colors": removed}]}
            with patch("scripts.quaternary_triangle_saturation_prefilter_contacts.find_triangle_saturations_prefilter",
                       return_value=evidence):
                with self.assertRaisesRegex(ValueError, "bounded progress"):
                    propagate_prefilter_contacts(raw)


if __name__ == "__main__":
    unittest.main()

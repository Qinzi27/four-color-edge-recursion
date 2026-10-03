"""Check complete producer equivalence, fixed low-name choices and telemetry."""

import ast
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.quaternary_low_color import GEOMETRIC_SCHEDULE
from scripts.quaternary_triangle_saturation_low_color import (
    solve_saturation_contacts, solve_triangle_saturation,
)
from scripts.quaternary_triangle_saturation_prefilter_low_color import (
    IMPLEMENTATION_VERSION, INNER_POLICY, POLICY, solve_prefilter_contacts,
    solve_prefilter_triangle_saturation,
)
from scripts.validate_global_restart import export_geometries
from tests.test_quaternary_conditional_diamond_contacts import diamond_trial_document
from tests.test_quaternary_logical_neq import document, six_side_fixture
from tests.test_quaternary_triangle_saturation_contacts import (
    raw_saturation_trial_document, saturation_trial_document,
)
from tests.test_quaternary_triangle_saturation_prefilter_contacts import assert_work_matches_checks


def run_checks(run):
    """Flatten only detector calls, preserving phase and outer-round ordering."""
    return [row["triangle_check"] for phase in run["phases"]
            for row in phase["outcome"]["triangle_saturation"]["rounds"]
            if row["triangle_check"] is not None]


class TriangleSaturationPrefilterLowColorTests(unittest.TestCase):
    """Test semantic identity before replaying any frozen experimental corpus."""

    def test_inner_envelopes_equal_including_rejections_and_nested_closures(self):
        for raw in (diamond_trial_document(), saturation_trial_document(),
                    document(["A", "B", "C"], [("A", "B")], anchors={"A": 1})):
            with self.subTest(raw=raw):
                work = []
                old = solve_saturation_contacts(raw)
                new = solve_prefilter_contacts(raw, work_log=work)
                self.assertEqual(new, old)
                self.assertEqual(new["policy"], INNER_POLICY)
                self.assertTrue(all(event["symbol"] == min(event["candidates_before"])
                                    for event in new["events"]))
                assert_work_matches_checks(self, run_checks(new), work)

    def test_raw_wrapper_envelope_and_independent_learners_are_exactly_preserved(self):
        for raw in (six_side_fixture(), raw_saturation_trial_document()):
            with self.subTest(raw=raw):
                before, work = deepcopy(raw), []
                old = solve_triangle_saturation(raw)
                new = solve_prefilter_triangle_saturation(raw, work_log=work)
                self.assertEqual(new, old)
                self.assertEqual(raw, before)
                self.assertEqual(new["policy"], POLICY)
                self.assertNotEqual(IMPLEMENTATION_VERSION, POLICY)
                self.assertEqual(new["augmented_input"]["lines"], raw["lines"])
                assert_work_matches_checks(self, run_checks(new["run"]), work)
        self.assertEqual(new["run"]["events"][0]["kind"], "reject")
        self.assertEqual(new["run"]["status"], "solved")

    def test_all_commits_and_rejected_domains_keep_the_frozen_lifetime(self):
        raw = raw_saturation_trial_document()
        run = solve_prefilter_triangle_saturation(raw)["run"]
        anchors, states = dict(raw["anchors"]), {}
        for event in run["events"]:
            if event["kind"] == "commit":
                anchors[event["side"]] = event["symbol"]
            else:
                self.assertEqual(event["side"], "P")
                states["P"] = "0111"
            after = run["phases"][event["after_phase"]]["document"]
            self.assertEqual(after.get("anchors", {}), anchors)
            self.assertEqual(after.get("states", {}), states)
            self.assertNotIn("equal_names", after)
        self.assertEqual(run["backtracks"], 0)

    def test_budget_boundaries_match_even_after_a_rejected_trial(self):
        raw = saturation_trial_document()
        for limits in ({"decision_limit": 0}, {"probe_limit": 0}, {"probe_limit": 1},
                       {"decision_limit": 1}, {"decision_limit": 2, "probe_limit": 3}):
            with self.subTest(limits=limits):
                work = []
                result = solve_prefilter_contacts(raw, work_log=work, **limits)
                self.assertEqual(result, solve_saturation_contacts(raw, **limits))
                assert_work_matches_checks(self, run_checks(result), work)
        for limits in ({"decision_limit": True}, {"decision_limit": -1},
                       {"probe_limit": 1.5}, {"probe_limit": False}):
            with self.assertRaises(ValueError):
                solve_prefilter_contacts(raw, **limits)

    def test_terminal_producers_need_no_detector_and_no_budget(self):
        for raw in (document(["A"], anchors={"A": 4}),
                    document(["A", "B"], [("A", "B")], anchors={"A": 1, "B": 1})):
            work = []
            result = solve_prefilter_triangle_saturation(raw, decision_limit=0,
                                                        probe_limit=0, work_log=work)
            self.assertEqual(result, solve_triangle_saturation(raw, decision_limit=0, probe_limit=0))
            self.assertEqual(result["run"]["events"], [])
            self.assertEqual(work, [])

    def test_both_entrypoints_validate_optional_log_even_for_terminal_inputs(self):
        raw = document(["A"], anchors={"A": 4})
        for solver in (solve_prefilter_contacts, solve_prefilter_triangle_saturation):
            for invalid in ({}, (), False, 0):
                with self.subTest(solver=solver.__name__, work_log=invalid):
                    with self.assertRaisesRegex(ValueError, "work_log must be a list or None"):
                        solver(raw, decision_limit=0, probe_limit=0, work_log=invalid)

    def test_geometric_frame_fallback_preserves_complete_envelope(self):
        # Export a synthetic empty frame only; no frozen research record is run.
        rows = export_geometries([{"key": "synthetic-empty", "document": {
            "frame": {"width": 900, "height": 600}, "strokes": []}}])
        self.assertEqual(rows[0]["status"], "geometry_ok")
        geometry = rows[0]["geometry"]
        bounded = next(i for i in range(len(geometry["faces"])) if i != geometry["outerFace"])
        raw = adapt_exported_geometry(geometry, anchors={f"S{bounded}": 1})["contact_document"]
        work = []
        old = solve_triangle_saturation(raw, geometry=geometry)
        new = solve_prefilter_triangle_saturation(raw, geometry=geometry, work_log=work)
        self.assertEqual(new, old)
        self.assertEqual(new["run"]["schedule"], GEOMETRIC_SCHEDULE)
        self.assertEqual(new["run"]["events"][0]["selection"]["selection_group"], "frame-only-fallback")
        assert_work_matches_checks(self, run_checks(new["run"]), work)
        invalid_geometry = deepcopy(geometry)
        invalid_geometry["faceOfDart"][0] = True
        with self.assertRaises(ValueError):
            solve_prefilter_triangle_saturation(raw, geometry=invalid_geometry)

    def test_wrapper_rejects_extra_unproved_premises_and_never_calls_oracle(self):
        for extra in ({"states": {"A": "0111"}}, {"equal_names": [["A", "B"]]},
                      {"different_names": [["A", "B"]]}):
            with self.assertRaises(ValueError):
                solve_prefilter_triangle_saturation(document(["A", "B"], **extra))
        raw = six_side_fixture()
        before = deepcopy(raw)
        with patch("scripts.exact_extendibility_oracle.solve_exact", side_effect=AssertionError("oracle")):
            result = solve_prefilter_triangle_saturation(raw)
        self.assertFalse(result["oracle_feedback_to_producer"])
        self.assertFalse(result["old_colors_read"])
        result["original_input"]["lines"].clear()
        result["augmented_input"]["different_names"][0][0] = "changed"
        self.assertEqual(raw, before)
        root = Path(__file__).resolve().parents[1]
        for name in ("quaternary_triangle_saturation_prefilter_contacts.py",
                     "quaternary_triangle_saturation_prefilter_low_color.py"):
            tree = ast.parse((root / "scripts" / name).read_text(encoding="utf-8"))
            self.assertFalse(any("oracle" in (node.module or "") for node in ast.walk(tree)
                                 if isinstance(node, ast.ImportFrom)))


if __name__ == "__main__":
    unittest.main()

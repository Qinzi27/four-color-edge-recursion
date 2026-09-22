"""Check low-name semantics, real failed commitments and explicit work limits."""

import ast
from copy import deepcopy
from itertools import combinations
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.quaternary_low_color import (
    ABSTRACT_SCHEDULE, GEOMETRIC_SCHEDULE, solve_low_color,
)
from scripts.validate_global_restart import export_geometries

ROOT = Path(__file__).resolve().parents[1]


def contact_document(sides, pairs=(), **extra):
    """Construct literal contact examples without introducing a color oracle."""
    return {"sides": list(sides), "lines": [
        {"id": f"E{i}", "left": left, "right": right, "kind": "separator"}
        for i, (left, right) in enumerate(pairs)], **extra}


class QuaternaryLowColorTests(unittest.TestCase):
    """Fixtures share only the established Node geometry exporter and adapter."""

    @classmethod
    def setUpClass(cls):
        """Export the historical failure and empty frame once for all tests."""
        regressions = json.loads((ROOT / "examples/quaternary-real-regressions-2026-09-21.json")
                                 .read_text(encoding="utf-8"))
        case = regressions["cases"][0]
        cls.case = case
        inputs = [{"key": "failure", "document": case["drawing"]},
                  {"key": "empty", "document": {"frame": {"width": 900, "height": 600},
                                                    "strokes": []}}]
        cls.geometry = {}
        for row in export_geometries(inputs):
            if row["status"] != "geometry_ok" or row["coloring_performed"]:
                raise AssertionError("test input did not export as geometry only")
            cls.geometry[row["key"]] = row["geometry"]
        cls.failed_input = adapt_exported_geometry(cls.geometry["failure"],
                                                   anchors=case["anchors"])["contact_document"]

    def test_non_one_is_preserved_until_a_recorded_lowest_name_commitment(self):
        document = contact_document(["A"], states={"A": "0111"})
        result = solve_low_color(document)
        self.assertEqual(result["phases"][0]["outcome"]["name_states"]["A"]["candidates"], [2, 3, 4])
        self.assertEqual(result["colors"], {"A": 2})
        self.assertEqual(result["events"][0]["candidates_before"], [2, 3, 4])
        self.assertEqual(result["events"][0]["extension_claim"], "complete-witness")
        self.assertEqual(result["schedule"], ABSTRACT_SCHEDULE)

    def test_lowest_name_is_selected_for_each_current_domain(self):
        document = contact_document(["A", "B", "C"], combinations(["A", "B", "C"], 2),
                                    anchors={"A": 1})
        result = solve_low_color(document)
        self.assertEqual(result["colors"], {"A": 1, "B": 2, "C": 3})
        self.assertEqual(result["events"][0]["extension_claim"], "inconclusive")
        self.assertEqual(result["events"][-1]["extension_claim"], "complete-witness")
        for event in result["events"]:
            self.assertEqual(event["symbol"], min(event["candidates_before"]))

    def test_real_old_first_failure_is_rejected_before_committing(self):
        result = solve_low_color(self.failed_input, geometry=self.geometry["failure"])
        self.assertEqual(result["schedule"], GEOMETRIC_SCHEDULE)
        first = result["events"][0]
        self.assertEqual((first["kind"], first["side"], first["symbol"]), ("reject", "S10", 2))
        self.assertEqual(first["candidates_before"], [2, 3, 4])
        self.assertEqual(first["extension_claim"], "refuted")
        trial = result["phases"][first["trial_phase"]]
        after = result["phases"][first["after_phase"]]
        self.assertEqual(trial["kind"], "trial")
        self.assertEqual(trial["outcome"]["status"], "conflict")
        self.assertNotIn("S10", after["document"]["anchors"])
        self.assertEqual(after["document"]["states"]["S10"], "0011")
        self.assertEqual(after["outcome"]["name_states"]["S10"]["candidates"], [3, 4])
        self.assertEqual(result["status"], "solved")
        self.assertEqual(result["colors"]["S10"], 3)
        self.assertEqual(result["rejections"], 1)
        self.assertEqual(result["backtracks"], 0)

    def test_unguarded_control_preserves_the_same_first_choice_and_fails(self):
        result = solve_low_color(self.failed_input, geometry=self.geometry["failure"], probe=False)
        self.assertEqual(result["status"], "conflict")
        self.assertEqual((result["choices"], result["probes"], result["rejections"]), (1, 0, 0))
        event = result["events"][0]
        self.assertEqual((event["kind"], event["side"], event["symbol"]), ("commit", "S10", 2))
        self.assertEqual(event["extension_claim"], "unchecked")
        self.assertIsNone(event["trial_phase"])

    def test_no_hypothesis_survival_claims_general_safe_extension(self):
        sides = ["A", "B", "C", "D"]
        # Four mutually adjacent sides with only three names are impossible,
        # despite the initial relation propagation leaving every domain nonempty.
        document = contact_document(sides, combinations(sides, 2), states={s: "0111" for s in sides})
        result = solve_low_color(document)
        self.assertEqual(result["phases"][0]["outcome"]["status"], "underdetermined")
        self.assertEqual(result["status"], "conflict")
        self.assertGreater(result["rejections"], 0)
        self.assertEqual(result["choices"], 0)
        self.assertTrue(all(e["extension_claim"] == "refuted" for e in result["events"]))

    def test_frame_only_side_uses_explicit_fallback_after_single_anchor(self):
        geometry = self.geometry["empty"]
        bounded = next(i for i in range(len(geometry["faces"])) if i != geometry["outerFace"])
        document = adapt_exported_geometry(geometry, anchors={f"S{bounded}": 1})["contact_document"]
        result = solve_low_color(document, geometry=geometry)
        self.assertEqual(result["status"], "solved")
        event = result["events"][0]
        self.assertEqual(event["side"], f"S{geometry['outerFace']}")
        self.assertEqual(event["selection"]["selection_group"], "frame-only-fallback")
        self.assertEqual(event["selection"]["reason"], "no-unresolved-internal-occurrence")
        self.assertEqual(event["symbol"], 2)

    def test_budget_exhaustion_is_incomplete_without_a_hidden_choice(self):
        document = contact_document(["A", "B"])
        for kwargs, reason in (({"decision_limit": 0}, "decision-limit-exhausted"),
                               ({"probe_limit": 0}, "probe-limit-exhausted")):
            result = solve_low_color(document, **kwargs)
            self.assertEqual(result["status"], "incomplete")
            self.assertEqual(result["reason"], reason)
            self.assertEqual(result["events"], [])
            self.assertIsNone(result["colors"])
        partial = solve_low_color(document, decision_limit=1)
        self.assertEqual(partial["status"], "incomplete")
        self.assertEqual(partial["choices"], 1)
        self.assertEqual(partial["phases"][partial["final_phase"]]["document"]["anchors"], {"A": 1})
        unguarded = solve_low_color(document, probe=False, probe_limit=0)
        self.assertEqual(unguarded["status"], "solved")

    def test_trial_budget_retains_rejection_and_does_not_commit_after_exhaustion(self):
        result = solve_low_color(self.failed_input, geometry=self.geometry["failure"], probe_limit=1)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["reason"], "probe-limit-exhausted")
        self.assertEqual((result["probes"], result["choices"], result["rejections"]), (1, 0, 1))
        self.assertEqual(result["name_states"]["S10"]["candidates"], [3, 4])

    def test_initial_terminal_inputs_do_not_need_decision_or_probe_budget(self):
        solved = solve_low_color(contact_document(["A"], anchors={"A": 4}),
                                 decision_limit=0, probe_limit=0)
        conflict = solve_low_color(contact_document(["A"], anchors={"A": 1}, states={"A": "0111"}),
                                   decision_limit=0, probe_limit=0)
        self.assertEqual(solved["status"], "solved")
        self.assertEqual(conflict["status"], "conflict")
        self.assertEqual(solved["events"], [])
        self.assertEqual(conflict["events"], [])

    def test_supplied_states_equalities_and_anchors_are_never_relaxed(self):
        document = contact_document(["A", "B", "C"], [("B", "C")],
                                    anchors={"C": 1}, states={"A": "0011", "B": "0111"},
                                    equal_names=[["A", "B"]])
        result = solve_low_color(document)
        self.assertEqual(result["colors"], {"A": 3, "B": 3, "C": 1})
        for phase in result["phases"]:
            self.assertEqual(phase["document"]["states"], document["states"])
            self.assertEqual(phase["document"]["equal_names"], document["equal_names"])
            self.assertEqual(phase["document"]["anchors"]["C"], 1)

    def test_inputs_and_evidence_snapshots_do_not_alias_mutable_callers(self):
        document, geometry = deepcopy(self.failed_input), deepcopy(self.geometry["failure"])
        before_document, before_geometry = deepcopy(document), deepcopy(geometry)
        result = solve_low_color(document, geometry=geometry)
        self.assertEqual(document, before_document)
        self.assertEqual(geometry, before_geometry)
        result["original_input"]["anchors"]["S0"] = 4
        result["phases"][0]["document"]["anchors"]["S0"] = 4
        self.assertEqual(document, before_document)
        self.assertEqual(result["phases"][0]["outcome"]["original_input"], before_document)

    def test_invalid_limits_and_mismatched_real_geometry_are_rejected(self):
        for kwargs in ({"probe": 1}, {"probe_limit": True}, {"probe_limit": -1},
                       {"decision_limit": 1.5}, {"decision_limit": False}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                solve_low_color(contact_document(["A"]), **kwargs)
        for damage in ("order", "edge", "orientation", "face"):
            document, geometry = deepcopy(self.failed_input), deepcopy(self.geometry["failure"])
            if damage == "order":
                document["sides"].reverse()
            elif damage == "edge":
                document["lines"].pop()
            elif damage == "orientation":
                edge = next(row for row in document["lines"] if row["kind"] == "separator")
                edge["left"], edge["right"] = edge["right"], edge["left"]
            else:
                geometry["faceOfDart"][0] = True
            with self.subTest(damage=damage), self.assertRaises(ValueError):
                solve_low_color(document, geometry=geometry)

    def test_no_oracle_feedback_or_new_structural_filter_is_used(self):
        tree = ast.parse((ROOT / "scripts/quaternary_low_color.py").read_text(encoding="utf-8"))
        modules = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        self.assertFalse(any("oracle" in (module or "") or "structural_restart" in (module or "")
                             for module in modules))
        with patch("scripts.exact_extendibility_oracle.solve_exact", side_effect=AssertionError("oracle called")), \
                patch("fourcolor.structural_name_relations.refute_same_name", side_effect=AssertionError("structural called")), \
                patch("fourcolor.frontier_restart.propagate_hall", side_effect=AssertionError("Hall called")):
            result = solve_low_color(self.failed_input, geometry=self.geometry["failure"])
        self.assertEqual(result["status"], "solved")
        self.assertFalse(result["oracle_feedback_to_producer"])


if __name__ == "__main__":
    unittest.main()

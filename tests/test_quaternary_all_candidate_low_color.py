"""Check complete sweeps, cached commitments and sound rejection transitions.

These are small development fixtures, not the later frozen geometric cohort.
They deliberately exercise incomplete budgets and unsatisfiable restrictions;
success of a trial must never be mistaken for a general extension theorem.
"""

import ast
from copy import deepcopy
from itertools import combinations, product
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.audit_quaternary_geometry import audit_bounded_contacts
from scripts.quaternary_all_candidate_low_color import (
    POLICY, solve_all_candidate_contacts, solve_all_candidate_low_color,
)
from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.quaternary_low_color import ABSTRACT_SCHEDULE, GEOMETRIC_SCHEDULE
from scripts.validate_global_restart import export_geometries


ROOT = Path(__file__).resolve().parents[1]


def contact_document(sides, pairs=(), **extra):
    """Make small literal fixtures with explicitly declared separator edges."""
    return {"sides": list(sides), "lines": [
        {"id": f"E{i}", "left": a, "right": b, "kind": "separator"}
        for i, (a, b) in enumerate(pairs)], **extra}


class AllCandidateLowColorTests(unittest.TestCase):
    """The implementation's evidence contains every attempted hypothesis."""

    @classmethod
    def setUpClass(cls):
        """Use only a small empty-frame geometry to check the old scheduler."""
        records = export_geometries([{"key": "frame", "document": {
            "frame": {"width": 900, "height": 600}, "strokes": []}}])
        row = records[0]
        if row["status"] != "geometry_ok" or row["coloring_performed"]:
            raise AssertionError("geometry-only unit fixture export failed")
        cls.geometry = row["geometry"]

    def test_all_surviving_candidates_are_recorded_before_the_cached_commit(self):
        result = solve_all_candidate_contacts(contact_document(["A"]))
        self.assertEqual(result["policy"], POLICY)
        self.assertEqual(result["schedule"], ABSTRACT_SCHEDULE)
        self.assertEqual([(e["kind"], e["symbol"]) for e in result["events"]],
                         [("probe", 1), ("probe", 2), ("probe", 3), ("probe", 4), ("commit", 1)])
        self.assertEqual((result["probes"], result["choices"], len(result["phases"])), (4, 1, 5))
        self.assertEqual((result["sweeps_started"], result["sweeps_completed"]), (1, 1))
        self.assertEqual(result["final_phase"], 1)  # The chosen trial was not the last trial.
        for event in result["events"][:-1]:
            self.assertIsNone(event["selection"])
            self.assertEqual((event["before_phase"], event["after_phase"]), (0, 0))
            self.assertEqual(event["extension_claim"], "complete-witness")
        self.assertEqual(result["events"][-1]["trial_phase"], result["final_phase"])

    def test_sweep_covers_every_side_and_restarts_after_actual_commit(self):
        result = solve_all_candidate_contacts(contact_document(["A", "B"]))
        before_commit = result["events"][:8]
        self.assertEqual([(e["side"], e["symbol"]) for e in before_commit],
                         [(side, color) for side in ("A", "B") for color in range(1, 5)])
        self.assertTrue(all(e["kind"] == "probe" for e in before_commit))
        self.assertTrue(all(e["extension_claim"] == "inconclusive" for e in before_commit))
        self.assertEqual((result["probes"], result["choices"], result["sweeps_completed"]), (12, 2, 2))
        # B=1 was tested before A=1, then is retested under the new commitment.
        b_one = [e for e in result["events"] if e["kind"] == "probe"
                 and (e["side"], e["symbol"]) == ("B", 1)]
        self.assertEqual(len(b_one), 2)
        self.assertNotEqual(b_one[0]["before_phase"], b_one[1]["before_phase"])
        self.assertEqual(result["colors"], {"A": 1, "B": 1})

    def test_non_one_keeps_all_three_names_until_completed_sweep(self):
        result = solve_all_candidate_contacts(contact_document(["A"], states={"A": "0111"}))
        self.assertEqual([e["symbol"] for e in result["events"]], [2, 3, 4, 2])
        self.assertEqual(result["phases"][0]["outcome"]["domains"], [[2, 3, 4]])
        self.assertEqual(result["colors"], {"A": 2})

    def test_partial_sweep_does_not_commit_even_when_a_trial_is_solved(self):
        result = solve_all_candidate_contacts(contact_document(["A"]), probe_limit=3)
        self.assertEqual((result["status"], result["reason"]),
                         ("incomplete", "probe-limit-exhausted"))
        self.assertEqual((result["probes"], result["choices"], result["final_phase"]), (3, 0, 0))
        self.assertEqual((result["sweeps_started"], result["sweeps_completed"]), (1, 0))
        self.assertIsNone(result["colors"])
        self.assertTrue(all(e["extension_claim"] == "complete-witness" for e in result["events"]))

    def test_exact_probe_budget_allows_cached_commit_without_an_extra_call(self):
        result = solve_all_candidate_contacts(contact_document(["A"]), probe_limit=4)
        self.assertEqual((result["status"], result["probes"], result["choices"]), ("solved", 4, 1))
        result = solve_all_candidate_contacts(contact_document(["A", "B"]), probe_limit=8)
        self.assertEqual((result["status"], result["probes"], result["choices"]), ("incomplete", 8, 1))
        self.assertEqual(result["phases"][result["final_phase"]]["document"]["anchors"], {"A": 1})
        self.assertEqual((result["sweeps_started"], result["sweeps_completed"]), (2, 1))

    def test_zero_limits_have_separate_stopping_semantics(self):
        for limits, reason, started in (({"decision_limit": 0}, "decision-limit-exhausted", 0),
                                        ({"probe_limit": 0}, "probe-limit-exhausted", 1)):
            result = solve_all_candidate_contacts(contact_document(["A"]), **limits)
            self.assertEqual(result["reason"], reason)
            self.assertEqual(result["events"], [])
            self.assertEqual(result["sweeps_started"], started)
        result = solve_all_candidate_contacts(contact_document(["A", "B"]), decision_limit=1)
        self.assertEqual((result["probes"], result["choices"], result["sweeps_started"]), (8, 1, 1))
        self.assertEqual(result["reason"], "decision-limit-exhausted")

    def test_initial_terminal_input_ignores_both_caps(self):
        for document, status in ((contact_document(["A"], anchors={"A": 1}), "solved"),
                                  (contact_document(["A"], anchors={"A": 1}, states={"A": "0111"}),
                                   "conflict")):
            result = solve_all_candidate_contacts(document, decision_limit=0, probe_limit=0)
            self.assertEqual(result["status"], status)
            self.assertEqual(result["events"], [])
            self.assertEqual(result["sweeps_started"], 0)

    def test_other_side_can_be_rejected_before_scheduled_side_is_committed(self):
        # The isolated A is the old input-order choice. Restricted K4 is
        # globally impossible although its initial relation closure is open.
        clique = ["B", "C", "D", "E"]
        document = contact_document(["A"] + clique, combinations(clique, 2),
                                    states={side: "0111" for side in clique})
        result = solve_all_candidate_contacts(document)
        first = next(e for e in result["events"] if e["kind"] == "reject")
        self.assertEqual((first["side"], first["symbol"]), ("B", 2))
        self.assertEqual(result["events"][:4], [e for e in result["events"][:4]
                         if e["kind"] == "probe" and e["side"] == "A"])
        self.assertEqual(result["choices"], 0)
        after = result["phases"][first["after_phase"]]
        self.assertEqual(after["document"]["states"]["B"], "0011")
        self.assertNotIn("B", after["document"].get("anchors", {}))
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["backtracks"], 0)

    def test_rejection_restarts_from_first_side_and_preserves_all_current_solutions(self):
        # In this satisfiable list-colored K4, D must be 4. Binary consistency
        # alone initially leaves extra D candidates, so failed trials matter.
        clique = ["A", "B", "C", "D"]
        states = {"A": "1110", "B": "1110", "C": "1110", "D": "1111"}
        document = contact_document(["X"] + clique, combinations(clique, 2), states=states)
        result = solve_all_candidate_contacts(document)
        first_index = next(i for i, event in enumerate(result["events"])
                           if event["kind"] == "reject")
        first = result["events"][first_index]
        self.assertEqual((first["side"], first["symbol"]), ("D", 1))
        self.assertEqual(result["phases"][first["after_phase"]]["outcome"]["status"], "underdetermined")
        next_event = result["events"][first_index + 1]
        self.assertEqual((next_event["kind"], next_event["side"], next_event["symbol"]), ("probe", "X", 1))
        self.assertEqual(next_event["before_phase"], first["after_phase"])
        self.assertEqual(result["status"], "solved")
        self.assertEqual(result["colors"]["D"], 4)
        # Literal enumeration checks every rejected value against original
        # lists, raw edges and then-current commitments, without the producer.
        legal = []
        for values in product((1, 2, 3, 4), repeat=5):
            assignment = dict(zip(document["sides"], values))
            if any(assignment[a] == assignment[b] for a, b in combinations(clique, 2)):
                continue
            if any(states[side][assignment[side] - 1] == "0" for side in clique):
                continue
            legal.append(assignment)
        self.assertTrue(legal)
        for event in result["events"]:
            if event["kind"] != "reject":
                continue
            fixed = result["phases"][event["before_phase"]]["document"].get("anchors", {})
            still_legal = [row for row in legal if all(row[side] == color for side, color in fixed.items())]
            self.assertTrue(still_legal)
            self.assertTrue(all(row[event["side"]] != event["symbol"] for row in still_legal))
            for side, domain in zip(document["sides"], result["phases"][event["after_phase"]]["outcome"]["domains"]):
                self.assertTrue(all(row[side] in domain for row in still_legal))

    def test_all_phase_traces_replay_and_restrictions_preserve_literal_solutions(self):
        # Four small graphs cover disconnected, cycle, clique and diamond
        # constraints. Enumeration is an offline unit check, never production.
        sides = ["A", "B", "C", "D"]
        for edges in ([], [("A", "B"), ("B", "C"), ("C", "D"), ("D", "A")],
                      list(combinations(sides, 2)), list(combinations(sides, 2))[:-1]):
            document = contact_document(sides, edges, anchors={"A": 1})
            result = solve_all_candidate_contacts(document)
            for phase in result["phases"]:
                self.assertTrue(audit_bounded_contacts(phase["document"], phase["outcome"])["passed"])
                fixed = phase["document"].get("anchors", {})
                for colors in product((1, 2, 3, 4), repeat=4):
                    assignment = dict(zip(sides, colors))
                    if any(assignment[a] == assignment[b] for a, b in edges):
                        continue
                    if any(assignment[side] != color for side, color in fixed.items()):
                        continue
                    for side, domain in zip(sides, phase["outcome"]["domains"]):
                        self.assertIn(assignment[side], domain)

    def test_committed_anchors_never_disappear_and_every_new_phase_has_evidence(self):
        result = solve_all_candidate_contacts(contact_document(["A", "B", "C"], [("A", "B")]))
        self.assertEqual(len(result["phases"]), 1 + result["probes"] + result["rejections"])
        self.assertEqual(len(result["events"]), result["probes"] + result["choices"])
        fixed = {}
        for event in result["events"]:
            before = result["phases"][event["before_phase"]]["document"].get("anchors", {})
            self.assertEqual(before, fixed)
            if event["kind"] == "commit":
                fixed[event["side"]] = event["symbol"]
            after = result["phases"][event["after_phase"]]["document"].get("anchors", {})
            self.assertEqual(after, fixed)
        self.assertTrue(all(e["symbol"] == min(e["candidates_before"])
                            for e in result["events"] if e["kind"] == "commit"))

    def test_frame_fallback_uses_existing_geometry_schedule_after_full_sweep(self):
        geometry = self.geometry
        bounded = next(i for i in range(len(geometry["faces"])) if i != geometry["outerFace"])
        document = adapt_exported_geometry(geometry, anchors={f"S{bounded}": 1})["contact_document"]
        result = solve_all_candidate_low_color(document, geometry=geometry)["run"]
        commit = result["events"][-1]
        self.assertEqual(result["schedule"], GEOMETRIC_SCHEDULE)
        self.assertEqual(commit["selection"]["selection_group"], "frame-only-fallback")
        self.assertEqual(commit["side"], f"S{geometry['outerFace']}")
        self.assertEqual((result["probes"], commit["symbol"]), (3, 2))

    def test_wrapper_learns_logical_equality_once_without_merging_faces(self):
        rim = ["B", "C", "D"]
        document = contact_document(["A", "E"] + rim,
                                    list(combinations(rim, 2)) + [(a, b) for a in ("A", "E") for b in rim])
        original = deepcopy(document)
        result = solve_all_candidate_low_color(document)
        self.assertEqual(result["learning"]["equal_names"], [["A", "E"]])
        self.assertEqual(result["augmented_input"]["sides"], document["sides"])
        self.assertEqual(result["run"]["colors"]["A"], result["run"]["colors"]["E"])
        self.assertEqual(document, original)
        self.assertEqual(result["run"]["original_input"], result["augmented_input"])

    def test_wrapper_rejects_external_states_and_equalities(self):
        for extra in ({"states": {"A": "0111"}}, {"equal_names": [["A", "B"]]}):
            with self.assertRaises(ValueError):
                solve_all_candidate_low_color(contact_document(["A", "B"], **extra))

    def test_input_and_phase_snapshots_do_not_alias_callers(self):
        document = contact_document(["A", "B"], anchors={"A": 1})
        original = deepcopy(document)
        result = solve_all_candidate_low_color(document)
        result["original_input"]["anchors"]["A"] = 4
        result["run"]["phases"][0]["document"]["anchors"]["A"] = 3
        self.assertEqual(document, original)
        self.assertEqual(result["run"]["phases"][0]["outcome"]["original_input"], original)

    def test_invalid_caps_and_geometry_mismatch_raise(self):
        for limits in ({"probe_limit": True}, {"probe_limit": -1}, {"decision_limit": False},
                       {"decision_limit": 1.5}):
            with self.subTest(limits=limits), self.assertRaises(ValueError):
                solve_all_candidate_low_color(contact_document(["A"]), **limits)
        document = adapt_exported_geometry(self.geometry)["contact_document"]
        document["lines"].pop()
        with self.assertRaises(ValueError):
            solve_all_candidate_low_color(document, geometry=self.geometry)

    def test_no_production_oracle_or_rollback_helper_is_called(self):
        source = (ROOT / "scripts/quaternary_all_candidate_low_color.py").read_text(encoding="utf-8")
        modules = [node.module or "" for node in ast.walk(ast.parse(source))
                   if isinstance(node, ast.ImportFrom)]
        self.assertFalse(any("oracle" in name for name in modules))
        with patch("scripts.exact_extendibility_oracle.solve_exact", side_effect=AssertionError("oracle leak")), \
                patch("fourcolor.structural_name_relations.refute_same_name", side_effect=AssertionError("rescue")):
            result = solve_all_candidate_low_color(contact_document(["A", "B"], [("A", "B")]))
        self.assertFalse(result["oracle_feedback_to_producer"])
        self.assertFalse(result["old_colors_read"])
        self.assertEqual(result["run"]["backtracks"], 0)


if __name__ == "__main__":
    unittest.main()

"""Guarded low-color behavior after independently raw-derived EQ and NEQ."""

import ast
from copy import deepcopy
from itertools import combinations
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.quaternary_logical_neq_low_color import (
    INNER_POLICY, POLICY, solve_logical_contacts, solve_logical_neq,
)
from scripts.quaternary_low_color import solve_low_color
from tests.test_quaternary_logical_neq import document, known_geometry, six_side_fixture


ROOT = Path(__file__).resolve().parents[1]


class LogicalInequalityLowColorTests(unittest.TestCase):
    """No complete candidate sweep or exact search is introduced here."""

    def test_wrapper_learning_sources_share_only_original_raw_input(self):
        raw = six_side_fixture()
        original = deepcopy(raw)
        result = solve_logical_neq(raw)
        self.assertEqual(result["policy"], POLICY)
        self.assertEqual(result["run"]["policy"], INNER_POLICY)
        self.assertEqual(set(result["learning"]), {"equalities", "inequalities"})
        self.assertEqual(result["learning"]["equalities"]["raw_document_sha256"],
                         result["learning"]["inequalities"]["raw_document_sha256"])
        self.assertIn(["X", "E"], result["augmented_input"]["different_names"])
        self.assertIn(["A", "X"], result["augmented_input"]["equal_names"])
        self.assertEqual(raw, original)
        self.assertEqual(result["augmented_input"]["lines"], raw["lines"])
        self.assertEqual(result["augmented_input"]["sides"], raw["sides"])

    def test_no_relations_keeps_old_guarded_decisions_and_trial_budget(self):
        raw = document(["A", "B", "C"], [("A", "B")], anchors={"A": 1})
        old = solve_low_color(raw, probe=True, probe_limit=8192)
        new = solve_logical_neq(raw)
        self.assertEqual(new["learning"]["inequalities"]["different_names"], [])
        self.assertEqual(new["augmented_input"], raw)
        for key in ("events", "status", "colors", "domains", "name_states", "choices", "probes", "rejections"):
            self.assertEqual(new["run"][key], old[key])
        self.assertTrue(all(event["kind"] in ("commit", "reject") for event in new["run"]["events"]))

    def test_known_s10_gap_is_removed_at_initial_propagation_without_anchoring_s10(self):
        # This known candidate was never committed by the baseline scheduler;
        # earlier removal closes an inference gap, not an actual wrong commit.
        raw = adapt_exported_geometry(known_geometry(), anchors={"S1": 1})["contact_document"]
        result = solve_logical_neq(raw, geometry=known_geometry())
        self.assertIn(["S1", "S10"], result["learning"]["inequalities"]["different_names"])
        initial = result["run"]["phases"][0]
        self.assertEqual(initial["outcome"]["name_states"]["S10"]["quaternary"], "0111")
        self.assertEqual(initial["document"]["anchors"], {"S1": 1})
        self.assertEqual(initial["outcome"]["explicit_anchor_sources"]["S10"], [])
        self.assertEqual(result["run"]["status"], "solved")
        self.assertEqual(result["run"]["schedule"], "mother-peer-with-frame-only-fallback-v1")
        self.assertEqual(result["run"]["backtracks"], 0)
        for phase in result["run"]["phases"]:
            self.assertEqual(phase["document"]["lines"], raw["lines"])

    def test_rejection_retains_proof_and_never_becomes_an_anchor(self):
        sides = ["A", "B", "C", "D"]
        raw = document(sides, states={side: "0111" for side in sides},
                       different_names=[list(pair) for pair in combinations(sides, 2)])
        run = solve_logical_contacts(raw)
        self.assertEqual(run["status"], "conflict")
        self.assertEqual(run["choices"], 0)
        self.assertGreater(run["rejections"], 0)
        rejection = run["events"][0]
        self.assertEqual(rejection["kind"], "reject")
        self.assertEqual(rejection["extension_claim"], "refuted")
        self.assertNotIn("A", run["phases"][rejection["after_phase"]]["document"].get("anchors", {}))

    def test_limits_stop_without_hidden_choice_and_terminal_inputs_need_no_budget(self):
        raw = document(["A", "B"])
        for limits, reason in (({"decision_limit": 0}, "decision-limit-exhausted"),
                               ({"probe_limit": 0}, "probe-limit-exhausted")):
            run = solve_logical_neq(raw, **limits)["run"]
            self.assertEqual((run["status"], run["reason"]), ("incomplete", reason))
            self.assertEqual(run["events"], [])
        run = solve_logical_neq(raw, probe_limit=1)["run"]
        self.assertEqual((run["choices"], run["probes"]), (1, 1))
        self.assertEqual(run["phases"][run["final_phase"]]["document"]["anchors"], {"A": 1})
        run = solve_logical_neq(document(["A"], anchors={"A": 4}), decision_limit=0, probe_limit=0)["run"]
        self.assertEqual(run["status"], "solved")

    def test_preserved_logical_pairs_and_cumulative_commitments(self):
        raw = document(["A", "B", "C"], different_names=[["A", "B"], ["B", "C"]])
        result = solve_logical_contacts(raw)
        fixed = {}
        for event in result["events"]:
            self.assertEqual(event["symbol"], min(event["candidates_before"]))
            if event["kind"] == "commit":
                fixed[event["side"]] = event["symbol"]
            after = result["phases"][event["after_phase"]]["document"]
            self.assertEqual(after.get("anchors", {}), fixed)
            self.assertEqual(after["different_names"], raw["different_names"])
            self.assertEqual(after["lines"], [])

    def test_raw_wrapper_rejects_external_logic_and_invalid_limits(self):
        for extra in ({"states": {"A": "0111"}}, {"equal_names": [["A", "B"]]},
                      {"different_names": [["A", "B"]]}):
            with self.assertRaises(ValueError):
                solve_logical_neq(document(["A", "B"], **extra))
        for limit in ({"decision_limit": True}, {"probe_limit": -1}, {"probe_limit": 1.5}):
            with self.assertRaises(ValueError):
                solve_logical_neq(document(["A"]), **limit)

    def test_envelope_phases_and_caller_do_not_alias(self):
        raw = six_side_fixture()
        original = deepcopy(raw)
        result = solve_logical_neq(raw)
        result["augmented_input"]["different_names"][0][0] = "changed"
        self.assertNotEqual(result["run"]["original_input"], result["augmented_input"])
        result["original_input"]["lines"].clear()
        self.assertEqual(raw, original)

    def test_no_oracle_or_all_candidate_production_call(self):
        with patch("scripts.exact_extendibility_oracle.solve_exact", side_effect=AssertionError("oracle")), \
                patch("scripts.quaternary_all_candidate_low_color.solve_all_candidate_low_color",
                      side_effect=AssertionError("full sweep")):
            result = solve_logical_neq(six_side_fixture())
        self.assertEqual(result["run"]["status"], "solved")
        self.assertFalse(result["oracle_feedback_to_producer"])
        self.assertFalse(result["old_colors_read"])
        for name in ("quaternary_logical_neq.py", "quaternary_logical_neq_contacts.py", "quaternary_logical_neq_low_color.py"):
            tree = ast.parse((ROOT / "scripts" / name).read_text(encoding="utf-8"))
            self.assertFalse(any("oracle" in (node.module or "") for node in ast.walk(tree)
                                 if isinstance(node, ast.ImportFrom)))


if __name__ == "__main__":
    unittest.main()

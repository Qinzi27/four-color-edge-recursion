"""Guarded choice and conditional-EQ lifetime remain explicit in the new policy."""

import ast
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.quaternary_conditional_diamond_low_color import (
    INNER_POLICY, POLICY, solve_conditional_diamond, solve_diamond_contacts,
)
from scripts.quaternary_odd_wheel_low_color import solve_odd_wheel, solve_wheel_contacts
from tests.test_quaternary_conditional_diamond_contacts import diamond_trial_document
from tests.test_quaternary_logical_neq import document, six_side_fixture


class ConditionalDiamondLowColorTests(unittest.TestCase):
    """Synthetic inner controls do not establish full-policy actual reachability."""

    def test_outer_preserves_same_raw_learners_and_input_relation_contract(self):
        raw = six_side_fixture()
        old, new = solve_odd_wheel(raw), solve_conditional_diamond(raw)
        self.assertEqual(new["policy"], POLICY)
        self.assertEqual(new["run"]["policy"], INNER_POLICY)
        for field in ("learning", "original_input", "augmented_input"):
            self.assertEqual(new[field], old[field])
        self.assertEqual(new["augmented_input"]["lines"], raw["lines"])

    def test_no_new_pattern_keeps_guarded_events_and_lowest_colors(self):
        raw = document(["A", "B", "C"], [("A", "B")], anchors={"A": 1})
        old, new = solve_odd_wheel(raw)["run"], solve_conditional_diamond(raw)["run"]
        for field in ("events", "status", "colors", "domains", "choices", "probes", "rejections"):
            self.assertEqual(new[field], old[field])
        self.assertTrue(all(event["symbol"] == min(event["candidates_before"]) for event in new["events"]))

    def test_real_diamond_trial_rejects_and_does_not_leak_eq_into_next_main(self):
        raw = diamond_trial_document()
        old, new = solve_wheel_contacts(raw), solve_diamond_contacts(raw)
        self.assertEqual(old["events"][0]["kind"], "commit")
        self.assertEqual(old["status"], "conflict")
        event = new["events"][0]
        self.assertEqual((event["side"], event["symbol"], event["kind"]), ("P", 1, "reject"))
        trial = new["phases"][event["trial_phase"]]["outcome"]
        self.assertEqual(trial["conditional_eq"]["equal_names"], [["U", "V"]])
        self.assertEqual([r["outcome"]["status"] for r in trial["conditional_eq"]["rounds"]],
                         ["underdetermined", "conflict"])
        after = new["phases"][event["after_phase"]]
        self.assertEqual(after["document"]["states"]["P"], "0111")
        self.assertNotIn("P", after["document"].get("anchors", {}))
        self.assertNotIn("equal_names", after["document"])
        self.assertEqual(after["outcome"]["conditional_eq"]["equal_names"], [])
        next_event = new["events"][1]
        self.assertEqual((next_event["side"], next_event["symbol"], next_event["kind"]), ("P", 2, "commit"))
        self.assertEqual(new["status"], "solved")
        self.assertTrue(all(new["colors"][line["left"]] != new["colors"][line["right"]]
                            for line in raw["lines"]))
        self.assertNotEqual(new["colors"]["U"], new["colors"]["V"])

    def test_conditional_initial_conflict_needs_no_decision_or_probe(self):
        raw = diamond_trial_document()
        raw["anchors"] = {"P": 1}
        result = solve_diamond_contacts(raw, decision_limit=0, probe_limit=0)
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["events"], [])
        self.assertEqual((result["choices"], result["probes"], result["rejections"]), (0, 0, 0))

    def test_limits_remain_literal_and_complete_inputs_need_no_budget(self):
        raw = document(["A", "B"])
        for limits, reason in (({"decision_limit": 0}, "decision-limit-exhausted"),
                               ({"probe_limit": 0}, "probe-limit-exhausted")):
            result = solve_conditional_diamond(raw, **limits)["run"]
            self.assertEqual((result["status"], result["reason"]), ("incomplete", reason))
            self.assertEqual(result["events"], [])
        for limits in ({"decision_limit": True}, {"probe_limit": -1}, {"probe_limit": 1.5}):
            with self.assertRaises(ValueError):
                solve_diamond_contacts(raw, **limits)
        result = solve_conditional_diamond(document(["A"], anchors={"A": 4}), decision_limit=0, probe_limit=0)
        self.assertEqual(result["run"]["status"], "solved")

    def test_commits_persist_but_derived_eq_and_singletons_are_not_promoted(self):
        raw = diamond_trial_document()
        result = solve_diamond_contacts(raw)
        fixed = {}
        for event in result["events"]:
            if event["kind"] == "commit":
                fixed[event["side"]] = event["symbol"]
            after = result["phases"][event["after_phase"]]["document"]
            self.assertEqual(after.get("anchors", {}), fixed)
            self.assertEqual(after["different_names"], raw["different_names"])
            self.assertNotIn("equal_names", after)
        self.assertEqual(result["backtracks"], 0)

    def test_raw_wrapper_rejects_supplied_domains_and_unproved_relations(self):
        for extra in ({"states": {"A": "0111"}}, {"equal_names": [["A", "B"]]},
                      {"different_names": [["A", "B"]]}):
            with self.assertRaises(ValueError):
                solve_conditional_diamond(document(["A", "B"], **extra))

    def test_input_alias_and_oracle_feedback_are_absent(self):
        raw = six_side_fixture()
        before = deepcopy(raw)
        with patch("scripts.exact_extendibility_oracle.solve_exact", side_effect=AssertionError("oracle")):
            result = solve_conditional_diamond(raw)
        self.assertFalse(result["oracle_feedback_to_producer"])
        self.assertFalse(result["old_colors_read"])
        result["original_input"]["lines"].clear()
        result["augmented_input"]["different_names"][0][0] = "changed"
        self.assertEqual(raw, before)
        root = Path(__file__).resolve().parents[1]
        for filename in ("quaternary_conditional_diamond.py", "quaternary_conditional_diamond_contacts.py",
                         "quaternary_conditional_diamond_low_color.py"):
            tree = ast.parse((root / "scripts" / filename).read_text(encoding="utf-8"))
            self.assertFalse(any("oracle" in (node.module or "") for node in ast.walk(tree)
                                 if isinstance(node, ast.ImportFrom)))


if __name__ == "__main__":
    unittest.main()

"""The additive wheel version preserves frozen low-color scheduling semantics."""

import ast
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.quaternary_logical_neq_low_color import solve_logical_contacts, solve_logical_neq
from scripts.quaternary_odd_wheel_low_color import (
    INNER_POLICY, POLICY, solve_odd_wheel, solve_wheel_contacts,
)
from tests.test_quaternary_logical_neq import document, six_side_fixture
from tests.test_quaternary_odd_wheel import wheel_document


class OddWheelLowColorTests(unittest.TestCase):
    """These synthetic fixtures are separate from the formal archived gaps."""

    def test_outer_preserves_raw_learners_and_versions_inner_and_outer(self):
        raw = six_side_fixture()
        old, new = solve_logical_neq(raw), solve_odd_wheel(raw)
        self.assertEqual(new["policy"], POLICY)
        self.assertEqual(new["run"]["policy"], INNER_POLICY)
        for field in ("learning", "original_input", "augmented_input"):
            self.assertEqual(new[field], old[field])
        self.assertEqual(new["augmented_input"]["lines"], raw["lines"])

    def test_no_wheel_keeps_old_guarded_choices_and_lowest_colors(self):
        raw = document(["A", "B", "C"], [("A", "B")], anchors={"A": 1})
        old, new = solve_logical_neq(raw)["run"], solve_odd_wheel(raw)["run"]
        for field in ("events", "status", "colors", "domains", "choices", "probes", "rejections"):
            self.assertEqual(new[field], old[field])
        for event in new["events"]:
            self.assertEqual(event["symbol"], min(event["candidates_before"]))

    def test_initial_wheel_conflict_is_proved_without_any_choice(self):
        raw = wheel_document(states={side: "0111" for side in wheel_document()["sides"]})
        run = solve_wheel_contacts(raw)
        self.assertEqual(run["status"], "conflict")
        self.assertEqual((run["choices"], run["probes"], run["rejections"]), (0, 0, 0))
        self.assertEqual(run["events"], [])
        self.assertIsNotNone(run["phases"][0]["outcome"]["wheel_check"]["certificate"])

    def test_wheel_trial_rejection_uses_certificate_and_keeps_low_color_preference(self):
        # Synthetic INNER-loop control only: the outer EQ learner may discover
        # C=Z before this state. This does not establish a full-policy failure.
        raw = wheel_document()
        raw["sides"] = ["P", "Z"] + raw["sides"]
        raw["anchors"] = {"Z": 1}
        raw["lines"].append({"id": "p", "left": "P", "right": "C", "kind": "separator"})
        raw["lines"] += [{"id": f"z{i}", "left": "Z", "right": f"R{i}", "kind": "separator"}
                         for i in range(5)]
        old, new = solve_logical_contacts(raw), solve_wheel_contacts(raw)
        self.assertEqual(old["events"][0]["kind"], "commit")
        event = new["events"][0]
        self.assertEqual((event["side"], event["symbol"], event["kind"]), ("P", 1, "reject"))
        trial = new["phases"][event["trial_phase"]]["outcome"]
        self.assertEqual(trial["base_status"], "underdetermined")
        self.assertIsNotNone(trial["wheel_check"]["certificate"])
        after = new["phases"][event["after_phase"]]["document"]
        self.assertEqual(after["anchors"], {"Z": 1})
        self.assertEqual(after["states"], {"P": "0111"})
        next_event = new["events"][1]
        self.assertEqual((next_event["side"], next_event["symbol"], next_event["kind"]), ("P", 2, "commit"))
        self.assertEqual(new["status"], "solved")
        self.assertTrue(all(new["colors"][line["left"]] != new["colors"][line["right"]]
                            for line in raw["lines"]))

    def test_limits_remain_literal_and_terminal_inputs_need_no_budget(self):
        raw = document(["A", "B"])
        for limits, reason in (({"decision_limit": 0}, "decision-limit-exhausted"),
                               ({"probe_limit": 0}, "probe-limit-exhausted")):
            run = solve_odd_wheel(raw, **limits)["run"]
            self.assertEqual((run["status"], run["reason"]), ("incomplete", reason))
            self.assertEqual(run["events"], [])
        for limits in ({"decision_limit": True}, {"probe_limit": -1}, {"probe_limit": 1.5}):
            with self.assertRaises(ValueError):
                solve_wheel_contacts(raw, **limits)
        terminal = solve_odd_wheel(document(["A"], anchors={"A": 4}), decision_limit=0, probe_limit=0)
        self.assertEqual(terminal["run"]["status"], "solved")

    def test_commitments_persist_without_promoting_derived_singletons(self):
        raw = document(["A", "B", "C"], different_names=[["A", "B"], ["B", "C"]])
        result = solve_wheel_contacts(raw)
        fixed = {}
        for event in result["events"]:
            if event["kind"] == "commit":
                fixed[event["side"]] = event["symbol"]
            after = result["phases"][event["after_phase"]]["document"]
            self.assertEqual(after.get("anchors", {}), fixed)
            self.assertEqual(after["different_names"], raw["different_names"])
        self.assertEqual(result["backtracks"], 0)

    def test_existing_rejections_keep_proof_and_are_not_anchors(self):
        sides = ["A", "B", "C", "D"]
        pairs = [[a, b] for i, a in enumerate(sides) for b in sides[i + 1:]]
        raw = document(sides, states={side: "0111" for side in sides}, different_names=pairs)
        run = solve_wheel_contacts(raw)
        self.assertGreater(run["rejections"], 0)
        first = run["events"][0]
        self.assertEqual(first["kind"], "reject")
        self.assertEqual(first["extension_claim"], "refuted")
        self.assertNotIn(first["side"], run["phases"][first["after_phase"]]["document"].get("anchors", {}))

    def test_raw_wrapper_rejects_unproved_external_domain_and_relation_inputs(self):
        for extra in ({"states": {"A": "0111"}}, {"equal_names": [["A", "B"]]},
                      {"different_names": [["A", "B"]]}):
            with self.assertRaises(ValueError):
                solve_odd_wheel(document(["A", "B"], **extra))

    def test_no_input_alias_or_exact_oracle_feedback(self):
        raw = six_side_fixture()
        original = deepcopy(raw)
        with patch("scripts.exact_extendibility_oracle.solve_exact", side_effect=AssertionError("oracle")):
            result = solve_odd_wheel(raw)
        self.assertFalse(result["oracle_feedback_to_producer"])
        self.assertFalse(result["old_colors_read"])
        result["original_input"]["lines"].clear()
        result["augmented_input"]["different_names"][0][0] = "changed"
        self.assertEqual(raw, original)
        self.assertNotEqual(result["augmented_input"], result["run"]["original_input"])
        root = Path(__file__).resolve().parents[1]
        for name in ("quaternary_odd_wheel.py", "quaternary_odd_wheel_contacts.py", "quaternary_odd_wheel_low_color.py"):
            tree = ast.parse((root / "scripts" / name).read_text(encoding="utf-8"))
            self.assertFalse(any("oracle" in (node.module or "") for node in ast.walk(tree)
                                 if isinstance(node, ast.ImportFrom)))


if __name__ == "__main__":
    unittest.main()

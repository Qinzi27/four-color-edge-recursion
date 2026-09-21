"""Test the explicit new continuation policy without hiding its repair boundary."""

from copy import deepcopy
from itertools import product
import json
import unittest
from unittest.mock import patch

from fourcolor.inherited_names import initial_state
from fourcolor.kempe_history_policy import attempt_kempe_history_cut, replay_kempe_history
from fourcolor.triangle_chain_family import build_staggered_strip
from fourcolor.triangle_chain_replay import replay_staggered_history


class KempeHistoryPolicyTests(unittest.TestCase):
    """Check actual histories, full components, identities, and failure honesty."""

    def test_old_success_does_not_call_repair(self):
        state = initial_state(width=8, height=2)
        with patch("fourcolor.kempe_history_policy.single_kempe_split",
                   side_effect=AssertionError("repair must not be called")):
            result = attempt_kempe_history_cut(state, [[0, 1], [8, 1]], inherit="left")
        self.assertEqual(result["status"], "split")
        self.assertNotIn("repair_result", result)
        self.assertEqual(len(result["state"].cuts), 1)

    def test_old_successful_prefix_is_exactly_preserved(self):
        family = build_staggered_strip(2)
        old = replay_staggered_history(family, policy="forest")
        new = replay_kempe_history(family)
        for previous, current in zip(old["trace"][:-1], new["trace"]):
            for field in ("operation", "before", "after", "method", "cost_old_changes"):
                self.assertEqual(previous[field], current[field])
            self.assertNotIn("repair_result", current)
        repair = new["trace"][old["stop_step"] - 1]
        self.assertEqual(repair["before"], old["trace"][-1]["before"])
        self.assertEqual(repair["method"], "single_kempe_cost")
        self.assertEqual(repair["status"], "split")

    def test_all_six_attempts_and_selected_complete_component_are_auditable(self):
        result = replay_kempe_history(build_staggered_strip(2))
        for event in result["trace"]:
            if "repair_result" not in event:
                continue
            problem, report = event["repair_problem"], event["repair_result"]
            initial, daughters = problem["initial"], problem["daughters"]
            self.assertEqual(len(report["attempts"]), 6)
            self.assertEqual(problem["fixed"], ["outside"])
            self.assertIsNone(report["records_by_side"])
            self.assertEqual(problem["weights"]["outside"], 0)
            self.assertTrue(all(problem["weights"][side] == 0 for side in daughters))
            self.assertEqual(report["selected"], report["candidates"][0])
            for attempt in report["attempts"]:
                pair = set(attempt["pair"])
                reached = {attempt["seed"]}
                while True:
                    extended = reached | {
                        vertex for edge in problem["edges"] if set(edge) & reached
                        and all(initial[other] in pair for other in edge) for vertex in edge}
                    if extended == reached:
                        break
                    reached = extended
                self.assertEqual(reached, set(attempt["component"]))
            for candidate in report["candidates"]:
                component, pair = set(candidate["component"]), candidate["pair"]
                self.assertEqual(len(component & set(daughters)), 1)
                self.assertNotIn("outside", component)
                self.assertEqual(candidate["target"], {
                    side: pair[0] ^ pair[1] ^ color if side in component else color
                    for side, color in initial.items()})
                self.assertEqual(candidate["changed_weight"], sum(problem["weights"][side]
                                                                       for side in component))
            target = report["selected"]["target"]
            self.assertEqual({row["id"]: row["color"] for row in event["after"]["rectangles"]},
                             {side: color for side, color in target.items() if side != "outside"})
            self.assertEqual(event["cost_old_changes"], report["selected"]["changed_weight"])

    def test_actual_rectangles_cuts_and_positive_line_profiles_are_committed(self):
        result = replay_kempe_history(build_staggered_strip(1))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["committed_steps"], 8)
        for index, event in enumerate(result["trace"], 1):
            self.assertEqual(len(event["after"]["cuts"]), index)
            before = {row["id"]: row for row in event["before"]["rectangles"]}
            after = {row["id"]: row for row in event["after"]["rectangles"]}
            parent = event["actual_parent"]["id"]
            self.assertNotIn(parent, after)
            self.assertEqual(len(after.keys() - before.keys()), 2)
            for side in before.keys() & after.keys():
                self.assertEqual(before[side]["bounds"], after[side]["bounds"])
            self.assertTrue(all(row["color"] in (1, 2, 3) for row in after.values()))
            self.assertFalse(event["diagnostic_positive_names"]["conflicts"])
            self.assertEqual(len(event["diagnostic_positive_names"]["new_line_pair"]), 2)

    def test_repair_stall_stops_instead_of_using_another_solver(self):
        forced_stall = {"selected": None, "status": "stalled", "attempts": [], "candidates": []}
        with patch("fourcolor.kempe_history_policy.single_kempe_split",
                   return_value=forced_stall) as call:
            result = replay_kempe_history(build_staggered_strip(1))
        self.assertEqual(call.call_count, 1)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["stop_step"], 6)
        self.assertEqual(result["committed_steps"], 5)
        self.assertEqual(result["trace"][-1]["before"], result["trace"][-1]["after"])
        self.assertFalse(result["reached_final_parent"])
        self.assertIsNone(result["inherited_at_final_if_reached"])

    def test_declared_m1_variants_reach_the_pending_parent(self):
        family = build_staggered_strip(1)
        for inherit, row, order, reverse in product(
                ("left", "right"), ("lower_first", "upper_first"),
                ("left_to_right", "right_to_left"), (False, True)):
            result = replay_kempe_history(family, inherit=inherit, row_order=row,
                                          isolate_order=order, horizontal_reverse=reverse,
                                          vertical_reverse=reverse)
            self.assertTrue(result["reached_final_parent"])
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["inherited_at_final_if_reached"]["v0"],
                             result["inherited_at_final_if_reached"]["v2"])

    def test_hand_specified_difficult_colors_do_not_drive_the_policy(self):
        family = build_staggered_strip(1)
        changed = deepcopy(family)
        changed["problem"]["initial"] = {
            side: {0: 0, 1: 2, 2: 3, 3: 1}[color]
            for side, color in family["problem"]["initial"].items()}
        self.assertEqual(replay_kempe_history(family), replay_kempe_history(changed))

    def test_source_and_outputs_stay_portable_and_separate(self):
        family = build_staggered_strip(1)
        original = deepcopy(family)
        result = replay_kempe_history(family)
        json.dumps(result, allow_nan=False)
        self.assertEqual(family, original)
        self.assertEqual(result["cost_old_changes"], sum(row["cost_old_changes"] for row in result["trace"]))
        self.assertEqual(result["kempe_repair_attempts"], result["kempe_repair_successes"])
        self.assertNotEqual(result["policy"], "forest")
        with self.assertRaises(ValueError):
            replay_kempe_history(family, inherit="retry_both")


if __name__ == "__main__":
    unittest.main()

"""Check policy provenance, valid geometric variants, and honest early stops."""

from copy import deepcopy
from itertools import product
import json
import unittest
from unittest.mock import patch

from fourcolor.retained_profiles import attempt_profile_cut
from fourcolor.triangle_chain_family import build_staggered_strip
from fourcolor.triangle_chain_replay import (
    build_history_variant, replay_staggered_history,
)


class TriangleChainReplayTests(unittest.TestCase):
    """No test supplies an oracle coloring to a production replay policy."""

    def test_all_geometry_variants_cut_real_parents_and_preserve_leaves(self):
        # Reconstruct rectangles from raw stroke endpoints independently of
        # the variant's stored child names, child bounds, or parent labels.
        for m, row, order, horizontal, vertical in product(
                (1, 2), ("lower_first", "upper_first"),
                ("left_to_right", "right_to_left"), (False, True), (False, True)):
            family = build_staggered_strip(m)
            active = [family["bounds"][:]]
            history = build_history_variant(
                family, row_order=row, isolate_order=order,
                horizontal_reverse=horizontal, vertical_reverse=vertical)
            for step in history:
                self.assertIn(step["parent_bounds"], active)
                parent = step["parent_bounds"]
                self.assertEqual(active.count(parent), 1)
                active.remove(parent)
                first, second = parent[:], parent[:]
                p, q = step["points"]
                if p[0] == q[0]:
                    self.assertEqual(sorted((p[1], q[1])), parent[2:])
                    self.assertLess(parent[0], p[0])
                    self.assertLess(p[0], parent[1])
                    first[1], second[0] = p[0], p[0]
                else:
                    self.assertEqual(p[1], q[1])
                    self.assertEqual(sorted((p[0], q[0])), parent[:2])
                    self.assertLess(parent[2], p[1])
                    self.assertLess(p[1], parent[3])
                    first[3], second[2] = p[1], p[1]
                active.extend((first, second))
            self.assertEqual(sorted(active), sorted(family["rectangles"].values()))
            self.assertEqual(history[-1]["parent_bounds"], family["parent_rectangle"])
            self.assertEqual(len(history), 6 * m + 2)

    def test_default_history_matches_existing_geometric_certificate(self):
        family = build_staggered_strip(2)
        history = build_history_variant(family)
        for actual, old in zip(history, family["guillotine_steps"]):
            for key in ("parent", "axis", "at", "children"):
                self.assertEqual(actual[key], old[key])

    def test_default_policy_stops_are_concrete_historical_outcomes(self):
        # Distinguish the earlier local-mex stop from supported strip repairs.
        expected = {("plain", "left"): 3, ("plain", "right"): 6,
                    ("strip", "left"): 6, ("strip", "right"): 6,
                    ("forest", "left"): 6, ("forest", "right"): 6}
        for (policy, inherit), step in expected.items():
            result = replay_staggered_history(build_staggered_strip(1),
                                               policy=policy, inherit=inherit)
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["stop_step"], step)
            self.assertEqual(result["committed_steps"], step - 1)
            self.assertEqual(len(result["trace"]), step)
            self.assertFalse(result["reached_final_parent"])
            self.assertIsNone(result["inherited_at_final_if_reached"])
            self.assertEqual(result["trace"][-1]["before"], result["trace"][-1]["after"])
            self.assertEqual(result["trace"][-1]["actual_children"], [])

    def test_stops_without_retry_or_hidden_continuation(self):
        with patch("fourcolor.triangle_chain_replay.attempt_profile_cut",
                   wraps=attempt_profile_cut) as traced:
            result = replay_staggered_history(build_staggered_strip(1), policy="plain")
        self.assertEqual(traced.call_count, 3)
        self.assertEqual(result["committed_steps"], 2)
        self.assertTrue(all(call.kwargs == {"inherit": "left", "synchronize": False}
                            for call in traced.call_args_list))

    def test_supplied_difficult_coloring_never_selects_replay_names(self):
        original = build_staggered_strip(2)
        permuted = deepcopy(original)
        permutation = {0: 0, 1: 3, 2: 2, 3: 1}
        permuted["problem"]["initial"] = {
            side: permutation[color] for side, color in original["problem"]["initial"].items()}
        # Both are legal certificates, but the same geometric run must produce
        # precisely the same names from the one-rectangle initialization.
        self.assertEqual(replay_staggered_history(original),
                         replay_staggered_history(permuted))

    def test_trace_has_legal_names_and_exact_old_identity_costs(self):
        result = replay_staggered_history(build_staggered_strip(2), policy="forest")
        total = 0
        for event in result["trace"]:
            before = {row["id"]: row for row in event["before"]["rectangles"]}
            after = {row["id"]: row for row in event["after"]["rectangles"]}
            changed = {key for key in before.keys() & after.keys()
                       if before[key]["color"] != after[key]["color"]}
            self.assertEqual(changed, {row["id"] for row in event["changed_old_sides"]})
            self.assertEqual(len(changed), event["cost_old_changes"])
            self.assertTrue(all(row["color"] in (1, 2, 3) for row in after.values()))
            self.assertEqual(event["after"]["exterior_color"], 0)
            total += len(changed)
        self.assertEqual(total, result["cost_old_changes"])
        # Here the strip rule can switch which daughter inherits the old name
        # at an endpoint split, so synchronization need not change any old side.
        self.assertTrue(any(event["method"] == "verified_strip_sync"
                            for event in result["trace"]))
        self.assertEqual(total, 0)

    def test_outputs_are_portable_and_do_not_mutate_family(self):
        family = build_staggered_strip(1)
        before = deepcopy(family)
        output = replay_staggered_history(family)
        json.dumps(output, allow_nan=False)
        output["history"][0]["parent_bounds"][0] = 999
        self.assertEqual(family, before)

    def test_invalid_options_and_geometry_are_rejected(self):
        family = build_staggered_strip(1)
        for options in ({"row_order": "random"}, {"isolate_order": "random"},
                        {"horizontal_reverse": 1}, {"vertical_reverse": "yes"}):
            with self.assertRaises(ValueError):
                build_history_variant(family, **options)
        for options in ({"policy": "BFS"}, {"inherit": "retry_both"}):
            with self.assertRaises(ValueError):
                replay_staggered_history(family, **options)
        family["rectangles"]["v0"][0] -= 1
        with self.assertRaises(ValueError):
            build_history_variant(family)


if __name__ == "__main__":
    unittest.main()

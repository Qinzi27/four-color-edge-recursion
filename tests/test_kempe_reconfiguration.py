"""Independent finite state-graph oracles for bounded Kempe reconfiguration.

The oracle enumerates all proper colorings, then derives transitions by
comparing pairs of states and checking all cuts of their changed subset.
It shares neither traversal nor component generation with production code.
"""

from collections import deque
from copy import deepcopy
from itertools import combinations, product
import json
import unittest

from fourcolor.kempe_reconfiguration import search_kempe_repairs, verify_kempe_repair


def full_state_oracle(edges, initial, daughters, fixed, weights, records):
    """Exhaust a tiny graph's proper states and shortest additive-cost paths."""
    vertices = tuple(initial)
    positions = {vertex: index for index, vertex in enumerate(vertices)}
    indexed_edges = tuple((positions[left], positions[right]) for left, right in edges)
    anchors = tuple(positions[vertex] for vertex in fixed)
    children = tuple(positions[vertex] for vertex in daughters)
    start = tuple(initial.values())
    states = [state for state in product(range(4), repeat=len(vertices))
              if all(state[index] == start[index] for index in anchors)
              and all(state[left] != state[right] for left, right in indexed_edges)]
    transitions = {state: [] for state in states}
    for before, after in combinations(states, 2):
        changed = tuple(index for index in range(len(vertices)) if before[index] != after[index])
        pair = tuple(sorted((before[changed[0]], after[changed[0]])))
        if any(before[index] not in pair or after[index] != pair[0] ^ pair[1] ^ before[index]
               for index in changed):
            continue
        reached = set(changed)
        # Induced-color closure excludes a proper subset of a component.
        if any((left in reached) != (right in reached)
               for left, right in indexed_edges if before[left] in pair and before[right] in pair):
            continue
        # Every nontrivial cut needs an internal edge: no DFS/BFS reuse here.
        connected = True
        for flags in product((False, True), repeat=len(changed)):
            cut = {index for index, flag in zip(changed, flags) if flag}
            if cut and cut != reached and not any(
                    (left in cut) != (right in cut) for left, right in indexed_edges
                    if left in reached and right in reached):
                connected = False
                break
        if not connected:
            continue
        named = tuple(vertices[index] for index in changed)
        record_count = 0 if records is None else len({record for vertex in named for record in records[vertex]})
        weight = sum(weights[vertex] for vertex in named)
        transitions[before].append((after, record_count, weight, (pair, changed)))
        transitions[after].append((before, record_count, weight, (pair, changed)))
    # First establish distances on the complete independent state graph.
    distance, queue = {start: 0}, deque([start])
    while queue:
        before = queue.popleft()
        for after, *_ in transitions[before]:
            if after not in distance:
                distance[after] = distance[before] + 1
                queue.append(after)
    goals = [state for state in distance if state[children[0]] != state[children[1]]]
    if not goals:
        return {"status": "unreachable", "reachable_count": len(distance)}
    minimum = min(distance[state] for state in goals)
    goals = [state for state in goals if distance[state] == minimum]
    # Optimize over all edges in the shortest-path DAG, independently of the
    # search's layer insertion order and predecessor updates.
    costs = {start: (0, 0, ())}
    for depth in range(minimum):
        for before in states:
            if distance.get(before) != depth:
                continue
            for after, record_count, weight, key in transitions[before]:
                if distance.get(after) != depth + 1:
                    continue
                candidate = (costs[before][0] + record_count, costs[before][1] + weight,
                             costs[before][2] + (key,))
                if after not in costs or candidate < costs[after]:
                    costs[after] = candidate
    best = min(goals, key=costs.get)
    return {"status": "repaired", "shortest_steps": minimum, "goal_count": len(goals),
            "cost": costs[best], "target": dict(zip(vertices, best))}


def hard_fixture():
    """Return the published 20260927 hard snapshot, with its pending edge removed."""
    full = [(0, 1), (0, 2), (0, 3), (0, 4), (0, 5), (0, 6), (0, 7), (0, 8),
            (1, 2), (1, 8), (1, 9), (2, 3), (2, 9), (3, 4), (3, 7), (3, 9),
            (4, 5), (4, 7), (5, 6), (5, 7), (6, 7), (7, 8), (7, 9), (8, 9)]
    edges = [(str(left), str(right)) for left, right in full if (left, right) != (3, 7)]
    initial = dict(zip(map(str, range(10)), (0, 1, 2, 1, 3, 2, 3, 1, 2, 3)))
    return edges, initial, ("3", "7")


class KempeReconfigurationTests(unittest.TestCase):
    """Check shortest-layer guarantees, anchored moves, budgets, and witnesses."""

    def test_hard_case_requires_preparatory_components_and_three_layers(self):
        edges, initial, daughters = hard_fixture()
        result = search_kempe_repairs(edges, initial, daughters, fixed=("0",))
        self.assertEqual(result["status"], "repaired")
        self.assertEqual(result["shortest_steps"], 3)
        self.assertEqual(result["target_layer_candidate_count"], 12)
        self.assertEqual([layer["state_count"] for layer in result["layers"]], [1, 5, 15, 31])
        self.assertEqual(result["visited_states"], 52)
        self.assertTrue(result["shortest_steps_certified"])
        self.assertTrue(result["cost_optimal_within_shortest"])
        steps = result["selected"]["steps"]
        self.assertTrue(all(not set(step["component"]).intersection(daughters) for step in steps[:2]))
        self.assertTrue(all(step["after"]["0"] == 0 for step in steps))
        self.assertTrue(verify_kempe_repair(result))

    def test_single_anchor_and_multiple_fixed_blockers(self):
        anchored = search_kempe_repairs([], {"x": 0, "y": 0}, ("x", "y"), fixed=("x",))
        self.assertEqual(anchored["status"], "repaired")
        self.assertEqual(anchored["selected"]["steps"][0]["component"], ("y",))
        self.assertEqual(anchored["target_layer_candidate_count"], 3)
        # Both daughters frozen makes every reachable state a nontarget.
        blocked = search_kempe_repairs([], {"x": 0, "y": 0, "z": 2}, ("x", "y"),
                                       fixed=("x", "y"))
        self.assertEqual(blocked["status"], "unreachable")
        self.assertEqual(blocked["visited_states"], 4)
        self.assertEqual(blocked["stop_reason"], "reachable_component_exhausted")
        self.assertFalse(blocked["shortest_steps_certified"])

    def test_multistep_cost_optimum_matches_full_independent_hard_state_graph(self):
        # Independently enumerating all 4^10 assignments leaves a small
        # anchored proper-state graph. The expensive side changes the best
        # three-step route, so this exercises more than deterministic BFS.
        edges, initial, daughters = hard_fixture()
        weights = {vertex: 100 if vertex == "2" else 1 for vertex in initial}
        records = {vertex: ("shared", vertex) for vertex in initial}
        for associations in (None, records):
            expected = full_state_oracle(edges, initial, daughters, ("0",), weights, associations)
            actual = search_kempe_repairs(edges, initial, daughters, fixed=("0",),
                                          weights=weights, records_by_side=associations)
            selected = actual["selected"]
            self.assertEqual(actual["shortest_steps"], expected["shortest_steps"])
            self.assertEqual(actual["target_layer_candidate_count"], expected["goal_count"])
            self.assertEqual(selected["target"], expected["target"])
            self.assertEqual(selected["cumulative_changed_weight"], expected["cost"][1])
            if associations is not None:
                self.assertEqual(selected["cumulative_changed_record_count"], expected["cost"][0])
            else:
                self.assertEqual(selected["cumulative_changed_weight"], 4)
                self.assertEqual(selected["steps"][-1]["component"], ("5", "7"))
            path = tuple((step["pair"], tuple(tuple(initial).index(vertex) for vertex in step["component"]))
                         for step in selected["steps"])
            self.assertEqual(path, expected["cost"][2])

    def test_depth_and_state_caps_do_not_become_unreachable(self):
        edges, initial, daughters = hard_fixture()
        depth = search_kempe_repairs(edges, initial, daughters, fixed=("0",), max_depth=2)
        self.assertEqual((depth["status"], depth["stop_reason"]), ("unknown", "depth_limit"))
        self.assertEqual(depth["visited_states"], 21)
        self.assertIsNone(depth["selected"])
        self.assertFalse(depth["cost_optimal_within_shortest"])
        states = search_kempe_repairs(edges, initial, daughters, fixed=("0",), max_states=10)
        self.assertEqual((states["status"], states["stop_reason"]), ("unknown", "state_limit"))
        self.assertEqual(states["visited_states"], 10)
        self.assertFalse(states["layers"][-1]["generation_complete"])
        zero = search_kempe_repairs([], {"x": 0, "y": 0}, ("x", "y"), max_depth=0)
        self.assertEqual(zero["status"], "unknown")
        self.assertEqual(zero["visited_states"], 1)

    def test_truncated_successful_layer_does_not_claim_optimized_success(self):
        partial = search_kempe_repairs([], {"x": 0, "y": 0}, ("x", "y"), max_states=2)
        self.assertEqual(partial["status"], "unknown")
        self.assertEqual(partial["target_layer_candidate_count"], 1)
        self.assertIsNone(partial["selected"])
        self.assertFalse(partial["shortest_steps_certified"])
        complete = search_kempe_repairs([], {"x": 0, "y": 0}, ("x", "y"), max_states=7)
        self.assertEqual(complete["status"], "repaired")
        self.assertEqual(complete["target_layer_candidate_count"], 6)
        self.assertEqual(complete["visited_states"], 7)

    def test_record_cost_precedes_weight_and_missing_records_are_not_zero(self):
        initial, weights = {"x": 0, "y": 0}, {"x": 10, "y": 0}
        records = {"x": ("one", "one"), "y": ("a", "b", "c")}
        result = search_kempe_repairs([], initial, ("x", "y"), weights=weights, records_by_side=records)
        self.assertEqual(result["selected"]["target"], {"x": 1, "y": 0})
        self.assertEqual(result["selected"]["cumulative_changed_record_count"], 1)
        self.assertEqual(result["selected"]["cumulative_changed_weight"], 10)
        unmeasured = search_kempe_repairs([], initial, ("x", "y"), weights=weights)
        self.assertEqual(unmeasured["selected"]["target"], {"x": 0, "y": 1})
        self.assertIsNone(unmeasured["selected"]["cumulative_changed_record_count"])
        self.assertIsNone(unmeasured["selected"]["net_changed_record_count"])
        self.assertTrue(verify_kempe_repair(json.loads(json.dumps(result))))

    def test_replay_distinguishes_repeated_writes_from_endpoint_net_cost(self):
        result = search_kempe_repairs([], {"x": 0, "y": 0}, ("x", "y"), fixed=("x",),
                                      records_by_side={"x": (), "y": ("r",)})
        witness = deepcopy(result["selected"])
        first = witness["steps"][0]
        second = {**deepcopy(first), "pair": (1, 2), "before": {"x": 0, "y": 1},
                  "after": {"x": 0, "y": 2}}
        third = {**deepcopy(second), "before": {"x": 0, "y": 2}, "after": {"x": 0, "y": 1}}
        witness["steps"] = [first, second, third]
        for key in ("cumulative_changed_weight", "cumulative_changed_side_count", "cumulative_changed_record_count"):
            witness[key] = 3
        self.assertEqual(witness["net_changed_record_count"], 1)
        # The verifier checks feasibility and costs, not the route's optimality.
        self.assertTrue(verify_kempe_repair(result, witness))
        witness["cumulative_changed_record_count"] = 1
        self.assertFalse(verify_kempe_repair(result, witness))

    def test_tampered_steps_and_cost_metadata_are_rejected(self):
        edges, initial, daughters = hard_fixture()
        result = search_kempe_repairs(edges, initial, daughters, fixed=("0",),
                                      records_by_side={vertex: ("shared", vertex) for vertex in initial})
        corruptions = [
            lambda row: row["selected"]["steps"][0].update(component=("9", "9")),
            lambda row: row["selected"]["steps"][0].update(component=("0",)),
            lambda row: row["selected"]["steps"][0].update(pair=(0, True)),
            lambda row: row["selected"]["steps"][0]["before"].update({"0": False}),
            lambda row: row["selected"]["steps"][0]["after"].update({"1": 2}),
            lambda row: row["selected"]["steps"][0].update(changed_record_count=999),
            lambda row: row["selected"]["steps"][0].update(changed_weight=True),
            lambda row: row["selected"]["steps"].reverse(),
            lambda row: row["selected"]["target"].update({"0": False}),
            lambda row: row["selected"].update(net_changed_record_ids=("shared",)),
            lambda row: row["selected"].update(cumulative_changed_side_count=0),
        ]
        for corrupt in corruptions:
            changed = deepcopy(result)
            corrupt(changed)
            self.assertFalse(verify_kempe_repair(changed))
        # A proper subset of a connected two-color component is invalid even
        # if the report claims a different after-state and cheap costs.
        partial = {"base_edges": [("x", "a")], "initial": {"x": 0, "a": 1, "y": 0},
                   "daughters": ("x", "y"), "fixed": (),
                   "weights": {"x": 1, "a": 1, "y": 1}, "records_by_side": None,
                   "selected": {"steps": [{"pair": (0, 1), "component": ("x",),
                                             "before": {"x": 0, "a": 1, "y": 0},
                                             "after": {"x": 1, "a": 1, "y": 0}}]}}
        self.assertFalse(verify_kempe_repair(partial))

    def test_invalid_inputs_and_budget_types_are_rejected(self):
        valid = {"x": 0, "y": 0}
        invalid = [
            ([], {}, ("x", "y"), {}), ([], {"x": True, "y": 0}, ("x", "y"), {}),
            ([], {"x": 0, "y": 1}, ("x", "y"), {}), ([("x", "y")], valid, ("x", "y"), {}),
            ([("x", "x")], valid, ("x", "y"), {}), ([("x", "missing")], valid, ("x", "y"), {}),
            ([], valid, "xy", {}), ([], valid, ("x", "x"), {}),
            ([], valid, ("x", "y"), {"fixed": ("missing",)}),
            ([], valid, ("x", "y"), {"weights": {"x": -1, "y": 0}}),
            ([], valid, ("x", "y"), {"records_by_side": {"x": (), "y": "r"}}),
        ]
        invalid += [([], valid, ("x", "y"), {name: value})
                    for name, values in (("max_states", (0, -1, True, 1.5, None)),
                                         ("max_depth", (-1, True, 1.5, None))) for value in values]
        for edges, initial, daughters, kwargs in invalid:
            with self.subTest(initial=initial, daughters=daughters, kwargs=kwargs):
                with self.assertRaises(ValueError):
                    search_kempe_repairs(edges, initial, daughters, **kwargs)

    def test_input_snapshots_and_duplicate_normalization(self):
        edges, initial = [["x", "a"], ["a", "x"]], {"x": 0, "a": 1, "y": 0}
        records = {"x": ["r", "r"], "a": [], "y": []}
        result = search_kempe_repairs(edges, initial, ("x", "y"), fixed=("a", "a"), records_by_side=records)
        edges[0][0] = "missing"
        initial["x"] = 3
        records["x"].append("new")
        self.assertEqual(result["base_edges"], (("x", "a"),))
        self.assertEqual(result["initial"]["x"], 0)
        self.assertEqual(result["fixed"], ("a",))
        self.assertEqual(result["records_by_side"]["x"], ("r",))
        self.assertTrue(verify_kempe_repair(result))

    def test_complete_small_graph_state_spaces_match_independent_oracle(self):
        # Every graph compatible with these four-vertex starting colors is
        # included. Four anchor sets cover none, one daughter, a nondaughter,
        # and the conclusive two-daughter obstruction.
        vertices, initial = ("x", "y", "z", "w"), {"x": 0, "y": 0, "z": 1, "w": 2}
        weights = {"x": 4, "y": 1, "z": 0, "w": 2}
        records = {"x": ("shared", "x"), "y": ("y",), "z": ("shared",), "w": ("w",)}
        possible = tuple(edge for edge in combinations(vertices, 2) if initial[edge[0]] != initial[edge[1]])
        checked = 0
        for flags in product((False, True), repeat=len(possible)):
            edges = tuple(edge for edge, flag in zip(possible, flags) if flag)
            for fixed in ((), ("x",), ("z",), ("x", "y")):
                expected = full_state_oracle(edges, initial, ("x", "y"), fixed, weights, records)
                actual = search_kempe_repairs(edges, initial, ("x", "y"), fixed=fixed,
                                              weights=weights, records_by_side=records, max_depth=256)
                self.assertEqual(actual["status"], expected["status"])
                if actual["status"] == "unreachable":
                    self.assertEqual(actual["visited_states"], expected["reachable_count"])
                else:
                    selected = actual["selected"]
                    self.assertEqual(actual["shortest_steps"], expected["shortest_steps"])
                    self.assertEqual(actual["target_layer_candidate_count"], expected["goal_count"])
                    self.assertEqual(selected["cumulative_changed_record_count"], expected["cost"][0])
                    self.assertEqual(selected["cumulative_changed_weight"], expected["cost"][1])
                    self.assertEqual(selected["target"], expected["target"])
                    actual_path = tuple((step["pair"], tuple(vertices.index(vertex) for vertex in step["component"]))
                                        for step in selected["steps"])
                    self.assertEqual(actual_path, expected["cost"][2])
                    self.assertTrue(verify_kempe_repair(actual))
                checked += 1
        self.assertEqual(checked, 128)


if __name__ == "__main__":
    unittest.main()

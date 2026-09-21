"""Independent full-coloring oracles for net-change budget feasibility."""

from itertools import combinations, product
import json
import random
import unittest

from fourcolor.conservative_recoloring import find_budget_target


def brute_force_minimum(edges, initial, daughters, fixed, weights):
    """Enumerate all 4**n targets directly, without conflict-driven branching."""
    vertices = tuple(initial)
    constraints = tuple(edges) + (tuple(daughters),)
    best = None
    for colors in product(range(4), repeat=len(vertices)):
        target = dict(zip(vertices, colors))
        if any(target[vertex] != initial[vertex] for vertex in fixed):
            continue
        if any(target[left] == target[right] for left, right in constraints):
            continue
        cost = sum(weights[vertex] for vertex in vertices
                   if target[vertex] != initial[vertex])
        best = cost if best is None else min(best, cost)
    return best


class ConservativeRecoloringTests(unittest.TestCase):
    """Check endpoint feasibility independently from any legal recoloring path."""

    def assert_witness(self, result, edges, initial, daughters, fixed, weights, budget):
        """Check returned symbols, net costs, and actual constraints directly."""
        self.assertEqual(result["status"], "found")
        target = result["target"]
        self.assertEqual(set(target), set(initial))
        self.assertTrue(all(type(color) is int and 0 <= color <= 3 for color in target.values()))
        self.assertTrue(all(target[left] != target[right]
                            for left, right in tuple(edges) + (tuple(daughters),)))
        self.assertTrue(all(target[vertex] == initial[vertex] for vertex in fixed))
        changed = tuple(vertex for vertex in initial if target[vertex] != initial[vertex])
        cost = sum(weights[vertex] for vertex in changed)
        self.assertEqual(result["changed_vertices"], changed)
        self.assertEqual(result["changed_side_count"], len(changed))
        self.assertEqual(result["changed_weight"], cost)
        self.assertLessEqual(cost, budget)
        self.assertFalse(result["search_exhausted"])

    def test_zero_budget_can_change_several_zero_weight_vertices(self):
        # Fixed colors 2 and 3 leave x--a as an atomic 0/1 swap. All other
        # vertices are fixed, so no single legal vertex move can start it.
        initial = {"x": 0, "a": 1, "y": 0, "two": 2, "three": 3}
        edges = [("x", "a"), ("x", "two"), ("x", "three"),
                 ("a", "two"), ("a", "three")]
        fixed = ("y", "two", "three")
        weights = {vertex: 0 if vertex in ("x", "a") else 1 for vertex in initial}
        result = find_budget_target(edges, initial, ("x", "y"), fixed=fixed,
                                    weights=weights, max_changes=0)
        self.assert_witness(result, edges, initial, ("x", "y"), fixed, weights, 0)
        self.assertEqual(result["changed_vertices"], ("x", "a"))
        self.assertEqual(result["maximum_depth"], 2)
        self.assertEqual(result["path_semantics"], "target_only_search_states_may_violate_edges")

    def test_weighted_budget_is_net_cost_not_number_of_changed_sides(self):
        initial = {"x": 0, "y": 0}
        weights = {"x": 7, "y": 5}
        too_small = find_budget_target([], initial, ("x", "y"), weights=weights, max_changes=4)
        self.assertEqual(too_small["status"], "infeasible_budget")
        self.assertTrue(too_small["search_exhausted"])
        self.assertIsNone(too_small["target"])
        enough = find_budget_target([], initial, ("x", "y"), weights=weights, max_changes=5)
        self.assert_witness(enough, [], initial, ("x", "y"), (), weights, 5)
        self.assertEqual(enough["changed_vertices"], ("y",))

    def test_long_forced_zero_weight_repair_uses_no_python_recursion(self):
        # Every chain vertex is constrained against fixed colors 2 and 3.
        # Separating its first vertex from fixed y forces the entire chain
        # to exchange 0 and 1, exceeding Python's ordinary recursion limit.
        chain = tuple(f"s{index}" for index in range(1100))
        initial = {vertex: index % 2 for index, vertex in enumerate(chain)}
        initial.update({"y": 0, "two": 2, "three": 3})
        edges = list(zip(chain, chain[1:]))
        edges.extend((vertex, fixed) for vertex in chain for fixed in ("two", "three"))
        fixed = ("y", "two", "three")
        weights = {vertex: 0 for vertex in initial}
        result = find_budget_target(edges, initial, (chain[0], "y"), fixed=fixed,
                                    weights=weights, max_changes=0, max_nodes=1101)
        self.assert_witness(result, edges, initial, (chain[0], "y"), fixed, weights, 0)
        self.assertEqual(result["nodes"], 1101)
        self.assertEqual(result["maximum_depth"], 1100)
        self.assertEqual(result["changed_vertices"], chain)

    def test_caps_distinguish_unknown_from_exhaustion_even_at_exact_boundary(self):
        initial = {"x": 0, "y": 0}
        zero = find_budget_target([], initial, ("x", "y"), max_nodes=0)
        self.assertEqual((zero["status"], zero["nodes"]), ("unknown", 0))
        one = find_budget_target([], initial, ("x", "y"), max_nodes=1)
        self.assertEqual((one["status"], one["nodes"]), ("unknown", 1))
        self.assertFalse(one["search_exhausted"])
        self.assertIsNone(one["changed_weight"])
        two = find_budget_target([], initial, ("x", "y"), max_nodes=2)
        self.assertEqual((two["status"], two["nodes"]), ("found", 2))
        # If no successors exist, examining the final permitted node really
        # exhausts the search; reaching the numeric cap alone is not unknown.
        exhausted = find_budget_target([], initial, ("x", "y"), fixed=("x", "y"),
                                       max_nodes=1)
        self.assertEqual((exhausted["status"], exhausted["nodes"]), ("infeasible_budget", 1))

    def test_complete_graph_obstruction_has_no_target_at_any_budget(self):
        # K5 minus one edge has a proper inherited four-coloring, while
        # submitting that edge creates a non-four-colorable graph.
        initial = {"x": 0, "y": 0, "one": 1, "two": 2, "three": 3}
        edges = [edge for edge in combinations(initial, 2) if set(edge) != {"x", "y"}]
        weights = {vertex: 0 for vertex in initial}
        result = find_budget_target(edges, initial, ("x", "y"), weights=weights, max_changes=0)
        self.assertIsNone(brute_force_minimum(edges, initial, ("x", "y"), (), weights))
        self.assertEqual(result["status"], "infeasible_budget")
        self.assertTrue(result["search_exhausted"])

    def test_hard_case_minimum_two_old_sides_is_recovered_without_kempe(self):
        full = [(0, 1), (0, 2), (0, 3), (0, 4), (0, 5), (0, 6), (0, 7), (0, 8),
                (1, 2), (1, 8), (1, 9), (2, 3), (2, 9), (3, 4), (3, 7), (3, 9),
                (4, 5), (4, 7), (5, 6), (5, 7), (6, 7), (7, 8), (7, 9), (8, 9)]
        edges = [(str(left), str(right)) for left, right in full if (left, right) != (3, 7)]
        initial = dict(zip(map(str, range(10)), (0, 1, 2, 1, 3, 2, 3, 1, 2, 3)))
        weights = {vertex: int(vertex not in ("3", "7")) for vertex in initial}
        insufficient = find_budget_target(edges, initial, ("3", "7"), fixed=("0",),
                                          weights=weights, max_changes=1)
        self.assertEqual(insufficient["status"], "infeasible_budget")
        repaired = find_budget_target(edges, initial, ("3", "7"), fixed=("0",),
                                      weights=weights, max_changes=2)
        self.assert_witness(repaired, edges, initial, ("3", "7"), ("0",), weights, 2)
        self.assertEqual(repaired["changed_weight"], 2)

    def test_all_four_vertex_graphs_and_weights_match_independent_oracle(self):
        vertices = ("x", "y", "z", "w")
        weight_profiles = ((1, 1, 1, 1), (0, 0, 0, 0), (0, 0, 2, 3))
        checked = 0
        for z_color, w_color in product(range(4), repeat=2):
            initial = dict(zip(vertices, (0, 0, z_color, w_color)))
            possible = tuple(edge for edge in combinations(vertices, 2)
                             if initial[edge[0]] != initial[edge[1]])
            for flags in product((False, True), repeat=len(possible)):
                edges = tuple(edge for edge, present in zip(possible, flags) if present)
                for fixed in ((), ("x",), ("z",), ("x", "y")):
                    for profile in weight_profiles:
                        weights = dict(zip(vertices, profile))
                        minimum = brute_force_minimum(edges, initial, ("x", "y"), fixed, weights)
                        # Each fixture probes impossibility below its optimum
                        # and feasibility at it; globally impossible fixtures
                        # also receive the full available budget.
                        budgets = (0, sum(profile)) if minimum is None else tuple(sorted({0, max(0, minimum - 1), minimum}))
                        for budget in budgets:
                            result = find_budget_target(edges, initial, ("x", "y"), fixed=fixed,
                                                        weights=weights, max_changes=budget)
                            expected = minimum is not None and minimum <= budget
                            with self.subTest(initial=initial, edges=edges, fixed=fixed,
                                              weights=weights, budget=budget):
                                self.assertEqual(result["status"], "found" if expected else "infeasible_budget")
                                if expected:
                                    self.assert_witness(result, edges, initial, ("x", "y"), fixed, weights, budget)
                                else:
                                    self.assertTrue(result["search_exhausted"])
                            checked += 1
        self.assertGreater(checked, 5000)

    def test_seeded_six_vertex_instances_match_full_target_enumeration(self):
        rng = random.Random(20260920)
        vertices = tuple(map(str, range(6)))
        for case in range(80):
            initial = {vertex: rng.randrange(4) for vertex in vertices}
            initial["0"] = initial["1"] = 0
            edges = tuple(edge for edge in combinations(vertices, 2)
                          if initial[edge[0]] != initial[edge[1]] and rng.random() < 0.6)
            fixed = tuple(vertex for vertex in vertices if rng.random() < 0.25)
            weights = {vertex: rng.choice((0, 0, 1, 2, 3)) for vertex in vertices}
            budget = rng.randrange(5)
            minimum = brute_force_minimum(edges, initial, ("0", "1"), fixed, weights)
            result = find_budget_target(edges, initial, ("0", "1"), fixed=fixed,
                                        weights=weights, max_changes=budget)
            expected = minimum is not None and minimum <= budget
            with self.subTest(case=case):
                self.assertEqual(result["status"], "found" if expected else "infeasible_budget")
                if expected:
                    self.assert_witness(result, edges, initial, ("0", "1"), fixed, weights, budget)

    def test_inputs_are_copied_normalized_and_result_is_json_serializable(self):
        initial = {"x": 0, "a": 1, "y": 0}
        edges = [["a", "x"], ["x", "a"]]
        weights = {"x": 1, "a": 0, "y": 3}
        result = find_budget_target(edges, initial, ("x", "y"), fixed=["a", "a"], weights=weights)
        initial["x"] = 3
        edges[0][0] = "missing"
        weights["x"] = 99
        self.assertEqual(result["initial"]["x"], 0)
        self.assertEqual(result["base_edges"], (("x", "a"),))
        self.assertEqual(result["fixed"], ("a",))
        self.assertEqual(result["weights"]["x"], 1)
        self.assertEqual(json.loads(json.dumps(result))["status"], "found")

    def test_invalid_inputs_are_rejected(self):
        valid = {"x": 0, "y": 0}
        cases = [
            ([], {}, ("x", "y"), {}),
            ([], {"x": True, "y": 0}, ("x", "y"), {}),
            ([], {"x": 4, "y": 0}, ("x", "y"), {}),
            ([], {"": 0, "y": 0}, ("", "y"), {}),
            ([], {"x": 0, "y": 1}, ("x", "y"), {}),
            ([("x", "y")], valid, ("x", "y"), {}),
            ([("x", "x")], valid, ("x", "y"), {}),
            ([("x", "unknown")], valid, ("x", "y"), {}),
            (None, valid, ("x", "y"), {}),
            (["xy"], valid, ("x", "y"), {}),
            ([], valid, "xy", {}),
            ([], valid, None, {}),
            ([], valid, ("x",), {}),
            ([], valid, ("x", "x"), {}),
            ([], valid, ("x", "unknown"), {}),
            ([], valid, ("x", []), {}),
            ([], valid, ("x", "y"), {"fixed": "x"}),
            ([], valid, ("x", "y"), {"fixed": ["unknown"]}),
            ([], valid, ("x", "y"), {"weights": {"x": 1}}),
            ([], valid, ("x", "y"), {"weights": {"x": -1, "y": 0}}),
            ([], valid, ("x", "y"), {"weights": {"x": True, "y": 0}}),
            ([], valid, ("x", "y"), {"weights": {"x": 1.5, "y": 0}}),
        ]
        for option in ("max_changes", "max_nodes"):
            cases.extend(([], valid, ("x", "y"), {option: bad})
                         for bad in (-1, True, 1.5, "3", None))
        for edges, initial, daughters, kwargs in cases:
            with self.subTest(edges=edges, initial=initial, daughters=daughters, kwargs=kwargs):
                with self.assertRaises(ValueError):
                    find_budget_target(edges, initial, daughters, **kwargs)


if __name__ == "__main__":
    unittest.main()

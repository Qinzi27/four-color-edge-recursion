"""Independently compare the three-color equality quotient with literal targets."""

from itertools import combinations, product
import random
import unittest

from fourcolor.apex_triangle_cost import apex_triangle_cost_table


class ApexTriangleCostTests(unittest.TestCase):
    """Equality compression must preserve targets and initial-color-dependent cost."""

    def test_random_small_graphs_against_direct_assignments(self):
        """Fixed-seed exhaustive target oracles cover arbitrary interior constraints."""
        rng = random.Random(20260921)
        for _ in range(70):
            inner = [f"s{i}" for i in range(5)]
            initial = {"r": 0, **{v: rng.randrange(1, 4) for v in inner}}
            initial[inner[1]] = initial[inner[0]]
            edges = [("r", v) for v in inner]
            edges += [(u, v) for u, v in combinations(inner, 2)
                      if initial[u] != initial[v] and rng.randrange(2)]
            daughters = inner[:2]
            weights = {v: rng.randrange(3) for v in initial}
            result = apex_triangle_cost_table(edges, initial, daughters, apex="r", weights=weights)
            expected = {(a, b): [] for a in range(4) for b in range(4)}
            for colors in product(range(4), repeat=5):
                target = {"r": 0, **dict(zip(inner, colors))}
                if all(target[u] != target[v] for u, v in edges + [daughters]):
                    cost = sum(weights[v] for v in initial if initial[v] != target[v])
                    expected[tuple(target[v] for v in daughters)].append(cost)
            for row in result["rows"]:
                costs = expected[row["pair"]]
                self.assertEqual(row["target_count"], len(costs))
                self.assertEqual(row["minimum_cost"], min(costs) if costs else None)
                if costs:
                    self.assertEqual(row["optimal_target_count"], costs.count(min(costs)))

    def test_shared_edge_forces_opposites_equal(self):
        """A diamond in the final three-color graph merges the opposite vertices."""
        initial = {"r": 0, "x": 1, "y": 1, "u": 2, "v": 3}
        edges = [("r", v) for v in ("x", "y", "u", "v")]
        edges += [("x", "u"), ("x", "v"), ("y", "v"), ("u", "v")]
        result = apex_triangle_cost_table(edges, initial, ("x", "y"), apex="r")
        self.assertEqual(result["class_of"]["u"], result["class_of"]["y"])
        self.assertEqual(result["target_count"], 6)

    def test_missing_spoke_is_outside_scope(self):
        """Three-color reasoning is invalid when a vertex can use the apex color."""
        with self.assertRaises(ValueError):
            apex_triangle_cost_table([("r", "x")], {"r": 0, "x": 1, "y": 1},
                                     ("x", "y"), apex="r")

    def test_zero_budget_reports_unknown_without_a_false_minimum(self):
        """A cutoff is not a certificate of infeasibility or optimality."""
        result = apex_triangle_cost_table([("r", "x"), ("r", "y")],
                                          {"r": 0, "x": 1, "y": 1},
                                          ("x", "y"), apex="r", max_nodes=0)
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["minimum_cost"])
        self.assertIsNone(result["target_count"])
        for row in result["rows"]:
            if row["status"] == "unknown":
                self.assertIsNone(row["optimal_target_count"])
                self.assertIsNone(row["target_count"])
                self.assertEqual(row["targets_seen"], 0)
        self.assertTrue(any(row["status"] == "unknown" for row in result["rows"]))

    def test_nonzero_apex_color_and_zero_weights(self):
        """Literal palette and cost semantics cannot assume that apex color is zero."""
        result = apex_triangle_cost_table([("r", "x"), ("r", "y")],
                                          {"r": 2, "x": 0, "y": 0}, ("x", "y"),
                                          apex="r", weights={"r": 1, "x": 0, "y": 0})
        self.assertEqual(result["palette"], (0, 1, 3))
        self.assertEqual(result["minimum_cost"], 0)
        self.assertEqual(result["target_count"], 6)

    def test_input_limits_and_daughters_are_strict(self):
        """Malformed pending constraints fail before any target enumeration."""
        for daughters in (("x", "x"), ("r", "x"), "xy", ("x", "missing")):
            with self.assertRaises(ValueError):
                apex_triangle_cost_table([("r", "x"), ("r", "y")],
                                          {"r": 0, "x": 1, "y": 1}, daughters, apex="r")
        with self.assertRaises(ValueError):
            apex_triangle_cost_table([("r", "x"), ("r", "y")],
                                      {"r": 0, "x": 1, "y": 1}, ("x", "y"),
                                      apex="r", max_nodes=True)


if __name__ == "__main__":
    unittest.main()

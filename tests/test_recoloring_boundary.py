"""Independent full-assignment checks of endpoint boundary cost tables."""

from itertools import combinations, product
import json
import unittest

from fourcolor.recoloring_boundary import recoloring_boundary_table


def complete_oracle(edges, initial, daughters, fixed, weights):
    """Group literal 4**n assignments; do not reuse DFS domains or bounds."""
    names = tuple(initial)
    targets = {pair: [] for pair in product(range(4), repeat=2)}
    for colors in product(range(4), repeat=len(names)):
        target = dict(zip(names, colors))
        if any(target[v] != initial[v] for v in fixed):
            continue
        if any(target[u] == target[v] for u, v in tuple(edges) + (tuple(daughters),)):
            continue
        changed = tuple(v for v in names if target[v] != initial[v])
        cost = sum(weights[v] for v in changed)
        targets[tuple(target[v] for v in daughters)].append((cost, changed, target))
    return targets


class RecoloringBoundaryTests(unittest.TestCase):
    """Check exact counts, support unions, local certificates and cutoffs."""

    def assert_complete_oracle(self, result, oracle):
        """Compare every row with complete independently enumerated targets."""
        names, initial = result["vertices"], result["initial"]
        children, fixed = result["daughters"], result["fixed"]
        self.assertTrue(result["all_rows_complete"])
        self.assertEqual(len(result["rows"]), 16)
        for row in result["rows"]:
            with self.subTest(colors=row["colors"]):
                targets = oracle[row["colors"]]
                self.assertTrue(row["search_exhausted"])
                self.assertEqual(row["target_count"], len(targets))
                self.assertEqual(row["status"], "exact" if targets else "infeasible")
                minimum = min((entry[0] for entry in targets), default=None)
                self.assertEqual(row["minimum_cost"], minimum)
                optimal = [entry for entry in targets if entry[0] == minimum]
                self.assertEqual(row["optimal_target_count"], len(optimal))
                supports = {entry[1] for entry in optimal}
                self.assertEqual(set(row["optimal_changed_sets"]), supports)
                self.assertEqual(set(row["optimal_old_changed_sets"]),
                                 {tuple(v for v in support if v not in children) for support in supports})
                if targets:
                    self.assertLessEqual(row["direct_lower_bound"], minimum)
                    witness = row["witness"]
                    self.assertEqual(set(witness), set(names))
                    self.assertEqual(tuple(witness[v] for v in children), row["colors"])
                    self.assertTrue(all(witness[u] != witness[v]
                                        for u, v in result["base_edges"] + (children,)))
                    self.assertTrue(all(witness[v] == initial[v] for v in fixed))
                    self.assertEqual(sum(result["weights"][v] for v in names
                                         if witness[v] != initial[v]), minimum)
                    # Every target, not just the chosen optimum, obeys the
                    # elementary direct forced-change certificate.
                    for _, support, _ in targets:
                        self.assertTrue(set(row["direct_forced_changes"]) <= set(support))
                else:
                    self.assertIsNone(row["witness"])
        expected = min((entry[0] for values in oracle.values() for entry in values), default=None)
        self.assertEqual(result["minimum_cost"], expected)

    def test_all_four_vertex_graphs_fixed_sets_and_two_weight_profiles(self):
        names = ("x", "y", "a", "b")
        checked = 0
        for a, b in product(range(4), repeat=2):
            initial = dict(zip(names, (0, 0, a, b)))
            available = tuple(edge for edge in combinations(names, 2)
                              if initial[edge[0]] != initial[edge[1]])
            for flags in product((False, True), repeat=len(available)):
                edges = tuple(edge for edge, present in zip(available, flags) if present)
                for fixed in ((), ("a",), ("x",), ("x", "y")):
                    for profile in ((0, 0, 1, 1), (2, 0, 0, 3)):
                        weights = dict(zip(names, profile))
                        result = recoloring_boundary_table(edges, initial, ("x", "y"),
                                                           fixed=fixed, weights=weights)
                        oracle = complete_oracle(edges, initial, ("x", "y"), fixed, weights)
                        self.assert_complete_oracle(result, oracle)
                        checked += 1
        self.assertGreater(checked, 2000)

    def test_direct_bound_deduplicates_forced_neighbors_and_counts_boundary_weights(self):
        initial = {"x": 0, "y": 0, "a": 1, "b": 2}
        edges = [("x", "a"), ("y", "a"), ("y", "b")]
        weights = {"x": 7, "y": 5, "a": 2, "b": 3}
        result = recoloring_boundary_table(edges, initial, ("x", "y"), weights=weights)
        row = next(row for row in result["rows"] if row["colors"] == (1, 2))
        self.assertEqual(row["direct_forced_changes"], ("a", "b"))
        self.assertEqual(row["direct_lower_bound"], 17)
        self.assertEqual(row["minimum_cost"], 17)
        # The diagonal is impossible, but its local union should still not
        # charge twice for a common neighbor forced by both daughters.
        diagonal = next(row for row in result["rows"] if row["colors"] == (1, 1))
        self.assertEqual(len(diagonal["direct_forcing_reasons"]), 2)
        self.assertEqual(diagonal["direct_forced_changes"], ("a",))
        self.assertEqual(diagonal["direct_lower_bound"], 14)

    def test_defaults_charge_only_nondaughters(self):
        initial = {"x": 0, "y": 0, "a": 1}
        result = recoloring_boundary_table([("x", "a")], initial, ("x", "y"))
        self.assertEqual(result["weights"], {"x": 0, "y": 0, "a": 1})
        self.assert_complete_oracle(result, complete_oracle(
            [("x", "a")], initial, ("x", "y"), (), result["weights"]))

    def test_fixed_conflicts_are_proved_even_with_zero_node_budget(self):
        initial = {"x": 0, "y": 0, "a": 1}
        result = recoloring_boundary_table([("x", "a")], initial, ("x", "y"),
                                           fixed=("x", "a"), max_nodes_per_pair=0)
        rows = {row["colors"]: row for row in result["rows"]}
        self.assertEqual(rows[1, 2]["status"], "infeasible")
        self.assertEqual({entry["kind"] for entry in rows[1, 2]["direct_contradictions"]},
                         {"fixed_daughter", "fixed_neighbor"})
        self.assertEqual(rows[0, 2]["status"], "unknown")
        self.assertEqual(rows[0, 0]["status"], "infeasible")
        self.assertTrue(all(row["nodes"] == 0 for row in rows.values()))
        self.assertIsNone(result["minimum_cost"])

    def test_truncated_incumbent_is_not_an_optimum_or_a_complete_count(self):
        initial = {"x": 0, "y": 0, "a": 0}
        partial = recoloring_boundary_table([], initial, ("x", "y"), max_nodes_per_pair=2)
        row = next(row for row in partial["rows"] if row["colors"] == (0, 1))
        self.assertEqual(row["status"], "unknown")
        self.assertEqual((row["best_found_cost"], row["targets_seen"]), (0, 1))
        self.assertIsNotNone(row["witness"])
        for key in ("minimum_cost", "target_count", "optimal_target_count",
                    "optimal_changed_sets", "optimal_old_changed_sets"):
            self.assertIsNone(row[key])
        # Four leaves plus the preset root exactly exhaust this tree.
        complete = recoloring_boundary_table([], initial, ("x", "y"), max_nodes_per_pair=5)
        self.assertTrue(complete["all_rows_complete"])
        self.assertEqual(next(row for row in complete["rows"] if row["colors"] == (0, 1))["nodes"], 5)

    def test_nonlocal_impossibility_is_not_confused_with_direct_conflict(self):
        # Completing K5 minus the daughter edge is impossible. Some color
        # pairs have no fixed conflict, so DFS must establish emptiness.
        initial = {"x": 0, "y": 0, "a": 1, "b": 2, "c": 3}
        edges = [edge for edge in combinations(initial, 2) if set(edge) != {"x", "y"}]
        result = recoloring_boundary_table(edges, initial, ("x", "y"))
        self.assertTrue(result["all_rows_complete"])
        self.assertTrue(all(row["status"] == "infeasible" for row in result["rows"]))
        row = next(row for row in result["rows"] if row["colors"] == (0, 1))
        self.assertFalse(row["direct_contradictions"])
        self.assertGreater(row["nodes"], 0)

    def test_all_optimal_supports_are_retained(self):
        # With zero weights, every extension is optimal. Keeping only the
        # first witness would lose several distinct permissible supports.
        initial = {"x": 0, "y": 0, "a": 1, "b": 2}
        weights = dict.fromkeys(initial, 0)
        result = recoloring_boundary_table([], initial, ("x", "y"), weights=weights)
        row = next(row for row in result["rows"] if row["colors"] == (0, 1))
        self.assertEqual(row["optimal_target_count"], 16)
        self.assertEqual(set(row["optimal_old_changed_sets"]), {(), ("a",), ("b",), ("a", "b")})

    def test_inputs_are_copied_duplicates_normalized_and_json_serializable(self):
        initial = {"x": 0, "y": 0, "a": 1}
        edges = [["a", "x"], ["x", "a"]]
        result = recoloring_boundary_table(edges, initial, ("x", "y"), fixed=("a", "a"))
        initial["x"] = 3
        edges[0][0] = "unknown"
        self.assertEqual(result["initial"]["x"], 0)
        self.assertEqual(result["base_edges"], (("x", "a"),))
        self.assertEqual(result["fixed"], ("a",))
        self.assertEqual(len(json.loads(json.dumps(result))["rows"]), 16)

    def test_invalid_inputs_and_size_guard(self):
        valid = {"x": 0, "y": 0}
        bad = [
            ([], {}, ("x", "y"), {}),
            ([], {"x": True, "y": 0}, ("x", "y"), {}),
            ([], {"x": 4, "y": 0}, ("x", "y"), {}),
            ([], {"x": 0, "y": 1}, ("x", "y"), {}),
            ([("x", "y")], valid, ("x", "y"), {}),
            ([("x", "unknown")], valid, ("x", "y"), {}),
            (None, valid, ("x", "y"), {}),
            ([], valid, "xy", {}),
            ([], valid, None, {}),
            ([], valid, ("x", "x"), {}),
            ([], valid, ("x", []), {}),
            ([], valid, ("x", "unknown"), {}),
            ([], valid, ("x", "y"), {"weights": {"x": 0}}),
            ([], valid, ("x", "y"), {"weights": {"x": True, "y": 0}}),
            ([], valid, ("x", "y"), {"fixed": "x"}),
            ([], valid, ("x", "y"), {"fixed": ("unknown",)}),
            ([], {str(i): 0 for i in range(13)}, ("0", "1"), {}),
        ]
        for key in ("max_nodes_per_pair", "max_vertices"):
            values = (-1, True, None, 1.5, "12") + ((0, 1) if key == "max_vertices" else ())
            bad.extend(([], valid, ("x", "y"), {key: value}) for value in values)
        for edges, initial, daughters, kwargs in bad:
            with self.subTest(edges=edges, initial=initial, daughters=daughters, kwargs=kwargs):
                with self.assertRaises(ValueError):
                    recoloring_boundary_table(edges, initial, daughters, **kwargs)


if __name__ == "__main__":
    unittest.main()

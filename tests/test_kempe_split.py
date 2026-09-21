"""Bounded independent oracles for single-component daughter repairs.

Subset enumeration here checks component connectivity by all graph cuts,
not by reusing production traversal. It is test-only and never a fallback.
"""

from itertools import combinations, product
import json
import unittest

from fourcolor.kempe_split import single_kempe_split


def subsets(values):
    """Enumerate every finite subset in a declared tiny test fixture."""
    return [set(vertex for vertex, flag in zip(values, flags) if flag)
            for flags in product((False, True), repeat=len(values))]


def subset_oracle(edges, initial, daughters, fixed):
    """Find full components by induced-color closure and all internal cuts."""
    results = []
    vertices = tuple(initial)
    for pair in combinations(range(4), 2):
        allowed = tuple(vertex for vertex in vertices if initial[vertex] in pair)
        for chosen in subsets(allowed):
            if len(chosen.intersection(daughters)) != 1 or chosen.intersection(fixed):
                continue
            # Completeness: no induced two-color edge may exit the subset.
            if any((left in chosen) != (right in chosen)
                   for left, right in edges if left in allowed and right in allowed):
                continue
            # Connectivity: each nontrivial cut of the subset has an edge.
            if any(not any((left in cut) != (right in cut)
                           for left, right in edges if left in chosen and right in chosen)
                   for cut in subsets(tuple(chosen)) if cut and cut != chosen):
                continue
            target = {vertex: pair[0] ^ pair[1] ^ color if vertex in chosen else color
                      for vertex, color in initial.items()}
            if target[daughters[0]] == target[daughters[1]]:
                continue
            results.append((pair, tuple(vertex for vertex in vertices if vertex in chosen), target))
    return results


class KempeSplitTests(unittest.TestCase):
    """Check certificates, cost semantics, stopping rules, and input bounds."""

    def test_full_component_has_bidirectional_dependencies_and_one_atomic_batch(self):
        initial = {"x": 0, "a": 1, "b": 0, "c": 1, "y": 0, "wall": 2}
        edges = [("x", "a"), ("a", "b"), ("b", "c"), ("c", "wall")]
        result = single_kempe_split(edges, initial, ("x", "y"))
        candidate = next(row for row in result["candidates"]
                         if row["seed"] == "x" and row["pair"] == (0, 1))
        self.assertEqual(candidate["component"], ("x", "a", "b", "c"))
        self.assertEqual(candidate["dependencies"],
                         (("x", "a"), ("a", "x"), ("a", "b"),
                          ("b", "a"), ("b", "c"), ("c", "b")))
        self.assertEqual(candidate["components"], (("x", "a", "b", "c"),))
        self.assertEqual(candidate["batches"], candidate["components"])
        self.assertEqual(candidate["minimum_max_batch_size"], 4)
        self.assertEqual(candidate["minimum_max_batch_weight"], 4)
        self.assertEqual(candidate["target"], {"x": 1, "a": 0, "b": 1, "c": 0,
                                               "y": 0, "wall": 2})
        # Partially applying this swap breaks a pre-existing edge.
        partial = {**initial, "x": 1}
        self.assertEqual(partial["x"], partial["a"])

    def test_fixed_hits_and_both_daughters_are_reported_without_fallback(self):
        initial = {"x": 0, "a": 1, "y": 0}
        result = single_kempe_split([("x", "a"), ("a", "y")], initial,
                                    ("x", "y"), fixed=("x", "y"))
        self.assertEqual(result["status"], "stalled")
        self.assertEqual(result["candidates"], [])
        self.assertIsNone(result["selected"])
        self.assertEqual(len(result["attempts"]), 6)
        first = result["attempts"][0]
        self.assertEqual(first["blocked_reasons"],
                         ("contains_other_daughter", "contains_fixed_side"))
        self.assertEqual(first["fixed_hits"], ("x", "y"))

    def test_both_seed_daughters_are_scanned(self):
        result = single_kempe_split([], {"fixed_x": 0, "y": 0},
                                    ("fixed_x", "y"), fixed=("fixed_x",))
        self.assertEqual(result["status"], "repaired")
        self.assertEqual(len(result["candidates"]), 3)
        self.assertTrue(all(row["seed"] == "y" for row in result["candidates"]))
        self.assertEqual(result["selected"]["target"], {"fixed_x": 0, "y": 1})

    def test_weight_precedes_count_and_zero_weights_are_valid(self):
        initial = {"x": 0, "a": 1, "y": 0}
        result = single_kempe_split([("x", "a")], initial, ("x", "y"),
                                    weights={"x": 0, "a": 0, "y": 9})
        self.assertEqual(result["selected"]["component"], ("x",))
        self.assertEqual(result["selected"]["pair"], (0, 2))
        pair_swap = next(row for row in result["candidates"]
                         if row["component"] == ("x", "a"))
        self.assertEqual(pair_swap["changed_weight"], 0)
        self.assertEqual(pair_swap["minimum_max_batch_weight"], 0)

    def test_record_cost_is_a_union_not_xor_edges_or_per_side_sum(self):
        initial = {"x": 0, "a": 1, "y": 0}
        result = single_kempe_split([("x", "a")], initial, ("x", "y"),
                                    records_by_side={"x": ["shared", "left", "shared"],
                                                     "a": ["shared", "right"], "y": []})
        candidate = next(row for row in result["candidates"]
                         if row["component"] == ("x", "a"))
        self.assertEqual(candidate["changed_record_ids"], ("shared", "left", "right"))
        self.assertEqual(candidate["changed_record_count"], 3)
        self.assertEqual(initial["x"] ^ initial["a"],
                         candidate["target"]["x"] ^ candidate["target"]["a"])
        self.assertEqual(result["selected"]["component"], ("y",))
        self.assertEqual(result["selected"]["changed_record_count"], 0)

    def test_missing_records_are_unmeasured_and_output_is_json_serializable(self):
        result = single_kempe_split([], {"z": 0, "a": 0}, ("a", "z"))
        self.assertIsNone(result["records_by_side"])
        self.assertIsNone(result["selected"]["changed_record_count"])
        self.assertIsNone(result["selected"]["changed_record_ids"])
        self.assertEqual(result["selected"]["component"], ("z",))
        self.assertEqual(result["selected"]["pair"], (0, 1))
        self.assertEqual(json.loads(json.dumps(result))["status"], "repaired")

    def test_inputs_are_copied_and_duplicate_edges_records_fixed_are_normalized(self):
        edges = [["a", "z"], ["z", "a"]]
        initial = {"z": 0, "a": 1, "y": 0}
        records = {"z": ["r", "r"], "a": [], "y": []}
        weights = {"z": 1, "a": 2, "y": 3}
        result = single_kempe_split(edges, initial, ("z", "y"), fixed=["a", "a"],
                                    weights=weights, records_by_side=records)
        edges[0][0] = "missing"
        initial["z"] = 3
        records["z"].append("later")
        weights["z"] = 100
        self.assertEqual(result["initial"]["z"], 0)
        self.assertEqual(result["base_edges"], (("z", "a"),))
        self.assertEqual(result["fixed"], ("a",))
        self.assertEqual(result["records_by_side"]["z"], ("r",))
        self.assertEqual(result["weights"]["z"], 1)

    def test_invalid_inputs_are_rejected(self):
        valid = {"x": 0, "y": 0}
        invalid = [
            ([], {}, ("x", "y"), {}),
            ([], {"x": True, "y": 0}, ("x", "y"), {}),
            ([], {"x": 4, "y": 0}, ("x", "y"), {}),
            ([], {"": 0, "y": 0}, ("", "y"), {}),
            ([], {"x": 0, "y": 1}, ("x", "y"), {}),
            ([("x", "y")], valid, ("x", "y"), {}),
            ([("x", "x")], valid, ("x", "y"), {}),
            ([("x", "missing")], valid, ("x", "y"), {}),
            (["xy"], valid, ("x", "y"), {}),
            (None, valid, ("x", "y"), {}),
            ([], valid, "xy", {}),
            ([], valid, None, {}),
            ([], valid, ("x",), {}),
            ([], valid, ("x", "x"), {}),
            ([], valid, ("x", "missing"), {}),
            ([], valid, ("x", []), {}),
            ([], valid, ("x", "y"), {"fixed": "x"}),
            ([], valid, ("x", "y"), {"fixed": ["missing"]}),
            ([], valid, ("x", "y"), {"weights": {"x": 1}}),
            ([], valid, ("x", "y"), {"weights": {"x": -1, "y": 0}}),
            ([], valid, ("x", "y"), {"weights": {"x": True, "y": 0}}),
            ([], valid, ("x", "y"), {"weights": {"x": 1.5, "y": 0}}),
            ([], valid, ("x", "y"), {"records_by_side": {"x": []}}),
            ([], valid, ("x", "y"), {"records_by_side": {"x": "one", "y": []}}),
            ([], valid, ("x", "y"), {"records_by_side": {"x": None, "y": []}}),
            ([], valid, ("x", "y"), {"records_by_side": {"x": [1], "y": []}}),
            ([], valid, ("x", "y"), {"records_by_side": {"x": [" "], "y": []}}),
        ]
        for edges, initial, daughters, kwargs in invalid:
            with self.subTest(edges=edges, initial=initial, daughters=daughters, kwargs=kwargs):
                with self.assertRaises(ValueError):
                    single_kempe_split(edges, initial, daughters, **kwargs)

    def test_published_hard_case_stalls_despite_a_known_legal_target(self):
        # Exact adjacency and inherited/target colors from HARD_CASE-2026-09-18.md
        # sections 2--4. Its documented repair uses three swaps; this API must
        # expose the one-swap failure instead of quietly returning that target.
        full_edges = [(0, 1), (0, 2), (0, 3), (0, 4), (0, 5), (0, 6), (0, 7), (0, 8),
                      (1, 2), (1, 8), (1, 9), (2, 3), (2, 9), (3, 4), (3, 7), (3, 9),
                      (4, 5), (4, 7), (5, 6), (5, 7), (6, 7), (7, 8), (7, 9), (8, 9)]
        base = [(str(left), str(right)) for left, right in full_edges if (left, right) != (3, 7)]
        initial = dict(zip(map(str, range(10)), (0, 1, 2, 1, 3, 2, 3, 1, 2, 3)))
        target = (0, 1, 3, 2, 3, 2, 3, 1, 2, 0)
        self.assertTrue(all(target[left] != target[right] for left, right in full_edges))
        result = single_kempe_split(base, initial, ("3", "7"), fixed=("0",))
        self.assertEqual(result["status"], "stalled")
        self.assertEqual(len(result["attempts"]), 6)
        self.assertTrue(all(row["blocked_reasons"] for row in result["attempts"]))

    def test_long_component_needs_no_recursive_traversal(self):
        vertices = tuple(f"s{index}" for index in range(2500))
        initial = {vertex: index % 2 for index, vertex in enumerate(vertices)}
        initial["daughter"] = 0
        result = single_kempe_split(zip(vertices, vertices[1:]), initial,
                                    (vertices[0], "daughter"))
        candidate = next(row for row in result["candidates"]
                         if row["seed"] == vertices[0] and row["pair"] == (0, 1))
        self.assertEqual(candidate["component"], vertices)
        self.assertEqual(candidate["minimum_max_batch_size"], len(vertices))

    def test_small_graphs_match_independent_subset_connectivity_and_cost_oracle(self):
        vertices = ("x", "y", "z", "w")
        weights = {"x": 2, "y": 1, "z": 0, "w": 3}
        records = {"x": ("r0", "shared"), "y": ("r1",),
                   "z": ("shared", "r2"), "w": ("r3",)}
        checked = 0
        for z_color, w_color in product(range(4), repeat=2):
            initial = dict(zip(vertices, (0, 0, z_color, w_color)))
            possible = tuple(edge for edge in combinations(vertices, 2)
                             if initial[edge[0]] != initial[edge[1]])
            for flags in product((False, True), repeat=len(possible)):
                edges = tuple(edge for edge, flag in zip(possible, flags) if flag)
                for fixed in ((), ("x",), ("z",), ("x", "y")):
                    result = single_kempe_split(edges, initial, ("x", "y"), fixed=fixed,
                                                weights=weights, records_by_side=records)
                    expected = subset_oracle(edges, initial, ("x", "y"), fixed)
                    actual_keys = {(row["pair"], row["component"]) for row in result["candidates"]}
                    self.assertEqual(actual_keys, {(pair, component) for pair, component, _ in expected})
                    self.assertEqual(len(result["candidates"]), len(expected))
                    oracle_costs = []
                    for pair, component, target in expected:
                        candidate = next(row for row in result["candidates"]
                                         if (row["pair"], row["component"]) == (pair, component))
                        record_union = set(record for vertex in component for record in records[vertex])
                        weight = sum(weights[vertex] for vertex in component)
                        self.assertEqual(candidate["target"], target)
                        self.assertTrue(all(target[left] != target[right] for left, right in edges))
                        self.assertNotEqual(target["x"], target["y"])
                        self.assertTrue(all(target[vertex] == initial[vertex] for vertex in fixed))
                        self.assertEqual(set(candidate["changed_record_ids"]), record_union)
                        self.assertEqual(candidate["minimum_max_batch_size"], len(component))
                        self.assertEqual(candidate["minimum_max_batch_weight"], weight)
                        oracle_costs.append((weight, len(component), len(record_union),
                                             tuple(vertices.index(vertex) for vertex in component), pair))
                    self.assertEqual(result["status"], "repaired" if expected else "stalled")
                    if expected:
                        selected = result["selected"]
                        actual_cost = (selected["changed_weight"], selected["changed_side_count"],
                                       selected["changed_record_count"],
                                       tuple(vertices.index(vertex) for vertex in selected["component"]),
                                       selected["pair"])
                        self.assertEqual(actual_cost, min(oracle_costs))
                    checked += 1
        # Color cases: both zero, one zero, equal nonzero, distinct nonzero.
        # Each compatible graph is checked with all four declared fixed sets.
        self.assertEqual(checked, 4 * (1 + 6 * 8 + 3 * 16 + 6 * 32))


if __name__ == "__main__":
    unittest.main()

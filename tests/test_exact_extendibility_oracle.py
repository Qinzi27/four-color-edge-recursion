"""Compare the offline oracle with literal brute force and corrupt its evidence."""

from copy import deepcopy
from itertools import combinations, product
import json
import unittest

from scripts.exact_extendibility_oracle import solve_exact, verify_exact_result


def literal_witness(n, edges, anchors):
    """Independent tiny-instance baseline: enumerate every literal assignment."""
    for colors in product((1, 2, 3, 4), repeat=n):
        if all(colors[v] == c for v, c in anchors.items()) and all(colors[a] != colors[b] for a, b in edges):
            return list(colors)
    return None


def all_simple_graphs(n):
    """Generate all labelled simple graphs, with no isomorphism deduplication."""
    pairs = list(combinations(range(n), 2))
    for flags in product((False, True), repeat=len(pairs)):
        yield [pair for pair, keep in zip(pairs, flags) if keep]


class ExactExtendibilityOracleTests(unittest.TestCase):
    """No production solver or coloring propagation is used in this baseline."""

    def check(self, n, edges, anchors, *, node_limit=1_000_000):
        """Check both the mathematical answer and its separately replayed proof."""
        result = solve_exact(n, edges, anchors, node_limit=node_limit)
        audit = verify_exact_result(n, edges, anchors, result)
        self.assertTrue(audit["passed"])
        return result, audit

    def test_all_graphs_through_three_vertices_all_literal_partial_anchors(self):
        """Exhaust all 0..3-vertex graphs and all 5^n partial anchor maps."""
        for n in range(4):
            for edges in all_simple_graphs(n):
                for states in product((0, 1, 2, 3, 4), repeat=n):
                    anchors = {v: c for v, c in enumerate(states) if c}
                    expected = literal_witness(n, edges, anchors)
                    result, audit = self.check(n, edges, anchors)
                    self.assertEqual(result["status"], "sat" if expected is not None else "unsat")
                    self.assertTrue(audit["conclusive"])

    def test_all_four_vertex_graphs_with_declared_anchor_patterns(self):
        """Exhaust 64 graphs with three fixed anchor patterns, not all patterns."""
        for edges in all_simple_graphs(4):
            for anchors in ({}, {0: 1, 1: 1}, {0: 1, 1: 2, 2: 3, 3: 4}):
                expected = literal_witness(4, edges, anchors)
                result, _ = self.check(4, edges, anchors)
                self.assertEqual(result["status"], "sat" if expected is not None else "unsat")

    def test_k5_has_complete_literal_unsat_tree_without_symmetry_reduction(self):
        """K5 explores all 4, then 3, then 2, then 1 available literal colors."""
        edges = list(combinations(range(5), 2))
        result, audit = self.check(5, edges, {})
        self.assertEqual(result["status"], "unsat")
        self.assertEqual(result["nodes"], 1 + 4 + 12 + 24 + 24)
        self.assertEqual(audit["leaves_checked"], 24)
        self.assertEqual([x["color"] for x in result["certificate"]["children"]], [1, 2, 3, 4])
        self.assertIsNone(literal_witness(5, edges, {}))

    def test_anchor_conflict_is_a_direct_original_edge_leaf(self):
        result, audit = self.check(2, [(0, 1)], {0: 3, 1: 3})
        self.assertEqual(result["certificate"], {"kind": "conflict", "edge": [0, 1]})
        self.assertEqual(audit["nodes_independently_counted"], 1)

    def test_node_limit_unknown_is_not_unsat(self):
        edges = list(combinations(range(5), 2))
        for cap in (0, 1, 10, 64):
            result, audit = self.check(5, edges, {}, node_limit=cap)
            self.assertEqual(result["status"], "unknown")
            self.assertEqual(result["nodes"], cap)
            self.assertIsNone(result["certificate"])
            self.assertFalse(audit["conclusive"])
            self.assertEqual(audit["claim"], "unresolved")
            altered = deepcopy(result)
            altered["status"] = "unsat"
            with self.assertRaises(ValueError):
                verify_exact_result(5, edges, {}, altered)
        self.assertEqual(self.check(5, edges, {}, node_limit=65)[0]["status"], "unsat")

    def test_json_roundtrip_and_input_order_are_deterministic(self):
        edges = list(combinations(range(5), 2))
        first = solve_exact(5, edges, {0: 3})
        second = solve_exact(5, [tuple(reversed(e)) for e in reversed(edges)], {0: 3})
        self.assertEqual(first, second)
        self.assertTrue(verify_exact_result(5, edges, {0: 3}, json.loads(json.dumps(first)))["passed"])

    def test_missing_repeated_or_wrong_child_is_rejected(self):
        edges = list(combinations(range(5), 2))
        for change in ("drop", "repeat", "wrong-color"):
            result = solve_exact(5, edges, {})
            children = result["certificate"]["children"]
            if change == "drop":
                children.pop()
            elif change == "repeat":
                children[1] = deepcopy(children[0])
            else:
                children[0]["color"] = 4
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_exact_result(5, edges, {}, result)

    def test_forged_blocker_node_count_or_input_binding_is_rejected(self):
        edges = list(combinations(range(5), 2))
        for change in ("blocker", "nodes", "input"):
            result = solve_exact(5, edges, {})
            if change == "blocker":
                node = result["certificate"]
                while node["kind"] == "branch":
                    node = node["children"][0]["child"]
                node["blockers"][0]["neighbor"] = node["vertex"]
            elif change == "nodes":
                result["nodes"] += 1
            else:
                result["input_sha256"] = "0" * 64
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_exact_result(5, edges, {}, result)

    def test_sat_witness_must_match_both_edges_and_anchors(self):
        for colors in ([1, 1], [2, 1], [True, 2], [1]):
            result = solve_exact(2, [(0, 1)], {0: 1})
            result["witness"] = colors
            with self.subTest(colors=colors), self.assertRaises(ValueError):
                verify_exact_result(2, [(0, 1)], {0: 1}, result)

    def test_invalid_inputs_are_rejected(self):
        invalid = [(-1, [], {}), (True, [], {}), (2, [(0, 0)], {}),
                   (2, [(0, 1), (1, 0)], {}), (2, [(0, 2)], {}),
                   (2, [(False, 1)], {}), (2, [], {2: 1}), (2, [], {0: True}),
                   (2, [], {0: 5}), (2, [], {"0": 1}), (2, [], [])]
        for n, edges, anchors in invalid:
            with self.subTest(n=n, edges=edges, anchors=anchors), self.assertRaises(ValueError):
                solve_exact(n, edges, anchors)
        for cap in (-1, True, 1.5):
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                solve_exact(1, [], {}, node_limit=cap)

    def test_long_sat_path_does_not_depend_on_python_recursion_depth(self):
        """A deep complete witness uses the explicit stack, not recursive DFS."""
        n = 1050
        result, audit = self.check(n, [], {}, node_limit=n + 1)
        self.assertEqual(result["status"], "sat")
        self.assertEqual(result["witness"], [1] * n)
        self.assertTrue(audit["conclusive"])


if __name__ == "__main__":
    unittest.main()

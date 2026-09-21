"""Independently check conditional triangle refutations and their boundaries."""

from copy import deepcopy
import gzip
from itertools import combinations, product
import json
from pathlib import Path
import random
import unittest

from fourcolor.structural_name_relations import RULE, refute_same_name


def audit_certificate(test, vertex_count, edges, result):
    """Replay explicit edge/class witnesses without running the producer again.

    The verifier checks a claimed proof, not whether a particular greedy
    sequence of structural merges should have been chosen.  It uses original
    edges throughout, so an invented quotient edge cannot support a proof.
    """
    original = {frozenset(edge) for edge in edges}
    first, second = result["assumed_equal"]
    classes = {frozenset([vertex]) for vertex in range(vertex_count)}
    classes -= {frozenset([first]), frozenset([second])}
    classes.add(frozenset([first, second]))

    def check_edge(record):
        """Verify one original edge spans its two declared current classes."""
        left, right = map(frozenset, record["classes"])
        test.assertIn(left, classes)
        test.assertIn(right, classes)
        test.assertNotEqual(left, right)
        edge = frozenset(record["original_edge"])
        test.assertIn(edge, original)
        test.assertEqual(len(edge & left), 1)
        test.assertEqual(len(edge & right), 1)
        return frozenset([left, right])

    for step in result["merges"]:
        left, right = map(frozenset, (step["first_class"], step["second_class"]))
        triangle = list(map(frozenset, step["triangle"]))
        test.assertEqual(len(set(triangle + [left, right])), 5)
        test.assertTrue(set(triangle + [left, right]) <= classes)
        test.assertEqual({check_edge(record) for record in step["triangle_edges"]},
                         {frozenset(pair) for pair in combinations(triangle, 2)})
        test.assertEqual({check_edge(record) for record in step["spokes"]},
                         {frozenset([neighbor, vertex]) for neighbor in (left, right)
                          for vertex in triangle})
        test.assertEqual(frozenset(step["result_class"]), left | right)
        classes -= {left, right}
        classes.add(left | right)

    contradiction = result["contradiction"]
    if contradiction is None:
        test.assertEqual(result["status"], "inconclusive")
    elif contradiction["kind"] == "self_loop":
        test.assertEqual(result["status"], "proved_different")
        members = frozenset(contradiction["class"])
        edge = frozenset(contradiction["original_edge"])
        test.assertIn(members, classes)
        test.assertIn(edge, original)
        test.assertTrue(edge <= members)
    else:
        test.assertEqual(contradiction["kind"], "five_clique")
        test.assertEqual(result["status"], "proved_different")
        clique = list(map(frozenset, contradiction["classes"]))
        test.assertEqual(len(set(clique)), 5)
        test.assertEqual({check_edge(record) for record in contradiction["edges"]},
                         {frozenset(pair) for pair in combinations(clique, 2)})
    test.assertEqual(set(map(frozenset, result["final_classes"])), classes)
    test.assertEqual(result["statistics"]["final_class_count"], len(classes))
    test.assertEqual(result["statistics"]["forced_merges"], len(result["merges"]))
    test.assertLessEqual(len(result["merges"]), vertex_count - 2)


class StructuralNameRelationsTests(unittest.TestCase):
    """A proof needs authentic premises; no proof is not an extension witness."""

    def test_adjacent_assumption_has_direct_self_loop_refutation(self):
        """An actual inequality already refutes the assumed equality."""
        result = refute_same_name(3, [[1, 0]], 1, 0)
        self.assertEqual(result["assumed_equal"], [0, 1])
        self.assertEqual(result["merges"], [])
        self.assertEqual(result["contradiction"],
                         {"kind": "self_loop", "class": [0, 1], "original_edge": [0, 1]})
        audit_certificate(self, 3, [[1, 0]], result)

    def test_empty_or_disconnected_graph_returns_inconclusive(self):
        """Isolated identities are supported and do not create constraints."""
        for n, edges, first, second in ((2, [], 0, 1), (6, [[2, 3], [3, 4]], 0, 5)):
            with self.subTest(n=n, edges=edges):
                result = refute_same_name(n, edges, first, second)
                self.assertEqual(result["status"], "inconclusive")
                self.assertEqual(result["merges"], [])
                self.assertIsNone(result["contradiction"])
                audit_certificate(self, n, edges, result)

    def test_forced_merge_alone_does_not_claim_a_refutation(self):
        """Two vertices sharing a triangle can consistently have one name."""
        edges = list(combinations(range(3), 2)) + [(a, b) for a in range(3) for b in (3, 4)]
        result = refute_same_name(6, edges, 4, 5)
        self.assertEqual(result["status"], "inconclusive")
        self.assertEqual(len(result["merges"]), 1)
        self.assertEqual(result["merges"][0]["result_class"], [3, 4, 5])
        self.assertEqual(result["rule"], RULE)
        self.assertEqual(result["palette_size"], 4)
        audit_certificate(self, 6, edges, result)

    def test_real_v2_failure_has_geometry_only_refutation(self):
        """Recover the unique frozen v2 failure directly from its real shores."""
        root = Path(__file__).resolve().parents[1]
        with gzip.open(root / "outputs/level-sides-peer-full-2026-09-19.json.gz",
                       "rt", encoding="utf-8") as handle:
            geometry = json.load(handle)["least_conflict"]["geometry"]
        n = len(geometry["faces"])
        self.assertEqual(n, 19)
        shores = geometry["faceOfDart"]
        edges = sorted({tuple(sorted(shores[2 * index:2 * index + 2]))
                        for index in range(len(geometry["edges"]))
                        if shores[2 * index] != shores[2 * index + 1]})
        self.assertNotIn((1, 10), edges)
        result = refute_same_name(n, edges, 1, 10)
        self.assertEqual(result["status"], "proved_different")
        self.assertEqual(result["contradiction"]["kind"], "five_clique")
        self.assertGreater(len(result["merges"]), 0)
        audit_certificate(self, n, edges, result)
        # This independently checked witness ensures that the implication is
        # not merely vacuous because the original graph is uncolorable.
        witness = [1, 2, 3, 4, 2, 3, 4, 3, 4, 2, 3, 2, 4, 3, 1, 2, 1, 1, 2]
        self.assertTrue(all(witness[a] != witness[b] for a, b in edges))
        self.assertNotEqual(witness[1], witness[10])

    def test_edge_and_assumption_orientation_do_not_change_certificate(self):
        """Sorting input constraints gives deterministic, nonmutating evidence."""
        edges = [list(edge) for edge in combinations(range(5), 2)]
        before = deepcopy(edges)
        result = refute_same_name(6, edges, 4, 5)
        permuted = [edge[::-1] for edge in edges[::-1]]
        self.assertEqual(result, refute_same_name(6, permuted, 5, 4))
        self.assertEqual(edges, before)
        audit_certificate(self, 6, edges, result)

    def test_every_small_graph_refutation_preserves_all_four_colorings(self):
        """Exhaust all simple graphs with 2..5 vertices and all literal colors.

        The oracle tests original inequality edges directly.  It imports no
        quotient builder, triangle matcher, graph solver, or color propagator.
        For every emitted conclusion it checks that no proper assignment makes
        the two named identities equal.  Completeness is deliberately untested.
        """
        graph_count = refutation_count = 0
        for n in range(2, 6):
            pairs = list(combinations(range(n), 2))
            for mask in range(1 << len(pairs)):
                edges = [edge for index, edge in enumerate(pairs) if mask & (1 << index)]
                possible_equal = set()
                for colors in product(range(4), repeat=n):
                    if all(colors[a] != colors[b] for a, b in edges):
                        possible_equal.update(pair for pair in pairs
                                              if colors[pair[0]] == colors[pair[1]])
                for first, second in pairs:
                    result = refute_same_name(n, edges, first, second)
                    if result["status"] == "proved_different":
                        refutation_count += 1
                        self.assertNotIn((first, second), possible_equal,
                                         msg=(n, edges, first, second))
                graph_count += 1
        self.assertEqual(graph_count, 1098)
        self.assertGreater(refutation_count, 5000)

    def test_random_six_vertex_certificates_and_soundness(self):
        """Larger seeded cases exercise class merging beyond the tiny corpus."""
        rng = random.Random(20260921)
        pairs = list(combinations(range(6), 2))
        for _ in range(24):
            edges = [pair for pair in pairs if rng.random() < 0.6]
            proper = [colors for colors in product(range(4), repeat=6)
                      if all(colors[a] != colors[b] for a, b in edges)]
            for first, second in pairs:
                result = refute_same_name(6, edges, first, second)
                audit_certificate(self, 6, edges, result)
                if result["status"] == "proved_different":
                    self.assertTrue(all(colors[first] != colors[second] for colors in proper))

    def test_invalid_vertex_counts_and_assumptions_are_rejected(self):
        """Boolean IDs, missing identities, and reflexive assumptions are errors."""
        for n, first, second in ((True, 0, 1), (1, 0, 1), (2.0, 0, 1),
                                 (3, True, 2), (3, 0, False), (3, -1, 2),
                                 (3, 0, 3), (3, 1, 1), (3, "0", 1)):
            with self.subTest(n=n, first=first, second=second), self.assertRaises(ValueError):
                refute_same_name(n, [], first, second)

    def test_invalid_edges_are_rejected(self):
        """Malformed, repeated, loop, and out-of-range premises cannot enter a proof."""
        for edges in (None, set(), [0], [[0]], [[0, 1, 2]], [[0, True]],
                      [[0, 2.0]], [[0, -1]], [[0, 3]], [[1, 1]],
                      [[0, 1], [1, 0]], [[0, 1], [0, 1]]):
            with self.subTest(edges=edges), self.assertRaises(ValueError):
                refute_same_name(3, edges, 0, 2)


if __name__ == "__main__":
    unittest.main()

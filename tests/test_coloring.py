"""Check coloring enumeration, boundary relations, and color renaming."""

from itertools import product
import random
import unittest

from fourcolor.coloring import boundary_signature, canonical_colors, colorings
from tests.oracles import brute_colorings


class ColoringTests(unittest.TestCase):
    def test_small_graphs_against_independent_enumeration(self):
        fixtures = [
            (0, ()),
            (1, ()),
            (2, ((0, 1),)),
            (3, ((0, 1), (1, 2), (2, 0))),
            (4, tuple((u, v) for u in range(4) for v in range(u + 1, 4))),
            (2, ((0, 1), (0, 1))),
            (1, ((0, 0),)),
        ]
        for n, edges in fixtures:
            with self.subTest(n=n, edges=edges):
                result = list(colorings(n, edges))
                expected = brute_colorings(n, edges)
                self.assertEqual(set(result), expected)
                self.assertEqual(len(result), len(expected), "No duplicate assignments")

    def test_precolored_vertices_and_conflicts(self):
        edges = ((0, 1), (1, 2), (2, 0))
        for fixed in ({0: 0}, {0: 0, 1: 0}, {0: 3, 2: 1}):
            with self.subTest(precolored=fixed):
                self.assertEqual(
                    set(colorings(3, edges, precolored=fixed)),
                    brute_colorings(3, edges, fixed),
                )

    def test_random_small_graphs(self):
        rng = random.Random(20260906)
        for case in range(20):
            n = rng.randint(1, 5)
            edges = tuple(
                (u, v)
                for u in range(n)
                for v in range(u + 1, n)
                if rng.random() < 0.5
            )
            with self.subTest(case=case):
                self.assertEqual(set(colorings(n, edges)), brute_colorings(n, edges))

    def test_boundary_order_and_empty_boundary(self):
        edges = ((0, 1), (1, 2), (2, 0))
        for boundary in ((), (2,), (2, 0), (2, 0, 1)):
            expected = {
                tuple(colors[v] for v in boundary)
                for colors in brute_colorings(3, edges)
            }
            with self.subTest(boundary=boundary):
                self.assertEqual(set(boundary_signature(3, edges, boundary)), expected)
        self.assertEqual(set(boundary_signature(1, ((0, 0),), ())), set())

    def test_gluing_is_match_then_projection(self):
        # Two triangles share edge (0,1); their remaining vertices are 2 and 3.
        # Retain actual color names until the common boundary has been matched.
        triangle = ((0, 1), (1, 2), (2, 0))
        left = boundary_signature(3, triangle, (0, 1, 2))
        right = boundary_signature(3, triangle, (0, 1, 2))
        joined = {
            (a[2], b[2])
            for a in left
            for b in right
            if a[:2] == b[:2]
        }
        whole_edges = ((0, 1), (1, 2), (2, 0), (1, 3), (3, 0))
        expected = {
            (colors[2], colors[3])
            for colors in brute_colorings(4, whole_edges)
        }
        self.assertEqual(joined, expected)
        self.assertEqual(joined, set(boundary_signature(4, whole_edges, (2, 3))))
        self.assertEqual(len(joined), 16)

    def test_canonical_colors_preserve_equality_pattern(self):
        self.assertEqual(canonical_colors(()), ())
        self.assertEqual(canonical_colors((3, 3, 1, 2, 1)), (0, 0, 1, 2, 1))
        for assignment in product(range(4), repeat=4):
            normalized = canonical_colors(assignment)
            self.assertEqual(canonical_colors(normalized), normalized)
            for i in range(4):
                for j in range(4):
                    self.assertEqual(assignment[i] == assignment[j], normalized[i] == normalized[j])

    def test_independent_renaming_requires_alignment(self):
        # The shared vertex has real color 3 in both pieces, but occurs second
        # on the left and first on the right. Separate canonicalization gives
        # it names 1 and 0. A naive join would wrongly reject compatible pieces.
        left, right = (2, 3), (3, 2)
        self.assertEqual(left[1], right[0])
        self.assertNotEqual(canonical_colors(left)[1], canonical_colors(right)[0])

    def test_proper_boundary_may_fail_to_extend_to_a_colorable_map(self):
        # A four-cycle with a central vertex is planar. A rim using all four
        # colors is proper but leaves no hub color; alternating two rim colors
        # does extend. This is an obstruction to a chosen precoloring, not to 4CT.
        rim = ((0, 1), (1, 2), (2, 3), (3, 0))
        wheel = rim + tuple((vertex, 4) for vertex in range(4))
        proper_rims = brute_colorings(4, rim)
        extensions = brute_colorings(5, wheel)
        signature = set(boundary_signature(5, wheel, (0, 1, 2, 3)))
        self.assertEqual(len(proper_rims), 84)
        self.assertEqual(len(extensions), 72)
        self.assertEqual(len(signature), 60)
        self.assertEqual(signature, {assignment[:4] for assignment in extensions})
        self.assertIn((0, 1, 2, 3), proper_rims)
        self.assertNotIn((0, 1, 2, 3), signature)
        self.assertEqual(set(colorings(5, wheel, precolored={0: 0, 1: 1, 2: 2, 3: 3})), set())
        self.assertIn((0, 1, 0, 1, 2), extensions)
        self.assertEqual(proper_rims - signature, {colors for colors in proper_rims if len(set(colors)) == 4})


if __name__ == "__main__":
    unittest.main()

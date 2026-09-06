"""Check plane embeddings including loops, bridges, and multiedges."""

from itertools import product
import unittest

from fourcolor.embedding import PlaneMap, vertex_defects
from fourcolor.examples import dangling_triangle_map, tetrahedron_map, triangle_map
from tests.oracles import xor_defects


def face_assignment_is_proper(plane_map, colors):
    """Independent edge-by-edge face coloring definition, including bridges."""
    for edge_id in range(len(plane_map.edges)):
        left, right = plane_map.shores(edge_id)
        if left != right and colors[left] == colors[right]:
            return False
    return True


class EmbeddingTests(unittest.TestCase):
    def assert_plane_map(self, plane_map):
        self.assertEqual(len(plane_map.vertices) - len(plane_map.edges) + len(plane_map.faces), 2)
        darts = [dart for face in plane_map.faces for dart in face]
        self.assertEqual(sorted(darts), list(range(2 * len(plane_map.edges))))
        for face_id, boundary in enumerate(plane_map.faces):
            for dart in boundary:
                self.assertEqual(plane_map.face_of_dart[dart], face_id)
        for edge_id in range(len(plane_map.edges)):
            self.assertEqual(
                plane_map.shores(edge_id),
                (plane_map.face_of_dart[2 * edge_id], plane_map.face_of_dart[2 * edge_id + 1]),
            )

    def test_examples_euler_and_dart_partition(self):
        for builder in (triangle_map, tetrahedron_map, dangling_triangle_map):
            with self.subTest(example=builder.__name__):
                self.assert_plane_map(builder())

    def test_counterclockwise_rotation_gives_left_faces(self):
        # This explicit straight-line drawing realizes the example's rotations.
        # With each face on the traversal's left, bounded faces have positive
        # signed area; the unbounded face boundary has negative signed area.
        plane_map = tetrahedron_map()
        coordinates = {"A": (0, 2), "B": (-2, -1), "C": (2, -1), "O": (0, 0)}
        doubled_areas = []
        for face in plane_map.faces:
            area = 0
            for dart in face:
                u = plane_map.edges[dart // 2][dart % 2]
                v = plane_map.edges[dart // 2][1 - dart % 2]
                x1, y1 = coordinates[u]
                x2, y2 = coordinates[v]
                area += x1 * y2 - x2 * y1
            doubled_areas.append(area)
        self.assertEqual(sum(area > 0 for area in doubled_areas), 3)
        self.assertEqual(sum(area < 0 for area in doubled_areas), 1)
        left, right = plane_map.shores(0)  # A -> B has the interior on its left.
        self.assertGreater(doubled_areas[left], 0)
        self.assertLess(doubled_areas[right], 0)

    def test_isolated_single_vertex(self):
        plane_map = PlaneMap(edges=(), rotation={"A": ()})
        self.assert_plane_map(plane_map)
        self.assertEqual(len(plane_map.faces), 1)
        self.assertTrue(plane_map.check_coloring((0,)))
        self.assertEqual(plane_map.differences((0,)), ())
        self.assertEqual(plane_map.integrate(()), (0,))

    def test_bridge_has_same_face_on_both_sides(self):
        plane_map = PlaneMap(edges=(("A", "B"),), rotation={"A": (0,), "B": (1,)})
        self.assert_plane_map(plane_map)
        self.assertEqual(plane_map.shores(0), (0, 0))
        self.assertEqual(plane_map.differences((2,)), (0,))
        self.assertEqual(plane_map.integrate((0,)), (0,))
        for label in (1, 2, 3):
            with self.subTest(label=label):
                self.assertTrue(any(vertex_defects(plane_map, (label,)).values()))
                with self.assertRaises(ValueError):
                    plane_map.integrate((label,))

    def test_loop_separates_two_faces(self):
        plane_map = PlaneMap(edges=(("A", "A"),), rotation={"A": (0, 1)})
        self.assert_plane_map(plane_map)
        self.assertEqual(len(plane_map.faces), 2)
        self.assertNotEqual(*plane_map.shores(0))
        self.assertFalse(plane_map.check_coloring((0, 0)))
        for label in (1, 2, 3):
            with self.subTest(label=label):
                self.assertEqual(set(vertex_defects(plane_map, (label,)).values()), {0})
                colors = plane_map.integrate((label,))
                self.assertTrue(plane_map.check_coloring(colors))
                self.assertEqual(plane_map.differences(colors), (label,))

    def test_parallel_edges(self):
        plane_map = PlaneMap(
            edges=(("A", "B"),) * 3,
            rotation={"A": (0, 2, 4), "B": (1, 5, 3)},
        )
        self.assert_plane_map(plane_map)
        self.assertEqual(len(plane_map.faces), 3)
        for labels in product((1, 2, 3), repeat=3):
            valid = len(set(labels)) == 3
            self.assertEqual(not any(vertex_defects(plane_map, labels).values()), valid)
            if valid:
                self.assertTrue(plane_map.check_coloring(plane_map.integrate(labels)))
            else:
                with self.assertRaises(ValueError):
                    plane_map.integrate(labels)

    def test_tetrahedron_all_face_assignments(self):
        plane_map = tetrahedron_map()
        self.assertEqual(len(plane_map.faces), 4)
        valid_count = 0
        difference_states = set()
        for colors in product(range(4), repeat=4):
            expected = face_assignment_is_proper(plane_map, colors)
            self.assertEqual(plane_map.check_coloring(colors), expected)
            if expected:
                valid_count += 1
                labels = plane_map.differences(colors)
                difference_states.add(labels)
                self.assertTrue(all(labels))
                self.assertTrue(all(value == 0 for value in vertex_defects(plane_map, labels).values()))
                reconstructed = plane_map.integrate(labels)
                # Integration fixes one face to 0, so compare only differences.
                self.assertEqual(plane_map.differences(reconstructed), labels)
        self.assertEqual(valid_count, 24)
        self.assertEqual(len(difference_states), 6)

    def test_tetrahedron_all_nonzero_edge_assignments(self):
        plane_map = tetrahedron_map()
        index = {vertex: i for i, vertex in enumerate(plane_map.vertices)}
        integer_edges = tuple((index[u], index[v]) for u, v in plane_map.edges)
        balanced_count = 0
        for labels in product((1, 2, 3), repeat=len(plane_map.edges)):
            expected_defects = xor_defects(len(index), integer_edges, labels)
            self.assertEqual(tuple(vertex_defects(plane_map, labels).values()), expected_defects)
            balanced = all(value == 0 for value in expected_defects)
            if balanced:
                balanced_count += 1
                colors = plane_map.integrate(labels)
                self.assertTrue(plane_map.check_coloring(colors))
                self.assertEqual(plane_map.differences(colors), labels)
            else:
                with self.assertRaises(ValueError):
                    plane_map.integrate(labels)
        self.assertEqual(balanced_count, 6)

    def test_zero_nonbridge_differences_rejected_despite_zero_defects(self):
        # Zero XOR defects alone do not ensure a proper coloring. This API's
        # integrate() promises a proper coloring and also checks nonbridge edges.
        plane_map = triangle_map()
        labels = (0,) * len(plane_map.edges)
        self.assertTrue(all(value == 0 for value in vertex_defects(plane_map, labels).values()))
        with self.assertRaises(ValueError):
            plane_map.integrate(labels)

    def test_dangling_edge_forces_zero_difference(self):
        plane_map = dangling_triangle_map()
        bridges = [i for i in range(len(plane_map.edges)) if len(set(plane_map.shores(i))) == 1]
        self.assertEqual(len(bridges), 1)
        proper_count = 0
        for colors in product(range(4), repeat=len(plane_map.faces)):
            if face_assignment_is_proper(plane_map, colors):
                proper_count += 1
                labels = plane_map.differences(colors)
                self.assertEqual(labels[bridges[0]], 0)
                self.assertTrue(all(value == 0 for value in vertex_defects(plane_map, labels).values()))
        self.assertEqual(proper_count, 12)

    def test_invalid_rotation_rejected(self):
        invalid = [
            {"A": (0,), "B": ()},              # missing dart
            {"A": (0, 0), "B": (1,)},         # duplicate dart
            {"A": (1,), "B": (0,)},           # wrong dart tails
            {"A": (0,), "B": (1, 2)},         # nonexistent dart
        ]
        for rotation in invalid:
            with self.subTest(rotation=rotation), self.assertRaises(ValueError):
                PlaneMap(edges=(("A", "B"),), rotation=rotation)

    def test_toroidal_rotation_rejected_by_euler(self):
        # The same abstract theta multigraph, but this rotation has one face:
        # V-E+F=2-3+1=0, so it is not a sphere/plane embedding.
        with self.assertRaises(ValueError):
            PlaneMap(edges=(("A", "B"),) * 3, rotation={"A": (0, 2, 4), "B": (1, 3, 5)})


if __name__ == "__main__":
    unittest.main()

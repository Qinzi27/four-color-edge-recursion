"""Check explicit corner-based recursive construction of embedded maps."""

from itertools import product
import unittest

from fourcolor.examples import triangle_map
from fourcolor.history import close_split, extend, replay, tetrahedron_history
from tests.test_embedding import face_assignment_is_proper


def apply_operation(plane_map, operation):
    """Dispatch elementary operations independently of replay()."""
    if operation["kind"] == "extend":
        return extend(plane_map, operation["corner"], operation["vertex"])
    if operation["kind"] == "close_split":
        return close_split(plane_map, operation["start"], operation["end"])
    raise ValueError("unsupported test operation")


class HistoryTests(unittest.TestCase):
    def test_tetrahedron_construction_changes(self):
        initial, operations = tetrahedron_history()
        self.assertEqual(len(operations), 3)
        self.assertEqual([operation["kind"] for operation in operations], ["extend", "close_split", "close_split"])
        maps = [initial]
        for operation in operations:
            previous = maps[-1]
            before = (previous.edges, dict(previous.rotation), previous.faces)
            current = apply_operation(previous, operation)
            self.assertEqual((previous.edges, dict(previous.rotation), previous.faces), before)
            self.assertEqual(current.edges[:-1], previous.edges)
            maps.append(current)
        self.assertEqual([len(item.vertices) for item in maps], [3, 4, 4, 4])
        self.assertEqual([len(item.edges) for item in maps], [3, 4, 5, 6])
        self.assertEqual([len(item.faces) for item in maps], [2, 2, 3, 4])
        final = maps[-1]
        adjacent_pairs = {tuple(sorted(final.shores(edge))) for edge in range(len(final.edges))}
        self.assertEqual(adjacent_pairs, {(a, b) for a in range(4) for b in range(a + 1, 4)})
        self.assertEqual(sum(face_assignment_is_proper(final, colors) for colors in product(range(4), repeat=4)), 24)

    def test_extend_adds_a_bridge_without_splitting_a_face(self):
        initial = triangle_map()
        extended = extend(initial, 0, "O")
        self.assertEqual(len(extended.faces), len(initial.faces))
        self.assertEqual(extended.shores(len(initial.edges))[0], extended.shores(len(initial.edges))[1])
        self.assertEqual(extended.rotation["A"], (0, 6, 5))
        self.assertEqual(extended.rotation["O"], (7,))

    def test_close_split_accepts_parallel_edges(self):
        initial = triangle_map()
        changed = close_split(initial, 0, 2)
        self.assertEqual(len(changed.vertices), 3)
        self.assertEqual(len(changed.edges), 4)
        self.assertEqual(len(changed.faces), 3)
        self.assertEqual(changed.edges[-1], ("A", "B"))

    def test_distinct_corner_occurrences_can_create_a_loop(self):
        extended = extend(triangle_map(), 0, "O")
        self.assertEqual(extended.face_of_dart[0], extended.face_of_dart[6])
        changed = close_split(extended, 0, 6)
        self.assertEqual(changed.edges[-1], ("A", "A"))
        self.assertEqual(len(changed.faces), len(extended.faces) + 1)
        self.assertNotEqual(*changed.shores(len(changed.edges) - 1))

    def test_replay_matches_independent_dispatch_and_is_deterministic(self):
        initial, operations = tetrahedron_history()
        expected = initial
        for operation in operations:
            expected = apply_operation(expected, operation)
        actual, logs = replay(initial, operations)
        repeated, repeated_logs = replay(initial, operations)
        self.assertEqual(actual.edges, expected.edges)
        self.assertEqual(dict(actual.rotation), dict(expected.rotation))
        self.assertEqual(actual.faces, expected.faces)
        self.assertEqual(repeated.faces, actual.faces)
        self.assertEqual(logs, repeated_logs)
        self.assertIsInstance(logs, tuple)
        self.assertEqual(len(logs), len(operations))

    def test_logs_track_face_descendants_from_every_old_dart(self):
        initial, operations = tetrahedron_history()
        _, logs = replay(initial, operations)
        previous = initial
        for step, (operation, log) in enumerate(zip(operations, logs), start=1):
            current = apply_operation(previous, operation)
            self.assertEqual(log["step"], step)
            self.assertEqual(log["operation"], operation)
            self.assertEqual(log["created_edge"], len(previous.edges))
            corner = operation["corner"] if operation["kind"] == "extend" else operation["start"]
            self.assertEqual(log["parent_face"], previous.face_of_dart[corner])
            for name, item in (("before", previous), ("after", current)):
                self.assertEqual(log[name], {
                    "vertices": len(item.vertices),
                    "edges": len(item.edges),
                    "faces": len(item.faces),
                })
            expected = {
                old_face: sorted({current.face_of_dart[dart] for dart in darts})
                for old_face, darts in enumerate(previous.faces)
            }
            self.assertEqual(log["face_descendants"], expected)
            previous = current

    def test_empty_replay_preserves_embedding(self):
        initial = triangle_map()
        actual, logs = replay(initial, ())
        self.assertEqual(actual.edges, initial.edges)
        self.assertEqual(dict(actual.rotation), dict(initial.rotation))
        self.assertEqual(logs, ())

    def test_invalid_corners_and_duplicate_vertex_rejected(self):
        initial = triangle_map()
        for dart in (-1, 6, True):
            with self.subTest(dart=dart), self.assertRaises(ValueError):
                extend(initial, dart, "O")
            with self.subTest(dart=dart), self.assertRaises(ValueError):
                close_split(initial, 0, dart)
        with self.assertRaises(ValueError):
            extend(initial, 0, "A")
        with self.assertRaises(ValueError):
            close_split(initial, 0, 0)
        with self.assertRaises(ValueError):
            close_split(initial, 0, 1)  # Opposite faces of edge AB.

    def test_unknown_replay_operation_rejected(self):
        with self.assertRaises(ValueError):
            replay(triangle_map(), ({"kind": "erase_everything"},))


if __name__ == "__main__":
    unittest.main()

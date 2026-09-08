"""Check line-first names against an independent face-based test oracle.

The production API receives only a rotation system and directed line names.
Only these tests use ``PlaneMap.faces`` to independently verify consistency.
Small exhaustive checks are deliberately bounded correctness experiments, not
a coloring algorithm or evidence of a new Four-Color Theorem proof.
"""

from dataclasses import FrozenInstanceError
from itertools import product
import unittest

from fourcolor.embedding import PlaneMap
from fourcolor.examples import dangling_triangle_map, tetrahedron_map, triangle_map
from fourcolor.line_names import audit_line_names, branch_right, canonical_line_names


def rotation_of(plane_map):
    """Remove all face and vertex-name information from the production input."""
    return tuple(plane_map.rotation.values())


def line_names_from_oracle(plane_map, symbols):
    """Prepare test inputs using the independently established dart-to-face map."""
    return tuple(
        (symbols[plane_map.face_of_dart[2 * edge]],
         symbols[plane_map.face_of_dart[2 * edge + 1]])
        for edge in range(len(plane_map.edges))
    )


def oracle_status_and_names(plane_map, names):
    """Evaluate supplied labels directly on existing faces, without the auditor.

Unknown entries on a uniquely named face are forced. A multiply named face is
inconsistent, so its inputs remain unchanged. Proper separation is required
only between distinct faces; bridges create no inequality constraint.
"""
    original = [symbol for pair in names for symbol in pair]
    propagated = original[:]
    conflict = False
    unresolved = []
    for face_id, boundary in enumerate(plane_map.faces):
        known = {original[dart] for dart in boundary if original[dart] is not None}
        if len(known) > 1:
            conflict = True
        elif known:
            symbol = next(iter(known))
            for dart in boundary:
                propagated[dart] = symbol
        else:
            unresolved.append(face_id)
    for edge in range(len(plane_map.edges)):
        left, right = plane_map.shores(edge)
        first, second = propagated[2 * edge:2 * edge + 2]
        if left != right and first is not None and first == second:
            conflict = True
    status = "conflict" if conflict else "underdetermined" if unresolved else "consistent"
    pairs = tuple(zip(propagated[::2], propagated[1::2]))
    return status, pairs, tuple(unresolved)


def bridge_map():
    """A single segment has one side-continuation orbit, not two regions."""
    return PlaneMap(edges=(("A", "B"),), rotation={"A": (0,), "B": (1,)})


def loop_map():
    """A planar loop supplies the smallest genuine separator fixture."""
    return PlaneMap(edges=(("A", "A"),), rotation={"A": (0, 1)})


class LineNameTests(unittest.TestCase):
    """Distinguish geometric consistency, missing data, and color choice."""

    def assert_matches_oracle(self, plane_map, names):
        """Check status, forced propagation, and deterministic orbit indexing."""
        audit = audit_line_names(rotation_of(plane_map), names)
        expected_status, expected_names, unresolved = oracle_status_and_names(plane_map, names)
        self.assertEqual(audit.status, expected_status)
        self.assertEqual(audit.names, expected_names)
        self.assertEqual(audit.side_orbits, plane_map.faces)
        self.assertEqual(audit.unresolved_orbits, unresolved)
        self.assertEqual(bool(audit.conflicts), expected_status == "conflict")
        return audit

    def test_triangle_consistent_line_names(self):
        names = (("red", "blue"),) * 3
        audit = self.assert_matches_oracle(triangle_map(), names)
        self.assertEqual(audit.status, "consistent")
        self.assertEqual(audit.conflicts, ())

    def test_each_line_unequal_does_not_imply_global_consistency(self):
        # All three lines have different left/right symbols, but one reverses
        # the names of the continuing sides. Local legality is insufficient.
        names = (("red", "blue"), ("blue", "red"), ("red", "blue"))
        audit = self.assert_matches_oracle(triangle_map(), names)
        self.assertEqual(audit.status, "conflict")
        self.assertIn("side_mismatch", {item["kind"] for item in audit.conflicts})

    def test_side_mismatch_witness_follows_side_continuation(self):
        plane_map = triangle_map()
        names = (("red", "blue"), ("green", "blue"), (None, "blue"))
        audit = self.assert_matches_oracle(plane_map, names)
        flat = tuple(symbol for pair in names for symbol in pair)
        predecessor = {}
        for darts in rotation_of(plane_map):
            predecessor.update({dart: darts[index - 1] for index, dart in enumerate(darts)})
        witnesses = [item["darts"] for item in audit.conflicts if item["kind"] == "side_mismatch"]
        self.assertTrue(witnesses)
        for path in witnesses:
            self.assertIsInstance(path, tuple)
            self.assertGreaterEqual(len(path), 2)
            self.assertIsNotNone(flat[path[0]])
            self.assertIsNotNone(flat[path[-1]])
            self.assertNotEqual(flat[path[0]], flat[path[-1]])
            for first, second in zip(path, path[1:]):
                self.assertEqual(predecessor[first ^ 1], second)

    def test_partial_symbols_force_complete_triangle_names(self):
        names = (("red", None), (None, "blue"), (None, None))
        audit = self.assert_matches_oracle(triangle_map(), names)
        self.assertEqual(audit.status, "consistent")
        self.assertEqual(audit.names, (("red", "blue"),) * 3)

    def test_auditor_does_not_invent_an_unassigned_symbol(self):
        names = (("red", None), (None, None), (None, None))
        audit = self.assert_matches_oracle(triangle_map(), names)
        self.assertEqual(audit.status, "underdetermined")
        self.assertEqual(audit.names, (("red", None),) * 3)
        self.assertEqual(len(audit.unresolved_orbits), 1)

    def test_all_unknown_remains_underdetermined(self):
        plane_map = tetrahedron_map()
        names = ((None, None),) * len(plane_map.edges)
        audit = self.assert_matches_oracle(plane_map, names)
        self.assertEqual(audit.status, "underdetermined")
        self.assertEqual(len(audit.unresolved_orbits), 4)
        self.assertEqual(audit.names, names)

    def test_conflicting_orbit_is_not_arbitrarily_overwritten(self):
        names = (("red", "blue"), ("green", None), (None, None))
        audit = self.assert_matches_oracle(triangle_map(), names)
        self.assertEqual(audit.names, (("red", "blue"), ("green", "blue"), (None, "blue")))

    def test_separator_cannot_have_equal_known_names(self):
        audit = self.assert_matches_oracle(loop_map(), (("same", "same"),))
        self.assertEqual(audit.status, "conflict")
        self.assertIn("separator_equal", {item["kind"] for item in audit.conflicts})
        # Equality must also be checked after forced propagation, not just on
        # the initially supplied pairs.
        partial = (("same", None), (None, "same"), (None, None))
        self.assertEqual(self.assert_matches_oracle(triangle_map(), partial).status, "conflict")

    def test_bridge_requires_equal_side_names(self):
        plane_map = bridge_map()
        audit = self.assert_matches_oracle(plane_map, (("same", None),))
        self.assertEqual(audit.status, "consistent")
        self.assertEqual(audit.names, (("same", "same"),))
        bad = self.assert_matches_oracle(plane_map, (("first", "second"),))
        self.assertEqual(bad.status, "conflict")
        self.assertEqual({item["kind"] for item in bad.conflicts}, {"side_mismatch"})

    def test_dangling_triangle_keeps_two_orbits(self):
        plane_map = dangling_triangle_map()
        names = line_names_from_oracle(plane_map, ("inside", "outside"))
        audit = self.assert_matches_oracle(plane_map, names)
        self.assertEqual(audit.status, "consistent")
        self.assertEqual(len(audit.side_orbits), 2)
        self.assertEqual(names[3][0], names[3][1])

    def test_tetrahedron_accepts_four_distinct_symbol_names(self):
        plane_map = tetrahedron_map()
        names = line_names_from_oracle(plane_map, ("朱", "蓝", "green", "gold"))
        self.assertEqual(self.assert_matches_oracle(plane_map, names).status, "consistent")

    def test_five_symbols_are_legal_not_excluded_by_an_assumed_palette(self):
        # Five parallel segments form five side orbits. Giving them five
        # distinct names is valid, although fewer colors suffice for this map.
        plane_map = PlaneMap(
            edges=(("A", "B"),) * 5,
            rotation={"A": (0, 2, 4, 6, 8), "B": (9, 7, 5, 3, 1)},
        )
        symbols = tuple(f"symbol-{index}" for index in range(5))
        names = line_names_from_oracle(plane_map, symbols)
        audit = self.assert_matches_oracle(plane_map, names)
        self.assertEqual(audit.status, "consistent")
        self.assertEqual(len({symbol for pair in audit.names for symbol in pair}), 5)

    def test_empty_single_vertex_has_an_unnamed_empty_orbit(self):
        plane_map = PlaneMap(edges=(), rotation={"v": ()})
        audit = self.assert_matches_oracle(plane_map, ())
        self.assertEqual(audit.status, "underdetermined")
        self.assertEqual(audit.side_orbits, ((),))
        self.assertEqual(audit.unresolved_orbits, (0,))

    def test_global_renaming_preserves_audit_and_canonical_form(self):
        plane_map = tetrahedron_map()
        names = line_names_from_oracle(plane_map, ("a", "b", "c", "d"))
        renamed = line_names_from_oracle(plane_map, ("紫", "yellow", "long-name", "z"))
        first = audit_line_names(rotation_of(plane_map), names)
        second = audit_line_names(rotation_of(plane_map), renamed)
        self.assertEqual(first.status, second.status)
        self.assertEqual(first.side_orbits, second.side_orbits)
        self.assertEqual(canonical_line_names(names), canonical_line_names(renamed))
        partial = ((None, "b"), ("a", "b"), ("a", None))
        self.assertEqual(canonical_line_names(partial), ((None, 0), (1, 0), (1, None)))
        self.assertEqual(canonical_line_names(()), ())

    def test_right_branch_is_a_local_template_not_a_global_certificate(self):
        self.assertEqual(branch_right("a", "b", "c"), {
            "incoming": ("a", "b"),
            "continuation": ("a", "c"),
            "branch": ("c", "b"),
            "history": ("a", ("b", "c")),
        })
        # Three differently named sectors around an isolated T-shaped tree
        # do not become three faces; all six darts continue around one orbit.
        tree_rotation = ((1, 2, 4), (0,), (3,), (5,))
        tree_names = (("a", "b"), ("a", "c"), ("c", "b"))
        self.assertEqual(audit_line_names(tree_rotation, tree_names).status, "conflict")

    def test_rejects_invalid_symbol_names_and_branch_arguments(self):
        for bad in ("", 0, True, [], {}):
            with self.subTest(symbol=bad), self.assertRaises(ValueError):
                audit_line_names(((0, 1),), ((bad, "valid"),))
            with self.subTest(canonical_symbol=bad), self.assertRaises(ValueError):
                canonical_line_names(((bad, "valid"),))
        for args in (("a", "a", "b"), ("a", "b", "a"), ("a", "b", "b"),
                     ("", "b", "c"), ("a", None, "c"), ("a", "b", 3)):
            with self.subTest(branch=args), self.assertRaises(ValueError):
                branch_right(*args)

    def test_rejects_malformed_pair_lengths(self):
        for names in (((),), (("a",),), (("a", "b", "c"),), ("ab",), (b"ab",)):
            with self.subTest(names=names), self.assertRaises(ValueError):
                audit_line_names(((0, 1),), names)
            with self.subTest(canonical_names=names), self.assertRaises(ValueError):
                canonical_line_names(names)

    def test_rejects_invalid_dart_ids_and_disconnected_rotations(self):
        invalid = (
            (), ((0,), ()), ((0, 0), (1,)), ((0,), (1, 2)),
            ((False,), (1,)), ((0.0,), (1,)), ((-1,), (1,)),
            ((0,), (1,), ()),
        )
        for rotation in invalid:
            with self.subTest(rotation=rotation), self.assertRaises(ValueError):
                audit_line_names(rotation, (("a", "a"),))
        with self.assertRaises(ValueError):
            audit_line_names(((), ()), ())
        # Two independent loops are individually planar but disconnected.
        with self.assertRaises(ValueError):
            audit_line_names(((0, 1), (2, 3)), (("a", "b"), ("a", "b")))

    def test_rejects_positive_genus_rotation(self):
        # This theta graph has Euler characteristic zero, not a plane embedding.
        with self.assertRaises(ValueError):
            audit_line_names(((0, 2, 4), (1, 3, 5)), ((None, None),) * 3)

    def test_audit_is_deterministic_frozen_and_does_not_mutate_inputs(self):
        rotation = [list(darts) for darts in rotation_of(triangle_map())]
        names = [["red", None], [None, "blue"], [None, None]]
        rotation_snapshot = [darts[:] for darts in rotation]
        names_snapshot = [pair[:] for pair in names]
        first = audit_line_names(rotation, names)
        second = audit_line_names(rotation, names)
        self.assertEqual(first, second)
        self.assertEqual(rotation, rotation_snapshot)
        self.assertEqual(names, names_snapshot)
        names[0][0] = "changed-after-audit"
        rotation[0].reverse()
        self.assertEqual(first.names, (("red", "blue"),) * 3)
        with self.assertRaises(FrozenInstanceError):
            first.status = "modified"

    def test_exhaustive_two_symbol_dart_assignments(self):
        # Exactly 328 complete assignments: 4 + 4 + 64 + 256. Enumeration
        # belongs to this independent finite test, never to production naming.
        checked = 0
        for plane_map in (bridge_map(), loop_map(), triangle_map(), dangling_triangle_map()):
            for assignment in product(("a", "b"), repeat=2 * len(plane_map.edges)):
                names = tuple(zip(assignment[::2], assignment[1::2]))
                with self.subTest(rotation=rotation_of(plane_map), names=names):
                    self.assert_matches_oracle(plane_map, names)
                checked += 1
        self.assertEqual(checked, 328)

    def test_exhaustive_partial_dart_assignments(self):
        # Exactly 747 partial/full assignments: 3**2 + 3**2 + 3**6.
        checked = 0
        for plane_map in (bridge_map(), loop_map(), triangle_map()):
            for assignment in product((None, "a", "b"), repeat=2 * len(plane_map.edges)):
                names = tuple(zip(assignment[::2], assignment[1::2]))
                with self.subTest(rotation=rotation_of(plane_map), names=names):
                    self.assert_matches_oracle(plane_map, names)
                checked += 1
        self.assertEqual(checked, 747)


if __name__ == "__main__":
    unittest.main()

"""Audit the restricted endpoint-only interpretation, not the user's full rule.

The two-port mex and full-boundary diagnostic are deliberately different rules.
A local contradiction must not be described as disproving mother-line inheritance
or four-colorability. These tests never choose colors using a coloring solver.
"""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from itertools import combinations
import unittest

from fourcolor.inherited_names import (
    attempt_cut, choose_inherited_name, initial_state, line_profiles,
)


def geometry_names(state):
    """Compare physical names without confusing side IDs with their symbols."""
    return sorted((side.bounds, side.symbol) for side in state.sides)


def independent_conflicts(state):
    """Audit rectangle contacts directly, with corner-only contacts excluded."""
    conflicts = []
    for side in state.sides:
        x0, y0, x1, y1 = side.bounds
        if side.symbol == 1 and (x0 == 0 or y0 == 0 or x1 == state.width or y1 == state.height):
            conflicts.append((side.id, "outside"))
    for first, second in combinations(state.sides, 2):
        x0, y0, x1, y1 = first.bounds
        u0, v0, u1, v1 = second.bounds
        vertical = (x1 == u0 or u1 == x0) and min(y1, v1) > max(y0, v0)
        horizontal = (y1 == v0 or v1 == y0) and min(x1, u1) > max(x0, u0)
        if (vertical or horizontal) and first.symbol == second.symbol:
            conflicts.append((first.id, second.id))
    return conflicts


class InheritedNameTests(unittest.TestCase):
    """Keep the endpoint proposal, rejected state, and diagnostic repair apart."""

    def two_cut_state(self):
        """Build the valid 3 | 2 | 3 history in the stated stroke directions."""
        state = initial_state()
        for points in ([[300, 0], [300, 600]], [[600, 600], [600, 0]]):
            result = attempt_cut(state, points, inherit="left")
            self.assertEqual(result["status"], "split")
            state = result["state"]
        return state

    def assert_partition(self, state):
        """Check exact coverage/no overlap independently for these integer maps."""
        area = 0
        for side in state.sides:
            x0, y0, x1, y1 = side.bounds
            self.assertTrue(0 <= x0 < x1 <= state.width)
            self.assertTrue(0 <= y0 < y1 <= state.height)
            area += (x1 - x0) * (y1 - y0)
        self.assertEqual(area, state.width * state.height)
        for first, second in combinations(state.sides, 2):
            x0, y0, x1, y1 = first.bounds
            u0, v0, u1, v1 = second.bounds
            self.assertFalse(min(x1, u1) > max(x0, u0) and min(y1, v1) > max(y0, v0))

    def test_initial_closed_frame_and_invalid_dimensions(self):
        """One closed mother starts with outside 1 / inside 2, without cuts."""
        state = initial_state()
        self.assertEqual(geometry_names(state), [((0, 0, 900, 600), 2)])
        self.assertEqual(state.cuts, ())
        profile = line_profiles(state)
        self.assertEqual(set(profile), {"frame"})
        self.assertEqual(len(profile["frame"]), 4)
        self.assertTrue(all(item["pair"] == (1, 2) for item in profile["frame"]))
        self.assert_partition(state)
        for value in (True, False, 0, -1, float("nan"), float("inf"), "900", None):
            for dimension in ("width", "height"):
                with self.subTest(value=value, dimension=dimension):
                    with self.assertRaises(ValueError):
                        initial_state(**{dimension: value})

    def test_user_local_examples_and_unbounded_mex(self):
        """The helper implements mex, not a hard-coded four-symbol palette."""
        for inherited, retained, expected in ((2, [1], 3), (3, [1, 2], 4),
                                                (4, [1, 3], 2), (4, [1, 2, 3], 5)):
            with self.subTest(inherited=inherited, retained=retained):
                self.assertEqual(choose_inherited_name(inherited, retained), expected)
        # Independently verify minimality over all subsets of six small names.
        for inherited in range(1, 7):
            for mask in range(64):
                retained = [value for value in range(1, 7) if mask & (1 << (value - 1))]
                snapshot = retained.copy()
                result = choose_inherited_name(inherited, retained)
                forbidden = retained + [inherited]
                self.assertNotIn(result, forbidden)
                self.assertTrue(all(value in forbidden for value in range(1, result)))
                self.assertEqual(retained, snapshot)
                self.assertEqual(choose_inherited_name(inherited, iter(retained * 2)), result)

    def test_invalid_names_are_rejected_before_deduplication(self):
        """Boolean/float equality with 1 must not hide invalid source values."""
        cases = [(True, [1]), (1.0, [1]), (2, [1, True]), (2, [1, 1.0]),
                 (0, []), (-1, []), ("2", [1]), (2, [0]), (2, [-1]),
                 (2, [None]), (2, [float("nan")])]
        for inherited, retained in cases:
            with self.subTest(inherited=inherited, retained=retained):
                with self.assertRaises(ValueError):
                    choose_inherited_name(inherited, retained)

    def test_two_cuts_keep_distinct_side_ids_with_repeated_names(self):
        """Repeated 3 names are legal on nonadjacent sides and do not merge IDs."""
        state = self.two_cut_state()
        self.assertEqual(geometry_names(state), [((0, 0, 300, 600), 3),
                                                ((300, 0, 600, 600), 2),
                                                ((600, 0, 900, 600), 3)])
        self.assertEqual(len({side.id for side in state.sides}), 3)
        self.assertEqual(independent_conflicts(state), [])
        self.assert_partition(state)

    def test_endpoint_only_third_attempt_conflicts_without_mutating_history(self):
        """Both inheritance choices expose a missing old-boundary restriction."""
        state = self.two_cut_state()
        snapshot = deepcopy(state)
        for inherit, pair, conflicting_x in (("left", [2, 3], 300),
                                              ("right", [3, 2], 600)):
            with self.subTest(inherit=inherit):
                result = attempt_cut(state, [[450, 0], [450, 600]], inherit=inherit)
                event = result["event"]
                self.assertEqual(result["status"], "conflict")
                self.assertIs(result["state"], state)
                self.assertEqual(event["inherited_name"], 2)
                self.assertEqual(event["endpoint_retained"], [1])
                self.assertEqual(event["new_name"], 3)
                self.assertEqual(event["new_line_pair"], pair)
                self.assertEqual([port["mother"] for port in event["ports"]], ["frame", "frame"])
                self.assertEqual(len(event["conflicts"]), 1)
                self.assertEqual(event["conflicts"][0]["segment"],
                                 ((conflicting_x, 0), (conflicting_x, 600)))
                self.assertTrue(independent_conflicts(result["proposed_state"]))
                self.assert_partition(result["proposed_state"])
                self.assertEqual(len(result["proposed_state"].cuts), 3)
        self.assertEqual(state, snapshot)
        self.assertEqual(independent_conflicts(state), [])
        self.assertEqual(len(state.cuts), 2)

    def test_full_boundary_four_is_valid_diagnostic_not_applied_fallback(self):
        """Using full R={1,3} permits 4 but is a different rule from the two ports."""
        state = self.two_cut_state()
        result = attempt_cut(state, [[450, 0], [450, 600]])
        event = result["event"]
        parent = event["parent"]
        for diagnostic in event["boundary_diagnostics"]:
            self.assertEqual(diagnostic["full_boundary_retained"], [1, 3])
            self.assertEqual(diagnostic["missing_from_ports"], [3])
            self.assertEqual(diagnostic["diagnostic_new_name"], 4)
            self.assertEqual(diagnostic["diagnostic_conflicts"], [])
            # Independently construct this diagnostic only, without accepting it.
            child_id = parent + "." + diagnostic["new_name_side"][0]
            repaired_sides = tuple(replace(side, symbol=4 if side.id == child_id else 2)
                                   if side.id.startswith(parent + ".") else side
                                   for side in result["proposed_state"].sides)
            diagnostic_state = replace(result["proposed_state"], sides=repaired_sides)
            self.assertEqual(independent_conflicts(diagnostic_state), [])
            self.assert_partition(diagnostic_state)
        self.assertEqual(result["status"], "conflict")
        self.assertIs(result["state"], state)
        self.assertEqual(event["new_name"], 3)
        self.assertNotIn(4, [side.symbol for side in result["proposed_state"].sides])

    def test_reverse_strokes_and_swap_inheritance_preserves_physical_names(self):
        """Direction reverses ordered pairs, not the underlying geometric result."""
        forward = initial_state()
        reverse = initial_state()
        cuts = ([[300, 0], [300, 600]], [[600, 600], [600, 0]], [[450, 0], [450, 600]])
        for points in cuts:
            first = attempt_cut(forward, points, inherit="left")
            second = attempt_cut(reverse, list(reversed(points)), inherit="right")
            self.assertEqual(first["status"], second["status"])
            self.assertEqual(geometry_names(first["proposed_state"]),
                             geometry_names(second["proposed_state"]))
            self.assertEqual(first["event"]["new_line_pair"],
                             list(reversed(second["event"]["new_line_pair"])))
            forward, reverse = first["state"], second["state"]
        for original, backwards in zip(forward.cuts, reverse.cuts):
            self.assertEqual(original, tuple(reversed(backwards)))

    def test_mother_geometry_survives_local_profile_renaming(self):
        """A T junction changes part of the old pair without replacing its mother."""
        first = attempt_cut(initial_state(), [[300, 0], [300, 600]])["state"]
        before = line_profiles(first)
        result = attempt_cut(first, [[0, 300], [300, 300]])
        self.assertEqual(result["status"], "split")
        self.assertEqual(result["event"]["endpoint_retained"], [1, 2])
        self.assertEqual(result["event"]["inherited_name"], 3)
        self.assertEqual(result["event"]["new_name"], 4)
        self.assertEqual([port["mother"] for port in result["event"]["ports"]], ["frame", "cut-1"])
        after = line_profiles(result["state"])
        self.assertEqual(set(after), {"frame", "cut-1", "cut-2"})
        self.assertEqual(before["cut-1"], [{"segment": ((300, 0), (300, 600)), "pair": (2, 3)}])
        self.assertEqual(after["cut-1"], [
            {"segment": ((300, 0), (300, 300)), "pair": (2, 3)},
            {"segment": ((300, 300), (300, 600)), "pair": (2, 4)},
        ])
        self.assertEqual(after["cut-2"], [{"segment": ((0, 300), (300, 300)), "pair": (3, 4)}])
        self.assertEqual(result["state"].cuts[0], first.cuts[0])
        self.assertTrue(all(item["pair"][0] == 1 for item in after["frame"]))
        self.assertEqual(independent_conflicts(result["state"]), [])
        # The east side is untouched; its immutable object can be preserved.
        east = next(side for side in first.sides if side.bounds[0] == 300)
        self.assertIn(east, result["state"].sides)

    def test_state_and_input_point_lists_are_immutable(self):
        """Storing a cut copies nested input coordinates instead of aliasing them."""
        state = initial_state()
        points = [[300, 0], [300, 600]]
        result = attempt_cut(state, points)
        saved = result["state"]
        points[0][0] = 123
        points.append([0, 0])
        self.assertEqual(saved.cuts, (((300, 0), (300, 600)),))
        self.assertEqual(state.cuts, ())
        self.assertIs(saved, result["proposed_state"])
        with self.assertRaises(FrozenInstanceError):
            saved.width = 10
        with self.assertRaises(FrozenInstanceError):
            saved.sides[0].symbol = 10

    def test_unsupported_geometry_is_not_a_naming_contradiction(self):
        """Old junctions, loops and partial/multi-side cuts stay outside scope."""
        initial = initial_state()
        first = attempt_cut(initial, [[300, 0], [300, 600]])["state"]
        junction_result = attempt_cut(first, [[300, 300], [900, 300]])
        self.assertEqual(junction_result["status"], "split")
        cases = [(initial, [[100, 0], [100, 300]]),
                 (initial, [[0, 0], [900, 600]]),
                 (initial, [[100, 100], [100, 100]]),
                 (initial, [[0, 0], [900, 0]]),
                 (initial, [[0, 0], [100, 0], [100, 100], [0, 0]]),
                 (first, [[0, 300], [900, 300]]),
                 (first, [[300, 0], [300, 600]]),
                 (junction_result["state"], [[0, 300], [300, 300]])]
        malformed = (None, [], [[1, 2]], [1, 2], [[1, 2, 3], [4, 5]],
                     [[True, 0], [True, 600]], [["300", 0], [300, 600]],
                     [[float("nan"), 0], [300, 600]], [[300, 0], [300, float("inf")]])
        cases.extend((initial, points) for points in malformed)
        for state, points in cases:
            with self.subTest(points=points, cuts=len(state.cuts)):
                result = attempt_cut(state, points)
                self.assertEqual(result["status"], "outside_scope")
                self.assertIs(result["state"], state)
                self.assertTrue(result["event"]["reason"])
                self.assertNotIn("proposed_state", result)
        for inherit in (None, "west", "LEFT", 1, True):
            with self.subTest(inherit=inherit):
                with self.assertRaises(ValueError):
                    attempt_cut(initial, [[300, 0], [300, 600]], inherit=inherit)


if __name__ == "__main__":
    unittest.main()

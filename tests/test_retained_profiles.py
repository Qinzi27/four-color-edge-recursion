"""Independent audits of full-boundary naming and verified strip synchronization.

The frozen-old-name mex diagnostic is not a counterexample to the user's
renaming method. Tests distinguish that diagnostic from a synchronized update,
and distinguish a line's ordered pair from its unordered naming type.
"""

from copy import deepcopy
from itertools import combinations
import unittest

from fourcolor.inherited_names import RectSide, RectState, initial_state, line_profiles
from fourcolor.retained_profiles import attempt_profile_cut


def geometry_names(state):
    """Ignore side IDs only when comparing physical naming assignments."""
    return sorted((side.bounds, side.symbol) for side in state.sides)


def rectangle_conflicts(state):
    """Derive positive-length adjacency directly, without a coloring solver."""
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


class RetainedProfileTests(unittest.TestCase):
    """Verify complete geometry and all mother profiles after each update."""

    def assert_valid(self, state):
        """Check exact rectangle partition, legal names and real separators."""
        total_area = 0
        for side in state.sides:
            x0, y0, x1, y1 = side.bounds
            self.assertTrue(0 <= x0 < x1 <= state.width)
            self.assertTrue(0 <= y0 < y1 <= state.height)
            self.assertIs(type(side.symbol), int)
            self.assertTrue(1 <= side.symbol <= 4)
            total_area += (x1 - x0) * (y1 - y0)
        self.assertAlmostEqual(total_area, state.width * state.height)
        self.assertEqual(len({side.id for side in state.sides}), len(state.sides))
        for first, second in combinations(state.sides, 2):
            x0, y0, x1, y1 = first.bounds
            u0, v0, u1, v1 = second.bounds
            self.assertFalse(min(x1, u1) > max(x0, u0) and min(y1, v1) > max(y0, v0))
        self.assertEqual(rectangle_conflicts(state), [])

    def assert_profiles(self, state, profiles):
        """Sample both actual geometric shores and check intact line coverage."""
        self.assertEqual(set(profiles), {"frame"} | {f"cut-{i + 1}" for i in range(len(state.cuts))})
        delta = min(min(side.bounds[2] - side.bounds[0], side.bounds[3] - side.bounds[1])
                    for side in state.sides) / 10

        def name_at(x, y):
            """Read one interior rectangle, or the actual exterior of the paper."""
            if x < 0 or x > state.width or y < 0 or y > state.height:
                return 1
            found = [side.symbol for side in state.sides
                     if side.bounds[0] < x < side.bounds[2] and side.bounds[1] < y < side.bounds[3]]
            self.assertEqual(len(found), 1)
            return found[0]

        for mother, spans in profiles.items():
            length = 0
            for span in spans:
                (x0, y0), (x1, y1) = span["segment"]
                dx, dy = x1 - x0, y1 - y0
                segment_length = abs(dx) + abs(dy)
                self.assertGreater(segment_length, 0)
                length += segment_length
                # Screen coordinates: the directed left normal is (dy, -dx).
                mx, my = (x0 + x1) / 2, (y0 + y1) / 2
                nx, ny = dy / segment_length, -dx / segment_length
                expected = (name_at(mx + delta * nx, my + delta * ny),
                            name_at(mx - delta * nx, my - delta * ny))
                self.assertEqual(tuple(span["pair"]), expected)
                self.assertEqual(tuple(span["type"]), tuple(sorted(expected)))
                self.assertNotEqual(*expected)
            if mother == "frame":
                self.assertAlmostEqual(length, 2 * (state.width + state.height))
            else:
                start, end = state.cuts[int(mother.split("-")[1]) - 1]
                self.assertAlmostEqual(length, abs(end[0] - start[0]) + abs(end[1] - start[1]))
                self.assertEqual(tuple(spans[0]["segment"][0]), start)
                self.assertEqual(tuple(spans[-1]["segment"][1]), end)

    def user_state(self):
        """Construct the user's drawing by its actual three directed strokes."""
        state = initial_state()
        steps = [([[0, 200], [900, 200]], "left"),
                 ([[300, 200], [300, 600]], "right"),
                 ([[600, 200], [600, 600]], "right")]
        for points, inherit in steps:
            result = attempt_profile_cut(state, points, inherit=inherit)
            self.assertEqual(result["status"], "split")
            state = result["state"]
            self.assert_valid(state)
            self.assert_profiles(state, result["event"]["line_profiles_after"])
        return state

    def strip_state(self, count):
        """Use successful monotone cuts, not assigned target colors, for strips."""
        state = attempt_profile_cut(initial_state(), [[0, 200], [900, 200]])["state"]
        boundaries = [900 * index / count for index in range(count + 1)]
        for x in boundaries[1:-1]:
            result = attempt_profile_cut(state, [[x, 200], [x, 600]], inherit="right")
            self.assertEqual(result["status"], "split")
            state = result["state"]
        return state, boundaries

    def test_user_drawing_has_equal_unordered_but_reversed_ordered_line_names(self):
        """Two downward lines both have type {3,4}, not the same ordered pair."""
        state = self.user_state()
        self.assertEqual(geometry_names(state), [((0, 0, 900, 200), 2),
                                                ((0, 200, 300, 600), 3),
                                                ((300, 200, 600, 600), 4),
                                                ((600, 200, 900, 600), 3)])
        profiles = line_profiles(state)
        self.assertEqual([span["pair"] for span in profiles["cut-1"]], [(2, 3), (2, 4), (2, 3)])
        self.assertEqual([span["pair"] for span in profiles["cut-2"]], [(4, 3)])
        self.assertEqual([span["pair"] for span in profiles["cut-3"]], [(3, 4)])
        self.assertEqual(sorted(profiles["cut-2"][0]["pair"]), sorted(profiles["cut-3"][0]["pair"]))

    def test_frozen_old_names_require_five_only_as_explicit_diagnostic(self):
        """The proposed fifth name is retained as evidence, never committed."""
        state = self.user_state()
        snapshot = deepcopy(state)
        result = attempt_profile_cut(state, [[450, 200], [450, 600]], inherit="right")
        event = result["event"]
        self.assertEqual(result["status"], "blocked_sync_required")
        self.assertIs(result["state"], state)
        self.assertEqual(event["full_boundary_retained"], [1, 2, 3])
        self.assertEqual(event["inherited_name"], 4)
        self.assertEqual(event["diagnostic_new_name"], 5)
        self.assertIn(5, [side.symbol for side in result["proposed_state"].sides])
        self.assertEqual(rectangle_conflicts(result["proposed_state"]), [])
        self.assertEqual(event["changed_old_side_ids"], [])
        self.assertEqual(state, snapshot)

    def test_verified_sync_changes_old_side_and_refreshes_every_profile(self):
        """Synchronized four-name output is a new naming of the same old lines."""
        state = self.user_state()
        snapshot = deepcopy(state)
        result = attempt_profile_cut(state, [[450, 200], [450, 600]],
                                     inherit="right", synchronize=True)
        event = result["event"]
        self.assertEqual(result["status"], "split")
        self.assertEqual(event["method"], "verified_strip_sync")
        self.assertEqual(event["diagnostic_new_name"], 5)
        self.assertEqual(event["requested_inherit"], "right")
        self.assertEqual(event["actual_inherit"], "left")
        self.assertGreaterEqual(len(event["changed_old_side_ids"]), 1)
        self.assert_valid(result["state"])
        self.assert_profiles(state, event["line_profiles_before"])
        self.assert_profiles(result["state"], event["line_profiles_after"])
        bottom = sorted((side for side in result["state"].sides if side.bounds[1] == 200),
                        key=lambda side: side.bounds[0])
        self.assertTrue(all(side.symbol in (3, 4) for side in bottom))
        self.assertTrue(all(first.symbol != second.symbol for first, second in zip(bottom, bottom[1:])))
        before_ids = {side.id: side for side in state.sides}
        after_ids = {side.id: side for side in result["state"].sides}
        changed = {key for key in before_ids.keys() & after_ids.keys()
                   if before_ids[key].symbol != after_ids[key].symbol}
        self.assertEqual(set(event["changed_old_side_ids"]), changed)
        for key in before_ids.keys() & after_ids.keys():
            self.assertEqual(before_ids[key].bounds, after_ids[key].bounds)
        self.assertEqual(result["state"].cuts[:-1], state.cuts)
        # Changes must list every changed mother occurrence, including the frame.
        before_profiles, after_profiles = event["line_profiles_before"], event["line_profiles_after"]
        changed_mothers = {mother for mother in before_profiles.keys() | after_profiles.keys()
                           if before_profiles.get(mother, []) != after_profiles.get(mother, [])}
        self.assertEqual({row["mother"] for row in event["profile_changes"]}, changed_mothers)
        for row in event["profile_changes"]:
            self.assertEqual(row["before"], before_profiles.get(row["mother"], []))
            self.assertEqual(row["after"], after_profiles.get(row["mother"], []))
        self.assertEqual(state, snapshot)

    def test_three_simple_inheritance_examples_are_real_geometric_steps(self):
        """Reproduce 2/R1->3, 3/R12->4 and 4/R13->2 without hand coloring."""
        state = initial_state()
        examples = [([[300, 0], [300, 600]], 2, [1], 3),
                    ([[0, 300], [300, 300]], 3, [1, 2], 4),
                    ([[150, 300], [150, 600]], 4, [1, 3], 2)]
        for points, inherited, retained, new in examples:
            result = attempt_profile_cut(state, points)
            self.assertEqual(result["status"], "split")
            event = result["event"]
            self.assertEqual(event["inherited_name"], inherited)
            self.assertEqual(event["full_boundary_retained"], retained)
            self.assertEqual(event["new_name"], new)
            self.assertEqual(event["changed_old_side_ids"], [])
            state = result["state"]
            self.assert_valid(state)
            self.assert_profiles(state, event["line_profiles_after"])

    def test_old_parallel_example_uses_four_without_synchronization(self):
        """Complete boundary R={1,3}, unlike endpoint R={1}, directly allows 4."""
        state = initial_state()
        for points in ([[300, 0], [300, 600]], [[600, 600], [600, 0]]):
            result = attempt_profile_cut(state, points)
            self.assertEqual(result["status"], "split")
            state = result["state"]
        for inherit in ("left", "right"):
            result = attempt_profile_cut(state, [[450, 0], [450, 600]], inherit=inherit, synchronize=True)
            self.assertEqual(result["status"], "split")
            self.assertEqual(result["event"]["method"], "complete_boundary_mex")
            self.assertEqual(result["event"]["full_boundary_retained"], [1, 3])
            self.assertEqual(result["event"]["new_name"], 4)
            self.assertEqual(result["event"]["changed_old_side_ids"], [])
            self.assert_valid(result["state"])
            self.assert_profiles(result["state"], result["event"]["line_profiles_after"])

    def test_finite_strip_positions_and_direction_reversal(self):
        """Every location in one through six strips is checked independently."""
        for count in range(1, 7):
            state, boundaries = self.strip_state(count)
            snapshot = deepcopy(state)
            for index, (start, end) in enumerate(zip(boundaries, boundaries[1:])):
                x = (start + end) / 2
                with self.subTest(count=count, index=index):
                    forward = attempt_profile_cut(state, [[x, 200], [x, 600]],
                                                  inherit="right", synchronize=True)
                    reverse = attempt_profile_cut(state, [[x, 600], [x, 200]],
                                                  inherit="left", synchronize=True)
                    for result in (forward, reverse):
                        self.assertEqual(result["status"], "split")
                        self.assert_valid(result["state"])
                        self.assert_profiles(result["state"], result["event"]["line_profiles_after"])
                        if result["event"]["method"] == "verified_strip_sync":
                            self.assertEqual(len(result["event"]["changed_old_side_ids"]),
                                             min(index, count - index - 1))
                        else:
                            self.assertEqual(result["event"]["changed_old_side_ids"], [])
                    self.assertEqual(geometry_names(forward["state"]), geometry_names(reverse["state"]))
                    self.assertEqual(forward["event"]["new_line_pair"],
                                     list(reversed(reverse["event"]["new_line_pair"])))
            self.assertEqual(state, snapshot)

    def test_transposed_strip_uses_geometric_up_tie_rule(self):
        """Swapping x/y exercises the other band orientation, not a new solver."""
        def transpose(state):
            """Map the full geometry, existing names and historical directions."""
            return RectState(state.height, state.width,
                             tuple(RectSide(side.id,
                                            (side.bounds[1], side.bounds[0], side.bounds[3], side.bounds[2]),
                                            side.symbol) for side in state.sides),
                             tuple(tuple((y, x) for x, y in cut) for cut in state.cuts))

        state = self.user_state()
        forward = attempt_profile_cut(state, [[450, 200], [450, 600]],
                                      inherit="right", synchronize=True)
        transformed = attempt_profile_cut(transpose(state), [[200, 450], [600, 450]],
                                          inherit="left", synchronize=True)
        self.assertEqual(transformed["status"], "split")
        self.assertEqual(transformed["event"]["method"], "verified_strip_sync")
        self.assertEqual(transformed["event"]["synchronization"]["swapped_geometric_side"], "up")
        self.assertEqual(geometry_names(transformed["state"]), geometry_names(transpose(forward["state"])))
        self.assert_valid(transformed["state"])
        self.assert_profiles(transformed["state"], transformed["event"]["line_profiles_after"])

    def test_sync_refuses_splitting_the_anchor_out_of_the_strip_family(self):
        """An old strip state does not authorize a non-strip resulting geometry."""
        state = attempt_profile_cut(initial_state(), [[0, 300], [900, 300]])["state"]
        state = attempt_profile_cut(state, [[450, 0], [450, 300]], inherit="right")["state"]
        self.assert_valid(state)
        result = attempt_profile_cut(state, [[300, 300], [300, 600]],
                                     inherit="right", synchronize=True)
        self.assertEqual(result["status"], "blocked_sync_required")
        self.assertIs(result["state"], state)
        self.assertEqual(result["event"]["diagnostic_new_name"], 5)
        self.assertTrue(result["event"]["sync_scope_reason"])

    def test_valid_cycle_geometry_is_not_misidentified_as_a_strip(self):
        """Four quadrants form a side-cycle, not the required anchored chain."""
        state = RectState(900, 600,
                          (RectSide("tl", (0, 0, 450, 300), 4),
                           RectSide("tr", (450, 0, 900, 300), 3),
                           RectSide("bl", (0, 300, 450, 600), 2),
                           RectSide("br", (450, 300, 900, 600), 4)),
                          (((450, 0), (450, 600)), ((0, 300), (900, 300))))
        self.assert_valid(state)
        result = attempt_profile_cut(state, [[225, 0], [225, 300]],
                                     inherit="right", synchronize=True)
        self.assertEqual(result["status"], "blocked_sync_required")
        self.assertIs(result["state"], state)
        self.assertEqual(result["event"]["diagnostic_new_name"], 5)
        self.assertTrue(result["event"]["sync_scope_reason"])

    def test_geometrically_unsupported_attempt_is_not_a_sync_failure(self):
        """A diagonal, dangling cut, or unsupported old junction changes nothing."""
        state = self.user_state()
        for points in ([[100, 200], [200, 600]], [[450, 200], [450, 400]],
                       [[0, 400], [900, 400]], [[300, 200], [300, 600]],
                       [[0, 0], [100, 0], [0, 0]]):
            with self.subTest(points=points):
                result = attempt_profile_cut(state, points, synchronize=True)
                self.assertEqual(result["status"], "outside_scope")
                self.assertIs(result["state"], state)


if __name__ == "__main__":
    unittest.main()

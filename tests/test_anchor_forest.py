"""Regression and independent structural checks for the anchor-forest extension.

Saved certificates are comparison targets ONLY: production receives the old
state, requested cut and inheritance direction, never a certificate assignment.
Abstract cycle/star fixtures below test recognition, not claimed plane maps.
"""

from copy import deepcopy
from itertools import combinations
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from fourcolor.anchor_forest import attempt_forest_cut, recognize_anchor_paths
from fourcolor.inherited_names import RectSide, RectState, initial_state
from fourcolor.retained_profiles import attempt_profile_cut


ROOT = Path(__file__).resolve().parents[1]


def unpack_state(payload):
    """Restore only an input state's immutable rectangle/history records."""
    return RectState(payload["width"], payload["height"],
                     tuple(RectSide(side["id"], tuple(side["bounds"]), side["symbol"])
                           for side in payload["sides"]),
                     tuple(tuple(tuple(point) for point in cut) for cut in payload["cuts"]))


def geometry_names(state):
    """Compare physical bounds and names, rather than equating names with IDs."""
    return sorted((side.bounds, side.symbol) for side in state.sides)


def rectangle_adjacency(state):
    """Derive all positive-length contacts independently of production helpers."""
    adjacency = {"outside": set(), **{side.id: set() for side in state.sides}}

    def connect(first, second):
        """Store one undirected genuine separator."""
        adjacency[first].add(second)
        adjacency[second].add(first)

    for side in state.sides:
        x0, y0, x1, y1 = side.bounds
        if x0 == 0 or y0 == 0 or x1 == state.width or y1 == state.height:
            connect("outside", side.id)
    for first, second in combinations(state.sides, 2):
        x0, y0, x1, y1 = first.bounds
        u0, v0, u1, v1 = second.bounds
        vertical = (x1 == u0 or u1 == x0) and min(y1, v1) > max(y0, v0)
        horizontal = (y1 == v0 or v1 == y0) and min(x1, u1) > max(x0, u0)
        if vertical or horizontal:
            connect(first.id, second.id)
    return adjacency


def joined_graph(vertices, residual_edges):
    """Build an abstract K2-joined constraint fixture, not drawing geometry."""
    adjacency = {key: set() for key in ["outside", "anchor", *vertices]}
    for first, second in [("outside", "anchor"),
                          *(("outside", key) for key in vertices),
                          *(("anchor", key) for key in vertices), *residual_edges]:
        adjacency[first].add(second)
        adjacency[second].add(first)
    return adjacency


class AnchorForestTests(unittest.TestCase):
    """No output writes, certificate-fed production calls, or color search."""

    @classmethod
    def setUpClass(cls):
        """Read the preserved one-step audit, including its complete cohort."""
        report = json.loads((ROOT / "outputs/retained-blocks-2026-09-18.json").read_text(encoding="utf-8"))
        cls.records = report["records"]
        cls.certified = [record for record in cls.records if record["certificate"] is not None]
        cls.unqualified = [record for record in cls.records if record["certificate"] is None]

    def assert_named_geometry(self, state):
        """Independently check coverage, pairwise nonoverlap and every inequality."""
        area = 0
        for side in state.sides:
            x0, y0, x1, y1 = side.bounds
            self.assertTrue(0 <= x0 < x1 <= state.width)
            self.assertTrue(0 <= y0 < y1 <= state.height)
            self.assertIs(type(side.symbol), int)
            self.assertTrue(1 <= side.symbol <= 4)
            area += (x1 - x0) * (y1 - y0)
        self.assertAlmostEqual(area, state.width * state.height)
        for first, second in combinations(state.sides, 2):
            x0, y0, x1, y1 = first.bounds
            u0, v0, u1, v1 = second.bounds
            self.assertFalse(min(x1, u1) > max(x0, u0) and min(y1, v1) > max(y0, v0))
        symbols = {"outside": 1, **{side.id: side.symbol for side in state.sides}}
        self.assertEqual(len(symbols), len(state.sides) + 1)
        for key, neighbors in rectangle_adjacency(state).items():
            for other in neighbors:
                self.assertNotEqual(symbols[key], symbols[other])

    def assert_profiles(self, state, profiles):
        """Sample all oriented physical shores, including renamed old mothers."""
        expected_mothers = {"frame"} | {f"cut-{index + 1}" for index in range(len(state.cuts))}
        self.assertEqual(set(profiles), expected_mothers)
        delta = min(min(side.bounds[2] - side.bounds[0], side.bounds[3] - side.bounds[1])
                    for side in state.sides) / 1000

        def sample(x, y):
            """Resolve the actual interior identity before reading its name."""
            if x < 0 or y < 0 or x > state.width or y > state.height:
                return 1
            found = [side.symbol for side in state.sides
                     if side.bounds[0] < x < side.bounds[2] and side.bounds[1] < y < side.bounds[3]]
            self.assertEqual(len(found), 1)
            return found[0]

        for mother, spans in profiles.items():
            total = 0
            for span in spans:
                (x0, y0), (x1, y1) = span["segment"]
                dx, dy = x1 - x0, y1 - y0
                distance = abs(dx) + abs(dy)
                self.assertGreater(distance, 0)
                total += distance
                midx, midy = (x0 + x1) / 2, (y0 + y1) / 2
                nx, ny = dy / distance, -dx / distance
                expected = (sample(midx + delta * nx, midy + delta * ny),
                            sample(midx - delta * nx, midy - delta * ny))
                self.assertEqual(tuple(span["pair"]), expected)
                self.assertEqual(tuple(span["type"]), tuple(sorted(expected)))
            if mother == "frame":
                self.assertAlmostEqual(total, 2 * (state.width + state.height))
            else:
                first, last = state.cuts[int(mother.split("-")[1]) - 1]
                self.assertAlmostEqual(total, abs(last[0] - first[0]) + abs(last[1] - first[1]))
                self.assertEqual(tuple(spans[0]["segment"][0]), first)
                self.assertEqual(tuple(spans[-1]["segment"][1]), last)

    def test_all_eighty_five_saved_certificates_are_reproduced_without_feeding_colors(self):
        """Match names, anchors and old-name changes for every prior certificate."""
        self.assertEqual(len(self.records), 360)
        self.assertEqual(len(self.certified), 85)
        total_changed, changed_inherit, multiple_paths = 0, 0, 0
        for record in self.certified:
            with self.subTest(key=record["key"]):
                old = unpack_state(record["last_valid_state"])
                snapshot = deepcopy(old)
                # Deliberately pass no fields from record['certificate'] here.
                result = attempt_forest_cut(old, record["cut"], record["requested_inherit"])
                certificate = record["certificate"]
                event = result["event"]
                self.assertEqual(result["status"], "split")
                self.assertEqual(event["method"], "verified_anchor_forest_sync")
                self.assertEqual(geometry_names(result["state"]),
                                 geometry_names(unpack_state(certificate["state"])))
                self.assertEqual(event["anchors"], certificate["anchors"])
                self.assertEqual(event["paths"], certificate["paths"])
                self.assertEqual(event["remaining_names"], certificate["remaining_names"])
                self.assertEqual(event["symbols_by_side"], certificate["symbols_by_side"])
                self.assertEqual(event["actual_inherit"], certificate["actual_inherit"])
                self.assertEqual(event["changed_old_sides"], certificate["changed_unsplit_old_sides"])
                self.assertFalse(event["minimum_change_claim"])
                self.assertEqual(event["new_adjacency"],
                                 {key: sorted(neighbors)
                                  for key, neighbors in rectangle_adjacency(result["state"]).items()})
                self.assertEqual(event["old_adjacency"],
                                 {key: sorted(neighbors) for key, neighbors in rectangle_adjacency(old).items()})
                self.assertEqual(result["state"].cuts[:-1], old.cuts)
                self.assertEqual(old, snapshot)
                self.assert_named_geometry(result["state"])
                self.assert_profiles(old, event["line_profiles_before"])
                self.assert_profiles(result["state"], event["line_profiles_after"])
                total_changed += len(event["changed_old_sides"])
                changed_inherit += event["actual_inherit"] != record["requested_inherit"]
                multiple_paths += len(event["paths"]) > 1
        self.assertEqual(total_changed, 81)
        self.assertEqual(changed_inherit, 28)
        self.assertEqual(multiple_paths, 12)

    def test_all_unqualified_records_remain_blocked_and_preserve_the_input(self):
        """Recognition failure is preserved, not hidden by an arbitrary restart."""
        self.assertEqual(len(self.unqualified), 275)
        for record in self.unqualified:
            with self.subTest(key=record["key"]):
                old = unpack_state(record["last_valid_state"])
                snapshot = deepcopy(old)
                result = attempt_forest_cut(old, record["cut"], record["requested_inherit"])
                self.assertEqual(result["status"], "blocked_sync_required")
                self.assertIs(result["state"], old)
                self.assertTrue(result["event"]["forest_attempted"])
                self.assertTrue(result["event"]["forest_scope_reason"])
                self.assertEqual(result["event"]["candidate_anchors"], [])
                self.assertEqual(old, snapshot)

    def test_new_success_can_be_used_as_a_real_next_cut_state(self):
        """Feed only the produced state into a subsequent geometric operation."""
        record = next(row for row in self.certified if row["key"] == "baseline/20260909/left/3")
        result = attempt_forest_cut(unpack_state(record["last_valid_state"]),
                                    record["cut"], record["requested_inherit"])
        state = result["state"]
        snapshot = deepcopy(state)
        following = attempt_forest_cut(state, [[0, 400], [564, 400]], inherit="left")
        self.assertEqual(following["status"], "split")
        self.assertEqual(len(following["state"].cuts), len(state.cuts) + 1)
        self.assertEqual(following["state"].cuts[-1], ((0, 400), (564, 400)))
        self.assert_named_geometry(following["state"])
        self.assert_profiles(following["state"], following["event"]["line_profiles_after"])
        self.assertEqual(state, snapshot)

    def test_existing_direct_strip_and_unsupported_results_are_unchanged(self):
        """The extension is a fallback, not a replacement for existing successes."""
        def assert_unchanged(extended, baseline):
            """Allow the new diagnostic flag, while requiring every old field."""
            self.assertIs(extended["event"]["forest_attempted"], False)
            comparison = {**extended, "event": {**extended["event"]}}
            comparison["event"].pop("forest_attempted")
            self.assertEqual(comparison, baseline)

        state = initial_state()
        steps = [([[0, 200], [900, 200]], "left"),
                 ([[300, 200], [300, 600]], "right"),
                 ([[600, 200], [600, 600]], "right"),
                 ([[450, 200], [450, 600]], "right")]
        methods = []
        for points, inherit in steps:
            baseline = attempt_profile_cut(state, points, inherit=inherit, synchronize=True)
            extended = attempt_forest_cut(state, points, inherit=inherit)
            assert_unchanged(extended, baseline)
            self.assertEqual(extended["status"], "split")
            methods.append(extended["event"]["method"])
            state = extended["state"]
        self.assertEqual(methods, ["complete_boundary_mex"] * 3 + ["verified_strip_sync"])
        for points in ([[100, 200], [200, 600]], [[100, 200], [100, 400]],
                       [[0, 400], [900, 400]], [[0, 0], [100, 0], [0, 0]]):
            baseline = attempt_profile_cut(state, points, synchronize=True)
            extended = attempt_forest_cut(state, points)
            assert_unchanged(extended, baseline)
            self.assertEqual(extended["status"], "outside_scope")
            self.assertIs(extended["state"], state)

    def test_canonical_path_endpoints_and_disconnected_components(self):
        """Isolated vertices and multiple paths use deterministic local phases."""
        graph = joined_graph(["z", "middle", "a", "isolated"], [("z", "middle"), ("middle", "a")])
        self.assertEqual(recognize_anchor_paths(graph, "anchor"),
                         [["a", "middle", "z"], ["isolated"]])
        reversed_graph = {key: set(reversed(sorted(value))) for key, value in reversed(list(graph.items()))}
        self.assertEqual(recognize_anchor_paths(reversed_graph, "anchor"),
                         [["a", "middle", "z"], ["isolated"]])

    def test_cycles_branches_and_missing_anchor_contacts_are_rejected(self):
        """Reject even cycles too: the implemented theorem requires a forest."""
        cases = {
            "odd_cycle": joined_graph(["a", "b", "c"], [("a", "b"), ("b", "c"), ("c", "a")]),
            "even_cycle": joined_graph(["a", "b", "c", "d"],
                                        [("a", "b"), ("b", "c"), ("c", "d"), ("d", "a")]),
            "degree_three": joined_graph(["a", "b", "c", "d"], [("a", "b"), ("a", "c"), ("a", "d")]),
            "path_plus_cycle": joined_graph(["a", "b", "c", "d", "e"],
                                             [("a", "b"), ("c", "d"), ("d", "e"), ("e", "c")]),
        }
        for missing_from in ("outside", "anchor"):
            graph = joined_graph(["a", "b"], [("a", "b")])
            graph[missing_from].remove("b")
            graph["b"].remove(missing_from)
            cases["missing_" + missing_from] = graph
        for name, graph in cases.items():
            with self.subTest(graph=name):
                self.assertIsNone(recognize_anchor_paths(graph, "anchor"))
        for unusable in ("outside", "not-a-vertex", None):
            self.assertIsNone(recognize_anchor_paths(joined_graph(["a"], []), unusable))

    def test_invalid_adjacency_schema_is_not_silently_repaired(self):
        """Malformed graphs differ from well-formed graphs outside the theorem."""
        valid = joined_graph(["a", "b"], [("a", "b")])
        asymmetric = deepcopy(valid)
        asymmetric["a"].remove("b")
        self_loop = deepcopy(valid)
        self_loop["a"].add("a")
        unknown = deepcopy(valid)
        unknown["a"].add("not-a-vertex")
        for graph in (asymmetric, self_loop, unknown, {}, None, {"outside": None}):
            with self.subTest(graph=graph):
                with self.assertRaises(ValueError):
                    recognize_anchor_paths(graph, "anchor")

    def test_multiple_candidates_are_not_resolved_by_hidden_selection(self):
        """Fault-inject recognition ambiguity solely to exercise refusal logic."""
        record = self.certified[0]
        old = unpack_state(record["last_valid_state"])
        # This mocked structural response is NOT a claim about the physical map.
        # There is deliberately no invented certificate or coloring fallback.
        with patch("fourcolor.anchor_forest.recognize_anchor_paths", return_value=[["synthetic"]]):
            result = attempt_forest_cut(old, record["cut"], record["requested_inherit"])
        self.assertEqual(result["status"], "blocked_sync_required")
        self.assertIs(result["state"], old)
        self.assertGreater(len(result["event"]["candidate_anchors"]), 1)
        self.assertTrue(result["event"]["forest_scope_reason"])

    def test_forest_replay_is_deterministic_and_does_not_alias_input_points(self):
        """Repeated identical input gives identical evidence and immutable state."""
        record = self.certified[0]
        old = unpack_state(record["last_valid_state"])
        points = deepcopy(record["cut"])
        before = deepcopy(points)
        first = attempt_forest_cut(old, points, record["requested_inherit"])
        second = attempt_forest_cut(old, deepcopy(points), record["requested_inherit"])
        self.assertEqual(first, second)
        self.assertEqual(points, before)
        points[0][0] += 1
        self.assertEqual(first["state"].cuts[-1], tuple(tuple(point) for point in before))


if __name__ == "__main__":
    unittest.main()

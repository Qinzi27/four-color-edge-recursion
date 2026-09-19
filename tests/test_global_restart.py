"""Geometry-only restart regressions and independent current-priority replay.

These examples do not establish universal four-name completion. In particular,
the explicit seed908 witness is a manually supplied assignment check, distinct
from results automatically obtained by any restart policy.
"""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import unittest

from fourcolor.global_restart import (
    POLICIES, current_priorities, current_segments, restart_line_names,
)
from fourcolor.whole_lines import build_whole_lines, propagate_candidates
from scripts.validate_weighted_lines import independent_check


ROOT = Path(__file__).resolve().parents[1]
SEED_908_CUTS = (
    ((0, 212), (900, 212)), ((0, 439), (900, 439)),
    ((0, 489), (900, 489)), ((308, 0), (308, 212)),
    ((688, 0), (688, 212)), ((423, 489), (423, 600)),
    ((391, 439), (391, 489)),
)


def drawing(cuts):
    """Build an uncolored input document from exact directed line segments."""
    return {"frame": {"width": 900, "height": 600},
            "strokes": [{"a": first, "b": second} for first, second in cuts]}


def shore_signature(model, domains):
    """Compare geometry-position names, ignoring raw face IDs and degree2 splits."""
    result = []
    for mother in model.lines:
        spans = []
        for span in mother["spans"]:
            pair = (tuple(domains[span["left_side"]]), tuple(domains[span["right_side"]]))
            start, end = round(span["t0"], 10), round(span["t1"], 10)
            if spans and spans[-1][2] == pair and spans[-1][1] == start:
                spans[-1] = (spans[-1][0], end, pair)
            else:
                spans.append((start, end, pair))
        result.append((mother["id"], tuple(spans)))
    return tuple(result)


class GlobalRestartTests(unittest.TestCase):
    """Check discarded old names, current ports, dynamic priorities and witnesses."""

    @classmethod
    def setUpClass(cls):
        """Export all fixtures in one geometry-only Node batch without coloring."""
        horizontal = [((0, 300), (900, 300))]
        grid = [((x, 0), (x, 600)) for x in (300, 600)]
        grid += [((0, y), (900, y)) for y in (200, 400)]
        cuts = {
            "blank": [], "horizontal": horizontal,
            "t-junction": horizontal + [((450, 300), (450, 600))],
            "x-junction": horizontal + [((450, 0), (450, 600))],
            "multi-endpoint": horizontal + [((0, 0), (900, 300))],
            "degree-two": [((0, 300), (333, 300)), ((333, 300), (900, 300))],
            "grid": grid,
            "grid-reordered": list(reversed(grid)),
            "grid-reversed": [(second, first) for first, second in grid],
            "seed908-seven": SEED_908_CUTS,
            "bridge": [((0, 300), (350, 300))],
            "island": [((300, 200), (600, 200)), ((600, 200), (600, 400)),
                       ((600, 400), (300, 400)), ((300, 400), (300, 200))],
        }
        cases = [{"key": key, "document": drawing(value), "includeFacePoints": True}
                 for key, value in cuts.items()]
        contaminated = deepcopy(drawing(grid))
        contaminated.update({"colors": [99, 99], "names": {"outside": 99},
                             "fixedColors": {"0": 99}, "old_colors": [99]})
        for stroke in contaminated["strokes"]:
            stroke["old_name"] = [99, 99]
        cases.append({"key": "grid-old-names", "document": contaminated,
                      "includeFacePoints": True})
        process = subprocess.run(["node", "scripts/restart-geometry.mjs"], cwd=ROOT,
                                 input=json.dumps({"cases": cases}), capture_output=True,
                                 text=True, encoding="utf-8", check=True)
        exported = json.loads(process.stdout)
        if exported["coloring_performed"]:
            raise AssertionError("the geometry export unexpectedly selected colors")
        if any(row["status"] != "geometry_ok" for row in exported["results"]):
            raise AssertionError("a declared geometry fixture did not export")
        cls.geometry = {row["key"]: row["geometry"] for row in exported["results"]}
        cls.models = {key: build_whole_lines(value) for key, value in cls.geometry.items()}

    def test_previous_document_and_geometry_names_are_not_read(self):
        """Neither the geometry bridge nor the rule imports former color arrays."""
        self.assertEqual(self.geometry["grid-old-names"], self.geometry["grid"])
        contaminated = deepcopy(self.geometry["grid"])
        contaminated.update({"colors": [99], "old_colors": {"outside": 99},
                             "anchors_by_dart": {0: [99]}})
        frozen = deepcopy(contaminated)
        for policy in POLICIES:
            with self.subTest(policy=policy):
                expected = restart_line_names(self.geometry["grid"], policy)
                actual = restart_line_names(contaminated, policy)
                self.assertEqual(actual, expected)
                self.assertFalse(actual["old_colors_read"])
                self.assertIsNone(actual["local_budget"])
        self.assertEqual(contaminated, frozen)

    def test_every_restart_has_only_the_two_fresh_frame_anchors(self):
        """A later map starts from outside1 and one inside2, not earlier results."""
        for key in ("horizontal", "t-junction", "grid", "seed908-seven"):
            with self.subTest(key=key):
                result = restart_line_names(self.geometry[key], "shared-mother")
                anchors = result["initial_anchors_by_dart"]
                self.assertEqual(len(anchors), 2)
                self.assertEqual(sorted(anchors.values()), [[1], [2]])
                first, second = anchors
                self.assertEqual(first ^ 1, second)
                self.assertEqual(result["backtracks"], 0)

    def test_a_new_t_recomputes_segments_but_preserves_the_whole_mother(self):
        """The previous two-frame-port chord becomes two one-frame-port units."""
        mother = "L:0,300>900,300"
        before = [unit for unit in current_segments(self.models["horizontal"])
                  if unit["mother"] == mother]
        after = [unit for unit in current_segments(self.models["t-junction"])
                 if unit["mother"] == mother]
        self.assertEqual(len(before), 1)
        self.assertTrue(before[0]["same_single_mother"])
        self.assertEqual(before[0]["endpoint_mothers"], [["frame"], ["frame"]])
        self.assertEqual(len(after), 2)
        self.assertTrue(all(not unit["same_single_mother"] for unit in after))
        self.assertEqual([unit["frame_endpoint_count"] for unit in after], [1, 1])

    def test_x_junction_keeps_two_mothers_and_four_current_units(self):
        """A crossing splits intervals, not the underlying horizontal/vertical IDs."""
        model = self.models["x-junction"]
        self.assertEqual({mother["id"] for mother in model.lines},
                         {"frame", "L:0,300>900,300", "L:450,0>450,600"})
        internal = [unit for unit in current_segments(model) if unit["mother"] != "frame"]
        self.assertEqual(len(internal), 4)
        self.assertTrue(all(len(unit["endpoint_mothers"][0]) == 1
                            and len(unit["endpoint_mothers"][1]) == 1 for unit in internal))

    def test_degree_two_subdivision_neither_adds_a_unit_nor_adds_weight(self):
        """Input stroke segmentation alone is not a new mother attachment."""
        first, second = self.models["horizontal"], self.models["degree-two"]
        for key, model in (("horizontal", first), ("degree-two", second)):
            internal = [unit for unit in current_segments(model) if unit["mother"] != "frame"]
            self.assertEqual(len(internal), 1)
            self.assertEqual(len(internal[0]["occurrences"]), 2)
            domains = [[1] if side == self.geometry[key]["outerFace"] else [2, 3, 4]
                       for side in range(len(model.plane_map.faces))]
            row = next(row for row in current_priorities(internal, domains)
                       if row["mother"] == "L:0,300>900,300")
            self.assertEqual(row["constraint_weight"], 2)
        for policy in POLICIES:
            one = restart_line_names(self.geometry["horizontal"], policy)
            two = restart_line_names(self.geometry["degree-two"], policy)
            self.assertEqual(shore_signature(first, one["domains"]),
                             shore_signature(second, two["domains"]))

    def test_multiple_mothers_at_one_endpoint_do_not_qualify_as_unique(self):
        """A frame endpoint also touched by a diagonal is not 'only one mother'."""
        unit = next(unit for unit in current_segments(self.models["multi-endpoint"])
                    if unit["mother"] == "L:0,300>900,300")
        self.assertEqual(unit["endpoint_mothers"][0], ["frame"])
        self.assertEqual(len(unit["endpoint_mothers"][1]), 2)
        self.assertIn("frame", unit["endpoint_mothers"][1])
        self.assertFalse(unit["same_single_mother"])

    def test_constraint_weight_counts_distinct_unresolved_shores_not_edges(self):
        """The current unit builder must retain unique side identities per unit."""
        model = self.models["grid"]
        units = current_segments(model)
        domains = [[1] if side == self.geometry["grid"]["outerFace"] else [2, 3, 4]
                   for side in range(len(model.plane_map.faces))]
        rows = {row["unit"]: row for row in current_priorities(units, domains)}
        for unit in units:
            identities = [side for side, _ in unit["occurrences"]]
            self.assertEqual(len(identities), len(set(identities)))
            unknown = {side for side in identities if len(domains[side]) > 1}
            if unknown:
                self.assertEqual(rows[unit["id"]]["constraint_weight"], len(unknown))

    def test_each_segment_commitment_is_followed_by_fresh_priority_selection(self):
        """Replay each priority without calling the production weight function."""
        geometry, model = self.geometry["grid"], self.models["grid"]
        for policy in ("segment-constraints", "shared-mother"):
            result = restart_line_names(geometry, policy)
            units = result["units"]
            anchors = deepcopy(result["initial_anchors_by_dart"])
            for step in result["trace"]:
                propagated = propagate_candidates(model, anchors)
                domains = propagated["domains"]
                available = []
                for unit in units:
                    unknown = {side for side, _ in unit["occurrences"] if len(domains[side]) > 1}
                    if not unknown:
                        continue
                    score = (int(policy == "shared-mother" and unit["same_single_mother"]),
                             sum(4 - len(domains[side]) for side in unknown))
                    available.append((score, unit))
                highest = max(score for score, _ in available)
                tied = sorted((unit for score, unit in available if score == highest),
                              key=lambda unit: (unit["mother"], unit["t0"]))
                selected = tied[0]
                self.assertEqual(step["unit"], selected["id"])
                self.assertEqual(tuple(step["priority"]), highest)
                self.assertEqual(step["tied_units"], [unit["id"] for unit in tied])
                side, dart = next((side, dart) for side, dart in selected["occurrences"]
                                  if len(domains[side]) > 1)
                used = {domain[0] for domain in domains if len(domain) == 1}
                self.assertEqual((step["side"], step["dart"]), (side, dart))
                self.assertEqual(step["domain"], domains[side])
                self.assertEqual(step["symbol"], min(domains[side], key=lambda name: (name not in used, name)))
                anchors[dart] = [step["symbol"]]
            self.assertEqual(anchors, result["anchors_by_dart"])
            self.assertEqual(len(result["trace"]), result["choices"])
            self.assertTrue(independent_check(geometry, result))

    def test_real_bridge_has_equal_internal_shores_and_no_inequality(self):
        """A dangling line does not split the inside or force it to outside1."""
        geometry, model = self.geometry["bridge"], self.models["bridge"]
        self.assertTrue(geometry["real_bridge_edge_ids"])
        for policy in POLICIES:
            result = restart_line_names(geometry, policy)
            self.assertEqual(result["status"], "solved")
            self.assertEqual(len(result["colors"]), 2)
            for edge in geometry["real_bridge_edge_ids"]:
                left, right = model.plane_map.shores(edge)
                self.assertEqual(left, right)
                self.assertNotEqual(left, geometry["outerFace"])
                self.assertEqual(result["colors"][left], 2)

    def test_virtual_connectors_are_metadata_and_never_become_mothers(self):
        """An island's artificial connector contributes neither ports nor names."""
        geometry, model = self.geometry["island"], self.models["island"]
        self.assertTrue(geometry["virtual_bridge_edge_ids"])
        self.assertEqual(set(model.virtual_edges), set(geometry["virtual_bridge_edge_ids"]))
        for edge in model.virtual_edges:
            self.assertNotIn(edge, model.edge_owner)
            self.assertEqual(*model.plane_map.shores(edge))
        result = restart_line_names(geometry)
        self.assertEqual(result["status"], "solved")
        self.assertTrue(independent_check(geometry, result))

    def test_internal_one_is_allowed_while_external_identity_stays_one(self):
        """A fully surrounded grid side really receives1 in each declared run."""
        geometry, model = self.geometry["grid"], self.models["grid"]
        for policy in POLICIES:
            result = restart_line_names(geometry, policy)
            self.assertEqual(result["status"], "solved")
            exterior = geometry["outerFace"]
            self.assertEqual(result["colors"][exterior], 1)
            reused = {side for side, name in enumerate(result["colors"]) if name == 1 and side != exterior}
            self.assertTrue(reused)
            for edge in range(len(model.plane_map.edges)):
                left, right = model.plane_map.shores(edge)
                if left != right:
                    self.assertNotEqual(result["colors"][left], result["colors"][right])

    def test_reordered_or_reversed_strokes_preserve_geometric_side_names(self):
        """Raw topology IDs may change; the oriented geometric profile must not."""
        for policy in POLICIES:
            baseline = restart_line_names(self.geometry["grid"], policy)
            expected = shore_signature(self.models["grid"], baseline["domains"])
            for key in ("grid-reordered", "grid-reversed"):
                with self.subTest(policy=policy, variant=key):
                    result = restart_line_names(self.geometry[key], policy)
                    self.assertEqual(result["status"], baseline["status"])
                    self.assertEqual(shore_signature(self.models[key], result["domains"]), expected)

    def test_seed908_seventh_cut_completes_under_all_three_predeclared_restarts(self):
        """The earlier local-extension stop is not a failure of full restarts."""
        geometry = self.geometry["seed908-seven"]
        for policy in POLICIES:
            with self.subTest(policy=policy):
                result = restart_line_names(geometry, policy)
                self.assertEqual(result["status"], "solved")
                self.assertTrue(independent_check(geometry, result))
                self.assertEqual(set(result["colors"]), {1, 2, 3, 4})

    def test_seed908_manual_simultaneous_witness_is_separate_from_policy_output(self):
        """Verify the supplied bottom4/2-to-2/3 witness without a naming solver."""
        geometry, model = self.geometry["seed908-seven"], self.models["seed908-seven"]
        supplied = {
            (0, 0, 308, 212): 4, (308, 0, 688, 212): 3, (688, 0, 900, 212): 4,
            (0, 212, 900, 439): 2, (0, 439, 391, 489): 3, (391, 439, 900, 489): 4,
            (0, 489, 423, 600): 2, (423, 489, 900, 600): 3,
        }
        names = []
        for side, points in enumerate(geometry["face_points"]):
            if side == geometry["outerFace"]:
                names.append(1)
                continue
            bounds = (min(p[0] for p in points), min(p[1] for p in points),
                      max(p[0] for p in points), max(p[1] for p in points))
            names.append(supplied[bounds])
        self.assertTrue(model.plane_map.check_coloring([name - 1 for name in names]))
        result = {"status": "solved", "domains": [[name] for name in names],
                  "anchors_by_dart": {face[0]: [names[side]] for side, face in enumerate(model.plane_map.faces)}}
        self.assertTrue(independent_check(geometry, result))

    def test_unknown_policy_is_rejected_and_blank_geometry_is_a_valid_restart(self):
        """Invalid scheduling names must not silently fall back to another rule."""
        with self.assertRaises(ValueError):
            restart_line_names(self.geometry["blank"], "unknown")
        for policy in POLICIES:
            result = restart_line_names(self.geometry["blank"], policy)
            self.assertEqual(result["status"], "solved")
            self.assertEqual(result["choices"], 0)
            self.assertTrue(independent_check(self.geometry["blank"], result))


if __name__ == "__main__":
    unittest.main()

"""The provisional peer group removes a scope gate without inventing levels.

Small completed maps and exact six-case v1 preservation are finite tests. An
unranked peer is a deterministic scheduling convention, not a proved equal
generation or a guarantee that every greedy continuation can be completed.
"""

from copy import deepcopy
from pathlib import Path
import unittest

from fourcolor.level_sides import level_metadata, restart_level_side_names
from fourcolor.level_sides_peer import (
    POLICY, peer_mother_order, restart_level_peer_names,
)
from fourcolor.relation_frontier import propagate_frontier_relations
from fourcolor.whole_lines import build_whole_lines
from scripts.validate_frontier_restart import json_value, read_json
from scripts.validate_global_restart import export_geometries
from scripts.validate_level_sides_peer import verify_run
from tests.test_frontier_restart import side_profile
from tests import test_level_sides as v1_fixtures


ROOT = Path(__file__).resolve().parents[1]


class LevelSidePeerTests(unittest.TestCase):
    """Keep valid naming separate from rooted-support or peer-group metadata."""

    @classmethod
    def setUpClass(cls):
        """Reuse tiny geometry-only fixtures and add a bent cut and triangle."""
        v1_fixtures.LevelSideTests.setUpClass()
        cls.geometry = dict(v1_fixtures.LevelSideTests.geometry)
        triangle = [((430, 210), (650, 210)), ((650, 210), (540, 430)),
                    ((540, 430), (430, 210))]
        polyline = [((0, 300), (240, 100)), ((240, 100), (450, 200)),
                    ((450, 200), (660, 500)), ((660, 500), (900, 300))]
        cuts = {"triangle": triangle, "polyline": polyline,
                "polyline-reversed": [(end, start) for start, end in reversed(polyline)],
                "mixed": [((200, 0), (200, 600))] + triangle}
        cases = [{"key": key, "document": {"strokes": [
            {"a": start, "b": end} for start, end in strokes]}} for key, strokes in cuts.items()]
        cls.geometry.update({row["key"]: row["geometry"] for row in export_geometries(cases)})
        cls.models = {key: build_whole_lines(value) for key, value in cls.geometry.items()}

    def assert_legal_result(self, geometry, result):
        """Use the existing independent raw-edge and anchor checks, not a solver."""
        v1_fixtures.LevelSideTests.assert_legal_result(self, geometry, result)
        self.assertEqual(result["policy"], POLICY)
        self.assertEqual(result["unranked_mothers"], sorted(
            name for name, row in result["levels"].items() if row["level"] is None))

    def assert_same_rooted_behavior(self, earlier, candidate):
        """Only policy text and explicit selection-group annotations may differ."""
        for key, value in earlier.items():
            if key in ("policy", "scope", "trace"):
                continue
            self.assertEqual(json_value(candidate[key]), json_value(value), key)
        stripped = [{key: value for key, value in step.items() if key != "selection_group"}
                    for step in candidate["trace"]]
        self.assertEqual(json_value(stripped), json_value(earlier["trace"]))
        self.assertTrue(all(step["selection_group"] == "rooted" for step in candidate["trace"]))

    def test_peer_bucket_never_fabricates_an_equal_mathematical_level(self):
        """None remains unknown even though unranked entries share a sort bucket."""
        rooted = {"level": 5, "endpoints": [[100, 100], [500, 100]]}
        unknown_a = {"level": None, "endpoints": [[100, 50], [500, 50]]}
        unknown_b = {"level": None, "endpoints": [[100, 150], [500, 150]]}
        original = deepcopy([rooted, unknown_a, unknown_b])
        self.assertLess(peer_mother_order(rooted), peer_mother_order(unknown_a))
        self.assertLess(peer_mother_order(unknown_a), peer_mother_order(unknown_b))
        self.assertEqual([rooted, unknown_a, unknown_b], original)

    def test_rooted_small_fixtures_preserve_every_v1_decision_and_filter(self):
        """The new group has no effect when all mothers already have levels."""
        for key in ("blank", "horizontal", "T", "X", "siblings", "grid"):
            with self.subTest(key=key):
                earlier = restart_level_side_names(self.geometry[key])
                candidate = restart_level_peer_names(self.geometry[key])
                self.assert_legal_result(self.geometry[key], candidate)
                self.assert_same_rooted_behavior(earlier, candidate)

    def test_dangling_stroke_finishes_without_color_choices_or_self_inequality(self):
        """An unranked bridge no longer vetoes an already completely named map."""
        geometry = self.geometry["dangling"]
        self.assertEqual(restart_level_side_names(geometry)["status"], "outside_scope")
        candidate = restart_level_peer_names(geometry)
        self.assert_legal_result(geometry, candidate)
        self.assertTrue(candidate["unranked_mothers"])
        self.assertEqual(candidate["choices"], 0)
        self.assertEqual(candidate["trace"], [])
        self.assertEqual(sorted(candidate["colors"]), [1, 2])
        model = self.models["dangling"]
        real_bridges = [edge for edge in model.edge_owner
                        if model.plane_map.shores(edge)[0] == model.plane_map.shores(edge)[1]]
        self.assertTrue(real_bridges)
        for edge in real_bridges:
            left, right = model.plane_map.shores(edge)
            self.assertEqual(candidate["colors"][left], candidate["colors"][right])

    def test_bent_boundary_to_boundary_cut_is_named_despite_unrooted_straight_pieces(self):
        """A polyline is not silently merged or given made-up generation numbers."""
        geometry = self.geometry["polyline"]
        self.assertEqual(restart_level_side_names(geometry)["status"], "outside_scope")
        candidate = restart_level_peer_names(geometry)
        self.assert_legal_result(geometry, candidate)
        self.assertEqual(len(candidate["unranked_mothers"]), 4)
        self.assertTrue(candidate["trace"])
        self.assertTrue(all(step["level"] is None and step["selection_group"] == "unranked-peer"
                            for step in candidate["trace"]))
        self.assertEqual(candidate["levels"], level_metadata(self.models["polyline"]))

    def test_isolated_closed_polygons_reuse_one_without_a_new_loop_root(self):
        """Existing plane topology handles an island; no new loop algorithm enters."""
        for key in ("island", "triangle"):
            with self.subTest(key=key):
                geometry = self.geometry[key]
                self.assertEqual(restart_level_side_names(geometry)["status"], "outside_scope")
                candidate = restart_level_peer_names(geometry)
                self.assert_legal_result(geometry, candidate)
                self.assertEqual(sorted(candidate["colors"]), [1, 1, 2])
                self.assertTrue(candidate["unranked_mothers"])
                self.assertTrue(any(step["symbol"] == 1 for step in candidate["trace"]))
                self.assertTrue(all(step["selection_group"] == "unranked-peer"
                                    for step in candidate["trace"]))
                model = self.models[key]
                self.assertTrue(model.virtual_edges)
                for edge in model.virtual_edges:
                    self.assertEqual(*model.plane_map.shores(edge))

    def test_mixed_groups_use_known_lines_then_unranked_peers_and_minimum_candidates(self):
        """Replay ordering from active side profiles, including both real groups."""
        geometry, model = self.geometry["mixed"], self.models["mixed"]
        result = restart_level_peer_names(geometry)
        self.assert_legal_result(geometry, result)
        groups = [step["selection_group"] for step in result["trace"]]
        self.assertIn("rooted", groups)
        self.assertIn("unranked-peer", groups)
        self.assertEqual(groups, sorted(groups, key=lambda group: group == "unranked-peer"))
        anchors = deepcopy(result["initial_anchors_by_dart"])
        for step, phase in zip(result["trace"], result["propagation_phases"]):
            filtered = propagate_frontier_relations(model, anchors)
            self.assertEqual(phase["outcome"], filtered)
            self.assertEqual(phase["anchors_by_dart"], anchors)
            domains = filtered["domains"]
            active = []
            for line in model.lines:
                if line["id"] == "frame" or not any(
                        len(domains[span[side]]) > 1 for span in line["spans"]
                        for side in ("left_side", "right_side")):
                    continue
                info = result["levels"][line["id"]]
                points = tuple(sorted((p[1], p[0]) for p in line["endpoints"]))
                level = info["level"]
                active.append(((1, 0, points) if level is None else (0, level, points), line["id"]))
            self.assertEqual(step["mother"], min(active)[1])
            self.assertEqual(step["symbol"], min(domains[step["side"]]))
            self.assertEqual(step["selection_group"], "unranked-peer" if step["level"] is None else "rooted")
            v1_fixtures.LevelSideTests.assert_boundary(self, model, domains, step["side"], step["boundary"])
            anchors[step["dart"]] = [step["symbol"]]
        self.assertEqual(anchors, result["anchors_by_dart"])
        self.assertEqual(len(result["propagation_phases"]), result["choices"] + 1)
        self.assertEqual(result["propagation_phases"][-1]["outcome"],
                         propagate_frontier_relations(model, anchors))

    def test_old_color_or_claimed_level_metadata_is_never_used(self):
        """The new eligibility convention cannot become a hidden old-color oracle."""
        clean = self.geometry["mixed"]
        poisoned = deepcopy(clean)
        poisoned.update({"old_colors": [99], "colors": [99], "levels": {"frame": 999},
                         "selection_group": "rooted", "unranked_mothers": [],
                         "anchors_by_dart": {0: [99]}, "inherited_forbidden": [1, 2, 3, 4]})
        before = deepcopy(poisoned)
        self.assertEqual(restart_level_peer_names(poisoned), restart_level_peer_names(clean))
        self.assertEqual(poisoned, before)

    def test_stroke_reversal_and_repeated_calls_preserve_peer_results(self):
        """Mother identity comes from geometry, not stroke insertion direction."""
        base = restart_level_peer_names(self.geometry["polyline"])
        reverse = restart_level_peer_names(self.geometry["polyline-reversed"])
        self.assert_legal_result(self.geometry["polyline-reversed"], reverse)
        self.assertEqual(base, restart_level_peer_names(self.geometry["polyline"]))
        self.assertEqual(base["levels"], reverse["levels"])
        self.assertEqual(side_profile(self.models["polyline"], base["domains"]),
                         side_profile(self.models["polyline-reversed"], reverse["domains"]))

    def test_the_six_known_cases_keep_all_v1_choices_and_complete_certificates(self):
        """Archived witnesses are compared after running, never passed as inputs."""
        diagnostic = read_json(ROOT / "outputs/level-sides-six-2026-09-19.json.gz")
        self.assertEqual(len(diagnostic["records"]), 6)
        total = 0
        for archived in diagnostic["records"]:
            with self.subTest(key=archived["key"]):
                candidate = restart_level_peer_names(archived["geometry"])
                self.assert_legal_result(archived["geometry"], candidate)
                self.assert_same_rooted_behavior(archived["candidate"], candidate)
                total += candidate["choices"]
        self.assertEqual(total, 64)

    def test_independent_checker_replays_genuine_rooted_and_unranked_certificates(self):
        """A now-admitted drawing still requires the full normal proof replay."""
        for key in ("dangling", "polyline", "triangle", "mixed", "grid"):
            with self.subTest(key=key):
                geometry = self.geometry[key]
                result = restart_level_peer_names(geometry)
                before = deepcopy(result)
                checked = verify_run(geometry, result)
                self.assertTrue(checked["passed"])
                self.assertEqual(checked["claim"], "complete-proper-four-names")
                self.assertTrue(checked["final_legality"]["passed"])
                self.assertEqual(result, before)

    def test_independent_checker_rejects_a_forged_selection_group(self):
        """The display must not relabel an unranked peer as a rooted generation."""
        geometry = self.geometry["mixed"]
        genuine = restart_level_peer_names(geometry)
        for original_group in ("rooted", "unranked-peer"):
            with self.subTest(original_group=original_group):
                forged = deepcopy(genuine)
                decision = next(step for step in forged["trace"]
                                if step["selection_group"] == original_group)
                decision["selection_group"] = "unranked-peer" if original_group == "rooted" else "rooted"
                with self.assertRaises(AssertionError):
                    verify_run(geometry, forged)

    def test_independent_checker_rejects_invented_unknown_levels_or_erased_unknowns(self):
        """Actual unknown ancestry cannot be hidden behind plausible color output."""
        geometry = self.geometry["triangle"]
        genuine = restart_level_peer_names(geometry)
        for corruption in ("global-level", "decision-level", "unranked-list", "outside-scope"):
            with self.subTest(corruption=corruption):
                forged = deepcopy(genuine)
                if corruption == "global-level":
                    forged["levels"][forged["unranked_mothers"][0]]["level"] = 2
                elif corruption == "decision-level":
                    forged["trace"][0]["level"] = 2
                elif corruption == "unranked-list":
                    forged["unranked_mothers"] = []
                else:
                    forged["status"] = "outside_scope"
                with self.assertRaises(AssertionError):
                    verify_run(geometry, forged)


if __name__ == "__main__":
    unittest.main()

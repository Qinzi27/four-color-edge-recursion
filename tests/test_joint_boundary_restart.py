"""Integration checks separating extra information from altered scheduling."""

from copy import deepcopy
import unittest

from fourcolor.joint_boundary import find_boundary_books
from fourcolor.joint_boundary_restart import propagate_joint_boundary, restart_joint_boundary_names
from fourcolor.peer_batches import restart_peer_batch_names
from fourcolor.relation_frontier import propagate_frontier_relations
from fourcolor.whole_lines import build_whole_lines
from tests import test_level_sides_peer as peer_fixtures


class JointBoundaryRestartTests(unittest.TestCase):
    """Finite fixtures certify unchanged ablation behavior, not completeness."""

    @classmethod
    def setUpClass(cls):
        """Load the same independent geometry-only tiny fixtures as older tests."""
        peer_fixtures.LevelSidePeerTests.setUpClass()
        cls.geometries = peer_fixtures.LevelSidePeerTests.geometry

    def test_unary_ablation_preserves_every_old_decision(self):
        """Domain-only AtMost2 adds no pruning after the old fixed point."""
        for name in ("blank", "dangling", "grid", "T", "X", "mixed"):
            with self.subTest(name=name):
                geometry = self.geometries[name]
                old = restart_peer_batch_names(geometry)
                new = restart_joint_boundary_names(geometry, mode="domains")
                for key in ("status", "trace", "domains", "relations", "colors", "initialization"):
                    self.assertEqual(new[key], old[key], key)
                self.assertEqual(new["statistics"].get("domain_values_removed", 0), 0)

    def test_empty_book_cache_is_checked_against_real_geometry(self):
        """Callers cannot suppress or add geometry certificates through caching."""
        geometry = next(g for g in self.geometries.values() if find_boundary_books(build_whole_lines(g)))
        model = build_whole_lines(geometry)
        with self.assertRaises(ValueError):
            propagate_joint_boundary(model, {}, books=[])

    def test_joint_runs_preserve_input_ignore_old_colors_and_satisfy_real_edges(self):
        """Old answers cannot influence the new run; bridges impose no ban."""
        for name in ("blank", "dangling", "grid", "mixed"):
            with self.subTest(name=name):
                geometry = self.geometries[name]
                original = deepcopy(geometry)
                result = restart_joint_boundary_names(geometry)
                self.assertEqual(geometry, original)
                poisoned = {**geometry, "colors": [99], "old_colors": [99]}
                self.assertEqual(result, restart_joint_boundary_names(poisoned))
                self.assertEqual(result["status"], "solved")
                self.assertEqual(result["backtracks"], 0)
                self.assertFalse(result["old_colors_read"])
                model = build_whole_lines(geometry)
                colors = result["colors"]
                for edge in range(len(model.plane_map.edges)):
                    a, b = model.plane_map.shores(edge)
                    if a != b:
                        self.assertNotEqual(colors[a], colors[b])
                for dart, values in result["anchors_by_dart"].items():
                    self.assertIn(colors[model.plane_map.face_of_dart[dart]], values)

    def test_conflicting_anchors_remain_conflict_without_local_branches(self):
        """The stronger filter cannot rescue an inconsistent commitment."""
        model = build_whole_lines(self.geometries["blank"])
        edge = next(e for e in range(len(model.plane_map.edges))
                    if len(set(model.plane_map.shores(e))) == 2)
        anchors = {2 * edge: [1], 2 * edge + 1: [1]}
        old = propagate_frontier_relations(model, anchors)
        new = propagate_joint_boundary(model, anchors)
        self.assertEqual(old["status"], "conflict")
        self.assertEqual(new["status"], "conflict")
        self.assertIsNone(new["phases"][0]["boundary_filter"])

    def test_invalid_mode_rejected_without_a_strategy_fallback(self):
        """Every run identifies which fixed propagation rule it uses."""
        with self.assertRaises(ValueError):
            restart_joint_boundary_names(self.geometries["blank"], mode="auto")


if __name__ == "__main__":
    unittest.main()

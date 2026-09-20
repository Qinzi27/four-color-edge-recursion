"""Audit graph extraction, witnesses, worker isolation and timeout preservation."""

from copy import deepcopy
import subprocess
import unittest
from unittest.mock import patch

from fourcolor.embedding import PlaneMap
from scripts.check_prior_exact_failures import (
    exterior_bfs, graph_from_geometry, run_one, verify_raw_witness,
)


def tiny_geometry():
    """A triangle plus real/virtual dangling edges has exactly two map faces."""
    edges = [(0, 1), (1, 2), (2, 0), (0, 3), (0, 4)]
    rotation = [[0, 5, 6, 8], [1, 2], [3, 4], [7], [9]]
    plane = PlaneMap(tuple((str(a), str(b)) for a, b in edges),
                     {str(v): tuple(row) for v, row in enumerate(rotation)})
    return {"vertices": [[0, 0], [2, 0], [0, 2], [-1, -1], [-2, -1]],
            "edges": [{"a": a, "b": b, "virtual": i == 4} for i, (a, b) in enumerate(edges)],
            "rotation": rotation, "faces": [list(face) for face in plane.faces],
            "faceOfDart": list(plane.face_of_dart), "outerFace": 0}


class PriorExactFailureAuditTests(unittest.TestCase):
    """These tests check new audit plumbing, without retesting old exact algorithms."""

    def test_actual_edges_and_bridges_are_accounted_for_independently(self):
        """Neither a real bridge nor a virtual connector becomes an inequality."""
        geometry = tiny_geometry()
        graph = graph_from_geometry(geometry)
        self.assertEqual(graph["n"], 2)
        self.assertEqual(graph["edges"], [[0, 1]])
        self.assertEqual(graph["outer"], 0)
        self.assertEqual(graph["real_bridge_edge_ids"], [3])
        self.assertEqual(graph["virtual_edge_ids"], [4])
        checked = verify_raw_witness(geometry, [0, 1])
        self.assertEqual(checked["checked_inequality_edge_ids"], [0, 1, 2])
        self.assertTrue(checked["all_raw_edges_accounted_for"])
        with self.assertRaisesRegex(ValueError, "real shared boundary"):
            verify_raw_witness(geometry, [0, 0])
        for coloring in ([True, 1], [0], [0, 4]):
            with self.assertRaises(ValueError):
                verify_raw_witness(geometry, coloring)
        corrupted = deepcopy(geometry)
        corrupted["outerFace"] = 1
        with self.assertRaisesRegex(ValueError, "signed-area"):
            graph_from_geometry(corrupted)
        corrupted = deepcopy(geometry)
        corrupted["faceOfDart"][0] = 1
        with self.assertRaisesRegex(ValueError, "face/dart"):
            graph_from_geometry(corrupted)

    def test_bfs_has_fixed_root_neighbors_and_component_order(self):
        """Input edge order cannot become a favorable hidden processing choice."""
        edges = [[3, 4], [0, 2], [0, 1], [2, 3], [1, 3]]
        expected = [3, 1, 2, 4, 0, 5]
        self.assertEqual(exterior_bfs(6, edges, 3), expected)
        self.assertEqual(exterior_bfs(6, list(reversed(edges)), 3), expected)

    def test_worker_calls_old_programs_and_rejects_old_coloring_inputs(self):
        """Only the declared uncolored graph/order reaches either exact solver."""
        problem = {"n": 3, "edges": [[0, 1], [0, 2], [1, 2]], "order": [0, 1, 2]}
        for method in ("orbit", "two_port"):
            run = run_one(method, problem)
            self.assertEqual(run["status"], "completed")
            result = run["solver_result"]
            self.assertTrue(result["feasible"])
            self.assertEqual(len(set(result["one_coloring"])), 3)
            self.assertGreaterEqual(run["solver_elapsed_ns"], 0)
        rejected = run_one("orbit", {**problem, "old_colors": [0, 1, 2]})
        self.assertEqual(rejected["status"], "worker_error")
        self.assertIsNone(rejected["solver_result"])

    def test_timeout_is_recorded_once_without_fallback(self):
        """A timed-out order stays timed out rather than trying a favorable order."""
        problem = {"n": 1, "edges": [], "order": [0]}
        with patch("scripts.check_prior_exact_failures.subprocess.run",
                   side_effect=subprocess.TimeoutExpired("worker", 30)) as runner:
            run = run_one("orbit", problem)
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(run["status"], "timeout")
        self.assertIsNone(run["solver_result"])


if __name__ == "__main__":
    unittest.main()

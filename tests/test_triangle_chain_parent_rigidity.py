"""Check the genuine parent-map rigidity certificate independently of policy replay."""

from copy import deepcopy
import unittest

from fourcolor.triangle_chain_family import build_staggered_strip
from scripts.validate_triangle_chain_parent_rigidity import (
    enumerate_literal_parent_colors, parent_graph, two_tree_certificate,
    validate_parameter, verify_two_tree,
)


class TriangleChainParentRigidityTests(unittest.TestCase):
    """Old parent identity is one vertex; inherited daughters are two variables."""

    def test_all_eight_parameters_have_exact_six_colorings(self):
        for m in range(1, 9):
            row = validate_parameter(m)
            self.assertEqual(row["literal_enumeration"]["target_count"], 6)
            self.assertEqual(row["structural_audit"]["interior_vertices"], 6 * m + 2)
            self.assertEqual(row["structural_audit"]["interior_edges"], 12 * m + 1)
            self.assertEqual(len(row["two_tree_certificate"]["steps"]), 6 * m)
            self.assertTrue(all(item["minimum_old_cost"] == 2 * m for item in row["cost_checks"]))

    def test_smallest_parent_geometry_is_one_unsplit_rectangle(self):
        graph = parent_graph(build_staggered_strip(1))
        self.assertIn("parent", graph["vertices"])
        self.assertNotIn("v0", graph["vertices"])
        self.assertNotIn("v2", graph["vertices"])
        self.assertEqual(graph["rectangles"]["parent"], [-1, 3, 1, 2])
        self.assertEqual(len(graph["vertices"]), 9)
        self.assertEqual(len(graph["edges"]), 21)

    def test_missing_actual_edge_rejects_structural_certificate(self):
        graph = parent_graph(build_staggered_strip(1))
        graph["edges"].remove(["parent", "v1"])
        with self.assertRaises(AssertionError):
            verify_two_tree(graph, two_tree_certificate(1))

    def test_nonexistent_attachment_edge_is_rejected(self):
        graph = parent_graph(build_staggered_strip(1))
        certificate = two_tree_certificate(1)
        certificate["steps"][0]["edge"] = ["parent", "v5"]
        with self.assertRaises(AssertionError):
            verify_two_tree(graph, certificate)

    def test_duplicate_attachment_is_rejected(self):
        graph = parent_graph(build_staggered_strip(1))
        certificate = deepcopy(two_tree_certificate(1))
        certificate["steps"][1]["vertex"] = certificate["steps"][0]["vertex"]
        with self.assertRaises(AssertionError):
            verify_two_tree(graph, certificate)

    def test_enumerator_cap_does_not_claim_an_exact_count(self):
        graph = parent_graph(build_staggered_strip(1))
        result = enumerate_literal_parent_colors(graph, max_nodes=0)
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["target_count"])
        self.assertEqual(result["targets_seen"], 0)
        with self.assertRaises(ValueError):
            enumerate_literal_parent_colors(graph, max_nodes=True)


if __name__ == "__main__":
    unittest.main()

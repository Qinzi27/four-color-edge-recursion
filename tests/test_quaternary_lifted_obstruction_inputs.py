"""Test the lifted graph's real geometry without running a coloring policy."""

from copy import deepcopy
from itertools import combinations
import unittest

from scripts.audit_quaternary_geometry import audit_geometry
from scripts.current_corpus import stroke_set_key
from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.quaternary_lifted_obstruction_inputs import (
    REPRESENTATIONS, base_drawing, build_lifted_inventory, identify_lifted,
    transformed_drawing,
)
from scripts.validate_global_restart import canonical_document, export_geometries


class QuaternaryLiftedObstructionInputsTests(unittest.TestCase):
    """The independent audit checks all declared prefixes, not only the final map."""

    @classmethod
    def setUpClass(cls):
        """Batch geometry-only Node exports of the exact declared inventory."""
        cls.inventory = build_lifted_inventory()
        cls.by_key = {}
        for row in export_geometries(cls.inventory["records"]):
            if row["status"] != "geometry_ok" or row["coloring_performed"]:
                raise AssertionError("lifted drawing failed geometry-only export")
            cls.by_key[row["key"]] = row["geometry"]

    def test_four_declared_fixed_order_histories_have_all_prefixes(self):
        """Reconstruct every prefix key directly from its reflected coordinates."""
        histories = self.inventory["histories"]
        self.assertEqual(len(histories), 4)
        self.assertEqual({row["representation"] for row in histories},
                         {name for name, _, _ in REPRESENTATIONS})
        encountered = set()
        for history in histories:
            drawing = transformed_drawing(history["mirror_x"], history["mirror_y"])
            self.assertEqual(history["segment_order"], list(range(24)))
            self.assertEqual(len(history["prefix_keys"]), 25)
            for step, key in enumerate(history["prefix_keys"]):
                prefix = {"frame": drawing["frame"], "strokes": drawing["strokes"][:step]}
                self.assertEqual(key, stroke_set_key(prefix))
                encountered.add(key)
        self.assertEqual(encountered, {row["key"] for row in self.inventory["records"]})
        self.assertEqual(sum(len(row["aliases"]) for row in self.inventory["records"]), 100)
        self.assertEqual(self.inventory["generation"]["prefix_references"], 100)
        self.assertFalse(self.inventory["generation"]["all_insertion_orders"])

    def test_all_prefix_geometries_pass_independent_audit(self):
        """Verify actual source coverage and disconnected-face reconstruction."""
        for row in self.inventory["records"]:
            geometry = self.by_key[row["key"]]
            adapted = adapt_exported_geometry(geometry, drawing=row["document"])
            result, _ = audit_geometry(geometry, adapted)
            self.assertTrue(result["passed"])
            self.assertTrue(result["source_coverage_checked"])

    def test_four_complete_drawings_realize_exactly_the_declared_graph(self):
        """Graph role recovery and the full 19-edge contract agree independently."""
        for history in self.inventory["histories"]:
            geometry = self.by_key[history["prefix_keys"][-1]]
            original = deepcopy(geometry)
            identified = identify_lifted(geometry)
            labels = identified["labels"]
            self.assertEqual(geometry, original)
            self.assertEqual(len(set(labels.values())), 11)
            self.assertEqual(labels["F"], geometry["outerFace"])
            self.assertEqual(labels["Z"], 1)
            self.assertEqual(identified["frame_faces"], sorted([labels["Z"], labels["F"]]))
            expected_names = set(combinations("ABCDE", 2)) - {("A", "E")}
            expected_names |= set(combinations("PQXY", 2))
            expected_names |= {("A", "X"), ("A", "Y"), ("E", "Z"), ("Z", "F")}
            expected = {tuple(sorted((labels[a], labels[b]))) for a, b in expected_names}
            self.assertEqual(len(expected), 19)
            self.assertEqual({tuple(edge) for edge in identified["true_edges"]}, expected)
            self.assertEqual(identified["geometry_audit"]["real_components"], 4)

    def test_partial_inputs_are_not_mislabeled_as_the_complete_graph(self):
        """Reject incomplete prefixes rather than filling topology from intention."""
        history = self.inventory["histories"][0]
        for step in (0, 4, 13, 23):
            with self.subTest(step=step), self.assertRaises(ValueError):
                identify_lifted(self.by_key[history["prefix_keys"][step]])

    def test_drawings_are_fresh_and_have_no_color_restrictions(self):
        """Only geometry, source order, and reflection metadata select inputs."""
        first, second = base_drawing(), base_drawing()
        self.assertEqual(len(second["strokes"]), 24)
        first["strokes"][0]["a"][0] = -1
        self.assertEqual(second["strokes"][0]["a"], [100, 80])
        for row in self.inventory["records"]:
            self.assertEqual(set(row["document"]), {"frame", "strokes"})
            self.assertEqual(canonical_document(row["document"]), row["document"])
        self.assertFalse(self.inventory["generation"]["coloring_used_for_input_selection"])
        self.assertFalse(self.inventory["generation"]["colors_inherited_between_prefixes"])


if __name__ == "__main__":
    unittest.main()

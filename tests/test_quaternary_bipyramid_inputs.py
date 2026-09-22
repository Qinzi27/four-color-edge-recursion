"""Check the declared drawing inventory without consulting coloring outcomes."""

from collections import Counter
from copy import deepcopy
from itertools import combinations, permutations
import unittest

from scripts.audit_quaternary_geometry import audit_geometry
from scripts.current_corpus import stroke_set_key
from scripts.quaternary_bipyramid_inputs import (
    SEGMENTS, base_drawing, build_targeted_inventory, identify_bipyramid,
)
from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.validate_global_restart import canonical_document, export_geometries


class QuaternaryBipyramidInputsTests(unittest.TestCase):
    """All geometry is exported in one batch and independently audited."""

    @classmethod
    def setUpClass(cls):
        """Prepare exactly the declared 64 inputs; perform no name choices."""
        cls.inventory = build_targeted_inventory()
        exported = export_geometries(cls.inventory["records"])
        cls.by_key = {}
        for row in exported:
            if row["status"] != "geometry_ok" or row["coloring_performed"]:
                raise AssertionError("declared drawing failed geometry-only export")
            cls.by_key[row["key"]] = row["geometry"]

    def test_all_subsets_and_every_permutation_are_retained(self):
        """Independently reconstruct each prefix instead of trusting its count."""
        records = self.inventory["records"]
        histories = self.inventory["histories"]
        self.assertEqual({row["subset_mask"] for row in records}, set(range(64)))
        self.assertEqual(len({row["key"] for row in records}), 64)
        self.assertEqual(len(histories), 720)
        self.assertEqual(len({row["id"] for row in histories}), 720)
        self.assertEqual({tuple(row["segment_order"]) for row in histories},
                         set(permutations(range(6))))
        keys = {row["subset_mask"]: row["key"] for row in records}
        for row in histories:
            self.assertEqual(len(row["prefix_keys"]), 7)
            for step in range(7):
                indices = row["segment_order"][:step]
                document = {"frame": {"width": 900, "height": 600}, "strokes": [
                    {"a": list(SEGMENTS[i][0]), "b": list(SEGMENTS[i][1])}
                    for i in indices]}
                self.assertEqual(stroke_set_key(document), row["prefix_keys"][step])
                self.assertEqual(keys[sum(1 << i for i in indices)], row["prefix_keys"][step])
        self.assertEqual(self.inventory["generation"]["prefix_references"], 5040)
        self.assertEqual(Counter(len(row["document"]["strokes"]) for row in records),
                         {0: 1, 1: 6, 2: 15, 3: 20, 4: 15, 5: 6, 6: 1})

    def test_all_real_geometries_pass_independent_adjacency_audit(self):
        """All prefixes are valid even when a new line only produces a bridge."""
        bridge_inputs = []
        for row in self.inventory["records"]:
            geometry = self.by_key[row["key"]]
            adapted = adapt_exported_geometry(geometry, drawing=row["document"])
            audited, _ = audit_geometry(geometry, adapted)
            self.assertTrue(audited["passed"])
            self.assertTrue(audited["source_coverage_checked"])
            if any(line["kind"] == "bridge" for line in adapted["contact_document"]["lines"]):
                bridge_inputs.append(row["subset_mask"])
        # A lone spoke is attached to the frame and is a genuine bridge.
        self.assertIn(1 << 3, bridge_inputs)
        lone_spoke = self.by_key[self.inventory["records"][1 << 3]["key"]]
        self.assertEqual(len(lone_spoke["faces"]), 2)

    def test_complete_map_is_identified_from_geometry_as_k5_minus_apices(self):
        """The inner apex is recognized by lack of frame contact, not an ID."""
        row = self.inventory["records"][63]
        geometry = self.by_key[row["key"]]
        original = deepcopy(geometry)
        identified = identify_bipyramid(geometry)
        self.assertEqual(geometry, original)
        inner, outer = identified["apices"]
        self.assertEqual(identified["inner_apex"], inner)
        self.assertEqual(identified["outer_apex"], outer)
        self.assertEqual(outer, geometry["outerFace"])
        self.assertNotIn(inner, identified["frame_faces"])
        expected = set(combinations(range(5), 2)) - {tuple(sorted((inner, outer)))}
        self.assertEqual({tuple(edge) for edge in identified["true_edges"]}, expected)
        self.assertEqual(len(identified["rim"]), 3)
        adapted = adapt_exported_geometry(geometry, drawing=row["document"])
        mothers = [line for line in adapted["whole_lines"] if line["id"] != "frame"]
        self.assertEqual(len(mothers), 6)
        self.assertTrue(all(len(line["sources"]) == 1 for line in mothers))

    def test_identification_rejects_a_partial_map(self):
        """The target identifier must not label an arbitrary prefix a bipyramid."""
        for mask in (0, 7, 31):
            geometry = self.by_key[self.inventory["records"][mask]["key"]]
            with self.subTest(mask=mask), self.assertRaises(ValueError):
                identify_bipyramid(geometry)

    def test_inventory_contains_fresh_geometry_only_documents(self):
        """No anchors, domain restrictions, or previous outcomes select inputs."""
        first, second = base_drawing(), base_drawing()
        first["strokes"][0]["a"][0] = -99
        self.assertEqual(second["strokes"][0]["a"], [420, 150])
        self.assertEqual(canonical_document(second), self.inventory["records"][63]["document"])
        for row in self.inventory["records"]:
            self.assertEqual(set(row["document"]), {"frame", "strokes"})
            self.assertEqual(canonical_document(row["document"]), row["document"])
        self.assertFalse(self.inventory["generation"]["coloring_used_for_input_selection"])
        self.assertFalse(self.inventory["generation"]["colors_inherited_between_prefixes"])


if __name__ == "__main__":
    unittest.main()

"""Independent geometry checks for every declared support-history prefix."""

from copy import deepcopy
import unittest

from scripts.current_corpus import stroke_set_key
from scripts.quaternary_lifted_obstruction_inputs import identify_lifted
from scripts.quaternary_root_support_inputs import (
    CASES, EXTENSIONS, ORIENTATIONS, audit_support_geometry,
    build_support_inventory, inspect_support_geometry, rotate_point, support_drawing,
)
from scripts.validate_global_restart import canonical_document, export_geometries


class QuaternaryRootSupportInputsTests(unittest.TestCase):
    """No coloring producer, oracle, or externally assigned domain is called."""

    @classmethod
    def setUpClass(cls):
        """Export and independently audit all 16 frozen-by-definition inputs."""
        cls.inventory = build_support_inventory()
        cls.records = {row["key"]: row for row in cls.inventory["records"]}
        cls.geometries, cls.audits = {}, {}
        for exported in export_geometries(cls.inventory["records"]):
            if exported["status"] != "geometry_ok" or exported["coloring_performed"]:
                raise AssertionError("support input failed geometry-only export")
            key, geometry = exported["key"], exported["geometry"]
            row = cls.records[key]
            cls.geometries[key] = geometry
            cls.audits[key] = inspect_support_geometry(geometry, row)

    def test_complete_declared_inventory_and_all_short_prefixes(self):
        """Reconstruct every reference from the original extension schedule."""
        self.assertEqual(len(self.inventory["cases"]), 12)
        self.assertEqual(len(self.records), 16)
        self.assertEqual(self.inventory["generation"]["prefix_references"], 32)
        self.assertEqual(sum(len(r["aliases"]) for r in self.records.values()), 32)
        seen = set()
        for history in self.inventory["histories"]:
            order = history["extension_order"]
            self.assertEqual(len(history["prefix_keys"]), len(order) + 1)
            for step, key in enumerate(history["prefix_keys"]):
                doc = support_drawing(order[:step], history["orientation_degrees"])
                self.assertEqual(key, stroke_set_key(doc))
                self.assertEqual(len(doc["strokes"]), 24 + step)
                seen.add(key)
        self.assertEqual(seen, set(self.records))
        self.assertFalse(self.inventory["generation"]["old_base_prefixes_0_through_23_included"])

    def test_half_turn_is_rigid_and_preserves_frame_dimensions(self):
        """A half turn fits the frozen frame without squeezing the drawing."""
        for _, names in CASES:
            a, b = support_drawing(names, 0), support_drawing(names, 180)
            self.assertEqual(b["frame"], {"width": 900, "height": 600})
            for first, second in zip(a["strokes"], b["strokes"]):
                for end in ("a", "b"):
                    self.assertEqual(second[end], [900 - first[end][0], 600 - first[end][1]])
                lengths = [sum((s["a"][i] - s["b"][i]) ** 2 for i in (0, 1))
                           for s in (first, second)]
                self.assertEqual(*lengths)
        with self.assertRaises(ValueError):
            rotate_point((2, 3), 45)
        with self.assertRaises(ValueError):
            rotate_point((2, 3), 90)
        revision = self.inventory["generation"]["pre_freeze_geometry_revision"]
        self.assertEqual(revision["initially_planned_orientations"], [0, 90])
        self.assertEqual(revision["final_orientations"], [0, 180])
        self.assertFalse(revision["revision_used_coloring_results"])

    def test_all_prefixes_have_audited_real_geometry(self):
        """Check sources and literal topology rather than assuming old roles."""
        for key, row in self.records.items():
            with self.subTest(extensions=row["metadata"]["extensions"],
                              rotation=row["metadata"]["orientation_degrees"]):
                audit = self.audits[key]
                self.assertTrue(audit["geometry_audit"]["passed"])
                self.assertTrue(audit["geometry_audit"]["source_coverage_checked"])
                self.assertEqual(audit["faces"], len(self.geometries[key]["faces"]))
                self.assertEqual(audit["true_adjacency_edges"], len(audit["true_edges"]))
                self.assertLessEqual(audit["faces"], 40)
                self.assertFalse(audit["coloring_performed"])
                self.assertFalse(audit["old_named_face_ids_reused"])
                self.assertEqual(audit["role_mapping"] is not None,
                                 not row["metadata"]["extensions"])

    def test_both_complete_chords_recover_real_frame_rooting(self):
        """Only the two-ended completed extensions imply frame-rooted chords."""
        for key, row in self.records.items():
            names = set(row["metadata"]["extensions"])
            for chord, required in (
                ("horizontal_complete_chord", {"left", "right"}),
                ("diagonal_complete_chord", {"diagonal-upper", "diagonal-lower"}),
            ):
                evidence = self.audits[key]["complete_chords"][chord]
                expected = required <= names
                self.assertEqual(evidence["present"], expected)
                self.assertEqual(evidence["rooted_at_frame_level_two"], expected)
                if expected:
                    self.assertEqual(evidence["level"], 2)
                    self.assertTrue(evidence["atomic_real_edges"])
                    self.assertTrue(evidence["current_units"])

    def test_original_topology_is_only_asserted_for_unextended_base(self):
        """Retain the known base; explicitly allow extensions to split its faces."""
        for case in self.inventory["cases"]:
            if case["metadata"]["variant"] == "base":
                result = identify_lifted(self.geometries[case["key"]])
                self.assertEqual(len(result["true_edges"]), 19)
                self.assertTrue(self.audits[case["key"]]["contains_induced_K5_minus_edge"])
        self.assertTrue(any(row["faces"] != 11 for row in self.audits.values()))

    def test_fresh_inputs_preserve_all_base_segments_and_no_color_metadata(self):
        """Changing a returned object cannot contaminate later declared inputs."""
        a = support_drawing(tuple(EXTENSIONS), 0)
        b = support_drawing(tuple(EXTENSIONS), 0)
        expected = deepcopy(b)
        a["strokes"][0]["a"][0] = -9
        self.assertEqual(b, expected)
        for row in self.records.values():
            self.assertEqual(set(row["document"]), {"frame", "strokes"})
            self.assertEqual(canonical_document(row["document"]), row["document"])
        self.assertFalse(self.inventory["generation"]["coloring_used_for_input_selection"])
        self.assertFalse(self.inventory["generation"]["selection_order_improvement_claimed"])


if __name__ == "__main__":
    unittest.main()

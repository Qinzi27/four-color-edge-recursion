"""Geometry-only tests for the fixed inversion corpus and marked isomorphisms."""

from copy import deepcopy
from itertools import combinations
import unittest

from scripts.audit_quaternary_geometry import audit_geometry
from scripts.current_corpus import stroke_set_key
from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.quaternary_lifted_obstruction_inputs import base_drawing
from scripts.quaternary_reroot_inputs import (
    TARGET_CENTERS, build_reroot_inventory, identify_reroot,
    export_reroot_geometries, inversion_drawing, verify_target_centers,
)
from scripts.validate_global_restart import canonical_document, export_geometries


class QuaternaryRerootInputsTests(unittest.TestCase):
    """Check intended topology without executing a coloring policy."""

    @classmethod
    def setUpClass(cls):
        """Export every fixed final drawing, preserving failures for assertions."""
        cls.inventory = build_reroot_inventory()
        records = cls.inventory["records"]
        cls.exports = export_reroot_geometries(records)
        cls.legacy_exports = export_geometries(records)
        cls.by_key = {row["key"]: row for row in cls.exports}
        cls.base_geometry = export_geometries([{"key": "base", "document": base_drawing()}])[0]["geometry"]

    def test_declared_cartesian_product_is_complete_and_deterministic(self):
        """No invalid case is filtered and no untested prefix scope is implied."""
        self.assertEqual(self.inventory, build_reroot_inventory())
        rows = self.inventory["records"]
        self.assertEqual(len(rows), 28)
        self.assertEqual(len({row["key"] for row in rows}), 28)
        self.assertEqual({(row["target"], row["subdivisions"], row["rotation_degrees"]) for row in rows},
                         {(target, sub, rot) for target in TARGET_CENTERS for sub in (4, 8) for rot in (0, 90)})
        self.assertFalse(self.inventory["generation"]["original_implicit_frame_inverted"])
        self.assertFalse(self.inventory["generation"]["coloring_used_for_input_selection"])
        self.assertIn("prefixes not checked", self.inventory["generation"]["input_scope"])
        for row in rows:
            self.assertEqual(row["key"], stroke_set_key(row["document"]))
            self.assertEqual(row["document"], canonical_document(row["document"]))
            self.assertEqual(set(row["document"]), {"frame", "strokes"})
            self.assertEqual(len(row["document"]["strokes"]), 24 * row["subdivisions"])

    def test_original_centers_have_their_claimed_structural_roles(self):
        """Spatial P/Q and X/Y point labels are distinct from sorted face IDs."""
        report = verify_target_centers(self.base_geometry)
        self.assertTrue(report["passed"])
        self.assertEqual(len(set(report["center_faces"].values())), 7)
        self.assertTrue(report["geometry_audit"]["passed"])

    def test_uniform_fit_margin_and_decimal_precision(self):
        """Input fitting cannot clip curves against the engine's implicit frame."""
        for row in self.inventory["records"]:
            for stroke in row["document"]["strokes"]:
                self.assertNotEqual(stroke["a"], stroke["b"])
                for point in (stroke["a"], stroke["b"]):
                    self.assertTrue(50 <= point[0] <= 850)
                    self.assertTrue(50 <= point[1] <= 550)
                    self.assertEqual(point, [round(value, 8) for value in point])

    def test_exports_remain_geometry_only_and_outcomes_are_explicit(self):
        """Each generated case receives an export, including unsupported ones."""
        self.assertEqual(len(self.exports), 28)
        for exported in self.exports:
            self.assertFalse(exported["coloring_performed"])
            self.assertIn(exported["status"], {"geometry_ok", "geometry_error"})
            if exported["status"] == "geometry_error":
                self.assertTrue(exported["errors"])

    def test_frozen_exporter_retains_all_28_stroke_limit_failures(self):
        """The unchanged 80-stroke engine cannot inspect 96/192-stroke inputs.

        This is a supported-input boundary, not a graph-topology or coloring
        failure.  Testing the rejection explicitly prevents a zero-tested-case
        result from being presented as a successfully checked topology corpus.
        """
        for exported in self.legacy_exports:
            self.assertEqual(exported["status"], "geometry_error")
            self.assertEqual([error["code"] for error in exported["errors"]], ["limit"])
            self.assertIn("80", exported["errors"][0]["message"])

    def test_research_exporter_changes_only_declared_resource_profile(self):
        """The bound isolated exporter never changes the frozen engine on disk."""
        expected_old = "export const LIMITS = Object.freeze({strokes:80, edges:1600, faces:400});"
        expected_new = "export const LIMITS = Object.freeze({strokes:256, edges:1600, faces:400});"
        profiles = [row["engine_profile"] for row in self.exports]
        self.assertTrue(all(profile == profiles[0] for profile in profiles))
        profile = profiles[0]
        self.assertEqual(profile["exact_replacement"], {"from": expected_old, "to": expected_new, "occurrences": 1})
        self.assertEqual(profile["limits"], {"strokes": 256, "edges": 1600, "faces": 400})
        self.assertFalse(profile["old_engine_file_modified"])
        self.assertNotEqual(profile["original_engine_sha256"], profile["in_memory_engine_sha256"])
        original_export = export_reroot_geometries([{"key": "base", "document": base_drawing()}])[0]
        self.assertEqual(original_export["geometry"], self.base_geometry)

    def test_known_base_map_exercises_the_complete_isomorphism_checker(self):
        """Validate the matcher even when all new polylines exceed input limits."""
        result = identify_reroot(self.base_geometry, "Z")
        self.assertTrue(result["passed"])
        self.assertEqual(result["isomorphism_count"], 24)
        self.assertEqual(result["labels"]["Z"], result["bounded_frame_face"])
        self.assertEqual(set(result["ambiguous_roles"]), set("BCDPQXY"))
        expected = set(combinations("ABCDE", 2)) - {("A", "E")}
        expected |= set(combinations("PQXY", 2))
        expected |= {("A", "X"), ("A", "Y"), ("E", "Z"), ("F", "Z")}
        for mapping in result["all_equivalent_mappings"]:
            self.assertEqual({tuple(sorted((mapping[a], mapping[b]))) for a, b in expected},
                             {tuple(pair) for pair in result["true_edges"]})

    def test_each_identified_graph_has_exact_19_edge_contract(self):
        """Every accepted marking preserves edges and nonedges, plus frame role."""
        accepted = 0
        for row in self.inventory["records"]:
            exported = self.by_key[row["key"]]
            if exported["status"] != "geometry_ok":
                continue
            geometry = exported["geometry"]
            try:
                report = identify_reroot(geometry, row["target"])
            except ValueError:
                # Fixed chord approximations may alter topology; do not replace.
                continue
            accepted += 1
            adapted = adapt_exported_geometry(geometry, drawing=row["document"])
            audited, raw_edges = audit_geometry(geometry, adapted)
            self.assertTrue(audited["source_coverage_checked"])
            expected = set(combinations("ABCDE", 2)) - {("A", "E")}
            expected |= set(combinations("PQXY", 2))
            expected |= {("A", "X"), ("A", "Y"), ("E", "Z"), ("F", row["target"])}
            self.assertEqual(len(report["all_equivalent_mappings"]), report["isomorphism_count"])
            for labels in report["all_equivalent_mappings"]:
                self.assertEqual(len(set(labels.values())), 11)
                self.assertEqual(labels["F"], geometry["outerFace"])
                self.assertEqual(labels[row["target"]], report["bounded_frame_face"])
                self.assertEqual({tuple(sorted((labels[a], labels[b]))) for a, b in expected}, set(raw_edges))
            self.assertEqual(report["frame_faces"], sorted([report["outer_face"], report["bounded_frame_face"]]))
        self.assertGreater(accepted, 0, "all declared new inputs lack a verified topology")

    def test_identifier_preserves_input_and_reports_symmetry(self):
        """A/E and K4 groups are invariant, while symmetric labels stay explicit."""
        for row in self.inventory["records"]:
            exported = self.by_key[row["key"]]
            if exported["status"] != "geometry_ok":
                continue
            geometry = exported["geometry"]
            before = deepcopy(geometry)
            try:
                report = identify_reroot(geometry, row["target"])
            except ValueError:
                self.assertEqual(geometry, before)
                continue
            self.assertEqual(geometry, before)
            for name in "AEZF":
                self.assertEqual(len(report["role_possibilities"][name]), 1)
            self.assertEqual(set(report["ambiguous_roles"]) & set("BCD"), set("BCD"))
            self.assertEqual(report["isomorphism_count"], 12 if row["target"] in "PQXY" else 24)
            for mapping in report["all_equivalent_mappings"]:
                self.assertEqual(sorted(mapping[name] for name in "PQXY"),
                                 sorted(report["inner_patch"] + report["outer_patch"]))

    def test_wrong_marking_or_corrupt_geometry_is_rejected(self):
        """Do not infer roles from intent when the real graph contradicts it."""
        with self.assertRaises(ValueError):
            identify_reroot(self.base_geometry, "P")
        with self.assertRaises(ValueError):
            identify_reroot(self.base_geometry, "missing")
        bad = deepcopy(self.base_geometry)
        bad["outerFace"] = -1
        with self.assertRaises(ValueError):
            identify_reroot(bad, "Z")

    def test_undeclared_generator_parameters_are_rejected(self):
        """The generator cannot silently retry a different sample or angle."""
        for args in (("B", 4, 0), ("P", 16, 0), ("P", 4, 45)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                inversion_drawing(*args)


if __name__ == "__main__":
    unittest.main()

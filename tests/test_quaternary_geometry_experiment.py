"""Freeze real input selection and keep initialization/certificate modes apart."""

import unittest
from unittest.mock import patch

from scripts.validate_global_restart import digest, export_geometries
from scripts.validate_quaternary_geometry import (
    LEGACY, PRIMARY, ROUNDTRIP, input_inventory, run_drawing, run_record, standard_scenarios,
)


class QuaternaryGeometryExperimentTests(unittest.TestCase):
    """Check meaningful protocol boundaries rather than rerun the full corpus."""

    def test_archive_selection_keeps_all_grid_masks_and_all_historical_controls(self):
        """The new output must not determine which old failures are included."""
        inventory = input_inventory()
        rows = inventory["records"]
        self.assertEqual(len({r["key"] for r in rows}), len(rows))
        grid = [r for r in rows if "grid-subsets" in r["families"]]
        historical = [r for r in rows if "historical-controls" in r["families"]]
        self.assertEqual(sorted(r["subset_mask"] for r in grid), list(range(4096)))
        self.assertEqual(len(historical), 49)
        self.assertEqual(len(inventory["grid_histories"]), 4096)
        self.assertEqual(sum(len(h["prefix_keys"]) for h in inventory["grid_histories"]), 28672)
        self.assertEqual(sum(len(r["extra_scenarios"]) for r in rows), 2)
        grid_keys = {r["key"] for r in grid}
        for h in inventory["grid_histories"]:
            self.assertTrue(set(h["prefix_keys"]) <= grid_keys)

    def test_one_bounded_anchor_does_not_silently_fix_its_neighbor_to_two(self):
        """Only the separately named legacy mode may supply the second anchor."""
        document = {"frame": {"width": 900, "height": 600}, "strokes": []}
        geometry = export_geometries([{"key": "empty-frame", "document": document}])[0]["geometry"]
        cases = standard_scenarios(geometry, {"extra_scenarios": []})
        primary = next(r for r in cases if r["id"] == PRIMARY)
        legacy = next(r for r in cases if r["id"] == LEGACY)
        self.assertEqual(list(primary["anchors"].values()), [1])
        self.assertNotIn(f"S{geometry['outerFace']}", primary["anchors"])
        self.assertEqual(sorted(legacy["anchors"].values()), [1, 2])
        self.assertEqual(len(cases), 2)

    def test_archived_complete_colors_are_an_explicit_extra_input_mode(self):
        """Passing a complete certificate cannot inflate free completion counts."""
        geometry = export_geometries([{"key": "empty-frame", "document": {"strokes": []}}])[0]["geometry"]
        cases = standard_scenarios(geometry, {"extra_scenarios": [], "archived_colors": [1, 2]})
        self.assertEqual(len(cases), 3)
        case = next(r for r in cases if r["id"] == ROUNDTRIP)
        self.assertEqual(case["anchors"], {"S0": 1, "S1": 2})
        self.assertEqual(case["expected_producer_status"], "solved")

    def test_single_map_keeps_original_input_and_ignores_old_colors(self):
        """A saved old coloring is context, never an implicit new constraint."""
        document = {"strokes": [], "old_colors": {"S0": 4, "S1": 4}}
        report = run_drawing(document)
        self.assertEqual(report["original_input"], document)
        self.assertEqual(report["ignored_top_level_fields"], ["old_colors"])
        self.assertEqual(report["outcome"]["status"], "underdetermined")
        self.assertIsNone(report["outcome"]["colors"])
        self.assertEqual(report["outcome"]["choices"], 0)
        self.assertEqual(report["audit"]["oracle"]["status"], "sat")
        self.assertTrue(report["audit"]["passed"])

    def test_worker_audit_failure_retains_exact_scene_and_producer_output(self):
        """A rejected result must remain reviewable before a formal run stops."""
        document = {"strokes": []}
        geometry = export_geometries([{"key": "empty-frame", "document": document}])[0]["geometry"]
        row = {"key": "empty-frame", "document": document, "geometry": geometry,
               "geometry_sha256": digest(geometry), "families": ["test"],
               "scenarios": [{"id": PRIMARY, "anchors": {"S1": 1}}]}
        with patch("scripts.audit_quaternary_geometry.audit_run", side_effect=AssertionError("deliberate audit rejection")):
            failure = run_record((row, {"assignment_limit": 256, "node_limit": 200000}))
        self.assertTrue(failure["failed"])
        self.assertEqual(failure["scenario"]["id"], PRIMARY)
        self.assertEqual(failure["document"], document)
        self.assertEqual(failure["outcome"]["status"], "underdetermined")
        self.assertIsNone(failure["audit"])
        self.assertEqual(failure["error"], "deliberate audit rejection")


if __name__ == "__main__":
    unittest.main()

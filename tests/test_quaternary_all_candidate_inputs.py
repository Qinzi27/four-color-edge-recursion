"""Validate the new declarations without coloring, propagation, or search."""

from collections import Counter
from math import hypot
import unittest

from scripts.audit_quaternary_geometry import audit_geometry
from scripts.current_corpus import stroke_set_key
from scripts.quaternary_all_candidate_inputs import (
    ANGLE_OFFSETS, CENTER, CHORDS, FRAME, GUILLOTINE, POLYGONS, POLYGON_SIDES,
    RADII, RANDOM_FAMILIES, RING_COUNTS, SEEDS, STEPS,
    build_all_candidate_holdout, polygon_paths,
)
from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.validate_global_restart import canonical_document, export_geometries


class QuaternaryAllCandidateInputsTests(unittest.TestCase):
    """The input inventory is independent of naming outcomes and exclusions."""

    @classmethod
    def setUpClass(cls):
        """Generate the fixed inventory once, without running either policy."""
        cls.inventory = build_all_candidate_holdout()
        cls.records = {row["key"]: row for row in cls.inventory["records"]}

    def test_exact_counts_and_shared_empty_prefix(self):
        """All aliases remain present after literal stroke-set deduplication."""
        self.assertEqual(len(self.inventory["histories"]), 7)
        self.assertEqual(len(self.records), 75)
        self.assertEqual(sum(len(row["prefix_keys"]) for row in self.inventory["histories"]), 81)
        self.assertEqual(sum(len(row["aliases"]) for row in self.records.values()), 81)
        self.assertEqual(Counter(row["family"] for row in self.inventory["histories"]),
                         Counter({GUILLOTINE: 2, CHORDS: 2, POLYGONS: 3}))
        self.assertEqual(self.inventory["generation"]["maximum_source_strokes"], 21)
        empty = [row for row in self.records.values() if not row["document"]["strokes"]]
        self.assertEqual(len(empty), 1)
        self.assertEqual(len(empty[0]["aliases"]), 7)

    def test_every_ordered_prefix_reconstructs_the_canonical_record(self):
        """Check complete coverage, keys, aliases and one-stroke increments."""
        visited = set()
        for history in self.inventory["histories"]:
            for step, key in enumerate(history["prefix_keys"]):
                document = canonical_document({"frame": FRAME,
                                               "strokes": history["ordered_strokes"][:step]})
                self.assertEqual(self.records[key]["document"], document)
                self.assertEqual(stroke_set_key(document), key)
                self.assertEqual(set(document), {"frame", "strokes"})
                self.assertEqual(len(document["strokes"]), step)
                self.assertTrue(any(alias["history"] == history["id"] and alias["step"] == step
                                    for alias in self.records[key]["aliases"]))
                visited.add(key)
            self.assertEqual(history["terminal_key"], history["prefix_keys"][-1])
        self.assertEqual(visited, set(self.records))

    def test_parameter_product_and_stroke_budget(self):
        """No seed, size or declared prefix is filtered by observed success."""
        self.assertEqual(SEEDS, (20262601, 20262602))
        self.assertEqual(STEPS, 5)
        self.assertEqual(POLYGON_SIDES, (5, 6, 7))
        self.assertEqual(RING_COUNTS, (2,))
        self.assertEqual(ANGLE_OFFSETS, (17,))
        histories = self.inventory["histories"]
        self.assertEqual({(row["family"], row["seed"]) for row in histories
                          if row["family"] in RANDOM_FAMILIES},
                         {(family, seed) for family in RANDOM_FAMILIES for seed in SEEDS})
        self.assertEqual({(row["polygon_sides"], row["ring_count"], row["angle_offset_degrees"])
                          for row in histories if row["family"] == POLYGONS},
                         {(n, count, angle) for n in POLYGON_SIDES for count in RING_COUNTS
                          for angle in ANGLE_OFFSETS})
        for history in histories:
            expected = 3 * history["polygon_sides"] if history["family"] == POLYGONS else 5
            self.assertEqual(len(history["ordered_strokes"]), expected)
            self.assertLessEqual(expected, 80)

    def test_polygon_incidence_radii_and_parameter_rejection(self):
        """Check coordinates independently of the later face exporter."""
        for n in POLYGON_SIDES:
            paths = polygon_paths(n, 2, 17)
            self.assertEqual(len(paths), 3 * n)
            for layer, radius in enumerate(RADII[:2]):
                ring = [row[0] for row in paths[layer * n:(layer + 1) * n]]
                for i, (first, second) in enumerate(paths[layer * n:(layer + 1) * n]):
                    self.assertEqual(second, ring[(i + 1) % n])
                    self.assertAlmostEqual(hypot(first[0] - CENTER[0], first[1] - CENTER[1]),
                                           radius, places=7)
                    self.assertTrue(0 < first[0] < 900 and 0 < first[1] < 600)
                    self.assertTrue(all(value == round(value, 8) for value in first))
            self.assertEqual(paths[2 * n:], [[paths[i][0], paths[n + i][0]] for i in range(n)])
        for arguments in ((4, 2, 17), (5, 1, 17), (5, 2, 0)):
            with self.assertRaises(ValueError):
                polygon_paths(*arguments)

    def test_geometry_only_export_covers_all_inputs_and_face_budget(self):
        """Keep any exporter/audit errors explicit rather than dropping inputs."""
        exports = export_geometries(self.inventory["records"])
        self.assertEqual({row["key"] for row in exports}, set(self.records))
        self.assertEqual(len(exports), len(self.records))
        audited = 0
        terminals = {row["terminal_key"]: row for row in self.inventory["histories"]
                     if row["family"] == POLYGONS}
        for row in exports:
            self.assertFalse(row["coloring_performed"])
            if row["status"] == "geometry_error":
                self.assertTrue(row["errors"])
                continue
            self.assertEqual(row["status"], "geometry_ok")
            self.assertLessEqual(len(row["geometry"]["faces"]), 40)
            try:
                adapted = adapt_exported_geometry(row["geometry"],
                                                  drawing=self.records[row["key"]]["document"])
                audit, _ = audit_geometry(row["geometry"], adapted)
            except (ValueError, AssertionError) as error:
                self.assertTrue(str(error))
                continue
            audited += 1
            self.assertTrue(audit["passed"])
            self.assertTrue(audit["source_coverage_checked"])
            if row["key"] in terminals:
                self.assertEqual(len(row["geometry"]["faces"]),
                                 terminals[row["key"]]["polygon_sides"] + 3)
        self.assertGreater(audited, 0)

    def test_repeatability_and_declared_inference_boundaries(self):
        """Fresh initialization and correlated-family scope are explicit."""
        self.assertEqual(build_all_candidate_holdout(), self.inventory)
        generation = self.inventory["generation"]
        for field in ("outcome_filtering", "geometry_validation_performed_by_generator",
                      "propagation_performed", "oracle_performed", "colors_inherited_between_prefixes",
                      "all_insertion_orders"):
            self.assertFalse(generation[field])
        self.assertIn("fresh standard anchors", generation["prefix_initialization"])
        self.assertIn("not independent graph families", generation["scope"])
        self.assertIn("not graph isomorphism", generation["deduplication"])
        self.assertFalse(generation["chords"]["general_position_assumed"])

    def test_declared_terminal_hashes_are_stable(self):
        """Pin the new coordinate declaration independently of repeat calls."""
        expected = [
            "2e82f85b1ae8e2670a1c75400f47ab8d6bdb9d8473ed84792b3f6583060fbd0b",
            "60e18cad9cd2ad9f203f00d6a6f2de07c65dbdde57299f68d59a84a7915b0e81",
            "a190c7bf5db542a26c38c101af253b1912db59c6e5763f9f83f76b43de8e5d46",
            "1c0def70062a53f99002e5c318276521d6e9b552eaa154e661a9e7ba54f85bd5",
            "7de4f7934e01c485cc418e59419584de563fc5a1df66090bb69c5defe7a4e334",
            "8f7bb8ab44f84033d611c610fa1d3f46c94c92338fad74978a689ff0a153aed9",
            "691996204b96abc686352a78b87e245e5dfa1c24e7001847ccebe4e02bb46986",
        ]
        self.assertEqual([row["terminal_key"] for row in self.inventory["histories"]], expected)


if __name__ == "__main__":
    unittest.main()

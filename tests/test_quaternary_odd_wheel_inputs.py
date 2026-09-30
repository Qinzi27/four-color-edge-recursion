"""Validate the new declarations without coloring, propagation, or search."""

from collections import Counter
from math import hypot
import unittest

from scripts.current_corpus import stroke_set_key
from scripts.quaternary_odd_wheel_inputs import (
    ANGLE_OFFSETS, CENTER, CHORDS, FRAME, GUILLOTINE, POLYGONS, POLYGON_SIDES,
    RADII, RANDOM_FAMILIES, RING_COUNTS, SEEDS, STEPS,
    build_odd_wheel_holdout, polygon_paths,
)
from scripts.validate_global_restart import canonical_document


class QuaternaryOddWheelInputsTests(unittest.TestCase):
    """The input inventory is independent of naming outcomes and exclusions."""

    @classmethod
    def setUpClass(cls):
        """Generate the fixed inventory once, without running either policy."""
        cls.inventory = build_odd_wheel_holdout()
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
        self.assertEqual(SEEDS, (20263001, 20263002))
        self.assertEqual(STEPS, 5)
        self.assertEqual(POLYGON_SIDES, (5, 6, 7))
        self.assertEqual(RING_COUNTS, (2,))
        self.assertEqual(ANGLE_OFFSETS, (0,))
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
            paths = polygon_paths(n, 2, 0)
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
        for arguments in ((4, 2, 0), (5, 1, 0), (5, 2, 31)):
            with self.assertRaises(ValueError):
                polygon_paths(*arguments)

    def test_repeatability_and_declared_inference_boundaries(self):
        """Fresh initialization and correlated-family scope are explicit."""
        self.assertEqual(build_odd_wheel_holdout(), self.inventory)
        generation = self.inventory["generation"]
        for field in ("outcome_filtering", "geometry_validation_performed_by_generator",
                      "propagation_performed", "oracle_performed", "colors_inherited_between_prefixes",
                      "all_insertion_orders"):
            self.assertFalse(generation[field])
        self.assertIn("fresh standard anchors", generation["prefix_initialization"])
        self.assertIn("not independent graph families", generation["scope"])
        self.assertIn("not graph isomorphism", generation["deduplication"])
        self.assertFalse(generation["chords"]["general_position_assumed"])

if __name__ == "__main__":
    unittest.main()

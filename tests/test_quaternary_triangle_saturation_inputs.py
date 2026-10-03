"""Check only geometry declarations, without new naming or oracle outcomes."""

from collections import Counter
import unittest

from scripts.current_corpus import stroke_set_key
from scripts.quaternary_triangle_saturation_inputs import (
    CHORDS, FRAME, GUILLOTINE, RANDOM_FAMILIES, SEEDS, STEPS,
    build_triangle_saturation_holdout, chord_paths,
)
from scripts.validate_global_restart import canonical_document


class TriangleSaturationInputsTests(unittest.TestCase):
    """All declared aliases and insertion prefixes survive canonicalization."""

    @classmethod
    def setUpClass(cls):
        """Build coordinate-only records once for all tests."""
        cls.inventory = build_triangle_saturation_holdout()
        cls.records = {row["key"]: row for row in cls.inventory["records"]}

    def test_counts_and_shared_empty(self):
        """The four empty prefixes share one drawing but remain four references."""
        self.assertEqual(len(self.inventory["histories"]), 4)
        self.assertEqual(len(self.records), 21)
        self.assertEqual(sum(len(row["prefix_keys"]) for row in self.inventory["histories"]), 24)
        self.assertEqual(sum(len(row["aliases"]) for row in self.records.values()), 24)
        self.assertEqual(Counter(row["family"] for row in self.inventory["histories"]),
                         Counter({GUILLOTINE: 2, CHORDS: 2}))
        empty = [row for row in self.records.values() if not row["document"]["strokes"]]
        self.assertEqual(len(empty), 1)
        self.assertEqual(len(empty[0]["aliases"]), 4)
        self.assertEqual(self.inventory["generation"]["maximum_source_strokes"], 5)

    def test_every_prefix_reconstructs(self):
        """A history adds one distinct stroke per step, without inherited names."""
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

    def test_parameter_product_and_chord_endpoint_bounds(self):
        """Check the frozen seed product and literal integer endpoint range."""
        self.assertEqual(SEEDS, (20261001, 20261002))
        self.assertEqual(STEPS, 5)
        self.assertEqual({(row["family"], row["seed"]) for row in self.inventory["histories"]},
                         {(family, seed) for family in RANDOM_FAMILIES for seed in SEEDS})
        for seed in SEEDS:
            paths = chord_paths(seed)
            self.assertEqual(len(paths), 5)
            self.assertEqual(len({a[1] for a, _ in paths}), 5)
            self.assertEqual(len({b[1] for _, b in paths}), 5)
            for first, second in paths:
                self.assertEqual((first[0], second[0]), (0, 900))
                self.assertTrue(all(type(point[1]) is int and 20 <= point[1] <= 580
                                    for point in (first, second)))

    def test_repeatability_and_boundaries(self):
        """This declares correlated known-family inputs rather than coloring evidence."""
        self.assertEqual(build_triangle_saturation_holdout(), self.inventory)
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

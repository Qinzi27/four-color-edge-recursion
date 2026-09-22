"""Check frozen holdout inputs using geometry only, never the tested algorithm."""

from collections import Counter
import unittest

from scripts.current_corpus import stroke_set_key
from scripts.quaternary_low_color_inputs import (
    CHORDS, FAMILIES, GUILLOTINE, SEEDS, STEPS, build_holdout,
)
from scripts.validate_global_restart import canonical_document, export_geometries


def stroke_set(document):
    """Use literal endpoints to inspect increments without depending on hashes."""
    return {tuple(sorted((tuple(row["a"]), tuple(row["b"]))))
            for row in document["strokes"]}


class QuaternaryLowColorInputsTests(unittest.TestCase):
    """All geometry must be retained, even if a future algorithm fails on it."""

    @classmethod
    def setUpClass(cls):
        """Generate once, batch the existing geometry exporter, and retain all."""
        cls.holdout = build_holdout()
        cls.records = {row["key"]: row for row in cls.holdout["records"]}
        cls.geometry_rows = export_geometries(cls.holdout["records"])
        cls.geometries = {row["key"]: row["geometry"] for row in cls.geometry_rows}

    def test_every_declared_seed_family_and_prefix_is_present(self):
        histories = self.holdout["histories"]
        self.assertEqual(len(histories), 16)
        self.assertEqual(sum(len(row["prefix_keys"]) for row in histories), 144)
        self.assertEqual({(row["family"], row["seed"]) for row in histories},
                         {(family, seed) for family in FAMILIES for seed in SEEDS})
        self.assertEqual(len(self.records), 129)
        self.assertEqual(sum(len(row["aliases"]) for row in self.records.values()), 144)
        self.assertEqual(Counter(alias["step"] for row in self.records.values()
                                 for alias in row["aliases"]),
                         Counter({step: 16 for step in range(9)}))
        empty = [row for row in self.records.values() if not row["document"]["strokes"]]
        self.assertEqual(len(empty), 1)
        self.assertEqual(len(empty[0]["aliases"]), 16)

    def test_canonical_identity_and_exact_one_stroke_increments(self):
        for row in self.records.values():
            self.assertEqual(row["document"], canonical_document(row["document"]))
            self.assertEqual(row["key"], stroke_set_key(row["document"]))
        for history in self.holdout["histories"]:
            previous = set()
            for step, key in enumerate(history["prefix_keys"]):
                with self.subTest(history=history["id"], step=step):
                    row = self.records[key]
                    current = stroke_set(row["document"])
                    self.assertEqual(len(current), step)
                    self.assertTrue(previous <= current)
                    self.assertEqual(len(current - previous), int(step > 0))
                    self.assertEqual(row["document"], canonical_document({
                        "frame": {"width": 900, "height": 600},
                        "strokes": history["ordered_strokes"][:step],
                    }))
                    self.assertIn({"family": history["family"], "seed": history["seed"],
                                   "step": step}, row["aliases"])
                    previous = current

    def test_all_node_geometry_exports_are_valid_without_coloring(self):
        self.assertEqual(len(self.geometry_rows), len(self.records))
        for row in self.geometry_rows:
            with self.subTest(key=row["key"]):
                self.assertEqual(row["status"], "geometry_ok", row["errors"])
                self.assertFalse(row["coloring_performed"])
                geometry = row["geometry"]
                self.assertFalse(any(edge["virtual"] for edge in geometry["edges"]))
                self.assertEqual(geometry["real_bridge_edge_ids"], [])
                # All strokes join the connected frame; Euler uses one component.
                self.assertEqual(len(geometry["vertices"]) - len(geometry["edges"])
                                 + len(geometry["faces"]), 2)
                for x, y in geometry["vertices"]:
                    self.assertGreaterEqual(x, 0)
                    self.assertLessEqual(x, 900)
                    self.assertGreaterEqual(y, 0)
                    self.assertLessEqual(y, 600)

    def test_guillotine_steps_are_exact_single_cell_splits(self):
        for history in self.holdout["histories"]:
            if history["family"] != GUILLOTINE:
                continue
            cells = [(0, 0, 900, 600)]
            for step, stroke in enumerate(history["ordered_strokes"], 1):
                (ax, ay), (bx, by) = stroke["a"], stroke["b"]
                matching = []
                for i, (x0, y0, x1, y1) in enumerate(cells):
                    if ax == bx and x0 < ax < x1 and {ay, by} == {y0, y1}:
                        matching.append((i, [(x0, y0, ax, y1), (ax, y0, x1, y1)]))
                    elif ay == by and y0 < ay < y1 and {ax, bx} == {x0, x1}:
                        matching.append((i, [(x0, y0, x1, ay), (x0, ay, x1, y1)]))
                with self.subTest(history=history["id"], step=step):
                    self.assertEqual(len(matching), 1)
                    i, children = matching[0]
                    cells[i:i + 1] = children
                    self.assertEqual(len(self.geometries[history["prefix_keys"][step]]["faces"]),
                                     step + 2)

    def test_chords_are_complete_distinct_and_include_crossing_arrangements(self):
        crossing_histories = 0
        for history in self.holdout["histories"]:
            if history["family"] != CHORDS:
                continue
            left, right = [], []
            for stroke in history["ordered_strokes"]:
                self.assertEqual(stroke["a"][0], 0)
                self.assertEqual(stroke["b"][0], 900)
                for endpoint in (stroke["a"], stroke["b"]):
                    self.assertIs(type(endpoint[1]), int)
                    self.assertTrue(20 <= endpoint[1] <= 580)
                left.append(stroke["a"][1])
                right.append(stroke["b"][1])
            self.assertEqual(len(set(left)), STEPS)
            self.assertEqual(len(set(right)), STEPS)
            # Opposite boundary orders prove a proper interior crossing without
            # trusting the engine's face construction or a coloring result.
            crossing = any((left[i] - left[j]) * (right[i] - right[j]) < 0
                           for i in range(STEPS) for j in range(i))
            crossing_histories += crossing
        self.assertEqual(crossing_histories, len(SEEDS))

    def test_deterministic_generation_and_honest_scope_metadata(self):
        self.assertEqual(self.holdout, build_holdout())
        generation = self.holdout["generation"]
        self.assertFalse(generation["outcome_filtering"])
        self.assertFalse(generation["propagation_performed"])
        self.assertFalse(generation["oracle_performed"])
        self.assertFalse(generation["chords"]["general_position_assumed"])
        self.assertIn("not graph isomorphism", generation["deduplication"])
        self.assertIn("not independent samples", generation["scope"])


if __name__ == "__main__":
    unittest.main()

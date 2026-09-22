"""Independently check the finite mask universe and every representative prefix."""

from collections import Counter
from math import comb
import unittest

from scripts.exhaustive_grid_subsets import build_grid_inventory, unit_segments


class ExhaustiveGridSubsetTests(unittest.TestCase):
    """No naming policy or exact-coloring oracle is invoked by these tests."""

    @classmethod
    def setUpClass(cls):
        """Generate the full declared 3x3 family once for count/prefix audits."""
        cls.full = build_grid_inventory()

    def test_three_by_three_complete_counts_match_binomial_universe(self):
        report = self.full
        self.assertEqual(report["status"], "complete")
        self.assertTrue(report["generation_complete"])
        self.assertEqual(len(report["unit_segments"]), 12)
        self.assertEqual(len(report["records"]), 4096)
        self.assertEqual(len(report["histories"]), 4096)
        self.assertEqual(report["summary"]["history_prefix_references"], 4096 + 12 * 2048)
        self.assertEqual(report["summary"]["histories_by_added_segments"],
                         {str(k): comb(12, k) for k in range(13)})
        self.assertEqual([row["subset_mask"] for row in report["records"]], list(range(4096)))
        self.assertEqual((report["policy_runs"], report["oracle_runs"]), (0, 0))
        self.assertEqual(report["geometry_export_status"], "not_run")

    def test_all_prefixes_exactly_add_one_selected_segment_in_fixed_order(self):
        records = {row["subset_mask"]: row for row in self.full["records"]}
        history_by_key = {row["key"]: row for row in self.full["histories"]}
        references = Counter()
        for history in self.full["histories"]:
            mask = history["subset_mask"]
            indices = [index for index in range(12) if mask & (1 << index)]
            self.assertEqual([step["unit_segment_index"] for step in history["steps"]], indices)
            self.assertEqual(history["depth"], len(indices))
            self.assertEqual(history["prefix_masks"][0], 0)
            self.assertEqual(history["prefix_masks"][-1], mask)
            cumulative = 0
            for step, index in enumerate(indices, 1):
                cumulative += 1 << index
                self.assertEqual(history["prefix_masks"][step], cumulative)
            for step, prefix_mask in enumerate(history["prefix_masks"]):
                record = records[prefix_mask]
                self.assertEqual(history["prefix_keys"][step], record["key"])
                self.assertEqual(history_by_key[history["prefix_history_keys"][step]]["subset_mask"], prefix_mask)
                self.assertLessEqual(prefix_mask, mask)
                references[(record["key"], history["key"], step)] += 1
        aliases = Counter((record["key"], alias["history"], alias["step"])
                          for record in records.values() for alias in record["aliases"])
        self.assertEqual(aliases, references)
        self.assertTrue(all(count == 1 for count in references.values()))

    def test_exact_segment_universe_and_document_coordinates(self):
        expected = [((x, y), (x, y + 1)) for x in (1, 2) for y in (0, 1, 2)]
        expected += [((x, y), (x + 1, y)) for y in (1, 2) for x in (0, 1, 2)]
        self.assertEqual(list(unit_segments(3, 3)), expected)
        for mask, record in enumerate(self.full["records"]):
            wanted = {tuple(sorted(((a[0] * 300, a[1] * 200), (b[0] * 300, b[1] * 200))))
                      for i, (a, b) in enumerate(expected) if mask & (1 << i)}
            actual = {tuple(sorted((tuple(s["a"]), tuple(s["b"])))) for s in record["document"]["strokes"]}
            self.assertEqual(actual, wanted)
            self.assertEqual(len(actual), mask.bit_count())

    def test_bridges_disconnected_segment_and_closed_island_are_not_filtered(self):
        # Segment 1 has both ends strictly inside the frame. The central square
        # consists of segments 1, 4, 7, 10 and is disconnected from the frame.
        by_mask = {row["subset_mask"]: row for row in self.full["records"]}
        for mask in (1, 1 << 1, sum(1 << index for index in (1, 4, 7, 10))):
            self.assertIn(mask, by_mask)
        self.assertEqual(len(by_mask[1 << 1]["document"]["strokes"]), 1)
        island = by_mask[sum(1 << index for index in (1, 4, 7, 10))]
        self.assertEqual(len(island["document"]["strokes"]), 4)

    def test_cap_has_explicit_first_unvisited_mask_and_no_missing_prefix(self):
        for cap in (0, 1, 17, 4095):
            report = build_grid_inventory(subset_limit=cap)
            self.assertEqual(report["status"], "unknown")
            self.assertFalse(report["generation_complete"])
            self.assertEqual(report["truncation"]["next_mask"], cap)
            self.assertEqual(len(report["records"]), cap)
            keys = {row["key"] for row in report["records"]}
            self.assertTrue(all(set(h["prefix_keys"]) <= keys for h in report["histories"]))

    def test_smaller_grids_have_the_declared_full_subset_count(self):
        for width, height in ((1, 1), (1, 3), (2, 2), (2, 3)):
            count = (width - 1) * height + (height - 1) * width
            report = build_grid_inventory(width, height, 1 << count)
            self.assertTrue(report["generation_complete"])
            self.assertEqual(len(report["records"]), 1 << count)
            expected_references = 1 if count == 0 else (1 << count) + count * (1 << (count - 1))
            self.assertEqual(report["summary"]["history_prefix_references"], expected_references)

    def test_invalid_inputs_are_rejected_without_coercion(self):
        for parameters in ((0, 3, 1), (True, 3, 1), (3, 2.5, 1), (3, 3, -1), (3, 3, True)):
            with self.subTest(parameters=parameters), self.assertRaises(ValueError):
                build_grid_inventory(*parameters)


if __name__ == "__main__":
    unittest.main()

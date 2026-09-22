"""Independently check finite history coverage, geometry and truncation scope."""

from collections import Counter
from copy import deepcopy
from functools import lru_cache
import gzip
import json
from math import comb
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import exhaustive_rectangular_histories as generator
from scripts.current_corpus import stroke_set_key
from scripts.validate_global_restart import export_geometries


@lru_cache(maxsize=None)
def independent_history_count(width, height, cuts):
    """Count by the first split and interleaved subrectangle histories.

    This recurrence does not iterate the generator's cell states. Once the
    first cut is fixed, left/right (or bottom/top) histories are independent;
    choose their lengths and their binomially many order-preserving shuffles.
    """
    if cuts == 0:
        return 1
    if cuts >= width * height:
        return 0
    total = 0
    for first_width in range(1, width):
        for left_cuts in range(cuts):
            total += (comb(cuts - 1, left_cuts)
                      * independent_history_count(first_width, height, left_cuts)
                      * independent_history_count(width - first_width, height,
                                                  cuts - 1 - left_cuts))
    for first_height in range(1, height):
        for lower_cuts in range(cuts):
            total += (comb(cuts - 1, lower_cuts)
                      * independent_history_count(width, first_height, lower_cuts)
                      * independent_history_count(width, height - first_height,
                                                  cuts - 1 - lower_cuts))
    return total


class ExhaustiveRectangularHistoryTests(unittest.TestCase):
    """Keep generation correctness separate from any coloring claim."""

    def test_full_counts_match_first_cut_shuffle_recurrence(self):
        """Independently counted stopping lengths detect omitted/repeated branches."""
        for width, height, depth in ((1, 1, 3), (1, 4, 4), (2, 2, 4), (3, 3, 5)):
            with self.subTest(width=width, height=height, depth=depth):
                rows = list(generator.iter_histories(width, height, depth))
                counts = Counter(row["depth"] for row in rows)
                self.assertEqual([counts[k] for k in range(depth + 1)],
                                 [independent_history_count(width, height, k)
                                  for k in range(depth + 1)])
                self.assertEqual(len(rows), len({row["key"] for row in rows}))
        self.assertEqual([independent_history_count(3, 3, k) for k in range(6)],
                         [1, 4, 20, 96, 424, 1600])

    def test_certificates_replay_every_integer_cell_and_prefix(self):
        """Rebuild partitions using literal split formulas and unit-square coverage."""
        rows = list(generator.iter_histories(3, 3, 4))
        by_key = {row["key"]: row for row in rows}
        all_squares = {(x, y) for x in range(3) for y in range(3)}
        for row in rows:
            cells = {(0, 0, 3, 3)}
            self.assertEqual(len(row["prefix_keys"]), row["depth"] + 1)
            self.assertEqual(row["prefix_history_keys"][-1], row["key"])
            self.assertEqual(row["parent_history_key"],
                             row["prefix_history_keys"][-2] if row["depth"] else None)
            for k, event in enumerate(row["steps"], 1):
                cell = tuple(event["cell"])
                self.assertIn(cell, cells)
                x0, y0, x1, y1 = cell
                coordinate = event["coordinate"]
                if event["axis"] == "vertical":
                    self.assertTrue(x0 < coordinate < x1)
                    children = {(x0, y0, coordinate, y1), (coordinate, y0, x1, y1)}
                    segment = [[coordinate, y0], [coordinate, y1]]
                else:
                    self.assertEqual(event["axis"], "horizontal")
                    self.assertTrue(y0 < coordinate < y1)
                    children = {(x0, y0, x1, coordinate), (x0, coordinate, x1, y1)}
                    segment = [[x0, coordinate], [x1, coordinate]]
                self.assertEqual({tuple(c) for c in event["children"]}, children)
                self.assertEqual(event["grid_segment"], segment)
                self.assertEqual(event["step"], k)
                cells.remove(cell)
                cells.update(children)
                prefix = by_key[row["prefix_history_keys"][k]]
                self.assertEqual(cells, {tuple(c) for c in prefix["cells"]})
                self.assertEqual(prefix["geometry_key"], row["prefix_keys"][k])
            self.assertEqual(cells, {tuple(c) for c in row["cells"]})
            covered = Counter((x, y) for x0, y0, x1, y1 in cells
                              for x in range(x0, x1) for y in range(y0, y1))
            self.assertEqual(set(covered), all_squares)
            self.assertEqual(set(covered.values()), {1})
            self.assertEqual(len(cells), row["depth"] + 1)

    def test_geometry_only_dedup_keeps_all_ordered_references(self):
        """Four full 2x2 histories give two segmented stroke sets, not one."""
        report = generator.build_inventory(2, 2, 3)
        self.assertTrue(report["generation_complete"])
        self.assertEqual(report["summary"]["histories"], 11)
        self.assertEqual(report["summary"]["distinct_geometries"], 9)
        self.assertEqual(report["summary"]["history_prefix_references"], 33)
        expected_aliases = Counter()
        for row in report["histories"]:
            for step, key in enumerate(row["prefix_keys"]):
                expected_aliases[(key, row["key"], step, row["prefix_history_keys"][step])] += 1
        actual_aliases = Counter()
        for record in report["records"]:
            self.assertEqual(stroke_set_key(record["document"]), record["key"])
            for alias in record["aliases"]:
                actual_aliases[(record["key"], alias["history"], alias["step"],
                                alias["prefix_history_key"])] += 1
        self.assertEqual(actual_aliases, expected_aliases)
        finals = [row for row in report["histories"] if row["depth"] == 3]
        self.assertEqual(len({row["geometry_key"] for row in finals}), 2)
        self.assertEqual(len({tuple(tuple(c) for c in row["cells"]) for row in finals}), 1)

    def test_scaled_documents_pass_existing_geometry_only_exporter(self):
        """Actual Node integration verifies frame, topology and bounded face counts."""
        report = generator.build_inventory(2, 2, 3)
        exported = export_geometries(report["records"])
        for record, row in zip(report["records"], exported):
            self.assertEqual(record["document"]["frame"], {"width": 900, "height": 600})
            self.assertEqual(row["status"], "geometry_ok", row.get("errors"))
            self.assertFalse(row["coloring_performed"])
            self.assertEqual(len(row["geometry"]["faces"]),
                             len(record["document"]["strokes"]) + 2)
            self.assertEqual(row["geometry"]["real_bridge_edge_ids"], [])
        first_three_grid = next(row for row in generator.iter_histories(3, 3, 1)
                                if row["depth"] == 1)
        self.assertEqual(first_three_grid["document"]["strokes"],
                         [{"a": [300, 0], "b": [300, 600]}])

    def test_resource_cap_is_unknown_and_keeps_exact_enumeration_prefix(self):
        """An exactly sufficient cap completes; a smaller one never passes."""
        all_rows = list(generator.iter_histories(2, 2, 3))
        for limit in (1, 2, 3, 7, 10):
            with self.subTest(limit=limit):
                report = generator.build_inventory(2, 2, 3, history_limit=limit)
                self.assertEqual(report["status"], "unknown")
                self.assertFalse(report["generation_complete"])
                self.assertEqual(len(report["histories"]), limit)
                self.assertEqual([row["key"] for row in report["histories"]],
                                 [row["key"] for row in all_rows[:limit]])
                self.assertEqual(report["truncation"]["next_history_key"], all_rows[limit]["key"])
                self.assertEqual(report["summary"]["complete_depths"],
                                 list(range(all_rows[limit]["depth"])))
        report = generator.build_inventory(2, 2, 3, history_limit=11)
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["summary"]["complete_depths"], [0, 1, 2, 3])
        with self.assertRaises(generator.GenerationIncomplete):
            list(generator.iter_histories(2, 2, 3, history_limit=1))

    def test_exported_mutation_does_not_change_generation(self):
        """Caller-owned JSON containers cannot corrupt descendants or identities."""
        expected = list(generator.iter_histories(2, 2, 2))
        stream = generator.iter_histories(2, 2, 2)
        root = next(stream)
        root["key"] = "changed"
        root["geometry_key"] = "changed"
        root["cells"].clear()
        root["document"]["strokes"].append({"a": [0, 0], "b": [1, 1]})
        self.assertEqual(list(stream), expected[1:])

    def test_parameter_validation(self):
        """Invalid finite bounds are input errors, not empty complete families."""
        for field in ("width", "height", "max_cuts", "history_limit"):
            for value in (True, 1.5, None, "3", -1):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    list(generator.iter_histories(**{field: value}))
        for field in ("width", "height", "history_limit"):
            with self.assertRaises(ValueError):
                generator.build_inventory(**{field: 0})
        self.assertEqual(generator.build_inventory(max_cuts=0)["summary"]["histories"], 1)

    def test_generation_has_no_policy_or_geometry_export_calls(self):
        """Only separate tests and later experiments may call geometry or solvers."""
        with patch("scripts.validate_global_restart.export_geometries", side_effect=AssertionError), \
                patch("scripts.validate_global_restart.restart_line_names", side_effect=AssertionError):
            report = generator.enumerate_inventory(1, 2, 1)
        self.assertEqual(report["policy_runs"], 0)
        self.assertEqual(report["oracle_runs"], 0)
        self.assertEqual(report["geometry_export_status"], "not_run")

    def test_source_changes_invalidate_completion(self):
        """A source race cannot leave a complete provenance claim."""
        with patch.object(generator, "_source_hashes", side_effect=[{"a": "old"}, {"a": "new"}]):
            report = generator.build_inventory(1, 1, 0)
        self.assertEqual(report["status"], "unknown")
        self.assertFalse(report["sources_unchanged"])
        self.assertEqual(report["summary"]["complete_depths"], [])

    def test_cli_gzip_unknown_exit_and_overwrite_refusal(self):
        """Explicit output evidence preserves incomplete status and existing bytes."""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "generation.json.gz"
            summary = Path(directory) / "summary.json"
            args = ["--width", "2", "--height", "2", "--max-cuts", "3",
                    "--history-limit", "2", "--output", str(output), "--summary", str(summary)]
            with patch("builtins.print"):
                self.assertEqual(generator.main(args), 2)
            report = json.loads(gzip.decompress(output.read_bytes()))
            self.assertEqual(report["status"], "unknown")
            self.assertEqual(json.loads(summary.read_text())["summary"], report["summary"])
            before = deepcopy(output.read_bytes())
            with self.assertRaises(SystemExit) as error, patch("sys.stderr"):
                generator.main(args)
            self.assertEqual(error.exception.code, 2)
            self.assertEqual(output.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

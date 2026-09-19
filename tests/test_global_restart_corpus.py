"""Bounded corpus/restart reporting tests, independent of full benchmark runs."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.validate_global_restart import (
    POLICIES, build_report, canonical_document, digest, main,
    restart_inventory, summarize, write_report,
)


def history(key, paths, initial_cuts=(), symbols=(2,), budget=3):
    """Make an inventory input: old symbols are provenance, never solver inputs.

    Inventory tests need only source cuts. These intentionally tiny old side
    records are not offered as independently certified rectangular tilings.
    """
    return {
        "key": key, "family": "test-history", "seed": None,
        "history_sha256": digest({"key": key, "symbols": symbols}),
        "aliases": [{"key": key, "source": "synthetic-test"}],
        "initial_state": {
            "width": 900, "height": 600,
            "cuts": deepcopy(list(initial_cuts)),
            "sides": [{"id": str(i), "symbol": symbol} for i, symbol in enumerate(symbols)],
        },
        "paths": deepcopy(paths), "max_old_sides": budget,
    }


def corpus(histories=(), statics=()):
    """Supply only the fields used by the restart inventory and smoke runner."""
    return {
        "histories": list(histories), "static_inventory": list(statics),
        "source_sha256": {},
        "summary": {"unique_declared_histories": len(histories),
                    "static_distinct_stroke_sets": len(statics)},
    }


class GlobalRestartCorpusTests(unittest.TestCase):
    """Eight small tests protect geometry continuation and honest summaries."""

    def test_canonical_document_ignores_direction_order_duplicates_and_names(self):
        """Equivalent input strokes share cache input, not inherited coloring."""
        first = {"strokes": [
            {"a": [0, 300], "b": [900, 300]},
            {"a": [450, 0], "b": [450, 300]},
        ], "colors": [99, 99], "names": [[99, 99]], "title": "old-name provenance"}
        original = deepcopy(first)
        second = {"frame": {"width": 900, "height": 600}, "strokes": [
            {"a": [450, 300], "b": [450, 0]},
            {"a": [900, 300], "b": [0, 300]},
            {"a": [0, 300], "b": [900, 300]},
        ]}
        canonical = canonical_document(first)
        self.assertEqual(canonical, canonical_document(second))
        self.assertEqual(set(canonical), {"frame", "strokes"})
        self.assertEqual(len(canonical["strokes"]), 2)
        self.assertEqual(first, original)

    def test_canonical_document_does_not_fill_a_collinear_gap(self):
        """Coarse stroke normalization must not silently add drawing geometry."""
        broken = {"strokes": [
            {"a": [0, 300], "b": [400, 300]},
            {"a": [500, 300], "b": [900, 300]},
        ]}
        joined = {"strokes": [{"a": [0, 300], "b": [900, 300]}]}
        result = canonical_document(broken)
        self.assertEqual(len(result["strokes"]), 2)
        self.assertNotEqual(result, canonical_document(joined))
        self.assertEqual({tuple(point) for edge in result["strokes"] for point in edge.values()},
                         {(0, 300), (400, 300), (500, 300), (900, 300)})

    def test_different_precolors_share_geometry_cache_without_losing_history_maps(self):
        """Every source history keeps every prefix alias after names are erased."""
        base = [[[0, 300], [900, 300]]]
        paths = [[[450, 0], [450, 300]], [[450, 300], [450, 600]]]
        first = history("old-two-three", paths, base, (2, 3), budget=0)
        second = history("old-three-two", paths, base, (3, 2), budget=32)
        records, histories, statics = restart_inventory(corpus([first, second]))
        self.assertEqual(len(records), 3)
        self.assertEqual(len(histories), 2)
        self.assertEqual(statics, [])
        self.assertEqual(histories[0]["prefix_keys"], histories[1]["prefix_keys"])
        self.assertEqual([len(row["prefix_keys"]) for row in histories], [3, 3])
        self.assertNotEqual(histories[0]["original_history_sha256"], histories[1]["original_history_sha256"])
        self.assertEqual([row["local_budget_discarded"] for row in histories], [0, 32])
        self.assertTrue(all(row["initial_precolors_discarded"] for row in histories))
        self.assertEqual(sum(len(record["aliases"]) for record in records), 6)
        self.assertEqual({alias["history"] for record in records for alias in record["aliases"]},
                         {first["key"], second["key"]})

    def test_none_rectangular_start_keeps_explicit_initial_document_but_not_names(self):
        """A nonrectangular precolored seed is geometry, not an empty frame."""
        row = history("old-ring", [[[0, 300], [250, 300]]])
        row["initial_state"] = None
        row["initial_names"] = [[77, 88]]
        row["initial_document"] = {"strokes": [
            {"a": [250, 180], "b": [650, 180]},
            {"a": [650, 180], "b": [650, 420]},
            {"a": [650, 420], "b": [250, 420]},
            {"a": [250, 420], "b": [250, 180]},
        ], "names": [[77, 88]], "colors": [77, 88]}
        original = deepcopy(row)
        records, histories, _ = restart_inventory(corpus([row]))
        by_key = {record["key"]: record for record in records}
        self.assertEqual([len(by_key[key]["document"]["strokes"])
                          for key in histories[0]["prefix_keys"]], [4, 5])
        self.assertTrue(histories[0]["initial_precolors_discarded"])
        self.assertTrue(all(set(record["document"]) == {"frame", "strokes"} for record in records))
        self.assertEqual(row, original)

    def test_all_prefixes_are_generated_despite_an_old_expected_failure(self):
        """Former construction status metadata cannot truncate future geometry."""
        paths = [[[0, 300], [900, 300]], [[300, 0], [300, 300]], [[600, 0], [600, 300]]]
        row = history("continue-after-old-failure", paths)
        row["old_expected_statuses"] = ["split", "blocked", "not-previously-attempted"]
        final_document = {"strokes": [{"a": a, "b": b} for a, b in paths]}
        static = {"key": "same-final-static", "family": "test-static", "document": final_document,
                  "aliases": [{"key": "same-final-static"}], "matching_history_keys": [row["key"]]}
        records, histories, statics = restart_inventory(corpus([row], [static]))
        self.assertEqual(len(records), 4)
        self.assertEqual(len(histories[0]["prefix_keys"]), 4)
        self.assertEqual(histories[0]["prefix_keys"][-1], statics[0]["geometry_key"])
        last = next(record for record in records if record["key"] == statics[0]["geometry_key"])
        self.assertEqual(len(last["document"]["strokes"]), 3)
        self.assertEqual({alias["kind"] for alias in last["aliases"]}, {"history_prefix", "static"})

    def test_failure_then_recovery_does_not_become_all_prefix_success(self):
        """Both initially failing and middle-failing sequences retain recovery."""
        statuses = {"failed": "conflict", "solved": "solved", "solved-before": "solved"}
        records = [{"key": key, "runs": {policy: {"status": status} for policy in POLICIES}}
                   for key, status in statuses.items()]
        histories = [
            {"key": "initial-failure", "family": "synthetic", "prefix_keys": ["failed", "solved"]},
            {"key": "middle-failure", "family": "synthetic", "prefix_keys": ["solved-before", "failed", "solved"]},
        ]
        statics = [{"key": "last-drawing", "geometry_key": "solved"}]
        summaries, results = summarize(records, histories, statics)
        for policy in POLICIES:
            entries = {row["key"]: row for row in results if row["policy"] == policy}
            self.assertFalse(entries["initial-failure"]["all_prefixes_solved"])
            self.assertEqual(entries["initial-failure"]["first_failed_prefix"], 0)
            self.assertEqual(entries["initial-failure"]["solved_again_after_failure"], [1])
            self.assertFalse(entries["middle-failure"]["all_prefixes_solved"])
            self.assertEqual(entries["middle-failure"]["first_failed_prefix"], 1)
            self.assertEqual(entries["middle-failure"]["solved_again_after_failure"], [2])
            summary = next(row for row in summaries if row["policy"] == policy)
            self.assertEqual(summary["history_final_status"], {"solved": 2})
            self.assertEqual(summary["all_prefixes"], {"has_failure": 2})
            self.assertEqual(summary["static_status"], {"solved": 1})

    def test_smoke_report_is_explicit_and_excludes_incomplete_history_coverage(self):
        """A one-drawing smoke run is never reported as a complete history run."""
        tiny = corpus([history("two-prefixes", [[[0, 300], [900, 300]]])])

        def errors_only(records):
            """Avoid invoking any real geometry or naming work in this unit test."""
            return [{"key": row["key"], "status": "geometry_error", "errors": [{"code": "test"}]}
                    for row in records]

        with patch("scripts.validate_global_restart.build_corpus", return_value=tiny), \
                patch("scripts.validate_global_restart.export_geometries", side_effect=errors_only), \
                redirect_stdout(io.StringIO()):
            report = build_report(limit=1)
        self.assertEqual(report["smoke_limit"], 1)
        self.assertEqual(len(report["drawings"]), 1)
        self.assertEqual(report["histories"], [])
        self.assertEqual(report["original_corpus_summary"]["unique_declared_histories"], 1)
        self.assertEqual(report["independent_checks"], 0)
        self.assertTrue(all(row["history_count"] == 0 for row in report["summary"]))

    def test_plain_gzip_and_cli_refuse_overwriting_existing_evidence(self):
        """Temporary outputs exercise exclusivity without touching saved reports."""
        with tempfile.TemporaryDirectory(prefix="fourcolor-restart-test-") as folder:
            for filename in ("report.json", "report.json.gz"):
                with self.subTest(filename=filename):
                    target = Path(folder) / filename
                    report = {"smoke_limit": 1, "summary": []}
                    write_report(target, report)
                    before = target.read_bytes()
                    payload = gzip.decompress(before) if filename.endswith(".gz") else before
                    self.assertEqual(json.loads(payload), report)
                    if filename.endswith(".gz"):
                        self.assertEqual(before[4:8], b"\0\0\0\0")
                        self.assertEqual(before[3] & 8, 0)  # No source-machine filename header.
                    with self.assertRaises(FileExistsError):
                        write_report(target, {"must_not_replace": True})
                    self.assertEqual(target.read_bytes(), before)
                    summary = Path(folder) / (filename + ".summary")
                    with patch("sys.argv", ["validator", "--output", str(target), "--summary", str(summary)]), \
                            patch("scripts.validate_global_restart.build_report") as build, \
                            redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exited:
                        main()
                    self.assertEqual(exited.exception.code, 2)
                    build.assert_not_called()
                    self.assertFalse(summary.exists())
                    self.assertEqual(target.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

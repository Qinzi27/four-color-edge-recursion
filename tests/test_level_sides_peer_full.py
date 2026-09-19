"""Audit optional-level corpus replay without treating unknown depth as failure.

The large report supplies immutable inventory/provenance only. Computations use
six archived diagnostics, three actual formerly unrooted inputs, and tiny
checkpoint batches; no successful result is invented for an untested drawing.
"""

from concurrent.futures import ProcessPoolExecutor
from contextlib import redirect_stdout
from copy import deepcopy
import io
import multiprocessing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fourcolor.level_sides import restart_level_side_names
from scripts import validate_level_sides_peer_full as runner
from tests.test_level_sides_full import native_anchor_keys
from tests.test_relation_frontier_full import stable_evidence


class LevelSidePeerFullRunnerTests(unittest.TestCase):
    """Preserve proofs, coverage and resumability while removing the scope gate."""

    @classmethod
    def setUpClass(cls):
        """Select named archived fixtures, never a new conveniently colored map."""
        cls.previous = runner.read_json(runner.SOURCE)
        cls.diagnostic = runner.read_json(runner.DIAGNOSTIC)
        cls.six_by_key = {row["key"]: row for row in cls.diagnostic["records"]}
        by_key = {row["key"]: row for row in cls.previous["drawings"]}
        cls.six_rows = [by_key[key] for key in sorted(cls.six_by_key)]
        histories = ("construction-free-end", "construction-polyline", "construction-loop")
        cls.unrooted = [next(row for row in cls.previous["drawings"] if any(
            alias.get("history") == history and alias.get("step") == 1
            for alias in row["aliases"])) for history in histories]
        # Include two distinct unranked structures in the Windows-spawn test.
        cls.payloads = [(index, [row], {}) for index, row in enumerate(cls.unrooted[1:])]

    def test_six_cases_reproduce_every_mathematical_field_exactly(self):
        """Only the three explicitly descriptive metadata differences are allowed."""
        part = runner.run_batch((0, self.six_rows, self.six_by_key))
        self.assertEqual(part["diagnostic_exact_reproductions"], 6)
        self.assertEqual(len(part["records"]), 6)
        for row in part["records"]:
            with self.subTest(key=row["key"]):
                archived = self.six_by_key[row["key"]]
                actual = part["detailed_examples"][row["key"]]["outcome"]
                expected = native_anchor_keys(deepcopy(archived["candidate"]))
                expected["policy"], expected["scope"] = actual["policy"], actual["scope"]
                for step in expected["trace"]:
                    step["selection_group"] = "rooted"
                self.assertEqual(runner.json_value(actual), runner.json_value(expected))
                check = deepcopy(archived["candidate_check"])
                check["method"] = row["runs"][runner.POLICY]["verification"]["method"]
                # Restore native integer dart maps before hashing raw certificates.
                expected_compact = runner.compact_candidate(expected, check)
                self.assertEqual(runner.json_value(stable_evidence(row["runs"][runner.POLICY])),
                                 runner.json_value(expected_compact))

    def test_actual_unrooted_shapes_are_colored_and_independently_checked(self):
        """Dangling line, bent separator and isolated loop no longer stop startup."""
        before = deepcopy(self.unrooted)
        exports = runner.export_geometries(self.unrooted)
        for saved, exported in zip(self.unrooted, exports):
            with self.subTest(key=saved["key"]):
                geometry = exported["geometry"]
                old = restart_level_side_names(geometry)
                self.assertEqual(old["status"], "outside_scope")
                actual = runner.restart_level_peer_names(geometry)
                check = runner.verify_run(geometry, actual)
                self.assertTrue(check["passed"])
                self.assertIn(actual["status"], ("solved", "conflict"))
                self.assertNotEqual(actual["status"], "outside_scope")
                self.assertEqual(actual["unranked_mothers"], old["unranked_mothers"])
                self.assertTrue(actual["unranked_mothers"])
                for name in actual["unranked_mothers"]:
                    self.assertIsNone(actual["levels"][name]["level"])
                self.assertEqual(actual["backtracks"], 0)
                self.assertFalse(actual["old_colors_read"])
                self.assertEqual(len(actual["propagation_phases"]), actual["choices"] + 1)
                # These three archived fixtures were actually rerun first;
                # successful four-name legality is checked rather than assumed.
                self.assertEqual(actual["status"], "solved")
                self.assertTrue(check["final_legality"]["passed"])
                if actual["trace"]:
                    self.assertEqual({step["selection_group"] for step in actual["trace"]},
                                     {"unranked-peer"})
        self.assertEqual(self.unrooted, before)

    def test_spawn_and_serial_workers_produce_identical_certificates(self):
        """Process scheduling may change elapsed time, never mathematical evidence."""
        serial = [runner.run_batch(payload) for payload in self.payloads]
        with ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context("spawn")) as pool:
            parallel = list(pool.map(runner.run_batch, self.payloads))
        self.assertEqual(stable_evidence(serial), stable_evidence(parallel))
        self.assertEqual(sum(len(part["records"]) for part in parallel), 2)
        originals = {row["key"]: row for row in self.unrooted}
        for part in parallel:
            self.assertIsNone(part["least_outside_scope"])
            for row in part["records"]:
                self.assertTrue(row["runs"][runner.POLICY]["verification"]["passed"])
                self.assertEqual(row["runs"][runner.BASELINE],
                                 originals[row["key"]]["runs"][runner.BASELINE])

    def test_single_map_resume_never_reruns_a_worker(self):
        """Loading a verified checkpoint cannot silently recolor the saved input."""
        with tempfile.TemporaryDirectory(prefix="fourcolor-peer-resume-") as directory:
            checkpoint = Path(directory) / "checkpoint"
            with redirect_stdout(io.StringIO()):
                original = runner.build_report(runner.SOURCE, runner.DIAGNOSTIC, checkpoint,
                                               workers=1, batch_size=1, limit=1)
            with patch.object(runner, "run_batch", side_effect=AssertionError("resume reran worker")), \
                    redirect_stdout(io.StringIO()):
                resumed = runner.build_report(runner.SOURCE, runner.DIAGNOSTIC, checkpoint,
                                              workers=1, batch_size=1, limit=1, resume=True)
            self.assertEqual(runner.json_value(stable_evidence(original)),
                             runner.json_value(stable_evidence(resumed)))
            self.assertFalse(original["execution"]["resumed"])
            self.assertTrue(resumed["execution"]["resumed"])
            self.assertFalse(resumed["full_corpus_run"])
            self.assertFalse(resumed["baseline_newly_rerun"])
            self.assertEqual(resumed["smoke_limit"], 1)
            self.assertEqual(resumed["independent_checks"], 1)

    def test_resume_rejects_manifest_tampering(self):
        """Source, code, selection and policy are bound before any resumed work."""
        with tempfile.TemporaryDirectory(prefix="fourcolor-peer-manifest-") as directory:
            checkpoint = Path(directory) / "checkpoint"
            with redirect_stdout(io.StringIO()):
                runner.build_report(runner.SOURCE, runner.DIAGNOSTIC, checkpoint,
                                    workers=1, batch_size=1, limit=1)
            path = checkpoint / "manifest.json"
            real_read = runner.read_json
            genuine = real_read(path)
            for field in ("source", "diagnostic", "code", "policy", "keys", "batch-size"):
                with self.subTest(field=field):
                    changed = deepcopy(genuine)
                    if field == "source":
                        changed["source_evidence"]["sha256"] = "0" * 64
                    elif field == "diagnostic":
                        changed["diagnostic_evidence"]["sha256"] = "0" * 64
                    elif field == "code":
                        changed["source_sha256"][next(iter(changed["source_sha256"]))] = "0" * 64
                    elif field == "policy":
                        changed["policy"] = "not-the-frozen-policy"
                    elif field == "keys":
                        changed["selected_keys"] = ["not-a-real-key"]
                    else:
                        changed["batch_size"] = 2

                    def changed_read(filename):
                        """Mock only one read; preserve all actual evidence files."""
                        return deepcopy(changed) if Path(filename) == path else real_read(filename)

                    with patch.object(runner, "read_json", side_effect=changed_read), \
                            patch.object(runner, "run_batch", side_effect=AssertionError("worker called")):
                        with self.assertRaisesRegex(AssertionError, "checkpoint"):
                            runner.build_report(runner.SOURCE, runner.DIAGNOSTIC, checkpoint,
                                                workers=1, batch_size=1, limit=1, resume=True)

    def test_resume_rejects_part_checksum_tampering(self):
        """Correct manifest identity cannot authorize corrupted checkpoint bytes."""
        with tempfile.TemporaryDirectory(prefix="fourcolor-peer-checksum-") as directory:
            checkpoint = Path(directory) / "checkpoint"
            with redirect_stdout(io.StringIO()):
                runner.build_report(runner.SOURCE, runner.DIAGNOSTIC, checkpoint,
                                    workers=1, batch_size=1, limit=1)
            path = checkpoint / "part-00000.json.gz.sha256.json"
            real_read = runner.read_json
            changed = real_read(path)
            changed["sha256"] = "0" * 64

            def changed_read(filename):
                """Substitute the invalid checksum without overwriting real files."""
                return deepcopy(changed) if Path(filename) == path else real_read(filename)

            with patch.object(runner, "read_json", side_effect=changed_read), \
                    patch.object(runner, "run_batch", side_effect=AssertionError("worker called")):
                with self.assertRaisesRegex(AssertionError, "checksum"):
                    runner.build_report(runner.SOURCE, runner.DIAGNOSTIC, checkpoint,
                                        workers=1, batch_size=1, limit=1, resume=True)

    def test_inventory_and_summary_keep_all_prefix_denominators(self):
        """A final recovery does not erase an earlier failed construction prefix."""
        rows = runner.validate_inventory(self.previous)
        self.assertEqual(len(rows), 7069)
        self.assertEqual(len(self.previous["histories"]), 363)
        self.assertEqual(sum(len(h["prefix_keys"]) for h in self.previous["histories"]), 7678)
        self.assertEqual(len(self.previous["static_inputs"]), 302)
        statuses = dict(zip("abcde", ("solved", "conflict", "solved", "solved", "solved")))
        records = [{"key": key, "cohorts": [runner.EXISTING], "runs": {
            runner.BASELINE: {"status": "conflict" if key == "e" else "solved"},
            runner.POLICY: {"status": value}}} for key, value in statuses.items()]
        histories = [{"key": "recovery", "cohort": runner.EXISTING, "prefix_keys": list("abcd")}]
        statics = [{"key": key, "cohort": runner.EXISTING, "geometry_key": key} for key in "bde"]
        summaries, history_results, pairs = runner.summarize(records, histories, statics)
        candidate = next(row for row in summaries if row["cohort"] == "combined"
                         and row["policy"] == runner.POLICY)
        self.assertEqual(candidate["distinct_drawings"], 5)
        self.assertEqual(candidate["statuses"], {"solved": 4, "conflict": 1})
        self.assertEqual(candidate["history_prefix_references"], 4)
        self.assertEqual(candidate["all_prefixes_solved"], 0)
        self.assertEqual(candidate["histories_with_conflict"], 1)
        self.assertEqual(candidate["histories_with_outside_scope"], 0)
        self.assertEqual(candidate["history_final_status"], {"solved": 1})
        self.assertEqual(candidate["static_status"], {"conflict": 1, "solved": 2})
        trajectory = next(row for row in history_results if row["policy"] == runner.POLICY)
        self.assertEqual(trajectory["statuses"], [statuses[key] for key in "abcd"])
        self.assertEqual(trajectory["first_conflict_prefix"], 1)
        self.assertEqual(trajectory["recoveries"], [{"prefix": 2, "from": "conflict"}])
        comparison = next(row for row in pairs if row["cohort"] == "combined")
        self.assertFalse(comparison["baseline_newly_rerun"])
        self.assertEqual(sum(row["count"] for row in comparison["status_transitions"]), 5)
        self.assertEqual(comparison["distinct_drawings"]["regressed"], 1)
        self.assertEqual(comparison["distinct_drawings"]["improved"], 1)
        self.assertEqual(comparison["history_final"]["both_solved"], 1)
        with self.assertRaises(KeyError):
            runner.summarize(records[:2], histories, statics)

    def test_changed_certificate_and_missing_geometry_are_rejected(self):
        """Neither identical status nor an incomplete geometry export is enough."""
        saved = self.six_rows[0]
        altered = {saved["key"]: deepcopy(self.six_by_key[saved["key"]])}
        altered[saved["key"]]["candidate"]["trace"][0]["symbol"] = 99
        with self.assertRaisesRegex(AssertionError, "mathematical certificate"):
            runner.run_batch((0, [saved], altered))
        with patch.object(runner, "export_geometries", return_value=[]):
            with self.assertRaisesRegex(AssertionError, "dropped inputs"):
                runner.run_batch(self.payloads[0])


if __name__ == "__main__":
    unittest.main()

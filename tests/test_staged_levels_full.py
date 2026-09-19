"""Test full-corpus v3 orchestration using a small, predeclared set of maps.

Large archives supply inventory and provenance only; these unit tests do not
claim a new full rerun. Synthetic conflicts below test certificate retention,
not mathematical failure of any real map.
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

from scripts import validate_staged_levels_full as runner
from scripts.validate_frontier_restart import json_value
from tests.test_relation_frontier_full import stable_evidence


class StagedLevelsFullRunnerTests(unittest.TestCase):
    """Initialization changes may alter paths, but never coverage or provenance."""

    @classmethod
    def setUpClass(cls):
        """Select old diagnostics before observing any candidate result."""
        cls.previous = runner.read_json(runner.SOURCE)
        cls.diagnostic = runner.read_json(runner.DIAGNOSTIC)
        cls.rows = runner.validate_inventory(cls.previous)
        cls.six_keys = {row["key"] for row in cls.diagnostic["records"]}
        cls.old_failure_keys = {row["key"] for row in cls.rows
                                if row["runs"][runner.BASELINE]["status"] != "solved"}
        cls.diagnostic_keys = cls.six_keys | cls.old_failure_keys
        cls.diagnostic_rows = [row for row in cls.rows if row["key"] in cls.diagnostic_keys]
        cls.small = sorted(cls.rows, key=lambda row: (row["face_count"], row["key"]))[:2]

    def test_inventory_keeps_every_geometry_prefix_and_static_reference(self):
        """Shared histories do not inflate or shrink unique-map denominators."""
        self.assertEqual(len(self.rows), 7069)
        self.assertEqual(len(self.previous["histories"]), 363)
        self.assertEqual(sum(len(h["prefix_keys"]) for h in self.previous["histories"]), 7678)
        self.assertEqual(len(self.previous["static_inputs"]), 302)
        self.assertEqual(len(self.six_keys), 6)
        self.assertEqual(len(self.old_failure_keys), 1)
        self.assertEqual(len(self.diagnostic_keys), 7)

    def test_seven_diagnostics_are_freshly_checked_without_old_colors(self):
        """Old paths need not reproduce; every newly obtained path must verify."""
        before = deepcopy(self.diagnostic_rows)
        real_algorithm = runner.restart_staged_level_names
        with patch.object(runner, "restart_staged_level_names", wraps=real_algorithm) as observed:
            piece = runner.run_batch((0, self.diagnostic_rows, self.diagnostic_keys))
        self.assertEqual(len(observed.call_args_list), 7)
        self.assertEqual(piece["diagnostics_checked"], 7)
        self.assertEqual(set(piece["detailed_examples"]), self.diagnostic_keys)
        for invocation in observed.call_args_list:
            self.assertEqual(len(invocation.args), 1)
            self.assertEqual(invocation.kwargs, {})
            self.assertNotIn("runs", invocation.args[0])
            self.assertNotIn("colors", invocation.args[0])
        originals = {row["key"]: row for row in before}
        for row in piece["records"]:
            candidate = row["runs"][runner.POLICY]
            self.assertTrue(candidate["verification"]["passed"])
            self.assertEqual(candidate["backtracks"], 0)
            self.assertFalse(candidate["old_colors_read"])
            self.assertEqual(row["runs"][runner.BASELINE], originals[row["key"]]["runs"][runner.BASELINE])
            self.assertEqual(candidate["initial_retained_choice"]["symbol"], 2)
            self.assertEqual(len(candidate["initial_anchors_by_dart"]), 1)
        self.assertEqual(self.diagnostic_rows, before)

    def test_all_conflicts_keep_full_certificates_not_only_batch_minimum(self):
        """Synthetic status changes exercise storage only, never supply evidence."""
        exported = runner.export_geometries(self.small)
        outcomes = [runner.restart_staged_level_names(row["geometry"]) for row in exported]
        # These copies are deliberately synthetic and their checker is mocked;
        # no such output is saved as a mathematical experiment.
        for result in outcomes:
            result["status"] = "conflict"
            result["colors"] = None
        with patch.object(runner, "restart_staged_level_names", side_effect=outcomes), \
                patch.object(runner, "verify_run", return_value={"passed": True}):
            piece = runner.run_batch((0, self.small, set()))
        self.assertEqual(set(piece["detailed_examples"]), {row["key"] for row in self.small})
        self.assertIsNotNone(piece["least_conflict"])
        for detail in piece["detailed_examples"].values():
            self.assertIn("propagation_phases", detail["outcome"])
            self.assertIn("geometry", detail)
            self.assertFalse(detail["is_predeclared_diagnostic"])

    def test_missing_geometry_and_rejected_proof_stop_the_batch(self):
        """Neither a plausible status nor silently omitted input counts as checked."""
        with patch.object(runner, "export_geometries", return_value=[]):
            with self.assertRaisesRegex(AssertionError, "dropped inputs"):
                runner.run_batch((0, self.small, set()))
        with patch.object(runner, "verify_run", return_value={"passed": False}):
            with self.assertRaisesRegex(AssertionError, "independent"):
                runner.run_batch((0, self.small[:1], set()))

    def test_spawn_and_serial_workers_have_identical_mathematical_output(self):
        """Windows-spawn scheduling cannot alter choices or proof commitments."""
        payloads = [(i, [row], {row["key"]}) for i, row in enumerate(self.small)]
        serial = [runner.run_batch(payload) for payload in payloads]
        with ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context("spawn")) as pool:
            parallel = list(pool.map(runner.run_batch, payloads))
        self.assertEqual(stable_evidence(serial), stable_evidence(parallel))

    def test_resume_reuses_hash_matched_checkpoint_without_coloring_again(self):
        """Resume is byte-verified reuse, not another favorable attempt."""
        with tempfile.TemporaryDirectory(prefix="fourcolor-staged-resume-") as directory:
            path = Path(directory) / "checkpoint"
            with redirect_stdout(io.StringIO()):
                original = runner.build_report(runner.SOURCE, runner.DIAGNOSTIC, path,
                                               workers=1, batch_size=1, limit=1)
            with patch.object(runner, "run_batch", side_effect=AssertionError("worker reran")), \
                    redirect_stdout(io.StringIO()):
                resumed = runner.build_report(runner.SOURCE, runner.DIAGNOSTIC, path,
                                              workers=1, batch_size=1, limit=1, resume=True)
            self.assertEqual(json_value(stable_evidence(original)), json_value(stable_evidence(resumed)))
            self.assertFalse(original["full_corpus_run"])
            self.assertFalse(original["baseline_newly_rerun"])
            self.assertEqual(original["independent_checks"], 1)
            self.assertEqual(original["initialization_summary"]["retained_two_count"], 1)

    def test_resume_rejects_changed_manifest_or_saved_checksum(self):
        """Changing a manifest or a checksum never authorizes altered evidence."""
        with tempfile.TemporaryDirectory(prefix="fourcolor-staged-tamper-") as directory:
            checkpoint = Path(directory) / "checkpoint"
            with redirect_stdout(io.StringIO()):
                runner.build_report(runner.SOURCE, runner.DIAGNOSTIC, checkpoint,
                                    workers=1, batch_size=1, limit=1)
            for filename in ("manifest.json", "part-00000.json.gz.sha256.json"):
                with self.subTest(filename=filename):
                    target = checkpoint / filename
                    real_read = runner.read_json
                    changed = real_read(target)
                    if filename == "manifest.json":
                        changed["policy"] = "wrong-policy"
                    else:
                        changed["sha256"] = "0" * 64

                    def altered_read(path):
                        """Alter one read only, preserving actual archived files."""
                        return deepcopy(changed) if Path(path) == target else real_read(path)

                    with patch.object(runner, "read_json", side_effect=altered_read), \
                            patch.object(runner, "run_batch", side_effect=AssertionError("worker called")):
                        with self.assertRaisesRegex(AssertionError, "checkpoint"):
                            runner.build_report(runner.SOURCE, runner.DIAGNOSTIC, checkpoint,
                                                workers=1, batch_size=1, limit=1, resume=True)

    def test_source_hash_set_extends_all_frozen_v2_sources(self):
        """The new rule document is frozen along with producer and proof checker."""
        hashes = runner.source_hashes()
        self.assertEqual({name: hashes[name] for name in self.previous["source_sha256"]},
                         self.previous["source_sha256"])
        self.assertEqual(set(hashes) - set(self.previous["source_sha256"]), set(runner.NEW_SOURCES))

    def test_summary_reports_regression_and_recovered_history_separately(self):
        """A successful final drawing must not conceal a failed earlier prefix."""
        records = [{"key": key, "cohorts": [runner.EXISTING], "runs": {
            runner.BASELINE: {"status": "conflict" if key == "d" else "solved"},
            runner.POLICY: {"status": "conflict" if key == "b" else "solved"}}} for key in "abcd"]
        histories = [{"key": "recovered", "cohort": runner.EXISTING, "prefix_keys": list("abc")}]
        statics = [{"key": "static", "cohort": runner.EXISTING, "geometry_key": "d"}]
        summary, trajectories, comparisons = runner.summarize(records, histories, statics)
        candidate = next(row for row in summary if row["cohort"] == "combined" and row["policy"] == runner.POLICY)
        self.assertEqual(candidate["statuses"], {"solved": 3, "conflict": 1})
        self.assertEqual(candidate["all_prefixes_solved"], 0)
        self.assertEqual(candidate["history_final_status"], {"solved": 1})
        self.assertEqual(candidate["history_prefix_references"], 3)
        trace = next(row for row in trajectories if row["policy"] == runner.POLICY)
        self.assertEqual(trace["recoveries"], [{"prefix": 2, "from": "conflict"}])
        pair = next(row for row in comparisons if row["cohort"] == "combined")
        self.assertEqual(pair["regression_keys"], ["b"])
        self.assertEqual(pair["distinct_drawings"]["regressed"], 1)
        self.assertEqual(pair["distinct_drawings"]["improved"], 1)
        with self.assertRaises(KeyError):
            runner.summarize(records[:2], histories, statics)


if __name__ == "__main__":
    unittest.main()

"""Full-inventory runner integrity, exercised with small actual computations.

The archived 7,069 drawings are read to verify coverage only. Tiny geometry
batches, six previously archived certificates, and single-map checkpoints
exercise the runner without disguising out-of-scope geometry as a conflict.
"""

from concurrent.futures import ProcessPoolExecutor
from contextlib import redirect_stdout
from copy import deepcopy
import io
import multiprocessing
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import validate_level_sides_full as runner
from tests.test_relation_frontier_full import inventory_projection, stable_evidence


def native_anchor_keys(value):
    """Restore documented integer dart maps before hashing archived raw output.

    The shared digest sorts JSON keys; native integer order differs from the
    lexicographic order after a JSON round trip. Reconstruct only known anchor
    maps, leaving all mathematical content and unrelated string IDs untouched.
    """
    if isinstance(value, list):
        return [native_anchor_keys(item) for item in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            item = native_anchor_keys(item)
            if key in ("anchors_by_dart", "initial_anchors_by_dart", "hall_input_anchors"):
                item = {int(dart): allowed for dart, allowed in item.items()}
            result[key] = item
        return result
    return value


class LevelSideFullRunnerTests(unittest.TestCase):
    """One attempt per map, fixed evidence, and complete accounting are required."""

    @classmethod
    def setUpClass(cls):
        """Load archived inputs once; choose tiny worker fixtures by size/key."""
        cls.previous = runner.read_json(runner.SOURCE)
        cls.diagnostic = runner.read_json(runner.DIAGNOSTIC)
        cls.six_by_key = {row["key"]: row for row in cls.diagnostic["records"]}
        cls.small = sorted(cls.previous["drawings"], key=lambda row: (
            row["face_count"], len(row["document"]["strokes"]), row["key"]))[:3]
        cls.payloads = [(index, [row], {}) for index, row in enumerate(cls.small)]
        source_by_key = {row["key"]: row for row in cls.previous["drawings"]}
        cls.six_rows = [source_by_key[key] for key in sorted(cls.six_by_key)]

    def test_inventory_preserves_every_unique_map_and_history_reference(self):
        """Full coverage is a separate claim from solved or in-scope counts."""
        rows = runner.validate_inventory(self.previous)
        self.assertEqual(len(rows), 7069)
        self.assertEqual([row["key"] for row in rows], sorted({row["key"] for row in rows}))
        self.assertEqual(len(self.previous["histories"]), 363)
        self.assertEqual(sum(len(row["prefix_keys"]) for row in self.previous["histories"]), 7678)
        self.assertEqual(len(self.previous["static_inputs"]), 302)
        for corruption in ("duplicate", "missing-prefix", "missing-static", "smoke"):
            with self.subTest(corruption=corruption):
                changed = inventory_projection(self.previous)
                if corruption == "duplicate":
                    changed["drawings"][-1] = deepcopy(changed["drawings"][0])
                elif corruption == "missing-prefix":
                    changed["histories"][0]["prefix_keys"][0] = "not-a-real-map"
                elif corruption == "missing-static":
                    changed["static_inputs"][0]["geometry_key"] = "not-a-real-map"
                else:
                    changed["smoke_limit"] = 1
                with self.assertRaises(AssertionError):
                    runner.validate_inventory(changed)

    def test_summary_separates_scope_conflict_and_later_history_recovery(self):
        """Both noncompletion kinds count toward coverage, but not the same cause."""
        candidate_status = dict(zip("abcdef", ("solved", "outside_scope", "solved",
                                                "conflict", "solved", "solved")))
        records = [{"key": key, "cohorts": [runner.EXISTING], "runs": {
            runner.BASELINE: {"status": "conflict" if key == "f" else "solved"},
            runner.POLICY: {"status": value}}} for key, value in candidate_status.items()]
        histories = [{"key": "toy-recovery", "cohort": runner.EXISTING,
                      "prefix_keys": list("abcde")}]
        statics = [{"key": key, "cohort": runner.EXISTING, "geometry_key": key} for key in "bde"]
        summaries, history_results, paired = runner.summarize(records, histories, statics)
        current = next(row for row in summaries if row["cohort"] == "combined"
                       and row["policy"] == runner.POLICY)
        self.assertEqual(current["distinct_drawings"], 6)
        self.assertEqual(current["statuses"], {"solved": 4, "outside_scope": 1, "conflict": 1})
        self.assertEqual(current["history_prefix_references"], 5)
        self.assertEqual(current["histories_with_conflict"], 1)
        self.assertEqual(current["histories_with_outside_scope"], 1)
        self.assertEqual(current["all_prefixes_solved"], 0)
        self.assertEqual(current["history_final_status"], {"solved": 1})
        self.assertEqual(current["static_status"], {"outside_scope": 1, "conflict": 1, "solved": 1})
        trajectory = next(row for row in history_results if row["policy"] == runner.POLICY)
        self.assertEqual(trajectory["statuses"], [candidate_status[key] for key in "abcde"])
        self.assertEqual(trajectory["first_outside_scope_prefix"], 1)
        self.assertEqual(trajectory["first_conflict_prefix"], 3)
        self.assertEqual(trajectory["recoveries"], [{"prefix": 2, "from": "outside_scope"},
                                                   {"prefix": 4, "from": "conflict"}])
        comparison = next(row for row in paired if row["cohort"] == "combined")
        self.assertFalse(comparison["baseline_newly_rerun"])
        transitions = {(row["baseline_status"], row["candidate_status"]): row["count"]
                       for row in comparison["status_transitions"]}
        self.assertEqual(transitions[("solved", "outside_scope")], 1)
        self.assertEqual(transitions[("solved", "conflict")], 1)
        self.assertEqual(sum(transitions.values()), 6)
        self.assertEqual(comparison["distinct_drawings"]["regressed"], 2)
        self.assertEqual(comparison["history_final"]["both_solved"], 1)
        with self.assertRaises(KeyError):
            runner.summarize(records[:4], histories, statics)

    def test_actual_dangling_input_is_checked_outside_scope_not_a_color_conflict(self):
        """No missing solver fields are fabricated for a rejected inheritance root."""
        saved = next(row for row in self.previous["drawings"] if any(
            alias.get("history") == "construction-free-end" and alias.get("step") == 1
            for alias in row["aliases"]))
        before = deepcopy(saved)
        part = runner.run_batch((0, [saved], {}))
        result = part["records"][0]["runs"][runner.POLICY]
        self.assertEqual(result["status"], "outside_scope")
        self.assertTrue(result["verification"]["passed"])
        self.assertEqual(result["verification"]["method"], "independent-unrooted-level-scope-check")
        self.assertIsNone(result["colors"])
        self.assertEqual(result["choices"], 0)
        self.assertEqual(result["backtracks"], 0)
        self.assertNotIn("domains", result)
        self.assertNotIn("anchors_by_dart", result)
        self.assertIsNone(result["propagation_phases_sha256"])
        self.assertIsNone(part["least_conflict"])
        self.assertEqual(part["least_outside_scope"]["key"], saved["key"])
        self.assertEqual(saved, before)

    def test_spawn_parallel_and_serial_workers_produce_identical_evidence(self):
        """Use Windows-style spawn and compare all non-timing mathematical data."""
        serial = [runner.run_batch(payload) for payload in self.payloads]
        with ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context("spawn")) as pool:
            parallel = list(pool.map(runner.run_batch, self.payloads))
        self.assertEqual(stable_evidence(serial), stable_evidence(parallel))
        self.assertEqual(sum(len(part["records"]) for part in parallel), 3)
        originals = {row["key"]: row for row in self.small}
        for part in parallel:
            for row in part["records"]:
                self.assertTrue(row["runs"][runner.POLICY]["verification"]["passed"])
                # Baseline evidence is carried unchanged, not claimed as rerun.
                self.assertEqual(row["runs"][runner.BASELINE],
                                 originals[row["key"]]["runs"][runner.BASELINE])

    def test_all_six_archived_certificates_are_reproduced_exactly(self):
        """A success status alone cannot replace the six full trace/proof checks."""
        part = runner.run_batch((0, self.six_rows, self.six_by_key))
        self.assertEqual(len(part["records"]), 6)
        self.assertEqual(part["diagnostic_exact_reproductions"], 6)
        for row in part["records"]:
            archived = self.six_by_key[row["key"]]
            expected = runner.compact_candidate(native_anchor_keys(archived["candidate"]),
                                                archived["candidate_check"])
            # Archived JSON keys are strings; normalize only serialization,
            # retaining every commitment and all three certificate hashes.
            self.assertEqual(runner.json_value(stable_evidence(row["runs"][runner.POLICY])),
                             runner.json_value(stable_evidence(expected)))

    def test_worker_rejects_changed_six_case_certificate_or_missing_geometry(self):
        """Recorded proof equality and exporter coverage are independently guarded."""
        saved = self.six_rows[0]
        altered = {saved["key"]: deepcopy(self.six_by_key[saved["key"]])}
        altered[saved["key"]]["candidate"]["trace"][0]["symbol"] = 99
        with self.assertRaises(AssertionError):
            runner.run_batch((0, [saved], altered))
        with patch.object(runner, "export_geometries", return_value=[]):
            with self.assertRaises(AssertionError):
                runner.run_batch(self.payloads[0])

    def test_single_map_checkpoint_resume_never_reexecutes_a_worker(self):
        """Persisted JSON may stringify darts but cannot change mathematical data."""
        with tempfile.TemporaryDirectory(prefix="fourcolor-level-resume-") as directory:
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
            self.assertEqual(resumed["smoke_limit"], 1)
            self.assertEqual(len(resumed["drawings"]), 1)

    def test_resume_manifest_binds_sources_code_inventory_and_policy(self):
        """Corrupt only mocked reads, never alter archived or checkpoint files."""
        with tempfile.TemporaryDirectory(prefix="fourcolor-level-manifest-") as directory:
            checkpoint = Path(directory) / "checkpoint"
            with redirect_stdout(io.StringIO()):
                runner.build_report(runner.SOURCE, runner.DIAGNOSTIC, checkpoint,
                                    workers=1, batch_size=1, limit=1)
            path = checkpoint / "manifest.json"
            real_read = runner.read_json
            genuine = real_read(path)
            for field in ("source", "diagnostic", "code", "policy", "keys", "batch-size"):
                with self.subTest(field=field):
                    altered = deepcopy(genuine)
                    if field == "source":
                        altered["source_evidence"]["sha256"] = "0" * 64
                    elif field == "diagnostic":
                        altered["diagnostic_evidence"]["sha256"] = "0" * 64
                    elif field == "code":
                        altered["source_sha256"][next(iter(altered["source_sha256"]))] = "0" * 64
                    elif field == "policy":
                        altered["policy"] = "not-the-frozen-policy"
                    elif field == "keys":
                        altered["selected_keys"] = ["not-the-original-map"]
                    else:
                        altered["batch_size"] = 2

                    def changed_read(filename):
                        """Substitute only the manifest under test."""
                        return deepcopy(altered) if Path(filename) == path else real_read(filename)

                    with patch.object(runner, "read_json", side_effect=changed_read), \
                            patch.object(runner, "run_batch", side_effect=AssertionError("worker called")):
                        with self.assertRaisesRegex(AssertionError, "checkpoint"):
                            runner.build_report(runner.SOURCE, runner.DIAGNOSTIC, checkpoint,
                                                workers=1, batch_size=1, limit=1, resume=True)

    def test_checkpoint_part_checksum_mismatch_is_rejected(self):
        """A matching manifest does not make a corrupt saved part trustworthy."""
        with tempfile.TemporaryDirectory(prefix="fourcolor-level-checksum-") as directory:
            checkpoint = Path(directory) / "checkpoint"
            with redirect_stdout(io.StringIO()):
                runner.build_report(runner.SOURCE, runner.DIAGNOSTIC, checkpoint,
                                    workers=1, batch_size=1, limit=1)
            path = checkpoint / "part-00000.json.gz.sha256.json"
            real_read = runner.read_json
            altered = real_read(path)
            altered["sha256"] = "0" * 64

            def changed_read(filename):
                """Substitute the checksum value without overwriting actual bytes."""
                return deepcopy(altered) if Path(filename) == path else real_read(filename)

            with patch.object(runner, "read_json", side_effect=changed_read), \
                    patch.object(runner, "run_batch", side_effect=AssertionError("worker called")):
                with self.assertRaisesRegex(AssertionError, "checksum"):
                    runner.build_report(runner.SOURCE, runner.DIAGNOSTIC, checkpoint,
                                        workers=1, batch_size=1, limit=1, resume=True)

    def test_optimized_python_is_rejected_before_loading_reports(self):
        """Assertions are mathematical checks here, so -O cannot be accepted."""
        optimized = SimpleNamespace(flags=SimpleNamespace(optimize=1))
        with patch.object(runner, "sys", optimized), \
                patch.object(runner, "read_json", side_effect=AssertionError("unexpected input read")):
            with self.assertRaisesRegex(AssertionError, "without Python -O"):
                runner.build_report(Path("unused-source"), Path("unused-diagnostic"), Path("unused-checkpoint"))


if __name__ == "__main__":
    unittest.main()

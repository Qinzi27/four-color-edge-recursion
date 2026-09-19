"""Boundaries of the complete-inventory runner, using tiny audited executions.

The archived 7,069-map inventory is read only for coverage/provenance checks.
These tests never rerun that corpus: real computation uses three small maps
and one single-map checkpoint. No assignment enumeration or solution oracle
is introduced into the production naming rule.
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

from scripts import validate_relation_frontier_full as runner


def stable_evidence(value):
    """Remove measurement/run metadata, never mathematical states or proofs."""
    transient = {"runtime_seconds", "audit_seconds", "wall_seconds", "generated_at_utc", "resumed"}
    if isinstance(value, dict):
        return {key: stable_evidence(item) for key, item in value.items() if key not in transient}
    if isinstance(value, list):
        return [stable_evidence(item) for item in value]
    return value


def inventory_projection(previous):
    """Copy only fields needed to test coverage; avoid huge irrelevant traces."""
    return {"full_corpus_run": previous["full_corpus_run"],
            "smoke_limit": previous["smoke_limit"],
            "drawings": [{"key": row["key"], "cohorts": list(row["cohorts"])}
                         for row in previous["drawings"]],
            "histories": deepcopy(previous["histories"]),
            "static_inputs": deepcopy(previous["static_inputs"])}


class RelationFrontierFullRunnerTests(unittest.TestCase):
    """Coverage must be complete even when a particular naming attempt fails."""

    @classmethod
    def setUpClass(cls):
        """Choose the three smallest old diagnostic maps before running a rule."""
        cls.previous = runner.read_json(runner.SOURCE)
        cls.diagnostic = runner.read_json(runner.DIAGNOSTIC)
        cls.diagnostic_by_key = {row["key"]: row for row in cls.diagnostic["drawings"]}
        eligible = [row for row in cls.previous["drawings"] if row["key"] in cls.diagnostic_by_key]
        cls.small = sorted(eligible, key=lambda row: (
            row["face_count"], len(row["document"]["strokes"]), row["key"]))[:3]
        cls.payloads = [(index, [row], {row["key"]: cls.diagnostic_by_key[row["key"]]}, set())
                        for index, row in enumerate(cls.small)]

    def test_full_inventory_preserves_unique_maps_and_every_reference(self):
        """The two cohorts overlap; history aliases are not unique-map counts."""
        rows = runner.validate_inventory(self.previous)
        self.assertEqual(len(rows), 7069)
        self.assertEqual([row["key"] for row in rows], sorted({row["key"] for row in rows}))
        old = {row["key"] for row in rows if runner.EXISTING in row["cohorts"]}
        newer = {row["key"] for row in rows if runner.HELDOUT in row["cohorts"]}
        self.assertEqual((len(old), len(newer), len(old & newer)), (6113, 961, 5))
        self.assertEqual(len(self.previous["histories"]), 363)
        self.assertEqual(sum(len(row["prefix_keys"]) for row in self.previous["histories"]), 7678)
        self.assertEqual(len(self.previous["static_inputs"]), 302)

    def test_duplicate_missing_prefix_missing_static_and_smoke_are_rejected(self):
        """Corruption must stop the run, not silently lower its denominator."""
        for corruption in ("duplicate", "missing-prefix", "missing-static", "truncated-prefix", "smoke"):
            with self.subTest(corruption=corruption):
                previous = inventory_projection(self.previous)
                if corruption == "duplicate":
                    previous["drawings"][-1] = deepcopy(previous["drawings"][0])
                elif corruption == "missing-prefix":
                    previous["histories"][0]["prefix_keys"][0] = "not-a-real-map"
                elif corruption == "missing-static":
                    previous["static_inputs"][0]["geometry_key"] = "not-a-real-map"
                elif corruption == "truncated-prefix":
                    previous["histories"][0]["prefix_keys"].pop()
                else:
                    previous["smoke_limit"] = 1
                with self.assertRaises(AssertionError):
                    runner.validate_inventory(previous)

    def test_failed_middle_prefix_does_not_hide_recovered_suffix(self):
        """One history can finish successfully while its all-prefix result fails."""
        records = [{"key": key, "cohorts": [runner.EXISTING],
                    "runs": {policy: {"status": ("conflict" if policy == runner.POLICY and key == "b"
                                                  else "solved")}
                             for policy in runner.POLICIES}}
                   for key in ("a", "b", "c")]
        histories = [{"key": "toy-recovery", "family": "toy", "cohort": runner.EXISTING,
                      "prefix_keys": ["a", "b", "c"]}]
        statics = [{"key": "last", "cohort": runner.EXISTING, "geometry_key": "c"}]
        summary, history_results, _ = runner.summarize_frontier(
            records, histories, statics, runner.POLICIES)
        candidate = next(row for row in history_results if row["policy"] == runner.POLICY)
        self.assertEqual(candidate["statuses"], ["solved", "conflict", "solved"])
        self.assertFalse(candidate["all_prefixes_solved"])
        self.assertEqual(candidate["first_failed_prefix"], 1)
        self.assertEqual(candidate["solved_again_after_failure"], [2])
        self.assertEqual(candidate["final_status"], "solved")
        counts = next(row for row in summary if row["cohort"] == "combined"
                      and row["policy"] == runner.POLICY)
        self.assertEqual(counts["history_prefix_references"], 3)
        self.assertEqual(counts["distinct_drawings"], {"solved": 2, "conflict": 1})
        comparison = runner.hall_comparisons(records, histories, statics, history_results)[0]
        self.assertEqual(comparison["all_history_prefixes"]["regressed"], 1)
        self.assertEqual(comparison["history_final"]["both_solved"], 1)
        self.assertEqual(comparison["distinct_drawings"]["regressed"], 1)
        self.assertEqual(comparison["distinct_drawings"]["both_solved"], 2)
        # A missing final record is an error, never an invitation to truncate.
        with self.assertRaises(KeyError):
            runner.summarize_frontier(records[:2], histories, statics, runner.POLICIES)

    def test_spawn_parallel_and_sequential_batches_have_identical_evidence(self):
        """Explicit spawn protects the real Windows worker import/pickle path."""
        sequential = [runner.run_batch(payload) for payload in self.payloads]
        context = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=2, mp_context=context) as pool:
            parallel = list(pool.map(runner.run_batch, self.payloads))
        self.assertEqual(stable_evidence(sequential), stable_evidence(parallel))
        self.assertEqual(sum(part["diagnostic_exact_reproductions"] for part in parallel), 3)
        self.assertEqual(sum(len(part["records"]) for part in parallel), 3)
        for part in parallel:
            for record in part["records"]:
                self.assertEqual(set(record["runs"]), set(runner.POLICIES))
                self.assertTrue(all(run["verification"]["passed"] for run in record["runs"].values()))

    def test_exact_reproduction_rejects_changed_domain_or_trace(self):
        """A valid-looking status alone is insufficient for exact reproduction."""
        saved = self.small[0]["runs"]["tight-hall"]
        runner.exact_run(saved, saved)
        for field in ("domains", "trace_sha256"):
            with self.subTest(field=field):
                changed = deepcopy(saved)
                if field == "domains":
                    changed[field][0] = [99]
                else:
                    changed[field] = "0" * 64
                with self.assertRaisesRegex(AssertionError, field):
                    runner.exact_run(changed, saved)

    def test_batch_rejects_changed_diagnostic_proof_and_dropped_geometry(self):
        """Prior diagnostic outputs are comparison evidence, not solver inputs."""
        index, rows, diagnostic, named = deepcopy(self.payloads[0])
        diagnostic[rows[0]["key"]]["runs"][runner.POLICY]["propagation_phases_sha256"] = "0" * 64
        with self.assertRaisesRegex(AssertionError, "diagnostic proof"):
            runner.run_batch((index, rows, diagnostic, named))
        with patch.object(runner, "export_geometries", return_value=[]):
            with self.assertRaisesRegex(AssertionError, "dropped an input"):
                runner.run_batch(self.payloads[0])

    def test_single_map_checkpoint_resume_reuses_identical_audited_result(self):
        """Only one real map is run; resume cannot invoke a worker at all."""
        with tempfile.TemporaryDirectory(prefix="fourcolor-full-resume-") as directory:
            checkpoint = Path(directory) / "checkpoint"
            with redirect_stdout(io.StringIO()):
                original = runner.build_report(runner.SOURCE, runner.DIAGNOSTIC, checkpoint,
                                               workers=1, batch_size=1, limit=1)
            with patch.object(runner, "run_batch", side_effect=AssertionError("resume reran worker")), \
                    redirect_stdout(io.StringIO()):
                resumed = runner.build_report(runner.SOURCE, runner.DIAGNOSTIC, checkpoint,
                                              workers=1, batch_size=1, limit=1, resume=True)
            # JSON persists integer dart keys as strings. Normalize that known
            # serialization detail while retaining all names and proof values.
            self.assertEqual(runner.json_value(stable_evidence(original)),
                             runner.json_value(stable_evidence(resumed)))
            self.assertFalse(original["execution"]["resumed"])
            self.assertTrue(resumed["execution"]["resumed"])
            self.assertFalse(resumed["full_corpus_run"])
            self.assertEqual(resumed["smoke_limit"], 1)
            self.assertEqual(len(resumed["drawings"]), 1)
            self.assertEqual(resumed["independent_checks"], 3)
            self.assertEqual(resumed["baseline_exact_reproductions"], 2)

    def test_checkpoint_manifest_mismatches_are_rejected_before_workers(self):
        """Input/code hashes, policy declarations and map keys bind a checkpoint.

        Replace only the manifest as read, preserving all actual evidence files.
        Each corrupt variant must fail before any computation or reuse occurs.
        """
        with tempfile.TemporaryDirectory(prefix="fourcolor-full-manifest-") as directory:
            checkpoint = Path(directory) / "checkpoint"
            with redirect_stdout(io.StringIO()):
                runner.build_report(runner.SOURCE, runner.DIAGNOSTIC, checkpoint,
                                    workers=1, batch_size=1, limit=1)
            manifest_path = checkpoint / "manifest.json"
            real_read = runner.read_json
            genuine = real_read(manifest_path)
            for field in ("source", "diagnostic", "code", "policies", "keys", "batch-size"):
                with self.subTest(field=field):
                    altered = deepcopy(genuine)
                    if field == "source":
                        altered["source_evidence"]["sha256"] = "0" * 64
                    elif field == "diagnostic":
                        altered["diagnostic_evidence"]["sha256"] = "0" * 64
                    elif field == "code":
                        altered["source_sha256"][next(iter(altered["source_sha256"]))] = "0" * 64
                    elif field == "policies":
                        altered["policies"] = list(reversed(altered["policies"]))
                    elif field == "keys":
                        altered["selected_keys"] = ["not-the-original-map"]
                    else:
                        altered["batch_size"] = 2

                    def changed_read(path):
                        """Alter only the requested manifest, not source reports."""
                        return deepcopy(altered) if Path(path) == manifest_path else real_read(path)

                    with patch.object(runner, "read_json", side_effect=changed_read), \
                            patch.object(runner, "run_batch", side_effect=AssertionError("worker called")):
                        with self.assertRaisesRegex(AssertionError, "checkpoint source/code/inventory mismatch"):
                            runner.build_report(runner.SOURCE, runner.DIAGNOSTIC, checkpoint,
                                                workers=1, batch_size=1, limit=1, resume=True)

    def test_checkpoint_part_checksum_mismatch_is_rejected(self):
        """A matching manifest cannot authenticate corrupted batch bytes alone."""
        with tempfile.TemporaryDirectory(prefix="fourcolor-full-checksum-") as directory:
            checkpoint = Path(directory) / "checkpoint"
            with redirect_stdout(io.StringIO()):
                runner.build_report(runner.SOURCE, runner.DIAGNOSTIC, checkpoint,
                                    workers=1, batch_size=1, limit=1)
            checksum_path = checkpoint / "part-00000.json.gz.sha256.json"
            real_read = runner.read_json
            altered = real_read(checksum_path)
            altered["sha256"] = "0" * 64

            def changed_read(path):
                """Simulate a bad saved checksum without rewriting evidence."""
                return deepcopy(altered) if Path(path) == checksum_path else real_read(path)

            with patch.object(runner, "read_json", side_effect=changed_read), \
                    patch.object(runner, "run_batch", side_effect=AssertionError("worker called")):
                with self.assertRaisesRegex(AssertionError, "saved checksum"):
                    runner.build_report(runner.SOURCE, runner.DIAGNOSTIC, checkpoint,
                                        workers=1, batch_size=1, limit=1, resume=True)

    def test_optimized_python_is_rejected_before_any_input_read(self):
        """Proof replay uses assert internally, so disabling asserts is forbidden."""
        optimized = SimpleNamespace(flags=SimpleNamespace(optimize=1))
        with patch.object(runner, "sys", optimized), \
                patch.object(runner, "read_json", side_effect=AssertionError("unexpected input read")):
            with self.assertRaisesRegex(AssertionError, "without Python -O"):
                runner.build_report(Path("unused-source"), Path("unused-diagnostic"), Path("unused-checkpoint"))


if __name__ == "__main__":
    unittest.main()

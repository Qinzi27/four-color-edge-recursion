"""Check corpus-run provenance and coverage without rerunning the whole corpus."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts import validate_structural_restart_full as full


class StructuralFullRunnerTests(unittest.TestCase):
    """Reject input loss and keep paired/reference denominators honest."""

    def row(self, key, old, new):
        """Supply a tiny explicit result identity for summary-only checks."""
        return {"key": key, "cohorts": ["seen"], "runs": {
            full.BASELINE: {"status": old}, full.POLICY: {"status": new}}}

    def test_improvement_and_regression_are_both_counted(self):
        """An improvement must never hide a different new failure."""
        rows = [self.row("a", "conflict", "solved"), self.row("b", "solved", "conflict")]
        summary, histories, pairs = full.summarize(rows, [], [])
        pair = next(row for row in pairs if row["cohort"] == "combined")
        self.assertEqual(pair["distinct_drawings"]["improved"], 1)
        self.assertEqual(pair["distinct_drawings"]["regressed"], 1)

    def test_history_final_and_all_prefixes_are_separate(self):
        """A recovered final state does not erase an earlier failed prefix."""
        rows = [self.row("a", "solved", "conflict"), self.row("b", "solved", "solved")]
        history = {"key": "h", "cohort": "seen", "prefix_keys": ["a", "b", "b"]}
        summaries, histories, pairs = full.summarize(rows, [history], [])
        result = next(row for row in histories if row["policy"] == full.POLICY)
        self.assertEqual(result["final_status"], "solved")
        self.assertFalse(result["all_prefixes_solved"])
        self.assertEqual(result["recoveries"], [1])
        summary = next(row for row in summaries if row["cohort"] == "combined" and row["policy"] == full.POLICY)
        self.assertEqual(summary["distinct_drawings"], 2)
        self.assertEqual(summary["history_prefix_references"], 3)

    def test_duplicate_geometry_is_rejected(self):
        """Duplicate rows must not inflate the unique-drawing denominator."""
        row = self.row("a", "solved", "solved")
        with self.assertRaises(AssertionError):
            full.summarize([row, deepcopy(row)], [], [])

    def test_missing_export_is_rejected_before_candidate_runs(self):
        """A short Node export cannot silently reduce the test set."""
        with patch.object(full, "export_geometries", return_value=[]), \
             patch.object(full, "restart_structural_names") as candidate:
            with self.assertRaises(AssertionError):
                full.run_batch((0, [{"key": "a"}]))
            candidate.assert_not_called()

    def test_changed_geometry_hash_is_rejected_before_candidate(self):
        """The serialized input document must recreate the archived geometry."""
        exported = {"key": "a", "status": "geometry_ok", "geometry": {"x": 1}}
        with patch.object(full, "export_geometries", return_value=[exported]), \
             patch.object(full, "restart_structural_names") as candidate:
            with self.assertRaises(AssertionError):
                full.run_batch((0, [{"key": "a", "geometry_sha256": "incorrect"}]))
            candidate.assert_not_called()

    def test_rejected_audit_cannot_be_compacted_as_success(self):
        """A failed independent audit is an execution failure, not a result."""
        with self.assertRaises(AssertionError):
            full.compact_candidate({}, {"passed": False})

    def test_one_attempt_and_full_learned_evidence_are_preserved(self):
        """The runner copies the old baseline and saves every learned transcript.

        The opaque producer result is mocked here because this test covers
        orchestration contracts; the independent proof tests cover its math.
        """
        geometry = {"opaque-test-geometry": True}
        baseline = {"status": "conflict", "runtime_seconds": 123.0}
        saved = {"key": "a", "geometry_sha256": full.digest(geometry),
                 "aliases": [], "document": {}, "face_count": 3,
                 "runs": {full.BASELINE: baseline}}
        result = {"policy": full.POLICY, "status": "solved", "domains": [],
                  "anchors_by_dart": {}, "colors": [1, 2, 3], "choices": 1,
                  "backtracks": 0, "old_colors_read": False, "local_budget": None,
                  "hall_conflict": None, "statistics": {"learned_relations": 1},
                  "learned_pairs": [[1, 2]], "unranked_mothers": [],
                  "trace": [], "events": [], "proof_queries": [], "propagation_phases": []}
        exported = {"key": "a", "status": "geometry_ok", "geometry": geometry}
        with patch.object(full, "export_geometries", return_value=[exported]), \
             patch.object(full, "restart_structural_names", return_value=result) as candidate, \
             patch.object(full, "verify_run", return_value={"passed": True}) as audit:
            batch = full.run_batch((0, [saved]))
        candidate.assert_called_once_with(geometry)
        audit.assert_called_once_with(geometry, result)
        self.assertIs(batch["records"][0]["runs"][full.BASELINE], baseline)
        self.assertEqual(batch["detailed_examples"]["a"]["outcome"], result)
        compact = batch["records"][0]["runs"][full.POLICY]
        self.assertEqual(compact["full_transcript_sha256"], full.digest(result))

    def test_frozen_source_drift_is_rejected(self):
        """Old producer/checker changes invalidate the archived comparison."""
        previous = {"source_sha256": {"old.py": "expected"},
                    "source_sha256_end": {"old.py": "expected"}}
        with patch.object(full, "file_sha", return_value="changed"):
            with self.assertRaises(AssertionError):
                full.source_hashes(previous)


if __name__ == "__main__":
    unittest.main()

"""Small independent-validator tests; never run or tune the full seed corpus."""

from contextlib import redirect_stderr
from copy import deepcopy
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.validate_frontier_restart import (
    BASELINE, EXISTING, HELDOUT, complete_subsets, digest, export_geometries,
    independent_hall, main, paired_counts, restart_line_names,
    summarize_frontier, verify_result, write_report,
)


class FrontierRestartCorpusTests(unittest.TestCase):
    """Protect verification strength, honest denominators, and frozen evidence."""

    @classmethod
    def setUpClass(cls):
        """One tiny geometry-only Node batch; no random or benchmark generation."""
        exported = export_geometries([
            {"key": "blank-frame", "document": {"strokes": []}},
            {"key": "t-junction", "document": {"strokes": [
                {"a": [0, 300], "b": [900, 300]},
                {"a": [450, 300], "b": [450, 600]},
            ]}},
            {"key": "bridge", "document": {"strokes": [
                {"a": [0, 300], "b": [200, 300]},
            ]}},
        ])
        cls.geometry = {r["key"]: r["geometry"] for r in exported}

    def test_direct_success_does_not_require_singleton_propagation_from_anchors(self):
        """Full names can be verified without reusing any production inference."""
        geometry = self.geometry["t-junction"]
        result = restart_line_names(geometry, BASELINE)
        self.assertEqual(result["status"], "solved")
        # Erasing this already-solved result's commitments makes singleton
        # propagation underdetermined, but does not invalidate its actual names.
        result["anchors_by_dart"] = {}
        with patch("scripts.validate_frontier_restart.restart_line_names",
                   side_effect=AssertionError("verification must not rerun the solver")):
            audit = verify_result(geometry, result)
        self.assertTrue(audit["passed"])
        self.assertEqual(audit["method"], "direct-coloring-and-line-orbits")

    def test_completed_colors_domains_and_commitments_must_agree(self):
        """An alleged solution cannot hide equal opposite shores or bad metadata."""
        geometry = self.geometry["blank-frame"]
        base = restart_line_names(geometry, BASELINE)
        bad_domains = deepcopy(base)
        bad_domains["domains"][0] = [4]
        with self.assertRaisesRegex(AssertionError, "domains"):
            verify_result(geometry, bad_domains)
        bad_colors = deepcopy(base)
        bad_colors["colors"] = [1, 1]
        bad_colors["domains"] = [[1], [1]]
        bad_colors["anchors_by_dart"] = {}
        with self.assertRaisesRegex(AssertionError, "opposite actual shores"):
            verify_result(geometry, bad_colors)

    def test_real_bridge_equal_names_are_valid(self):
        """A hanging line does not become an invented face/color inequality."""
        geometry = self.geometry["bridge"]
        self.assertTrue(geometry["real_bridge_edge_ids"])
        result = restart_line_names(geometry, BASELINE)
        self.assertTrue(verify_result(geometry, result)["passed"])
        for edge in geometry["real_bridge_edge_ids"]:
            self.assertEqual(geometry["faceOfDart"][2 * edge], geometry["faceOfDart"][2 * edge + 1])

    def test_conflict_cannot_be_certified_from_producer_empty_domains(self):
        """Poisoned producer state is not independent evidence of impossibility."""
        geometry = self.geometry["blank-frame"]
        result = restart_line_names(geometry, BASELINE)
        result.update({"status": "conflict", "colors": None, "domains": [[], []]})
        audit = verify_result(geometry, result)
        self.assertFalse(audit["passed"])
        self.assertEqual(audit["certificate"]["rule"], "nonempty-fixed-point-is-inconclusive")

    def test_true_triangle_hall_deficiency_is_independently_certified(self):
        """Three pairwise adjacent shores cannot all use just two symbols."""
        adjacent = [{1, 2}, {0, 2}, {0, 1}]
        domains = [{1, 2}, {1, 2}, {1, 2}]
        unchanged = deepcopy(domains)
        audit = independent_hall(domains, adjacent)
        self.assertTrue(audit["certified"])
        self.assertTrue(audit["rule"].startswith("clique-hall"))
        self.assertEqual(domains, unchanged)

    def test_hall_reservation_activates_without_assignment_search(self):
        """A tight pair in a genuine triangle excludes its colors from the third."""
        adjacent = [{1, 2}, {0, 2}, {0, 1}]
        audit = independent_hall([{1, 2}, {1, 2}, {1, 2, 3}], adjacent)
        self.assertFalse(audit["certified"])
        self.assertEqual(audit["reductions"], 2)
        self.assertEqual(audit["domains_sha256"], digest([[1, 2], [1, 2], [3]]))

    def test_cycle_is_not_treated_as_pairwise_all_different(self):
        """Opposite shores of a four-cycle may reuse the same two symbols."""
        adjacent = [{1, 3}, {0, 2}, {1, 3}, {0, 2}]
        subsets = complete_subsets(adjacent)
        self.assertEqual({len(s) for s, _ in subsets}, {2})
        self.assertFalse(independent_hall([{1, 2}] * 4, adjacent)["certified"])

    def test_recovery_final_and_whole_history_have_distinct_paired_counts(self):
        """One improved final drawing cannot conceal an earlier failed prefix."""
        candidate = "synthetic-candidate"
        records = [
            {"key": "a", "cohorts": [EXISTING, HELDOUT],
             "runs": {BASELINE: {"status": "solved"}, candidate: {"status": "conflict"}}},
            {"key": "b", "cohorts": [EXISTING],
             "runs": {BASELINE: {"status": "conflict"}, candidate: {"status": "solved"}}},
        ]
        histories = [{"key": "h", "family": "toy", "cohort": EXISTING, "prefix_keys": ["a", "b"]}]
        statics = [{"key": "s", "cohort": EXISTING, "geometry_key": "b"}]
        summary, results, comparisons = summarize_frontier(records, histories, statics, (BASELINE, candidate))
        row = next(r for r in results if r["policy"] == candidate)
        self.assertFalse(row["all_prefixes_solved"])
        self.assertEqual(row["first_failed_prefix"], 0)
        self.assertEqual(row["solved_again_after_failure"], [1])
        self.assertEqual(row["final_status"], "solved")
        compare = next(r for r in comparisons if r["cohort"] == EXISTING)
        self.assertEqual(compare["distinct_drawings"], {
            "both_solved": 0, "improved": 1, "regressed": 1, "both_not_solved": 0})
        self.assertEqual(compare["all_history_prefixes"]["both_not_solved"], 1)
        self.assertEqual(compare["history_final"]["improved"], 1)
        heldout = next(r for r in summary if r["cohort"] == HELDOUT and r["policy"] == candidate)
        self.assertEqual(heldout["distinct_drawing_count"], 1)
        self.assertEqual(heldout["history_count"], 0)
        self.assertEqual(paired_counts([]), {
            "both_solved": 0, "improved": 0, "regressed": 0, "both_not_solved": 0})

    def test_cli_refuses_overwriting_evidence_before_running_algorithms(self):
        """Output protection is checked before corpus creation or any expensive run."""
        with tempfile.TemporaryDirectory(prefix="fourcolor-frontier-test-") as folder:
            target, summary = Path(folder) / "kept.json.gz", Path(folder) / "new.json"
            write_report(target, {"kept": True})
            before = target.read_bytes()
            with patch("sys.argv", ["validator", "--output", str(target), "--summary", str(summary)]), \
                    patch("scripts.validate_frontier_restart.build_report") as build, \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exited:
                main()
            self.assertEqual(exited.exception.code, 2)
            build.assert_not_called()
            self.assertEqual(target.read_bytes(), before)
            self.assertFalse(summary.exists())


if __name__ == "__main__":
    unittest.main()

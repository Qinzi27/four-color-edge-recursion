"""Check predeclared generation, paired attempts and honest result denominators."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts import validate_structural_restart_new_seeds as runner


class StructuralNewSeedTests(unittest.TestCase):
    """Synthetic orchestration fixtures are separate from mathematical audits."""

    def generated(self):
        """Create all required seed identities and 24 distinct axis cuts each."""
        return [{"seed": seed, "paths": [[[index * 25 + cut + 1, 0],
                                          [index * 25 + cut + 1, 600]]
                                         for cut in range(runner.CUTS)]}
                for index, seed in enumerate(runner.SEEDS)]

    def result(self, policy, status="solved", learned=False):
        """Opaque traces let the test inspect orchestration, not mock mathematics."""
        answer = {"policy": policy, "status": status, "domains": [], "anchors_by_dart": {},
                  "colors": [1] if status == "solved" else None, "choices": 0,
                  "backtracks": 0, "old_colors_read": False, "local_budget": None,
                  "hall_conflict": None, "unranked_mothers": [], "trace": [],
                  "propagation_phases": []}
        if policy == runner.POLICY:
            answer.update(statistics={"learned_relations": int(learned)},
                          learned_pairs=[[0, 1]] if learned else [], events=[], proof_queries=[])
        return answer

    def row(self, key, old, new, membership):
        """Summary rows retain membership independently of their outcomes."""
        return {"key": key, "old_inventory_membership": membership,
                "runs": {runner.BASELINE: {"status": old}, runner.POLICY: {"status": new}}}

    def test_fixed_seed_and_full_prefix_inventory(self):
        """500 references include all empty prefixes but only one empty geometry."""
        generated = self.generated()
        before = deepcopy(generated)
        first, histories, inputs = runner.make_inventory(generated, set())
        self.assertEqual(len(first), 481)
        self.assertEqual(len(histories), 20)
        self.assertEqual(sum(len(row["prefix_keys"]) for row in histories), 500)
        self.assertTrue(all(len(row["paths"]) == 24 for row in inputs))
        self.assertEqual(generated, before)
        old = {first[0]["key"], first[-1]["key"]}
        records, _, _ = runner.make_inventory(generated, old)
        self.assertEqual(sum(row["old_inventory_membership"] == "overlap" for row in records), 2)
        self.assertEqual({row["key"] for row in records}, {row["key"] for row in first})

    def test_dropped_reordered_or_short_history_is_rejected(self):
        """No naming outcome can silently remove an inconvenient generated case."""
        good = self.generated()
        short = deepcopy(good)
        short[0]["paths"].pop()
        bad_endpoint = deepcopy(good)
        bad_endpoint[0]["paths"][0][0][0] = True
        for generated in (good[:-1], good[::-1], short, bad_endpoint):
            with self.subTest(rows=len(generated)), self.assertRaises(AssertionError):
                runner.make_inventory(generated, set())

    def test_novelty_prefix_and_final_denominators_stay_separate(self):
        """A final recovery does not erase earlier failures or repeated aliases."""
        rows = [self.row("a", "solved", "conflict", "novel"),
                self.row("b", "conflict", "solved", "overlap")]
        histories = [{"key": "h", "seed": 1, "prefix_keys": ["a", "b", "b"]}]
        groups, summary, history_results = runner.summarize(rows, histories)
        combined = next(row for row in groups if row["old_inventory_membership"] == "combined")
        novel = next(row for row in groups if row["old_inventory_membership"] == "novel")
        overlap = next(row for row in groups if row["old_inventory_membership"] == "overlap")
        self.assertEqual(combined["distinct_drawings"]["count"], 2)
        self.assertEqual(combined["prefix_references"]["count"], 3)
        self.assertEqual(combined["distinct_drawings"]["paired"]["improved"], 1)
        self.assertEqual(combined["distinct_drawings"]["paired"]["regressed"], 1)
        self.assertEqual(novel["prefix_references"]["count"], 1)
        self.assertEqual(overlap["prefix_references"]["count"], 2)
        self.assertEqual(overlap["final_references"]["count"], 1)
        self.assertEqual(summary["policies"][runner.POLICY]["all_prefixes_solved"], 0)
        self.assertEqual(summary["policies"][runner.POLICY]["final_status"], {"solved": 1})
        self.assertEqual(next(row for row in history_results if row["policy"] == runner.POLICY)["recoveries"], [1])

    def test_duplicate_results_and_missing_prefixes_are_rejected(self):
        """Coverage failures must not quietly shrink result denominators."""
        row = self.row("a", "solved", "solved", "novel")
        with self.assertRaises(AssertionError):
            runner.summarize([row, deepcopy(row)], [])
        with self.assertRaises(AssertionError):
            runner.summarize([row], [{"key": "h", "seed": 1, "prefix_keys": ["missing"]}])

    def test_each_policy_and_auditor_runs_once_and_failure_trace_is_retained(self):
        """A baseline failure is evidence even when the candidate learns nothing."""
        geometry = {"faces": [[0]]}
        saved = {"key": "k", "document": {}, "aliases": [], "old_inventory_membership": "novel"}
        exported = {"key": "k", "status": "geometry_ok", "geometry": geometry}
        baseline = self.result(runner.BASELINE, "conflict")
        candidate = self.result(runner.POLICY)
        with patch.object(runner, "export_geometries", return_value=[exported]), \
             patch.object(runner, "restart_level_peer_names", return_value=baseline) as old, \
             patch.object(runner, "restart_structural_names", return_value=candidate) as new, \
             patch.object(runner, "verify_baseline", return_value={"passed": True}) as old_check, \
             patch.object(runner, "verify_candidate", return_value={"passed": True}) as new_check:
            piece = runner.run_batch((0, [saved]))
        old.assert_called_once_with(geometry)
        new.assert_called_once_with(geometry)
        old_check.assert_called_once_with(geometry, baseline)
        new_check.assert_called_once_with(geometry, candidate)
        self.assertEqual(piece["detailed_examples"]["k"]["runs"],
                         {runner.BASELINE: baseline, runner.POLICY: candidate})
        self.assertEqual(piece["records"][0]["runs"][runner.POLICY]["full_transcript_sha256"],
                         runner.digest(candidate))

    def test_learned_success_retains_both_full_transcripts(self):
        """Successful new deductions are preserved, not just exceptional failures."""
        geometry = {"faces": [[0]]}
        saved = {"key": "k", "document": {}, "aliases": []}
        candidate = self.result(runner.POLICY, learned=True)
        with patch.object(runner, "export_geometries", return_value=[
                {"key": "k", "status": "geometry_ok", "geometry": geometry}]), \
             patch.object(runner, "restart_level_peer_names", return_value=self.result(runner.BASELINE)), \
             patch.object(runner, "restart_structural_names", return_value=candidate), \
             patch.object(runner, "verify_baseline", return_value={"passed": True}), \
             patch.object(runner, "verify_candidate", return_value={"passed": True}):
            piece = runner.run_batch((0, [saved]))
        self.assertEqual(set(piece["detailed_examples"]["k"]["runs"]), {runner.BASELINE, runner.POLICY})

    def test_failed_export_stops_before_any_policy(self):
        """Malformed geometry cannot become an omitted or favorable input."""
        for exported in ([], [{"key": "k", "status": "geometry_error"}]):
            with patch.object(runner, "export_geometries", return_value=exported), \
                 patch.object(runner, "restart_level_peer_names") as baseline, \
                 patch.object(runner, "restart_structural_names") as candidate:
                with self.assertRaises(AssertionError):
                    runner.run_batch((0, [{"key": "k"}]))
                baseline.assert_not_called()
                candidate.assert_not_called()

    def test_rejected_audit_never_enters_results(self):
        """A failed independent proof check aborts instead of recording success."""
        with self.assertRaises(AssertionError):
            runner.compact_run(self.result(runner.POLICY), {"passed": False})

    def test_source_hash_drift_is_rejected(self):
        """Changing old code invalidates the controlled comparison before execution."""
        previous = {"source_sha256": {"old.py": "fixed"}, "source_sha256_end": {"old.py": "fixed"}}
        with patch.object(runner, "file_sha", return_value="changed"), self.assertRaises(AssertionError):
            runner.source_hashes(previous)


if __name__ == "__main__":
    unittest.main()

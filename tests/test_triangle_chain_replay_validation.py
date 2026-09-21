"""Independent geometry and provenance checks for actual history replay."""

from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from fourcolor.triangle_chain_family import build_staggered_strip
from fourcolor.triangle_chain_replay import build_history_variant, replay_staggered_history
from scripts.validate_triangle_chain_replay import (
    audit_kempe_candidates, audit_trace, compare_final_inherited, diagnose_stop, pending_problem,
    snapshot_colors, variants, verify_history,
)


class TriangleChainReplayValidationTests(unittest.TestCase):
    """A legal coloring alone must not certify that the policy ever reached it."""

    def setUp(self):
        """A small real history reaches a known earlier policy obstruction."""
        self.family = build_staggered_strip(1)
        self.history = build_history_variant(self.family)
        self.record = replay_staggered_history(self.family)

    def test_all_declared_geometry_orders_end_at_the_same_map(self):
        """Direction and isolation order vary while final rectangles stay fixed."""
        self.assertEqual(len(variants()), 8)
        for m in (1, 2):
            family = build_staggered_strip(m)
            for variant in variants():
                verify_history(family, build_history_variant(family, **variant))

    def test_actual_trace_and_separate_cost_oracle_pass(self):
        """The oracle explains a stopped prefix and is not used to continue it."""
        audit = audit_trace(self.family, self.history, self.record)
        self.assertTrue(audit["passed"])
        self.assertEqual(self.record["stop_step"], 6)
        diagnosis = diagnose_stop(self.family, self.record)
        self.assertFalse(diagnosis["used_to_continue_history"])
        self.assertIsNotNone(diagnosis["quotient"]["minimum_cost"])
        self.assertEqual(compare_final_inherited(self.family, self.record)["status"], "not_reached")

    def test_missing_or_changed_steps_do_not_pass(self):
        """Neither a skipped prefix nor an edited operation is a valid replay."""
        bad = deepcopy(self.record)
        bad["trace"].pop(0)
        with self.assertRaises(AssertionError):
            audit_trace(self.family, self.history, bad)
        bad = deepcopy(self.record)
        bad["trace"][0]["operation"]["at"] = 0
        with self.assertRaises(AssertionError):
            audit_trace(self.family, self.history, bad)

    def test_failed_transaction_and_false_reachability_are_rejected(self):
        """Unreached target parents cannot be marked as observed initial states."""
        for key, value in (("reached_final_parent", True), ("status", "completed"),
                           ("stop_step", None), ("cost_old_changes", 999)):
            bad = deepcopy(self.record)
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(AssertionError):
                audit_trace(self.family, self.history, bad)

    def test_geometric_adjacency_detects_bad_colors_and_overlap(self):
        """The audit builds constraints from boxes instead of stored adjacency."""
        bad = deepcopy(self.record["trace"][0]["after"])
        bad["rectangles"][0]["color"] = 0
        with self.assertRaises(AssertionError):
            snapshot_colors(bad, self.family["bounds"])
        bad = deepcopy(self.record["trace"][0]["after"])
        bad["rectangles"][0]["bounds"] = self.family["bounds"][:]
        with self.assertRaises(AssertionError):
            snapshot_colors(bad, self.family["bounds"])

    def test_wrong_final_geometry_or_last_parent_is_rejected(self):
        """Every control must still pose exactly the intended final split."""
        with self.assertRaises(AssertionError):
            verify_history(self.family, self.history[:-1])
        bad = deepcopy(self.history)
        bad[-1]["points"][0][0] += 1
        with self.assertRaises(AssertionError):
            verify_history(self.family, bad)

    def test_pending_problem_preserves_initial_and_cost_semantics(self):
        """Only the two fresh daughters have zero old-side price."""
        entry = self.record["trace"][-1]
        problem, _ = pending_problem(entry["before"], entry["operation"], self.family["bounds"])
        self.assertEqual(problem["initial"][problem["daughters"][0]],
                         problem["initial"][problem["daughters"][1]])
        self.assertEqual(sum(problem["weights"].values()), len(problem["initial"]) - 3)
        self.assertTrue(all(problem["initial"][u] != problem["initial"][v]
                            for u, v in problem["edges"]))

    def test_diagnostic_kempe_candidate_coverage_is_not_trusted(self):
        """A legal endpoint cannot replace the promised complete component audit."""
        diagnosis = diagnose_stop(self.family, self.record)
        bad = deepcopy(diagnosis["single_kempe"])
        self.assertTrue(bad["candidates"])
        bad["candidates"].pop()
        with self.assertRaises(AssertionError):
            audit_kempe_candidates(diagnosis["problem"], bad)

    @unittest.skipUnless(shutil.which("node"), "browser-policy replay needs existing Node.js")
    def test_real_browser_module_replays_and_stops_atomically(self):
        """Cross-runtime integration invokes the real published policy module."""
        root = Path(__file__).resolve().parents[1]
        case = {"m": 1, "variant": variants()[0], "bounds": self.family["bounds"], "history": self.history}
        result = subprocess.run([shutil.which("node"), str(root / "scripts/replay_triangle_chain_web.mjs")],
                                input=json.dumps({"schema_version": 1, "cases": [case]}),
                                text=True, encoding="utf-8", capture_output=True, check=True, timeout=30)
        row = json.loads(result.stdout)["results"][0]
        self.assertTrue(audit_trace(self.family, self.history, row)["passed"])
        self.assertEqual(row["stop_step"], 6)
        self.assertEqual(row["trace"][-1]["before"], row["trace"][-1]["after"])


if __name__ == "__main__":
    unittest.main()

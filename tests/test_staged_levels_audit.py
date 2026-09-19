"""Adversarial tests for the independent v3 aggregate/certificate audit.

These are finite bookkeeping and certificate checks, not a completeness test.
Fixtures remain small; the full 7,069-input experiment runs only via its CLI.
"""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fourcolor.staged_levels import POLICY, restart_staged_level_names
from scripts.audit_staged_levels_full import (
    BASELINE, MODES, audit_anchor_geometry, audit_checkpoints,
    audit_geometries_and_samples, audit_initialization_summary, audit_summaries,
    check_compact_certificate, native_certificate, paired,
)
from scripts.validate_frontier_restart import file_sha, independent_geometry, json_value
from scripts.validate_global_restart import digest, write_report
from scripts.validate_staged_levels import verify_run
from tests import test_level_sides_peer as peer_fixtures


def compact(result, check):
    """Build the documented compact contract without importing the full runner."""
    keys = ("status", "policy", "choices", "backtracks", "old_colors_read", "colors",
            "unranked_mothers", "initialization", "initial_anchors_by_dart", "domains",
            "anchors_by_dart", "local_budget", "hall_conflict")
    record = {key: result[key] for key in keys}
    record.update(verification=check, raw_result_sha256=digest(result),
                  trace_sha256=digest(result["trace"]), levels_sha256=digest(result["levels"]),
                  propagation_phases_sha256=digest(result["propagation_phases"]))
    record["active_one_choices"] = sum(s["symbol"] == 1 for s in result["trace"])
    record["direct_one_bans"] = sum(1 in s["boundary"]["direct_forbidden"] for s in result["trace"])
    record["derived_one_bans"] = sum(1 in s["boundary"]["derived_exclusions"] for s in result["trace"])
    record["initial_retained_choice"] = {k: result["trace"][0][k] for k in
        ("choice_kind", "mother", "side", "dart", "domain", "symbol")}
    return json_value(record)


class StagedLevelsAuditTests(unittest.TestCase):
    """Verify exact replay and rejection of plausible corrupted summaries."""

    @classmethod
    def setUpClass(cls):
        """Reuse only small geometry fixtures, never an old solved coloring."""
        peer_fixtures.LevelSidePeerTests.setUpClass()
        cls.geometry = peer_fixtures.LevelSidePeerTests.geometry["grid"]
        cls.result = restart_staged_level_names(cls.geometry)
        cls.check = verify_run(cls.geometry, cls.result)
        cls.compact = compact(cls.result, cls.check)

    def test_native_dart_maps_restore_full_certificate_hash(self):
        """Storage string keys must not invalidate native numeric-key hashes."""
        stored = json_value(self.result)
        self.assertEqual(digest(native_certificate(stored)), digest(self.result))
        check_compact_certificate(self.compact, stored, self.check)
        bad = deepcopy(self.compact)
        bad["raw_result_sha256"] = "0" * 64
        with self.assertRaises(AssertionError):
            check_compact_certificate(bad, stored, self.check)

    def test_full_compact_binding_rejects_event_and_commitment_changes(self):
        """A valid output cannot hide changed proof hashes or trace counters."""
        for field in ("trace_sha256", "levels_sha256", "propagation_phases_sha256",
                      "active_one_choices", "direct_one_bans", "derived_one_bans"):
            bad = deepcopy(self.compact)
            bad[field] = ("0" * 64 if field.endswith("sha256") else bad[field] + 1)
            with self.subTest(field=field), self.assertRaises(AssertionError):
                check_compact_certificate(bad, self.result, self.check)

    def test_every_initial_frame_evidence_is_checked_geometrically(self):
        """Point contact or a missing final initial commitment is not enough."""
        plane, _ = independent_geometry(self.geometry)
        audit_anchor_geometry(self.geometry, self.compact, plane)
        for mutation in ("frame-edge", "outer-side", "extra-anchor", "lost-two"):
            bad = deepcopy(self.compact)
            init = bad["initialization"]
            if mutation == "frame-edge":
                init["frame_boundary_edges"] = []
            elif mutation == "outer-side":
                init["outside_side"] = init["side"]
            elif mutation == "extra-anchor":
                bad["initial_anchors_by_dart"][str(init["dart"])] = [2]
            else:
                bad["anchors_by_dart"].pop(str(init["dart"]))
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                audit_anchor_geometry(self.geometry, bad, plane)

    def test_initialization_summary_recounts_actual_records(self):
        """The denominator and symbol counts are checked separately from success."""
        first = self.compact["initial_retained_choice"]
        mode = self.compact["initialization"]["mode"]
        report = {"drawings": [{"key": "grid", "runs": {POLICY: self.compact}}],
            "initialization_summary": {"mode_counts": {mode: 1}, "retained_symbol_counts": {"2": 1},
                "retained_two_count": 1, "selections": [{"key": "grid", "mode": mode,
                    "retained_choice": first, "status": self.compact["status"]}]}}
        self.assertEqual(audit_initialization_summary(report), report["initialization_summary"])
        for mutation in ("total", "mode", "side", "coarse-pair"):
            bad = deepcopy(report)
            if mutation == "total":
                bad["initialization_summary"]["retained_two_count"] = 2
            elif mutation == "mode":
                bad["drawings"][0]["runs"][POLICY]["initialization"]["mode"] = MODES[1]
            elif mutation == "side":
                bad["drawings"][0]["runs"][POLICY]["initial_retained_choice"]["side"] = 999
            else:
                bad["drawings"][0]["runs"][POLICY]["initialization"]["coarse_split_pair_unordered"] = None
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                audit_initialization_summary(bad)

    def test_paired_accounting_includes_regressions(self):
        """No status transition disappears when the new policy is strengthened."""
        self.assertEqual(paired([(True, True), (False, True), (True, False), (False, False)]),
                         dict(both_solved=1, improved=1, regressed=1, both_not_solved=1))

    def test_empty_summary_is_independently_reconstructed_and_tamper_rejected(self):
        """Even zero-data unit fixtures must satisfy every explicit count field."""
        # Main rejects empty/full-corpus evidence; this isolated test exercises
        # the independent aggregate function without executing the experiment.
        summaries, comparisons = [], []
        for cohort in ("combined", "existing-corpus", "new-seeds-20261901-20261940"):
            for policy in (BASELINE, POLICY):
                summaries.append({"cohort": cohort, "policy": policy, "distinct_drawings": 0,
                    "statuses": {}, "histories": 0, "history_prefix_references": 0,
                    "all_prefixes_solved": 0, "histories_with_conflict": 0,
                    "history_final_status": {}, "static_references": 0, "static_status": {}})
            comparisons.append({"cohort": cohort, "baseline": BASELINE, "candidate": POLICY,
                "baseline_newly_rerun": False, "distinct_drawings": paired([]), "status_transitions": [],
                "all_history_prefixes": paired([]), "history_final": paired([]),
                "static_final": paired([]), "regression_keys": []})
        report = {"drawings": [], "histories": [], "static_inputs": [], "history_results": [],
                  "summary": summaries, "paired_comparisons": comparisons}
        self.assertEqual(audit_summaries(report), (summaries, comparisons))
        bad = deepcopy(report)
        bad["summary"][0]["all_prefixes_solved"] = 1
        with self.assertRaises(AssertionError):
            audit_summaries(bad)

    def test_history_failure_recovery_and_regression_are_not_final_only_counts(self):
        """Three hand-counted drawings distinguish prefixes from final outputs."""
        existing, newer = "existing-corpus", "new-seeds-20261901-20261940"
        rows = [{"key": key, "cohorts": [cohort], "runs": {
                    BASELINE: {"status": before}, POLICY: {"status": after}}}
                for key, cohort, before, after in (
                    ("a", existing, "solved", "conflict"),
                    ("b", existing, "conflict", "solved"),
                    ("c", newer, "solved", "solved"))]
        histories = [{"key": "h1", "cohort": existing, "prefix_keys": ["a", "b"]},
                     {"key": "h2", "cohort": newer, "prefix_keys": ["c"]}]
        history_results = []
        for policy in (BASELINE, POLICY):
            states = ["solved", "conflict"] if policy == BASELINE else ["conflict", "solved"]
            history_results.append({"key": "h1", "cohort": existing, "policy": policy,
                "statuses": states, "all_prefixes_solved": False,
                "first_non_solved_prefix": 1 if policy == BASELINE else 0,
                "recoveries": [] if policy == BASELINE else [{"prefix": 1, "from": "conflict"}],
                "final_status": "conflict" if policy == BASELINE else "solved"})
            history_results.append({"key": "h2", "cohort": newer, "policy": policy,
                "statuses": ["solved"], "all_prefixes_solved": True,
                "first_non_solved_prefix": None, "recoveries": [], "final_status": "solved"})
        summaries, comparisons = [], []
        for cohort in ("combined", existing, newer):
            combined, recent = cohort == "combined", cohort == newer
            for policy in (BASELINE, POLICY):
                old = policy == BASELINE
                summaries.append({"cohort": cohort, "policy": policy,
                    "distinct_drawings": 3 if combined else 1 if recent else 2,
                    "statuses": {"solved": 1} if recent else {"solved": 2 if combined else 1, "conflict": 1},
                    "histories": 2 if combined else 1,
                    "history_prefix_references": 3 if combined else 1 if recent else 2,
                    "all_prefixes_solved": int(combined or recent),
                    "histories_with_conflict": int(not recent),
                    "history_final_status": ({"solved": 1} if recent else
                        {"conflict": 1, "solved": 1} if combined and old else
                        {"solved": 2} if combined else {"conflict": 1} if old else {"solved": 1}),
                    "static_references": 2 if combined else 1,
                    "static_status": ({"solved": 1} if recent else
                        {"solved": 2} if combined and old else
                        {"solved": 1, "conflict": 1} if combined else
                        {"solved": 1} if old else {"conflict": 1})})
            both = int(combined or recent)
            changed = int(not recent)
            distinct = dict(both_solved=both, improved=changed, regressed=changed, both_not_solved=0)
            prefix = dict(both_solved=both, improved=0, regressed=0, both_not_solved=changed)
            final = dict(both_solved=both, improved=changed, regressed=0, both_not_solved=0)
            static = dict(both_solved=both, improved=0, regressed=changed, both_not_solved=0)
            transitions = ([] if recent else [
                {"baseline_status": "conflict", "candidate_status": "solved", "count": 1},
                {"baseline_status": "solved", "candidate_status": "conflict", "count": 1}])
            if both:
                transitions.append({"baseline_status": "solved", "candidate_status": "solved", "count": 1})
            comparisons.append({"cohort": cohort, "baseline": BASELINE, "candidate": POLICY,
                "baseline_newly_rerun": False, "distinct_drawings": distinct,
                "status_transitions": transitions, "all_history_prefixes": prefix,
                "history_final": final, "static_final": static,
                "regression_keys": [] if recent else ["a"]})
        report = {"drawings": rows, "histories": histories,
            "static_inputs": [{"cohort": existing, "geometry_key": "a"}, {"cohort": newer, "geometry_key": "c"}],
            "history_results": history_results, "summary": summaries, "paired_comparisons": comparisons}
        self.assertEqual(audit_summaries(report), (summaries, comparisons))
        bad = deepcopy(report)
        bad["history_results"][2]["all_prefixes_solved"] = True
        with self.assertRaises(AssertionError):
            audit_summaries(bad)

    def test_checkpoint_hashes_sidecars_and_exact_order_are_bound(self):
        """Rehashing bytes is insufficient unless record coverage is also exact."""
        rows = [{"key": key, "runs": {POLICY: {"status": "solved"}}} for key in ("a", "b")]
        report = {"drawings": rows, "source_evidence": {}, "diagnostic_evidence": {}, "source_sha256": {},
            "policy": POLICY, "baseline": BASELINE, "baseline_newly_rerun": False,
            "diagnostic_keys": [], "old_failure_keys": [], "diagnostics_checked": 0,
            "detailed_examples": {}, "least_conflict": None,
            "execution": {"batch_size": 1, "part_sha256": {}}}
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            manifest = {name: report[name] for name in ("source_evidence", "diagnostic_evidence", "source_sha256",
                "policy", "baseline", "baseline_newly_rerun", "diagnostic_keys", "old_failure_keys")}
            manifest.update(selected_keys=["a", "b"], smoke_limit=None, batch_size=1)
            write_report(folder / "manifest.json", manifest)
            for index, row in enumerate(rows):
                path = folder / f"part-{index:05d}.json.gz"
                write_report(path, {"index": index, "records": [row], "detailed_examples": {},
                                    "least_conflict": None, "diagnostics_checked": 0})
                checksum = file_sha(path)
                write_report(path.with_suffix(path.suffix + ".sha256.json"),
                             {"filename": path.name, "sha256": checksum})
                report["execution"]["part_sha256"][path.name] = checksum
            self.assertEqual(audit_checkpoints(report, folder)["checkpoint_records_checked"], 2)
            bad = deepcopy(report)
            bad["execution"]["part_sha256"]["part-00000.json.gz"] = "0" * 64
            with self.assertRaises(AssertionError):
                audit_checkpoints(bad, folder)


if __name__ == "__main__":
    unittest.main()

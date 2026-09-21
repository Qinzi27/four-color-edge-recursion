"""Reject fabricated Kempe targets, costs and evidence in the research audit."""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fourcolor.kempe_split import single_kempe_split
from scripts.validate_kempe_split import (
    audit_attempts, audit_candidate, check_global_targets, make_problem, write_new_report,
)
from scripts.validate_renaming import audit_record

ROOT = Path(__file__).resolve().parents[1]


class KempeSplitValidationTests(unittest.TestCase):
    """Use actual line geometry independently of the production SCC metadata."""

    @classmethod
    def setUpClass(cls):
        """Load one geometric regression and one bounded all-target example."""
        source = json.loads((ROOT / "outputs/renaming-round-2026-09-18-v2.json").read_text(encoding="utf-8"))
        cls.row = source["records"][0]
        cls.checked = audit_record(cls.row)
        cls.problem = make_problem(cls.row, cls.checked)
        cls.result = single_kempe_split(**cls.problem)
        cls.candidate = cls.result["selected"]
        cls.small = next(row for row in source["records"] if row["seed"] == 20260909)
        cls.small_checked = audit_record(cls.small)
        profiles = json.loads((ROOT / "outputs/target-renaming-2026-09-18-v2.json").read_text(encoding="utf-8"))
        cls.profile = next(row for row in profiles["target_profiles"]["records"] if row["seed"] == cls.small["seed"])

    def test_selected_geometric_certificate(self):
        metrics = audit_candidate(self.problem, self.candidate)
        self.assertEqual(metrics["changed_weight"], 1)
        self.assertEqual(metrics["changed_side_count"], 2)

    def test_changed_outsider_is_rejected(self):
        bad = deepcopy(self.candidate)
        outsider = self.problem["fixed"][0]
        bad["target"][outsider] = (bad["target"][outsider] + 1) % 4
        with self.assertRaises(AssertionError):
            audit_candidate(self.problem, bad)

    def test_partial_component_is_rejected(self):
        bad = deepcopy(self.candidate)
        bad["component"] = bad["component"][:-1]
        with self.assertRaises(AssertionError):
            audit_candidate(self.problem, bad)

    def test_fabricated_scc_and_cost_are_rejected(self):
        for field, value in (("dependencies", []), ("minimum_max_batch_size", 1),
                             ("changed_weight", 0), ("changed_record_ids", [])):
            bad = deepcopy(self.candidate)
            bad[field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                audit_candidate(self.problem, bad)

    def test_candidate_seed_and_duplicate_dependencies_are_rejected(self):
        for field, value in (("seed", "not-a-side"),
                             ("dependencies", self.candidate["dependencies"] * 2)):
            bad = deepcopy(self.candidate)
            bad[field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                audit_candidate(self.problem, bad)

    def test_attempt_coverage_and_reasons_are_independently_checked(self):
        audit_attempts(self.problem, self.result["attempts"])
        for field, value in (("seed", "not-a-side"), ("component", []),
                             ("fixed_hits", ["not-a-side"]),
                             ("blocked_reasons", ["fabricated-reason"])):
            attempts = deepcopy(self.result["attempts"])
            attempts[0][field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                audit_attempts(self.problem, attempts)
        attempts = deepcopy(self.result["attempts"])
        attempts[1] = attempts[0]
        with self.assertRaises(AssertionError):
            audit_attempts(self.problem, attempts)

    def test_all_target_oracle_detects_missing_archived_target(self):
        bad = deepcopy(self.profile)
        bad["candidate_profiles"].pop()
        with self.assertRaisesRegex(AssertionError, "oracle drift"):
            check_global_targets(self.small, self.small_checked, bad, None)

    def test_existing_report_is_preserved(self):
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "report.json"
            write_new_report({"original": True}, destination)
            original = destination.read_bytes()
            with self.assertRaises(FileExistsError):
                write_new_report({"replacement": True}, destination)
            self.assertEqual(destination.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()

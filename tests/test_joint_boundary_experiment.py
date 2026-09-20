"""Independent certificate replay and diagnostic-report scope checks."""

from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from fourcolor.joint_boundary import filter_boundary_books
from fourcolor.joint_boundary_restart import restart_joint_boundary_names
from scripts import validate_joint_boundary as experiment
from tests import test_level_sides_peer as peer_fixtures
from tests.test_joint_boundary import BOOK, matrix_of


class JointBoundaryExperimentTests(unittest.TestCase):
    """Reject altered evidence without asking the producer to certify itself."""

    @classmethod
    def setUpClass(cls):
        """Share the existing tiny geometry export used by prior protocol tests."""
        peer_fixtures.LevelSidePeerTests.setUpClass()
        cls.geometry = peer_fixtures.LevelSidePeerTests.geometry

    def test_full_proof_replay_and_mode_counter_mutations(self):
        """A mislabeled strategy or fabricated operation counter cannot pass."""
        geometry = self.geometry["mixed"]
        run = restart_joint_boundary_names(geometry, mode="joint")
        checked = experiment.verify_new_run(geometry, run)
        self.assertTrue(checked["propagation_deletions_independently_replayed"])
        for alteration in ("mode", "phase_mode", "statistics", "color"):
            changed = deepcopy(run)
            if alteration == "mode":
                changed["mode"] = "domains"
                changed["policy"] = "peer-batch-boundary-domains-pilot"
            elif alteration == "phase_mode":
                changed["propagation_phases"][0]["outcome"]["mode"] = "domains"
            elif alteration == "statistics":
                changed["statistics"]["conditional_cases"] += 1
            else:
                changed["colors"][0] = 99
            with self.subTest(alteration=alteration), self.assertRaises(ValueError):
                experiment.verify_new_run(geometry, changed)

    def test_conditional_replay_detects_omitted_branch_and_bad_update(self):
        """Local branch coverage and permitted pair unions are independently reconstructed."""
        matrix = matrix_of([[1, 2, 3, 4]] * 5)
        result = filter_boundary_books(matrix, [BOOK], mode="joint")
        decoded = experiment.decoded_matrix(matrix, 5)
        replayed, counts = experiment.replay_boundary(decoded, [BOOK], result, "joint")
        self.assertEqual(replayed, decoded)
        self.assertEqual(counts["independent_conditional_closures"], 12)
        omitted = deepcopy(result)
        omitted["events"][0]["branches"].pop()
        with self.assertRaisesRegex(ValueError, "branches"):
            experiment.replay_boundary(decoded, [BOOK], omitted, "joint")
        incorrect = deepcopy(result)
        incorrect["events"][0]["updates"].append({"sides": [0, 0]})
        with self.assertRaisesRegex(ValueError, "updates"):
            experiment.replay_boundary(decoded, [BOOK], incorrect, "joint")

    def test_local_oracle_and_witness_checks_do_not_trust_surviving_domains_alone(self):
        """The whole K2 book has 96 assignments; every witness pair must survive."""
        matrix = matrix_of([[1, 2, 3, 4]] * 5)
        oracle = experiment.exhaustive_local_projection(matrix, list(range(5)))
        self.assertEqual(oracle["surviving_assignments"], 96)
        colors = [1, 2, 3, 3, 3]
        outcome = {"domains": [[1, 2, 3, 4]] * 5, "relations": matrix}
        self.assertTrue(experiment.witness_survives(colors, outcome)["passed"])
        bad = deepcopy(outcome)
        bad["relations"][2][3] = 0
        with self.assertRaisesRegex(ValueError, "binary"):
            experiment.witness_survives(colors, bad)
        with self.assertRaisesRegex(ValueError, "2..8"):
            experiment.exhaustive_local_projection(matrix, list(range(9)))

    def test_checker_enforces_shared_edges_and_commitments(self):
        """Adjacent colors and dart anchors are independent obligations."""
        plane = SimpleNamespace(face_of_dart=[0, 1])
        adjacency = [{1}, {0}]
        self.assertTrue(experiment.check_coloring(plane, adjacency, [1, 2], {0: [1]})["passed"])
        for colors, anchors in (([1, 1], {}), ([1, 2], {0: [2]}), ([True, 2], {})):
            with self.subTest(colors=colors, anchors=anchors), self.assertRaises(ValueError):
                experiment.check_coloring(plane, adjacency, colors, anchors)

    def test_summary_separates_old_candidate_coverage_new_completion_and_regression(self):
        """One removed historical name cannot be counted as one successful map."""
        records = [
            {"key": "a", "cohort": "frozen-failure", "baseline_status": "conflict",
             "runs": {"domains": {"status": "conflict"}, "joint": {"status": "conflict"}}},
            {"key": "b", "cohort": "prior-diagnostic-control", "baseline_status": "solved",
             "runs": {"domains": {"status": "solved"}, "joint": {"status": "conflict"}}}]
        fatal = [{"modes": {"domains": {"fatal_name_excluded": False},
                             "joint": {"fatal_name_excluded": True}}}]
        summary = experiment.summarize(records, fatal)
        joint = next(row for row in summary["full_trajectory_comparison"]
                     if row["mode"] == "joint" and row["cohort"] == "all")
        self.assertEqual(joint["fixed_failures"], 0)
        self.assertEqual(joint["regressions"], 1)
        self.assertEqual(summary["frozen_first_fatal_candidates_excluded"]["joint"], 1)
        self.assertFalse(summary["full_corpus_run"])

    def test_fresh_report_preserves_existing_bytes(self):
        """Both compressed and plain output use exclusive creation."""
        with tempfile.TemporaryDirectory() as folder:
            for filename in ("report.json", "report.json.gz"):
                path = Path(folder) / filename
                experiment.write_report(path, {"original": True})
                before = path.read_bytes()
                with self.assertRaises(FileExistsError):
                    experiment.write_report(path, {"replacement": True})
                self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

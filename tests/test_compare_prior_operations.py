"""Check historical comparisons and reject forged operation-replay evidence."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from fourcolor.level_sides_peer import restart_level_peer_names
from fourcolor.prior_operation_restart import restart_prior_operation_names
from fourcolor.prior_rule_reuse import certified_pair_relations
from scripts import compare_prior_operations as experiment
from tests import test_level_sides_peer as peer_fixtures


class PriorOperationsExperimentTests(unittest.TestCase):
    """The checker must catch changed proofs, policies, and experiment scope."""

    @classmethod
    def setUpClass(cls):
        """Use existing small geometries plus one frozen template-bearing map."""
        peer_fixtures.LevelSidePeerTests.setUpClass()
        cls.geometry = peer_fixtures.LevelSidePeerTests.geometry
        cls.archives = {version: experiment.read_json(experiment.ROOT / path)
                        for version, (path, _) in experiment.ARCHIVES.items()}
        cls.least = cls.archives["v4"]["detailed_examples"][
            "83774b23a0d4ca689637eb9555de40af629ace7e0de4eedd9855bb4864c7baba"]["geometry"]

    def test_all_eight_modes_have_independent_replay(self):
        """Each factor combination has a declared initialization and scheduler."""
        self.assertEqual(len({experiment.mode_name(mode) for mode in experiment.MODES}), 8)
        for mode in experiment.MODES:
            with self.subTest(mode=mode):
                result = restart_prior_operation_names(self.geometry["mixed"], **mode)
                check = experiment.verify_run(self.geometry["mixed"], result, mode)
                self.assertTrue(check["passed"])
                self.assertTrue(check["final_legality"]["passed"])

    def test_geometry_and_replay_reject_forged_certificates_and_statistics(self):
        """Raw edges, every deduction, and its counters are separate obligations."""
        mode = {"initialization": "retained", "schedule": "ready", "implicit": True}
        certificates = certified_pair_relations(self.least)
        result = restart_prior_operation_names(self.least, **mode, certificates=certificates)
        self.assertTrue(experiment.verify_run(self.least, result, mode)["passed"])
        self.assertGreater(result["statistics"]["template_relation_bits_removed"], 0)
        for mutation in ("raw_edge", "event", "statistics", "phase_statistics", "mode"):
            altered = deepcopy(result)
            if mutation == "raw_edge":
                altered["implicit_certificates"][0]["required_adjacencies"][0]["raw_edge_ids"] = [-1]
            elif mutation == "event":
                event = next(phase["implicit_filter"]["trace"][0]
                             for call in altered["propagation_phases"]
                             for phase in call["outcome"]["phases"] if phase["implicit_filter"]["trace"])
                event["removed"] = 0
            elif mutation == "statistics":
                altered["statistics"]["template_relation_bits_removed"] += 1
            elif mutation == "phase_statistics":
                altered["propagation_phases"][0]["outcome"]["statistics"]["template_relation_bits_removed"] += 1
            else:
                altered["implicit"] = False
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                experiment.verify_run(self.least, altered, mode)

    def test_plain_history_comparison_includes_exact_choices_and_propagation(self):
        """Matching only final success must not count as historical reproduction."""
        geometry = self.geometry["mixed"]
        old = restart_level_peer_names(geometry)
        compact = {**old, "trace_sha256": experiment.digest(old["trace"]),
                   "propagation_phases_sha256": experiment.digest(old["propagation_phases"])}
        result = restart_prior_operation_names(geometry, initialization="frame", schedule="peer")
        self.assertTrue(experiment.check_baseline_reproduction(result, compact)["passed"])
        altered = deepcopy(result)
        altered["propagation_phases"][0]["outcome"]["revisions"] += 1
        with self.assertRaisesRegex(ValueError, "propagation"):
            experiment.check_baseline_reproduction(altered, compact)
        altered = deepcopy(result)
        altered["trace"][0]["symbol"] = 99
        with self.assertRaisesRegex(ValueError, "trace"):
            experiment.check_baseline_reproduction(altered, compact)

    def test_selection_covers_every_old_failure_without_dropping_controls(self):
        """The fixed 49 include fourteen distinct failures across three policies."""
        keys, _, failures, controls = experiment.select_inventory(self.archives)
        self.assertEqual(len(keys), 49)
        self.assertEqual(len(set.union(*failures.values())), 14)
        self.assertEqual(len(controls), 40)
        altered = dict(self.archives)
        altered["v4"] = {**altered["v4"], "diagnostic_keys": altered["v4"]["diagnostic_keys"][:-1]}
        with self.assertRaisesRegex(ValueError, "control selection"):
            experiment.select_inventory(altered)

    def test_summaries_keep_repairs_and_regressions_separate(self):
        """A new success on one graph must not hide a new failure on another."""
        names = [experiment.mode_name(mode) for mode in experiment.MODES]
        records = [
            {"key": "old-failure", "historical": {version: {"status": "conflict"} for version in experiment.ARCHIVES},
             "runs": {name: {"status": "solved" if name.endswith("implicit") else "conflict"} for name in names}},
            {"key": "control", "historical": {version: {"status": "solved"} for version in experiment.ARCHIVES},
             "runs": {name: {"status": "conflict" if name.endswith("implicit") else "solved"} for name in names}},
        ]
        summary = experiment.summarize(records)
        self.assertFalse(summary["full_corpus_run"])
        self.assertFalse(summary["per_map_policy_selection"])
        for contrast in summary["implicit_factor_contrasts"]:
            self.assertEqual((contrast["fixed_failures"], contrast["regressions"]), (1, 1))
        chosen = next(row for row in summary["policy_comparisons"]
                      if row["mode"] == "retained-ready-implicit" and row["reference"] == "v4")
        self.assertEqual(chosen["fixed_keys"], ["old-failure"])
        self.assertEqual(chosen["regression_keys"], ["control"])

    def test_report_writes_are_exclusive(self):
        """A rerun needs new output paths and cannot silently replace evidence."""
        with tempfile.TemporaryDirectory() as folder:
            for name in ("report.json", "report.json.gz"):
                path = Path(folder) / name
                experiment.write_report(path, {"original": True})
                original = path.read_bytes()
                with self.assertRaises(FileExistsError):
                    experiment.write_report(path, {"replacement": True})
                self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()

"""The new relation rule must preserve geometry-only restarting semantics."""

from copy import deepcopy
from functools import lru_cache
import gzip
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from fourcolor.level_sides_peer import restart_level_peer_names
from fourcolor.structural_restart import restart_structural_names
from scripts.validate_structural_restart import verify_run


@lru_cache(maxsize=1)
def failure_geometry():
    """Use the frozen genuine geometry, not a convenient replacement graph."""
    path = Path(__file__).resolve().parents[1] / "outputs/level-sides-peer-full-2026-09-19.json.gz"
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)["least_conflict"]["geometry"]


class StructuralRestartTests(unittest.TestCase):
    """Regression, ablation and no-rescue behavior for the actual old failure."""

    @classmethod
    def setUpClass(cls):
        """Run the core once, then deep-copy any evidence before altering it."""
        cls.geometry = failure_geometry()
        cls.result = restart_structural_names(cls.geometry)

    def test_real_old_failure_is_repaired_by_a_relation_before_commit(self):
        """The wrong proposal is rejected before entering permanent anchors."""
        self.assertEqual(self.result["status"], "solved")
        event = self.result["events"][0]
        self.assertEqual((event["kind"], event["proposal"]["side"], event["proposal"]["symbol"]),
                         ("learn_relation", 10, 2))
        self.assertEqual(event["learned_pair"], [1, 10])
        calls = self.result["propagation_phases"]
        self.assertEqual(calls[0]["anchors_by_dart"], calls[1]["anchors_by_dart"])
        self.assertEqual((self.result["trace"][0]["side"], self.result["trace"][0]["symbol"]), (10, 3))
        self.assertTrue(verify_run(self.geometry, self.result)["passed"])

    def test_disabled_extension_reproduces_old_v2_decisions_and_states(self):
        """Turning the new rule off must not silently alter the baseline."""
        with patch("fourcolor.structural_restart.refute_same_name", side_effect=AssertionError("no structural calls")):
            disabled = restart_structural_names(self.geometry, structural=False)
        old = restart_level_peer_names(self.geometry)
        for field in ("status", "trace", "domains", "relations", "anchors_by_dart", "colors", "levels", "units"):
            self.assertEqual(disabled[field], old[field], field)
        for new_call, old_call in zip(disabled["propagation_phases"], old["propagation_phases"]):
            for key in ("status", "domains", "relations", "revisions", "hall_conflict"):
                self.assertEqual(new_call["outcome"][key], old_call["outcome"][key])
            for new_phase, old_phase in zip(new_call["outcome"]["phases"], old_call["outcome"]["phases"]):
                self.assertEqual({key: new_phase[key] for key in old_phase}, old_phase)
        self.assertTrue(verify_run(self.geometry, disabled)["passed"])

    def test_inconclusive_queries_do_not_trigger_hidden_solver(self):
        """When no structural proof is available, the old failed path stays failed."""
        with patch("fourcolor.structural_restart.refute_same_name", return_value={"status": "inconclusive"}):
            row = restart_structural_names(self.geometry)
        self.assertEqual(row["status"], "conflict")
        self.assertEqual(row["learned_pairs"], [])
        self.assertEqual((row["choices"], row["backtracks"]), (1, 0))

    def test_geometry_and_history_metadata_are_not_mutated(self):
        """An unused foreign-color field cannot inject a prior coloring."""
        geometry = deepcopy(self.geometry)
        geometry["previous_colors"] = [99] * 19
        original = deepcopy(geometry)
        result = restart_structural_names(geometry)
        self.assertEqual(geometry, original)
        self.assertEqual(result, self.result)
        self.assertFalse(result["old_colors_read"])

    def test_every_query_reads_only_geometry_and_an_unordered_pair(self):
        """Queries are cached graph questions, not color-value or endpoint searches."""
        pairs = [tuple(row["pair"]) for row in self.result["proof_queries"]]
        self.assertEqual(len(pairs), len(set(pairs)))
        self.assertTrue(all(a < b for a, b in pairs))
        self.assertTrue(all(row["certificate"]["assumed_equal"] == row["pair"]
                            for row in self.result["proof_queries"]))
        self.assertNotIn([1, 10], [row["pair"] for row in self.result["geometric_edge_sources"]])

    def test_nonboolean_ablation_is_rejected(self):
        with self.assertRaises(ValueError):
            restart_structural_names(self.geometry, structural=1)


if __name__ == "__main__":
    unittest.main()

"""Historical operation ablations must reproduce their unmodified baselines."""

from copy import deepcopy
from pathlib import Path
import unittest

from fourcolor.level_sides_peer import restart_level_peer_names
from fourcolor.peer_batches import restart_peer_batch_names
from fourcolor.prior_operation_restart import restart_prior_operation_names
from fourcolor.prior_rule_reuse import certified_pair_relations
from fourcolor.staged_levels import restart_staged_level_names
from scripts.validate_frontier_restart import read_json
from tests import test_level_sides_peer as peer_fixtures


class PriorOperationRestartTests(unittest.TestCase):
    """No favorable old coloring or different strategy may rescue a new run."""

    @classmethod
    def setUpClass(cls):
        """Load tiny geometry fixtures and one frozen failed map, not its colors."""
        peer_fixtures.LevelSidePeerTests.setUpClass()
        cls.geometries = peer_fixtures.LevelSidePeerTests.geometry
        root = Path(__file__).resolve().parents[1]
        archive = read_json(root / "outputs/peer-batches-full-2026-09-19.json.gz")
        cls.least = archive["detailed_examples"][
            "83774b23a0d4ca689637eb9555de40af629ace7e0de4eedd9855bb4864c7baba"]["geometry"]

    def test_three_plain_modes_match_all_old_mathematical_outputs(self):
        """Keeping the old operations must exactly preserve their traces."""
        modes = (("frame", "peer", restart_level_peer_names),
                 ("retained", "peer", restart_staged_level_names),
                 ("retained", "ready", restart_peer_batch_names))
        for name in ("blank", "dangling", "grid", "mixed"):
            for initialization, schedule, baseline in modes:
                with self.subTest(name=name, initialization=initialization, schedule=schedule):
                    geometry = self.geometries[name]
                    old = baseline(geometry)
                    new = restart_prior_operation_names(geometry, initialization, schedule)
                    for key in ("status", "trace", "domains", "relations", "colors",
                                "anchors_by_dart", "initial_anchors_by_dart", "hall_conflict"):
                        self.assertEqual(new[key], old[key], key)
                    self.assertEqual(new["statistics"]["template_relation_bits_removed"], 0)
                    self.assertEqual(len(old["propagation_phases"]), len(new["propagation_phases"]))
                    for previous, current in zip(old["propagation_phases"], new["propagation_phases"]):
                        for key in previous["outcome"]:
                            if key == "phases":
                                continue
                            self.assertEqual(previous["outcome"][key], current["outcome"][key], key)

    def test_minimum_failure_has_identical_state_before_ready_gate_divergence(self):
        """Only selection differs at this exact state; no result is borrowed."""
        peer = restart_prior_operation_names(self.least, "retained", "peer")
        ready = restart_prior_operation_names(self.least, "retained", "ready")
        self.assertEqual(peer["propagation_phases"][1], ready["propagation_phases"][1])
        self.assertEqual(peer["trace"][1]["side"], 13)
        self.assertEqual(peer["trace"][1]["domain"], [3, 4])
        self.assertEqual(ready["trace"][1]["side"], 4)
        self.assertEqual(ready["trace"][1]["domain"], [2, 3, 4])
        self.assertEqual(peer["status"], "solved")
        self.assertEqual(ready["status"], "conflict")

    def test_geometry_only_certificates_block_known_fatal_name_without_color_probe(self):
        """Check the previously proved implication, not a hand-picked answer."""
        geometry = self.least
        before = deepcopy(geometry)
        certificates = certified_pair_relations(geometry)
        result = restart_prior_operation_names(geometry, implicit=True, certificates=certificates)
        self.assertEqual(geometry, before)
        self.assertTrue(any(set(c["conclusion"]["sides"]) == {1, 4} for c in certificates))
        self.assertNotIn(2, result["propagation_phases"][1]["outcome"]["domains"][4])
        self.assertEqual(result["backtracks"], 0)
        self.assertFalse(result["old_colors_read"])
        self.assertIsNone(result["local_budget"])
        self.assertEqual(result, restart_prior_operation_names(
            {**geometry, "old_colors": [99], "colors": [99]}, implicit=True))

    def test_invalid_switches_and_forged_certificates_are_rejected(self):
        """Policy identity and raw-edge proof authentication are required."""
        blank = self.geometries["blank"]
        for kwargs in ({"initialization": "auto"}, {"schedule": "best"}, {"implicit": 1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                restart_prior_operation_names(blank, **kwargs)
        certificates = certified_pair_relations(self.least)
        forged = deepcopy(certificates)
        forged[0]["required_adjacencies"][0]["raw_edge_ids"] = [-1]
        with self.assertRaises(ValueError):
            restart_prior_operation_names(self.least, implicit=True, certificates=forged)
        with self.assertRaises(ValueError):
            restart_prior_operation_names(self.least, implicit=False, certificates=certificates)


if __name__ == "__main__":
    unittest.main()

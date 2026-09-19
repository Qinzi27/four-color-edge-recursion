"""Finite replay and adversarial metadata tests for coarse-to-fine scheduling.

Archived failures are regression inputs, not unseen evidence. Their outcomes
are certified without assuming the new candidate must solve them. No archived
color or witness is passed to the production naming function.
"""

from copy import deepcopy
from pathlib import Path
import unittest

from fourcolor.peer_batches import POLICY, restart_peer_batch_names
from fourcolor.whole_lines import build_whole_lines
from scripts.validate_frontier_restart import json_value, read_json
from scripts.validate_peer_batches import independent_batches, verify_run
from tests import test_level_sides_peer as peer_fixtures
from tests.test_frontier_restart import side_profile


ROOT = Path(__file__).resolve().parents[1]
LEAST_FAILURE = "dc9cebec632a0762379de1441eea298761571ed5faf53f484d3672c4a6ce8739"
BLUE = "8070783fd68de9a9dd22c6d4c8831a55c330290f4a30e2e9c8f6edb70af66132"


class PeerBatchTests(unittest.TestCase):
    """A batch groups geometry; it does not force all descendants to one name."""

    @classmethod
    def setUpClass(cls):
        """Reuse trusted geometry fixtures and all four exact archived failures."""
        peer_fixtures.LevelSidePeerTests.setUpClass()
        cls.geometry = dict(peer_fixtures.LevelSidePeerTests.geometry)
        archive = read_json(ROOT / "outputs/staged-levels-full-2026-09-19.json.gz")
        cls.details = archive["detailed_examples"]
        cls.failures = {key: value for key, value in cls.details.items()
                        if value["outcome"]["status"] == "conflict"}

    def checked(self, geometry):
        """Require independent replay even if the candidate reaches a conflict."""
        before = deepcopy(geometry)
        result = restart_peer_batch_names(geometry)
        self.assertEqual(geometry, before)
        original = deepcopy(result)
        audit = verify_run(geometry, result)
        self.assertEqual(result, original)
        self.assertTrue(audit["passed"])
        self.assertEqual(result["policy"], POLICY)
        self.assertFalse(result["old_colors_read"])
        self.assertEqual(result["backtracks"], 0)
        if result["status"] == "solved":
            self.assertTrue(audit["final_legality"]["passed"])
        else:
            self.assertEqual(result["status"], "conflict")
            self.assertIsNone(result["colors"])
        return result

    def test_five_through_mothers_activate_together_before_internal_shores(self):
        """The user's five lines yield six coarse strips, not final equalities."""
        geometry = self.failures[LEAST_FAILURE]["geometry"]
        result = self.checked(geometry)
        batch = result["batch_geometry"]
        second = next(row for row in batch["stages"] if row["stage"] == 2)
        self.assertEqual(second["new_mothers"],
                         [f"L:{x},0>{x},600" for x in (190, 274, 551, 708, 817)])
        self.assertEqual(len(second["coarse_cells"]), 7)  # Six inner strips plus exterior.
        self.assertEqual(second["ready_sides"], [0, 3, 4, 5, 6])
        self.assertEqual(batch["side_ready_stage"],
                         [1, 3, 3, 2, 2, 2, 2, 3, 4, 4, 4, 3, 4, 3, 3, 4, 4, 4])
        self.assertEqual(result["trace"][0]["side"], 2)
        self.assertEqual(result["trace"][0]["symbol"], 2)
        # The safe first normalization may precede its readiness stage; the
        # next ordinary choice must no longer be the old premature side 13.
        self.assertIn(result["trace"][1]["side"], [3, 4, 5, 6])
        self.assertEqual(result["trace"][1]["active_stage"], 2)

    def test_bfs_singleton_stages_equal_maximum_real_boundary_stage(self):
        """Independent removal/reachability agrees with the elementary formula."""
        for name, geometry in self.geometry.items():
            with self.subTest(name=name):
                result = self.checked(geometry)
                model = build_whole_lines(geometry)
                expected = [1] * len(model.plane_map.faces)
                stages = result["batch_geometry"]["mother_stages"]
                for edge, mother in model.edge_owner.items():
                    first, second = model.plane_map.shores(edge)
                    if first != second:
                        expected[first] = max(expected[first], stages[mother])
                        expected[second] = max(expected[second], stages[mother])
                self.assertEqual(result["batch_geometry"]["side_ready_stage"], expected)

    def test_blank_and_dangling_bridges_do_not_postpone_the_inner_side(self):
        """Dangling edges add no real inequality or new region to unfold."""
        for key in ("blank", "dangling"):
            with self.subTest(key=key):
                result = self.checked(self.geometry[key])
                self.assertEqual(result["status"], "solved")
                self.assertEqual(result["batch_geometry"]["side_ready_stage"], [1, 1])
                self.assertEqual(result["choices"], 1)

    def test_t_and_x_contacts_preserve_whole_mother_activation(self):
        """Middle ports cannot split a geometric mother into extra generations."""
        for key in ("T", "X"):
            with self.subTest(key=key):
                result = self.checked(self.geometry[key])
                batch = result["batch_geometry"]
                self.assertEqual(batch["mother_stages"]["L:0,300>900,300"], 2)
                if key == "X":
                    self.assertEqual(batch["mother_stages"]["L:450,0>450,600"], 2)

    def test_unknown_levels_share_a_declared_bucket_but_remain_unknown(self):
        """Activation order does not assert an unavailable ancestry theorem."""
        for key in ("island", "triangle", "polyline", "mixed"):
            with self.subTest(key=key):
                result = self.checked(self.geometry[key])
                self.assertTrue(result["unranked_mothers"])
                batch = result["batch_geometry"]
                maximum = max(row["level"] for row in result["levels"].values()
                              if row["level"] is not None)
                self.assertEqual(batch["unranked_stage"], maximum + 1)
                for name in result["unranked_mothers"]:
                    self.assertIsNone(result["levels"][name]["level"])
                    self.assertEqual(batch["mother_stages"][name], maximum + 1)

    def test_all_four_old_failures_and_blue_are_freshly_certified(self):
        """Tests never convert an old valid witness into a new solver result."""
        self.assertEqual(len(self.failures), 4)
        for key, archived in {**self.failures, BLUE: self.details[BLUE]}.items():
            with self.subTest(key=key):
                self.checked(archived["geometry"])

    def test_all_post_initial_choices_use_the_least_unresolved_ready_stage(self):
        """Later coarse regions cannot bypass existing ready unresolved shores."""
        geometry = self.failures[LEAST_FAILURE]["geometry"]
        result = self.checked(geometry)
        ready = result["batch_geometry"]["side_ready_stage"]
        for index, step in enumerate(result["trace"][1:], start=1):
            domains = result["propagation_phases"][index]["outcome"]["domains"]
            active = min(ready[side] for side, domain in enumerate(domains) if len(domain) > 1)
            self.assertEqual(step["active_stage"], active)
            self.assertEqual(step["ready_stage"], active)
            self.assertEqual(step["eligible_side_ids"],
                             [side for side, domain in enumerate(domains)
                              if len(domain) > 1 and ready[side] == active])

    def test_internal_one_reuse_is_not_replaced_with_a_stage_color_ban(self):
        """Readiness decides when to choose, not a permanent inherited palette."""
        result = self.checked(self.geometry["grid"])
        ones = [step for step in result["trace"] if step["symbol"] == 1]
        self.assertTrue(ones)
        self.assertTrue(all(step["boundary"]["one_allowed"] for step in ones))

    def test_old_colors_and_claimed_stage_fields_never_affect_geometry_only_run(self):
        """The producer must ignore all caller-supplied coloring suggestions."""
        geometry = self.geometry["mixed"]
        poisoned = deepcopy(geometry)
        poisoned.update(old_colors=[99], colors=[99], batch_geometry={"side_ready_stage": [999]},
                        levels={"frame": 999}, initialization={"symbol": 99})
        self.assertEqual(restart_peer_batch_names(poisoned), restart_peer_batch_names(geometry))

    def test_stroke_reversal_degree_two_and_json_roundtrip_are_deterministic(self):
        """The stage certificate survives representation changes to same lines."""
        for base, alternate in (("grid", "grid-reversed"), ("grid", "grid-reordered"),
                                ("horizontal", "degree-two"), ("polyline", "polyline-reversed")):
            with self.subTest(base=base, alternate=alternate):
                first = self.checked(self.geometry[base])
                second = self.checked(self.geometry[alternate])
                self.assertTrue(verify_run(self.geometry[base], json_value(first))["passed"])
                self.assertEqual(side_profile(build_whole_lines(self.geometry[base]), first["domains"]),
                                 side_profile(build_whole_lines(self.geometry[alternate]), second["domains"]))

    def test_checker_rejects_coarse_cells_stages_and_ready_metadata_forgery(self):
        """Final legal colors cannot excuse a fabricated batch derivation."""
        geometry = self.failures[LEAST_FAILURE]["geometry"]
        genuine = restart_peer_batch_names(geometry)
        for kind in ("mother-stage", "unranked-stage", "coarse-cell", "ready-side",
                     "newly-ready", "active-mothers", "new-mothers", "side-ready", "stage-number"):
            with self.subTest(kind=kind):
                forged = deepcopy(genuine)
                batch = forged["batch_geometry"]
                row = batch["stages"][1]
                if kind == "mother-stage":
                    batch["mother_stages"]["frame"] = 999
                elif kind == "unranked-stage":
                    batch["unranked_stage"] = 999
                elif kind == "coarse-cell":
                    row["coarse_cells"] = [[side] for side in range(len(forged["domains"]))]
                elif kind == "ready-side":
                    row["ready_sides"].append(13)
                elif kind == "newly-ready":
                    row["newly_ready_sides"] = []
                elif kind == "active-mothers":
                    row["active_mothers"] = []
                elif kind == "new-mothers":
                    row["new_mothers"] = []
                elif kind == "side-ready":
                    batch["side_ready_stage"][13] = 2
                else:
                    row["stage"] = 999
                with self.assertRaises(AssertionError):
                    verify_run(geometry, forged)

    def test_checker_rejects_choice_and_initialization_metadata_forgery(self):
        """Replay checks every shown score as well as the geometry selection."""
        geometry = self.failures[LEAST_FAILURE]["geometry"]
        genuine = restart_peer_batch_names(geometry)
        mutations = {"ready_stage": 999, "active_stage": 999, "eligible_side_ids": [],
                     "coarse_cell": [999], "urgency": 999, "unresolved_neighbors": 999,
                     "constraint_weight": 999, "including_named_weight": 999,
                     "tied_units": [], "unresolved_shores": [], "mother": "frame",
                     "choice_kind": "initial-retained-name", "selection_group": "unknown"}
        for field, value in mutations.items():
            with self.subTest(field=field):
                forged = deepcopy(genuine)
                forged["trace"][1][field] = value
                with self.assertRaises(AssertionError):
                    verify_run(geometry, forged)
        forged = deepcopy(genuine)
        forged["initialization"]["prebound_final_inner_anchor"] = True
        with self.assertRaises(AssertionError):
            verify_run(geometry, forged)


if __name__ == "__main__":
    unittest.main()

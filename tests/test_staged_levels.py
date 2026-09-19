"""Finite geometry and adversarial-certificate tests for stage initialization.

The archived blue-box example is a regression fixture, not an unseen test.
These checks distinguish a corrected first retained name from guaranteed
completion of every future greedy path or every plane map.
"""

from copy import deepcopy
from pathlib import Path
import unittest

from fourcolor.level_sides_peer import restart_level_peer_names
from fourcolor.staged_levels import POLICY, restart_staged_level_names
from fourcolor.whole_lines import build_whole_lines
from scripts.validate_frontier_restart import json_value, read_json
from scripts.validate_global_restart import export_geometries
from scripts.validate_staged_levels import verify_run
from tests import test_level_sides_peer as peer_fixtures
from tests.test_frontier_restart import side_profile


ROOT = Path(__file__).resolve().parents[1]


class StagedLevelTests(unittest.TestCase):
    """No prior coloring enters a run, and every active decision is replayed."""

    @classmethod
    def setUpClass(cls):
        """Use frozen tiny geometry and one explicit vertical first split."""
        peer_fixtures.LevelSidePeerTests.setUpClass()
        cls.geometry = dict(peer_fixtures.LevelSidePeerTests.geometry)
        vertical = export_geometries([{"key": "vertical", "document": {"strokes": [
            {"a": [450, 0], "b": [450, 600]}]}}])[0]
        cls.geometry["vertical"] = vertical["geometry"]
        # The long diagonal has two frame endpoints but its two current shores
        # touch the frame only at points. Endpoint incidence alone is not enough.
        point_touch = [((0, 0), (900, 600)), ((0, 0), (900, 200)),
                       ((0, 0), (300, 600)), ((900, 600), (600, 0)),
                       ((900, 600), (0, 400))]
        exported = export_geometries([{"key": "point-touch", "document": {"strokes": [
            {"a": first, "b": second} for first, second in point_touch]}}])[0]
        cls.geometry["point-touch"] = exported["geometry"]
        archive = read_json(ROOT / "outputs/level-sides-peer-full-2026-09-19.json.gz")
        cls.blue = archive["least_conflict"]
        cls.six = read_json(ROOT / "outputs/level-sides-six-2026-09-19.json.gz")["records"]

    def checked(self, geometry):
        """A solved run needs both a replay certificate and final edge audit."""
        result = restart_staged_level_names(geometry)
        before = deepcopy(result)
        audit = verify_run(geometry, result)
        self.assertTrue(audit["passed"])
        self.assertEqual(result, before)
        self.assertEqual(result["policy"], POLICY)
        self.assertEqual(len(result["initial_anchors_by_dart"]), 1)
        self.assertEqual(list(result["initial_anchors_by_dart"].values()), [[1]])
        self.assertEqual(result["backtracks"], 0)
        self.assertFalse(result["old_colors_read"])
        self.assertEqual(len(result["propagation_phases"]), result["choices"] + 1)
        self.assertEqual(result["trace"][0]["choice_kind"], "initial-retained-name")
        self.assertEqual(result["trace"][0]["symbol"], 2)
        self.assertEqual(result["trace"][0]["domain"], [2, 3, 4])
        for step in result["trace"]:
            self.assertEqual(step["symbol"], min(step["domain"]))
        if result["status"] == "solved":
            self.assertTrue(audit["final_legality"]["passed"])
            self.assertEqual(audit["claim"], "complete-proper-four-names")
        else:
            self.assertEqual(result["status"], "conflict")
            self.assertIsNone(result["colors"])
        return result

    def test_blank_and_dangling_keep_only_the_real_initial_inner_name(self):
        """A dangling bridge does not split its side or create a false mother."""
        for key in ("blank", "dangling"):
            with self.subTest(key=key):
                result = self.checked(self.geometry[key])
                self.assertEqual(result["status"], "solved")
                self.assertEqual(result["choices"], 1)
                self.assertEqual(sorted(result["colors"]), [1, 2])
                self.assertEqual(result["trace"][0]["mother"], "frame")

    def test_first_horizontal_vertical_t_and_x_mothers_are_true_full_lines(self):
        """T/X ports retain parent identity instead of becoming new endpoints."""
        expected = {"horizontal": "L:0,300>900,300", "vertical": "L:450,0>450,600",
                    "T": "L:0,300>900,300", "X": "L:450,0>450,600"}
        for key, mother in expected.items():
            with self.subTest(key=key):
                result = self.checked(self.geometry[key])
                self.assertEqual(result["status"], "solved")
                step = result["trace"][0]
                self.assertEqual(step["mother"], mother)
                self.assertEqual(step["parents"], [["frame"], ["frame"]])
                self.assertEqual(step["level"], 2)
                self.assertTrue(step["frame_boundary_edges"])

    def test_unranked_islands_and_polylines_remain_eligible_without_fabricated_levels(self):
        """Absence of a straight through-mother invokes a declared frame anchor."""
        for key in ("island", "triangle", "polyline", "mixed"):
            with self.subTest(key=key):
                result = self.checked(self.geometry[key])
                self.assertEqual(result["status"], "solved")
                self.assertTrue(result["unranked_mothers"])
                self.assertTrue(all(result["levels"][name]["level"] is None
                                    for name in result["unranked_mothers"]))
                if key != "mixed":
                    self.assertEqual(result["trace"][0]["mother"], "frame")

    def test_old_blue_box_conflict_now_anchors_its_retained_bottom_name_first(self):
        """The first interior 2 cannot be preassigned to the final top-left side."""
        self.assertEqual(self.blue["key"],
                         "8070783fd68de9a9dd22c6d4c8831a55c330290f4a30e2e9c8f6edb70af66132")
        geometry = self.blue["geometry"]
        self.assertEqual(restart_level_peer_names(geometry)["status"], "conflict")
        result = self.checked(geometry)
        first = result["trace"][0]
        self.assertEqual((first["mother"], first["side"], first["symbol"]),
                         ("L:0,412>900,412", 10, 2))
        self.assertEqual(result["status"], "solved")
        self.assertEqual(result["colors"][10], 2)
        self.assertNotEqual(result["colors"][1], 2)

    def test_point_contacts_do_not_fake_a_frame_boundary_exclusion(self):
        """A through diagonal with no real frame-adjacent shore is ineligible."""
        result = self.checked(self.geometry["point-touch"])
        diagonal = "L:0,0>900,600"
        self.assertTrue(all("frame" in port for port in
                            result["levels"][diagonal]["endpoint_contacts"]))
        self.assertNotIn(diagonal, result["initialization"]["eligible_mothers"])
        self.assertEqual(result["trace"][0]["mother"], "L:0,0>900,200")
        self.assertEqual(result["trace"][0]["frame_boundary_edges"], [1, 2])

    def test_internal_current_side_can_reuse_one_despite_ancestral_frame_one(self):
        """The root's 1 does not become a permanent prohibition on descendants."""
        result = self.checked(self.geometry["grid"])
        choices = [step for step in result["trace"] if step["symbol"] == 1]
        self.assertTrue(choices)
        for step in choices:
            self.assertTrue(step["boundary"]["one_allowed"])
            self.assertNotIn(1, step["boundary"]["direct_forbidden"])
            self.assertNotEqual(step["side"], self.geometry["grid"]["outerFace"])

    def test_six_archived_diagnostics_are_recomputed_and_certified_not_assumed_successful(self):
        """Outcome checking never treats their old valid colors as an input."""
        self.assertEqual(len(self.six), 6)
        for archived in self.six:
            with self.subTest(key=archived["key"]):
                self.checked(archived["geometry"])

    def test_old_names_claimed_levels_and_suggested_initialization_do_not_change_run(self):
        """Caller metadata is deliberately irrelevant to a geometry-only restart."""
        clean = self.geometry["mixed"]
        poisoned = deepcopy(clean)
        poisoned.update({"old_colors": [99], "colors": [99], "levels": {"frame": 999},
                         "anchors_by_dart": {0: [99]}, "initialization": {"side": 999},
                         "retained_name": 99, "inherited_forbidden": [1, 2, 3, 4]})
        before = deepcopy(poisoned)
        self.assertEqual(restart_staged_level_names(poisoned), restart_staged_level_names(clean))
        self.assertEqual(poisoned, before)

    def test_repeated_runs_input_reversal_and_json_storage_are_deterministic(self):
        """Coordinate reading conventions survive stroke reversal and JSON keys."""
        for baseline, variants in (("grid", ("grid-reordered", "grid-reversed")),
                                   ("polyline", ("polyline-reversed",)),
                                   ("horizontal", ("degree-two",))):
            original = self.checked(self.geometry[baseline])
            self.assertEqual(original, restart_staged_level_names(self.geometry[baseline]))
            self.assertTrue(verify_run(self.geometry[baseline], json_value(original))["passed"])
            expected = side_profile(build_whole_lines(self.geometry[baseline]), original["domains"])
            for key in variants:
                alternate = self.checked(self.geometry[key])
                self.assertEqual(side_profile(build_whole_lines(self.geometry[key]),
                                              alternate["domains"]), expected)

    def test_checker_rejects_initial_anchor_choice_and_provenance_tampering(self):
        """A plausible final coloring cannot hide an invalid initialization."""
        geometry = self.geometry["grid"]
        genuine = restart_staged_level_names(geometry)
        for corruption in ("old-inner-anchor", "chosen-symbol", "choice-kind", "frame-edge",
                           "mother", "priority", "boundary", "phase-zero"):
            with self.subTest(corruption=corruption):
                forged = deepcopy(genuine)
                step = forged["trace"][0]
                if corruption == "old-inner-anchor":
                    outer_dart = next(iter(forged["initial_anchors_by_dart"]))
                    forged["initial_anchors_by_dart"][outer_dart ^ 1] = [2]
                elif corruption == "chosen-symbol":
                    step["symbol"] = 3
                elif corruption == "choice-kind":
                    step["choice_kind"] = "greedy-not-a-proved-safe-extension"
                elif corruption == "frame-edge":
                    step["frame_boundary_edges"] = []
                elif corruption == "mother":
                    step["mother"] = "frame"
                elif corruption == "priority":
                    step["priority"] = [0, 0, 0, 0]
                elif corruption == "boundary":
                    step["boundary"]["sources"].pop()
                else:
                    forged["propagation_phases"][0]["anchors_by_dart"][step["dart"]] = [2]
                with self.assertRaises(AssertionError):
                    verify_run(geometry, forged)

    def test_checker_rejects_later_greedy_and_level_tampering(self):
        """Initialization is not a license to skip ordinary later-choice audits."""
        geometry = self.geometry["mixed"]
        genuine = restart_staged_level_names(geometry)
        self.assertGreater(len(genuine["trace"]), 1)
        for corruption in ("symbol", "level", "group", "unranked", "units"):
            with self.subTest(corruption=corruption):
                forged = deepcopy(genuine)
                step = forged["trace"][1]
                if corruption == "symbol":
                    step["symbol"] = max(step["domain"])
                elif corruption == "level":
                    step["level"] = 999
                elif corruption == "group":
                    step["selection_group"] = "invented-equal-generation"
                elif corruption == "unranked":
                    forged["unranked_mothers"] = []
                else:
                    forged["units"].pop()
                with self.assertRaises(AssertionError):
                    verify_run(geometry, forged)

    def test_checker_rejects_every_initialization_metadata_mutation(self):
        """Metadata is independently derived rather than accepted as narration."""
        geometry = self.geometry["horizontal"]
        genuine = restart_staged_level_names(geometry)
        replacements = {
            "mode": "frame-interior-no-eligible-through-mother",
            "eligible_mothers": [], "mother": "frame", "side": 999, "dart": 999,
            "frame_boundary_edges": [], "domain_before": [2], "symbol": 3,
            "historical_frame_pair": [1, 3], "coarse_split_pair_unordered": [2, 4],
            "birth_pair_is_not_a_final_profile_constraint": False,
            "outside_dart": 999, "outside_side": 999,
            "prebound_final_inner_anchor": True,
        }
        self.assertEqual(set(replacements), set(genuine["initialization"]))
        for field, replacement in replacements.items():
            with self.subTest(field=field):
                forged = deepcopy(genuine)
                self.assertNotEqual(forged["initialization"][field], replacement)
                forged["initialization"][field] = replacement
                with self.assertRaises(AssertionError):
                    verify_run(geometry, forged)


if __name__ == "__main__":
    unittest.main()

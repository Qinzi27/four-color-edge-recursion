"""Regression checks for the bounded current-name policy, not completeness.

Rectangle cases verify actual geometry. The last two adjacency-only examples
test the conditional two-name theorem and are not counted as rectangle maps.
"""

from copy import deepcopy
import unittest

from fourcolor.anchor_forest import _state_adjacency
from fourcolor.current_names import attempt_current_cut, release_neighbor_names
from fourcolor.inherited_names import RectSide, RectState, initial_state
from fourcolor.local_reuse import solve_two_name_patch
from scripts.compare_local_marks import validate_state
from scripts.validate_local_reuse import declared_cases, E_CUTS, E_PENDING


def frozen_case(key):
    """Read the declared old fixture rather than inventing a replacement."""
    return next(case for case in declared_cases() if case["key"] == key)


def symbols(state):
    """Include the fixed exterior explicitly in every name comparison."""
    return {"outside": 1, **{side.id: side.symbol for side in state.sides}}


def simple_graph(vertices, edges):
    """Create a symmetric adjacency-only theorem fixture."""
    graph = {vertex: set() for vertex in ["outside", *vertices]}
    for first, second in edges:
        graph[first].add(second)
        graph[second].add(first)
    return graph


def interior_one_state():
    """An internal parent1 has top3, bottom4, and two exterior-touching flank2s."""
    return RectState(900, 600, (
        RectSide("T", (0, 0, 900, 180), 3),
        RectSide("B", (0, 420, 900, 600), 4),
        RectSide("L", (0, 180, 300, 420), 2),
        RectSide("M", (300, 180, 600, 420), 1),
        RectSide("R", (600, 180, 900, 420), 2),
    ), (((0, 180), (900, 180)), ((0, 420), (900, 420)),
        ((300, 180), (300, 420)), ((600, 180), (600, 420))))


class CurrentNamesTests(unittest.TestCase):
    """Keep preservation, release, and pinned-patch claims independently checked."""

    def test_all_five_declared_restarts_complete_with_legal_boundaries(self):
        """All named construction histories are replayed, without changing cuts."""
        cases = [case for case in declared_cases() if case["key"].endswith("_restart")]
        self.assertEqual({case["case"] for case in cases}, set("ABCDE"))
        for case in cases:
            with self.subTest(case=case["key"]):
                state = case["start"]
                for cut in case["cuts"]:
                    previous = deepcopy(state)
                    result = attempt_current_cut(state, cut)
                    self.assertEqual(state, previous)
                    self.assertEqual(result["status"], "split")
                    self.assertIn(result["event"]["s"], result["event"]["new_line_pair"])
                    self.assertLessEqual(result["event"]["changed_old_count"], 3)
                    state = result["state"]
                    validate_state(state)

    def test_c_uses_three_two_three_before_the_last_cut(self):
        """Reuse precedes arbitrary inheritance direction or a new fourth name."""
        state = initial_state()
        for cut in (((0, 357), (900, 357)), ((0, 487), (900, 487))):
            result = attempt_current_cut(state, cut)
            self.assertEqual(result["event"]["method"], "current_direct")
            state = result["state"]
        ordered = sorted(state.sides, key=lambda side: side.bounds[1])
        self.assertEqual([side.symbol for side in ordered], [3, 2, 3])
        self.assertFalse(result["event"]["introduced_new_name"])

    def test_e_restart_uses_internal_one_and_finishes_without_release(self):
        """The actual restarted E, not the frozen draft, determines this claim."""
        state = initial_state()
        for index, cut in enumerate((*E_CUTS, E_PENDING), 1):
            result = attempt_current_cut(state, cut)
            self.assertEqual(result["status"], "split")
            self.assertEqual(result["event"]["method"], "current_direct")
            self.assertEqual(result["event"]["release_trace"], [])
            state = result["state"]
            if index >= 7:
                center = next(side for side in state.sides
                              if side.bounds == (312, 123, 598, 214))
                self.assertEqual(center.symbol, 1)
                self.assertNotIn("outside", _state_adjacency(state)[center.id])
        by_bounds = {side.bounds: side.symbol for side in state.sides}
        self.assertEqual(by_bounds[(0, 214, 454, 471)], 2)
        self.assertEqual(by_bounds[(454, 214, 900, 471)], 4)

    def test_zero_release_budget_preserves_every_name_and_geometry(self):
        """A zero-budget preview cannot silently lower the old E center."""
        old = frozen_case("E_frozen_start")["start"]
        result = release_neighbor_names(old, "M", max_old_sides=0)
        self.assertEqual(result["state"], old)
        self.assertEqual(result["trace"], [])
        self.assertEqual(result["touched_ids"], [])
        self.assertEqual(result["potential_before"], result["potential_after"])
        self.assertEqual(result["stop_reason"], "budget_limited")
        self.assertEqual(result["budget_blocked_ids"], ["G"])

    def test_zero_cut_budget_is_atomic(self):
        """Even a possible new cut is not partially committed on budget failure."""
        case = frozen_case("D_frozen_start")
        result = attempt_current_cut(case["start"], case["cuts"][0], max_old_sides=0)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["event"]["reason"], "local_budget_exceeded")
        self.assertIs(result["state"], case["start"])

    def test_old_e_release_lowers_only_g_and_preserves_all_identities(self):
        """A local G correction is checked separately from replaying history."""
        old = frozen_case("E_frozen_start")["start"]
        frozen = deepcopy(old)
        result = release_neighbor_names(old, "M")
        self.assertEqual(old, frozen)
        self.assertEqual(result["touched_ids"], ["G"])
        self.assertEqual(result["stop_reason"], "locally_stable")
        self.assertEqual(result["budget_blocked_ids"], [])
        self.assertEqual([(row["id"], row["before"], row["after"])
                          for row in result["trace"]], [("G", 4, 1)])
        self.assertEqual(symbols(result["state"]), {**symbols(old), "G": 1})
        self.assertEqual(result["state"].cuts, old.cuts)
        self.assertEqual([(s.id, s.bounds) for s in result["state"].sides],
                         [(s.id, s.bounds) for s in old.sides])
        validate_state(result["state"])

    def test_old_e_g_one_is_not_a_direct_extension_certificate(self):
        """Both complete daughter domains remain empty after changing G alone."""
        case = frozen_case("E_frozen_start")
        corrected = release_neighbor_names(case["start"], "M")["state"]
        result = attempt_current_cut(corrected, case["cuts"][0], release=False)
        self.assertTrue(all(row["available_names"] == []
                            for row in result["event"]["initial_candidates"]))
        self.assertEqual(result["status"], "blocked")
        self.assertIs(result["state"], corrected)

    def test_failed_patch_rolls_back_an_actual_release(self):
        """An uncommitted G4-to-1 preview must not mutate the old E fixture."""
        case = frozen_case("E_frozen_start")
        result = attempt_current_cut(case["start"], case["cuts"][0], max_old_sides=1)
        self.assertEqual(result["status"], "blocked")
        self.assertIs(result["state"], case["start"])
        self.assertEqual(result["event"]["release_trace"][0]["id"], "G")
        self.assertEqual(symbols(case["start"])["G"], 4)

    def test_release_never_introduces_unused_two(self):
        """Numerically lowering 3/4 to an unused2 would violate reuse priority."""
        old = RectState(900, 600, tuple(
            RectSide(label, (index * 225, 0, (index + 1) * 225, 600), name)
            for index, (label, name) in enumerate(zip("abcd", (3, 4, 3, 4)))
        ), tuple(((x, 0), (x, 600)) for x in (225, 450, 675)))
        validate_state(old)
        for parent in "abcd":
            with self.subTest(parent=parent):
                result = release_neighbor_names(old, parent)
                self.assertEqual(result["trace"], [])
                self.assertLessEqual(set(symbols(result["state"]).values()), {1, 3, 4})

    def test_direct_success_does_not_trigger_unnecessary_neighbor_release(self):
        """A successful top-band cut need not rename the available internal G."""
        old = frozen_case("E_frozen_start")["start"]
        result = attempt_current_cut(old, ((0, 60), (900, 60)))
        self.assertEqual(result["status"], "split")
        self.assertEqual(result["event"]["method"], "current_direct")
        self.assertEqual(result["event"]["release_trace"], [])
        self.assertEqual(symbols(result["state"])["G"], 4)

    def test_fixed_outside_produces_a_phase_certificate_not_an_exception(self):
        """Interior parent1 is legal; exterior1 remains a noneditable boundary."""
        old = interior_one_state()
        result = attempt_current_cut(old, ((450, 180), (450, 420)), release=False)
        self.assertEqual(result["status"], "blocked")
        self.assertIs(result["state"], old)
        self.assertEqual(result["event"]["reason"], "boundary_phase_conflict")
        certificate = result["event"]["patch_certificate"]
        self.assertNotIn("outside", certificate["patch"])
        self.assertEqual({pin["outside_neighbor"] for pin in certificate["conflicting_pins"]},
                         {"outside"})
        self.assertEqual({pin["required_phase"] for pin in certificate["conflicting_pins"]},
                         {0, 1})

    def test_release_can_free_a_current_name_before_a_pinned_patch_is_needed(self):
        """With release enabled, B4-to-3 frees4 while the parent remains1."""
        old = interior_one_state()
        result = attempt_current_cut(old, ((450, 180), (450, 420)))
        self.assertEqual(result["status"], "split")
        self.assertEqual(result["event"]["method"], "current_release_direct")
        self.assertEqual([(row["id"], row["before"], row["after"])
                          for row in result["event"]["release_trace"]], [("B", 4, 3)])
        self.assertEqual(result["event"]["changed_old_count"], 1)
        self.assertEqual(set(result["event"]["new_line_pair"]), {1, 4})
        self.assertNotIn("patch_certificate", result["event"])
        validate_state(result["state"])

    def test_equal_names_do_not_merge_distinct_interface_identities(self):
        """D's equally named left/right flanks are not one common old neighbor."""
        case = frozen_case("D_frozen_start")
        result = attempt_current_cut(case["start"], case["cuts"][0])
        self.assertEqual(result["status"], "split")
        self.assertEqual({row["id"] for row in result["event"]["fixed_common_interfaces"]},
                         {"outside", "T"})
        self.assertEqual(result["event"]["changed_old_count"], 1)
        self.assertEqual(result["event"]["pair"], [2, 3])

    def test_identical_inputs_have_identical_results_and_release_traces(self):
        """Selection must not depend on hash-set iteration or mutable history."""
        case = frozen_case("E_frozen_start")
        first = attempt_current_cut(case["start"], case["cuts"][0])
        for _ in range(3):
            self.assertEqual(attempt_current_cut(case["start"], case["cuts"][0]), first)
            released = release_neighbor_names(case["start"], "M")
            self.assertLessEqual(len(released["trace"]), 3 * 3)
            self.assertLess(released["potential_after"], released["potential_before"])

    def test_invalid_parameters_are_rejected(self):
        """Boolean budgets and nonboolean release controls are not accepted."""
        state = initial_state()
        for budget in (-1, True, 1.5, "3"):
            with self.subTest(budget=budget):
                with self.assertRaises(ValueError):
                    release_neighbor_names(state, "root", budget)
                with self.assertRaises(ValueError):
                    attempt_current_cut(state, ((0, 300), (900, 300)), budget)
        for release in (0, 1, None, "yes"):
            with self.assertRaises(ValueError):
                attempt_current_cut(state, ((0, 300), (900, 300)), release=release)
        for parent in ("outside", "unknown"):
            with self.assertRaises(ValueError):
                release_neighbor_names(state, parent)

    def test_adjacency_only_pair_one_success_keeps_exterior_pinned(self):
        """A theorem-only example: reaching exterior1 need not block pair1/2."""
        graph = simple_graph("abuvxy", [
            ("u", "v"), ("u", "outside"), ("u", "a"), ("v", "b"),
            ("u", "x"), ("u", "y"), ("v", "x"), ("v", "y"),
        ])
        names = {"outside": 1, "a": 1, "b": 1, "u": 2, "v": 2, "x": 3, "y": 4}
        result = solve_two_name_patch(graph, names, set("auvb"), (1, 2),
                                      old_names={"a": 1, "b": 1, "x": 3, "y": 4})
        self.assertEqual(result["status"], "renamed")
        self.assertEqual(result["names"], {**names, "v": 1, "b": 2})
        self.assertEqual(result["changed_old_ids"], ["b"])
        self.assertEqual(result["components"][0]["allowed_phases"], [0])

    def test_adjacency_only_preferring_one_can_regress_against_pair_two(self):
        """Allowing1 is safe but choosing it once need not dominate old policy."""
        graph = simple_graph("abcdxzuv", [
            ("u", "v"), ("u", "a"), ("v", "b"), ("a", "x"), ("x", "b"),
            ("u", "c"), ("v", "d"), ("u", "z"), ("v", "z"),
            ("outside", "z"),
        ])
        names = {"outside": 1, "a": 1, "b": 1, "x": 3, "c": 2, "d": 2,
                 "z": 4, "u": 3, "v": 3}
        old_names = {key: name for key, name in names.items() if key not in {"u", "v"}}
        first = solve_two_name_patch(graph, names, set("uaxbv"), (1, 3), old_names)
        second = solve_two_name_patch(graph, names, set("cuvd"), (2, 3), old_names)
        self.assertEqual(first["reason"], "odd_cycle_in_patch")
        self.assertEqual(len(first["odd_cycle"]) - 1, 5)
        self.assertEqual(second["status"], "renamed")
        self.assertEqual(second["minimum_old_changes_in_fixed_patch_pair"], 1)


if __name__ == "__main__":
    unittest.main()

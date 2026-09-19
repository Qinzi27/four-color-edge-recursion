"""Tests for one safe common-interface release, not a general repair solver.

The seed20260911 fixture is an exact four-cut prefix of the predeclared
guillotine generator. Mocked refusal tests exercise transaction semantics only;
they are explicitly not claimed as new geometric obstruction examples.
"""

from copy import deepcopy
from unittest.mock import patch
import unittest

from fourcolor.anchor_forest import _state_adjacency
from fourcolor.current_names import attempt_current_cut
from fourcolor.inherited_names import initial_state
from fourcolor.interface_names import attempt_interface_cut
from scripts.compare_local_marks import validate_state
from scripts.validate_local_reuse import declared_cases


# Exact generatedPaths('guillotine', 20260911) prefix, with input directions.
SEED_911 = (
    ((337, 0), (337, 600)),
    ((337, 409), (900, 409)),
    ((175, 0), (175, 600)),
    ((175, 219), (337, 219)),
)


def before_shared_release():
    """Replay the first three successful steps without introducing new colors."""
    state = initial_state()
    for cut in SEED_911[:3]:
        result = attempt_current_cut(state, cut)
        if result["status"] != "split":
            raise AssertionError("the declared old prefix stopped before its fourth cut")
        state = result["state"]
    return state


def name_by_bounds(state):
    """Positions identify display regions; symbols are never region identities."""
    return {side.bounds: side.symbol for side in state.sides}


class InterfaceNamesTests(unittest.TestCase):
    """Check exact improvement, preserved successes, and bounded atomicity."""

    def test_seed_911_is_really_a_no_companion_stop_of_the_frozen_policy(self):
        """The old failure is reproduced, not asserted from a screenshot."""
        state = before_shared_release()
        self.assertEqual(name_by_bounds(state), {
            (0, 0, 175, 600): 2, (175, 0, 337, 600): 3,
            (337, 0, 900, 409): 4, (337, 409, 900, 600): 2,
        })
        result = attempt_current_cut(state, SEED_911[3])
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["event"]["reason"], "no_companion_with_common_interfaces_fixed")
        self.assertEqual({row["name"] for row in result["event"]["fixed_common_interfaces"]},
                         {1, 2, 4})

    def test_seed_911_releases_left_two_to_four_and_finishes(self):
        """One legal increase frees the common ban2 and gives middle top2/bottom3."""
        state = before_shared_release()
        frozen = deepcopy(state)
        result = attempt_interface_cut(state, SEED_911[3])
        self.assertEqual(state, frozen)
        self.assertEqual(result["status"], "split")
        self.assertEqual(result["event"]["method"], "shared_interface_release")
        move = result["event"]["shared_release"]
        self.assertEqual((move["before"], move["after"]), (2, 4))
        self.assertEqual(name_by_bounds(result["state"]), {
            (0, 0, 175, 600): 4, (175, 0, 337, 219): 2,
            (175, 219, 337, 600): 3, (337, 0, 900, 409): 4,
            (337, 409, 900, 600): 2,
        })
        validate_state(result["state"])

    def test_one_old_side_budget_suffices_and_is_not_counted_as_zero(self):
        """Precharging the interface leaves a zero-budget DIRECT second stage."""
        result = attempt_interface_cut(before_shared_release(), SEED_911[3], max_old_sides=1)
        self.assertEqual(result["status"], "split")
        self.assertEqual(result["event"]["changed_old_count"], 1)
        self.assertEqual(len(result["event"]["shared_release"]["precharged_old_ids"]), 1)
        following = result["event"]["after_shared_release_event"]
        self.assertEqual(following["max_old_sides"], 0)
        self.assertEqual(following["method"], "current_direct")

    def test_zero_budget_rejects_without_a_negative_budget_or_mutation(self):
        """Budget-ineligible interface moves are rejected before the second call."""
        state = before_shared_release()
        result = attempt_interface_cut(state, SEED_911[3], max_old_sides=0)
        self.assertEqual(result["status"], "blocked")
        self.assertIs(result["state"], state)
        self.assertEqual(result["event"]["reason"], "no_safe_shared_interface_release")
        self.assertNotIn("after_shared_release_event", result["event"])

    def test_all_teaching_successful_prefixes_are_preserved_exactly(self):
        """Compare every prefix of A--E, not just their final used color sets."""
        checked = 0
        for case in declared_cases():
            if not case["key"].endswith("_restart"):
                continue
            state = case["start"]
            for index, cut in enumerate(case["cuts"], 1):
                with self.subTest(case=case["key"], step=index):
                    current = attempt_current_cut(state, cut)
                    self.assertEqual(current["status"], "split")
                    self.assertEqual(attempt_interface_cut(state, cut), current)
                    state = current["state"]
                    checked += 1
        self.assertEqual(checked, 24)

    def test_old_e_is_not_silently_given_a_different_repair_policy(self):
        """The old E budget stop is not the declared no-companion trigger."""
        case = next(case for case in declared_cases() if case["key"] == "E_frozen_start")
        current = attempt_current_cut(case["start"], case["cuts"][0])
        result = attempt_interface_cut(case["start"], case["cuts"][0])
        self.assertEqual(result, current)
        self.assertEqual(result["status"], "blocked")
        self.assertIs(result["state"], case["start"])
        self.assertNotIn("shared_release_attempted", result["event"])

    def test_failed_second_stage_rolls_back_one_tentative_legal_increase(self):
        """A mocked later refusal tests atomicity, not a claimed new map failure."""
        state = before_shared_release()
        first = attempt_current_cut(state, SEED_911[3])
        frozen = deepcopy(state)
        calls = []

        def controlled_result(received, points, **kwargs):
            """The first call is real evidence; the next is a transaction probe."""
            calls.append(received)
            if len(calls) == 1:
                self.assertIs(received, state)
                return first
            validate_state(received)
            self.assertEqual(name_by_bounds(received)[(0, 0, 175, 600)], 4)
            self.assertFalse(kwargs["release"])
            return {"status": "blocked", "state": received,
                    "event": {"reason": "controlled_test_refusal"}}

        with patch("fourcolor.interface_names.attempt_current_cut", side_effect=controlled_result):
            result = attempt_interface_cut(state, SEED_911[3])
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["status"], "blocked")
        self.assertIs(result["state"], state)
        self.assertEqual(state, frozen)
        self.assertEqual(result["event"]["reason"], "after_shared_release/controlled_test_refusal")

    def test_common_ban_really_drops_once_and_move_respects_all_old_neighbors(self):
        """Uniqueness is by side identity, while legality reads the full boundary."""
        state = before_shared_release()
        result = attempt_interface_cut(state, SEED_911[3])
        move = result["event"]["shared_release"]
        common_before, common_after = set(move["common_names_before"]), set(move["common_names_after"])
        self.assertEqual(common_before - common_after, {move["before"]})
        self.assertEqual(common_after, common_before - {move["before"]})
        names = {"outside": 1, **{side.id: side.symbol for side in state.sides}}
        neighbors = _state_adjacency(state)[move["id"]]
        self.assertNotIn(move["after"], {names[vertex] for vertex in neighbors})
        self.assertIn(move["after"], common_before)

    def test_all_mother_profiles_refresh_against_original_input(self):
        """The final audit must count the precharged interface, not only step2."""
        state = before_shared_release()
        result = attempt_interface_cut(state, SEED_911[3])
        event = result["event"]
        move = event["shared_release"]
        self.assertEqual(event["changed_old_sides"], [{"id": move["id"], "before": 2, "after": 4}])
        self.assertEqual(event["changed_old_side_ids"], [move["id"]])
        self.assertTrue(event["profile_changes"])
        self.assertEqual(event["conflicts"], [])
        self.assertEqual(result["state"].cuts[:-1], state.cuts)
        self.assertEqual(set(event["new_line_pair"]), {2, 3})

    def test_identical_inputs_select_the_identical_single_interface(self):
        """Determinism is checked on full event records, including the preview."""
        state = before_shared_release()
        first = attempt_interface_cut(state, SEED_911[3])
        for _ in range(3):
            self.assertEqual(attempt_interface_cut(state, SEED_911[3]), first)

    def test_repair_reuses_validated_cut_instead_of_consuming_an_iterator_twice(self):
        """Geometry accepts coordinate iterators, including on a repair branch."""
        state = before_shared_release()
        expected = attempt_interface_cut(state, SEED_911[3])
        result = attempt_interface_cut(state, (point for point in SEED_911[3]))
        self.assertEqual(result["status"], "split")
        self.assertEqual(result, expected)

    def test_non_trigger_results_are_returned_verbatim(self):
        """A control-flow test covers every status outside the one declared trigger."""
        state = initial_state()
        for status, reason in (("split", None), ("outside_scope", "unsupported_geometry"),
                               ("blocked", "odd_cycle_in_patch"),
                               ("blocked", "local_budget_exceeded")):
            with self.subTest(status=status, reason=reason):
                original = {"status": status, "state": state, "event": {"reason": reason}}
                with patch("fourcolor.interface_names.attempt_current_cut", return_value=original) as call:
                    self.assertIs(attempt_interface_cut(state, ((0, 300), (900, 300))), original)
                    self.assertEqual(call.call_count, 1)

    def test_invalid_budgets_are_rejected_by_the_underlying_contract(self):
        """The wrapper does not bypass the core's integer-and-nonnegative check."""
        for budget in (-1, True, 1.5, "3"):
            with self.subTest(budget=budget):
                with self.assertRaises(ValueError):
                    attempt_interface_cut(initial_state(), ((0, 300), (900, 300)), budget)


if __name__ == "__main__":
    unittest.main()

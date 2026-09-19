"""Regression checks for the marked A replay and local reuse of 1 in B."""

from dataclasses import replace
import unittest

from scripts.audit_retained_blocks import unpack_state
from scripts.validate_marked_cases import audit_rectangle_state, build_report


def names_by_bounds(payload):
    """Compare physical assignments while keeping IDs intact in the report."""
    return {tuple(side["bounds"]): side["symbol"] for side in payload["sides"]}


class MarkedCaseTests(unittest.TestCase):
    """Keep observed successes separate from original fixed-policy blocks."""

    @classmethod
    def setUpClass(cls):
        """Build one audited report; Node and rotation checks are not mocked."""
        cls.report = build_report()

    def test_a_replay_matches_user_drawing_exactly(self):
        """Four declared left-inheritance cuts reproduce all five marked sides."""
        case = self.report["cases"]["user_a_replay"]
        self.assertEqual(len(case["steps"]), 4)
        self.assertEqual(names_by_bounds(case["final_state"]), {
            (415, 0, 900, 600): 2,
            (0, 0, 187, 402): 4,
            (187, 0, 415, 402): 3,
            (0, 402, 233, 600): 2,
            (233, 402, 415, 600): 4,
        })
        self.assertEqual([(step["event"]["s"], step["event"]["R"], step["event"]["t"])
                          for step in case["steps"]],
                         [(2, [1], 3), (3, [1, 2], 4),
                          (4, [1, 3], 2), (3, [1, 2], 4)])

    def test_original_a_reverse_is_not_the_full_replay(self):
        """A one-step repair must not be presented as the same naming history."""
        case = self.report["cases"]["original_a_reverse"]
        replay = self.report["cases"]["user_a_replay"]
        self.assertNotEqual(names_by_bounds(case["final_state"]),
                            names_by_bounds(replay["final_state"]))
        self.assertEqual(case["steps"][0]["event"]["changed_old_sides"], [])
        old = {side["id"]: side["symbol"] for side in case["initial_state"]["sides"]}
        for side in case["final_state"]["sides"]:
            if side["id"] in old:
                self.assertEqual(side["symbol"], old[side["id"]])

    def test_b_reuses_one_only_on_the_interior_child(self):
        """The exterior bans 1 only on a daughter actually sharing its edge."""
        case = self.report["cases"]["b_reverse"]
        names = names_by_bounds(case["final_state"])
        self.assertEqual(names[(160, 172, 518, 327)], 1)
        self.assertEqual(names[(0, 172, 160, 327)], 4)
        domains = {row["geometric_side"]: row for row in case["final_step_domains"]}
        self.assertEqual(domains["page_right"]["R"], [2, 3])
        self.assertEqual(domains["page_right"]["available_names"], [1])
        self.assertEqual(domains["page_left"]["R"], [1, 2, 3])
        self.assertEqual(domains["page_left"]["available_names"], [])
        self.assertEqual(case["steps"][0]["event"]["changed_old_sides"], [])

    def test_wrongly_giving_b_left_child_one_conflicts_with_outside(self):
        """A negative control guards against treating all uses of 1 equally."""
        payload = self.report["cases"]["b_reverse"]["final_state"]
        state = unpack_state(payload)
        bad = replace(state, sides=tuple(
            replace(side, symbol=1) if side.bounds == (0, 172, 160, 327) else side
            for side in state.sides))
        with self.assertRaisesRegex(AssertionError, "equal opposing names"):
            audit_rectangle_state(bad)

    def test_original_directions_remain_blocked_without_implicit_retry(self):
        """Both reported failures are preserved, rather than rewritten as wins."""
        for control in self.report["original_direction_controls"].values():
            self.assertEqual(control["status"], "blocked_sync_required")
            self.assertTrue(control["state_unchanged"])
            self.assertEqual(control["t"], 5)

    def test_all_committed_states_pass_independent_geometry(self):
        """Every saved initial and resulting state has its own line certificate."""
        summary = self.report["summary"]
        self.assertEqual(summary["successful_steps"], 6)
        self.assertEqual(summary["rectangle_states_audited"], 9)
        self.assertEqual(summary["node_and_rotation_states_audited"], 9)
        for case in self.report["cases"].values():
            self.assertEqual(case["independent_audit"]["python_status"], "consistent")
            for step in case["steps"]:
                self.assertEqual(step["independent_audit"]["python_status"], "consistent")
                self.assertEqual(step["event"]["changed_old_sides"], [])
                self.assertFalse(step["event"]["sync_attempted"])

    def test_same_input_is_deterministic(self):
        """No timestamps, random tie choices or coloring enumeration affect output."""
        self.assertEqual(self.report, build_report())


if __name__ == "__main__":
    unittest.main()

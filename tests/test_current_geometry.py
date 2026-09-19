"""Pure geometric proposals at ordinary and already occupied mother endpoints.

The two-child drafts deliberately share one name. These tests never submit
such an uncommitted draft to a coloring oracle or present it as a valid naming.
"""

from copy import deepcopy
import unittest
from unittest.mock import patch

from fourcolor.current_geometry import propose_rect_split
from fourcolor.inherited_names import RectSide, RectState, initial_state
from fourcolor.retained_profiles import _validate_state


def one_t_state():
    """A valid top-2/bottom-3,4 map with a T at (450,300)."""
    return RectState(900, 600,
                     (RectSide("top", (0, 0, 900, 300), 2),
                      RectSide("bottom-left", (0, 300, 450, 600), 3),
                      RectSide("bottom-right", (450, 300, 900, 600), 4)),
                     (((0, 300), (900, 300)), ((450, 300), (450, 600))))


def two_t_state():
    """Two existing T junctions bound one unsplit middle rectangular side."""
    return RectState(900, 600,
                     (RectSide("top-left", (0, 0, 450, 200), 3),
                      RectSide("top-right", (450, 0, 900, 200), 4),
                      RectSide("middle", (0, 200, 900, 400), 2),
                      RectSide("bottom-left", (0, 400, 450, 600), 3),
                      RectSide("bottom-right", (450, 400, 900, 600), 4)),
                     (((0, 200), (900, 200)), ((0, 400), (900, 400)),
                      ((450, 0), (450, 200)), ((450, 400), (450, 600))))


class CurrentGeometryTests(unittest.TestCase):
    """Names are carried through drafts only; all tested changes are geometric."""

    def test_vertical_direction_reversal_swaps_left_right_geometry(self):
        state = initial_state()
        down = propose_rect_split(state, ((450, 0), (450, 600)))
        up = propose_rect_split(state, ((450, 600), (450, 0)))
        self.assertEqual(down["status"], "proposed")
        self.assertEqual(up["status"], "proposed")
        by_down = {side.id: side for side in down["proposed_state"].sides}
        by_up = {side.id: side for side in up["proposed_state"].sides}
        self.assertEqual(by_down["root.l"].bounds, (450, 0, 900, 600))
        self.assertEqual(by_down["root.r"].bounds, (0, 0, 450, 600))
        self.assertEqual(by_down["root.l"].bounds, by_up["root.r"].bounds)
        self.assertEqual(by_down["root.r"].bounds, by_up["root.l"].bounds)
        self.assertEqual(up["event"]["cut"], down["event"]["cut"][::-1])
        self.assertEqual(down["event"]["child_ids"], ("root.l", "root.r"))
        self.assertTrue(all(side.symbol == 2 for side in down["proposed_state"].sides))

    def test_horizontal_direction_reversal_swaps_top_bottom(self):
        state = initial_state()
        east = propose_rect_split(state, ((0, 300), (900, 300)))
        west = propose_rect_split(state, ((900, 300), (0, 300)))
        east_sides = {side.id: side.bounds for side in east["proposed_state"].sides}
        west_sides = {side.id: side.bounds for side in west["proposed_state"].sides}
        self.assertEqual(east_sides["root.l"], (0, 0, 900, 300))
        self.assertEqual(east_sides["root.r"], (0, 300, 900, 600))
        self.assertEqual(east_sides["root.l"], west_sides["root.r"])
        self.assertEqual(east_sides["root.r"], west_sides["root.l"])

    def test_free_ends_zero_oblique_and_bad_coordinates_are_outside_scope(self):
        state = initial_state()
        bad = [((450, 0), (450, 300)), ((200, 300), (600, 300)),
               ((450, 0), (450, 0)), ((0, 0), (900, 600)),
               ((0, 0), (1e-8, 600)), ((False, 0), (False, 600)),
               ((450, float("nan")), (450, 600)), (), None]
        for cut in bad:
            with self.subTest(cut=cut):
                result = propose_rect_split(state, cut)
                self.assertEqual(result["status"], "outside_scope")
                self.assertIs(result["state"], state)
                self.assertNotIn("proposed_state", result)

    def test_crossing_multiple_old_sides_is_not_a_single_side_split(self):
        state = one_t_state()
        for cut in (((225, 0), (225, 600)), ((0, 300), (900, 300))):
            with self.subTest(cut=cut):
                result = propose_rect_split(state, cut)
                self.assertEqual(result["status"], "outside_scope")
                self.assertIs(result["state"], state)

    def test_mother_interior_endpoint_proposes_an_ordinary_t(self):
        state = RectState(900, 600,
                          (RectSide("top", (0, 0, 900, 300), 2),
                           RectSide("bottom", (0, 300, 900, 600), 3)),
                          (((0, 300), (900, 300)),))
        result = propose_rect_split(state, ((450, 300), (450, 600)))
        self.assertEqual(result["status"], "proposed")
        port = result["event"]["endpoint_incidence"][0]
        self.assertEqual([mother["id"] for mother in port["incident_mothers"]], ["cut-1"])
        self.assertEqual(port["incident_mothers"][0]["position"], "interior")
        self.assertEqual({side["id"] for side in port["incident_old_sides"]}, {"top", "bottom"})

    def test_existing_t_accepts_multiple_mothers_and_can_become_x(self):
        state = one_t_state()
        result = propose_rect_split(state, ((450, 0), (450, 300)))
        self.assertEqual(result["status"], "proposed")
        port = result["event"]["endpoint_incidence"][1]
        mothers = {mother["id"]: mother for mother in port["incident_mothers"]}
        self.assertEqual(set(mothers), {"cut-1", "cut-2"})
        self.assertEqual(mothers["cut-1"]["position"], "interior")
        self.assertEqual(mothers["cut-2"]["position"], "endpoint")
        self.assertEqual({side["id"] for side in port["incident_old_sides"]},
                         {"top", "bottom-left", "bottom-right"})
        self.assertFalse(port["creates_color_constraint"])
        self.assertTrue(port["closed_incidence_only"])
        self.assertNotIn("R", result["event"])
        self.assertNotIn("new_name", result["event"])

    def test_both_ends_can_extend_existing_t_junctions_into_x_junctions(self):
        state = two_t_state()
        result = propose_rect_split(state, ((450, 200), (450, 400)))
        reverse = propose_rect_split(state, ((450, 400), (450, 200)))
        self.assertEqual(result["status"], "proposed")
        self.assertEqual(reverse["status"], "proposed")
        ports = result["event"]["endpoint_incidence"]
        self.assertEqual([{row["id"] for row in port["incident_mothers"]} for port in ports],
                         [{"cut-1", "cut-3"}, {"cut-2", "cut-4"}])
        self.assertEqual([len(port["incident_old_sides"]) for port in ports], [3, 3])
        self.assertEqual(result["event"]["endpoint_incidence"],
                         reverse["event"]["endpoint_incidence"][::-1])

    def test_frame_incidence_and_every_old_cut_are_preserved(self):
        state = one_t_state()
        saved = deepcopy(state)
        result = propose_rect_split(state, ((450, 0), (450, 300)))
        draft = result["proposed_state"]
        self.assertEqual(state, saved)
        self.assertIs(result["state"], state)
        self.assertEqual(draft.cuts[:-1], state.cuts)
        self.assertEqual(draft.cuts[-1], ((450, 0), (450, 300)))
        self.assertEqual(result["event"]["endpoint_incidence"][0]["frame_segments"][0]["frame_edge"], "top")
        for side in state.sides:
            if side.id != "top":
                self.assertIs(next(item for item in draft.sides if item.id == side.id), side)
        self.assertEqual({side.symbol for side in draft.sides if side.id.startswith("top.")}, {2})
        self.assertFalse(result["event"]["committed"])

    def test_only_old_state_is_validated_not_the_same_name_draft(self):
        state = initial_state()
        with patch("fourcolor.current_geometry._validate_state", wraps=_validate_state) as validate:
            result = propose_rect_split(state, ((450, 0), (450, 600)))
        validate.assert_called_once_with(state)
        self.assertEqual(result["status"], "proposed")
        self.assertEqual([side.symbol for side in result["proposed_state"].sides], [2, 2])

    def test_invalid_old_names_are_rejected_before_geometric_proposal(self):
        for symbol in (1, 5):
            with self.subTest(symbol=symbol), self.assertRaises(ValueError):
                state = RectState(900, 600, (RectSide("root", (0, 0, 900, 600), symbol),))
                propose_rect_split(state, ((450, 0), (450, 600)))


if __name__ == "__main__":
    unittest.main()

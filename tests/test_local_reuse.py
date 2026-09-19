"""Finite independent checks of direct reuse and fixed-boundary parity rules."""

from copy import deepcopy
from itertools import combinations, product
import unittest

from fourcolor.inherited_names import RectSide, RectState, attempt_cut, initial_state
from fourcolor.local_reuse import attempt_local_cut, solve_two_name_patch


def graph_with_edges(vertices, edges):
    """Build a full symmetric graph; outside is an explicit fixed identity."""
    graph = {v: set() for v in ["outside", *vertices]}
    for a, b in edges:
        graph[a].add(b)
        graph[b].add(a)
    return graph


def d_state(top=4, flanks=2, middle=3):
    """Exact D geometry, with independent side IDs and three old mother lines."""
    return RectState(900, 600, (
        RectSide("T", (0, 0, 900, 180), top),
        RectSide("A", (0, 180, 300, 600), flanks),
        RectSide("M", (300, 180, 600, 600), middle),
        RectSide("D", (600, 180, 900, 600), flanks),
    ), (((0, 180), (900, 180)), ((300, 180), (300, 600)), ((600, 180), (600, 600))))


class LocalReuseTests(unittest.TestCase):
    """These local theorem tests do not claim to cover arbitrary plane maps."""

    def test_c_history_reuses_a_name_before_considering_position(self):
        """Second C cut must reuse3 on the bottom, not introduce4 above it."""
        state = initial_state()
        for cut in (((0, 357), (900, 357)), ((0, 487), (900, 487))):
            result = attempt_local_cut(state, cut)
            self.assertEqual(result["event"]["method"], "reuse_first_direct")
            state = result["state"]
        ordered = sorted(state.sides, key=lambda side: side.bounds[1])
        self.assertEqual([side.symbol for side in ordered], [3, 2, 3])
        self.assertFalse(result["event"]["introduced_new_name"])
        result = attempt_local_cut(state, ((442, 357), (442, 487)))
        self.assertEqual(result["event"]["target"], 4)
        self.assertEqual(result["event"]["changed_old_count"], 0)

    def test_d_both_naming_conventions_use_one_old_change(self):
        """Shared INTERFACE IDs, not equal flank colors, select the companion."""
        for old, expected_pair in [(d_state(), [2, 3]), (d_state(3, 4, 2), [2, 4])]:
            frozen = deepcopy(old)
            result = attempt_local_cut(old, ((450, 180), (450, 600)))
            self.assertEqual(old, frozen)
            self.assertEqual(result["status"], "split")
            self.assertEqual(result["event"]["method"], "bounded_two_name_parity")
            self.assertEqual(result["event"]["pair"], expected_pair)
            self.assertEqual(result["event"]["changed_old_count"], 1)
            fixed = result["event"]["fixed_common_interfaces"]
            self.assertEqual({entry["id"] for entry in fixed}, {"outside", "T"})
            new_top = next(side.symbol for side in result["state"].sides if side.id == "T")
            self.assertEqual(new_top, old.sides[0].symbol)
            self.assertIn(old.sides[2].symbol, result["event"]["new_line_pair"])

    def test_budget_rejection_is_atomic_and_never_swaps_a_prefix(self):
        """An incomplete component is evidence of budget exhaustion, not impossibility."""
        old = d_state()
        result = attempt_local_cut(old, ((450, 180), (450, 600)), max_old_sides=0)
        self.assertIs(result["state"], old)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["event"]["reason"], "local_budget_exceeded")
        self.assertFalse(result["event"]["rejection_members_complete"])
        self.assertNotIn("patch_certificate", result["event"])

    def test_disabling_repair_keeps_the_old_map(self):
        """Frozen minimal D has no direct extension with all other old names fixed."""
        old = d_state()
        result = attempt_local_cut(old, ((450, 180), (450, 600)), repair=False)
        self.assertIs(result["state"], old)
        self.assertEqual(result["event"]["reason"], "both_direct_domains_empty")
        self.assertFalse(result["event"]["repair_attempted"])

    def test_geometry_rejection_does_not_create_a_split(self):
        """A free endpoint is outside the rectangular closed-cut adapter."""
        old = initial_state()
        result = attempt_local_cut(old, ((0, 300), (450, 300)))
        self.assertEqual(result["status"], "outside_scope")
        self.assertIs(result["state"], old)

    def test_even_cycle_and_branch_are_supported_by_the_patch_theorem(self):
        """The theorem is not restricted to the previously proved strip chain."""
        for edges in [[("a", "b"), ("b", "c"), ("c", "d"), ("d", "a")],
                      [("a", "b"), ("a", "c"), ("a", "d")]]:
            graph = graph_with_edges("abcd", edges)
            names = {"outside": 1, **dict.fromkeys("abcd", 2)}
            result = solve_two_name_patch(graph, names, set("abcd"), (2, 3))
            self.assertEqual(result["status"], "renamed")
            self.assertTrue(all(result["names"][a] != result["names"][b] for a, b in edges))

    def test_odd_cycle_returns_a_checkable_closed_witness(self):
        """Odd cycles reject THIS two-name patch, not four-name feasibility."""
        graph = graph_with_edges("abc", [("a", "b"), ("b", "c"), ("c", "a")])
        result = solve_two_name_patch(graph, {"outside": 1, "a": 2, "b": 3, "c": 2}, "abc", (2, 3))
        self.assertEqual(result["reason"], "odd_cycle_in_patch")
        cycle = result["odd_cycle"]
        self.assertEqual(cycle[0], cycle[-1])
        self.assertEqual((len(cycle) - 1) % 2, 1)
        self.assertTrue(all(b in graph[a] for a, b in zip(cycle, cycle[1:])))

    def test_boundary_conflict_in_a_tree_is_not_misreported_as_an_odd_cycle(self):
        """The same pinned color at adjacent ends forces opposite phases."""
        graph = graph_with_edges(["a", "b", "u", "v"], [("a", "b"), ("a", "u"), ("b", "v")])
        names = {"outside": 1, "a": 2, "b": 3, "u": 2, "v": 2}
        result = solve_two_name_patch(graph, names, {"a", "b"}, (2, 3))
        self.assertEqual(result["reason"], "boundary_phase_conflict")
        self.assertEqual({pin["required_phase"] for pin in result["conflicting_pins"]}, {0, 1})
        self.assertEqual(result["connecting_path"], ["a", "b"])

    def test_disconnected_components_minimize_cost_independently(self):
        """No Cartesian product over component phases is needed."""
        graph = graph_with_edges("abcd", [("a", "b"), ("c", "d")])
        names = {"outside": 1, "a": 2, "b": 3, "c": 3, "d": 2}
        result = solve_two_name_patch(graph, names, set("abcd"), (2, 3))
        self.assertEqual(result["names"], names)
        self.assertEqual(len(result["components"]), 2)
        self.assertEqual(result["minimum_old_changes_in_fixed_patch_pair"], 0)

    def test_fixed_boundary_and_new_daughter_cost_are_respected(self):
        """A boundary pin wins over lower cost; daughters can have zero cost."""
        graph = graph_with_edges(["a", "b", "u"], [("a", "b"), ("a", "u")])
        names = {"outside": 1, "a": 2, "b": 3, "u": 2}
        result = solve_two_name_patch(graph, names, {"a", "b"}, (2, 3), old_names={"a": 2})
        self.assertEqual(result["names"], {"outside": 1, "a": 3, "b": 2, "u": 2})
        self.assertEqual(result["changed_old_ids"], ["a"])

    def test_invalid_fixed_exterior_is_an_input_error(self):
        """Do not blame the local patch for a preexisting frozen conflict."""
        graph = graph_with_edges(["a", "u", "v"], [("u", "v")])
        with self.assertRaises(ValueError):
            solve_two_name_patch(graph, {"outside": 1, "a": 2, "u": 3, "v": 3}, {"a"}, (2, 3))

    def test_invalid_parameters_are_rejected(self):
        """The outside cannot be silently included in a local rename."""
        graph = graph_with_edges(["a"], [])
        for patch, pair in [({"outside"}, (2, 3)), ({"a"}, (2, 2)), ({"a"}, (2, 5))]:
            with self.assertRaises(ValueError):
                solve_two_name_patch(graph, {"outside": 1, "a": 2}, patch, pair)
        with self.assertRaises(ValueError):
            attempt_local_cut(initial_state(), ((0, 1), (900, 1)), max_old_sides=True)

    def test_interior_name_one_never_makes_outside_editable(self):
        """A valid internal mother1 may have a pair component reaching outside1."""
        old = RectState(900, 600, (
            RectSide("T", (0, 0, 900, 180), 3),
            RectSide("B", (0, 420, 900, 600), 4),
            RectSide("L", (0, 180, 300, 420), 2),
            RectSide("M", (300, 180, 600, 420), 1),
            RectSide("R", (600, 180, 900, 420), 2),
        ), (((0, 180), (900, 180)), ((0, 420), (900, 420)),
            ((300, 180), (300, 420)), ((600, 180), (600, 420))))
        result = attempt_local_cut(old, ((450, 180), (450, 420)))
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["event"]["reason"], "fixed_outside_reached")
        self.assertIs(result["state"], old)
        self.assertNotIn("outside", result["event"]["rejection_members"])

    def test_old_e_has_a_real_five_cycle_in_the_selected_pair(self):
        """Three old sides plus the daughters already obstruct a 2/3-only repair."""
        from scripts.audit_retained_blocks import rectangle_adjacency
        from scripts.validate_local_reuse import declared_cases

        case = next(c for c in declared_cases() if c["key"] == "E_frozen_start")
        geometry = attempt_cut(case["start"], case["cuts"][0])["proposed_state"]
        graph = rectangle_adjacency(geometry)
        cycle = ["A", "B", "M.l", "M.r", "F", "A"]
        self.assertTrue(all(b in graph[a] for a, b in zip(cycle, cycle[1:])))
        old = {"outside": 1, **{s.id: s.symbol for s in case["start"].sides}}
        draft = {v: 2 if v in ("M.l", "M.r") else old[v] for v in graph}
        result = solve_two_name_patch(graph, draft, set(cycle), (2, 3))
        self.assertEqual(result["reason"], "odd_cycle_in_patch")
        self.assertEqual(len(result["odd_cycle"]) - 1, 5)

    def test_e_restart_reuses_internal_one_then_finishes_directly(self):
        """A successful restart must not be illustrated with frozen G4 names."""
        from scripts.compare_local_marks import validate_state
        from scripts.validate_local_reuse import E_CUTS, E_PENDING

        state = initial_state()
        for cut in (*E_CUTS, E_PENDING):
            result = attempt_local_cut(state, cut)
            self.assertEqual(result["status"], "split")
            self.assertEqual(result["event"]["method"], "reuse_first_direct")
            self.assertEqual(result["event"]["changed_old_count"], 0)
            state = result["state"]
            graph = validate_state(state)
            if len(state.cuts) >= 7:
                g = next(s for s in state.sides if s.bounds == (312, 123, 598, 214))
                names = {s.id: s.symbol for s in state.sides}
                self.assertNotIn("outside", graph[g.id])
                self.assertEqual({names[v] for v in graph[g.id]}, {2, 3, 4})
                self.assertEqual(g.symbol, 1)
        by_bounds = {s.bounds: s.symbol for s in state.sides}
        self.assertEqual(by_bounds[(0, 214, 454, 471)], 2)
        self.assertEqual(by_bounds[(454, 214, 900, 471)], 4)

    def test_old_e_g_one_is_legal_but_not_the_complete_restart(self):
        """Fixing only G differs from replaying all earlier naming decisions."""
        from scripts.compare_local_marks import validate_state
        from scripts.validate_local_reuse import declared_cases

        case = next(c for c in declared_cases() if c["key"] == "E_frozen_start")
        old = case["start"]
        graph = validate_state(old)
        names = {s.id: s.symbol for s in old.sides}
        self.assertEqual(graph["G"], {"A", "B", "F", "M"})
        self.assertEqual({names[v] for v in graph["G"]}, {2, 3})
        corrected = RectState(old.width, old.height, tuple(
            RectSide(s.id, s.bounds, 1 if s.id == "G" else s.symbol) for s in old.sides), old.cuts)
        validate_state(corrected)
        result = attempt_local_cut(corrected, case["cuts"][0], repair=False)
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(all(row["R"] == [1, 3, 4] and row["available_names"] == []
                            for row in result["event"]["candidates"]))

    def test_all_graphs_up_to_three_patch_vertices_and_all_boundary_masks(self):
        """Independent finite oracle checks feasibility AND minimum old changes.

        Enumeration is confined to this test, never called by the naming rule.
        For each vertex, a two-bit mask describes external bans on names2/3.
        """
        cases = 0
        for size in range(1, 4):
            vertices = [f"v{i}" for i in range(size)]
            possible = list(combinations(vertices, 2))
            for edge_bits in product((0, 1), repeat=len(possible)):
                edges = [edge for edge, bit in zip(possible, edge_bits) if bit]
                for masks in product(range(4), repeat=size):
                    graph = graph_with_edges(vertices + ["ban2", "ban3"], edges)
                    names = {"outside": 1, "ban2": 2, "ban3": 3,
                             **{v: 2 + (i % 2) for i, v in enumerate(vertices)}}
                    for v, mask in zip(vertices, masks):
                        for bit, pin in ((1, "ban2"), (2, "ban3")):
                            if mask & bit:
                                graph[v].add(pin)
                                graph[pin].add(v)
                    costs = []
                    for choices in product((2, 3), repeat=size):
                        candidate = {**names, **dict(zip(vertices, choices))}
                        if all(candidate[a] != candidate[b] for a in graph for b in graph[a]):
                            costs.append(sum(candidate[v] != names[v] for v in vertices))
                    result = solve_two_name_patch(graph, names, vertices, (2, 3))
                    self.assertEqual(result["status"] == "renamed", bool(costs))
                    if costs:
                        self.assertEqual(result["minimum_old_changes_in_fixed_patch_pair"], min(costs))
                    cases += 1
        self.assertEqual(cases, 548)


if __name__ == "__main__":
    unittest.main()

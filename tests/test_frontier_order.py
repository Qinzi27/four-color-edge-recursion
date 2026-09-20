"""Compare exact frontier states with independently enumerated prefix colorings."""

from itertools import combinations, permutations, product
import unittest

from fourcolor.frontier_order import frontier_trace, traversal_order


def prefix_oracle(n, edges, order, palette_size):
    """Enumerate every full prefix assignment, then project its actual boundary.

    Unlike the producer, this oracle does not forget any prefix colors before
    checking every induced edge. It is deliberately limited to tiny graphs.
    """
    rows = []
    for size in range(1, n + 1):
        prefix = tuple(order[:size])
        processed = set(prefix)
        boundary = sorted(vertex for vertex in prefix if any(
            (a == vertex and b not in processed) or (b == vertex and a not in processed)
            for a, b in edges))
        assignments = set()
        for colors in product(range(palette_size), repeat=size):
            mapping = dict(zip(prefix, colors))
            if all(mapping[a] != mapping[b] for a, b in edges
                   if a in processed and b in processed):
                assignments.add(tuple(mapping[vertex] for vertex in boundary))
        rows.append((boundary, assignments))
    return rows


def orbit_pattern(state):
    """Encode only pairwise color equalities using the first matching position."""
    # First equal occurrence positions identify a partition without using the
    # producer's sequential color-renaming implementation.
    return tuple(state.index(color) for color in state)


class FrontierOrderTests(unittest.TestCase):
    """Test existence, all frontier states, witness recovery and order generation."""

    def test_five_vertex_path_has_explicit_counts_and_forgets_safely(self):
        """A natural path order has width one despite many complete colorings."""
        edges = tuple((vertex, vertex + 1) for vertex in range(4))
        trace = frontier_trace(5, edges, range(5), include_states=True)
        self.assertTrue(trace["feasible"])
        self.assertEqual([row["boundary"] for row in trace["rows"]],
                         [[0], [1], [2], [3], []])
        self.assertEqual([row["labeled_states"] for row in trace["rows"]], [4, 4, 4, 4, 1])
        self.assertEqual([row["orbit_states"] for row in trace["rows"]], [1, 1, 1, 1, 1])
        self.assertEqual([row["attempted_transitions"] for row in trace["rows"]],
                         [4, 16, 16, 16, 16])
        self.assertEqual([row["accepted_transitions"] for row in trace["rows"]],
                         [4, 12, 12, 12, 12])
        self.assertEqual(trace["rows"][-1]["states"], [[]])
        self.assertEqual(trace["summary"], {
            "peak_width": 1, "peak_labeled_states": 4, "peak_orbit_states": 1,
            "cumulative_labeled_states": 17, "cumulative_orbit_states": 5,
            "attempted_transitions": 68, "accepted_transitions": 52,
        })
        self.assertEqual(len(trace["one_coloring"]), 5)
        self.assertTrue(all(trace["one_coloring"][a] != trace["one_coloring"][b] for a, b in edges))

    def test_same_path_different_order_preserves_answer_but_changes_states(self):
        """No frozen interior assignments are assumed when frontier width grows."""
        edges = tuple((vertex, vertex + 1) for vertex in range(4))
        order = (0, 2, 4, 1, 3)
        trace = frontier_trace(5, edges, order, include_states=True)
        self.assertTrue(trace["feasible"])
        self.assertEqual([row["boundary"] for row in trace["rows"]],
                         [[0], [0, 2], [0, 2, 4], [2, 4], []])
        self.assertEqual([row["labeled_states"] for row in trace["rows"]], [4, 16, 64, 16, 1])
        self.assertEqual([row["orbit_states"] for row in trace["rows"]], [1, 2, 5, 2, 1])
        self.assertEqual([row["accepted_transitions"] for row in trace["rows"]],
                         [4, 16, 64, 144, 36])
        self.assertEqual(trace["summary"]["peak_width"], 3)
        self.assertEqual(trace["summary"]["peak_labeled_states"], 64)

    def test_complete_graphs_distinguish_three_four_and_five_colors(self):
        """Global named states must not collapse into independently renamed pieces."""
        k4 = tuple(combinations(range(4), 2))
        impossible = frontier_trace(4, k4, (3, 0, 2, 1), palette_size=3)
        possible = frontier_trace(4, k4, (3, 0, 2, 1), palette_size=4)
        self.assertFalse(impossible["feasible"])
        self.assertIsNone(impossible["one_coloring"])
        self.assertTrue(possible["feasible"])
        self.assertEqual(len(set(possible["one_coloring"])), 4)
        k5 = tuple(combinations(range(5), 2))
        trace = frontier_trace(5, k5, range(5), palette_size=4, include_states=True)
        self.assertFalse(trace["feasible"])
        self.assertEqual(trace["rows"][-1]["states"], [])
        self.assertIsNone(trace["one_coloring"])

    def test_self_loop_kills_states_when_reached_and_parallel_edges_deduplicate(self):
        """Loops remain real inequality constraints; repeated edges do not multiply them."""
        edges = ((0, 1), (1, 0), (0, 1), (1, 2), (2, 2), (2, 2))
        trace = frontier_trace(3, edges, (0, 1, 2), include_states=True)
        self.assertEqual(trace["edges"], [[0, 1], [1, 2], [2, 2]])
        self.assertEqual([row["labeled_states"] for row in trace["rows"]], [4, 4, 0])
        self.assertFalse(trace["feasible"])
        self.assertEqual(trace["rows"][-1]["accepted_transitions"], 0)
        early = frontier_trace(3, edges, (2, 0, 1), include_states=True)
        self.assertEqual([row["labeled_states"] for row in early["rows"]], [0, 0, 0])
        self.assertEqual([row["attempted_transitions"] for row in early["rows"]], [4, 0, 0])
        without_loop = ((0, 1), (1, 0), (0, 1), (1, 2))
        duplicated = frontier_trace(3, without_loop, range(3), include_states=True)
        simple = frontier_trace(3, ((0, 1), (1, 2)), range(3), include_states=True)
        self.assertEqual(duplicated, simple)

    def test_empty_graph_disconnected_components_and_isolated_vertices(self):
        """Forgetting a component retains an internal witness with fixed color names."""
        empty = frontier_trace(0, (), (), include_states=True)
        self.assertTrue(empty["feasible"])
        self.assertEqual(empty["one_coloring"], [])
        self.assertEqual(empty["rows"], [])
        self.assertEqual(empty["summary"]["peak_labeled_states"], 1)
        self.assertEqual(empty["summary"]["cumulative_labeled_states"], 0)
        isolated = frontier_trace(3, (), (2, 0, 1), palette_size=1, include_states=True)
        self.assertEqual(isolated["one_coloring"], [0, 0, 0])
        self.assertEqual([row["states"] for row in isolated["rows"]], [[[]], [[]], [[]]])
        edges = ((0, 1), (2, 3))
        trace = frontier_trace(5, edges, (1, 3, 4, 0, 2), palette_size=2, include_states=True)
        self.assertTrue(trace["feasible"])
        self.assertEqual(len(trace["one_coloring"]), 5)
        self.assertTrue(all(trace["one_coloring"][a] != trace["one_coloring"][b] for a, b in edges))
        for row, (boundary, states) in zip(trace["rows"], prefix_oracle(5, edges, (1, 3, 4, 0, 2), 2)):
            self.assertEqual(row["boundary"], boundary)
            self.assertEqual({tuple(state) for state in row["states"]}, states)

    def test_states_are_optional_but_do_not_change_computation(self):
        """Diagnostic verbosity cannot change state retention or the witness."""
        edges = tuple(combinations(range(4), 2))
        detailed = frontier_trace(4, edges, range(4), include_states=True)
        compact = frontier_trace(4, edges, range(4))
        for row in detailed["rows"]:
            row.pop("states")
        self.assertEqual(detailed, compact)
        self.assertEqual(compact, frontier_trace(4, edges, range(4)))

    def test_traversals_are_deterministic_and_continue_across_components(self):
        """BFS/DFS use ascending neighbor IDs, then restart from the least unused ID."""
        edges = ((0, 1), (0, 2), (1, 3), (2, 4), (5, 6))
        self.assertEqual(traversal_order(8, edges, 0, "bfs"), [0, 1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(traversal_order(8, edges, 0, "dfs"), [0, 1, 3, 2, 4, 5, 6, 7])
        self.assertEqual(traversal_order(8, edges, 0, "min_frontier"), [0, 1, 3, 2, 4, 5, 6, 7])
        for method in ("bfs", "dfs", "min_frontier"):
            self.assertEqual(traversal_order(0, (), None, method), [])
            self.assertEqual(traversal_order(8, edges, 6, method)[:2], [6, 5])
            self.assertEqual(traversal_order(3, ((0, 0),), 2, method), [2, 0, 1])
            self.assertEqual(traversal_order(8, reversed(edges), 0, method),
                             traversal_order(8, edges, 0, method))

    def test_min_frontier_uses_all_available_neighbors_and_declared_priority(self):
        """Audit the heuristic independently over each selected prefix."""
        edges = ((0, 1), (0, 4), (1, 2), (1, 3), (2, 5), (3, 5), (4, 6))
        order = traversal_order(8, edges, 0, "min_frontier")
        processed = {order[0]}
        for chosen in order[1:]:
            available = {b if a in processed else a for a, b in edges
                         if (a in processed) != (b in processed)}
            if available:
                def independent_width(candidate):
                    """Inspect edge crossings directly, without the producer helper."""
                    prefix = processed | {candidate}
                    inside_endpoints = {a if a in prefix else b for a, b in edges
                                        if (a in prefix) != (b in prefix)}
                    return len(inside_endpoints)
                self.assertEqual(chosen, min(available, key=lambda vertex:
                                            (independent_width(vertex), vertex)))
            else:
                self.assertEqual(chosen, min(set(range(8)) - processed))
            processed.add(chosen)

    def test_strict_input_validation(self):
        """Reject ambiguous booleans, malformed endpoints, orders and palettes."""
        invalid_graphs = ((True, ()), (-1, ()), (2.0, ()),
                          (2, None), (2, (None,)), (2, ((0,),)),
                          (2, ((0, 1, 1),)), (2, ((0, 2),)),
                          (2, ((-1, 0),)), (2, ((False, 1),)))
        for n, edges in invalid_graphs:
            with self.subTest(n=n, edges=edges):
                with self.assertRaises(ValueError):
                    frontier_trace(n, edges, ())
                with self.assertRaises(ValueError):
                    traversal_order(n, edges, 0)
        for order in (None, (), (0,), (0, 0), (0, 2), (False, 1), (0, 1, 2)):
            with self.subTest(order=order):
                with self.assertRaises(ValueError):
                    frontier_trace(2, (), order)
        for palette in (0, 5, True, 2.0, None):
            with self.subTest(palette=palette):
                with self.assertRaises(ValueError):
                    frontier_trace(2, (), (0, 1), palette_size=palette)
        with self.assertRaises(ValueError):
            frontier_trace(2, (), (0, 1), include_states=1)
        for start in (None, -1, 2, False, 1.0):
            with self.subTest(start=start):
                with self.assertRaises(ValueError):
                    traversal_order(2, (), start)
        with self.assertRaises(ValueError):
            traversal_order(0, (), 0)
        for method in (None, "random", True, []):
            with self.subTest(method=method):
                with self.assertRaises(ValueError):
                    traversal_order(2, (), 0, method)

    def test_all_small_simple_graphs_orders_and_palettes_match_every_prefix(self):
        """Exhaust n<=4, all graph edge sets, all orders, and palettes 1..4.

        Each row is checked against independently enumerated complete prefix
        colorings before projection. This tests forgotten information, state
        multiplicities and orbit counts without trusting final feasibility alone.
        """
        graph_count = trace_count = prefix_count = 0
        for n in range(5):
            possible_edges = tuple(combinations(range(n), 2))
            for edge_mask in range(1 << len(possible_edges)):
                edges = tuple(edge for position, edge in enumerate(possible_edges)
                              if edge_mask & (1 << position))
                graph_count += 1
                for order in permutations(range(n)):
                    for palette in range(1, 5):
                        trace_count += 1
                        trace = frontier_trace(n, edges, order, palette, include_states=True)
                        expected = prefix_oracle(n, edges, order, palette)
                        previous_state_count = 1
                        with self.subTest(n=n, edges=edges, order=order, palette=palette):
                            for step, (row, (boundary, states)) in enumerate(zip(trace["rows"], expected), 1):
                                prefix_count += 1
                                self.assertEqual(row["step"], step)
                                self.assertEqual(row["vertex"], order[step - 1])
                                self.assertEqual(row["boundary"], boundary)
                                self.assertEqual(row["width"], len(boundary))
                                self.assertEqual(row["states"], [list(state) for state in sorted(states)])
                                self.assertEqual(row["labeled_states"], len(states))
                                self.assertEqual(row["orbit_states"], len({orbit_pattern(state) for state in states}))
                                self.assertEqual(row["attempted_transitions"], previous_state_count * palette)
                                previous_state_count = len(states)
                            feasible = bool(expected[-1][1]) if n else True
                            self.assertEqual(trace["feasible"], feasible)
                            if feasible:
                                witness = trace["one_coloring"]
                                self.assertEqual(len(witness), n)
                                self.assertTrue(all(type(color) is int and 0 <= color < palette for color in witness))
                                self.assertTrue(all(witness[a] != witness[b] for a, b in edges))
                            else:
                                self.assertIsNone(trace["one_coloring"])
        self.assertEqual(graph_count, 76)
        self.assertEqual(trace_count, 6360)
        self.assertEqual(prefix_count, 25188)


if __name__ == "__main__":
    unittest.main()

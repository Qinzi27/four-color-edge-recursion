"""Audit the orbit quotient against complete independent prefix enumeration."""

from itertools import combinations, permutations, product
import unittest

from fourcolor.frontier_order import frontier_trace
from fourcolor.orbit_frontier import orbit_frontier_trace


def prefix_partition_oracle(n, edges, order, palette_size):
    """Brute-force induced prefixes without the producer's forgetting or naming.

    An orbit is encoded by each position's first equal-color position. This
    represents an equality partition without copying restricted-growth code.
    """
    rows = []
    for size in range(1, n + 1):
        prefix = tuple(order[:size])
        processed = set(prefix)
        boundary = sorted({a if a in processed else b for a, b in edges
                           if (a in processed) != (b in processed)})
        partitions = set()
        for colors in product(range(palette_size), repeat=size):
            coloring = dict(zip(prefix, colors))
            if all(coloring[a] != coloring[b] for a, b in edges
                   if a in processed and b in processed):
                projected = tuple(coloring[item] for item in boundary)
                partitions.add(tuple(projected.index(color) for color in projected))
        rows.append((boundary, partitions))
    return rows


class OrbitFrontierTests(unittest.TestCase):
    """Check exact states, global witness renaming, failures and counted work."""

    def assert_matches_oracle(self, n, edges, order, palette_size):
        """Compare every retained state, not just final feasibility."""
        result = orbit_frontier_trace(n, edges, order, palette_size, include_states=True)
        expected = prefix_partition_oracle(n, edges, order, palette_size)
        for row, (boundary, partitions) in zip(result["rows"], expected):
            self.assertEqual(row["boundary"], boundary)
            actual = {tuple(state.index(color) for color in state)
                      for state in row["states"]}
            self.assertEqual(actual, partitions)
            self.assertEqual(row["orbit_states"], len(partitions))
            for state in row["states"]:
                # First use creates exactly the next class, independently of
                # the oracle representation used to check equality partitions.
                seen = set()
                for color in state:
                    if color not in seen:
                        self.assertEqual(color, len(seen))
                        seen.add(color)
        feasible = bool(expected[-1][1]) if expected else True
        self.assertEqual(result["feasible"], feasible)
        if feasible:
            coloring = result["one_coloring"]
            self.assertEqual(len(coloring), n)
            self.assertTrue(all(0 <= color < palette_size for color in coloring))
            self.assertTrue(all(coloring[a] != coloring[b] for a, b in edges))
        else:
            self.assertIsNone(result["one_coloring"])
        return result

    def test_small_graphs_all_palettes_against_independent_prefix_oracle(self):
        """Exhaust n<=3 orders, then every n=4 graph with three different orders.

        This bounded suite checks 984 traces / 3,684 nonempty prefixes; the
        separate named-state module already tests all n=4 permutations. Both
        suites use brute-force prefix assignments rather than each other as
        their correctness oracle.
        """
        trace_count = prefix_count = 0
        for n in range(5):
            possible = tuple(combinations(range(n), 2))
            orders = (tuple(permutations(range(n))) if n <= 3
                      else ((0, 1, 2, 3), (3, 2, 1, 0), (0, 2, 3, 1)))
            for mask in range(1 << len(possible)):
                edges = tuple(edge for index, edge in enumerate(possible)
                              if mask & (1 << index))
                for order in orders:
                    for palette in range(1, 5):
                        with self.subTest(n=n, mask=mask, order=order, palette=palette):
                            self.assert_matches_oracle(n, edges, order, palette)
                        trace_count += 1
                        prefix_count += n
        self.assertEqual(trace_count, 984)
        self.assertEqual(prefix_count, 3684)

    def test_path_recolors_forgotten_vertices_and_reuses_absent_names(self):
        """Every path step forgets a name while the full witness stays proper."""
        edges = tuple((vertex, vertex + 1) for vertex in range(5))
        result = self.assert_matches_oracle(6, edges, tuple(range(6)), 2)
        self.assertEqual([row["states"] for row in result["rows"]],
                         [[[0]], [[0]], [[0]], [[0]], [[0]], [[]]])
        self.assertEqual(result["summary"]["attempted_transitions"], 11)
        self.assertEqual(result["summary"]["accepted_transitions"], 6)
        self.assertEqual(result["summary"]["peak_states"], 1)
        # Merely renaming the boundary at each step would eventually make
        # adjacent forgotten vertices equal; this checks the recovered witness.
        self.assertEqual(result["one_coloring"], [0, 1, 0, 1, 0, 1])

    def test_four_colors_and_nonconsecutive_forgetting_keep_all_equalities(self):
        """Removing early classes must preserve different remaining classes."""
        edges = tuple(combinations(range(4), 2)) + ((1, 4), (2, 4), (3, 5), (4, 5))
        result = self.assert_matches_oracle(6, edges, (0, 1, 3, 2, 5, 4), 4)
        self.assertTrue(result["feasible"])
        self.assertEqual(len(set(result["one_coloring"][:4])), 4)

    def test_exact_named_baseline_agrees_and_symmetry_reduces_transition_count(self):
        """A fixed order isolates color-symmetry work from order-selection work."""
        edges = tuple((vertex, vertex + 1) for vertex in range(4))
        order = (0, 2, 4, 1, 3)
        orbit = self.assert_matches_oracle(5, edges, order, 4)
        named = frontier_trace(5, edges, order, palette_size=4)
        self.assertEqual([row["orbit_states"] for row in orbit["rows"]],
                         [row["orbit_states"] for row in named["rows"]])
        self.assertEqual(orbit["summary"]["peak_states"], 5)
        self.assertLess(orbit["summary"]["attempted_transitions"],
                        named["summary"]["attempted_transitions"])

    def test_complete_graph_negative_cases(self):
        """Quotienting cannot make K4 three-colorable or K5 four-colorable."""
        for n, palette in ((4, 3), (5, 4)):
            edges = tuple(combinations(range(n), 2))
            result = self.assert_matches_oracle(n, edges, tuple(reversed(range(n))), palette)
            self.assertFalse(result["feasible"])
            self.assertEqual(result["rows"][-1]["states"], [])
        self.assertTrue(self.assert_matches_oracle(
            4, tuple(combinations(range(4), 2)), (2, 0, 3, 1), 4)["feasible"])

    def test_loops_parallel_edges_and_unsatisfiable_prefix(self):
        """A self-loop kills states; repeated inequalities do not change them."""
        duplicates = ((0, 1), (1, 0), (0, 1), (1, 2))
        simple = ((0, 1), (1, 2))
        self.assertEqual(orbit_frontier_trace(3, duplicates, range(3), include_states=True),
                         orbit_frontier_trace(3, simple, range(3), include_states=True))
        looped = self.assert_matches_oracle(3, simple + ((1, 1),), (1, 0, 2), 4)
        self.assertEqual([row["attempted_transitions"] for row in looped["rows"]], [1, 0, 0])
        self.assertEqual([row["orbit_states"] for row in looped["rows"]], [0, 0, 0])

    def test_empty_disconnected_and_isolated_inputs(self):
        """Closed components keep witnesses even when every frontier name vanishes."""
        empty = self.assert_matches_oracle(0, (), (), 1)
        self.assertEqual(empty["one_coloring"], [])
        self.assertEqual(empty["summary"], {
            "peak_width": 0, "peak_states": 1, "cumulative_states": 0,
            "attempted_transitions": 0, "accepted_transitions": 0,
        })
        edges = ((0, 1), (2, 3), (3, 4), (4, 2))
        for order in ((0, 1, 2, 3, 4, 5), (4, 0, 5, 2, 1, 3)):
            self.assert_matches_oracle(6, edges, order, 3)
        isolated = self.assert_matches_oracle(3, (), (2, 0, 1), 1)
        self.assertEqual(isolated["one_coloring"], [0, 0, 0])

    def test_optional_states_and_determinism(self):
        """Adding diagnostics must not change a state, counter or full witness."""
        edges = ((0, 1), (0, 2), (1, 3), (2, 3))
        detailed = orbit_frontier_trace(4, edges, (0, 2, 1, 3), include_states=True)
        compact = orbit_frontier_trace(4, edges, (0, 2, 1, 3))
        for row in detailed["rows"]:
            row.pop("states")
        self.assertEqual(detailed, compact)
        self.assertEqual(compact, orbit_frontier_trace(4, reversed(edges), (0, 2, 1, 3)))

    def test_strict_input_validation(self):
        """Reject ambiguous booleans and malformed graph/order/palette inputs."""
        for n, edges in ((True, ()), (-1, ()), (2.0, ()), (2, None),
                         (2, (None,)), (2, ((0,),)), (2, ((0, 1, 1),)),
                         (2, ((0, 2),)), (2, ((-1, 0),)), (2, ((False, 1),))):
            with self.subTest(n=n, edges=edges):
                with self.assertRaises(ValueError):
                    orbit_frontier_trace(n, edges, ())
        for order in (None, (), (0,), (0, 0), (0, 2), (False, 1), (0, 1, 2)):
            with self.subTest(order=order):
                with self.assertRaises(ValueError):
                    orbit_frontier_trace(2, (), order)
        for palette in (0, 5, True, 2.0, None):
            with self.subTest(palette=palette):
                with self.assertRaises(ValueError):
                    orbit_frontier_trace(2, (), (0, 1), palette_size=palette)
        with self.assertRaises(ValueError):
            orbit_frontier_trace(2, (), (0, 1), include_states=1)


if __name__ == "__main__":
    unittest.main()

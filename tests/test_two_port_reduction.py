"""Independent feasibility and relation checks for two-terminal elimination."""

from copy import deepcopy
from itertools import combinations, permutations, product
import unittest

from fourcolor.two_port_reduction import DIFF, EQ, compose_relations, two_port_trace


def brute_coloring(n, edges, palette_size):
    """Enumerate concrete full colorings, without elimination or orbit code."""
    return next((colors for colors in product(range(palette_size), repeat=n)
                 if all(colors[a] != colors[b] for a, b in edges)), None)


class TwoPortReductionTests(unittest.TestCase):
    """Check exact existential composition and reverse witness reconstruction."""

    def assert_witness(self, result):
        """Check original edges and all saved, possibly generated constraints."""
        if not result["feasible"]:
            self.assertIsNone(result["one_coloring"])
            self.assertIn("cause", result)
            return
        colors = result["one_coloring"]
        self.assertEqual(len(colors), result["n"])
        self.assertTrue(all(0 <= color < result["palette_size"] for color in colors))
        self.assertTrue(all(colors[a] != colors[b] for a, b in result["edges"]))
        assembled = set(result["core"]["vertices"])
        for record in reversed(result["reductions"]):
            vertex = record["vertex"]
            self.assertNotIn(vertex, assembled)
            self.assertTrue(set(record["neighbors"]) <= assembled)
            for other, mask in zip(record["neighbors"], record["relation_masks"]):
                bit = EQ if colors[vertex] == colors[other] else DIFF
                self.assertTrue(mask & bit, (record, colors))
            assembled.add(vertex)
        self.assertEqual(assembled, set(range(result["n"])))

    def test_all_graphs_through_four_vertices_against_full_assignments(self):
        """All small graphs, all palettes, all n<=3 orders and three n=4 orders."""
        traces = 0
        for n in range(5):
            possible = tuple(combinations(range(n), 2))
            orders = (tuple(permutations(range(n))) if n <= 3
                      else ((0, 1, 2, 3), (3, 2, 1, 0), (0, 2, 3, 1)))
            for bits in range(1 << len(possible)):
                edges = [edge for index, edge in enumerate(possible) if bits >> index & 1]
                for q in range(1, 5):
                    expected = brute_coloring(n, edges, q) is not None
                    for order in orders:
                        result = two_port_trace(n, edges, order, q)
                        self.assertEqual(result["feasible"], expected, (n, edges, order, q))
                        self.assert_witness(result)
                        traces += 1
        self.assertEqual(traces, 984)

    def test_all_relation_masks_against_all_terminal_assignments(self):
        """Check every pair, not just the two representative terminal patterns."""
        for q, left, right in product(range(1, 5), range(4), range(4)):
            actual = compose_relations(q, left, right)
            for first, second in product(range(q), repeat=2):
                expected = any((left & (EQ if first == middle else DIFF))
                               and (right & (EQ if middle == second else DIFF))
                               for middle in range(q))
                bit = EQ if first == second else DIFF
                self.assertEqual(bool(actual & bit), bool(expected), (q, left, right))
            if q == 1:
                self.assertFalse(actual & DIFF)
        self.assertEqual(compose_relations(2, DIFF, DIFF), EQ)
        self.assertEqual(compose_relations(3, DIFF, DIFF), EQ | DIFF)
        self.assertEqual(compose_relations(4, EQ, DIFF), DIFF)
        self.assertEqual(compose_relations(1, DIFF, EQ | DIFF), 0)

    def test_cycle_parity_and_triangle_palette_boundary(self):
        """An odd two-color cycle fails during elimination, not a hidden search."""
        for n in range(3, 11):
            edges = [(v, (v + 1) % n) for v in range(n)]
            for q in (2, 3, 4):
                result = two_port_trace(n, edges, list(range(n)), q)
                self.assertEqual(result["feasible"], q >= 3 or n % 2 == 0)
                self.assertIsNone(result["core"]["trace"])
                self.assertEqual(result["summary"]["attempted_transitions"], 0)
                self.assert_witness(result)
                if not result["feasible"]:
                    self.assertEqual(result["cause"]["kind"], "empty_terminal_intersection")

    def test_generated_equality_is_saved_and_not_replaced_by_inequality(self):
        """The square generates an EQ edge absent from the original input."""
        edges = [(0, 1), (1, 2), (2, 3), (3, 0)]
        result = two_port_trace(4, edges, [0, 2, 1, 3], 2)
        self.assertTrue(result["feasible"])
        self.assertEqual(result["reductions"][0]["terminal_vertices"], [1, 3])
        self.assertEqual(result["reductions"][0]["result_mask"], EQ)
        self.assertEqual(result["reductions"][1]["previous_mask"], EQ)
        self.assertEqual(result["reductions"][2]["relation_masks"], [EQ])
        self.assert_witness(result)

    def test_existing_terminal_constraint_is_intersected_not_overwritten(self):
        """DIFF intersect EQ is empty; deleting that DIFF would miscolor a triangle."""
        result = two_port_trace(3, [(0, 1), (0, 2), (1, 2)], [0, 1, 2], 2)
        self.assertFalse(result["feasible"])
        record = result["reductions"][0]
        self.assertEqual((record["previous_mask"], record["composed_mask"], record["result_mask"]),
                         (DIFF, EQ, 0))

    def test_k4_stays_in_core_and_uses_the_declared_exact_solver(self):
        """A minimum-degree-three graph does not masquerade as a two-port piece."""
        edges = list(combinations(range(4), 2))
        for q in (2, 3, 4):
            result = two_port_trace(4, edges, [2, 0, 3, 1], q)
            self.assertEqual(result["feasible"], q == 4)
            self.assertEqual(result["reductions"], [])
            self.assertEqual(result["core"]["classes"], [[2], [0], [3], [1]])
            self.assertIsNotNone(result["core"]["trace"])
            self.assertEqual(result["summary"]["core_vertices"], 4)
            self.assertEqual(result["summary"]["relation_compositions"], 0)
            self.assert_witness(result)

    def test_equality_contraction_rejects_internal_inequality(self):
        """Two subdivided K4 edges force an EQ chain contradictory to its chord."""
        edges = [(0, 2), (0, 3), (1, 3), (2, 3), (0, 4), (4, 1), (1, 5), (5, 2)]
        result = two_port_trace(6, edges, [4, 5, 0, 1, 2, 3], 2)
        self.assertFalse(result["feasible"])
        self.assertEqual(result["summary"]["eliminated_vertices"], 2)
        self.assertEqual(result["cause"]["kind"], "inequality_inside_equality_class")
        self.assertIsNone(result["core"]["trace"])
        self.assertIn([0, 1, 2], result["core"]["classes"])

    def test_equality_core_contraction_and_expansion_reconstruct_a_solution(self):
        """Subdividing every K4 edge makes its branch vertices one equality class."""
        edges = []
        for new_vertex, (first, second) in enumerate(combinations(range(4), 2), 4):
            edges.extend([(first, new_vertex), (new_vertex, second)])
        result = two_port_trace(10, edges, list(range(4, 10)) + list(range(4)), 2)
        self.assertTrue(result["feasible"])
        self.assertEqual(result["summary"]["core_vertices"], 4)
        self.assertEqual(result["summary"]["core_classes"], 1)
        self.assertEqual(result["core"]["classes"], [[0, 1, 2, 3]])
        self.assertIsNotNone(result["core"]["trace"])
        self.assert_witness(result)

    def test_disconnected_parallel_empty_and_one_color_inputs(self):
        """Input normalization preserves isolated vertices and explicit failures."""
        empty = two_port_trace(0, [], [], 1)
        self.assertTrue(empty["feasible"])
        self.assertEqual(empty["one_coloring"], [])
        self.assertEqual(empty["summary"]["peak_states"], 0)
        isolated = two_port_trace(4, [], [3, 1, 2, 0], 1)
        self.assertEqual(isolated["one_coloring"], [0, 0, 0, 0])
        edges = [(0, 1), (1, 0), (0, 1), (2, 3)]
        result = two_port_trace(5, edges, [4, 3, 1, 2, 0], 2)
        self.assertEqual(result["edges"], [[0, 1], [2, 3]])
        self.assert_witness(result)
        self.assertFalse(two_port_trace(2, [(0, 1)], [0, 1], 1)["feasible"])
        for q in range(1, 5):
            result = two_port_trace(3, [(0, 1), (2, 2)], [0, 1, 2], q)
            self.assertFalse(result["feasible"])
            self.assertEqual(result["cause"]["kind"], "empty_input_relation" if q == 1 else "self_loop")

    def test_priority_is_supplied_order_and_inputs_are_unchanged(self):
        """Fill creation does not mutate source lists or borrow their identities."""
        edges = [[0, 1], [1, 2], [2, 3], [3, 0]]
        order = [2, 0, 3, 1]
        before = deepcopy((edges, order))
        result = two_port_trace(4, edges, order, 3)
        self.assertEqual([record["vertex"] for record in result["reductions"]], order)
        self.assertEqual((edges, order), before)
        result["edges"][0][0] = 99
        result["order"][0] = 99
        self.assertEqual((edges, order), before)

    def test_invalid_inputs_raise_value_errors(self):
        """Reject malformed masks and graph inputs, including bool-as-integer."""
        for q in (0, 5, True, 2.0, None):
            with self.assertRaises(ValueError):
                two_port_trace(1, [], [0], q)
            with self.assertRaises(ValueError):
                compose_relations(q, EQ, DIFF)
        for mask in (-1, 4, True, 1.0, None):
            with self.assertRaises(ValueError):
                compose_relations(3, mask, EQ)
            with self.assertRaises(ValueError):
                compose_relations(3, EQ, mask)
        for args in ((True, [], []), (-1, [], []), (2, [(0, 2)], [0, 1]),
                     (2, [(False, 1)], [0, 1]), (2, [(0,)], [0, 1]),
                     (2, None, [0, 1]), (2, [], [0, 0]), (2, [], [0, True]),
                     (2, [], None)):
            with self.assertRaises(ValueError):
                two_port_trace(*args)

    def test_long_chain_is_iterative_and_separates_work_counters(self):
        """Elimination and reconstruction require no recursion or core search."""
        n = 1500
        edges = [(vertex, vertex + 1) for vertex in range(n - 1)]
        result = two_port_trace(n, edges, list(range(n)), 2)
        self.assertTrue(result["feasible"])
        self.assertEqual(result["summary"]["eliminated_vertices"], n)
        self.assertEqual(result["summary"]["core_vertices"], 0)
        self.assertEqual(result["summary"]["attempted_transitions"], 0)
        self.assertEqual(result["summary"]["relation_compositions"], 0)
        self.assertGreater(result["summary"]["unary_support_checks"], 0)
        self.assertGreaterEqual(result["summary"]["reconstruction_attempts"], n)
        self.assert_witness(result)


if __name__ == "__main__":
    unittest.main()

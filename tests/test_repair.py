"""Compare the SP flow-defect recurrence to exhaustive edge-label search."""

from itertools import product
from math import inf
import random
import unittest

from fourcolor.repair import Edge, Parallel, Series, minimum_repair, realize, repair_table
from tests.oracles import brute_repair_table, random_expression, xor_defects


class RepairTests(unittest.TestCase):
    def assert_expression_matches_oracle(self, expression):
        n, edges, original, terminals = realize(expression)
        expected, _ = brute_repair_table(n, edges, original, terminals)
        actual = tuple(repair_table(expression))
        self.assertEqual(actual, expected, "Compare every terminal-flow state q, not just q=0")
        self.assertTrue(all(type(cost) is int for cost in actual if cost != inf))
        cost, labels = minimum_repair(expression)
        self.assertEqual(cost, expected[0])
        if cost == inf:
            self.assertEqual(tuple(labels), ())
        else:
            self.assertEqual(len(labels), len(edges))
            self.assertTrue(all(label in (1, 2, 3) for label in labels))
            self.assertEqual(sum(old != new for old, new in zip(original, labels)), cost)
            self.assertEqual(xor_defects(n, edges, labels), (0,) * n)

    def test_edge_and_series_base_cases(self):
        self.assertEqual(tuple(repair_table(Edge(2))), (inf, 1, 0, 1))
        self.assertEqual(tuple(repair_table(Series(Edge(1), Edge(2)))), (inf, 1, 1, 2))
        self.assert_expression_matches_oracle(Edge(2))
        self.assert_expression_matches_oracle(Series(Edge(1), Edge(2)))

    def test_parallel_base_case_and_witness(self):
        # Two equally labeled parallel edges have zero terminal defect.
        expression = Parallel(Edge(1), Edge(1))
        self.assertEqual(tuple(repair_table(expression))[0], 0)
        self.assert_expression_matches_oracle(expression)

    def test_all_triangle_original_labels(self):
        # A triangle is one direct edge in parallel with a two-edge path.
        for labels in product((1, 2, 3), repeat=3):
            expression = Parallel(Edge(labels[0]), Series(Edge(labels[1]), Edge(labels[2])))
            with self.subTest(labels=labels):
                self.assert_expression_matches_oracle(expression)
                self.assertEqual(minimum_repair(expression)[0], 3 - max(labels.count(k) for k in (1, 2, 3)))

    def test_all_theta_original_labels(self):
        # Three direct parallel branches balance exactly when their colors differ.
        for labels in product((1, 2, 3), repeat=3):
            expression = Parallel(Parallel(Edge(labels[0]), Edge(labels[1])), Edge(labels[2]))
            with self.subTest(labels=labels):
                self.assert_expression_matches_oracle(expression)
                self.assertEqual(minimum_repair(expression)[0], 3 - len(set(labels)))

    def test_subdivided_theta(self):
        expression = Parallel(
            Series(Edge(1), Edge(2)),
            Parallel(Series(Edge(2), Edge(3)), Series(Edge(3), Edge(1))),
        )
        self.assert_expression_matches_oracle(expression)

    def test_seeded_random_expressions(self):
        rng = random.Random(20260906)
        for case in range(30):
            expression = random_expression(rng, rng.randint(1, 7))
            with self.subTest(case=case, expression=expression):
                self.assert_expression_matches_oracle(expression)

    def test_eight_edge_example(self):
        expression = Parallel(
            Series(Parallel(Edge(1), Edge(2)), Parallel(Edge(3), Edge(1))),
            Series(Parallel(Edge(2), Edge(3)), Parallel(Edge(1), Edge(1))),
        )
        self.assert_expression_matches_oracle(expression)

    def test_deep_trees_do_not_depend_on_python_recursion_limit(self):
        # Closed-form fixtures check deep skew syntax without exponential search.
        # An even number of parallel 1-labeled edges is already balanced; a
        # series path can carry only a nonzero terminal defect of one shared label.
        edge_count = 1200
        parallel = Edge(1)
        series = Edge(1)
        for _ in range(edge_count - 1):
            parallel = Parallel(parallel, Edge(1))
            series = Series(series, Edge(1))
        self.assertEqual(minimum_repair(parallel), (0, (1,) * edge_count))
        self.assertEqual(len(realize(parallel)[1]), edge_count)
        self.assertEqual(tuple(repair_table(series)), (inf, 0, edge_count, edge_count))
        self.assertEqual(minimum_repair(series), (inf, ()))
        self.assertEqual(realize(series)[0], edge_count + 1)

    def test_shared_syntax_keeps_large_costs_exact(self):
        # A shared syntax DAG compactly describes repeated edge occurrences.
        # Never realize this exponentially large graph: its four-state table
        # is enough to detect precision loss above the exact float-int range.
        expression = Edge(1)
        for _ in range(54):
            expression = Series(expression, expression)
        expression = Series(expression, Edge(1))
        size = 2 ** 54 + 1
        table = tuple(repair_table(expression))
        self.assertEqual(table, (inf, 0, size, size))
        self.assertTrue(all(type(cost) is int for cost in table if cost != inf))
        # Mixing an unreachable-state sentinel with huge integers must not
        # coerce integers to floats or raise OverflowError during convolution.
        huge = Series(Edge(1), Edge(2))
        for _ in range(2000):
            huge = Series(huge, huge)
        huge_table = tuple(repair_table(Parallel(huge, Edge(1))))
        self.assertEqual(huge_table[0], 2 ** 2000)
        self.assertTrue(all(type(cost) is int for cost in huge_table if cost != inf))


if __name__ == "__main__":
    unittest.main()

"""Independent finite checks of safe single-face-interface composition."""

from itertools import combinations, product
import unittest

from fourcolor.closed_interfaces import biconnected_blocks, closed_interface_trace


class ClosedInterfaceTests(unittest.TestCase):
    """Test true solution existence, reconstruction and separator scope."""

    def test_all_graphs_up_to_four_vertices_and_palettes(self):
        """Compare to full assignments, not another decomposition solver."""
        for n in range(5):
            possible = list(combinations(range(n), 2))
            for mask in range(1 << len(possible)):
                edges = [edge for i, edge in enumerate(possible) if mask >> i & 1]
                for q in range(1, 5):
                    expected = any(all(c[a] != c[b] for a, b in edges)
                                   for c in product(range(q), repeat=n))
                    for order in (list(range(n)), list(reversed(range(n)))):
                        actual = closed_interface_trace(n, edges, order, q)
                        self.assertEqual(actual["feasible"], expected, (n, edges, q))
                        if expected:
                            colors = actual["one_coloring"]
                            self.assertTrue(all(0 <= c < q for c in colors))
                            self.assertTrue(all(colors[a] != colors[b] for a, b in edges))

    def test_blocks_and_single_port_contract(self):
        """Two triangles, a bridge and an isolate have known exact blocks."""
        edges = [(0, 1), (1, 2), (2, 0), (2, 3), (3, 4), (4, 2), (4, 5)]
        self.assertEqual(biconnected_blocks(7, edges), ((0, 1, 2), (2, 3, 4), (4, 5), (6,)))
        result = closed_interface_trace(7, edges, [5, 4, 3, 2, 1, 0, 6], 3)
        self.assertTrue(result["feasible"])
        self.assertEqual(result["summary"]["single_port_blocks"], 2)
        positions = {b: i for i, b in enumerate(result["computation_order"])}
        for block in result["blocks"]:
            if block["parent"] is not None:
                self.assertEqual(block["interface_relation"], "all_colors")
                parent = result["blocks"][block["parent"]]
                self.assertEqual(set(block["vertices"]) & set(parent["vertices"]), {block["port"]})
                self.assertLess(positions[block["id"]], positions[block["parent"]])

    def test_two_port_pieces_are_not_unsafely_split(self):
        """A square is one block, even though paths meet at two variables."""
        self.assertEqual(biconnected_blocks(4, [(0, 1), (1, 2), (2, 3), (3, 0)]),
                         ((0, 1, 2, 3),))

    def test_unsatisfiable_block_propagates(self):
        """Attaching a leaf must not hide a triangle's two-color failure."""
        result = closed_interface_trace(4, [(0, 1), (1, 2), (0, 2), (2, 3)], [3, 2, 1, 0], 2)
        self.assertFalse(result["feasible"])
        self.assertIsNone(result["one_coloring"])

    def test_loops_parallel_edges_and_empty_input(self):
        """Unsupported precolors are absent; graph edge corner cases explicit."""
        self.assertTrue(closed_interface_trace(0, [], [], 1)["feasible"])
        self.assertTrue(closed_interface_trace(2, [(0, 1), (1, 0)], [0, 1], 2)["feasible"])
        for edges in ([(0, 0)], [(0, 1), (1, 1)]):
            self.assertFalse(closed_interface_trace(2, edges, [0, 1], 4)["feasible"])
        with self.assertRaises(ValueError):
            closed_interface_trace(1, [], [0], True)
        with self.assertRaises(ValueError):
            closed_interface_trace(2, [], [0, 0], 4)

    def test_long_chain_decomposition_is_iterative(self):
        """Decomposition itself must not depend on Python's recursion limit."""
        n = 1500
        blocks = biconnected_blocks(n, [(v, v + 1) for v in range(n - 1)])
        self.assertEqual(len(blocks), n - 1)
        self.assertTrue(all(len(block) == 2 for block in blocks))


if __name__ == "__main__":
    unittest.main()

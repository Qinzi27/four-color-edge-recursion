"""Independent boundary-extension and gluing tests, including the user's map."""

from itertools import combinations, product
import unittest

from fourcolor.interface_signatures import (boundary_patterns, glue_two_terminal_pieces,
                                            interface_signature, two_terminal_signature)


def equality_pairs(values):
    """An independent equality-partition encoding, without canonical labels."""
    return tuple((i, j) for i in range(len(values)) for j in range(i) if values[i] == values[j])


class InterfaceSignatureTests(unittest.TestCase):
    """Quantify the exact information needed at two and three shared faces."""

    def test_all_small_graph_boundary_relations_against_full_assignments(self):
        """All n<=4 graphs, palettes, and terminal subsets up to size three."""
        queries = 0
        for n in range(5):
            possible = list(combinations(range(n), 2))
            for mask in range(1 << len(possible)):
                edges = [e for i, e in enumerate(possible) if mask >> i & 1]
                for q in range(1, 5):
                    legal = [c for c in product(range(q), repeat=n)
                             if all(c[a] != c[b] for a, b in edges)]
                    for arity in range(min(3, n) + 1):
                        for ports in combinations(range(n), arity):
                            # Reverse port order to exercise nonascending IDs.
                            ports = tuple(reversed(ports))
                            projected = {tuple(c[v] for v in ports) for c in legal}
                            expected = {equality_pairs(values) for values in projected}
                            actual = interface_signature(n, edges, ports, q, reversed(range(n)))
                            self.assertEqual({equality_pairs(p) for p in actual["patterns"]}, expected,
                                             (n, edges, ports, q))
                            self.assertEqual(actual["named_boundary_assignments"], len(projected))
                            self.assertEqual(actual["feasible"], bool(legal))
                            for branch in actual["queries"]:
                                witness = branch["one_coloring"]
                                if branch["feasible"]:
                                    self.assertIn(tuple(witness), legal)
                                    self.assertEqual([witness[v] for v in ports], branch["pattern"])
                                else:
                                    self.assertIsNone(witness)
                            queries += 1
        self.assertEqual(queries, 4140)

    def test_two_terminal_masks_include_forced_equality_with_three_colors(self):
        """K4 minus its terminal edge forces equal terminal colors for q=3."""
        diamond = [(0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
        self.assertEqual(two_terminal_signature(4, diamond, [0, 1], 3)["mask"], 1)
        self.assertEqual(two_terminal_signature(4, diamond, [0, 1], 4)["mask"], 3)
        self.assertEqual(two_terminal_signature(2, [(0, 1)], [0, 1], 3)["mask"], 2)
        self.assertEqual(two_terminal_signature(2, [(0, 1)], [0, 1], 1)["mask"], 0)

    def test_local_feasibility_does_not_imply_compatible_two_ports(self):
        """A two-color edge and even-length path each work, but not together."""
        pieces = [{"n": 2, "edges": [(0, 1)], "terminals": [0, 1]},
                  {"n": 3, "edges": [(0, 2), (2, 1)], "terminals": [0, 1]}]
        result = glue_two_terminal_pieces(pieces, 2)
        self.assertTrue(all(piece["feasible"] for piece in result["pieces"]))
        self.assertEqual([piece["mask"] for piece in result["pieces"]], [2, 1])
        self.assertFalse(result["feasible"])
        self.assertEqual(result["summary"]["gluing_search_calls"], 0)
        self.assertTrue(glue_two_terminal_pieces(pieces, 3)["feasible"])

    def test_gluing_orders_and_empty_piece_collection(self):
        """Local IDs need not agree, except at the declared ordered ports."""
        pieces = [{"n": 3, "edges": [(0, 1), (1, 2)], "terminals": [2, 0]},
                  {"n": 3, "edges": [(0, 2), (2, 1)], "terminals": [0, 1]}]
        result = glue_two_terminal_pieces(pieces, 2)
        self.assertEqual(result["n"], 4)
        self.assertEqual(result["mask"], 1)
        self.assertEqual(result["one_coloring"][:2], [0, 0])
        empty = glue_two_terminal_pieces([], 1)
        self.assertEqual(empty["one_coloring"], [0, 0])
        self.assertEqual(empty["mask"], 1)

    def test_original_three_blue_lines_need_genuine_three_port_relation(self):
        """Pairwise ALL projections lose the forbidden all-distinct pattern."""
        # 0,1,2 are exterior/two island faces; 3,4 are the two split regions.
        edges = [(3, 4)] + [(port, inner) for port in range(3) for inner in (3, 4)]
        result = interface_signature(5, edges, [0, 1, 2], 4)
        self.assertEqual(result["patterns"], [[0, 0, 0], [0, 0, 1], [0, 1, 0], [0, 1, 1]])
        self.assertEqual(result["named_boundary_assignments"], 40)
        for pair in combinations(range(3), 2):
            self.assertEqual(two_terminal_signature(5, edges, pair, 4)["mask"], 3)
        self.assertEqual(interface_signature(5, edges, [0, 1, 2], 3)["patterns"], [[0, 0, 0]])
        self.assertFalse(interface_signature(5, edges, [0, 1, 2], 2)["feasible"])

    def test_boundary_arity_and_unsupported_constraint_validation(self):
        for n in (None, "5", True, -1):
            with self.assertRaises(ValueError):
                two_terminal_signature(n, [], [0, 1])
        self.assertEqual(len(boundary_patterns(3, 4)), 5)
        self.assertEqual(len(boundary_patterns(3, 2)), 4)
        self.assertEqual(boundary_patterns(0, 1), ((),))
        for terminals in (None, [0, 0], [0, 4], [[0]], [False], [0, 1, 2, 3]):
            with self.assertRaises(ValueError):
                interface_signature(4, [], terminals, 4)
        with self.assertRaises(ValueError):
            glue_two_terminal_pieces([{"n": 2, "edges": [], "terminals": [0, 1],
                                       "precolored": {0: 0}}], 4)


if __name__ == "__main__":
    unittest.main()

"""Independent checks of the experiment's order-width and prefix oracles."""

from itertools import combinations, permutations
import unittest

from scripts.validate_inside_out import brute_prefix_counts, minimum_connected_width


class InsideOutExperimentTests(unittest.TestCase):
    """Check the subset optimizer against every connected small-graph order."""

    def test_subset_width_oracle_against_all_small_orders(self):
        """For n <= 4, enumerate graphs/orders directly, independent of subset DP."""
        checked = 0
        for n in range(1, 5):
            possible = list(combinations(range(n), 2))
            for mask in range(1 << len(possible)):
                edges = [edge for i, edge in enumerate(possible) if mask >> i & 1]
                adjacency = [{b if a == v else a for a, b in edges if v in (a, b)}
                             for v in range(n)]
                best = {}
                for order in permutations(range(n)):
                    done, peak, connected = set(), 0, True
                    for v in order:
                        if done and not adjacency[v] & done:
                            connected = False
                            break
                        done.add(v)
                        peak = max(peak, sum(bool(adjacency[u] - done) for u in done))
                    if connected:
                        best[order[0]] = min(peak, best.get(order[0], n))
                for root, expected in best.items():
                    result = minimum_connected_width(n, edges, root)
                    self.assertEqual(result["minimum_width"], expected)
                    self.assertEqual(result["one_order"][0], root)
                    self.assertEqual(sorted(result["one_order"]), list(range(n)))
                    done, width = set(), 0
                    for v in result["one_order"]:
                        self.assertTrue(not done or adjacency[v] & done)
                        done.add(v)
                        width = max(width, sum(bool(adjacency[u] - done) for u in done))
                    self.assertEqual(width, expected)
                    checked += 1
        self.assertEqual(checked, 167)

    def test_prefix_oracle_distinguishes_state_types(self):
        """Opposite ends of a partly exposed path may match or differ in color."""
        edges = [(0, 1), (1, 2), (2, 3), (3, 4)]
        self.assertEqual(brute_prefix_counts(5, edges, [2, 1, 3, 0, 4]),
                         [(1, 4, 1), (2, 12, 1), (2, 16, 2), (1, 4, 1), (0, 1, 1)])
        self.assertEqual(brute_prefix_counts(5, edges, [0, 1, 2, 3, 4]),
                         [(1, 4, 1)] * 4 + [(0, 1, 1)])


if __name__ == "__main__":
    unittest.main()

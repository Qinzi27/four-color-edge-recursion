"""Abstract research oracle tests, explicitly not geometric construction tests."""
import unittest
from scripts.search_construction_gap import reverse_chain, verify_chain


class ConstructionGapTests(unittest.TestCase):
    """Do not interchange a failed fixed coloring with all possible histories."""

    def test_four_cycle_fixed_state_obstruction_and_alternative(self):
        edges = ((0, 1), (0, 3), (1, 2), (2, 3))
        self.assertIsNone(reverse_chain(4, edges, (0, 1, 0, 1)))
        colors = (0, 1, 0, 2)
        chain = reverse_chain(4, edges, colors, True, True)
        self.assertIsNotNone(chain)
        verify_chain(4, edges, colors, chain)

    def test_octahedron_fixed_state_obstruction_and_alternative(self):
        edges = tuple((u, v) for u in range(6) for v in range(u+1, 6) if u//2 != v//2)
        self.assertIsNone(reverse_chain(6, edges, (0, 0, 1, 1, 2, 2)))
        colors = (0, 0, 1, 1, 2, 3)
        chain = reverse_chain(6, edges, colors, True, True)
        self.assertIsNotNone(chain)
        verify_chain(6, edges, colors, chain)

    def test_outer_side_is_not_absorbed(self):
        edges = ((0, 1), (0, 2), (1, 2))
        chain = reverse_chain(3, edges, (0, 1, 2), True, True)
        self.assertEqual(chain, ((1, 2),))
        verify_chain(3, edges, (0, 1, 2), chain)


if __name__ == '__main__':
    unittest.main()

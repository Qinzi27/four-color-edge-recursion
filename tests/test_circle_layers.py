"""Independently check fixed-layer completion, odd cuts and bounded feasibility."""

from copy import deepcopy
from itertools import combinations, product
import unittest

from fourcolor.circle_layers import (
    complete_second_layer, verify_second_layer_certificate,
)


def independent_even(vertices, edges, chosen):
    """Use integer degrees, rather than the producer's parity implementation."""
    degrees = dict.fromkeys(vertices, 0)
    for index in chosen:
        a, b = edges[index]
        degrees[a] += 1
        degrees[b] += 1
    return all(degree % 2 == 0 for degree in degrees.values())


def all_subsets(size):
    """Enumerate index subsets in a fixed order for the independent small oracle."""
    return [{index for index in range(size) if mask & (1 << index)}
            for mask in range(1 << size)]


class CircleLayerTests(unittest.TestCase):
    """No test imports or modifies a production map-naming solver."""

    def test_three_circles_with_all_three_links(self):
        """Each circle has two parallel arcs; the three blue links close a ring."""
        vertices = tuple(range(6))
        edges = ((0, 5), (0, 5), (1, 2), (1, 2), (3, 4), (3, 4),
                 (0, 1), (2, 3), (4, 5))
        first = tuple(range(6))
        result = complete_second_layer(vertices, edges, first)
        self.assertEqual(result["status"], "completed")
        self.assertTrue({6, 7, 8} <= set(result["second_layer"]))
        self.assertTrue(independent_even(vertices, edges, result["second_layer"]))
        self.assertEqual(set(first) | set(result["second_layer"]), set(range(9)))
        self.assertTrue(verify_second_layer_certificate(vertices, edges, first, result)["passed"])

    def test_fixed_triangle_on_k4_has_an_odd_cut(self):
        """A vertex outside A has three required edges, obstructing this A only."""
        vertices = tuple(range(4))
        edges = tuple(combinations(vertices, 2))
        first = (0, 1, 3)  # Triangle 0-1-2-0; vertex 3 is isolated in A.
        result = complete_second_layer(vertices, edges, first)
        self.assertEqual(result["status"], "obstructed")
        cut = result["obstruction"]
        self.assertEqual(len(cut["crossing_remaining_edges"]), 3)
        self.assertIn(cut["component_vertices"], ([0, 1, 2], [3]))
        self.assertTrue(verify_second_layer_certificate(vertices, edges, first, result)["passed"])

    def test_spanning_four_cycle_on_k4_can_be_completed(self):
        """The same graph permits two layers when the fixed first layer differs."""
        vertices = tuple(range(4))
        edges = tuple(combinations(vertices, 2))
        first = (0, 2, 3, 5)  # 0-1-2-3-0.
        result = complete_second_layer(vertices, edges, first)
        self.assertEqual(result["status"], "completed")
        self.assertTrue(independent_even(vertices, edges, result["second_layer"]))
        self.assertEqual(set(first) | set(result["second_layer"]), set(range(6)))

    def test_two_circles_with_three_radial_links_require_a_different_first_layer(self):
        """Two fixed ring boundaries each have an odd three-edge remaining cut.

        This triangular-prism graph still admits another pair of layers. The
        test distinguishes obstruction for the fixed A from global infeasibility.
        """
        vertices = tuple(range(6))
        edges = ((0, 1), (1, 2), (2, 0), (3, 4), (4, 5), (5, 3),
                 (0, 3), (1, 4), (2, 5))
        ring_boundaries = tuple(range(6))
        blocked = complete_second_layer(vertices, edges, ring_boundaries)
        self.assertEqual(blocked["status"], "obstructed")
        self.assertEqual(blocked["obstruction"]["crossing_remaining_edges"], [6, 7, 8])
        alternative = (0, 1, 8, 4, 3, 6)  # Spanning cycle 0-1-2-5-4-3-0.
        completed = complete_second_layer(vertices, edges, alternative)
        self.assertEqual(completed["status"], "completed")
        self.assertTrue(independent_even(vertices, edges, completed["second_layer"]))
        self.assertEqual(set(alternative) | set(completed["second_layer"]), set(range(9)))

        # Independent face graph: three annular sectors form a triangle. The
        # outside and inner island each meet all three sectors, but not each other.
        dual_edges = ((2, 3), (3, 4), (2, 4), (0, 2), (0, 3),
                      (0, 4), (1, 2), (1, 3), (1, 4))
        valid_counts = {}
        for palette in (3, 4):
            valid_counts[palette] = sum(
                all(colors[a] != colors[b] for a, b in dual_edges)
                for colors in product(range(palette), repeat=5))
        self.assertEqual(valid_counts, {3: 0, 4: 24})

    def test_loops_parallel_edges_disconnection_and_isolated_vertices(self):
        """Loops count twice; the forest ignores them without losing coverage."""
        vertices = (0, 1, 2, 3, 4)
        edges = ((0, 0), (0, 1), (0, 1), (1, 1), (3, 4), (3, 4))
        first = (0, 1, 2)
        result = complete_second_layer(vertices, edges, first)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["second_layer"], [3, 4, 5])
        self.assertTrue(independent_even(vertices, edges, result["second_layer"]))
        self.assertTrue(verify_second_layer_certificate(vertices, edges, first, result)["passed"])

    def test_empty_graph_and_even_graph_allow_an_empty_layer(self):
        """The algebra permits zero selected edges; no color-count claim is made."""
        for vertices in ((), (17, 25)):
            result = complete_second_layer(vertices, (), ())
            self.assertEqual(result["second_layer"], [])
        edges = ((1, 2), (1, 2), (2, 2))
        result = complete_second_layer((1, 2), edges, ())
        self.assertEqual(result["second_layer"], [0, 1, 2])
        self.assertTrue(independent_even((1, 2), edges, result["second_layer"]))

    def test_required_bridge_is_an_obstruction(self):
        """All input edges are required; plane callers must remove actual bridges."""
        result = complete_second_layer((0, 1), ((0, 1),), ())
        self.assertEqual(result["status"], "obstructed")
        self.assertEqual(result["obstruction"]["crossing_remaining_edges"], [0])

    def test_malformed_graphs_and_first_layers_are_rejected(self):
        """Reject duplicates, unknown endpoints, boolean IDs and non-even A."""
        invalid = (
            ((0, 0), (), ()),
            ((False,), (), ()),
            ((0,), ((0, 1),), ()),
            ((0,), ((0,),), ()),
            ((0,), ((0, 0, 0),), ()),
            ((0,), (None,), ()),
            ((0,), ((0, False),), ()),
            ((0,), ((0, 0),), (0, 0)),
            ((0,), ((0, 0),), (-1,)),
            ((0,), ((0, 0),), (1,)),
            ((0,), ((0, 0),), (False,)),
            ((0, 1), ((0, 1),), (0,)),
        )
        for vertices, edges, first in invalid:
            with self.subTest(vertices=vertices, edges=edges, first=first):
                with self.assertRaises(ValueError):
                    complete_second_layer(vertices, edges, first)

    def test_altered_success_certificates_are_rejected(self):
        """A valid-looking status cannot hide missing coverage or odd second degree."""
        vertices = tuple(range(4))
        edges = tuple(combinations(vertices, 2))
        first = (0, 2, 3, 5)
        good = complete_second_layer(vertices, edges, first)
        for field, replacement in (("second_layer", []),
                                    ("added_from_first_layer", []),
                                    ("remaining_edges", []),
                                    ("first_layer", []),
                                    ("first_layer", [False, 2, 3, 5]),
                                    ("remaining_edges", [True, 4]),
                                    ("second_layer", good["second_layer"] * 2),
                                    ("status", "obstructed")):
            changed = deepcopy(good)
            changed[field] = replacement
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    verify_second_layer_certificate(vertices, edges, first, changed)

    def test_altered_odd_cut_certificates_are_rejected(self):
        """Check exact cut IDs and entire components, not merely an odd count."""
        vertices = tuple(range(4))
        edges = tuple(combinations(vertices, 2))
        first = (0, 1, 3)
        good = complete_second_layer(vertices, edges, first)
        replacements = (("component_vertices", [0]),
                        ("component_vertices", [0, 1, 2, 3]),
                        ("component_vertices", [0, 0]),
                        ("crossing_remaining_edges", [0]),
                        ("crossing_remaining_edges", [2, 2, 4]),
                        ("kind", "unverified-claim"))
        for field, replacement in replacements:
            changed = deepcopy(good)
            changed["obstruction"][field] = replacement
            with self.subTest(field=field, replacement=replacement):
                with self.assertRaises(ValueError):
                    verify_second_layer_certificate(vertices, edges, first, changed)

    def test_every_simple_graph_through_four_vertices_against_all_second_layers(self):
        """For every even A, exhaust all B independently and compare feasibility.

        The bound is n <= 4, at most six edges and 2^6 edge subsets per graph.
        This finite oracle audits the implementation, not the general theorem.
        """
        graph_count = fixed_layer_count = candidate_count = 0
        for size in range(5):
            vertices = tuple(range(size))
            possible_edges = tuple(combinations(vertices, 2))
            for graph_ids in all_subsets(len(possible_edges)):
                edges = tuple(possible_edges[index] for index in sorted(graph_ids))
                graph_count += 1
                subsets = all_subsets(len(edges))
                even = {frozenset(chosen) for chosen in subsets
                        if independent_even(vertices, edges, chosen)}
                required = set(range(len(edges)))
                for first in subsets:
                    if frozenset(first) not in even:
                        continue
                    fixed_layer_count += 1
                    feasible_count = 0
                    for second in subsets:
                        candidate_count += 1
                        if frozenset(second) in even and first | second == required:
                            feasible_count += 1
                    result = complete_second_layer(vertices, edges, first)
                    with self.subTest(size=size, edges=edges, first=sorted(first)):
                        self.assertEqual(result["status"] == "completed", feasible_count > 0)
                        self.assertTrue(verify_second_layer_certificate(
                            vertices, edges, first, result)["passed"])
        self.assertEqual(graph_count, 76)
        self.assertGreater(fixed_layer_count, graph_count)
        self.assertGreater(candidate_count, fixed_layer_count)


if __name__ == "__main__":
    unittest.main()

"""Verify tiny line-side probability models with a face-based independent oracle.

The oracle deliberately uses PlaneMap faces and ordinary products instead of
the production auditor, orbit reduction, and log-space accumulator. It is only
used with small well-scaled fixtures; separate tests exercise underflow safety.
"""

from itertools import product
from math import exp, fsum, isfinite, log, prod
from random import Random
import unittest

from fourcolor.examples import dangling_triangle_map, tetrahedron_map, triangle_map
from fourcolor.probabilistic_names import infer_names


def face_oracle(plane_map, likelihoods, require_separator=True):
    """Enumerate existing face colors without consulting line-side inference."""
    palette_size = len(likelihoods[0])
    weighted = []
    for colors in product(range(palette_size), repeat=len(plane_map.faces)):
        if require_separator and any(left != right and colors[left] == colors[right]
                                     for left, right in (plane_map.shores(edge)
                                                         for edge in range(len(plane_map.edges)))):
            continue
        labels = tuple(colors[face] for face in plane_map.face_of_dart)
        weight = prod(row[label] for row, label in zip(likelihoods, labels))
        weighted.append((labels, weight))
    partition = fsum(weight for _, weight in weighted)
    marginals = tuple(tuple(fsum(weight for labels, weight in weighted if labels[dart] == label)
                            / partition for label in range(palette_size))
                      for dart in range(len(likelihoods)))
    best_labels, best_weight = max(weighted, key=lambda item: item[1])
    return marginals, best_labels, best_weight, log(partition)


def varied_likelihoods(dart_count, palette_size=4):
    """Deterministic positive, asymmetric evidence avoids accidental MAP ties."""
    rng = Random(941)
    return tuple(tuple(rng.uniform(0.05, 0.95) for _ in range(palette_size))
                 for _ in range(dart_count))


class ProbabilisticNameTests(unittest.TestCase):
    """Check model distinctions, bridge handling, and probability invariances."""

    def assert_marginals_close(self, actual, expected):
        """Check all labels, dimensions, and normalized probabilities."""
        self.assertEqual(len(actual), len(expected))
        for actual_row, expected_row in zip(actual, expected):
            self.assertEqual(len(actual_row), len(expected_row))
            self.assertAlmostEqual(fsum(actual_row), 1.0, places=11)
            for actual_value, expected_value in zip(actual_row, expected_row):
                self.assertAlmostEqual(actual_value, expected_value, places=11)

    def test_joint_and_orbit_match_independent_face_oracle(self):
        for builder in (triangle_map, dangling_triangle_map, tetrahedron_map):
            plane_map = builder()
            likelihoods = varied_likelihoods(2 * len(plane_map.edges))
            for mode in ("orbit", "joint"):
                with self.subTest(map=builder.__name__, mode=mode):
                    result = infer_names(tuple(plane_map.rotation.values()), likelihoods, mode)
                    expected = face_oracle(plane_map, likelihoods, mode == "joint")
                    self.assert_marginals_close(result.dart_marginals, expected[0])
                    self.assertEqual(result.map_labels, expected[1])
                    self.assertAlmostEqual(result.log_partition, expected[3])
                    self.assertEqual(result.side_orbits, plane_map.faces)
                    self.assertEqual(result.state_count, 4 ** len(plane_map.faces))

    def test_independent_ignores_symbol_constraints_but_checks_topology(self):
        plane_map = triangle_map()
        rows = ((0.9, 0.1),) * 6
        result = infer_names(tuple(plane_map.rotation.values()), rows, "independent", max_states=1)
        self.assertEqual(result.map_labels, (0,) * 6)
        self.assert_marginals_close(result.dart_marginals, rows)
        self.assertEqual(result.state_count, 2 ** 6)
        self.assertAlmostEqual(result.log_partition, 0.0)
        with self.assertRaises(ValueError):
            infer_names(((0,), (0,)), ((0.9, 0.1),) * 2, "independent")

    def test_bridge_combines_evidence_without_inequality(self):
        # The two darts observe the SAME side; demanding distinct labels fails.
        result = infer_names(((0,), (1,)), ((0.8, 0.2), (0.3, 0.7)))
        self.assert_marginals_close(result.dart_marginals, ((12 / 19, 7 / 19),) * 2)
        self.assertEqual(result.map_labels, (0, 0))
        self.assertAlmostEqual(exp(result.log_partition), 0.38)
        self.assertEqual(result.state_count, 2)

    def test_map_is_a_joint_configuration_even_when_marginals_tie(self):
        # Every dart has a uniform marginal, but taking every argmax as zero
        # would violate this loop separator. The complete MAP must differ.
        result = infer_names(((0, 1),), ((1, 1), (1, 1)))
        self.assert_marginals_close(result.dart_marginals, ((0.5, 0.5),) * 2)
        self.assertEqual(result.map_labels, (0, 1))

    def test_zero_likelihoods_and_impossible_palette(self):
        rows = ((1, 0), (1, 0))
        with self.assertRaisesRegex(ValueError, "no positive-weight"):
            infer_names(((0, 1),), rows)
        with self.assertRaisesRegex(ValueError, "no positive-weight"):
            infer_names(((0,), (1,)), ((1, 0), (0, 1)), "orbit")
        plane_map = tetrahedron_map()
        with self.assertRaisesRegex(ValueError, "no positive-weight"):
            infer_names(tuple(plane_map.rotation.values()), ((1, 1, 1),) * 12)

    def test_input_validation(self):
        invalid_rows = (
            (), ((1,), (1,)), ((1, 1),), ((1, 1), (1, 1, 1)),
            ((-1, 1), (1, 1)), ((float("nan"), 1), (1, 1)),
            ((float("inf"), 1), (1, 1)), ((0, 0), (1, 1)),
            ((None, 1), (1, 1)), (1, 2), ("11", "11"),
        )
        for rows in invalid_rows:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                infer_names(((0,), (1,)), rows)
        for cap in (0, -1, 1.5, True):
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                infer_names(((0,), (1,)), ((1, 1),) * 2, max_states=cap)
        with self.assertRaises(ValueError):
            infer_names(((0,), (1,)), ((1, 1),) * 2, mode="unknown")

    def test_state_cap_counts_raw_assignments_before_pruning(self):
        plane_map = tetrahedron_map()
        rotation = tuple(plane_map.rotation.values())
        rows = ((1, 1, 1, 1),) * 12
        with self.assertRaisesRegex(ValueError, "256 raw states"):
            infer_names(rotation, rows, max_states=255)
        self.assertEqual(infer_names(rotation, rows, max_states=256).state_count, 256)
        self.assertEqual(infer_names(rotation, rows, "orbit", max_states=1).state_count, 256)

    def test_log_space_prevents_product_underflow(self):
        rotation = tuple(triangle_map().rotation.values())
        rows = varied_likelihoods(6, 2)
        ordinary = infer_names(rotation, rows)
        tiny = infer_names(rotation, tuple(tuple(value * 1e-250 for value in row) for row in rows))
        self.assertTrue(isfinite(tiny.log_partition))
        self.assert_marginals_close(tiny.dart_marginals, ordinary.dart_marginals)
        self.assertAlmostEqual(tiny.log_partition - ordinary.log_partition, 6 * log(1e-250))
        self.assertEqual(tiny.map_labels, ordinary.map_labels)

    def test_direction_reversal_preserves_probabilities(self):
        plane_map = dangling_triangle_map()
        rows = varied_likelihoods(8)
        # Reverse the listed direction of edge 1 by relabeling its two darts.
        relabel = lambda dart: dart ^ 1 if dart // 2 == 1 else dart
        reversed_rotation = tuple(tuple(relabel(dart) for dart in turn)
                                  for turn in plane_map.rotation.values())
        reversed_rows = tuple(rows[relabel(dart)] for dart in range(8))
        for mode in ("independent", "orbit", "joint"):
            with self.subTest(mode=mode):
                original = infer_names(tuple(plane_map.rotation.values()), rows, mode)
                reversed_result = infer_names(reversed_rotation, reversed_rows, mode)
                self.assert_marginals_close(reversed_result.dart_marginals,
                                            tuple(original.dart_marginals[relabel(dart)] for dart in range(8)))
                self.assertEqual(reversed_result.map_labels,
                                 tuple(original.map_labels[relabel(dart)] for dart in range(8)))
                self.assertAlmostEqual(reversed_result.log_partition, original.log_partition)

    def test_symbol_permutation_preserves_probabilities(self):
        plane_map = tetrahedron_map()
        rows = varied_likelihoods(12)
        permutation = (2, 0, 3, 1)  # old label -> new label
        inverse = tuple(permutation.index(label) for label in range(4))
        permuted_rows = tuple(tuple(row[inverse[label]] for label in range(4)) for row in rows)
        for mode in ("independent", "orbit", "joint"):
            with self.subTest(mode=mode):
                original = infer_names(tuple(plane_map.rotation.values()), rows, mode)
                permuted = infer_names(tuple(plane_map.rotation.values()), permuted_rows, mode)
                expected = tuple(tuple(row[inverse[label]] for label in range(4))
                                 for row in original.dart_marginals)
                self.assert_marginals_close(permuted.dart_marginals, expected)
                self.assertEqual(permuted.map_labels, tuple(permutation[label] for label in original.map_labels))
                self.assertAlmostEqual(permuted.log_partition, original.log_partition)


if __name__ == "__main__":
    unittest.main()

"""Independent assignment oracles for the experimental joint-boundary filter."""

from copy import deepcopy
from itertools import combinations, permutations, product
from random import Random
from types import SimpleNamespace
import unittest

from fourcolor.joint_boundary import filter_boundary_books, find_boundary_books
from fourcolor.relation_names import relation_closure


PALETTE = (1, 2, 3, 4)
BOOK = {"internal": [0, 1], "boundary": [2, 3, 4]}
BOOK_EDGES = [(0, 1)] + [(core, shore) for core in (0, 1) for shore in (2, 3, 4)]


def mask_of(pairs):
    """Literal ordered-pair encoding, independent of producer helpers."""
    return sum(1 << (4 * (a - 1) + b - 1) for a, b in set(pairs))


def matrix_of(domains, edges=BOOK_EDGES):
    """Build only declared inequalities and diagonal unary constraints."""
    edges = {frozenset(edge) for edge in edges}
    return [[mask_of((a, b) for a in first for b in second
                     if (a == b if i == j else
                         a != b if frozenset((i, j)) in edges else True))
             for j, second in enumerate(domains)] for i, first in enumerate(domains)]


def assignments(matrix):
    """Enumerate all 4**n assignments, checking every directed input relation."""
    return [colors for colors in product(PALETTE, repeat=len(matrix))
            if all(matrix[i][j] & mask_of([(a, b)])
                   for i, a in enumerate(colors) for j, b in enumerate(colors))]


def oracle_matrix(solutions, n):
    """Collect exact unary and binary supports from independent full assignments."""
    return [[mask_of((colors[i], colors[j]) for colors in solutions)
             for j in range(n)] for i in range(n)]


def permute_matrix(matrix, permutation):
    """Rename both coordinates under one full palette permutation."""
    return [[mask_of((permutation[a - 1], permutation[b - 1])
                     for a, b in product(PALETTE, repeat=2)
                     if mask & mask_of([(a, b)]))
             for mask in row] for row in matrix]


class JointBoundaryTests(unittest.TestCase):
    """Separate true dual adjacency, unary cardinality and joint pair supports."""

    def assert_sound(self, before, result):
        """Every original full assignment must survive; conflict needs no solutions."""
        solutions = assignments(before)
        self.assertEqual(assignments(result["relations"]), solutions)
        if result["conflict"]:
            self.assertFalse(solutions)
        self.assertTrue(all(new & old == new for old_row, new_row in
                            zip(before, result["relations"]) for old, new in zip(old_row, new_row)))
        return solutions

    def test_unanchored_book_preserves_all_ninety_six_colorings(self):
        """A genuine three-way restriction need not shrink unanchored binary pairs."""
        matrix = matrix_of([PALETTE] * 5)
        before, books = deepcopy(matrix), deepcopy([BOOK])
        for mode in ("domains", "joint"):
            outcome = filter_boundary_books(matrix, books, mode=mode)
            self.assertFalse(outcome["changed"])
            self.assertFalse(outcome["conflict"])
            self.assertEqual(len(self.assert_sound(matrix, outcome)), 96)
            self.assertEqual(outcome["statistics"]["book_checks"], 1)
            self.assertEqual(outcome["statistics"]["conditional_cases"], 12 if mode == "joint" else 0)
        self.assertEqual(matrix, before)
        self.assertEqual(books, [BOOK])

    def test_one_anchor_reveals_pairs_missing_from_old_path_consistency(self):
        """In the actual planar book, z=3 forbids six x,y pairs but no unary value."""
        matrix = matrix_of([PALETTE, PALETTE, PALETTE, PALETTE, [3]])
        old = relation_closure(matrix)
        self.assertFalse(old["conflict"])
        self.assertEqual(old["relations"][2][3], 0xFFFF)
        plain = filter_boundary_books(old["relations"], [BOOK], mode="domains")
        self.assertFalse(plain["changed"])
        joint = filter_boundary_books(old["relations"], [BOOK])
        solutions = self.assert_sound(old["relations"], joint)
        self.assertEqual(len(solutions), 24)
        self.assertEqual(joint["relations"], oracle_matrix(solutions, 5))
        forbidden = mask_of((a, b) for a in (1, 2, 4) for b in (1, 2, 4) if a != b)
        self.assertEqual(joint["relations"][2][3], 0xFFFF ^ forbidden)
        self.assertEqual(joint["relations"][2][3].bit_count(), 10)
        self.assertEqual(joint["statistics"]["domain_values_removed"], 0)
        self.assertEqual(joint["statistics"]["relation_bits_removed"], 12)

    def test_auxiliary_correlations_enable_a_strict_unary_improvement(self):
        """Synthetic non-edge records are explicitly additional constraints."""
        matrix = matrix_of([PALETTE] * 5)
        extra = mask_of((a, b) for a, b in product(PALETTE, repeat=2)
                        if a != b or a == b == 1)
        for a, b in combinations((2, 3, 4), 2):
            matrix[a][b] = matrix[b][a] = extra
        self.assertEqual(relation_closure(matrix)["relations"], matrix)
        self.assertFalse(filter_boundary_books(matrix, [BOOK], mode="domains")["changed"])
        result = filter_boundary_books(matrix, [BOOK])
        solutions = self.assert_sound(matrix, result)
        self.assertIn((2, 3, 1, 1, 1), solutions)
        self.assertEqual(result["relations"], oracle_matrix(solutions, 5))
        for side in (0, 1):
            self.assertFalse(result["relations"][side][side] & mask_of([(1, 1)]))
        self.assertGreaterEqual(result["statistics"]["domain_values_removed"], 2)

    def test_global_palette_permutations_commute_with_joint_filtering(self):
        """No display color has a special mathematical role in the rule."""
        matrix = relation_closure(matrix_of([PALETTE] * 4 + [[3]]))["relations"]
        expected = filter_boundary_books(matrix, [BOOK])["relations"]
        for permutation in permutations(PALETTE):
            with self.subTest(permutation=permutation):
                renamed = filter_boundary_books(permute_matrix(matrix, permutation), [BOOK])
                self.assertEqual(renamed["relations"], permute_matrix(expected, permutation))

    def test_seeded_arbitrary_binary_constraints_preserve_all_completions(self):
        """48 small local inputs use independent exhaustive, not producer, oracles."""
        rng = Random(20260920)
        for index in range(48):
            domains = [rng.sample(PALETTE, rng.randrange(1, 5)) for _ in range(5)]
            matrix = matrix_of(domains)
            for a, b in combinations((2, 3, 4), 2):
                retained = [(x, y) for x in domains[a] for y in domains[b] if rng.random() < 0.7]
                matrix[a][b] = mask_of(retained)
                matrix[b][a] = mask_of((y, x) for x, y in retained)
            for mode in ("domains", "joint"):
                with self.subTest(case=index, mode=mode):
                    result = filter_boundary_books(matrix, [BOOK], mode=mode)
                    self.assert_sound(matrix, result)

    def test_unary_cardinality_filters_even_without_other_closure(self):
        """Two singleton boundary names reserve their two-color palette."""
        matrix = matrix_of([PALETTE, PALETTE, [1], [2], PALETTE])
        result = filter_boundary_books(matrix, [BOOK], mode="domains")
        self.assertEqual(result["relations"][4][4], mask_of([(1, 1), (2, 2)]))
        self.assertEqual(result["statistics"]["domain_values_removed"], 2)
        self.assertEqual(result["statistics"]["palette_checks"], 6)
        self.assert_sound(matrix, result)
        # Three distinct singleton names violate the necessary boundary bound.
        impossible = matrix_of([PALETTE, PALETTE, [1], [2], [3]])
        for mode in ("domains", "joint"):
            result = filter_boundary_books(impossible, [BOOK], mode=mode)
            self.assertTrue(result["conflict"])
            self.assertTrue(result["changed"])
            self.assert_sound(impossible, result)

    def test_branch_certificates_replay_and_join_without_hidden_assignments(self):
        """Recreate each local conditional input, then check the reported OR union."""
        original = relation_closure(matrix_of([PALETTE] * 4 + [[3]]))["relations"]
        result = filter_boundary_books(original, [BOOK])
        event = result["events"][0]
        self.assertEqual(event["input_relations"], original)
        union = [[0] * 5 for _ in range(5)]
        revisions = 0
        for branch in event["branches"]:
            candidate = deepcopy(event["input_relations"])
            first, second = branch["colors"]
            candidate[0][0] = mask_of([(first, first)])
            candidate[1][1] = mask_of([(second, second)])
            replay = relation_closure(candidate)
            self.assertEqual(branch["relations"], replay["relations"])
            self.assertEqual(branch["revisions"], replay["revisions"])
            self.assertEqual(branch["deletion_events"], len(replay["trace"]))
            self.assertEqual(branch["status"] == "conflict", replay["conflict"])
            revisions += replay["revisions"]
            if not replay["conflict"]:
                for i in range(5):
                    for j in range(5):
                        union[i][j] |= replay["relations"][i][j]
        self.assertEqual(union, result["relations"])
        self.assertEqual(revisions, result["statistics"]["local_revisions"])
        self.assertLessEqual(len(event["branches"]), 12)

    def test_overlapping_books_and_boundary_orders_preserve_global_solutions(self):
        """Sequential scans may share variables; no independence assumption is made."""
        edges = [(0, 1)] + [(core, shore) for core in (0, 1) for shore in range(2, 6)]
        matrix = matrix_of([PALETTE] * 5 + [[3]], edges)
        books = [{"internal": [1, 0], "boundary": [5, 3, 2]},
                 {"internal": [0, 1], "boundary": [2, 3, 4, 5]}]
        result = filter_boundary_books(matrix, books)
        self.assertEqual(result["statistics"]["book_checks"], 2)
        self.assert_sound(matrix, result)

    def test_extractor_preserves_parallel_witnesses_and_ignores_bridges(self):
        """A plane-map protocol stub isolates shore IDs from primal endpoint IDs."""
        shores = BOOK_EDGES + [(0, 1), (4, 4), (0, 0)]
        plane = SimpleNamespace(faces=[[] for _ in range(5)], edges=[None] * len(shores),
                                shores=lambda edge: shores[edge])
        model = SimpleNamespace(plane_map=plane)
        books = find_boundary_books(model)
        self.assertEqual(len(books), 1)
        self.assertEqual(books[0]["internal"], [0, 1])
        self.assertEqual(books[0]["boundary"], [2, 3, 4])
        witness = books[0]["edge_witnesses"]
        self.assertEqual(witness[0], {"sides": [0, 1], "raw_edge_ids": [0, 7]})
        self.assertEqual({edge for row in witness for edge in row["raw_edge_ids"]}, set(range(8)))
        for row in witness:
            self.assertTrue(all(sorted(shores[edge]) == row["sides"] for edge in row["raw_edge_ids"]))
        filter_boundary_books(matrix_of([PALETTE] * 5), books)
        self.assertEqual(books, find_boundary_books(model))

    def test_invalid_matrices_books_and_witness_caches_are_rejected(self):
        """A claimed boundary must never introduce a missing inequality silently."""
        for matrix in ([], [[]], [[1, 2]], [[True]], [[1.0]], [[-1]], [[65536]], [[2]]):
            with self.subTest(matrix=matrix), self.assertRaises(ValueError):
                filter_boundary_books(matrix, [])
        good = matrix_of([PALETTE] * 5)
        for book in ({}, {"internal": [0, 0], "boundary": [2, 3, 4]},
                     {"internal": [0, 1], "boundary": [2, 3]},
                     {"internal": [0, 1], "boundary": [2, 3, True]},
                     {"internal": [0, 1], "boundary": [2, 3, 5]},
                     {**BOOK, "extra": 1}, {**BOOK, "edge_witnesses": []}):
            with self.subTest(book=book), self.assertRaises(ValueError):
                filter_boundary_books(good, [book])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            filter_boundary_books(good, [BOOK, BOOK])
        with self.assertRaisesRegex(ValueError, "unequal"):
            filter_boundary_books(matrix_of([PALETTE] * 5, edges=BOOK_EDGES[1:]), [BOOK])
        with self.assertRaisesRegex(ValueError, "mode"):
            filter_boundary_books(good, [BOOK], mode="secret-search")
        asymmetric = deepcopy(good)
        asymmetric[0][1] &= ~mask_of([(1, 2)])
        with self.assertRaisesRegex(ValueError, "transposes"):
            filter_boundary_books(asymmetric, [BOOK])
        for books in (None, {}, [None]):
            with self.assertRaises(ValueError):
                filter_boundary_books(good, books)

    def test_empty_constraints_are_reported_without_disguised_filter_progress(self):
        """A pre-existing empty relation is a conflict, not a newly proved deletion."""
        result = filter_boundary_books([[0]], [])
        self.assertTrue(result["conflict"])
        self.assertFalse(result["changed"])
        self.assertEqual(result["relations"], [[0]])
        self.assertEqual(result["events"], [])
        self.assertEqual(result["statistics"]["book_checks"], 0)
        result = filter_boundary_books([[0x8421]], [])
        self.assertFalse(result["conflict"])
        self.assertFalse(result["changed"])


if __name__ == "__main__":
    unittest.main()

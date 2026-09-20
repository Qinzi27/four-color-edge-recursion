"""Check certified reuse independently of scheduling and chosen color names."""

from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import call, patch

from fourcolor.implicit_inequality import (
    certify_implicit_inequality, verify_implicit_inequality,
)
from fourcolor.prior_rule_reuse import (
    UNEQUAL_MASK, certified_pair_relations, intersect_certified_relations,
)
from fourcolor.relation_names import transpose
from scripts.validate_frontier_restart import read_json
from scripts.validate_global_restart import export_geometries


def unconstrained_matrix(n):
    """Supply four names at each face and no restriction between distinct faces."""
    return [[0x8421 if i == j else 65535 for j in range(n)] for i in range(n)]


def premise_matrix(n, certificate):
    """Include the actual inequality premises before applying their conclusion."""
    matrix = unconstrained_matrix(n)
    for witness in certificate["required_adjacencies"]:
        a, b = witness["sides"]
        matrix[a][b] = matrix[b][a] = UNEQUAL_MASK
    return matrix


class PriorRuleReuseTests(unittest.TestCase):
    """Archived geometry authenticates the proof; literal edges check soundness."""

    @classmethod
    def setUpClass(cls):
        """Read an uncolored drawing, independently of its failed solver trace."""
        root = Path(__file__).resolve().parents[1]
        source = read_json(root / "outputs/staged-levels-full-2026-09-19.json.gz")
        key = "66b1a56305161b76660d5d2567a7f9720ecde941c8df98f922e594da95d898ed"
        row = next(row for row in source["drawings"] if row["key"] == key)
        cls.geometry = export_geometries([row])[0]["geometry"]
        cls.mapping = {"O": 0, "A": 1, "B": 4, "p": 2, "q": 3,
                       "r": 14, "s": 15, "t": 10, "u": 19}
        cls.certificate = certify_implicit_inequality(cls.geometry, cls.mapping)
        cls.n = len(cls.geometry["faces"])

    def test_automatic_search_is_geometric_verified_and_deterministic(self):
        """Every emitted proof is unique per target and uses no existing edge."""
        before = deepcopy(self.geometry)
        certificates = certified_pair_relations(self.geometry)
        self.assertEqual(certificates, certified_pair_relations(self.geometry))
        self.assertEqual(self.geometry, before)
        targets = [tuple(sorted(c["conclusion"]["sides"])) for c in certificates]
        self.assertEqual(targets, sorted(set(targets)))
        self.assertIn((1, 4), targets)
        real_edges = {tuple(sorted(self.geometry["faceOfDart"][2 * i:2 * i + 2]))
                      for i in range(len(self.geometry["edges"]))}
        for certificate, target in zip(certificates, targets):
            self.assertNotIn(target, real_edges)
            self.assertTrue(verify_implicit_inequality(self.geometry, certificate)["passed"])

    def test_search_tries_reverse_only_after_no_match_and_skips_real_edges(self):
        """An asymmetric matcher must not silently omit reverse template matches."""
        proof_02, proof_12 = {"target": [2, 0]}, {"target": [1, 2]}
        answers = {(2, 0): proof_02, (1, 2): proof_12}
        with patch("fourcolor.prior_rule_reuse._adjacency",
                   return_value=([{1}, {0}, set()], {})), \
                patch("fourcolor.prior_rule_reuse.find_implicit_inequality",
                      side_effect=lambda geometry, a, b: answers.get((a, b))) as finder, \
                patch("fourcolor.prior_rule_reuse.verify_implicit_inequality") as verifier:
            self.assertEqual(certified_pair_relations({}), [proof_02, proof_12])
        self.assertEqual(finder.call_args_list, [call({}, 0, 2), call({}, 2, 0), call({}, 1, 2)])
        self.assertEqual(verifier.call_args_list, [call({}, proof_02), call({}, proof_12)])

    def test_all_312_valid_template_assignments_survive_intersection(self):
        """Independent edge-pruned enumeration checks every valid template coloring.

        The literal nineteen edges are intentionally not imported from the
        certificate producer.  Partial-edge pruning only avoids enumerating
        already-invalid prefixes; all valid four-name assignments are visited.
        """
        edges = ((0, 1), (0, 2), (0, 3), (1, 3), (0, 4), (2, 4), (3, 4),
                 (5, 3), (5, 4), (5, 1), (6, 5), (6, 1), (7, 0), (7, 2),
                 (7, 6), (8, 2), (8, 5), (8, 6), (8, 7))
        previous = [set() for _ in range(9)]
        for a, b in edges:
            previous[max(a, b)].add(min(a, b))
        matrix = premise_matrix(self.n, self.certificate)
        original_matrix, original_proof = deepcopy(matrix), deepcopy(self.certificate)
        result = intersect_certified_relations(matrix, [self.certificate])
        count = 0

        def visit(colors):
            """Enumerate proper prefixes and validate the emitted binary restriction."""
            nonlocal count
            i = len(colors)
            if i == 9:
                count += 1
                bit = 1 << (4 * colors[1] + colors[2])
                self.assertTrue(result["relations"][1][4] & bit)
                self.assertNotEqual(colors[1], colors[2])
                return
            for color in range(4):
                if all(colors[j] != color for j in previous[i]):
                    visit(colors + [color])

        visit([])
        self.assertEqual(count, 312)
        self.assertEqual(matrix, original_matrix)
        self.assertEqual(self.certificate, original_proof)
        self.assertTrue(result["changed"])
        self.assertFalse(result["conflict"])
        self.assertEqual(result["relations"][1][4], UNEQUAL_MASK)
        self.assertEqual(result["relations"][4][1], transpose(UNEQUAL_MASK))
        self.assertEqual(result["trace"], [{"certificate_index": 0, "sides": [1, 4],
                         "kind": "derived-name-relation-not-geometric-edge", "relation": "!=",
                         "before": 65535, "after": UNEQUAL_MASK, "removed": 0x8421}])
        for i in range(self.n):
            for j in range(self.n):
                if (i, j) not in ((1, 4), (4, 1)):
                    self.assertEqual(result["relations"][i][j], matrix[i][j])

    def test_intersection_is_idempotent_and_preserves_existing_bans(self):
        """Reusing a certificate cannot reintroduce pairs removed by another filter."""
        matrix = premise_matrix(self.n, self.certificate)
        matrix[1][4] &= ~(1 << 1)
        matrix[4][1] = transpose(matrix[1][4])
        once = intersect_certified_relations(matrix, [self.certificate, self.certificate])
        self.assertEqual(len(once["trace"]), 1)
        self.assertFalse(once["relations"][1][4] & (1 << 1))
        twice = intersect_certified_relations(once["relations"], [self.certificate])
        self.assertEqual(twice["relations"], once["relations"])
        self.assertFalse(twice["changed"])
        self.assertEqual(twice["trace"], [])

    def test_conflict_is_reported_without_committing_a_color(self):
        """Equality-only target domains contradict a verified unequal-name relation."""
        matrix = premise_matrix(self.n, self.certificate)
        matrix[1][4] = matrix[4][1] = 0x8421
        result = intersect_certified_relations(matrix, [self.certificate])
        self.assertEqual(result["relations"][1][4], 0)
        self.assertEqual(result["relations"][4][1], 0)
        self.assertTrue(result["conflict"])
        self.assertTrue(result["changed"])
        matrix[2][3] = matrix[3][2] = 0
        empty_batch = intersect_certified_relations(matrix, [])
        self.assertTrue(empty_batch["conflict"])
        self.assertFalse(empty_batch["changed"])

    def test_invalid_matrices_are_rejected(self):
        """Malformed masks, diagonal entries and reverse relations are not trusted."""
        for matrix in (None, [], [[1, 2]], [[True]], [[65536]], [[-1]], [[2]],
                       [[1, 2], [2, 1]], [[1], 0]):
            with self.subTest(matrix=matrix), self.assertRaises(ValueError):
                intersect_certified_relations(matrix, [])

    def test_certificate_cannot_strengthen_a_matrix_missing_its_premises(self):
        """A genuine geometric certificate must not be applied to an unrelated CSP."""
        matrix = premise_matrix(self.n, self.certificate)
        a, b = self.certificate["required_adjacencies"][0]["sides"]
        matrix[a][b] = matrix[b][a] = 65535
        with self.assertRaisesRegex(ValueError, "inequality premise is missing"):
            intersect_certified_relations(matrix, [self.certificate])
        with self.assertRaisesRegex(ValueError, "inequality premise is missing"):
            intersect_certified_relations(unconstrained_matrix(self.n), [self.certificate])

    def test_malformed_certificates_are_rejected_before_any_result(self):
        """Shape validation rejects changed targets and malformed edge evidence."""
        malformed = [None, {}, {**self.certificate, "palette_size": True},
                     {**self.certificate, "kind": "unknown"},
                     {**self.certificate, "mapping": {}},
                     {**self.certificate, "required_adjacencies": []},
                     {**self.certificate, "extra": "unreviewed"}]
        for change in ("target", "range", "repeat", "witness", "raw_ids"):
            proof = deepcopy(self.certificate)
            if change == "target":
                proof["conclusion"]["sides"] = [1, 5]
            elif change == "range":
                proof["mapping"]["u"] = self.n
            elif change == "repeat":
                proof["mapping"]["u"] = proof["mapping"]["s"]
            elif change == "witness":
                proof["required_adjacencies"][0]["sides"] = [0, 4]
            else:
                proof["required_adjacencies"][0]["raw_edge_ids"] = [True]
            malformed.append(proof)
        for proof in malformed:
            with self.subTest(proof=proof), self.assertRaises(ValueError):
                intersect_certified_relations(premise_matrix(self.n, self.certificate),
                                              [self.certificate, proof])
        with self.assertRaises(ValueError):
            intersect_certified_relations(unconstrained_matrix(self.n), None)

    def test_geometry_mismatch_is_rejected_before_search(self):
        """The matcher cannot authenticate inconsistent face/dart identities."""
        geometry = deepcopy(self.geometry)
        geometry["faceOfDart"][0] = (geometry["faceOfDart"][0] + 1) % self.n
        with self.assertRaisesRegex(ValueError, "side/dart identities"):
            certified_pair_relations(geometry)


if __name__ == "__main__":
    unittest.main()

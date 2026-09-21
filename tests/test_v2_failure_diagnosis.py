"""Reject broken premises and altered conclusions in the fixed v2 diagnosis."""

import unittest

from scripts.diagnose_v2_failure_20260921 import (
    contraction_certificate, verify_certificate,
)


class V2FailureCertificateTests(unittest.TestCase):
    """Use explicit original-side edges, independent of archived color names."""

    def setUp(self):
        """Retain the actual geometric graph's needed sixteen-side subgraph."""
        adjacent = {
            0: (1, 2, 3, 7, 8, 9, 10, 11, 12),
            1: (2, 12, 13, 17), 2: (3, 17), 3: (17, 18),
            7: (8, 16, 18), 8: (9, 16), 9: (10, 16),
            10: (11, 14, 15, 16), 11: (12, 14), 12: (13, 14, 15),
            13: (15, 16, 17, 18), 14: (15,), 15: (16,),
            16: (18,), 17: (18,),
        }
        self.edges = {(a, b) for a, values in adjacent.items() for b in values}

    def test_four_merges_yield_five_mutually_adjacent_classes(self):
        """The given real-edge pattern proves the nonadjacent tips different."""
        proof = contraction_certificate(self.edges)
        result = verify_certificate(self.edges, proof)
        self.assertEqual(result["forced_equality_steps"], 4)
        self.assertEqual(result["used_sides"], 16)
        self.assertEqual(proof["contradiction"]["classes"],
                         [[0, 13, 14], [1, 3, 8, 10], [7], [16], [18]])
        self.assertNotIn((1, 10), self.edges)

    def test_remove_required_triangle_edge_is_rejected(self):
        """Two common tips require a complete triangle, not just a path."""
        with self.assertRaises(ValueError):
            contraction_certificate(self.edges - {(11, 12)})

    def test_remove_terminal_clique_edge_is_rejected(self):
        """A four-clique plus one partial neighbor is not a contradiction."""
        with self.assertRaises(ValueError):
            contraction_certificate(self.edges - {(7, 18)})

    def test_tampered_conclusion_is_rejected(self):
        """The checked implication cannot be relabelled to another side pair."""
        proof = contraction_certificate(self.edges)
        proof["conclusion"]["sides"] = [1, 9]
        with self.assertRaises(ValueError):
            verify_certificate(self.edges, proof)

    def test_tampered_merge_is_rejected(self):
        """No unproved side may be inserted into an equality class."""
        proof = contraction_certificate(self.edges)
        proof["steps"][0]["merged_class"].append(18)
        with self.assertRaises(ValueError):
            verify_certificate(self.edges, proof)


if __name__ == "__main__":
    unittest.main()

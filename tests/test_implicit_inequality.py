"""Validate the fixed nine-side implication separately from any naming solver."""

from copy import deepcopy
from itertools import product
from pathlib import Path
import unittest

from fourcolor.implicit_inequality import (
    certify_implicit_inequality, find_implicit_inequality, verify_implicit_inequality,
)
from scripts.validate_frontier_restart import read_json
from scripts.validate_global_restart import export_geometries


class ImplicitInequalityTests(unittest.TestCase):
    """The proof's finite graph and geometry certificate have independent checks."""

    @classmethod
    def setUpClass(cls):
        """Reconstruct one archived map from its uncolored document, not v4 output."""
        root = Path(__file__).resolve().parents[1]
        source = read_json(root / "outputs/staged-levels-full-2026-09-19.json.gz")
        key = "66b1a56305161b76660d5d2567a7f9720ecde941c8df98f922e594da95d898ed"
        row = next(row for row in source["drawings"] if row["key"] == key)
        cls.geometry = export_geometries([row])[0]["geometry"]
        cls.mapping = {"O": 0, "A": 1, "B": 4, "p": 2, "q": 3, "r": 14, "s": 15, "t": 10, "u": 19}

    def test_all_four_to_the_nine_assignments_obey_the_implication(self):
        """An independent literal graph checks all 262144 name assignments.

        This finite enumeration validates this FIXED lemma only. It is not
        imported into or used to repair the production map-naming algorithm.
        """
        # Independent order: O,A,B,p,q,r,s,t,u. Do not import the producer's
        # edge list, so an accidental missing production edge cannot hide here.
        edges = ((0, 1), (0, 2), (0, 3), (1, 3), (0, 4), (2, 4), (3, 4),
                 (5, 3), (5, 4), (5, 1), (6, 5), (6, 1), (7, 0), (7, 2),
                 (7, 6), (8, 2), (8, 5), (8, 6), (8, 7))
        checked, valid = 0, 0
        for colors in product(range(1, 5), repeat=9):
            checked += 1
            if all(colors[a] != colors[b] for a, b in edges):
                valid += 1
                self.assertNotEqual(colors[1], colors[2])
        self.assertEqual(checked, 4 ** 9)
        self.assertGreater(valid, 0, "implication must not be a vacuous impossible-template artifact")

    def test_given_and_automatically_matched_certificate_are_valid(self):
        """All nineteen required relations have explicit raw-boundary edge IDs."""
        given = certify_implicit_inequality(self.geometry, self.mapping)
        self.assertTrue(verify_implicit_inequality(self.geometry, given)["passed"])
        self.assertEqual(len(given["required_adjacencies"]), 19)
        found = find_implicit_inequality(self.geometry, 1, 4)
        self.assertIsNotNone(found)
        self.assertTrue(verify_implicit_inequality(self.geometry, found)["passed"])
        self.assertEqual(found["conclusion"]["sides"], [1, 4])
        self.assertEqual(found["conclusion"]["kind"], "derived-name-relation-not-geometric-edge")
        self.assertEqual(found, find_implicit_inequality(self.geometry, 1, 4))

    def test_repeated_side_and_false_adjacency_mapping_are_rejected(self):
        """A template cannot reuse a side to evade a required inequality."""
        repeated = {**self.mapping, "u": self.mapping["s"]}
        with self.assertRaisesRegex(ValueError, "distinct"):
            certify_implicit_inequality(self.geometry, repeated)
        false_mapping = {**self.mapping, "u": 8}
        with self.assertRaisesRegex(ValueError, "missing required adjacency"):
            certify_implicit_inequality(self.geometry, false_mapping)

    def test_forged_edge_ids_and_changed_conclusion_are_rejected(self):
        """A plausible mapped pattern does not authenticate an altered certificate."""
        certificate = certify_implicit_inequality(self.geometry, self.mapping)
        for corruption in ("edge", "conclusion", "palette"):
            with self.subTest(corruption=corruption):
                changed = deepcopy(certificate)
                if corruption == "edge":
                    changed["required_adjacencies"][0]["raw_edge_ids"] = [999999]
                elif corruption == "conclusion":
                    changed["conclusion"]["sides"] = [1, 5]
                else:
                    changed["palette_size"] = 5
                with self.assertRaisesRegex(ValueError, "certificate differs"):
                    verify_implicit_inequality(self.geometry, changed)

    def test_invalid_target_side_pairs_are_rejected(self):
        """Boolean, out-of-range and identical identities are not valid targets."""
        for pair in ((1, 1), (-1, 4), (True, 4), (1, 999999)):
            with self.subTest(pair=pair), self.assertRaisesRegex(ValueError, "invalid target"):
                find_implicit_inequality(self.geometry, *pair)


if __name__ == "__main__":
    unittest.main()

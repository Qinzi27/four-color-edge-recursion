"""Check independent bare-graph enumeration and rejection of false evidence."""

import unittest
from unittest.mock import patch

from scripts.audit_bare_bipyramid import (
    audit_bare_bipyramid, bare_document, literal_solutions,
)


class BareBipyramidTests(unittest.TestCase):
    """Keep the partial-commitment audit separate from geometric reachability."""

    def test_literal_solution_characterization(self):
        """The opposite apices share the unique color absent from the triangle."""
        solutions = literal_solutions()
        self.assertEqual(len(solutions), 24)
        for a, b, c, d, e in solutions:
            self.assertEqual(a, e)
            self.assertEqual(len({a, b, c, d}), 4)

    def test_document_has_no_external_domains(self):
        """Only actual singleton commitments constrain this audit population."""
        document = bare_document((1, 0, 0, 0, 0))
        self.assertEqual(document["anchors"], {"A": 1})
        self.assertEqual(document["states"], {})
        self.assertEqual(len(document["lines"]), 9)
        with self.assertRaises(ValueError):
            bare_document((True, 0, 0, 0, 0))

    def test_all_partial_commitments_and_literal_trials(self):
        """Every surviving bare-graph trial has an independent full extension."""
        report = audit_bare_bipyramid(max_examples=1)
        counts = report["counts"]
        self.assertEqual(counts["partial_commitments_enumerated"], 3125)
        self.assertEqual(counts["extendible_partial_commitments"], 481)
        self.assertEqual(counts["unresolved_candidate_trials"], 952)
        self.assertEqual(counts["nonextendible_unresolved_candidate_trials"], 24)
        self.assertEqual(counts["trial_conflicts"], counts["nonextendible_trials"])
        self.assertEqual(counts["trial_survivors"], counts["extendible_trials"])
        self.assertEqual(len(report["refuted_candidate_examples"]), 1)
        self.assertFalse(report["geometry_or_mother_schedule_checked"])

    def test_false_propagation_conflict_is_rejected(self):
        """An independently extendible input must not pass a lying producer."""
        with patch("scripts.audit_bare_bipyramid.propagate_contacts",
                   return_value={"status": "conflict"}):
            with self.assertRaisesRegex(AssertionError, "extendible initial state"):
                audit_bare_bipyramid()


if __name__ == "__main__":
    unittest.main()

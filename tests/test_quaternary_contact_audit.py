"""Reject prematurely fixed representatives and lost contact possibilities."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from scripts.quaternary_contact_model import propagate_contacts
from scripts.validate_quaternary_contacts import audit_document, build_inventory, document_for


class QuaternaryContactAuditTests(unittest.TestCase):
    """Use literal complete assignments, not the producer's display, as evidence."""

    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "examples/quaternary-contact-prototype-2026-09-21.json"
        cls.examples = json.loads(path.read_text(encoding="utf-8"))["cases"]
        cls.document = cls.examples[1]["document"]
        cls.result = propagate_contacts(cls.document)

    def test_same_display_keeps_six_real_contact_options(self):
        audit = audit_document(self.document, self.result)
        self.assertEqual(audit["legal_assignments"], 6)
        self.assertEqual(audit["status"], "underdetermined")
        self.assertFalse(audit["representatives_are_complete_assignment"])

    def test_display_minimum_cannot_be_reported_as_a_fixed_domain(self):
        wrong = deepcopy(self.result)
        wrong["name_states"]["A"]["candidates"] = [2]
        wrong["name_states"]["A"]["quaternary"] = "0300"
        wrong["name_states"]["A"]["code"] = int("0300", 4)
        with self.assertRaises(AssertionError):
            audit_document(self.document, wrong)

    def test_missing_legal_ordered_pair_is_rejected(self):
        wrong = deepcopy(self.result)
        wrong["relations"][1][2] &= ~(1 << (4 * (3 - 1) + (2 - 1)))
        with self.assertRaises(AssertionError):
            audit_document(self.document, wrong)

    def test_wrong_line_encoding_or_representative_coloring_is_rejected(self):
        for change in ("line", "colors"):
            wrong = deepcopy(self.result)
            if change == "line":
                wrong["lines"][0]["relation_code"] = "00000000"
            else:
                wrong["colors"] = {"I": 1, "A": 2, "B": 2}
            with self.subTest(change=change), self.assertRaises(AssertionError):
                audit_document(self.document, wrong)

    def test_all_declared_local_examples_are_independently_checked(self):
        for example in self.examples:
            with self.subTest(example=example["id"]):
                self.assertTrue(audit_document(example["document"], propagate_contacts(example["document"]))["passed"])

    def test_exhaustive_recipes_have_complete_cartesian_counts(self):
        records = build_inventory()
        self.assertEqual(sum(r["family"] == "simple" for r in records), 41055)
        self.assertEqual(sum(r["family"] == "domain-pair" for r in records), 768)
        self.assertEqual(sum(r["family"] == "bridge" for r in records), 16)
        self.assertEqual(len(records), 41847)
        self.assertEqual(document_for(records[0])["anchors"], {})


if __name__ == "__main__":
    unittest.main()

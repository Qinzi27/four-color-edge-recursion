"""The wheel wrapper must retain the frozen binary proof and its premises."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts.quaternary_logical_neq_contacts import propagate_logical_contacts
from scripts.quaternary_odd_wheel_contacts import MODEL, propagate_wheel_contacts
from tests.test_quaternary_odd_wheel import wheel_document


class OddWheelContactTests(unittest.TestCase):
    """Independent trace replay is provided by the separate wheel auditor."""

    def test_conflict_does_not_fabricate_empty_binary_domains_or_relations(self):
        raw = wheel_document(states={side: "0111" for side in wheel_document()["sides"]})
        old = propagate_logical_contacts(raw)
        self.assertEqual(old["status"], "underdetermined")
        new = propagate_wheel_contacts(raw)
        self.assertEqual(new["model"], MODEL)
        self.assertEqual(new["base_status"], "underdetermined")
        self.assertEqual(new["status"], "conflict")
        self.assertIsNotNone(new["wheel_check"]["certificate"])
        self.assertTrue(all(new["domains"]))
        restored = deepcopy(new)
        restored.pop("base_status")
        restored.pop("wheel_check")
        restored["model"], restored["status"] = old["model"], old["status"]
        self.assertEqual(restored, old)

    def test_four_color_wheel_and_even_three_color_wheel_keep_base(self):
        for raw in (wheel_document(), wheel_document(4, states={side: "0111" for side in wheel_document(4)["sides"]})):
            old, new = propagate_logical_contacts(raw), propagate_wheel_contacts(raw)
            self.assertEqual(new["status"], old["status"])
            self.assertIsNone(new["wheel_check"]["certificate"])
            self.assertEqual(new["relations"], old["relations"])
            self.assertEqual(new["domains"], old["domains"])

    def test_terminal_base_states_skip_detection(self):
        for raw in ({"sides": ["A"], "lines": [], "anchors": {"A": 1}},
                    {"sides": ["A"], "lines": [], "states": {"A": "0000"}}):
            with patch("scripts.quaternary_odd_wheel_contacts.find_odd_wheel",
                       side_effect=AssertionError("terminal base need not be scanned")):
                result = propagate_wheel_contacts(raw)
            self.assertIsNone(result["wheel_check"])
            self.assertEqual(result["status"], result["base_status"])

    def test_old_propagator_is_called_once_and_output_does_not_alias_it(self):
        raw = wheel_document()
        base = propagate_logical_contacts(raw)
        with patch("scripts.quaternary_odd_wheel_contacts.propagate_logical_contacts", return_value=base) as old:
            outcome = propagate_wheel_contacts(raw)
        old.assert_called_once_with(raw)
        outcome["domains"][0].clear()
        outcome["original_input"]["lines"].clear()
        self.assertEqual(base["domains"][0], [1, 2, 3, 4])
        self.assertEqual(raw, wheel_document())

    def test_logical_only_wheel_is_not_a_physical_certificate(self):
        raw = wheel_document(states={side: "0111" for side in wheel_document()["sides"]})
        raw["different_names"] = [[line["left"], line["right"]] for line in raw["lines"]]
        raw["lines"] = []
        result = propagate_wheel_contacts(raw)
        self.assertEqual(result["status"], "underdetermined")
        self.assertIsNone(result["wheel_check"]["certificate"])

    def test_malformed_input_is_rejected_before_a_wheel_scan(self):
        raw = wheel_document(anchors={"C": True})
        with self.assertRaises(ValueError):
            propagate_wheel_contacts(raw)


if __name__ == "__main__":
    unittest.main()

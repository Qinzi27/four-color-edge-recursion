"""Round chaining, local-premise lifetime and projection controls for EQ closure."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts.quaternary_conditional_diamond_contacts import (
    MODEL, VERSION, propagate_diamond_contacts,
)
from scripts.quaternary_contact_model import NameState
from scripts.quaternary_odd_wheel_contacts import propagate_wheel_contacts
from tests.test_quaternary_conditional_diamond import diamond_document


def chain_document():
    """Two synthetic diamonds; learning the first removes W=1 for the second.

    If W=1, then X=2, Y=3 and Z=4, forcing U and V to different colors.
    The first certified U=V instead excludes W=1 by binary closure. This
    activates the second diamond, which could not use a common palette in
    the first round. This is a declared-domain unit fixture, not a claim of
    actual reachability from the full raw-policy initialization.
    """
    raw = diamond_document()
    raw["sides"] += ["W", "X", "Y", "Z", "T", "M", "N"]
    edges = [("W", "X"), ("W", "Y"), ("W", "Z"), ("U", "X"), ("V", "Y"), ("V", "Z"),
             ("W", "M"), ("W", "N"), ("T", "M"), ("T", "N"), ("M", "N")]
    raw["lines"] += [{"id": f"added{i}", "left": a, "right": b, "kind": "separator"}
                     for i, (a, b) in enumerate(edges)]
    domains = {s: [2, 3, 4] for s in ["U", "V", "A", "B", "T", "M", "N"]}
    domains.update(W=[1, 2, 3, 4], X=[1, 2], Y=[1, 3], Z=[1, 4])
    raw["states"] = {side: NameState.from_candidates(domain).to_quaternary()
                     for side, domain in domains.items()}
    return raw


def diamond_trial_document():
    """A conditional rejection fixture for the INNER loop with declared NEQ."""
    raw = diamond_document(states={side: "0111" for side in ["U", "V", "A"]},
                           different_names=[["U", "V"]])
    raw["sides"] = ["P"] + raw["sides"]
    raw["lines"].append({"id": "pb", "left": "P", "right": "B", "kind": "separator"})
    return raw


class ConditionalDiamondContactTests(unittest.TestCase):
    """The evidence must retain every round rather than flattening its premise chain."""

    def test_single_batch_is_appended_locally_and_replayed_to_fixed_point(self):
        raw = diamond_document(states={side: "0111" for side in ["U", "V", "A", "B"]})
        before = deepcopy(raw)
        result = propagate_diamond_contacts(raw)
        self.assertEqual(result["model"], MODEL)
        self.assertEqual(result["conditional_eq"]["version"], VERSION)
        self.assertEqual(result["conditional_eq"]["equal_names"], [["U", "V"]])
        rounds = result["conditional_eq"]["rounds"]
        self.assertEqual(len(rounds), 2)
        self.assertEqual(rounds[0]["document"], raw)
        self.assertEqual(rounds[1]["document"], {**raw, "equal_names": [["U", "V"]]})
        self.assertEqual(rounds[1]["diamond_check"]["certificates"], [])
        self.assertEqual(raw, before)

    def test_three_round_chain_uses_new_auditable_domains_for_second_certificate(self):
        raw = chain_document()
        result = propagate_diamond_contacts(raw)
        rounds = result["conditional_eq"]["rounds"]
        self.assertEqual(len(rounds), 3)
        self.assertEqual(result["conditional_eq"]["equal_names"], [["U", "V"], ["W", "T"]])
        self.assertEqual(rounds[0]["outcome"]["domains"][4], [1, 2, 3, 4])
        self.assertEqual(rounds[1]["outcome"]["domains"][4], [2, 3, 4])
        self.assertEqual(rounds[0]["diamond_check"]["certificates"][0]["pair"], ["U", "V"])
        self.assertEqual(rounds[1]["diamond_check"]["certificates"][0]["pair"], ["W", "T"])
        self.assertEqual(rounds[2]["diamond_check"]["certificates"], [])
        for row in rounds:
            self.assertEqual(row["document"]["states"], raw["states"])
            self.assertEqual(row["document"]["lines"], raw["lines"])
            self.assertEqual(row["outcome"], propagate_wheel_contacts(row["document"]))

    def test_top_projection_is_exact_final_wheel_outcome_except_explicit_additions(self):
        raw = chain_document()
        result = propagate_diamond_contacts(raw)
        rounds = result["conditional_eq"]["rounds"]
        restored = deepcopy(result)
        restored.pop("conditional_eq")
        restored["model"] = rounds[-1]["outcome"]["model"]
        restored["original_input"] = rounds[-1]["document"]
        self.assertEqual(restored, rounds[-1]["outcome"])
        self.assertEqual(result["original_input"], raw)
        self.assertEqual(result["trace"], rounds[-1]["outcome"]["trace"])
        self.assertGreater(sum(len(row["outcome"]["trace"]) for row in rounds), len(result["trace"]))

    def test_terminal_rounds_skip_detection_and_have_no_extra_equality(self):
        for raw in ({"sides": ["A"], "lines": [], "anchors": {"A": 1}},
                    {"sides": ["A"], "lines": [], "states": {"A": "0000"}}):
            with patch("scripts.quaternary_conditional_diamond_contacts.find_conditional_diamonds",
                       side_effect=AssertionError("terminal detection")):
                result = propagate_diamond_contacts(raw)
            self.assertEqual(len(result["conditional_eq"]["rounds"]), 1)
            self.assertIsNone(result["conditional_eq"]["rounds"][0]["diamond_check"])
            self.assertEqual(result["conditional_eq"]["equal_names"], [])

    def test_conflict_after_equality_does_not_masquerade_as_initial_input_eq(self):
        raw = diamond_trial_document()
        raw["anchors"] = {"P": 1}
        result = propagate_diamond_contacts(raw)
        rounds = result["conditional_eq"]["rounds"]
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(len(rounds), 2)
        self.assertEqual(rounds[0]["outcome"]["status"], "underdetermined")
        self.assertEqual(rounds[1]["outcome"]["status"], "conflict")
        self.assertIsNone(rounds[1]["diamond_check"])
        self.assertNotIn("equal_names", result["original_input"])
        self.assertEqual(result["equal_names"], [["U", "V"]])

    def test_existing_literal_eq_list_is_preserved_in_order(self):
        raw = chain_document()
        raw["equal_names"] = [["A", "A"], ["A", "A"]]
        result = propagate_diamond_contacts(raw)
        self.assertEqual(result["equal_names"], [["A", "A"], ["A", "A"], ["U", "V"], ["W", "T"]])
        self.assertEqual(result["conditional_eq"]["equal_names"], [["U", "V"], ["W", "T"]])

    def test_separate_calls_do_not_inherit_hypothetical_equalities(self):
        restricted = diamond_document(states={side: "0111" for side in ["U", "V", "A", "B"]})
        first = propagate_diamond_contacts(restricted)
        second = propagate_diamond_contacts(diamond_document())
        self.assertEqual(first["conditional_eq"]["equal_names"], [["U", "V"]])
        self.assertEqual(second["conditional_eq"]["equal_names"], [])
        first["conditional_eq"]["rounds"][0]["document"]["lines"].clear()
        first["domains"][0].clear()
        self.assertEqual(len(restricted["lines"]), 5)
        self.assertTrue(first["conditional_eq"]["rounds"][-1]["outcome"]["domains"][0])

    def test_bad_detector_cannot_cause_unbounded_repeated_eq(self):
        raw = diamond_document(states={side: "0111" for side in ["U", "V", "A", "B"]})
        repeated = {"certificates": [{"pair": ["U", "V"], "edge": ["A", "B"], "excluded_color": 1}]}
        with patch("scripts.quaternary_conditional_diamond_contacts.find_conditional_diamonds", return_value=repeated):
            with self.assertRaisesRegex(ValueError, "bounded progress"):
                propagate_diamond_contacts(raw)

    def test_no_diamond_keeps_exact_old_outcome_and_invalid_input_rejects(self):
        raw = diamond_document()
        old, new = propagate_wheel_contacts(raw), propagate_diamond_contacts(raw)
        projected = deepcopy(new)
        projected.pop("conditional_eq")
        projected["model"] = old["model"]
        self.assertEqual(projected, old)
        for malformed in (None, {"sides": ["A"], "lines": [], "anchors": {"A": True}}):
            with self.assertRaises(ValueError):
                propagate_diamond_contacts(malformed)


if __name__ == "__main__":
    unittest.main()

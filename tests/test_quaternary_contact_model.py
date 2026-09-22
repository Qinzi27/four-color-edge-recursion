"""Check quaternary syntax and contact semantics without greedy commitments."""

from copy import deepcopy
from dataclasses import FrozenInstanceError
from itertools import product
import unittest

from scripts.quaternary_contact_model import (
    NameState, from_candidates, propagate_contacts, relation_code,
)


def line(identifier, left, right, kind="separator"):
    """Construct a literal input contact, without inferred graph structure."""
    return {"id": identifier, "left": left, "right": right, "kind": kind}


def decode_pairs(mask):
    """Independent bit decoding for the full relation, including nonedges."""
    return {(a, b) for a in (1, 2, 3, 4) for b in (1, 2, 3, 4)
            if mask & 2 ** (4 * (a - 1) + b - 1)}


class QuaternaryNameStateTests(unittest.TestCase):
    """Exhaust the small code space rather than sampling display examples."""

    def test_all_sixteen_candidate_domains_roundtrip(self):
        for mask in range(16):
            values = {name for name in (1, 2, 3, 4) if mask & (1 << (name - 1))}
            with self.subTest(mask=mask):
                state = from_candidates(values)
                self.assertEqual(set(state.candidates), values)
                self.assertEqual(state.candidate_mask, mask)
                self.assertEqual(NameState.from_quaternary(state.to_quaternary()), state)
                self.assertEqual(NameState(state.code), state)
                self.assertEqual(state.minimum_representative, min(values) if values else None)
                self.assertFalse(state.anchored)
                self.assertEqual(len(state.to_quaternary()), 4)
                if len(values) == 1:
                    anchored = from_candidates(values, anchored=True)
                    self.assertTrue(anchored.anchored)
                    self.assertEqual(set(anchored.candidates), values)
                    self.assertIn("3", anchored.to_quaternary())

    def test_all_256_codes_have_exactly_twenty_canonical_members(self):
        accepted = []
        for code in range(256):
            # Derive digit validity independently using base-four division.
            digits = [(code // divisor) % 4 for divisor in (64, 16, 4, 1)]
            positive = [digit for digit in digits if digit > 0]
            valid = (not positive or (len(positive) == 1 and positive[0] in (2, 3))
                     or (len(positive) > 1 and all(digit == 1 for digit in positive)))
            if valid:
                state = NameState(code)
                accepted.append(code)
                self.assertEqual(state.to_quaternary(), "".join(map(str, digits)))
            else:
                with self.assertRaises(ValueError):
                    NameState(code)
        self.assertEqual(len(accepted), 20)
        self.assertEqual(NameState(0).to_quaternary(), "0000")

    def test_same_representative_keeps_four_different_domains(self):
        states = [from_candidates(values) for values in ({2}, {2, 3}, {2, 4}, {2, 3, 4})]
        self.assertEqual([state.minimum_representative for state in states], [2, 2, 2, 2])
        self.assertEqual([state.to_quaternary() for state in states],
                         ["0200", "0110", "0101", "0111"])
        self.assertEqual(len({state.code for state in states}), 4)
        before = states[-1].code
        self.assertEqual(states[-1].minimum_representative, 2)
        self.assertEqual(states[-1].code, before)
        with self.assertRaises(FrozenInstanceError):
            states[-1].code = 32

    def test_strict_code_name_and_anchor_validation(self):
        for value in (True, False, -1, 256, 2.0, "0111", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                NameState(value)
        for text in (1111, "", "111", "11111", "0140", " 111", "111\n", "0100", "0230"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                NameState.from_quaternary(text)
        for values in ([True], [0], [5], [1.0], "123", None):
            with self.subTest(values=values), self.assertRaises(ValueError):
                from_candidates(values)
        self.assertEqual(from_candidates([2, 2]).to_quaternary(), "0200")
        for values in ([], [1, 2]):
            with self.assertRaises(ValueError):
                from_candidates(values, anchored=True)
        with self.assertRaises(ValueError):
            from_candidates([2], anchored=1)

    def test_relation_encoding_is_eight_digit_numeric_packing(self):
        for mask in (0, 1, 2, 65535, 0x8421, 0x7BDE):
            text = relation_code(mask)
            self.assertEqual(len(text), 8)
            self.assertEqual(int(text, 4), mask)
        for mask in (True, -1, 65536, 2.0, "1"):
            with self.assertRaises(ValueError):
                relation_code(mask)


class QuaternaryContactTests(unittest.TestCase):
    """Separate true shared boundaries, point contacts and logical equalities."""

    def test_non_one_is_a_candidate_set_not_a_commitment(self):
        document = {"sides": ["inside", "outside"],
                    "lines": [line("circle", "inside", "outside")],
                    "anchors": {"inside": 1}}
        before = deepcopy(document)
        result = propagate_contacts(document)
        self.assertEqual(document, before)
        self.assertEqual(result["original_input"], before)
        self.assertEqual(result["name_states"]["inside"]["quaternary"], "3000")
        self.assertEqual(result["name_states"]["outside"]["quaternary"], "0111")
        self.assertEqual(result["name_states"]["outside"]["representative"], 2)
        self.assertEqual(result["name_states"]["outside"]["candidates"], [2, 3, 4])
        self.assertEqual(result["status"], "underdetermined")
        self.assertIsNone(result["colors"])
        self.assertEqual(result["choices"], 0)
        self.assertFalse(result["representatives_are_assignments"])

    def test_adjacent_same_display_retains_six_ordered_pairs(self):
        result = propagate_contacts({"sides": ["A", "B"], "lines": [line("ab", "A", "B")],
                                     "states": {"A": "0111", "B": "0111"}})
        expected = {(a, b) for a in (2, 3, 4) for b in (2, 3, 4) if a != b}
        self.assertEqual(result["domains"], [[2, 3, 4], [2, 3, 4]])
        self.assertEqual({tuple(pair) for pair in result["lines"][0]["allowed_pairs"]}, expected)
        self.assertEqual(len(expected), 6)
        self.assertEqual([result["name_states"][side]["representative"] for side in ("A", "B")], [2, 2])
        self.assertEqual(result["status"], "underdetermined")

    def test_reverse_line_transposes_asymmetric_relation(self):
        result = propagate_contacts({"sides": ["A", "B"], "lines": [line("ab", "A", "B")],
                                     "states": {"A": "1100", "B": "0111"}})
        forward = result["lines"][0]
        reverse = forward["reverse"]
        expected = {(a, b) for a in (1, 2) for b in (2, 3, 4) if a != b}
        self.assertEqual(decode_pairs(forward["relation_mask"]), expected)
        self.assertEqual(decode_pairs(reverse["relation_mask"]), {(b, a) for a, b in expected})
        self.assertEqual((reverse["left"], reverse["right"]), ("B", "A"))
        self.assertEqual(int(reverse["relation_code"], 4), reverse["relation_mask"])

    def test_bridge_identity_and_point_contact_add_no_inequality(self):
        result = propagate_contacts({"sides": ["A", "B"],
                                     "lines": [line("bridge", "A", "A", "bridge")],
                                     "anchors": {"A": 1, "B": 1},
                                     "point_contacts": [{"sides": ["A", "B"]}]})
        self.assertEqual(result["status"], "solved")
        self.assertEqual(result["colors"], {"A": 1, "B": 1})
        self.assertEqual(result["lines"][0]["allowed_pairs"], [[1, 1]])
        self.assertEqual(result["point_contacts"], [{"sides": ["A", "B"]}])

    def test_equality_is_logical_and_preserves_separate_side_identities(self):
        result = propagate_contacts({"sides": ["A", "B", "C"],
                                     "lines": [line("bc", "B", "C")],
                                     "anchors": {"A": 2}, "equal_names": [["A", "B"]]})
        self.assertEqual(result["side_order"], ["A", "B", "C"])
        self.assertEqual(len(result["relations"]), 3)
        self.assertEqual(result["name_states"]["A"]["quaternary"], "0300")
        self.assertEqual(result["name_states"]["B"]["quaternary"], "0200")
        self.assertFalse(result["name_states"]["B"]["anchored"])
        self.assertEqual(result["name_states"]["C"]["candidates"], [1, 3, 4])

    def test_input_states_intersect_anchors_and_preserve_provenance(self):
        matching = propagate_contacts({"sides": ["A"], "lines": [],
                                       "states": {"A": "0111"}, "anchors": {"A": 2}})
        self.assertEqual(matching["initial_domains"], [[2]])
        self.assertEqual(matching["name_states"]["A"]["quaternary"], "0300")
        for state, anchor in (("0111", 1), ("0030", 2), ("0000", 1)):
            with self.subTest(state=state, anchor=anchor):
                result = propagate_contacts({"sides": ["A"], "lines": [],
                                             "states": {"A": state}, "anchors": {"A": anchor}})
                self.assertEqual(result["status"], "conflict")
                self.assertEqual(result["initial_domains"], [[]])
                self.assertEqual(result["name_states"]["A"]["quaternary"], "0000")
                self.assertIsNone(result["colors"])
        supplied = propagate_contacts({"sides": ["A"], "lines": [], "states": {"A": "0030"}})
        self.assertEqual(supplied["explicit_anchor_sources"]["A"], [{"source": "states", "name": 3}])

    def test_real_conflicts_are_results_not_parser_errors(self):
        cases = [
            {"sides": ["A"], "lines": [], "states": {"A": "0000"}},
            {"sides": ["A", "B"], "lines": [line("ab", "A", "B")], "anchors": {"A": 1, "B": 1}},
            {"sides": ["A", "B"], "lines": [line("ab", "A", "B")], "equal_names": [["A", "B"]]},
        ]
        for document in cases:
            with self.subTest(document=document):
                result = propagate_contacts(document)
                self.assertEqual(result["status"], "conflict")
                self.assertIsNone(result["colors"])

    def test_all_singleton_solved_output_checks_raw_constraints(self):
        result = propagate_contacts({"sides": ["A", "B", "C", "D"],
                                     "lines": [line("ad", "A", "D"), line("bd", "B", "D"),
                                               line("cd", "C", "D")],
                                     "anchors": {"A": 1, "B": 2, "C": 3}})
        self.assertEqual(result["status"], "solved")
        self.assertEqual(result["name_states"]["D"]["quaternary"], "0002")
        self.assertEqual(result["colors"], {"A": 1, "B": 2, "C": 3, "D": 4})

    def test_constraints_preserve_all_literal_solutions_in_a_small_example(self):
        document = {"sides": ["A", "B", "C", "D"],
                    "lines": [line("ab", "A", "B"), line("bc", "B", "C")],
                    "states": {"A": "1100", "C": "0111"}, "equal_names": [["A", "D"]],
                    "point_contacts": [{"sides": ["A", "C"]}]}
        result = propagate_contacts(document)
        initial = result["initial_domains"]
        legal = [values for values in product(*initial)
                 if values[0] != values[1] and values[1] != values[2] and values[0] == values[3]]
        self.assertTrue(legal)
        for values in legal:
            for i in range(4):
                self.assertIn(values[i], result["domains"][i])
                for j in range(4):
                    self.assertIn((values[i], values[j]), decode_pairs(result["relations"][i][j]))

    def test_strict_contact_input_validation(self):
        baseline = {"sides": ["A", "B"], "lines": [line("ab", "A", "B")]}
        malformed = [
            None, {}, {"sides": [], "lines": []}, {"sides": ["A", "A"], "lines": []},
            {"sides": [True], "lines": []}, {"sides": ["A"], "lines": [], "extra": 1},
            {**baseline, "lines": [line("ab", "A", "B"), line("ab", "B", "A")]},
            {**baseline, "lines": [line("x", "A", "B", "bridge")]},
            {**baseline, "lines": [line("x", "A", "A")]},
            {**baseline, "lines": [line("x", "A", "missing")]},
            {**baseline, "lines": [line(True, "A", "B")]},
            {**baseline, "anchors": {"A": True}}, {**baseline, "anchors": {"missing": 1}},
            {**baseline, "states": {"A": 85}}, {**baseline, "states": {"A": "1102"}},
            {**baseline, "states": {"missing": "1111"}},
            {**baseline, "point_contacts": [{"sides": ["A", "missing"]}]},
            {**baseline, "equal_names": [["A", "missing"]]},
        ]
        for document in malformed:
            with self.subTest(document=document), self.assertRaises(ValueError):
                propagate_contacts(document)


if __name__ == "__main__":
    unittest.main()

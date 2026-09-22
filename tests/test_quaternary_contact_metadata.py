"""Independent v2 metadata tamper checks; frozen v1 code remains untouched."""

from copy import deepcopy
from itertools import combinations, product
import unittest

from scripts.quaternary_contact_model import propagate_contacts
from scripts.validate_quaternary_contacts import build_inventory, sources as v1_sources
from scripts.validate_quaternary_contacts_v2 import (
    AUDIT_VERSION, SUPPLEMENT, audit_document, parse_state_word, sources,
)


def two_minimum_representatives():
    """Two displayed 2s retain six compatible ordered pairs, not a commitment."""
    return {"sides": ["A", "B"], "states": {"A": "0111", "B": "0111"},
            "lines": [{"id": "ab", "left": "A", "right": "B", "kind": "separator"}]}


class QuaternaryContactMetadataTests(unittest.TestCase):
    """Reject semantic metadata corruption while keeping soundness scope exact."""

    def assert_rejected(self, document, change):
        """Mutate one fresh result, leaving its original input bytes unaltered."""
        result = propagate_contacts(document)
        change(result)
        with self.assertRaises(AssertionError):
            audit_document(document, result)

    def test_two_minimum_representatives_are_still_uncommitted(self):
        """The core illustrative ambiguity is resolved by the full domains."""
        document = two_minimum_representatives()
        result = propagate_contacts(document)
        audit = audit_document(document, result)
        self.assertTrue(audit["metadata_passed"])
        self.assertEqual(audit["audit_version"], AUDIT_VERSION)
        self.assertEqual(audit["legal_assignments"], 6)
        self.assertEqual(result["status"], "underdetermined")
        self.assertIsNone(result["colors"])
        self.assertEqual(result["choices"], 0)
        self.assertEqual(result["lines"][0]["relation_mask"], 27328)
        self.assertEqual(result["lines"][0]["relation_code"], "12223000")
        for state in result["name_states"].values():
            self.assertEqual(state["quaternary"], "0111")
            self.assertEqual(state["representative"], 2)
            self.assertFalse(state["anchored"])

    def test_explicit_anchor_cannot_be_relabelled_as_derived(self):
        """Marker 3 has input provenance that marker 2 must not erase."""
        document = {"sides": ["A"], "lines": [], "anchors": {"A": 1}}
        self.assert_rejected(document, lambda result: result["name_states"]["A"].update(
            quaternary="2000", code=128, anchored=False))
        self.assert_rejected(document, lambda result: result["initial_states"]["A"].update(
            quaternary="2000", code=128, anchored=False))

    def test_supplied_unanchored_singleton_cannot_become_explicit_anchor(self):
        """An externally provided 2 remains a restriction rather than a 3 source."""
        document = {"sides": ["A"], "lines": [], "states": {"A": "2000"}}
        valid = propagate_contacts(document)
        self.assertTrue(audit_document(document, valid)["passed"])
        self.assertEqual(valid["explicit_anchor_sources"], {"A": []})
        self.assert_rejected(document, lambda result: result["name_states"]["A"].update(
            quaternary="3000", code=192, anchored=True))

    def test_multiple_nonzero_anchor_markers_are_noncanonical(self):
        """Nonzero positions alone are insufficient to validate a state word."""
        self.assert_rejected(two_minimum_representatives(), lambda result: result["name_states"]["A"].update(
            quaternary="0333", code=int("0333", 4), anchored=True))
        self.assert_rejected({"sides": ["A"], "lines": [], "states": {"A": "2000"}},
                             lambda result: result["name_states"]["A"].update(quaternary="1000", code=64))

    def test_candidate_mask_and_anchored_flag_cannot_drift(self):
        """Metadata must encode exactly the same candidates and epistemic state."""
        document = two_minimum_representatives()
        self.assert_rejected(document, lambda result: result["name_states"]["A"].update(candidate_mask=15))
        self.assert_rejected(document, lambda result: result["name_states"]["A"].update(anchored=True))
        self.assert_rejected(document, lambda result: result["initial_states"]["A"].update(candidate_mask=0))

    def test_state_type_checks_reject_boolean_integer_aliases(self):
        """Python equality cannot allow True to impersonate literal name one."""
        document = {"sides": ["A"], "lines": [], "anchors": {"A": 1}}
        self.assert_rejected(document, lambda result: result["name_states"]["A"].update(candidate_mask=True))
        self.assert_rejected(document, lambda result: result["name_states"]["A"].update(representative=True))
        self.assert_rejected(document, lambda result: result["name_states"]["A"].update(candidates=[True]))
        self.assert_rejected(document, lambda result: result["name_states"]["A"].update(anchored=1))
        self.assert_rejected(document, lambda result: result["colors"].update(A=True))
        self.assert_rejected(document, lambda result: result.update(choices=False))

    def test_explicit_sources_include_both_state_anchor_and_anchor_mapping(self):
        """Both matching declarations remain visible rather than deduplicated."""
        document = {"sides": ["A"], "lines": [], "states": {"A": "3000"}, "anchors": {"A": 1}}
        result = propagate_contacts(document)
        self.assertTrue(audit_document(document, result)["passed"])
        self.assertEqual(result["explicit_anchor_sources"]["A"],
                         [{"source": "states", "name": 1}, {"source": "anchors", "name": 1}])
        self.assert_rejected(document, lambda item: item["explicit_anchor_sources"].update(
            A=[{"source": "anchors", "name": 1}]))
        self.assert_rejected(document, lambda item: item["explicit_anchor_sources"]["A"][0].update(name=True))

    def test_conflicting_anchors_keep_sources_but_empty_state_is_not_anchored(self):
        """0000 retains the reason for conflict in separate provenance fields."""
        document = {"sides": ["A"], "lines": [], "states": {"A": "3000"}, "anchors": {"A": 2}}
        result = propagate_contacts(document)
        audit = audit_document(document, result)
        self.assertEqual((result["status"], audit["legal_assignments"]), ("conflict", 0))
        self.assertEqual(result["initial_states"]["A"]["quaternary"], "0000")
        self.assertFalse(result["name_states"]["A"]["anchored"])
        self.assertEqual(len(result["explicit_anchor_sources"]["A"]), 2)
        self.assert_rejected(document, lambda item: item["initial_states"]["A"].update(anchored=True))

    def test_initial_and_final_matrices_require_exact_square_16_bit_integers(self):
        """Ignored high bits, bool masks and malformed rows must be rejected."""
        document = two_minimum_representatives()
        for field in ("initial_relations", "relations"):
            with self.subTest(field=field):
                self.assert_rejected(document, lambda result, f=field: result[f][0].__setitem__(
                    0, result[f][0][0] | 65536))
                self.assert_rejected(document, lambda result, f=field: result[f][0].__setitem__(0, True))
                self.assert_rejected(document, lambda result, f=field: result[f].pop())
                self.assert_rejected(document, lambda result, f=field: result[f][0].append(0))
                self.assert_rejected(document, lambda result, f=field: result[f][0].__setitem__(0, -1))

    def test_initial_matrix_is_bound_to_raw_contacts_and_final_cannot_widen(self):
        """A syntactically valid mask is still wrong if it invents permissions."""
        document = two_minimum_representatives()
        def add_forbidden_pair(result, field):
            # Pair (2,2) is symmetric and stays in each unary domain, but the
            # actual shared boundary prohibits it.
            result[field][0][1] |= 1 << 5
            result[field][1][0] |= 1 << 5
        self.assert_rejected(document, lambda result: add_forbidden_pair(result, "initial_relations"))
        self.assert_rejected(document, lambda result: add_forbidden_pair(result, "relations"))
        self.assert_rejected(document, lambda result: result["relations"][0].__setitem__(1, 0))

    def test_initial_and_final_domain_arrays_are_bound_to_states_and_diagonals(self):
        """The parallel domain array cannot hide a different candidate set."""
        document = two_minimum_representatives()
        self.assert_rejected(document, lambda result: result["domains"].__setitem__(0, [2, 3]))
        self.assert_rejected(document, lambda result: result["initial_domains"].__setitem__(0, [2, 3]))
        self.assert_rejected(document, lambda result: result["domains"].__setitem__(0, [4, 3, 2]))
        anchored = {"sides": ["A"], "lines": [], "anchors": {"A": 1}}
        self.assert_rejected(anchored, lambda result: result["domains"].__setitem__(0, [True]))

    def test_reverse_line_identifiers_and_literal_pairs_are_checked(self):
        """Transposing the numbers must also reverse their named endpoints."""
        document = two_minimum_representatives()
        self.assert_rejected(document, lambda result: result["lines"][0]["reverse"].update(left="missing"))
        self.assert_rejected(document, lambda result: result["lines"][0]["reverse"].update(right="B"))
        asymmetric = {"sides": ["A", "B"], "states": {"A": "1100", "B": "0111"},
                      "lines": [{"id": "ab", "left": "A", "right": "B", "kind": "separator"}]}
        result = propagate_contacts(asymmetric)
        self.assertTrue(audit_document(asymmetric, result)["passed"])
        self.assertNotEqual(result["lines"][0]["relation_mask"], result["lines"][0]["reverse"]["relation_mask"])
        self.assert_rejected(asymmetric, lambda item: item["lines"][0]["allowed_pairs"][0].__setitem__(0, True))

    def test_point_contact_equality_and_bridge_echoes_keep_identity_semantics(self):
        """Point touch does not enforce NEQ, while EQ does not merge side IDs."""
        document = {"sides": ["A", "B"], "lines": [{"id": "bridge", "left": "A", "right": "A", "kind": "bridge"}],
                    "point_contacts": [{"sides": ["A", "B"]}], "equal_names": [["A", "B"]]}
        result = propagate_contacts(document)
        self.assertTrue(audit_document(document, result)["passed"])
        self.assertEqual(result["side_order"], ["A", "B"])
        self.assertEqual(len(result["lines"][0]["allowed_pairs"]), 4)
        self.assert_rejected(document, lambda item: item.update(point_contacts=[]))
        self.assert_rejected(document, lambda item: item.update(equal_names=[]))
        self.assert_rejected(document, lambda item: item["name_states"].update(C=deepcopy(item["name_states"]["A"])))

    def test_status_must_match_conflict_or_exact_singleton_classification(self):
        """Unknown tags cannot bypass solved-vs-unresolved checks."""
        document = two_minimum_representatives()
        self.assert_rejected(document, lambda result: result.update(status="unchecked"))
        self.assert_rejected(document, lambda result: result.update(status="solved"))
        singleton = {"sides": ["A"], "lines": [], "anchors": {"A": 1}}
        self.assert_rejected(singleton, lambda result: result.update(status="underdetermined", colors=None))

    def test_planar_k4_with_three_candidates_is_a_permitted_scope_counterexample(self):
        """Local consistency may hold while all 81 complete assignments fail.

        This named diagnostic is separate from the 41847 frozen inventory; it
        must not change the producer to turn local consistency into a solver.
        """
        sides = ["A", "B", "C", "D"]
        document = {"sides": sides, "states": {side: "0111" for side in sides},
                    "lines": [{"id": f"e{i}", "left": a, "right": b, "kind": "separator"}
                              for i, (a, b) in enumerate(combinations(sides, 2))]}
        result = propagate_contacts(document)
        audit = audit_document(document, result)
        self.assertEqual(result["status"], "underdetermined")
        self.assertEqual(result["choices"], 0)
        self.assertIsNone(result["colors"])
        self.assertEqual(audit["literal_assignments_checked"], 81)
        self.assertEqual(audit["legal_assignments"], 0)
        self.assertTrue(audit["passed"])

    def test_trace_is_explicitly_outside_step_by_step_audit_scope(self):
        """Do not present checked endpoints as a replayed intermediate trace."""
        document = {"sides": ["A", "B"], "anchors": {"A": 1},
                    "lines": [{"id": "ab", "left": "A", "right": "B", "kind": "separator"}]}
        result = propagate_contacts(document)
        self.assertTrue(result["trace"])
        result["trace"] = []
        audit = audit_document(document, result)
        self.assertEqual(audit["trace_audit"], "not_replayed")
        self.assertTrue(audit["initial_to_final_matrix_subset"])

    def test_exactly_twenty_canonical_input_words(self):
        """All 256 numerals are classified without the production parser."""
        accepted = []
        for digits in product("0123", repeat=4):
            word = "".join(digits)
            try:
                parse_state_word(word)
            except AssertionError:
                continue
            accepted.append(word)
        self.assertEqual(len(accepted), 20)
        self.assertIn("0000", accepted)
        self.assertIn("0111", accepted)
        self.assertIn("0200", accepted)
        self.assertIn("0300", accepted)
        self.assertNotIn("0100", accepted)

    def test_v2_preserves_inventory_and_adds_versioned_dependencies(self):
        """Adding an audit does not silently enlarge the frozen finite corpus."""
        self.assertEqual(len(build_inventory()), 41847)
        old, new = v1_sources(), sources()
        self.assertTrue(set(old) <= set(new))
        self.assertTrue(all(new[name] == value for name, value in old.items()))
        self.assertIn("scripts/validate_quaternary_contacts_v2.py", new)
        self.assertIn("tests/test_quaternary_contact_metadata.py", new)
        self.assertIn(SUPPLEMENT, new)


if __name__ == "__main__":
    unittest.main()

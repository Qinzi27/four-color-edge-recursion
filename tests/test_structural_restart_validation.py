"""Reject plausible-looking but ungrounded structural restart certificates."""

from copy import deepcopy
import unittest

from fourcolor.structural_name_relations import refute_same_name
from fourcolor.structural_restart import restart_structural_names
from scripts.validate_structural_restart import audit_refutation, verify_run
from tests.test_structural_restart import failure_geometry


class StructuralProofAuditTests(unittest.TestCase):
    """Every learned relation needs real current classes and real source edges."""

    @classmethod
    def setUpClass(cls):
        cls.geometry = failure_geometry()
        cls.result = restart_structural_names(cls.geometry)
        cls.edges = [row["pair"] for row in cls.result["geometric_edge_sources"]]
        cls.proof = cls.result["proof_queries"][0]["certificate"]

    def test_real_certificate_and_inconclusive_saturation_pass(self):
        self.assertTrue(audit_refutation(19, self.edges, 1, 10, self.proof)["passed"])
        unknown = refute_same_name(5, [(0, 1), (1, 2), (2, 3), (3, 4)], 0, 4)
        self.assertEqual(unknown["status"], "inconclusive")
        self.assertTrue(audit_refutation(5, [(0, 1), (1, 2), (2, 3), (3, 4)], 0, 4, unknown)["passed"])

    def test_invented_or_missing_edge_premise_fails(self):
        for change in ("invent", "drop", "duplicate"):
            proof = deepcopy(self.proof)
            witnesses = proof["merges"][0]["spokes"]
            if change == "invent":
                witnesses[0]["original_edge"] = [1, 10]
            elif change == "drop":
                witnesses.pop()
            else:
                witnesses[-1] = deepcopy(witnesses[0])
            with self.subTest(change=change), self.assertRaises(AssertionError):
                audit_refutation(19, self.edges, 1, 10, proof)

    def test_wrong_class_union_or_hypothesis_fails(self):
        for change in ("union", "hypothesis", "partition"):
            proof = deepcopy(self.proof)
            if change == "union":
                proof["merges"][0]["result_class"].append(99)
            elif change == "hypothesis":
                proof["assumed_equal"] = [1, 9]
            else:
                proof["final_classes"].pop()
            with self.subTest(change=change), self.assertRaises(AssertionError):
                audit_refutation(19, self.edges, 1, 10, proof)

    def test_false_inconclusive_cannot_hide_a_found_clique(self):
        proof = deepcopy(self.proof)
        proof["status"], proof["contradiction"] = "inconclusive", None
        with self.assertRaises(AssertionError):
            audit_refutation(19, self.edges, 1, 10, proof)

    def test_refuted_proposal_must_not_be_committed(self):
        result = deepcopy(self.result)
        result["events"][0]["kind"] = "commit"
        with self.assertRaises(AssertionError):
            verify_run(self.geometry, result)

    def test_omitted_query_and_fabricated_geometric_edge_fail(self):
        for change in ("query", "edge"):
            result = deepcopy(self.result)
            if change == "query":
                result["events"][0]["checks"] = []
            else:
                result["geometric_edge_sources"][0]["raw_edge_ids"] = []
            with self.subTest(change=change), self.assertRaises(AssertionError):
                verify_run(self.geometry, result)

    def test_unproved_auxiliary_relation_or_missing_learn_action_fails(self):
        for change in ("extra", "omit"):
            result = deepcopy(self.result)
            if change == "extra":
                result["propagation_phases"][0]["learned_pairs"] = [[1, 10]]
            else:
                result["events"].pop(0)
            with self.subTest(change=change), self.assertRaises(AssertionError):
                verify_run(self.geometry, result)

    def test_wrong_rule_pass_count_and_scope_metadata_fail(self):
        for field, value in (("rule", "unsupported-rule"), ("passes", 999)):
            proof = deepcopy(self.proof)
            target = proof if field == "rule" else proof["statistics"]
            target[field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                audit_refutation(19, self.edges, 1, 10, proof)
        result = deepcopy(self.result)
        result["local_budget"] = 2
        with self.assertRaises(AssertionError):
            verify_run(self.geometry, result)


if __name__ == "__main__":
    unittest.main()

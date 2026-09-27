"""Independent witness, coverage and declared finite-rule checks for odd EQ."""

from copy import deepcopy
from itertools import combinations, product
import unittest
from unittest.mock import patch

from scripts.check_odd_cycle_eq_rule_soundness import check_rule_soundness, rule_inventory
from scripts.quaternary_contact_model import propagate_contacts
from scripts.quaternary_odd_cycle_eq import (
    VERSION, learn_odd_cycle_equalities, verify_odd_cycle_equalities,
)
from scripts.quaternary_triangle_eq import learn_triangle_equalities


def graph_document(sides, edges, **extra):
    """Create literal input edges, without a geometric or coloring inference."""
    return {"sides": list(sides), "lines": [
        {"id": f"edge-{i}", "left": sides[a], "right": sides[b], "kind": "separator"}
        for i, (a, b) in enumerate(edges)], **extra}


def cycle_document(length):
    """Return the unanchored full two-apex cycle fixture of a given length."""
    sides = ["A", "E"] + [f"R{i}" for i in range(length)]
    edges = [(apex, rim + 2) for apex in (0, 1) for rim in range(length)]
    edges += [(i + 2, (i + 1) % length + 2) for i in range(length)]
    return graph_document(sides, edges)


class OddCycleEqualityTests(unittest.TestCase):
    """Check original-edge semantics and the independent certificate boundary."""

    def test_five_cycle_discovers_equality_missing_from_triangle_rule(self):
        document = cycle_document(5)
        before = deepcopy(document)
        learned = learn_odd_cycle_equalities(document)
        self.assertEqual(learn_triangle_equalities(document)["equal_names"], [])
        self.assertEqual(learned["version"], VERSION)
        self.assertEqual(learned["equal_names"], [["A", "E"]])
        self.assertEqual(learned["certificates"], [{"apices": ["A", "E"],
                                                   "cycle": [f"R{i}" for i in range(5)]}])
        self.assertEqual(learned["stats"]["neq_edge_count"], 15)
        self.assertEqual(document, before)
        self.assertTrue(verify_odd_cycle_equalities(document, learned)["passed"])

    def test_odd_seven_and_even_four_six_controls(self):
        for length in (3, 4, 5, 6, 7):
            with self.subTest(length=length):
                document = cycle_document(length)
                learned = learn_odd_cycle_equalities(document)
                self.assertEqual(learned["equal_names"], [["A", "E"]] if length % 2 else [])
                self.assertTrue(verify_odd_cycle_equalities(document, learned)["passed"])

    def test_each_single_missing_cycle_or_spoke_edge_blocks_apex_rule(self):
        for length in (3, 5, 7):
            base = cycle_document(length)
            for deletion in range(3 * length):
                document = deepcopy(base)
                document["lines"].pop(deletion)
                learned = learn_odd_cycle_equalities(document)
                self.assertNotIn(["A", "E"], learned["equal_names"])
                self.assertTrue(verify_odd_cycle_equalities(document, learned)["passed"])

    def test_coverage_on_all_1024_common_graphs_on_five_vertices(self):
        # The expected condition is checked by exhausting all binary labelings,
        # not by another graph traversal or the production certificate finder.
        pairs = list(combinations(range(5), 2))
        sides = ["A", "E"] + [f"R{i}" for i in range(5)]
        for mask in range(1 << len(pairs)):
            common_edges = [edge for i, edge in enumerate(pairs) if mask & (1 << i)]
            edges = [(apex, rim + 2) for apex in (0, 1) for rim in range(5)]
            edges += [(a + 2, b + 2) for a, b in common_edges]
            document = graph_document(sides, edges)
            learned = learn_odd_cycle_equalities(document)
            bipartite = any(all(labels[a] != labels[b] for a, b in common_edges)
                            for labels in product((0, 1), repeat=5))
            self.assertEqual(["A", "E"] in learned["equal_names"], not bipartite, mask)
            old = learn_triangle_equalities(document)
            self.assertTrue(all(pair in learned["equal_names"] for pair in old["equal_names"]))
            self.assertTrue(verify_odd_cycle_equalities(document, learned)["passed"])

    def test_bfs_reconstructs_cycle_with_lca_below_tree_root(self):
        # Common graph R0--R1--R2 followed by the C5 R2,R3,R4,R5,R6.
        sides = ["A", "E"] + [f"R{i}" for i in range(7)]
        edges = [(apex, rim + 2) for apex in (0, 1) for rim in range(7)]
        edges += [(2, 3), (3, 4), (4, 5), (5, 6), (6, 7), (7, 8), (8, 4)]
        document = graph_document(sides, edges)
        learned = learn_odd_cycle_equalities(document)
        self.assertEqual(learned["certificates"][0], {"apices": ["A", "E"],
                                                     "cycle": [f"R{i}" for i in range(2, 7)]})
        self.assertTrue(verify_odd_cycle_equalities(document, learned)["passed"])

    def test_disconnected_common_graph_prefers_triangle_before_earlier_c5(self):
        sides = ["A", "E"] + [f"R{i}" for i in range(8)]
        edges = [(apex, rim + 2) for apex in (0, 1) for rim in range(8)]
        edges += [(2 + i, 2 + (i + 1) % 5) for i in range(5)]
        edges += [(7, 8), (8, 9), (7, 9)]
        document = graph_document(sides, edges)
        learned = learn_odd_cycle_equalities(document)
        self.assertEqual(learned["certificates"][0]["cycle"], ["R5", "R6", "R7"])
        self.assertTrue(verify_odd_cycle_equalities(document, learned)["passed"])
        # Soundness checking deliberately accepts another valid normalized
        # witness and does not secretly call the learner to select it again.
        learned["certificates"][0]["cycle"] = [f"R{i}" for i in range(5)]
        self.assertTrue(verify_odd_cycle_equalities(document, learned)["passed"])

    def test_side_order_controls_canonical_rotation_not_lexical_name(self):
        document = cycle_document(5)
        document["sides"] = ["E", "A", "R3", "R1", "R0", "R4", "R2"]
        learned = learn_odd_cycle_equalities(document)
        self.assertEqual(learned["certificates"], [{"apices": ["E", "A"],
                                                   "cycle": ["R3", "R4", "R0", "R1", "R2"]}])
        self.assertTrue(verify_odd_cycle_equalities(document, learned)["passed"])

    def test_point_contact_and_bridge_do_not_replace_missing_rim_edge(self):
        document = cycle_document(5)
        removed = document["lines"].pop()
        document["point_contacts"] = [{"sides": [removed["left"], removed["right"]]}]
        document["lines"].append({"id": "bridge", "left": "R0", "right": "R0", "kind": "bridge"})
        learned = learn_odd_cycle_equalities(document)
        self.assertEqual(learned["equal_names"], [])
        self.assertEqual(learned["stats"]["bridge_line_count"], 1)
        self.assertEqual(learned["stats"]["point_contact_count"], 1)
        self.assertTrue(verify_odd_cycle_equalities(document, learned)["passed"])

    def test_parallel_reverse_separator_counts_once(self):
        document = cycle_document(5)
        document["lines"].append({"id": "parallel", "left": "R0", "right": "A", "kind": "separator"})
        learned = learn_odd_cycle_equalities(document)
        self.assertEqual(learned["stats"]["separator_line_count"], 16)
        self.assertEqual(learned["stats"]["neq_edge_count"], 15)
        self.assertEqual(learned["equal_names"], [["A", "E"]])
        self.assertTrue(verify_odd_cycle_equalities(document, learned)["passed"])

    def test_anchors_do_not_guide_learning_but_remain_hash_bound(self):
        document = cycle_document(5)
        learned = learn_odd_cycle_equalities(document)
        document["anchors"] = {"A": 1, "E": 2}
        anchored = learn_odd_cycle_equalities(document)
        self.assertEqual(anchored["equal_names"], learned["equal_names"])
        self.assertEqual(anchored["certificates"], learned["certificates"])
        self.assertNotEqual(anchored["raw_document_sha256"], learned["raw_document_sha256"])
        self.assertTrue(verify_odd_cycle_equalities(document, anchored)["passed"])

    def test_adjacent_apices_not_certified(self):
        document = cycle_document(5)
        document["lines"].append({"id": "apex", "left": "A", "right": "E", "kind": "separator"})
        learned = learn_odd_cycle_equalities(document)
        self.assertNotIn(["A", "E"], learned["equal_names"])
        self.assertTrue(verify_odd_cycle_equalities(document, learned)["passed"])

    def test_external_states_and_eq_rejected_empty_fields_allowed(self):
        for field, value in [("states", {"A": "1111"}), ("equal_names", [["A", "E"]])]:
            document = cycle_document(5)
            learned = learn_odd_cycle_equalities(document)
            document[field] = value
            with self.assertRaises(ValueError):
                learn_odd_cycle_equalities(document)
            with self.assertRaises(ValueError):
                verify_odd_cycle_equalities(document, learned)
        document = cycle_document(5)
        document.update(states={}, equal_names=[])
        self.assertEqual(learn_odd_cycle_equalities(document)["equal_names"], [["A", "E"]])

    def test_name_propagation_preserves_distinct_face_identities(self):
        document = cycle_document(5)
        document["anchors"] = {"A": 2}
        document["equal_names"] = learn_odd_cycle_equalities(document)["equal_names"]
        outcome = propagate_contacts(document)
        self.assertEqual(outcome["side_order"], document["sides"])
        self.assertEqual(outcome["name_states"]["E"]["candidates"], [2])
        self.assertFalse(outcome["name_states"]["E"]["anchored"])

    def test_checker_calls_neither_learner_nor_cycle_finder(self):
        document = cycle_document(5)
        learned = learn_odd_cycle_equalities(document)
        with patch("scripts.quaternary_odd_cycle_eq.learn_odd_cycle_equalities", side_effect=AssertionError), \
                patch("scripts.quaternary_odd_cycle_eq._odd_cycle", side_effect=AssertionError), \
                patch("scripts.quaternary_odd_cycle_eq._normalize_cycle", side_effect=AssertionError):
            self.assertTrue(verify_odd_cycle_equalities(document, learned)["passed"])

    def test_missing_extra_duplicate_reordered_and_forged_certificates_rejected(self):
        document = cycle_document(5)
        correct = learn_odd_cycle_equalities(document)
        changes = [
            ("version", "other"), ("raw_document_sha256", "0" * 64),
            ("equal_names", []), ("equal_names", [["E", "A"]]),
            ("equal_names", [["A", "E"], ["A", "E"]]), ("certificates", []),
        ]
        for field, value in changes:
            changed = deepcopy(correct)
            changed[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                verify_odd_cycle_equalities(document, changed)
        bad_cycles = [None, {}, ["R0", "R1", "R2"], ["R0", "R1", "R2", "R3"],
                      ["R0", "R1", "R2", "R3", "R3"], ["A", "R1", "R2", "R3", "R4"],
                      ["R1", "R2", "R3", "R4", "R0"], ["R0", "R4", "R3", "R2", "R1"],
                      ["R0", "R1", "R3", "R2", "R4"], ["R0", "R1", "R2", "R3", "unknown"]]
        for cycle in bad_cycles:
            changed = deepcopy(correct)
            changed["certificates"][0]["cycle"] = cycle
            with self.subTest(cycle=cycle), self.assertRaises(ValueError):
                verify_odd_cycle_equalities(document, changed)
        changed = deepcopy(correct)
        changed["stats"]["certificate_count"] = True
        with self.assertRaises(ValueError):
            verify_odd_cycle_equalities(document, changed)

    def test_missing_pair_coverage_rejected_when_other_certificate_still_valid(self):
        document = cycle_document(5)
        document["sides"].insert(2, "F")
        document["lines"].extend({"id": f"F-{i}", "left": "F", "right": f"R{i}",
                                  "kind": "separator"} for i in range(5))
        learned = learn_odd_cycle_equalities(document)
        self.assertEqual(learned["equal_names"], [["A", "E"], ["A", "F"], ["E", "F"]])
        learned["equal_names"].pop()
        learned["certificates"].pop()
        learned["stats"]["certificate_count"] -= 1
        with self.assertRaises(ValueError):
            verify_odd_cycle_equalities(document, learned)

    def test_hash_binds_metadata_and_schema_rejects_palette_change(self):
        document = cycle_document(5)
        learned = learn_odd_cycle_equalities(document)
        document["point_contacts"] = [{"sides": ["A", "E"]}]
        with self.assertRaises(ValueError):
            verify_odd_cycle_equalities(document, learned)
        document["palette"] = [1, 2, 3, 4, 5]
        with self.assertRaises(ValueError):
            learn_odd_cycle_equalities(document)


class OddCycleFiniteArtifactTests(unittest.TestCase):
    """Check finite scope and exact totals against independent simple formulas."""

    @classmethod
    def setUpClass(cls):
        """Run all declared graph-assignment pairs once for artifact assertions."""
        cls.result = check_rule_soundness()

    def test_declared_inventory_and_literal_counts(self):
        result = self.result
        inventory = rule_inventory()
        self.assertTrue(result["passed"])
        self.assertEqual(result["graph_count"], sum(1 + 3 * k for k in range(3, 8)))
        self.assertEqual(result["graph_count"], 80)
        self.assertEqual(result["graph_assignment_pairs"], 7337984)
        self.assertEqual([row["id"] for row in result["per_graph"]], [row["id"] for row in inventory])
        self.assertTrue(all(row["literal_assignments_checked"] == 4 ** (row["rim_length"] + 2)
                            for row in result["per_graph"]))
        self.assertFalse(result["scope"]["color_symmetry_reduction"])
        self.assertFalse(result["scope"]["vertex_symmetry_reduction"])
        self.assertFalse(result["scope"]["oracle_used"])

    def test_full_graph_counts_and_negative_control_witnesses(self):
        full = [row for row in self.result["per_graph"] if row["deleted_edge"] is None]
        # Equal apices: 4 choices, followed by a 3-color cycle. Different
        # apices: 4*3 choices times two alternating assignments on even cycles.
        for row in full:
            length = row["rim_length"]
            expected = 4 * (2 ** length + 2 * (-1) ** length) + (24 if length % 2 == 0 else 0)
            self.assertEqual(row["legal_assignments"], expected)
        self.assertEqual(self.result["graphs_with_certificates"], 3)
        self.assertEqual(self.result["certificate_count"], 3)
        self.assertEqual(self.result["eq_projection_checks"], 24 + 120 + 504)
        self.assertEqual(self.result["negative_control_witnesses"], 77)
        self.assertEqual(self.result["graphs_without_legal_assignments"], 0)
        for record, row in zip(rule_inventory(), self.result["per_graph"]):
            witness = row["unequal_apices_witness"]
            if witness is not None:
                names = dict(zip(record["document"]["sides"], witness))
                self.assertNotEqual(names["A"], names["E"])
                self.assertTrue(all(names[edge["left"]] != names[edge["right"]]
                                    for edge in record["document"]["lines"]))

    def test_deterministic_artifact_replay(self):
        self.assertEqual(check_rule_soundness(), self.result)
        self.assertEqual(len(self.result["input_inventory_sha256"]), 64)
        self.assertEqual(len(self.result["per_graph_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()

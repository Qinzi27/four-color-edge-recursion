"""Finite soundness and independent-certificate tests for shared-triangle EQ."""

from copy import deepcopy
from itertools import combinations, product
import unittest
from unittest.mock import patch

from scripts.quaternary_contact_model import propagate_contacts
from scripts.quaternary_triangle_eq import (
    VERSION, learn_triangle_equalities, verify_triangle_equalities,
)
from scripts.check_triangle_eq_rule_soundness import check_rule_soundness


def graph_document(sides, edges, **extra):
    """Build literal NEQ inputs without inferring any geometry or coloring."""
    return {"sides": list(sides),
            "lines": [{"id": f"edge-{i}", "left": sides[a], "right": sides[b],
                       "kind": "separator"} for i, (a, b) in enumerate(edges)],
            **extra}


def bipyramid_document():
    """Return the five-side K5-minus-apex-edge diagnostic in fixed order."""
    return graph_document(["A", "E", "B", "C", "D"],
                          [(a, b) for a, b in combinations(range(5), 2) if (a, b) != (0, 1)])


def literal_solutions(document, palette=(1, 2, 3, 4)):
    """Enumerate scalar assignments independently of relation propagation."""
    sides = document["sides"]
    for values in product(palette, repeat=len(sides)):
        names = dict(zip(sides, values))
        if all(names[row["left"]] != names[row["right"]]
               for row in document["lines"] if row["kind"] == "separator"):
            if all(names[side] == color for side, color in document.get("anchors", {}).items()):
                yield names


class TriangleEqualityTests(unittest.TestCase):
    """Certify a local theorem while exposing its assumptions and limits."""

    def test_five_side_all_1024_assignments_preserve_24_legal_solutions(self):
        document = bipyramid_document()
        before = deepcopy(document)
        result = learn_triangle_equalities(document)
        self.assertEqual(result["version"], VERSION)
        self.assertEqual(result["equal_names"], [["A", "E"]])
        self.assertEqual(result["certificates"], [{"apices": ["A", "E"], "rim": ["B", "C", "D"]}])
        self.assertEqual(result["stats"]["neq_edge_count"], 9)
        self.assertEqual(document, before)
        solutions = list(literal_solutions(document))
        self.assertEqual(len(solutions), 24)
        self.assertTrue(all(solution["A"] == solution["E"] for solution in solutions))
        self.assertTrue(verify_triangle_equalities(document, result)["passed"])

    def test_six_side_all_4096_assignments_with_two_shared_apices(self):
        # A, E, F all see the same BCD triangle, without becoming one face.
        sides = ["A", "E", "F", "B", "C", "D"]
        edges = [(a, b) for a in range(3) for b in range(3, 6)] + list(combinations(range(3, 6), 2))
        document = graph_document(sides, edges)
        learned = learn_triangle_equalities(document)
        self.assertEqual(learned["equal_names"], [["A", "E"], ["A", "F"], ["E", "F"]])
        solutions = list(literal_solutions(document))
        self.assertEqual(len(solutions), 24)
        self.assertTrue(all(all(solution[a] == solution[b] for a, b in learned["equal_names"])
                            for solution in solutions))
        self.assertTrue(verify_triangle_equalities(document, learned)["passed"])

    def test_all_1024_five_vertex_graphs_and_all_1024_assignments(self):
        # Exhaust every labeled simple five-vertex graph. The universal literal
        # assignments are precomputed once; a bit mask tests each graph without
        # sharing the learner's triangle criterion or a coloring oracle.
        pairs = list(combinations(range(5), 2))
        assignments = [(values, sum(1 << i for i, (a, b) in enumerate(pairs) if values[a] != values[b]))
                       for values in product(range(1, 5), repeat=5)]
        equality_graphs = 0
        for edge_mask in range(1 << len(pairs)):
            document = graph_document([f"side-{i}" for i in range(5)],
                                      [edge for i, edge in enumerate(pairs) if edge_mask & (1 << i)])
            learned = learn_triangle_equalities(document)
            verify_triangle_equalities(document, learned)
            equality_indices = [(document["sides"].index(a), document["sides"].index(b))
                                for a, b in learned["equal_names"]]
            equality_graphs += bool(equality_indices)
            for values, legal_edge_mask in assignments:
                if edge_mask & legal_edge_mask == edge_mask:
                    self.assertTrue(all(values[a] == values[b] for a, b in equality_indices),
                                    (edge_mask, values, learned))
        self.assertEqual(equality_graphs, 10)

    def test_each_of_nine_missing_edges_blocks_this_witness(self):
        base = bipyramid_document()
        for index in range(9):
            document = deepcopy(base)
            document["lines"].pop(index)
            learned = learn_triangle_equalities(document)
            self.assertEqual(learned["equal_names"], [])
            # Losing even one required NEQ really allows A and E to differ.
            self.assertTrue(any(names["A"] != names["E"] for names in literal_solutions(document)))
            self.assertTrue(verify_triangle_equalities(document, learned)["passed"])

    def test_point_contacts_and_bridges_never_replace_a_separator(self):
        document = bipyramid_document()
        removed = document["lines"].pop()
        document["point_contacts"] = [{"sides": [removed["left"], removed["right"]]}]
        document["lines"].append({"id": "dangling", "left": removed["left"],
                                  "right": removed["left"], "kind": "bridge"})
        result = learn_triangle_equalities(document)
        self.assertEqual(result["equal_names"], [])
        self.assertEqual(result["stats"]["neq_edge_count"], 8)
        self.assertEqual(result["stats"]["bridge_line_count"], 1)
        self.assertEqual(result["stats"]["point_contact_count"], 1)
        self.assertTrue(verify_triangle_equalities(document, result)["passed"])

    def test_parallel_reversed_lines_are_one_edge_and_one_certificate(self):
        document = bipyramid_document()
        duplicate = deepcopy(document["lines"][0])
        duplicate.update(id="parallel", left=duplicate["right"], right=duplicate["left"])
        document["lines"].append(duplicate)
        result = learn_triangle_equalities(document)
        self.assertEqual(result["equal_names"], [["A", "E"]])
        self.assertEqual(result["stats"]["separator_line_count"], 10)
        self.assertEqual(result["stats"]["neq_edge_count"], 9)
        self.assertTrue(verify_triangle_equalities(document, result)["passed"])

    def test_relabel_and_reorder_follow_side_identity_order_not_name_sort(self):
        document = bipyramid_document()
        replacements = {"A": "z-last", "E": "a-first", "B": "甲", "C": "beta", "D": "3"}
        document["sides"] = [replacements[side] for side in ["E", "A", "D", "B", "C"]]
        for row in document["lines"]:
            row["left"], row["right"] = replacements[row["left"]], replacements[row["right"]]
        result = learn_triangle_equalities(document)
        self.assertEqual(result["certificates"], [{"apices": ["a-first", "z-last"],
                                                   "rim": ["3", "甲", "beta"]}])
        self.assertTrue(verify_triangle_equalities(document, result)["passed"])

    def test_first_of_several_triangles_is_canonical(self):
        # This deliberately nonplanar UNSAT graph tests deterministic witness
        # selection only; the contact language makes no planarity claim.
        document = graph_document(["A", "E", "B", "C", "D", "F"],
                                  [(a, b) for a, b in combinations(range(6), 2) if (a, b) != (0, 1)])
        result = learn_triangle_equalities(document)
        self.assertEqual(result["certificates"], [{"apices": ["A", "E"], "rim": ["B", "C", "D"]}])
        self.assertTrue(verify_triangle_equalities(document, result)["passed"])
        result["certificates"][0]["rim"] = ["B", "C", "F"]
        with self.assertRaises(ValueError):
            verify_triangle_equalities(document, result)

    def test_adjacent_apices_are_explicitly_outside_rule(self):
        document = bipyramid_document()
        document["lines"].append({"id": "ae", "left": "A", "right": "E", "kind": "separator"})
        result = learn_triangle_equalities(document)
        self.assertEqual(result["equal_names"], [])
        self.assertEqual(result["stats"]["eligible_apex_pairs"], 0)
        self.assertEqual(list(literal_solutions(document)), [])

    def test_four_name_assumption_is_essential(self):
        document = bipyramid_document()
        # Five names admit B=1,C=2,D=3,A=4,E=5. The function has no configurable
        # palette and rejects a document pretending to change the schema.
        names = {"B": 1, "C": 2, "D": 3, "A": 4, "E": 5}
        self.assertTrue(all(names[row["left"]] != names[row["right"]] for row in document["lines"]))
        self.assertNotEqual(names["A"], names["E"])
        document["palette"] = [1, 2, 3, 4, 5]
        with self.assertRaises(ValueError):
            learn_triangle_equalities(document)

    def test_anchors_are_allowed_but_never_select_the_learned_equality(self):
        document = bipyramid_document()
        empty = learn_triangle_equalities(document)
        document["anchors"] = {"A": 1, "E": 2}
        anchored = learn_triangle_equalities(document)
        self.assertEqual(empty["equal_names"], anchored["equal_names"])
        self.assertEqual(empty["certificates"], anchored["certificates"])
        self.assertNotEqual(empty["raw_document_sha256"], anchored["raw_document_sha256"])
        self.assertTrue(verify_triangle_equalities(document, anchored)["passed"])

    def test_supplied_candidates_and_equality_are_rejected(self):
        for field, value in [("states", {"A": "1111"}), ("equal_names", [["A", "E"]])]:
            document = bipyramid_document()
            learned = learn_triangle_equalities(document)
            document[field] = value
            with self.assertRaises(ValueError):
                learn_triangle_equalities(document)
            with self.assertRaises(ValueError):
                verify_triangle_equalities(document, learned)
        document = bipyramid_document()
        document.update(states={}, equal_names=[])
        self.assertEqual(learn_triangle_equalities(document)["equal_names"], [["A", "E"]])

    def test_equality_propagates_names_without_merging_side_identity(self):
        document = bipyramid_document()
        document["anchors"] = {"A": 2}
        learned = learn_triangle_equalities(document)
        augmented = deepcopy(document)
        augmented["equal_names"] = learned["equal_names"]
        result = propagate_contacts(augmented)
        self.assertEqual(result["side_order"], document["sides"])
        self.assertEqual(len(result["relations"]), 5)
        self.assertEqual(result["name_states"]["E"]["candidates"], [2])
        self.assertFalse(result["name_states"]["E"]["anchored"])

    def test_verifier_does_not_call_learner(self):
        document = bipyramid_document()
        learned = learn_triangle_equalities(document)
        with patch("scripts.quaternary_triangle_eq.learn_triangle_equalities", side_effect=AssertionError):
            self.assertTrue(verify_triangle_equalities(document, learned)["passed"])

    def test_certificate_and_summary_tampering_are_rejected(self):
        document = bipyramid_document()
        correct = learn_triangle_equalities(document)
        mutations = []
        for field, value in [("version", "unknown"), ("raw_document_sha256", "0" * 64),
                             ("equal_names", []), ("equal_names", [["E", "A"]]),
                             ("certificates", []), ("certificates", [{"apices": ["A", "E"], "rim": ["A", "B", "C"]}]),
                             ("certificates", [{"apices": ["A", "E"], "rim": ["D", "C", "B"]}])]:
            changed = deepcopy(correct)
            changed[field] = value
            mutations.append(changed)
        duplicate = deepcopy(correct)
        duplicate["equal_names"] *= 2
        duplicate["certificates"] *= 2
        mutations.append(duplicate)
        bad_count = deepcopy(correct)
        bad_count["stats"]["certificate_count"] = True
        mutations.append(bad_count)
        extra_field = deepcopy(correct)
        extra_field["oracle"] = "unused"
        mutations.append(extra_field)
        for changed in mutations:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                verify_triangle_equalities(document, changed)

    def test_raw_input_binding_includes_contact_metadata(self):
        document = bipyramid_document()
        learned = learn_triangle_equalities(document)
        document["point_contacts"] = [{"sides": ["A", "E"]}]
        with self.assertRaises(ValueError):
            verify_triangle_equalities(document, learned)

    def test_bad_contact_schema_is_rejected_before_graph_use(self):
        for change in [None, {}, {"sides": ["A", "A"], "lines": []},
                       {"sides": ["A", "E"], "lines": [{"id": "bad", "left": "A", "right": "E", "kind": "bridge"}]}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                learn_triangle_equalities(change)


class TriangleEqualityFiniteArtifactTests(unittest.TestCase):
    """Check exhaustive artifact counts independently and deterministic replay."""

    @classmethod
    def setUpClass(cls):
        """Run the fixed million graph-assignment pairs once for these tests."""
        cls.result = check_rule_soundness()

    def test_complete_labeled_graph_and_assignment_coverage(self):
        result = self.result
        self.assertTrue(result["passed"])
        self.assertEqual(result["graph_count"], 1024)
        self.assertEqual(result["assignments_per_graph"], 1024)
        self.assertEqual(result["graph_assignment_pairs"], 1048576)
        self.assertEqual([row["graph_mask"] for row in result["per_graph"]], list(range(1024)))
        self.assertTrue(all(row["literal_assignments_checked"] == 1024 for row in result["per_graph"]))
        self.assertEqual(result["graphs_without_legal_assignments"], 1)
        self.assertFalse(result["scope"]["color_symmetry_reduction"])
        self.assertFalse(result["scope"]["vertex_symmetry_reduction"])
        self.assertFalse(result["scope"]["oracle_used"])
        self.assertEqual(result["scope"]["anchors"], {})

    def test_legality_total_by_independent_assignment_first_count(self):
        # For each assignment, every subset of its unequal pairs is precisely
        # one graph that it colors legally. This reverses the main graph-first
        # loop and provides an independent combinatorial count of all legal pairs.
        total = sum(2 ** sum(colors[a] != colors[b] for a, b in combinations(range(5), 2))
                    for colors in product((1, 2, 3, 4), repeat=5))
        self.assertEqual(self.result["total_legal_assignments"], total)
        self.assertEqual(sum(row["legal_assignments"] for row in self.result["per_graph"]), total)
        self.assertEqual(self.result["graphs_with_certificates"], 10)
        self.assertEqual(self.result["certificate_count"], 10)
        self.assertEqual(self.result["legal_assignments_in_certified_graphs"], 240)
        self.assertEqual(self.result["eq_projection_checks"], 240)

    def test_artifact_is_deterministic_and_small_counts_are_correct(self):
        self.assertEqual(self.result, check_rule_soundness())
        rows = self.result["per_graph"]
        self.assertEqual(rows[0]["legal_assignments"], 4 ** 5)
        self.assertEqual(rows[1]["legal_assignments"], 4 ** 4 * 3)
        self.assertEqual(rows[-1]["legal_assignments"], 0)
        self.assertTrue(all(len(row["learning_sha256"]) == 64 for row in rows))
        self.assertEqual(len(self.result["per_graph_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()

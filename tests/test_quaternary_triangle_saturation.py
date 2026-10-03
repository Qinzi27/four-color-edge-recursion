"""Literal certificate controls for triangle saturation, independent of solving."""

from copy import deepcopy
from itertools import combinations, product
import unittest

from scripts.quaternary_triangle_saturation import (
    STATISTIC_KEYS, VERSION, find_triangle_saturations,
)


def make_document(sides, edges=(), **extra):
    """Build a small synthetic contact input with distinct physical line IDs."""
    return {"sides": sides, "lines": [
        {"id": f"e{i}", "left": a, "right": b, "kind": "separator"}
        for i, (a, b) in enumerate(edges)], **extra}


def triangle_document(**extra):
    """A target T adjacent to the literal A/B/C triangle (a four-vertex clique)."""
    return make_document(["T", "A", "B", "C"],
                         list(combinations(["T", "A", "B", "C"], 2)), **extra)


def lifted_document(**extra):
    """The T class's three adjacencies use different equal physical identities."""
    raw = make_document(["T", "T2", "A", "B", "C"],
                        [("A", "B"), ("A", "C"), ("B", "C"),
                         ("T", "A"), ("T2", "B"), ("T2", "C")], **extra)
    return raw


class TriangleSaturationTests(unittest.TestCase):
    """Structural pattern discovery never supplies its own domain/EQ premises."""

    def test_literal_triangle_forces_fourth_color_with_six_physical_witnesses(self):
        raw = triangle_document()
        domains = [[1, 2, 3, 4]] + [[2, 3, 4] for _ in range(3)]
        result = find_triangle_saturations(raw, domains, [])
        self.assertEqual(result["version"], VERSION)
        self.assertEqual(result["classes"], [["T"], ["A"], ["B"], ["C"]])
        self.assertEqual(result["certificates"], [{
            "target": "T", "triangle": ["A", "B", "C"], "excluded_color": 1,
            "removed_colors": [2, 3, 4],
            "edges": [["A", "B"], ["A", "C"], ["B", "C"],
                      ["T", "A"], ["T", "B"], ["T", "C"]],
        }])
        self.assertEqual(set(result["statistics"]), set(STATISTIC_KEYS))
        self.assertEqual(result["statistics"]["physical_witness_edges"], 6)
        self.assertEqual(result["statistics"]["certificates_found"], 1)

    def test_literal_enumeration_preserves_all_domain_and_real_edge_solutions(self):
        raw = triangle_document()
        for q in (1, 2, 3, 4):
            domains = [[1, 2, 3, 4]] + [[c for c in (1, 2, 3, 4) if c != q] for _ in range(3)]
            result = find_triangle_saturations(raw, domains, [])
            legal = [assignment for assignment in product(*domains) if len(set(assignment)) == 4]
            self.assertEqual(len(legal), 6)
            self.assertTrue(all(assignment[0] == q for assignment in legal))
            self.assertEqual(result["certificates"][0]["removed_colors"], domains[1])

    def test_eq_quotient_keeps_face_identity_and_actual_edge_endpoints(self):
        raw = lifted_document()
        domains = [[1, 2, 3, 4], [1, 2, 3, 4]] + [[2, 3, 4] for _ in range(3)]
        equal = [["T2", "T"], ["T", "T2"], ["T", "T"]]
        before = deepcopy((raw, domains, equal))
        result = find_triangle_saturations(raw, domains, equal)
        self.assertEqual(result["classes"][0], ["T", "T2"])
        self.assertEqual(result["certificates"][0]["edges"][-3:],
                         [["T", "A"], ["T2", "B"], ["T2", "C"]])
        self.assertEqual((raw, domains, equal), before)
        self.assertEqual(find_triangle_saturations(raw, domains, [])["certificates"], [])

    def test_witness_orientation_and_tie_break_depend_on_class_not_line_order(self):
        raw = lifted_document()
        raw["sides"] = ["A", "B", "C", "T", "T2"]
        raw["lines"].append({"id": "extra", "left": "B", "right": "T", "kind": "separator"})
        domains = [[2, 3, 4] for _ in range(3)] + [[1, 2, 3, 4], [1, 2, 3, 4]]
        a = find_triangle_saturations(raw, domains, [["T", "T2"]])
        raw["lines"].reverse()
        b = find_triangle_saturations(raw, domains, [["T2", "T"]])
        self.assertEqual(a["certificates"], b["certificates"])
        self.assertEqual(a["certificates"][0]["edges"][-2], ["T", "B"])
        self.assertNotEqual(a["raw_document_sha256"], b["raw_document_sha256"])
        self.assertNotEqual(a["equal_names_sha256"], b["equal_names_sha256"])

    def test_missing_triangle_or_target_edge_has_no_substitute_from_logical_neq(self):
        for omitted in range(6):
            raw = triangle_document()
            edge = raw["lines"].pop(omitted)
            raw["different_names"] = [[edge["left"], edge["right"]]]
            raw["point_contacts"] = [{"sides": [edge["left"], edge["right"]]}]
            domains = [[1, 2, 3, 4]] + [[2, 3, 4] for _ in range(3)]
            self.assertEqual(find_triangle_saturations(raw, domains, [])["certificates"], [])

    def test_relaxing_one_triangle_domain_or_already_restricted_target_changes_nothing(self):
        raw = triangle_document()
        for relaxed in (1, 2, 3):
            domains = [[1, 2, 3, 4]] + [[2, 3, 4] for _ in range(3)]
            domains[relaxed] = [1, 2, 3, 4]
            self.assertEqual(find_triangle_saturations(raw, domains, [])["certificates"], [])
        for target in ([1], []):
            domains = [target] + [[2, 3, 4] for _ in range(3)]
            # An empty target has no further deletion; vacuous certificates
            # for other classes are valid under that already UNSAT premise.
            result = find_triangle_saturations(raw, domains, [])
            self.assertFalse(any(certificate["target"] == "T" for certificate in result["certificates"]))

    def test_target_can_lose_every_color_but_rule_does_not_claim_an_original_graph_conflict(self):
        raw = triangle_document()
        result = find_triangle_saturations(raw, [[2, 3, 4] for _ in range(4)], [])
        self.assertEqual(len(result["certificates"]), 4)
        self.assertTrue(all(row["removed_colors"] == [2, 3, 4] for row in result["certificates"]))
        self.assertNotIn("status", result)

    def test_strict_domain_shapes_literal_types_and_eq_references(self):
        raw = triangle_document()
        good = [[1, 2, 3, 4]] + [[2, 3, 4] for _ in range(3)]
        for bad in (None, (), good[:-1], [[True]] + good[1:], [[0]] + good[1:],
                    [[2, 1]] + good[1:], [[1, 1]] + good[1:], [(1, 2)] + good[1:]):
            with self.subTest(domain=bad), self.assertRaises(ValueError):
                find_triangle_saturations(raw, bad, [])
        for bad in (None, (), [["T"]], [["T", "unknown"]], [("T", "A")], [["T", True]]):
            with self.subTest(eq=bad), self.assertRaises(ValueError):
                find_triangle_saturations(raw, good, bad)

    def test_mismatched_eq_domains_or_internal_physical_edges_reject(self):
        raw = lifted_document()
        with self.assertRaisesRegex(ValueError, "same domain"):
            find_triangle_saturations(raw, [[1, 2, 3, 4]] + [[2, 3, 4] for _ in range(4)], [["T", "T2"]])
        with self.assertRaisesRegex(ValueError, "inside an equality class"):
            find_triangle_saturations(triangle_document(), [[1, 2, 3, 4] for _ in range(4)], [["T", "A"]])


if __name__ == "__main__":
    unittest.main()

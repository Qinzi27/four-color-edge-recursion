"""Physical-edge, palette and literal-evidence tests for odd-wheel discovery."""

from copy import deepcopy
from itertools import product
import unittest

from scripts.quaternary_odd_wheel import VERSION, _digest, find_odd_wheel


def wheel_document(rim_length=5, **extra):
    """Build a synthetic simple wheel, unrelated to the frozen 19-face cases."""
    rim = [f"R{i}" for i in range(rim_length)]
    edges = [("C", side) for side in rim]
    edges += [(rim[i], rim[(i + 1) % rim_length]) for i in range(rim_length)]
    return {"sides": ["C"] + rim,
            "lines": [{"id": f"e{i}", "left": a, "right": b, "kind": "separator"}
                      for i, (a, b) in enumerate(edges)], **extra}


class OddWheelTests(unittest.TestCase):
    """A certificate proves incompatibility under its exact domain premises."""

    def test_three_palette_wheel_has_canonical_simple_odd_rim(self):
        raw = wheel_document()
        domains = [[2, 3, 4] for _ in raw["sides"]]
        result = find_odd_wheel(raw, domains)
        self.assertEqual(result["version"], VERSION)
        self.assertEqual(result["certificate"], {
            "center": "C", "rim": [f"R{i}" for i in range(5)], "excluded_color": 1})
        self.assertEqual(result["raw_document_sha256"], _digest(raw))
        self.assertEqual(result["domains_sha256"], _digest(domains))
        self.assertEqual(result["statistics"]["odd_cycles_found"], 1)
        self.assertTrue(all(type(n) is int and n >= 0 for n in result["statistics"].values()))

    def test_every_excluded_color_and_triangle_case(self):
        raw = wheel_document(3)
        for excluded in range(1, 5):
            palette = [color for color in range(1, 5) if color != excluded]
            certificate = find_odd_wheel(raw, [palette[:] for _ in raw["sides"]])["certificate"]
            self.assertEqual(certificate["excluded_color"], excluded)
            self.assertEqual(len(certificate["rim"]), 3)

    def test_even_rim_and_missing_physical_edges_are_negative(self):
        for raw in (wheel_document(4), wheel_document(6)):
            self.assertIsNone(find_odd_wheel(raw, [[1, 2, 3] for _ in raw["sides"]])["certificate"])
        for edge_index in (0, 5):
            raw = wheel_document()
            raw["lines"].pop(edge_index)
            self.assertIsNone(find_odd_wheel(raw, [[1, 2, 3] for _ in raw["sides"]])["certificate"])

    def test_one_unblocked_wheel_vertex_prevents_this_certificate(self):
        raw = wheel_document()
        for vertex in range(6):
            domains = [[2, 3, 4] for _ in raw["sides"]]
            domains[vertex] = [1, 2, 3, 4]
            self.assertIsNone(find_odd_wheel(raw, domains)["certificate"])

    def test_logical_neq_eq_point_and_bridge_do_not_replace_physical_edges(self):
        raw = wheel_document()
        edge = raw["lines"].pop(5)
        pair = [edge["left"], edge["right"]]
        raw.update(different_names=[pair], equal_names=[pair], point_contacts=[{"sides": pair}])
        raw["lines"].append({"id": "bridge", "left": "C", "right": "C", "kind": "bridge"})
        self.assertIsNone(find_odd_wheel(raw, [[2, 3, 4] for _ in raw["sides"]])["certificate"])

    def test_duplicate_and_reversed_lines_preserve_witness(self):
        raw = wheel_document()
        domains = [[2, 3, 4] for _ in raw["sides"]]
        expected = find_odd_wheel(raw, domains)
        raw["lines"] = list(reversed(raw["lines"]))
        raw["lines"].append({"id": "duplicate", "left": "R0", "right": "C", "kind": "separator"})
        actual = find_odd_wheel(raw, domains)
        self.assertEqual(actual["certificate"], expected["certificate"])
        self.assertEqual(actual["statistics"], expected["statistics"])
        self.assertNotEqual(actual["raw_document_sha256"], expected["raw_document_sha256"])

    def test_palette_is_common_not_merely_three_colors_per_vertex(self):
        raw = wheel_document()
        domains = [[1, 2, 3], [2, 3, 4], [1, 2, 3], [2, 3, 4], [1, 2, 3], [2, 3, 4]]
        self.assertIsNone(find_odd_wheel(raw, domains)["certificate"])

    def test_disconnected_eligible_neighbors_and_nonroot_common_ancestor(self):
        raw = {"sides": ["C", "A", "B", "D", "E", "F"], "lines": []}
        # A-B-D is a tail into the triangle D-E-F, testing the LCA truncation.
        edges = [("C", side) for side in raw["sides"][1:]]
        edges += [("A", "B"), ("B", "D"), ("D", "E"), ("E", "F"), ("F", "D")]
        raw["lines"] = [{"id": str(i), "left": a, "right": b, "kind": "separator"}
                        for i, (a, b) in enumerate(edges)]
        certificate = find_odd_wheel(raw, [[2, 3, 4] for _ in raw["sides"]])["certificate"]
        self.assertEqual(certificate["rim"], ["D", "E", "F"])

    def test_strict_domain_schema_rejects_bools_duplicates_and_wrong_alignment(self):
        raw = wheel_document(3)
        for bad in (None, {}, [[1, 2, 3]], [[1, 2, 3]] * 5,
                    [[True, 2, 3]] * 4, [[1, 1, 3]] * 4, [[3, 2, 1]] * 4,
                    [(1, 2, 3)] * 4, [[0, 2, 3]] * 4, [[1.0, 2, 3]] * 4):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                find_odd_wheel(raw, bad)

    def test_full_document_schema_is_checked(self):
        for change in ({"unknown": 1}, {"anchors": {"C": True}}, {"different_names": [["C", "C"]]}):
            raw = wheel_document(3, **change)
            with self.assertRaises(ValueError):
                find_odd_wheel(raw, [[1, 2, 3]] * 4)

    def test_no_witness_still_binds_complete_input_and_empty_domains_are_literal(self):
        raw = {"sides": ["A"], "lines": [], "anchors": {"A": 1}}
        result = find_odd_wheel(raw, [[]])
        self.assertIsNone(result["certificate"])
        self.assertEqual(result["raw_document_sha256"], _digest(raw))
        self.assertEqual(result["domains_sha256"], _digest([[]]))
        self.assertEqual(result["statistics"]["palettes_examined"], 4)

    def test_input_does_not_alias_evidence_and_repeated_calls_are_identical(self):
        raw = wheel_document()
        domains = [[2, 3, 4] for _ in raw["sides"]]
        before = deepcopy((raw, domains))
        first = find_odd_wheel(raw, domains)
        self.assertEqual(first, find_odd_wheel(raw, domains))
        first["certificate"]["rim"].clear()
        self.assertEqual((raw, domains), before)

    def test_finite_literal_assignments_confirm_positive_and_negative_controls(self):
        for rim_length in (3, 4, 5):
            raw = wheel_document(rim_length)
            sides = raw["sides"]
            for excluded in range(1, 5):
                palette = [color for color in range(1, 5) if color != excluded]
                domains = [palette[:] for _ in sides]
                legal_count = 0
                for values in product(palette, repeat=len(sides)):
                    assignment = dict(zip(sides, values))
                    legal_count += all(assignment[line["left"]] != assignment[line["right"]]
                                       for line in raw["lines"])
                certificate = find_odd_wheel(raw, domains)["certificate"]
                self.assertEqual(certificate is not None, legal_count == 0)
                self.assertEqual(legal_count == 0, rim_length % 2 == 1)


if __name__ == "__main__":
    unittest.main()

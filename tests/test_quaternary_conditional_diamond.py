"""Literal domain, physical-edge and certificate controls for conditional EQ."""

from copy import deepcopy
from itertools import product
import unittest

from scripts.quaternary_conditional_diamond import (
    STATISTIC_KEYS, VERSION, _digest, find_conditional_diamonds,
)


def diamond_document(**extra):
    """A synthetic K4 minus U-V, independent of the archived development map."""
    edges = [("U", "A"), ("U", "B"), ("V", "A"), ("V", "B"), ("A", "B")]
    return {"sides": ["U", "V", "A", "B"],
            "lines": [{"id": str(i), "left": a, "right": b, "kind": "separator"}
                      for i, (a, b) in enumerate(edges)], **extra}


def literal_matrix(document, domains):
    """Build only domain products and real edge inequalities, with no closure."""
    sides = document["sides"]
    edges = {frozenset((line["left"], line["right"])) for line in document["lines"]
             if line["kind"] == "separator"}
    return [[sum(1 << (4 * (a - 1) + b - 1)
                 for a in domains[i] for b in domains[j]
                 if (i != j or a == b)
                 and (frozenset((sides[i], sides[j])) not in edges or a != b))
             for j in range(len(sides))] for i in range(len(sides))]


class ConditionalDiamondTests(unittest.TestCase):
    """The rule requires a common palette, not merely small individual domains."""

    def test_common_three_palette_returns_one_exact_certificate_and_bindings(self):
        raw, domains = diamond_document(), [[2, 3, 4] for _ in range(4)]
        matrix = literal_matrix(raw, domains)
        result = find_conditional_diamonds(raw, domains, matrix)
        self.assertEqual(result["version"], VERSION)
        self.assertEqual(result["certificates"], [
            {"pair": ["U", "V"], "edge": ["A", "B"], "excluded_color": 1}])
        for field, value in (("raw_document", raw), ("domains", domains), ("relations", matrix)):
            self.assertEqual(result[field + "_sha256"], _digest(value))
        self.assertEqual(set(result["statistics"]), set(STATISTIC_KEYS))
        self.assertEqual(result["statistics"]["certificates_found"], 1)
        self.assertTrue(all(type(n) is int and n >= 0 for n in result["statistics"].values()))

    def test_each_excluded_color_has_nonvacuous_equal_legal_solutions(self):
        raw = diamond_document()
        for excluded in range(1, 5):
            palette = [color for color in range(1, 5) if color != excluded]
            domains = [palette[:] for _ in range(4)]
            result = find_conditional_diamonds(raw, domains, literal_matrix(raw, domains))
            self.assertEqual(result["certificates"][0]["excluded_color"], excluded)
            legal = [values for values in product(palette, repeat=4)
                     if all(dict(zip(raw["sides"], values))[line["left"]]
                            != dict(zip(raw["sides"], values))[line["right"]]
                            for line in raw["lines"])]
            self.assertEqual(len(legal), 6)
            self.assertTrue(all(values[0] == values[1] for values in legal))

    def test_four_colors_allow_unequal_opposite_vertices(self):
        raw, domains = diamond_document(), [[1, 2, 3, 4] for _ in range(4)]
        self.assertEqual(find_conditional_diamonds(raw, domains, literal_matrix(raw, domains))[
            "certificates"], [])
        coloring = {"U": 1, "V": 2, "A": 3, "B": 4}
        self.assertTrue(all(coloring[line["left"]] != coloring[line["right"]]
                            for line in raw["lines"]))

    def test_one_relaxed_vertex_or_no_common_excluded_color_blocks_rule(self):
        raw = diamond_document()
        for vertex in range(4):
            domains = [[2, 3, 4] for _ in range(4)]
            domains[vertex] = [1, 2, 3, 4]
            self.assertEqual(find_conditional_diamonds(raw, domains, literal_matrix(raw, domains))[
                "certificates"], [])
        domains = [[1, 2, 3], [2, 3, 4], [1, 2, 3], [2, 3, 4]]
        self.assertEqual(find_conditional_diamonds(raw, domains, literal_matrix(raw, domains))[
            "certificates"], [])

    def test_each_missing_real_edge_blocks_rule_even_with_logical_replacement(self):
        for edge_index in range(5):
            raw = diamond_document()
            missing = raw["lines"].pop(edge_index)
            pair = [missing["left"], missing["right"]]
            raw.update(equal_names=[pair], different_names=[pair], point_contacts=[{"sides": pair}])
            raw["lines"].append({"id": "bridge", "left": "U", "right": "U", "kind": "bridge"})
            domains = [[2, 3, 4] for _ in range(4)]
            self.assertEqual(find_conditional_diamonds(raw, domains, literal_matrix(raw, domains))[
                "certificates"], [])

    def test_extra_real_opposite_edge_is_allowed_and_certifies_conditional_conflict(self):
        raw = diamond_document()
        raw["lines"].append({"id": "uv", "left": "U", "right": "V", "kind": "separator"})
        domains = [[2, 3, 4] for _ in range(4)]
        result = find_conditional_diamonds(raw, domains, literal_matrix(raw, domains))
        self.assertEqual(len(result["certificates"]), 6)
        self.assertEqual(result["certificates"][0]["pair"], ["U", "V"])

    def test_diagonal_only_and_empty_relations_skip_even_without_explicit_eq(self):
        raw, domains = diamond_document(), [[2, 3, 4] for _ in range(4)]
        for mask in (0, sum(1 << (5 * (a - 1)) for a in domains[0])):
            matrix = literal_matrix(raw, domains)
            matrix[0][1] = matrix[1][0] = mask
            self.assertEqual(find_conditional_diamonds(raw, domains, matrix)["certificates"], [])

    def test_side_order_controls_pair_order_and_first_color_then_edge(self):
        raw = diamond_document()
        raw["sides"] = ["V", "U", "B", "A", "X", "Y"]
        raw["lines"] += [{"id": f"extra{i}", "left": a, "right": b, "kind": "separator"}
                         for i, (a, b) in enumerate([
                             ("U", "X"), ("U", "Y"), ("V", "X"), ("V", "Y"), ("X", "Y")])]
        domains = [[2, 3] for _ in range(6)]
        result = find_conditional_diamonds(raw, domains, literal_matrix(raw, domains))
        self.assertEqual(result["certificates"], [
            {"pair": ["V", "U"], "edge": ["B", "A"], "excluded_color": 1}])
        raw["lines"].reverse()
        raw["lines"].append({"id": "dup", "left": "A", "right": "B", "kind": "separator"})
        repeated = find_conditional_diamonds(raw, domains, literal_matrix(raw, domains))
        self.assertEqual(repeated["certificates"], result["certificates"])
        self.assertEqual(repeated["statistics"], result["statistics"])

    def test_strict_domains_reject_bool_duplicates_wrong_shape_and_nonintegers(self):
        raw = diamond_document()
        matrix = literal_matrix(raw, [[2, 3, 4] for _ in range(4)])
        for bad in (None, {}, [[2, 3, 4]], [[2, 3, 4]] * 5,
                    [[True, 2, 3]] * 4, [[1, 1, 3]] * 4, [[3, 2, 1]] * 4,
                    [(1, 2, 3)] * 4, [[0, 2, 3]] * 4, [[1.0, 2, 3]] * 4):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                find_conditional_diamonds(raw, bad, matrix)

    def test_matrix_shape_type_bounds_transpose_diagonal_and_domain_containment(self):
        raw, domains = diamond_document(), [[2, 3, 4] for _ in range(4)]
        good = literal_matrix(raw, domains)
        bad_values = [None, {}, good[:3], [row[:3] for row in good], [tuple(row) for row in good]]
        for value in (True, -1, 65536, 1.0, "1"):
            bad = deepcopy(good)
            bad[0][1] = value
            bad_values.append(bad)
        for first, second, mask in ((0, 0, 0), (0, 1, good[0][1] ^ (1 << 6)), (0, 1, 1)):
            bad = deepcopy(good)
            bad[first][second] = mask
            bad_values.append(bad)
        for bad in bad_values:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                find_conditional_diamonds(raw, domains, bad)

    def test_full_document_validation_rejects_unknown_or_malformed_premises(self):
        for extra in ({"unknown": 1}, {"anchors": {"U": True}}, {"different_names": [["U", "U"]]}):
            raw = diamond_document(**extra)
            domains = [[2, 3, 4] for _ in range(4)]
            with self.assertRaises(ValueError):
                find_conditional_diamonds(raw, domains, literal_matrix(raw, domains))

    def test_empty_domains_are_literal_and_digests_do_not_alias_inputs(self):
        raw = {"sides": ["U"], "lines": []}
        self.assertEqual(find_conditional_diamonds(raw, [[]], [[0]])["certificates"], [])
        raw, domains = diamond_document(), [[2, 3, 4] for _ in range(4)]
        matrix = literal_matrix(raw, domains)
        original = deepcopy((raw, domains, matrix))
        first = find_conditional_diamonds(raw, domains, matrix)
        self.assertEqual(first, find_conditional_diamonds(raw, domains, matrix))
        first["certificates"][0]["pair"].clear()
        self.assertEqual((raw, domains, matrix), original)


if __name__ == "__main__":
    unittest.main()

"""Synthetic exact-equivalence checks for the necessary-condition prefilter.

These tests do not use production archives, raw-color oracles, or algorithm
choices. They exercise the literal detector boundary, including empty domains
and conditional premises that may already be unsatisfiable.
"""

from copy import deepcopy
from itertools import combinations, product
from random import Random
import unittest

from scripts.quaternary_triangle_saturation import find_triangle_saturations
from scripts.quaternary_triangle_saturation_prefilter import (
    IMPLEMENTATION_VERSION, WORK_STATISTIC_KEYS, find_triangle_saturations_prefilter,
)


def document(sides, edges=(), **extra):
    """Build a distinct-side synthetic document with literal separator IDs."""
    return {"sides": sides, "lines": [
        {"id": f"e{i}", "left": a, "right": b, "kind": "separator"}
        for i, (a, b) in enumerate(edges)], **extra}


def clique_document():
    """The smallest graph containing one target and its physical triangle."""
    sides = ["T", "A", "B", "C"]
    return document(sides, combinations(sides, 2))


def domain_subsets():
    """All sixteen sorted literal domains, including empty and full domains."""
    return [[color for color in range(1, 5) if mask & (1 << (color - 1))]
            for mask in range(16)]


class TriangleSaturationPrefilterTests(unittest.TestCase):
    """Preserve old evidence and separately account for actual loop work."""

    def assertEquivalent(self, raw, domains, equal=()):
        """Compare complete evidence and telemetry without mutating inputs."""
        equal = list(equal)
        before = deepcopy((raw, domains, equal))
        old = find_triangle_saturations(raw, domains, equal)
        log = [{"existing": "preserved"}]
        result = find_triangle_saturations_prefilter(raw, domains, equal, work_log=log)
        self.assertEqual(result, old)
        self.assertEqual((raw, domains, equal), before)
        self.assertEqual(log[0], {"existing": "preserved"})
        self.assertEqual(len(log), 2)
        record = log[1]
        self.assertEqual(set(record), {"implementation", "raw_document_sha256", "domains_sha256",
                                      "equal_names_sha256", "statistics"})
        self.assertEqual(record["implementation"], IMPLEMENTATION_VERSION)
        for key in ("raw_document_sha256", "domains_sha256", "equal_names_sha256"):
            self.assertEqual(record[key], result[key])
        work = record["statistics"]
        self.assertEqual(set(work), set(WORK_STATISTIC_KEYS))
        self.assertTrue(all(type(value) is int and value >= 0 for value in work.values()))
        self.assertEqual(work["triangles_skipped"] + work["triangles_enumerated"],
                         result["statistics"]["triangles_examined"])
        self.assertLessEqual(work["skipped_palette_checks"], work["eligible_palette_checks"])
        return result, work

    def test_full_domains_skip_every_clique_triple_with_exact_virtual_counts(self):
        result, work = self.assertEquivalent(clique_document(), [[1, 2, 3, 4]] * 4)
        self.assertEqual(result["certificates"], [])
        self.assertEqual(work, {
            "eligible_palette_checks": 16, "neighbor_membership_tests": 48,
            "skipped_palette_checks": 16, "triangles_skipped": 16, "triangles_enumerated": 0,
        })

    def test_successful_certificate_keeps_order_after_skipped_palettes(self):
        for excluded in range(1, 5):
            palette = [c for c in range(1, 5) if c != excluded]
            result, work = self.assertEquivalent(clique_document(), [[1, 2, 3, 4]] + [palette] * 3)
            self.assertEqual(result["certificates"][0]["excluded_color"], excluded)
            self.assertEqual(result["certificates"][0]["triangle"], ["A", "B", "C"])
            self.assertEqual(work["triangles_enumerated"], 1)

    def test_every_literal_domain_as_target_and_uniform_neighbor_domain(self):
        # This is an exhaustive 16 x 16 paired-domain family, not all 16^4
        # independently assigned domains or an exhaustive graph-family claim.
        for target, neighbors in product(domain_subsets(), repeat=2):
            with self.subTest(target=target, neighbors=neighbors):
                self.assertEquivalent(clique_document(), [target] + [neighbors] * 3)

    def test_all_four_vertex_graphs_with_every_target_domain(self):
        sides = ["T", "A", "B", "C"]
        possible = list(combinations(sides, 2))
        for mask in range(64):
            raw = document(sides, [edge for bit, edge in enumerate(possible) if mask & (1 << bit)])
            for target in domain_subsets():
                self.assertEquivalent(raw, [target, [], [2], [2, 3, 4]])

    def test_q_absent_from_target_and_non_three_element_domains_still_certify(self):
        result, work = self.assertEquivalent(clique_document(), [[2], [2], [], [3, 4]])
        target = next(item for item in result["certificates"] if item["target"] == "T")
        self.assertEqual(target["excluded_color"], 1)
        self.assertEqual(target["removed_colors"], [2])
        self.assertGreater(work["triangles_enumerated"], 0)

    def test_low_degree_and_empty_target_do_not_count_nonexistent_triples(self):
        raw = document(["A", "B", "C"], [("A", "B"), ("B", "C")])
        _, work = self.assertEquivalent(raw, [[], [1], [2, 3, 4]])
        self.assertEqual(work["eligible_palette_checks"], 7)
        self.assertEqual(work["neighbor_membership_tests"], 10)
        self.assertEqual(work["skipped_palette_checks"], 7)
        self.assertEqual(work["triangles_skipped"], 0)
        self.assertEqual(work["triangles_enumerated"], 0)

    def test_eq_classes_use_actual_members_and_deterministic_physical_witness(self):
        raw = document(["T", "T2", "A", "B", "C"],
                       [("A", "B"), ("A", "C"), ("B", "C"),
                        ("T", "A"), ("T2", "B"), ("T2", "C"), ("B", "T")])
        eq = [["T2", "T"], ["T", "T2"], ["T", "T"]]
        for target, palette in product(domain_subsets(), repeat=2):
            self.assertEquivalent(raw, [target, target] + [palette] * 3, eq)
        domains = [[1, 2, 3, 4]] * 2 + [[2, 3, 4]] * 3
        result, _ = self.assertEquivalent(raw, domains, eq)
        self.assertEqual(result["certificates"][0]["edges"][-2], ["T", "B"])
        raw["lines"].reverse()
        reversed_result, _ = self.assertEquivalent(raw, domains, list(reversed(eq)))
        self.assertEqual(result["certificates"], reversed_result["certificates"])

    def test_logical_neq_and_point_contacts_never_replace_missing_physical_edge(self):
        for omitted in range(6):
            raw = clique_document()
            edge = raw["lines"].pop(omitted)
            raw["different_names"] = [[edge["left"], edge["right"]]]
            raw["point_contacts"] = [{"sides": [edge["left"], edge["right"]]}]
            result, _ = self.assertEquivalent(raw, [[1, 2, 3, 4]] + [[2, 3, 4]] * 3)
            self.assertEqual(result["certificates"], [])

    def test_shared_eq_neighborhood_counts_classes_not_individual_face_members(self):
        raw = document(["T", "A", "A2", "B"],
                       [("T", "A"), ("T", "A2"), ("T", "B"), ("A", "B")])
        result, work = self.assertEquivalent(raw, [[1, 2, 3, 4]] + [[2, 3, 4]] * 3,
                                             [["A", "A2"]])
        self.assertEqual(result["certificates"], [])
        self.assertEqual(work["triangles_enumerated"], 0)

    def test_seeded_mixed_graphs_domains_and_line_orders_match_without_cache(self):
        rng = Random(20261003)
        subsets = domain_subsets()
        for size in range(4, 9):
            for _ in range(20):
                sides = [f"s{i}" for i in range(size)]
                edges = [edge for edge in combinations(sides, 2) if rng.random() < 0.65]
                rng.shuffle(edges)
                raw = document(sides, edges)
                domains = [list(rng.choice(subsets)) for _ in sides]
                self.assertEquivalent(raw, domains)

    def test_invalid_inputs_fail_with_old_error_and_do_not_append_telemetry(self):
        raw = clique_document()
        good = [[1, 2, 3, 4]] * 4
        cases = [(raw, value, []) for value in
                 (None, (), good[:-1], [[True]] + good[1:], [[1, 1]] + good[1:])]
        cases += [(raw, good, eq) for eq in (None, (), [["T"]], [["T", "unknown"]], [["T", "A"]])]
        for data, domains, equal in cases:
            log = []
            with self.assertRaises(ValueError) as old_error:
                find_triangle_saturations(data, domains, equal)
            with self.assertRaises(ValueError) as new_error:
                find_triangle_saturations_prefilter(data, domains, equal, work_log=log)
            self.assertEqual(str(new_error.exception), str(old_error.exception))
            self.assertEqual(log, [])
        with self.assertRaisesRegex(ValueError, "work_log"):
            find_triangle_saturations_prefilter(raw, good, [], work_log={})

    def test_optional_log_does_not_change_evidence_or_leave_cross_call_state(self):
        raw = clique_document()
        domains = [[1, 2, 3, 4]] + [[2, 3, 4]] * 3
        expected = find_triangle_saturations(raw, domains, [])
        self.assertEqual(find_triangle_saturations_prefilter(raw, domains, []), expected)
        log = []
        self.assertEqual(find_triangle_saturations_prefilter(raw, domains, [], work_log=log), expected)
        raw["lines"].pop()
        result, _ = self.assertEquivalent(raw, domains)
        self.assertEqual(result["certificates"], [])
        self.assertEqual(len(log), 1)


if __name__ == "__main__":
    unittest.main()

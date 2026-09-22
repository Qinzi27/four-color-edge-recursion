"""Preserve the distinction between conditional obstruction and reached failure."""

from copy import deepcopy
import unittest

from scripts.diagnose_conditional_obstruction import (
    audit_rotation, build_obstruction, certify_common_odd_cycle, diagnose,
)


class ConditionalObstructionTests(unittest.TestCase):
    """Check literal witnesses, an exhaustive negative result, and planar input."""

    def test_five_cycle_obstruction_has_verified_before_and_after_evidence(self):
        """A legal commitment set becomes impossible while pair checks allow it."""
        report = diagnose(5)
        self.assertTrue(report["all_passed"])
        self.assertEqual(report["before_commit"]["status"], "sat")
        self.assertEqual(report["after_commit"]["status"], "unsat")
        self.assertEqual(report["unconditional_same_name_witness"]["status"], "sat")
        self.assertEqual(report["domains_before_commit"][1], [1, 2])
        self.assertEqual(report["same_name_query"]["status"], "inconclusive")
        self.assertEqual(report["complete_enumeration"]["target_count"], 20)
        self.assertEqual(report["complete_enumeration"]["assignments_checked"], 4 ** 6)
        self.assertEqual(report["current_policy_reachability"], "not_established")
        self.assertEqual(report["geometric_mother_drawing"], "not_supplied")
        self.assertEqual(report["global_equality_certificate"]["status"], "proved_equal")
        self.assertTrue(all(audit["conclusive"] for audit in report["exact_audits"]))

    def test_seven_cycle_is_a_distinct_finite_family_member(self):
        """The same issue is checked on a longer odd rim without extrapolation."""
        report = diagnose(7)
        self.assertEqual(report["complete_enumeration"]["target_count"], 84)
        self.assertEqual(report["complete_enumeration"]["assignments_checked"], 4 ** 8)
        self.assertEqual(report["embedding_audit"]["euler_characteristic"], 2)

    def test_constraint_embedding_is_a_verified_rotation_not_a_drawing_claim(self):
        """Euler evidence uses every actual oriented graph edge."""
        for cycle_size in (5, 7, 9, 15):
            problem = build_obstruction(cycle_size)
            audit = audit_rotation(problem)
            self.assertEqual(len(audit["faces"]), 2 * cycle_size)
            self.assertEqual(sum(map(len, audit["faces"])), 2 * len(problem["edges"]))
        broken = deepcopy(build_obstruction())
        broken["rotation_by_vertex"][0].pop()
        with self.assertRaises(AssertionError):
            audit_rotation(broken)

    def test_invalid_family_and_exhaustive_enumeration_guard(self):
        """Odd rim size and the bounded test scope cannot silently drift."""
        for size in (True, None, 3, 4, 6, 1.5, "5"):
            with self.subTest(size=size), self.assertRaises(ValueError):
                build_obstruction(size)
        with self.assertRaises(ValueError):
            diagnose(11)

    def test_odd_common_cycle_equality_requires_every_literal_edge(self):
        """Even cycles and invented spokes cannot justify the global equality."""
        problem = build_obstruction(5)
        edges = problem["edges"]
        certificate = certify_common_odd_cycle(8, edges, 0, 1, [2, 3, 4, 5, 6])
        self.assertEqual(certificate["pair"], (0, 1))
        self.assertEqual(len(certificate["common_neighbor_edges"]), 10)
        with self.assertRaises(ValueError):
            certify_common_odd_cycle(8, edges, 0, 1, [2, 3, 4, 5])
        with self.assertRaises(ValueError):
            certify_common_odd_cycle(8, [edge for edge in edges if edge != (0, 2)],
                                     0, 1, [2, 3, 4, 5, 6])
        with self.assertRaises(ValueError):
            certify_common_odd_cycle(8, edges, 0, 1, [2, 3, 4, 5, 2])


if __name__ == "__main__":
    unittest.main()

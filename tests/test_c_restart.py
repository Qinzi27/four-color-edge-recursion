"""Regressions separating proper frozen names from minimum reuse in case C."""

import unittest

from scripts.audit_retained_blocks import unpack_state
from scripts.validate_c_restart import build_report, clique_bound


class CRestartTests(unittest.TestCase):
    """Verify the fixed example without solving arbitrary coloring instances."""

    @classmethod
    def setUpClass(cls):
        """Skip Node here; the standalone report runs its independent oracle."""
        cls.report = build_report(with_node_oracle=False)
        cls.replay = cls.report["declared_left_replay"]

    def test_old_snapshot_is_proper_but_not_minimum(self):
        """342 is a lawful fixed-policy output, not the proposed minimal start."""
        certificate = self.report["minimality_certificates"]["old_fixed_right"]
        self.assertEqual(certificate["used_names"], [1, 2, 3, 4])
        self.assertEqual(certificate["lower_bound_including_outside"], 3)
        self.assertFalse(certificate["attains_bound"])
        self.assertEqual(self.report["first_avoidable_extra_name_step"], 2)

    def test_restarted_bands_are_232(self):
        """Read top-to-bottom by geometry, not by a misleading side suffix."""
        sides = self.replay["steps"][1]["state"]["sides"]
        self.assertEqual([side["symbol"] for side in sorted(sides, key=lambda x: x["bounds"][1])],
                         [2, 3, 2])
        self.assertTrue(self.report["minimality_certificates"]["restarted_before"]["attains_bound"])

    def test_three_cuts_are_direct_without_old_renaming(self):
        """Check the actual full-boundary arithmetic, not only final colors."""
        expected = [(2, [1], 3), (3, [1], 2), (3, [1, 2], 4)]
        for step, triple in zip(self.replay["steps"], expected):
            event = step["event"]
            self.assertEqual((event["s"], event["R"], event["t"]), triple)
            self.assertFalse(event["sync_attempted"])
            self.assertFalse(event["changed_old_sides"])
            self.assertEqual(step["status"], "split")

    def test_final_page_left_is_four_and_page_right_is_three(self):
        """For a downward stroke, directed left is the page-right child."""
        names = {tuple(side["bounds"]): side["symbol"] for side in self.replay["final_state"]["sides"]}
        self.assertEqual(names, {(0, 0, 900, 357): 2, (0, 487, 900, 600): 2,
                                 (0, 357, 442, 487): 4, (442, 357, 900, 487): 3})

    def test_four_is_necessary_only_after_pending_cut(self):
        """Four pairwise edge-adjacent sides provide an explicit lower bound."""
        certificate = self.report["minimality_certificates"]["restarted_after"]
        self.assertEqual(certificate["lower_bound_including_outside"], 4)
        self.assertEqual(len(certificate["positive_length_pairs"]), 6)
        self.assertTrue(certificate["attains_bound"])

    def test_all_three_methods_need_no_repair_on_corrected_start(self):
        """The old frozen snapshot cannot be reused as a minimal-rule failure."""
        for result in self.report["normalized_three_methods"]:
            with self.subTest(method=result["method"]):
                self.assertEqual(result["used_stage"], "M1_direct")
                self.assertEqual(result["new_name"], 4)
                self.assertFalse(result["repair"]["attempted"])
                self.assertEqual(result["changed_old_count"], 0)

    def test_nonadjacent_bands_do_not_form_a_clique(self):
        """Do not turn two separated strips into a false minimality witness."""
        before = unpack_state(self.replay["steps"][1]["state"])
        with self.assertRaises(ValueError):
            clique_bound(before, ["outside", "root.l", "root.r.r"])


if __name__ == "__main__":
    unittest.main()

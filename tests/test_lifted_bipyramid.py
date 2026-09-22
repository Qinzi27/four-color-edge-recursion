"""Small structural and producer checks for the lifted development diagnostic."""

import unittest

from scripts.audit_lifted_bipyramid import EDGES, SIDES, lifted_document
from scripts.quaternary_low_color import solve_low_color


class LiftedBipyramidTests(unittest.TestCase):
    """Keep a discovered abstract failure distinct from geometric scheduling."""

    def test_input_has_one_anchor_and_real_neq_only(self):
        """The formerly external domains must not be supplied in the input."""
        document = lifted_document()
        self.assertEqual(document["anchors"], {"Z": 1})
        self.assertEqual(document["states"], {})
        self.assertEqual(len(document["sides"]), 10)
        self.assertEqual(len(document["lines"]), 18)
        self.assertTrue(all(row["kind"] == "separator" for row in document["lines"]))
        self.assertNotIn("equal_names", document)

    def test_precommitment_witness_and_apex_obstruction(self):
        """A concrete complete coloring supports every commitment before A=1."""
        witness = dict(Z=1, P=1, Q=2, X=3, Y=4, A=2, E=2, B=1, C=3, D=4)
        self.assertTrue(all(witness[a] != witness[b] for a, b in EDGES))
        self.assertEqual(witness["A"], witness["E"])
        self.assertEqual(len({witness[v] for v in ("B", "C", "D")}), 3)

    def test_actual_low_color_prefix_generates_domains(self):
        """Replay the producer cheaply; the full posterior audit is separate."""
        result = solve_low_color(lifted_document(), probe=True)
        commits = [event for event in result["events"] if event["kind"] == "commit"]
        self.assertEqual([(event["side"], event["symbol"]) for event in commits],
                         [("P", 1), ("Q", 2), ("X", 3), ("A", 1)])
        before = result["phases"][commits[-1]["before_phase"]]["outcome"]
        domains = dict(zip(SIDES, before["domains"]))
        self.assertEqual(domains["A"], [1, 2])
        self.assertEqual(domains["E"], [2, 3, 4])
        self.assertEqual(domains["Y"], [4])
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(commits[-1]["extension_claim"], "inconclusive")
        self.assertFalse(result["oracle_feedback_to_producer"])


if __name__ == "__main__":
    unittest.main()

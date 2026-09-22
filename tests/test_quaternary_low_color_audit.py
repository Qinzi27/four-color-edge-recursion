"""Posterior checks must distinguish sound rejection from unsafe commitments."""

from copy import deepcopy
from itertools import combinations
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.audit_quaternary_low_color import audit_low_color
from scripts.quaternary_contact_model import propagate_contacts
from scripts.quaternary_low_color import solve_low_color
from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.validate_global_restart import export_geometries

ROOT = Path(__file__).resolve().parents[1]


def contact(n=2, edges=((0, 1),), anchors=None):
    """Make literal raw test graphs, with no derived domain restrictions."""
    return {"sides": ["S" + str(i) for i in range(n)], "lines": [
        {"id": "E" + str(i), "left": "S" + str(a), "right": "S" + str(b),
         "kind": "separator"} for i, (a, b) in enumerate(edges)],
        "anchors": {"S0": 1} if anchors is None else anchors}


class LowColorAuditTests(unittest.TestCase):
    """Exercise evidence corruption and known first-loss controls."""

    @classmethod
    def setUpClass(cls):
        """Export one frozen real counterexample and an empty-frame control."""
        cases = json.loads((ROOT / "examples/quaternary-real-regressions-2026-09-21.json").read_text(
            encoding="utf-8"))["cases"]
        cls.case = cases[0]
        cls.drawings = {"old": cls.case["drawing"],
                        "empty": {"frame": {"width": 900, "height": 600}, "strokes": []}}
        cls.geometry = {row["key"]: row["geometry"] for row in export_geometries([
            {"key": key, "document": drawing} for key, drawing in cls.drawings.items()])}

    def real(self, key="old"):
        """Use exact original commitments, never old derived candidates."""
        geometry = self.geometry[key]
        anchors = self.case["anchors"] if key == "old" else {"S0": 1}
        adapted = adapt_exported_geometry(geometry, anchors=anchors, drawing=self.drawings[key])
        return geometry, adapted, adapted["contact_document"]

    def test_small_safe_runs_and_complete_assignments(self):
        document = contact()
        for probe in (False, True):
            result = solve_low_color(document, probe=probe)
            audit = audit_low_color(document, result)
            self.assertTrue(audit["passed"])
            self.assertEqual(audit["commitment_counts"],
                             {"safe": 1, "unsafe": 0, "unknown": 0, "preexisting_unsat": 0})
            self.assertEqual(audit["full_enumeration"]["literal_assignments_checked"], 4)
            self.assertEqual(audit["full_enumeration"]["initial_legal_assignments"], 3)
            self.assertEqual(audit["full_enumeration"]["phase_checks"], 2)
            self.assertIsNone(audit["first_bad_commitment"])

    def test_original_states_and_equalities_are_rejected_explicitly(self):
        for addition in ({"states": {"S1": "0111"}}, {"equal_names": [["S0", "S1"]]}):
            document = {**contact(), **addition}
            with self.assertRaisesRegex(AssertionError, "states/EQ unsupported"):
                audit_low_color(document, solve_low_color(document))

    def test_oracle_unknown_never_becomes_safe(self):
        document = contact()
        audit = audit_low_color(document, solve_low_color(document), node_limit=0)
        self.assertEqual(audit["commitment_counts"]["unknown"], 1)
        self.assertEqual(audit["commitment_counts"]["safe"], 0)
        self.assertEqual(audit["oracle_unknown"], 2)
        self.assertTrue(all(row["result"]["status"] == "unknown" for row in audit["oracle_records"]))

    def test_assignment_limit_is_input_product_and_inclusive(self):
        document = contact()
        result = solve_low_color(document)
        self.assertEqual(audit_low_color(document, result, assignment_limit=4)["full_enumeration"]["status"], "run")
        audit = audit_low_color(document, result, assignment_limit=3)
        self.assertEqual(audit["full_enumeration"]["status"], "not_run")
        self.assertIsNone(audit["full_enumeration"]["initial_legal_assignments"])
        self.assertEqual(audit["commitment_counts"]["safe"], 1)

    def test_resource_stops_are_not_completion(self):
        document = contact()
        for resources in ({"decision_limit": 0}, {"probe_limit": 0}):
            result = solve_low_color(document, **resources)
            audit = audit_low_color(document, result)
            self.assertEqual(result["status"], "incomplete")
            self.assertEqual(audit["phase_count"], 1)
            bad = deepcopy(result)
            bad["status"] = "solved"
            with self.assertRaisesRegex(AssertionError, "exhaustion mislabeled"):
                audit_low_color(document, bad)

    def test_real_baseline_preserves_first_bad_commitment_evidence(self):
        geometry, adapted, document = self.real()
        result = solve_low_color(document, geometry=geometry, probe=False)
        audit = audit_low_color(document, result, geometry=geometry, adapted=adapted)
        self.assertTrue(audit["passed"])
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(audit["commitment_counts"]["unsafe"], 1)
        bad = audit["first_bad_commitment"]
        self.assertEqual((bad["side"], bad["symbol"]), ("S10", 2))
        self.assertEqual(bad["before"]["result"]["status"], "sat")
        self.assertIsNotNone(bad["before"]["result"]["witness"])
        self.assertEqual(bad["after"]["result"]["status"], "unsat")
        self.assertIsNotNone(bad["after"]["result"]["certificate"])

    def test_real_guard_rejects_bad_two_without_oracle_domain_feedback(self):
        geometry, adapted, document = self.real()
        result = solve_low_color(document, geometry=geometry)
        audit = audit_low_color(document, result, geometry=geometry, adapted=adapted)
        self.assertTrue(audit["passed"])
        self.assertEqual(audit["steps"][0]["extendibility"], "refuted")
        self.assertEqual(audit["rejection_counts"]["exact_unsat"], 1)
        self.assertEqual(audit["commitment_counts"]["unsafe"], 0)
        self.assertEqual(result["status"], "solved")
        first = audit["steps"][0]
        self.assertEqual(first["before_oracle_index"], first["after_oracle_index"])
        original = audit["oracle_records"][first["after_oracle_index"]]["input"]["anchors"]
        self.assertEqual(original, [[0, 1], [1, 2]])
        self.assertNotIn([10, 2], original)

    def test_real_rejection_with_zero_oracle_budget_remains_unknown(self):
        geometry, adapted, document = self.real()
        result = solve_low_color(document, geometry=geometry, probe_limit=1)
        audit = audit_low_color(document, result, geometry=geometry, adapted=adapted, node_limit=0)
        self.assertEqual(audit["rejection_counts"], {"exact_unsat": 0, "unknown": 1})
        self.assertEqual(audit["steps"][0]["extendibility"], "refuted")
        self.assertEqual(audit["commitment_counts"]["safe"], 0)

    def test_frame_only_fallback_is_explicit_and_checked(self):
        geometry, adapted, document = self.real("empty")
        result = solve_low_color(document, geometry=geometry)
        self.assertEqual(result["events"][0]["selection"]["selection_group"], "frame-only-fallback")
        audit_low_color(document, result, geometry=geometry, adapted=adapted)
        result["events"][0]["selection"]["reason"] = "pretend-internal"
        with self.assertRaisesRegex(AssertionError, "scheduler metadata"):
            audit_low_color(document, result, geometry=geometry, adapted=adapted)

    def test_auditor_never_calls_producer_or_propagator(self):
        document = contact()
        result = solve_low_color(document)
        with patch("scripts.quaternary_low_color.solve_low_color", side_effect=AssertionError("producer called")), \
                patch("scripts.quaternary_low_color.propagate_contacts", side_effect=AssertionError("filter called")):
            self.assertTrue(audit_low_color(document, result)["passed"])

    def test_lowest_color_and_event_chain_tampering_rejected(self):
        document = contact()
        result = solve_low_color(document)
        for field, value in (("symbol", 3), ("before_phase", 1), ("after_phase", 0), ("trial_phase", 0)):
            bad = deepcopy(result)
            bad["events"][0][field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                audit_low_color(document, bad)

    def test_rejection_cannot_smuggle_an_extra_anchor(self):
        geometry, adapted, document = self.real()
        result = solve_low_color(document, geometry=geometry, probe_limit=1)
        bad = deepcopy(result)
        bad["phases"][2]["document"]["anchors"]["S10"] = 3
        bad["phases"][2]["outcome"] = propagate_contacts(bad["phases"][2]["document"])
        with self.assertRaisesRegex(AssertionError, "post-rejection restrictions"):
            audit_low_color(document, bad, geometry=geometry, adapted=adapted)

    def test_consistent_trial_cannot_add_unannounced_constraints(self):
        document = contact(3, edges=((0, 1), (1, 2)))
        result = solve_low_color(document, probe_limit=1)
        result["phases"][1]["document"]["anchors"]["S2"] = 3
        result["phases"][1]["outcome"] = propagate_contacts(result["phases"][1]["document"])
        with self.assertRaisesRegex(AssertionError, "trial assumptions"):
            audit_low_color(document, result)

    def test_surviving_trial_cannot_be_relabelled_as_a_rejection(self):
        document = contact()
        result = solve_low_color(document)
        result["events"][0].update(kind="reject", extension_claim="refuted")
        with self.assertRaisesRegex(AssertionError, "lacks a proved propagation conflict"):
            audit_low_color(document, result)

    def test_final_colors_trace_and_unreferenced_phases_are_checked(self):
        document = contact()
        result = solve_low_color(document)
        for mutate in (lambda r: r["colors"].update(S1=1),
                       lambda r: r["phases"].append(deepcopy(r["phases"][0])),
                       lambda r: r["phases"][0]["outcome"]["relations"][0].__setitem__(1, 65535)):
            bad = deepcopy(result)
            mutate(bad)
            with self.assertRaises(AssertionError):
                audit_low_color(document, bad)

    def test_initial_unsat_is_separate_from_first_bad_commitment(self):
        document = contact(2, anchors={"S0": 1, "S1": 1})
        result = solve_low_color(document)
        audit = audit_low_color(document, result)
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(audit["oracle_records"][0]["result"]["status"], "unsat")
        self.assertEqual(audit["commitment_counts"]["unsafe"], 0)
        self.assertIsNone(audit["first_bad_commitment"])

    def test_preexisting_global_unsat_is_not_safe_or_new_failure(self):
        document = contact(5, list(combinations(range(5), 2)), anchors={})
        result = solve_low_color(document, probe=False)
        audit = audit_low_color(document, result)
        self.assertEqual(audit["commitment_counts"]["preexisting_unsat"], 2)
        self.assertEqual(audit["commitment_counts"]["unsafe"], 0)

    def test_serialized_output_preserves_schedule_evidence(self):
        geometry, adapted, document = self.real()
        result = json.loads(json.dumps(solve_low_color(document, geometry=geometry, probe_limit=1)))
        self.assertTrue(audit_low_color(document, result, geometry=geometry, adapted=adapted)["passed"])


if __name__ == "__main__":
    unittest.main()

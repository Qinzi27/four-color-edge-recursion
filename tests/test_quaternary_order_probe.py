"""Old small fixtures test post-hoc binding, ordering and epistemic boundaries."""

from copy import deepcopy
from itertools import combinations
import json
from pathlib import Path
from unittest.mock import patch
import unittest

from scripts.audit_lifted_bipyramid import lifted_document
from scripts.audit_quaternary_low_color import audit_low_color
from scripts.audit_quaternary_order_probe import check_saved_schedule, diagnose_order
from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.quaternary_low_color import solve_low_color
from scripts.validate_global_restart import export_geometries


def bare_document():
    """An old five-vertex core with E=2 rejects the first proposed A=1."""
    edges = [pair for pair in combinations("ABCDE", 2) if pair != ("A", "E")]
    return {"sides": list("ABCDE"), "anchors": {"E": 2}, "lines": [
        {"id": f"E{i}", "left": a, "right": b, "kind": "separator"}
        for i, (a, b) in enumerate(edges)]}


class OrderDiagnosticTests(unittest.TestCase):
    """Producer/oracle work finishes before this separate report-only module."""

    @classmethod
    def setUpClass(cls):
        """Reuse existing diagnostic inputs, never new experiment input families."""
        cls.bare = bare_document()
        cls.bare_result = solve_low_color(cls.bare, probe=True)
        cls.bare_audit = audit_low_color(cls.bare, cls.bare_result)
        cls.lifted = lifted_document()
        cls.lifted_result = solve_low_color(cls.lifted, probe=True)
        cls.lifted_audit = audit_low_color(cls.lifted, cls.lifted_result, assignment_limit=0)
        cls.mapping = {name: cls.lifted["sides"].index(name) for name in ("A", "E", "P", "Q", "X", "Y")}

    def test_lifted_wrong_commit_has_exact_binding(self):
        result = diagnose_order(self.lifted, self.lifted_result, self.lifted_audit,
                                role_mapping=self.mapping)
        self.assertEqual(result["exact_commitment_counts"],
                         {"safe": 3, "unsafe": 1, "unknown": 0, "preexisting_unsat": 0})
        bad = result["motif_scan"]["matches"]["inconclusive_commit"]
        self.assertEqual(len(bad), 1)
        self.assertTrue(bad[0]["structural_match_is_exact_failure"])
        self.assertEqual(bad[0]["exact_step"]["before_status"], "sat")
        self.assertEqual(bad[0]["exact_step"]["after_status"], "unsat")
        self.assertEqual(bad[0]["selected_apex"], "A")

    def test_non_S_side_names_use_index_roles_and_full_events(self):
        found = diagnose_order(self.lifted, self.lifted_result, self.lifted_audit,
                               role_mapping=self.mapping)
        commits = found["commitment_order"]
        self.assertEqual([row["selected_roles"] for row in commits], [["P"], ["Q"], ["X"], ["A"]])
        self.assertEqual([row["event"]["side"] for row in found["K4_commits_before_E_singleton"]],
                         ["P", "Q", "X"])
        for row, event in zip(found["events"], self.lifted_result["events"]):
            self.assertEqual(row["event"], event)
            self.assertEqual(row["selection_group"], "input-order")
            self.assertIsNone(row["mother"])

    def test_initial_singleton_is_phase_zero(self):
        found = diagnose_order(self.bare, self.bare_result, self.bare_audit,
                               role_mapping={"A": 0, "E": 4, "P": 1})
        self.assertEqual(found["first_singleton_phase"]["E"], 0)
        self.assertTrue(found["E_singleton_observed"])
        self.assertEqual(found["K4_commits_before_E_singleton"], [])
        self.assertTrue(all(row["before_first_E_singleton"] is False for row in found["events"]))

    def test_rejected_trial_is_excluded_but_post_rejection_is_retained(self):
        found = diagnose_order(self.bare, self.bare_result, self.bare_audit)
        phases = [row["phase"] for row in found["persistent_states"]]
        self.assertEqual(phases, [0] + [event["after_phase"] for event in self.bare_result["events"]])
        self.assertNotIn(1, phases)
        self.assertIn(2, phases)
        self.assertEqual(found["events"][0]["exact_step"]["trial_status"], "unsat")
        self.assertEqual(found["events"][0]["exact_step"]["after_status"], "sat")

    def test_histogram_counts_every_persistent_motif_state(self):
        found = diagnose_order(self.lifted, self.lifted_result, self.lifted_audit)
        for item in found["motif_scan"]["motif_statistics"]:
            self.assertEqual(sum(row["phases"] for row in item["domain_intersection_histogram"]),
                             len(found["persistent_states"]))
        self.assertEqual(found["motif_scan"]["counts"]["strict_apex_matches"],
                         len(found["motif_scan"]["matches"]["strict"]))

    def test_unmapped_roles_remain_unavailable(self):
        found = diagnose_order(self.bare, self.bare_result, self.bare_audit)
        self.assertIsNone(found["role_mapping"])
        self.assertIsNone(found["first_singleton_phase"])
        self.assertTrue(all(row["selected_roles"] is None for row in found["events"]))
        self.assertTrue(all(row["role_domains"] is None for row in found["persistent_states"]))

    def test_unknown_exact_results_are_not_safe(self):
        audit = audit_low_color(self.bare, self.bare_result, assignment_limit=0, node_limit=0)
        found = diagnose_order(self.bare, self.bare_result, audit)
        self.assertEqual(found["exact_commitment_counts"]["safe"], 0)
        self.assertEqual(found["exact_commitment_counts"]["unknown"], self.bare_result["choices"])
        self.assertGreater(found["oracle_unknown"], 0)

    def test_structural_risk_is_not_called_unsafe_when_exact_unknown(self):
        audit = audit_low_color(self.lifted, self.lifted_result, assignment_limit=0, node_limit=0)
        found = diagnose_order(self.lifted, self.lifted_result, audit)
        row = found["motif_scan"]["matches"]["inconclusive_commit"][0]
        self.assertEqual(row["exact_step"]["extendibility"], "unknown")
        self.assertFalse(row["structural_match_is_exact_failure"])

    def test_no_coloring_producer_or_oracle_called_by_diagnostic(self):
        with patch("scripts.quaternary_low_color.solve_low_color", side_effect=AssertionError("producer called")), \
             patch("scripts.exact_extendibility_oracle.solve_exact", side_effect=AssertionError("oracle called")):
            found = diagnose_order(self.bare, self.bare_result, self.bare_audit)
        self.assertFalse(found["producer_or_oracle_called"])

    def test_diagnostic_does_not_mutate_supplied_evidence(self):
        original = deepcopy((self.lifted, self.lifted_result, self.lifted_audit, self.mapping))
        found = diagnose_order(self.lifted, self.lifted_result, self.lifted_audit, role_mapping=self.mapping)
        found["events"][0]["event"]["side"] = "modified"
        self.assertEqual((self.lifted, self.lifted_result, self.lifted_audit, self.mapping), original)

    def test_mismatched_original_input_is_rejected(self):
        document = deepcopy(self.bare)
        document["anchors"]["E"] = 3
        with self.assertRaisesRegex(ValueError, "original input"):
            diagnose_order(document, self.bare_result, self.bare_audit)

    def test_mismatched_step_side_phase_and_status_are_rejected(self):
        for field, value in (("side", "C"), ("after_phase", 1), ("before_status", "unsat")):
            audit = deepcopy(self.bare_audit)
            audit["steps"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                diagnose_order(self.bare, self.bare_result, audit)

    def test_oracle_raw_graph_and_commitment_binding(self):
        for field, value in (("edges", []), ("anchors", [])):
            audit = deepcopy(self.bare_audit)
            audit["oracle_records"][audit["initial_oracle_index"]]["input"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "oracle input"):
                diagnose_order(self.bare, self.bare_result, audit)

    def test_invalid_role_indices_and_aliases_rejected(self):
        for roles in ({"A": -1}, {"A": 5}, {"A": True}, {"A": 0, "E": 0}):
            with self.subTest(roles=roles), self.assertRaises(ValueError):
                diagnose_order(self.bare, self.bare_result, self.bare_audit, role_mapping=roles)

    def test_count_and_first_bad_binding_rejected(self):
        audit = deepcopy(self.lifted_audit)
        audit["commitment_counts"]["unsafe"] = 0
        with self.assertRaisesRegex(ValueError, "counts"):
            diagnose_order(self.lifted, self.lifted_result, audit)
        audit = deepcopy(self.lifted_audit)
        audit["first_bad_commitment"] = None
        with self.assertRaisesRegex(ValueError, "first unsafe"):
            diagnose_order(self.lifted, self.lifted_result, audit)

    def test_phase_audit_and_trial_assumption_binding(self):
        audit = deepcopy(self.bare_audit)
        audit["phase_audits"][0]["status"] = "conflict"
        with self.assertRaisesRegex(ValueError, "phase audit"):
            diagnose_order(self.bare, self.bare_result, audit)
        result = deepcopy(self.bare_result)
        result["phases"][1]["document"]["anchors"]["A"] = 4
        with self.assertRaisesRegex(ValueError, "trial document"):
            diagnose_order(self.bare, result, self.bare_audit)

    def test_post_rejection_candidate_deletion_is_bound(self):
        result = deepcopy(self.bare_result)
        result["phases"][2]["document"]["states"]["A"] = "1111"
        with self.assertRaisesRegex(ValueError, "post-rejection document"):
            diagnose_order(self.bare, result, self.bare_audit)

    def test_optional_geometry_binding_uses_raw_shores(self):
        document = deepcopy(self.bare)
        names = {name: "S" + str(i) for i, name in enumerate(document["sides"])}
        document["sides"] = list(names.values())
        document["anchors"] = {names[name]: color for name, color in document["anchors"].items()}
        shores = []
        for line in document["lines"]:
            for endpoint in ("left", "right"):
                shores.append(list(names).index(line[endpoint]))
                line[endpoint] = names[line[endpoint]]
        # This is only a shores-binding fixture, not a geometric realization.
        geometry = {"faces": [[] for _ in names], "edges": [{} for _ in document["lines"]],
                    "faceOfDart": shores}
        result = solve_low_color(document, probe=True)
        audit = audit_low_color(document, result)
        found = diagnose_order(document, result, audit, geometry=geometry)
        self.assertTrue(found["geometry_adjacency_bound"])
        geometry["edges"][0]["virtual"] = True
        with self.assertRaisesRegex(ValueError, "geometry"):
            diagnose_order(document, result, audit, geometry=geometry)


class SavedScheduleTests(unittest.TestCase):
    """Check scheduler metadata using only old real controls and abstract inputs."""

    @classmethod
    def setUpClass(cls):
        """The old regression and empty frame are not this experiment's new family."""
        root = Path(__file__).resolve().parents[1]
        old = json.loads((root / "examples/quaternary-real-regressions-2026-09-21.json")
                         .read_text(encoding="utf-8"))["cases"][0]
        drawings = {"old": old["drawing"], "empty": {"frame": {"width": 900, "height": 600}, "strokes": []}}
        cls.geometries = {row["key"]: row["geometry"] for row in export_geometries([
            {"key": key, "document": drawing} for key, drawing in drawings.items()])}
        cls.documents, cls.results = {}, {}
        cls.resources = {"decision_limit": 128, "probe_limit": 512}
        for key, geometry in cls.geometries.items():
            anchors = old["anchors"] if key == "old" else {"S0": 1}
            document = adapt_exported_geometry(geometry, anchors=anchors)["contact_document"]
            cls.documents[key] = document
            cls.results[key] = solve_low_color(document, geometry=geometry, **cls.resources)

    def check(self, key="old", result=None, resources=None):
        """Use the same frozen current geometry and literal document each time."""
        return check_saved_schedule(self.documents[key], result or self.results[key],
                                    self.geometries[key], resources or self.resources)

    def test_shared_scheduler_replays_internal_and_frame_fallback(self):
        for key in ("old", "empty"):
            with self.subTest(key=key):
                found = self.check(key)
                self.assertTrue(found["passed"])
                self.assertEqual(found["events_checked"], len(self.results[key]["events"]))
        self.assertEqual(self.results["empty"]["events"][0]["selection"]["selection_group"],
                         "frame-only-fallback")

    def test_mother_group_and_reason_cannot_be_relabelled(self):
        for field in ("mother", "selection_group", "reason"):
            bad = deepcopy(self.results["old"])
            bad["events"][0]["selection"][field] = "tampered"
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "scheduler metadata"):
                self.check(result=bad)

    def test_contract_flags_and_policy_rejected(self):
        for field, value in (("policy", "other-v1"), ("schedule", "input-order"),
                             ("old_colors_read", True), ("probe", False),
                             ("oracle_feedback_to_producer", True), ("backtracks", True)):
            bad = deepcopy(self.results["old"])
            bad[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check(result=bad)

    def test_budget_and_terminal_reason_rejected(self):
        with self.assertRaisesRegex(ValueError, "resource limit"):
            self.check(resources={"decision_limit": 127, "probe_limit": 512})
        bad = deepcopy(self.results["old"])
        bad["reason"] = "budget-exhausted"
        with self.assertRaisesRegex(ValueError, "terminal reason"):
            self.check(result=bad)

    def test_valid_and_tampered_incomplete_runs(self):
        document = bare_document()
        resources = {"decision_limit": 0, "probe_limit": 512}
        result = solve_low_color(document, **resources)
        self.assertTrue(check_saved_schedule(document, result, None, resources)["passed"])
        result["reason"] = "probe-limit-exhausted"
        with self.assertRaisesRegex(ValueError, "resource stop"):
            check_saved_schedule(document, result, None, resources)

    def test_no_producer_propagation_or_oracle_search(self):
        with patch("scripts.quaternary_low_color.solve_low_color", side_effect=AssertionError("producer called")), \
             patch("scripts.quaternary_low_color.propagate_contacts", side_effect=AssertionError("propagation called")), \
             patch("scripts.audit_quaternary_low_color.solve_exact", side_effect=AssertionError("oracle called")):
            self.assertTrue(self.check()["passed"])


if __name__ == "__main__":
    unittest.main()

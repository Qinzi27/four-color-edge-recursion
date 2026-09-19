"""Tamper rejection and predeclared selection tests for the independent audit.

These tests use actual production certificates and then corrupt copies. They
perform no coloring enumeration, do not provide solutions to production, and
never modify the archived source report or the running formal validator.
"""

from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from fourcolor.relation_frontier import restart_relation_frontier_names
from scripts import validate_relation_frontier as audit


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SELECTION_SHA = "91d7d410e92246a6c890402ae0bb7c8d76558a5edb36540d9a900ff708fdf9b9"


def first_relation_event(result):
    """Locate a real deletion rather than assuming a trace's first phase shape."""
    return next(event for record in result["propagation_phases"]
                for phase in record["outcome"]["phases"]
                for event in phase["relation_trace"])


class RelationFrontierAuditTests(unittest.TestCase):
    """A certificate is useful only if plausible-looking false records fail."""

    @classmethod
    def setUpClass(cls):
        """Read one preserved geometry and compute a fresh genuine certificate."""
        path = ROOT / "docs/figures/frontier-regression-audit-2026-09-19/manifest.json"
        cls.geometry = json.loads(path.read_text(encoding="utf-8"))["geometry"]
        cls.result = restart_relation_frontier_names(cls.geometry)

    def test_genuine_full_certificate_passes_independent_replay(self):
        """The validator replays all filter rounds, not just the final colors."""
        result = deepcopy(self.result)
        verification = audit.independent_check(self.geometry, result)
        self.assertTrue(verification["passed"])
        self.assertEqual(verification["claim"], "complete-proper-four-names")
        self.assertEqual(verification["propagations"], result["choices"] + 1)
        self.assertGreater(verification["relation_events"], 0)
        self.assertGreater(verification["ordered_pair_deletions_replayed"], 0)
        self.assertEqual(result, self.result)

    def test_changed_pair_removal_or_after_mask_is_rejected(self):
        """Both the deletion and its claimed resulting relation need checking."""
        for field in ("removed", "after"):
            with self.subTest(field=field):
                altered = deepcopy(self.result)
                event = first_relation_event(altered)
                event[field] = 0 if field == "removed" else event[field] ^ 1
                with self.assertRaises(AssertionError):
                    audit.independent_check(self.geometry, altered)

    def test_changed_hall_domain_projection_is_rejected(self):
        """A narrowed domain cannot be accepted simply because it is recorded."""
        altered = deepcopy(self.result)
        phase = altered["propagation_phases"][0]["outcome"]["phases"][0]
        self.assertEqual(phase["hall_domains"][self.geometry["outerFace"]], [1])
        phase["hall_domains"][self.geometry["outerFace"]] = [2]
        with self.assertRaises(AssertionError):
            audit.independent_check(self.geometry, altered)

    def test_changed_choice_or_commitment_anchors_are_rejected(self):
        """Detect altered greedy names and both intermediate/final anchor maps."""
        for target in ("symbol", "recorded-anchors", "final-anchors"):
            with self.subTest(target=target):
                altered = deepcopy(self.result)
                self.assertTrue(altered["trace"])
                first = altered["trace"][0]
                changed = first["symbol"] % 4 + 1
                if target == "symbol":
                    first["symbol"] = changed
                elif target == "recorded-anchors":
                    altered["propagation_phases"][1]["anchors_by_dart"][first["dart"]] = [changed]
                else:
                    altered["anchors_by_dart"][first["dart"]] = [changed]
                with self.assertRaises(AssertionError):
                    audit.independent_check(self.geometry, altered)

    def test_changed_final_color_is_rejected_even_with_genuine_trace(self):
        """Valid deductions cannot authenticate an independently altered output."""
        altered = deepcopy(self.result)
        altered["colors"][self.geometry["outerFace"]] = 2
        with self.assertRaises(AssertionError):
            audit.independent_check(self.geometry, altered)


class RelationFrontierSelectionTests(unittest.TestCase):
    """Sampling is fixed by archived old results, never by the new experiment."""

    @classmethod
    def setUpClass(cls):
        """Load only the prior 7,069-drawing report; no new report is consulted."""
        cls.previous = audit.read_json(audit.SOURCE)

    def test_groups_counts_named_examples_and_deduplicated_selection_are_fixed(self):
        """Recompute declared groups from old status fields and historical aliases."""
        selected, groups, named = audit.declared_selection(self.previous)
        rows = self.previous["drawings"]
        old = [row for row in rows if audit.EXISTING in row["cohorts"]]
        self.assertEqual(len(rows), 7069)
        self.assertEqual(len(old), 6113)
        regression_keys = sorted(row["key"] for row in old
                                 if row["runs"]["closed-support"]["status"] == "solved"
                                 and row["runs"]["tight-hall"]["status"] != "solved")
        control_keys = sorted(row["key"] for row in old
                              if row["runs"]["tight-hall"]["status"] == "solved")[:135]
        previous_failure_keys = sorted(row["key"] for row in rows
                                       if audit.HELDOUT in row["cohorts"]
                                       and row["runs"]["tight-hall"]["status"] != "solved")
        self.assertEqual(groups["old-closed-success-hall-regressions"], regression_keys)
        self.assertEqual(groups["old-hall-success-key-sorted-controls"], control_keys)
        self.assertEqual(groups["previous-new-seeds-hall-failures-now-diagnostic"],
                         previous_failure_keys)
        self.assertEqual((len(regression_keys), len(control_keys), len(previous_failure_keys)),
                         (135, 135, 36))
        expected_named = {}
        for history, step in (("guillotine-20261027", 6),
                              ("heldout-guillotine-20261937", 6),
                              ("guillotine-20261209", 9)):
            matching = [row["key"] for row in rows if any(
                alias.get("history") == history and alias.get("step") == step
                for alias in row["aliases"])]
            self.assertEqual(len(matching), 1)
            expected_named[f"{history}/step-{step}"] = matching[0]
        self.assertEqual(named, expected_named)
        self.assertEqual(groups["named-manual-diagnostics"], sorted(set(expected_named.values())))
        expected_keys = sorted(set(regression_keys + control_keys + previous_failure_keys
                                   + list(expected_named.values())))
        actual_keys = [row["key"] for row in selected]
        self.assertEqual(actual_keys, expected_keys)
        self.assertEqual(len(actual_keys), 307)
        self.assertEqual(len(actual_keys), len(set(actual_keys)))
        self.assertEqual(audit.digest(actual_keys), EXPECTED_SELECTION_SHA)

    def test_new_candidate_outcomes_and_record_order_cannot_change_selection(self):
        """Poison candidate-only metadata and prohibit invoking either solver.

        This is a metadata-only projection of the old report, not a fabricated
        map corpus: selection needs keys, cohorts, aliases and two OLD statuses.
        """
        projected = {"drawings": [
            {"key": row["key"], "cohorts": list(row["cohorts"]),
             "aliases": deepcopy(row["aliases"]),
             "runs": {"closed-support": {"status": row["runs"]["closed-support"]["status"]},
                      "tight-hall": {"status": row["runs"]["tight-hall"]["status"]},
                      audit.POLICY: {"status": "conflict"}}}
            for row in reversed(self.previous["drawings"])]}
        with patch.object(audit, "restart_frontier_names", side_effect=AssertionError("old solver called")), \
                patch.object(audit, "restart_relation_frontier_names",
                             side_effect=AssertionError("candidate solver called")):
            first, groups, named = audit.declared_selection(projected)
            for row in projected["drawings"]:
                row["runs"][audit.POLICY]["status"] = "solved"
            second, second_groups, second_named = audit.declared_selection(projected)
        first_keys = [row["key"] for row in first]
        self.assertEqual(first_keys, [row["key"] for row in second])
        self.assertEqual(groups, second_groups)
        self.assertEqual(named, second_named)
        self.assertEqual(audit.digest(first_keys), EXPECTED_SELECTION_SHA)


if __name__ == "__main__":
    unittest.main()

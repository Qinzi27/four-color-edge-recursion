"""Check minimum-number choices without changing the current naming rules.

The core filter is tested for unused-name symmetry. The read-only audit is
tested against recorded pre-choice states, including deliberately altered
toy certificates. These tests do not run the full corpus or use a coloring
search to make production choices.
"""

from copy import deepcopy
from itertools import combinations
import json
from pathlib import Path
import unittest

from fourcolor.relation_frontier import propagate_frontier_relations, restart_relation_frontier_names
from scripts.audit_minimum_names import inspect_choices
from tests import test_frontier_restart as fixtures


ROOT = Path(__file__).resolve().parents[1]
PALETTE = (1, 2, 3, 4)


def decoded_pairs(mask):
    """Decode binary candidates independently of the production helper."""
    return {(a, b) for a in PALETTE for b in PALETTE
            if mask & (1 << (4 * (a - 1) + b - 1))}


def swap_unused(name):
    """Exchange the as-yet unnamed symbols 3 and 4, fixing root symbols."""
    return {3: 4, 4: 3}.get(name, name)


def toy_result(chosen=3):
    """A single valid-in-domain decision; no plane embedding is claimed here."""
    before = {0: [1], 1: [2]}
    after = {**before, 4: [chosen]}
    return {"choices": 1,
            "initial_anchors_by_dart": deepcopy(before),
            "anchors_by_dart": deepcopy(after),
            "trace": [{"side": 2, "dart": 4, "domain": [3, 4],
                       "used_names": [1, 2], "symbol": chosen}],
            "propagation_phases": [
                {"anchors_by_dart": deepcopy(before),
                 "outcome": {"status": "underdetermined", "domains": [[1], [2], [3, 4]]}},
                {"anchors_by_dart": deepcopy(after),
                 "outcome": {"status": "solved", "domains": [[1], [2], [chosen]]}},
            ]}


class MinimumNameSymmetryTests(unittest.TestCase):
    """A consecutive used-name prefix makes the old sorting expression minimal."""

    def test_unintroduced_three_four_names_remain_symmetric_in_domains_and_pairs(self):
        """Five abstract graph families x four symmetric initial domain patterns.

        Same-shore bridge occurrences are included by the existing fixture.
        Symmetry is checked for non-edge auxiliary relations as well as actual
        inequalities; a name is never chosen during this filter-only test.
        """
        families = (
            (3, [(0, 1), (1, 2)]),
            (3, list(combinations(range(3), 2))),
            (4, [(0, 1), (1, 2), (2, 3), (0, 3)]),
            (4, list(combinations(range(4), 2))),
            (5, [(0, 1), (1, 2), (2, 3), (3, 4), (0, 4)]),
        )
        checked = 0
        for size, adjacent in families:
            model, darts = fixtures.constraint_model(size, adjacent)
            patterns = (
                [PALETTE] * size,
                [(1,), (2,)] + [PALETTE] * (size - 2),
                [(1,), (2,)] + [(3, 4)] * (size - 2),
                [(1, 3, 4) if side % 2 == 0 else (2, 3, 4) for side in range(size)],
            )
            for domains in patterns:
                with self.subTest(adjacent=adjacent, domains=domains):
                    self.assertTrue(all({swap_unused(c) for c in domain} == set(domain)
                                        for domain in domains))
                    result = propagate_frontier_relations(
                        model, fixtures.domain_anchors(darts, domains))
                    self.assertEqual(result["choices"], 0)
                    self.assertEqual(result["backtracks"], 0)
                    for domain in result["domains"]:
                        self.assertEqual({swap_unused(c) for c in domain}, set(domain))
                    for row in result["relations"]:
                        for mask in row:
                            pairs = decoded_pairs(mask)
                            self.assertEqual({(swap_unused(a), swap_unused(b)) for a, b in pairs}, pairs)
                checked += 1
        self.assertEqual(checked, 20)

    def test_reuse_then_numeric_order_equals_min_for_every_used_prefix(self):
        """Exhaust 15 nonempty domains x 5 used prefixes, including the empty one."""
        checked = 0
        for prefix_length in range(5):
            used = set(range(1, prefix_length + 1))
            for bits in range(1, 16):
                domain = [name for name in PALETTE if bits & (1 << (name - 1))]
                chosen = min(domain, key=lambda name: (name not in used, name))
                self.assertEqual(chosen, min(domain))
                checked += 1
        self.assertEqual(checked, 75)

    def test_external_nonprefix_used_names_show_why_the_premise_matters(self):
        """This is NOT a reachable-run counterexample to the two-root procedure."""
        used, domain = {1, 3}, [2, 3]
        self.assertNotEqual(used, set(range(1, max(used) + 1)))
        self.assertEqual(min(domain, key=lambda name: (name not in used, name)), 3)
        self.assertEqual(min(domain), 2)


class MinimumNameAuditTests(unittest.TestCase):
    """Inspect pre-decision domains, not a rewritten or final coloring."""

    def test_consistent_minimum_choice_is_reported_without_mutation(self):
        """A matching certificate has no minimum or prefix discrepancy."""
        result = toy_result()
        original = deepcopy(result)
        audit = inspect_choices(result)
        self.assertEqual(audit["choices"], 1)
        self.assertEqual(audit["minimum_mismatches"], [])
        self.assertEqual(audit["prefix_mismatches"], [])
        self.assertEqual(len(audit["decisions"]), 1)
        decision = audit["decisions"][0]
        self.assertEqual((decision["side"], decision["dart"]), (2, 4))
        self.assertEqual(decision["domain"], [3, 4])
        self.assertEqual(decision["used_names"], [1, 2])
        self.assertEqual((decision["chosen"], decision["minimum"]), (3, 3))
        self.assertTrue(decision["is_minimum"])
        self.assertTrue(decision["used_is_prefix"])
        self.assertEqual(result, original)

    def test_legal_nonminimum_choice_is_recorded_not_rejected_or_hidden(self):
        """The audit must detect an in-domain 4 where 3 was also available."""
        audit = inspect_choices(toy_result(chosen=4))
        self.assertEqual(audit["choices"], 1)
        self.assertEqual(len(audit["minimum_mismatches"]), 1)
        self.assertEqual(audit["prefix_mismatches"], [])
        decision = audit["decisions"][0]
        self.assertEqual((decision["chosen"], decision["minimum"]), (4, 3))
        self.assertFalse(decision["is_minimum"])

    def test_nonprefix_metadata_is_reported_when_it_matches_actual_state(self):
        """An external state with used {1,3} is diagnosed, not silently normalized."""
        result = toy_result(chosen=3)
        result["trace"][0].update({"domain": [2, 3], "used_names": [1, 3]})
        result["propagation_phases"][0]["outcome"]["domains"] = [[1], [3], [2, 3]]
        result["propagation_phases"][1]["outcome"]["domains"] = [[1], [3], [3]]
        result["initial_anchors_by_dart"][1] = [3]
        result["anchors_by_dart"][1] = [3]
        for record in result["propagation_phases"]:
            record["anchors_by_dart"][1] = [3]
        audit = inspect_choices(result)
        self.assertEqual(len(audit["prefix_mismatches"]), 1)
        self.assertEqual(len(audit["minimum_mismatches"]), 1)
        self.assertFalse(audit["decisions"][0]["used_is_prefix"])

    def test_trace_domains_used_names_and_choice_must_match_prechoice_state(self):
        """Reject invented candidate lists, used names, or out-of-domain symbols."""
        for target in ("domain", "used_names", "symbol"):
            with self.subTest(target=target):
                result = toy_result()
                result["trace"][0][target] = {"domain": [3], "used_names": [1], "symbol": 2}[target]
                with self.assertRaises(AssertionError):
                    inspect_choices(result)

    def test_phase_counts_and_committed_anchor_chain_must_match(self):
        """Reject missing phases, fabricated choice counts and changed commitments."""
        for target in ("choices", "phases", "terminal", "intermediate-anchor", "initial-anchor", "final-anchor"):
            with self.subTest(target=target):
                result = toy_result()
                if target == "choices":
                    result["choices"] = 2
                elif target == "phases":
                    result["propagation_phases"].pop()
                elif target == "terminal":
                    result["propagation_phases"][0]["outcome"]["status"] = "solved"
                elif target == "intermediate-anchor":
                    result["propagation_phases"][1]["anchors_by_dart"][4] = [4]
                elif target == "initial-anchor":
                    result["initial_anchors_by_dart"][0] = [2]
                else:
                    result["anchors_by_dart"][4] = [4]
                with self.assertRaises(AssertionError):
                    inspect_choices(result)

    def test_json_string_dart_keys_are_equivalent_to_integer_keys(self):
        """A saved report and its in-memory precursor describe the same anchors."""
        result = toy_result()
        persisted = json.loads(json.dumps(result))
        self.assertEqual(inspect_choices(persisted), inspect_choices(result))


class MinimumNameRealGeometryTests(unittest.TestCase):
    """Small fresh restarts demonstrate the minimum rule at every real decision."""

    @classmethod
    def setUpClass(cls):
        """Reuse geometry-only fixtures plus the preserved old regression map."""
        fixtures.FrontierRestartTests.setUpClass()
        cls.geometry = {key: fixtures.FrontierRestartTests.geometry[key]
                        for key in ("blank", "horizontal", "grid", "island")}
        manifest = ROOT / "docs/figures/frontier-regression-audit-2026-09-19/manifest.json"
        cls.geometry["old-regression"] = json.loads(manifest.read_text(encoding="utf-8"))["geometry"]

    def test_real_choices_are_minimum_and_used_names_are_consecutive(self):
        """Derive candidates/used sets independently from each previous propagation."""
        checked_choices = 0
        for key, geometry in self.geometry.items():
            with self.subTest(geometry=key):
                result = restart_relation_frontier_names(geometry)
                self.assertEqual(result["status"], "solved")
                audit = inspect_choices(result)
                self.assertEqual(audit["minimum_mismatches"], [])
                self.assertEqual(audit["prefix_mismatches"], [])
                self.assertEqual(audit["choices"], len(result["trace"]))
                for index, step in enumerate(result["trace"]):
                    domains = result["propagation_phases"][index]["outcome"]["domains"]
                    domain = domains[step["side"]]
                    used = {values[0] for values in domains if len(values) == 1}
                    self.assertEqual(used, set(range(1, max(used) + 1)))
                    self.assertEqual(step["symbol"], min(domain))
                    self.assertEqual(step["used_names"], sorted(used))
                    self.assertEqual(step["domain"], domain)
                    checked_choices += 1
        self.assertGreater(checked_choices, 0)


if __name__ == "__main__":
    unittest.main()

"""Soundness and restart regressions for the Hall-plus-pair relation filter.

Full assignment enumeration is an independent TEST oracle only. The tested
production code must neither consume these assignments nor turn a nonempty
local fixed point into a claim of global completion or a four-color proof.
"""

from copy import deepcopy
from itertools import combinations, product
import json
from pathlib import Path
import unittest

from fourcolor.frontier_restart import neighbor_sets, propagate_hall, small_cliques
from fourcolor.closed_support import supported_cycle_units
from fourcolor.global_restart import current_segments
from fourcolor.relation_frontier import (
    propagate_frontier_relations, restart_relation_frontier_names,
)
from fourcolor.whole_lines import build_whole_lines
from tests import test_frontier_restart as fixtures


ROOT = Path(__file__).resolve().parents[1]
PALETTE = (1, 2, 3, 4)


def relation_pairs(mask):
    """Decode masks independently, so assertions compare ordinary pair sets."""
    return {(a, b) for a in PALETTE for b in PALETTE
            if mask & (1 << (4 * (a - 1) + b - 1))}


def oracle_compose(first, second):
    """Plain set composition, independent of the production bit operations."""
    return {(a, b) for a, middle in relation_pairs(first)
            for other, b in relation_pairs(second) if middle == other}


class RelationFrontierPropagationTests(unittest.TestCase):
    """The filter may only delete names or pairs excluded by sound constraints."""

    def assert_fixed_point(self, result):
        """Inspect every diagonal, transpose, and triple-support condition."""
        relations = result["relations"]
        for i, row in enumerate(relations):
            self.assertEqual(relation_pairs(row[i]),
                             {(name, name) for name in result["domains"][i]})
            for j, mask in enumerate(row):
                decoded = relation_pairs(mask)
                self.assertEqual(relation_pairs(relations[j][i]),
                                 {(b, a) for a, b in decoded})
                self.assertTrue(all(a in result["domains"][i]
                                    and b in result["domains"][j] for a, b in decoded))
                for via in range(len(relations)):
                    self.assertLessEqual(decoded,
                                         oracle_compose(relations[i][via], relations[via][j]))

    def test_two_name_path_retains_correlation_without_picking_a_name(self):
        """The end shores are equal even though neither singleton is chosen."""
        model, darts = fixtures.constraint_model(3, [(0, 1), (1, 2)])
        anchors = fixtures.domain_anchors(darts, [(1, 2)] * 3)
        result = propagate_frontier_relations(model, anchors)
        self.assertEqual(result["status"], "underdetermined")
        self.assertEqual(result["domains"], [[1, 2]] * 3)
        self.assertEqual(relation_pairs(result["relations"][0][2]), {(1, 1), (2, 2)})
        self.assertEqual(result["choices"], 0)
        self.assertEqual(result["backtracks"], 0)
        self.assert_fixed_point(result)

    def test_odd_two_name_cycle_is_detected_without_assignment_trials(self):
        """Pair propagation can resolve the old unary/Hall-only blind spot."""
        adjacent = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 4)]
        model, darts = fixtures.constraint_model(5, adjacent)
        anchors = fixtures.domain_anchors(darts, [(1, 2)] * 5)
        self.assertEqual(propagate_hall(model, anchors)["status"], "underdetermined")
        result = propagate_frontier_relations(model, anchors)
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["choices"], 0)
        self.assertEqual(result["backtracks"], 0)

    def test_hall_reservation_and_pair_filter_reach_a_common_fixed_point(self):
        """A Hall-forced third name propagates along a following chain."""
        adjacent = [(0, 1), (0, 2), (1, 2), (2, 3), (3, 4)]
        model, darts = fixtures.constraint_model(5, adjacent)
        anchors = fixtures.domain_anchors(darts, [(1, 2), (1, 2), (1, 2, 3),
                                                (3, 4), (1, 4)])
        original = deepcopy(anchors)
        result = propagate_frontier_relations(model, anchors)
        self.assertEqual(result["domains"], [[1, 2], [1, 2], [3], [4], [1]])
        self.assertEqual(anchors, original)
        repeated = propagate_frontier_relations(model, anchors)
        self.assertEqual(repeated, result)
        restricted = fixtures.domain_anchors(darts, result["domains"])
        restarted = propagate_frontier_relations(model, restricted)
        self.assertEqual(restarted["relations"], result["relations"])
        self.assertEqual(restarted["domains"], result["domains"])
        self.assertEqual(propagate_hall(model, restricted)["domains"], result["domains"])
        self.assert_fixed_point(result)

    def test_complete_four_shore_hall_rule_remains_available(self):
        """Three distinct-name shores reserve {1,2,3}, forcing the fourth to 4."""
        model, darts = fixtures.constraint_model(4, list(combinations(range(4), 2)))
        anchors = fixtures.domain_anchors(darts, [(1, 2, 3)] * 3 + [PALETTE])
        result = propagate_frontier_relations(model, anchors)
        self.assertEqual(result["domains"], [[1, 2, 3]] * 3 + [[4]])
        self.assertEqual(result, propagate_frontier_relations(
            model, anchors, small_cliques(neighbor_sets(model))))
        self.assert_fixed_point(result)

    def test_k5_is_a_nonplane_kernel_warning_not_a_map_counterexample(self):
        """Local consistency still does not certify completion: K5 needs five.

        K5 is deliberately an abstract NONPLANAR constraint-kernel fixture.
        Nothing in this test represents it as an admissible plane-map input.
        """
        adjacent = list(combinations(range(5), 2))
        model, darts = fixtures.constraint_model(5, adjacent)
        result = propagate_frontier_relations(
            model, fixtures.domain_anchors(darts, [PALETTE] * 5))
        self.assertEqual(result["status"], "underdetermined")
        self.assertEqual(result["domains"], [list(PALETTE)] * 5)
        self.assertFalse(any(all(names[a] != names[b] for a, b in adjacent)
                             for names in product(PALETTE, repeat=5)))
        self.assert_fixed_point(result)

    def test_empty_domain_and_adjacent_equal_singletons_report_conflict(self):
        """No artificial choice is needed to recognize already bad anchors."""
        model, darts = fixtures.constraint_model(2, [(0, 1)])
        for domains in (((), PALETTE), ((2,), (2,))):
            with self.subTest(domains=domains):
                anchors = fixtures.domain_anchors(darts, domains)
                original = deepcopy(anchors)
                result = propagate_frontier_relations(model, anchors)
                self.assertEqual(result["status"], "conflict")
                self.assertEqual(result["choices"], 0)
                self.assertEqual(result["backtracks"], 0)
                self.assertEqual(anchors, original)

    def test_bridge_self_relations_preserve_the_whole_supplied_domain(self):
        """A bridge has one shore identity twice, not two unequal colors."""
        model, darts = fixtures.constraint_model(1, [])
        result = propagate_frontier_relations(
            model, fixtures.domain_anchors(darts, [(1, 3)]))
        self.assertEqual(result["status"], "underdetermined")
        self.assertEqual(result["domains"], [[1, 3]])
        self.assertEqual(relation_pairs(result["relations"][0][0]), {(1, 1), (3, 3)})

    def test_input_validation_cannot_be_bypassed_by_the_new_filter(self):
        """Reject nonexistent symbols/darts and falsely asserted cliques."""
        model, darts = fixtures.constraint_model(3, [(0, 1), (1, 2)])
        for anchors in ({darts[0]: [0]}, {darts[0]: [5]}, {-1: [1]}, {99: [1]}):
            with self.subTest(anchors=anchors):
                with self.assertRaises(ValueError):
                    propagate_frontier_relations(model, anchors)
        with self.assertRaises(ValueError):
            propagate_frontier_relations(model, {}, [(0, 1, 2)])

    def test_all_simple_graphs_through_four_shores_preserve_all_solutions(self):
        """Check 75 graphs x six declared domain patterns, including ALL pairs.

        The independent oracle enumerates at most 4**4 assignments per graph.
        No conclusion is drawn from a nonempty filter result without solutions.
        """
        checked = 0
        retained_assignments = 0
        for size in range(1, 5):
            possible = tuple(combinations(range(size), 2))
            patterns = (
                [PALETTE] * size,
                [(1, 2)] * size,
                [(1, 2, 3)] * size,
                [((1, 2) if side % 2 == 0 else (2, 3)) for side in range(size)],
                [((1,) if side == 0 else PALETTE) for side in range(size)],
                [((side % 4 + 1,) if side % 2 == 0 else (1, 3, 4))
                 for side in range(size)],
            )
            for flags in product((False, True), repeat=len(possible)):
                adjacent = [edge for edge, present in zip(possible, flags) if present]
                model, darts = fixtures.constraint_model(size, adjacent)
                proper = [names for names in product(PALETTE, repeat=size)
                          if all(names[a] != names[b] for a, b in adjacent)]
                for domains in patterns:
                    context = (size, adjacent, domains)
                    compatible = [names for names in proper
                                  if all(name in domain for name, domain in zip(names, domains))]
                    result = propagate_frontier_relations(
                        model, fixtures.domain_anchors(darts, domains))
                    self.assertTrue(all(set(after) <= set(before) for after, before
                                        in zip(result["domains"], domains)), context)
                    self.assertEqual(result["choices"], 0, context)
                    self.assertEqual(result["backtracks"], 0, context)
                    if result["status"] == "conflict":
                        self.assertFalse(compatible, context)
                    else:
                        self.assert_fixed_point(result)
                    for names in compatible:
                        self.assertNotEqual(result["status"], "conflict", context)
                        for i, a in enumerate(names):
                            self.assertIn(a, result["domains"][i], context)
                            for j, b in enumerate(names):
                                self.assertIn((a, b), relation_pairs(result["relations"][i][j]),
                                              context)
                    if result["status"] == "solved":
                        self.assertIn(tuple(domain[0] for domain in result["domains"]),
                                      compatible, context)
                    checked += 1
                    retained_assignments += len(compatible)
        self.assertEqual(checked, 450)
        self.assertGreater(retained_assignments, 0)


class RelationFrontierRestartTests(unittest.TestCase):
    """Real geometric inputs check fresh anchoring, bridge rules and regressions."""

    @classmethod
    def setUpClass(cls):
        """Reuse the established Node geometry-only fixtures without coloring."""
        fixtures.FrontierRestartTests.setUpClass()
        cls.geometry = fixtures.FrontierRestartTests.geometry
        cls.models = fixtures.FrontierRestartTests.models
        manifest = ROOT / "docs/figures/frontier-regression-audit-2026-09-19/manifest.json"
        cls.regression = json.loads(manifest.read_text(encoding="utf-8"))

    def assert_legal_result(self, geometry, result):
        """Check every actual boundary and every committed dart independently."""
        plane = build_whole_lines(geometry).plane_map
        self.assertEqual(result["status"], "solved")
        self.assertEqual(result["domains"], [[name] for name in result["colors"]])
        self.assertTrue(plane.check_coloring([name - 1 for name in result["colors"]]))
        self.assertEqual(result["colors"][geometry["outerFace"]], 1)
        self.assertEqual(result["policy"], "tight-hall-relations")
        self.assertEqual(result["backtracks"], 0)
        self.assertEqual(result["choices"], len(result["trace"]))
        for dart, allowed in result["anchors_by_dart"].items():
            self.assertIn(result["colors"][plane.face_of_dart[dart]], allowed)

    def test_restart_ignores_old_colors_and_does_not_mutate_geometry(self):
        """Unknown stale metadata cannot become an undeclared coloring oracle."""
        clean = self.geometry["grid"]
        poisoned = deepcopy(clean)
        poisoned.update({"colors": [99], "old_colors": {0: 99},
                         "anchors_by_dart": {0: [99]}, "names": [[99, 99]]})
        before = deepcopy(poisoned)
        result = restart_relation_frontier_names(poisoned)
        self.assertEqual(result, restart_relation_frontier_names(clean))
        self.assertEqual(poisoned, before)
        self.assertFalse(result["old_colors_read"])
        self.assert_legal_result(clean, result)

    def test_blank_bridge_and_island_respect_real_and_virtual_bridges(self):
        """Dangling strokes do not add a face; virtual joins add no inequality."""
        for key in ("blank", "bridge", "island"):
            with self.subTest(key=key):
                result = restart_relation_frontier_names(self.geometry[key])
                self.assert_legal_result(self.geometry[key], result)
                self.assertEqual(sorted(result["initial_anchors_by_dart"].values()), [[1], [2]])
                if key in ("blank", "bridge"):
                    self.assertEqual(result["choices"], 0)
                    self.assertEqual(len(result["colors"]), 2)
                for edge in self.models[key].virtual_edges:
                    a, b = self.models[key].plane_map.shores(edge)
                    self.assertEqual(a, b)

    def test_geometry_equivalence_and_repeated_calls_are_deterministic(self):
        """Direction, insertion order and degree-two splits do not decide names."""
        for baseline, variants in (("grid", ("grid-reordered", "grid-reversed")),
                                   ("horizontal", ("degree-two",))):
            result = restart_relation_frontier_names(self.geometry[baseline])
            self.assert_legal_result(self.geometry[baseline], result)
            self.assertEqual(result, restart_relation_frontier_names(self.geometry[baseline]))
            expected = fixtures.side_profile(self.models[baseline], result["domains"])
            for key in variants:
                alternate = restart_relation_frontier_names(self.geometry[key])
                self.assert_legal_result(self.geometry[key], alternate)
                self.assertEqual(fixtures.side_profile(self.models[key], alternate["domains"]),
                                 expected)

    def test_known_regression_prunes_fatal_second_name_before_commitment(self):
        """Old first commitment was safe; old side 6 = 2 must no longer survive."""
        geometry = self.regression["geometry"]
        model = build_whole_lines(geometry)
        previous = self.regression["new_result"]
        anchors = {int(dart): names for dart, names in previous["initial_anchors_by_dart"].items()}
        first, fatal = previous["trace"][:2]
        self.assertEqual((first["side"], first["symbol"]), (7, 3))
        self.assertEqual((fatal["side"], fatal["symbol"]), (6, 2))
        anchors[first["dart"]] = [first["symbol"]]
        self.assertEqual(propagate_hall(model, anchors)["domains"][fatal["side"]], [2, 4])
        result = propagate_frontier_relations(model, anchors)
        self.assertNotEqual(result["status"], "conflict")
        self.assertEqual(result["domains"][fatal["side"]], [4])
        self.assertEqual(result["choices"], 0)
        # A witness from the archived audit is checked, never fed to production.
        witness = self.regression["first_commitment_extension"]
        for side, name in enumerate(witness):
            self.assertIn(name, result["domains"][side])
        self.assert_legal_result(geometry, restart_relation_frontier_names(geometry))

    def test_every_commitment_replays_unchanged_priorities_and_recorded_filters(self):
        """Only propagation changes: the previous tight-degree schedule remains.

        Scores are independently recomputed here without frontier_priorities.
        Every recorded filter call must precede exactly one choice, except for
        the final status, and no inferred singleton is mislabeled as a choice.
        """
        for geometry in (self.geometry["grid"], self.regression["geometry"]):
            model = build_whole_lines(geometry)
            result = restart_relation_frontier_names(geometry)
            units = current_segments(model)
            neighbors = neighbor_sets(model)
            anchors = deepcopy(result["initial_anchors_by_dart"])
            self.assertEqual(len(result["propagation_phases"]), len(result["trace"]) + 1)
            for step, recorded in zip(result["trace"], result["propagation_phases"]):
                filtered = propagate_frontier_relations(model, anchors)
                self.assertEqual(recorded["anchors_by_dart"], anchors)
                self.assertEqual(recorded["outcome"], filtered)
                self.assertEqual(filtered["status"], "underdetermined")
                domains = filtered["domains"]
                support = supported_cycle_units(model, domains, units)
                rows = []
                for unit in units:
                    unresolved = [(side, dart) for side, dart in unit["occurrences"]
                                  if len(domains[side]) > 1]
                    if not unresolved:
                        continue
                    scores = [(4 - len(domains[side]),
                               sum(len(domains[n]) > 1 for n in neighbors[side]))
                              for side, _ in unresolved]
                    selected = scores.index(max(scores))
                    side, dart = unresolved[selected]
                    total = sum(4 - len(domains[s]) for s, _ in unresolved)
                    priority = scores[selected] + (total, int(support[unit["id"]]["supported"]))
                    rows.append((priority, unit, side, dart))
                highest = max(row[0] for row in rows)
                tied = sorted((row for row in rows if row[0] == highest),
                              key=lambda row: (row[1]["mother"], row[1]["t0"]))
                _, unit, side, dart = tied[0]
                self.assertEqual(step["unit"], unit["id"])
                self.assertEqual((step["side"], step["dart"]), (side, dart))
                self.assertEqual(tuple(step["priority"]), highest)
                self.assertEqual(step["tied_units"], [row[1]["id"] for row in tied])
                used = {domain[0] for domain in domains if len(domain) == 1}
                name = min(domains[side], key=lambda value: (value not in used, value))
                self.assertEqual(step["symbol"], name)
                self.assertEqual(step["choice_kind"], "greedy-not-a-proved-safe-extension")
                anchors[dart] = [name]
            final = result["propagation_phases"][-1]
            self.assertEqual(final["anchors_by_dart"], anchors)
            self.assertEqual(final["outcome"], propagate_frontier_relations(model, anchors))
            self.assertEqual(final["outcome"]["domains"], result["domains"])
            self.assertEqual(anchors, result["anchors_by_dart"])


if __name__ == "__main__":
    unittest.main()

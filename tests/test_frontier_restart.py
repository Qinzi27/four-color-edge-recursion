"""Independent checks for tight-side scheduling and small-clique propagation.

Exhaustive assignment enumeration lives ONLY in these tests. It checks that
Hall-domain deductions preserve every compatible coloring; it neither supplies
production decisions nor establishes completion on arbitrary planar maps.
"""

from copy import deepcopy
from itertools import combinations, product
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest

from fourcolor.closed_support import supported_cycle_units
from fourcolor.frontier_restart import (
    frontier_priorities, neighbor_sets, propagate_hall, restart_frontier_names,
    small_cliques,
)
from fourcolor.global_restart import current_segments
from fourcolor.whole_lines import build_whole_lines, propagate_candidates


ROOT = Path(__file__).resolve().parents[1]
POLICIES = ("anchored-pressure", "tight-frontier", "tight-degree", "tight-hall")


def constraint_model(size, adjacent):
    """Make a constraint-kernel test double, NOT a claimed plane embedding.

    The pair for each fake edge records its two shores. A same-shore edge per
    side supplies an anchor occurrence even for isolated nodes and additionally
    exercises the rule that bridges cannot introduce inequality constraints.
    """
    pairs = tuple(adjacent) + tuple((side, side) for side in range(size))
    darts = tuple(side for pair in pairs for side in pair)
    plane = SimpleNamespace(
        edges=tuple((str(index), str(index + 1)) for index in range(len(pairs))),
        faces=tuple(tuple(dart for dart, value in enumerate(darts) if value == side)
                    for side in range(size)),
        face_of_dart=darts,
        shores=lambda edge: pairs[edge],
    )
    model = SimpleNamespace(plane_map=plane, edge_owner={}, virtual_edges=(), lines=[])
    representatives = tuple(2 * (len(adjacent) + side) for side in range(size))
    return model, representatives


def domain_anchors(representatives, domains):
    """Express allowed side symbols as actual dart-addressed constraints."""
    return {dart: list(domain) for dart, domain in zip(representatives, domains)}


def priority_unit(identifier, occurrences, t0=0):
    """Construct only geometry metadata consumed by the pure priority helper."""
    return {"id": identifier, "mother": identifier.split("@")[0], "t0": t0,
            "t1": 1, "occurrences": occurrences, "same_single_mother": False}


def side_profile(model, domains):
    """Compare geometric left/right names without depending on raw face IDs."""
    profile = []
    for line in model.lines:
        spans = []
        for span in line["spans"]:
            pair = (tuple(domains[span["left_side"]]), tuple(domains[span["right_side"]]))
            first, last = round(span["t0"], 10), round(span["t1"], 10)
            if spans and spans[-1][1] == first and spans[-1][2] == pair:
                spans[-1] = (spans[-1][0], last, pair)
            else:
                spans.append((first, last, pair))
        profile.append((line["id"], tuple(spans)))
    return tuple(profile)


class HallPropagationTests(unittest.TestCase):
    """Check only sound deductions, never equate consistency with completion."""

    def test_neighbors_deduplicate_parallel_boundaries_and_ignore_same_side(self):
        """One neighbor identity counts once, regardless of repeated boundaries."""
        model, _ = constraint_model(3, [(0, 1), (0, 1), (1, 2)])
        self.assertEqual(neighbor_sets(model), [{1}, {0, 2}, {1}])
        self.assertEqual(small_cliques(neighbor_sets(model)), [])

    def test_small_cliques_equal_an_independent_subset_oracle(self):
        """Exhaust all 1,099 simple graphs on one through five nodes."""
        checked = 0
        for size in range(1, 6):
            possible = tuple(combinations(range(size), 2))
            for flags in product((False, True), repeat=len(possible)):
                adjacent = [pair for pair, present in zip(possible, flags) if present]
                model, _ = constraint_model(size, adjacent)
                relations = {frozenset(pair) for pair in adjacent}
                expected = {group for count in (3, 4)
                            for group in combinations(range(size), count)
                            if all(frozenset(pair) in relations for pair in combinations(group, 2))}
                actual = small_cliques(neighbor_sets(model))
                self.assertEqual(set(actual), expected)
                self.assertEqual(len(actual), len(set(actual)))
                self.assertTrue(all(tuple(sorted(group)) == group for group in actual))
                checked += 1
        self.assertEqual(checked, 1099)

    def test_hall_pair_removes_two_names_without_selecting_an_assignment(self):
        """Two unresolved neighbors occupy {1,2}, without choosing their order."""
        model, darts = constraint_model(3, [(0, 1), (0, 2), (1, 2)])
        anchors = domain_anchors(darts, [(1, 2), (1, 2), (1, 2, 3, 4)])
        before = deepcopy(anchors)
        ordinary = propagate_candidates(model, anchors)
        result = propagate_hall(model, anchors)
        self.assertEqual(ordinary["domains"], [[1, 2], [1, 2], [1, 2, 3, 4]])
        self.assertEqual(result["domains"], [[1, 2], [1, 2], [3, 4]])
        self.assertEqual(result["status"], "underdetermined")
        self.assertEqual(result["choices"], 0)
        self.assertEqual(result["backtracks"], 0)
        self.assertEqual(result["palette"], [1, 2, 3, 4])
        self.assertEqual(anchors, before)

    def test_hall_triple_in_k4_forces_the_fourth_name(self):
        """A complete four-side neighborhood has a genuine all-different rule."""
        model, darts = constraint_model(4, list(combinations(range(4), 2)))
        anchors = domain_anchors(darts, [(1, 2, 3)] * 3 + [(1, 2, 3, 4)])
        result = propagate_hall(model, anchors)
        self.assertEqual(result["domains"], [[1, 2, 3]] * 3 + [[4]])
        self.assertEqual(result, propagate_hall(model, anchors, small_cliques(neighbor_sets(model))))

    def test_hall_deficiency_is_detected_before_any_singleton_exists(self):
        """Three mutually adjacent sides cannot share only two available names."""
        model, darts = constraint_model(3, [(0, 1), (0, 2), (1, 2)])
        anchors = domain_anchors(darts, [(1, 2)] * 3)
        self.assertEqual(propagate_candidates(model, anchors)["status"], "underdetermined")
        result = propagate_hall(model, anchors)
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["choices"], 0)
        self.assertEqual(result["backtracks"], 0)

    def test_nonclique_candidates_are_not_treated_as_all_different(self):
        """The endpoints of a path may legitimately repeat a symbol."""
        model, darts = constraint_model(3, [(0, 1), (1, 2)])
        result = propagate_hall(model, domain_anchors(darts, [(1, 2)] * 3))
        self.assertEqual(result["status"], "underdetermined")
        self.assertEqual(result["domains"], [[1, 2]] * 3)

    def test_local_consistency_is_not_reported_as_a_completion_guarantee(self):
        """An odd cycle with two-symbol domains defeats this local filter."""
        adjacent = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 4)]
        model, darts = constraint_model(5, adjacent)
        result = propagate_hall(model, domain_anchors(darts, [(1, 2)] * 5))
        self.assertEqual(result["status"], "underdetermined")
        self.assertEqual(result["domains"], [[1, 2]] * 5)
        completions = [names for names in product((1, 2), repeat=5)
                       if all(names[first] != names[second] for first, second in adjacent)]
        self.assertEqual(completions, [])

    def test_hall_and_singletons_iterate_until_the_same_fixed_point(self):
        """A Hall-forced name must propagate through a following ordinary chain."""
        model, darts = constraint_model(5, [(0, 1), (0, 2), (1, 2), (2, 3), (3, 4)])
        domains = [(1, 2), (1, 2), (1, 2, 3), (3, 4), (1, 4)]
        result = propagate_hall(model, domain_anchors(darts, domains))
        self.assertEqual(result["domains"], [[1, 2], [1, 2], [3], [4], [1]])
        restarted = propagate_hall(model, domain_anchors(darts, result["domains"]))
        self.assertEqual(restarted["domains"], result["domains"])
        self.assertEqual(restarted["status"], result["status"])

    def test_invalid_anchor_symbols_and_darts_are_rejected(self):
        """The stronger filter must not bypass the existing input contract."""
        model, darts = constraint_model(2, [(0, 1)])
        for anchors in ({darts[0]: [0]}, {darts[0]: [5]}, {-1: [1]}, {99: [1]}):
            with self.subTest(anchors=anchors):
                with self.assertRaises(ValueError):
                    propagate_hall(model, anchors)

    def test_caller_supplied_cliques_cannot_invent_an_all_different_relation(self):
        """An optional cache is validated, not accepted as a mathematical axiom."""
        model, _ = constraint_model(4, [(0, 1), (1, 2), (2, 3), (0, 3)])
        for cliques in ([(0, 1, 2)], [(0, 1, 2, 3)], [(0, 0, 1)], [(0, 1, 4)]):
            with self.subTest(cliques=cliques):
                with self.assertRaises(ValueError):
                    propagate_hall(model, {}, cliques)

    def test_small_domain_corpus_preserves_every_oracle_completion(self):
        """Exhaust the declared six-domain pool on five tiny adjacency families.

        The oracle enumerates 4**n assignments independently of Hall subsets,
        propagation order and production scheduling. A nonempty fixed point is
        NOT asserted to possess a completion: only sound pruning is required.
        """
        families = (
            (3, [(0, 1), (0, 2), (1, 2)]),
            (4, list(combinations(range(4), 2))),
            (4, [(0, 1), (0, 2), (1, 2), (1, 3), (2, 3)]),
            (4, [(0, 1), (1, 2), (2, 3), (0, 3)]),
            (4, [(0, 1), (1, 2), (2, 3)]),
        )
        pool = ((1,), (1, 2), (2, 3), (1, 2, 3), (2, 3, 4), (1, 2, 3, 4))
        checked, satisfiable = 0, 0
        for size, adjacent in families:
            model, darts = constraint_model(size, adjacent)
            proper = [names for names in product(range(1, 5), repeat=size)
                      if all(names[first] != names[second] for first, second in adjacent)]
            cliques = small_cliques(neighbor_sets(model))
            for domains in product(pool, repeat=size):
                compatible = [names for names in proper
                              if all(name in domain for name, domain in zip(names, domains))]
                result = propagate_hall(model, domain_anchors(darts, domains), cliques)
                context = (adjacent, domains, result)
                self.assertTrue(all(set(after) <= set(before)
                                    for after, before in zip(result["domains"], domains)), context)
                if result["status"] == "conflict":
                    self.assertFalse(compatible, context)
                for names in compatible:
                    self.assertNotEqual(result["status"], "conflict", context)
                    self.assertTrue(all(name in domain for name, domain in
                                        zip(names, result["domains"])), context)
                if result["status"] == "solved":
                    self.assertIn(tuple(domain[0] for domain in result["domains"]), compatible, context)
                checked += 1
                satisfiable += bool(compatible)
        self.assertEqual(checked, 5400)
        self.assertGreater(satisfiable, 0)


class FrontierPriorityTests(unittest.TestCase):
    """The selected occurrence, not just the sum over its line, is constrained."""

    def test_tighter_side_beats_equal_total_weight_and_closed_support(self):
        """A tight second occurrence must not lose to a loose first occurrence."""
        domains = [[1, 2, 3], [2, 3, 4], [1, 2, 3, 4], [2, 4]]
        units = [priority_unit("A@0", [(0, 0), (1, 2)]),
                 priority_unit("B@0", [(2, 4), (3, 6)])]
        support = {"A@0": {"supported": True}, "B@0": {"supported": False}}
        rows = frontier_priorities(units, domains, [set() for _ in domains], support)
        best = max(rows, key=lambda row: row["priority"])
        self.assertEqual(best["unit"], "B@0")
        self.assertEqual((best["side"], best["dart"]), (3, 6))
        self.assertEqual(tuple(best["priority"]), (2, 2, 0))

    def test_degree_uses_unresolved_distinct_neighbors_and_can_change_occurrence(self):
        """Resolved neighbors do not inflate a still-unresolved degree count."""
        domains = [[1, 2, 3], [1, 2, 3], [1, 2], [2, 3], [4]]
        units = [priority_unit("A@0", [(1, 2), (0, 0)])]
        neighbors = [{2, 3}, {2, 4}, {0, 1}, {0}, {1}]
        support = {"A@0": {"supported": False}}
        ordinary = frontier_priorities(units, domains, neighbors, support)[0]
        enhanced = frontier_priorities(units, domains, neighbors, support, degree=True)[0]
        self.assertEqual((ordinary["side"], ordinary["dart"]), (1, 2))
        self.assertEqual((enhanced["side"], enhanced["dart"]), (0, 0))
        self.assertEqual(tuple(enhanced["priority"]), (1, 2, 2, 0))

    def test_resolved_units_are_omitted_and_equal_scores_keep_occurrence_order(self):
        """Tie resolution must not sort by arbitrary raw side or dart numbers."""
        domains = [[1], [2], [1, 3], [2, 4]]
        units = [priority_unit("resolved@0", [(0, 0), (1, 2)]),
                 priority_unit("active@0", [(3, 6), (2, 4)])]
        support = {unit["id"]: {"supported": False} for unit in units}
        for degree in (False, True):
            rows = frontier_priorities(units, domains, [set() for _ in domains], support, degree)
            self.assertEqual(len(rows), 1)
            self.assertEqual((rows[0]["side"], rows[0]["dart"]), (3, 6))

    def test_anchored_pressure_keeps_named_side_weight_until_the_unit_finishes(self):
        """Candidate restriction cannot lower q_all on an unchanged active unit."""
        units = [priority_unit("A@0", [(0, 0), (1, 2)])]
        support = {"A@0": {"supported": False}}
        stages = ([[1, 2, 3], [1, 2, 3, 4]], [[1, 2], [1, 2, 3, 4]],
                  [[1], [2, 3, 4]], [[1], [2, 3]])
        weights = []
        for domains in stages:
            row = frontier_priorities(units, domains, [{1}, {0}], support, anchored=True)[0]
            weights.append(row["including_named_weight"])
            self.assertEqual(tuple(row["priority"]), (sum(4 - len(d) for d in domains), 0))
        self.assertEqual(weights, [1, 2, 4, 5])
        self.assertEqual(weights, sorted(weights))
        self.assertEqual(frontier_priorities(units, [[1], [2]], [{1}, {0}], support,
                                              anchored=True), [])

    def test_anchored_pressure_selects_first_unknown_not_the_tightest_side(self):
        """The aggregate-pressure control retains its separately declared order."""
        units = [priority_unit("A@0", [(0, 0), (1, 2)])]
        domains = [[1, 2, 3], [1, 2]]
        support = {"A@0": {"supported": True}}
        row = frontier_priorities(units, domains, [{1}, {0}], support, anchored=True)[0]
        self.assertEqual((row["side"], row["dart"]), (0, 0))
        self.assertEqual(tuple(row["priority"]), (3, 1))


class FrontierRestartTests(unittest.TestCase):
    """End-to-end checks use real exported geometry, never fake planar maps."""

    @classmethod
    def setUpClass(cls):
        """Export one geometry-only batch, with no naming algorithm in Node."""
        grid = [((x, 0), (x, 600)) for x in (300, 600)]
        grid += [((0, y), (900, y)) for y in (200, 400)]
        cuts = {"blank": [], "bridge": [((0, 300), (350, 300))],
                "horizontal": [((0, 300), (900, 300))],
                "degree-two": [((0, 300), (333, 300)), ((333, 300), (900, 300))],
                "grid": grid, "grid-reordered": list(reversed(grid)),
                "grid-reversed": [(second, first) for first, second in grid],
                "island": [((300, 200), (600, 200)), ((600, 200), (600, 400)),
                           ((600, 400), (300, 400)), ((300, 400), (300, 200))]}
        cases = [{"key": key, "document": {"frame": {"width": 900, "height": 600},
                  "strokes": [{"a": first, "b": second} for first, second in value]}}
                 for key, value in cuts.items()]
        process = subprocess.run(["node", "scripts/restart-geometry.mjs"], cwd=ROOT,
                                 input=json.dumps({"cases": cases}), capture_output=True,
                                 text=True, encoding="utf-8", check=True)
        exported = json.loads(process.stdout)
        if exported["coloring_performed"]:
            raise AssertionError("geometry export unexpectedly selected names")
        if any(row["status"] != "geometry_ok" for row in exported["results"]):
            raise AssertionError("declared geometry fixture did not export")
        cls.geometry = {row["key"]: row["geometry"] for row in exported["results"]}
        cls.models = {key: build_whole_lines(value) for key, value in cls.geometry.items()}

    def assert_legal_result(self, geometry, result):
        """Check solved names and every supplied dart anchor by direct incidence."""
        plane = build_whole_lines(geometry).plane_map
        self.assertEqual(result["status"], "solved")
        self.assertEqual(result["domains"], [[name] for name in result["colors"]])
        self.assertTrue(plane.check_coloring([name - 1 for name in result["colors"]]))
        for dart, permitted in result["anchors_by_dart"].items():
            self.assertIn(result["colors"][plane.face_of_dart[dart]], permitted)
        self.assertEqual(result["colors"][geometry["outerFace"]], 1)

    def test_each_policy_discards_old_names_without_mutating_geometry(self):
        """Poisoned previous color fields cannot affect a geometry-only restart."""
        geometry = deepcopy(self.geometry["grid"])
        geometry.update({"colors": [99], "old_colors": {0: 99},
                         "anchors_by_dart": {0: [99]}, "names": [[99, 99]]})
        before = deepcopy(geometry)
        for policy in POLICIES:
            result = restart_frontier_names(geometry, policy)
            self.assertEqual(result, restart_frontier_names(self.geometry["grid"], policy))
            self.assertFalse(result["old_colors_read"])
            self.assertEqual(result["backtracks"], 0)
            self.assertEqual(result["choices"], len(result["trace"]))
            self.assert_legal_result(geometry, result)
        self.assertEqual(geometry, before)

    def test_blank_bridge_and_virtual_island_do_not_create_false_inequalities(self):
        """Real and virtual bridges both retain the same shore on both sides."""
        for key in ("blank", "bridge", "island"):
            for policy in POLICIES:
                with self.subTest(key=key, policy=policy):
                    geometry, model = self.geometry[key], self.models[key]
                    result = restart_frontier_names(geometry, policy)
                    self.assert_legal_result(geometry, result)
                    self.assertEqual(result["backtracks"], 0)
                    if key in ("blank", "bridge"):
                        self.assertEqual(result["choices"], 0)
                        self.assertEqual(len(result["colors"]), 2)
                    for side, adjacent in enumerate(neighbor_sets(model)):
                        self.assertNotIn(side, adjacent)
                    for edge in model.virtual_edges:
                        self.assertEqual(*model.plane_map.shores(edge))

    def test_geometry_order_direction_and_degree_two_subdivision_are_deterministic(self):
        """Stable geometric IDs decide ties, not insertion order or raw face IDs."""
        for policy in POLICIES:
            for baseline, variants in (("grid", ("grid-reordered", "grid-reversed")),
                                       ("horizontal", ("degree-two",))):
                result = restart_frontier_names(self.geometry[baseline], policy)
                expected = side_profile(self.models[baseline], result["domains"])
                self.assertEqual(result, restart_frontier_names(self.geometry[baseline], policy))
                for variant in variants:
                    actual = restart_frontier_names(self.geometry[variant], policy)
                    self.assertEqual(actual["status"], result["status"])
                    self.assertEqual(side_profile(self.models[variant], actual["domains"]), expected)

    def test_every_commitment_independently_replays_its_side_and_unit_priorities(self):
        """Rebuild scores without calling the production priority helper."""
        geometry, model = self.geometry["grid"], self.models["grid"]
        units = current_segments(model)
        neighbors = [set() for _ in model.plane_map.faces]
        for edge in range(len(model.plane_map.edges)):
            left, right = model.plane_map.shores(edge)
            if left != right:
                neighbors[left].add(right)
                neighbors[right].add(left)
        for policy in POLICIES:
            result = restart_frontier_names(geometry, policy)
            anchors = deepcopy(result["initial_anchors_by_dart"])
            self.assertEqual(sorted(anchors.values()), [[1], [2]])
            first, second = anchors
            self.assertEqual(first ^ 1, second)
            for step in result["trace"]:
                propagation = propagate_hall if policy == "tight-hall" else propagate_candidates
                domains = propagation(model, anchors)["domains"]
                support = supported_cycle_units(model, domains, units)
                available = []
                for unit in units:
                    unresolved = [(side, dart) for side, dart in unit["occurrences"]
                                  if len(domains[side]) > 1]
                    if not unresolved:
                        continue
                    individual = [(4 - len(domains[side]),) +
                                  ((sum(len(domains[other]) > 1 for other in neighbors[side]),)
                                   if policy in ("tight-degree", "tight-hall") else ())
                                  for side, _ in unresolved]
                    position = 0 if policy == "anchored-pressure" else individual.index(max(individual))
                    side, dart = unresolved[position]
                    total = sum(4 - len(domains[other]) for other in {s for s, _ in unresolved})
                    if policy == "anchored-pressure":
                        total = sum(4 - len(domains[other]) for other in
                                    {s for s, _ in unit["occurrences"]})
                        score = (total, int(support[unit["id"]]["supported"]))
                    else:
                        score = individual[position] + (total, int(support[unit["id"]]["supported"]))
                    available.append((score, unit, side, dart))
                highest = max(row[0] for row in available)
                tied = sorted((row for row in available if row[0] == highest),
                              key=lambda row: (row[1]["mother"], row[1]["t0"]))
                _, selected, side, dart = tied[0]
                self.assertEqual(step["unit"], selected["id"])
                self.assertEqual(tuple(step["priority"]), highest)
                self.assertEqual((step["side"], step["dart"]), (side, dart))
                self.assertEqual(step["tied_units"], [row[1]["id"] for row in tied])
                used = {domain[0] for domain in domains if len(domain) == 1}
                expected_name = min(domains[side], key=lambda name: (name not in used, name))
                self.assertEqual(step["symbol"], expected_name)
                self.assertNotIn(dart, anchors)
                anchors[dart] = [expected_name]
            self.assertEqual(anchors, result["anchors_by_dart"])
            self.assert_legal_result(geometry, result)

    def test_unknown_policy_is_rejected(self):
        """An unrecognized strategy must not silently switch algorithm."""
        with self.assertRaises(ValueError):
            restart_frontier_names(self.geometry["blank"], "unknown")


if __name__ == "__main__":
    unittest.main()

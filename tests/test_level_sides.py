"""Checks for generation-first whole mothers and current local side evidence.

The fixtures test implementation contracts, not completion for arbitrary maps.
An ancestor's color is never an automatic inherited ban; all present boundary
neighbors still matter, including an internal neighbor that already uses 1.
"""

from copy import deepcopy
import unittest

from fourcolor.closed_support import supported_cycle_units
from fourcolor.frontier_restart import frontier_priorities, neighbor_sets
from fourcolor.global_restart import current_segments
from fourcolor.level_sides import (
    effective_boundary, level_metadata, restart_level_side_names,
)
from fourcolor.relation_frontier import propagate_frontier_relations
from fourcolor.whole_lines import build_whole_lines
from scripts.validate_global_restart import export_geometries
from scripts.validate_level_sides import verify_run
from tests.test_frontier_restart import side_profile


PALETTE = [1, 2, 3, 4]


class LevelSideTests(unittest.TestCase):
    """Real exported geometry supplies both incidence and complete mother IDs."""

    @classmethod
    def setUpClass(cls):
        """Export a deterministic geometry-only batch, without selecting colors."""
        grid = [((x, 0), (x, 600)) for x in (300, 600)]
        grid += [((0, y), (900, y)) for y in (200, 400)]
        sibling_lines = [((544, 0), (544, 600))]
        sibling_lines += [((0, y), (544, y)) for y in (254, 274, 318, 422)]
        cuts = {
            "blank": [],
            "horizontal": [((0, 300), (900, 300))],
            "degree-two": [((0, 300), (333, 300)), ((333, 300), (900, 300))],
            "T": [((0, 300), (900, 300)), ((450, 300), (450, 600))],
            "X": [((0, 300), (900, 300)), ((450, 0), (450, 600))],
            "siblings": sibling_lines,
            "grid": grid,
            "grid-reordered": list(reversed(grid)),
            "grid-reversed": [(end, start) for start, end in grid],
            "dangling": [((0, 300), (350, 300))],
            "island": [((300, 200), (600, 200)), ((600, 200), (600, 400)),
                       ((600, 400), (300, 400)), ((300, 400), (300, 200))],
        }
        cases = [{"key": key, "document": {"strokes": [
            {"a": start, "b": end} for start, end in strokes]}}
                 for key, strokes in cuts.items()]
        exported = export_geometries(cases)
        cls.geometry = {row["key"]: row["geometry"] for row in exported}
        cls.models = {key: build_whole_lines(value) for key, value in cls.geometry.items()}

    def grid_context(self):
        """Find the unique central grid side using adjacency, not a face number."""
        model = self.models["grid"]
        outer = self.geometry["grid"]["outerFace"]
        adjacent = [set() for _ in model.plane_map.faces]
        for edge in range(len(model.plane_map.edges)):
            first, second = model.plane_map.shores(edge)
            if first != second:
                adjacent[first].add(second)
                adjacent[second].add(first)
        internal = [side for side in range(len(adjacent))
                    if side != outer and outer not in adjacent[side]]
        self.assertEqual(len(internal), 1)
        domains = [list(PALETTE) for _ in adjacent]
        domains[outer] = [1]
        return model, outer, internal[0], adjacent, domains

    def assert_boundary(self, model, domains, side, actual):
        """Rebuild actual opposite shores directly from every real primal edge."""
        expected = {}
        spans = {span["edge"]: span for line in model.lines for span in line["spans"]}
        for edge, mother in model.edge_owner.items():
            first, second = model.plane_map.shores(edge)
            if first == second or side not in (first, second):
                continue
            neighbor = second if first == side else first
            expected[edge] = (mother, neighbor, domains[neighbor],
                              [spans[edge]["t0"], spans[edge]["t1"]])
        self.assertEqual(len(actual["sources"]), len(expected))
        self.assertEqual({source["edge"] for source in actual["sources"]}, set(expected))
        for source in actual["sources"]:
            mother, neighbor, domain, interval = expected[source["edge"]]
            self.assertEqual(source["mother"], mother)
            self.assertEqual(source["neighbor"], neighbor)
            self.assertEqual(source["neighbor_domain"], domain)
            self.assertEqual(source["interval"], interval)
        forbidden = {domain[0] for _, _, domain, _ in expected.values() if len(domain) == 1}
        local = set(PALETTE) - forbidden
        self.assertEqual(actual["direct_forbidden"], sorted(forbidden))
        self.assertEqual(actual["local_candidates"], sorted(local))
        self.assertEqual(actual["derived_exclusions"], sorted(local - set(domains[side])))
        self.assertEqual(actual["one_allowed"], 1 in domains[side])

    def assert_legal_result(self, geometry, result):
        """Verify a finished coloring independently of the scheduling policy."""
        model = build_whole_lines(geometry)
        self.assertEqual(result["status"], "solved")
        self.assertEqual(result["domains"], [[name] for name in result["colors"]])
        self.assertTrue(all(name in PALETTE for name in result["colors"]))
        self.assertEqual(result["colors"][geometry["outerFace"]], 1)
        for edge in range(len(model.plane_map.edges)):
            first, second = model.plane_map.shores(edge)
            if first != second:
                self.assertNotEqual(result["colors"][first], result["colors"][second])
        for dart, allowed in result["anchors_by_dart"].items():
            self.assertIn(result["colors"][model.plane_map.face_of_dart[dart]], allowed)
        self.assertEqual(result["backtracks"], 0)
        self.assertFalse(result["old_colors_read"])
        self.assertEqual(result["choices"], len(result["trace"]))

    def test_frame_level_one_and_two_frame_endpoints_level_two(self):
        """Levels are structural labels, not additional coloring symbols."""
        levels = level_metadata(self.models["horizontal"])
        self.assertEqual(levels["frame"]["level"], 1)
        horizontal = levels["L:0,300>900,300"]
        self.assertEqual(horizontal["level"], 2)
        self.assertEqual(horizontal["parents"], [["frame"], ["frame"]])
        self.assertEqual(horizontal["endpoints"], [[0, 300], [900, 300]])

    def test_t_contact_does_not_restart_or_truncate_the_parent_mother(self):
        """The child's endpoint can meet a middle point of a complete mother."""
        levels = level_metadata(self.models["T"])
        self.assertEqual(levels["L:0,300>900,300"]["level"], 2)
        child = levels["L:450,300>450,600"]
        self.assertEqual(child["level"], 3)
        self.assertEqual(child["parents"], [["L:0,300>900,300"], ["frame"]])
        self.assertEqual(len(levels), 3)

    def test_x_contact_is_not_a_false_cyclic_parent_dependency(self):
        """Crossing mothers both retain their actual frame-to-frame endpoints."""
        levels = level_metadata(self.models["X"])
        for mother in ("L:0,300>900,300", "L:450,0>450,600"):
            self.assertEqual(levels[mother]["level"], 2)
            self.assertEqual(levels[mother]["parents"], [["frame"], ["frame"]])

    def test_same_parent_siblings_share_a_level_not_sequential_birth_numbers(self):
        """The user's four horizontal siblings all inherit frame plus blue line."""
        levels = level_metadata(self.models["siblings"])
        parent = "L:544,0>544,600"
        self.assertEqual(levels[parent]["level"], 2)
        for y in (254, 274, 318, 422):
            record = levels[f"L:0,{y}>544,{y}"]
            self.assertEqual(record["level"], 3)
            self.assertEqual(record["parents"], [["frame"], [parent]])

    def test_unrooted_and_dangling_mothers_have_unknown_level_not_fake_parents(self):
        """An absent two-ended ancestry is outside this policy's declared scope."""
        for key in ("dangling", "island"):
            with self.subTest(key=key):
                levels = level_metadata(self.models[key])
                self.assertTrue(any(row["level"] is None for name, row in levels.items()
                                    if name != "frame"))
                result = restart_level_side_names(self.geometry[key])
                self.assertEqual(result["status"], "outside_scope")
                self.assertIsNone(result["colors"])
                self.assertEqual(result["choices"], 0)
                self.assertEqual(result["backtracks"], 0)

    def test_outer_neighbor_forbids_one_but_remote_ancestor_does_not(self):
        """Interior adjacency, not all historical ancestor labels, defines a ban."""
        model, outer, center, adjacent, domains = self.grid_context()
        # These handcrafted domains isolate direct-boundary reporting from the
        # separate sound filter; restricting the boundary side matches its ban.
        boundary_side = min(adjacent[outer])
        domains[boundary_side] = [2, 3, 4]
        outer_record = effective_boundary(model, domains, boundary_side)
        center_record = effective_boundary(model, domains, center)
        self.assert_boundary(model, domains, boundary_side, outer_record)
        self.assert_boundary(model, domains, center, center_record)
        self.assertIn(1, outer_record["direct_forbidden"])
        self.assertFalse(outer_record["one_allowed"])
        self.assertNotIn(1, center_record["direct_forbidden"])
        self.assertTrue(center_record["one_allowed"])

    def test_another_internal_neighbor_using_one_still_forbids_one(self):
        """Leaving the exterior does not grant unconditional permission for 1."""
        model, _, center, adjacent, domains = self.grid_context()
        domains[min(adjacent[center])] = [1]
        domains[center] = [2, 3, 4]
        actual = effective_boundary(model, domains, center)
        self.assert_boundary(model, domains, center, actual)
        self.assertIn(1, actual["direct_forbidden"])
        self.assertFalse(actual["one_allowed"])
        self.assertEqual(len(actual["sources"]), 4)

    def test_derived_exclusions_are_not_mislabeled_as_direct_boundary_bans(self):
        """A filter's removal of 1 is distinguished from a neighboring fixed 1."""
        model, _, center, _, domains = self.grid_context()
        domains[center] = [2, 3]
        actual = effective_boundary(model, domains, center)
        self.assert_boundary(model, domains, center, actual)
        self.assertEqual(actual["direct_forbidden"], [])
        self.assertEqual(actual["local_candidates"], PALETTE)
        self.assertEqual(actual["derived_exclusions"], [1, 4])
        self.assertFalse(actual["one_allowed"])

    def test_bridge_sources_do_not_invent_self_inequality_constraints(self):
        """A dangling stroke has the same side twice and supplies no opposite ban."""
        model = self.models["dangling"]
        domains = [list(PALETTE) for _ in model.plane_map.faces]
        bridge_edges = {edge for edge in model.edge_owner
                        if model.plane_map.shores(edge)[0] == model.plane_map.shores(edge)[1]}
        self.assertTrue(bridge_edges)
        for side in range(len(domains)):
            actual = effective_boundary(model, domains, side)
            self.assert_boundary(model, domains, side, actual)
            self.assertFalse(bridge_edges & {source["edge"] for source in actual["sources"]})

    def test_small_rooted_drawings_finish_with_independently_valid_names(self):
        """Small fixtures are finite evidence, not an arbitrary-map guarantee."""
        for key in ("blank", "horizontal", "T", "X", "siblings", "grid"):
            with self.subTest(key=key):
                result = restart_level_side_names(self.geometry[key])
                self.assert_legal_result(self.geometry[key], result)
                self.assertEqual(sorted(result["initial_anchors_by_dart"].values()), [[1], [2]])

    def test_complete_grid_actually_reuses_one_on_an_internal_side(self):
        """Reusing 1 is observed in an actual run, not just a handcrafted domain."""
        _, outer, center, _, _ = self.grid_context()
        result = restart_level_side_names(self.geometry["grid"])
        self.assert_legal_result(self.geometry["grid"], result)
        self.assertEqual(result["colors"][outer], 1)
        self.assertEqual(result["colors"][center], 1)
        decision = next(step for step in result["trace"] if step["side"] == center)
        self.assertEqual(decision["symbol"], 1)
        self.assertTrue(decision["boundary"]["one_allowed"])
        self.assertNotIn(1, decision["boundary"]["direct_forbidden"])

    def test_every_choice_replays_lowest_mother_level_and_current_boundary_evidence(self):
        """Replay geometry-order selection separately from the unchanged filter."""
        for key in ("siblings", "grid"):
            model = self.models[key]
            result = restart_level_side_names(self.geometry[key])
            levels = level_metadata(model)
            anchors = deepcopy(result["initial_anchors_by_dart"])
            units = current_segments(model)
            by_id = {unit["id"]: unit for unit in units}
            neighbors = neighbor_sets(model)
            self.assertEqual(len(result["propagation_phases"]), len(result["trace"]) + 1)
            previous_level = 1
            for step, phase in zip(result["trace"], result["propagation_phases"]):
                filtered = propagate_frontier_relations(model, anchors)
                self.assertEqual(phase["anchors_by_dart"], anchors)
                self.assertEqual(phase["outcome"], filtered)
                domains = filtered["domains"]
                active = [line["id"] for line in model.lines if line["id"] != "frame"
                          and any(len(domains[side]) > 1 for span in line["spans"]
                                  for side in (span["left_side"], span["right_side"]))]

                def mother_key(name):
                    """Read endpoint coordinates numerically, never string-sort IDs."""
                    points = sorted((point[1], point[0]) for point in levels[name]["endpoints"])
                    return levels[name]["level"], tuple(points), name

                selected_mother = min(active, key=mother_key)
                self.assertEqual(step["mother"], selected_mother)
                self.assertNotEqual(step["mother"], "frame")
                self.assertEqual(step["level"], levels[selected_mother]["level"])
                self.assertEqual(step["parents"], levels[selected_mother]["parents"])
                self.assertGreaterEqual(step["level"], previous_level)
                previous_level = step["level"]
                support = supported_cycle_units(model, domains, units)
                rows = [row for row in frontier_priorities(units, domains, neighbors, support,
                                                           degree=True)
                        if row["mother"] == selected_mother]
                priority = max(row["priority"] for row in rows)
                expected = min((row for row in rows if row["priority"] == priority),
                               key=lambda row: by_id[row["unit"]]["t0"])
                self.assertEqual((step["side"], step["dart"]),
                                 (expected["side"], expected["dart"]))
                self.assertEqual(step["domain"], domains[step["side"]])
                self.assertEqual(step["symbol"], min(step["domain"]))
                self.assert_boundary(model, domains, step["side"], step["boundary"])
                anchors[step["dart"]] = [step["symbol"]]
            self.assertEqual(result["anchors_by_dart"], anchors)
            final = result["propagation_phases"][-1]
            self.assertEqual(final["anchors_by_dart"], anchors)
            self.assertEqual(final["outcome"], propagate_frontier_relations(model, anchors))

    def test_old_color_metadata_cannot_affect_a_geometry_only_restart(self):
        """Old decisions, claimed levels and inherited bans are untrusted extras."""
        clean = self.geometry["grid"]
        poisoned = deepcopy(clean)
        poisoned.update({"colors": [99], "old_colors": {0: 99}, "levels": {"frame": -9},
                         "anchors_by_dart": {0: [99]}, "names": [[99, 99]],
                         "inherited_forbidden": [1, 2, 3, 4]})
        before = deepcopy(poisoned)
        result = restart_level_side_names(poisoned)
        self.assertEqual(result, restart_level_side_names(clean))
        self.assertEqual(poisoned, before)
        self.assert_legal_result(clean, result)

    def test_geometric_equivalence_and_repeated_calls_preserve_results(self):
        """Input order, stroke direction, and degree-two breaks add no genealogy."""
        for baseline, variants in (("grid", ("grid-reordered", "grid-reversed")),
                                   ("horizontal", ("degree-two",))):
            result = restart_level_side_names(self.geometry[baseline])
            self.assertEqual(result, restart_level_side_names(self.geometry[baseline]))
            expected = side_profile(self.models[baseline], result["domains"])
            for key in variants:
                alternate = restart_level_side_names(self.geometry[key])
                self.assert_legal_result(self.geometry[key], alternate)
                self.assertEqual(side_profile(self.models[key], alternate["domains"]), expected)
                self.assertEqual(level_metadata(self.models[key]),
                                 level_metadata(self.models[baseline]))

    def test_independent_certificate_checker_accepts_a_genuine_grid_run(self):
        """The checker replays set proofs rather than trusting final color claims."""
        geometry = self.geometry["grid"]
        result = restart_level_side_names(geometry)
        before = deepcopy(result)
        checked = verify_run(geometry, result)
        self.assertTrue(checked["passed"])
        self.assertEqual(checked["claim"], "complete-proper-four-names")
        self.assertTrue(checked["final_legality"]["passed"])
        self.assertGreater(checked["filter_phases"], 0)
        self.assertEqual(result, before)

    def test_independent_certificate_checker_rejects_a_changed_chosen_name(self):
        """An unchanged final coloring cannot conceal an altered earlier choice."""
        geometry = self.geometry["grid"]
        result = restart_level_side_names(geometry)
        forged = deepcopy(result)
        decision = forged["trace"][0]
        alternate = max(decision["domain"])
        self.assertNotEqual(alternate, decision["symbol"])
        decision["symbol"] = alternate
        with self.assertRaises(AssertionError):
            verify_run(geometry, forged)

    def test_independent_certificate_checker_rejects_a_missing_boundary_interval(self):
        """The purported local evidence must cover every actual boundary interval."""
        geometry = self.geometry["grid"]
        forged = deepcopy(restart_level_side_names(geometry))
        sources = forged["trace"][0]["boundary"]["sources"]
        self.assertGreater(len(sources), 1)
        sources.pop()
        with self.assertRaises(AssertionError):
            verify_run(geometry, forged)

    def test_independent_certificate_checker_rejects_forged_levels_or_parents(self):
        """Neither displayed geometry ancestry nor per-choice ancestry is trusted."""
        geometry = self.geometry["grid"]
        genuine = restart_level_side_names(geometry)
        selected = genuine["trace"][0]["mother"]
        for target, field in (("levels", "level"), ("levels", "parents"),
                              ("trace", "level"), ("trace", "parents")):
            with self.subTest(target=target, field=field):
                forged = deepcopy(genuine)
                record = forged["levels"][selected] if target == "levels" else forged["trace"][0]
                record[field] = record[field] + 1 if field == "level" else [[], []]
                with self.assertRaises(AssertionError):
                    verify_run(geometry, forged)


if __name__ == "__main__":
    unittest.main()

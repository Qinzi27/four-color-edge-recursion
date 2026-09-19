"""Primal cycle-support certificates and constraint-first integration checks.

Small graph enumeration validates the structural Tarjan helper only. It does
not enumerate colorings and does not establish completeness of a naming rule.
"""

from itertools import combinations, permutations, product
import json
from pathlib import Path
import subprocess
from unittest.mock import patch
import unittest

from fourcolor.closed_support import _cyclic_blocks, _support_edge_ids, supported_cycle_units
from fourcolor.global_restart import POLICIES, current_priorities, current_segments, restart_line_names
from fourcolor.whole_lines import build_whole_lines, propagate_candidates
from scripts.validate_weighted_lines import independent_check


ROOT = Path(__file__).resolve().parents[1]


def common_block_pairs(blocks):
    """Compare distinct vertex pairs, never confusing one shared articulation."""
    return {frozenset(pair) for block in blocks for pair in combinations(block["vertices"], 2)}


class ClosedSupportTests(unittest.TestCase):
    """Established primal cycles affect a tie, not the admissible color domains."""

    @classmethod
    def setUpClass(cls):
        """Batch-export actual geometry; generated examples use exact cut prefixes."""
        program = r'''
import {exportRestartGeometry} from './scripts/restart-geometry.mjs';
import {generatedPaths} from './scripts/construction-experiments.mjs';
const docs={
 chord:[[[0,300],[900,300]]],
 grid:[[[300,0],[300,600]],[[600,0],[600,600]],[[0,200],[900,200]],[[0,400],[900,400]]],
 bridge:[[[0,300],[350,300]]],
 island:[[[300,200],[600,200]],[[600,200],[600,400]],[[600,400],[300,400]],[[300,400],[300,200]]],
 'seed908-seven':generatedPaths('guillotine',20260908).slice(0,7),
 'seed943-four':generatedPaths('guillotine',20260943).slice(0,4),
};
console.log(JSON.stringify(Object.entries(docs).map(([key,cuts])=>exportRestartGeometry({
 key,includeFacePoints:true,document:{frame:{width:900,height:600},strokes:cuts.map(p=>({a:p[0],b:p[1]}))}
}))));
'''
        rows = json.loads(subprocess.check_output(["node", "--input-type=module", "-e", program],
                                                 cwd=ROOT, text=True, encoding="utf-8"))
        if any(row["status"] != "geometry_ok" for row in rows):
            raise AssertionError("a cycle-support geometry fixture failed to export")
        cls.geometry = {row["key"]: row["geometry"] for row in rows}
        cls.models = {key: build_whole_lines(value) for key, value in cls.geometry.items()}

    def test_a_bridge_does_not_join_a_cycle_to_its_remote_endpoint(self):
        """Connected support is weaker than two endpoints on a common cycle."""
        edges = (("a", "b"), ("b", "c"), ("c", "a"), ("c", "d"))
        blocks = _cyclic_blocks("abcd", edges, range(len(edges)))
        self.assertEqual([block["edge_ids"] for block in blocks], [frozenset((0, 1, 2))])
        self.assertNotIn(frozenset(("a", "d")), common_block_pairs(blocks))

    def test_figure_eight_cycles_remain_two_point_biconnected_blocks(self):
        """Deleting bridges would wrongly merge these two articulation-linked loops."""
        edges = (("a", "x"), ("x", "b"), ("b", "a"),
                 ("x", "c"), ("c", "d"), ("d", "x"))
        blocks = _cyclic_blocks("xabcd", edges, range(len(edges)))
        self.assertEqual({block["edge_ids"] for block in blocks},
                         {frozenset((0, 1, 2)), frozenset((3, 4, 5))})
        pairs = common_block_pairs(blocks)
        self.assertIn(frozenset(("a", "x")), pairs)
        self.assertNotIn(frozenset(("a", "c")), pairs)

    def test_parallel_edges_are_a_two_edge_cycle_but_a_loop_has_one_vertex(self):
        """The actual parent edge ID, not its parent vertex, must be skipped."""
        edges = (("a", "b"), ("a", "b"), ("b", "c"), ("c", "c"))
        blocks = _cyclic_blocks("abc", edges, range(len(edges)))
        self.assertIn(frozenset((0, 1)), {block["edge_ids"] for block in blocks})
        self.assertEqual(common_block_pairs(blocks), {frozenset(("a", "b"))})
        without_parallel = _cyclic_blocks("abc", edges, (0, 2, 3))
        self.assertEqual(common_block_pairs(without_parallel), set())

    def test_deep_support_graph_does_not_depend_on_python_recursion_limit(self):
        """A long bridge chain followed by a triangle has exactly one cyclic block."""
        vertices = [str(index) for index in range(1603)]
        edges = [(str(index), str(index + 1)) for index in range(1602)]
        edges.append(("1602", "1600"))
        blocks = _cyclic_blocks(vertices, edges, range(len(edges)))
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["vertices"], frozenset(("1600", "1601", "1602")))

    def test_all_simple_graphs_up_to_four_vertices_match_a_cycle_oracle(self):
        """Independent tiny simple-cycle enumeration checks co-block membership."""
        checked = 0
        for size in range(1, 5):
            vertices = [str(index) for index in range(size)]
            possible = list(combinations(vertices, 2))
            for flags in product((False, True), repeat=len(possible)):
                edges = [edge for edge, present in zip(possible, flags) if present]
                available = {frozenset(edge) for edge in edges}
                expected = set()
                for length in range(3, size + 1):
                    for selected in combinations(vertices, length):
                        for tail in permutations(selected[1:]):
                            cycle = (selected[0], *tail)
                            if all(frozenset((a, b)) in available
                                   for a, b in zip(cycle, cycle[1:] + cycle[:1])):
                                expected.update(frozenset(pair) for pair in combinations(cycle, 2))
                actual = common_block_pairs(_cyclic_blocks(vertices, edges, range(len(edges))))
                self.assertEqual(actual, expected)
                checked += 1
        self.assertEqual(checked, 75)

    def test_frame_is_root_support_but_frame_units_are_never_preferred(self):
        """A chord's two ends lie on the established frame without using the chord."""
        model = self.models["chord"]
        domains = [[1] if side == self.geometry["chord"]["outerFace"] else [2, 3, 4]
                   for side in range(len(model.plane_map.faces))]
        units = current_segments(model)
        result = supported_cycle_units(model, domains, units)
        for unit in units:
            certificate = result[unit["id"]]
            if unit["mother"] == "frame":
                self.assertFalse(certificate["supported"])
            else:
                self.assertTrue(certificate["supported"])
                self.assertTrue(all(isinstance(vertex, str) for vertex in certificate["endpoint_vertices"]))
                self.assertEqual(set(certificate["block_edge_ids"]),
                                 {span["edge"] for mother in model.lines if mother["id"] == "frame"
                                  for span in mother["spans"]})
                self.assertFalse(set(certificate["block_edge_ids"]) & set(unit["edges"]))

    def test_only_both_named_real_shores_supply_nonframe_support(self):
        """Unknown internal edges and artificial island connectors are excluded."""
        model = self.models["island"]
        unknown = [[1, 2, 3, 4] for _ in model.plane_map.faces]
        root = {span["edge"] for mother in model.lines if mother["id"] == "frame"
                for span in mother["spans"]}
        self.assertEqual(_support_edge_ids(model, unknown), root)
        known = [[1] for _ in model.plane_map.faces]
        support = _support_edge_ids(model, known)
        self.assertEqual(support, set(range(len(model.plane_map.edges))) - set(model.virtual_edges))
        self.assertFalse(set(model.virtual_edges) & support)

    def test_newly_named_multimother_network_can_support_an_internal_interval(self):
        """A support loop can use several mothers, unlike the old same-mother flag."""
        geometry, model = self.geometry["grid"], self.models["grid"]
        units = current_segments(model)
        selected = next(unit for unit in units if unit["mother"] == "L:300,0>300,600"
                        and abs(unit["t0"] - 1 / 3) < 1e-9 and abs(unit["t1"] - 2 / 3) < 1e-9)
        unknown = [[1] if side == geometry["outerFace"] else [2, 3, 4]
                   for side in range(len(model.plane_map.faces))]
        self.assertFalse(supported_cycle_units(model, unknown, units)[selected["id"]]["supported"])
        established = []
        for side, points in enumerate(geometry["face_points"]):
            if side == geometry["outerFace"]:
                established.append([1])
                continue
            x0, y0 = min(p[0] for p in points), min(p[1] for p in points)
            established.append([1, 2, 4] if (x0, y0) == (300, 200)
                               else [2 + (int(x0 / 300) + int(y0 / 200)) % 2])
        certificate = supported_cycle_units(model, established, units)[selected["id"]]
        self.assertTrue(certificate["supported"])
        self.assertFalse(selected["same_single_mother"])
        self.assertGreater(len({model.edge_owner[edge] for edge in certificate["block_edge_ids"]}), 1)

    def test_a_bridge_and_fully_named_units_are_not_preferred(self):
        """A free end does not lie on the frame cycle; no decision remains when named."""
        model = self.models["bridge"]
        units = current_segments(model)
        unknown = [[1] if side == self.geometry["bridge"]["outerFace"] else [2, 3, 4]
                   for side in range(len(model.plane_map.faces))]
        self.assertTrue(all(not row["supported"] for row in supported_cycle_units(model, unknown, units).values()))
        known = [[1] if side == self.geometry["bridge"]["outerFace"] else [2]
                 for side in range(len(model.plane_map.faces))]
        self.assertTrue(all(not row["supported"] for row in supported_cycle_units(model, known, units).values()))

    def test_defensive_support_filter_removes_the_targets_own_edges(self):
        """Fault-injected support membership cannot let a target certify itself."""
        model = self.models["chord"]
        units = current_segments(model)
        domains = [[1] if side == self.geometry["chord"]["outerFace"] else [2, 3, 4]
                   for side in range(len(model.plane_map.faces))]
        with patch("fourcolor.closed_support._support_edge_ids",
                   return_value=frozenset(range(len(model.plane_map.edges)))):
            with patch("fourcolor.closed_support._cyclic_blocks", wraps=_cyclic_blocks) as decomposition:
                result = supported_cycle_units(model, domains, units)
        self.assertEqual(decomposition.call_count, 2)
        for unit in units:
            if result[unit["id"]]["supported"]:
                self.assertFalse(set(unit["edges"]) & set(result[unit["id"]]["block_edge_ids"]))

    def test_ordinary_unresolved_units_share_one_tarjan_decomposition(self):
        """Do not redo a full graph traversal separately for every current interval."""
        model = self.models["grid"]
        domains = [[1] if side == self.geometry["grid"]["outerFace"] else [2, 3, 4]
                   for side in range(len(model.plane_map.faces))]
        units = current_segments(model)
        with patch("fourcolor.closed_support._cyclic_blocks", wraps=_cyclic_blocks) as decomposition:
            result = supported_cycle_units(model, domains, units)
        self.assertEqual(decomposition.call_count, 1)
        self.assertEqual(len(result), len(units))

    def test_bad_domain_shape_and_invalid_graph_edges_are_rejected(self):
        """Invalid state data must not become a misleading support certificate."""
        model = self.models["chord"]
        units = current_segments(model)
        with self.assertRaises(ValueError):
            supported_cycle_units(model, [], units)
        for bad in ([], [1, 1], [5], [True]):
            domains = [[1, 2] for _ in model.plane_map.faces]
            domains[0] = bad
            with self.assertRaises(ValueError):
                supported_cycle_units(model, domains, units)
        with self.assertRaises(ValueError):
            _cyclic_blocks("ab", (("a", "b"),), [True])

    def test_cycle_support_only_breaks_ties_after_current_constraint_weight(self):
        """This priority-only fixture cannot be mistaken for another coloring map."""
        units = [{"id": name, "mother": name, "same_single_mother": False,
                  "occurrences": [(side, 2 * side)]}
                 for side, name in enumerate(("more-bans", "supported-fewer", "supported-tie"))]
        domains = [[1, 2], [1, 2, 3], [1, 2]]
        support = {unit["id"]: {"supported": unit["id"] != "more-bans",
                                "block_edge_ids": [], "endpoint_vertices": ["a", "b"]}
                   for unit in units}
        rows = {row["unit"]: row for row in current_priorities(units, domains, cycle_support=support)}
        self.assertGreater(rows["more-bans"]["priority"], rows["supported-fewer"]["priority"])
        self.assertGreater(rows["supported-tie"]["priority"], rows["more-bans"]["priority"])

    def test_declared_seed_examples_run_all_policies_and_closed_support_never_overrides_bans(self):
        """Independently check decisions and terminal results, keeping conflicts visible."""
        for key in ("seed908-seven", "seed943-four"):
            geometry, model = self.geometry[key], self.models[key]
            for policy in POLICIES:
                result = restart_line_names(geometry, policy)
                self.assertIn(result["status"], ("solved", "conflict"))
                self.assertTrue(independent_check(geometry, result))
                if policy != "closed-support":
                    continue
                self.assertEqual(result["status"], "solved")
                anchors = dict(result["initial_anchors_by_dart"])
                for step in result["trace"]:
                    domains = propagate_candidates(model, anchors)["domains"]
                    weights = [sum(4 - len(domains[side]) for side in
                                   {side for side, _ in unit["occurrences"] if len(domains[side]) > 1})
                               for unit in result["units"]
                               if any(len(domains[side]) > 1 for side, _ in unit["occurrences"])]
                    self.assertEqual(step["constraint_weight"], max(weights))
                    self.assertEqual(step["priority"][0], max(weights))
                    anchors[step["dart"]] = [step["symbol"]]


if __name__ == "__main__":
    unittest.main()

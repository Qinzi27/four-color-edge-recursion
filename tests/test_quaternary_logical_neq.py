"""Raw-only inequality discovery and finite certificate calibration fixtures."""

from copy import deepcopy
from functools import lru_cache
from itertools import combinations, product
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from fourcolor.structural_name_relations import refute_same_name
from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.quaternary_logical_neq import VERSION, learn_logical_inequalities
from scripts.validate_global_restart import export_geometries
from scripts.validate_structural_restart import audit_refutation


ROOT = Path(__file__).resolve().parents[1]


def document(sides, edges=(), **extra):
    """Make a literal raw fixture; face IDs are labels, not color names."""
    return {"sides": list(sides), "lines": [
        {"id": str(i), "left": a, "right": b, "kind": "separator"}
        for i, (a, b) in enumerate(edges)], **extra}


def six_side_fixture():
    """K4 plus its duplicated apex and a leaf gives nonphysical X != E."""
    core = ["A", "B", "C", "D"]
    return document(core + ["X", "E"], list(combinations(core, 2))
                    + [("X", side) for side in core[1:]] + [("A", "E")])


@lru_cache(maxsize=1)
def known_geometry():
    """Export the old 19-face development calibration, never a fresh holdout."""
    drawing = json.loads((ROOT / "examples/structural-v2-failure-map-2026-09-21.json")
                         .read_text(encoding="utf-8"))
    row = export_geometries([{"key": "known-calibration", "document": drawing}])[0]
    if row["status"] != "geometry_ok" or row["coloring_performed"]:
        raise AssertionError("old geometry calibration did not export without coloring")
    return row["geometry"]


class LogicalInequalityLearningTests(unittest.TestCase):
    """Every nonedge query is saved, but only actual refutations become NEQ."""

    def test_every_raw_nonedge_is_queried_once_in_input_side_order(self):
        raw = document(["z", "a", "m", "b"], [("z", "m")], anchors={"z": 4})
        with patch("scripts.quaternary_logical_neq.refute_same_name", wraps=refute_same_name) as spy:
            result = learn_logical_inequalities(raw)
        wanted = [(i, j) for i, j in combinations(range(4), 2) if (i, j) != (0, 2)]
        self.assertEqual([call.args for call in spy.call_args_list],
                         [(4, [(0, 2)], i, j) for i, j in wanted])
        self.assertEqual([row["pair"] for row in result["queries"]],
                         [[raw["sides"][i], raw["sides"][j]] for i, j in wanted])
        self.assertEqual(result["different_names"], [])
        self.assertEqual(result["stats"]["inconclusive"], 5)
        self.assertTrue(all(row["result"]["status"] == "inconclusive" for row in result["queries"]))

    def test_known_nonphysical_inequality_has_raw_certificate_and_legal_witnesses(self):
        raw = six_side_fixture()
        found = learn_logical_inequalities(raw)
        self.assertEqual(found["version"], VERSION)
        self.assertIn(["X", "E"], found["different_names"])
        edges = [(raw["sides"].index(line["left"]), raw["sides"].index(line["right"]))
                 for line in raw["lines"]]
        self.assertNotIn((4, 5), edges)
        for query in found["queries"]:
            first, second = map(raw["sides"].index, query["pair"])
            self.assertTrue(audit_refutation(6, edges, first, second, query["result"])["passed"])
        proper = [colors for colors in product((1, 2, 3, 4), repeat=6)
                  if all(colors[a] != colors[b] for a, b in edges)]
        self.assertEqual(len(proper), 72)
        for pair in found["different_names"]:
            a, b = map(raw["sides"].index, pair)
            self.assertTrue(all(colors[a] != colors[b] for colors in proper))

    def test_anchors_bind_hash_but_do_not_change_queries_or_learning(self):
        raw = six_side_fixture()
        first = learn_logical_inequalities(raw)
        second = learn_logical_inequalities({**raw, "anchors": {"A": 2, "E": 2}})
        # Even contradictory anchors must not make an otherwise unproved
        # relation appear proved; discovery has no color premises at all.
        self.assertNotEqual(first["raw_document_sha256"], second["raw_document_sha256"])
        self.assertEqual(first["queries"], second["queries"])
        self.assertEqual(first["different_names"], second["different_names"])
        self.assertEqual(first["stats"], second["stats"])

    def test_parallel_lines_bridge_and_point_contacts_do_not_invent_raw_edges(self):
        raw = document(["A", "B", "C"], [("A", "B"), ("B", "A")],
                       point_contacts=[{"sides": ["B", "C"]}])
        raw["lines"].append({"id": "bridge", "left": "C", "right": "C", "kind": "bridge"})
        result = learn_logical_inequalities(raw)
        self.assertEqual(result["stats"], {"side_count": 3, "neq_edge_count": 1,
                         "separator_line_count": 2, "bridge_line_count": 1, "point_contact_count": 1,
                         "eligible_pairs": 2, "proved_different": 0, "inconclusive": 2})
        self.assertEqual([q["pair"] for q in result["queries"]], [["A", "C"], ["B", "C"]])

    def test_input_unchanged_and_queries_do_not_alias_output_pairs(self):
        raw = six_side_fixture()
        original = deepcopy(raw)
        found = learn_logical_inequalities(raw)
        pair = found["different_names"][0]
        old_pair = list(pair)
        pair[0] = "changed"
        self.assertTrue(any(query["pair"] == old_pair for query in found["queries"]))
        self.assertEqual(raw, original)

    def test_raw_scope_rejects_external_states_eq_and_logical_neq(self):
        for extra in ({"states": {"A": "0111"}}, {"equal_names": [["A", "B"]]},
                      {"different_names": []}, {"different_names": [["A", "B"]]}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                learn_logical_inequalities(document(["A", "B"], **extra))

    def test_single_side_and_complete_graph_have_no_eligible_queries(self):
        for raw in (document(["A"]), document(["A", "B"], [("A", "B")])):
            with patch("scripts.quaternary_logical_neq.refute_same_name", side_effect=AssertionError("query")):
                found = learn_logical_inequalities(raw)
            self.assertEqual(found["queries"], [])
            self.assertEqual(found["stats"]["eligible_pairs"], 0)

    def test_known_19_face_calibration_learns_s1_neq_s10_from_original_edges(self):
        raw = adapt_exported_geometry(known_geometry(), anchors={"S1": 1})["contact_document"]
        found = learn_logical_inequalities(raw)
        self.assertIn(["S1", "S10"], found["different_names"])
        query = next(q for q in found["queries"] if q["pair"] == ["S1", "S10"])
        self.assertEqual(query["result"]["status"], "proved_different")
        self.assertEqual(query["result"]["contradiction"]["kind"], "five_clique")
        self.assertEqual(found["stats"]["eligible_pairs"], 120)
        edges = sorted({tuple(sorted((raw["sides"].index(l["left"]), raw["sides"].index(l["right"]))))
                        for l in raw["lines"] if l["kind"] == "separator"})
        self.assertNotIn((1, 10), edges)
        self.assertTrue(audit_refutation(19, edges, 1, 10, query["result"])["passed"])


if __name__ == "__main__":
    unittest.main()

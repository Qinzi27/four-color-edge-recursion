"""Independent fixtures for structural/domain matching and persistent-state scope."""

from copy import deepcopy
from itertools import combinations, permutations
import unittest

from scripts.scan_low_color_obstruction_states import (
    classify_domains, persistent_phases, raw_graph, scan_run, triangle_bipyramids,
)


def bipyramid_edges():
    """Use apices 0/4 with a 1/2/3 triangle rim."""
    return [edge for edge in combinations(range(5), 2) if edge != (0, 4)]


def sample_result():
    """Make a literal archived-style wrong commitment with no producer import."""
    sides = [f"S{i}" for i in range(5)]
    domains = [[1, 2], [1, 2, 3, 4], [1, 2, 3, 4], [1, 2, 3, 4], [2, 3, 4]]
    before = {"status": "underdetermined", "domains": domains, "side_order": sides}
    after = deepcopy(before)
    after["domains"][0] = [1]
    event = {"side": "S0", "symbol": 1, "kind": "commit", "before_phase": 0,
             "trial_phase": 1, "after_phase": 1, "extension_claim": "inconclusive"}
    return {"probe": True, "original_input": {"sides": sides},
            "phases": [{"kind": "main", "outcome": before}, {"kind": "trial", "outcome": after}],
            "events": [event], "final_phase": 1}


class StructureTests(unittest.TestCase):
    """Detect induced structures from raw adjacency and ignore nonedges correctly."""

    def test_exact_bipyramid(self):
        self.assertEqual(triangle_bipyramids(5, bipyramid_edges()), [{"apices": [0, 4], "rim": [1, 2, 3]}])

    def test_apex_edge_or_missing_rim_edge_prevents_match(self):
        self.assertEqual(triangle_bipyramids(5, list(combinations(range(5), 2))), [])
        self.assertEqual(triangle_bipyramids(5, [e for e in bipyramid_edges() if e != (1, 2)]), [])

    def test_outside_vertices_do_not_destroy_induced_structure(self):
        edges = bipyramid_edges() + [(0, 5), (1, 5)]
        self.assertEqual(triangle_bipyramids(6, edges), [{"apices": [0, 4], "rim": [1, 2, 3]}])

    def test_raw_edges_ignore_virtual_and_bridge_but_deduplicate_contact(self):
        geometry = {"faces": [[], [], []], "edges": [{}, {}, {"virtual": True}, {}],
                    "faceOfDart": [0, 1, 2, 2, 0, 2, 1, 0]}
        sides, edges, lines = raw_graph(geometry)
        self.assertEqual(sides, ["S0", "S1", "S2"])
        self.assertEqual(edges, [(0, 1)])
        self.assertEqual([line["id"] for line in lines], ["E0", "E1", "E3"])
        self.assertEqual(lines[1]["kind"], "bridge")


class DomainTests(unittest.TestCase):
    """Check color permutation matching while preserving numeric low-name order."""

    def test_known_external_pattern(self):
        found = classify_domains([1, 2], [2, 3, 4])
        self.assertTrue(found["strict_apex_signature"])
        self.assertTrue(found["proper_both"])
        self.assertTrue(found["lowest_excluded_by_other"])
        self.assertEqual(found["intersection"], [2])

    def test_all_color_permutations_use_actual_numeric_order(self):
        for p in permutations([1, 2, 3, 4]):
            found = classify_domains([p[0], p[1]], [p[1], p[2], p[3]])
            self.assertEqual(found["strict_apex_signature"], p[0] < p[1])

    def test_empty_equal_subset_and_reverse_are_not_strict(self):
        for first, second in [([], [1]), ([1, 2], [1, 2]), ([1, 2], [1, 2, 3]), ([2, 3, 4], [1, 2])]:
            self.assertFalse(classify_domains(first, second)["strict_apex_signature"])
        self.assertFalse(classify_domains([1], [1, 2])["proper_both"])

    def test_broad_overlap_without_strict_shape(self):
        found = classify_domains([1, 2, 3], [2, 3, 4])
        self.assertTrue(found["proper_both"])
        self.assertTrue(found["lowest_excluded_by_other"])
        self.assertFalse(found["strict_apex_signature"])


class PersistentTests(unittest.TestCase):
    """A surviving probe counts only after commit; rejected probes never count."""

    def test_accepted_trial_is_persistent(self):
        self.assertEqual(persistent_phases(sample_result()), [(0, 0), (1, None)])

    def test_rejected_trial_excluded_and_post_rejection_main_included(self):
        result = sample_result()
        result["phases"][1]["outcome"]["status"] = "conflict"
        result["phases"].append({"kind": "main", "outcome": deepcopy(result["phases"][0]["outcome"])})
        result["events"][0].update(kind="reject", after_phase=2, extension_claim="refuted")
        result["final_phase"] = 2
        self.assertEqual(persistent_phases(result), [(0, 0), (2, None)])

    def test_disconnected_or_unreferenced_phases_rejected(self):
        result = sample_result()
        result["events"][0]["before_phase"] = 1
        with self.assertRaises(ValueError):
            persistent_phases(result)
        result = sample_result()
        result["phases"].append(deepcopy(result["phases"][0]))
        with self.assertRaises(ValueError):
            persistent_phases(result)

    def test_risk_and_histogram_cover_both_persistent_states(self):
        motifs = triangle_bipyramids(5, bipyramid_edges())
        found = scan_run(sample_result(), motifs, {"key": "fixture"})
        self.assertEqual(found["counts"]["persistent_phases"], 2)
        self.assertEqual(found["counts"]["strict_apex_matches"], 1)
        self.assertEqual(found["counts"]["strict_full_rim_matches"], 1)
        self.assertEqual(found["counts"]["inconclusive_bad_commits"], 1)
        self.assertEqual(found["matches"]["inconclusive_commit"][0]["next_event"], 0)
        hist = found["motif_statistics"][0]["domain_intersection_histogram"]
        self.assertEqual(sum(item["phases"] for item in hist), 2)

    def test_zero_detail_limit_never_changes_total_counts(self):
        motifs = triangle_bipyramids(5, bipyramid_edges())
        found = scan_run(sample_result(), motifs, {}, detail_limit=0)
        self.assertEqual(found["counts"]["inconclusive_bad_commits"], 1)
        self.assertTrue(all(not rows for rows in found["matches"].values()))

    def test_other_selected_side_is_not_apex_risk(self):
        result = sample_result()
        result["events"][0]["side"] = "S1"
        found = scan_run(result, triangle_bipyramids(5, bipyramid_edges()), {})
        self.assertEqual(found["counts"]["strict_apex_matches"], 1)
        self.assertEqual(found["counts"]["selected_bad_minimum_attempts"], 0)


if __name__ == "__main__":
    unittest.main()

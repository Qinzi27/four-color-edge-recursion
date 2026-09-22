"""Independent checks on actual Node-exported drawings, including corrupted evidence."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts.audit_quaternary_geometry import audit_run
from scripts.quaternary_contact_model import propagate_contacts
from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.validate_global_restart import export_geometries


def box(x0, y0, x1, y1):
    """Four real input strokes form a bounded component, not a graph-only mock."""
    points = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    return [{"a": points[i], "b": points[(i + 1) % 4]} for i in range(4)]


class QuaternaryGeometryAuditTests(unittest.TestCase):
    """Expected elementary topology is specified independently of the adapter."""

    @classmethod
    def setUpClass(cls):
        """Export all literal drawings together; no naming policy creates fixtures."""
        strokes = {
            "empty": [],
            "pendant": [{"a": [0, 300], "b": [900, 300]}, {"a": [450, 300], "b": [450, 150]}],
            "floating": [{"a": [100, 100], "b": [300, 100]}],
            "cross": [{"a": [0, 300], "b": [900, 300]}, {"a": [450, 0], "b": [450, 600]}],
            "islands": box(150, 150, 300, 300) + box(600, 150, 750, 300),
            "nested": box(200, 100, 700, 500) + box(350, 220, 550, 380),
            "tangent": box(150, 150, 350, 350) + box(350, 350, 550, 550),
            "oblique": [{"a": [0, 0], "b": [900, 600]}, {"a": [0, 600], "b": [900, 0]}],
            "overlap": [{"a": [0, 300], "b": [900, 300]}, {"a": [700, 300], "b": [200, 300]},
                        {"a": [900, 300], "b": [0, 300]}],
        }
        cls.drawings = {key: {"frame": {"width": 900, "height": 600}, "strokes": value}
                        for key, value in strokes.items()}
        cls.geometries = {}
        for row in export_geometries([{"key": k, "document": d} for k, d in cls.drawings.items()]):
            if row["status"] != "geometry_ok" or row["coloring_performed"]:
                raise AssertionError(row)
            cls.geometries[row["key"]] = row["geometry"]

    def fixture(self, key="empty", *, anchors=None, states=None):
        """Fresh copies make corruption tests independent and preserve source inputs."""
        geometry = deepcopy(self.geometries[key])
        adapted = adapt_exported_geometry(geometry, anchors=anchors, states=states, drawing=self.drawings[key])
        return geometry, adapted, propagate_contacts(adapted["contact_document"])

    def test_actual_drawings_pass_independent_topology_and_contact_checks(self):
        expected_faces = {"empty": 2, "pendant": 3, "floating": 2, "cross": 5,
                          "islands": 4, "nested": 4, "tangent": 4, "oblique": 5, "overlap": 3}
        for key, faces in expected_faces.items():
            with self.subTest(drawing=key):
                result = audit_run(*self.fixture(key))
                self.assertTrue(result["passed"])
                self.assertEqual(result["geometry"]["faces"], faces)
                self.assertTrue(result["geometry"]["coordinate_rotation_outer_and_crossings_checked"])
                self.assertTrue(result["geometry"]["source_coverage_checked"])
                self.assertEqual(result["oracle"]["status"], "sat")
                self.assertTrue(result["oracle_verification"]["passed"])
                self.assertTrue(result["oracle_witness_satisfies_all_input_domains"])

    def test_bridge_and_island_geometry_has_no_spurious_neq(self):
        for key in ("floating", "pendant"):
            geometry, adapted, outcome = self.fixture(key)
            bridges = [line for line in adapted["contact_document"]["lines"] if line["kind"] == "bridge"]
            self.assertTrue(bridges)
            self.assertTrue(all(line["left"] == line["right"] != adapted["outer_side_id"] for line in bridges))
            audit = audit_run(geometry, adapted, outcome)
            self.assertTrue(all(a != b for a, b in audit["oracle_input"]["edges"]))
        result = audit_run(*self.fixture("islands"))
        self.assertEqual(result["geometry"]["real_components"], 3)
        self.assertEqual(result["geometry"]["real_boundary_walks"], 6)
        self.assertEqual(result["geometry"]["point_only_pairs"], 0)

    def test_point_contact_can_have_equal_explicit_names(self):
        geometry, adapted, _ = self.fixture("tangent")
        self.assertEqual(len(adapted["contact_document"]["point_contacts"]), 1)
        pair = adapted["contact_document"]["point_contacts"][0]["sides"]
        anchored = adapt_exported_geometry(geometry, anchors={s: 1 for s in pair}, drawing=self.drawings["tangent"])
        outcome = propagate_contacts(anchored["contact_document"])
        result = audit_run(geometry, anchored, outcome)
        self.assertEqual(result["oracle"]["status"], "sat")
        self.assertNotEqual(outcome["status"], "conflict")
        self.assertEqual(result["geometry"]["point_only_pairs"], 1)

    def test_threshold_uses_original_domains_and_is_inclusive(self):
        fixture = self.fixture()
        full = audit_run(*fixture, assignment_limit=16)
        self.assertEqual(full["assignment_product"], 16)
        self.assertEqual(full["full_enumeration"]["status"], "run")
        self.assertEqual(full["full_enumeration"]["literal_assignments_checked"], 16)
        self.assertEqual(full["full_enumeration"]["legal_assignments"], 12)
        with patch("scripts.audit_quaternary_geometry.audit_document", side_effect=AssertionError("must not enumerate")):
            bounded = audit_run(*fixture, assignment_limit=15)
        self.assertEqual(bounded["full_enumeration"]["status"], "not_run")
        self.assertIsNone(bounded["full_enumeration"]["legal_assignments"])
        # One explicit name reduces the INPUT product to four, not the final
        # three compatible names on the adjacent region after propagation.
        anchored = audit_run(*self.fixture(anchors={"S0": 1}), assignment_limit=4)
        self.assertEqual(anchored["assignment_product"], 4)
        self.assertEqual(anchored["full_enumeration"]["legal_assignments"], 3)

    def test_oracle_budget_exhaustion_is_unknown_even_when_enumeration_runs(self):
        result = audit_run(*self.fixture(), node_limit=0)
        self.assertEqual(result["oracle"]["status"], "unknown")
        self.assertIsNone(result["oracle"]["witness"])
        self.assertFalse(result["oracle_verification"]["conclusive"])
        self.assertEqual(result["full_enumeration"]["legal_assignments"], 12)

    def test_anchored_true_separator_conflict_gets_offline_unsat_certificate(self):
        result = audit_run(*self.fixture(anchors={"S0": 1, "S1": 1}), assignment_limit=0)
        self.assertEqual(result["bounded_metadata_trace"]["status"], "conflict")
        self.assertEqual(result["oracle"]["status"], "unsat")
        self.assertIsNotNone(result["oracle"]["certificate"])
        self.assertTrue(result["oracle_verification"]["conclusive"])

    def test_restricted_nonsingleton_input_marks_adjacency_oracle_relaxation(self):
        result = audit_run(*self.fixture(states={"S0": "0111", "S1": "0111"}), assignment_limit=0)
        self.assertEqual(result["oracle"]["status"], "sat")
        self.assertEqual(result["oracle_scope"], "relaxation_ignoring_nonsingleton_domain_restrictions")
        self.assertFalse(result["oracle_witness_satisfies_all_input_domains"])
        self.assertFalse(result["oracle_feedback_to_producer"])

    def test_empty_input_domain_does_not_turn_relaxed_sat_into_contact_sat(self):
        result = audit_run(*self.fixture(states={"S0": "0000"}), assignment_limit=0)
        self.assertEqual(result["assignment_product"], 0)
        self.assertEqual(result["full_enumeration"]["legal_assignments"], 0)
        self.assertEqual(result["oracle"]["status"], "sat")
        self.assertFalse(result["oracle_witness_satisfies_all_input_domains"])

    def test_missing_real_edge_is_rejected_even_if_producer_accepts_changed_document(self):
        geometry, adapted, _ = self.fixture()
        adapted["contact_document"]["lines"].pop()
        outcome = propagate_contacts(adapted["contact_document"])
        with self.assertRaises(AssertionError):
            audit_run(geometry, adapted, outcome)

    def test_wrong_side_or_virtual_physical_edge_is_rejected(self):
        geometry, adapted, outcome = self.fixture("floating")
        wrong_side = deepcopy(adapted)
        wrong_side["atomic_edge_provenance"][0]["left_side"] = "S999"
        with self.assertRaises(AssertionError):
            audit_run(geometry, wrong_side, outcome)
        connector = adapted["virtual_connectors"][0]
        adapted["contact_document"]["lines"].append({"id": f"E{connector['edge_id']}",
            "left": connector["left_side"], "right": connector["right_side"], "kind": "bridge"})
        with self.assertRaises(AssertionError):
            audit_run(geometry, adapted, propagate_contacts(adapted["contact_document"]))

    def test_point_contact_metadata_cannot_be_omitted_or_promoted(self):
        geometry, adapted, outcome = self.fixture("cross")
        adapted["contact_document"]["point_contacts"] = []
        with self.assertRaises(AssertionError):
            audit_run(geometry, adapted, outcome)
        geometry, adapted, outcome = self.fixture("cross")
        pair = adapted["contact_document"]["point_contacts"][0]["sides"]
        adapted["contact_document"]["lines"].append({"id": "invented", "left": pair[0], "right": pair[1], "kind": "separator"})
        with self.assertRaises(AssertionError):
            audit_run(geometry, adapted, propagate_contacts(adapted["contact_document"]))

    def test_coordinate_rotation_and_outer_identity_are_independently_checked(self):
        geometry, adapted, outcome = self.fixture("cross")
        vertex = next(i for i, row in enumerate(geometry["rotation"]) if len(row) == 4)
        geometry["rotation"][vertex].reverse()
        with self.assertRaisesRegex(AssertionError, "coordinate cyclic rotation"):
            audit_run(geometry, adapted, outcome)
        geometry, adapted, outcome = self.fixture()
        geometry["outerFace"] = 1 - geometry["outerFace"]
        with self.assertRaisesRegex(AssertionError, "outer face"):
            audit_run(geometry, adapted, outcome)

    def test_boundary_component_and_geometry_echo_tampering_are_rejected(self):
        geometry, adapted, outcome = self.fixture("islands")
        adapted["real_boundary_walks"][0]["region_id"] = "S999"
        with self.assertRaises(AssertionError):
            audit_run(geometry, adapted, outcome)
        geometry, adapted, outcome = self.fixture("nested")
        adapted["geometry"]["edges"][0]["virtual"] = True
        with self.assertRaises(AssertionError):
            audit_run(geometry, adapted, outcome)

    def test_large_path_checks_anchor_marker_and_directed_line_metadata(self):
        for mutation in ("state", "reverse", "mask", "status"):
            geometry, adapted, outcome = self.fixture(anchors={"S0": 1})
            if mutation == "state":
                outcome["name_states"]["S0"].update(quaternary="2000", code=128, anchored=False)
            elif mutation == "reverse":
                outcome["lines"][0]["reverse"]["left"] = "S999"
            elif mutation == "mask":
                outcome["relations"][0][0] += 1 << 16
            else:
                outcome["status"] = "solved"
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                audit_run(geometry, adapted, outcome, assignment_limit=0)

    def test_trace_premises_deletion_and_coverage_are_all_checked(self):
        # Two frame regions alone have a nonempty deletion trace after an
        # explicit anchor, so no abstract-only fake result is needed here.
        for mutation in ("premise", "after", "remove"):
            geometry, adapted, outcome = self.fixture(anchors={"S0": 1})
            self.assertTrue(outcome["trace"])
            if mutation == "premise":
                outcome["trace"][0]["left"] ^= 1
            elif mutation == "after":
                outcome["trace"][0]["after"] ^= 1
            else:
                outcome["trace"].pop()
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                audit_run(geometry, adapted, outcome, assignment_limit=0)


if __name__ == "__main__":
    unittest.main()

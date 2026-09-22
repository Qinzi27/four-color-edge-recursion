"""Exercise actual drawings, multiple boundary components and contact semantics."""

from copy import deepcopy
from itertools import combinations
import unittest
from unittest.mock import patch

from scripts.quaternary_contact_model import propagate_contacts
from scripts.quaternary_geometry_adapter import adapt_exported_geometry, adapt_geometry
from scripts.validate_global_restart import export_geometries


def rectangle(x0, y0, x1, y1):
    """Keep four literal drawn strokes, not a synthetic graph-only cycle."""
    points = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    return [{"a": points[i], "b": points[(i + 1) % 4]} for i in range(4)]


def drawing(strokes):
    """Use the actual engine frame and drawing input schema."""
    return {"frame": {"width": 900, "height": 600}, "strokes": strokes}


class QuaternaryGeometryAdapterTests(unittest.TestCase):
    """Geometry export is shared, while expected topology is fixed independently."""

    @classmethod
    def setUpClass(cls):
        """Batch pure Node exports once; no fixture calls a naming policy."""
        cls.drawings = {
            "empty": drawing([]),
            "horizontal": drawing([{"a": [0, 300], "b": [900, 300]}]),
            "tee": drawing([{"a": [0, 300], "b": [900, 300]},
                            {"a": [450, 300], "b": [450, 600]}]),
            "cross": drawing([{"a": [0, 300], "b": [900, 300]},
                              {"a": [450, 0], "b": [450, 600]}]),
            "islands": drawing(rectangle(100, 100, 300, 300) + rectangle(550, 100, 750, 300)),
            "nested": drawing(rectangle(100, 100, 800, 500) + rectangle(300, 200, 600, 400)),
            "dangling": drawing([{"a": [0, 300], "b": [250, 300]}]),
            "floating": drawing([{"a": [250, 250], "b": [600, 350]}]),
            "point_squares": drawing(rectangle(100, 100, 300, 300) + rectangle(300, 300, 500, 500)),
            "overlap": drawing([{"a": [0, 300], "b": [900, 300]},
                                {"a": [700, 300], "b": [200, 300]},
                                {"a": [900, 300], "b": [0, 300]}]),
            "oblique": drawing([{"a": [0, 0], "b": [900, 600]},
                                {"a": [0, 600], "b": [900, 0]}]),
        }
        exported = export_geometries([{"key": key, "document": doc} for key, doc in cls.drawings.items()])
        cls.geometries = {}
        for row in exported:
            if row["status"] != "geometry_ok" or row["coloring_performed"]:
                raise AssertionError(row)
            cls.geometries[row["key"]] = row["geometry"]
        cls.adapted = {key: adapt_exported_geometry(geometry, drawing=cls.drawings[key])
                       for key, geometry in cls.geometries.items()}

    def test_wrapper_and_batched_entry_point_agree_without_default_anchors(self):
        report = adapt_geometry(self.drawings["empty"])
        self.assertEqual(report, self.adapted["empty"])
        self.assertEqual(report["contact_document"]["anchors"], {})
        self.assertEqual(report["contact_document"]["states"], {})
        self.assertEqual(report["choices"], 0)
        self.assertEqual(report["propagation_runs"], 0)
        self.assertFalse(report["old_colors_read"])
        outcome = propagate_contacts(report["contact_document"])
        self.assertEqual(outcome["status"], "underdetermined")
        self.assertTrue(all(state["quaternary"] == "1111" for state in outcome["name_states"].values()))

    def test_real_edges_map_once_and_virtual_bridges_never_become_contacts(self):
        for key, report in self.adapted.items():
            with self.subTest(key=key):
                geometry = self.geometries[key]
                real = [i for i, edge in enumerate(geometry["edges"]) if not edge["virtual"]]
                virtual = [i for i, edge in enumerate(geometry["edges"]) if edge["virtual"]]
                contacts = {line["id"]: line for line in report["contact_document"]["lines"]}
                self.assertEqual(set(contacts), {f"E{i}" for i in real})
                self.assertEqual(len(report["atomic_edge_provenance"]), len(real))
                self.assertEqual({row["edge_id"] for row in report["virtual_connectors"]}, set(virtual))
                for i in real:
                    left, right = (f"S{geometry['faceOfDart'][2*i]}", f"S{geometry['faceOfDart'][2*i+1]}")
                    contact = contacts[f"E{i}"]
                    self.assertEqual((contact["left"], contact["right"]), (left, right))
                    self.assertEqual(contact["kind"], "bridge" if left == right else "separator")
                for row in report["virtual_connectors"]:
                    self.assertEqual(row["left_side"], row["right_side"])
                self.assertEqual(report["outer_side_id"], f"S{geometry['outerFace']}")

    def test_disconnected_islands_share_one_background_region(self):
        report = self.adapted["islands"]
        self.assertEqual(len(report["regions"]), 4)
        self.assertEqual(len(report["real_components"]), 3)
        self.assertEqual(len(report["real_boundary_walks"]), 6)
        backgrounds = [r for r in report["regions"] if len(r["real_boundary_walk_ids"]) == 3]
        self.assertEqual(len(backgrounds), 1)
        self.assertFalse(backgrounds[0]["is_outer"])
        self.assertEqual(report["contact_document"]["point_contacts"], [])
        # Giving the common background name 1 excludes it on BOTH island
        # interiors, although those interiors have no common real edge.
        anchored = adapt_exported_geometry(self.geometries["islands"], anchors={backgrounds[0]["id"]: 1})
        outcome = propagate_contacts(anchored["contact_document"])
        self.assertEqual(outcome["name_states"][backgrounds[0]["id"]]["quaternary"], "3000")
        self.assertEqual(sum(state["quaternary"] == "0111" for state in outcome["name_states"].values()), 3)

    def test_nested_boundaries_do_not_create_extra_side_variables(self):
        report = self.adapted["nested"]
        self.assertEqual(len(report["regions"]), 4)
        self.assertEqual(sorted(len(r["real_boundary_walk_ids"]) for r in report["regions"]), [1, 1, 2, 2])
        walks = report["real_boundary_walks"]
        self.assertEqual(len(walks), 6)
        self.assertEqual({w["region_id"] for w in walks}, set(report["side_order"]))
        covered = [dart for walk in walks for dart in walk["darts"]]
        self.assertEqual(len(covered), len(set(covered)))
        self.assertEqual(len(covered), 2 * len(report["atomic_edge_provenance"]))

    def test_real_dangling_and_floating_bridges_keep_the_interior_side(self):
        for key, expected_components in (("dangling", 1), ("floating", 2)):
            with self.subTest(key=key):
                report = self.adapted[key]
                self.assertEqual(len(report["regions"]), 2)
                self.assertEqual(len(report["real_components"]), expected_components)
                bridges = [row for row in report["contact_document"]["lines"] if row["kind"] == "bridge"]
                self.assertTrue(bridges)
                self.assertTrue(all(row["left"] == row["right"] != report["outer_side_id"] for row in bridges))

    def test_x_junction_opposite_regions_are_only_point_contacts(self):
        report = self.adapted["cross"]
        self.assertEqual(len(report["regions"]), 5)
        pairs = report["contact_document"]["point_contacts"]
        self.assertEqual(len(pairs), 2)
        center = next(row for row in report["vertex_contacts"] if row["point"] == [450, 300])
        self.assertEqual(len(center["incident_side_ids"]), 4)
        self.assertEqual(len(center["globally_point_only_pairs"]), 2)
        separators = {frozenset((r["left"], r["right"])) for r in report["contact_document"]["lines"]}
        for contact in pairs:
            self.assertNotIn(frozenset(contact["sides"]), separators)
            anchored = adapt_exported_geometry(self.geometries["cross"],
                                               anchors={side: 1 for side in contact["sides"]})
            self.assertNotEqual(propagate_contacts(anchored["contact_document"])["status"], "conflict")
        self.assertEqual(self.adapted["tee"]["contact_document"]["point_contacts"], [])

    def test_point_touching_islands_do_not_impose_an_inequality(self):
        report = self.adapted["point_squares"]
        self.assertEqual(len(report["regions"]), 4)
        contacts = report["point_contact_provenance"]
        self.assertEqual(len(contacts), 1)
        self.assertEqual([report["geometry"]["vertices"][v] for v in contacts[0]["vertices"]], [[300, 300]])
        anchored = adapt_exported_geometry(self.geometries["point_squares"],
                                           anchors={side: 2 for side in contacts[0]["sides"]})
        self.assertNotEqual(propagate_contacts(anchored["contact_document"])["status"], "conflict")

    def test_original_overlapping_strokes_and_mother_spans_remain_distinct_records(self):
        report = self.adapted["overlap"]
        self.assertEqual(report["drawing"], self.drawings["overlap"])
        horizontal = [row for row in report["whole_lines"] if row["id"] != "frame"]
        self.assertEqual(len(horizontal), 1)
        self.assertEqual(horizontal[0]["sources"], [0, 1, 2])
        self.assertEqual(len(horizontal[0]["spans"]), 3)
        middle = next(row for row in report["atomic_edge_provenance"]
                      if set(row["source_stroke_indices"]) == {0, 1, 2})
        self.assertEqual(middle["source_strokes"][1], {"index": 1, "a": [700, 300], "b": [200, 300]})
        for key in ("tee", "cross"):
            mothers = [row for row in self.adapted[key]["whole_lines"] if row["id"] != "frame"]
            self.assertEqual(len(mothers), 2)

    def test_orientation_follows_atomic_dart_in_screen_coordinates(self):
        report = self.adapted["horizontal"]
        atomic = next(row for row in report["atomic_edge_provenance"] if not row["frame"])
        self.assertEqual((atomic["a"], atomic["b"]), ([0, 300], [900, 300]))
        # The frame top interior dart borders the top region. For an eastward
        # horizontal stroke that same region lies on its mathematical left.
        frame_top = next(row for row in report["atomic_edge_provenance"]
                         if row["frame"] and row["a"] == [0, 0] and row["b"] == [900, 0])
        self.assertEqual(atomic["left_side"], frame_top["right_side"])
        self.assertEqual(atomic["dart"], 2 * atomic["edge_id"])
        self.assertEqual(len(self.adapted["oblique"]["regions"]), 5)

    def test_explicit_domains_are_caller_supplied_and_input_containers_are_unchanged(self):
        geometry = deepcopy(self.geometries["empty"])
        original = deepcopy(geometry)
        doc = deepcopy(self.drawings["empty"])
        doc["old_colors"] = [1, 1]
        report = adapt_exported_geometry(geometry, states={"S0": "0111"}, drawing=doc)
        self.assertEqual(geometry, original)
        self.assertEqual(report["contact_document"]["states"], {"S0": "0111"})
        self.assertEqual(report["contact_document"]["anchors"], {})
        self.assertIn("old_colors", report["ignored_drawing_fields"])
        report["geometry"]["edges"].clear()
        report["drawing"]["strokes"].append({"a": [0, 0], "b": [1, 1]})
        self.assertEqual(geometry, original)
        self.assertEqual(doc["strokes"], [])
        with patch("scripts.quaternary_contact_model.propagate_contacts", side_effect=AssertionError), \
                patch("scripts.quaternary_geometry_adapter.export_geometries", side_effect=AssertionError):
            adapt_exported_geometry(geometry)

    def test_malformed_geometry_and_false_provenance_are_rejected(self):
        bad_face = deepcopy(self.geometries["empty"])
        bad_face["faceOfDart"][0] = True
        wrong_outer = deepcopy(self.geometries["empty"])
        wrong_outer["outerFace"] = 1 - wrong_outer["outerFace"]
        virtual_separator = deepcopy(self.geometries["empty"])
        virtual_separator["edges"][0].update(virtual=True, frame=False, sources=[])
        bad_source = deepcopy(self.geometries["horizontal"])
        next(e for e in bad_source["edges"] if not e["frame"])["sources"] = [99]
        for geometry in (bad_face, wrong_outer, virtual_separator, bad_source):
            with self.subTest(geometry=geometry["original"]), self.assertRaises(ValueError):
                adapt_exported_geometry(geometry, drawing=self.drawings["horizontal"])
        mismatched = drawing([{"a": [0, 200], "b": [900, 200]}])
        with self.assertRaises(ValueError):
            adapt_exported_geometry(self.geometries["horizontal"], drawing=mismatched)
        for kwargs in ({"anchors": {"S0": True}}, {"anchors": {"missing": 1}},
                       {"states": {"S0": "0100"}}, {"states": {"missing": "1111"}}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                adapt_exported_geometry(self.geometries["empty"], **kwargs)

    def test_invalid_drawing_rejected_without_old_name_side_effects(self):
        bad = [None, {}, {"strokes": [] , "frame": {"width": True, "height": 600}},
               drawing([{"a": [True, 0], "b": [900, 0]}]),
               drawing([{"a": [0, float("nan")], "b": [900, 0]}]),
               drawing([{"a": [0, 0], "b": [0, 0]}]),
               drawing([{"a": [-1, 0], "b": [900, 0]}])]
        for document in bad:
            with self.subTest(document=document), self.assertRaises(ValueError):
                adapt_geometry(document)


if __name__ == "__main__":
    unittest.main()

"""Check declared held-out histories using coordinates and geometry only."""

from collections import Counter
from math import hypot
import unittest

from scripts.audit_quaternary_geometry import audit_geometry
from scripts.current_corpus import stroke_set_key
from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.quaternary_triangle_eq_inputs import (
    ANGLE_OFFSETS, CENTER, CHORDS, GUILLOTINE, POLYGONS, POLYGON_SIDES,
    RADII, RANDOM_FAMILIES, RING_COUNTS, SEEDS, STEPS, build_eq_holdout, polygon_paths,
)
from scripts.validate_global_restart import canonical_document, export_geometries


def stroke_set(document):
    """Compare literal undirected segments independently from hash identity."""
    return {tuple(sorted((tuple(row["a"]), tuple(row["b"]))))
            for row in document["strokes"]}


class QuaternaryTriangleEqInputsTests(unittest.TestCase):
    """These checks do not invoke coloring, equality propagation, or an oracle."""

    @classmethod
    def setUpClass(cls):
        """Export every declared prefix once without filtering invalid geometry."""
        cls.inventory = build_eq_holdout()
        cls.records = {row["key"]: row for row in cls.inventory["records"]}
        cls.exports = {row["key"]: row for row in export_geometries(cls.inventory["records"])}
        cls.audit_results = {}
        for key, row in cls.exports.items():
            if row["status"] != "geometry_ok":
                cls.audit_results[key] = {"status": "export_failed", "errors": row["errors"]}
                continue
            try:
                adapted = adapt_exported_geometry(row["geometry"], drawing=cls.records[key]["document"])
                audit, edges = audit_geometry(row["geometry"], adapted)
                cls.audit_results[key] = {"status": "audited", "audit": audit, "edges": edges}
            except (ValueError, AssertionError) as error:
                # A declared input remains in the inventory even if the frozen
                # geometry implementation cannot certify its rounded contacts.
                cls.audit_results[key] = {"status": "audit_failed", "error": str(error)}

    def test_complete_predeclared_counts_and_alias_coverage(self):
        """Shared rings, prefixes and the empty frame are counted honestly."""
        self.assertEqual(len(self.inventory["histories"]), 20)
        self.assertEqual(len(self.records), 129)
        self.assertEqual(sum(len(row["prefix_keys"]) for row in self.inventory["histories"]), 212)
        self.assertEqual(sum(len(row["aliases"]) for row in self.records.values()), 212)
        self.assertEqual(Counter(row["family"] for row in self.inventory["histories"]),
                         Counter({GUILLOTINE: 4, CHORDS: 4, POLYGONS: 12}))
        self.assertEqual(self.inventory["generation"]["maximum_source_strokes"], 25)
        empty = [row for row in self.records.values() if not row["document"]["strokes"]]
        self.assertEqual(len(empty), 1)
        self.assertEqual(len(empty[0]["aliases"]), 20)

    def test_every_history_replays_all_single_stroke_prefixes(self):
        """Canonical records preserve each insertion history without colors."""
        visited = set()
        for history in self.inventory["histories"]:
            previous = set()
            for step, key in enumerate(history["prefix_keys"]):
                row = self.records[key]
                document = canonical_document({"frame": {"width": 900, "height": 600},
                                               "strokes": history["ordered_strokes"][:step]})
                self.assertEqual(row["document"], document)
                self.assertEqual(key, stroke_set_key(document))
                self.assertEqual(set(document), {"frame", "strokes"})
                current = stroke_set(document)
                self.assertEqual(len(current), step)
                self.assertTrue(previous <= current)
                self.assertEqual(len(current - previous), int(step > 0))
                self.assertTrue(any(alias["history"] == history["id"] and alias["step"] == step
                                    for alias in row["aliases"]))
                previous = current
                visited.add(key)
            self.assertEqual(history["terminal_key"], history["prefix_keys"][-1])
        self.assertEqual(visited, set(self.records))

    def test_seeds_and_polygon_parameter_product_are_exact(self):
        """No shape or sampled seed is omitted after geometry inspection."""
        histories = self.inventory["histories"]
        self.assertEqual({(row["family"], row["seed"]) for row in histories
                          if row["family"] in RANDOM_FAMILIES},
                         {(family, seed) for family in RANDOM_FAMILIES for seed in SEEDS})
        self.assertEqual({(row["polygon_sides"], row["ring_count"], row["angle_offset_degrees"])
                          for row in histories if row["family"] == POLYGONS},
                         {(n, count, angle) for n in POLYGON_SIDES for count in RING_COUNTS
                          for angle in ANGLE_OFFSETS})
        for row in histories:
            expected = (row["polygon_sides"] * (2 * row["ring_count"] - 1)
                        if row["family"] == POLYGONS else STEPS)
            self.assertEqual(len(row["ordered_strokes"]), expected)

    def test_regular_rings_shared_endpoints_and_strict_frame_interior(self):
        """Check intended geometry from coordinates independently of faces."""
        for n in POLYGON_SIDES:
            for count in RING_COUNTS:
                for angle in ANGLE_OFFSETS:
                    paths = polygon_paths(n, count, angle)
                    self.assertEqual(len(paths), n * (2 * count - 1))
                    offset, previous_ring = 0, None
                    for layer, radius in enumerate(RADII[:count]):
                        edges = paths[offset:offset + n]
                        ring = [edge[0] for edge in edges]
                        for i, (first, second) in enumerate(edges):
                            self.assertEqual(second, ring[(i + 1) % n])
                            self.assertAlmostEqual(hypot(first[0] - CENTER[0], first[1] - CENTER[1]),
                                                   radius, places=7)
                            self.assertTrue(0 < first[0] < 900 and 0 < first[1] < 600)
                            self.assertTrue(all(value == round(value, 8) for value in first))
                        offset += n
                        if layer:
                            self.assertEqual(paths[offset:offset + n],
                                             [[previous_ring[i], ring[i]] for i in range(n)])
                            offset += n
                        previous_ring = ring
                    self.assertEqual(offset, len(paths))
        for parameters in ((4, 1, 0), (3, 4, 0), (3, 1, 45)):
            with self.assertRaises(ValueError):
                polygon_paths(*parameters)

    def test_geometry_export_and_audit_cover_all_inputs_without_filtering(self):
        """Failures remain explicit rather than changing the predeclared set."""
        self.assertEqual(set(self.exports), set(self.records))
        self.assertEqual(set(self.audit_results), set(self.records))
        for key, row in self.exports.items():
            self.assertFalse(row["coloring_performed"])
            self.assertIn(row["status"], {"geometry_ok", "geometry_error"})
            audit = self.audit_results[key]
            if audit["status"] == "audited":
                self.assertTrue(audit["audit"]["passed"])
                self.assertTrue(audit["audit"]["source_coverage_checked"])
                self.assertLessEqual(len(row["geometry"]["faces"]), 40)
            elif audit["status"] == "export_failed":
                self.assertTrue(audit["errors"])
            else:
                self.assertEqual(audit["status"], "audit_failed")
                self.assertTrue(audit["error"])

    def test_audited_polygon_terminals_have_expected_number_of_real_faces(self):
        """A complete new ring creates n annular cells; dangling prefixes may not."""
        audited_terminals = 0
        for history in self.inventory["histories"]:
            if history["family"] != POLYGONS:
                continue
            key = history["terminal_key"]
            if self.audit_results[key]["status"] != "audited":
                continue
            audited_terminals += 1
            geometry = self.exports[key]["geometry"]
            self.assertEqual(len(geometry["faces"]),
                             history["polygon_sides"] * (history["ring_count"] - 1) + 3)
        self.assertGreater(audited_terminals, 0)

    def test_deterministic_reconstruction_and_no_independence_overclaim(self):
        """The same declared inputs reproduce without inspecting old outcomes."""
        self.assertEqual(self.inventory, build_eq_holdout())
        generation = self.inventory["generation"]
        for field in ("outcome_filtering", "geometry_validation_performed_by_generator",
                      "propagation_performed", "oracle_performed", "colors_inherited_between_prefixes"):
            self.assertFalse(generation[field])
        self.assertFalse(generation["all_insertion_orders"])
        self.assertFalse(generation["chords"]["general_position_assumed"])
        self.assertIn("not independent graph families", generation["scope"])
        self.assertIn("not graph isomorphism", generation["deduplication"])


if __name__ == "__main__":
    unittest.main()

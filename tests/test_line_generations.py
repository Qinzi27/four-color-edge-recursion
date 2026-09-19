"""Geometry-derived mother-generation accounting, independent of coloring.

These small contact graphs are abstract incidence fixtures, not assertions
that every one has a specific planar drawing. Counts distinguish repeated
parent ports from distinct ancestor identities; ambiguity must remain visible
instead of choosing an arbitrary lexicographic parent.
"""

from copy import deepcopy
import unittest

from fourcolor.whole_lines import build_whole_lines
from scripts.analyze_line_generations import derive_generations, extract_whole_contacts
from scripts.validate_global_restart import export_geometries


class LineGenerationTests(unittest.TestCase):
    """Activation is synchronous and requires an established parent at BOTH ends."""

    def assert_counts(self, record, depth, port_count, ancestor_ids):
        """Compare depth and both explicitly different counting conventions."""
        self.assertEqual(record["depth"], depth)
        self.assertEqual(record["port_count"], port_count)
        self.assertEqual(record["ancestor_ids"], ancestor_ids)
        self.assertEqual(record["distinct_count"], len(ancestor_ids))
        self.assertNotIn("frame", ancestor_ids)

    def test_frame_is_the_only_initial_zero_depth_zero_count_root(self):
        """The frame is a reference, not a counted interior ancestor."""
        result = derive_generations({"frame": [[], []]})
        self.assertEqual(set(result), {"frame"})
        self.assert_counts(result["frame"], 0, 0, [])

    def test_line_with_two_frame_endpoints_has_depth_one(self):
        """Two attachments to the same frame do not create two interior ancestors."""
        contacts = {"frame": [[], []], "A": [["frame"], ["frame"]]}
        result = derive_generations(contacts)
        self.assert_counts(result["A"], 1, 1, ["A"])
        self.assertEqual(result["A"]["parent_depths"], [0, 0])
        self.assertEqual(result["A"]["parents"], [["frame"], ["frame"]])

    def test_one_root_and_one_child_endpoint_uses_the_deeper_parent(self):
        """A one-ended shortcut to frame cannot erase the other endpoint's depth."""
        contacts = {"frame": [[], []], "A": [["frame"], ["frame"]],
                    "B": [["frame"], ["A"]], "C": [["B"], ["frame"]]}
        result = derive_generations(contacts)
        self.assert_counts(result["B"], 2, 2, ["A", "B"])
        self.assert_counts(result["C"], 3, 3, ["A", "B", "C"])
        self.assertEqual(result["B"]["parent_depths"], [0, 1])
        self.assertEqual(result["C"]["parent_depths"], [2, 0])

    def test_sibling_lines_activate_together_and_child_waits_one_round(self):
        """Dictionary position cannot make a sibling an artificially earlier layer."""
        contacts = {"C": [["A"], ["B"]], "B": [["frame"], ["frame"]],
                    "frame": [[], []], "A": [["frame"], ["frame"]]}
        result = derive_generations(contacts)
        self.assertEqual((result["A"]["depth"], result["B"]["depth"]), (1, 1))
        self.assertEqual(result["C"]["parent_depths"], [1, 1])
        self.assert_counts(result["C"], 2, 3, ["A", "B", "C"])

    def test_shared_parent_is_counted_per_port_but_deduplicated_as_ancestor(self):
        """Repeated lineage grows 1,3,7 by ports but only 1,2,3 by identities."""
        contacts = {"frame": [[], []], "A": [["frame"], ["frame"]],
                    "B": [["A"], ["A"]], "C": [["B"], ["B"]]}
        result = derive_generations(contacts)
        self.assert_counts(result["A"], 1, 1, ["A"])
        self.assert_counts(result["B"], 2, 3, ["A", "B"])
        self.assert_counts(result["C"], 3, 7, ["A", "B", "C"])
        self.assertEqual(result["B"]["parents"], [["A"], ["A"]])

    def test_cycle_missing_endpoint_and_dependents_remain_unranked(self):
        """A circular dependency is not resolved by inventing a starting parent."""
        contacts = {"frame": [[], []], "A": [["frame"], ["B"]],
                    "B": [["frame"], ["A"]], "C": [["frame"], ["A"]],
                    "dangling": [["frame"], []]}
        result = derive_generations(contacts)
        self.assertEqual(set(result), set(contacts))
        for name in ("A", "B", "C", "dangling"):
            with self.subTest(line=name):
                for field in ("depth", "parent_depths", "port_count", "distinct_count", "ancestor_ids"):
                    self.assertIsNone(result[name][field])

    def test_multiple_endpoint_contacts_choose_only_the_lowest_depth_options(self):
        """Higher-level contacts are not counted as necessary parents."""
        contacts = {"frame": [[], []], "A": [["frame"], ["frame"]],
                    "B": [["A"], ["frame"]],
                    "C": [["B", "frame"], ["B", "A"]]}
        result = derive_generations(contacts)
        self.assertEqual(result["C"]["parents"], [["frame"], ["A"]])
        self.assertEqual(result["C"]["parent_depths"], [0, 1])
        self.assert_counts(result["C"], 2, 2, ["A", "C"])
        self.assertNotIn("B", result["C"]["ancestor_ids"])

    def test_tied_minimum_parents_keep_counts_unknown_for_descendants(self):
        """Depth may be known even when a unique lineage cannot be selected."""
        contacts = {"frame": [[], []], "A": [["frame"], ["frame"]],
                    "B": [["frame"], ["frame"]],
                    "X": [["B", "A"], ["frame"]],
                    "Y": [["X"], ["frame"]]}
        result = derive_generations(contacts)
        self.assertEqual(result["X"]["depth"], 2)
        self.assertEqual(result["X"]["parent_depths"], [1, 0])
        self.assertEqual(result["X"]["parents"], [["A", "B"], ["frame"]])
        self.assertEqual(result["Y"]["depth"], 3)
        self.assertEqual(result["Y"]["parents"], [["X"], ["frame"]])
        for name in ("X", "Y"):
            for field in ("port_count", "distinct_count", "ancestor_ids"):
                self.assertIsNone(result[name][field])

    def test_reversing_dictionary_and_contact_order_preserves_results_and_input(self):
        """Synchronous levels and sorted options do not depend on line ID scans."""
        contacts = {"frame": [[], []], "A": [["frame"], ["frame"]],
                    "B": [["frame"], ["frame"]],
                    "C": [["A"], ["A"]],
                    "X": [["C", "B", "A"], ["frame"]],
                    "Y": [["X"], ["C"]],
                    "cycle-a": [["cycle-b"], ["frame"]],
                    "cycle-b": [["cycle-a"], ["frame"]]}
        original = deepcopy(contacts)
        result = derive_generations(contacts)
        reversed_contacts = {name: [list(reversed(end)) for end in ends]
                             for name, ends in reversed(list(contacts.items()))}
        self.assertEqual(result, derive_generations(reversed_contacts))
        self.assertEqual(contacts, original)


class WholeLineGenerationGeometryTests(unittest.TestCase):
    """Real T/X junctions preserve one complete mother across middle contacts."""

    @classmethod
    def setUpClass(cls):
        """Export only two tiny geometries; no coloring routine is invoked."""
        exported = export_geometries([
            {"key": "T", "document": {"strokes": [
                {"a": [0, 300], "b": [900, 300]},
                {"a": [450, 300], "b": [450, 600]},
            ]}},
            {"key": "X", "document": {"strokes": [
                {"a": [0, 300], "b": [900, 300]},
                {"a": [450, 0], "b": [450, 600]},
            ]}},
        ])
        cls.models = {row["key"]: build_whole_lines(row["geometry"]) for row in exported}

    def test_t_attachment_is_child_endpoint_but_not_new_mother_endpoint(self):
        """The horizontal mother's two frame anchors survive the internal T."""
        model = self.models["T"]
        horizontal, vertical = "L:0,300>900,300", "L:450,300>450,600"
        contacts, details = extract_whole_contacts(model)
        self.assertEqual(set(contacts), {"frame", horizontal, vertical})
        self.assertEqual(contacts[horizontal], [["frame"], ["frame"]])
        self.assertEqual(contacts[vertical], [[horizontal], ["frame"]])
        self.assertEqual(details[horizontal]["endpoints"], [[0, 300], [900, 300]])
        self.assertEqual(details[horizontal]["interior_contacts"], [vertical])
        result = derive_generations(contacts)
        self.assertEqual(result[horizontal]["depth"], 1)
        self.assertEqual(result[vertical]["depth"], 2)
        self.assertEqual(result[vertical]["port_count"], 2)
        self.assertEqual(result[vertical]["distinct_count"], 2)

    def test_x_crossing_does_not_create_cyclic_endpoint_dependencies(self):
        """Both complete lines still have only frame parents, despite crossing."""
        model = self.models["X"]
        horizontal, vertical = "L:0,300>900,300", "L:450,0>450,600"
        contacts, details = extract_whole_contacts(model)
        self.assertEqual(set(contacts), {"frame", horizontal, vertical})
        result = derive_generations(contacts)
        for line, other in ((horizontal, vertical), (vertical, horizontal)):
            self.assertEqual(contacts[line], [["frame"], ["frame"]])
            self.assertEqual(details[line]["interior_contacts"], [other])
            self.assertEqual(result[line]["depth"], 1)
            self.assertEqual(result[line]["port_count"], 1)
            self.assertEqual(result[line]["ancestor_ids"], [line])


if __name__ == "__main__":
    unittest.main()

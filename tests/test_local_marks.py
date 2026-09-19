"""Finite regressions for the three deliberately bounded local comparisons."""

from copy import deepcopy
from pathlib import Path
import unittest

from scripts.compare_local_marks import (
    METHODS, ROOT, bounded_component, compare_cut, load_cases, validate_state,
)
from scripts.audit_retained_blocks import unpack_state


class LocalMarksTests(unittest.TestCase):
    """Test saved examples and repair guards without changing production policy."""

    @classmethod
    def setUpClass(cls):
        """Use the exact saved failures, never hand-adjust their old names."""
        cls.cases = {case["case"]: case for case in load_cases(
            ROOT / "docs/figures/anchor-failures-2026-09-18/manifest.json",
            ROOT / "outputs/anchor-forest-continuation-2026-09-18-v2.json")}

    def run_case(self, name, method):
        """Keep originals immutable and independently validate accepted outputs."""
        case = self.cases[name]
        before = deepcopy(case["state"])
        result = compare_cut(case["state"], case["cut"], method)
        self.assertEqual(case["state"], before)
        if result["status"] == "split":
            validate_state(unpack_state(result["final_state"]))
            self.assertTrue(result["boundary_audit"]["all_constraints_valid"])
        return result

    def test_a_and_b_need_no_old_side_repair(self):
        """The lightweight candidate decision suffices for both user examples."""
        for name in ("A", "B"):
            for method in METHODS:
                with self.subTest(case=name, method=method):
                    result = self.run_case(name, method)
                    self.assertEqual(result["status"], "split")
                    self.assertEqual(result["used_stage"], "M1_direct")
                    self.assertEqual(result["changed_old_count"], 0)
                    self.assertFalse(result["repair"]["attempted"])
                    self.assertEqual(result["repair"]["reason"], "no_repair_needed")

    def test_a_original_names_are_not_silently_swapped(self):
        """A uses the preserved old state, not the user's globally relabeled one."""
        result = self.run_case("A", METHODS[0])
        self.assertEqual(result["new_name"], 3)
        self.assertEqual(result["new_name_child_bounds"], (0, 0, 187, 402))
        self.assertEqual(result["actual_inherit"], "left")

    def test_b_reuses_one_only_in_the_internal_child(self):
        """Exterior name 1 is not a permanent inherited ban on interior sides."""
        result = self.run_case("B", METHODS[0])
        self.assertEqual(result["new_name"], 1)
        self.assertEqual(result["new_name_child_bounds"], (160, 172, 518, 327))
        self.assertEqual(result["actual_inherit"], "right")

    def test_old_fixed_right_c_requires_one_old_side_repair(self):
        """Historical 342 only: corrected 232 needs no repair (test_c_restart)."""
        direct = self.run_case("C", METHODS[0])
        self.assertEqual(direct["status"], "blocked")
        self.assertEqual([entry["candidates"] for entry in direct["candidates_before"]], [[], []])
        outputs = []
        for method in METHODS[1:]:
            result = self.run_case("C", method)
            self.assertEqual(result["status"], "split")
            self.assertEqual(result["changed_old_count"], 1)
            self.assertEqual(result["old_name_changes"], [{"id": "root.r.r", "before": 2, "after": 3}])
            self.assertEqual(result["new_name"], 2)
            self.assertEqual(result["repair"]["component_ids"], ["root.r.r"])
            outputs.append(result["final_state"])
        self.assertEqual(outputs[0], outputs[1])

    def test_profile_records_are_not_side_counts(self):
        """New spans and renamed old spans have separately defined accounting."""
        result = self.run_case("C", METHODS[1])
        self.assertEqual(result["profile_change_record_count"], len(result["profile_changes"]))
        self.assertEqual(result["touched_mother_count"], len(result["touched_mothers"]))
        self.assertGreater(result["profile_change_record_count"], result["changed_old_count"])

    def test_component_rejects_outside_and_parent(self):
        """Fixed anchors may be encountered but are never swapped."""
        graph = {"outside": {"a"}, "a": {"outside", "p"}, "p": {"a"}}
        names = {"outside": 1, "a": 2, "p": 3}
        _, reason = bounded_component(graph, names, "a", {1, 2}, "p")
        self.assertEqual(reason, "component_reaches_fixed_outside_or_parent")
        _, reason = bounded_component(graph, names, "a", {2, 3}, "p")
        self.assertEqual(reason, "component_reaches_fixed_outside_or_parent")

    def test_component_is_rejected_not_truncated_at_size_limit(self):
        """A four-side component cannot masquerade as a successful three-side swap."""
        graph = {"p": {"a"}, "a": {"p", "b"}, "b": {"a", "c"},
                 "c": {"b", "d"}, "d": {"c"}, "outside": set()}
        names = {"p": 4, "a": 2, "b": 3, "c": 2, "d": 3, "outside": 1}
        component, reason = bounded_component(graph, names, "a", {2, 3}, "p")
        self.assertEqual(component, {"a", "b", "c", "d"})
        self.assertEqual(reason, "component_exceeds_three_old_sides")

    def test_component_rejects_distance_three(self):
        """The radius guard is independent of the three-side cardinality guard."""
        graph = {"p": {"a"}, "a": {"p", "b"}, "b": {"a", "c"},
                 "c": {"b"}, "outside": set()}
        names = {"p": 4, "a": 2, "b": 3, "c": 2, "outside": 1}
        component, reason = bounded_component(graph, names, "a", {2, 3}, "p")
        self.assertEqual(component, {"a", "b", "c"})
        self.assertEqual(reason, "component_exceeds_distance_two")

    def test_oversized_chain_stops_at_rejection_witness_without_mutation(self):
        """Do not collect a long tail or exchange a truncated prefix after rejection."""
        graph = {"p": {"a"}, "a": {"p", "b"}, "b": {"a", "c"},
                 "c": {"b", "d"}, "d": {"c", "e"}, "e": {"d"}, "outside": set()}
        names = {"p": 4, "a": 2, "b": 3, "c": 2, "d": 3, "e": 2, "outside": 1}
        before = dict(names)
        component, reason = bounded_component(graph, names, "a", {2, 3}, "p")
        self.assertEqual(component, {"a", "b", "c", "d"})
        self.assertEqual(reason, "component_exceeds_three_old_sides")
        self.assertNotIn("e", component)
        self.assertEqual(names, before)

    def test_unknown_method_is_rejected(self):
        """Method spelling cannot silently enable a more expansive policy."""
        case = self.cases["A"]
        with self.assertRaises(ValueError):
            compare_cut(case["state"], case["cut"], "search_until_success")


if __name__ == "__main__":
    unittest.main()

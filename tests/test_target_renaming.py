"""Independent finite oracles for fixed-target atomic renaming schedules.

Enumeration belongs only to these bounded tests. The production planner
uses no color search and does not claim to find a proper target naming.
"""

from dataclasses import FrozenInstanceError, replace
from itertools import combinations, permutations, product
import unittest

from fourcolor.target_renaming import plan_target_renaming, required_atomic_batch, verify_schedule


def proper(symbols, edges):
    """Check literal old-edge inequalities without the production verifier."""
    return all(symbols[left] != symbols[right] for left, right in edges)


def ordered_partitions(vertices):
    """Enumerate all ordered nonempty set partitions for at most three IDs."""
    if not vertices:
        yield ()
        return
    for count in range(1, len(vertices) + 1):
        for slots in product(range(count), repeat=len(vertices)):
            if set(slots) == set(range(count)):
                yield tuple(tuple(vertex for vertex, slot in zip(vertices, slots) if slot == index)
                            for index in range(count))


def legal_replay(initial, target, edges, batches):
    """Check each complete intermediate state directly, independent of SCCs."""
    current = dict(initial)
    for batch in batches:
        for vertex in batch:
            current[vertex] = target[vertex]
        if not proper(current, edges):
            return False
    return current == target


class TargetRenamingTests(unittest.TestCase):
    """Check exact bounds, operational assumptions, validation, and scaling."""

    def test_two_vertex_swap_requires_one_atomic_pair(self):
        plan = plan_target_renaming([("left", "right")], {"left": 0, "right": 1},
                                    {"left": 1, "right": 0})
        self.assertEqual(plan.components, (("left", "right"),))
        self.assertEqual(plan.minimum_max_batch_size, 2)
        self.assertTrue(verify_schedule(plan, plan.batches))
        self.assertFalse(verify_schedule(plan, [("left",), ("right",)]))
        self.assertFalse(verify_schedule(plan, [("right",), ("left",)]))

    def test_triangle_rotation_requires_three_simultaneous_changes(self):
        plan = plan_target_renaming(combinations(("a", "b", "c"), 2),
                                    {"a": 0, "b": 1, "c": 2},
                                    {"a": 1, "b": 2, "c": 0})
        self.assertEqual(plan.components, (("a", "b", "c"),))
        self.assertEqual(plan.minimum_max_batch_size, 3)
        for schedule in ordered_partitions(plan.changed_ids):
            self.assertEqual(verify_schedule(plan, schedule), len(schedule) == 1)

    def test_directed_chain_uses_dependencies_first_but_can_be_one_batch(self):
        plan = plan_target_renaming([("a", "b"), ("b", "c")],
                                    {"a": 0, "b": 1, "c": 2},
                                    {"a": 1, "b": 2, "c": 3})
        self.assertEqual(plan.dependencies, (("a", "b"), ("b", "c")))
        self.assertEqual(plan.batches, (("c",), ("b",), ("a",)))
        self.assertEqual(plan.minimum_max_batch_size, 1)
        self.assertTrue(verify_schedule(plan, plan.batches))
        self.assertTrue(verify_schedule(plan, [plan.changed_ids]))
        self.assertTrue(verify_schedule(plan, [("b", "c"), ("a",)]))
        self.assertFalse(verify_schedule(plan, [("a",), ("b",), ("c",)]))

    def test_pending_edge_can_conflict_until_final_commit(self):
        plan = plan_target_renaming([], {"a": 0, "b": 0}, {"a": 1, "b": 2},
                                    added_edges=[("a", "b")])
        self.assertTrue(verify_schedule(plan, plan.batches))
        self.assertEqual(plan.dependencies, ())
        self.assertTrue(verify_schedule(plan, [("b",), ("a",)]))
        # The same conflicting edge would be disallowed if already committed.
        with self.assertRaises(ValueError):
            plan_target_renaming([("a", "b")], {"a": 0, "b": 0}, {"a": 1, "b": 2})

    def test_components_may_merge_but_cannot_be_arbitrarily_reordered(self):
        plan = plan_target_renaming([("a", "b"), ("b", "c")],
                                    {"a": 0, "b": 1, "c": 2, "d": 0},
                                    {"a": 1, "b": 0, "c": 1, "d": 3})
        self.assertEqual(plan.components, (("a", "b"), ("c",), ("d",)))
        self.assertTrue(verify_schedule(plan, [("a", "b", "d"), ("c",)]))
        self.assertFalse(verify_schedule(plan, [("c",), ("a", "b", "d")]))
        self.assertTrue(verify_schedule(plan, [plan.changed_ids]))

    def test_weighted_optimum_zero_weights_and_fixed_ids(self):
        plan = plan_target_renaming([("a", "b")],
                                    {"outside": 0, "a": 1, "b": 2, "free": 0},
                                    {"outside": 0, "a": 2, "b": 1, "free": 3},
                                    fixed=["outside", "outside"],
                                    weights={"outside": 500, "a": 3, "b": 4, "free": 10})
        self.assertEqual(plan.minimum_max_batch_size, 2)
        self.assertEqual(plan.minimum_max_batch_weight, 10)
        self.assertEqual(plan.fixed_ids, ("outside",))
        zero = plan_target_renaming([("a", "b")], {"a": 0, "b": 1},
                                    {"a": 1, "b": 0}, weights={"a": 0, "b": 0})
        self.assertEqual(zero.minimum_max_batch_weight, 0)
        self.assertEqual(zero.minimum_max_batch_size, 2)

    def test_no_changes_means_no_batches(self):
        plan = plan_target_renaming([("a", "b")], {"a": 0, "b": 1}, {"b": 1, "a": 0})
        self.assertEqual(plan.components, ())
        self.assertEqual(plan.batches, ())
        self.assertEqual(plan.minimum_max_batch_size, 0)
        self.assertEqual(plan.minimum_max_batch_weight, 0)
        self.assertTrue(verify_schedule(plan, ()))
        self.assertFalse(verify_schedule(plan, [()]))
        self.assertFalse(verify_schedule(plan, [("a",)]))

    def test_input_copies_are_immutable_and_order_is_stable(self):
        edges = [["a", "z"], ["z", "a"]]
        initial = {"z": 0, "a": 1}
        target = {"a": 0, "z": 1}
        weights = {"z": 2, "a": 3}
        plan = plan_target_renaming(edges, initial, target, weights=weights)
        edges[0][0] = "missing"
        initial["z"] = 3
        target["a"] = 2
        weights["z"] = 99
        self.assertEqual(plan.vertices, ("z", "a"))
        self.assertEqual(plan.base_edges, (("z", "a"),))
        self.assertEqual(plan.initial_symbols, (0, 1))
        self.assertEqual(plan.target_symbols, (1, 0))
        self.assertEqual(plan.weights, (2, 3))
        self.assertTrue(verify_schedule(plan, plan.batches))
        with self.assertRaises(FrozenInstanceError):
            plan.minimum_max_batch_size = 99

    def test_verifier_checks_states_not_dependency_metadata(self):
        plan = plan_target_renaming([("a", "b")], {"a": 0, "b": 1}, {"a": 1, "b": 0})
        misleading = replace(plan, dependencies=(), components=(), minimum_max_batch_size=1)
        self.assertFalse(verify_schedule(misleading, [("a",), ("b",)]))
        self.assertTrue(verify_schedule(misleading, [("a", "b")]))
        for schedule in ([()], [("a", "a", "b")], [("a",)], [("missing",)], "ab", None,
                         [("a", "b"), ("a",)], ["ab"], [("a", [])]):
            with self.subTest(schedule=schedule):
                self.assertFalse(verify_schedule(plan, schedule))
        self.assertFalse(verify_schedule(replace(plan, changed_ids=("a",)), [("a", "b")]))

    def test_invalid_inputs_are_rejected(self):
        invalid = [
            ([], {}, {}, {}),
            ([], {"": 0}, {"": 1}, {}),
            ([], {"  ": 0}, {"  ": 1}, {}),
            ([], {1: 0}, {1: 1}, {}),
            ([], {"a": True}, {"a": 1}, {}),
            ([], {"a": 0}, {"a": False}, {}),
            ([], {"a": 4}, {"a": 1}, {}),
            ([], {"a": 0}, {"b": 1}, {}),
            ([("a", "a")], {"a": 0}, {"a": 1}, {}),
            ([("a", "missing")], {"a": 0}, {"a": 1}, {}),
            ([("a",)], {"a": 0}, {"a": 1}, {}),
            (["ab"], {"a": 0, "b": 1}, {"a": 1, "b": 2}, {}),
            (None, {"a": 0}, {"a": 1}, {}),
            ([], {"a": 0}, {"a": 1}, {"fixed": ["a"]}),
            ([], {"a": 0}, {"a": 1}, {"fixed": ["missing"]}),
            ([], {"a": 0}, {"a": 1}, {"fixed": "a"}),
            ([], {"a": 0}, {"a": 1}, {"weights": {}}),
            ([], {"a": 0}, {"a": 1}, {"weights": {"a": -1}}),
            ([], {"a": 0}, {"a": 1}, {"weights": {"a": True}}),
            ([], {"a": 0}, {"a": 1}, {"weights": {"a": 1.5}}),
            ([], {"a": 0}, {"a": 1}, {"weights": {"a": 1, "b": 2}}),
            ([("a", "b")], {"a": 0, "b": 1}, {"a": 2, "b": 2}, {}),
            ([], {"a": 0, "b": 1}, {"a": 2, "b": 2}, {"added_edges": [("a", "b")]}),
        ]
        for edges, initial, target, kwargs in invalid:
            with self.subTest(edges=edges, initial=initial, target=target, kwargs=kwargs):
                with self.assertRaises(ValueError):
                    plan_target_renaming(edges, initial, target, **kwargs)

    def test_long_directed_chain_does_not_use_recursion(self):
        vertices = tuple(f"class-{index}" for index in range(4000))
        edges = tuple(zip(vertices, vertices[1:]))
        initial = {vertex: index % 4 for index, vertex in enumerate(vertices)}
        target = {vertex: (index + 1) % 4 for index, vertex in enumerate(vertices)}
        plan = plan_target_renaming(edges, initial, target)
        self.assertEqual(plan.minimum_max_batch_size, 1)
        self.assertEqual(plan.batches, tuple((vertex,) for vertex in reversed(vertices)))
        self.assertTrue(verify_schedule(plan, [plan.changed_ids]))

    def test_required_batch_follows_closure_not_only_start_component(self):
        plan = plan_target_renaming([("a", "b"), ("b", "c")],
                                    {"a": 0, "b": 1, "c": 2},
                                    {"a": 1, "b": 2, "c": 3})
        self.assertEqual(plan.minimum_max_batch_size, 1)
        self.assertEqual(required_atomic_batch(plan, ["a"]), ("a", "b", "c"))
        self.assertEqual(required_atomic_batch(plan, ["a"], completed=["c"]), ("a", "b"))
        self.assertEqual(required_atomic_batch(plan, ["c"]), ("c",))
        self.assertEqual(required_atomic_batch(plan, []), ())
        self.assertEqual(required_atomic_batch(plan, [], completed=plan.changed_ids), ())
        self.assertEqual(required_atomic_batch(plan, ["b", "b"]), ("b", "c"))
        for requested, completed in (([], ["a"]), (["a"], ["a"]), (["missing"], []),
                                     ("a", []), (None, []), ([], "c"), ([], ["missing"])):
            with self.subTest(requested=requested, completed=completed):
                with self.assertRaises(ValueError):
                    required_atomic_batch(plan, requested, completed=completed)

    def test_required_batch_is_smallest_by_independent_subset_enumeration(self):
        # This four-vertex fixture includes a nontrivial SCC, its dependent,
        # and an independent change. Enumerate every valid completed set and
        # every request to test necessity and sufficiency against actual edges.
        initial = {"a": 0, "b": 1, "c": 2, "d": 0}
        target = {"a": 1, "b": 0, "c": 1, "d": 3}
        edges = [("a", "b"), ("b", "c")]
        plan = plan_target_renaming(edges, initial, target)
        for flags in product((False, True), repeat=4):
            done = {v for v, flag in zip(plan.vertices, flags) if flag}
            current = {v: target[v] if v in done else initial[v] for v in plan.vertices}
            if not proper(current, edges):
                continue
            remaining = tuple(v for v in plan.vertices if v not in done)
            subsets = [{v for v, flag in zip(remaining, subset_flags) if flag}
                       for subset_flags in product((False, True), repeat=len(remaining))]
            for requested in subsets:
                result = set(required_atomic_batch(plan, requested, completed=done))
                self.assertTrue(requested <= result)
                legal_batches = []
                for candidate in subsets:
                    if not requested <= candidate:
                        continue
                    updated = {v: target[v] if v in candidate else current[v] for v in plan.vertices}
                    if proper(updated, edges):
                        legal_batches.append(candidate)
                self.assertIn(result, legal_batches)
                self.assertTrue(all(result <= candidate for candidate in legal_batches))

    def test_exhaustive_three_color_graphs_up_to_three_vertices(self):
        # Every simple labeled graph and every proper initial/target pair is
        # included. Ordered partitions provide an independent optimization
        # oracle; subsets check the exact completed-set closure equivalence.
        cases = 0
        for size in range(1, 4):
            vertices = tuple(f"v{index}" for index in range(size))
            possible_edges = tuple(combinations(vertices, 2))
            weights = {vertex: index for index, vertex in enumerate(vertices)}
            for mask in product((False, True), repeat=len(possible_edges)):
                edges = tuple(edge for edge, included in zip(possible_edges, mask) if included)
                colorings = [dict(zip(vertices, colors)) for colors in product(range(3), repeat=size)
                             if proper(dict(zip(vertices, colors)), edges)]
                for initial, target in product(colorings, repeat=2):
                    plan = plan_target_renaming(edges, initial, target, weights=weights)
                    changed = plan.changed_ids
                    legal = [batches for batches in ordered_partitions(changed)
                             if legal_replay(initial, target, edges, batches)]
                    self.assertTrue(legal)
                    self.assertEqual(plan.minimum_max_batch_size,
                                     min(max(map(len, batches), default=0) for batches in legal))
                    self.assertEqual(plan.minimum_max_batch_weight, min(
                        max((sum(weights[v] for v in batch) for batch in batches), default=0)
                        for batches in legal))
                    self.assertTrue(verify_schedule(plan, plan.batches))
                    self.assertTrue(legal_replay(initial, target, edges, plan.batches))

                    # Test single-vertex feasibility through actual permutations,
                    # not the planner's chosen component order.
                    sequential = any(legal_replay(initial, target, edges,
                                                 tuple((vertex,) for vertex in order))
                                     for order in permutations(changed))
                    self.assertEqual(sequential, all(len(group) == 1 for group in plan.components))
                    for flags in product((False, True), repeat=len(changed)):
                        completed = {vertex for vertex, flag in zip(changed, flags) if flag}
                        state = {vertex: target[vertex] if vertex in completed else initial[vertex]
                                 for vertex in vertices}
                        closed = all(source not in completed or dependency in completed
                                     for source, dependency in plan.dependencies)
                        self.assertEqual(proper(state, edges), closed)
                    cases += 1
        self.assertEqual(cases, 2295)


if __name__ == "__main__":
    unittest.main()

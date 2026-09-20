"""Audit local layer repair with independent parity and small finite oracles."""

from copy import deepcopy
from itertools import combinations
import unittest

from fourcolor.circle_layer_repair import repair_first_layer, verify_repair_result


def independent_even(vertices, edges, chosen):
    """Count full integer degrees, including two incidences for every loop."""
    degrees = dict.fromkeys(vertices, 0)
    for edge_id in chosen:
        for vertex in edges[edge_id]:
            degrees[vertex] += 1
    return all(value % 2 == 0 for value in degrees.values())


def independent_q(vertices, edges, chosen):
    """Use union-find and full graph degrees, independent of the repair forest."""
    parent = {vertex: vertex for vertex in vertices}
    degrees = dict.fromkeys(vertices, 0)

    def root(vertex):
        """Follow parent links; tiny oracle instances need no path compression."""
        while parent[vertex] != vertex:
            vertex = parent[vertex]
        return vertex

    for a, b in edges:
        degrees[a] += 1
        degrees[b] += 1
    for edge_id in chosen:
        a, b = edges[edge_id]
        parent[root(a)] = root(b)
    odd_counts = dict.fromkeys((root(vertex) for vertex in vertices), 0)
    for vertex in vertices:
        odd_counts[root(vertex)] += degrees[vertex] % 2
    return sum(value % 2 for value in odd_counts.values())


def all_subsets(size):
    """Enumerate edge subsets by bit mask with no random sampling."""
    return [frozenset(index for index in range(size) if mask & (1 << index))
            for mask in range(1 << size)]


def prism(size):
    """Return two disjoint rings, their radial links, and annular face moves."""
    vertices = tuple(range(2 * size))
    edges = (tuple((index, (index + 1) % size) for index in range(size))
             + tuple((size + index, size + (index + 1) % size) for index in range(size))
             + tuple((index, size + index) for index in range(size)))
    moves = tuple((index, size + index, 2 * size + index,
                   2 * size + (index + 1) % size) for index in range(size))
    return vertices, edges, tuple(range(2 * size)), moves


def wheel(size):
    """Give every bounded triangle and the outer rim as explicit even moves."""
    vertices = tuple(range(size + 1))
    edges = (tuple((index, (index + 1) % size) for index in range(size))
             + tuple((index, size) for index in range(size)))
    moves = tuple((index, size + index, size + (index + 1) % size)
                  for index in range(size)) + (tuple(range(size)),)
    return vertices, edges, moves


class CircleLayerRepairTests(unittest.TestCase):
    """Exercise certified progress, explicit stalls, validation and cost semantics."""

    def test_odd_prisms_repair_in_one_annular_face_move(self):
        """One four-edge toggle joins the two odd ring components into an even one."""
        for size in (3, 5):
            vertices, edges, first, moves = prism(size)
            result = repair_first_layer(vertices, edges, first, moves)
            with self.subTest(size=size):
                self.assertEqual(result["status"], "completed")
                self.assertEqual(result["initial_obstruction_count"], 2)
                self.assertEqual(result["final_obstruction_count"], 0)
                self.assertEqual(result["step_count"], 1)
                self.assertEqual(result["total_edge_flip_count"], 4)
                self.assertEqual(result["final_edge_change_count"], 4)
                self.assertTrue(independent_even(vertices, edges, result["final_first_layer"]))
                self.assertTrue(independent_even(vertices, edges, result["completion"]["second_layer"]))
                self.assertEqual(set(result["final_first_layer"])
                                 | set(result["completion"]["second_layer"]), set(range(len(edges))))
                self.assertTrue(verify_repair_result(vertices, edges, first, moves, result)["passed"])

    def test_cost_selects_cheapest_improving_move_before_edge_id_ties(self):
        """All prism face moves reach q=0; exact integer costs break the tie."""
        vertices, edges, first, moves = prism(5)
        costs = [1] * len(edges)
        costs[0] = 10
        result = repair_first_layer(vertices, edges, first, moves, edge_costs=costs)
        self.assertEqual(result["steps"][0]["selected_candidate_index"], 1)
        self.assertEqual(result["cumulative_flip_cost"], 4)
        self.assertEqual(result["final_changed_cost"], 4)
        self.assertEqual(result["edge_costs"], costs)
        self.assertTrue(verify_repair_result(
            vertices, edges, first, moves, result, edge_costs=costs)["passed"])

    def test_edge_ids_make_equal_cost_choices_independent_of_candidate_order(self):
        """Candidate order matters only after the complete mathematical priority."""
        vertices, edges, first, moves = prism(3)
        forward = repair_first_layer(vertices, edges, first, moves)
        backward = repair_first_layer(vertices, edges, first, tuple(reversed(moves)))
        self.assertEqual(forward["final_first_layer"], backward["final_first_layer"])
        self.assertEqual(forward["steps"][0]["selected_candidate_index"], 0)
        self.assertEqual(backward["steps"][0]["selected_candidate_index"], 2)

    def test_an_already_completable_layer_is_unchanged(self):
        """Even prism rings already pass the fixed-layer criterion: do no work."""
        vertices, edges, first, moves = prism(4)
        result = repair_first_layer(vertices, edges, first, moves)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["steps"], [])
        self.assertEqual(result["initial_first_layer"], result["final_first_layer"])
        self.assertEqual(result["final_changed_edges"], [])
        self.assertEqual(result["total_edge_flip_count"], 0)
        self.assertEqual(result["terminal_candidate_scores"], [])

    def test_empty_candidate_family_stalls_without_global_infeasibility_claim(self):
        """No candidate is not evidence against a different pair of layers."""
        vertices, edges, first, _ = prism(3)
        result = repair_first_layer(vertices, edges, first, ())
        self.assertEqual(result["status"], "stalled")
        self.assertEqual(result["final_obstruction_count"], 2)
        self.assertEqual(result["terminal_candidate_scores"], [])
        self.assertIsNone(result["completion"])
        claim = verify_repair_result(vertices, edges, first, (), result)["claim"]
        self.assertEqual(claim, "no-strictly-improving-supplied-move-at-final-state")

    def test_wheel_single_faces_stall_but_two_face_union_can_escape(self):
        """Two hub-sharing triangle boundaries form an even nonsimple move.

        The initial state has no improving single face boundary. Supplying their
        edge-disjoint union permits a single strict drop from q=2 to q=0. This
        distinguishes a move-family stall from mathematical uncolorability.
        """
        vertices, edges, moves = wheel(8)
        first = (0, 1, 4, 5, 8, 10, 12, 14)
        stalled = repair_first_layer(vertices, edges, first, moves)
        self.assertEqual(stalled["status"], "stalled")
        self.assertEqual(stalled["initial_obstruction_count"], 2)
        self.assertEqual(len(stalled["terminal_candidate_scores"]), 9)
        self.assertTrue(all(score["q_after"] >= 2
                            for score in stalled["terminal_candidate_scores"]))
        composite_move = (2, 6, 10, 11, 14, 15)
        extended = moves + (composite_move,)
        completed = repair_first_layer(vertices, edges, first, extended)
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["step_count"], 1)
        self.assertEqual(completed["steps"][0]["selected_candidate_index"], 9)
        self.assertEqual(completed["final_obstruction_count"], 0)
        self.assertEqual(completed["cumulative_flip_cost"], 6)
        self.assertTrue(verify_repair_result(vertices, edges, first, moves, stalled)["passed"])
        self.assertTrue(verify_repair_result(vertices, edges, first, extended, completed)["passed"])

    def test_repeated_flips_and_final_changes_have_different_costs(self):
        """A five-wheel reaches q=6 -> 2 -> 0 and flips one rim edge twice."""
        vertices, edges, moves = wheel(5)
        costs = [2] * 5 + [1] * 5
        result = repair_first_layer(vertices, edges, (), moves, edge_costs=costs)
        self.assertEqual([(step["q_before"], step["q_after"]) for step in result["steps"]],
                         [(6, 2), (2, 0)])
        self.assertEqual(result["total_edge_flip_count"], 8)
        self.assertEqual(result["final_edge_change_count"], 6)
        self.assertEqual(result["cumulative_flip_cost"], 14)
        self.assertEqual(result["final_changed_cost"], 10)
        self.assertEqual(result["strict_descent_step_bound"], 3)
        self.assertLessEqual(result["step_count"], result["strict_descent_step_bound"])
        # q takes priority over cost: the first move is the costlier whole rim.
        self.assertEqual(result["steps"][0]["selected_candidate_index"], 5)

    def test_loops_parallel_edges_disconnected_graph_and_isolates(self):
        """An isolated vertex remains an even component; loops have even degree."""
        vertices = tuple(range(7))
        edges = tuple(combinations(range(4), 2)) + ((4, 4), (4, 5), (4, 5))
        first = (0, 1, 3, 6, 7, 8)
        moves = ((1, 2, 5), (6,), (7, 8))
        result = repair_first_layer(vertices, edges, first, moves)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["odd_degree_vertices"], [0, 1, 2, 3])
        self.assertEqual(result["initial_obstructed_components"], [[0, 1, 2], [3]])
        self.assertTrue(set((6, 7, 8)) <= set(result["final_first_layer"]))
        self.assertTrue(verify_repair_result(vertices, edges, first, moves, result)["passed"])

    def test_empty_graph_and_zero_costs_are_valid(self):
        """Zero costs are exact; no phantom edge or vertex is introduced."""
        result = repair_first_layer((), (), (), (), edge_costs=())
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["completion"]["second_layer"], [])
        vertices, edges, first, moves = prism(3)
        free = repair_first_layer(vertices, edges, first, moves, edge_costs=[0] * len(edges))
        self.assertEqual(free["cumulative_flip_cost"], 0)
        self.assertEqual(free["final_changed_cost"], 0)
        self.assertEqual(free["total_edge_flip_count"], 4)

    def test_invalid_moves_layers_and_costs_are_rejected(self):
        """Malformed inputs cannot be interpreted as alternative mathematical data."""
        vertices, edges, first, moves = prism(3)
        invalid_moves = (None, ((),), ((0,),), ((0, 0),), ((False,),),
                         ((len(edges),),), (moves[0], tuple(reversed(moves[0]))))
        for candidates in invalid_moves:
            with self.subTest(moves=candidates):
                with self.assertRaises(ValueError):
                    repair_first_layer(vertices, edges, first, candidates)
        invalid_costs = ((), [1] * (len(edges) - 1), [True] * len(edges),
                         [-1] * len(edges), [1.0] * len(edges), [float("nan")] * len(edges), 4)
        for costs in invalid_costs:
            with self.subTest(costs=costs):
                with self.assertRaises(ValueError):
                    repair_first_layer(vertices, edges, first, moves, edge_costs=costs)
        for wrong_first in ((0,), (0, 0), (False,), (len(edges),)):
            with self.subTest(first=wrong_first):
                with self.assertRaises(ValueError):
                    repair_first_layer(vertices, edges, wrong_first, moves)
        with self.assertRaises(ValueError):
            repair_first_layer((0, True), (), (), ())

    def test_tampered_reports_are_rejected(self):
        """Audit scores, transitions, totals, strict numeric types and completion."""
        vertices, edges, first, moves = prism(3)
        good = repair_first_layer(vertices, edges, first, moves)
        changed_reports = []
        for field, value in (("initial_obstruction_count", 4),
                             ("final_obstruction_count", False),
                             ("step_count", True),
                             ("status", "stalled"),
                             ("final_changed_edges", []),
                             ("total_edge_flip_count", 0),
                             ("cumulative_flip_cost", 0),
                             ("final_changed_cost", 0),
                             ("edge_costs", [True] * len(edges)),
                             ("initial_obstructed_components", [])):
            changed = deepcopy(good)
            changed[field] = value
            changed_reports.append(changed)
        for field, value in (("q_after", 2), ("selected_candidate_index", 1),
                             ("first_layer_after", []), ("step", True)):
            changed = deepcopy(good)
            changed["steps"][0][field] = value
            changed_reports.append(changed)
        for field, value in (("q_after", -2), ("flip_cost", 0),
                             ("strictly_improves", 1), ("candidate_index", False)):
            changed = deepcopy(good)
            changed["steps"][0]["candidate_scores"][0][field] = value
            changed_reports.append(changed)
        changed = deepcopy(good)
        changed["completion"]["second_layer"] = []
        changed_reports.append(changed)
        changed = deepcopy(good)
        changed["steps"].append(deepcopy(changed["steps"][0]))
        changed_reports.append(changed)
        changed = deepcopy(good)
        changed["unverified_claim"] = "globally optimal"
        changed_reports.append(changed)
        for position, changed in enumerate(changed_reports):
            with self.subTest(position=position):
                with self.assertRaises(ValueError):
                    verify_repair_result(vertices, edges, first, moves, changed)

    def test_forged_stall_or_incomplete_terminal_scores_are_rejected(self):
        """The whole supplied move family must be represented at a stalled state."""
        vertices, edges, moves = wheel(8)
        first = (0, 1, 4, 5, 8, 10, 12, 14)
        stalled = repair_first_layer(vertices, edges, first, moves)
        for mutate in (lambda result: result["terminal_candidate_scores"].pop(),
                       lambda result: result["terminal_candidate_scores"][0].update(q_after=0),
                       lambda result: result.update(completion={"status": "completed"})):
            changed = deepcopy(stalled)
            mutate(changed)
            with self.assertRaises(ValueError):
                verify_repair_result(vertices, edges, first, moves, changed)
        # Reusing an empty-family stall with newly supplied improving moves fails.
        vertices, edges, first, moves = prism(3)
        empty_family_stall = repair_first_layer(vertices, edges, first, ())
        with self.assertRaises(ValueError):
            verify_repair_result(vertices, edges, first, moves, empty_family_stall)

    def test_every_small_graph_all_even_moves_against_independent_layer_oracle(self):
        """Exhaust all simple graphs through four vertices and every even A.

        The candidate family is every nonempty even subset. Thus any feasible
        alternative A can be reached directly by A XOR A'. A completed result
        must coincide with existence of any covering pair of even subsets.
        This finite test audits code only and is not a general coloring proof.
        """
        graph_count = first_layer_count = 0
        for size in range(5):
            vertices = tuple(range(size))
            possible = tuple(combinations(vertices, 2))
            for graph_ids in all_subsets(len(possible)):
                edges = tuple(possible[index] for index in sorted(graph_ids))
                graph_count += 1
                even_layers = [chosen for chosen in all_subsets(len(edges))
                               if independent_even(vertices, edges, chosen)]
                moves = [chosen for chosen in even_layers if chosen]
                required = frozenset(range(len(edges)))
                has_covering_pair = any(first | second == required
                                        for first in even_layers for second in even_layers)
                for first in even_layers:
                    first_layer_count += 1
                    result = repair_first_layer(vertices, edges, first, moves)
                    with self.subTest(vertices=size, edges=edges, first=sorted(first)):
                        self.assertEqual(result["initial_obstruction_count"],
                                         independent_q(vertices, edges, first))
                        self.assertEqual(result["status"] == "completed", has_covering_pair)
                        self.assertLessEqual(result["step_count"],
                                             result["initial_obstruction_count"] // 2)
                        for step in result["steps"]:
                            current = frozenset(step["first_layer_before"])
                            for score, move in zip(step["candidate_scores"], moves):
                                self.assertEqual(score["q_after"],
                                                 independent_q(vertices, edges, current ^ move))
                        self.assertTrue(verify_repair_result(
                            vertices, edges, first, moves, result)["passed"])
        self.assertEqual(graph_count, 76)
        self.assertGreater(first_layer_count, graph_count)


if __name__ == "__main__":
    unittest.main()

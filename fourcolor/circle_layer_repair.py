"""Try to repair a fixed even layer by strictly decreasing odd components.

This research module is separate from the map-naming solvers. Every supplied
edge is required: plane-map callers must first remove the actual primal bridges.
Vertices, edges and layers use the same integer-ID contract as circle_layers.

Let T be the odd-degree vertices of the full required graph. For an even layer
A, q(A) counts components of (V, A) containing an odd number of vertices of T,
including isolated vertices. The fixed-layer completion criterion is q(A) = 0.
The potential q is always even, so strict descent takes at most q(A0) / 2 steps.

Each supplied move is an even edge subset, not necessarily a simple cycle.
Replacing A by its symmetric difference with a move preserves even degrees.
Only strict q decreases are accepted. A stalled result certifies failure of
this move family and this descent rule at the reported state; it does not
certify that another even layer, another route, or four colors are impossible.
"""

from .circle_layers import (
    _boundary, _edge_ids, _first_adjacency, _forest, _prepare, _require,
    complete_second_layer, verify_second_layer_certificate,
)


def _prepare_repair(vertices, edges, first_layer, moves, edge_costs):
    """Share the established multigraph validation, then validate moves/costs.

    Integer costs deliberately avoid floating-point ties and rounding claims.
    A cost is paid for every edge flip; an edge flipped twice is paid twice.
    """
    vertices, edges, first = _prepare(vertices, edges, first_layer)
    try:
        supplied_moves = tuple(moves)
    except TypeError as exc:
        raise ValueError("moves must be an iterable of edge-index collections") from exc
    normalized_moves = []
    for position, supplied in enumerate(supplied_moves):
        chosen = _edge_ids(supplied, len(edges), "move " + str(position))
        _require(bool(chosen), "moves must be nonempty")
        _require(not any(_boundary(vertices, edges, chosen).values()),
                 "each move must have even degree at every vertex")
        _require(chosen not in normalized_moves, "duplicate moves")
        normalized_moves.append(chosen)
    if edge_costs is None:
        costs = (1,) * len(edges)
    else:
        try:
            costs = tuple(edge_costs)
        except TypeError as exc:
            raise ValueError("edge_costs must be an iterable") from exc
        _require(len(costs) == len(edges), "edge_costs length must equal edge count")
        _require(all(type(cost) is int and cost >= 0 for cost in costs),
                 "edge_costs must contain nonnegative integers, not booleans")
    return vertices, edges, first, tuple(normalized_moves), costs


def _obstructed_components(vertices, edges, first, odd_vertices):
    """Return whole A components with odd T cardinality, preserving isolates."""
    components, _, _, _ = _forest(vertices, _first_adjacency(vertices, edges, first))
    return [list(component) for component in components
            if sum(vertex in odd_vertices for vertex in component) % 2]


def _candidate_scores(vertices, edges, first, moves, costs, odd_vertices, current_q):
    """Evaluate every candidate at the same current state, in supplied order."""
    result = []
    for position, move in enumerate(moves):
        changed = first ^ move
        next_q = len(_obstructed_components(vertices, edges, changed, odd_vertices))
        result.append({
            "candidate_index": position,
            "edge_ids": sorted(move),
            "q_after": next_q,
            "flip_cost": sum(costs[index] for index in move),
            "flip_count": len(move),
            "strictly_improves": next_q < current_q,
        })
    return result


def _priority(score):
    """Use exact integer costs and edge IDs to break every selection tie."""
    return (score["q_after"], score["flip_cost"], score["flip_count"],
            tuple(score["edge_ids"]), score["candidate_index"])


def repair_first_layer(vertices, edges, first_layer, moves, edge_costs=None):
    """Try deterministic strict-descent repair and return a checkable trace.

    ``moves`` contains distinct, nonempty even edge subsets. An empty move
    family is allowed. ``edge_costs`` optionally assigns a nonnegative integer
    to every edge, with one per edge by default. At each step, accepted moves
    minimize (q_after, cost, edge count, sorted edge IDs, candidate position).
    This is a greedy rule, without a general global-optimality guarantee.

    A completed result includes the original second-layer certificate. A
    stalled result includes scores for every terminal candidate. Cumulative
    flips/cost count repeated changes; final changes/cost measure A0 XOR Afinal.
    """
    vertices, edges, initial, moves, costs = _prepare_repair(
        vertices, edges, first_layer, moves, edge_costs)
    odd_vertices = frozenset(vertex for vertex, parity in
                            _boundary(vertices, edges, range(len(edges))).items() if parity)
    initial_components = _obstructed_components(vertices, edges, initial, odd_vertices)
    initial_q = len(initial_components)
    current, current_q, steps = initial, initial_q, []
    terminal_scores = []

    while current_q:
        scores = _candidate_scores(vertices, edges, current, moves, costs,
                                   odd_vertices, current_q)
        improving = [score for score in scores if score["strictly_improves"]]
        if not improving:
            terminal_scores = scores
            break
        selected = min(improving, key=_priority)
        next_first = current ^ moves[selected["candidate_index"]]
        steps.append({
            "step": len(steps) + 1,
            "first_layer_before": sorted(current),
            "first_layer_after": sorted(next_first),
            "q_before": current_q,
            "q_after": selected["q_after"],
            "candidate_scores": scores,
            "selected_candidate_index": selected["candidate_index"],
        })
        current, current_q = next_first, selected["q_after"]

    changed = initial ^ current
    selected_scores = [step["candidate_scores"][step["selected_candidate_index"]]
                       for step in steps]
    result = {
        "status": "completed" if current_q == 0 else "stalled",
        "initial_first_layer": sorted(initial),
        "final_first_layer": sorted(current),
        "candidate_moves": [sorted(move) for move in moves],
        "edge_costs": list(costs),
        "odd_degree_vertices": sorted(odd_vertices),
        "initial_obstruction_count": initial_q,
        "final_obstruction_count": current_q,
        "initial_obstructed_components": initial_components,
        "final_obstructed_components": _obstructed_components(
            vertices, edges, current, odd_vertices),
        "steps": steps,
        "step_count": len(steps),
        "strict_descent_step_bound": initial_q // 2,
        "total_edge_flip_count": sum(score["flip_count"] for score in selected_scores),
        "cumulative_flip_cost": sum(score["flip_cost"] for score in selected_scores),
        "final_changed_edges": sorted(changed),
        "final_edge_change_count": len(changed),
        "final_changed_cost": sum(costs[index] for index in changed),
        "terminal_candidate_scores": terminal_scores,
        "completion": complete_second_layer(vertices, edges, current) if current_q == 0 else None,
    }
    verify_repair_result(vertices, edges, initial, moves, result, edge_costs=costs)
    return result


def _same(actual, expected, label):
    """Compare JSON-shaped records strictly, so False cannot forge integer zero."""
    _require(type(actual) is type(expected), label + " has incorrect type")
    if isinstance(expected, dict):
        _require(set(actual) == set(expected), label + " has incorrect fields")
        for key in expected:
            _same(actual[key], expected[key], label + "." + key)
    elif isinstance(expected, list):
        _require(len(actual) == len(expected), label + " has incorrect length")
        for position, (left, right) in enumerate(zip(actual, expected)):
            _same(left, right, label + "[" + str(position) + "]")
    else:
        _require(actual == expected, label + " differs")


def verify_repair_result(vertices, edges, first_layer, moves, result, edge_costs=None):
    """Audit reported transitions and certificates without rerunning the search.

    The verifier recomputes all local candidate scores at each reported state,
    checks the selected deterministic minimum, checks evenness and strict
    descent, and checks the terminal claim. It accepts any valid completion
    certificate rather than requiring the producer's particular spanning tree.
    """
    vertices, edges, initial, moves, costs = _prepare_repair(
        vertices, edges, first_layer, moves, edge_costs)
    _require(type(result) is dict, "repair result must be a dictionary")
    odd_vertices = frozenset(vertex for vertex, parity in
                            _boundary(vertices, edges, range(len(edges))).items() if parity)
    initial_components = _obstructed_components(vertices, edges, initial, odd_vertices)
    initial_q = len(initial_components)
    _require(initial_q % 2 == 0, "odd-component count must be even")
    steps = result.get("steps")
    _require(type(steps) is list, "steps must be a list")
    current, current_q = initial, initial_q
    cumulative_count = cumulative_cost = 0

    for position, step in enumerate(steps):
        _require(current_q > 0, "steps continue after completion")
        _require(type(step) is dict, "step must be a dictionary")
        scores = _candidate_scores(vertices, edges, current, moves, costs,
                                   odd_vertices, current_q)
        improving = [score for score in scores if score["strictly_improves"]]
        _require(bool(improving), "reported step has no strictly improving move")
        selected = min(improving, key=_priority)
        next_first = current ^ moves[selected["candidate_index"]]
        _same(step, {
            "step": position + 1,
            "first_layer_before": sorted(current),
            "first_layer_after": sorted(next_first),
            "q_before": current_q,
            "q_after": selected["q_after"],
            "candidate_scores": scores,
            "selected_candidate_index": selected["candidate_index"],
        }, "step " + str(position + 1))
        _require(not any(_boundary(vertices, edges, next_first).values()),
                 "reported first layer is not even")
        _require(selected["q_after"] % 2 == 0 and selected["q_after"] <= current_q - 2,
                 "strict descent must reduce the even potential by at least two")
        cumulative_count += selected["flip_count"]
        cumulative_cost += selected["flip_cost"]
        current, current_q = next_first, selected["q_after"]

    terminal_scores = []
    if current_q:
        terminal_scores = _candidate_scores(vertices, edges, current, moves, costs,
                                            odd_vertices, current_q)
        _require(not any(score["strictly_improves"] for score in terminal_scores),
                 "stalled claim omits an improving move")
        _require(result.get("completion") is None, "stalled result cannot have completion")
    else:
        completion = result.get("completion")
        _require(type(completion) is dict and completion.get("status") == "completed",
                 "completed repair requires a completed second-layer certificate")
        verify_second_layer_certificate(vertices, edges, current, completion)

    changed = initial ^ current
    # Completion is checked mathematically above, independently of tree choice.
    # All other fields have one canonical representation for audit and replay.
    expected = {
        "status": "completed" if current_q == 0 else "stalled",
        "initial_first_layer": sorted(initial),
        "final_first_layer": sorted(current),
        "candidate_moves": [sorted(move) for move in moves],
        "edge_costs": list(costs),
        "odd_degree_vertices": sorted(odd_vertices),
        "initial_obstruction_count": initial_q,
        "final_obstruction_count": current_q,
        "initial_obstructed_components": initial_components,
        "final_obstructed_components": _obstructed_components(
            vertices, edges, current, odd_vertices),
        "steps": steps,
        "step_count": len(steps),
        "strict_descent_step_bound": initial_q // 2,
        "total_edge_flip_count": cumulative_count,
        "cumulative_flip_cost": cumulative_cost,
        "final_changed_edges": sorted(changed),
        "final_edge_change_count": len(changed),
        "final_changed_cost": sum(costs[index] for index in changed),
        "terminal_candidate_scores": terminal_scores,
        "completion": result.get("completion"),
    }
    _same(result, expected, "repair result")
    _require(len(steps) <= initial_q // 2, "strict-descent step bound violated")
    return {
        "passed": True,
        "claim": ("two-even-layers-cover-all-provided-edges-after-strict-descent"
                  if current_q == 0 else "no-strictly-improving-supplied-move-at-final-state"),
    }

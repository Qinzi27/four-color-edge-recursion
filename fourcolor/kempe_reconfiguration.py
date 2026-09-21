"""Bounded breadth-first diagnostics for complete-component Kempe repairs.

This is explicit search in a coloring reconfiguration graph, not a new
four-color theorem or a search-free insertion rule. Vertices of the input
inequality graph are side-consistency classes. Every intermediate coloring
is proper on H; the missing daughter edge is committed only at the end.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from itertools import combinations

from .kempe_split import _copy_daughters, _copy_records
from .target_renaming import plan_target_renaming


def _inputs(edges, initial, daughters, fixed, weights, records_by_side):
    """Normalize copied inputs through the existing strict graph validator."""
    baseline = plan_target_renaming(edges, initial, initial, fixed=fixed, weights=weights)
    vertices = baseline.vertices
    children = _copy_daughters(daughters, vertices)
    before = dict(zip(vertices, baseline.initial_symbols))
    if before[children[0]] != before[children[1]]:
        raise ValueError("daughters must initially have the same color")
    if any(set(edge) == set(children) for edge in baseline.base_edges):
        raise ValueError("the pending daughter edge must be absent from edges")
    return {
        "vertices": vertices, "initial": before, "base_edges": baseline.base_edges,
        "daughters": children, "fixed": baseline.fixed_ids,
        "weights": dict(zip(vertices, baseline.weights)),
        "records_by_side": _copy_records(records_by_side, vertices),
    }


def _component_moves(adjacency, state, fixed_indices):
    """Yield all six pairs' full components, including preparatory moves."""
    for pair in combinations(range(4), 2):
        remaining = {index for index, color in enumerate(state) if color in pair}
        while remaining:
            start = min(remaining)
            remaining.remove(start)
            reached, pending = {start}, [start]
            while pending:
                current = pending.pop()
                for neighbor in adjacency[current]:
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        reached.add(neighbor)
                        pending.append(neighbor)
            if reached.intersection(fixed_indices):
                continue
            component = tuple(sorted(reached))
            after = tuple(pair[0] ^ pair[1] ^ color if index in reached else color
                          for index, color in enumerate(state))
            yield pair, component, after


def _costs(component, weights, records):
    """Count record writes as a per-step union, retaining repeated later writes."""
    changed_records = (None if records is None else tuple(dict.fromkeys(
        record for vertex in component for record in records[vertex])))
    return {
        "changed_weight": sum(weights[vertex] for vertex in component),
        "changed_side_count": len(component),
        "changed_record_ids": changed_records,
        "changed_record_count": None if changed_records is None else len(changed_records),
    }


def _witness(inputs, target, nodes):
    """Reconstruct the selected predecessor chain and its endpoint net costs."""
    vertices = inputs["vertices"]
    initial = tuple(inputs["initial"].values())
    current, steps = target, []
    while current != initial:
        node = nodes[current]
        parent = node["parent"]
        pair, indices = node["move"]
        component = tuple(vertices[index] for index in indices)
        steps.append({
            "pair": pair, "component": component,
            "before": dict(zip(vertices, parent)), "after": dict(zip(vertices, current)),
            **_costs(component, inputs["weights"], inputs["records_by_side"]),
        })
        current = parent
    steps.reverse()
    changed = tuple(vertex for vertex, old, new in zip(vertices, initial, target) if old != new)
    net = _costs(changed, inputs["weights"], inputs["records_by_side"])
    return {
        "steps": steps, "target": dict(zip(vertices, target)),
        "cumulative_changed_weight": sum(step["changed_weight"] for step in steps),
        "cumulative_changed_side_count": sum(step["changed_side_count"] for step in steps),
        "cumulative_changed_record_count": (None if inputs["records_by_side"] is None else
                                             sum(step["changed_record_count"] for step in steps)),
        "net_changed_weight": net["changed_weight"],
        "net_changed_side_count": net["changed_side_count"],
        "net_changed_record_ids": net["changed_record_ids"],
        "net_changed_record_count": net["changed_record_count"],
    }


def search_kempe_repairs(
    edges: Iterable[tuple[str, str]], initial: Mapping[str, int], daughters: Iterable[str], *,
    fixed: Iterable[str] = (), weights: Mapping[str, int] | None = None,
    records_by_side: Mapping[str, Iterable[str]] | None = None,
    max_states: int = 50000, max_depth: int = 6,
) -> dict:
    """Find a shortest repair, minimizing additive costs only at that depth.

    All complete two-color components avoiding fixed sides are allowed,
    including components touching neither or both daughters. BFS completes
    the entire first successful layer. Within that layer it minimizes the
    sum of per-step record-union sizes, then cumulative changed weight, then
    the lexicographic sequence of (color pair, input-index component). If
    records are omitted, their counts remain None and weight breaks ties.
    This is not endpoint-cost minimization or unrestricted cheapest-path
    search. Intermediate atomic swaps preserve H, not the pending edge.

    max_states includes the initial state and every discovered state. A
    truncated layer or depth limit yields unknown with no selected witness;
    only exhausting the reachable component can yield unreachable. Hence
    even a feasible target discovered in a truncated layer is not reported
    as an optimized repair. Search can take exponential time and space.
    """
    if type(max_states) is not int or max_states < 1:
        raise ValueError("max_states must be a positive integer, excluding bools")
    if type(max_depth) is not int or max_depth < 0:
        raise ValueError("max_depth must be a nonnegative integer, excluding bools")
    inputs = _inputs(edges, initial, daughters, fixed, weights, records_by_side)
    vertices = inputs["vertices"]
    positions = {vertex: index for index, vertex in enumerate(vertices)}
    children = tuple(positions[vertex] for vertex in inputs["daughters"])
    fixed_indices = {positions[vertex] for vertex in inputs["fixed"]}
    adjacency = [set() for _ in vertices]
    for left, right in inputs["base_edges"]:
        adjacency[positions[left]].add(positions[right])
        adjacency[positions[right]].add(positions[left])
    start = tuple(inputs["initial"].values())
    # Each completed BFS layer fixes the cheapest path to every state in it.
    # An optimal path to a new layer cannot use a nonoptimal prefix: the
    # transition availability depends only on the complete current coloring.
    nodes = {start: {"depth": 0, "cost": (0, 0, ()), "parent": None, "move": None}}
    frontier = [start]
    result = {
        **inputs, "status": "unknown", "stop_reason": "depth_limit",
        "selected": None, "shortest_steps": None, "shortest_steps_certified": False,
        "cost_optimal_within_shortest": False, "target_layer_candidate_count": 0,
        "visited_states": 1, "max_states": max_states, "max_depth": max_depth,
        "optimality_scope": "shortest_steps_then_cumulative_record_writes_then_cumulative_weight",
        "layers": [{"depth": 0, "state_count": 1, "target_count": 0,
                    "generation_complete": True, "expanded_states": 0,
                    "expansion_complete": False}],
    }
    cost_cache = {}
    for depth in range(1, max_depth + 1):
        next_frontier, targets = [], []
        next_layer = {"depth": depth, "state_count": 0, "target_count": 0,
                      "generation_complete": False, "expanded_states": 0,
                      "expansion_complete": False}
        previous_layer = result["layers"][-1]
        for before in frontier:
            for pair, component, after in _component_moves(adjacency, before, fixed_indices):
                known = nodes.get(after)
                if known is not None and known["depth"] < depth:
                    continue
                if known is None and len(nodes) >= max_states:
                    result["layers"].append(next_layer)
                    result.update(stop_reason="state_limit", visited_states=len(nodes),
                                  target_layer_candidate_count=len(targets))
                    return result
                if component not in cost_cache:
                    named = tuple(vertices[index] for index in component)
                    measured = _costs(named, inputs["weights"], inputs["records_by_side"])
                    cost_cache[component] = (measured["changed_record_count"] or 0,
                                             measured["changed_weight"])
                record_cost, weight_cost = cost_cache[component]
                previous_cost = nodes[before]["cost"]
                cost = (previous_cost[0] + record_cost, previous_cost[1] + weight_cost,
                        previous_cost[2] + ((pair, component),))
                if known is None:
                    next_frontier.append(after)
                    next_layer["state_count"] += 1
                    if after[children[0]] != after[children[1]]:
                        targets.append(after)
                        next_layer["target_count"] += 1
                if known is None or cost < known["cost"]:
                    nodes[after] = {"depth": depth, "cost": cost,
                                    "parent": before, "move": (pair, component)}
            previous_layer["expanded_states"] += 1
        previous_layer["expansion_complete"] = True
        next_layer["generation_complete"] = True
        result["layers"].append(next_layer)
        result["visited_states"] = len(nodes)
        if targets:
            selected_state = min(targets, key=lambda state: nodes[state]["cost"])
            result.update(status="repaired", stop_reason="complete_first_target_layer",
                          selected=_witness(inputs, selected_state, nodes), shortest_steps=depth,
                          shortest_steps_certified=True, cost_optimal_within_shortest=True,
                          target_layer_candidate_count=len(targets))
            if not verify_kempe_repair(result):
                raise RuntimeError("generated Kempe witness failed independent replay")
            return result
        if not next_frontier:
            result.update(status="unreachable", stop_reason="reachable_component_exhausted")
            return result
        frontier = next_frontier
    return result


def verify_kempe_repair(result: Mapping, selected: Mapping | None = None) -> bool:
    """Independently replay a route and its costs against the reported inputs.

    This checks full components by edge-closure iteration rather than calling
    the search generator. It certifies feasibility and measured costs only;
    it does not establish the reported BFS coverage or optimality claims.
    Callers needing external provenance must also compare the input copies
    to their trusted source. JSON round trips (lists replacing tuples) work.
    """
    try:
        inputs = _inputs(result["base_edges"], result["initial"], result["daughters"],
                         result["fixed"], result["weights"], result["records_by_side"])
        witness = result["selected"] if selected is None else selected
        if not isinstance(witness, Mapping):
            return False
        vertices, edges = inputs["vertices"], inputs["base_edges"]
        current = inputs["initial"].copy()
        steps = witness["steps"]
        if not isinstance(steps, (list, tuple)) or not steps:
            return False
        totals = {"changed_weight": 0, "changed_side_count": 0, "changed_record_count": 0}

        def same_costs(actual, expected, prefix=""):
            """Reject bool-as-int and ensure exact ordered record IDs."""
            for key, value in expected.items():
                candidate = actual[prefix + key]
                if value is None:
                    if candidate is not None:
                        return False
                elif isinstance(value, tuple):
                    if not isinstance(candidate, (list, tuple)) or tuple(candidate) != value:
                        return False
                elif type(candidate) is not int or candidate != value:
                    return False
            return True

        for step in steps:
            # Explicit symbol validation prevents Python's bool/int equality
            # from letting a malformed certificate pass a dictionary compare.
            for label in ("before", "after"):
                symbols = step[label]
                if (not isinstance(symbols, Mapping) or set(symbols) != set(vertices)
                        or any(type(value) is not int or value not in range(4)
                               for value in symbols.values())):
                    return False
            if dict(step["before"]) != current:
                return False
            pair, component = step["pair"], step["component"]
            if (not isinstance(pair, (list, tuple)) or len(pair) != 2
                    or any(type(color) is not int or color not in range(4) for color in pair)
                    or pair[0] >= pair[1]):
                return False
            if (not isinstance(component, (list, tuple)) or not component
                    or any(not isinstance(vertex, str) or vertex not in current for vertex in component)
                    or len(set(component)) != len(component)
                    or tuple(component) != tuple(vertex for vertex in vertices if vertex in component)
                    or set(component).intersection(inputs["fixed"])):
                return False
            if current[component[0]] not in pair:
                return False
            reached = {component[0]}
            while True:
                enlarged = reached.copy()
                for left, right in edges:
                    if current[left] in pair and current[right] in pair:
                        if left in reached:
                            enlarged.add(right)
                        if right in reached:
                            enlarged.add(left)
                if enlarged == reached:
                    break
                reached = enlarged
            if reached != set(component):
                return False
            expected_after = {vertex: pair[0] ^ pair[1] ^ color if vertex in reached else color
                              for vertex, color in current.items()}
            if dict(step["after"]) != expected_after:
                return False
            if any(expected_after[left] == expected_after[right] for left, right in edges):
                return False
            costs = _costs(tuple(component), inputs["weights"], inputs["records_by_side"])
            if not same_costs(step, costs):
                return False
            for key in totals:
                totals[key] += costs[key] or 0
            current = expected_after
        target = witness["target"]
        if (not isinstance(target, Mapping) or set(target) != set(vertices)
                or any(type(value) is not int for value in target.values()) or target != current
                or current[inputs["daughters"][0]] == current[inputs["daughters"][1]]):
            return False
        if inputs["records_by_side"] is None:
            totals["changed_record_count"] = None
        if not same_costs(witness, totals, "cumulative_"):
            return False
        changed = tuple(vertex for vertex in vertices if current[vertex] != inputs["initial"][vertex])
        net = _costs(changed, inputs["weights"], inputs["records_by_side"])
        return same_costs(witness, net, "net_")
    except (KeyError, TypeError, ValueError, AttributeError):
        return False

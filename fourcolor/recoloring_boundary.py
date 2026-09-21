"""Exact two-daughter boundary cost tables for small recoloring problems.

For each ordered daughter-color pair, retain the minimum *endpoint* cost and
all distinct optimal change supports. This is ordinary finite constraint
enumeration, not a new coloring algorithm or a legal Kempe execution path.
Rows keep literal color labels: permuting colors without also transporting
the initial coloring and fixed constraints would change the cost problem.

The direct lower bound is elementary. If a daughter is assigned color c,
every old neighbor initially colored c must change; take the union over both
daughters to avoid double counting. A fixed member makes that row impossible.
Further interactions between old vertices may force additional changes.
Enumeration measures that gap without claiming the local bound is complete.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from itertools import product

from .target_renaming import plan_target_renaming


def recoloring_boundary_table(
    edges: Iterable[tuple[str, str]],
    initial: Mapping[str, int],
    daughters: Iterable[str],
    *,
    fixed: Iterable[str] = (),
    weights: Mapping[str, int] | None = None,
    max_nodes_per_pair: int = 200000,
    max_vertices: int = 12,
) -> dict:
    """Return 16 boundary rows, with exactness only after exhaustive search.

    ``initial`` properly colors H with colors 0..3; its distinct equally
    colored daughters are nonadjacent. Targets color H plus their pending
    edge. Default weights are zero on daughters and one elsewhere. Explicit
    weights must be complete nonnegative integer weights, including daughters.

    ``max_vertices`` is an explicit guard against accidental large experiments.
    Each off-diagonal row has its own ``max_nodes_per_pair`` budget. A node is
    an examined partial proper assignment, including its preset root. Direct
    contradictions are certified before search and cost zero search nodes.
    Search uses an explicit stack, minimum-remaining-values vertex selection,
    and edge-consistency pruning. It does NOT prune more expensive solutions,
    because ``target_count`` counts all extensions when the row is complete.

    Row statuses are ``exact`` (one or more targets, completely enumerated),
    ``infeasible`` (complete contradiction), and ``unknown`` (node cutoff).
    On unknown rows, ``minimum_cost``, ``target_count`` and optimal counts/
    supports are None. The separate ``best_found_*`` fields record only an
    incumbent and cannot be interpreted as an optimum. A returned witness
    realizes the best found cost and is independently checkable on the edges.

    Optimal supports include every changed vertex, including free daughters;
    ``optimal_old_changed_sets`` projects them onto nondaughter vertices.
    Only one deterministic witness is stored, not every optimal assignment.
    A future composition must ensure interior constraints are separated and
    shared-boundary costs are counted once; this function implements no join.
    """
    if type(max_nodes_per_pair) is not int or max_nodes_per_pair < 0:
        raise ValueError("max_nodes_per_pair must be a nonnegative integer")
    if type(max_vertices) is not int or max_vertices < 2:
        raise ValueError("max_vertices must be an integer at least two")
    normalized = plan_target_renaming(edges, initial, initial, fixed=fixed, weights=weights)
    names = normalized.vertices
    before = normalized.initial_symbols
    positions = {name: index for index, name in enumerate(names)}
    if len(names) > max_vertices:
        raise ValueError("input exceeds the declared max_vertices guard")
    if isinstance(daughters, (str, bytes)):
        raise ValueError("daughters must contain two distinct known vertex IDs")
    try:
        children = tuple(daughters)
    except TypeError as error:
        raise ValueError("daughters must contain two distinct known vertex IDs") from error
    if (len(children) != 2 or any(not isinstance(v, str) or v not in positions for v in children)
            or children[0] == children[1]):
        raise ValueError("daughters must contain two distinct known vertex IDs")
    child_indices = tuple(positions[v] for v in children)
    if before[child_indices[0]] != before[child_indices[1]]:
        raise ValueError("daughters must initially have the same color")
    if any(set(edge) == set(children) for edge in normalized.base_edges):
        raise ValueError("the pending daughter edge must be absent from edges")
    child_set = frozenset(child_indices)
    fixed_indices = frozenset(positions[v] for v in normalized.fixed_ids)
    costs = (tuple(int(i not in child_set) for i in range(len(names)))
             if weights is None else normalized.weights)
    indexed_edges = tuple((positions[u], positions[v]) for u, v in normalized.base_edges)
    adjacency = [set() for _ in names]
    for u, v in indexed_edges + (child_indices,):
        adjacency[u].add(v)
        adjacency[v].add(u)

    rows = []
    for colors in product(range(4), repeat=2):
        # These reasons can be checked without trusting any search state.
        reasons = []
        forced = set()
        for child, color in zip(child_indices, colors):
            for neighbor in sorted(adjacency[child] - child_set):
                if before[neighbor] == color:
                    forced.add(neighbor)
                    reasons.append({"daughter": names[child], "target_color": color,
                                    "neighbor": names[neighbor], "initial_color": before[neighbor]})
        boundary_changed = {child for child, color in zip(child_indices, colors)
                            if before[child] != color}
        direct_bound = sum(costs[i] for i in forced | boundary_changed)
        contradictions = []
        if colors[0] == colors[1]:
            contradictions.append({"kind": "pending_edge_equal_colors", "vertices": children})
        for child, color in zip(child_indices, colors):
            if child in fixed_indices and before[child] != color:
                contradictions.append({"kind": "fixed_daughter", "vertex": names[child],
                                       "initial_color": before[child], "target_color": color})
        for vertex in sorted(forced & fixed_indices):
            contradictions.append({"kind": "fixed_neighbor", "vertex": names[vertex]})

        nodes = target_count = best_count = 0
        best_cost = None
        witness = None
        supports = set()
        complete = True
        if not contradictions:
            preset = [-1] * len(names)
            for i in fixed_indices:
                preset[i] = before[i]
            for i, color in zip(child_indices, colors):
                preset[i] = color
            stack = [tuple(preset)]
            while stack:
                if nodes >= max_nodes_per_pair:
                    complete = False
                    break
                current = stack.pop()
                nodes += 1
                domains = []
                for vertex, color in enumerate(current):
                    if color == -1:
                        banned = {current[neighbor] for neighbor in adjacency[vertex]
                                  if current[neighbor] != -1}
                        available = tuple(c for c in range(4) if c not in banned)
                        domains.append((len(available), -len(adjacency[vertex]), vertex, available))
                if not domains:
                    target_count += 1
                    support = tuple(i for i in range(len(names)) if current[i] != before[i])
                    cost = sum(costs[i] for i in support)
                    if best_cost is None or cost < best_cost:
                        best_cost, best_count, supports = cost, 1, {support}
                        witness = current
                    elif cost == best_cost:
                        best_count += 1
                        supports.add(support)
                        witness = min(witness, current)
                    continue
                _, _, vertex, available = min(domains)
                # Lower immediate cost is only a visitation heuristic. Every
                # legal color is retained, preserving exact extension counts.
                ordered = sorted(available, key=lambda c: (costs[vertex] * (c != before[vertex]), c))
                for color in reversed(ordered):
                    updated = list(current)
                    updated[vertex] = color
                    stack.append(tuple(updated))

        status = ("unknown" if not complete else "exact" if target_count else "infeasible")
        rendered_supports = tuple(tuple(names[i] for i in support) for support in sorted(supports))
        old_supports = tuple(tuple(names[i] for i in support) for support in sorted(
            {tuple(i for i in support if i not in child_set) for support in supports}))
        rows.append({
            "colors": colors,
            "status": status,
            "search_exhausted": complete,
            "nodes": nodes,
            "direct_forced_changes": tuple(names[i] for i in sorted(forced)),
            "direct_forcing_reasons": tuple(reasons),
            "direct_lower_bound": direct_bound,
            "direct_contradictions": tuple(contradictions),
            "minimum_cost": best_cost if complete else None,
            "best_found_cost": best_cost,
            "witness": None if witness is None else dict(zip(names, witness)),
            "target_count": target_count if complete else None,
            "targets_seen": target_count,
            "optimal_target_count": best_count if complete else None,
            "best_found_target_count": best_count,
            "optimal_changed_sets": rendered_supports if complete else None,
            "optimal_old_changed_sets": old_supports if complete else None,
            "best_found_changed_sets": rendered_supports,
        })

    complete = all(row["search_exhausted"] for row in rows)
    minima = [row["minimum_cost"] for row in rows if row["status"] == "exact"]
    return {
        "vertices": names,
        "initial": dict(zip(names, before)),
        "base_edges": normalized.base_edges,
        "daughters": children,
        "fixed": normalized.fixed_ids,
        "weights": dict(zip(names, costs)),
        "max_vertices": max_vertices,
        "max_nodes_per_pair": max_nodes_per_pair,
        "rows": rows,
        "all_rows_complete": complete,
        "minimum_cost": min(minima) if complete and minima else None,
        "scope": "all endpoint colorings conditioned on literal ordered daughter colors",
        "path_semantics": "no claim of a legal intermediate recoloring path",
    }

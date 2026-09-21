"""Find a legal daughter-edge target within a declared net recoloring budget.

The objects are side-consistency classes of an abstract inequality graph.
This is a bounded feasibility search for a final coloring, not a search for
Kempe moves or a legal sequence of intermediate colorings. No planarity or
geometric realizability is assumed or certified here.

The elementary branching rule is complete for budget feasibility. Starting
from the initial colors, select a violated edge. Any extending proper target
must change at least one still-uncommitted endpoint to a noninitial color.
Try every such endpoint and color, committing it permanently. Along a branch
compatible with any witness target, this step preserves compatibility and
never spends more than the witness's nonnegative net-change cost. Depth is at
most the number of nonfixed vertices, including zero-weight ones. Therefore
exhaustion rules out all budget-feasible targets; a resource cutoff does not.

This standard finite search is an independent comparator for the project's
restricted single-swap rule, not a claim of a novel coloring theorem.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .target_renaming import plan_target_renaming


def find_budget_target(
    edges: Iterable[tuple[str, str]],
    initial: Mapping[str, int],
    daughters: Iterable[str],
    *,
    fixed: Iterable[str] = (),
    weights: Mapping[str, int] | None = None,
    max_changes: int = 3,
    max_nodes: int = 200000,
) -> dict:
    """Decide budget feasibility, or report an explicit node-limit unknown.

    ``initial`` must properly color H using integer colors 0..3. Its distinct
    equally colored daughters must not already be adjacent. The desired
    target properly colors H plus their pending edge and preserves ``fixed``.
    Cost is sum(weights[v] for v with target[v] != initial[v]); default weights
    are one and supplied weights must be complete nonnegative integers.
    ``max_changes`` is this weighted budget, not the number of search steps.

    Results have status ``found``, ``infeasible_budget``, or ``unknown``.
    A found target is not necessarily cheapest within the given budget.
    ``infeasible_budget`` follows only from exhaustive branching. ``unknown``
    means another distinct state remained when ``max_nodes`` was exhausted.
    A zero node limit is allowed and immediately returns unknown. ``nodes``
    counts distinct examined states, including the initial one when examined;
    ``maximum_depth`` counts the largest number of commitments examined.

    Committed vertices never return to their initial colors, so a color tuple
    uniquely determines both the commitment set and cost. Memoization by that
    tuple is sound, even when some weights are zero. An explicit DFS stack
    avoids imposing Python's recursion limit on zero-weight commitments.
    Search states may violate old edges and must not be executed as a repair
    schedule. A separate fixed-target scheduler can examine a found target.
    """
    if type(max_changes) is not int or max_changes < 0:
        raise ValueError("max_changes must be a nonnegative integer, excluding bools")
    if type(max_nodes) is not int or max_nodes < 0:
        raise ValueError("max_nodes must be a nonnegative integer, excluding bools")

    # Reuse only the existing input normalization. No Kempe candidate search
    # or scheduling result contributes to target discovery.
    baseline = plan_target_renaming(edges, initial, initial, fixed=fixed, weights=weights)
    vertices = baseline.vertices
    before = baseline.initial_symbols
    positions = {vertex: index for index, vertex in enumerate(vertices)}
    if isinstance(daughters, (str, bytes)):
        raise ValueError("daughters must contain two distinct known vertex IDs")
    try:
        children = tuple(daughters)
    except TypeError as error:
        raise ValueError("daughters must contain two distinct known vertex IDs") from error
    if (len(children) != 2
            or any(not isinstance(vertex, str) or vertex not in positions for vertex in children)
            or children[0] == children[1]):
        raise ValueError("daughters must contain two distinct known vertex IDs")
    daughter_indices = (positions[children[0]], positions[children[1]])
    if before[daughter_indices[0]] != before[daughter_indices[1]]:
        raise ValueError("daughters must initially have the same color")
    if any(set(edge) == set(children) for edge in baseline.base_edges):
        raise ValueError("the pending daughter edge must be absent from edges")

    indexed_edges = tuple((positions[left], positions[right])
                          for left, right in baseline.base_edges) + (daughter_indices,)
    adjacency = [[] for _ in vertices]
    for left, right in indexed_edges:
        adjacency[left].append(right)
        adjacency[right].append(left)
    fixed_indices = frozenset(positions[vertex] for vertex in baseline.fixed_ids)
    costs = baseline.weights

    # Each frame owns an immutable color tuple; neither caller input nor a
    # sibling search branch is mutated. State order is deterministic.
    stack = [(before, 0, 0)]
    seen: set[tuple[int, ...]] = set()
    nodes = 0
    maximum_depth = 0
    witness = None
    witness_cost = None
    status = "infeasible_budget"
    while stack:
        colors, spent, depth = stack.pop()
        if colors in seen:
            continue
        if nodes >= max_nodes:
            status = "unknown"
            break
        seen.add(colors)
        nodes += 1
        maximum_depth = max(maximum_depth, depth)
        conflict = next(((left, right) for left, right in indexed_edges
                         if colors[left] == colors[right]), None)
        if conflict is None:
            witness, witness_cost = colors, spent
            status = "found"
            break

        children_states = []
        # Lower-weight endpoints are attempted first as a heuristic only.
        # The three alternative colors are all retained for completeness.
        for vertex in sorted(conflict, key=lambda item: (costs[item], item)):
            if vertex in fixed_indices or colors[vertex] != before[vertex]:
                continue
            next_cost = spent + costs[vertex]
            if next_cost > max_changes:
                continue
            locked_colors = {colors[neighbor] for neighbor in adjacency[vertex]
                             if neighbor in fixed_indices or colors[neighbor] != before[neighbor]}
            for color in range(4):
                if color == before[vertex] or color in locked_colors:
                    continue
                updated = list(colors)
                updated[vertex] = color
                state = tuple(updated)
                if state not in seen:
                    children_states.append((state, next_cost, depth + 1))
        # Reversing push order makes DFS visit the declared ascending order.
        stack.extend(reversed(children_states))

    changed = (None if witness is None else tuple(
        vertex for index, vertex in enumerate(vertices) if witness[index] != before[index]))
    return {
        "status": status,
        "target": None if witness is None else dict(zip(vertices, witness)),
        "changed_weight": witness_cost,
        "changed_side_count": None if changed is None else len(changed),
        "changed_vertices": changed,
        "nodes": nodes,
        "maximum_depth": maximum_depth,
        "max_changes": max_changes,
        "max_nodes": max_nodes,
        "search_exhausted": status == "infeasible_budget",
        "optimality_scope": "budget_feasibility_only",
        "path_semantics": "target_only_search_states_may_violate_edges",
        "vertices": vertices,
        "initial": dict(zip(vertices, before)),
        "base_edges": baseline.base_edges,
        "daughters": children,
        "fixed": baseline.fixed_ids,
        "weights": dict(zip(vertices, costs)),
    }

"""Exact frontier-state coloring diagnostics for a specified vertex order.

This independent research module measures computation order. It is neither a
mother-line naming algorithm nor a proof of a general coloring theorem. All
global color names are retained in every active frontier state. Canonical
color patterns are counted for diagnostics only: they never merge states or
permit independent recoloring of different parts of the graph.

At a processed prefix P, its boundary consists of vertices in P with a neighbor
outside P. A state records colors on that boundary, in ascending vertex order.
When a new vertex is processed, all its already processed neighbors lie on the
previous boundary. After checking their constraints, vertices with no future
neighbors can be forgotten. Equal labeled boundary states have identical
future constraints, so keeping one full witness per state preserves existence
and permits recovery of a complete coloring without a separate search.
"""

from collections import deque


def _require(condition, message):
    """Raise reproducible input errors even when Python assertions are disabled."""
    if not condition:
        raise ValueError(message)


def _graph(n, edges):
    """Validate once, normalize undirected parallel edges, and build adjacency."""
    _require(type(n) is int and n >= 0, "n must be a nonnegative integer, not bool")
    try:
        supplied = tuple(tuple(edge) for edge in edges)
    except TypeError as exc:
        raise ValueError("edges must be an iterable of endpoint pairs") from exc
    _require(all(len(edge) == 2 for edge in supplied),
             "each edge must contain exactly two endpoints")
    _require(all(type(vertex) is int and 0 <= vertex < n
                 for edge in supplied for vertex in edge),
             "edge endpoints must be integer IDs in range(n), not bool")
    # Parallel edges impose the same inequality; a self-loop is retained as an
    # unsatisfiable inequality and will kill states when its vertex is visited.
    normalized = tuple(sorted({tuple(sorted(edge)) for edge in supplied}))
    adjacent = [set() for _ in range(n)]
    for first, second in normalized:
        adjacent[first].add(second)
        adjacent[second].add(first)
    return normalized, tuple(frozenset(neighbors) for neighbors in adjacent)


def _order(n, order):
    """A valid processing order visits every declared vertex exactly once."""
    try:
        supplied = tuple(order)
    except TypeError as exc:
        raise ValueError("order must be an iterable of vertex IDs") from exc
    _require(len(supplied) == n
             and all(type(vertex) is int and 0 <= vertex < n for vertex in supplied)
             and len(set(supplied)) == n,
             "order must be a permutation of range(n), with integer IDs only")
    return supplied


def _boundary(processed, adjacent):
    """Return the structural frontier, including no already closed vertices."""
    return tuple(vertex for vertex in sorted(processed)
                 if any(neighbor not in processed for neighbor in adjacent[vertex]))


def _canonical_colors(colors):
    """Relabel by first appearance solely to count global permutation orbits."""
    names, result = {}, []
    for color in colors:
        if color not in names:
            names[color] = len(names)
        result.append(names[color])
    return tuple(result)


def frontier_trace(n, edges, order, palette_size=4, include_states=False):
    """Run exact labeled frontier dynamic programming and return its trace.

    Vertices are ``0..n-1``; ``order`` is a permutation of these IDs. Color
    names are the fixed integers ``0..palette_size-1``, with palette sizes 1..4.
    ``one_coloring`` is a complete vertex-ID-aligned list, or None if infeasible.
    The empty graph has one empty solution. Parallel edges are deduplicated;
    a self-loop makes the instance infeasible without a special search path.

    Each row reports the boundary AFTER its vertex is processed and forgotten
    vertices are projected away. Accepted transitions are legal extensions
    BEFORE that projection is deduplicated. They are not counts of all full
    colorings, because a state stores only one internal witness. State-count
    peaks include the initial one empty state; cumulative counts sum rows only.
    If requested, ``states`` lists all retained labeled tuples in sorted order.
    """
    normalized_edges, adjacent = _graph(n, edges)
    ordered = _order(n, order)
    _require(type(palette_size) is int and 1 <= palette_size <= 4,
             "palette_size must be an integer from 1 through 4, not bool")
    _require(type(include_states) is bool, "include_states must be bool")

    # A -1 sentinel marks vertices not yet processed in the internal witness.
    # Boundary keys contain only actual color names, never this sentinel.
    states = {(): (-1,) * n}
    processed, previous_boundary, rows = set(), (), []
    peak_labeled = peak_orbits = 1
    for step_number, vertex in enumerate(ordered, 1):
        next_processed = processed | {vertex}
        next_boundary = _boundary(next_processed, adjacent)
        previous_positions = {item: position for position, item in enumerate(previous_boundary)}
        old_neighbors = sorted(adjacent[vertex] & processed)
        has_self_loop = vertex in adjacent[vertex]
        # This assertion checks the structural reason forgetting is safe. It
        # never depends on a color assignment or freezes an interior choice.
        _require(all(neighbor in previous_positions for neighbor in old_neighbors),
                 "internal frontier omitted an old neighbor of the new vertex")
        attempted = len(states) * palette_size
        accepted = 0
        next_states = {}
        for state in sorted(states):
            old_colors = dict(zip(previous_boundary, state))
            for color in range(palette_size):
                if has_self_loop or any(old_colors[neighbor] == color for neighbor in old_neighbors):
                    continue
                accepted += 1
                current_colors = {**old_colors, vertex: color}
                projected = tuple(current_colors[item] for item in next_boundary)
                if projected not in next_states:
                    witness = list(states[state])
                    witness[vertex] = color
                    next_states[projected] = tuple(witness)
        states = next_states
        orbit_count = len({_canonical_colors(state) for state in states})
        row = {
            "step": step_number,
            "vertex": vertex,
            "boundary": list(next_boundary),
            "width": len(next_boundary),
            "labeled_states": len(states),
            "orbit_states": orbit_count,
            "attempted_transitions": attempted,
            "accepted_transitions": accepted,
        }
        if include_states:
            row["states"] = [list(state) for state in sorted(states)]
        rows.append(row)
        peak_labeled = max(peak_labeled, len(states))
        peak_orbits = max(peak_orbits, orbit_count)
        processed, previous_boundary = next_processed, next_boundary

    # Every vertex has been processed, so any surviving state has empty key.
    # Its retained witness was constructed during these same DP transitions.
    coloring = list(states[()]) if states else None
    if coloring is not None:
        _require(all(0 <= color < palette_size for color in coloring),
                 "internal witness contains an unprocessed vertex")
        _require(all(coloring[first] != coloring[second] for first, second in normalized_edges),
                 "internal witness violates an edge constraint")
    return {
        "n": n,
        "edges": [list(edge) for edge in normalized_edges],
        "order": list(ordered),
        "palette_size": palette_size,
        "feasible": bool(states),
        "one_coloring": coloring,
        "rows": rows,
        "summary": {
            "peak_width": max((row["width"] for row in rows), default=0),
            "peak_labeled_states": peak_labeled,
            "peak_orbit_states": peak_orbits,
            "cumulative_labeled_states": sum(row["labeled_states"] for row in rows),
            "cumulative_orbit_states": sum(row["orbit_states"] for row in rows),
            "attempted_transitions": sum(row["attempted_transitions"] for row in rows),
            "accepted_transitions": sum(row["accepted_transitions"] for row in rows),
        },
    }


def traversal_order(n, edges, start, method="bfs"):
    """Construct deterministic BFS, DFS, or greedy frontier-width vertex order.

    The first component starts at ``start``. Other components restart at the
    smallest unprocessed ID. For an empty graph, start must be None. BFS and
    recursive-preorder-equivalent DFS visit neighbors in ascending ID order.
    ``min_frontier`` chooses among unprocessed neighbors of the entire visited
    region, minimizing the boundary width after addition and then vertex ID.
    It is a local heuristic, not a minimum-pathwidth algorithm or a coloring.
    """
    _, adjacent = _graph(n, edges)
    _require(type(method) is str and method in {"bfs", "dfs", "min_frontier"},
             "method must be bfs, dfs, or min_frontier")
    if n == 0:
        _require(start is None, "start must be None for an empty graph")
        return []
    _require(type(start) is int and 0 <= start < n,
             "start must be an integer vertex ID in range(n), not bool")
    ordered, seen = [], set()

    if method == "min_frontier":
        current = start
        while len(seen) < n:
            seen.add(current)
            ordered.append(current)
            if len(seen) == n:
                break
            candidates = set().union(*(adjacent[vertex] for vertex in seen)) - seen
            if candidates:
                current = min(candidates, key=lambda vertex:
                              (len(_boundary(seen | {vertex}, adjacent)), vertex))
            else:
                current = min(set(range(n)) - seen)
        return ordered

    # Both traversal methods finish the current component before restarting.
    # The explicit DFS iterator stack gives the same order as recursive DFS
    # while avoiding Python recursion limits for longer diagnostic graphs.
    current = start
    while len(seen) < n:
        seen.add(current)
        ordered.append(current)
        if method == "bfs":
            queue = deque([current])
            while queue:
                vertex = queue.popleft()
                for neighbor in sorted(adjacent[vertex]):
                    if neighbor not in seen:
                        seen.add(neighbor)
                        ordered.append(neighbor)
                        queue.append(neighbor)
        else:
            stack = [(current, iter(sorted(adjacent[current])))]
            while stack:
                _, neighbors = stack[-1]
                neighbor = next(neighbors, None)
                if neighbor is None:
                    stack.pop()
                elif neighbor not in seen:
                    seen.add(neighbor)
                    ordered.append(neighbor)
                    stack.append((neighbor, iter(sorted(adjacent[neighbor]))))
        if len(seen) < n:
            current = min(set(range(n)) - seen)
    return ordered

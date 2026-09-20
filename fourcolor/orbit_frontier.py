"""Exact coloring frontier DP modulo one global color-name permutation.

This independent optimization stores one restricted-growth pattern for each
orbit of boundary colorings, instead of every globally named coloring. It is
the standard color-symmetry quotient, not a new coloring theorem or a change
to the project's original line-side naming algorithm. The entire graph and a
processing order are inputs; there is no hidden coloring oracle or fallback.

The quotient is exact for ordinary graph coloring with an unrestricted
palette. With r distinct colors on the current boundary, a new vertex has r
existing color classes and, if r < q, one new class to try. All absent color
names are interchangeable under permutations that fix the boundary. A color
may still occur on forgotten vertices: these vertices have no future edge,
so its reuse does not add an untested constraint.

After forgetting vertices, boundary patterns are canonicalized in ascending
vertex order. The same permutation is applied to the *entire* retained
partial coloring, including forgotten vertices. This is essential for a
consistent final witness. Precolored vertices, color lists, color-dependent
costs and separately renamed pieces are outside this module's contract.
"""

from .frontier_order import _boundary, _graph, _order, _require


def _canonical_projection(colors, palette_size):
    """Return a restricted-growth pattern and an extending palette permutation.

    Boundary names are assigned in order of first appearance. Remaining old
    names receive the remaining new names in numerical order, so the mapping
    is a bijection of the full palette even when colors occur only inside.
    """
    mapping = {}
    pattern = []
    for color in colors:
        if color not in mapping:
            mapping[color] = len(mapping)
        pattern.append(mapping[color])
    for old_color in range(palette_size):
        if old_color not in mapping:
            mapping[old_color] = len(mapping)
    return tuple(pattern), tuple(mapping[color] for color in range(palette_size))


def orbit_frontier_trace(n, edges, order, palette_size=4, include_states=False):
    """Color exactly while retaining one witness per boundary-color orbit.

    Inputs and loop/parallel-edge handling match ``frontier_trace``. Vertices
    are ``0..n-1``; ``order`` is a permutation; the palette size is 1 through
    4. The returned ``one_coloring`` follows vertex ID order, or is None when
    infeasible. Colors have no permanent individual meanings.

    Each row describes the boundary after processing and projection, with
    ``orbit_states``, ``attempted_transitions`` and ``accepted_transitions``.
    Attempts count the r existing boundary classes plus at most one new
    class for each previous state. Accepted transitions precede projection
    and deduplication. Neither counter counts complete colorings. Optional
    ``states`` contains the sorted restricted-growth patterns themselves.

    ``summary.peak_states`` includes the initial empty state; cumulative
    state counts include rows only. Transition counts omit the cost of
    canonicalization and full-witness permutation, so they alone establish
    neither wall-clock acceleration nor a running-time complexity bound.
    """
    normalized_edges, adjacent = _graph(n, edges)
    ordered = _order(n, order)
    _require(type(palette_size) is int and 1 <= palette_size <= 4,
             "palette_size must be an integer from 1 through 4, not bool")
    _require(type(include_states) is bool, "include_states must be bool")

    # A -1 witness entry is an unprocessed vertex, never a color class.
    states = {(): (-1,) * n}
    processed, previous_boundary, rows = set(), (), []
    peak_states = 1
    for step_number, vertex in enumerate(ordered, 1):
        next_processed = processed | {vertex}
        next_boundary = _boundary(next_processed, adjacent)
        old_neighbors = adjacent[vertex] & processed
        has_self_loop = vertex in adjacent[vertex]
        _require(old_neighbors <= set(previous_boundary),
                 "internal frontier omitted an old neighbor of the new vertex")
        attempted = accepted = 0
        next_states = {}
        for state in sorted(states):
            old_colors = dict(zip(previous_boundary, state))
            # Restricted-growth keys use every name from 0 to r-1. Name r
            # represents all absent names, even if forgotten vertices use it.
            distinct_colors = len(set(state))
            candidate_count = distinct_colors + (distinct_colors < palette_size)
            attempted += candidate_count
            for color in range(candidate_count):
                if has_self_loop or any(old_colors[neighbor] == color
                                        for neighbor in old_neighbors):
                    continue
                accepted += 1
                current_colors = {**old_colors, vertex: color}
                projected = tuple(current_colors[item] for item in next_boundary)
                canonical, permutation = _canonical_projection(projected, palette_size)
                if canonical not in next_states:
                    witness = list(states[state])
                    witness[vertex] = color
                    # Renaming only the new boundary would corrupt edges to
                    # forgotten vertices; one global bijection preserves them.
                    next_states[canonical] = tuple(
                        permutation[item] if item >= 0 else -1 for item in witness)
        states = next_states
        row = {
            "step": step_number,
            "vertex": vertex,
            "boundary": list(next_boundary),
            "width": len(next_boundary),
            "orbit_states": len(states),
            "attempted_transitions": attempted,
            "accepted_transitions": accepted,
        }
        if include_states:
            row["states"] = [list(state) for state in sorted(states)]
        rows.append(row)
        peak_states = max(peak_states, len(states))
        processed, previous_boundary = next_processed, next_boundary

    coloring = list(states[()]) if states else None
    if coloring is not None:
        _require(all(0 <= color < palette_size for color in coloring),
                 "internal witness contains an unprocessed vertex")
        _require(all(coloring[first] != coloring[second]
                     for first, second in normalized_edges),
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
            "peak_states": peak_states,
            "cumulative_states": sum(row["orbit_states"] for row in rows),
            "attempted_transitions": sum(row["attempted_transitions"] for row in rows),
            "accepted_transitions": sum(row["accepted_transitions"] for row in rows),
        },
    }

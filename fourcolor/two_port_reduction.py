"""Exact elimination through at most two color-variable interfaces.

This module is an ordinary constraint-graph solver for a complete, fixed
input. A two-terminal relation records whether equal and/or different colors
extend through the removed interior. EQ=1 and DIFF=2 are relation bits, not
individual color names. With one available color the universe is EQ only.

Only vertices of degree at most two in the CURRENT nonuniversal constraint
graph are eliminated. Existential composition replaces their incident
relations, and intersection preserves any pre-existing terminal constraint.
Fill relations are logical constraints, not new geometric edges of a map.
This is standard binary constraint elimination, not a new coloring theorem
or a decomposition of every subgraph with a two-vertex separator.

The residual core is part of the specified algorithm: contract equality
relations and solve its inequality graph with the existing exact orbit
frontier algorithm. It is not a solver selected after a heuristic fails.
Precolors, lists, color costs, and unknown future edges are outside scope.
"""

from heapq import heappop, heappush

from .frontier_order import _graph, _order, _require
from .orbit_frontier import orbit_frontier_trace


EQ = 1
DIFF = 2


def _palette(palette_size):
    """Validate the ordinary, unlabeled palette and return its relation mask."""
    _require(type(palette_size) is int and 1 <= palette_size <= 4,
             "palette_size must be an integer from 1 through 4, not bool")
    return EQ if palette_size == 1 else EQ | DIFF


def _allows(mask, first, second):
    """Evaluate a relation on concrete color names during witness assembly."""
    return bool(mask & (EQ if first == second else DIFF))


def compose_relations(palette_size, left_mask, right_mask):
    """Return ``exists x: left(a,x) and right(x,b)`` as an EQ/DIFF mask.

    The two possible terminal color patterns have representatives (0,0)
    and (0,1). Color-permutation invariance makes these representatives
    sufficient; the latter is unavailable when q=1. Masks must be integers
    in 0..3. In particular, DIFF with q=1 denotes the empty relation.
    """
    universe = _palette(palette_size)
    _require(all(type(mask) is int and 0 <= mask <= 3
                 for mask in (left_mask, right_mask)),
             "relation masks must be integers from 0 through 3, not bool")
    left_mask &= universe
    right_mask &= universe
    result = 0
    for terminal, bit in ((0, EQ), (1, DIFF)):
        if not (universe & bit):
            continue
        if any(_allows(left_mask, 0, middle)
               and _allows(right_mask, middle, terminal)
               for middle in range(palette_size)):
            result |= bit
    return result


def two_port_trace(n, edges, order, palette_size=4):
    """Solve exactly with degree-0/1/2 elimination and an explicit core DP.

    Inputs follow ``orbit_frontier_trace``: vertices are ``range(n)``, order
    is a permutation, and q is 1..4. Parallel inequalities are deduplicated;
    any self-loop is infeasible. Input lists are never modified. Eligible
    vertices are selected by their position in the supplied order.

    Every reduction stores the incident relations at elimination time,
    including generated relations. On success these records are traversed
    backwards, choosing an extending color for each removed vertex. The
    complete witness is checked against all original inequalities.

    ``core.classes`` lists original vertex IDs by quotient ID. Its edges
    and order use quotient IDs. ``core.constraints`` retains original core
    IDs and relation masks, before contraction. ``core.trace`` is None when
    the core is empty or infeasibility was established before its DP.

    Summary counters deliberately separate relation compositions, relation
    intersections, unary support checks, reconstruction trials and core DP
    transitions. They are not a combined cost model or a speed measurement.
    ``peak_states`` counts active core DP states only (zero without a DP),
    and does not count reductions, classes or stored reconstruction data.
    """
    normalized, _ = _graph(n, edges)
    ordered = _order(n, order)
    universe = _palette(palette_size)
    rank = {vertex: index for index, vertex in enumerate(ordered)}
    active = set(range(n))
    relations = [dict() for _ in range(n)]
    reductions = []
    compositions = intersections = unary_checks = reconstruction_attempts = 0
    heap_pops = 0
    cause = None

    # Only nonuniversal constraints are stored. For q=1 an input inequality
    # is empty, so it must be rejected rather than mistaken for a missing edge.
    for first, second in normalized:
        if first == second:
            cause = {"kind": "self_loop", "vertex": first}
            break
        mask = DIFF & universe
        if not mask:
            cause = {"kind": "empty_input_relation", "vertices": [first, second]}
            break
        relations[first][second] = relations[second][first] = mask

    pending = []
    queued = set()

    def enqueue(vertex):
        """Add newly eligible vertices once; priorities stay deterministic."""
        if vertex in active and len(relations[vertex]) <= 2 and vertex not in queued:
            heappush(pending, (rank[vertex], vertex))
            queued.add(vertex)

    if cause is None:
        for vertex in ordered:
            enqueue(vertex)
    while pending and cause is None:
        _, vertex = heappop(pending)
        heap_pops += 1
        queued.remove(vertex)
        if vertex not in active or len(relations[vertex]) > 2:
            continue
        neighbors = sorted(relations[vertex], key=rank.get)
        masks = [relations[vertex][other] for other in neighbors]
        record = {"vertex": vertex, "neighbors": neighbors, "relation_masks": masks}

        if len(neighbors) == 1:
            # All terminal names are equivalent, but nonempty support still
            # has to be established, including the q=1 boundary case.
            supported = False
            for color in range(palette_size):
                unary_checks += 1
                if _allows(masks[0], color, 0):
                    supported = True
                    break
            if not supported:
                cause = {"kind": "empty_unary_support", "vertex": vertex,
                         "neighbor": neighbors[0], "relation_mask": masks[0]}
        elif len(neighbors) == 2:
            first, second = neighbors
            composed = compose_relations(palette_size, masks[0], masks[1])
            compositions += 1
            prior = relations[first].get(second, universe)
            merged = prior & composed
            intersections += 1
            record.update({"terminal_vertices": [first, second],
                           "composed_mask": composed, "previous_mask": prior,
                           "result_mask": merged})
            if merged == universe:
                relations[first].pop(second, None)
                relations[second].pop(first, None)
            else:
                relations[first][second] = relations[second][first] = merged
            if not merged:
                cause = {"kind": "empty_terminal_intersection", "vertex": vertex,
                         "terminals": [first, second], "previous_mask": prior,
                         "composed_mask": composed}

        # Records retain the exact old neighbor constraints before deletion.
        # A contradiction record is retained too, but never reconstructed.
        reductions.append(record)
        for other in neighbors:
            del relations[other][vertex]
        relations[vertex].clear()
        active.remove(vertex)
        for other in neighbors:
            enqueue(other)

    vertices = sorted(active, key=rank.get)
    constraints = [[first, second, mask] for first in sorted(active)
                   for second, mask in sorted(relations[first].items()) if first < second]
    core = {"vertices": vertices, "constraints": constraints,
            "classes": [], "edges": [], "order": [], "trace": None}
    coloring = None

    if cause is None:
        # Equalities are genuine relations produced by elimination (for
        # instance, the ends of an even-length path in a two-color palette).
        parent = {vertex: vertex for vertex in active}

        def find(vertex):
            """Iterative path compression avoids recursion on long classes."""
            while parent[vertex] != vertex:
                parent[vertex] = parent[parent[vertex]]
                vertex = parent[vertex]
            return vertex

        for first, second, mask in constraints:
            if mask == EQ:
                left, right = find(first), find(second)
                if left != right:
                    if rank[left] > rank[right]:
                        left, right = right, left
                    parent[right] = left
        grouped = {}
        for vertex in vertices:
            grouped.setdefault(find(vertex), []).append(vertex)
        classes = sorted(grouped.values(), key=lambda members: min(rank[v] for v in members))
        quotient_id = {vertex: index for index, members in enumerate(classes) for vertex in members}
        quotient_edges = set()
        for first, second, mask in constraints:
            if mask == DIFF:
                left, right = quotient_id[first], quotient_id[second]
                if left == right:
                    cause = {"kind": "inequality_inside_equality_class",
                             "vertices": [first, second], "class": left}
                    break
                quotient_edges.add(tuple(sorted((left, right))))
        core.update({"classes": classes, "edges": [list(edge) for edge in sorted(quotient_edges)],
                     "order": list(range(len(classes)))})
        if cause is None:
            if classes:
                trace = orbit_frontier_trace(len(classes), sorted(quotient_edges),
                                             core["order"], palette_size=palette_size)
                core["trace"] = trace
                if not trace["feasible"]:
                    cause = {"kind": "infeasible_core"}
                else:
                    coloring = [-1] * n
                    for members, color in zip(classes, trace["one_coloring"]):
                        for vertex in members:
                            coloring[vertex] = color
            else:
                coloring = [-1] * n

    if coloring is not None:
        for record in reversed(reductions):
            vertex = record["vertex"]
            neighbors, masks = record["neighbors"], record["relation_masks"]
            _require(coloring[vertex] == -1, "eliminated vertex was already colored")
            _require(all(coloring[other] >= 0 for other in neighbors),
                     "reconstruction encountered an unassembled terminal")
            for color in range(palette_size):
                reconstruction_attempts += 1
                if all(_allows(mask, color, coloring[other])
                       for other, mask in zip(neighbors, masks)):
                    coloring[vertex] = color
                    break
            _require(coloring[vertex] >= 0, "reduction relation has no witness extension")
        _require(all(0 <= color < palette_size for color in coloring), "uncolored vertex")
        _require(all(coloring[first] != coloring[second] for first, second in normalized),
                 "reconstructed witness violates an original edge")

    trace_summary = core["trace"]["summary"] if core["trace"] is not None else {}
    result = {
        "n": n, "edges": [list(edge) for edge in normalized], "order": list(ordered),
        "palette_size": palette_size, "feasible": coloring is not None,
        "one_coloring": coloring, "reductions": reductions, "core": core,
        "summary": {
            "eliminated_vertices": len(reductions), "core_vertices": len(vertices),
            "core_classes": len(core["classes"]), "core_edges": len(core["edges"]),
            "peak_states": trace_summary.get("peak_states", 0),
            "peak_width": trace_summary.get("peak_width", 0),
            "attempted_transitions": trace_summary.get("attempted_transitions", 0),
            "accepted_transitions": trace_summary.get("accepted_transitions", 0),
            "relation_compositions": compositions, "relation_intersections": intersections,
            "unary_support_checks": unary_checks, "reconstruction_attempts": reconstruction_attempts,
            "heap_pops": heap_pops,
        },
    }
    if cause is not None:
        result["cause"] = cause
    return result

"""Exact ordered boundary signatures for at most three face variables.

An interface is an ordered tuple of vertices of a complete constraint graph,
not a set of primal flow ports. Ordinary colors have no individual meaning.
Consequently a signature records feasible equality partitions of the ports.
At most three ports are supported here: at most five exact queries, not an
unbounded or hidden enumeration of every coloring. Queries explicitly use
two-port reduction followed by its exact residual-core solver.

The gluing routine below accepts declared pieces whose interiors are made
disjoint and whose only shared vertices are their two ordered terminals. It
does not infer a geometric decomposition or silently drop cross-piece edges.
"""

from itertools import combinations

from .frontier_order import _graph, _order, _require
from .two_port_reduction import two_port_trace


def boundary_patterns(arity, palette_size):
    """List restricted-growth partitions, respecting the available palette."""
    _require(type(arity) is int and 0 <= arity <= 3, "arity must be an integer in 0..3")
    _require(type(palette_size) is int and 1 <= palette_size <= 4,
             "palette_size must be an integer in 1..4")
    patterns = [()]
    for _ in range(arity):
        patterns = [prefix + (value,) for prefix in patterns
                    for value in range(min(palette_size, 1 + len(set(prefix))))]
    return tuple(patterns)


def _ports(n, terminals):
    """Keep terminal order, identity and arity explicit."""
    _require(type(n) is int and n >= 0, "n must be a nonnegative integer, not bool")
    try:
        ports = tuple(terminals)
    except TypeError as error:
        raise ValueError("terminals must be an ordered iterable") from error
    _require(len(ports) <= 3 and all(type(v) is int and 0 <= v < n for v in ports)
             and len(set(ports)) == len(ports),
             "terminals must be at most three distinct vertex IDs")
    return ports


def _rename_witness(witness, terminals, pattern, palette_size):
    """Extend the required terminal map to a full palette permutation."""
    mapping = {}
    for vertex, target in zip(terminals, pattern):
        source = witness[vertex]
        _require(source not in mapping or mapping[source] == target, "inconsistent terminal equality")
        mapping[source] = target
    _require(len(set(mapping.values())) == len(mapping), "terminal map is not injective")
    remaining = iter(c for c in range(palette_size) if c not in mapping.values())
    for source in range(palette_size):
        if source not in mapping:
            mapping[source] = next(remaining)
    return [mapping[color] for color in witness]


def interface_signature(n, edges, terminals, palette_size=4, order=None):
    """Compute every feasible port partition and one full witness for each.

    Each partition query contracts terminal classes and adds inequalities
    between different classes. The synthetic graph is an oracle constraint
    representation, not a claim about new geometric map edges or planarity.
    Existence of a query coloring is equivalent to extension of that pattern.
    It is not necessary to preassign or distinguish actual color names.
    """
    normalized, _ = _graph(n, edges)
    ports = _ports(n, terminals)
    ordered = _order(n, range(n) if order is None else order)
    candidates = boundary_patterns(len(ports), palette_size)
    branches, feasible_patterns = [], []
    for pattern in candidates:
        representatives = list(range(n))
        first = {}
        for vertex, label in zip(ports, pattern):
            first.setdefault(label, vertex)
            representatives[vertex] = first[label]
        groups = {}
        for vertex, representative in enumerate(representatives):
            groups.setdefault(representative, []).append(vertex)
        classes = sorted(groups.values(), key=lambda members: min(members))
        index = {vertex: i for i, members in enumerate(classes) for vertex in members}
        query_edges = {(index[a], index[b]) for a, b in normalized}
        terminal_classes = sorted({index[v] for v in ports})
        query_edges.update(combinations(terminal_classes, 2))
        query_order = list(dict.fromkeys(index[v] for v in ordered))
        trace = two_port_trace(len(classes), sorted(query_edges), query_order, palette_size)
        witness = None
        if trace["feasible"]:
            expanded = [trace["one_coloring"][index[v]] for v in range(n)]
            witness = _rename_witness(expanded, ports, pattern, palette_size)
            _require(all(witness[a] != witness[b] for a, b in normalized), "signature witness violates edge")
            _require(tuple(witness[v] for v in ports) == pattern, "wrong terminal pattern")
            feasible_patterns.append(list(pattern))
        branches.append({"pattern": list(pattern), "feasible": trace["feasible"],
                         "one_coloring": witness, "query_classes": classes,
                         "query_edges": [list(edge) for edge in sorted(query_edges)],
                         "query_order": query_order, "solver_summary": trace["summary"]})
    named_count = 0
    for pattern in feasible_patterns:
        multiplicity = 1
        for used in range(len(set(pattern))):
            multiplicity *= palette_size - used
        named_count += multiplicity
    return {
        "n": n, "edges": [list(edge) for edge in normalized], "terminals": list(ports),
        "palette_size": palette_size, "order": list(ordered),
        "patterns": feasible_patterns, "feasible": bool(feasible_patterns),
        "named_boundary_assignments": named_count, "queries": branches,
        "summary": {"pattern_queries": len(branches), "feasible_patterns": len(feasible_patterns)},
    }


def two_terminal_signature(n, edges, terminals, palette_size=4, order=None):
    """Return the exact EMPTY/EQ/DIFF/ALL mask as well as its witnesses."""
    ports = _ports(n, terminals)
    _require(len(ports) == 2, "exactly two terminals are required")
    result = interface_signature(n, edges, ports, palette_size, order)
    result["mask"] = sum(1 if pattern == [0, 0] else 2 for pattern in result["patterns"])
    return result


def glue_two_terminal_pieces(pieces, palette_size=4):
    """Glue parallel pieces using intersection, with no further coloring search.

    Each input has n, edges and two ordered terminals (optional order and
    description). The constructed graph identifies terminal 0 across pieces,
    and likewise terminal 1, while assigning unique IDs to every interior.
    No other shared identity is implied by equal LOCAL vertex IDs.
    """
    boundary_patterns(2, palette_size)
    try:
        supplied = list(pieces)
    except TypeError as error:
        raise ValueError("pieces must be an iterable of graph records") from error
    allowed = {"n", "edges", "terminals", "order", "description"}
    summaries, mappings, combined_edges = [], [], set()
    vertex_count = 2
    mask = 1 if palette_size == 1 else 3
    for piece in supplied:
        _require(isinstance(piece, dict) and {"n", "edges", "terminals"} <= set(piece)
                 and not set(piece) - allowed, "invalid piece fields or unsupported constraints")
        summary = two_terminal_signature(piece["n"], piece["edges"], piece["terminals"],
                                         palette_size, piece.get("order"))
        mapping = {summary["terminals"][0]: 0, summary["terminals"][1]: 1}
        for vertex in range(piece["n"]):
            if vertex not in mapping:
                mapping[vertex] = vertex_count
                vertex_count += 1
        combined_edges.update(tuple(sorted((mapping[a], mapping[b]))) for a, b in summary["edges"])
        mappings.append([mapping[v] for v in range(piece["n"])])
        summaries.append(summary)
        mask &= summary["mask"]
    coloring, selected = None, None
    if mask:
        selected = [0, 0] if mask & 1 else [0, 1]
        coloring = [-1] * vertex_count
        coloring[:2] = selected
        for summary, mapping in zip(summaries, mappings):
            witness = next(branch["one_coloring"] for branch in summary["queries"]
                           if branch["pattern"] == selected and branch["feasible"])
            # Each query witness already has these exact terminal names. Its
            # other vertices are disjoint, so equality on ports is sufficient.
            for local, global_id in enumerate(mapping):
                _require(coloring[global_id] in (-1, witness[local]), "piece interface mismatch")
                coloring[global_id] = witness[local]
        _require(all(0 <= c < palette_size for c in coloring), "unassigned glued vertex")
        _require(all(coloring[a] != coloring[b] for a, b in combined_edges), "invalid glued witness")
    return {
        "n": vertex_count, "edges": [list(edge) for edge in sorted(combined_edges)],
        "palette_size": palette_size, "terminals": [0, 1], "mask": mask,
        "selected_pattern": selected, "feasible": bool(mask), "one_coloring": coloring,
        "pieces": summaries, "local_to_global": mappings,
        "summary": {"pieces": len(summaries),
                    "pattern_queries": sum(s["summary"]["pattern_queries"] for s in summaries),
                    "gluing_search_calls": 0},
    }

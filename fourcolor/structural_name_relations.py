"""Prove unequal face names by conditional, geometry-only equality closure.

The input is a simple constraint graph on face identities.  It contains no
colors, old solution, mother schedule, or guessed target coloring.  Under the
temporary assumption that two faces have the same name, three pairwise
different names leave exactly one of four names for any common neighbor.
Consequently, common neighbors of a triangle must have the same name.

The algorithm records these forced identifications in a quotient graph.  A
self-loop or a five-clique refutes the initial same-name assumption.  Failure
to obtain a contradiction is only ``inconclusive``: this rule is not a complete
four-colorability test.  Derived relations are auxiliary name constraints,
never additional geometric edges or a new proof of the Four Color Theorem.
"""

from itertools import combinations


RULE = "four-name-shared-triangle-refutation-v1"


def _require(condition, message):
    """Reject invalid input even when Python runs with assertions disabled."""
    if not condition:
        raise ValueError(message)


def _validated_input(vertex_count, edges, first, second):
    """Normalize a strictly simple graph without silently accepting bad IDs.

    A primal bridge must already have been omitted when constructing the face
    constraint graph; a self-loop here cannot stand for a valid separation.
    Duplicate undirected edges are rejected so provenance has one input edge
    per constraint.  Both edge orientations and arbitrary input order work.
    """
    _require(type(vertex_count) is int and vertex_count >= 2,
             "vertex_count must be an integer of at least two")
    _require(type(first) is int and type(second) is int,
             "assumed face identities must be integers")
    _require(0 <= first < vertex_count and 0 <= second < vertex_count,
             "assumed face identity is outside the graph")
    _require(first != second, "same-name assumption requires two distinct faces")
    _require(isinstance(edges, (list, tuple)), "edges must be a list or tuple")
    normalized = set()
    for edge in edges:
        _require(isinstance(edge, (list, tuple)) and len(edge) == 2,
                 "every edge must contain two vertex identities")
        left, right = edge
        _require(type(left) is int and type(right) is int,
                 "edge identities must be integers")
        _require(0 <= left < vertex_count and 0 <= right < vertex_count,
                 "edge identity is outside the graph")
        _require(left != right, "input constraint graph must not contain self-loops")
        pair = tuple(sorted((left, right)))
        _require(pair not in normalized, "input constraint graph contains a duplicate edge")
        normalized.add(pair)
    return sorted(normalized), tuple(sorted((first, second)))


def _quotient(classes, edges):
    """Rebuild the quotient and retain a real original edge for every edge.

    Class IDs are their least original member.  Selecting the least original
    edge makes the certificate independent of the supplied edge ordering.
    No inferred inequality or artificial adjacency enters this construction.
    """
    owner = {member: representative for representative, members in classes.items()
             for member in members}
    adjacent = {representative: set() for representative in classes}
    witnesses = {}
    loop = None
    for left, right in edges:
        first, second = owner[left], owner[right]
        if first == second:
            if loop is None:
                loop = (first, (left, right))
            continue
        pair = tuple(sorted((first, second)))
        if pair not in witnesses:
            witnesses[pair] = (left, right)
        adjacent[first].add(second)
        adjacent[second].add(first)
    return adjacent, witnesses, loop


def _edge_record(first, second, classes, witnesses):
    """Expose original endpoints and the current classes supporting one edge."""
    first, second = sorted((first, second))
    return {"classes": [list(classes[first]), list(classes[second])],
            "original_edge": list(witnesses[(first, second)])}


def _triangles(adjacent):
    """Enumerate each existing quotient triangle once, in numerical order."""
    for first in sorted(adjacent):
        for second in sorted(vertex for vertex in adjacent[first] if vertex > first):
            for third in sorted((adjacent[first] & adjacent[second]) - {first, second}):
                if third > second:
                    yield (first, second, third)


def refute_same_name(vertex_count, edges, first, second):
    """Return a replayable four-name refutation or an inconclusive closure.

    ``edges`` is a list/tuple of distinct, non-loop undirected edges on the
    integer identities ``0 .. vertex_count - 1``.  No connectedness or planar
    embedding is required for this implication; the caller separately proves
    that each constraint edge comes from a real shared boundary when using it
    for a map.  The four-name palette size is fixed, not inferred from data.

    A merge records three mutually adjacent classes and two common neighbors.
    In any four-name assignment satisfying the current assumption, the latter
    neighbors must share the one name missing from the triangle.  All quotient
    edges have original input-edge witnesses.  Adjacent common neighbors form
    a five-clique instead, directly contradicting the four-name assumption.

    Every successful merge reduces the number of classes.  Thus there are at
    most ``vertex_count - 2`` forced merges after the initial assumption, and
    no recursive color search, retry, or hidden fallback is performed.  This
    termination bound is not a linear-time complexity claim.
    """
    original_edges, assumption = _validated_input(vertex_count, edges, first, second)
    classes = {vertex: [vertex] for vertex in range(vertex_count)}
    first, second = assumption
    classes[first] = [first, second]
    del classes[second]
    merges = []
    contradiction = None
    passes = triangles_examined = 0

    while True:
        passes += 1
        adjacent, witnesses, loop = _quotient(classes, original_edges)
        if loop is not None:
            representative, edge = loop
            contradiction = {"kind": "self_loop", "class": list(classes[representative]),
                             "original_edge": list(edge)}
            break

        chosen = None
        for triangle in _triangles(adjacent):
            triangles_examined += 1
            common = sorted(set.intersection(*(adjacent[vertex] for vertex in triangle)))
            if len(common) < 2:
                continue
            # Any adjacent pair gives a short contradiction without enumerating
            # five-vertex subsets.  Otherwise all common neighbors are forced
            # equal, and one deterministic pair suffices for this merge step.
            adjacent_pair = next(((left, right) for left, right in combinations(common, 2)
                                  if right in adjacent[left]), None)
            if adjacent_pair is not None:
                clique = sorted((*triangle, *adjacent_pair))
                contradiction = {
                    "kind": "five_clique", "classes": [list(classes[item]) for item in clique],
                    "edges": [_edge_record(left, right, classes, witnesses)
                              for left, right in combinations(clique, 2)],
                }
                break
            chosen = (common[0], common[1], triangle)
            break

        if contradiction is not None or chosen is None:
            break
        left, right, triangle = chosen
        merged = sorted(classes[left] + classes[right])
        merges.append({
            "first_class": list(classes[left]), "second_class": list(classes[right]),
            "triangle": [list(classes[item]) for item in triangle],
            "triangle_edges": [_edge_record(a, b, classes, witnesses)
                               for a, b in combinations(triangle, 2)],
            "spokes": [_edge_record(neighbor, vertex, classes, witnesses)
                       for neighbor in (left, right) for vertex in triangle],
            "result_class": merged,
        })
        classes[left] = merged
        del classes[right]

    return {
        "schema_version": 1, "rule": RULE, "palette_size": 4,
        "vertex_count": vertex_count, "assumed_equal": list(assumption),
        "status": "proved_different" if contradiction is not None else "inconclusive",
        "merges": merges, "contradiction": contradiction,
        "final_classes": [list(classes[vertex]) for vertex in sorted(classes)],
        "statistics": {"input_edges": len(original_edges), "passes": passes,
                       "triangles_examined": triangles_examined,
                       "forced_merges": len(merges), "final_class_count": len(classes)},
        "scope": "Four-name conditional equality closure on constraint identities; "
                 "inconclusive does not mean equal names extend. Derived inequality "
                 "is not a geometric edge or a complete four-coloring algorithm.",
    }

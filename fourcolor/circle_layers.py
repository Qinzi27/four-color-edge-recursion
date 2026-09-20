"""Complete one fixed even edge layer by a second, or certify obstruction.

This independent research module uses graph parity only. It does not search
colors or run any existing naming solver. Every supplied edge must be covered;
for a plane-map interpretation, callers first remove actual primal bridges.
The graph itself need not be planar. Loops, parallel edges, disconnected graphs
and isolated vertices are supported; a loop contributes two to vertex degree.

For an even first layer A and R = E minus A, a second layer has the form
B = R union X with X contained in A. The boundary equation is dX = dR over
GF(2). It is solvable exactly when each connected component of (V, A) has an
even number of R edges crossing its boundary. A spanning forest constructs X.
The construction does not minimize layer length or the number of cycles.
"""


def _require(condition, message):
    """Keep validation enabled under optimized Python execution."""
    if not condition:
        raise ValueError(message)


def _edge_ids(values, size, label):
    """Validate an edge-index collection before converting it to a set."""
    try:
        items = tuple(values)
    except TypeError as exc:
        raise ValueError(label + " must be an iterable of edge indices") from exc
    _require(all(type(item) is int and 0 <= item < size for item in items),
             label + " contains an invalid edge index")
    _require(len(items) == len(set(items)), label + " contains duplicate indices")
    return frozenset(items)


def _boundary(vertices, edges, indices):
    """Return degree parity; toggling both endpoints counts loops twice."""
    parity = {vertex: 0 for vertex in vertices}
    for index in indices:
        first, second = edges[index]
        parity[first] ^= 1
        parity[second] ^= 1
    return parity


def _prepare(vertices, edges, first_layer):
    """Validate an integer-labelled multigraph and its fixed even first layer."""
    try:
        vertex_items = tuple(vertices)
    except TypeError as exc:
        raise ValueError("vertices must be iterable") from exc
    _require(all(type(vertex) is int for vertex in vertex_items),
             "vertex IDs must be integers, not booleans")
    _require(len(vertex_items) == len(set(vertex_items)), "duplicate vertex IDs")
    normalized_vertices = tuple(sorted(vertex_items))
    vertex_set = set(vertex_items)
    try:
        normalized_edges = tuple(tuple(edge) for edge in edges)
    except TypeError as exc:
        raise ValueError("edges must be an iterable of endpoint pairs") from exc
    _require(all(len(edge) == 2 for edge in normalized_edges),
             "each edge must have exactly two endpoints")
    _require(all(type(vertex) is int and vertex in vertex_set
                 for edge in normalized_edges for vertex in edge),
             "edge endpoint is not a declared integer vertex")
    first = _edge_ids(first_layer, len(normalized_edges), "first_layer")
    _require(not any(_boundary(normalized_vertices, normalized_edges, first).values()),
             "first_layer must have even degree at every vertex")
    return normalized_vertices, normalized_edges, first


def _first_adjacency(vertices, edges, first):
    """Keep parallel edge IDs distinct in a deterministic adjacency listing."""
    adjacent = {vertex: [] for vertex in vertices}
    for index in sorted(first):
        a, b = edges[index]
        adjacent[a].append((b, index))
        adjacent[b].append((a, index))
    return adjacent


def _forest(vertices, adjacent):
    """Return all first-layer components and one parent forest, including isolates."""
    visited = set()
    components, order, parent, parent_edge = [], [], {}, {}
    for root in vertices:
        if root in visited:
            continue
        visited.add(root)
        parent[root] = None
        component, queue = [], [root]
        for vertex in queue:
            component.append(vertex)
            order.append(vertex)
            for neighbor, index in adjacent[vertex]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    parent[neighbor] = vertex
                    parent_edge[neighbor] = index
                    queue.append(neighbor)
        components.append(tuple(sorted(component)))
    return components, order, parent, parent_edge


def complete_second_layer(vertices, edges, first_layer):
    """Return a covering second even layer, or an independently checkable odd cut.

    ``vertices`` contains distinct integer IDs. ``edges`` is a sequence of
    endpoint pairs; its positions are the edge IDs, preserving parallel edges.
    ``first_layer`` contains distinct valid edge IDs and must be even. Every
    supplied edge is required, including loops. The result status is either
    ``completed`` or ``obstructed``. An obstruction concerns this fixed A only,
    not the existence of a different pair of layers for the same graph.
    """
    vertices, edges, first = _prepare(vertices, edges, first_layer)
    remaining = frozenset(range(len(edges))) - first
    parity = _boundary(vertices, edges, remaining)
    adjacent = _first_adjacency(vertices, edges, first)
    components, order, parent, parent_edge = _forest(vertices, adjacent)
    common = {"first_layer": sorted(first), "remaining_edges": sorted(remaining)}

    # A component has no A edge leaving it. Any covering even B would therefore
    # cross its cut on exactly these R edges, which cannot have odd cardinality.
    for component in components:
        if sum(parity[vertex] for vertex in component) % 2:
            members = set(component)
            crossing = [index for index in sorted(remaining)
                        if (edges[index][0] in members) != (edges[index][1] in members)]
            result = {"status": "obstructed", **common, "obstruction": {
                "kind": "odd-remaining-cut-of-first-layer-component",
                "component_vertices": list(component),
                "crossing_remaining_edges": crossing,
            }}
            verify_second_layer_certificate(vertices, edges, first, result)
            return result

    # Process leaves before parents. Selecting the parent edge removes an odd
    # residual at the child and transfers it to the parent. Component parity
    # ensures the final residual at every root is zero.
    residual = dict(parity)
    selected = set()
    for vertex in reversed(order):
        ancestor = parent[vertex]
        if ancestor is not None and residual[vertex]:
            selected.add(parent_edge[vertex])
            residual[vertex] ^= 1
            residual[ancestor] ^= 1
    _require(not any(residual.values()), "internal forest parity construction failed")
    second = remaining | selected
    result = {"status": "completed", **common,
              "added_from_first_layer": sorted(selected),
              "second_layer": sorted(second)}
    verify_second_layer_certificate(vertices, edges, first, result)
    return result


def verify_second_layer_certificate(vertices, edges, first_layer, result):
    """Check the mathematical certificate without replaying the producer's tree.

    Any valid covering second layer is accepted. For obstruction, the reported
    vertices must form a whole connected component of A, and the exact R cut
    must have odd cardinality. Neither check searches color assignments.
    """
    vertices, edges, first = _prepare(vertices, edges, first_layer)
    remaining = frozenset(range(len(edges))) - first
    _require(isinstance(result, dict), "certificate must be a dictionary")
    # Python considers False == 0 and True == 1. Validate index types before
    # comparing lists, so that equality cannot authenticate boolean forgeries.
    _edge_ids(result.get("first_layer", ()), len(edges), "certificate first_layer")
    _edge_ids(result.get("remaining_edges", ()), len(edges), "certificate remaining_edges")
    _require(result.get("first_layer") == sorted(first), "certificate first_layer differs")
    _require(result.get("remaining_edges") == sorted(remaining),
             "certificate remaining_edges differ")

    if result.get("status") == "completed":
        _require(set(result) == {"status", "first_layer", "remaining_edges",
                                 "added_from_first_layer", "second_layer"},
                 "completed certificate fields differ")
        selected = _edge_ids(result["added_from_first_layer"], len(edges),
                             "added_from_first_layer")
        second = _edge_ids(result["second_layer"], len(edges), "second_layer")
        _require(selected <= first, "added edges must belong to first_layer")
        _require(second == remaining | selected, "second_layer differs from R union X")
        _require(first | second == frozenset(range(len(edges))), "edge coverage incomplete")
        _require(not any(_boundary(vertices, edges, second).values()),
                 "second_layer is not even")
        return {"passed": True, "claim": "two-even-layers-cover-all-provided-edges"}

    _require(result.get("status") == "obstructed", "unknown certificate status")
    _require(set(result) == {"status", "first_layer", "remaining_edges", "obstruction"},
             "obstruction certificate fields differ")
    obstruction = result["obstruction"]
    _require(isinstance(obstruction, dict) and set(obstruction) == {
        "kind", "component_vertices", "crossing_remaining_edges"},
        "odd-cut certificate fields differ")
    _require(obstruction["kind"] == "odd-remaining-cut-of-first-layer-component",
             "unknown obstruction kind")
    supplied = obstruction["component_vertices"]
    _require(isinstance(supplied, list) and supplied,
             "component_vertices must be a nonempty list")
    _require(all(type(vertex) is int and vertex in vertices for vertex in supplied),
             "invalid component vertex")
    _require(len(supplied) == len(set(supplied)), "duplicate component vertices")
    members = set(supplied)

    # Reconstruct only this claimed component, independently of the producer's
    # full forest and its parity decisions. Reaching outside detects truncation.
    adjacent = _first_adjacency(vertices, edges, first)
    reached, queue = {supplied[0]}, [supplied[0]]
    for vertex in queue:
        for neighbor, _ in adjacent[vertex]:
            if neighbor not in reached:
                reached.add(neighbor)
                queue.append(neighbor)
    _require(reached == members, "claimed vertices are not an entire first-layer component")
    crossing = frozenset(index for index in remaining
                         if (edges[index][0] in members) != (edges[index][1] in members))
    supplied_crossing = _edge_ids(obstruction["crossing_remaining_edges"], len(edges),
                                 "crossing_remaining_edges")
    _require(supplied_crossing == crossing, "reported cut differs from actual R cut")
    _require(len(crossing) % 2 == 1, "reported cut is not odd")
    return {"passed": True, "claim": "no-second-even-layer-for-fixed-first-layer"}

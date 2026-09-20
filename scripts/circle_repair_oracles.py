"""Small, bounded exhaustive oracles for repairing an even first edge layer.

This research helper is independent of ``fourcolor.circle_layers`` and of the
production repair algorithm. It enumerates all edge subsets by Gray code and
retains the even ones. Feasibility uses an independently implemented component
parity test, so the oracle shares the proved mathematical criterion, not its
implementation. Validation must additionally compare this criterion against
direct two-layer coverage on tiny graphs. None of these routines uses planarity
or supplies a general efficient algorithm. All provided edges require coverage;
plane-map callers must remove actual bridges before invoking these routines.
"""

def _prepare(vertices, edges, max_edges):
    """Validate input and enforce a hard maximum of 2**20 subset candidates."""
    if type(max_edges) is not int or not 0 <= max_edges <= 20:
        raise ValueError("max_edges must be an integer between 0 and 20")
    try:
        vertices = tuple(vertices)
        edges = tuple(tuple(edge) for edge in edges)
    except TypeError as exc:
        raise ValueError("vertices and edges must be iterable") from exc
    if any(type(v) is not int for v in vertices) or len(set(vertices)) != len(vertices):
        raise ValueError("vertices must contain distinct integer IDs")
    known = set(vertices)
    if any(len(edge) != 2 or any(type(v) is not int or v not in known for v in edge)
           for edge in edges):
        raise ValueError("each edge must have two declared integer endpoints")
    if len(edges) > max_edges:
        raise ValueError("edge count exceeds the explicit exhaustive-search bound")
    vertices = tuple(sorted(vertices))
    position = {v: i for i, v in enumerate(vertices)}
    incidence = tuple((1 << position[u]) ^ (1 << position[v]) for u, v in edges)
    return vertices, edges, incidence


def _indices(mask, size):
    """Convert a bit mask to a stable tuple of edge indices."""
    return tuple(i for i in range(size) if mask >> i & 1)


def _even_masks(incidence):
    """Visit every subset once, updating parity by its single Gray-code flip."""
    masks = [0]
    previous = parity = 0
    for step in range(1, 1 << len(incidence)):
        mask = step ^ (step >> 1)
        changed = mask ^ previous
        parity ^= incidence[changed.bit_length() - 1]
        if parity == 0:
            masks.append(mask)
        previous = mask
    return sorted(masks)


def all_even_edge_sets(vertices, edges, max_edges=20):
    """Return every even edge subset, including empty, by ascending bit mask.

    Returned items are tuples of edge indices. Loops contribute degree two and
    parallel edges remain distinct. The requested edge bound cannot exceed 20;
    enumerating 2**m candidates is deliberate and limited to small experiments.
    """
    _, edges, incidence = _prepare(vertices, edges, max_edges)
    return [_indices(mask, len(edges)) for mask in _even_masks(incidence)]


def _components(vertices, edges, selected):
    """Reconstruct connected components with a standalone union-find routine."""
    parents = {v: v for v in vertices}

    def root(vertex):
        while parents[vertex] != vertex:
            parents[vertex] = parents[parents[vertex]]
            vertex = parents[vertex]
        return vertex

    for i in selected:
        a, b = edges[i]
        a, b = root(a), root(b)
        if a != b:
            parents[a] = b
    grouped = {}
    for vertex in vertices:
        grouped.setdefault(root(vertex), []).append(vertex)
    return sorted(tuple(group) for group in grouped.values())


def _bad_components(vertices, edges, selected):
    """Count odd cuts using original degree parity and whole A components.

    Since selected A is even, remaining-edge vertex parity equals the parity of
    the whole graph. Summing over one component cancels all internal edges.
    Isolated A vertices are components and must not be discarded.
    """
    parity = {v: 0 for v in vertices}
    for a, b in edges:
        parity[a] ^= 1
        parity[b] ^= 1
    return [component for component in _components(vertices, edges, selected)
            if sum(parity[v] for v in component) % 2]


def simple_cycle_edge_sets(vertices, edges, max_edges=20):
    """Return every connected nonempty 2-regular edge subset, by (length, IDs).

    This is an exhaustive simple-cycle definition for multigraphs: a loop is a
    one-edge cycle and a pair of parallel edges is a two-edge cycle. No cycles
    are silently limited to a chosen basis or to facial boundaries.
    """
    vertices, edges, incidence = _prepare(vertices, edges, max_edges)
    cycles = []
    for mask in _even_masks(incidence):
        if not mask:
            continue
        selected = _indices(mask, len(edges))
        degree = {v: 0 for v in vertices}
        for i in selected:
            a, b = edges[i]
            degree[a] += 1
            degree[b] += 1
        active = {v for v in vertices if degree[v]}
        if any(degree[v] != 2 for v in active):
            continue
        active_components = [component for component in _components(vertices, edges, selected)
                             if any(v in active for v in component)]
        if len(active_components) == 1:
            cycles.append(selected)
    return sorted(cycles, key=lambda selected: (len(selected), selected))


def oracle_minimum_repair(vertices, edges, first, costs=None, max_edges=20):
    """Exhaustively minimize the changed-edge cost among all completable A.

    ``costs`` is an optional sequence of nonnegative integer weights, one per
    edge. Exact integers avoid rounding-dependent optimality claims. Default
    unit weights give minimum Hamming distance. Ties use
    changed-edge count, changed edge IDs, then repaired edge IDs; ``tied_optima``
    counts all candidates with equal minimum cost before those tie-breaks.

    Feasibility is the odd-component-cut criterion, implemented independently
    here. This is an oracle for finite optimality, not a second mathematical
    proof of that criterion. Graphs that admit no two-layer cover return
    ``unrepairable``; this can include graphs with bridges or nonplanar inputs.
    """
    vertices, edges, incidence = _prepare(vertices, edges, max_edges)
    try:
        first = tuple(first)
    except TypeError as exc:
        raise ValueError("first must be an iterable of edge indices") from exc
    if (any(type(i) is not int or not 0 <= i < len(edges) for i in first)
            or len(set(first)) != len(first)):
        raise ValueError("first must contain distinct valid edge indices")
    first = tuple(sorted(first))
    boundary = 0
    first_mask = 0
    for i in first:
        boundary ^= incidence[i]
        first_mask |= 1 << i
    if boundary:
        raise ValueError("first must be an even edge subset")
    if costs is None:
        costs = (1,) * len(edges)
    else:
        try:
            costs = tuple(costs)
        except TypeError as exc:
            raise ValueError("costs must be iterable") from exc
        if len(costs) != len(edges) or any(type(value) is not int or value < 0 for value in costs):
            raise ValueError("costs must be nonnegative integers, one per edge")

    masks = _even_masks(incidence)
    best = None
    feasible = tied = 0
    for mask in masks:
        candidate = _indices(mask, len(edges))
        if _bad_components(vertices, edges, candidate):
            continue
        feasible += 1
        changed = _indices(mask ^ first_mask, len(edges))
        cost = sum(costs[i] for i in changed)
        ordering = (cost, len(changed), changed, candidate)
        if best is None or cost < best[0]:
            tied = 1
            best = ordering
        elif cost == best[0]:
            tied += 1
            if ordering < best:
                best = ordering

    return {
        "status": "repaired" if best is not None else "unrepairable",
        "first_layer": list(first),
        "first_layer_bad_component_count": len(_bad_components(vertices, edges, first)),
        "repaired_first_layer": list(best[3]) if best is not None else None,
        "changed_edges": list(best[2]) if best is not None else None,
        "cost": best[0] if best is not None else None,
        "examined_even_layers": len(masks),
        "feasible_even_layers": feasible,
        "tied_optima": tied,
        "feasibility_method": "independent-component-parity-criterion",
        "optimality_scope": "all-even-first-layers-on-the-provided-finite-graph",
    }

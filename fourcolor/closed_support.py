"""Recognize an already established PRIMAL cycle supporting two end ports.

The graph here is the original embedded line network, NOT the shore/dual
adjacency graph. The frame is a geometric root; another real edge is support
only when both of its current shore domains are singleton. Virtual connectors
are never support. A target cannot supply the edges of its own support cycle.

This module only returns a geometric tie-breaking certificate. It introduces
no color ban and makes no claim that a supported target has a valid completion.
"""


def _cyclic_blocks(vertices, edges, selected_edge_ids):
    """Find cyclic VERTEX-biconnected blocks using iterative Tarjan DFS.

The edge stack produces the usual point-biconnected blocks, not components
obtained merely by deleting bridges. Thus two cycles sharing one articulation
vertex stay separate. Parallel edges are distinguished by edge ID, so two
parallel edges correctly form a two-edge cycle. Self-loops form singleton
blocks; they cannot witness a cycle through two distinct target endpoints.

The DFS and its edge-stack work are O(V+E), without Python recursion. Returned
blocks use edge/vertex sets; any later certificate ordering is separate work.
"""
    selected = set(selected_edge_ids)
    if any(type(edge) is not int or not 0 <= edge < len(edges) for edge in selected):
        raise ValueError("support edge IDs must index the supplied primal edges")
    adjacency = {vertex: [] for vertex in vertices}
    blocks = []
    for edge, (first, second) in enumerate(edges):
        if edge not in selected:
            continue
        if first not in adjacency or second not in adjacency:
            raise ValueError("every primal endpoint must occur in the vertex set")
        if first == second:
            blocks.append({"edge_ids": frozenset((edge,)),
                           "vertices": frozenset((first,))})
            continue
        adjacency[first].append((second, edge))
        adjacency[second].append((first, edge))

    discovery, low, parent, parent_edge = {}, {}, {}, {}
    pending_edges = []

    def save_block(last_edge):
        """Pop one DFS block and retain it only if it actually contains a cycle."""
        members, endpoints = set(), set()
        while pending_edges:
            edge = pending_edges.pop()
            members.add(edge)
            endpoints.update(edges[edge])
            if edge == last_edge:
                break
        else:
            raise AssertionError("Tarjan edge stack lost its tree edge")
        # Each emitted block is connected. A bridge is one edge/two vertices;
        # a two-parallel-edge block has two edges/two vertices and is cyclic.
        if len(members) >= len(endpoints):
            blocks.append({"edge_ids": frozenset(members),
                           "vertices": frozenset(endpoints)})

    for root in adjacency:
        if root in discovery:
            continue
        discovery[root] = low[root] = len(discovery)
        stack = [(root, iter(adjacency[root]))]
        while stack:
            vertex, onward = stack[-1]
            try:
                other, edge = next(onward)
            except StopIteration:
                stack.pop()
                if vertex in parent:
                    ancestor = parent[vertex]
                    low[ancestor] = min(low[ancestor], low[vertex])
                    if low[vertex] >= discovery[ancestor]:
                        save_block(parent_edge[vertex])
                elif pending_edges:
                    raise AssertionError("a completed DFS root retained unassigned edges")
                continue
            if edge == parent_edge.get(vertex):
                continue
            if other not in discovery:
                pending_edges.append(edge)
                parent[other], parent_edge[other] = vertex, edge
                discovery[other] = low[other] = len(discovery)
                stack.append((other, iter(adjacency[other])))
            elif discovery[other] < discovery[vertex]:
                # Skip only the actual parent EDGE above. Another parallel
                # parent connection is a genuine back edge and must remain.
                pending_edges.append(edge)
                low[vertex] = min(low[vertex], discovery[other])
    return blocks


def _support_edge_ids(model, domains):
    """The geometric frame and fully named real edges form current support."""
    frame = {span["edge"] for line in model.lines if line["id"] == "frame"
             for span in line["spans"]}
    virtual = set(model.virtual_edges)
    return frozenset(edge for edge in range(len(model.plane_map.edges))
                     if edge not in virtual and
                     (edge in frame or all(len(domains[side]) == 1
                                           for side in model.plane_map.shores(edge))))


def _block_index(blocks):
    """Index a vertex's cyclic blocks without joining articulation neighbors."""
    membership = {}
    for index, block in enumerate(blocks):
        for vertex in block["vertices"]:
            membership.setdefault(vertex, set()).add(index)
    return membership


def supported_cycle_units(model, domains, units):
    """Return one current primal-cycle certificate per scheduling unit.

    Public output is ``{unit_id: {supported, block_edge_ids, endpoint_vertices}}``.
    Endpoint vertices are strings from PlaneMap, ordered with the mother line.
    Only unresolved INTERNAL units are eligible; frame root units and fully
    named units return false. Two distinct endpoints must belong to the SAME
    cyclic point-biconnected block after all target edges have been excluded.

    Active ordinary intervals have no support edges of their own, so they share
    one linear Tarjan decomposition. Defensive mixed intervals get a cached
    separate decomposition with their own edges removed. Total certificate
    output and these exceptional decompositions are not claimed to be linear.
    """
    plane = model.plane_map
    if len(domains) != len(plane.faces):
        raise ValueError("one current domain per real shore identity is required")
    copied_domains = [tuple(domain) for domain in domains]
    if any(not domain or len(set(domain)) != len(domain)
           or any(type(name) is not int or name not in (1, 2, 3, 4) for name in domain)
           for domain in copied_domains):
        raise ValueError("domains must be nonempty distinct subsets of names1..4")
    mothers = {line["id"]: {span["edge"]: span for span in line["spans"]}
               for line in model.lines}
    support = _support_edge_ids(model, copied_domains)
    blocks = _cyclic_blocks(plane.vertices, plane.edges, support)
    cache = {frozenset(): (blocks, _block_index(blocks))}
    result = {}
    for unit in units:
        if unit["id"] in result:
            raise ValueError("scheduling unit IDs must be distinct")
        spans = mothers.get(unit["mother"])
        unit_edges = unit["edges"]
        if spans is None or not unit_edges or any(edge not in spans for edge in unit_edges):
            raise ValueError("each unit must contain real edges of its declared mother")
        first_dart, last_dart = spans[unit_edges[0]]["dart"], spans[unit_edges[-1]]["dart"]
        first = plane.edges[first_dart // 2][first_dart % 2]
        last = plane.edges[last_dart // 2][1 - last_dart % 2]
        record = {"supported": False, "block_edge_ids": [],
                  "endpoint_vertices": [first, last]}
        result[unit["id"]] = record
        if (unit["mother"] == "frame" or first == last
                or not any(len(copied_domains[side]) > 1 for side, _ in unit["occurrences"])):
            continue
        excluded = support.intersection(unit_edges)
        if excluded not in cache:
            revised = _cyclic_blocks(plane.vertices, plane.edges, support - excluded)
            cache[excluded] = revised, _block_index(revised)
        available, membership = cache[excluded]
        common = membership.get(first, set()) & membership.get(last, set())
        if common:
            witness = available[min(common)]
            record["supported"] = True
            record["block_edge_ids"] = sorted(witness["edge_ids"])
            if set(unit_edges) & witness["edge_ids"]:
                raise AssertionError("a target edge leaked into its support witness")
    return result

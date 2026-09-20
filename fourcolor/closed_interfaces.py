"""Exact coloring through single-vertex interfaces in the constraint graph.

Vertices here are map faces when called on a dual constraint graph. A block
interface is a shared FACE VARIABLE, not a primal flow port or a geometric
circle. Standard biconnected blocks meet in at most one articulation vertex.
Without fixed colors or lists, a feasible block permits every color at that
vertex by a global permutation. Its outgoing relation is therefore universal.

This module uses exact orbit-frontier searches inside blocks. It does not
claim a new decomposition theorem, a greedy four-color algorithm, or a method
for extending an unknown future graph. The input graph is complete and fixed.
"""

from collections import deque

from fourcolor.frontier_order import _graph, _order, _require
from fourcolor.orbit_frontier import orbit_frontier_trace


def biconnected_blocks(n, edges):
    """Return deterministic vertex blocks using iterative Tarjan DFS.

    Bridges form two-vertex blocks; isolated vertices form singleton blocks.
    Parallel constraints are deduplicated by the shared graph validator.
    A self-loop is an unsatisfiable singleton constraint, attached to its
    existing vertex block when the caller extracts induced block edges.
    Iteration avoids a recursion-depth assumption for long input chains.
    """
    _, adjacent = _graph(n, edges)
    neighbors = [tuple(sorted(adjacent[v] - {v})) for v in range(n)]
    discovery, low, parent = [-1] * n, [-1] * n, [-1] * n
    edge_stack, blocks = [], []
    clock = 0
    for root in range(n):
        if discovery[root] != -1:
            continue
        if not neighbors[root]:
            blocks.append((root,))
            discovery[root] = low[root] = clock
            clock += 1
            continue
        discovery[root] = low[root] = clock
        clock += 1
        stack = [(root, iter(neighbors[root]))]
        while stack:
            vertex, pending = stack[-1]
            other = next(pending, None)
            if other is not None:
                if discovery[other] == -1:
                    parent[other] = vertex
                    edge_stack.append((vertex, other))
                    discovery[other] = low[other] = clock
                    clock += 1
                    stack.append((other, iter(neighbors[other])))
                elif other != parent[vertex] and discovery[other] < discovery[vertex]:
                    low[vertex] = min(low[vertex], discovery[other])
                    edge_stack.append((vertex, other))
                continue
            stack.pop()
            ancestor = parent[vertex]
            if ancestor == -1:
                continue
            low[ancestor] = min(low[ancestor], low[vertex])
            if low[vertex] >= discovery[ancestor]:
                members = set()
                while edge_stack:
                    edge = edge_stack.pop()
                    members.update(edge)
                    if edge == (ancestor, vertex):
                        break
                blocks.append(tuple(sorted(members)))
    return tuple(sorted(blocks))


def _block_forest(n, blocks, order):
    """Orient the block-cut forest without constructing clique adjacencies.

    Several blocks sharing the same articulation are siblings. A single scan
    of each vertex's incidence list keeps a high-degree star from becoming a
    quadratic list of block pairs. The chosen order supplies deterministic
    root and neighbor priorities, not a coloring oracle.
    """
    incidence = [[] for _ in range(n)]
    for index, members in enumerate(blocks):
        for vertex in members:
            incidence[vertex].append(index)
    rank = {vertex: i for i, vertex in enumerate(order)}
    priorities = [min(rank[v] for v in block) for block in blocks]
    parents, ports, preorder = {}, {}, []
    expanded_vertices = set()
    for root in sorted(range(len(blocks)), key=lambda i: (priorities[i], i)):
        if root in parents:
            continue
        parents[root], ports[root] = None, None
        queue = deque([root])
        while queue:
            index = queue.popleft()
            preorder.append(index)
            for vertex in sorted(blocks[index], key=rank.get):
                if vertex in expanded_vertices:
                    continue
                expanded_vertices.add(vertex)
                for child in sorted(incidence[vertex], key=lambda i: (priorities[i], i)):
                    if child not in parents:
                        parents[child], ports[child] = index, vertex
                        queue.append(child)
    return preorder, parents, ports


def closed_interface_trace(n, edges, order, palette_size=4):
    """Solve each block, then align witnesses through its sole parent port.

    Blocks are computed leaves first; their local orders are restrictions of
    the supplied global order. Witness assembly is parent first. No interior
    name is permanently frozen: a child witness is globally permuted so its
    port equals the already assembled face color. Fixed-color/list constraints
    are deliberately absent from this API and are not silently accepted.

    ``peak_states`` measures the largest ACTIVE local DP table, not the sum of
    stored witnesses or Python memory. Benchmark memory separately. Searches
    are exact; there is no switching to a different solver on failure.
    """
    normalized, _ = _graph(n, edges)
    ordered = _order(n, order)
    _require(type(palette_size) is int and 1 <= palette_size <= 4,
             "palette_size must be an integer from 1 through 4, not bool")
    blocks = biconnected_blocks(n, normalized)
    preorder, parents, ports = _block_forest(n, blocks, ordered)
    rank = {v: i for i, v in enumerate(ordered)}
    incidence = [set() for _ in range(n)]
    for index, members in enumerate(blocks):
        for vertex in members:
            incidence[vertex].add(index)
    block_edges = [[] for _ in blocks]
    for a, b in normalized:
        owners = incidence[a] & incidence[b]
        _require(bool(owners) and (a == b or len(owners) == 1), "edge block partition failed")
        # One loop in any incident block suffices to propagate impossibility.
        block_edges[min(owners)].append((a, b))
    local_results = {}
    for index in reversed(preorder):
        members = blocks[index]
        local_ids = {vertex: i for i, vertex in enumerate(members)}
        local_edges = [(local_ids[a], local_ids[b]) for a, b in block_edges[index]]
        local_order = sorted(range(len(members)), key=lambda i: rank[members[i]])
        trace = orbit_frontier_trace(len(members), local_edges, local_order,
                                     palette_size=palette_size)
        local_results[index] = {
            "id": index, "vertices": list(members), "parent": parents[index],
            "port": ports[index], "order": [members[i] for i in local_order],
            "feasible": trace["feasible"], "one_coloring": trace["one_coloring"],
            "interface_relation": "all_colors" if trace["feasible"] and ports[index] is not None
                                  else "feasible_empty" if trace["feasible"] else "empty",
            "summary": trace["summary"],
        }
    feasible = all(row["feasible"] for row in local_results.values())
    coloring = [-1] * n if feasible else None
    if feasible:
        for index in preorder:
            row, port = local_results[index], ports[index]
            local = row["one_coloring"]
            permutation = list(range(palette_size))
            if port is not None:
                source = local[blocks[index].index(port)]
                target = coloring[port]
                _require(target >= 0, "parent interface was not assembled")
                # A transposition is a full bijection, even if either name is
                # also used by internal vertices of the child block.
                permutation[source], permutation[target] = target, source
            for vertex, local_color in zip(blocks[index], local):
                value = permutation[local_color]
                _require(coloring[vertex] in (-1, value), "block interfaces disagree")
                coloring[vertex] = value
        _require(all(0 <= c < palette_size for c in coloring), "uncolored vertex")
        _require(all(coloring[a] != coloring[b] for a, b in normalized), "invalid witness")
    summaries = [row["summary"] for row in local_results.values()]
    return {
        "n": n, "edges": [list(e) for e in normalized], "order": list(ordered),
        "palette_size": palette_size, "feasible": feasible, "one_coloring": coloring,
        "blocks": [local_results[i] for i in range(len(blocks))],
        "computation_order": list(reversed(preorder)), "assembly_order": preorder,
        "summary": {
            "block_count": len(blocks), "largest_block": max(map(len, blocks), default=0),
            "single_port_blocks": sum(port is not None for port in ports.values()),
            "peak_states": max((s["peak_states"] for s in summaries), default=1),
            "attempted_transitions": sum(s["attempted_transitions"] for s in summaries),
            "accepted_transitions": sum(s["accepted_transitions"] for s in summaries),
        },
    }

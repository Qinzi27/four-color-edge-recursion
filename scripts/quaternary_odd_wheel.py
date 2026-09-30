"""Find a physical odd wheel confined to a common palette of three names.

A wheel center uses one of the common three names. Its physically adjacent
odd rim can then use at most two names, which is impossible. The supplied
domains are premises: their derivation must be independently audited by the
contact wrapper's checker. This detector does not claim that arbitrary
caller-supplied restrictions follow from the raw graph.
"""

from collections import deque
import hashlib
import json

from scripts.quaternary_logical_neq_contacts import _validate_logical


VERSION = "quaternary-domain-odd-wheel-v1"


def _digest(value):
    """Bind the complete literal JSON input, including all logical premises."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False).encode("utf-8")).hexdigest()


def _canonical_cycle(cycle):
    """Choose an index-based orientation and rotation of a simple cycle."""
    start = cycle.index(min(cycle))
    forward = cycle[start:] + cycle[:start]
    reverse = [forward[0]] + list(reversed(forward[1:]))
    return min(forward, reverse)


def _tree_cycle(first, second, parent):
    """Close a same-parity BFS edge through its lowest common ancestor."""
    first_path, vertex = [], first
    while vertex is not None:
        first_path.append(vertex)
        vertex = parent[vertex]
    positions = {vertex: i for i, vertex in enumerate(first_path)}
    second_path, vertex = [], second
    while vertex not in positions:
        second_path.append(vertex)
        vertex = parent[vertex]
    return _canonical_cycle(first_path[:positions[vertex] + 1] + list(reversed(second_path)))


def find_odd_wheel(document, domains):
    """Return the first deterministic physical wheel certificate, or None.

    Excluded colors and centers are considered in increasing color and literal
    side-index order. Each eligible neighbor graph is tested by BFS with sorted
    neighbors. The first parity conflict supplies a simple odd rim; the search
    does not claim a globally shortest cycle. Bridges, point contacts and
    logical EQ/NEQ never become physical wheel edges.
    """
    sides, _ = _validate_logical(document)
    if not isinstance(domains, list) or len(domains) != len(sides):
        raise ValueError("domains must be a side-aligned array")
    for domain in domains:
        if (not isinstance(domain, list)
                or any(type(color) is not int or color not in (1, 2, 3, 4) for color in domain)
                or domain != sorted(set(domain))):
            raise ValueError("each domain must be a sorted unique array of integer names 1..4")
    index = {side: i for i, side in enumerate(sides)}
    adjacency = [set() for _ in sides]
    for line in document["lines"]:
        if line["kind"] == "separator":
            first, second = index[line["left"]], index[line["right"]]
            adjacency[first].add(second)
            adjacency[second].add(first)
    statistics = {key: 0 for key in (
        "palettes_examined", "centers_examined", "eligible_neighbor_sets",
        "bfs_components", "vertices_visited", "edges_examined", "odd_cycles_found")}
    certificate = None
    for excluded in (1, 2, 3, 4):
        statistics["palettes_examined"] += 1
        eligible = {i for i, domain in enumerate(domains) if excluded not in domain}
        for center in sorted(eligible):
            statistics["centers_examined"] += 1
            neighbors = adjacency[center] & eligible
            if len(neighbors) < 3:
                continue
            statistics["eligible_neighbor_sets"] += 1
            parity, parent = {}, {}
            for root in sorted(neighbors):
                if root in parity:
                    continue
                statistics["bfs_components"] += 1
                parity[root], parent[root] = 0, None
                queue = deque([root])
                while queue:
                    vertex = queue.popleft()
                    statistics["vertices_visited"] += 1
                    for adjacent in sorted(adjacency[vertex] & neighbors):
                        statistics["edges_examined"] += 1
                        if adjacent not in parity:
                            parity[adjacent], parent[adjacent] = 1 - parity[vertex], vertex
                            queue.append(adjacent)
                        elif parity[adjacent] == parity[vertex]:
                            rim = _tree_cycle(vertex, adjacent, parent)
                            certificate = {"center": sides[center],
                                           "rim": [sides[i] for i in rim],
                                           "excluded_color": excluded}
                            statistics["odd_cycles_found"] += 1
                            break
                    if certificate is not None:
                        break
                if certificate is not None:
                    break
            if certificate is not None:
                break
        if certificate is not None:
            break
    return {"version": VERSION, "raw_document_sha256": _digest(document),
            "domains_sha256": _digest(domains), "certificate": certificate,
            "statistics": statistics}

"""Offline exact four-name extendibility with independently checked evidence.

This module imports no project coloring or propagation code. It uses only the
original simple adjacency graph and literal fixed names. Every UNSAT branch
retains all available names from 1, 2, 3, 4; no color-symmetry reduction is used.
The oracle is for post-run verification, never production choice or repair.
"""

from collections.abc import Mapping
from hashlib import sha256
import json


METHOD = "independent-mrv-literal-four-colors-v1"
PALETTE = (1, 2, 3, 4)


def _require(condition, message):
    """Keep validation active under Python optimization."""
    if not condition:
        raise ValueError(message)


def _inputs(n, edges, anchors):
    """Validate identities and normalize parsing, without any inference rule.

    A bridge's repeated side must be omitted before this simple constraint
    graph API is called. A self-loop cannot silently stand for such a bridge.
    Literal duplicate undirected edges are rejected to reveal caller errors.
    """
    _require(type(n) is int and n >= 0, "n must be a nonnegative integer")
    _require(isinstance(edges, (list, tuple)), "edges must be a list or tuple")
    normalized = set()
    for pair in edges:
        _require(isinstance(pair, (list, tuple)) and len(pair) == 2,
                 "each edge must contain two identities")
        first, second = pair
        _require(type(first) is int and type(second) is int and
                 0 <= first < n and 0 <= second < n, "edge identity outside 0..n-1")
        _require(first != second, "self-loops are not valid simple side constraints")
        key = tuple(sorted(pair))
        _require(key not in normalized, "duplicate undirected edge")
        normalized.add(key)
    _require(isinstance(anchors, Mapping), "anchors must map integer identities to literal names")
    fixed = {}
    for vertex, color in anchors.items():
        _require(type(vertex) is int and 0 <= vertex < n, "anchor identity outside 0..n-1")
        _require(type(color) is int and color in PALETTE, "anchor name must be 1, 2, 3 or 4")
        fixed[vertex] = color
    return sorted(normalized), dict(sorted(fixed.items()))


def _input_hash(n, edges, anchors):
    """Bind evidence to normalized literal input rather than Python key types."""
    value = {"n": n, "edges": [list(edge) for edge in edges],
             "anchors": [[v, c] for v, c in anchors.items()]}
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()


def solve_exact(n, edges, anchors, *, node_limit=1_000_000):
    """Return SAT, a complete UNSAT tree, or UNKNOWN when the node cap is hit.

    ``anchors`` is a mapping ``{integer_vertex: literal_color_1_to_4}``.
    ``edges`` is a duplicate-free list/tuple of distinct-endpoint pairs.
    A node is one visited partial assignment, including the root and leaves.
    MRV chooses the smallest remaining domain, then highest original degree,
    then least vertex identity. Children try all available literal names in
    ascending order. Explicit stacks avoid a recursion-depth resource limit.

    SAT evidence is a complete witness; its search-node count is telemetry.
    UNSAT evidence is the full tree, so its node count can be checked exactly.
    UNKNOWN has no witness or certificate and makes no satisfiability claim.
    """
    original_edges, fixed = _inputs(n, edges, anchors)
    _require(type(node_limit) is int and node_limit >= 0, "node_limit must be a nonnegative integer")
    input_hash = _input_hash(n, original_edges, fixed)
    adjacent = [set() for _ in range(n)]
    for first, second in original_edges:
        adjacent[first].add(second)
        adjacent[second].add(first)
    names = [fixed.get(vertex, 0) for vertex in range(n)]
    stack, nodes = [], 0

    def result(status, *, witness=None, certificate=None, reason=None):
        """Use one explicit schema for conclusive and inconclusive outcomes."""
        return {"schema_version": 1, "method": METHOD, "palette": list(PALETTE),
                "input_sha256": input_hash, "status": status, "witness": witness,
                "certificate": certificate, "nodes": nodes, "node_limit": node_limit,
                "reason": reason}

    while True:
        if nodes >= node_limit:
            return result("unknown", reason="node_limit")
        nodes += 1
        bad = next(((a, b) for a, b in original_edges if names[a] and names[a] == names[b]), None)
        if bad is not None:
            completed = {"kind": "conflict", "edge": list(bad)}
        else:
            options = []
            for vertex in range(n):
                if names[vertex]:
                    continue
                forbidden = {names[other] for other in adjacent[vertex] if names[other]}
                available = [color for color in PALETTE if color not in forbidden]
                options.append((len(available), -len(adjacent[vertex]), vertex, available))
            if not options:
                return result("sat", witness=list(names))
            _, _, vertex, available = min(options)
            if available:
                stack.append({"vertex": vertex, "available": available,
                              "next_index": 0, "children": []})
                names[vertex] = available[0]
                continue
            completed = {"kind": "dead_end", "vertex": vertex,
                         "blockers": [{"color": color,
                                       "neighbor": min(other for other in adjacent[vertex]
                                                       if names[other] == color)}
                                      for color in PALETTE]}
        # The current subtree is exhausted. Its complete proof becomes one
        # parent's child; only then can the next literal color be explored.
        while stack:
            frame = stack[-1]
            vertex, index = frame["vertex"], frame["next_index"]
            frame["children"].append({"color": frame["available"][index], "child": completed})
            names[vertex] = 0
            frame["next_index"] += 1
            if frame["next_index"] < len(frame["available"]):
                names[vertex] = frame["available"][frame["next_index"]]
                break
            stack.pop()
            completed = {"kind": "branch", "vertex": vertex, "children": frame["children"]}
        else:
            return result("unsat", certificate=completed)


def verify_exact_result(n, edges, anchors, result):
    """Check evidence directly, without calling the solver or its MRV selector.

    Tree replay accepts any unassigned branch vertex, recomputes its complete
    available literal-color set from raw edges, and checks every branch and
    every terminal conflict. It does not trust recorded MRV reasoning, domains,
    symmetry assumptions, or a producer's neighbor/propagation helper.

    For UNKNOWN, ``passed=True`` validates only the undecided result schema;
    ``conclusive=False`` and ``claim='unresolved'`` must remain distinct from a
    verified UNSAT certificate. SAT and UNKNOWN node counts are telemetry only.
    """
    original_edges, fixed = _inputs(n, edges, anchors)
    _require(isinstance(result, dict), "result must be a dictionary")
    required = {"schema_version", "method", "palette", "input_sha256", "status",
                "witness", "certificate", "nodes", "node_limit", "reason"}
    _require(set(result) == required, "unexpected or missing result field")
    _require(type(result["schema_version"]) is int and result["schema_version"] == 1 and
             result["method"] == METHOD and result["palette"] == list(PALETTE), "wrong method schema or palette")
    _require(result["input_sha256"] == _input_hash(n, original_edges, fixed), "evidence belongs to different input")
    nodes, limit = result["nodes"], result["node_limit"]
    _require(type(nodes) is int and type(limit) is int and 0 <= nodes <= limit,
             "invalid node count or resource limit")
    status = result["status"]
    _require(status in ("sat", "unsat", "unknown"), "unknown result status")
    if status == "unknown":
        _require(result["witness"] is None and result["certificate"] is None and
                 result["reason"] == "node_limit" and nodes == limit,
                 "UNKNOWN must not carry conclusive evidence")
        return {"passed": True, "status": "unknown", "conclusive": False,
                "claim": "unresolved", "nodes_independently_counted": None}
    _require(nodes >= 1 and result["reason"] is None, "conclusive result requires a visited node")
    if status == "sat":
        colors = result["witness"]
        _require(result["certificate"] is None and isinstance(colors, list) and len(colors) == n,
                 "SAT requires one complete literal witness")
        _require(all(type(color) is int and color in PALETTE for color in colors), "invalid witness name")
        _require(all(colors[v] == c for v, c in fixed.items()), "witness violates an anchor")
        _require(all(colors[a] != colors[b] for a, b in original_edges), "witness violates a raw edge")
        return {"passed": True, "status": "sat", "conclusive": True,
                "claim": "complete-four-name-witness", "edges_checked": len(original_edges),
                "anchors_checked": len(fixed), "nodes_independently_counted": None}
    _require(result["witness"] is None and isinstance(result["certificate"], dict),
             "UNSAT requires a complete proof tree and no witness")
    assigned = dict(fixed)
    raw = {frozenset(pair) for pair in original_edges}
    pending = [("visit", result["certificate"])]
    visited, object_ids, leaves = 0, set(), 0
    while pending:
        task = pending.pop()
        if task[0] == "undo":
            del assigned[task[1]]
            continue
        if task[0] == "child":
            _, vertex, color, child = task
            _require(vertex not in assigned, "branch attempts to overwrite an assignment")
            assigned[vertex] = color
            pending.append(("undo", vertex))
            pending.append(("visit", child))
            continue
        node = task[1]
        _require(isinstance(node, dict) and id(node) not in object_ids, "proof must be a finite tree")
        object_ids.add(id(node))
        visited += 1
        _require(visited <= nodes, "proof has more nodes than declared")
        kind = node.get("kind")
        if kind == "conflict":
            _require(set(node) == {"kind", "edge"}, "malformed conflict leaf")
            pair = node["edge"]
            _require(isinstance(pair, list) and len(pair) == 2 and
                     all(type(v) is int and 0 <= v < n for v in pair), "invalid conflict edge")
            a, b = pair
            _require(frozenset(pair) in raw and a in assigned and b in assigned and
                     assigned[a] == assigned[b], "leaf has no original same-name edge conflict")
            leaves += 1
            continue
        _require(kind in ("branch", "dead_end"), "unsupported proof node")
        vertex = node.get("vertex")
        _require(type(vertex) is int and 0 <= vertex < n and vertex not in assigned,
                 "proof must choose an unassigned original vertex")
        # Deliberately scan raw edge endpoints, rather than calling the
        # producer's adjacency/MRV logic to validate its own color coverage.
        forbidden = set()
        for a, b in original_edges:
            if a == vertex and b in assigned:
                forbidden.add(assigned[b])
            if b == vertex and a in assigned:
                forbidden.add(assigned[a])
        available = [color for color in (1, 2, 3, 4) if color not in forbidden]
        if kind == "dead_end":
            _require(set(node) == {"kind", "vertex", "blockers"} and not available,
                     "dead-end leaf still has an available name")
            blockers = node["blockers"]
            _require(isinstance(blockers, list) and len(blockers) == 4, "four literal-name blockers required")
            for color, blocker in zip((1, 2, 3, 4), blockers):
                _require(isinstance(blocker, dict) and set(blocker) == {"color", "neighbor"}
                         and type(blocker["color"]) is int and blocker["color"] == color,
                         "missing or repeated blocked literal name")
                other = blocker["neighbor"]
                _require(type(other) is int and 0 <= other < n and
                         frozenset((vertex, other)) in raw and assigned.get(other) == color,
                         "blocker is not a correctly named original neighbor")
            leaves += 1
            continue
        _require(set(node) == {"kind", "vertex", "children"} and available,
                 "branch must have at least one available literal name")
        children = node["children"]
        _require(isinstance(children, list) and len(children) == len(available),
                 "branch does not cover all available names")
        for color, entry in zip(available, children):
            _require(isinstance(entry, dict) and set(entry) == {"color", "child"}
                     and type(entry["color"]) is int and entry["color"] == color,
                     "omitted, duplicate or reordered literal-color branch")
        for entry in reversed(children):
            pending.append(("child", vertex, entry["color"], entry["child"]))
    _require(visited == nodes and assigned == fixed, "proof node count or assignment unwind differs")
    return {"passed": True, "status": "unsat", "conclusive": True,
            "claim": "complete-literal-four-name-unsat-tree", "leaves_checked": leaves,
            "nodes_independently_counted": visited}

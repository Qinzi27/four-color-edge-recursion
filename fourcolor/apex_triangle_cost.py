"""Exact recoloring costs after certified equalities under a fixed universal side.

A universal fixed vertex removes its color from all other vertices. With
three remaining colors, the opposite vertices of two triangles sharing an
edge must have the same color. This elementary, known implication permits
an equality quotient without losing any legal targets. It is NOT a new
planar coloring theorem; the core does not certify a plane embedding.

The quotient stores the cost of each literal color for each class. Global
color permutations cannot silently identify states because the old coloring
and fixed apex determine the cost semantics.
"""

from itertools import combinations

from .target_renaming import plan_target_renaming


def apex_triangle_cost_table(edges, initial, daughters, *, apex, weights=None,
                             max_nodes=200000):
    """Return equality witnesses, a quotient, and an exact 4x4 daughter table.

The complete initial coloring is proper on H. The pending edge joins two
distinct, equally colored daughters and is absent from H. The apex is a
different vertex adjacent to EVERY other vertex. It stays at its initial
color. Nonnegative integer weights price final changes from that initial
coloring. The two daughters should be explicitly given zero weight when
used in the split experiment.

Only equalities witnessed by original shared-edge triangles are merged;
we do not need to invent geometric adjacencies or iterate implications.
Enumeration visits proper partial quotient assignments and is limited by
max_nodes. A cutoff yields unknown, with witnessed upper bounds only.
"""
    if type(max_nodes) is not int or max_nodes < 0:
        raise ValueError("max_nodes must be a nonnegative integer")
    baseline = plan_target_renaming(edges, initial, initial, fixed=[apex], weights=weights)
    vertices = baseline.vertices
    positions = {v: i for i, v in enumerate(vertices)}
    if isinstance(daughters, (str, bytes)):
        raise ValueError("two distinct known daughters required")
    try:
        children = tuple(daughters)
    except TypeError as error:
        raise ValueError("two distinct known daughters required") from error
    if (len(children) != 2 or children[0] == children[1]
            or any(not isinstance(v, str) or v not in positions or v == apex for v in children)):
        raise ValueError("two distinct known non-apex daughters required")
    before = dict(zip(vertices, baseline.initial_symbols))
    costs = dict(zip(vertices, baseline.weights))
    if before[children[0]] != before[children[1]]:
        raise ValueError("daughters must initially have the same color")
    base = baseline.base_edges
    if any(set(edge) == set(children) for edge in base):
        raise ValueError("pending daughter edge must be absent")
    graph_edges = base + (children,)
    adjacent = {v: set() for v in vertices}
    for u, v in graph_edges:
        adjacent[u].add(v)
        adjacent[v].add(u)
    if adjacent[apex] != set(vertices) - {apex}:
        raise ValueError("apex must be adjacent to every other vertex")
    interior = tuple(v for v in vertices if v != apex)
    palette = tuple(c for c in range(4) if c != before[apex])
    parent = {v: v for v in interior}

    def root(v):
        """Find representatives without depending on external graph libraries."""
        while parent[v] != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v

    equalities = []
    for u, v in graph_edges:
        if apex in (u, v):
            continue
        opposite = sorted((adjacent[u] & adjacent[v]) - {apex}, key=positions.get)
        for a, b in combinations(opposite, 2):
            equalities.append({"shared_edge": (u, v), "opposite_vertices": (a, b)})
            ra, rb = root(a), root(b)
            if ra != rb:
                first, second = sorted((ra, rb), key=positions.get)
                parent[second] = first
    groups = {}
    for v in interior:
        groups.setdefault(root(v), []).append(v)
    classes = tuple(tuple(members) for members in groups.values())
    class_of = {v: i for i, members in enumerate(classes) for v in members}
    quotient_edges = tuple(sorted({tuple(sorted((class_of[u], class_of[v])))
                                   for u, v in graph_edges if apex not in (u, v)}))
    class_costs = tuple({c: sum(costs[v] for v in members if before[v] != c)
                        for c in palette} for members in classes)
    rows = {(a, b): {"pair": (a, b), "target_count": 0, "minimum_cost": None,
                     "best_found_cost": None, "optimal_target_count": 0,
                     "witness": None} for a in range(4) for b in range(4)}
    quotient_adj = [set() for _ in classes]
    impossible = any(u == v for u, v in quotient_edges)
    for u, v in quotient_edges:
        quotient_adj[u].add(v)
        quotient_adj[v].add(u)
    nodes, stopped = 0, False
    # An explicit stack avoids adding an implicit recursion-depth restriction.
    stack = [] if impossible else [()]
    while stack:
        chosen = stack.pop()
        if nodes >= max_nodes:
            stopped = True
            break
        nodes += 1
        index = len(chosen)
        if index == len(classes):
            target = {apex: before[apex]}
            target.update({v: chosen[class_of[v]] for v in interior})
            pair = tuple(target[v] for v in children)
            row = rows[pair]
            cost = sum(class_costs[i][c] for i, c in enumerate(chosen))
            row["target_count"] += 1
            if row["best_found_cost"] is None or cost < row["best_found_cost"]:
                row.update(best_found_cost=cost, optimal_target_count=1, witness=target)
            elif cost == row["best_found_cost"]:
                row["optimal_target_count"] += 1
            continue
        banned = {chosen[i] for i in quotient_adj[index] if i < index}
        stack.extend(chosen + (c,) for c in reversed(palette) if c not in banned)
    for (a, b), row in rows.items():
        trivially_impossible = a == b or before[apex] in (a, b) or impossible
        row["status"] = ("infeasible" if trivially_impossible else "unknown" if stopped
                         else "exact" if row["target_count"] else "infeasible")
        if row["status"] == "exact":
            row["minimum_cost"] = row["best_found_cost"]
        row["counts_complete"] = not stopped or trivially_impossible
        # Incomplete counts describe witnessed targets, never a proved optimum.
        row["targets_seen"] = row["target_count"]
        row["best_found_target_count"] = row["optimal_target_count"]
        if not row["counts_complete"]:
            row["target_count"] = None
            row["optimal_target_count"] = None
    found = [row["best_found_cost"] for row in rows.values() if row["best_found_cost"] is not None]
    return {"status": "unknown" if stopped else "exact", "nodes": nodes, "max_nodes": max_nodes,
            "apex": apex, "fixed_color": before[apex], "palette": palette,
            "vertices": vertices, "initial": before, "weights": costs,
            "base_edges": base, "daughters": children, "equality_witnesses": equalities,
            "classes": classes, "class_of": class_of, "quotient_edges": quotient_edges,
            "class_color_costs": class_costs, "rows": list(rows.values()),
            "target_count": None if stopped else sum(row["target_count"] for row in rows.values()),
            "targets_seen": sum(row["targets_seen"] for row in rows.values()),
            "minimum_cost": None if stopped or not found else min(found),
            "best_found_cost": min(found) if found else None,
            "counts_complete": not stopped,
            "scope": "known three-color shared-edge equality under a fixed universal apex"}

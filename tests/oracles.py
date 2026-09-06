"""Small exhaustive oracles; these do not call the algorithms being checked.

Exponential enumeration is deliberate: it provides an independent correctness
reference for small inputs, never a claim about all planar graphs.
"""

from itertools import product
from math import inf


def brute_colorings(n, edges, precolored=None):
    """List proper vertex colorings directly from all 4**n assignments."""
    fixed = {} if precolored is None else precolored
    return {
        assignment
        for assignment in product(range(4), repeat=n)
        if all(assignment[u] != assignment[v] for u, v in edges)
        and all(assignment[v] == color for v, color in fixed.items())
    }


def xor_defects(n, edges, labels):
    """Compute incidence XOR independently, counting each loop endpoint twice."""
    defects = [0] * n
    for (u, v), label in zip(edges, labels):
        defects[u] ^= label
        defects[v] ^= label
    return tuple(defects)


def brute_repair_table(n, edges, original, terminals):
    """Minimize Hamming cost by enumerating every nonzero edge assignment.

The terminal state is a FLOW defect, not a terminal vertex-color difference.
Both terminal defects must equal q; all other vertex defects must be zero.
"""
    costs = [inf] * 4
    witnesses = [None] * 4
    source, sink = terminals
    for labels in product((1, 2, 3), repeat=len(edges)):
        defects = xor_defects(n, edges, labels)
        if any(defects[v] for v in range(n) if v not in terminals):
            continue
        q = defects[source]
        if defects[sink] != q:
            continue
        cost = sum(before != after for before, after in zip(original, labels))
        if cost < costs[q]:
            costs[q] = cost
            witnesses[q] = labels
    return tuple(costs), tuple(witnesses)


def random_expression(rng, edge_count):
    """Build a deterministic-seed binary SP expression with exactly m leaves."""
    from fourcolor.repair import Edge, Parallel, Series

    if edge_count == 1:
        return Edge(rng.randint(1, 3))
    left_count = rng.randint(1, edge_count - 1)
    left = random_expression(rng, left_count)
    right = random_expression(rng, edge_count - left_count)
    operation = Series if rng.randrange(2) == 0 else Parallel
    return operation(left, right)

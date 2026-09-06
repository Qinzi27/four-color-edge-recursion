"""Exact nonzero Z2 x Z2 FLOW repair on two-terminal series-parallel networks.

State q is the XOR of incident edge labels at EACH terminal, with every
internal vertex balanced.  It is NOT a terminal vertex-color difference.
Consequently series composition adds costs for equal q, while parallel
composition uses min-plus XOR convolution.  The root target q=0 balances all
vertices.  Original and repaired edge labels are always nonzero (1..3).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import inf
from typing import Callable


@dataclass(frozen=True)
class Edge:
    """A two-terminal single edge with an original nonzero group label."""

    label: int

    def __post_init__(self) -> None:
        if type(self.label) is not int or self.label not in (1, 2, 3):
            raise ValueError("edge labels must be integers in 1..3")


@dataclass(frozen=True)
class Series:
    """Identify the left sink with the right source, making it internal."""

    left: SPExpression
    right: SPExpression

    def __post_init__(self) -> None:
        _validate_expression(self.left)
        _validate_expression(self.right)


@dataclass(frozen=True)
class Parallel:
    """Identify both source terminals and both sink terminals."""

    left: SPExpression
    right: SPExpression

    def __post_init__(self) -> None:
        _validate_expression(self.left)
        _validate_expression(self.right)


SPExpression = Edge | Series | Parallel
RepairTable = tuple[int | float, int | float, int | float, int | float]


def _validate_expression(expr: SPExpression) -> None:
    """Keep malformed syntax from failing deep inside a dynamic program."""
    if not isinstance(expr, (Edge, Series, Parallel)):
        raise TypeError("expected an Edge, Series or Parallel expression")


def _add_cost(first: int | float, second: int | float) -> int | float:
    """Add min-plus costs without converting an arbitrarily large int to float."""
    if first == inf or second == inf:
        return inf
    return first + second


def _solver() -> Callable[[SPExpression], RepairTable]:
    """Create an iterative, identity-cached solver with four states per node.

    Identity keys avoid recursively hashing immutable expression trees, which
    would add hidden superlinear work on long skew trees.  Retained references
    keep identity keys valid for the lifetime of this small per-call cache.
    """
    cache: dict[int, RepairTable] = {}
    retained: dict[int, SPExpression] = {}

    def table(expr: SPExpression) -> RepairTable:
        pending = [(expr, False)]
        while pending:
            node, expanded = pending.pop()
            key = id(node)
            if key in cache:
                continue
            retained[key] = node
            if isinstance(node, Edge):
                # Finite costs remain arbitrary-precision integers.  Only the
                # impossible-state sentinel uses a floating-point infinity.
                cache[key] = (inf, int(node.label != 1),
                              int(node.label != 2), int(node.label != 3))
            elif not expanded:
                # Postorder ensures both child tables exist before combining.
                pending.extend(((node, True), (node.right, False), (node.left, False)))
            else:
                left, right = cache[id(node.left)], cache[id(node.right)]
                if isinstance(node, Series):
                    # The new internal junction has defect q_left XOR q_right.
                    cache[key] = tuple(_add_cost(left[q], right[q]) for q in range(4))
                else:
                    # Terminal defects XOR when parallel parts are identified.
                    cache[key] = tuple(min(_add_cost(left[p], right[p ^ q]) for p in range(4))
                                       for q in range(4))
        return cache[id(expr)]
    return table


def repair_table(expr: SPExpression) -> RepairTable:
    """Minimum Hamming costs for terminal-defect targets q=0,1,2,3.

    ``math.inf`` means no assignment of nonzero edge labels meets the target.
    The recurrence has four states per syntax node and uses iterative
    postorder traversal, including for deeply nested expression trees.
    """
    _validate_expression(expr)
    return _solver()(expr)


def realize(
    expr: SPExpression,
) -> tuple[int, tuple[tuple[int, int], ...], tuple[int, ...], tuple[int, int]]:
    """Return (vertex count, edges, original labels, terminals=(0,1)).

    Every Series node creates a fresh internal vertex.  Edges follow a
    left-to-right traversal of leaves, the same order as repair witnesses.
    """
    _validate_expression(expr)
    edges: list[tuple[int, int]] = []
    labels: list[int] = []
    next_vertex = 2

    pending = [(expr, 0, 1)]
    while pending:
        node, source, sink = pending.pop()
        if isinstance(node, Edge):
            edges.append((source, sink))
            labels.append(node.label)
        elif isinstance(node, Series):
            junction = next_vertex
            next_vertex += 1
            pending.extend(((node.right, junction, sink), (node.left, source, junction)))
        else:
            pending.extend(((node.right, source, sink), (node.left, source, sink)))
    return next_vertex, tuple(edges), tuple(labels), (0, 1)


def minimum_repair(expr: SPExpression) -> tuple[int | float, tuple[int, ...]]:
    """Balance ALL vertices with minimum edge-label changes, with a witness.

    Returns ``(math.inf, ())`` if infeasible.  Otherwise labels are in realize's
    edge order.  Zero edge labels are forbidden throughout, so a network with
    a bridge cannot have a feasible balanced-root repair.
    """
    _validate_expression(expr)
    table = _solver()
    cost = table(expr)[0]
    if cost == inf:
        return inf, ()

    witness: list[int] = []
    pending = [(expr, 0)]
    while pending:
        node, q = pending.pop()
        if isinstance(node, Edge):
            witness.append(q)
        elif isinstance(node, Series):
            pending.extend(((node.right, q), (node.left, q)))
        else:
            left, right = table(node.left), table(node.right)
            # Integer order makes ties deterministic and reproducible.
            chosen = min(range(4), key=lambda p: _add_cost(left[p], right[p ^ q]))
            pending.extend(((node.right, chosen ^ q), (node.left, chosen)))
    return int(cost), tuple(witness)

"""Exact four-color enumeration and boundary signatures for finite graphs.

These algorithms may take exponential time.  Graph vertices here represent
color variables (for example, FACES of a plane map), not automatically the
vertices of its primal boundary graph.
"""

from __future__ import annotations

from collections.abc import Hashable, Iterable, Iterator, Sequence


def _vertex_count(n: int) -> None:
    """Reject malformed finite graph sizes before starting a search."""
    if type(n) is not int or n < 0:
        raise ValueError("n must be a nonnegative integer")


def _vertex(vertex: int, n: int) -> None:
    """Check an index without silently accepting negative or boolean indices."""
    if type(vertex) is not int or not 0 <= vertex < n:
        raise ValueError("vertex indices must be integers in 0..n-1")


def colorings(
    n: int,
    edges: Iterable[tuple[int, int]],
    precolored: dict[int, int] | None = None,
) -> Iterator[tuple[int, ...]]:
    """Enumerate all proper 4-colorings, respecting optional fixed colors.

    Parallel edges repeat the same constraint.  A self-loop makes proper
    vertex coloring impossible.  The empty graph has the one empty coloring.
    Inputs are validated eagerly, even though returned solutions are lazy.
    """
    _vertex_count(n)
    adjacency: list[set[int]] = [set() for _ in range(n)]
    has_loop = False
    for edge in edges:
        endpoints = tuple(edge)
        if len(endpoints) != 2:
            raise ValueError("each edge must contain exactly two vertex indices")
        first, second = endpoints
        _vertex(first, n)
        _vertex(second, n)
        has_loop |= first == second
        adjacency[first].add(second)
        adjacency[second].add(first)
    assigned = [-1] * n
    for vertex, color in (precolored or {}).items():
        _vertex(vertex, n)
        if type(color) is not int or not 0 <= color <= 3:
            raise ValueError("precolors must be integers in 0..3")
        assigned[vertex] = color
    if has_loop or any(assigned[v] != -1 and assigned[v] == assigned[w]
                       for v in range(n) for w in adjacency[v]):
        return iter(())

    def visit() -> Iterator[tuple[int, ...]]:
        """Choose the most constrained remaining vertex, then backtrack."""
        chosen = -1
        choices: tuple[int, ...] = ()
        best_key = (5, 0, n)
        for vertex in range(n):
            if assigned[vertex] != -1:
                continue
            forbidden = {assigned[neighbor] for neighbor in adjacency[vertex]}
            available = tuple(color for color in range(4) if color not in forbidden)
            if not available:
                return
            key = (len(available), -len(adjacency[vertex]), vertex)
            if key < best_key:
                chosen, choices, best_key = vertex, available, key
        if chosen == -1:
            yield tuple(assigned)
            return
        for color in choices:
            assigned[chosen] = color
            yield from visit()
        assigned[chosen] = -1

    return visit()


def boundary_signature(
    n: int,
    edges: Iterable[tuple[int, int]],
    boundary: tuple[int, ...],
) -> set[tuple[int, ...]]:
    """Return exactly the extendable labeled colorings of the ordered boundary.

    Repeated boundary vertices are allowed and retain their repeated entries.
    Color names stay globally aligned.  Independently canonicalizing pieces
    before gluing can lose their shared-color alignment and is unsound.
    """
    _vertex_count(n)
    checked_boundary = tuple(boundary)
    for vertex in checked_boundary:
        _vertex(vertex, n)
    return {tuple(colors[vertex] for vertex in checked_boundary)
            for colors in colorings(n, edges)}


def canonical_colors(colors: Sequence[Hashable]) -> tuple[int, ...]:
    """Rename color identities in first-appearance order, starting with 0.

    This is useful for comparing a COMPLETE state up to color permutation.
    It is not a replacement for matching shared labels between two states.
    """
    names: dict[Hashable, int] = {}
    result: list[int] = []
    for color in colors:
        if color not in names:
            names[color] = len(names)
        result.append(names[color])
    return tuple(result)

"""Line-first symbolic naming, without enumerating color assignments.

Edge i is the pair of directed half-edges (darts) 2*i and 2*i+1.
Its name (a,b) gives the left symbol of the first and second dart,
respectively. The input is names plus CCW junction rotations, NOT faces.
Symbols are arbitrary nonempty strings: four is not assumed or derived.

This is an equality-propagation / consistency checker, not a complete
four-color solver or an incremental editing data structure. Connectivity
and genus-zero checks delimit the scope where side orbits represent faces.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


Symbol = str | None
LineName = tuple[Symbol, Symbol]


def _names(values: Sequence[LineName]) -> tuple[LineName, ...]:
    """Copy symbolic names, keeping unknown distinct from every real symbol."""
    pairs = tuple(values)
    if any(isinstance(pair, (str, bytes)) for pair in pairs):
        raise ValueError("a line name must be a pair, not an unstructured string")
    result = tuple(tuple(pair) for pair in pairs)
    if any(len(pair) != 2 for pair in result):
        raise ValueError("each line name must have two ordered side symbols")
    if any(value is not None and (not isinstance(value, str) or not value)
           for pair in result for value in pair):
        raise ValueError("side symbols must be nonempty strings or None")
    return result


@dataclass(frozen=True)
class NameAudit:
    """A check result; unresolved names are not silently assigned a color.

    side_orbits are DERIVED from line connections. A side_mismatch contains
    an oriented boundary-path witness; it is not a closed dual-walk claim.
    Status 'consistent' means a fully specified proper symbolic naming,
    without a palette-size limit. 'underdetermined' makes no four-color
    completion claim. Input contradictions take precedence over unknowns.
    """

    status: str
    names: tuple[LineName, ...]
    side_orbits: tuple[tuple[int, ...], ...]
    unresolved_orbits: tuple[int, ...]
    conflicts: tuple[dict, ...]


def audit_line_names(
    rotation: Sequence[Sequence[int]], names: Sequence[LineName],
) -> NameAudit:
    """Propagate equal side symbols in O(E+V), with no choice or backtracking.

    rotation lists outgoing darts counterclockwise at each junction. For
    every dart d, its left side continues as pred_CCW(d XOR 1). Equalities
    along this permutation propagate a known name around the whole side.
    The topology must be a connected plane map. Disconnected nested curves
    need additional containment data and are deliberately rejected here.

    A dangling line has both darts in one side orbit and must have equal
    side symbols. A genuine separator has distinct side orbits and must
    have different symbols when both have been specified.
    """
    checked = _names(names)
    turns = tuple(tuple(turn) for turn in rotation)
    if not turns:
        raise ValueError("at least one junction is required")
    count = 2 * len(checked)
    predecessor = [-1] * count
    owner = [-1] * count
    for vertex, turn in enumerate(turns):
        for index, dart in enumerate(turn):
            if type(dart) is not int or not 0 <= dart < count:
                raise ValueError("dart IDs must be integers in 0..2E-1")
            if owner[dart] != -1:
                raise ValueError("each dart must occur exactly once")
            owner[dart] = vertex
            predecessor[dart] = turn[index - 1]
    if any(vertex == -1 for vertex in owner):
        raise ValueError("each dart must occur exactly once")

    # Derive endpoint connectivity from paired darts, without region objects.
    neighbors: list[list[int]] = [[] for _ in turns]
    for edge in range(len(checked)):
        first, second = owner[2 * edge], owner[2 * edge + 1]
        neighbors[first].append(second)
        neighbors[second].append(first)
    reached = {0}
    pending = [0]
    while pending:
        for neighbor in neighbors[pending.pop()]:
            if neighbor not in reached:
                reached.add(neighbor)
                pending.append(neighbor)
    if len(reached) != len(turns):
        raise ValueError("disconnected lines need explicit containment data")

    successor = tuple(predecessor[dart ^ 1] for dart in range(count))
    side_class = [-1] * count
    orbits: list[tuple[int, ...]] = []
    for start in range(count):
        if side_class[start] != -1:
            continue
        orbit: list[int] = []
        dart = start
        while side_class[dart] == -1:
            side_class[dart] = len(orbits)
            orbit.append(dart)
            dart = successor[dart]
        orbits.append(tuple(orbit))
    if not count:
        orbits.append(())  # The isolated-junction case has one unnamed side.
    if len(turns) - len(checked) + len(orbits) != 2:
        raise ValueError("junction rotations do not define a plane map")

    original = [value for pair in checked for value in pair]
    propagated = list(original)
    unresolved: list[int] = []
    conflicts: list[dict] = []
    for side_id, orbit in enumerate(orbits):
        anchors = [(i, original[dart]) for i, dart in enumerate(orbit)
                   if original[dart] is not None]
        if not anchors:
            unresolved.append(side_id)
            continue
        first_index, value = anchors[0]
        mismatch = next(((i, other) for i, other in anchors if other != value), None)
        if mismatch is not None:
            last_index, other = mismatch
            conflicts.append({
                "kind": "side_mismatch", "side_orbit": side_id,
                "symbols": (value, other),
                "darts": orbit[first_index:last_index + 1],
            })
            continue
        for dart in orbit:
            propagated[dart] = value

    for edge in range(len(checked)):
        first, second = 2 * edge, 2 * edge + 1
        if (side_class[first] != side_class[second]
                and propagated[first] is not None
                and propagated[first] == propagated[second]):
            conflicts.append({"kind": "separator_equal", "edge": edge,
                              "symbol": propagated[first], "darts": (first, second)})

    status = "conflict" if conflicts else "underdetermined" if unresolved else "consistent"
    completed = tuple((propagated[i], propagated[i + 1]) for i in range(0, count, 2))
    return NameAudit(status, completed, tuple(orbits), tuple(unresolved), tuple(conflicts))


def canonical_line_names(names: Sequence[LineName]) -> tuple[tuple[int | None, int | None], ...]:
    """Remove global symbol-renaming duplicates for ONE fixed ordered map.

    This is not graph-isomorphism canonicalization, and separately normalized
    pieces must not be glued without restoring their common symbol alignment.
    Distinct lines keep their identities even when their names are identical.
    """
    checked = _names(names)
    numbering: dict[str, int] = {}
    result = []
    for pair in checked:
        renamed = []
        for symbol in pair:
            if symbol is None:
                renamed.append(None)
            else:
                if symbol not in numbering:
                    numbering[symbol] = len(numbering)
                renamed.append(numbering[symbol])
        result.append(tuple(renamed))
    return tuple(result)


def branch_right(a: str, b: str, c: str) -> dict:
    """Propose a right-side T-junction template, preserving recursive history.

    The main line enters with (a,b) and continues with (a,c). The new branch
    points OUT of the junction into the original right side, so its name is
    (c,b), not (b,c). Reversing it reverses its name. The template describes
    three locally distinct sectors, not a standalone globally valid T-tree;
    a dangling branch alone does not separate a new region. c is supplied,
    never secretly chosen by a solver.
    """
    checked = _names(((a, b), (b, c)))
    if any(value is None for pair in checked for value in pair) or len({a, b, c}) != 3:
        raise ValueError("this three-sector template needs three distinct known symbols")
    return {"incoming": (a, b), "continuation": (a, c),
            "branch": (c, b), "history": (a, (b, c))}

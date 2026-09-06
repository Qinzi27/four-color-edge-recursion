"""Executable corner-based construction of embedded maps and face histories.

An outgoing dart names the corner on its LEFT face.  Inserting a new outgoing
dart immediately after it in the CCW rotation places the new edge in that
corner.  ``extend`` adds a pendant edge; ``close_split`` joins two occurrences
on one face and splits it.  These are combinatorial operations: no coordinates
or straight-line geometric realization are assumed.

The operations preserve topology, not a previously chosen coloring.  A face
split can require recoloring existing faces.  Initial maps plus operation logs
are reproducible construction histories, not proofs that arbitrary local
color choices will always extend.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .embedding import PlaneMap
from .examples import triangle_map


def _corner(plane_map: PlaneMap, dart: int) -> tuple[str, int]:
    """Resolve a corner to its tail and old left-face ID, validating the ID."""
    if not isinstance(plane_map, PlaneMap):
        raise TypeError("plane_map must be a PlaneMap")
    if type(dart) is not int or not 0 <= dart < 2 * len(plane_map.edges):
        raise ValueError("corner dart must be an integer in the map's dart range")
    return plane_map.edges[dart // 2][dart % 2], plane_map.face_of_dart[dart]


def _insert_after(
    rotation: Mapping[str, tuple[int, ...]],
    insertions: dict[int, int],
) -> dict[str, tuple[int, ...]]:
    """Insert once per selected old dart without shifting a second corner.

    Two corner occurrences can belong to one vertex.  Rebuilding each cyclic
    list from original darts avoids index-shift errors in that case.
    """
    result: dict[str, tuple[int, ...]] = {}
    for vertex, darts in rotation.items():
        updated: list[int] = []
        for dart in darts:
            updated.append(dart)
            if dart in insertions:
                updated.append(insertions[dart])
        result[vertex] = tuple(updated)
    return result


def extend(plane_map: PlaneMap, corner_dart: int, new_vertex: str) -> PlaneMap:
    """Add a pendant edge at one face corner, leaving the face count unchanged.

    The new vertex must be a fresh string label.  The new edge is appended in
    tail-to-new-vertex direction, preserving all preexisting edge and dart IDs.
    A lone isolated vertex has no dart corner and is outside this operation's
    domain; a nonempty initial map must be supplied to use this corner API.
    """
    tail, _ = _corner(plane_map, corner_dart)
    if not isinstance(new_vertex, str):
        raise ValueError("new_vertex must be a string")
    if new_vertex in plane_map.rotation:
        raise ValueError("new_vertex must not already occur in the map")
    new_dart = 2 * len(plane_map.edges)
    rotation = _insert_after(plane_map.rotation, {corner_dart: new_dart})
    rotation[new_vertex] = (new_dart + 1,)
    result = PlaneMap(plane_map.edges + ((tail, new_vertex),), rotation)
    if len(result.faces) != len(plane_map.faces):
        raise RuntimeError("pendant extension unexpectedly changed the face count")
    return result


def close_split(plane_map: PlaneMap, start_dart: int, end_dart: int) -> PlaneMap:
    """Join two distinct corner occurrences of one face, adding exactly a face.

    Endpoints may be the same vertex, provided the dart occurrences differ;
    this creates a loop.  Different faces cannot be joined by this operation.
    The appended edge points from the start corner's tail to the end's tail.
    """
    start, first_face = _corner(plane_map, start_dart)
    end, second_face = _corner(plane_map, end_dart)
    if start_dart == end_dart:
        raise ValueError("close_split requires two distinct corner dart occurrences")
    if first_face != second_face:
        raise ValueError("close_split corners must lie on the same face")
    new_dart = 2 * len(plane_map.edges)
    rotation = _insert_after(plane_map.rotation,
                             {start_dart: new_dart, end_dart: new_dart + 1})
    result = PlaneMap(plane_map.edges + ((start, end),), rotation)
    if len(result.faces) != len(plane_map.faces) + 1:
        raise RuntimeError("close_split did not increase the face count by one")
    return result


def _counts(plane_map: PlaneMap) -> dict[str, int]:
    """Keep operation logs explicit about Euler-relevant graph sizes."""
    return {"vertices": len(plane_map.vertices), "edges": len(plane_map.edges),
            "faces": len(plane_map.faces)}


def replay(
    initial: PlaneMap,
    operations: Sequence[dict],
) -> tuple[PlaneMap, tuple[dict, ...]]:
    """Apply operations and return the final map plus deterministic face logs.

    Supported dictionaries are ``{"kind": "extend", "corner": d,
    "vertex": "new"}`` and ``{"kind": "close_split", "start": d,
    "end": e}``.  Unknown or missing fields are rejected.

    A log maps each old face to the new face IDs containing its original
    darts.  Faces may be renumbered, so numerical identity is never assumed.
    Each split daughter contains original darts because the two selected
    occurrences are distinct.  Replay requires the initial map as well as the
    operation dictionaries; a split tree alone does not encode an embedding.
    """
    if not isinstance(initial, PlaneMap):
        raise TypeError("initial must be a PlaneMap")
    current = initial
    logs: list[dict] = []
    for step, operation in enumerate(operations, start=1):
        if not isinstance(operation, dict):
            raise ValueError(f"operation {step} must be a dictionary")
        kind = operation.get("kind")
        before = current
        if kind == "extend":
            if set(operation) != {"kind", "corner", "vertex"}:
                raise ValueError("extend requires exactly kind, corner and vertex fields")
            _, parent_face = _corner(before, operation["corner"])
            current = extend(before, operation["corner"], operation["vertex"])
        elif kind == "close_split":
            if set(operation) != {"kind", "start", "end"}:
                raise ValueError("close_split requires exactly kind, start and end fields")
            _, parent_face = _corner(before, operation["start"])
            current = close_split(before, operation["start"], operation["end"])
        else:
            raise ValueError(f"unknown operation kind at step {step}: {kind!r}")

        # Every old dart keeps its ID, making ancestry independently checkable.
        descendants = {face_id: sorted({current.face_of_dart[dart] for dart in darts})
                       for face_id, darts in enumerate(before.faces)}
        logs.append({"step": step, "operation": dict(operation),
                     "before": _counts(before), "after": _counts(current),
                     "parent_face": parent_face, "face_descendants": descendants,
                     "created_edge": len(before.edges)})
    return current, tuple(logs)


def tetrahedron_history() -> tuple[PlaneMap, tuple[dict, ...]]:
    """Build a tetrahedral map from a triangle with face counts 2 -> 2 -> 3 -> 4.

    First add an interior dangling edge A--O, then join O to B and C.  The
    final O corner is found from the embedding rather than guessed from IDs.
    The result needs four face colors; the intermediate dangling line alone
    creates no new region.
    """
    initial = triangle_map()
    operations = [{"kind": "extend", "corner": 0, "vertex": "O"},
                  {"kind": "close_split", "start": 7, "end": 2}]
    partial, _ = replay(initial, operations)
    c_corner = 4
    face = partial.face_of_dart[c_corner]
    candidates = [dart for dart in partial.rotation["O"]
                  if partial.face_of_dart[dart] == face]
    if not candidates:
        raise RuntimeError("tetrahedron construction lost the O-to-C face corner")
    operations.append({"kind": "close_split", "start": min(candidates), "end": c_corner})
    return initial, tuple(operations)

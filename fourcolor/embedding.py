"""Connected plane maps represented by darts and a counterclockwise rotation.

Edge i has dart 2*i in its listed direction and dart 2*i+1 in the reverse
direction.  A face is the orbit of predecessor_CCW(twin(d)).  Thus face_of_dart
records the face on a dart's left.  Loops, parallel edges and bridges are
supported; a bridge has the SAME face on both sides.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, Sequence


def _group_values(values: Sequence[int], size: int, name: str) -> tuple[int, ...]:
    """Validate a finite vector in Z2 x Z2, rejecting bool-as-int surprises."""
    result = tuple(values)
    if len(result) != size:
        raise ValueError(f"{name} must contain exactly {size} entries")
    if any(type(value) is not int or not 0 <= value <= 3 for value in result):
        raise ValueError(f"{name} entries must be integers in 0..3")
    return result


@dataclass(frozen=True)
class PlaneMap:
    """A connected orientable rotation system with genus zero.

    ``rotation[v]`` lists ALL darts with tail v, once each, counterclockwise.
    Face and vertex identifiers are deterministic for the supplied order.
    Input containers are copied so later caller mutations cannot corrupt the
    validated embedding.  A singleton ``rotation={"v": ()}`` has one empty
    face.  Empty and disconnected maps are intentionally outside this API.
    """

    edges: tuple[tuple[str, str], ...]
    rotation: Mapping[str, tuple[int, ...]]
    vertices: tuple[str, ...] = field(init=False)
    faces: tuple[tuple[int, ...], ...] = field(init=False)
    face_of_dart: tuple[int, ...] = field(init=False)

    def __post_init__(self) -> None:
        """Validate incidence, connectivity and the Euler characteristic."""
        edges = tuple(tuple(edge) for edge in self.edges)
        rotation = {vertex: tuple(darts) for vertex, darts in self.rotation.items()}
        if not rotation or any(not isinstance(vertex, str) for vertex in rotation):
            raise ValueError("rotation must contain at least one string vertex")
        if any(len(edge) != 2 for edge in edges):
            raise ValueError("each edge must have exactly two endpoints")
        if any(not isinstance(vertex, str) or vertex not in rotation
               for edge in edges for vertex in edge):
            raise ValueError("every edge endpoint must be a vertex in rotation")

        dart_count = 2 * len(edges)
        seen: set[int] = set()
        predecessor = [-1] * dart_count
        for vertex, darts in rotation.items():
            for index, dart in enumerate(darts):
                if type(dart) is not int or not 0 <= dart < dart_count:
                    raise ValueError("rotation dart IDs must be integers in range")
                if dart in seen:
                    raise ValueError("every dart must occur exactly once in rotation")
                if edges[dart // 2][dart % 2] != vertex:
                    raise ValueError(f"dart {dart} has the wrong tail at {vertex!r}")
                seen.add(dart)
                predecessor[dart] = darts[index - 1]
        if len(seen) != dart_count:
            raise ValueError("every dart must occur exactly once in rotation")

        # Connectivity refers to the underlying graph, including isolated
        # vertices declared in the rotation system.
        adjacency: dict[str, set[str]] = {vertex: set() for vertex in rotation}
        for first, second in edges:
            adjacency[first].add(second)
            adjacency[second].add(first)
        root = next(iter(rotation))
        reached = {root}
        pending = [root]
        while pending:
            vertex = pending.pop()
            for neighbor in adjacency[vertex] - reached:
                reached.add(neighbor)
                pending.append(neighbor)
        if len(reached) != len(rotation):
            raise ValueError("PlaneMap requires a connected underlying graph")

        faces: list[tuple[int, ...]] = []
        face_of_dart = [-1] * dart_count
        for start in range(dart_count):
            if face_of_dart[start] != -1:
                continue
            face_id = len(faces)
            boundary: list[int] = []
            dart = start
            while face_of_dart[dart] == -1:
                face_of_dart[dart] = face_id
                boundary.append(dart)
                dart = predecessor[dart ^ 1]
            if dart != start:
                raise ValueError("invalid face permutation")
            faces.append(tuple(boundary))
        if dart_count == 0:
            faces.append(())
        if len(rotation) - len(edges) + len(faces) != 2:
            raise ValueError("rotation is not a plane embedding: Euler V-E+F != 2")

        object.__setattr__(self, "edges", edges)
        object.__setattr__(self, "rotation", MappingProxyType(rotation))
        object.__setattr__(self, "vertices", tuple(rotation))
        object.__setattr__(self, "faces", tuple(faces))
        object.__setattr__(self, "face_of_dart", tuple(face_of_dart))

    def shores(self, edge_id: int) -> tuple[int, int]:
        """Return (left face, right face) for the listed direction of an edge."""
        if type(edge_id) is not int or not 0 <= edge_id < len(self.edges):
            raise ValueError("edge_id must be an integer in range")
        return self.face_of_dart[2 * edge_id], self.face_of_dart[2 * edge_id + 1]

    def check_coloring(self, colors: Sequence[int]) -> bool:
        """Check a proper face coloring; a bridge creates no adjacency constraint."""
        try:
            checked = _group_values(colors, len(self.faces), "colors")
        except (TypeError, ValueError):
            return False
        return all(left == right or checked[left] != checked[right]
                   for left, right in (self.shores(i) for i in range(len(self.edges))))

    def differences(self, colors: Sequence[int]) -> tuple[int, ...]:
        """Return left XOR right, requiring a proper face coloring first.

        Non-bridge edges have differences 1..3.  Bridges necessarily have 0;
        excluding zero on bridges would incorrectly exclude valid plane maps.
        """
        checked = _group_values(colors, len(self.faces), "colors")
        if not self.check_coloring(checked):
            raise ValueError("colors are not a proper face coloring")
        return tuple(checked[left] ^ checked[right]
                     for left, right in (self.shores(i) for i in range(len(self.edges))))

    def integrate(self, differences: Sequence[int]) -> tuple[int, ...]:
        """Recover face colors, fixing face 0 to color 0.

        Propagation takes place in the DUAL graph: a move across primal edge e
        changes the face color by differences[e].  Conflicting dual paths are
        rejected.  Every valid solution differs by a common XOR translation.
        """
        checked = _group_values(differences, len(self.edges), "differences")
        dual: list[list[tuple[int, int, int]]] = [[] for _ in self.faces]
        for edge_id, delta in enumerate(checked):
            left, right = self.shores(edge_id)
            if left == right:
                if delta != 0:
                    raise ValueError(f"edge {edge_id} has one face on both sides; difference must be 0")
                continue
            if delta == 0:
                raise ValueError(f"edge {edge_id} separates distinct faces; difference must be nonzero")
            dual[left].append((right, delta, edge_id))
            dual[right].append((left, delta, edge_id))

        colors: list[int | None] = [None] * len(self.faces)
        colors[0] = 0
        pending: deque[int] = deque([0])
        while pending:
            face = pending.popleft()
            current = colors[face]
            assert current is not None
            for neighbor, delta, edge_id in dual[face]:
                proposed = current ^ delta
                if colors[neighbor] is None:
                    colors[neighbor] = proposed
                    pending.append(neighbor)
                elif colors[neighbor] != proposed:
                    raise ValueError(f"inconsistent closed dual walk detected across edge {edge_id}")
        if any(color is None for color in colors):
            # A connected plane map has a connected dual; reaching this case
            # would indicate an implementation error, not a coloring failure.
            raise RuntimeError("unexpected disconnected dual graph")
        return tuple(int(color) for color in colors if color is not None)


def vertex_defects(plane_map: PlaneMap, differences: Sequence[int]) -> dict[str, int]:
    """XOR incident dart labels at each primal vertex; a loop counts twice.

    This accepts arbitrary group labels so it can diagnose invalid proposals.
    Vanishing defects plus the shore nonzero/zero conditions characterize
    integrable proper face differences for the connected plane maps above.
    """
    checked = _group_values(differences, len(plane_map.edges), "differences")
    defects: dict[str, int] = {}
    for vertex in plane_map.vertices:
        defect = 0
        for dart in plane_map.rotation[vertex]:
            defect ^= checked[dart // 2]
        defects[vertex] = defect
    return defects

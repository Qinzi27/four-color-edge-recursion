"""Declare bounded map-face fixtures for comparing inside/outside traversal.

Every returned vertex ID is a MAP FACE, never a primal graph vertex.  Edges
are distinct unordered face-adjacency constraints; bridges and virtual drawing
connectors contribute no self-inequality.  These fixtures choose every face of
maximum declared depth, without selecting a start by its coloring outcome.

Nested Jordan-loop trees have genuine containment depth.  The other families
use shortest face-adjacency distance from the exterior as an explicit depth
proxy; that proxy is not a unique geometric containment or a growth history.
No previous report is modified.  Only the standard library is required.
"""

from collections import deque
import json
import math
from pathlib import Path
import random

from fourcolor.embedding import PlaneMap
from scripts.validate_circle_repair import family_graph


ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_REPORT = "outputs/circle-rank-2026-09-20.json"
RANDOM_TREE_SEED = 20260920
DUAL_DEPTH = (
    "Shortest-path distance in the simple face-adjacency graph from the "
    "unbounded exterior face; a declared depth proxy, not unique containment."
)
NESTING_DEPTH = (
    "Number of nested Jordan boundaries separating the face from the "
    "unbounded exterior; equal to rooted-tree distance for this family."
)


def _require(condition, message):
    """Keep fixture audits active even when Python optimization is enabled."""
    if not condition:
        raise ValueError(message)


def _depths(n, edges, outer):
    """Compute every face distance and reject disconnected fixture graphs."""
    adjacency = [[] for _ in range(n)]
    for first, second in edges:
        adjacency[first].append(second)
        adjacency[second].append(first)
    distances = [-1] * n
    distances[outer] = 0
    pending = deque([outer])
    while pending:
        first = pending.popleft()
        for second in adjacency[first]:
            if distances[second] == -1:
                distances[second] = distances[first] + 1
                pending.append(second)
    _require(all(value >= 0 for value in distances), "face graph is disconnected")
    return distances


def _case(key, family, n, edges, outer, definition, geometry):
    """Normalize a case, keeping all deepest starts in deterministic ID order."""
    _require(type(n) is int and 2 <= n <= 17, "face-count bound violated")
    _require(type(outer) is int and 0 <= outer < n, "invalid exterior face")
    constraints = sorted({tuple(sorted(edge)) for edge in edges})
    _require(all(len(edge) == 2 and edge[0] != edge[1] and
                 all(type(face) is int and 0 <= face < n for face in edge)
                 for edge in constraints), "invalid face adjacency")
    depths = _depths(n, constraints, outer)
    deepest = max(depths)
    return {
        "key": key, "family": family, "n": n,
        "edges": [list(edge) for edge in constraints], "outer": outer,
        "inner_candidates": [face for face in range(n) if depths[face] == deepest],
        "depths": depths, "depth_definition": definition,
        "geometry": geometry,
    }


def _dual(plane, excluded=()):
    """Extract simple face constraints, omitting same-face primal edges."""
    excluded = set(excluded)
    constraints = set()
    for index in range(len(plane.edges)):
        first, second = plane.shores(index)
        if index not in excluded and first != second:
            constraints.add(tuple(sorted((first, second))))
    return sorted(constraints)


def _plane_evidence(plane, outer, extra=None):
    """Retain the rotation and dart faces needed to independently reconstruct."""
    evidence = {
        "kind": "verified-connected-plane-map",
        "primal_edges": [list(edge) for edge in plane.edges],
        "primal_rotation": {vertex: list(darts) for vertex, darts in plane.rotation.items()},
        "face_darts": [list(face) for face in plane.faces],
        "outer_face": outer,
        "euler": {"V": len(plane.vertices), "E": len(plane.edges),
                  "F": len(plane.faces), "components": 1,
                  "V_minus_E_plus_F": len(plane.vertices) - len(plane.edges) + len(plane.faces)},
        "plane_map_verified": True,
    }
    if extra:
        evidence.update(extra)
    return evidence


def _original_cases():
    """Reconstruct all eight saved drawings and their exact engine face IDs."""
    report = json.loads((ROOT / ORIGINAL_REPORT).read_text(encoding="utf-8"))
    records = report["results"]
    _require(len(records) == 8, "original report no longer has eight cases")
    _require({record["blue_mask"] for record in records} == set(range(8)),
             "original report blue masks changed")
    result = []
    for record in records:
        geometry = record["geometry"]
        edges = tuple((str(edge["a"]), str(edge["b"])) for edge in geometry["edges"])
        rotation = {str(vertex): tuple(darts)
                    for vertex, darts in enumerate(geometry["rotation"])}
        plane = PlaneMap(edges, rotation)
        _require(list(plane.face_of_dart) == geometry["faceOfDart"],
                 "original Python and saved face IDs disagree")
        virtual = [index for index, edge in enumerate(geometry["edges"]) if edge["virtual"]]
        _require(all(plane.shores(index)[0] == plane.shores(index)[1] for index in virtual),
                 "a virtual connector unexpectedly separates faces")
        constraints = _dual(plane, virtual)
        _require(constraints == [tuple(edge) for edge in record["simple_dual_edges"]],
                 "original face constraints changed")
        outer = record["role_face_ids"]["outer"]
        _require(outer == geometry["outerFace"], "original exterior IDs disagree")
        evidence = _plane_evidence(plane, outer, {
            "source_report": ORIGINAL_REPORT, "source_case_key": record["key"],
            "blue_mask": record["blue_mask"],
            "role_face_ids": record["role_face_ids"],
            "virtual_edge_ids_excluded_from_constraints": virtual,
            "real_bridge_edge_ids": geometry["real_bridge_edge_ids"],
            "embedding_note": "Virtual bridges connect drawing components for face traversal only.",
        })
        case = _case(record["key"], "original-blue-subsets", len(plane.faces),
                     constraints, outer, DUAL_DEPTH, evidence)
        islands = sorted([record["role_face_ids"]["left_island"],
                          record["role_face_ids"]["right_island"]])
        _require(case["inner_candidates"] == islands, "deepest original faces changed")
        result.append(case)
    return result


def _nesting_case(key, parents, subtype, parameters):
    """Realize a rooted tree by one separate Jordan loop per nonroot face.

    Each loop can be represented by a triangle inside its parent's region;
    sibling triangles can be disjoint.  The region graph is exactly the tree.
    This is a constructive topological fixture, not a sampled natural map.
    """
    _require(parents[0] is None and
             all(type(parent) is int and 0 <= parent < face
                 for face, parent in enumerate(parents[1:], start=1)),
             "nesting parents must precede children")
    n = len(parents)
    edges = [(parent, face) for face, parent in enumerate(parents) if parent is not None]
    loops = n - 1
    evidence = {
        "kind": "constructive-nested-disjoint-jordan-loops", "subtype": subtype,
        "parents": parents, "parameters": parameters,
        "realization": (
            "Place one simple triangle for each nonroot face inside its parent's region; "
            "sibling triangles are disjoint. Each triangle has its parent outside and "
            "its child region immediately inside."
        ),
        "euler": {"V": 3 * loops, "E": 3 * loops, "F": n,
                  "components": loops, "V_minus_E_plus_F": n,
                  "one_plus_components": 1 + loops},
        "topological_construction_verified": True,
    }
    return _case(key, "nested-jordan-tree", n, edges, 0, NESTING_DEPTH, evidence)


def _nesting_cases():
    """Build declared chains, two arms, balanced trees, and seeded stress cases."""
    result = []
    # Two arms also include five-face paths with the exterior in different positions.
    for first_length in range(1, 5):
        for second_length in range(1, 5):
            parents = [None]
            for length in (first_length, second_length):
                parent = 0
                for _ in range(length):
                    parents.append(parent)
                    parent = len(parents) - 1
            result.append(_nesting_case(
                f"nested-arms-{first_length}-{second_length}", parents, "two-arms",
                {"arm_edge_lengths": [first_length, second_length]}))
    for length in range(2, 9):
        parents = [None] + list(range(length))
        result.append(_nesting_case(f"nested-chain-{length}", parents, "single-chain",
                                    {"chain_edge_length": length}))
    for depth in (2, 3):
        n = 2 ** (depth + 1) - 1
        parents = [None] + [(face - 1) // 2 for face in range(1, n)]
        result.append(_nesting_case(f"nested-binary-depth-{depth}", parents,
                                    "balanced-binary", {"maximum_nesting_depth": depth}))
    generator = random.Random(RANDOM_TREE_SEED)
    for index in range(12):
        n = 8 + index % 8
        parents = [None] + [generator.randrange(face) for face in range(1, n)]
        result.append(_nesting_case(
            f"nested-seeded-{index:02d}-faces{n}", parents, "seeded-recursive-tree",
            {"seed": RANDOM_TREE_SEED, "sequence_index": index,
             "sampling": "Each face i chooses a parent uniformly among IDs 0..i-1.",
             "scope_note": "Synthetic stress cases, not a natural-map distribution."}))
    return result


def _wheel_prism_cases():
    """Convert existing explicit primal embeddings to actual map-face graphs."""
    result = []
    for family, sizes in (("wheel", range(3, 10)), ("prism", range(3, 8))):
        for rim in sizes:
            graph = family_graph(family, rim)
            plane = PlaneMap(tuple((str(a), str(b)) for a, b in graph["edges"]), graph["rotation"])
            face_by_edges = {tuple(sorted(dart // 2 for dart in face)): face_id
                             for face_id, face in enumerate(plane.faces)}
            outer = face_by_edges[tuple(range(rim))]
            evidence = _plane_evidence(plane, outer, {
                "source_generator": "scripts.validate_circle_repair.family_graph",
                "primal_family": family, "primal_rim_size": rim,
                "declared_outer_ring_edge_ids": list(range(rim)),
            })
            case = _case(f"face-dual-{family}-rim{rim}", f"{family}-face-dual",
                         len(plane.faces), _dual(plane), outer, DUAL_DEPTH, evidence)
            if family == "prism":
                inner = face_by_edges[tuple(range(rim, 2 * rim))]
                evidence["geometric_inner_ring_face"] = inner
                _require(case["inner_candidates"] == [inner], "prism deepest face mismatch")
            else:
                _require(case["inner_candidates"] == [face for face in range(len(plane.faces))
                                                       if face != outer],
                         "wheel deepest faces mismatch")
            result.append(case)
    return result


def _grid_case(rows, columns):
    """Check a rectangular cell map via a straight-line primal rotation system."""
    coordinates = {row * (columns + 1) + column: (column, row)
                   for row in range(rows + 1) for column in range(columns + 1)}
    edges = []
    for row in range(rows + 1):
        for column in range(columns):
            first = row * (columns + 1) + column
            edges.append((first, first + 1))
    for row in range(rows):
        for column in range(columns + 1):
            first = row * (columns + 1) + column
            edges.append((first, first + columns + 1))
    incident = {vertex: [] for vertex in coordinates}
    for index, (first, second) in enumerate(edges):
        incident[first].append(2 * index)
        incident[second].append(2 * index + 1)
    rotation = {}
    for vertex, darts in incident.items():
        x, y = coordinates[vertex]
        rotation[str(vertex)] = tuple(sorted(darts, key=lambda dart: math.atan2(
            coordinates[edges[dart // 2][1 - dart % 2]][1] - y,
            coordinates[edges[dart // 2][1 - dart % 2]][0] - x)))
    plane = PlaneMap(tuple((str(a), str(b)) for a, b in edges), rotation)
    areas = []
    for face in plane.faces:
        points = [coordinates[edges[dart // 2][dart % 2]] for dart in face]
        double_area = sum(x * points[(index + 1) % len(points)][1] -
                          y * points[(index + 1) % len(points)][0]
                          for index, (x, y) in enumerate(points))
        areas.append(double_area / 2)
    outers = [face for face, area in enumerate(areas) if area < 0]
    _require(len(outers) == 1, "grid exterior orientation ambiguous")
    outer = outers[0]
    _require(len(plane.faces) == rows * columns + 1, "grid face count mismatch")
    _require(areas[outer] == -rows * columns and
             all(area == 1 for face, area in enumerate(areas) if face != outer),
             "grid cell area audit failed")
    evidence = _plane_evidence(plane, outer, {
        "grid_cell_rows": rows, "grid_cell_columns": columns,
        "primal_coordinates": {str(vertex): list(point) for vertex, point in coordinates.items()},
        "coordinate_note": "Abstract unit cells; these are not measured spatial data.",
        "face_signed_areas": areas,
        "outer_identification": "Unique negative-area dart face with counterclockwise rotation.",
    })
    return _case(f"rectangular-cells-{rows}x{columns}", "rectangular-cell-map",
                 len(plane.faces), _dual(plane), outer, DUAL_DEPTH, evidence)


def make_cases():
    """Return the complete predeclared 63-case collection, with no outcome filter."""
    cases = _original_cases() + _nesting_cases() + _wheel_prism_cases()
    cases += [_grid_case(rows, columns) for rows, columns in
              ((2, 2), (2, 3), (2, 4), (3, 3), (3, 4), (4, 4))]
    _require(len(cases) == 63, "predeclared fixture count changed")
    _require(len({case["key"] for case in cases}) == len(cases), "fixture keys collide")
    return cases

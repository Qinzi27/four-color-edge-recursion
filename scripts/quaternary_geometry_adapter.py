"""Adapt current drawing regions to the separate quaternary contact language.

Node first connects disconnected drawn components using virtual graph bridges.
Those bridges preserve the global regions, allowing PlaneMap's connected-map
face orbits to represent regions with several real boundary components. We
remove virtual darts only when recording real boundary walks, never to invent
one new region for each disconnected boundary walk.

No coloring or candidate propagation is performed here. Default anchors and
states are empty; callers must explicitly supply any naming assumptions.
"""

from collections import defaultdict
from copy import deepcopy
from itertools import combinations
import json
from math import hypot, isfinite
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.embedding import PlaneMap
from fourcolor.whole_lines import build_whole_lines
from scripts.current_corpus import stroke_set_key
from scripts.quaternary_contact_model import NameState
from scripts.validate_global_restart import digest, export_geometries


def _require(condition, message):
    """Reject malformed geometry even when Python assertions are disabled."""
    if not condition:
        raise ValueError(message)


def _drawing_input(drawing):
    """Preserve stroke indices/directions, while excluding old names from geometry."""
    _require(isinstance(drawing, dict) and isinstance(drawing.get("strokes"), list),
             "drawing requires a strokes array")
    try:
        json.dumps(drawing, allow_nan=False)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("drawing must be finite JSON data") from exc
    if "schemaVersion" in drawing:
        _require(type(drawing["schemaVersion"]) is int and drawing["schemaVersion"] == 1,
                 "unsupported drawing schemaVersion")
    frame = drawing.get("frame", {"width": 900, "height": 600})
    _require(isinstance(frame, dict)
             and all(type(frame.get(k)) in (int, float) and frame[k] == value
                     for k, value in (("width", 900), ("height", 600))),
             "drawing frame must be 900 by 600")
    strokes = []
    for item in drawing["strokes"]:
        _require(isinstance(item, dict) and "a" in item and "b" in item, "stroke needs a and b")
        for key in ("a", "b"):
            point = item[key]
            _require(isinstance(point, list) and len(point) == 2
                     and all(type(value) in (int, float) and isfinite(value) for value in point),
                     "stroke endpoints must be finite numeric coordinate pairs")
            _require(0 <= point[0] <= 900 and 0 <= point[1] <= 600, "stroke outside frame")
        _require(item["a"] != item["b"], "zero-length stroke")
        strokes.append({"a": list(item["a"]), "b": list(item["b"])})
    return {"frame": {"width": 900, "height": 600}, "strokes": strokes}


def _validated_plane(geometry, drawing):
    """Rebuild the augmented rotation system and check global face identities."""
    _require(isinstance(geometry, dict), "geometry must be an exported object")
    required = {"vertices", "edges", "rotation", "faceOfDart", "faces", "outerFace", "original"}
    _require(required <= set(geometry), "incomplete geometry export")
    vertices, edges = geometry["vertices"], geometry["edges"]
    _require(isinstance(vertices, list) and bool(vertices) and isinstance(edges, list), "invalid graph arrays")
    for point in vertices:
        _require(isinstance(point, list) and len(point) == 2
                 and all(type(v) in (int, float) and isfinite(v) for v in point), "invalid vertex coordinates")
    for edge in edges:
        _require(isinstance(edge, dict) and {"a", "b", "virtual", "frame", "sources"} <= set(edge),
                 "incomplete atomic edge")
        _require(all(type(edge[end]) is int and 0 <= edge[end] < len(vertices) for end in ("a", "b"))
                 and edge["a"] != edge["b"] and vertices[edge["a"]] != vertices[edge["b"]],
                 "invalid atomic edge endpoints")
        _require(type(edge["virtual"]) is bool and type(edge["frame"]) is bool, "edge flags must be booleans")
        sources = edge["sources"]
        _require(isinstance(sources, list) and all(type(s) is int and s >= 0 for s in sources)
                 and len(sources) == len(set(sources)), "invalid original-stroke references")
        _require(not edge["virtual"] or (not edge["frame"] and not sources), "virtual edge claims a real source")
        _require(edge["virtual"] or edge["frame"] or bool(sources), "real nonframe edge has no original source")
        if drawing is not None:
            _require(all(s < len(drawing["strokes"]) for s in sources), "unknown original-stroke reference")
    rotation = geometry["rotation"]
    _require(isinstance(rotation, list) and len(rotation) == len(vertices), "rotation/vertex counts differ")
    plane = PlaneMap(tuple((str(e["a"]), str(e["b"])) for e in edges),
                     {str(v): tuple(darts) for v, darts in enumerate(rotation)})
    _require(isinstance(geometry["faceOfDart"], list)
             and all(type(v) is int for v in geometry["faceOfDart"])
             and geometry["faceOfDart"] == list(plane.face_of_dart), "global dart/region identity mismatch")
    _require(geometry["faces"] == [list(face) for face in plane.faces], "global region walks differ")
    _require(type(geometry["outerFace"]) is int and 0 <= geometry["outerFace"] < len(plane.faces),
             "invalid outer region identity")
    original = geometry["original"]
    _require(isinstance(original, dict) and all(type(original.get(k)) is int and original[k] >= 1
                                              for k in ("vertices", "edges", "components")),
             "invalid original disconnected-graph counts")
    _require(len(plane.faces) == original["edges"] - original["vertices"] + original["components"] + 1,
             "virtual augmentation changed the original Euler region count")
    _require(all(plane.shores(i)[0] == plane.shores(i)[1] for i, e in enumerate(edges) if e["virtual"]),
             "a virtual connector must not separate regions")
    return plane


def _real_boundary_walks(geometry, plane):
    """Keep disconnected boundary walks grouped under their existing global region."""
    edges = geometry["edges"]
    real_darts = {dart for i, edge in enumerate(edges) if not edge["virtual"] for dart in (2 * i, 2 * i + 1)}
    predecessor = {}
    for rotation in geometry["rotation"]:
        real = [dart for dart in rotation if dart in real_darts]
        for index, dart in enumerate(real):
            predecessor[dart] = real[index - 1]
    walks, covered = [], set()
    for start in sorted(real_darts):
        if start in covered:
            continue
        boundary, dart = [], start
        while dart not in covered:
            covered.add(dart)
            boundary.append(dart)
            dart = predecessor[dart ^ 1]
        _require(dart == start, "real boundary walk failed to close")
        regions = {plane.face_of_dart[d] for d in boundary}
        _require(len(regions) == 1, "one real boundary walk was assigned to several global regions")
        face = regions.pop()
        walks.append({"id": f"W{len(walks)}", "region_id": f"S{face}", "face_index": face,
                      "darts": boundary, "edge_ids": [d // 2 for d in boundary]})
    _require(covered == real_darts, "missing real boundary dart")
    return walks


def _real_components(geometry):
    """Count components of real edges only, ignoring purely virtual subdivision vertices."""
    adjacent = defaultdict(set)
    real_edges = 0
    for edge in geometry["edges"]:
        if not edge["virtual"]:
            adjacent[edge["a"]].add(edge["b"])
            adjacent[edge["b"]].add(edge["a"])
            real_edges += 1
    remaining, components = set(adjacent), []
    while remaining:
        seed = min(remaining)
        reached, pending = {seed}, [seed]
        while pending:
            vertex = pending.pop()
            new = adjacent[vertex] - reached
            reached.update(new)
            pending.extend(sorted(new))
        remaining.difference_update(reached)
        components.append(sorted(reached))
    return components, len(adjacent), real_edges


def _check_source_coverage(geometry, drawing):
    """Verify each original segment is covered by its declared real atomic pieces.

    The engine rounds vertices to 1e-6 pixels. A 1e-5 pixel tolerance matches
    the existing mother-line adapter; this is provenance checking, not a second
    independent geometric planarizer.
    """
    intervals = defaultdict(list)
    for edge in geometry["edges"]:
        for source in edge["sources"]:
            stroke = drawing["strokes"][source]
            a, b = stroke["a"], stroke["b"]
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = hypot(dx, dy)
            parameters = []
            for vertex in (edge["a"], edge["b"]):
                p = geometry["vertices"][vertex]
                t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (length * length)
                distance = abs(dx * (p[1] - a[1]) - dy * (p[0] - a[0])) / length
                _require(distance <= 1e-5 and -1e-5 / length <= t <= 1 + 1e-5 / length,
                         "atomic edge does not lie on its claimed original stroke")
                parameters.append(t)
            intervals[source].append(sorted(parameters))
    for source, stroke in enumerate(drawing["strokes"]):
        length = hypot(stroke["b"][0] - stroke["a"][0], stroke["b"][1] - stroke["a"][1])
        cursor = 0.0
        for first, last in sorted(intervals[source]):
            _require(first <= cursor + 1e-5 / length, "uncovered gap in an original stroke")
            cursor = max(cursor, last)
        _require(cursor >= 1 - 1e-5 / length, "original stroke missing from exported edges")


def adapt_exported_geometry(geometry, anchors=None, states=None, drawing=None):
    """Adapt one geometry-only Node export without starting another Node process.

    Side IDs are S0..S(n-1), in the validated global face order. Atomic contact
    E<i> follows dart 2*i from edge a to b; in screen-y-down coordinates its
    left is the mathematical left (e.g. east of a downward vertical dart).
    Anchors/states address these side IDs and are never selected automatically.
    """
    source_drawing = _drawing_input(drawing) if drawing is not None else None
    plane = _validated_plane(geometry, source_drawing)
    if source_drawing is not None:
        _check_source_coverage(geometry, source_drawing)
    sides = [f"S{i}" for i in range(len(plane.faces))]
    anchors, states = {} if anchors is None else anchors, {} if states is None else states
    _require(isinstance(anchors, dict) and isinstance(states, dict), "anchors and states must be mappings")
    for side, name in anchors.items():
        _require(side in sides and type(name) is int and name in (1, 2, 3, 4), "invalid explicit side anchor")
    for side, code in states.items():
        _require(side in sides, "state has unknown global side")
        NameState.from_quaternary(code)

    model = build_whole_lines(geometry)
    _require(model.plane_map.face_of_dart == plane.face_of_dart, "mother model changed region identities")
    frames = [mother for mother in model.lines if mother["id"] == "frame"]
    _require(len(frames) == 1 and all(span["left_side"] == geometry["outerFace"]
                                     for span in frames[0]["spans"]), "outer region is not left of the oriented frame")
    span_by_edge = {span["edge"]: (mother["id"], span)
                    for mother in model.lines for span in mother["spans"]}
    lines, provenance, virtual = [], [], []
    adjacent_pairs = set()
    for edge_id, edge in enumerate(geometry["edges"]):
        first, second = plane.shores(edge_id)
        evidence = {"edge_id": edge_id, "dart": 2 * edge_id,
                    "tail_vertex": edge["a"], "head_vertex": edge["b"],
                    "a": list(geometry["vertices"][edge["a"]]),
                    "b": list(geometry["vertices"][edge["b"]]),
                    "left_side": sides[first], "right_side": sides[second],
                    "frame": edge["frame"], "virtual": edge["virtual"],
                    "source_stroke_indices": list(edge["sources"])}
        if edge["virtual"]:
            _require(edge_id not in model.edge_owner, "virtual edge became a mother line")
            virtual.append(evidence)
            continue
        mother_id, span = span_by_edge[edge_id]
        evidence.update({"line_id": f"E{edge_id}", "mother_id": mother_id,
                         "mother_span": deepcopy(span)})
        if source_drawing is not None:
            evidence["source_strokes"] = [{"index": index, **deepcopy(source_drawing["strokes"][index])}
                                          for index in edge["sources"]]
        provenance.append(evidence)
        lines.append({"id": f"E{edge_id}", "left": sides[first], "right": sides[second],
                      "kind": "bridge" if first == second else "separator"})
        if first != second:
            adjacent_pairs.add(tuple(sorted((first, second))))

    # Only real incidences establish point contact. A virtual bridge's endpoint
    # does not connect its remote region to a physically unrelated region.
    vertices, point_witnesses = [], defaultdict(list)
    for vertex, rotation in enumerate(geometry["rotation"]):
        real_darts = [d for d in rotation if not geometry["edges"][d // 2]["virtual"]]
        incident = sorted({plane.face_of_dart[d] for d in real_darts})
        pure = [pair for pair in combinations(incident, 2) if pair not in adjacent_pairs]
        for pair in pure:
            point_witnesses[pair].append(vertex)
        vertices.append({"vertex": vertex, "point": list(geometry["vertices"][vertex]),
                         "real_outgoing_darts_ccw": real_darts,
                         "incident_side_ids": [sides[i] for i in incident],
                         "globally_point_only_pairs": [[sides[a], sides[b]] for a, b in pure]})
    point_provenance = [{"sides": [sides[a], sides[b]], "vertices": members}
                        for (a, b), members in sorted(point_witnesses.items())]
    walks = _real_boundary_walks(geometry, plane)
    regions = [{"id": sides[i], "face_index": i, "is_outer": i == geometry["outerFace"],
                "augmented_boundary_darts": list(face),
                "real_boundary_walk_ids": [walk["id"] for walk in walks if walk["face_index"] == i]}
               for i, face in enumerate(plane.faces)]
    components, real_vertices, real_edges = _real_components(geometry)
    _require(len(components) == geometry["original"]["components"], "real component count changed")
    _require(len(sides) == real_edges - real_vertices + len(components) + 1,
             "real disconnected Euler region count differs")
    _require({row["edge_id"] for row in provenance} == set(model.edge_owner), "real edge coverage differs")
    contact_document = {"sides": sides, "lines": lines, "anchors": deepcopy(anchors),
                        "states": deepcopy(states),
                        "point_contacts": [{"sides": row["sides"][:]} for row in point_provenance]}
    return {"schema_version": 1, "status": "adapted", "contact_document": contact_document,
            "geometry": deepcopy(geometry), "geometry_sha256": digest(geometry),
            "drawing": deepcopy(drawing), "geometry_input": source_drawing,
            "drawing_sha256": digest(drawing) if drawing is not None else None,
            "geometry_key": stroke_set_key(source_drawing) if source_drawing is not None else None,
            "outer_side_id": sides[geometry["outerFace"]], "side_order": sides,
            "regions": regions, "real_boundary_walks": walks,
            "atomic_edge_provenance": provenance, "whole_lines": deepcopy(model.lines),
            "virtual_connectors": virtual, "vertex_contacts": vertices,
            "point_contact_provenance": point_provenance, "real_components": components,
            "choices": 0, "propagation_runs": 0, "old_colors_read": False,
            "ignored_drawing_fields": sorted(set(drawing) - {"strokes", "frame", "schemaVersion"})
                                      if drawing is not None else [],
            "validation": {"python_global_face_orbits_match": True, "real_euler_region_count": len(sides),
                           "original_component_count": len(components), "real_edge_count": real_edges,
                           "real_boundary_walk_count": len(walks),
                           "source_stroke_coverage_checked": drawing is not None},
            "scope": "Existing Node planarization and virtual-bridge region assembly, followed by Python "
                     "rotation reconstruction. Real boundary walks are grouped by global region, not "
                     "treated as separate sides. Only real separators create NEQ; bridges share one "
                     "side identity; point contact creates no NEQ. Whole mothers remain the existing "
                     "maximal straight runs plus frame, not a new general curved-mother definition. "
                     "No candidate propagation or active naming is performed."}


def adapt_geometry(drawing, anchors=None, states=None):
    """Export one drawing using Node geometry only, then use the pure adapter."""
    document = _drawing_input(drawing)
    key = stroke_set_key(document)
    result = export_geometries([{"key": key, "document": document}])[0]
    _require(result["key"] == key and result["status"] == "geometry_ok",
             "geometry rejected: " + json.dumps(result.get("errors", []), ensure_ascii=False))
    _require(result["coloring_performed"] is False, "geometry export unexpectedly performed coloring")
    return adapt_exported_geometry(result["geometry"], anchors=anchors, states=states, drawing=drawing)

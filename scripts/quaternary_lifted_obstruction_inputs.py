"""Geometry-only inputs for a lifted triangular-bipyramid obstruction audit.

The construction realizes a prescribed adjacency graph in an actual drawing.
It does not supply colors/domains, decide algorithm reachability, or inspect a
coloring outcome. Four coordinate representations and their fixed-order
prefixes are a declared sample, not all insertion orders or planar drawings.
"""

from copy import deepcopy
from itertools import combinations

from scripts.audit_quaternary_geometry import audit_geometry
from scripts.current_corpus import stroke_set_key
from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.validate_global_restart import canonical_document


INPUT_VERSION = "quaternary-lifted-obstruction-inputs-v1"
REPRESENTATIONS = (
    ("identity", False, False),
    ("mirror-x", True, False),
    ("mirror-y", False, True),
    ("mirror-xy", True, True),
)
SOURCE_PATHS = (
    "scripts/quaternary_lifted_obstruction_inputs.py",
    "tests/test_quaternary_lifted_obstruction_inputs.py",
    "scripts/current_corpus.py",
    "scripts/validate_global_restart.py",
    "scripts/quaternary_geometry_adapter.py",
    "scripts/audit_quaternary_geometry.py",
    "scripts/restart-geometry.mjs",
)


def _segments():
    """Return the 24 declared segments in the fixed construction order.

    The outer rectangle separates Z from E. Two triangles and their three
    spokes form the A/B/C/D/E core. Two diamonds and three connectors insert
    a K4 patch in A; only its two outer regions X/Y touch A. The rectangular
    drawing frame is provided by the engine and is not a source segment.
    """
    rectangle = ((100, 80), (800, 80), (800, 540), (100, 540))
    outer_triangle = ((400, 150), (700, 460), (180, 480))
    inner_triangle = ((420, 250), (560, 400), (310, 410))
    outer_diamond = ((430, 300), (490, 355), (430, 395), (370, 355))
    inner_diamond = ((430, 335), (450, 355), (430, 375), (410, 355))
    segments = []

    def add_cycle(points):
        """Preserve the prescribed vertex order rather than sorting strokes."""
        segments.extend((points[i], points[(i + 1) % len(points)])
                        for i in range(len(points)))

    add_cycle(rectangle)
    add_cycle(outer_triangle)
    add_cycle(inner_triangle)
    segments.extend(zip(outer_triangle, inner_triangle))
    add_cycle(outer_diamond)
    add_cycle(inner_diamond)
    segments.extend(((outer_diamond[0], inner_diamond[0]),
                     (inner_diamond[2], outer_diamond[2]),
                     (inner_diamond[3], inner_diamond[1])))
    return tuple(segments)


def base_drawing():
    """Return a fresh complete drawing with no anchors or candidate domains."""
    return {"frame": {"width": 900, "height": 600}, "strokes": [
        {"a": list(a), "b": list(b)} for a, b in _segments()]}


def transformed_drawing(mirror_x=False, mirror_y=False):
    """Reflect coordinates only, retaining source order and endpoint direction."""
    document = base_drawing()
    for stroke in document["strokes"]:
        for endpoint in ("a", "b"):
            x, y = stroke[endpoint]
            stroke[endpoint] = [900 - x if mirror_x else x,
                                600 - y if mirror_y else y]
    return document


def identify_lifted(geometry):
    """Recover graph roles from audited real adjacency, never supplied labels.

    A, F and Z have unique degrees 5, 1 and 2. E is Z's neighbor other than F.
    The three rim faces touch E, while X/Y are the other two neighbors of A;
    P/Q are the remaining pair. Symmetric groups use increasing current face
    IDs as a reporting convention, without claiming coordinate-label invariance
    across reflections. The complete nineteen-edge contract is then checked.
    """
    adapted = adapt_exported_geometry(geometry)
    geometry_audit, raw_edges = audit_geometry(geometry, adapted)
    faces = set(range(len(geometry["faces"])))
    if len(faces) != 11:
        raise ValueError("lifted obstruction requires exactly eleven global faces")
    neighbors = {face: set() for face in faces}
    for a, b in raw_edges:
        neighbors[a].add(b)
        neighbors[b].add(a)

    def unique_degree(degree, name):
        """Reject a role unless its actual degree singles out one face."""
        candidates = [face for face in faces if len(neighbors[face]) == degree]
        if len(candidates) != 1:
            raise ValueError(f"role {name} is not unique at degree {degree}")
        return candidates[0]

    apex = unique_degree(5, "A")
    exterior = unique_degree(1, "F")
    background = unique_degree(2, "Z")
    if exterior != geometry["outerFace"] or neighbors[exterior] != {background}:
        raise ValueError("outer face F must have Z as its unique real neighbor")
    other = neighbors[background] - {exterior}
    if len(other) != 1:
        raise ValueError("Z must separate E from exterior F")
    other_apex = next(iter(other))
    rim = sorted(neighbors[other_apex] - {background})
    outer_patch = sorted(neighbors[apex] - set(rim))
    assigned = {apex, exterior, background, other_apex, *rim, *outer_patch}
    inner_patch = sorted(faces - assigned)
    if len(rim) != 3 or len(outer_patch) != 2 or len(inner_patch) != 2 or len(assigned) != 9:
        raise ValueError("core rim and four-face patch do not have the declared roles")
    labels = {
        "A": apex, "B": rim[0], "C": rim[1], "D": rim[2], "E": other_apex,
        "X": outer_patch[0], "Y": outer_patch[1],
        "P": inner_patch[0], "Q": inner_patch[1], "Z": background, "F": exterior,
    }
    core = {tuple(sorted(pair)) for pair in combinations([apex, *rim, other_apex], 2)}
    core.remove(tuple(sorted((apex, other_apex))))
    patch = {tuple(sorted(pair)) for pair in combinations(outer_patch + inner_patch, 2)}
    connections = {tuple(sorted(pair)) for pair in (
        (apex, outer_patch[0]), (apex, outer_patch[1]),
        (other_apex, background), (background, exterior))}
    expected_edges = core | patch | connections
    if set(raw_edges) != expected_edges or len(expected_edges) != 19:
        raise ValueError("real shared-edge adjacency differs from the declared lifted graph")
    frame_faces = {
        geometry["faceOfDart"][2 * i + orientation]
        for i, edge in enumerate(geometry["edges"])
        if edge["frame"] and not edge["virtual"]
        for orientation in (0, 1)
    }
    if frame_faces != {background, exterior}:
        raise ValueError("Z must be the unique bounded face touching the real frame")
    return {
        "labels": labels,
        "inner_apex": apex,
        "outer_core_apex": other_apex,
        "background": background,
        "outer_face": exterior,
        "rim": rim,
        "outer_patch": outer_patch,
        "inner_patch": inner_patch,
        "frame_faces": sorted(frame_faces),
        "true_edges": [list(pair) for pair in raw_edges],
        "label_convention": "A/E/Z/F structural roles; B/C/D, X/Y and P/Q sorted by current face ID",
        "geometry_audit": geometry_audit,
        "scope": "geometry realizability only; no coloring-policy reachability inference",
    }


def build_lifted_inventory():
    """Retain all 25 fixed-order prefixes in four prescribed representations.

    These are exactly four coordinate representations of one construction,
    not all 24! insertion orders, an independent random family, or a claim
    that every step splits a face. All current drawings are canonicalized by
    their undirected stroke set; the original reflection and order are kept
    on each history so its drawing process remains reconstructible.
    """
    records, by_key, histories = [], {}, []
    for name, mirror_x, mirror_y in REPRESENTATIONS:
        drawing = transformed_drawing(mirror_x, mirror_y)
        history_id = "lifted-obstruction-" + name
        keys = []
        for step in range(len(drawing["strokes"]) + 1):
            document = canonical_document({"frame": drawing["frame"],
                                           "strokes": drawing["strokes"][:step]})
            key = stroke_set_key(document)
            if key not in by_key:
                record = {"key": key, "document": document, "aliases": []}
                by_key[key] = record
                records.append(record)
            if by_key[key]["document"] != document:
                raise AssertionError("stroke-set key collision in declared lifted inputs")
            by_key[key]["aliases"].append({"history": history_id, "step": step})
            keys.append(key)
        histories.append({"id": history_id, "representation": name,
                          "mirror_x": mirror_x, "mirror_y": mirror_y,
                          "segment_order": list(range(len(drawing["strokes"]))),
                          "prefix_keys": keys})
    return {
        "version": INPUT_VERSION,
        "records": records,
        "histories": histories,
        "generation": {
            "base_drawing": deepcopy(base_drawing()),
            "source_segments": 24,
            "frame": {"width": 900, "height": 600},
            "representations": [name for name, _, _ in REPRESENTATIONS],
            "distinct_drawings": len(records),
            "history_count": len(histories),
            "prefixes_per_history": 25,
            "prefix_references": sum(len(row["prefix_keys"]) for row in histories),
            "generation_scope": "four prescribed coordinate representations, each fixed 24-segment order",
            "all_insertion_orders": False,
            "deduplication": "canonical_document and stroke_set_key; not graph isomorphism",
            "prefix_scope": "steps 0..24; bridges and disconnected components allowed",
            "coloring_used_for_input_selection": False,
            "colors_inherited_between_prefixes": False,
            "seed": None,
        },
        "direct_source_paths": list(SOURCE_PATHS),
    }

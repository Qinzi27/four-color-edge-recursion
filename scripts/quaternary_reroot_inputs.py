"""Declared inversion drawings that move one lifted-graph region to the frame.

Only the 24 explicit source segments are inverted.  The engine's implicit
rectangle is added afterwards, so the intended new adjacency is F--R.  Straight
chords approximate inverted circular arcs at fixed subdivision counts; failures
of that approximation remain geometry-invalid cases, never replaced inputs.
No coloring policy, oracle result, or candidate domain selects these drawings.
"""

from itertools import combinations
from hashlib import sha256
import json
from math import hypot
from pathlib import Path
import subprocess

from scripts.audit_quaternary_geometry import audit_geometry
from scripts.current_corpus import stroke_set_key
from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.quaternary_lifted_obstruction_inputs import (
    SOURCE_PATHS as LIFTED_SOURCES, base_drawing, identify_lifted,
)
from scripts.validate_global_restart import canonical_document


INPUT_VERSION = "quaternary-reroot-inversion-inputs-v1"
ROOT = Path(__file__).resolve().parents[1]
ENGINE_SHA256 = "1451287b703e6f90765a1ed96acd2c4c5fc30d467be6c207da81f4b982035d84"
TARGET_CENTERS = {
    "Z": (40, 40), "P": (430, 345), "Q": (430, 365),
    "X": (390, 350), "Y": (470, 350), "A": (420, 280),
    "E": (150, 100),
}
SUBDIVISIONS = (4, 8)
ROTATIONS = (0, 90)
SOURCE_PATHS = tuple(dict.fromkeys((
    "scripts/quaternary_reroot_inputs.py",
    "tests/test_quaternary_reroot_inputs.py", "scripts/order-probe-geometry.mjs",
    "web/engine.js", *LIFTED_SOURCES,
)))


def export_reroot_geometries(records):
    """Use the isolated 256-stroke geometry profile and bind every source hash.

    Results have the usual export_geometries shape plus engine_profile on each
    row.  The frozen 80-stroke exporter still rejects these drawings; this new
    research profile is explicitly separate and changes no stored engine file.
    """
    before = sha256((ROOT / "web/engine.js").read_bytes()).hexdigest()
    if before != ENGINE_SHA256:
        raise ValueError("frozen geometry engine hash differs")
    command = ["node", str(ROOT / "scripts/order-probe-geometry.mjs")]
    result = subprocess.run(command, cwd=ROOT,
                            input=json.dumps({"cases": [{"key": row["key"], "document": row["document"]}
                                                         for row in records]}),
                            capture_output=True, text=True, encoding="utf-8", check=True)
    payload = json.loads(result.stdout)
    profile = payload["engine_profile"]
    if (payload["coloring_performed"] or len(payload["results"]) != len(records)
            or profile["original_engine_sha256"] != before
            or profile["exporter_sha256"] != sha256((ROOT / "scripts/order-probe-geometry.mjs").read_bytes()).hexdigest()
            or profile["limits"] != {"strokes": 256, "edges": 1600, "faces": 400}
            or profile["old_engine_file_modified"]
            or before != sha256((ROOT / "web/engine.js").read_bytes()).hexdigest()):
        raise ValueError("research geometry exporter provenance or no-color contract differs")
    for row, exported in zip(records, payload["results"]):
        if exported["key"] != row["key"] or exported["coloring_performed"]:
            raise ValueError("research geometry export case order or no-color contract differs")
        exported["engine_profile"] = profile
    return payload["results"]


def _expected_edges(target):
    """Return all 18 lifted core adjacencies plus the new frame contact."""
    edges = set(combinations("ABCDE", 2)) - {("A", "E")}
    edges |= set(combinations("PQXY", 2))
    edges |= {("A", "X"), ("A", "Y"), ("E", "Z"), ("F", target)}
    return {tuple(sorted(pair)) for pair in edges}


def _point_face(geometry, point):
    """Locate a strict interior point by parity of augmented boundary walks.

    The two opposite darts of each virtual connector cancel.  Thus holes and
    disconnected real boundaries need no invented extra face identities.
    """
    x, y = point
    matches = []
    for face, walk in enumerate(geometry["faces"]):
        if face == geometry["outerFace"]:
            continue
        inside = False
        for dart in walk:
            edge = geometry["edges"][dart // 2]
            a = geometry["vertices"][edge["b" if dart % 2 else "a"]]
            b = geometry["vertices"][edge["a" if dart % 2 else "b"]]
            dx, dy = b[0] - a[0], b[1] - a[1]
            cross = dx * (y - a[1]) - dy * (x - a[0])
            projection = (x - a[0]) * dx + (y - a[1]) * dy
            if (not edge["virtual"] and abs(cross) <= 1e-5 * hypot(dx, dy)
                    and 0 <= projection <= dx * dx + dy * dy):
                raise ValueError("declared inversion center lies on a real boundary")
            if (a[1] > y) != (b[1] > y):
                if x < a[0] + (y - a[1]) * dx / dy:
                    inside = not inside
        if inside:
            matches.append(face)
    if len(matches) != 1:
        raise ValueError("declared inversion center lacks a unique bounded region")
    return matches[0]


def verify_target_centers(geometry):
    """Verify original sample roles geometrically without arbitrary P/Q labels.

    The selected upper/lower sample points define P and Q within their symmetric
    pair; similarly the left/right samples define X/Y.  Only their structural
    sets are inherited from identify_lifted's face-ID reporting convention.
    """
    identified = identify_lifted(geometry)
    faces = {name: _point_face(geometry, point)
             for name, point in TARGET_CENTERS.items()}
    expected = {"Z": identified["background"], "A": identified["inner_apex"],
                "E": identified["outer_core_apex"]}
    if any(faces[name] != face for name, face in expected.items()):
        raise ValueError("declared A/E/Z center does not belong to its structural role")
    if ({faces["P"], faces["Q"]} != set(identified["inner_patch"])
            or {faces["X"], faces["Y"]} != set(identified["outer_patch"])
            or len(set(faces.values())) != len(faces)):
        raise ValueError("declared P/Q or X/Y centers do not identify the patch roles")
    return {"passed": True, "center_faces": faces,
            "centers": {name: list(point) for name, point in TARGET_CENTERS.items()},
            "geometry_audit": identified["geometry_audit"],
            "label_scope": "P/Q and X/Y distinguished by source sample points only"}


def inversion_drawing(target, subdivisions, rotation):
    """Invert fixed equal subdivisions, rotate, uniformly fit, and round once."""
    if target not in TARGET_CENTERS or subdivisions not in SUBDIVISIONS or rotation not in ROTATIONS:
        raise ValueError("parameters must belong to the declared 7 x 2 x 2 inventory")
    cx, cy = TARGET_CENTERS[target]
    polylines = []
    for stroke in base_drawing()["strokes"]:
        a, b = stroke["a"], stroke["b"]
        points = []
        for step in range(subdivisions + 1):
            x = a[0] + (b[0] - a[0]) * step / subdivisions - cx
            y = a[1] + (b[1] - a[1]) * step / subdivisions - cy
            radius_squared = x * x + y * y
            if not radius_squared:
                raise ValueError("declared inversion center coincides with a sampled boundary")
            x, y = x / radius_squared, y / radius_squared
            points.append((-y, x) if rotation == 90 else (x, y))
        polylines.append(points)
    points = [point for line in polylines for point in line]
    xmin, xmax = min(p[0] for p in points), max(p[0] for p in points)
    ymin, ymax = min(p[1] for p in points), max(p[1] for p in points)
    scale = min(800 / (xmax - xmin), 500 / (ymax - ymin))
    xcenter, ycenter = (xmin + xmax) / 2, (ymin + ymax) / 2

    def fit(point):
        """Center the fixed aspect ratio inside the 50-pixel margin."""
        return [round(450 + scale * (point[0] - xcenter), 8),
                round(300 + scale * (point[1] - ycenter), 8)]

    return {"frame": {"width": 900, "height": 600}, "strokes": [
        {"a": fit(a), "b": fit(b)}
        for line in polylines for a, b in zip(line, line[1:])]}


def build_reroot_inventory():
    """Return all 28 prescribed final drawings, including any topology failure."""
    records = []
    for target in TARGET_CENTERS:
        for subdivisions in SUBDIVISIONS:
            for rotation in ROTATIONS:
                document = canonical_document(inversion_drawing(target, subdivisions, rotation))
                records.append({
                    "id": f"reroot-{target}-sub{subdivisions}-rot{rotation}",
                    "key": stroke_set_key(document), "document": document,
                    "target": target, "center": list(TARGET_CENTERS[target]),
                    "subdivisions": subdivisions, "rotation_degrees": rotation,
                    "source_segment_count": 24, "polyline_segment_count": 24 * subdivisions,
                })
    return {"version": INPUT_VERSION, "records": records,
            "generation": {
                "source_segment_count": 24, "original_implicit_frame_inverted": False,
                "centers": {name: list(point) for name, point in TARGET_CENTERS.items()},
                "subdivisions": list(SUBDIVISIONS), "rotations_degrees": list(ROTATIONS),
                "frame": {"width": 900, "height": 600}, "margin_pixels": 50,
                "fit": "uniform scale, center within frame", "coordinate_decimal_places": 8,
                "declared_drawings": 28, "distinct_drawing_keys": len({r["key"] for r in records}),
                "inversion": "(x-cx,y-cy)/((x-cx)^2+(y-cy)^2)",
                "input_scope": "fixed final polyline drawings; insertion prefixes not checked",
                "approximation_scope": "finite chord approximations; no topology preservation assumed",
                "invalid_geometry_policy": "retain every case; no parameter replacement",
                "coloring_used_for_input_selection": False, "seed": None,
            }, "direct_source_paths": list(SOURCE_PATHS)}


def identify_reroot(geometry, target):
    """Enumerate every marked graph isomorphism from independently audited NEQ.

    Fix F to the actual outer region and the requested R to the only bounded
    frame region.  The complete 19-edge graph, including absent edges, is checked.
    A canonical representative is for display only; all symmetric alternatives
    and invariant role sets are retained for downstream interpretation.
    """
    if target not in TARGET_CENTERS:
        raise ValueError("unknown declared frame target")
    try:
        adapted = adapt_exported_geometry(geometry)
        geometry_audit, raw_edges = audit_geometry(geometry, adapted)
    except (AssertionError, KeyError, TypeError, ValueError) as error:
        raise ValueError(f"reroot geometry audit failed: {error}") from error
    faces = set(range(len(geometry["faces"])))
    if len(faces) != 11 or len(raw_edges) != 19:
        raise ValueError("reroot graph requires exactly eleven faces and nineteen real adjacencies")
    outer = geometry["outerFace"]
    frame_faces = {geometry["faceOfDart"][2 * i + orientation]
                   for i, edge in enumerate(geometry["edges"])
                   if edge["frame"] and not edge["virtual"] for orientation in (0, 1)}
    bounded_frame = frame_faces - {outer}
    if len(bounded_frame) != 1 or outer not in frame_faces:
        raise ValueError("reroot map requires exactly one bounded real-frame region")
    frame_region = next(iter(bounded_frame))
    expected_edges = _expected_edges(target)
    roles = sorted("ABCDEFPQXYZ")
    expected = {role: set() for role in roles}
    actual = {face: set() for face in faces}
    for a, b in expected_edges:
        expected[a].add(b)
        expected[b].add(a)
    for a, b in raw_edges:
        actual[a].add(b)
        actual[b].add(a)
    mappings = []

    def search(mapping):
        """Degree and assigned-neighbor constraints bound a tiny exact search."""
        if len(mapping) == len(roles):
            mappings.append({role: mapping[role] for role in roles})
            return
        remaining = [role for role in roles if role not in mapping]
        candidates = {}
        for role in remaining:
            candidates[role] = [face for face in sorted(faces - set(mapping.values()))
                                if len(actual[face]) == len(expected[role])
                                and all((other in expected[role]) == (value in actual[face])
                                        for other, value in mapping.items())]
        role = min(remaining, key=lambda item: (len(candidates[item]),
                                               -len(expected[item] & set(mapping)), item))
        for face in candidates[role]:
            search({**mapping, role: face})

    if actual[outer] == {frame_region}:
        search({"F": outer, target: frame_region})
    if not mappings:
        raise ValueError("real adjacency has no declared marked lifted-graph isomorphism")
    mappings.sort(key=lambda mapping: tuple(mapping[role] for role in roles))
    possibilities = {role: sorted({mapping[role] for mapping in mappings}) for role in roles}
    representative = mappings[0]
    # All accepted markings must agree on structural group identities.
    groups = {"rim": "BCD", "outer_patch": "XY", "inner_patch": "PQ"}
    group_sets = {}
    for name, names in groups.items():
        values = {tuple(sorted(mapping[role] for role in names)) for mapping in mappings}
        if len(values) != 1:
            raise ValueError(f"structural group {name} is not identifiable")
        group_sets[name] = list(next(iter(values)))
    if any(len(possibilities[role]) != 1 for role in "AEZF"):
        raise ValueError("structural A/E/Z/F roles are not identifiable")
    return {
        "passed": True, "target": target, "labels": representative,
        "all_equivalent_mappings": mappings, "isomorphism_count": len(mappings),
        "role_possibilities": possibilities,
        "ambiguous_roles": [role for role in roles if len(possibilities[role]) > 1],
        "inner_apex": representative["A"], "outer_core_apex": representative["E"],
        "background": representative["Z"], "outer_face": outer,
        "bounded_frame_face": frame_region, "frame_faces": sorted(frame_faces),
        **group_sets, "true_edges": [list(pair) for pair in raw_edges],
        "geometry_audit": geometry_audit,
        "label_convention": "lexicographically first marked isomorphism for display; all alternatives retained",
        "scope": "audited adjacency and marked isomorphism only; no coloring or reachability claim",
    }

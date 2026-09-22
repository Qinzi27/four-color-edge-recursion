"""Freeze a real drawing family for the triangular-bipyramid reachability audit.

The six integer-coordinate segments are chosen only to realize the declared
topology.  No coloring routine, oracle, candidate domain, or archived outcome
selects an input.  All 64 segment subsets and all 720 insertion permutations
are retained, including prefixes with dangling or disconnected real edges.
"""

from copy import deepcopy
from itertools import combinations, permutations

from scripts.audit_quaternary_geometry import audit_geometry
from scripts.current_corpus import stroke_set_key
from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.validate_global_restart import canonical_document


INPUT_VERSION = "quaternary-triangular-bipyramid-inputs-v1"

# Indices 0..2 are the triangle sides; 3..5 join its respective vertices to
# distinct frame points. No two incident segments are collinear, so the six
# source segments remain six distinct non-frame mothers in the complete map.
SEGMENTS = (
    ((420, 150), (660, 410)),
    ((660, 410), (260, 420)),
    ((260, 420), (420, 150)),
    ((420, 150), (360, 0)),
    ((660, 410), (900, 440)),
    ((260, 420), (0, 480)),
)

# This is the direct dependency list, not a claim to enumerate transitive
# imports. A frozen experiment should also bind the dependencies recorded by
# its geometry/producer/auditor manifest, including the Node geometry engine.
SOURCE_PATHS = (
    "scripts/quaternary_bipyramid_inputs.py",
    "tests/test_quaternary_bipyramid_inputs.py",
    "scripts/current_corpus.py",
    "scripts/validate_global_restart.py",
    "scripts/quaternary_geometry_adapter.py",
    "scripts/audit_quaternary_geometry.py",
    "scripts/restart-geometry.mjs",
)


def _drawing(segment_indices):
    """Build fresh JSON-compatible input while retaining the requested order."""
    return {
        "frame": {"width": 900, "height": 600},
        "strokes": [{"a": list(SEGMENTS[i][0]), "b": list(SEGMENTS[i][1])}
                    for i in segment_indices],
    }


def base_drawing():
    """Return the complete six-segment drawing, without any supplied colors."""
    return _drawing(range(len(SEGMENTS)))


def identify_bipyramid(geometry):
    """Identify A/E and B/C/D from audited actual face adjacency and the frame.

    A is the unique face with no real frame edge; E is the coordinate-checked
    exterior. The three remaining faces form the rim. Their B/C/D labels use
    increasing current face IDs, solely to make reports deterministic. This
    does not preserve those labels across a different geometric embedding.
    """
    adapted = adapt_exported_geometry(geometry)
    audit, actual_edges = audit_geometry(geometry, adapted)
    faces = set(range(len(geometry["faces"])))
    if len(faces) != 5:
        raise ValueError("triangular bipyramid requires exactly five global faces")
    frame_faces = {
        geometry["faceOfDart"][2 * i + orientation]
        for i, edge in enumerate(geometry["edges"])
        if edge["frame"] and not edge["virtual"]
        for orientation in (0, 1)
    }
    interior = faces - frame_faces
    outer = geometry["outerFace"]
    if len(interior) != 1 or outer not in frame_faces:
        raise ValueError("require one non-frame interior apex and a frame exterior")
    inner = next(iter(interior))
    rim = sorted(faces - {inner, outer})
    missing = tuple(sorted((inner, outer)))
    expected = set(combinations(sorted(faces), 2)) - {missing}
    if set(actual_edges) != expected:
        raise ValueError("true shared-edge adjacency is not K5 minus the apex pair")
    return {
        "apices": [inner, outer],
        "inner_apex": inner,
        "outer_apex": outer,
        "rim": rim,
        "labels": {"A": inner, "B": rim[0], "C": rim[1], "D": rim[2], "E": outer},
        "label_convention": "A unique non-frame face; E outer; B/C/D increasing other face IDs",
        "true_edges": [list(edge) for edge in actual_edges],
        "missing_apex_edge": list(missing),
        "frame_faces": sorted(frame_faces),
        "geometry_audit": audit,
        "scope": "topology identification only; no coloring or reachability decision",
    }


def build_targeted_inventory():
    """Enumerate exactly all subsets and every full insertion permutation.

    A history has seven prefix keys, including the empty input. Each step adds
    one distinct declared segment, but need not split a face. Current drawings
    use the project's stroke-set canonicalization, which discards insertion
    order/direction and is not graph-isomorphism deduplication. The history
    retains the actual insertion order independently for replay and reporting.
    """
    records, by_mask, seen = [], {}, set()
    for mask in range(1 << len(SEGMENTS)):
        indices = [i for i in range(len(SEGMENTS)) if mask & (1 << i)]
        document = canonical_document(_drawing(indices))
        key = stroke_set_key(document)
        if key in seen:
            raise AssertionError("distinct declared segment subsets share a stroke-set key")
        seen.add(key)
        by_mask[mask] = key
        records.append({"key": key, "document": document, "subset_mask": mask})

    histories = []
    for order in permutations(range(len(SEGMENTS))):
        mask, prefix_keys = 0, [by_mask[0]]
        for segment in order:
            mask |= 1 << segment
            prefix_keys.append(by_mask[mask])
        histories.append({
            "id": "bipyramid-order-" + "".join(str(i) for i in order),
            "prefix_keys": prefix_keys,
            "segment_order": list(order),
        })

    return {
        "version": INPUT_VERSION,
        "records": records,
        "histories": histories,
        "generation": {
            "segments": deepcopy(base_drawing()["strokes"]),
            "frame": {"width": 900, "height": 600},
            "segment_indices": list(range(len(SEGMENTS))),
            "subset_masks_inclusive": [0, (1 << len(SEGMENTS)) - 1],
            "distinct_drawings": len(records),
            "history_count": len(histories),
            "prefixes_per_history": len(SEGMENTS) + 1,
            "prefix_references": sum(len(row["prefix_keys"]) for row in histories),
            "complete_generation": "all 2^6 segment subsets and all 6! insertion permutations",
            "deduplication": "canonical_document and stroke_set_key; not graph isomorphism",
            "order_scope": "each order adds all six distinct segments once",
            "prefix_scope": "empty through six segments; dangling edges need not split faces",
            "colors_inherited_between_prefixes": False,
            "coloring_used_for_input_selection": False,
            "seed": None,
        },
        "direct_source_paths": list(SOURCE_PATHS),
    }

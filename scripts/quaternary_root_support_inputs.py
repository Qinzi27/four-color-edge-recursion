"""Geometry-only support extensions of the fixed 24-segment lifted drawing.

Extensions may split the original faces and destroy its old graph roles. This
module records the actual topology and whole-line support rather than assuming
the original K4/bipyramid survives or predicting a coloring selection order.
"""

from copy import deepcopy

from fourcolor.global_restart import current_segments
from fourcolor.level_sides import level_metadata
from fourcolor.whole_lines import build_whole_lines
from scripts.audit_quaternary_geometry import audit_geometry
from scripts.current_corpus import stroke_set_key
from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.quaternary_lifted_obstruction_inputs import base_drawing, identify_lifted
from scripts.scan_low_color_obstruction_states import triangle_bipyramids
from scripts.validate_global_restart import canonical_document


INPUT_VERSION = "quaternary-root-support-inputs-v1"
EXTENSIONS = {
    "left": ((0, 355), (410, 355)),
    "right": ((450, 355), (900, 355)),
    "diagonal-upper": ((95, 0), (430, 335)),
    "diagonal-lower": ((450, 355), (695, 600)),
}
CASES = (
    ("base", ()),
    ("left", ("left",)),
    ("right", ("right",)),
    ("horizontal", ("left", "right")),
    ("diagonal", ("diagonal-upper", "diagonal-lower")),
    ("both", ("left", "right", "diagonal-upper", "diagonal-lower")),
)
ORIENTATIONS = (0, 180)
SOURCE_PATHS = (
    "scripts/quaternary_root_support_inputs.py",
    "tests/test_quaternary_root_support_inputs.py",
    "scripts/quaternary_lifted_obstruction_inputs.py",
    "scripts/current_corpus.py",
    "scripts/validate_global_restart.py",
    "scripts/quaternary_geometry_adapter.py",
    "scripts/audit_quaternary_geometry.py",
    "scripts/scan_low_color_obstruction_states.py",
    "scripts/restart-geometry.mjs",
    "fourcolor/global_restart.py",
    "fourcolor/level_sides.py",
    "fourcolor/whole_lines.py",
)


def rotate_point(point, orientation):
    """Apply a genuine half turn, preserving distance, incidence and frame."""
    x, y = point
    if orientation == 0:
        return [x, y]
    if orientation == 180:
        return [900 - x, 600 - y]
    raise ValueError("only the declared 0/180 degree orientations are supported")


def support_drawing(extension_names=(), orientation=0):
    """Preserve all old strokes and append the named extensions in order."""
    original = base_drawing()
    if len(original["strokes"]) != 24:
        raise ValueError("support family requires the frozen 24-segment source")
    strokes = deepcopy(original["strokes"])
    for name in extension_names:
        a, b = EXTENSIONS[name]
        strokes.append({"a": list(a), "b": list(b)})
    rotated = [{end: rotate_point(stroke[end], orientation) for end in ("a", "b")}
               for stroke in strokes]
    frame = {"width": 900, "height": 600}
    return {"frame": frame, "strokes": rotated}


def coordinate_provenance(orientation):
    """Report source locations, never hard-coded identities of resulting faces."""
    groups = {
        "outer_patch_diamond": [(430, 300), (490, 355), (430, 395), (370, 355)],
        "inner_patch_diamond": [(430, 335), (450, 355), (430, 375), (410, 355)],
        "original_PQ_separator": [(410, 355), (450, 355)],
        "original_inner_diagonal_edge": [(430, 335), (450, 355)],
        "horizontal_complete_chord": [(0, 355), (900, 355)],
        "diagonal_complete_chord": [(95, 0), (695, 600)],
    }
    return {name: [rotate_point(point, orientation) for point in points]
            for name, points in groups.items()}


def build_support_inventory():
    """Declare 12 final cases and all their fixed short-history prefixes.

Every history starts at the complete old 24-segment map, not the empty frame.
The earlier 0..23 prefixes are deliberately excluded. Deduplication is by the
actual canonical stroke set, retaining all case/history aliases; no outcome,
candidate domain, oracle, or graph-isomorphism test selects these inputs.
"""
    records, by_key, cases, histories = [], {}, [], []
    for orientation in ORIENTATIONS:
        provenance = coordinate_provenance(orientation)
        for name, extensions in CASES:
            case_id = f"root-support-{name}-rotation-{orientation}"
            keys = []
            for step in range(len(extensions) + 1):
                prefix = extensions[:step]
                document = canonical_document(support_drawing(prefix, orientation))
                key = stroke_set_key(document)
                if key not in by_key:
                    record = {"key": key, "document": document, "aliases": [],
                              "metadata": {"orientation_degrees": orientation,
                                           "extensions": list(prefix),
                                           "base_segments": 24,
                                           "source_segments": 24 + len(prefix),
                                           "source_locations": deepcopy(provenance)}}
                    records.append(record)
                    by_key[key] = record
                if by_key[key]["document"] != document:
                    raise AssertionError("canonical support-input hash collision")
                by_key[key]["aliases"].append({"history": case_id, "step": step,
                                              "source_segments": 24 + step})
                keys.append(key)
            metadata = {"variant": name, "orientation_degrees": orientation,
                        "extensions": list(extensions), "base_segments": 24,
                        "source_segments": 24 + len(extensions),
                        "source_locations": deepcopy(provenance)}
            cases.append({"id": case_id, "key": keys[-1], "metadata": metadata})
            histories.append({"id": case_id, "prefix_keys": keys,
                              "starts_at_complete_base": True,
                              "base_segments": 24, "extension_order": list(extensions),
                              "orientation_degrees": orientation})
    return {
        "version": INPUT_VERSION, "records": records, "cases": cases,
        "histories": histories,
        "generation": {
            "base_drawing": base_drawing(), "base_segments": 24,
            "extensions_original_coordinates": {
                name: [list(a), list(b)] for name, (a, b) in EXTENSIONS.items()},
            "variants": [{"id": name, "extension_order": list(ext)} for name, ext in CASES],
            "orientations_degrees": list(ORIENTATIONS),
            "rotation_180": "(x,y) -> (900-x,600-y); frame remains 900x600",
            "pre_freeze_geometry_revision": {
                "initially_planned_orientations": [0, 90],
                "final_orientations": [0, 180],
                "reason": "frozen exporter, geometry adapter and independent geometry auditor require 900x600",
                "quarter_turn_geometry_error": "600x900 frame rejected before any coloring run",
                "quarter_turn_deferred": True,
                "revision_used_coloring_results": False,
                "scope": "declared pre-freeze geometry feasibility revision; not a failed coloring input removed",
            },
            "distinct_drawings": len(records), "final_cases": len(cases),
            "history_count": len(histories),
            "prefix_references": sum(len(row["prefix_keys"]) for row in histories),
            "prefix_scope": "complete 24-segment base plus each declared extension prefix only",
            "old_base_prefixes_0_through_23_included": False,
            "all_insertion_orders": False,
            "deduplication": "canonical_document and stroke_set_key; not graph isomorphism",
            "topology_preservation_claimed": False,
            "coloring_used_for_input_selection": False,
            "colors_inherited_between_prefixes": False,
            "selection_order_improvement_claimed": False,
            "face_budget_for_runner": 40, "seed": None,
        },
        "direct_source_paths": list(SOURCE_PATHS),
    }


def audit_support_geometry(geometry, drawing, orientation):
    """Audit actual adjacency and whole-line root support without coloring.

    A frame-to-frame chord is geometrically rooted at level two. That fact says
    nothing about which unresolved face the coloring scheduler selects first.
    The old named patch is recorded only by its source coordinates; extensions
    can split it and the old bipyramid. All current induced motifs are reported.
    """
    adapted = adapt_exported_geometry(geometry, drawing=drawing)
    audit, edges = audit_geometry(geometry, adapted)
    model = build_whole_lines(geometry)
    levels = level_metadata(model)
    units = current_segments(model)
    provenance = coordinate_provenance(orientation)
    chords = {}
    for name in ("horizontal_complete_chord", "diagonal_complete_chord"):
        endpoints = provenance[name]
        matched = [line for line in model.lines if line["id"] != "frame"
                   and sorted(line["endpoints"]) == sorted(endpoints)]
        if len(matched) > 1:
            raise ValueError("multiple whole lines claim the same declared chord")
        line = matched[0] if matched else None
        info = levels[line["id"]] if line else None
        rooted = bool(info and info["level"] == 2
                      and all("frame" in port for port in info["parents"]))
        chords[name] = {
            "source_endpoints": endpoints, "present": bool(line),
            "mother": line["id"] if line else None,
            "level": info["level"] if info else None,
            "parents": info["parents"] if info else None,
            "rooted_at_frame_level_two": rooted,
            "atomic_real_edges": [s["edge"] for s in line["spans"]] if line else [],
            "current_units": [u["id"] for u in units
                              if line and u["mother"] == line["id"]],
        }
    motifs = triangle_bipyramids(len(geometry["faces"]), edges)
    return {
        "geometry_audit": audit, "faces": len(geometry["faces"]),
        "true_adjacency_edges": len(edges), "true_edges": [list(e) for e in edges],
        "real_atomic_edges": sum(not e.get("virtual", False) for e in geometry["edges"]),
        "induced_bipyramids": motifs, "induced_bipyramid_count": len(motifs),
        "contains_induced_K5_minus_edge": bool(motifs),
        "whole_line_levels": levels, "complete_chords": chords,
        "source_locations": provenance,
        "old_named_face_ids_reused": False,
        "topology_preservation_claimed": False,
        "coloring_performed": False,
        "scope": "geometry and root support only; no early-K4-selection or coloring inference",
    }


def inspect_support_geometry(geometry, record):
    """Runner entry point with bound drawing provenance and optional base roles."""
    result = audit_support_geometry(geometry, record["document"],
                                    record["metadata"]["orientation_degrees"])
    result["extensions"] = deepcopy(record["metadata"]["extensions"])
    result["role_mapping"] = (identify_lifted(geometry)
                              if not record["metadata"]["extensions"] else None)
    return result

"""Enumerate a finite integer-grid guillotine family without naming any side.

An ordered history may stop after any number of cuts from zero to max_cuts.
At each step one existing rectangular cell is split across its entire width
or height at a strictly interior integer grid coordinate. The exact grid
certificate is retained separately from the drawing: the existing web engine
requires a 900-by-600 frame, so coordinates are scaled into that frame.

No graph-isomorphism, reflection, rotation, or history-order reduction is used.
Only the final documents are deduplicated by the existing undirected input
stroke-set key; differently segmented collinear strokes remain different keys.
A predeclared history cap produces unknown, never a claim of exhaustion.
This family is not all rectangular subdivisions or all plane maps.
"""

from argparse import ArgumentParser
from collections import Counter, deque
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.current_corpus import stroke_set_key
from scripts.validate_global_restart import canonical_document, digest, write_report


FRAME = {"width": 900, "height": 600}
FAMILY = "integer-grid-rectangular-guillotine"
SOURCE_FILES = (
    "AGENTS.md",
    "scripts/exhaustive_rectangular_histories.py",
    "scripts/current_corpus.py",
    "scripts/validate_global_restart.py",
    "tests/test_exhaustive_rectangular_histories.py",
)


class GenerationIncomplete(RuntimeError):
    """A concrete unvisited history witnesses that a resource cap truncated us."""

    def __init__(self, history_limit, emitted, next_depth, next_history_key):
        super().__init__("history_limit reached before the next legal history")
        self.details = {
            "reason": "history_limit", "history_limit": history_limit,
            "emitted_histories": emitted, "next_history_depth": next_depth,
            "next_history_key": next_history_key,
        }


def _validate_parameters(width, height, max_cuts, history_limit):
    """Reject booleans, floats and absent limits rather than silently coercing."""
    for name, value, minimum in (
        ("width", width, 1), ("height", height, 1),
        ("max_cuts", max_cuts, 0), ("history_limit", history_limit, 1),
    ):
        if type(value) is not int or value < minimum:
            raise ValueError(f"{name} must be an integer >= {minimum}")


def _legal_cuts(cells):
    """Visit cells lexicographically, then vertical before horizontal cuts."""
    for cell in cells:
        x0, y0, x1, y1 = cell
        for coordinate in range(x0 + 1, x1):
            yield cell + ("vertical", coordinate)
        for coordinate in range(y0 + 1, y1):
            yield cell + ("horizontal", coordinate)


def _split(cut):
    """Return exact child rectangles and endpoints for one legal grid cut."""
    x0, y0, x1, y1, axis, coordinate = cut
    if axis == "vertical":
        return ((x0, y0, coordinate, y1), (coordinate, y0, x1, y1)), (
            (coordinate, y0), (coordinate, y1))
    return ((x0, y0, x1, coordinate), (x0, coordinate, x1, y1)), (
        (x0, coordinate), (x1, coordinate))


def _scaled_point(point, width, height):
    """Use integral document coordinates whenever the rational scale permits.

    Grid legality is exact. Other widths/heights may need floating drawing
    coordinates and must separately pass the existing geometry engine limits.
    This adapter does not certify that engine's numerical acceptance.
    """
    coordinates = []
    for value, extent, grid_extent in zip(point, (900, 600), (width, height)):
        numerator = value * extent
        coordinates.append(numerator // grid_extent if numerator % grid_extent == 0
                           else numerator / grid_extent)
    return coordinates


def _document(width, height, cuts):
    """Discard order only in the geometry input, not in its history evidence."""
    strokes = []
    for cut in cuts:
        _, (first, second) = _split(cut)
        strokes.append({"a": _scaled_point(first, width, height),
                        "b": _scaled_point(second, width, height)})
    return canonical_document({"frame": dict(FRAME), "strokes": strokes})


def _history_key(width, height, cuts):
    """Hash exact ordered grid instructions, independent of drawing rounding."""
    return digest({"family": FAMILY, "grid_width": width, "grid_height": height,
                   "ordered_cuts": cuts})


def _row(width, height, cells, cuts, parent_keys, prefix_keys):
    """Materialize a fresh public certificate from immutable internal tuples."""
    key = _history_key(width, height, cuts)
    document = _document(width, height, cuts)
    geometry_key = stroke_set_key(document)
    steps = []
    for step, cut in enumerate(cuts, 1):
        children, segment = _split(cut)
        steps.append({"step": step, "cell": list(cut[:4]), "axis": cut[4],
                      "coordinate": cut[5], "children": [list(c) for c in children],
                      "grid_segment": [list(point) for point in segment]})
    return {"key": key, "family": FAMILY, "seed": None, "depth": len(cuts),
            "parent_history_key": parent_keys[-1] if parent_keys else None,
            "prefix_history_keys": list(parent_keys + (key,)),
            "prefix_keys": list(prefix_keys + (geometry_key,)),
            "geometry_key": geometry_key, "steps": steps,
            "cells": [list(cell) for cell in cells], "document": document}


def iter_histories(width=3, height=3, max_cuts=4, *, history_limit=1_000_000):
    """Yield every ordered history of lengths 0..max_cuts in breadth-first order.

    Each history includes exact integer cells, the selected cell and two child
    cells for every step, all ancestral history/geometry keys, and an exportable
    document. All prefixes are themselves emitted histories. Output mutation
    cannot modify the private immutable search state.

    A cap is checked only when another actual history exists: a limit exactly
    equal to the exhaustive size therefore completes. A truncated iterator
    raises GenerationIncomplete; build_inventory catches it as status unknown.
    Consumers stopping iteration themselves have not established completeness.
    """
    _validate_parameters(width, height, max_cuts, history_limit)
    # Queue entries store exact geometry, ordered instructions and ancestral
    # keys. They contain no color, solver state, or parsed planar embedding.
    pending = deque([(((0, 0, width, height),), (), (), ())])
    emitted = 0
    while pending:
        cells, cuts, parents, prefixes = pending.popleft()
        # The root is the only prequeued row. Later queued rows were cap-checked
        # when discovered, so both emitted and queued states stay bounded.
        row = _row(width, height, cells, cuts, parents, prefixes)
        history_key, geometry_key = row["key"], row["geometry_key"]
        emitted += 1
        yield row
        if len(cuts) >= max_cuts:
            continue
        for cut in _legal_cuts(cells):
            children, _ = _split(cut)
            child_cells = tuple(sorted(tuple(c for c in cells if c != cut[:4]) + children))
            child_cuts = cuts + (cut,)
            if emitted + len(pending) >= history_limit:
                # Drain already-discovered earlier BFS rows before raising, so
                # the prefix of the full enumeration contains exactly the cap.
                next_key = _history_key(width, height, child_cuts)
                while pending:
                    queued = pending.popleft()
                    emitted += 1
                    yield _row(width, height, *queued)
                raise GenerationIncomplete(history_limit, emitted, len(child_cuts), next_key)
            pending.append((child_cells, child_cuts,
                            parents + (history_key,), prefixes + (geometry_key,)))


def _source_hashes():
    """Bind generator, shared canonicalization/key helpers, tests and protocol."""
    return {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def build_inventory(width=3, height=3, max_cuts=4, history_limit=1_000_000):
    """Collect all histories and geometry-only deduplication with honest status.

    records is directly accepted by export_geometries(records). Every historical
    prefix reference is retained as an alias, including repeated empty frames.
    The function performs no naming, exact coloring, or Node geometry export.
    """
    _validate_parameters(width, height, max_cuts, history_limit)
    before = _source_hashes()
    inventory, histories = {}, []
    truncation = None
    try:
        for row in iter_histories(width, height, max_cuts, history_limit=history_limit):
            document = row.pop("document")
            key = row["geometry_key"]
            if key not in inventory:
                inventory[key] = {"key": key, "document": document, "aliases": []}
            elif inventory[key]["document"] != document:
                raise AssertionError("stroke-set hash collision")
            histories.append(row)
            for step, prefix_key in enumerate(row["prefix_keys"]):
                # Breadth-first order guarantees each ancestor was registered.
                inventory[prefix_key]["aliases"].append({
                    "kind": "history_prefix", "history": row["key"], "step": step,
                    "prefix_history_key": row["prefix_history_keys"][step],
                })
    except GenerationIncomplete as exc:
        truncation = exc.details
    after = _source_hashes()
    unchanged = before == after
    complete = truncation is None and unchanged
    counts = Counter(row["depth"] for row in histories)
    geometry_counts = Counter(len(row["document"]["strokes"]) for row in inventory.values())
    summary = {
        "histories": len(histories), "distinct_geometries": len(inventory),
        "history_prefix_references": sum(len(row["prefix_keys"]) for row in histories),
        "histories_by_cuts": {str(k): counts[k] for k in range(max_cuts + 1)},
        "geometries_by_cuts": {str(k): geometry_counts[k] for k in range(max_cuts + 1)},
        "max_cuts_histories": counts[max_cuts],
        "complete_depths": list(range(max_cuts + 1)) if complete else (
            list(range(truncation["next_history_depth"])) if truncation and unchanged else []),
    }
    return {
        "schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "Generation only: exhaustive bounded integer-grid guillotine histories",
        "family": FAMILY, "status": "complete" if complete else "unknown",
        "generation_complete": complete,
        "parameters": {"width": width, "height": height, "max_cuts": max_cuts,
                       "history_limit": history_limit, "drawing_frame": dict(FRAME)},
        "summary": summary, "records": list(inventory.values()), "histories": histories,
        "truncation": truncation, "source_sha256": before, "source_sha256_end": after,
        "sources_unchanged": unchanged, "policy_runs": 0, "oracle_runs": 0,
        "geometry_export_status": "not_run",
        "input_sha256": digest({"width": width, "height": height,
                                "max_cuts": max_cuts, "history_limit": history_limit}),
        "completeness": {
            "objects": "All finite ordered legal histories, including empty and every stopping length up to max_cuts.",
            "basis": "The empty frame is the unique depth-zero history.",
            "induction": "For each history, visit every current cell and every strictly interior integer x or y; each legal next cut occurs once and produces its exact two children.",
            "termination": "Each cut increases cell count by one, up to width*height; max_cuts also bounds depth. A resource cap is reported separately.",
            "ordering": "Breadth first; cells lexicographic (x0,y0,x1,y1); vertical then horizontal; coordinates increasing.",
            "deduplication": "Only canonical undirected input stroke sets with frame; retain every history and prefix alias, collinear segmentation, and grid orientation.",
            "colors": "No color assignment or color symmetry is involved; no precolored states are generated.",
            "scope": "Integer-grid guillotine rectangular subdivisions with full-cell cuts, not all plane maps or all rectangular layouts.",
            "shared_code": "Existing canonical_document and stroke_set_key only; no policy, oracle, or geometry exporter is called by generation.",
            "numerical_boundary": "Exact integer grid certificates are scaled to the engine's 900x600 frame; geometry export and numerical acceptance require separate verification.",
        },
    }


def enumerate_inventory(width=3, height=3, max_cuts=4, *, history_limit=1_000_000):
    """Descriptive alias for build_inventory, with the identical return schema."""
    return build_inventory(width, height, max_cuts, history_limit)


def main(argv=None):
    """Write exclusive generation evidence; unknown returns exit code two."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=3)
    parser.add_argument("--height", type=int, default=3)
    parser.add_argument("--max-cuts", type=int, default=4)
    parser.add_argument("--history-limit", type=int, default=1_000_000)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args(argv)
    paths = [args.output] + ([args.summary] if args.summary else [])
    if any(path.exists() for path in paths) or len({p.resolve() for p in paths}) != len(paths):
        parser.error("choose distinct new output and summary paths")
    try:
        report = build_inventory(args.width, args.height, args.max_cuts, args.history_limit)
    except ValueError as exc:
        parser.error(str(exc))
    write_report(args.output, report)
    if args.summary:
        write_report(args.summary, {k: v for k, v in report.items() if k not in ("records", "histories")})
    print(json.dumps({"status": report["status"], "summary": report["summary"],
                      "truncation": report["truncation"]}, ensure_ascii=False))
    return 0 if report["generation_complete"] else 2


if __name__ == "__main__":
    sys.exit(main())

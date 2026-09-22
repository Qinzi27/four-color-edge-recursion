"""Generate every subset of a bounded grid's interior unit line segments.

This is a second geometric family, not a guillotine-cut enumerator. Bridges,
dangling segments and disconnected islands are retained. Each subset has ONE
canonical representative history, adding its selected segments in fixed order;
the program does not enumerate all possible addition orders. It performs no
geometry export, naming, policy run or oracle call.
"""

from argparse import ArgumentParser
from collections import Counter
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
FAMILY = "interior-grid-unit-segment-subsets"
SOURCE_FILES = ("AGENTS.md", "scripts/exhaustive_grid_subsets.py",
                "tests/test_exhaustive_grid_subsets.py", "scripts/current_corpus.py",
                "scripts/validate_global_restart.py")


def _parameters(width, height, subset_limit):
    """Validate the finite grid and its explicit generation resource cap."""
    for name, value, minimum in (("width", width, 1), ("height", height, 1),
                                 ("subset_limit", subset_limit, 0)):
        if type(value) is not int or value < minimum:
            raise ValueError(f"{name} must be an integer >= {minimum}")


def unit_segments(width, height):
    """Enumerate vertical x/y first, then horizontal y/x, all off the frame."""
    _parameters(width, height, 0)
    vertical = [((x, y), (x, y + 1))
                for x in range(1, width) for y in range(height)]
    horizontal = [((x, y), (x + 1, y))
                  for y in range(1, height) for x in range(width)]
    return tuple(vertical + horizontal)


def _scale(point, width, height):
    """Keep exact integers where possible; retain exact grid evidence as well."""
    values = []
    for coordinate, extent, cells in zip(point, (900, 600), (width, height)):
        numerator = coordinate * extent
        values.append(numerator // cells if numerator % cells == 0 else numerator / cells)
    return values


def _history_key(width, height, mask):
    """Bind the representative to the grid, subset and declared addition order."""
    return digest({"family": FAMILY, "width": width, "height": height,
                   "subset_mask": mask, "addition_order": "increasing-unit-segment-index"})


def _source_hashes():
    """Bind generation and shared document identity helpers, not a policy."""
    return {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def build_grid_inventory(width=3, height=3, subset_limit=4096):
    """Return records/histories compatible with the rectangular inventory API.

    Masks increase from zero. The history for one mask adds its selected bits
    in increasing index order, so each proper prefix has a smaller mask and is
    already a registered record. ``subset_limit`` counts emitted subsets, not
    strokes or policy decisions. A cap below the complete 2^m size yields
    ``status='unknown'`` and the first missing mask; no completeness is claimed.
    """
    _parameters(width, height, subset_limit)
    before = _source_hashes()
    segments = unit_segments(width, height)
    total = 1 << len(segments)
    emitted = min(total, subset_limit)
    records, histories, by_mask = [], [], {}
    for mask in range(emitted):
        chosen = [index for index in range(len(segments)) if mask & (1 << index)]
        strokes = [{"a": _scale(segments[index][0], width, height),
                    "b": _scale(segments[index][1], width, height)} for index in chosen]
        document = canonical_document({"frame": dict(FRAME), "strokes": strokes})
        key = stroke_set_key(document)
        record = {"key": key, "document": document, "aliases": [], "subset_mask": mask}
        records.append(record)
        by_mask[mask] = record
        prefix_masks, steps, prefix = [0], [], 0
        for step, index in enumerate(chosen, 1):
            prefix |= 1 << index
            prefix_masks.append(prefix)
            steps.append({"step": step, "unit_segment_index": index,
                          "grid_segment": [list(point) for point in segments[index]],
                          "prefix_mask": prefix})
        history_key = _history_key(width, height, mask)
        prefix_keys = [by_mask[prefix_mask]["key"] for prefix_mask in prefix_masks]
        prefix_history_keys = [_history_key(width, height, prefix_mask) for prefix_mask in prefix_masks]
        history = {"key": history_key, "family": FAMILY, "seed": None,
                   "depth": len(chosen), "subset_mask": mask, "geometry_key": key,
                   "parent_history_key": prefix_history_keys[-2] if len(chosen) else None,
                   "prefix_history_keys": prefix_history_keys, "prefix_keys": prefix_keys,
                   "prefix_masks": prefix_masks, "steps": steps}
        histories.append(history)
        for step, prefix_mask in enumerate(prefix_masks):
            by_mask[prefix_mask]["aliases"].append({
                "kind": "history_prefix", "history": history_key, "step": step,
                "prefix_history_key": prefix_history_keys[step], "prefix_mask": prefix_mask})
    if len({row["key"] for row in records}) != len(records):
        raise AssertionError("different unit-segment masks unexpectedly share a stroke-set key")
    after = _source_hashes()
    unchanged = before == after
    complete = emitted == total and unchanged
    by_depth = Counter(row["depth"] for row in histories)
    return {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "experiment": "Generation only: interior unit-grid segment subsets with one ordered representative each",
            "family": FAMILY, "status": "complete" if complete else "unknown",
            "generation_complete": complete,
            "parameters": {"width": width, "height": height, "subset_limit": subset_limit,
                           "drawing_frame": dict(FRAME), "unit_segment_count": len(segments)},
            "unit_segments": [{"index": index, "grid_segment": [list(p) for p in segment],
                               "drawing_segment": [_scale(p, width, height) for p in segment]}
                              for index, segment in enumerate(segments)],
            "summary": {"histories": len(histories), "distinct_geometries": len(records),
                        "history_prefix_references": sum(len(h["prefix_keys"]) for h in histories),
                        "expected_subsets": total, "emitted_subsets": emitted,
                        "histories_by_added_segments": {str(k): by_depth[k] for k in range(len(segments) + 1)},
                        "max_depth": max(by_depth, default=None)},
            "records": records, "histories": histories,
            "truncation": None if emitted == total else {
                "reason": "subset_limit", "subset_limit": subset_limit, "emitted_subsets": emitted,
                "expected_subsets": total, "next_mask": emitted},
            "source_sha256": before, "source_sha256_end": after, "sources_unchanged": unchanged,
            "policy_runs": 0, "oracle_runs": 0, "geometry_export_status": "not_run",
            "input_sha256": digest({"width": width, "height": height, "subset_limit": subset_limit,
                                    "unit_segments": segments}),
            "completeness": {
                "objects": "Every subset of m=(width-1)*height+(height-1)*width interior unit segments; precisely one fixed-order history for each subset.",
                "basis": "The empty subset mask 0 is included and has a one-element empty-frame prefix list.",
                "enumeration": "Integer masks 0..2^m-1 bijectively encode every segment subset; a cap emits an initial mask interval only.",
                "ordering": "Vertical segments by increasing x then y; horizontal segments by increasing y then x. Within each history add selected indices increasingly.",
                "prefixes": "Every proper prefix mask is smaller and already recorded. Every alias is retained; repeated references are not independent inputs.",
                "deduplication": "Identity is the canonical undirected input stroke set with frame; no graph-isomorphism, rotation, reflection or collinear-segmentation reduction.",
                "allowed_geometry": "No topology filter: retain bridges, dangling edges, disconnected segments and islands. Existing geometry exporter must separately verify its supported scope.",
                "history_scope": "NOT all segment-addition orders and NOT all plane maps; depth counts added unit segments, not necessarily face-splitting cuts.",
                "colors": "No colors, precolorings or color symmetry are generated.",
                "shared_code": "Existing canonical_document and stroke_set_key only; no policy, oracle or Node geometry call.",
                "numerical_boundary": "Exact grid evidence is scaled into 900x600; non-integral scales and geometry acceptance require separate checking."}}


def main(argv=None):
    """Write new generation evidence; a capped inventory exits with code two."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=3)
    parser.add_argument("--height", type=int, default=3)
    parser.add_argument("--subset-limit", type=int, default=4096)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args(argv)
    paths = [args.output] + ([args.summary] if args.summary else [])
    if any(path.exists() for path in paths) or len({path.resolve() for path in paths}) != len(paths):
        parser.error("choose distinct new output and summary paths")
    try:
        report = build_grid_inventory(args.width, args.height, args.subset_limit)
    except ValueError as exc:
        parser.error(str(exc))
    write_report(args.output, report)
    if args.summary:
        write_report(args.summary, {key: value for key, value in report.items() if key not in ("records", "histories")})
    print(json.dumps({"status": report["status"], "summary": report["summary"],
                      "truncation": report["truncation"]}, ensure_ascii=False))
    return 0 if report["generation_complete"] else 2


if __name__ == "__main__":
    sys.exit(main())

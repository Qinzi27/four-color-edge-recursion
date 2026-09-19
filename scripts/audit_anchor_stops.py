"""Distinguish missing common anchors from a common anchor in a new child.

This read-only classification does not choose names, migrate anchors, retry a
cut or continue a history. It preserves the completed continuation experiment.
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
from scripts.audit_retained_blocks import rectangle_adjacency, unpack_state, dual_anchor_paths


def classify(row):
    """Rebuild exact contacts, preserving old/new side identity distinction."""
    proposed = unpack_state(row["last_proposed_state"])
    adjacency = rectangle_adjacency(proposed)
    assert {v: sorted(ns) for v, ns in adjacency.items()} == row["stop_diagnosis"]["adjacency"]
    vertices = set(adjacency)
    parent = row["events"][-1]["parent"]
    children = {parent + ".l", parent + ".r"}
    outside_missing = sorted(vertices - {"outside"} - adjacency["outside"])
    universal = [side for side in proposed.sides if adjacency[side.id] == vertices - {side.id}]
    old_anchors = [s for s in universal if s.id not in children]
    new_anchors = [s for s in universal if s.id in children]
    if outside_missing:
        category = "outside_not_universal"
    elif old_anchors:
        category = "uncut_common_anchor_unhandled"
    elif new_anchors:
        category = "common_anchor_only_in_new_child"
        assert all(dual_anchor_paths(adjacency, s.id) is not None for s in new_anchors)
    else:
        category = "no_second_common_anchor_of_any_age"
    return {"family": row["family"], "seed": row["seed"], "inherit": row["inherit"],
            "stopped_step": row["committed_steps"] + 1,
            "baseline_stopped_step": row["baseline_committed_steps"] + 1,
            "extra_steps": row["extra_committed_steps"], "category": category,
            "cut": row["events"][-1]["cut"], "outside_missing": outside_missing,
            "outside_missing_bounds": [s.bounds for s in proposed.sides if s.id in outside_missing],
            "universal_old_ids": [s.id for s in old_anchors],
            "universal_new_children": [{"id": s.id, "bounds": s.bounds,
                                        "diagnostic_name_not_committed": s.symbol,
                                        "residual_paths": dual_anchor_paths(adjacency, s.id)} for s in new_anchors],
            "missing_by_side": {v: sorted(vertices - {v} - ns) for v, ns in adjacency.items()}}


def main():
    """Write a fresh portable classification report; refuse all overwrites."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; choose a new filename")
    raw = args.input.read_bytes()
    source = json.loads(raw)
    assert source["schema_version"] == 1
    records = [classify(row) for row in source["runs"] if row["status"] == "blocked_sync_required"]
    files = ["scripts/audit_anchor_stops.py", "scripts/audit_retained_blocks.py"]
    report = {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Structural classification only; no new anchor-migration rule or successful coloring claimed.",
              "input": {"filename": args.input.name, "sha256": sha256(raw).hexdigest()},
              "source_sha256": {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in files},
              "summary": {"blocked_runs": len(records), "categories": dict(Counter(r["category"] for r in records))},
              "records": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Predeclare and run a bounded, sampled 5x5 grid commitment probe.

This is 384 distinct Bernoulli masks, NOT exhaustive grid coverage and NOT an
addition to the frozen small-exhaustion scores. Each policy finishes before
the offline audit starts. Solved runs use their actual final coloring as a
witness extending every explicit commitment; conflicts receive the separate
exact per-commit audit, with no oracle answer fed back into the candidate.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import gzip
import json
from pathlib import Path
import platform
import random
import subprocess
import sys
from time import monotonic

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.structural_restart import POLICY, restart_structural_names
from scripts.audit_commit_extendibility import audit_candidate, side_anchors, source_hashes
from scripts.current_corpus import stroke_set_key
from scripts.exhaustive_grid_subsets import FRAME, _scale, unit_segments
from scripts.validate_frontier_restart import independent_geometry
from scripts.validate_global_restart import canonical_document, digest
from scripts.validate_structural_restart import verify_run


SEED = 20262121
DENSITIES = (0.60, 0.75, 0.90)
PER_DENSITY = 128
WALL_LIMIT_SECONDS = 600


def write_new(path, value):
    """Preserve prior inputs and reports with exclusive creation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if path.suffix == ".gz":
        payload = gzip.compress(payload, mtime=0)
    with path.open("xb") as stream:
        stream.write(payload)


def hashes():
    """Freeze the existing policy/audit closure plus this independent runner."""
    result = source_hashes()
    name = "scripts/probe_grid_commitments.py"
    result[name] = sha256((ROOT / name).read_bytes()).hexdigest()
    return result


def build_records():
    """Sample each bit once per attempt; reject globally duplicate masks."""
    segments = unit_segments(5, 5)
    if len(segments) != 40:
        raise AssertionError("5x5 grid must expose exactly forty interior unit segments")
    rng, seen, records, attempt = random.Random(SEED), set(), [], 0
    for density in DENSITIES:
        accepted = 0
        while accepted < PER_DENSITY:
            attempt += 1
            flags = [rng.random() < density for _ in segments]
            mask = sum(1 << i for i, present in enumerate(flags) if present)
            if mask in seen:
                continue
            seen.add(mask)
            accepted += 1
            chosen = [i for i, present in enumerate(flags) if present]
            document = canonical_document({"frame": dict(FRAME), "strokes": [
                {"a": _scale(segments[i][0], 5, 5), "b": _scale(segments[i][1], 5, 5)}
                for i in chosen]})
            records.append({"ordinal": len(records), "key": stroke_set_key(document),
                            "seed": SEED, "density": density, "density_ordinal": accepted - 1,
                            "rng_attempt": attempt, "mask": mask, "mask_hex": f"{mask:010x}",
                            "chosen_segment_indices": chosen, "document": document})
    if len(records) != 384 or len({row["key"] for row in records}) != 384:
        raise AssertionError("sampled masks must have distinct document identities")
    return records, attempts_metadata(attempt)


def attempts_metadata(attempt):
    """Record rejected duplicates without changing the fixed sampling rule."""
    return {"total_mask_attempts": attempt, "duplicate_masks_rejected": attempt - 384,
            "random_draws": attempt * 40}


def prepare(directory):
    """Save all documents and source hashes before any policy or export run."""
    records, generation = build_records()
    manifest = {"schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "policy": POLICY, "python_version": platform.python_version(),
                "scope": {"kind": "sampled_exploratory_probe", "width": 5, "height": 5,
                          "unit_segment_count": 40, "seed": SEED, "densities": DENSITIES,
                          "distinct_masks_per_density": PER_DENSITY,
                          "sampling": "one continuous random.Random stream; forty Bernoulli draws per attempt; reject duplicates across all densities",
                          "prefixes": "only the 384 final masks; no all-prefix or all-history claim",
                          "not_merged_into": "frozen exhaustive small-grid results"},
                "resources": {"wall_limit_seconds": WALL_LIMIT_SECONDS, "workers": 1,
                              "oracle_node_limit_per_commit": 1000000,
                              "literal_assignment_limit": 0, "geometry_batch_size": 32},
                "audit_protocol": {"solved": "verify_run plus actual final witness checked against original edges and every phase commitment",
                                   "conflict": "audit_candidate only after the candidate completes; exact per-commit evidence",
                                   "cutoff": "unfinished cases remain unknown, not failed or passed",
                                   "outside": "geometry export rejection retained separately"},
                "generation": generation, "source_sha256": hashes(), "records": records,
                "policy_runs_before_manifest": 0, "oracle_runs_before_manifest": 0}
    write_new(directory / "manifest.json", manifest)
    return manifest


def worker(geometry, checkpoint):
    """Finish the frozen policy, then audit without influencing its choices."""
    candidate = restart_structural_names(geometry)
    if candidate["status"] != "solved":
        # A later exact audit timeout must not erase the already found conflict.
        write_new(checkpoint, {"geometry": geometry, "candidate": candidate})
        audit = audit_candidate(geometry, candidate, node_limit=1000000, assignment_limit=0)
        return {"status": "conflict", "candidate": candidate, "audit": audit,
                "first_bad_commitment_found": audit["first_bad_commitment"] is not None}
    replay = verify_run(geometry, candidate)
    plane, adjacent = independent_geometry(geometry)
    colors = candidate["colors"]
    if len(colors) != len(adjacent) or any(type(c) is not int or c not in (1, 2, 3, 4) for c in colors):
        raise AssertionError("solved candidate has invalid literal colors")
    if any(colors[v] == colors[u] for v, neighbors in enumerate(adjacent) for u in neighbors):
        raise AssertionError("final coloring violates an original shared boundary")
    phases = []
    for index, phase in enumerate(candidate["propagation_phases"]):
        anchors = side_anchors(plane, phase["anchors_by_dart"])
        if any(colors[v] != color for v, color in anchors.items()):
            raise AssertionError("final coloring does not extend a recorded commitment")
        phases.append({"phase": index, "anchors": [[v, c] for v, c in sorted(anchors.items())]})
    return {"status": "solved", "candidate_sha256": digest(candidate), "colors": colors,
            "choices": candidate["choices"], "trace": candidate["trace"],
            "statistics": candidate["statistics"], "candidate_replay": replay,
            "all_phase_extension_witness": {"kind": "actual_final_coloring", "phases": phases,
                                             "passed": True},
            "exhaustive_rule_soundness": "not_enumerated", "oracle_runs": 0}


def execute(directory):
    """Run the frozen manifest with process timeouts and retain every outcome."""
    manifest_path = directory / "manifest.json"
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    records, generation = build_records()
    if digest(records) != digest(manifest["records"]) or generation != manifest["generation"]:
        raise AssertionError("manifest does not match the fixed seeded sample")
    if manifest["source_sha256"] != hashes() or manifest["policy"] != POLICY:
        raise AssertionError("source or policy changed after predeclaration")
    started, rows = monotonic(), []
    deadline = started + WALL_LIMIT_SECONDS
    for start in range(0, len(records), 32):
        batch = records[start:start + 32]
        remaining = deadline - monotonic()
        exported, export_error = [], None
        if remaining > 0:
            request = {"cases": [{"key": row["key"], "document": row["document"]} for row in batch]}
            try:
                process = subprocess.run(["node", str(ROOT / "scripts/restart-geometry.mjs")], cwd=ROOT,
                                         input=json.dumps(request), capture_output=True, text=True,
                                         encoding="utf-8", check=True, timeout=remaining)
                exported_payload = json.loads(process.stdout)
                exported = exported_payload["results"]
                if exported_payload["coloring_performed"] or len(exported) != len(batch):
                    raise AssertionError("geometry-only batch contract differs")
            except Exception as error:
                export_error = {"type": type(error).__name__, "message": str(error)}
        for position, record in enumerate(batch):
            base = {key: record[key] for key in ("ordinal", "key", "mask", "density", "seed")}
            remaining = deadline - monotonic()
            if remaining <= 0 or not exported:
                rows.append({**base, "status": "unknown", "reason": "wall_limit" if remaining <= 0 else "geometry_export_error",
                             "error": export_error})
                continue
            item = exported[position]
            if item["key"] != record["key"]:
                raise AssertionError("exported record identity differs")
            if item["status"] != "geometry_ok":
                rows.append({**base, "status": "outside_geometry_export", "export": item})
                continue
            geometry = item["geometry"]
            checkpoint = directory / f"conflict-candidate-{record['ordinal']:03d}.json.gz"
            try:
                process = subprocess.run([sys.executable, "-X", "utf8", str(Path(__file__).resolve()),
                                          "--worker", "--checkpoint", str(checkpoint)], cwd=ROOT,
                                         input=json.dumps(geometry), capture_output=True, text=True,
                                         encoding="utf-8", check=True, timeout=remaining)
                result = json.loads(process.stdout)
                row = {**base, **result, "geometry": geometry}
                rows.append(row)
                if row["status"] == "conflict":
                    write_new(directory / f"conflict-audit-{record['ordinal']:03d}.json.gz", row)
                    print(json.dumps({"event": "conflict", "ordinal": record["ordinal"],
                                      "bad_commitment": row["first_bad_commitment_found"]}), flush=True)
            except subprocess.TimeoutExpired:
                rows.append({**base, "status": "unknown", "reason": "wall_limit", "geometry": geometry,
                             "candidate_checkpoint": checkpoint.name if checkpoint.exists() else None})
            except Exception as error:
                rows.append({**base, "status": "audit_failed", "geometry": geometry,
                             "error": {"type": type(error).__name__, "message": str(error),
                                       "stderr": getattr(error, "stderr", None)},
                             "candidate_checkpoint": checkpoint.name if checkpoint.exists() else None})
        print(json.dumps({"completed_records": len(rows), "counts": dict(Counter(row["status"] for row in rows)),
                          "elapsed_seconds": round(monotonic() - started, 2)}), flush=True)
    unchanged = hashes() == manifest["source_sha256"]
    counts = dict(Counter(row["status"] for row in rows))
    complete = unchanged and not any(row["status"] in ("unknown", "audit_failed") for row in rows)
    report = {"schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "status": "complete" if complete else "incomplete", "counts": counts,
              "input_count": len(records), "record_count": len(rows),
              "scope": manifest["scope"], "resources": manifest["resources"],
              "manifest_sha256": sha256(raw).hexdigest(), "source_sha256": manifest["source_sha256"],
              "sources_unchanged": unchanged, "elapsed_seconds": monotonic() - started,
              "actual_bad_commitments": sum(bool(row.get("first_bad_commitment_found")) for row in rows),
              "rows": rows, "claim": "sample outcomes only; not exhaustive or a universal completion guarantee"}
    write_new(directory / "report.json.gz", report)
    return report


def main():
    """Preparation and execution remain distinct replayable operations."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--directory", type=Path)
    args = parser.parse_args()
    if args.worker:
        if args.checkpoint is None:
            parser.error("worker requires a unique checkpoint path")
        print(json.dumps(worker(json.load(sys.stdin), args.checkpoint)))
        return
    if args.prepare == args.execute:
        parser.error("choose exactly one of --prepare or --execute")
    if args.directory is None:
        parser.error("choose a new directory under outputs/_local")
    if args.prepare:
        manifest = prepare(args.directory)
        print(json.dumps({"manifest": str(args.directory / "manifest.json"), "records": len(manifest["records"]),
                          "generation": manifest["generation"], "policy_runs": 0}))
    else:
        report = execute(args.directory)
        print(json.dumps({"report": str(args.directory / "report.json.gz"), "status": report["status"],
                          "counts": report["counts"], "actual_bad_commitments": report["actual_bad_commitments"]}))


if __name__ == "__main__":
    main()

"""Replay the ENTIRE frozen inventory with bounded parallel proof checking.

Rules are never changed or retried. Each geometric prefix is a fresh naming
problem even after another prefix fails. Reuse of a deduplicated drawing is
only memoization of identical input, not omission of its history references.
Checkpoints contain independently audited results and are never overwritten.
"""

from argparse import ArgumentParser
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.frontier_restart import restart_frontier_names
from fourcolor.global_restart import restart_line_names
from fourcolor.relation_frontier import POLICY, restart_relation_frontier_names
from scripts.validate_frontier_restart import (
    EXISTING, HELDOUT, file_sha, json_value, paired_counts, read_json,
    summarize_frontier, verify_result,
)
from scripts.validate_global_restart import compact_result, digest, export_geometries, write_report
from scripts.validate_relation_frontier import independent_check

SOURCE = ROOT / "outputs/frontier-restart-all-2026-09-19.json.gz"
DIAGNOSTIC = ROOT / "outputs/relation-frontier-diagnostic-2026-09-19.json.gz"
POLICIES = ("closed-support", "tight-hall", POLICY)
EXACT_FIELDS = ("status", "domains", "anchors_by_dart", "colors", "trace_sha256")
SOURCE_FILES = (
    "fourcolor/relation_frontier.py", "fourcolor/relation_names.py",
    "fourcolor/frontier_restart.py", "fourcolor/global_restart.py",
    "fourcolor/closed_support.py", "fourcolor/whole_lines.py",
    "fourcolor/joint_lines.py", "fourcolor/weighted_lines.py",
    "fourcolor/embedding.py", "fourcolor/line_names.py", "web/engine.js",
    "scripts/restart-geometry.mjs", "scripts/validate_relation_frontier.py",
    "scripts/validate_frontier_restart.py", "scripts/validate_global_restart.py",
    "scripts/validate_relation_frontier_full.py",
)


def require(condition, message):
    """Do not let optimized Python silently disable inventory/provenance guards."""
    if not condition:
        raise AssertionError(message)


def exact_run(candidate, saved):
    """Exclude timing, but require identical states and deterministic choices."""
    normalized = json_value(candidate)
    for field in EXACT_FIELDS:
        require(normalized[field] == saved[field], "frozen result drift: " + field)


def source_hashes():
    """Hash algorithm, geometry and proof-checker code, not private machine paths."""
    return {path: file_sha(ROOT / path) for path in SOURCE_FILES}


def validate_inventory(previous):
    """Require all declared inputs and references before any candidate is run."""
    require(previous["full_corpus_run"] and previous["smoke_limit"] is None, "source is smoke")
    rows = previous["drawings"]
    keys = {r["key"] for r in rows}
    old = {r["key"] for r in rows if EXISTING in r["cohorts"]}
    newer = {r["key"] for r in rows if HELDOUT in r["cohorts"]}
    require(len(keys) == len(rows) == 7069, "complete unique drawing inventory required")
    require(len(old) == 6113 and len(newer) == 961 and len(old & newer) == 5,
            "cohort denominators drifted")
    require(keys == old | newer, "unaccounted cohort")
    histories, statics = previous["histories"], previous["static_inputs"]
    require(len(histories) == 363 and len(statics) == 302, "history/static inventory drift")
    require(sum(len(h["prefix_keys"]) for h in histories) == 7678, "prefix references drift")
    require(all(k in keys for h in histories for k in h["prefix_keys"]), "missing prefix")
    require(all(s["geometry_key"] in keys for s in statics), "missing static map")
    return sorted(rows, key=lambda row: row["key"])


def failure_rank(detail):
    """A reproducible small example order, not a search for favorable outcomes."""
    return detail["face_count"], len(detail["document"]["strokes"]), detail["key"]


def run_batch(payload):
    """Worker: recreate geometry, run once per policy, verify EVERY proof phase."""
    index, saved_rows, diagnostic, named_keys = payload
    records, detailed = [], {}
    least_failure = None
    repeated_diagnostics = 0
    for saved, exported in zip(saved_rows, export_geometries(saved_rows)):
        require(exported["key"] == saved["key"] and exported["status"] == "geometry_ok",
                "geometry export changed or failed")
        geometry = exported["geometry"]
        require(digest(geometry) == saved["geometry_sha256"], "geometry hash changed")
        record = {key: value for key, value in saved.items() if key != "runs"}
        record["runs"] = {}
        raw = {}
        for policy in POLICIES:
            start = perf_counter()
            result = (restart_line_names(geometry, policy) if policy == "closed-support" else
                      restart_frontier_names(geometry, policy) if policy == "tight-hall" else
                      restart_relation_frontier_names(geometry))
            elapsed = perf_counter() - start
            start = perf_counter()
            checked = independent_check(geometry, result) if policy == POLICY else verify_result(geometry, result)
            require(checked["passed"], "independent proof verification failed")
            compact = compact_result(result)
            compact.update({"verification": checked, "runtime_seconds": elapsed,
                            "audit_seconds": perf_counter() - start,
                            "hall_conflict": result.get("hall_conflict"),
                            "hall_derivation_events_including_recomputations": result.get(
                                "hall_derivation_events_including_recomputations", 0)})
            if policy != POLICY:
                exact_run(compact, saved["runs"][policy])
            else:
                compact["propagation_phases_sha256"] = digest(result["propagation_phases"])
                compact["hall_derivation_events_including_recomputations"] = sum(
                    event.get("rule") == "hall-reservation"
                    for call in result["propagation_phases"] for phase in call["outcome"]["phases"]
                    for event in phase["hall_trace"])
                if saved["key"] in diagnostic:
                    earlier = diagnostic[saved["key"]]["runs"][POLICY]
                    exact_run(compact, earlier)
                    require(compact["propagation_phases_sha256"] == earlier["propagation_phases_sha256"],
                            "previous diagnostic proof changed")
                    repeated_diagnostics += 1
            record["runs"][policy] = compact
            raw[policy] = result
        records.append(record)
        if saved["key"] in named_keys or raw[POLICY]["status"] != "solved":
            detail = {"key": saved["key"], "document": saved["document"],
                      "face_count": saved["face_count"], "geometry": geometry,
                      "baseline": raw["tight-hall"], "outcome": raw[POLICY]}
            if saved["key"] in named_keys:
                detailed[saved["key"]] = detail
            if raw[POLICY]["status"] != "solved" and (
                    least_failure is None or failure_rank(detail) < failure_rank(least_failure)):
                least_failure = detail
    require(len(records) == len(saved_rows), "worker dropped an input")
    return {"index": index, "records": records, "detailed_examples": detailed,
            "least_failure": least_failure, "diagnostic_exact_reproductions": repeated_diagnostics}


def hall_comparisons(records, histories, statics, history_results):
    """Add paired comparisons against the immediate predecessor as well."""
    by_key = {r["key"]: r for r in records}
    index = {(r["key"], r["policy"]): r for r in history_results}
    output = []
    for cohort in ("combined", EXISTING, HELDOUT):
        drawings = [r for r in records if cohort == "combined" or cohort in r["cohorts"]]
        sequences = [h for h in histories if cohort == "combined" or h["cohort"] == cohort]
        inputs = [s for s in statics if cohort == "combined" or s["cohort"] == cohort]
        status_pair = lambda row: (row["runs"]["tight-hall"]["status"] == "solved",
                                   row["runs"][POLICY]["status"] == "solved")
        output.append({"cohort": cohort, "baseline": "tight-hall", "candidate": POLICY,
                       "distinct_drawings": paired_counts(status_pair(r) for r in drawings),
                       "all_history_prefixes": paired_counts((index[(h["key"], "tight-hall")]["all_prefixes_solved"],
                                                              index[(h["key"], POLICY)]["all_prefixes_solved"])
                                                             for h in sequences),
                       "history_final": paired_counts((index[(h["key"], "tight-hall")]["final_status"] == "solved",
                                                        index[(h["key"], POLICY)]["final_status"] == "solved")
                                                       for h in sequences),
                       "static_final": paired_counts(status_pair(by_key[s["geometry_key"]]) for s in inputs)})
    return output


def build_report(source, diagnostic_path, checkpoint_dir, workers=4, batch_size=25, limit=None, resume=False):
    """Run immutable batches; reuse checkpoints only for identical code and input."""
    require(sys.flags.optimize == 0, "proof replay must run without Python -O")
    began = perf_counter()
    previous, diagnostic_report = read_json(source), read_json(diagnostic_path)
    rows = validate_inventory(previous)
    hashes = source_hashes()
    require(all(hashes[p] == value for p, value in diagnostic_report["source_sha256"].items()),
            "diagnostic algorithm/checker changed")
    if limit is not None:
        rows = rows[:limit]
    selected = {r["key"] for r in rows}
    histories = [h for h in previous["histories"] if set(h["prefix_keys"]) <= selected]
    statics = [s for s in previous["static_inputs"] if s["geometry_key"] in selected]
    diagnostic = {r["key"]: r for r in diagnostic_report["drawings"]}
    named = set(diagnostic_report["named_examples"].values())
    manifest = {"source_evidence": {"filename": source.name, "sha256": file_sha(source)},
                "diagnostic_evidence": {"filename": diagnostic_path.name, "sha256": file_sha(diagnostic_path)},
                "source_sha256": hashes, "selected_keys": [r["key"] for r in rows],
                "batch_size": batch_size, "smoke_limit": limit, "policies": list(POLICIES)}
    manifest_path = checkpoint_dir / "manifest.json"
    if resume:
        require(read_json(manifest_path) == manifest, "checkpoint source/code/inventory mismatch")
    else:
        checkpoint_dir.mkdir(parents=True, exist_ok=False)
        write_report(manifest_path, manifest)
    jobs, pieces, part_hashes = [], {}, {}
    for index, start in enumerate(range(0, len(rows), batch_size)):
        part_path = checkpoint_dir / f"part-{index:05d}.json.gz"
        batch = rows[start:start + batch_size]
        if resume and part_path.exists():
            checksum = read_json(part_path.with_suffix(part_path.suffix + ".sha256.json"))
            require(checksum == {"filename": part_path.name, "sha256": file_sha(part_path)},
                    "checkpoint bytes fail their saved checksum")
            piece = read_json(part_path)
            require(piece["index"] == index and [r["key"] for r in piece["records"]] == [r["key"] for r in batch],
                    "checkpoint batch coverage mismatch")
            pieces[index] = piece
            part_hashes[part_path.name] = file_sha(part_path)
        else:
            jobs.append((index, batch, {r["key"]: diagnostic[r["key"]] for r in batch if r["key"] in diagnostic}, named))
    pool = ProcessPoolExecutor(max_workers=workers) if workers > 1 else None
    try:
        completed = pool.map(run_batch, jobs) if pool is not None else map(run_batch, jobs)
        for piece in completed:
            part_path = checkpoint_dir / f"part-{piece['index']:05d}.json.gz"
            require(not part_path.exists(), "refuse to overwrite a checkpoint")
            write_report(part_path, piece)
            write_report(part_path.with_suffix(part_path.suffix + ".sha256.json"),
                         {"filename": part_path.name, "sha256": file_sha(part_path)})
            pieces[piece["index"]] = piece
            part_hashes[part_path.name] = file_sha(part_path)
            count = sum(len(p["records"]) for p in pieces.values())
            solved = sum(r["runs"][POLICY]["status"] == "solved" for p in pieces.values() for r in p["records"])
            print({"drawings_checked": count, "total": len(rows), "candidate_solved": solved,
                   "candidate_not_solved": count - solved, "seconds": round(perf_counter() - began, 1)}, flush=True)
    finally:
        if pool is not None:
            pool.shutdown(wait=True)
    records = [r for index in sorted(pieces) for r in pieces[index]["records"]]
    require([r["key"] for r in records] == [r["key"] for r in rows], "final coverage mismatch")
    ending = source_hashes()
    require(ending == hashes and manifest["source_evidence"]["sha256"] == file_sha(source)
            and manifest["diagnostic_evidence"]["sha256"] == file_sha(diagnostic_path), "source changed during run")
    summary, history_results, paired = summarize_frontier(records, histories, statics, POLICIES)
    totals = Counter()
    for record in records:
        totals.update({k: v for k, v in record["runs"][POLICY]["verification"].items() if type(v) is int})
    failures = [p["least_failure"] for p in pieces.values() if p["least_failure"] is not None]
    return {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "experiment": "Frozen Hall-pair restart: complete prior inventory and all prefix references",
            "smoke_limit": limit, "full_corpus_run": limit is None, "unseen_holdout": False,
            "source_evidence": manifest["source_evidence"], "diagnostic_evidence": manifest["diagnostic_evidence"],
            "source_sha256": hashes, "source_sha256_end": ending, "source_hashes_unchanged": True,
            "policies": list(POLICIES), "execution": {"workers": workers, "batch_size": batch_size,
                "resumed": resume, "wall_seconds": perf_counter() - began,
                "checkpoint_directory": checkpoint_dir.name, "part_sha256": part_hashes},
            "drawings": records, "histories": histories, "static_inputs": statics,
            "history_results": history_results, "summary": summary, "paired_comparisons": paired,
            "paired_vs_hall": hall_comparisons(records, histories, statics, history_results),
            "independent_checks": 3 * len(records), "baseline_exact_reproductions": 2 * len(records),
            "diagnostic_exact_reproductions": sum(p["diagnostic_exact_reproductions"] for p in pieces.values()),
            "replay_totals": dict(totals),
            "detailed_examples": {k: v for p in pieces.values() for k, v in p["detailed_examples"].items()},
            "least_failure": min(failures, key=failure_rank) if failures else None,
            "limits": ["Complete FINITE prior corpus, not all plane maps or a proof of universal success.",
                "Prior new-seed cohort has now been inspected; it is not an unseen holdout in this run.",
                "Each prefix restarts from geometry; previous failure never removes later inputs.",
                "Source policy frozen; no alternate assignment retries, oracle rescue, or old colors.",
                "Four names are given; nonempty filtering does not prove extendibility.",
                "Checks of valid final names and of conflicting commitments are separate from success counts.",
                "Parallel wall time is not a controlled algorithm speed benchmark."]}


def main():
    """Choose fresh outputs; explicit resume only reuses matching batch evidence."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--diagnostic", type=Path, default=DIAGNOSTIC)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--checkpoints", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or args.summary.exists() or args.output.resolve() == args.summary.resolve():
        parser.error("choose two distinct fresh output files")
    if not 1 <= args.workers <= 8 or args.batch_size < 1 or (args.limit is not None and args.limit < 1):
        parser.error("workers must be 1..8, batch size and optional smoke limit positive")
    report = build_report(args.source, args.diagnostic, args.checkpoints,
                          args.workers, args.batch_size, args.limit, args.resume)
    write_report(args.output, report)
    small = {k: v for k, v in report.items()
             if k not in ("drawings", "histories", "static_inputs", "history_results", "detailed_examples", "least_failure")}
    small["input"] = {"filename": args.output.name, "sha256": file_sha(args.output)}
    small["least_failure_key"] = report["least_failure"]["key"] if report["least_failure"] else None
    write_report(args.summary, small)
    print({"complete": True, "drawings": len(report["drawings"]),
           "independent_checks": report["independent_checks"], "sha256": file_sha(args.output)}, flush=True)


if __name__ == "__main__":
    main()

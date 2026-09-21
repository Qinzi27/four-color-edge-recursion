"""Audit one frozen structural naming attempt on every archived v2 geometry.

The baseline is copied from a hash-bound old report, not rerun or combined with
candidate answers. All candidate transcripts are independently replayed. Full
transcripts are retained for every learned relation and every noncompletion;
other checked transcripts remain reproducible from their hashes and geometry.
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

from fourcolor.level_sides_peer import POLICY as BASELINE
from fourcolor.structural_restart import POLICY, restart_structural_names
from scripts.validate_frontier_restart import file_sha, paired_counts, read_json
from scripts.validate_global_restart import digest, export_geometries, write_report
from scripts.validate_relation_frontier_full import require, validate_inventory
from scripts.validate_structural_restart import verify_run

SOURCE = ROOT / "outputs/level-sides-peer-full-2026-09-19.json.gz"
SOURCE_SHA256 = "5085627be22653ea9b6ea13de5ff851c452a8c702996ee6eda0672d2d72eca07"
EXTRA_SOURCES = (
    "docs/STRUCTURAL_RESTART_RULES-2026-09-21.md",
    "fourcolor/structural_name_relations.py", "fourcolor/structural_restart.py",
    "scripts/validate_structural_restart.py", "scripts/validate_structural_restart_full.py",
    "tests/test_structural_name_relations.py", "tests/test_structural_restart.py",
    "tests/test_structural_restart_validation.py", "tests/test_structural_restart_full.py",
)


def source_hashes(previous):
    """Verify all frozen dependencies and bind each new producer/checker/test."""
    require(previous["source_sha256"] == previous["source_sha256_end"],
            "baseline source hashes drifted")
    current = {name: file_sha(ROOT / name)
               for name in sorted(set(previous["source_sha256"]) | set(EXTRA_SOURCES))}
    require(all(current[name] == expected
                for name, expected in previous["source_sha256"].items()),
            "frozen baseline source changed")
    return current


def compact_candidate(result, check):
    """Preserve actual names and provenance after full independent replay."""
    require(check["passed"], "independent candidate audit failed")
    require(result["policy"] == POLICY and result["status"] in ("solved", "conflict"),
            "unexpected policy or incomplete status")
    compact = {name: result[name] for name in (
        "policy", "status", "domains", "anchors_by_dart", "colors", "choices",
        "backtracks", "old_colors_read", "local_budget", "hall_conflict",
        "statistics", "learned_pairs", "unranked_mothers")}
    compact.update({"verification": check, "independent_check_passed": True,
                    "trace_sha256": digest(result["trace"]),
                    "events_sha256": digest(result["events"]),
                    "proof_queries_sha256": digest(result["proof_queries"]),
                    "propagation_phases_sha256": digest(result["propagation_phases"]),
                    "full_transcript_sha256": digest(result),
                    "hall_derivation_events_including_recomputations": sum(
                        event.get("rule") == "hall-reservation"
                        for call in result["propagation_phases"]
                        for phase in call["outcome"]["phases"] for event in phase["hall_trace"])})
    return compact


def run_batch(payload):
    """Re-export each document, then run and audit the candidate exactly once."""
    index, saved_rows = payload
    exports = export_geometries(saved_rows)
    require(len(exports) == len(saved_rows), "geometry export dropped an input")
    records, detailed = [], {}
    for saved, exported in zip(saved_rows, exports):
        require(exported["key"] == saved["key"] and exported["status"] == "geometry_ok",
                "geometry export key or status changed")
        geometry = exported["geometry"]
        require(digest(geometry) == saved["geometry_sha256"], "geometry hash changed")
        started = perf_counter()
        result = restart_structural_names(geometry)
        runtime = perf_counter() - started
        started = perf_counter()
        check = verify_run(geometry, result)
        audit_seconds = perf_counter() - started
        # Recheck after both calls: an in-place geometry mutation is never an
        # admissible way to turn this drawing into a successful input.
        require(digest(geometry) == saved["geometry_sha256"], "candidate/auditor mutated geometry")
        compact = compact_candidate(result, check)
        compact.update(runtime_seconds=runtime, audit_seconds=audit_seconds)
        row = {name: value for name, value in saved.items() if name != "runs"}
        row["runs"] = {BASELINE: saved["runs"][BASELINE], POLICY: compact}
        records.append(row)
        if result["learned_pairs"] or result["status"] != "solved":
            detailed[saved["key"]] = {
                "key": saved["key"], "aliases": saved["aliases"],
                "document": saved["document"], "face_count": saved["face_count"],
                "geometry": geometry, "outcome": result, "verification": check,
                "archived_baseline": saved["runs"][BASELINE]}
    require(len(records) == len(saved_rows), "worker result coverage changed")
    return {"index": index, "records": records, "detailed_examples": detailed}


def summarize(records, histories, statics):
    """Keep unique drawings, repeated prefixes and final histories separate."""
    by_key = {row["key"]: row for row in records}
    require(len(by_key) == len(records), "duplicate result geometry")
    histories_by_policy, history_results = {}, []
    for policy in (BASELINE, POLICY):
        for history in histories:
            statuses = [by_key[key]["runs"][policy]["status"] for key in history["prefix_keys"]]
            row = {"key": history["key"], "cohort": history["cohort"], "policy": policy,
                   "statuses": statuses, "all_prefixes_solved": all(x == "solved" for x in statuses),
                   "first_failed_prefix": next((i for i, x in enumerate(statuses) if x != "solved"), None),
                   "recoveries": [i for i in range(1, len(statuses))
                                  if statuses[i] == "solved" and statuses[i - 1] != "solved"],
                   "final_status": statuses[-1]}
            histories_by_policy[(history["key"], policy)] = row
            history_results.append(row)
    summaries, comparisons = [], []
    cohorts = ["combined", *sorted({c for row in records for c in row["cohorts"]})]
    for cohort in cohorts:
        drawings = [r for r in records if cohort == "combined" or cohort in r["cohorts"]]
        sequences = [h for h in histories if cohort == "combined" or h["cohort"] == cohort]
        static_rows = [s for s in statics if cohort == "combined" or s["cohort"] == cohort]
        for policy in (BASELINE, POLICY):
            sequence_rows = [histories_by_policy[(h["key"], policy)] for h in sequences]
            summaries.append({
                "cohort": cohort, "policy": policy, "distinct_drawings": len(drawings),
                "statuses": dict(Counter(r["runs"][policy]["status"] for r in drawings)),
                "histories": len(sequences),
                "history_prefix_references": sum(len(h["prefix_keys"]) for h in sequences),
                "all_prefixes_solved": sum(h["all_prefixes_solved"] for h in sequence_rows),
                "history_final_status": dict(Counter(h["final_status"] for h in sequence_rows)),
                "static_references": len(static_rows),
                "static_status": dict(Counter(by_key[s["geometry_key"]]["runs"][policy]["status"]
                                              for s in static_rows))})
        def solved_pair(row):
            """Compare the same geometry under both separately recorded policies."""
            return tuple(row["runs"][policy]["status"] == "solved" for policy in (BASELINE, POLICY))
        comparisons.append({"cohort": cohort, "baseline": BASELINE, "candidate": POLICY,
            "distinct_drawings": paired_counts(solved_pair(r) for r in drawings),
            "all_history_prefixes": paired_counts(tuple(
                histories_by_policy[(h["key"], p)]["all_prefixes_solved"] for p in (BASELINE, POLICY))
                for h in sequences),
            "history_final": paired_counts(tuple(
                histories_by_policy[(h["key"], p)]["final_status"] == "solved" for p in (BASELINE, POLICY))
                for h in sequences),
            "static_final": paired_counts(solved_pair(by_key[s["geometry_key"]]) for s in static_rows)})
    return summaries, history_results, comparisons


def build_report(source, checkpoint_dir, workers=4, batch_size=25, limit=None):
    """Execute exclusive checkpoints for a fixed, explicitly bounded inventory."""
    require(not sys.flags.optimize, "proof replay requires Python without -O")
    require(type(workers) is int and workers >= 1 and type(batch_size) is int and batch_size >= 1,
            "positive worker and batch counts required")
    require(limit is None or type(limit) is int and limit >= 1, "positive smoke limit required")
    require(file_sha(source) == SOURCE_SHA256, "source is not the frozen complete v2 archive")
    started = perf_counter()
    previous = read_json(source)
    all_rows = validate_inventory(previous)
    require(previous["policy"] == BASELINE, "wrong archived baseline policy")
    hashes = source_hashes(previous)
    # The old inventory checker fixes lexical key ordering independently of
    # successes. A limit always takes its first rows, never selected successes.
    rows = all_rows if limit is None else all_rows[:limit]
    selected = {row["key"] for row in rows}
    histories = [h for h in previous["histories"] if set(h["prefix_keys"]) <= selected]
    statics = [s for s in previous["static_inputs"] if s["geometry_key"] in selected]
    manifest = {"source": {"filename": source.name, "sha256": SOURCE_SHA256},
                "source_sha256": hashes, "selected_keys": [r["key"] for r in rows],
                "input_selection": "lexical-geometry-key-order", "smoke_limit": limit,
                "policy": POLICY, "baseline": BASELINE, "baseline_newly_rerun": False,
                "workers": workers, "batch_size": batch_size}
    checkpoint_dir.mkdir(parents=True, exist_ok=False)
    write_report(checkpoint_dir / "manifest.json", manifest)
    jobs = [(index, rows[offset:offset + batch_size])
            for index, offset in enumerate(range(0, len(rows), batch_size))]
    pieces, part_hashes, checked = {}, {}, 0
    statuses = Counter()
    pool = ProcessPoolExecutor(max_workers=workers) if workers > 1 else None
    try:
        for piece in (pool.map(run_batch, jobs) if pool else map(run_batch, jobs)):
            index = piece["index"]
            require(index not in pieces and 0 <= index < len(jobs), "duplicate or invalid worker batch")
            require([r["key"] for r in piece["records"]] == [r["key"] for r in jobs[index][1]],
                    "worker batch coverage/order changed")
            path = checkpoint_dir / f"part-{index:05d}.json.gz"
            write_report(path, piece)
            checksum = file_sha(path)
            write_report(path.with_suffix(path.suffix + ".sha256.json"),
                         {"filename": path.name, "sha256": checksum})
            pieces[index], part_hashes[path.name] = piece, checksum
            checked += len(piece["records"])
            statuses.update(row["runs"][POLICY]["status"] for row in piece["records"])
            print({"checked": checked, "total": len(rows), "statuses": dict(statuses),
                   "seconds": round(perf_counter() - started, 1)}, flush=True)
    finally:
        if pool:
            pool.shutdown(wait=True)
    records = [row for index in sorted(pieces) for row in pieces[index]["records"]]
    require([row["key"] for row in records] == [row["key"] for row in rows], "final coverage changed")
    ending = source_hashes(previous)
    require(ending == hashes and file_sha(source) == SOURCE_SHA256, "source changed during execution")
    summaries, history_results, paired = summarize(records, histories, statics)
    changes = {"improved": [], "regressed": [], "remaining_failures": []}
    statistics, audit_totals = Counter(), Counter()
    for row in records:
        old, new = (row["runs"][policy]["status"] == "solved" for policy in (BASELINE, POLICY))
        identity = {key: row[key] for key in ("key", "aliases", "face_count")}
        if new and not old:
            changes["improved"].append(identity)
        if old and not new:
            changes["regressed"].append(identity)
        if not new:
            changes["remaining_failures"].append(identity)
        statistics.update(row["runs"][POLICY]["statistics"])
        audit_totals.update({k: v for k, v in row["runs"][POLICY]["verification"].items() if type(v) is int})
    details = {key: detail for piece in pieces.values() for key, detail in piece["detailed_examples"].items()}
    expected_details = {row["key"] for row in records
                        if row["runs"][POLICY]["learned_pairs"] or row["runs"][POLICY]["status"] != "solved"}
    require(set(details) == expected_details, "learned/failure full-transcript coverage changed")
    return {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "Structural same-name refutation before the frozen v2 greedy commitment",
        "policy": POLICY, "baseline": BASELINE, "baseline_newly_rerun": False,
        "baseline_evidence": "Copied unchanged from the hash-bound independently audited v2 full archive",
        "source_evidence": manifest["source"], "source_sha256": hashes, "source_sha256_end": ending,
        "source_hashes_unchanged": True, "full_corpus_run": limit is None, "smoke_limit": limit,
        "unseen_holdout": False, "input_selection": manifest["input_selection"],
        "execution": {"workers": workers, "batch_size": batch_size, "resumed": False,
                      "wall_seconds": perf_counter() - started, "checkpoint_directory": checkpoint_dir.name,
                      "part_sha256": part_hashes},
        "drawings": records, "histories": histories, "static_inputs": statics,
        "summary": summaries, "history_results": history_results, "paired_comparisons": paired,
        "changes": changes, "independent_checks": len(records), "candidate_attempts": len(records),
        "structural_statistics": dict(statistics), "audit_totals": dict(audit_totals),
        "detailed_examples": details, "full_transcripts_retained": len(details),
        "limits": ["Finite previously inspected corpus, not an unseen holdout or a general theorem.",
                   "Each history prefix is independently renamed; repeated references are not independent samples.",
                   "Baseline runs and runtimes are archived; only the candidate is newly executed.",
                   "Structural assumptions can prove inequality; inconclusive does not certify extendibility.",
                   "No previous colors, assignment search, Kempe repair or policy retry enter the candidate.",
                   "Every transcript is audited; full transcripts retained for all learned relations and failures.",
                   "A conflict rejects this greedy commitment sequence, not four-colorability of the map."]}


def main():
    """Write distinct new artifacts and never resume or replace checkpoints."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--checkpoints", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.output.exists() or args.summary.exists() or args.checkpoints.exists():
        parser.error("choose new output, summary and checkpoint paths")
    if args.output.resolve() == args.summary.resolve():
        parser.error("output and summary must be distinct")
    report = build_report(args.source, args.checkpoints, args.workers, args.batch_size, args.limit)
    write_report(args.output, report)
    small = {key: value for key, value in report.items() if key not in (
        "drawings", "histories", "static_inputs", "history_results", "detailed_examples")}
    small.update({"input": {"filename": args.output.name, "sha256": file_sha(args.output)},
                  "distinct_drawings": len(report["drawings"]), "histories": len(report["histories"]),
                  "history_prefix_references": sum(len(h["prefix_keys"]) for h in report["histories"]),
                  "static_references": len(report["static_inputs"])})
    write_report(args.summary, small)
    print({"summary": report["summary"], "paired": report["paired_comparisons"],
           "changes": report["changes"], "structural_statistics": report["structural_statistics"]}, flush=True)


if __name__ == "__main__":
    main()

"""Replay the corpus with levels as OPTIONAL scheduling metadata.

Every input receives one fresh attempt and independent certificate checking.
Previous-policy outcomes are hash-bound comparisons, NOT newly executed runs.
Unrooted lines remain eligible; no fabricated depth or hard scope gate is used.
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

from fourcolor.level_sides_peer import POLICY, restart_level_peer_names
from scripts.validate_frontier_restart import EXISTING, HELDOUT, file_sha, json_value, paired_counts, read_json
from scripts.validate_global_restart import digest, export_geometries, write_report
from scripts.validate_level_sides import BASELINE, EXTRA_SOURCES, SOURCE
from scripts.validate_level_sides_peer import mathematical_projection, verify_run
from scripts.validate_relation_frontier_full import failure_rank, require, source_hashes as baseline_hashes, validate_inventory

DIAGNOSTIC = ROOT / "outputs/level-sides-six-2026-09-19.json.gz"
POLICIES = (BASELINE, POLICY)


def source_hashes():
    """Bind old geometry/checkers, frozen candidate, and this execution wrapper."""
    result = baseline_hashes()
    result.update({p: file_sha(ROOT / p) for p in EXTRA_SOURCES})
    result.update({p: file_sha(ROOT / p) for p in (
        "fourcolor/level_sides_peer.py", "scripts/validate_level_sides_peer.py",
        "scripts/validate_level_sides_peer_full.py")})
    return result


def compact_candidate(result, check):
    """Retain auditable commitments without fabricating absent out-of-scope fields."""
    require(check["passed"], "independent candidate check failed")
    compact = {k: result[k] for k in (
        "status", "policy", "choices", "backtracks", "old_colors_read", "colors", "unranked_mothers")}
    for key in ("domains", "anchors_by_dart", "local_budget", "reason", "hall_conflict"):
        if key in result:
            compact[key] = result[key]
    verification = dict(check)
    verification.setdefault("method", "independent-unrooted-level-scope-check")
    steps = result["trace"]
    compact.update({"verification": verification, "independent_check_passed": True,
                    "trace_sha256": digest(steps), "levels_sha256": digest(result["levels"]),
                    "raw_result_sha256": digest(result),
                    "propagation_phases_sha256": digest(result["propagation_phases"])
                    if "propagation_phases" in result else None,
                    "active_one_choices": sum(s["symbol"] == 1 for s in steps),
                    "direct_one_bans": sum(1 in s["boundary"]["direct_forbidden"] for s in steps),
                    "derived_one_bans": sum(1 in s["boundary"]["derived_exclusions"] for s in steps)})
    return compact


def run_batch(payload):
    """Re-export geometry and replay every decision/filter without an old color input."""
    index, saved_rows, six_by_key = payload
    exports = export_geometries(saved_rows)
    require(len(exports) == len(saved_rows), "geometry export dropped inputs")
    records, details = [], {}
    least = {"conflict": None, "outside_scope": None}
    exact = 0
    for saved, exported in zip(saved_rows, exports):
        require(exported["key"] == saved["key"] and exported["status"] == "geometry_ok",
                "geometry export changed or failed")
        geometry = exported["geometry"]
        require(digest(geometry) == saved["geometry_sha256"], "geometry hash changed")
        start = perf_counter()
        result = restart_level_peer_names(geometry)
        elapsed = perf_counter() - start
        start = perf_counter()
        check = verify_run(geometry, result)
        compact = compact_candidate(result, check)
        compact.update(runtime_seconds=elapsed, audit_seconds=perf_counter() - start)
        require(result["status"] in ("solved", "conflict"), "optional levels must not prevent coloring")
        if saved["key"] in six_by_key:
            archived = six_by_key[saved["key"]]
            require(mathematical_projection(result) == mathematical_projection(archived["candidate"]),
                    "six-case mathematical certificate changed")
            require({k: v for k, v in json_value(check).items() if k != "method"} ==
                    {k: v for k, v in archived["candidate_check"].items() if k != "method"},
                    "six-case verification changed")
            exact += 1
        record = {k: v for k, v in saved.items() if k != "runs"}
        # The baseline is deliberately carried unchanged, with its provenance
        # stated at report level. Its archived runtime is NOT a rerun runtime.
        record["runs"] = {BASELINE: saved["runs"][BASELINE], POLICY: compact}
        records.append(record)
        if result["status"] != "solved" or saved["key"] in six_by_key:
            detail = {"key": saved["key"], "document": saved["document"], "aliases": saved["aliases"],
                      "face_count": saved["face_count"], "geometry": geometry,
                      "outcome": result, "verification": check,
                      "previous_result": saved["runs"][BASELINE]}
            if saved["key"] in six_by_key:
                details[saved["key"]] = detail
            status = result["status"]
            if status in least and (least[status] is None or failure_rank(detail) < failure_rank(least[status])):
                least[status] = detail
    return {"index": index, "records": records, "detailed_examples": details,
            "least_conflict": least["conflict"], "least_outside_scope": least["outside_scope"],
            "diagnostic_exact_reproductions": exact}


def summarize(records, histories, statics):
    """Account for every reference; out-of-scope never means a color contradiction."""
    by_key = {r["key"]: r for r in records}
    history_results = []
    for policy in POLICIES:
        for history in histories:
            statuses = [by_key[k]["runs"][policy]["status"] for k in history["prefix_keys"]]
            first = lambda status: next((i for i, s in enumerate(statuses) if s == status), None)
            history_results.append({"key": history["key"], "cohort": history["cohort"], "policy": policy,
                "statuses": statuses, "all_prefixes_solved": all(s == "solved" for s in statuses),
                "first_non_solved_prefix": next((i for i, s in enumerate(statuses) if s != "solved"), None),
                "first_conflict_prefix": first("conflict"), "first_outside_scope_prefix": first("outside_scope"),
                "recoveries": [{"prefix": i, "from": statuses[i - 1]} for i in range(1, len(statuses))
                               if statuses[i] == "solved" and statuses[i - 1] != "solved"],
                "final_status": statuses[-1]})
    hi = {(r["key"], r["policy"]): r for r in history_results}
    summaries, comparisons = [], []
    for cohort in ("combined", EXISTING, HELDOUT):
        drawings = [r for r in records if cohort == "combined" or cohort in r["cohorts"]]
        sequences = [h for h in histories if cohort == "combined" or h["cohort"] == cohort]
        inputs = [s for s in statics if cohort == "combined" or s["cohort"] == cohort]
        for policy in POLICIES:
            states = [hi[(h["key"], policy)] for h in sequences]
            summaries.append({"cohort": cohort, "policy": policy, "distinct_drawings": len(drawings),
                "statuses": dict(Counter(r["runs"][policy]["status"] for r in drawings)),
                "histories": len(sequences), "history_prefix_references": sum(len(h["prefix_keys"]) for h in sequences),
                "all_prefixes_solved": sum(h["all_prefixes_solved"] for h in states),
                "histories_with_conflict": sum(h["first_conflict_prefix"] is not None for h in states),
                "histories_with_outside_scope": sum(h["first_outside_scope_prefix"] is not None for h in states),
                "history_final_status": dict(Counter(h["final_status"] for h in states)),
                "static_references": len(inputs),
                "static_status": dict(Counter(by_key[s["geometry_key"]]["runs"][policy]["status"] for s in inputs))})
        pair = lambda r: (r["runs"][BASELINE]["status"] == "solved", r["runs"][POLICY]["status"] == "solved")
        matrix = Counter((r["runs"][BASELINE]["status"], r["runs"][POLICY]["status"]) for r in drawings)
        comparisons.append({"cohort": cohort, "baseline": BASELINE, "candidate": POLICY,
            "baseline_newly_rerun": False, "distinct_drawings": paired_counts(pair(r) for r in drawings),
            "status_transitions": [{"baseline_status": a, "candidate_status": b, "count": n}
                                   for (a, b), n in sorted(matrix.items())],
            "all_history_prefixes": paired_counts((hi[(h["key"], BASELINE)]["all_prefixes_solved"],
                                                    hi[(h["key"], POLICY)]["all_prefixes_solved"]) for h in sequences),
            "history_final": paired_counts((hi[(h["key"], BASELINE)]["final_status"] == "solved",
                                             hi[(h["key"], POLICY)]["final_status"] == "solved") for h in sequences),
            "static_final": paired_counts(pair(by_key[s["geometry_key"]]) for s in inputs)})
    return summaries, history_results, comparisons


def build_report(source_path, diagnostic_path, checkpoint_dir, workers=4, batch_size=25, limit=None, resume=False):
    """Checkpoint exactly one frozen attempt, refusing changed code or inputs."""
    require(sys.flags.optimize == 0, "proof replay must run without Python -O")
    require(workers >= 1 and batch_size >= 1 and (limit is None or limit >= 1), "invalid execution bounds")
    began = perf_counter()
    previous, diagnostic = read_json(source_path), read_json(diagnostic_path)
    rows = validate_inventory(previous)
    hashes = source_hashes()
    require(baseline_hashes() == previous["source_sha256"] == previous["source_sha256_end"], "baseline code changed")
    require(diagnostic["source"]["sha256"] == file_sha(source_path), "six cases came from another source")
    require(diagnostic["source_sha256"] == diagnostic["source_sha256_end"], "diagnostic code drifted")
    require(all(hashes[p] == v for p, v in diagnostic["source_sha256"].items()), "frozen six-case code changed")
    six = {r["key"]: r for r in diagnostic["records"]}
    require(len(six) == 6 and set(six) <= {r["key"] for r in rows}, "six-case coverage changed")
    if limit is not None:
        rows = rows[:limit]
    selected = {r["key"] for r in rows}
    histories = [h for h in previous["histories"] if set(h["prefix_keys"]) <= selected]
    statics = [s for s in previous["static_inputs"] if s["geometry_key"] in selected]
    manifest = {"source_evidence": {"filename": source_path.name, "sha256": file_sha(source_path)},
                "diagnostic_evidence": {"filename": diagnostic_path.name, "sha256": file_sha(diagnostic_path)},
                "source_sha256": hashes, "selected_keys": [r["key"] for r in rows], "batch_size": batch_size,
                "smoke_limit": limit, "policy": POLICY, "baseline": BASELINE, "baseline_newly_rerun": False}
    manifest_path = checkpoint_dir / "manifest.json"
    if resume:
        require(read_json(manifest_path) == manifest, "checkpoint source/code/inventory mismatch")
    else:
        checkpoint_dir.mkdir(parents=True, exist_ok=False)
        write_report(manifest_path, manifest)
    jobs, pieces, part_hashes = [], {}, {}
    for index, start in enumerate(range(0, len(rows), batch_size)):
        path = checkpoint_dir / f"part-{index:05d}.json.gz"
        batch = rows[start:start + batch_size]
        if resume and path.exists():
            require(read_json(path.with_suffix(path.suffix + ".sha256.json")) ==
                    {"filename": path.name, "sha256": file_sha(path)}, "checkpoint bytes fail saved checksum")
            piece = read_json(path)
            require(piece["index"] == index and [r["key"] for r in piece["records"]] == [r["key"] for r in batch],
                    "checkpoint coverage mismatch")
            pieces[index], part_hashes[path.name] = piece, file_sha(path)
        else:
            jobs.append((index, batch, {r["key"]: six[r["key"]] for r in batch if r["key"] in six}))
    pool = ProcessPoolExecutor(max_workers=workers) if workers > 1 else None
    try:
        for piece in (pool.map(run_batch, jobs) if pool else map(run_batch, jobs)):
            path = checkpoint_dir / f"part-{piece['index']:05d}.json.gz"
            write_report(path, piece)
            write_report(path.with_suffix(path.suffix + ".sha256.json"), {"filename": path.name, "sha256": file_sha(path)})
            pieces[piece["index"]], part_hashes[path.name] = piece, file_sha(path)
            statuses = Counter(r["runs"][POLICY]["status"] for p in pieces.values() for r in p["records"])
            print({"checked": sum(statuses.values()), "total": len(rows), "statuses": dict(statuses),
                   "seconds": round(perf_counter() - began, 1)}, flush=True)
    finally:
        if pool:
            pool.shutdown(wait=True)
    records = [r for index in sorted(pieces) for r in pieces[index]["records"]]
    require([r["key"] for r in records] == [r["key"] for r in rows], "final coverage mismatch")
    ending = source_hashes()
    require(ending == hashes and manifest["source_evidence"]["sha256"] == file_sha(source_path)
            and manifest["diagnostic_evidence"]["sha256"] == file_sha(diagnostic_path), "sources changed during run")
    summary, history_results, paired = summarize(records, histories, statics)
    exact = sum(p["diagnostic_exact_reproductions"] for p in pieces.values())
    require(exact == len(selected & set(six)), "diagnostic reproduction missing")
    totals = Counter()
    for record in records:
        totals.update({k: v for k, v in record["runs"][POLICY]["verification"].items() if type(v) is int})
    report = {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "Optional mother levels and unranked peers: complete previously inspected inventory",
        "smoke_limit": limit, "full_corpus_run": limit is None, "unseen_holdout": False,
        "source_evidence": manifest["source_evidence"], "diagnostic_evidence": manifest["diagnostic_evidence"],
        "source_sha256": hashes, "source_sha256_end": ending, "source_hashes_unchanged": True,
        "policy": POLICY, "baseline": BASELINE, "baseline_newly_rerun": False,
        "baseline_evidence": "Copied unchanged from hash-bound independently verified prior full report",
        "execution": {"workers": workers, "batch_size": batch_size, "resumed": resume,
                      "wall_seconds": perf_counter() - began, "checkpoint_directory": checkpoint_dir.name,
                      "part_sha256": part_hashes},
        "drawings": records, "histories": histories, "static_inputs": statics,
        "summary": summary, "history_results": history_results, "paired_comparisons": paired,
        "independent_checks": len(records), "diagnostic_exact_reproductions": exact, "replay_totals": dict(totals),
        "detailed_examples": {k: v for p in pieces.values() for k, v in p["detailed_examples"].items()},
        "limits": ["Finite already-inspected corpus, not all plane maps or an unseen holdout.",
            "Only the candidate is rerun; baseline outcomes and timings are archived comparisons.",
            "Unrooted lines remain eligible as an unranked-peer group; level=None is not equal-depth proof.",
            "conflict is after this fixed greedy path, NOT a proof the map needs five colors.",
            "No policy retry, old-color input, search rescue, or backtracking.",
            "History all-prefix success differs from final success; each prefix restarts independently.",
            "Detailed full certificates saved for six diagnostics and batch-minimal noncompletions; all others checked then hashed.",
            "Six-case exact reproduction excludes only policy/scope text and the new descriptive selection_group field.",
            "User clarified levels are auxiliary; known-first/unknown-after is a provisional deterministic tie convention."]}
    for kind in ("conflict", "outside_scope"):
        examples = [p["least_" + kind] for p in pieces.values() if p["least_" + kind] is not None]
        report["least_" + kind] = min(examples, key=failure_rank) if examples else None
    return report


def main():
    """Save new reports exclusively; checkpoint resume never alters the naming rule."""
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
        parser.error("choose two distinct NEW output paths")
    report = build_report(args.source, args.diagnostic, args.checkpoints, args.workers, args.batch_size, args.limit, args.resume)
    write_report(args.output, report)
    small = {k: v for k, v in report.items() if k not in (
        "drawings", "histories", "static_inputs", "history_results", "detailed_examples", "least_conflict", "least_outside_scope")}
    small.update({"input": {"filename": args.output.name, "sha256": file_sha(args.output)},
                  "distinct_drawings": len(report["drawings"]),
                  "history_prefix_references": sum(len(h["prefix_keys"]) for h in report["histories"]),
                  "static_references": len(report["static_inputs"])})
    for kind in ("conflict", "outside_scope"):
        detail = report["least_" + kind]
        small["least_" + kind] = {k: detail[k] for k in ("key", "face_count", "aliases")} if detail else None
    write_report(args.summary, small)
    print({"summary": report["summary"], "paired": report["paired_comparisons"]}, flush=True)


if __name__ == "__main__":
    main()

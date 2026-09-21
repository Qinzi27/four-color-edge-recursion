"""Paired, independently audited restarts on twenty predeclared new seeds.

All twenty geometrical histories are generated before any naming run. Every
prefix is included, regardless of earlier naming failures. Exact stroke-set
deduplication saves repeated work but does not turn prefixes into independent
samples. Both the frozen v2 policy and the candidate run afresh on every input.
"""

from argparse import ArgumentParser
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import median
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.level_sides_peer import POLICY as BASELINE, restart_level_peer_names
from fourcolor.structural_restart import POLICY, restart_structural_names
from scripts.validate_frontier_restart import file_sha, paired_counts, read_json
from scripts.validate_global_restart import digest, export_geometries, restart_inventory, write_report
from scripts.validate_level_sides_peer import verify_run as verify_baseline
from scripts.validate_relation_frontier_full import require, validate_inventory
from scripts.validate_structural_restart import verify_run as verify_candidate

SOURCE = ROOT / "outputs/level-sides-peer-full-2026-09-19.json.gz"
SOURCE_SHA256 = "5085627be22653ea9b6ea13de5ff851c452a8c702996ee6eda0672d2d72eca07"
SEEDS = tuple(range(20262101, 20262121))
CUTS = 24
COHORT = "predeclared-new-guillotine-seeds-20262101-20262120"
EXTRA_SOURCES = (
    "docs/STRUCTURAL_RESTART_RULES-2026-09-21.md",
    "fourcolor/structural_name_relations.py", "fourcolor/structural_restart.py",
    "scripts/validate_structural_restart.py", "scripts/validate_structural_restart_new_seeds.py",
    "scripts/current_corpus.py", "scripts/construction-experiments.mjs",
    "web/construction.js", "web/construction-cases.js",
    "tests/test_structural_name_relations.py", "tests/test_structural_restart.py",
    "tests/test_structural_restart_validation.py", "tests/test_structural_restart_new_seeds.py",
)


def source_hashes(previous):
    """Bind unchanged historical code plus every new generator/producer/checker."""
    require(previous["source_sha256"] == previous["source_sha256_end"], "old source hashes differ")
    files = sorted(set(previous["source_sha256"]) | set(EXTRA_SOURCES))
    hashes = {name: file_sha(ROOT / name) for name in files}
    require(all(hashes[name] == value for name, value in previous["source_sha256"].items()),
            "historical source changed")
    return hashes


def generate_histories():
    """Call only the frozen geometric generator with the fixed twenty seeds."""
    script = """
import {generatedPaths} from './scripts/construction-experiments.mjs';
const rows=[];
for(let seed=20262101;seed<=20262120;seed++)
  rows.push({seed,paths:generatedPaths('guillotine',seed)});
process.stdout.write(JSON.stringify(rows));
"""
    process = subprocess.run(["node", "--input-type=module", "-e", script], cwd=ROOT,
                             capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(process.stdout)


def make_inventory(generated, old_keys):
    """Validate seed/cut coverage before deduplicating all 500 prefix references."""
    require([row["seed"] for row in generated] == list(SEEDS), "declared seed list changed")
    inputs = []
    for item in generated:
        require(len(item["paths"]) == CUTS, "a declared history lost a cut")
        for path in item["paths"]:
            require(isinstance(path, list) and len(path) == 2, "cut must have two endpoints")
            require(all(isinstance(point, list) and len(point) == 2
                        and all(type(value) is int for value in point)
                        and 0 <= point[0] <= 900 and 0 <= point[1] <= 600 for point in path),
                    "invalid generated endpoint")
            require(path[0] != path[1] and (path[0][0] == path[1][0] or path[0][1] == path[1][1]),
                    "cut must be nonzero and axis-aligned")
        key = "new-seed-guillotine-" + str(item["seed"])
        row = {"key": key, "family": "guillotine", "cohort": COHORT,
               "seed": item["seed"], "paths": item["paths"], "initial_state": None,
               "initial_document": {"frame": {"width": 900, "height": 600}, "strokes": []},
               "max_old_sides": 3,
               "aliases": [{"key": key, "family": "guillotine", "cohort": COHORT,
                            "seed": item["seed"], "kind": "predeclared-generator-history",
                            "source": "scripts/construction-experiments.mjs::generatedPaths"}]}
        row["history_sha256"] = digest({field: row.get(field) for field in (
            "initial_state", "initial_document", "initial_names", "paths", "max_old_sides")})
        inputs.append(row)
    records, histories, statics = restart_inventory({"histories": inputs, "static_inventory": []})
    require(not statics and len(histories) == len(SEEDS)
            and sum(len(row["prefix_keys"]) for row in histories) == len(SEEDS) * (CUTS + 1),
            "history or prefix coverage changed")
    require(all(len(row["prefix_keys"]) == CUTS + 1 for row in histories), "short history inventory")
    for record in records:
        record["old_inventory_membership"] = "overlap" if record["key"] in old_keys else "novel"
        record["cohorts"] = [COHORT]
    for history in histories:
        history["cohort"] = COHORT
    return sorted(records, key=lambda row: row["key"]), histories, inputs


def compact_run(result, check):
    """Keep actual final names and deterministic hashes after full proof replay."""
    require(check["passed"] and result["status"] in ("solved", "conflict"), "invalid audited result")
    compact = {name: result[name] for name in (
        "policy", "status", "domains", "anchors_by_dart", "colors", "choices",
        "backtracks", "old_colors_read", "local_budget", "hall_conflict", "unranked_mothers")}
    compact.update({"independent_check_passed": True, "verification": check,
                    "trace_sha256": digest(result["trace"]),
                    "propagation_phases_sha256": digest(result["propagation_phases"]),
                    "full_transcript_sha256": digest(result)})
    if result["policy"] == POLICY:
        compact.update({"statistics": result["statistics"], "learned_pairs": result["learned_pairs"],
                        "events_sha256": digest(result["events"]),
                        "proof_queries_sha256": digest(result["proof_queries"])})
    return compact


def run_batch(payload):
    """Execute both policies once per geometry; retain every failed/learned run."""
    index, inputs = payload
    exports = export_geometries(inputs)
    require(len(exports) == len(inputs), "geometry exporter dropped input")
    records, details = [], {}
    for saved, exported in zip(inputs, exports):
        require(exported["key"] == saved["key"] and exported["status"] == "geometry_ok",
                "geometric export failed or changed input order")
        geometry = exported["geometry"]
        geometry_hash = digest(geometry)
        record = {**saved, "geometry_status": "geometry_ok", "geometry_sha256": geometry_hash,
                  "face_count": len(geometry["faces"]), "runs": {}}
        raw, checks = {}, {}
        for policy, producer, auditor in ((BASELINE, restart_level_peer_names, verify_baseline),
                                          (POLICY, restart_structural_names, verify_candidate)):
            started = perf_counter()
            result = producer(geometry)
            seconds = perf_counter() - started
            require(result["policy"] == policy, "wrong executed policy")
            started = perf_counter()
            check = auditor(geometry, result)
            audit_seconds = perf_counter() - started
            require(digest(geometry) == geometry_hash, "producer or auditor mutated geometry")
            compact = compact_run(result, check)
            compact.update(runtime_seconds=seconds, audit_seconds=audit_seconds)
            record["runs"][policy], raw[policy], checks[policy] = compact, result, check
        records.append(record)
        if raw[POLICY]["learned_pairs"] or any(result["status"] != "solved" for result in raw.values()):
            details[saved["key"]] = {"key": saved["key"], "geometry": geometry,
                                      "document": saved["document"], "aliases": saved["aliases"],
                                      "runs": raw, "verification": checks}
    require(len(records) == len(inputs), "worker lost an input")
    return {"index": index, "records": records, "detailed_examples": details}


def summarize(records, histories):
    """Separate distinct maps, repeated prefixes, final references and histories."""
    by_key = {row["key"]: row for row in records}
    require(len(by_key) == len(records), "duplicate result drawing")
    require(all(key in by_key for h in histories for key in h["prefix_keys"]), "missing history prefix")
    history_results = []
    for history in histories:
        for policy in (BASELINE, POLICY):
            statuses = [by_key[key]["runs"][policy]["status"] for key in history["prefix_keys"]]
            history_results.append({"key": history["key"], "seed": history["seed"], "policy": policy,
                "statuses": statuses, "all_prefixes_solved": all(s == "solved" for s in statuses),
                "first_failed_prefix": next((i for i, s in enumerate(statuses) if s != "solved"), None),
                "recoveries": [i for i in range(1, len(statuses))
                               if statuses[i] == "solved" and statuses[i - 1] != "solved"],
                "final_status": statuses[-1]})
    history_by_key = {(row["key"], row["policy"]): row for row in history_results}

    def paired(rows):
        """Never combine the two policies' successful subsets into one solver."""
        return paired_counts(tuple(row["runs"][policy]["status"] == "solved"
                                   for policy in (BASELINE, POLICY)) for row in rows)

    def counts(rows):
        """Count the supplied denominator exactly, including repeated references."""
        return {"count": len(rows), "statuses": {policy: dict(Counter(
            row["runs"][policy]["status"] for row in rows)) for policy in (BASELINE, POLICY)},
                "paired": paired(rows)}

    groups = []
    for membership in ("combined", "novel", "overlap"):
        selected = {key for key, row in by_key.items()
                    if membership == "combined" or row["old_inventory_membership"] == membership}
        groups.append({"old_inventory_membership": membership,
            "distinct_drawings": counts([by_key[key] for key in sorted(selected)]),
            "prefix_references": counts([by_key[key] for h in histories
                                         for key in h["prefix_keys"] if key in selected]),
            "final_references": counts([by_key[h["prefix_keys"][-1]] for h in histories
                                        if h["prefix_keys"][-1] in selected])})
    history_summary = {"histories": len(histories), "policies": {},
        "all_prefixes_paired": paired_counts(tuple(history_by_key[(h["key"], p)]["all_prefixes_solved"]
                                                 for p in (BASELINE, POLICY)) for h in histories),
        "final_paired": paired_counts(tuple(history_by_key[(h["key"], p)]["final_status"] == "solved"
                                            for p in (BASELINE, POLICY)) for h in histories)}
    for policy in (BASELINE, POLICY):
        rows = [row for row in history_results if row["policy"] == policy]
        history_summary["policies"][policy] = {
            "all_prefixes_solved": sum(row["all_prefixes_solved"] for row in rows),
            "final_status": dict(Counter(row["final_status"] for row in rows))}
    return groups, history_summary, history_results


def build_report(checkpoint_dir, workers=4, batch_size=25, limit=None, source=SOURCE):
    """Freeze source/input manifests, run disjoint batches, then check drift."""
    require(not sys.flags.optimize, "independent audit requires Python without -O")
    require(type(workers) is int and workers >= 1 and type(batch_size) is int and batch_size >= 1,
            "positive worker and batch counts required")
    require(limit is None or type(limit) is int and limit >= 1, "positive smoke limit required")
    require(file_sha(source) == SOURCE_SHA256, "incorrect frozen comparison inventory")
    started = perf_counter()
    previous = read_json(source)
    old_rows = validate_inventory(previous)
    require(previous["policy"] == BASELINE, "wrong historical policy")
    old_keys = {row["key"] for row in old_rows}
    hashes = source_hashes(previous)
    generated = generate_histories()
    all_records, all_histories, generated_histories = make_inventory(generated, old_keys)
    records = all_records if limit is None else all_records[:limit]
    selected = {row["key"] for row in records}
    histories = [h for h in all_histories if set(h["prefix_keys"]) <= selected]
    manifest = {"source": {"filename": source.name, "sha256": SOURCE_SHA256},
                "source_sha256": hashes, "generated_histories_sha256": digest(generated_histories),
                "generated_histories": generated_histories, "all_histories": all_histories,
                "all_inventory_sha256": digest(all_records), "selected_keys": [r["key"] for r in records],
                "seeds": list(SEEDS), "cuts_per_history": CUTS, "smoke_limit": limit,
                "selection": "lexical-geometry-key-order", "baseline": BASELINE, "candidate": POLICY,
                "both_policies_newly_rerun": True, "workers": workers, "batch_size": batch_size}
    checkpoint_dir.mkdir(parents=True, exist_ok=False)
    write_report(checkpoint_dir / "manifest.json", manifest)
    jobs = [(index, records[offset:offset + batch_size])
            for index, offset in enumerate(range(0, len(records), batch_size))]
    pieces, part_hashes, checked = {}, {}, 0
    statuses = {BASELINE: Counter(), POLICY: Counter()}
    pool = ProcessPoolExecutor(max_workers=workers) if workers > 1 else None
    try:
        for piece in (pool.map(run_batch, jobs) if pool else map(run_batch, jobs)):
            index = piece["index"]
            require(index not in pieces and 0 <= index < len(jobs), "invalid worker index")
            require([row["key"] for row in piece["records"]] == [row["key"] for row in jobs[index][1]],
                    "worker coverage or ordering changed")
            path = checkpoint_dir / f"part-{index:05d}.json.gz"
            write_report(path, piece)
            part_hashes[path.name] = file_sha(path)
            pieces[index] = piece
            checked += len(piece["records"])
            for policy in (BASELINE, POLICY):
                statuses[policy].update(row["runs"][policy]["status"] for row in piece["records"])
            print({"checked": checked, "total": len(records),
                   "statuses": {p: dict(c) for p, c in statuses.items()},
                   "seconds": round(perf_counter() - started, 1)}, flush=True)
    finally:
        if pool:
            pool.shutdown(wait=True)
    output = [row for index in sorted(pieces) for row in pieces[index]["records"]]
    require([row["key"] for row in output] == [row["key"] for row in records], "final coverage changed")
    ending = source_hashes(previous)
    require(ending == hashes and file_sha(source) == SOURCE_SHA256, "source changed during execution")
    groups, history_summary, history_results = summarize(output, histories)
    details = {key: row for piece in pieces.values() for key, row in piece["detailed_examples"].items()}
    expected = {row["key"] for row in output if row["runs"][POLICY]["learned_pairs"]
                or any(row["runs"][p]["status"] != "solved" for p in (BASELINE, POLICY))}
    require(set(details) == expected, "learned or failed full-transcript coverage changed")
    changes = {"improved": [], "regressed": [], "remaining_candidate_failures": []}
    statistics = Counter()
    for row in output:
        old, new = (row["runs"][p]["status"] == "solved" for p in (BASELINE, POLICY))
        identity = {name: row[name] for name in ("key", "aliases", "old_inventory_membership", "face_count")}
        if new and not old:
            changes["improved"].append(identity)
        if old and not new:
            changes["regressed"].append(identity)
        if not new:
            changes["remaining_candidate_failures"].append(identity)
        statistics.update(row["runs"][POLICY]["statistics"])
    timing = {"fixed_execution_order": [BASELINE, POLICY],
              "controlled_benchmark": False, "policies": {},
              "note": "Fresh paired observations in concurrent workers; cache/order and other process load are uncontrolled."}
    for policy in (BASELINE, POLICY):
        runtimes = [row["runs"][policy]["runtime_seconds"] for row in output]
        audits = [row["runs"][policy]["audit_seconds"] for row in output]
        timing["policies"][policy] = {"producer_total_seconds": sum(runtimes),
            "producer_median_seconds": median(runtimes), "audit_total_seconds": sum(audits),
            "audit_median_seconds": median(audits)}
    timing["median_paired_producer_difference_seconds"] = median(
        row["runs"][POLICY]["runtime_seconds"] - row["runs"][BASELINE]["runtime_seconds"] for row in output)
    return {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "Predeclared twenty new guillotine seeds with fresh paired naming and full proof replay",
        "baseline": BASELINE, "candidate": POLICY, "both_policies_newly_rerun": True,
        "source_evidence": manifest["source"], "source_sha256": hashes, "source_sha256_end": ending,
        "source_hashes_unchanged": True, "full_declared_run": limit is None, "smoke_limit": limit,
        "generator": {"family": "guillotine", "seeds": list(SEEDS), "histories": len(SEEDS),
                      "cuts_per_history": CUTS, "total_prefix_references": len(SEEDS) * (CUTS + 1),
                      "input_selection": "all predeclared seeds and all prefixes before solving",
                      "independent_graph_family": False},
        "generated_histories": generated_histories, "generated_histories_sha256": digest(generated_histories),
        "drawings": output, "histories": histories, "all_generated_histories": all_histories,
        "membership_summaries": groups, "history_summary": history_summary, "history_results": history_results,
        "changes": changes, "attempts_per_policy": len(output), "independent_checks": 2 * len(output),
        "structural_statistics": dict(statistics), "detailed_examples": details,
        "fresh_paired_timing": timing,
        "full_transcripts_retained_geometries": len(details),
        "execution": {"workers": workers, "batch_size": batch_size, "resumed": False,
                      "checkpoint_directory": checkpoint_dir.name, "part_sha256": part_hashes,
                      "wall_seconds": perf_counter() - started},
        "limits": ["The seeds are new, but the guillotine generator family is unchanged.",
                   "Exact stroke-set keys define novelty relative to the archived 7069 maps, not graph isomorphism.",
                   "History prefixes and repeated geometry references are not independent random samples.",
                   "Each prefix is renamed from scratch even after failures on other prefixes.",
                   "Both policies run once; their success sets are never combined.",
                   "No outcome from these seeds changes the frozen candidate rule.",
                   "All runs are independently audited; all failures and learned examples retain full transcripts.",
                   "Inconclusive structural checks do not prove that the subsequent greedy choice extends.",
                   "Timing includes separate audits and evidence writes and is not a speed benchmark."]}


def main():
    """Create exclusive new report, summary and evidence files."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--checkpoints", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if any(path.exists() for path in (args.output, args.summary, args.checkpoints)):
        parser.error("choose new output, summary and checkpoint paths")
    if args.output.resolve() == args.summary.resolve():
        parser.error("output and summary must differ")
    report = build_report(args.checkpoints, args.workers, args.batch_size, args.limit)
    write_report(args.output, report)
    small = {name: value for name, value in report.items() if name not in (
        "drawings", "histories", "all_generated_histories", "generated_histories", "history_results",
        "detailed_examples")}
    small.update({"input": {"filename": args.output.name, "sha256": file_sha(args.output)},
                  "distinct_drawings": len(report["drawings"])})
    write_report(args.summary, small)
    print({"membership_summaries": report["membership_summaries"],
           "history_summary": report["history_summary"], "changes": report["changes"],
           "structural_statistics": report["structural_statistics"]}, flush=True)


if __name__ == "__main__":
    main()

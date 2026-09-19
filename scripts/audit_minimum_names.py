"""Audit whether EVERY actual choice already uses the smallest candidate.

This does not implement a second solver or silently change line scheduling.
Recreate the frozen runs and compare their complete decision/proof hashes with
the prior full report. Independently read each PRE-decision domain, rather
than trusting its trace description. If every choice is the numerical minimum,
determinism proves that replacing reuse-first with min(domain) gives the same
run on that input. An observed mismatch invalidates that equivalence claim;
it is recorded, not repaired or counted as a new-policy coloring.
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

from fourcolor.relation_frontier import POLICY, restart_relation_frontier_names
from scripts.validate_frontier_restart import file_sha, json_value, read_json
from scripts.validate_global_restart import compact_result, digest, export_geometries, write_report
from scripts.validate_relation_frontier import independent_check
from scripts.validate_relation_frontier_full import exact_run, require, source_hashes, validate_inventory

SOURCE = ROOT / "outputs/relation-frontier-full-2026-09-19.json.gz"


def anchor_dict(values):
    """Normalize portable JSON dart keys without altering name lists."""
    return {int(key): list(value) for key, value in values.items()}


def inspect_choices(result):
    """Compare choices with independently read previous domains and commitments.

    A legitimate non-minimal choice is evidence, not an assertion failure.
    Inconsistent domain, used-name, or commitment records are malformed data
    and must raise instead of passing as an audit of the actual execution.
    """
    trace, calls = result["trace"], result["propagation_phases"]
    require(len(calls) == len(trace) + 1 and result["choices"] == len(trace),
            "decision/propagation count mismatch")
    if "initial_anchors_by_dart" in result:
        require(anchor_dict(result["initial_anchors_by_dart"]) == anchor_dict(calls[0]["anchors_by_dart"]),
                "initial commitments mismatch")
    decisions = []
    for index, step in enumerate(trace):
        before = calls[index]["outcome"]
        require(before["status"] == "underdetermined", "choice after terminal propagation")
        domains = before["domains"]
        domain = sorted(domains[step["side"]])
        used = sorted({d[0] for d in domains if len(d) == 1})
        require(len(domain) > 1 and domain == step["domain"], "trace domain is not pre-choice domain")
        require(used == step["used_names"], "trace used names are not pre-choice singleton names")
        require(step["symbol"] in domain, "choice outside pre-choice domain")
        expected = anchor_dict(calls[index]["anchors_by_dart"])
        expected[step["dart"]] = [step["symbol"]]
        require(expected == anchor_dict(calls[index + 1]["anchors_by_dart"]),
                "next propagation does not preserve actual commitments")
        is_prefix = used == list(range(1, len(used) + 1))
        decisions.append({"index": index + 1, "side": step["side"], "dart": step["dart"],
                          "domain": domain, "used_names": used, "chosen": step["symbol"],
                          "minimum": min(domain), "is_minimum": step["symbol"] == min(domain),
                          "used_is_prefix": is_prefix})
    if "anchors_by_dart" in result:
        require(anchor_dict(result["anchors_by_dart"]) == anchor_dict(calls[-1]["anchors_by_dart"]),
                "final commitments mismatch")
    return {"choices": len(trace), "decisions": decisions,
            "minimum_mismatches": [d for d in decisions if not d["is_minimum"]],
            "prefix_mismatches": [d for d in decisions if not d["used_is_prefix"]]}


def run_batch(payload):
    """Rebuild geometry and the original rule once; never retry an assignment."""
    index, saved_rows = payload
    records, failures = [], []
    exported_rows = export_geometries(saved_rows)
    require(len(exported_rows) == len(saved_rows), "geometry export dropped an input")
    for saved, exported in zip(saved_rows, exported_rows):
        require(exported["status"] == "geometry_ok" and exported["key"] == saved["key"],
                "geometry export status/order changed")
        geometry = exported["geometry"]
        require(digest(geometry) == saved["geometry_sha256"], "geometry hash changed")
        result = restart_relation_frontier_names(geometry)
        compact = compact_result(result)
        original = saved["runs"][POLICY]
        exact_run(compact, original)
        phase_hash = digest(result["propagation_phases"])
        require(phase_hash == original["propagation_phases_sha256"], "proof phases changed")
        require(original["verification"]["passed"], "source result has no prior successful proof check")
        choices = inspect_choices(result)
        row = {"key": saved["key"], "aliases": saved["aliases"], "cohorts": saved["cohorts"],
               "geometry_sha256": saved["geometry_sha256"], "status": result["status"],
               "trace_sha256": compact["trace_sha256"], "propagation_phases_sha256": phase_hash,
               "original_result_and_proofs_exact": True,
               "minimum_only_change_is_equivalent_on_this_input": not choices["minimum_mismatches"],
               **choices}
        records.append(row)
        if result["status"] == "conflict":
            # Independently recheck all six failure certificates, not just hashes.
            checked = independent_check(geometry, result)
            require(checked["passed"], "failure certificate did not independently replay")
            failures.append({"key": saved["key"], "document": saved["document"],
                             "geometry": geometry, "result": result, "verification": checked})
    return {"index": index, "records": records, "failure_certificates": failures}


def recount(records, source):
    """Keep map completion, every-prefix completion and final completion distinct."""
    by_key = {r["key"]: r for r in records}
    histories = [h for h in source["histories"] if set(h["prefix_keys"]) <= by_key.keys()]
    statics = [s for s in source["static_inputs"] if s["geometry_key"] in by_key]
    solved = lambda key: by_key[key]["status"] == "solved"
    return {"drawings": len(records), "statuses": dict(Counter(r["status"] for r in records)),
            "active_choices": sum(r["choices"] for r in records),
            "nonminimum_choices": sum(len(r["minimum_mismatches"]) for r in records),
            "nonprefix_used_name_states": sum(len(r["prefix_mismatches"]) for r in records),
            "minimum_equivalent_inputs": sum(r["minimum_only_change_is_equivalent_on_this_input"] for r in records),
            "histories_completely_covered": len(histories),
            "history_prefix_references": sum(len(h["prefix_keys"]) for h in histories),
            "all_prefixes_solved": sum(all(solved(k) for k in h["prefix_keys"]) for h in histories),
            "final_histories_solved": sum(solved(h["prefix_keys"][-1]) for h in histories),
            "static_references": len(statics),
            "static_solved": sum(solved(s["geometry_key"]) for s in statics)}


def build_report(source_path, parts_dir, workers=4, mode="full"):
    """Audit an immutable full inventory or the six explicitly labeled failures."""
    require(sys.flags.optimize == 0, "proof checking requires Python without -O")
    started = perf_counter()
    source = read_json(source_path)
    rows = validate_inventory(source)
    original_sha = file_sha(source_path)
    current = source_hashes()
    require(current == source["source_sha256"] == source["source_sha256_end"],
            "frozen algorithm/checker source changed")
    current["scripts/audit_minimum_names.py"] = file_sha(Path(__file__))
    if mode == "failures":
        rows = [r for r in rows if r["runs"][POLICY]["status"] == "conflict"]
    require(mode in ("full", "failures"), "unknown selection mode")
    parts_dir.mkdir(parents=True, exist_ok=False)
    manifest = {"source": {"filename": source_path.name, "sha256": original_sha},
                "source_sha256": current, "mode": mode, "selected_keys": [r["key"] for r in rows],
                "batch_size": 25, "solver_changed": False, "new_policy_executed": False}
    write_report(parts_dir / "manifest.json", manifest)
    jobs = [(index, rows[start:start + 25]) for index, start in enumerate(range(0, len(rows), 25))]
    pool = ProcessPoolExecutor(max_workers=workers) if workers > 1 else None
    records, failures, part_hashes = [], [], {}
    try:
        batches = pool.map(run_batch, jobs) if pool else map(run_batch, jobs)
        for piece in batches:
            part = parts_dir / f"part-{piece['index']:05d}.json.gz"
            require(not part.exists(), "refuse to overwrite a part")
            write_report(part, piece)
            part_hashes[part.name] = file_sha(part)
            records.extend(piece["records"])
            failures.extend(piece["failure_certificates"])
            print({"checked": len(records), "total": len(rows),
                   "nonminimum_choices": sum(len(r["minimum_mismatches"]) for r in records),
                   "seconds": round(perf_counter() - started, 1)}, flush=True)
    finally:
        if pool:
            pool.shutdown(wait=True)
    require([r["key"] for r in records] == [r["key"] for r in rows], "final coverage/order mismatch")
    ending = source_hashes()
    ending["scripts/audit_minimum_names.py"] = file_sha(Path(__file__))
    require(ending == current and file_sha(source_path) == original_sha, "inputs changed during audit")
    counts = recount(records, source)
    return {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            **manifest, "full_corpus_run": mode == "full", "source_sha256_end": ending,
            "execution": {"workers": workers, "wall_seconds": perf_counter() - started,
                          "parts_directory": parts_dir.name, "part_sha256": part_hashes},
            "summary": counts, "records": records, "failure_certificates": failures,
            "fresh_independent_failure_proof_replays": len(failures),
            "all_minimum_equivalent": counts["nonminimum_choices"] == 0,
            "limits": ["Original solver rerun; no separately changed solver or successful repair is claimed.",
                       "Pre-choice domains and singleton names checked directly for EVERY active choice.",
                       "No difference implies identical deterministic transitions after replacing only the expression.",
                       "All old proof hashes matched; only failure proofs were freshly independently replayed here.",
                       "Numerically smallest label is not a minimum-total-colors or safe-extension proof.",
                       "Existing finite corpus, not unseen data or a theorem about all plane maps."]}


def main():
    """Require fresh evidence paths; preserve the solver and every older report."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--parts", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--mode", choices=("full", "failures"), default="full")
    args = parser.parse_args()
    if args.output.exists() or args.summary.exists() or args.output.resolve() == args.summary.resolve():
        parser.error("choose distinct fresh outputs")
    if not 1 <= args.workers <= 8:
        parser.error("workers must be 1..8")
    report = build_report(args.source, args.parts, args.workers, args.mode)
    write_report(args.output, report)
    small = {k: v for k, v in report.items() if k not in ("records", "failure_certificates")}
    small["result_sha256"] = file_sha(args.output)
    write_report(args.summary, small)
    print(json_value({"complete": True, **report["summary"], "sha256": small["result_sha256"]}), flush=True)


if __name__ == "__main__":
    main()

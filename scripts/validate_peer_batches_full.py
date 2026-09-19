"""Replay every frozen drawing with same-stage peer-batch geometry.

The candidate receives geometry alone, makes one deterministic attempt, and is
checked independently. The v3 comparison is copied from hash-bound evidence;
its old colors and timings are never inputs to the new naming rule. Every
failure and every predeclared diagnostic retains its complete certificate.
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

from fourcolor.staged_levels import POLICY as BASELINE
from fourcolor.peer_batches import POLICY, restart_peer_batch_names
from scripts.validate_frontier_restart import EXISTING, HELDOUT, file_sha, paired_counts, read_json
from scripts.validate_global_restart import digest, export_geometries, write_report
from scripts.validate_staged_levels_full import source_hashes as previous_source_hashes
from scripts.validate_relation_frontier_full import failure_rank, require, validate_inventory as geometric_inventory
from scripts.validate_peer_batches import verify_run

SOURCE = ROOT / "outputs/staged-levels-full-2026-09-19.json.gz"
SOURCE_SHA256 = "87250016644ba5c9c25573e0894af563eb451cd43915c11bad73927308af4910"
SELECTION = ROOT / "outputs/peer-batch-selection-2026-09-19.json"
SELECTION_SHA256 = "fcf7338222accfce47c6ee1963beaacb6079868f6910124c463a0bafefb38b8a"
POLICIES = (BASELINE, POLICY)
NEW_SOURCES = ("fourcolor/peer_batches.py", "scripts/validate_peer_batches.py",
               "scripts/validate_peer_batches_full.py", "docs/PEER_BATCH_RULES-2026-09-19.md")


def source_hashes():
    """Bind prior algorithms plus the candidate, independent checker and runner."""
    hashes = previous_source_hashes()
    hashes.update({name: file_sha(ROOT / name) for name in NEW_SOURCES})
    return hashes


def validate_inventory(previous):
    """Check geometric denominators, then require the immediate v3 baseline.

    The shared inventory guard reads only geometry keys, cohorts and references;
    it makes no assumption about which older policies are present in ``runs``.
    """
    rows = geometric_inventory(previous)
    require(previous["policy"] == BASELINE, "source is not the frozen v3 policy")
    require(all(BASELINE in row["runs"] for row in rows), "v3 baseline record missing")
    require(all(row["runs"][BASELINE]["status"] in ("solved", "conflict")
                for row in rows), "v3 baseline status is invalid")
    require(len(previous["source_sha256"]) == 26, "frozen v3 source inventory changed")
    return rows


def validate_selection(selection, rows, source_path):
    """Bind forty diagnostic geometries without passing their old names to v4."""
    require(selection["schema_version"] == 1 and selection["reference_policy"] == BASELINE,
            "selection schema or baseline changed")
    require(selection["unseen_holdout"] is False and selection["old_colors_read"] is False
            and selection["production_solver_executed"] is False,
            "selection provenance changed")
    require(selection["source_evidence"] ==
            {"filename": source_path.name, "sha256": file_sha(source_path)},
            "selection uses a different source archive")
    content = {name: selection[name] for name in ("selected_keys", "roles", "controls", "failed_histories")}
    require(digest(content) == selection["selection_sha256"] == SELECTION_SHA256,
            "fixed selection membership changed")
    require(selection["selection_script_sha256"] == file_sha(ROOT / "scripts/select_batch_diagnostics.py"),
            "selection script changed")
    for name, checksum in selection["preserved_theory_evidence"].items():
        require(file_sha(ROOT / name) == checksum, "preserved conflict evidence changed: " + name)
    keys = set(selection["selected_keys"])
    indexed = {row["key"]: row for row in rows}
    require(len(keys) == len(selection["selected_keys"]) == 40 and keys <= set(indexed),
            "forty-case coverage changed")
    require([row["key"] for row in selection["drawings"]] == selection["selected_keys"],
            "selected geometry order changed")
    for row in selection["drawings"]:
        saved = indexed[row["key"]]
        require(all(row[name] == saved[name] for name in (
            "document", "aliases", "cohorts", "geometry_sha256", "face_count",
            "real_bridge_count", "virtual_connector_count")), "selected input geometry changed")
        require(row["reference_status"] == saved["runs"][BASELINE]["status"],
                "selected reference status changed")
        require(row["roles"] == selection["roles"][row["key"]], "selected diagnostic role changed")
        require("colors" not in row and "runs" not in row, "selection unexpectedly contains old colors")
    require(selection["counts"]["distinct_drawings"] == 40
            and selection["counts"]["current_failures"] == 4
            and selection["counts"]["prior_diagnostics"] == 7
            and selection["counts"]["failed_history_prefix_references"] == 25
            and selection["counts"]["successful_controls"] == 8
            and selection["counts"]["reference_statuses"] ==
                dict(Counter(indexed[key]["runs"][BASELINE]["status"] for key in keys)),
            "selection declared counts changed")
    return keys


def compact_candidate(result, check):
    """Keep initialization and final states, with hashes of every full proof."""
    require(check["passed"], "independent candidate check failed")
    compact = {key: result[key] for key in (
        "status", "policy", "choices", "backtracks", "old_colors_read", "colors",
        "unranked_mothers", "initialization", "initial_anchors_by_dart",
        "domains", "anchors_by_dart", "local_budget", "hall_conflict")}
    steps = result["trace"]
    compact.update({"verification": check, "independent_check_passed": True,
        "trace_sha256": digest(steps), "levels_sha256": digest(result["levels"]),
        "batch_geometry_sha256": digest(result["batch_geometry"]),
        "raw_result_sha256": digest(result),
        "propagation_phases_sha256": digest(result["propagation_phases"]),
        "active_one_choices": sum(step["symbol"] == 1 for step in steps),
        "direct_one_bans": sum(1 in step.get("boundary", {}).get("direct_forbidden", []) for step in steps),
        "derived_one_bans": sum(1 in step.get("boundary", {}).get("derived_exclusions", []) for step in steps)})
    # Save explicit retained-side evidence rather than inferring it from final
    # colors: later propagation can name other sides 2 as well.
    compact["initial_retained_choice"] = (
        {key: steps[0].get(key) for key in ("choice_kind", "mother", "side", "dart", "domain", "symbol")}
        if steps else None)
    compact["initial_trace"] = steps[0] if steps else None
    batch = result["batch_geometry"]
    stages = batch["stages"]
    # This compact structure records scope and scheduling, not the full
    # coarse-cell membership; all diagnostic/failure certificates retain that.
    compact["batch_geometry_summary"] = {
        "stage_count": len(stages), "unranked_stage": batch["unranked_stage"],
        "mother_stage_counts": dict(Counter(str(value) for value in batch["mother_stages"].values())),
        "ready_side_stage_counts": dict(Counter(str(value) for value in batch["side_ready_stage"])),
        "active_stage_choice_counts": dict(Counter(str(step["active_stage"]) for step in steps[1:])),
        "ready_choices": len(steps) - 1,
        "coarse_cell_counts": {str(row["stage"]): len(row["coarse_cells"]) for row in stages},
        "max_peer_batch_size": max((len(row["new_mothers"]) for row in stages), default=0),
        "nontrivial_peer_stages": sum(len(row["new_mothers"]) > 1 for row in stages),
        "max_unfinished_cell_size": max((len(cell) for row in stages for cell in row["coarse_cells"]),
                                         default=0),
        "initial_retained_ready_stage": batch["side_ready_stage"][steps[0]["side"]] if steps else None,
    }
    return compact


def run_batch(payload):
    """Reconstruct each drawing and run exactly once without old color input."""
    index, saved_rows, diagnostic_keys = payload
    exported_rows = export_geometries(saved_rows)
    require(len(exported_rows) == len(saved_rows), "geometry export dropped inputs")
    records, details = [], {}
    least = None
    for saved, exported in zip(saved_rows, exported_rows):
        require(exported["key"] == saved["key"] and exported["status"] == "geometry_ok",
                "geometry export changed or failed")
        geometry = exported["geometry"]
        require(digest(geometry) == saved["geometry_sha256"], "geometry hash changed")
        start = perf_counter()
        result = restart_peer_batch_names(geometry)
        elapsed = perf_counter() - start
        start = perf_counter()
        check = verify_run(geometry, result)
        compact = compact_candidate(result, check)
        compact.update(runtime_seconds=elapsed, audit_seconds=perf_counter() - start)
        require(result["status"] in ("solved", "conflict"), "optional levels must not block startup")
        record = {key: value for key, value in saved.items() if key != "runs"}
        record["runs"] = {BASELINE: saved["runs"][BASELINE], POLICY: compact}
        records.append(record)
        # Unlike the earlier batch-minimum convention, save ALL failures.
        # Earlier diagnostics can legitimately acquire different trajectories.
        if result["status"] != "solved" or saved["key"] in diagnostic_keys:
            detail = {"key": saved["key"], "document": saved["document"],
                "aliases": saved["aliases"], "face_count": saved["face_count"],
                "geometry": geometry, "outcome": result, "verification": check,
                "previous_result": saved["runs"][BASELINE],
                "is_predeclared_diagnostic": saved["key"] in diagnostic_keys}
            details[saved["key"]] = detail
            if result["status"] != "solved" and (least is None or failure_rank(detail) < failure_rank(least)):
                least = detail
    return {"index": index, "records": records, "detailed_examples": details,
            "least_conflict": least,
            "diagnostics_checked": sum(row["key"] in diagnostic_keys for row in records)}


def summarize(records, histories, statics):
    """Count unique drawings and history references separately for both policies."""
    by_key = {row["key"]: row for row in records}
    history_results = []
    for policy in POLICIES:
        for history in histories:
            states = [by_key[key]["runs"][policy]["status"] for key in history["prefix_keys"]]
            history_results.append({"key": history["key"], "cohort": history["cohort"], "policy": policy,
                "statuses": states, "all_prefixes_solved": all(s == "solved" for s in states),
                "first_non_solved_prefix": next((i for i, s in enumerate(states) if s != "solved"), None),
                "recoveries": [{"prefix": i, "from": states[i - 1]} for i in range(1, len(states))
                               if states[i] == "solved" and states[i - 1] != "solved"],
                "final_status": states[-1]})
    indexed = {(row["key"], row["policy"]): row for row in history_results}
    summaries, comparisons = [], []
    for cohort in ("combined", EXISTING, HELDOUT):
        drawings = [row for row in records if cohort == "combined" or cohort in row["cohorts"]]
        sequences = [row for row in histories if cohort == "combined" or row["cohort"] == cohort]
        inputs = [row for row in statics if cohort == "combined" or row["cohort"] == cohort]
        for policy in POLICIES:
            states = [indexed[(row["key"], policy)] for row in sequences]
            summaries.append({"cohort": cohort, "policy": policy, "distinct_drawings": len(drawings),
                "statuses": dict(Counter(row["runs"][policy]["status"] for row in drawings)),
                "histories": len(sequences),
                "history_prefix_references": sum(len(row["prefix_keys"]) for row in sequences),
                "all_prefixes_solved": sum(row["all_prefixes_solved"] for row in states),
                "histories_with_conflict": sum("conflict" in row["statuses"] for row in states),
                "history_final_status": dict(Counter(row["final_status"] for row in states)),
                "static_references": len(inputs),
                "static_status": dict(Counter(by_key[row["geometry_key"]]["runs"][policy]["status"]
                                               for row in inputs))})
        def paired_status(row):
            """A conflict is an unsuccessful attempt, not a non-four-colorable map."""
            return (row["runs"][BASELINE]["status"] == "solved", row["runs"][POLICY]["status"] == "solved")
        transitions = Counter((row["runs"][BASELINE]["status"], row["runs"][POLICY]["status"])
                              for row in drawings)
        comparisons.append({"cohort": cohort, "baseline": BASELINE, "candidate": POLICY,
            "baseline_newly_rerun": False,
            "distinct_drawings": paired_counts(paired_status(row) for row in drawings),
            "status_transitions": [{"baseline_status": a, "candidate_status": b, "count": count}
                                   for (a, b), count in sorted(transitions.items())],
            "all_history_prefixes": paired_counts((indexed[(row["key"], BASELINE)]["all_prefixes_solved"],
                                                   indexed[(row["key"], POLICY)]["all_prefixes_solved"])
                                                  for row in sequences),
            "history_final": paired_counts((indexed[(row["key"], BASELINE)]["final_status"] == "solved",
                                            indexed[(row["key"], POLICY)]["final_status"] == "solved")
                                           for row in sequences),
            "static_final": paired_counts(paired_status(by_key[row["geometry_key"]]) for row in inputs),
            "regression_keys": [row["key"] for row in drawings if paired_status(row) == (True, False)]})
    return summaries, history_results, comparisons


def initialization_summary(records):
    """Expose retained color, selected mother and mode without assuming success."""
    modes = Counter()
    symbols = Counter()
    selections = []
    for row in records:
        run = row["runs"][POLICY]
        choice = run["initial_retained_choice"]
        mode = run["initialization"].get("mode", "unspecified")
        modes[mode] += 1
        if choice is not None:
            symbols[str(choice["symbol"])] += 1
        selections.append({"key": row["key"], "mode": mode,
                           "retained_choice": choice, "status": run["status"]})
    return {"mode_counts": dict(modes), "retained_symbol_counts": dict(symbols),
            "retained_two_count": symbols.get("2", 0), "selections": selections}


def batch_geometry_summary(records):
    """Aggregate staging counts across independent drawings, not history aliases."""
    stage_counts, active_stages, ready_stages, mother_stages = Counter(), Counter(), Counter(), Counter()
    totals = Counter()
    for row in records:
        compact = row["runs"][POLICY]["batch_geometry_summary"]
        stage_counts[str(compact["stage_count"])] += 1
        active_stages.update(compact["active_stage_choice_counts"])
        ready_stages.update(compact["ready_side_stage_counts"])
        mother_stages.update(compact["mother_stage_counts"])
        totals.update({"ready_choices": compact["ready_choices"],
                       "drawings_with_unranked_stage": compact["unranked_stage"] is not None,
                       "drawings_with_peer_batch": compact["nontrivial_peer_stages"] > 0,
                       "nontrivial_peer_stages": compact["nontrivial_peer_stages"]})
    return {"distinct_drawings": len(records), "stage_count_distribution": dict(stage_counts),
            "active_stage_choice_counts": dict(active_stages), "ready_side_stage_counts": dict(ready_stages),
            "mother_stage_counts": dict(mother_stages), **dict(totals)}


def build_report(source_path, selection_path, checkpoint_dir, workers=4, batch_size=25, limit=None, resume=False):
    """Freeze provenance before execution and refuse any changed resume input."""
    require(sys.flags.optimize == 0, "proof replay must run without Python -O")
    require(1 <= workers <= 8 and batch_size >= 1 and (limit is None or limit >= 1), "invalid execution bounds")
    began = perf_counter()
    require(file_sha(source_path) == SOURCE_SHA256, "source is not the frozen v3 archive")
    previous, selection = read_json(source_path), read_json(selection_path)
    rows = validate_inventory(previous)
    hashes = source_hashes()
    require(previous["source_sha256"] == previous["source_sha256_end"], "baseline source drifted")
    require(previous_source_hashes() == previous["source_sha256"], "baseline code changed")
    diagnostics = validate_selection(selection, rows, source_path)
    old_failure_keys = {row["key"] for row in rows if row["runs"][BASELINE]["status"] != "solved"}
    require(len(old_failure_keys) == 4 and old_failure_keys <= diagnostics,
            "frozen v3 four failures missing from selection")
    if limit is not None:
        rows = rows[:limit]
    selected = {row["key"] for row in rows}
    histories = [row for row in previous["histories"] if set(row["prefix_keys"]) <= selected]
    statics = [row for row in previous["static_inputs"] if row["geometry_key"] in selected]
    manifest = {"source_evidence": {"filename": source_path.name, "sha256": file_sha(source_path)},
        "selection_evidence": {"filename": selection_path.name, "sha256": file_sha(selection_path)},
        "source_sha256": hashes, "selected_keys": [row["key"] for row in rows], "batch_size": batch_size,
        "smoke_limit": limit, "policy": POLICY, "baseline": BASELINE, "baseline_newly_rerun": False,
        "diagnostic_keys": sorted(diagnostics), "old_failure_keys": sorted(old_failure_keys)}
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
            require(piece["index"] == index and [row["key"] for row in piece["records"]] ==
                    [row["key"] for row in batch], "checkpoint coverage mismatch")
            pieces[index], part_hashes[path.name] = piece, file_sha(path)
        else:
            jobs.append((index, batch, diagnostics & {row["key"] for row in batch}))
    pool = ProcessPoolExecutor(max_workers=workers) if workers > 1 else None
    try:
        for piece in (pool.map(run_batch, jobs) if pool else map(run_batch, jobs)):
            path = checkpoint_dir / f"part-{piece['index']:05d}.json.gz"
            checksum_path = path.with_suffix(path.suffix + ".sha256.json")
            require(not path.exists() and not checksum_path.exists(), "refuse to overwrite checkpoint evidence")
            write_report(path, piece)
            write_report(checksum_path, {"filename": path.name, "sha256": file_sha(path)})
            pieces[piece["index"]], part_hashes[path.name] = piece, file_sha(path)
            statuses = Counter(row["runs"][POLICY]["status"] for p in pieces.values() for row in p["records"])
            print({"checked": sum(statuses.values()), "total": len(rows), "statuses": dict(statuses),
                   "seconds": round(perf_counter() - began, 1)}, flush=True)
    finally:
        if pool:
            pool.shutdown(wait=True)
    records = [row for index in sorted(pieces) for row in pieces[index]["records"]]
    require([row["key"] for row in records] == [row["key"] for row in rows], "final coverage mismatch")
    ending = source_hashes()
    require(ending == hashes and manifest["source_evidence"]["sha256"] == file_sha(source_path)
            and manifest["selection_evidence"]["sha256"] == file_sha(selection_path), "sources changed during run")
    validate_selection(selection, validate_inventory(previous), source_path)
    summary, history_results, paired = summarize(records, histories, statics)
    details = {key: value for piece in pieces.values() for key, value in piece["detailed_examples"].items()}
    failures = {row["key"] for row in records if row["runs"][POLICY]["status"] != "solved"}
    require(set(details) == failures | (selected & diagnostics), "full failure/diagnostic certificates missing")
    totals = Counter()
    for row in records:
        totals.update({key: value for key, value in row["runs"][POLICY]["verification"].items() if type(value) is int})
    least = min((details[key] for key in failures), key=failure_rank) if failures else None
    return {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "experiment": "Peer-batch geometry and ready-side naming: entire frozen inventory",
        "smoke_limit": limit, "full_corpus_run": limit is None, "unseen_holdout": False,
        "source_evidence": manifest["source_evidence"], "selection_evidence": manifest["selection_evidence"],
        "source_sha256": hashes, "source_sha256_end": ending, "source_hashes_unchanged": True,
        "policy": POLICY, "baseline": BASELINE, "baseline_newly_rerun": False,
        "baseline_evidence": "Copied unchanged from hash-bound independently checked v3 full report; not rerun",
        "execution": {"workers": workers, "batch_size": batch_size, "resumed": resume,
            "wall_seconds": perf_counter() - began, "checkpoint_directory": checkpoint_dir.name,
            "part_sha256": part_hashes},
        "drawings": records, "histories": histories, "static_inputs": statics,
        "summary": summary, "history_results": history_results, "paired_comparisons": paired,
        "independent_checks": len(records), "replay_totals": dict(totals),
        "diagnostic_keys": sorted(diagnostics), "diagnostics_checked": len(selected & diagnostics),
        "old_failure_keys": sorted(old_failure_keys), "failure_keys": sorted(failures),
        "initialization_summary": initialization_summary(records),
        "batch_geometry_summary": batch_geometry_summary(records),
        "detailed_examples": details, "least_conflict": least,
        "limits": ["Complete finite already-inspected corpus, not all plane maps or an unseen holdout.",
            "Only v4 is rerun; v3 outcomes and runtimes are archived comparisons.",
            "Every geometry prefix restarts independently; final success does not erase a failed prefix.",
            "All failed runs and the forty predeclared diagnostics retain full certificates.",
            "The earlier diagnostics may have new trajectories; exact v3 reproduction is not required.",
            "Four names are an input; independent checks certify this path, not universal extendibility.",
            "No old colors, alternative-policy retry, assignment enumeration or backtracking.",
            "Peer stages organize current geometry; readiness does not prove that every greedy choice extends."]}


def main():
    """Write new reports only; resume uses strictly hash-matched checkpoints."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--selection", type=Path, default=SELECTION)
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
    report = build_report(args.source, args.selection, args.checkpoints,
                          args.workers, args.batch_size, args.limit, args.resume)
    write_report(args.output, report)
    small = {key: value for key, value in report.items() if key not in (
        "drawings", "histories", "static_inputs", "history_results", "detailed_examples",
        "least_conflict", "initialization_summary")}
    small.update({"input": {"filename": args.output.name, "sha256": file_sha(args.output)},
        "distinct_drawings": len(report["drawings"]),
        "history_prefix_references": sum(len(row["prefix_keys"]) for row in report["histories"]),
        "static_references": len(report["static_inputs"]),
        "initialization_summary": {key: value for key, value in report["initialization_summary"].items()
                                   if key != "selections"}})
    detail = report["least_conflict"]
    small["least_conflict"] = {key: detail[key] for key in ("key", "face_count", "aliases")} if detail else None
    write_report(args.summary, small)
    print({"summary": report["summary"], "paired": report["paired_comparisons"]}, flush=True)


if __name__ == "__main__":
    main()

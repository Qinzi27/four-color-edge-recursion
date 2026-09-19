"""Independently recalculate the full level-rule report and replay fixed samples.

This audit does not import the full runner's summarizer or mutate frozen inputs.
All 7,069 stored records and checkpoint bytes are checked. Only the explicitly
listed sample is newly solved here; the original run checked every certificate.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.level_sides import POLICY, restart_level_side_names
from scripts.validate_frontier_restart import file_sha, json_value, read_json
from scripts.validate_global_restart import digest, export_geometries, write_report
from scripts.validate_level_sides import verify_run


def require(condition, reason):
    """Retain audit guards even if a caller accidentally enables optimization."""
    if not condition:
        raise AssertionError(reason)


def paired(values):
    """Compute paired completion counts without the producer's helper."""
    result = dict(both_solved=0, improved=0, regressed=0, both_not_solved=0)
    for old, new in values:
        key = ("both_solved" if old and new else "improved" if new else
               "regressed" if old else "both_not_solved")
        result[key] += 1
    return result


def audit_summaries(report):
    """Rebuild drawing, history, static and status-pair accounting from records."""
    rows = report["drawings"]
    by_key = {r["key"]: r for r in rows}
    baseline = report["baseline"]
    policies = (baseline, POLICY)
    expected_histories = []
    for policy in policies:
        for history in report["histories"]:
            states = [by_key[k]["runs"][policy]["status"] for k in history["prefix_keys"]]
            indices = {name: [i for i, value in enumerate(states) if value == name]
                       for name in ("conflict", "outside_scope")}
            incomplete = [i for i, value in enumerate(states) if value != "solved"]
            expected_histories.append({
                "key": history["key"], "cohort": history["cohort"], "policy": policy,
                "statuses": states, "all_prefixes_solved": not incomplete,
                "first_non_solved_prefix": incomplete[0] if incomplete else None,
                "first_conflict_prefix": next(iter(indices["conflict"]), None),
                "first_outside_scope_prefix": next(iter(indices["outside_scope"]), None),
                "recoveries": [{"prefix": i, "from": states[i - 1]}
                               for i in range(1, len(states))
                               if states[i] == "solved" and states[i - 1] != "solved"],
                "final_status": states[-1]})
    require(report["history_results"] == expected_histories, "history detail accounting mismatch")
    history_by_key = {(h["key"], h["policy"]): h for h in expected_histories}
    summaries, comparisons = [], []
    for cohort in ("combined", "existing-corpus", "new-seeds-20261901-20261940"):
        drawings = [r for r in rows if cohort == "combined" or cohort in r["cohorts"]]
        histories = [h for h in report["histories"] if cohort == "combined" or h["cohort"] == cohort]
        statics = [s for s in report["static_inputs"] if cohort == "combined" or s["cohort"] == cohort]
        for policy in policies:
            states = [history_by_key[(h["key"], policy)] for h in histories]
            summaries.append({
                "cohort": cohort, "policy": policy, "distinct_drawings": len(drawings),
                "statuses": dict(Counter(r["runs"][policy]["status"] for r in drawings)),
                "histories": len(histories),
                "history_prefix_references": sum(len(h["prefix_keys"]) for h in histories),
                "all_prefixes_solved": sum(h["all_prefixes_solved"] for h in states),
                "histories_with_conflict": sum(h["first_conflict_prefix"] is not None for h in states),
                "histories_with_outside_scope": sum(h["first_outside_scope_prefix"] is not None for h in states),
                "history_final_status": dict(Counter(h["final_status"] for h in states)),
                "static_references": len(statics),
                "static_status": dict(Counter(by_key[s["geometry_key"]]["runs"][policy]["status"]
                                              for s in statics))})
        matrix = Counter((r["runs"][baseline]["status"], r["runs"][POLICY]["status"]) for r in drawings)
        comparisons.append({
            "cohort": cohort, "baseline": baseline, "candidate": POLICY,
            "baseline_newly_rerun": False,
            "distinct_drawings": paired((r["runs"][baseline]["status"] == "solved",
                                          r["runs"][POLICY]["status"] == "solved") for r in drawings),
            "status_transitions": [{"baseline_status": old, "candidate_status": new, "count": count}
                                   for (old, new), count in sorted(matrix.items())],
            "all_history_prefixes": paired((history_by_key[(h["key"], baseline)]["all_prefixes_solved"],
                                            history_by_key[(h["key"], POLICY)]["all_prefixes_solved"])
                                           for h in histories),
            "history_final": paired((history_by_key[(h["key"], baseline)]["final_status"] == "solved",
                                      history_by_key[(h["key"], POLICY)]["final_status"] == "solved")
                                     for h in histories),
            "static_final": paired((by_key[s["geometry_key"]]["runs"][baseline]["status"] == "solved",
                                     by_key[s["geometry_key"]]["runs"][POLICY]["status"] == "solved")
                                    for s in statics)})
    require(report["summary"] == summaries, "summary counts mismatch")
    require(report["paired_comparisons"] == comparisons, "paired counts mismatch")
    return summaries, comparisons


def audit_checkpoints(report, folder):
    """Rehash every compressed part and verify exact ordered record coverage."""
    declared = report["execution"]["part_sha256"]
    files = sorted(folder.glob("part-*.json.gz"))
    require(len(files) == len(declared) == 283, "expected 283 complete checkpoints")
    require({p.name for p in files} == set(declared), "checkpoint filename inventory mismatch")
    manifest = read_json(folder / "manifest.json")
    require(manifest["selected_keys"] == [r["key"] for r in report["drawings"]], "manifest keys changed")
    require(manifest["source_sha256"] == report["source_sha256"], "manifest source binding changed")
    require(manifest["smoke_limit"] is None and manifest["batch_size"] == 25, "manifest scope changed")
    for name in ("source_evidence", "diagnostic_evidence"):
        require(manifest[name] == report[name], "manifest input binding changed")
    combined, details = [], {}
    exact, checked = 0, {}
    minima = {"conflict": [], "outside_scope": []}
    for index, path in enumerate(files):
        checksum = file_sha(path)
        require(checksum == declared[path.name], "checkpoint SHA changed: " + path.name)
        require(read_json(path.with_suffix(path.suffix + ".sha256.json")) ==
                {"filename": path.name, "sha256": checksum}, "checkpoint sidecar mismatch")
        part = read_json(path)
        require(part["index"] == index, "checkpoint index mismatch")
        require(len(part["records"]) == (25 if index < 282 else 19), "checkpoint batch size mismatch")
        combined.extend(part["records"])
        details.update(part["detailed_examples"])
        exact += part["diagnostic_exact_reproductions"]
        for status in minima:
            if part["least_" + status] is not None:
                minima[status].append(part["least_" + status])
        checked[path.name] = checksum
    require(combined == report["drawings"], "checkpoint record content/order mismatch")
    require(details == report["detailed_examples"], "checkpoint detailed examples mismatch")
    require(exact == report["diagnostic_exact_reproductions"] == 6, "six-case exact count mismatch")
    rank = lambda r: (r["face_count"], len(r["document"]["strokes"]), r["key"])
    for status, candidates in minima.items():
        expected = min(candidates, key=rank) if candidates else None
        require(expected == report["least_" + status], "batch minimum mismatch: " + status)
        eligible = [r for r in report["drawings"] if r["runs"][POLICY]["status"] == status]
        require((expected["key"] if expected else None) ==
                (min(eligible, key=rank)["key"] if eligible else None), "global minimum mismatch")
    return {"checkpoints_checked": len(files), "checkpoint_records_checked": len(combined),
            "diagnostic_exact_reproductions": exact, "hashes": checked}


def replay_samples(report, six):
    """Re-solve six diagnostics, both minima, and five fixed sorted-key positions."""
    rows = report["drawings"]
    selected = set(six)
    for status in ("conflict", "outside_scope"):
        detail = report["least_" + status]
        if detail:
            selected.add(detail["key"])
    indices = (0, 1767, 3534, 5301, 7068)
    selected.update(rows[i]["key"] for i in indices)
    samples = [r for r in rows if r["key"] in selected]
    exported = export_geometries(samples)
    require(len(exported) == len(samples), "sample geometry coverage mismatch")
    outcomes = []
    for row, export in zip(samples, exported):
        require(export["status"] == "geometry_ok" and export["key"] == row["key"], "sample export failed")
        geometry = export["geometry"]
        require(digest(geometry) == row["geometry_sha256"], "sample geometry SHA changed")
        fresh = restart_level_side_names(geometry)
        check = verify_run(geometry, fresh)
        stored = row["runs"][POLICY]
        require(check["passed"] and digest(fresh) == stored["raw_result_sha256"], "sample full result mismatch")
        require(digest(fresh["trace"]) == stored["trace_sha256"], "sample trace mismatch")
        require(digest(fresh["levels"]) == stored["levels_sha256"], "sample levels mismatch")
        require((digest(fresh["propagation_phases"]) if "propagation_phases" in fresh else None) ==
                stored["propagation_phases_sha256"], "sample proof hash mismatch")
        normalized_check = dict(check)
        normalized_check.setdefault("method", "independent-unrooted-level-scope-check")
        require(normalized_check == stored["verification"], "sample verification mismatch")
        for status in ("conflict", "outside_scope"):
            detail = report["least_" + status]
            if detail and row["key"] == detail["key"]:
                require(json_value(fresh) == detail["outcome"] and json_value(check) == detail["verification"],
                        "saved minimal certificate mismatch")
        if row["key"] in six:
            require(json_value(fresh) == six[row["key"]]["candidate"], "six-case full result drift")
            require(json_value(check) == six[row["key"]]["candidate_check"], "six-case proof check drift")
        outcomes.append({"key": row["key"], "face_count": row["face_count"], "status": fresh["status"],
                         "choices": fresh["choices"], "geometry_sha256": row["geometry_sha256"],
                         "raw_result_sha256": stored["raw_result_sha256"], "verification": check})
    return {"fixed_sorted_key_indices": list(indices), "sample_size": len(samples),
            "six_diagnostics_replayed": len(six), "records": outcomes}


def main():
    """Refuse partial evidence or overwrite, then write one independently derived audit."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "outputs/level-sides-full-2026-09-19.json.gz")
    parser.add_argument("--summary", type=Path, default=ROOT / "outputs/level-sides-full-summary-2026-09-19.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not sys.flags.optimize, "certificate replay requires Python without -O")
    require(not args.output.exists(), "choose a fresh audit output")
    report, small = read_json(args.report), read_json(args.summary)
    require(report["full_corpus_run"] is True and report["smoke_limit"] is None, "not a complete run")
    require(report["unseen_holdout"] is False and report["baseline_newly_rerun"] is False,
            "misstated experiment provenance")
    require(report["policy"] == POLICY, "candidate policy changed")
    require(small["input"] == {"filename": args.report.name, "sha256": file_sha(args.report)},
            "summary report hash mismatch")
    require(report["source_sha256"] == report["source_sha256_end"], "source changed during run")
    for path, expected in report["source_sha256"].items():
        require(file_sha(ROOT / path) == expected, "source changed after run: " + path)
    inputs = {}
    for name in ("source_evidence", "diagnostic_evidence"):
        path = args.report.parent / report[name]["filename"]
        require(file_sha(path) == report[name]["sha256"], "input evidence hash mismatch")
        inputs[name] = read_json(path)
    old, six = inputs["source_evidence"], {r["key"]: r for r in inputs["diagnostic_evidence"]["records"]}
    rows = report["drawings"]
    require(len(rows) == len({r["key"] for r in rows}) == 7069, "drawing denominator mismatch")
    previous = {r["key"]: r for r in old["drawings"]}
    require([r["key"] for r in rows] == sorted(previous), "frozen corpus keys mismatch")
    require(report["histories"] == old["histories"] and len(report["histories"]) == 363,
            "history corpus changed")
    require(report["static_inputs"] == old["static_inputs"] and len(report["static_inputs"]) == 302,
            "static corpus changed")
    require(sum(len(h["prefix_keys"]) for h in report["histories"]) == 7678, "prefix denominator mismatch")
    for row in rows:
        prior = previous[row["key"]]
        require({k: v for k, v in row.items() if k != "runs"} ==
                {k: v for k, v in prior.items() if k != "runs"}, "geometry/metadata changed")
        require(row["runs"][report["baseline"]] == prior["runs"][report["baseline"]], "archived baseline changed")
        candidate = row["runs"][POLICY]
        require(candidate["status"] in ("solved", "conflict", "outside_scope"), "unknown status")
        require(candidate["independent_check_passed"] and candidate["verification"]["passed"], "unverified record")
        require(candidate["backtracks"] == 0 and candidate["old_colors_read"] is False, "unexpected fallback")
        require((candidate["colors"] is not None) == (candidate["status"] == "solved"), "status/colors disagree")
    require(report["independent_checks"] == 7069 and len(six) == 6, "check count mismatch")
    summaries, comparisons = audit_summaries(report)
    require(small["summary"] == summaries and small["paired_comparisons"] == comparisons,
            "standalone summary differs")
    totals = Counter()
    for row in rows:
        totals.update({k: v for k, v in row["runs"][POLICY]["verification"].items() if type(v) is int})
    require(dict(totals) == report["replay_totals"], "proof event totals mismatch")
    parts = audit_checkpoints(report, args.report.parent / report["execution"]["checkpoint_directory"])
    replay = replay_samples(report, six)
    result = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "passed": True,
              "report": {"filename": args.report.name, "sha256": file_sha(args.report)},
              "audit_script_sha256": file_sha(Path(__file__)), "stored_drawings_checked": len(rows),
              "histories_checked": len(report["histories"]), "history_prefix_references_checked": 7678,
              "static_references_checked": len(report["static_inputs"]), "source_files_checked": len(report["source_sha256"]),
              "summary": summaries, "paired_comparisons": comparisons, "checkpoint_audit": parts,
              "fresh_sample_replay": replay,
              "limits": ["All stored summaries and checkpoint bytes rechecked; only the declared sample newly solved here.",
                         "Reuses the independent certificate checker, not the producer's summary functions.",
                         "The full runner separately checked every input certificate; the audit is not a second full 7069 solve."]}
    write_report(args.output, result)
    print({"passed": True, "records": len(rows), "parts": parts["checkpoints_checked"],
           "replayed": replay["sample_size"], "sha256": file_sha(args.output)})


if __name__ == "__main__":
    main()

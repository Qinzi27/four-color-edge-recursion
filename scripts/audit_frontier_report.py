"""Independently audit saved frontier-report arithmetic and provenance.

This standard-library audit never imports or runs a naming policy. It checks
all saved result/mapping counts, pairs, source bytes, and baseline states.
Geometric coloring certification remains the separately recorded runner
check: recomputing that production experiment is deliberately out of scope.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import json
from math import fsum, isclose
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXISTING = "existing-corpus"
HELDOUT = "new-seeds-20261901-20261940"
BASELINE = "closed-support"


def read_report(path):
    """Retain the compressed file hash, not merely a reserialization hash."""
    raw = path.read_bytes()
    payload = gzip.decompress(raw) if path.suffix == ".gz" else raw
    return json.loads(payload), sha256(raw).hexdigest()


def portable_hash(value):
    """Recompute documented JSON identities without importing production code."""
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")).hexdigest()


def verify(condition, message):
    """Abort on any mismatch rather than producing a misleading success log."""
    if not condition:
        raise AssertionError(message)


def table_of_pairs(pairs):
    """Compute the four cells independently from Boolean status pairs."""
    cells = Counter((bool(a), bool(b)) for a, b in pairs)
    return {"both_solved": cells[(True, True)], "improved": cells[(False, True)],
            "regressed": cells[(True, False)], "both_not_solved": cells[(False, False)]}


def audit(input_path, summary_path, baseline_path):
    """Audit existing saved rows and exact baseline states without rerunning them."""
    report, report_sha = read_report(input_path)
    small, summary_sha = read_report(summary_path)
    baseline, baseline_sha = read_report(baseline_path)
    verify(report["smoke_limit"] is None and report["full_corpus_run"], "report is not full corpus")
    verify(small["input"] == {"filename": input_path.name, "sha256": report_sha}, "summary input hash")
    for key, value in small.items():
        if key in report:
            verify(value == report[key], "small/full summary mismatch: " + key)
    sources = report["source_sha256"]
    verify(sources == report["source_sha256_end"] and report["source_hashes_unchanged"], "source start/end")
    current_sources = {path: sha256((ROOT / path).read_bytes()).hexdigest() for path in sources}
    verify(current_sources == sources, "current source bytes drift")
    verify(len(sources) == 33, "expected 33 recorded sources")
    verify(len(baseline["source_sha256"]) == 31, "expected 31 baseline sources")
    verify(all(sources[path] == value for path, value in baseline["source_sha256"].items()),
           "baseline sources do not match")

    records = report["drawings"]
    histories = report["histories"]
    statics = report["static_inputs"]
    policies = report["policies"]
    by_key = {r["key"]: r for r in records}
    old = {r["key"]: r for r in baseline["drawings"]}
    by_history = {r["key"]: r for r in histories}
    verify(len(by_key) == len(records), "duplicate geometry keys")
    verify(len(by_history) == len(histories), "duplicate history keys")
    verify(len(set(policies)) == len(policies) == 5 and policies[0] == BASELINE, "five independent policies")
    old_keys = {r["key"] for r in records if EXISTING in r["cohorts"]}
    new_keys = {r["key"] for r in records if HELDOUT in r["cohorts"]}
    verify(old_keys == set(old) and len(old_keys) == 6113, "same 6113 old drawings required")
    verify(len(new_keys) == 961 and len(old_keys & new_keys) == 5, "heldout distinct/overlap denominator")
    verify(len(records) == 7069 and old_keys | new_keys == set(by_key), "combined union denominator")
    verify(len(histories) == 363 and len(statics) == 302, "history/static denominator")
    verify(sorted(r["seed"] for r in histories if r["cohort"] == HELDOUT) == list(range(20261901, 20261941)),
           "predeclared heldout seeds")
    verify(all(len(r["prefix_keys"]) == 25 for r in histories if r["cohort"] == HELDOUT), "24-cut new histories")
    verify(all(r["cohort"] == EXISTING for r in statics), "new cohort has no static gallery")
    old_histories = {r["key"]: r for r in baseline["histories"]}
    for row in histories:
        verify(all(k in by_key for k in row["prefix_keys"]), "missing history prefix")
        if row["cohort"] == EXISTING:
            verify({k: row[k] for k in old_histories[row["key"]]} == old_histories[row["key"]],
                   "old history mapping or provenance drift")
    verify(sum(len(r["prefix_keys"]) for r in histories) == 7678, "prefix references")

    expected_aliases = Counter((key, "history_prefix", row["key"], step)
                               for row in histories for step, key in enumerate(row["prefix_keys"]))
    expected_aliases.update((row["geometry_key"], "static", row["key"], None) for row in statics)
    actual_aliases = Counter()
    for row in records:
        document = row["document"]
        strokes = sorted({tuple(sorted((tuple(s["a"]), tuple(s["b"])))) for s in document["strokes"]})
        key = portable_hash({"frame": document["frame"], "undirected_stroke_set": strokes})
        verify(key == row["key"], "drawing content hash mismatch")
        verify(row["geometry_status"] == "geometry_ok" and row["topology_checked"], "geometry not certified")
        verify(set(row["runs"]) == set(policies), "missing independent policy outcome")
        groups = set()
        for alias in row["aliases"]:
            if alias["kind"] == "history_prefix":
                actual_aliases[(key, "history_prefix", alias["history"], alias["step"])] += 1
                groups.add(by_history[alias["history"]]["cohort"])
            else:
                actual_aliases[(key, "static", alias["source"], None)] += 1
                groups.add(EXISTING)
        verify(groups == set(row["cohorts"]), "cohort labels disagree with aliases")
        for policy, run in row["runs"].items():
            verify(run["status"] in ("solved", "conflict"), "unclassified outcome")
            verify(run["independent_check_passed"] and run["verification"]["passed"], "missing check flag")
            verify(run["backtracks"] == 0 and not run["old_colors_read"] and run["local_budget"] is None,
                   "fresh no-fallback metadata mismatch")
            if run["status"] == "conflict":
                verify(run["verification"]["certificate"]["certified"] and run["colors"] is None,
                       "conflict certificate flag missing")
            else:
                verify(run["domains"] == [[c] for c in run["colors"]] and len(run["colors"]) == row["face_count"],
                       "completed domain/size metadata mismatch")
        if key in old:
            verify(row["geometry_sha256"] == old[key]["geometry_sha256"], "baseline geometry changed")
            for field in ("status", "domains", "anchors_by_dart", "colors", "trace_sha256"):
                verify(row["runs"][BASELINE][field] == old[key]["runs"][BASELINE][field],
                       "baseline state changed: " + field)
    verify(actual_aliases == expected_aliases, "lost, extra, or duplicated source mapping")
    verify(sum(actual_aliases.values()) == 7980, "total alias references")
    verify(report["independent_checks"] == 35345, "five checks per drawing")
    verify(report["baseline_evidence"]["sha256"] == baseline_sha and
           report["baseline_evidence"]["drawings_reproduced"] == 6113 and
           report["baseline_evidence"]["sources_matched"] == 31, "baseline evidence metadata")

    # Recompute all histories from raw drawing outcomes, not saved history_results.
    history_results = {}
    for row in histories:
        for policy in policies:
            statuses = [by_key[key]["runs"][policy]["status"] for key in row["prefix_keys"]]
            failed = [i for i, value in enumerate(statuses) if value != "solved"]
            entry = {"key": row["key"], "policy": policy, "family": row["family"], "cohort": row["cohort"],
                     "statuses": statuses, "all_prefixes_solved": not failed,
                     "first_failed_prefix": min(failed) if failed else None,
                     "solved_again_after_failure": [i for i in range(1, len(statuses))
                                                    if statuses[i - 1] != "solved" and statuses[i] == "solved"],
                     "final_status": statuses[-1]}
            history_results[(row["key"], policy)] = entry
    saved_history = {(r["key"], r["policy"]): r for r in report["history_results"]}
    verify(saved_history == history_results and len(saved_history) == len(report["history_results"]),
           "history status/recovery summary mismatch")

    rows_summary = []
    recomputed_pairs = []
    for group in ("combined", EXISTING, HELDOUT):
        drawings = [r for r in records if group == "combined" or group in r["cohorts"]]
        sequences = [r for r in histories if group == "combined" or r["cohort"] == group]
        static_group = [r for r in statics if group == "combined" or r["cohort"] == group]
        for policy in policies:
            rows = [history_results[(r["key"], policy)] for r in sequences]
            families = {}
            for row in rows:
                f = families.setdefault(row["family"], {"histories": 0, "all_prefixes_solved": 0,
                                                        "final_status": Counter()})
                f["histories"] += 1
                f["all_prefixes_solved"] += row["all_prefixes_solved"]
                f["final_status"][row["final_status"]] += 1
            expected = {"cohort": group, "policy": policy, "distinct_drawing_count": len(drawings),
                        "distinct_drawings": dict(Counter(r["runs"][policy]["status"] for r in drawings)),
                        "verification": dict(Counter(r["runs"][policy]["verification"]["method"] for r in drawings)),
                        "history_count": len(rows),
                        "history_prefix_references": sum(len(r["prefix_keys"]) for r in sequences),
                        "all_prefixes": {"all_solved": sum(r["all_prefixes_solved"] for r in rows),
                                         "has_failure": sum(not r["all_prefixes_solved"] for r in rows)},
                        "history_final_status": dict(Counter(r["final_status"] for r in rows)),
                        "history_families": families, "static_count": len(static_group),
                        "static_status": dict(Counter(by_key[r["geometry_key"]]["runs"][policy]["status"] for r in static_group)),
                        "hall_active_drawings": sum(r["runs"][policy].get("hall_derivation_events_including_recomputations", 0) > 0 for r in drawings),
                        "hall_derivation_events_including_recomputations": sum(r["runs"][policy].get("hall_derivation_events_including_recomputations", 0) for r in drawings),
                        "hall_explicit_deficiency_drawings": sum(bool(r["runs"][policy].get("hall_conflict")) for r in drawings)}
            saved = next(r for r in report["summary"] if r["cohort"] == group and r["policy"] == policy)
            verify({key: saved[key] for key in expected} == expected, "summary arithmetic: " + group + "/" + policy)
            seconds = fsum(r["runs"][policy]["runtime_seconds"] for r in drawings)
            verify(isclose(seconds, saved["runtime_seconds"], rel_tol=1e-12, abs_tol=1e-10), "runtime sum")
            rows_summary.append({**expected, "runtime_seconds": seconds})
            if policy == BASELINE:
                continue
            paired = {"cohort": group, "baseline": BASELINE, "candidate": policy,
                      "distinct_drawings": table_of_pairs((r["runs"][BASELINE]["status"] == "solved",
                                                           r["runs"][policy]["status"] == "solved") for r in drawings),
                      "all_history_prefixes": table_of_pairs((history_results[(r["key"], BASELINE)]["all_prefixes_solved"],
                                                             history_results[(r["key"], policy)]["all_prefixes_solved"]) for r in sequences),
                      "history_final": table_of_pairs((history_results[(r["key"], BASELINE)]["final_status"] == "solved",
                                                       history_results[(r["key"], policy)]["final_status"] == "solved") for r in sequences),
                      "static_final": table_of_pairs((by_key[r["geometry_key"]]["runs"][BASELINE]["status"] == "solved",
                                                      by_key[r["geometry_key"]]["runs"][policy]["status"] == "solved") for r in static_group)}
            saved_pair = next(r for r in report["paired_comparisons"] if r["cohort"] == group and r["candidate"] == policy)
            verify(paired == saved_pair, "paired counts: " + group + "/" + policy)
            recomputed_pairs.append(paired)
    verify(len(report["summary"]) == 15 and len(report["paired_comparisons"]) == 12, "summary row counts")

    # Selection is explicit: smallest input stroke count, then shores, then key;
    # it is not a claim of a minimal counterexample among all possible maps.
    remaining = sorted((r for r in records if r["runs"]["tight-hall"]["status"] != "solved"),
                       key=lambda r: (len(r["document"]["strokes"]), r["face_count"], r["key"]))
    examples = [{"key": r["key"], "input_strokes": len(r["document"]["strokes"]),
                 "face_count_including_exterior": r["face_count"], "aliases": r["aliases"],
                 "policy_status": {p: run["status"] for p, run in r["runs"].items()}}
                for r in remaining[:5]]
    return {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "audit_passed": True, "algorithm_rerun": False,
            "inputs": [{"filename": p.name, "sha256": value} for p, value in (
                (input_path, report_sha), (summary_path, summary_sha), (baseline_path, baseline_sha))],
            "auditor_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "checks": {"current_source_hashes_matched": len(sources), "baseline_source_hashes_matched": 31,
                       "baseline_geometry_and_status_domains_anchors_colors_trace_matches": 6113,
                       "distinct_drawings": len(records), "history_prefix_references": 7678,
                       "static_references": 302, "all_alias_references": 7980,
                       "stored_verified_policy_results": report["independent_checks"],
                       "history_result_rows_recomputed": len(history_results),
                       "summary_rows_recomputed": len(rows_summary), "paired_rows_recomputed": len(recomputed_pairs)},
            "cohort_denominators": {EXISTING: {"distinct_drawings": 6113, "histories": 323,
                                               "prefix_references": 6678, "static_references": 302},
                                    HELDOUT: {"distinct_drawings": 961, "histories": 40,
                                              "prefix_references": 1000, "static_references": 0},
                                    "drawing_overlap": len(old_keys & new_keys), "combined_distinct_drawings": len(records)},
            "recomputed_summary": rows_summary, "recomputed_pairs": recomputed_pairs,
            "smallest_remaining_examples": examples,
            "limits": ["Audits saved arithmetic/provenance; does not repeat geometric production or solver runs.",
                       "Verified-result flags are checked for consistent recording, not treated as a new independent mathematical proof.",
                       "Five cohort-overlap drawings are cached once; drawing denominators cannot be added directly.",
                       "Remaining examples are minimal only under declared ordering within this finite corpus.",
                       "Greedy-anchor inconsistency is not an obstruction to four-coloring the underlying map."]}


def main():
    """Create an exclusive evidence log; earlier experiments remain untouched."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "outputs/frontier-restart-all-2026-09-19.json.gz")
    parser.add_argument("--summary", type=Path, default=ROOT / "outputs/frontier-restart-summary-2026-09-19.json")
    parser.add_argument("--baseline", type=Path, default=ROOT / "outputs/global-restart-all-2026-09-18-v2.json.gz")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/frontier-report-audit-2026-09-19.json")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("choose a new output path; audit evidence is never overwritten")
    result = audit(args.input, args.summary, args.baseline)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"audit_passed": True, "checks": result["checks"],
                      "denominators": result["cohort_denominators"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

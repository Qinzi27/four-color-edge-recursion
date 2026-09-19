"""Audit immutable full-restart reports and replay a few ordering witnesses.

Standard-library only. The complete corpus is audited from saved evidence;
only selected small prefix drawings are rerun to distinguish real selection
changes from trace hashes that merely changed because of new metadata fields.
Existing reports and outputs are never overwritten.
"""

from argparse import ArgumentParser
from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def require(condition, message):
    """Do not publish an audit summary if any checked invariant fails."""
    if not condition:
        raise AssertionError(message)


def digest(value):
    """Match the report's canonical JSON trace/geometry hash convention."""
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode("utf-8")).hexdigest()


def read_report(path):
    """Preserve exact compressed input provenance without private paths."""
    raw = path.read_bytes()
    payload = gzip.decompress(raw) if path.suffix == ".gz" else raw
    return json.loads(payload), {"filename": path.name, "sha256": sha256(raw).hexdigest(), "bytes": len(raw)}


def index(rows, fields):
    """Reject duplicate logical identities before a dictionary hides them."""
    result = {tuple(row[field] for field in fields): row for row in rows}
    require(len(result) == len(rows), "duplicate identity: " + repr(fields))
    return result


def verify_mappings_and_summaries(report):
    """Recompute every prefix/static mapping, recovery and family summary."""
    drawings = index(report["drawings"], ("key",))
    histories = index(report["histories"], ("key",))
    statics = index(report["static_inputs"], ("key",))
    expected_aliases = Counter()
    for history in histories.values():
        for step, key in enumerate(history["prefix_keys"]):
            require((key,) in drawings, "history prefix missing geometry")
            expected_aliases[(key, "history_prefix", history["key"], step)] += 1
    for row in statics.values():
        require((row["geometry_key"],) in drawings, "static input missing geometry")
        expected_aliases[(row["geometry_key"], "static", row["key"], None)] += 1
    actual_aliases = Counter()
    checks = 0
    for drawing in drawings.values():
        require(drawing["geometry_status"] == "geometry_ok" and drawing["topology_checked"],
                "unexpected unchecked geometry")
        for alias in drawing["aliases"]:
            actual_aliases[(drawing["key"], alias["kind"],
                            alias.get("history", alias.get("source")), alias.get("step"))] += 1
        for run in drawing["runs"].values():
            require(run["independent_check_passed"] is True and run["old_colors_read"] is False
                    and run["local_budget"] is None and run["backtracks"] == 0,
                    "restart/check contract changed")
            checks += 1
    require(expected_aliases == actual_aliases, "source/prefix aliases are incomplete or duplicated")
    require(checks == report["independent_checks"], "independent-check count differs")
    saved_histories = index(report["history_results"], ("policy", "key"))
    for summary in report["summary"]:
        policy = summary["policy"]
        final, prefixes, families = Counter(), Counter(), {}
        for history in histories.values():
            statuses = [drawings[(key,)]["runs"][policy]["status"] for key in history["prefix_keys"]]
            failed = [step for step, status in enumerate(statuses) if status != "solved"]
            recovery = [step for step in range(1, len(statuses))
                        if statuses[step] == "solved" and statuses[step - 1] != "solved"]
            expected = {"key": history["key"], "policy": policy, "statuses": statuses,
                        "all_prefixes_solved": not failed, "first_failed_prefix": failed[0] if failed else None,
                        "solved_again_after_failure": recovery, "final_status": statuses[-1]}
            require(saved_histories[(policy, history["key"]) ] == expected, "history status/recovery differs")
            final[statuses[-1]] += 1
            prefixes["all_solved" if not failed else "has_failure"] += 1
            family = families.setdefault(history["family"], {"histories": 0, "all_prefixes_solved": 0,
                                                             "final_status": Counter()})
            family["histories"] += 1
            family["all_prefixes_solved"] += not failed
            family["final_status"][statuses[-1]] += 1
        expected_summary = {"policy": policy,
                            "distinct_drawings": Counter(row["runs"][policy]["status"] for row in drawings.values()),
                            "history_count": len(histories), "all_prefixes": prefixes,
                            "history_final_status": final, "history_families": families,
                            "static_count": len(statics),
                            "static_status": Counter(drawings[(row["geometry_key"],)]["runs"][policy]["status"]
                                                      for row in statics.values())}
        require(summary == expected_summary, "policy/family summary differs: " + policy)
    return {"drawings": len(drawings), "histories": len(histories), "static_inputs": len(statics),
            "history_prefix_references": sum(len(row["prefix_keys"]) for row in histories.values()),
            "total_alias_references": sum(expected_aliases.values()), "independent_checks": checks,
            "all_mappings_and_summaries_consistent": True}


def compare_success(pairs):
    """A success gain and a regression are counted independently, never netted."""
    counts = Counter()
    for before, after in pairs:
        counts["both_solved" if before and after else "improved" if after
               else "regressed" if before else "neither_solved"] += 1
    return {name: counts[name] for name in ("improved", "regressed", "both_solved", "neither_solved")}


def compare_closed(report):
    """Compare the tie-only proposal to the unchanged segment constraint rule."""
    rows = {row["key"]: row for row in report["drawings"]}
    saved = {(row["policy"], row["key"]): row for row in report["history_results"]}
    baseline, proposed = "segment-constraints", "closed-support"
    drawing_pairs = [(row["runs"][baseline]["status"] == "solved",
                      row["runs"][proposed]["status"] == "solved") for row in rows.values()]
    return {"baseline": baseline, "proposal": proposed,
            "distinct_drawings": compare_success(drawing_pairs),
            "history_all_prefixes": compare_success((saved[(baseline, row["key"])]["all_prefixes_solved"],
                                                      saved[(proposed, row["key"])]["all_prefixes_solved"])
                                                     for row in report["histories"]),
            "history_final": compare_success((saved[(baseline, row["key"])]["final_status"] == "solved",
                                               saved[(proposed, row["key"])]["final_status"] == "solved")
                                              for row in report["histories"]),
            "static_inputs": compare_success((rows[row["geometry_key"]]["runs"][baseline]["status"] == "solved",
                                               rows[row["geometry_key"]]["runs"][proposed]["status"] == "solved")
                                              for row in report["static_inputs"]),
            "domains_differ": sum(row["runs"][baseline]["domains"] != row["runs"][proposed]["domains"]
                                    for row in rows.values()),
            "anchors_differ": sum(row["runs"][baseline]["anchors_by_dart"] != row["runs"][proposed]["anchors_by_dart"]
                                    for row in rows.values()),
            "warning": "Trace hashes differ when priority/closed-support metadata differ; that alone is not an ordering change."}


def bounded_ordering_replays(report):
    """Rebuild named small witnesses and compare actual commitment sequences."""
    from fourcolor.global_restart import restart_line_names

    histories = {row["key"]: row for row in report["histories"]}
    drawings = {row["key"]: row for row in report["drawings"]}
    outcomes = {(row["policy"], row["key"]): row for row in report["history_results"]}
    requested = [("guillotine-20260908", 7), ("guillotine-20260943", 4)]
    seed_summary = {}
    for history_key in ("guillotine-20260908", "guillotine-20260943"):
        seed_summary[history_key] = {}
        for policy in ("segment-constraints", "closed-support"):
            result = outcomes[(policy, history_key)]
            seed_summary[history_key][policy] = {
                "first_failed_prefix": result["first_failed_prefix"],
                "final_status": result["final_status"], "all_prefixes_solved": result["all_prefixes_solved"],
            }
            if history_key == "guillotine-20260908" and result["first_failed_prefix"] is not None:
                requested.append((history_key, result["first_failed_prefix"]))
    # If the hand-picked prefixes happen to have identical orders, this one
    # predetermined first saved status disagreement supplies another small check.
    changed = next((row for row in report["drawings"]
                    if row["runs"]["segment-constraints"]["status"] != row["runs"]["closed-support"]["status"]), None)
    cases = {}
    for history_key, step in requested:
        key = histories[history_key]["prefix_keys"][step]
        cases.setdefault(key, {"key": key, "document": drawings[key]["document"], "references": []})
        cases[key]["references"].append({"history": history_key, "prefix": step})
    if changed is not None:
        cases.setdefault(changed["key"], {"key": changed["key"], "document": changed["document"],
                                           "references": [{"selection": "first_saved_status_disagreement"}]})
    process = subprocess.run(["node", str(ROOT / "scripts/restart-geometry.mjs")], cwd=ROOT,
                             input=json.dumps({"cases": list(cases.values())}), capture_output=True,
                             text=True, encoding="utf-8", check=True)
    exported = json.loads(process.stdout)["results"]
    require([row["key"] for row in exported] == list(cases), "bounded geometry order changed")
    witnesses = []
    for item in exported:
        require(item["status"] == "geometry_ok", "bounded witness geometry failed")
        record = drawings[item["key"]]
        require(digest(item["geometry"]) == record["geometry_sha256"], "replayed geometry hash changed")
        runs = {policy: restart_line_names(item["geometry"], policy)
                for policy in ("segment-constraints", "closed-support")}
        for policy, run in runs.items():
            saved = record["runs"][policy]
            require(digest(run["trace"]) == saved["trace_sha256"], "bounded trace hash differs from full report")
            require(run["status"] == saved["status"] and run["domains"] == saved["domains"],
                    "bounded replay result changed")
        # Exclude priority tuple/metadata fields: only actual commitments matter.
        sequences = {policy: [(row["unit"], row["dart"], row["symbol"]) for row in run["trace"]]
                     for policy, run in runs.items()}
        first, second = sequences["segment-constraints"], sequences["closed-support"]
        divergence = next((step for step in range(max(len(first), len(second)))
                           if (first[step] if step < len(first) else None)
                           != (second[step] if step < len(second) else None)), None)
        first_difference = None
        if divergence is not None:
            first_difference = {"choice_index_one_based": divergence + 1}
            for policy, run in runs.items():
                trace = run["trace"]
                first_difference[policy] = trace[divergence] if divergence < len(trace) else None
        witnesses.append({"geometry_key": item["key"], "references": cases[item["key"]]["references"],
                          "statuses": {policy: run["status"] for policy, run in runs.items()},
                          "selection_sequences_differ": divergence is not None,
                          "trace_hashes_match_saved_full_run": True,
                          "first_actual_choice_difference": first_difference})
    return {"seed_history_results": seed_summary, "bounded_replayed_drawings": len(witnesses),
            "drawings_with_actual_choice_changes": sum(row["selection_sequences_differ"] for row in witnesses),
            "witnesses": witnesses}


def build_audit(input_path, previous_path):
    """Validate sources and previous controls before reporting new comparisons."""
    latest, input_info = read_report(input_path)
    previous, previous_info = read_report(previous_path)
    require(latest["smoke_limit"] is None and previous["smoke_limit"] is None, "full reports required")
    for filename, expected in latest["source_sha256"].items():
        path = (ROOT / filename).resolve()
        require(path.is_relative_to(ROOT.resolve()), "source path leaves repository")
        require(sha256(path.read_bytes()).hexdigest() == expected, "source hash changed: " + filename)
    checked = verify_mappings_and_summaries(latest)
    require(previous["histories"] == latest["histories"] and previous["static_inputs"] == latest["static_inputs"],
            "old and new reports have different source mappings")
    old = index(previous["drawings"], ("key",))
    new = index(latest["drawings"], ("key",))
    require(set(old) == set(new), "old and new geometry inventories differ")
    old_policies = [row["policy"] for row in previous["summary"]]
    require(old_policies == ["whole-constraints", "segment-constraints", "shared-mother"], "unexpected previous controls")
    for key, before in old.items():
        after = new[key]
        for field in ("document", "aliases", "geometry_status", "geometry_sha256"):
            require(before[field] == after[field], "old geometry/provenance changed: " + field)
        for policy in old_policies:
            require(before["runs"][policy] == after["runs"][policy], "old-policy compact result changed: " + policy)
    return {"schema_version": 1, "input": input_info, "previous_report": previous_info,
            "audit_script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "current_source_validation": {"sources_checked": len(latest["source_sha256"]), "all_match": True},
            "mapping_and_summary_checks": checked,
            "unchanged_previous_policies": {"policies": old_policies, "geometries": len(old),
                                            "compact_results_compared": len(old) * len(old_policies),
                                            "all_identical_including_status_domains_anchors_trace_hash": True},
            "policy_summaries": latest["summary"], "closed_vs_segment": compare_closed(latest),
            "ordering_witnesses": bounded_ordering_replays(latest),
            "limits": ["Saved-report audit plus bounded exact trace replays, not another full corpus run.",
                       "Related prefixes are not independent statistical samples; four remains the input palette.",
                       "Success gains and regressions are both retained; a changed ordering is not itself an improvement."]}


def main():
    """Exclusive output only; preserve every older research report."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "outputs/global-restart-all-2026-09-18-v2.json.gz")
    parser.add_argument("--previous", type=Path, default=ROOT / "outputs/global-restart-all-2026-09-18.json.gz")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/global-restart-audit-2026-09-18.json")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; choose a new filename")
    audit = build_audit(args.input, args.previous)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(audit, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"output": args.output.name, "source_validation": audit["current_source_validation"],
                      "mappings": audit["mapping_and_summary_checks"],
                      "closed_vs_segment": audit["closed_vs_segment"],
                      "seed_history_results": audit["ordering_witnesses"]["seed_history_results"],
                      "bounded_actual_order_changes": audit["ordering_witnesses"]["drawings_with_actual_choice_changes"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

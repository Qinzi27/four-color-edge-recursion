"""Independently check saved corpus reports and emit a compact evidence summary.

This script reads JSON or gzip JSON and never reruns a naming method. It checks
state/certificate bookkeeping, current source hashes and the old four policies'
unchanged results. Event display compaction is not confused with state changes.
Use a new --output path: all previous reports and summaries remain untouched.
"""

from argparse import ArgumentParser
from collections import Counter
from hashlib import sha256
import gzip
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "outputs/current-names-all-2026-09-18-v3.json.gz"
DEFAULT_PREVIOUS = ROOT / "outputs/current-names-all-2026-09-18.json"
DEFAULT_OUTPUT = ROOT / "outputs/current-names-summary-2026-09-18.json"


def require(condition, message):
    """Fail closed rather than publish an unchecked summary."""
    if not condition:
        raise AssertionError(message)


def digest(value):
    """Match the producer's state hashing, independently of its imports."""
    return sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def read_report(path):
    """Hash exact source bytes and decode an ordinary or gzip JSON report."""
    raw = path.read_bytes()
    payload = gzip.decompress(raw) if path.suffix == ".gz" else raw
    return json.loads(payload), {"filename": path.name, "sha256": sha256(raw).hexdigest(),
                                 "bytes": len(raw), "decoded_bytes": len(payload)}


def keyed(rows, fields):
    """Build an index while rejecting duplicate certificate or history keys."""
    result = {tuple(row[field] for field in fields): row for row in rows}
    require(len(result) == len(rows), "duplicate keys: " + ",".join(fields))
    return result


def verify_bookkeeping(report):
    """Check all saved runs, state hashes, certificates, and displayed counts.

    This is an independent report audit, not a rerun of Node geometric checking.
    Certificates state what the producer verified; their identities and hashes
    are cross-linked here to every legal initial and committed state.
    """
    histories = keyed(report["corpus"]["histories"], ("key",))
    runs = keyed(report["runs"], ("policy", "history_sha256"))
    certificates = keyed(report["independent_name_certificates"], ("key",))
    expected_certificates = set()
    submitted, initials, unsupported_starts = 0, 0, 0
    for run in runs.values():
        history = histories[(run["key"],)]
        require(run["history_sha256"] == history["history_sha256"], "history hash differs")
        require(run["aliases"] == history["aliases"], "history source aliases differ")
        require(run["planned_steps"] == len(history["paths"]), "planned steps differ")
        if history["initial_state"] is None:
            require(run["status"] == "outside_scope" and run["final_state"] is None
                    and run["steps"] == [] and run["committed_steps"] == 0,
                    "unsupported precolored seed was not preserved")
            unsupported_starts += 1
            continue
        stem = run["policy"] + "/" + run["key"]
        initial_key = (stem + "/initial",)
        previous_hash = digest(history["initial_state"])
        require(certificates[initial_key]["state_sha256"] == previous_hash,
                "initial certificate differs from the supplied start")
        expected_certificates.add(initial_key)
        initials += 1
        committed = sum(step["status"] == "split" for step in run["steps"])
        require(committed == run["committed_steps"], "committed step count differs")
        complete = committed == run["planned_steps"]
        require((run["status"] == "completed") == complete, "completion status differs")
        require(len(run["steps"]) == committed + (not complete), "history did not stop at first failure")
        for number, step in enumerate(run["steps"], 1):
            require(step["step"] == number, "step numbering differs")
            if step["status"] == "split":
                key = (stem + "/" + str(number),)
                require(certificates[key]["state_sha256"] == step["state_sha256"],
                        "step and independent certificate state hashes differ")
                previous_hash = step["state_sha256"]
                expected_certificates.add(key)
                submitted += 1
            else:
                require(number == len(run["steps"]) and step["status"] == run["status"]
                        and "state_sha256" not in step, "uncommitted draft was treated as committed")
        require(digest(run["final_state"]) == previous_hash, "final state hash differs")
        require(run["final_state"]["cuts"] == history["initial_state"]["cuts"] + history["paths"][:committed],
                "final geometry is not exactly the committed path prefix")
        require(all(type(side["symbol"]) is int and 1 <= side["symbol"] <= 4
                    for side in run["final_state"]["sides"]), "invalid committed palette")
    require(expected_certificates == set(certificates), "missing or extra state certificates")
    require(all(row["python_status"] == "consistent" for row in certificates.values()),
            "an independent line-name certificate is inconsistent")
    for group in report["groups"]:
        selected = [run for run in runs.values() if run["policy"] == group["policy"]]
        require(group["histories"] == len(selected) == len(histories), "policy history coverage differs")
        require(group["outcomes"] == dict(Counter(run["status"] for run in selected)), "outcome totals differ")
        require(group["committed_splits"] == sum(run["committed_steps"] for run in selected), "split totals differ")
        require({row["family"] for row in group["families"]} == {run["family"] for run in selected},
                "family coverage differs")
        for family in group["families"]:
            subset = [run for run in selected if run["family"] == family["family"]]
            require(family["histories"] == len(subset), "family size differs")
            require(family["outcomes"] == dict(Counter(run["status"] for run in subset)), "family outcomes differ")
            require(family["reasons"] == dict(Counter(run["reason"] for run in subset if run["reason"])),
                    "family reason counts differ")
    statics = report["static_topology_checks"]
    require([row["key"] for row in statics] == [row["key"] for row in report["corpus"]["static_inventory"]],
            "static topology inventory coverage differs")
    require(all(row["topology_checked"] and row["naming_claim"] is False for row in statics),
            "static topology was represented as successful coloring")
    return {"runs_checked": len(runs), "committed_step_hashes_checked": submitted,
            "initial_certificates_checked": initials, "name_certificates_checked": len(certificates),
            "unsupported_precolored_starts_preserved": unsupported_starts,
            "static_topologies_checked": len(statics), "static_naming_success_claims": 0,
            "all_group_and_family_counts_agree": True}


def old_policy_equivalence(previous, latest):
    """Compare algorithmic states, excluding intentionally compacted event prose."""
    old = keyed(previous["runs"], ("policy", "history_sha256"))
    new = keyed(latest["runs"], ("policy", "history_sha256"))
    old_policies = {policy["key"] for policy in previous["policies"]}
    require(len(old_policies) == 4, "the previous report must contain exactly the old four policies")
    require(previous["corpus"] == latest["corpus"], "input corpus or corpus source hashes changed")
    for key, before in old.items():
        after = new[key]
        for field in ("key", "status", "reason", "committed_steps", "planned_steps", "max_old_sides",
                      "old_side_change_events", "pending_path"):
            require(before.get(field) == after.get(field), "old-policy result changed: " + str(key) + "/" + field)
        require(digest(before["final_state"]) == digest(after["final_state"]), "old-policy final state changed")
        signature = lambda run: [(step["step"], step["status"], step.get("state_sha256")) for step in run["steps"]]
        require(signature(before) == signature(after), "old-policy state/status sequence changed")
    old_certificates = previous["independent_name_certificates"]
    new_certificates = [row for row in latest["independent_name_certificates"]
                        if row["key"].split("/", 1)[0] in old_policies]
    require(old_certificates == new_certificates, "old-policy independent certificates changed")
    require(previous["static_topology_checks"] == latest["static_topology_checks"], "static topology checks changed")
    require(previous["groups"] == [group for group in latest["groups"] if group["policy"] in old_policies],
            "old-policy summaries changed")
    return {"old_policy_count": 4, "matched_runs": len(old),
            "matched_step_state_hashes": sum(run["committed_steps"] for run in old.values()),
            "matched_name_certificates": len(old_certificates),
            "matched_static_topologies": len(previous["static_topology_checks"]),
            "all_algorithmic_results_unchanged": True,
            "events": "Verbose incidence/profile records were compacted; event JSON byte equality is not required."}


def comparison(report, before_policy, after_policy):
    """Separate deeper progress, completed histories, and local repair counts."""
    before = {run["history_sha256"]: run for run in report["runs"] if run["policy"] == before_policy}
    after = {run["history_sha256"]: run for run in report["runs"] if run["policy"] == after_policy}
    require(set(before) == set(after), "comparison input histories differ")
    deltas = [after[key]["committed_steps"] - run["committed_steps"] for key, run in before.items()]
    earlier = [after[key]["key"] for key, run in before.items()
               if after[key]["committed_steps"] < run["committed_steps"]]
    lost = [after[key]["key"] for key, run in before.items()
            if run["status"] == "completed" and after[key]["status"] != "completed"]
    require(not earlier and not lost, "declared refinement regressed on a saved history")
    newly_completed = [after[key]["key"] for key, run in before.items()
                       if run["status"] != "completed" and after[key]["status"] == "completed"]
    return {"before_policy": before_policy, "after_policy": after_policy, "matched_histories": len(before),
            "further": sum(delta > 0 for delta in deltas), "equal_depth": sum(delta == 0 for delta in deltas),
            "earlier": 0, "additional_committed_splits": sum(deltas),
            "old_complete_now_not": [], "newly_completed_count": len(newly_completed),
            "newly_completed_keys": newly_completed, "no_earlier_stop_verified": True}


def repair_summary(report, policy):
    """Count successful repair events separately from full-history completion."""
    rows = [run for run in report["runs"] if run["policy"] == policy]
    success_steps = [step for run in rows for step in run["steps"] if step["status"] == "split"]

    def shared(run):
        return any(step["status"] == "split" and step["event"].get("method") == "shared_interface_release"
                   for step in run["steps"])

    return {"policy": policy, "successful_step_methods": dict(Counter(step["event"].get("method")
                                                                       for step in success_steps)),
            "successful_shared_interface_repairs": sum(step["event"].get("method") == "shared_interface_release"
                                                         for step in success_steps),
            "histories_with_successful_shared_interface_repair": sum(shared(run) for run in rows),
            "completed_histories_with_shared_interface_repair": sum(shared(run) and run["status"] == "completed"
                                                                      for run in rows),
            "all_successful_old_side_repair_events": sum(step["event"].get("changed_old_count", 0) > 0
                                                          for step in success_steps),
            "completed_histories_total": sum(run["status"] == "completed" for run in rows)}


def build_summary(input_path, previous_path):
    """Load immutable evidence, perform checks, and return a compact summary."""
    latest, input_info = read_report(input_path)
    previous, previous_info = read_report(previous_path)
    for filename, expected in latest["source_sha256"].items():
        path = (ROOT / filename).resolve()
        require(path.is_relative_to(ROOT.resolve()), "source provenance path leaves repository")
        require(sha256(path.read_bytes()).hexdigest() == expected, "current source hash differs: " + filename)
    latest_checks = verify_bookkeeping(latest)
    previous_checks = verify_bookkeeping(previous)
    equivalence = old_policy_equivalence(previous, latest)
    comparisons = [comparison(latest, first, second) for first, second in (
        ("legacy-b3", "interface-b3"), ("release-b3", "interface-b3"),
        ("release-b32-control", "interface-b32-control"))]
    blocked = [run for run in latest["runs"] if run["policy"] == "interface-b3" and run["status"] == "blocked"]
    raw_reasons = Counter(run["reason"] for run in blocked)
    categories = {"local_budget_exceeded": "budget", "boundary_phase_conflict": "phase",
                  "odd_cycle_in_patch": "odd_cycle", "no_safe_shared_interface_release": "no_safe_interface_release"}
    aggregate = Counter()
    for reason, count in raw_reasons.items():
        base_reason = reason.removeprefix("after_shared_release/")
        require(base_reason in categories, "unclassified latest failure reason: " + reason)
        aggregate[categories[base_reason]] += count
    require(sum(aggregate.values()) == len(blocked), "failure categories are not exhaustive")
    old_source_changes = [name for name, value in previous["source_sha256"].items()
                          if latest["source_sha256"].get(name) != value]
    new_sources = sorted(set(latest["source_sha256"]) - set(previous["source_sha256"]))
    return {"schema_version": 1, "input": input_info, "previous_report": previous_info,
            "summarizer_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "source_validation": {"all_current_source_hashes_match": True,
                                  "checked_sources": len(latest["source_sha256"]),
                                  "changed_since_previous": old_source_changes,
                                  "newly_recorded_sources": new_sources},
            "corpus_counts": latest["corpus"]["summary"],
            "latest_report_checks": latest_checks, "previous_report_checks": previous_checks,
            "old_four_policy_equivalence": equivalence,
            "policy_and_family_counts": latest["groups"], "matched_refinement_comparisons": comparisons,
            "interface_b3_failures": {"blocked_histories": len(blocked), "raw_reasons": dict(raw_reasons),
                                       "exhaustive_categories": dict(aggregate),
                                       "category_rule": "after_shared_release/local_budget_exceeded counts once as budget."},
            "repair_events_not_completion_counts": [repair_summary(latest, policy)
                                                     for policy in ("interface-b3", "interface-b32-control")],
            "limits": ["This is a report/hash audit, not another independent execution of the coloring algorithm.",
                       "302 static topology certificates make zero naming-success claims.",
                       "Histories, aliases, unique drawings, successful local repairs and completed histories are different counts.",
                       "Finite exploratory input coverage does not establish a universal proof or statistical generalization."]}


def main():
    """Write one new portable summary; refuse any existing destination."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--previous", type=Path, default=DEFAULT_PREVIOUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; choose a new filename")
    result = build_summary(args.input, args.previous)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"output": args.output.name, "source_validation": result["source_validation"],
                      "old_four_policy_equivalence": result["old_four_policy_equivalence"],
                      "latest_report_checks": result["latest_report_checks"],
                      "comparisons": result["matched_refinement_comparisons"],
                      "failure_categories": result["interface_b3_failures"]["exhaustive_categories"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

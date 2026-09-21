"""Audit a separately named forest-then-single-Kempe continuous policy.

The geometric constraints are reconstructed independently from each actual
snapshot. Exact endpoint solvers are read-only auditors and never select a
policy action. Frozen controls are compared before the first divergence.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import io
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.apex_triangle_cost import apex_triangle_cost_table
from fourcolor.kempe_history_policy import replay_kempe_history
from fourcolor.recoloring_boundary import recoloring_boundary_table
from fourcolor.triangle_chain_family import build_staggered_strip
from scripts.validate_recoloring_obstructions import audit_quotient
from scripts.validate_triangle_chain_replay import (
    PARAMETERS, audit_kempe_candidates, audit_trace, compare_final_inherited,
    pending_problem, require, source_hashes, variants, verify_history,
)

CONTROL = "outputs/triangle-chain-replay-2026-09-21.json.gz"
CONTROL_SHA256 = "ddccbc32f6c97f63fbb6df88278396d590aa77fcdf53ed80bd02d96c64e2a678"
ADDED_SOURCES = (
    "fourcolor/kempe_history_policy.py", "tests/test_kempe_history_policy.py",
    "scripts/validate_kempe_history_continuation.py",
    "tests/test_kempe_history_continuation_validation.py",
)


def file_digest(path):
    """Hash large report bytes incrementally instead of copying them in memory."""
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hashes():
    """Bind the new policy to the exact earlier sources and comparison report."""
    return {**source_hashes(), **{name: file_digest(ROOT / name)
                                for name in (CONTROL,) + ADDED_SOURCES}}


def case_key(record):
    """Use explicit history parameters, never array position, to match controls."""
    return record["m"], record["inherit"], json.dumps(record["variant"], sort_keys=True)


def audit_control_prefix(record, control):
    """Require unchanged states and decisions before the old policy first stops."""
    require(control["status"] == "blocked", "control did not stop as specified")
    require(case_key(record) == case_key(control), "mismatched history control")
    require(len(record["trace"]) >= len(control["trace"]), "extension lost a valid prefix")
    for new, old in zip(record["trace"], control["trace"]):
        require(new["before"] == old["before"] and new["operation"] == old["operation"],
                "changed a pre-divergence input")
        if old["status"] == "split":
            require(new["after"] == old["after"] and new["method"] == old["method"],
                    "changed an old successful decision")
        else:
            require("repair_problem" in new, "missing explicit repair at the old stop")
    return {"passed": True, "unchanged_successful_prefix_length": len(control["trace"]) - 1,
            "first_new_repair_step": len(control["trace"])}


def audit_repair_geometry(family, entry):
    """Bind every literal Kempe input and committed target to independent boxes.

The core supplies real retained IDs. The oracle uses separately constructed
IDs sorted by coordinates; the bijection is checked before comparing edges,
colors, free daughters, and weights. A valid but unrelated graph is rejected.
"""
    expected, oracle_ids = pending_problem(entry["before"], entry["operation"], family["bounds"])
    problem = entry["repair_problem"]
    boxes = {key: tuple(box) for key, box in entry["repair_boxes"].items()}
    require(len(set(boxes.values())) == len(boxes) and set(boxes.values()) == set(oracle_ids),
            "repair boxes are not the actual pending geometry")
    require(len(problem["fixed"]) == 1, "repair must fix precisely the exterior")
    outside = problem["fixed"][0]
    require(set(problem["initial"]) == set(boxes) | {outside} and outside not in boxes,
            "repair side identities differ")
    actual_at = {box: key for key, box in boxes.items()}
    rename = {"r": outside, **{oracle_ids[box]: actual_at[box] for box in oracle_ids}}
    for field in ("initial", "weights"):
        require(problem[field] == {rename[v]: value for v, value in expected[field].items()},
                "repair literal colors or costs differ from actual parent")
    require(set(problem["daughters"]) == {rename[v] for v in expected["daughters"]},
            "repair free daughters differ")
    require({frozenset(edge) for edge in problem["edges"]}
            == {frozenset(rename[v] for v in edge) for edge in expected["edges"]},
            "repair graph differs from geometric adjacency")
    require(len(problem["edges"]) == len(expected["edges"]), "duplicate geometric edge")
    candidate_audit = audit_kempe_candidates(problem, entry["repair_result"])
    selected = entry["repair_result"]["selected"]
    if selected is None:
        require(entry["status"] == "blocked", "unwitnessed successful repair")
    else:
        require(entry["status"] == "split" and entry["method"] == "single_kempe_cost",
                "incorrect repair outcome label")
        after = {side["id"]: side for side in entry["after"]["rectangles"]}
        require(set(after) == set(boxes), "committed different repaired IDs")
        require(all(tuple(after[v]["bounds"]) == boxes[v]
                    and after[v]["color"] == selected["target"][v] for v in boxes),
                "committed state differs from audited Kempe target")
        require(entry["cost_old_changes"] == selected["changed_weight"], "commit cost differs")
    return {"passed": True, "independent_geometry_checked": True, "kempe": candidate_audit}


def exact_cost(problem):
    """A separate cost lower bound, computed only after the replay is complete."""
    quotient = apex_triangle_cost_table(problem["edges"], problem["initial"], problem["daughters"],
                                       apex=problem["fixed"][0], weights=problem["weights"])
    direct = recoloring_boundary_table(**problem) if len(problem["initial"]) <= 12 else None
    audit = audit_quotient(problem, quotient, direct)
    return {"quotient": quotient, "independent_audit": audit,
            "direct_boundary_table": direct, "used_to_select_policy_action": False}


def audit_history(family, record, control=None):
    """Audit every visit, every fallback, and the actual final-parent coloring."""
    verify_history(family, record["history"])
    record["trace_audit"] = audit_trace(family, record["history"], record)
    if control is not None:
        record["control_prefix_audit"] = audit_control_prefix(record, control)
    for entry in record["trace"]:
        if "repair_problem" not in entry:
            continue
        entry["repair_audit"] = audit_repair_geometry(family, entry)
        entry["endpoint_cost_audit"] = exact_cost(entry["repair_problem"])
        selected = entry["repair_result"]["selected"]
        if selected is not None:
            minimum = entry["endpoint_cost_audit"]["quotient"]["minimum_cost"]
            gap = selected["changed_weight"] - minimum
            require(gap >= 0, "witness violates independently checked lower bound")
            entry["selected_cost_minus_endpoint_minimum"] = gap
    record["final_initial_comparison"] = compare_final_inherited(family, record)
    if record["reached_final_parent"]:
        entry = record["trace"][-1]
        problem, _ = pending_problem(entry["before"], entry["operation"], family["bounds"])
        record["final_split_cost_audit"] = {"problem": problem, **exact_cost(problem)}
    return record


def summarize(rows):
    """Keep cumulative history cost distinct from the final cut's endpoint cost."""
    repairs = [entry for row in rows for entry in row["trace"] if "repair_problem" in entry]
    return {
        "histories": len(rows), "completed": sum(r["status"] == "completed" for r in rows),
        "reached_final_parent": sum(r["reached_final_parent"] for r in rows),
        "final_initial_matches_up_to_permutation": sum(
            r["final_initial_comparison"]["matches_up_to_permutation"] is True for r in rows),
        "fallback_attempts": len(repairs),
        "fallback_successes": sum(e["repair_result"]["selected"] is not None for e in repairs),
        "fallback_cost_minus_global_minimum": dict(sorted(Counter(
            e.get("selected_cost_minus_endpoint_minimum") for e in repairs).items())),
        "by_m": [{"m": m, "histories": len(subset),
                  "completed": sum(r["status"] == "completed" for r in subset),
                  "final_cut_minimum_costs": sorted({
                      r["final_split_cost_audit"]["quotient"]["minimum_cost"] for r in subset
                      if "final_split_cost_audit" in r}),
                  "final_cut_actual_costs": sorted({r["trace"][-1]["cost_old_changes"] for r in subset
                                                     if r["status"] == "completed"}),
                  "cumulative_history_cost_range": [min(r["cost_old_changes"] for r in subset),
                                                     max(r["cost_old_changes"] for r in subset)]}
                 for m in sorted({r["m"] for r in rows})
                 for subset in [[r for r in rows if r["m"] == m]]],
    }


def run_experiment():
    """Freeze sources, replay 128 cases, then apply independent read-only audits."""
    before = hashes()
    require(before[CONTROL] == CONTROL_SHA256, "frozen control report changed")
    with gzip.open(ROOT / CONTROL, "rt", encoding="utf-8") as stream:
        controls = json.load(stream)
    require(controls["input_and_source_sha256"] == source_hashes(), "control sources changed")
    index = {case_key(row): row for row in controls["histories"] if row["policy"] == "forest"}
    rows = []
    for m in PARAMETERS:
        family = build_staggered_strip(m)
        for variant in variants():
            for inherit in ("left", "right"):
                record = replay_kempe_history(family, inherit=inherit, **variant)
                rows.append(audit_history(family, record, index[case_key(record)]))
        print(json.dumps({"m": m, "histories_independently_audited": len(rows)}), flush=True)
    require(hashes() == before, "source changed during continuation experiment")
    return {"schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "all_passed": True, "python_version": platform.python_version(), "randomness": "none",
            "parameters": PARAMETERS, "variants": variants(), "histories": rows,
            "summary": summarize(rows), "input_and_source_sha256": before, "unchanged_at_end": True,
            "scope": "explicit new policy, eight parameters and eight geometric histories",
            "claims_not_made": ["old policies completed these histories", "all m tested",
                                "all guillotine histories covered", "a general Four Color algorithm",
                                "global optimality of cumulative cost", "literature originality"]}


def main():
    """Write an exclusive, reproducible gzip container or plain JSON report."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; choose a new filename")
    report = run_experiment()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as raw:
        if args.output.suffix == ".gz":
            with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
                with io.TextIOWrapper(compressed, encoding="utf-8", newline="\n") as text:
                    json.dump(report, text, ensure_ascii=False, indent=2)
                    text.write("\n")
        else:
            with io.TextIOWrapper(raw, encoding="utf-8", newline="\n") as text:
                json.dump(report, text, ensure_ascii=False, indent=2)
                text.write("\n")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

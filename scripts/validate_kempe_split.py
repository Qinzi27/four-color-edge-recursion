"""Compare cost-selected single Kempe swaps with the frozen C repair rule.

This is a first-blocked-state experiment, not a completed-history solver.
The production rule never sees the bounded all-target oracle. Existing files
are preserved, and input/source bytes are checked again before publication.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import platform
import sys
from time import perf_counter_ns

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.kempe_split import single_kempe_split
from scripts.validate_renaming import (
    all_assignments, audit_record, audit_xor, component_moves, first_post_swap,
)

ARCHIVE = "outputs/renaming-round-2026-09-18-v2.json"
PROFILES = "outputs/target-renaming-2026-09-18-v2.json"
ARCHIVE_SHA256 = "a9aba8d8d9fb2b579fb878dfee00f6e4c261a6c7d17cf85ccc84f98e2b8d29ce"
SOURCES = (
    "fourcolor/kempe_split.py", "fourcolor/target_renaming.py",
    "fourcolor/embedding.py", "scripts/validate_kempe_split.py",
    "scripts/validate_renaming.py", "scripts/rename-diagnostics.mjs",
    "tests/test_kempe_split.py", "tests/test_kempe_split_validation.py",
)


def require(condition, message):
    """Do not disable scientific checks when Python runs with -O."""
    if not condition:
        raise AssertionError(message)


def file_hashes(paths):
    """Use repository-relative paths only in public provenance."""
    return {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in paths}


def make_problem(row, checked):
    """Adapt rederived side identities, never greedy partial domains."""
    names = tuple(f"s{i}" for i in range(len(row["inherited"])))
    daughters = set(row["daughters"])
    outer = row["new_map"]["outerFace"]
    records = {name: [] for name in names}
    for edge_id in range(len(checked["new_plane"].edges)):
        for side in set(checked["new_plane"].shores(edge_id)):
            records[names[side]].append(f"e{edge_id}")
    return {
        "edges": [(names[u], names[v]) for u, adjacent in enumerate(checked["relaxed"])
                  for v in sorted(adjacent) if u < v],
        "initial": dict(zip(names, row["inherited"])),
        "daughters": [names[v] for v in row["daughters"]],
        "fixed": [names[outer]],
        "weights": {name: int(i not in daughters and i != outer)
                    for i, name in enumerate(names)},
        "records_by_side": records,
    }


def target_metrics(problem, target):
    """Count changed side classes and literal ordered line-record writes."""
    changed = [v for v in problem["initial"] if problem["initial"][v] != target[v]]
    records = {record for v in changed for record in problem["records_by_side"][v]}
    return {"changed_weight": sum(problem["weights"][v] for v in changed),
            "changed_side_count": len(changed), "changed_record_count": len(records)}


def audit_attempts(problem, attempts):
    """Validate all six positive/negative component certificates independently.

    Repeated edge scans compute a reachability fixed point, instead of using
    the production traversal or trusting its component and reason fields.
    """
    initial, children = problem["initial"], problem["daughters"]
    expected_keys = {(seed, tuple(sorted((initial[seed], b))))
                     for seed in children for b in range(4) if b != initial[seed]}
    require(len(attempts) == 6, "six attempts required")
    seen = set()
    for attempt in attempts:
        seed, pair = attempt["seed"], tuple(attempt["pair"])
        require(all(type(c) is int for c in pair), "invalid attempt colors")
        key = (seed, pair)
        require(key in expected_keys and key not in seen, "attempt key missing, duplicate or invalid")
        seen.add(key)
        reached = {seed}
        while True:
            grown = set(reached)
            for u, v in problem["edges"]:
                if initial[u] in pair and initial[v] in pair:
                    if u in reached:
                        grown.add(v)
                    if v in reached:
                        grown.add(u)
            if grown == reached:
                break
            reached = grown
        component = tuple(v for v in initial if v in reached)
        require(tuple(attempt["component"]) == component, "attempt component mismatch")
        hits = tuple(v for v in problem["fixed"] if v in reached)
        require(tuple(attempt["fixed_hits"]) == hits, "attempt fixed hits mismatch")
        other = children[1] if seed == children[0] else children[0]
        reasons = []
        if other in reached:
            reasons.append("contains_other_daughter")
        if hits:
            reasons.append("contains_fixed_side")
        require(tuple(attempt["blocked_reasons"]) == tuple(reasons), "attempt blocking reasons mismatch")
    require(seen == expected_keys, "attempt coverage mismatch")


def audit_candidate(problem, candidate):
    """Check a certificate through raw edges, connectedness and mixed states.

    This verifier does not call the new rule or its SCC planner. Saturation of
    the connected two-color set proves that it is a whole Kempe component.
    Both sides of an internal edge require each other, proving one atomic SCC.
    """
    initial, target = problem["initial"], candidate["target"]
    vertices, edges = tuple(initial), problem["edges"]
    require(set(target) == set(initial), "target identity mismatch")
    require(all(type(c) is int and c in range(4) for c in target.values()), "bad target color")
    component = tuple(candidate["component"])
    chosen = set(component)
    require(bool(chosen) and len(chosen) == len(component) and chosen <= set(vertices),
            "invalid component identities")
    pair = tuple(candidate["pair"])
    require(len(pair) == 2 and pair[0] < pair[1] and all(type(c) is int and c in range(4) for c in pair),
            "invalid color pair")
    require(all(initial[v] in pair for v in chosen), "component includes a third color")
    require(len(chosen & set(problem["daughters"])) == 1, "component does not separate daughters")
    require(candidate["seed"] in chosen & set(problem["daughters"]), "invalid candidate seed")
    require(not chosen & set(problem["fixed"]), "component touches a fixed side")
    adjacent = {v: set() for v in vertices}
    for u, v in edges:
        adjacent[u].add(v)
        adjacent[v].add(u)
        require(initial[u] != initial[v] and target[u] != target[v], "base-edge conflict")
    reached = {component[0]}
    while True:
        grown = reached | {w for v in reached for w in adjacent[v] if w in chosen}
        if grown == reached:
            break
        reached = grown
    require(reached == chosen, "component is disconnected")
    require(all(initial[w] not in pair for v in chosen for w in adjacent[v] - chosen),
            "partial rather than complete component")
    expected = {v: pair[0] ^ pair[1] ^ initial[v] if v in chosen else initial[v] for v in vertices}
    require(target == expected, "swap target or unchanged exterior mismatch")
    x, y = problem["daughters"]
    require(target[x] != target[y], "pending constraint still conflicts")
    metrics = target_metrics(problem, target)
    for key, value in metrics.items():
        require(candidate[key] == value, f"incorrect {key}")
    record_ids = {record for v in chosen for record in problem["records_by_side"][v]}
    require(set(candidate["changed_record_ids"]) == record_ids
            and len(candidate["changed_record_ids"]) == len(record_ids), "incorrect record union")
    expected_arcs = {(u, v) for u, v in edges if u in chosen and v in chosen}
    expected_arcs |= {(v, u) for u, v in tuple(expected_arcs)}
    require({tuple(arc) for arc in candidate["dependencies"]} == expected_arcs
            and len(candidate["dependencies"]) == len(expected_arcs),
            "incorrect dependencies")
    for key in ("components", "batches"):
        require(len(candidate[key]) == 1 and set(candidate[key][0]) == chosen
                and len(candidate[key][0]) == len(chosen), f"incorrect {key}")
    require(candidate["minimum_max_batch_size"] == len(chosen), "incorrect atomic size")
    require(candidate["minimum_max_batch_weight"] == metrics["changed_weight"], "incorrect atomic weight")
    return metrics


def selection_key(problem, candidate):
    """Independent declaration of the preselected lexicographic objective."""
    positions = {v: i for i, v in enumerate(problem["initial"])}
    metrics = target_metrics(problem, candidate["target"])
    return (metrics["changed_weight"], metrics["changed_side_count"], metrics["changed_record_count"],
            tuple(sorted(positions[v] for v in candidate["component"])), tuple(candidate["pair"]))


def check_global_targets(row, checked, old_profile, chosen):
    """Re-enumerate all <=10-side targets independently of the new selector."""
    actual = set(all_assignments(checked["new_adj"], row["new_map"]["outerFace"]))
    archived = {tuple(item["target"]) for item in old_profile["candidate_profiles"]}
    require(actual == archived and len(actual) == old_profile["targets"], "target oracle drift")
    daughters, outer = set(row["daughters"]), row["new_map"]["outerFace"]
    free_old = [i for i in range(len(row["inherited"])) if i not in daughters and i != outer]
    minimum = min(sum(target[i] != row["inherited"][i] for i in free_old) for target in actual)
    result = {"legal_targets": len(actual), "minimum_changed_old": minimum,
              "single_swap_status": "stalled" if chosen is None else "repaired",
              "selected_old_change_gap": None if chosen is None else chosen["changed_weight"] - minimum}
    if chosen is not None:
        target = tuple(chosen["target"][f"s{i}"] for i in range(len(row["inherited"])))
        require(target in actual and result["selected_old_change_gap"] >= 0, "invalid oracle comparison")
    return result


def run_experiment():
    """Audit all 160 archived first blocks; never sample only successful cases."""
    before = file_hashes((ARCHIVE, PROFILES) + SOURCES)
    require(before[ARCHIVE] == ARCHIVE_SHA256, "frozen repair input hash mismatch")
    source = json.loads((ROOT / ARCHIVE).read_text(encoding="utf-8"))
    profile_source = json.loads((ROOT / PROFILES).read_text(encoding="utf-8"))["target_profiles"]
    require(profile_source["source_sha256"] == before[ARCHIVE], "profile/input hash mismatch")
    profiles = {item["seed"]: item for item in profile_source["records"]}
    counts, records = Counter(), []
    sums = {label: Counter() for label in ("old_first", "cost_selected")}
    for row in source["records"]:
        checked = audit_record(row)
        problem = make_problem(row, checked)
        started = perf_counter_ns()
        result = single_kempe_split(**problem)
        elapsed = perf_counter_ns() - started
        names = tuple(problem["initial"])
        all_old = [colors for _pair, component, colors in component_moves(
            checked["relaxed"], tuple(row["inherited"]), row["new_map"]["outerFace"])
            if len(set(component) & set(row["daughters"])) == 1]
        new_targets = [tuple(c["target"][v] for v in names) for c in result["candidates"]]
        require(len(set(new_targets)) == len(new_targets) and set(new_targets) == set(all_old),
                "new candidate set disagrees with independent old component enumerator")
        audit_attempts(problem, result["attempts"])
        counts["attempt_certificates"] += len(result["attempts"])
        require(result["status"] == ("repaired" if all_old else "stalled"), "wrong result status")
        require(bool(all_old) == checked["C"], "single-swap applicability differs from frozen C")
        for candidate in result["candidates"]:
            audit_candidate(problem, candidate)
            colors = tuple(candidate["target"][v] for v in names)
            audit_xor(checked["new_plane"], colors)
            # Count actual changes to ordered two-shore records, including internal
            # swapped edges whose XOR difference itself remains unchanged.
            shores = checked["new_plane"].shores
            actual_records = {f"e{i}" for i in range(len(checked["new_plane"].edges))
                              if tuple(row["inherited"][v] for v in shores(i))
                              != tuple(colors[v] for v in shores(i))}
            require(actual_records == set(candidate["changed_record_ids"]), "literal record writes differ")
        require(result["candidates"] == sorted(result["candidates"], key=lambda c: selection_key(problem, c)),
                "candidate cost ordering differs")
        chosen = result["selected"]
        require(chosen == (result["candidates"][0] if all_old else None), "selected candidate differs")
        comparison = None
        if chosen is not None:
            old_colors = first_post_swap(checked["relaxed"], tuple(row["inherited"]),
                                        row["new_map"]["outerFace"], row["daughters"])
            require(old_colors == tuple(row["C"]["colors"]), "frozen first-match target differs")
            old_metrics = target_metrics(problem, dict(zip(names, old_colors)))
            new_metrics = target_metrics(problem, chosen["target"])
            comparison = {"old_first": old_metrics, "cost_selected": new_metrics,
                          "old_target": dict(zip(names, old_colors))}
            for metric in old_metrics:
                direction = "improved" if new_metrics[metric] < old_metrics[metric] else (
                    "worse" if new_metrics[metric] > old_metrics[metric] else "equal")
                counts[f"{metric}_{direction}"] += 1
            sums["old_first"].update(old_metrics)
            sums["cost_selected"].update(new_metrics)
        counts[result["status"]] += 1
        counts["candidates"] += len(result["candidates"])
        global_result = None
        if len(names) <= 10:
            global_result = check_global_targets(row, checked, profiles[row["seed"]], chosen)
            counts["global_oracle_maps"] += 1
            counts["global_oracle_targets"] += global_result["legal_targets"]
            gap = global_result["selected_old_change_gap"]
            counts["global_stalled" if gap is None else "global_optimal_old" if gap == 0 else "global_suboptimal_old"] += 1
        records.append({"seed": row["seed"], "new_sides": len(names), "problem": problem,
                        "result": result, "comparison": comparison, "global_target_oracle": global_result,
                        "core_elapsed_ns_descriptive_only": elapsed})
    require(counts["repaired"] == source["counts"]["C"] == 95 and counts["stalled"] == 65,
            "frozen C count mismatch")
    require(counts["global_oracle_maps"] == len(profiles) == 108, "oracle scope differs")
    # Explicit zeroes keep absent improvements/regressions distinguishable
    # from an unmeasured metric in the saved machine-readable summary.
    for metric in ("changed_weight", "changed_side_count", "changed_record_count"):
        for direction in ("improved", "equal", "worse"):
            counts.setdefault(f"{metric}_{direction}", 0)
    counts.setdefault("global_suboptimal_old", 0)
    after = file_hashes((ARCHIVE, PROFILES) + SOURCES)
    require(after == before, "source or input changed during experiment")
    return {"schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "python_version": platform.python_version(), "all_passed": True,
            "scope": "160 frozen first-blocked guillotine splits, not completed histories or v2/v4 repairs",
            "seeds": source["seed_range"], "randomness": "none; all archived records, no new sampling",
            "selection": ["changed unsplit old sides", "all changed side classes", "changed ordered line records",
                          "input-index component tuple", "color pair"],
            "oracle": "320 maps reconstructed; preexisting full-component enumeration; literal edges/records; all <=10-side targets",
            "counts": dict(sorted(counts.items())), "aggregate_costs_on_95_common_successes": sums,
            "latest_restart_failures": {"status": "not_applicable_missing_complete_inherited_coloring",
                                        "reason": "v2/v4 greedy partial domains are not legal H colorings with two daughters"},
            "not_implemented": ["multi-step Kempe search", "D-reducible configuration library",
                                "near-linear coloring algorithm", "browser integration"],
            "input_and_source_sha256": before, "unchanged_at_end": True, "records": records}


def write_new_report(report, destination):
    """Preserve every existing output, including failed-run reports."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    """Run the fixed experiment, with a unique default output filename."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = args.output or ROOT / "outputs" / f"kempe-split-{stamp}.json"
    if output.exists():
        parser.error("output exists; choose a new filename")
    report = run_experiment()
    write_new_report(report, output)
    print(json.dumps({"report": output.name, "counts": report["counts"],
                      "aggregate_costs": report["aggregate_costs_on_95_common_successes"]}, indent=2))


if __name__ == "__main__":
    main()

"""Diagnose frozen split repairs with bounded paths and conservative targets.

This research driver never changes the production naming rule. A complete
proper coloring of H precedes the pending daughter edge. Target feasibility,
Kempe reachability, and path cost are different questions and are reported
separately. All caps, failed searches, source hashes, and witnesses are retained.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from itertools import combinations, product
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.conservative_recoloring import find_budget_target
from fourcolor.kempe_reconfiguration import search_kempe_repairs
from scripts.validate_kempe_split import (
    ARCHIVE, ARCHIVE_SHA256, make_problem, require, target_metrics, write_new_report,
)
from scripts.validate_renaming import (
    all_assignments, audit_move, audit_record, audit_xor, component_moves,
)

BASELINE = "outputs/kempe-split-2026-09-20-v2.json"
SOURCES = (
    "fourcolor/conservative_recoloring.py", "fourcolor/kempe_reconfiguration.py",
    "fourcolor/target_renaming.py", "fourcolor/embedding.py", "fourcolor/kempe_split.py",
    "scripts/validate_renaming.py", "scripts/validate_kempe_split.py",
    "scripts/validate_kempe_progress.py", "tests/test_conservative_recoloring.py",
    "tests/test_kempe_reconfiguration.py", "tests/test_kempe_progress_validation.py",
)


def hashes():
    """Record repository-relative paths, without machine paths or private state."""
    return {name: sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (ARCHIVE, BASELINE) + SOURCES}


def degeneracy_certificate(problem):
    """Certify degeneracy by a peeling order and a matching induced core.

The order proves an upper bound. At the step where the maximum minimum
degree is attained, the remaining induced subgraph proves the lower bound.
"""
    names = tuple(problem["initial"])
    position = {v: i for i, v in enumerate(names)}
    adjacent = {v: set() for v in names}
    for u, v in problem["edges"]:
        adjacent[u].add(v)
        adjacent[v].add(u)
    remaining, order, degrees, bound, core = set(names), [], [], -1, ()
    while remaining:
        v = min(remaining, key=lambda v: (len(adjacent[v] & remaining), position[v]))
        degree = len(adjacent[v] & remaining)
        if degree > bound:
            bound, core = degree, tuple(v for v in names if v in remaining)
        order.append(v)
        degrees.append(degree)
        remaining.remove(v)
    # Independently rescan actual edges rather than trusting stored degrees.
    for i, v in enumerate(order):
        suffix = set(order[i + 1:])
        actual = sum((u == v and w in suffix) or (w == v and u in suffix)
                     for u, w in problem["edges"])
        require(actual == degrees[i] and actual <= bound, "bad peeling certificate")
    require(all(sum(w in core for w in adjacent[v]) >= bound for v in core),
            "bad degeneracy lower-bound core")
    return {"degeneracy": bound, "order": order, "later_degrees": degrees,
            "lower_bound_core": core, "four_color_connectivity_from_degeneracy": bound <= 3}


def literal_cost(plane, before, after):
    """Count changed ordered shore-pair records, not changed XOR labels."""
    return {f"e{i}" for i in range(len(plane.edges))
            if tuple(before[v] for v in plane.shores(i))
            != tuple(after[v] for v in plane.shores(i))}


def audit_path(row, checked, problem, result):
    """Replay each transition using the older independent move enumerator."""
    if result["status"] != "repaired":
        require(result["status"] in ("unknown", "unreachable"), "unknown search status")
        return None
    selected = result["selected"]
    require(selected is not None and result["shortest_steps_certified"], "missing path certificate")
    names = tuple(problem["initial"])
    index = {name: i for i, name in enumerate(names)}
    current = tuple(row["inherited"])
    outer = row["new_map"]["outerFace"]
    weight = tuple(problem["weights"][name] for name in names)
    cumulative_records = cumulative_weight = cumulative_sides = 0
    touched, changed_back = set(), set()
    for step in selected["steps"]:
        require(step["before"] == dict(zip(names, current)), "path before mismatch")
        after = tuple(step["after"][name] for name in names)
        members = tuple(index[v] for v in step["component"])
        audit_move(checked["relaxed"], current, outer, step["pair"], members, after)
        records = literal_cost(checked["new_plane"], current, after)
        changed = {i for i in range(len(names)) if current[i] != after[i]}
        cost = sum(weight[i] for i in changed)
        require(step["changed_weight"] == cost and step["changed_side_count"] == len(changed),
                "wrong step vertex cost")
        require(step["changed_record_count"] == len(records)
                and set(step["changed_record_ids"]) == records
                and len(step["changed_record_ids"]) == len(records), "wrong literal step record cost")
        touched.update(changed)
        cumulative_records += len(records)
        cumulative_weight += cost
        cumulative_sides += len(changed)
        current = after
    require(len(selected["steps"]) == result["shortest_steps"], "wrong shortest length")
    require(selected["target"] == dict(zip(names, current)), "final target mismatch")
    audit_xor(checked["new_plane"], current)
    metrics = target_metrics(problem, selected["target"])
    for key, value in metrics.items():
        require(selected["net_" + key] == value, "wrong net target cost")
    require(selected["cumulative_changed_record_count"] == cumulative_records,
            "wrong cumulative records")
    require(selected["cumulative_changed_weight"] == cumulative_weight,
            "wrong cumulative weight")
    require(selected["cumulative_changed_side_count"] == cumulative_sides,
            "wrong cumulative sides")
    net_records = literal_cost(checked["new_plane"], row["inherited"], current)
    require(set(selected["net_changed_record_ids"]) == net_records
            and len(selected["net_changed_record_ids"]) == len(net_records), "wrong net record identities")
    changed_back = {i for i in touched if current[i] == row["inherited"][i]}
    return {"replayed_steps": len(selected["steps"]),
            "temporarily_changed_then_restored_sides": [names[i] for i in sorted(changed_back)],
            "temporarily_changed_then_restored_old_sides":
                [names[i] for i in sorted(changed_back) if weight[i] > 0]}


def small_path_oracle(row, checked, problem, max_depth):
    """Use old integer-state moves to independently check shortest-layer cost.

Unlike the new core's API and certificate verifier, this oracle uses the
preexisting tuple-state enumerator and geometric record comparisons. It is
limited to ten side classes and is never consulted by either search core.
"""
    require(len(problem["initial"]) <= 10, "oracle limited to ten sides")
    start = tuple(row["inherited"])
    outer = row["new_map"]["outerFace"]
    x, y = row["daughters"]
    weights = tuple(problem["weights"].values())
    seen = {start}
    layer = {start: (0, 0)}
    sizes = [1]
    for depth in range(max_depth + 1):
        goals = {state: cost for state, cost in layer.items() if state[x] != state[y]}
        if goals:
            return {"status": "repaired", "shortest_steps": depth,
                    "target_layer_candidate_count": len(goals),
                    "best_cumulative_record_weight": min(goals.values()), "layers": sizes}
        if not layer:
            return {"status": "unreachable", "layers": sizes}
        if depth == max_depth:
            return {"status": "unknown", "layers": sizes}
        next_layer = {}
        for state, cost in layer.items():
            for _pair, component, target in component_moves(checked["relaxed"], state, outer):
                if target in seen:
                    continue
                candidate = (cost[0] + len(literal_cost(checked["new_plane"], state, target)),
                             cost[1] + sum(weights[v] for v in component))
                if target not in next_layer or candidate < next_layer[target]:
                    next_layer[target] = candidate
        seen.update(next_layer)
        layer = next_layer
        sizes.append(len(layer))
    raise AssertionError("unreachable loop exit")


def budget_profile(problem, max_budget, max_nodes):
    """Search ascending budgets; only exhaustive lower failures certify a minimum."""
    query = {key: problem[key] for key in ("edges", "initial", "daughters", "fixed", "weights")}
    attempts = []
    minimum = None
    for budget in range(max_budget + 1):
        result = find_budget_target(**query, max_changes=budget, max_nodes=max_nodes)
        attempts.append(result)
        if result["status"] == "found":
            target = result["target"]
            require(set(target) == set(problem["initial"]), "budget target identities differ")
            require(all(type(c) is int and c in range(4) for c in target.values()), "bad target color")
            require(all(target[v] == problem["initial"][v] for v in problem["fixed"]), "anchor changed")
            require(all(target[u] != target[v] for u, v in problem["edges"] + [problem["daughters"]]),
                    "budget target conflicts")
            metrics = target_metrics(problem, target)
            require(metrics["changed_weight"] == result["changed_weight"] <= budget, "wrong target cost")
            if all(item["status"] == "infeasible_budget" for item in attempts[:-1]):
                minimum = result["changed_weight"]
            break
    return {"minimum_old_side_changes": minimum, "minimum_certified": minimum is not None,
            "attempts": attempts, "target": attempts[-1]["target"]}


def independent_budget_lower_bound(problem, minimum):
    """Enumerate changed subsets below a claimed minimum, independently of DFS.

The frozen experiment has unit-weight old sides, two free daughters, and
fixed exterior. Explicitly enforce that scope: enumerate each cheaper old
subset, all three alternative colors on it, and all daughter colors. A
direct scan of G's edges then proves absence of a cheaper target. Together
with the already-replayed upper witness this certifies the exact minimum,
including examples too large for unrestricted 4^n target enumeration.
"""
    require(type(minimum) is int and minimum >= 0, "invalid lower bound")
    initial, weights = problem["initial"], problem["weights"]
    fixed, daughters = set(problem["fixed"]), tuple(problem["daughters"])
    require(not fixed.intersection(daughters), "oracle requires unfixed daughters")
    old = tuple(v for v in initial if v not in fixed and v not in daughters)
    require(all(weights[v] == 1 for v in old)
            and all(weights[v] == 0 for v in daughters), "oracle requires unit old-side costs")
    edges = tuple(problem["edges"]) + (daughters,)
    checked = 0
    for cost in range(minimum):
        for subset in combinations(old, cost):
            domains = [tuple(c for c in range(4) if c != initial[v]) for v in subset]
            domains += [range(4), range(4)]
            for values in product(*domains):
                target = dict(initial)
                target.update(zip(subset + daughters, values))
                checked += 1
                require(any(target[u] == target[v] for u, v in edges),
                        "cheaper target refutes claimed minimum")
    return {"scope": "unit-cost old sides, two free daughters, fixed exterior",
            "minimum_verified_with_upper_witness": minimum,
            "lower_budgets_exhausted": list(range(minimum)),
            "assignments_checked": checked}


def run_experiment(max_states=50000, max_depth=6, max_budget=4, max_nodes=200000):
    """Run one fixed bounded protocol on all 160 frozen snapshots."""
    before = hashes()
    require(before[ARCHIVE] == ARCHIVE_SHA256, "frozen input mismatch")
    source = json.loads((ROOT / ARCHIVE).read_text(encoding="utf-8"))
    baseline = json.loads((ROOT / BASELINE).read_text(encoding="utf-8"))
    prior = {item["seed"]: item for item in baseline["records"]}
    require(len(prior) == len(source["records"]) == 160, "unexpected archive coverage")
    counts, rows, path_lengths, min_costs, deg_stalled = Counter(), [], Counter(), Counter(), Counter()
    for ordinal, row in enumerate(source["records"], 1):
        checked = audit_record(row)
        problem = make_problem(row, checked)
        require(json.loads(json.dumps(problem)) == prior[row["seed"]]["problem"],
                "reconstructed problem differs from baseline")
        single = prior[row["seed"]]["result"]
        require(checked["C"] == (single["status"] == "repaired"), "single-step baseline differs")
        structure = degeneracy_certificate(problem)
        path = search_kempe_repairs(**problem, max_states=max_states, max_depth=max_depth)
        path_audit = audit_path(row, checked, problem, path)
        budget = budget_profile(problem, max_budget, max_nodes)
        lower_bound = (independent_budget_lower_bound(problem, budget["minimum_old_side_changes"])
                       if budget["minimum_certified"] else None)
        if lower_bound is not None:
            counts["independent_minimum_cost_cases"] += 1
            counts["independent_lower_cost_assignments"] += lower_bound["assignments_checked"]
        small = None
        if len(problem["initial"]) <= 10:
            targets = set(all_assignments(checked["new_adj"], row["new_map"]["outerFace"]))
            weights = tuple(problem["weights"].values())
            exact_min = min(sum(w for w, a, b in zip(weights, row["inherited"], target) if a != b)
                            for target in targets)
            require(not budget["minimum_certified"] or budget["minimum_old_side_changes"] == exact_min,
                    "budget search disagrees with independent target enumeration")
            for attempt in budget["attempts"]:
                if attempt["status"] == "infeasible_budget":
                    require(exact_min > attempt["max_changes"], "false budget infeasibility")
            oracle = small_path_oracle(row, checked, problem, max_depth)
            if path["status"] == "repaired":
                require(oracle["status"] == "repaired"
                        and path["shortest_steps"] == oracle["shortest_steps"]
                        and path["target_layer_candidate_count"] == oracle["target_layer_candidate_count"],
                        "shortest path layer differs from old enumerator")
                chosen = path["selected"]
                require((chosen["cumulative_changed_record_count"], chosen["cumulative_changed_weight"])
                        == oracle["best_cumulative_record_weight"], "shortest-layer minimum cost differs")
            elif path["status"] == "unreachable":
                require(oracle["status"] == "unreachable", "false unreachable assertion")
            small = {"legal_target_count": len(targets), "minimum_old_side_changes": exact_min,
                     "independent_path_oracle": oracle}
            counts["small_oracle_cases"] += 1
            counts["small_oracle_targets"] += len(targets)
        group = "single_stalled" if single["status"] == "stalled" else "single_repaired"
        counts[group] += 1
        counts[group + "_multistep_" + path["status"]] += 1
        counts[group + "_budget_minimum_certified"] += int(budget["minimum_certified"])
        if group == "single_stalled":
            deg_stalled[structure["degeneracy"]] += 1
            if path["status"] == "repaired":
                path_lengths[path["shortest_steps"]] += 1
                first_component = set(path["selected"]["steps"][0]["component"])
                counts["stalled_chosen_first_move_avoids_daughters"] += int(
                    not first_component.intersection(problem["daughters"]))
            if budget["minimum_certified"]:
                min_costs[budget["minimum_old_side_changes"]] += 1
        gap = None
        if path["status"] == "repaired":
            if budget["minimum_certified"]:
                gap = path["selected"]["net_changed_weight"] - budget["minimum_old_side_changes"]
                require(gap >= 0, "path beats supposedly minimum budget")
                counts[group + "_shortest_path_net_cost_above_minimum"] += int(gap > 0)
            counts[group + "_chosen_path_restores_old_sides"] += int(bool(
                path_audit["temporarily_changed_then_restored_old_sides"]))
        rows.append({"seed": row["seed"], "side_count": len(problem["initial"]),
                     "single_step_status": single["status"], "structure": structure,
                     "multistep": path, "path_audit": path_audit, "budget_profile": budget,
                     "independent_budget_lower_bound": lower_bound,
                     "chosen_path_net_old_cost_gap": gap, "small_oracle": small})
        if ordinal % 20 == 0:
            print(json.dumps({"progress": ordinal, "total": 160, "counts": dict(counts)}), flush=True)
    require(hashes() == before, "source/input changed during run")
    return {"schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "python_version": platform.python_version(), "all_passed": True,
            "scope": "160 frozen first-blocked guillotine splits; explicit research searches, not a production solver",
            "seed_range": source["seed_range"], "randomness": "none; no additional sampling",
            "limits": {"max_states": max_states, "max_depth": max_depth,
                       "max_old_side_changes": max_budget, "max_nodes_per_budget": max_nodes},
            "objectives": {"path": "fewest Kempe steps, then cumulative ordered-record writes, then cumulative old-side recolorings",
                           "target": "minimum net changed unsplit old sides, free daughters, fixed exterior"},
            "counts": dict(sorted(counts.items())),
            "stalled_shortest_step_distribution": dict(sorted(path_lengths.items())),
            "stalled_minimum_old_side_distribution": dict(sorted(min_costs.items())),
            "stalled_degeneracy_distribution": dict(sorted(deg_stalled.items())),
            "single_anchor_note": "single fixed exterior cannot itself obstruct existence of a Kempe repair to the permutation-invariant daughter-inequality goal; costs and length need not be preserved",
            "input_and_source_sha256": before, "unchanged_at_end": True, "records": rows}


def main():
    """Use unique outputs by default and reject accidental overwrites."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-states", type=int, default=50000)
    parser.add_argument("--max-depth", type=int, default=6)
    parser.add_argument("--max-budget", type=int, default=4)
    parser.add_argument("--max-nodes", type=int, default=200000)
    args = parser.parse_args()
    if args.max_states < 1 or args.max_depth < 0 or args.max_budget < 0 or args.max_nodes < 1:
        parser.error("invalid search cap")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = args.output or ROOT / "outputs" / f"kempe-progress-{stamp}.json"
    if output.exists():
        parser.error("output exists; choose a new filename")
    report = run_experiment(args.max_states, args.max_depth, args.max_budget, args.max_nodes)
    write_new_report(report, output)
    print(json.dumps({"report": output.name, "counts": report["counts"],
                      "steps": report["stalled_shortest_step_distribution"],
                      "net_cost": report["stalled_minimum_old_side_distribution"]}, indent=2))


if __name__ == "__main__":
    main()

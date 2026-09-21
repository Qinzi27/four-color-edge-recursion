"""Explain two cost-four splits and test declared constraint relaxations.

Original instances are reconstructed from their geometric archive. Deleting
constraints or side variables gives abstract relaxations, not automatically
another geometric split. A separately generated staggered rectangle family
has explicit geometry and cut-history certificates. Preserve this distinction.
"""

from argparse import ArgumentParser
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.apex_triangle_cost import apex_triangle_cost_table
from fourcolor.conservative_recoloring import find_budget_target
from fourcolor.kempe_split import single_kempe_split
from fourcolor.recoloring_boundary import recoloring_boundary_table
from fourcolor.triangle_chain_family import build_staggered_strip, verify_staggered_geometry
from scripts.validate_kempe_split import ARCHIVE, ARCHIVE_SHA256, make_problem, require, write_new_report
from scripts.validate_renaming import audit_record, audit_xor

BASELINE = "outputs/kempe-progress-2026-09-20-v2.json"
SEEDS = (20260926, 20260980)
FAMILY_PARAMETERS = tuple(range(1, 9)) + (16, 32, 64, 100)
SOURCES = (
    "fourcolor/apex_triangle_cost.py", "fourcolor/recoloring_boundary.py",
    "fourcolor/triangle_chain_family.py", "fourcolor/conservative_recoloring.py",
    "fourcolor/kempe_split.py",
    "fourcolor/target_renaming.py", "fourcolor/embedding.py",
    "scripts/validate_recoloring_obstructions.py", "scripts/validate_kempe_split.py",
    "scripts/validate_renaming.py", "tests/test_apex_triangle_cost.py",
    "tests/test_recoloring_boundary.py", "tests/test_triangle_chain_family.py",
    "tests/test_recoloring_obstructions_validation.py",
)


def hashes():
    """Capture relative source names and immutable input byte identities."""
    return {name: sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (ARCHIVE, BASELINE) + SOURCES}


def query(problem):
    """Drop record-write metadata: this experiment measures net side cost."""
    return {key: problem[key] for key in ("edges", "initial", "daughters", "fixed", "weights")}


def check_target(problem, target, expected_cost):
    """Check a witnessed upper bound by literal edges and initial colors."""
    require(set(target) == set(problem["initial"]), "target side identities differ")
    require(all(type(c) is int and c in range(4) for c in target.values()), "bad target color")
    require(all(target[v] == problem["initial"][v] for v in problem["fixed"]), "fixed side changed")
    require(all(target[u] != target[v] for u, v in list(problem["edges"]) + [problem["daughters"]]),
            "target violates constraint")
    cost = sum(problem["weights"][v] for v in target if target[v] != problem["initial"][v])
    require(cost == expected_cost, "target cost differs")


def audit_quotient(problem, quotient, table=None):
    """Reconstruct the certificate's equivalence relation from actual triangles.

This verifier uses set merging, not the core's union-find implementation.
Its cost tables remain tied to literal colors and the original assignment.
When supplied, the direct per-vertex boundary table supplies a second exact
count/cost oracle independent of equality compression.
"""
    apex = quotient["apex"]
    initial = problem["initial"]
    edges = {frozenset(e) for e in list(problem["edges"]) + [problem["daughters"]]}
    require(quotient["status"] == "exact", "incomplete quotient enumeration")
    require(problem["fixed"] == [apex], "certificate requires precisely one fixed apex")
    require(quotient["counts_complete"], "incomplete counts")
    require(quotient["initial"] == initial and quotient["weights"] == problem["weights"],
            "certificate initial state or costs differ")
    require(tuple(quotient["daughters"]) == tuple(problem["daughters"]), "daughter identities differ")
    require({frozenset(e) for e in quotient["base_edges"]}
            == {frozenset(e) for e in problem["edges"]}, "certificate base constraints differ")
    require(all(frozenset((apex, v)) in edges for v in initial if v != apex), "apex not universal")
    require(quotient["fixed_color"] == initial[apex], "wrong apex color")
    groups = [{v} for v in initial if v != apex]
    for witness in quotient["equality_witnesses"]:
        u, v = witness["shared_edge"]
        a, b = witness["opposite_vertices"]
        require(len({u, v, a, b}) == 4 and apex not in (u, v, a, b), "bad triangle identities")
        require(all(frozenset(e) in edges for e in ((u, v), (u, a), (v, a), (u, b), (v, b))),
                "equality is missing a triangle edge")
        left = next(group for group in groups if a in group)
        right = next(group for group in groups if b in group)
        if left is not right:
            left.update(right)
            groups.remove(right)
    actual_classes = {frozenset(group) for group in groups}
    require(len(quotient["classes"]) == len(actual_classes)
            and {frozenset(group) for group in quotient["classes"]} == actual_classes
            and sum(map(len, quotient["classes"])) == len(initial) - 1,
            "classes exceed witnessed equalities")
    class_of = {v: i for i, members in enumerate(quotient["classes"]) for v in members}
    require(class_of == quotient["class_of"], "incorrect class membership map")
    expected_edges = {tuple(sorted((class_of[u], class_of[v])))
                      for u, v in (tuple(e) for e in edges) if apex not in (u, v)}
    require(set(map(tuple, quotient["quotient_edges"])) == expected_edges, "quotient edge mismatch")
    palette = set(range(4)) - {initial[apex]}
    require(set(quotient["palette"]) == palette, "wrong palette")
    for i, members in enumerate(quotient["classes"]):
        for color in palette:
            expected = sum(problem["weights"][v] for v in members if initial[v] != color)
            # JSON round trips change integer dictionary keys to strings.
            costs = quotient["class_color_costs"][i]
            require(costs.get(color, costs.get(str(color))) == expected, "class cost mismatch")
    # The experiment only has tiny quotient graphs. A Cartesian-product oracle
    # avoids sharing the core's partial-assignment stack or counting logic.
    require(len(actual_classes) <= 10, "independent quotient oracle exceeds declared scope")
    expected_rows = {(a, b): [] for a in range(4) for b in range(4)}
    for assignment in product(sorted(palette), repeat=len(actual_classes)):
        if any(assignment[u] == assignment[v] for u, v in expected_edges):
            continue
        pair = tuple(assignment[class_of[v]] for v in problem["daughters"])
        cost = sum(problem["weights"][v] for v in initial if v != apex
                   and assignment[class_of[v]] != initial[v])
        expected_rows[pair].append(cost)
    require(len(quotient["rows"]) == 16 and
            {tuple(row["pair"]) for row in quotient["rows"]} == set(expected_rows),
            "boundary pairs must cover all sixteen assignments exactly once")
    for row in quotient["rows"]:
        costs = expected_rows[tuple(row["pair"])]
        minimum = min(costs) if costs else None
        require(row["status"] == ("exact" if costs else "infeasible")
                and row["counts_complete"], "wrong row status")
        require(row["target_count"] == len(costs)
                and row["optimal_target_count"] == (costs.count(minimum) if costs else 0),
                "wrong row target counts")
        require(row["minimum_cost"] == minimum and row["best_found_cost"] == minimum,
                "wrong exact row minimum")
        require((row["witness"] is not None) == bool(costs), "wrong row witness presence")
        if costs:
            require(tuple(row["witness"][v] for v in problem["daughters"]) == tuple(row["pair"]),
                    "row witness has different daughter colors")
    all_costs = [cost for costs in expected_rows.values() for cost in costs]
    require(quotient["target_count"] == len(all_costs)
            and quotient["minimum_cost"] == (min(all_costs) if all_costs else None)
            and quotient["best_found_cost"] == quotient["minimum_cost"], "wrong aggregate result")
    if table is not None:
        require(table["all_rows_complete"], "incomplete direct boundary table")
        direct = {tuple(row["colors"]): row for row in table["rows"]}
        for row in quotient["rows"]:
            other = direct[tuple(row["pair"])]
            for key in ("minimum_cost", "target_count", "optimal_target_count"):
                require(row[key] == other[key], f"quotient/direct boundary {key} mismatch")
    for row in quotient["rows"]:
        if row["witness"] is not None:
            check_target(problem, row["witness"], row["minimum_cost"])
    return {"verified_equalities": len(quotient["equality_witnesses"]),
            "interior_vertices": len(initial) - 1, "quotient_vertices": len(actual_classes),
            "direct_table_compared": table is not None}


def audit_family_kempe(family, result):
    """Check the literal two components without trusting the swap constructor.

    Reachability is rebuilt by repeatedly scanning induced edges. The reported
    minimum of one step follows from a valid swap and invalid zero-step target.
    """
    problem, m = family["problem"], family["m"]
    initial = problem["initial"]
    active = {v for v, color in initial.items() if color in (1, 3)}
    components = []
    while active:
        reached = {next(iter(active))}
        while True:
            extended = reached | {v for edge in problem["edges"] for v in edge
                                  if set(edge) & reached and all(initial[u] in (1, 3) for u in edge)}
            if extended == reached:
                break
            reached = extended
        active -= reached
        components.append(reached)
    require(len(components) == 2 and all(len(c) == 2 * m + 1 for c in components),
            "family must have exactly two specified-size Kempe components")
    require(result["status"] == "repaired" and len(result["candidates"]) == 2,
            "unexpected single-step repair candidates")
    require({frozenset(c["component"]) for c in result["candidates"]}
            == {frozenset(c) for c in components}, "reported components differ")
    for candidate in result["candidates"]:
        reached = set(candidate["component"])
        require(tuple(candidate["pair"]) == (1, 3)
                and len(reached & set(problem["daughters"])) == 1
                and not reached & set(problem["fixed"]), "illegal family swap component")
        target = {v: 4 - c if v in reached else c for v, c in initial.items()}
        require(target == candidate["target"], "candidate differs from literal 1/3 swap")
        require(candidate["changed_weight"] == 2 * m, "incorrect old-side swap cost")
        check_target(problem, target, 2 * m)
    require(initial[problem["daughters"][0]] == initial[problem["daughters"][1]],
            "zero steps must not already repair the pending constraint")
    return {"passed": True, "minimum_kempe_steps": 1,
            "minimum_old_side_changes": 2 * m, "component_size_including_daughter": 2 * m + 1}


def audit_family_certificate(family, quotient):
    """Bind the formula certificate to independently enumerated literal targets."""
    certificate, problem, m = family["certificate"], family["problem"], family["m"]
    require(certificate["old_side_count"] == sum(problem["weights"].values()) == 6 * m + 1,
            "wrong old-side count")
    require(certificate["minimum_old_cost"] == quotient["minimum_cost"] == 2 * m,
            "wrong formula minimum")
    require({frozenset(c) for c in certificate["modulo_classes"]}
            == {frozenset(c) for c in quotient["classes"]}, "wrong periodic classes")
    expected = {tuple(row["witness"][v] for v in problem["initial"])
                for row in quotient["rows"] if row["witness"] is not None}
    supplied = certificate["targets"]
    require(len(supplied) == 6 and len(expected) == 6, "wrong family target count")
    require({tuple(row["target"][v] for v in problem["initial"]) for row in supplied} == expected,
            "formula targets differ from the exact quotient")
    for row in supplied:
        check_target(problem, row["target"], row["changed_old_sides"])
        require(all(row["target"][v] == row["residue_colors"][i % 3]
                    for v, i in family["index_by_side"].items()), "wrong residue labels")
    return {"passed": True, "target_count": 6, "minimum_old_side_changes": 2 * m}


def remove_edge(problem, edge):
    """Relax one abstract old constraint; the pending edge stays separate."""
    result = deepcopy(query(problem))
    result["edges"] = [e for e in result["edges"] if set(e) != set(edge)]
    require(len(result["edges"]) == len(problem["edges"]) - 1, "edge not found uniquely")
    return result


def remove_old_vertex(problem, vertex):
    """Remove a priced old variable, never the anchor or either daughter."""
    require(vertex not in set(problem["fixed"]) | set(problem["daughters"]), "protected vertex")
    result = deepcopy(query(problem))
    result["initial"].pop(vertex)
    result["weights"].pop(vertex)
    result["edges"] = [e for e in result["edges"] if vertex not in e]
    return result


def diagnose(problem):
    """Cross-check an exact boundary minimum with a separate conflict search."""
    table = recoloring_boundary_table(**query(problem))
    require(table["all_rows_complete"], "variant boundary search exhausted its declared cap")
    minimum = table["minimum_cost"]
    require(minimum is not None, "relaxing a feasible input cannot destroy all targets")
    witness = next(row["witness"] for row in table["rows"] if row["minimum_cost"] == minimum)
    check_target(problem, witness, minimum)
    tests = {}
    for budget in ((minimum - 1, minimum) if minimum else (0,)):
        test = find_budget_target(**query(problem), max_changes=budget, max_nodes=200000)
        expected = "found" if budget == minimum else "infeasible_budget"
        require(test["status"] == expected, "independent budget algorithm disagrees")
        tests[str(budget)] = {"status": test["status"], "nodes": test["nodes"]}
    return {"minimum_cost": minimum, "target_count": sum(row["target_count"] for row in table["rows"]),
            "witness": witness, "boundary_nodes": sum(row["nodes"] for row in table["rows"]),
            "budget_crosscheck": tests}


def greedy_core(problem, cached, reverse=False, keep_apex=False):
    """Find an inclusion-minimal edge set, not a globally minimum-size one."""
    current = deepcopy(query(problem))
    initial_edges = list(current["edges"])
    order = list(reversed(initial_edges)) if reverse else initial_edges
    anchor = problem["fixed"][0]
    removed, decisions = [], []
    for edge in order:
        if keep_apex and anchor in edge:
            continue
        trial = remove_edge(current, edge)
        result = cached(trial)
        accepted = result["minimum_cost"] == 4
        decisions.append({"edge": edge, "trial_minimum": result["minimum_cost"], "removed": accepted})
        if accepted:
            current = trial
            removed.append(edge)
    critical = []
    for edge in current["edges"]:
        if keep_apex and anchor in edge:
            continue
        value = cached(remove_edge(current, edge))["minimum_cost"]
        require(value < 4, "greedy remainder is not inclusion-minimal")
        critical.append({"edge": edge, "minimum_after_deletion": value})
    return {"reverse": reverse, "keep_all_apex_edges": keep_apex,
            "problem": current, "removed_edges": removed,
            "decisions": decisions, "remaining_edge_count": len(current["edges"]),
            "remaining_edge_deletions": critical, "minimum_cost": cached(current)["minimum_cost"],
            "scope": "inclusion-minimal under stated removable edges; minimum cardinality not established"}


def run_experiment():
    """Run declared originals, all one-step relaxations, and ordered cores."""
    before = hashes()
    require(before[ARCHIVE] == ARCHIVE_SHA256, "frozen geometry hash mismatch")
    archive = json.loads((ROOT / ARCHIVE).read_text(encoding="utf-8"))
    prior = json.loads((ROOT / BASELINE).read_text(encoding="utf-8"))
    prior_by_seed = {row["seed"]: row for row in prior["records"]}
    records = []
    for seed in SEEDS:
        source = next(row for row in archive["records"] if row["seed"] == seed)
        checked = audit_record(source)
        problem = query(make_problem(source, checked))
        require(prior_by_seed[seed]["budget_profile"]["minimum_old_side_changes"] == 4,
                "wrong selected cost-four input")
        table = recoloring_boundary_table(**problem)
        quotient = apex_triangle_cost_table(problem["edges"], problem["initial"], problem["daughters"],
                                            apex=problem["fixed"][0], weights=problem["weights"])
        audit = audit_quotient(problem, quotient, table)
        for row in table["rows"]:
            if row["witness"] is not None:
                audit_xor(checked["new_plane"], tuple(row["witness"][v] for v in problem["initial"]))
        cache = {}

        def cached(candidate):
            """Reuse exact results only when the entire cost problem matches."""
            key = json.dumps(candidate, sort_keys=True)
            if key not in cache:
                cache[key] = diagnose(candidate)
            return cache[key]

        base = cached(problem)
        require(base["minimum_cost"] == 4, "original cost changed")
        edge_variants = [{"deleted_edge": edge, **cached(remove_edge(problem, edge))}
                         for edge in problem["edges"]]
        old = [v for v in problem["initial"] if v not in set(problem["fixed"]) | set(problem["daughters"])]
        vertex_variants = [{"deleted_old_side": v, **cached(remove_old_vertex(problem, v))} for v in old]
        require(all(row["minimum_cost"] <= 4 for row in edge_variants + vertex_variants),
                "constraint relaxation increased optimum")
        cores = [greedy_core(problem, cached, reverse, keep_apex)
                 for keep_apex in (False, True) for reverse in (False, True)]
        records.append({"seed": seed, "problem": problem, "boundary_table": table,
                        "apex_quotient": quotient, "certificate_audit": audit,
                        "single_edge_deletions": edge_variants,
                        "single_old_side_deletions": vertex_variants,
                        "single_edge_minimum_distribution": dict(sorted(Counter(
                            row["minimum_cost"] for row in edge_variants).items())),
                        "cores": cores, "distinct_cost_problems_checked": len(cache)})
        print(json.dumps({"seed": seed, "quotient_classes": len(quotient["classes"]),
                          "cost_problems_checked": len(cache), "minimum": base["minimum_cost"]}), flush=True)
    family_rows = []
    for parameter in FAMILY_PARAMETERS:
        family = build_staggered_strip(parameter)
        geometry = verify_staggered_geometry(family)
        problem = family["problem"]
        quotient = apex_triangle_cost_table(problem["edges"], problem["initial"], problem["daughters"],
                                            apex=problem["fixed"][0], weights=problem["weights"])
        direct = recoloring_boundary_table(**problem) if len(problem["initial"]) <= 12 else None
        audit = audit_quotient(problem, quotient, direct)
        require(quotient["minimum_cost"] == 2 * parameter and quotient["target_count"] == 6,
                "family formula disagrees with exact quotient")
        require(sorted(row["minimum_cost"] for row in quotient["rows"] if row["status"] == "exact")
                == sorted([2 * parameter] * 2 + [5 * parameter + 1] * 4), "family cost spectrum differs")
        kempe = single_kempe_split(**problem)
        kempe_audit = audit_family_kempe(family, kempe)
        formula_audit = audit_family_certificate(family, quotient)
        family_rows.append({"m": parameter, "family": family, "geometry_audit": geometry,
                            "quotient": quotient, "quotient_audit": audit,
                            "direct_boundary_table": direct, "single_kempe": kempe,
                            "single_kempe_audit": kempe_audit, "formula_audit": formula_audit})
    require(hashes() == before, "source/input changed during formal run")
    return {"schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "python_version": platform.python_version(), "all_passed": True,
            "scope": "two frozen cost-four snapshots; abstract constraint relaxations; separately certified guillotine rectangle family",
            "randomness": "none in formal experiment", "seeds": SEEDS,
            "family_parameters": FAMILY_PARAMETERS, "records": records, "family_records": family_rows,
            "input_and_source_sha256": before, "unchanged_at_end": True,
            "claims_not_made": ["originality in the literature", "new four-color theorem proof",
                                "family initial colors generated by old greedy strategy",
                                "deleted-constraint cores retain guillotine realization",
                                "greedy core has minimum possible cardinality"]}


def main():
    """Preserve earlier outputs; report names are unique unless explicitly set."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = args.output or ROOT / "outputs" / f"recoloring-obstructions-{stamp}.json"
    if output.exists():
        parser.error("output exists; choose a new filename")
    report = run_experiment()
    write_new_report(report, output)
    print(json.dumps({"report": output.name, "all_passed": report["all_passed"],
                      "family_minima": [[r["m"], r["quotient"]["minimum_cost"]]
                                         for r in report["family_records"]]}, indent=2))


if __name__ == "__main__":
    main()

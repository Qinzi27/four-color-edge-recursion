"""Replay fixed historical policies before diagnosing any blocked assignment.

Policies never receive an oracle target. Exact cost solvers run only after a
history has stopped, and cannot create evidence that its last state was reached.
All geometry is an affine copy of the previously certified rectangle family.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from itertools import permutations, product
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.apex_triangle_cost import apex_triangle_cost_table
from fourcolor.kempe_split import single_kempe_split
from fourcolor.recoloring_boundary import recoloring_boundary_table
from fourcolor.triangle_chain_family import build_staggered_strip, verify_staggered_geometry
from fourcolor.triangle_chain_replay import build_history_variant, replay_staggered_history
from scripts.validate_recoloring_obstructions import audit_quotient, check_target
from scripts.validate_kempe_split import audit_attempts

INPUT = "outputs/recoloring-obstructions-2026-09-21.json"
INPUT_SHA256 = "a1a10b9fab64565426744f022dfb6af7ea4d50eaa96726c2547bde44dd94598e"
PARAMETERS = tuple(range(1, 9))
SOURCES = (
    "fourcolor/triangle_chain_replay.py", "fourcolor/triangle_chain_family.py",
    "fourcolor/inherited_names.py", "fourcolor/retained_profiles.py",
    "fourcolor/anchor_forest.py", "fourcolor/strip_chain.py",
    "fourcolor/apex_triangle_cost.py", "fourcolor/recoloring_boundary.py",
    "fourcolor/kempe_split.py", "fourcolor/target_renaming.py",
    "fourcolor/conservative_recoloring.py", "fourcolor/embedding.py",
    "web/construction.js", "web/engine.js",
    "scripts/replay_triangle_chain_web.mjs", "scripts/validate_triangle_chain_replay.py",
    "scripts/validate_recoloring_obstructions.py", "scripts/validate_kempe_split.py",
    "scripts/validate_renaming.py", "tests/test_triangle_chain_replay.py",
    "tests/test_triangle_chain_replay_validation.py",
)


def require(condition, message):
    """Do not let optimized Python disable certificate checks."""
    if not condition:
        raise AssertionError(message)


def variants():
    """Eight predeclared histories: row order, isolation order, stroke direction."""
    return [{"row_order": row, "isolate_order": order,
             "horizontal_reverse": reverse, "vertical_reverse": reverse}
            for row, order, reverse in product(("lower_first", "upper_first"),
                                               ("left_to_right", "right_to_left"), (False, True))]


def shared(a, b):
    """Positive-length contact, independently computed from coordinate boxes."""
    return (((a[1] == b[0] or b[1] == a[0]) and min(a[3], b[3]) > max(a[2], b[2]))
            or ((a[3] == b[2] or b[3] == a[2]) and min(a[1], b[1]) > max(a[0], b[0])))


def snapshot_colors(snapshot, bounds):
    """Check tiling, stable identities, all true adjacencies, and fixed exterior."""
    require(snapshot["exterior_color"] == 0, "exterior moved")
    rectangles = snapshot["rectangles"]
    require(rectangles and len({r["id"] for r in rectangles}) == len(rectangles), "duplicate or empty IDs")
    colors = {tuple(r["bounds"]): r["color"] for r in rectangles}
    require(len(colors) == len(rectangles), "duplicate rectangle geometry")
    area = 0
    for box, color in colors.items():
        require(type(color) is int and color in range(4), "invalid literal color")
        require(len(box) == 4 and all(type(x) is int for x in box), "noninteger original geometry")
        require(bounds[0] <= box[0] < box[1] <= bounds[1]
                and bounds[2] <= box[2] < box[3] <= bounds[3], "rectangle outside frame")
        area += (box[1] - box[0]) * (box[3] - box[2])
        if box[0] == bounds[0] or box[1] == bounds[1] or box[2] == bounds[2] or box[3] == bounds[3]:
            require(color != 0, "rectangle conflicts with exterior")
    boxes = list(colors)
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            require(not (min(a[1], b[1]) > max(a[0], b[0])
                         and min(a[3], b[3]) > max(a[2], b[2])), "overlapping rectangles")
            if shared(a, b):
                require(colors[a] != colors[b], "improper geometric state")
    require(area == (bounds[1] - bounds[0]) * (bounds[3] - bounds[2]), "incomplete area")
    return colors


def split_boxes(operation):
    """Reconstruct daughters from a cut, without invoking any naming policy."""
    parent = tuple(operation["parent_bounds"])
    axis, at = operation["axis"], operation["at"]
    require(axis in ("x", "y"), "unknown split axis")
    index = 0 if axis == "x" else 2
    require(parent[index] < at < parent[index + 1], "cut outside parent")
    points = operation["points"]
    expected = {(at, parent[2]), (at, parent[3])} if axis == "x" else {(parent[0], at), (parent[1], at)}
    require(len(points) == 2 and set(map(tuple, points)) == expected, "cut endpoints differ")
    first, second = list(parent), list(parent)
    first[index + 1], second[index] = at, at
    return parent, (tuple(first), tuple(second))


def verify_history(family, history):
    """All variants must geometrically reach the identical final rectangles."""
    active = {tuple(family["bounds"])}
    for operation in history:
        parent, daughters = split_boxes(operation)
        require(parent in active, "history splits nonexistent parent")
        active.remove(parent)
        active.update(daughters)
    require(active == {tuple(b) for b in family["rectangles"].values()}, "wrong final geometry")
    require(tuple(history[-1]["parent_bounds"]) == tuple(family["parent_rectangle"]), "wrong final parent")


def audit_trace(family, history, record):
    """Audit every actually visited state and refuse skipped or invented suffixes."""
    trace = record["trace"]
    require(trace and len(trace) <= len(history), "invalid trace length")
    require(record["intended_steps"] == len(history), "wrong intended length")
    expected_before = {tuple(family["bounds"]): 1}
    costs = []
    for index, entry in enumerate(trace):
        require(entry["step"] == index + 1, "skipped or duplicated step")
        require(entry["operation"] == history[index], "different requested operation")
        if index:
            require(entry["before"] == trace[index - 1]["after"], "identities or state changed between steps")
        before = snapshot_colors(entry["before"], family["bounds"])
        after = snapshot_colors(entry["after"], family["bounds"])
        require(before == expected_before, "trace states do not join")
        parent, daughters = split_boxes(history[index])
        require(parent in before, "current parent missing")
        if entry["status"] == "blocked":
            require(index == len(trace) - 1, "history continued after policy stopped")
            require(entry["after"] == entry["before"], "failed cut modified state")
        else:
            require(entry["status"] == "split", "unsupported policy outcome")
            require(set(after) == (set(before) - {parent}) | set(daughters), "wrong geometry transition")
            old_ids = {tuple(r["bounds"]): r["id"] for r in entry["before"]["rectangles"]}
            new_ids = {tuple(r["bounds"]): r["id"] for r in entry["after"]["rectangles"]}
            require(all(new_ids[b] == old_ids[b] for b in before if b != parent),
                    "unsplit old identity changed")
            require(all(new_ids[b] not in set(old_ids.values()) for b in daughters),
                    "daughter identity is not new")
            cost = sum(after[b] != c for b, c in before.items() if b != parent)
            if "cost_old_changes" in entry:
                require(entry["cost_old_changes"] == cost, "reported step cost differs")
            costs.append(cost)
        expected_before = after
    blocked = trace[-1]["status"] == "blocked"
    require(record["status"] == ("blocked" if blocked else "completed"), "false completion label")
    require(blocked or len(trace) == len(history), "unfinished successful prefix")
    require(record["stop_step"] == (len(trace) if blocked else None), "wrong stop step")
    require(record["reached_final_parent"] == (len(trace) == len(history)), "wrong reachability label")
    require(snapshot_colors(record["final_state"], family["bounds"]) == expected_before,
            "wrong final state")
    if "cost_old_changes" in record:
        require(record["cost_old_changes"] == sum(costs), "wrong cumulative cost")
    return {"passed": True, "successful_steps": len(costs),
            "old_side_changes_per_successful_step": costs, "cumulative_old_side_changes": sum(costs)}


def pending_problem(snapshot, operation, bounds):
    """Generate a diagnostic H only from the actual state preceding one cut."""
    old = snapshot_colors(snapshot, bounds)
    parent, daughter_boxes = split_boxes(operation)
    require(parent in old, "pending parent is missing")
    boxes = sorted((set(old) - {parent}) | set(daughter_boxes))
    ids = {box: f"s{i}" for i, box in enumerate(boxes)}
    initial = {"r": 0, **{ids[box]: old[parent] if box in daughter_boxes else old[box] for box in boxes}}
    daughters = [ids[box] for box in daughter_boxes]
    edges = []
    for i, box in enumerate(boxes):
        if box[0] == bounds[0] or box[1] == bounds[1] or box[2] == bounds[2] or box[3] == bounds[3]:
            edges.append(["r", ids[box]])
        for other in boxes[i + 1:]:
            if shared(box, other) and set((box, other)) != set(daughter_boxes):
                edges.append([ids[box], ids[other]])
    return {"edges": edges, "initial": initial, "daughters": daughters, "fixed": ["r"],
            "weights": {v: int(v != "r" and v not in daughters) for v in initial}}, ids


def audit_kempe_candidates(problem, result):
    """Audit complete component coverage and literal costs without record metadata."""
    audit_attempts(problem, result["attempts"])
    eligible = {(a["seed"], tuple(a["pair"])): a for a in result["attempts"] if not a["blocked_reasons"]}
    require(len(result["candidates"]) == len(eligible), "missing eligible Kempe candidates")
    seen = set()
    for candidate in result["candidates"]:
        key = candidate["seed"], tuple(candidate["pair"])
        require(key in eligible and key not in seen, "unexpected or duplicate Kempe candidate")
        seen.add(key)
        component = set(eligible[key]["component"])
        require(tuple(candidate["component"]) == tuple(eligible[key]["component"]), "partial Kempe component")
        a, b = key[1]
        target = {v: a ^ b ^ c if v in component else c for v, c in problem["initial"].items()}
        require(candidate["target"] == target, "wrong literal swap")
        cost = sum(problem["weights"][v] for v in component)
        require(candidate["changed_weight"] == cost and candidate["changed_side_count"] == len(component),
                "wrong Kempe cost")
        check_target(problem, target, cost)
    require(result["status"] == ("repaired" if eligible else "stalled"), "wrong Kempe status")
    if eligible:
        require(result["selected"] in result["candidates"] and result["selected"]["changed_weight"]
                == min(c["changed_weight"] for c in result["candidates"]), "wrong least-cost candidate")
    else:
        require(result["selected"] is None, "spurious selected repair")
    return {"passed": True, "attempts_verified": 6, "candidates_verified": len(eligible)}


def diagnose_stop(family, record):
    """Cost analysis is read-only and never feeds a target back into the policy."""
    entry = record["trace"][-1]
    problem, _ = pending_problem(entry["before"], entry["operation"], family["bounds"])
    quotient = apex_triangle_cost_table(problem["edges"], problem["initial"], problem["daughters"],
                                        apex="r", weights=problem["weights"])
    direct = recoloring_boundary_table(**problem) if len(problem["initial"]) <= 12 else None
    audit = audit_quotient(problem, quotient, direct)
    kempe = single_kempe_split(**problem)
    kempe_audit = audit_kempe_candidates(problem, kempe)
    return {"problem": problem, "quotient": quotient, "quotient_audit": audit,
            "direct_boundary_table": direct, "single_kempe": kempe, "single_kempe_audit": kempe_audit,
            "used_to_continue_history": False}


def compare_final_inherited(family, record):
    """Compare actual final-parent colors literally and under fixed-exterior relabeling."""
    if not record["reached_final_parent"]:
        return {"status": "not_reached", "matches_literal": None, "matches_up_to_permutation": None}
    before = snapshot_colors(record["trace"][-1]["before"], family["bounds"])
    inherited = {"r": 0}
    parent = tuple(family["parent_rectangle"])
    for side, box in family["rectangles"].items():
        inherited[side] = before[parent] if side in family["problem"]["daughters"] else before[tuple(box)]
    reference = family["problem"]["initial"]
    mappings = []
    for colors in permutations((1, 2, 3)):
        mapping = dict(enumerate((0,) + colors))
        if all(mapping[inherited[v]] == reference[v] for v in reference):
            mappings.append(mapping)
    return {"status": "compared", "inherited": inherited,
            "matches_literal": inherited == reference,
            "matches_up_to_permutation": bool(mappings), "matching_permutations": mappings}


def source_hashes():
    """Keep unchanged baselines and exact policy sources identifiable."""
    return {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in (INPUT,) + SOURCES}


def run_experiment(node="node"):
    """Run 384 Python histories and 64 unchanged browser-policy histories."""
    before = source_hashes()
    require(before[INPUT] == INPUT_SHA256, "frozen family source changed")
    saved = json.loads((ROOT / INPUT).read_text(encoding="utf-8"))
    saved_families = {r["m"]: r["family"] for r in saved["family_records"]}
    cases, rows = [], []
    for m in PARAMETERS:
        family = build_staggered_strip(m)
        require(family == saved_families[m], "family generator changed")
        verify_staggered_geometry(family)
        for variant in variants():
            history = build_history_variant(family, **variant)
            verify_history(family, history)
            cases.append({"m": m, "variant": variant, "bounds": family["bounds"], "history": history})
            for policy, inherit in product(("plain", "strip", "forest"), ("left", "right")):
                record = replay_staggered_history(family, policy=policy, inherit=inherit, **variant)
                record["audit"] = audit_trace(family, history, record)
                record["final_initial_comparison"] = compare_final_inherited(family, record)
                if record["status"] == "blocked":
                    record["stop_diagnosis"] = diagnose_stop(family, record)
                rows.append(record)
        print(json.dumps({"m": m, "python_histories_checked": len(rows)}), flush=True)
    executable = shutil.which(node)
    require(executable is not None, "Node.js is required to replay the actual browser module")
    response = subprocess.run([executable, str(ROOT / "scripts/replay_triangle_chain_web.mjs")],
                              input=json.dumps({"schema_version": 1, "cases": cases}),
                              text=True, encoding="utf-8", capture_output=True, check=True, cwd=ROOT,
                              timeout=180)
    web = json.loads(response.stdout)
    require(len(web["results"]) == len(cases), "missing browser cases")
    for case, record in zip(cases, web["results"]):
        require(record["m"] == case["m"] and record["variant"] == case["variant"], "browser case mismatch")
        family = saved_families[case["m"]]
        record["audit"] = audit_trace(family, case["history"], record)
        record["final_initial_comparison"] = compare_final_inherited(family, record)
        if record["status"] == "blocked":
            record["stop_diagnosis"] = diagnose_stop(family, record)
        rows.append(record)
    summaries = []
    keys = sorted({(row["policy"], row.get("inherit", "automatic")) for row in rows})
    for policy, inherit in keys:
        subset = [r for r in rows if (r["policy"], r.get("inherit", "automatic")) == (policy, inherit)]
        blocked = [r for r in subset if r["status"] == "blocked"]
        summaries.append({"policy": policy, "inherit": inherit, "histories": len(subset),
                          "completed": sum(r["status"] == "completed" for r in subset),
                          "reached_final_parent": sum(r["reached_final_parent"] for r in subset),
                          "target_initial_matches_up_to_permutation": sum(
                              r["final_initial_comparison"]["matches_up_to_permutation"] is True for r in subset),
                          "actual_blocked_minimum_costs": dict(sorted(Counter(
                              r["stop_diagnosis"]["quotient"]["minimum_cost"] for r in blocked).items())),
                          "blocked_with_single_kempe_repair": sum(
                              r["stop_diagnosis"]["single_kempe"]["status"] == "repaired" for r in blocked)})
    require(source_hashes() == before, "source changed during formal replay")
    return {"schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "all_passed": True, "python_version": platform.python_version(), "node_version": web["node_version"],
            "parameters": PARAMETERS, "variants": variants(), "randomness": "none",
            "histories": rows, "summaries": summaries, "input_and_source_sha256": before,
            "unchanged_at_end": True, "scope": "specified histories and deterministic existing policies only",
            "claims_not_made": ["all cut histories exhausted", "target initial state globally unreachable",
                                "diagnostic target was produced by a policy", "originality or general completeness"]}


def main():
    """Preserve earlier research reports and provide a compact console summary."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--node", default="node")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; choose a new filename")
    report = run_experiment(args.node)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(report["summaries"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

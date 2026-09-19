"""Compare three fixed, bounded local naming rules on saved cases A, B and C.

This is a three-map, one-cut experiment, not a continuation benchmark or a
four-color proof. No production rule is changed. Current boundary constraints
are recomputed; historical names are not accumulated as permanent prohibitions.
"""

from argparse import ArgumentParser
from collections import Counter, deque
from datetime import datetime, timezone
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.inherited_names import (
    RectSide, RectState, attempt_cut, find_conflicts, line_profiles, state_payload,
)
from scripts.audit_retained_blocks import independent_audits, rectangle_adjacency, unpack_state


METHODS = ("M1_candidates", "M2_one_neighbor", "M3_bounded_two_name")
PALETTE = frozenset((1, 2, 3, 4))


def validate_state(state):
    """Independently check rectangular coverage and every real named boundary."""
    area = 0
    for side in state.sides:
        x0, y0, x1, y1 = side.bounds
        if not (0 <= x0 < x1 <= state.width and 0 <= y0 < y1 <= state.height):
            raise ValueError("invalid rectangle bounds")
        if type(side.symbol) is not int or side.symbol not in PALETTE:
            raise ValueError("the committed palette is exactly 1..4")
        area += (x1 - x0) * (y1 - y0)
    if area != state.width * state.height:
        raise ValueError("rectangles do not cover the complete canvas")
    for first, second in combinations(state.sides, 2):
        x0, y0, x1, y1 = first.bounds
        u0, v0, u1, v1 = second.bounds
        if min(x1, u1) > max(x0, u0) and min(y1, v1) > max(y0, v0):
            raise ValueError("rectangle interiors overlap")
    graph = rectangle_adjacency(state)
    names = {"outside": 1, **{side.id: side.symbol for side in state.sides}}
    if any(names[v] == names[w] for v, neighbors in graph.items() for w in neighbors):
        raise ValueError("equal names across a positive-length boundary")
    if find_conflicts(state.sides, state.width, state.height):
        raise AssertionError("independent adjacency and boundary checker disagree")
    return graph


def profile_changes(before, after):
    """Count exact span-key changes, not sides, with split spans kept explicit.

    Replacing one span by two counts as one removal and two additions. This is
    a record-diff measure, not the number of changed connected sides or pixels.
    """
    def index(state):
        return {(mother, tuple(tuple(p) for p in entry["segment"])): tuple(entry["pair"])
                for mother, entries in line_profiles(state).items() for entry in entries}

    old, new = index(before), index(after)
    changes = [{"mother": key[0], "segment": key[1],
                "before_pair": old.get(key), "after_pair": new.get(key),
                "kind": "added" if key not in old else "removed" if key not in new else "renamed"}
               for key in sorted(set(old) | set(new)) if old.get(key) != new.get(key)]
    mothers = sorted({entry["mother"] for entry in changes})
    old_mothers = {key[0] for key in old}
    return {"profile_change_record_count": len(changes),
            "profile_count_definition": "union of exact mother/span keys; subdivision counts removed and added records",
            "profile_changes": changes, "touched_mothers": mothers,
            "touched_mother_count": len(mothers),
            "touched_existing_mother_count": len(set(mothers) & old_mothers)}


def bounded_component(graph, names, start, pair, parent, max_sides=3, max_distance=2):
    """Accept only an entire component; stop at a sufficient rejection witness.

    Traversal follows fixed graph structure, not alternative color assignments.
    Distance is measured in the full old adjacency graph, including outside.
    A rejected member set may be partial; none of its members are swapped.
    """
    component, queue = {start}, deque([start])
    while queue:
        vertex = queue.popleft()
        for neighbor in sorted(graph[vertex]):
            if neighbor not in component and names[neighbor] in pair:
                component.add(neighbor)
                if neighbor in {"outside", parent}:
                    return component, "component_reaches_fixed_outside_or_parent"
                if len(component) > max_sides:
                    return component, "component_exceeds_three_old_sides"
                queue.append(neighbor)
    if component & {"outside", parent}:
        return component, "component_reaches_fixed_outside_or_parent"
    if len(component) > max_sides:
        return component, "component_exceeds_three_old_sides"
    distance, queue = {parent: 0}, deque([parent])
    while queue:
        vertex = queue.popleft()
        if distance[vertex] >= max_distance:
            continue
        for neighbor in sorted(graph[vertex]):
            if neighbor not in distance:
                distance[neighbor] = distance[vertex] + 1
                queue.append(neighbor)
    if any(v not in distance for v in component):
        return component, "component_exceeds_distance_two"
    return component, None


def compare_cut(state, cut, method):
    """Apply exactly one documented decision, with no target or branch retry."""
    if method not in METHODS:
        raise ValueError("unknown comparison method")
    old_graph = validate_state(state)
    # Only the cut geometry/identities are reused; its suggested names are ignored.
    geometry = attempt_cut(state, cut, inherit="left")
    if geometry["status"] == "outside_scope":
        return {"method": method, "status": "outside_scope", "reason": geometry["event"]["reason"]}
    proposal = geometry["proposed_state"]
    parent = geometry["event"]["parent"]
    old_names = {"outside": 1, **{side.id: side.symbol for side in state.sides}}
    s = old_names[parent]
    children = sorted((side for side in proposal.sides if side.id not in old_names),
                      key=lambda side: side.bounds)
    if len(children) != 2:
        raise AssertionError("a rectangle cut must introduce exactly two children")
    new_graph = rectangle_adjacency(proposal)
    child_ids = {side.id for side in children}
    constraints = []
    for child in children:
        neighbors = sorted(new_graph[child.id] - child_ids)
        retained = sorted({old_names[v] for v in neighbors})
        constraints.append({"child_id": child.id, "bounds": child.bounds,
                            "old_neighbor_ids": neighbors, "R": retained,
                            "candidates": sorted(PALETTE - set(retained) - {s})})
    result = {"method": method, "status": "blocked", "parent": parent, "s": s,
              "cut": geometry["event"]["cut"], "candidates_before": constraints,
              "changed_old_ids": [], "changed_old_count": 0,
              "touched_mother_count": 0, "profile_change_record_count": 0,
              "repair": {"needed": False, "attempted": False},
              "decision_order": "new-child bounds lexicographic, then smallest candidate name",
              "validation_scope": "all actual old/final boundaries; mutation support is separately bounded"}
    chosen = next((entry for entry in constraints if entry["candidates"]), None)
    renamed = dict(old_names)
    if chosen is not None:
        target = chosen["candidates"][0]
        result["used_stage"] = "M1_direct"
        result["repair"]["reason"] = "no_repair_needed"
    elif method == METHODS[0]:
        result["reason"] = "both_current_candidate_sets_empty"
        return result
    else:
        # A single predeclared target is tried; failure never selects another.
        chosen = constraints[0]
        forbidden = {s} | ({1} if "outside" in chosen["old_neighbor_ids"] else set())
        targets = sorted(PALETTE - forbidden)
        if not targets:
            result["reason"] = "no_fixed_target"
            return result
        target = targets[0]
        blockers = [v for v in chosen["old_neighbor_ids"] if old_names[v] == target]
        result["repair"] = {"needed": True, "attempted": True, "target": target,
                            "chosen_child_id": chosen["child_id"], "blocker_ids": blockers}
        if len(blockers) != 1 or blockers[0] == "outside":
            result["reason"] = "target_has_no_unique_nonoutside_old_blocker"
            return result
        blocker = blockers[0]
        if method == METHODS[1]:
            legal = sorted(PALETTE - {old_names[v] for v in old_graph[blocker]} - {target})
            if not legal:
                result["reason"] = "single_blocker_has_no_legal_replacement"
                return result
            q = legal[0]
            component = {blocker}
            renamed[blocker] = q
            result["used_stage"] = "M2_one_neighbor"
        else:
            options = sorted(PALETTE - {s, target, 1})
            if not options:
                result["reason"] = "no_fixed_second_name"
                return result
            q = options[0]
            component, reason = bounded_component(old_graph, old_names, blocker,
                                                   {target, q}, parent)
            result["repair"].update({"component_ids": sorted(component), "q": q,
                                     "component_record_kind": ("complete_accepted_component" if reason is None
                                                               else "rejection_witness_not_promised_complete"),
                                     "max_old_sides": 3, "max_old_graph_distance": 2})
            if reason:
                result["reason"] = reason
                return result
            for vertex in component:
                renamed[vertex] = q if old_names[vertex] == target else target
            result["used_stage"] = "M3_bounded_two_name"
        result["repair"].update({"q": q, "component_ids": sorted(component)})
        repaired_old = RectState(state.width, state.height,
                                tuple(RectSide(side.id, side.bounds, renamed[side.id])
                                      for side in state.sides), state.cuts)
        validate_state(repaired_old)
        if target in {renamed[v] for v in chosen["old_neighbor_ids"]}:
            result["reason"] = "swap_introduces_target_at_another_child_neighbor"
            return result
    # Commit only after the whole fixed operation satisfies every boundary.
    final = RectState(state.width, state.height,
                      tuple(RectSide(side.id, side.bounds,
                                     target if side.id == chosen["child_id"] else
                                     s if side.id in child_ids else renamed[side.id])
                            for side in proposal.sides), proposal.cuts)
    final_graph = validate_state(final)
    changed = sorted(v for v in old_names if v not in ("outside", parent)
                     and old_names[v] != renamed[v])
    result.update({"status": "split", "new_name": target,
                   "new_name_child_id": chosen["child_id"],
                   "new_name_child_bounds": chosen["bounds"],
                   "actual_inherit": "right" if chosen["child_id"].endswith(".l") else "left",
                   "changed_old_ids": changed, "changed_old_count": len(changed),
                   "old_name_changes": [{"id": v, "before": old_names[v], "after": renamed[v]}
                                        for v in changed],
                   "final_state": state_payload(final),
                   "boundary_audit": {"all_constraints_valid": True,
                                      "unique_adjacencies_checked": sum(map(len, final_graph.values())) // 2,
                                      "independent_rectangle_adjacency": True,
                                      "production_boundary_crosscheck": True}})
    result.update(profile_changes(state, final))
    return result


def load_cases(manifest_path, report_path):
    """Load exact A/B geometry and the earliest documented double-empty C."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    cases = [{"case": entry["case"], "seed": entry["seed"],
              "original_inherit": entry["inherit"], "stopped_step": entry["stopped_step"],
              "state": unpack_state(entry["current_committed_state"]), "cut": entry["pending_cut"]}
             for entry in manifest["cases"] if entry["case"] in ("A", "B")]
    matches = [row for row in report["runs"]
               if row["family"] == "guillotine" and row["seed"] == 20260960 and row["inherit"] == "right"]
    if len(matches) != 1 or matches[0]["committed_steps"] != 2:
        raise ValueError("expected unique original C stopped at step three")
    row = matches[0]
    cases.append({"case": "C", "seed": row["seed"], "original_inherit": row["inherit"],
                  "stopped_step": 3, "state": unpack_state(row["last_valid_state"]),
                  "cut": row["events"][-1]["cut"]})
    if [case["case"] for case in cases] != ["A", "B", "C"]:
        raise ValueError("this comparison requires exactly A, B, C")
    return cases


def build_report(manifest_path, report_path):
    """Run the nine fixed comparisons and preserve inputs/hashes for replay."""
    runs = []
    for case in load_cases(manifest_path, report_path):
        for method in METHODS:
            result = compare_cut(case["state"], case["cut"], method)
            result.update({key: value for key, value in case.items() if key not in ("state", "cut")})
            result["input_state"] = state_payload(case["state"])
            runs.append(result)
    # Rebuild every accepted output from its actual strokes, independently of
    # rectangle adjacency. Rejected proposals never become success certificates.
    accepted = [row for row in runs if row["status"] == "split"]
    certificates = [{"key": row["case"] + "/" + row["method"],
                     "certificate": {"state": row["final_state"]}} for row in accepted]
    independent_count = independent_audits(certificates)
    for row, certificate in zip(accepted, certificates):
        row["independent_audit"] = certificate["certificate"]["independent_audit"]
    return {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "scope": "3 saved maps x 3 fixed one-cut methods; no continuation, backtracking, proof or production change",
            "inputs": [{"filename": path.name, "sha256": sha256(path.read_bytes()).hexdigest()}
                       for path in (manifest_path, report_path)],
            "source_sha256": {name: sha256((ROOT / name).read_bytes()).hexdigest()
                              for name in ("scripts/compare_local_marks.py", "tests/test_local_marks.py",
                                           "fourcolor/inherited_names.py", "scripts/audit_retained_blocks.py",
                                           "fourcolor/line_names.py", "scripts/inherited-oracle.mjs", "web/engine.js")},
            "policy": {"M1": "two current child candidate sets, lexicographic bounds then smallest name",
                       "M2": "M1, otherwise one fixed target and one old neighbor, smallest legal replacement",
                       "M3": "M1, otherwise same fixed target/blocker, one fixed two-name component; max 3 old sides and distance 2",
                       "no_retry": "no alternative target, second name, component or repair branch is tried",
                       "locality": "limits constrain changed old sides, not reading complete boundary constraints"},
            "summary": {"maps": 3, "one_cut_runs": len(runs),
                        "node_and_rotation_success_states": independent_count,
                        "by_method": {method: dict(Counter(r["status"] for r in runs if r["method"] == method))
                                      for method in METHODS},
                        "M3_nontrivial_multiside_repairs": sum(r["method"] == METHODS[2] and r["changed_old_count"] > 1
                                                               for r in runs)},
            "runs": runs}


def main():
    """Write only a new requested report; never overwrite an existing result."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "docs/figures/anchor-failures-2026-09-18/manifest.json")
    parser.add_argument("--input", type=Path, default=ROOT / "outputs/anchor-forest-continuation-2026-09-18-v2.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; choose a new filename")
    report = build_report(args.manifest, args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

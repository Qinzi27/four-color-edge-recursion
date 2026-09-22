"""Offline exact audit of actual commitments of the frozen structural policy.

The candidate finishes before any oracle call. Only true geometric adjacency
and explicit commitments enter the independent oracle; inferred domains never
become oracle assumptions. Small inputs additionally enumerate every literal
four-name assignment consistent with the two initialization anchors.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from itertools import product
import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.structural_restart import POLICY, restart_structural_names
from scripts.exact_extendibility_oracle import solve_exact, verify_exact_result
from scripts.exhaustive_rectangular_histories import build_inventory
from scripts.validate_frontier_restart import independent_geometry
from scripts.validate_global_restart import digest, export_geometries, write_report
from scripts.validate_structural_restart import verify_run


def side_anchors(plane, by_dart):
    """Translate explicit singleton darts, rejecting contradictory duplicate sides."""
    result = {}
    for dart, domain in by_dart.items():
        if len(domain) != 1:
            raise AssertionError("oracle input must contain explicit singleton commitments")
        side = plane.face_of_dart[int(dart)]
        if side in result and result[side] != domain[0]:
            raise AssertionError("inconsistent duplicate side commitment")
        result[side] = domain[0]
    return result


def literal_solutions(n, edges, anchors, assignment_limit):
    """Enumerate the complete anchored Cartesian product or explicitly skip it."""
    free = [v for v in range(n) if v not in anchors]
    count = 4 ** len(free)
    if count > assignment_limit:
        return None, count
    solutions = []
    for names in product((1, 2, 3, 4), repeat=len(free)):
        coloring = [anchors.get(v, 0) for v in range(n)]
        for v, c in zip(free, names):
            coloring[v] = c
        if all(coloring[a] != coloring[b] for a, b in edges):
            solutions.append(coloring)
    return solutions, count


def check_retained_solutions(solutions, anchors, outcome):
    """Verify every compatible full solution survives all final unary/pair filters.

The separate trace checker verifies monotone deletion at every intermediate
step. Thus preservation by the final masks also checks every earlier deletion.
"""
    compatible = [c for c in solutions if all(c[v] == name for v, name in anchors.items())]
    for coloring in compatible:
        for v, name in enumerate(coloring):
            if name not in outcome["domains"][v]:
                raise AssertionError("soundness failure: a genuine coloring lost a unary value")
        for a in range(len(coloring)):
            for b in range(len(coloring)):
                bit = 1 << (4 * (coloring[a] - 1) + coloring[b] - 1)
                if not outcome["relations"][a][b] & bit:
                    raise AssertionError("soundness failure: a genuine coloring lost a pair")
    return len(compatible)


def audit_candidate(geometry, result, *, node_limit=1000000, assignment_limit=4096):
    """Check initialization and every reachable commitment without changing it."""
    replay = verify_run(geometry, result)
    plane, adjacent = independent_geometry(geometry)
    edges = [(a, b) for a, neighbors in enumerate(adjacent) for b in sorted(neighbors) if a < b]
    n = len(adjacent)
    initial = side_anchors(plane, result["initial_anchors_by_dart"])
    solutions, attempted = literal_solutions(n, edges, initial, assignment_limit)
    if solutions is not None:
        for query in result["proof_queries"]:
            if query["certificate"]["status"] == "proved_different":
                a, b = query["pair"]
                if any(c[a] == c[b] for c in solutions):
                    raise AssertionError("structural inequality deletes a legal coloring")
    rows, first_failure, oracle_nodes = [], None, 0
    last_anchors, last_exact = None, None
    for index, call in enumerate(result["propagation_phases"]):
        anchors = side_anchors(plane, call["anchors_by_dart"])
        # Learned relations are checked for soundness but never fed to the oracle.
        if anchors != last_anchors:
            exact = solve_exact(n, edges, anchors, node_limit=node_limit)
            verify_exact_result(n, edges, anchors, exact)
            oracle_nodes += exact["nodes"]
        else:
            exact = last_exact
        compatible = (check_retained_solutions(solutions, anchors, call["outcome"])
                      if solutions is not None else None)
        if compatible is not None and exact["status"] != "unknown":
            if bool(compatible) != (exact["status"] == "sat"):
                raise AssertionError("literal enumeration and exact oracle disagree")
        event = None if index == 0 else result["events"][index - 1]
        row = {"phase": index, "kind": "initialization" if event is None else event["kind"],
               "anchors": [[v, c] for v, c in sorted(anchors.items())],
               "oracle": exact, "compatible_literal_solutions": compatible}
        if event is not None:
            row["proposal"] = event["proposal"]
        rows.append(row)
        if (event is not None and event["kind"] == "commit" and last_exact["status"] == "sat"
                and exact["status"] == "unsat" and first_failure is None):
            first_failure = {"event_index": index - 1, "proposal": event["proposal"],
                             "before_anchors": rows[-2]["anchors"], "after_anchors": row["anchors"],
                             "before_witness": last_exact["witness"], "after_exact": exact,
                             "checks": event["checks"]}
        last_anchors, last_exact = anchors, exact
    return {"vertex_count": n, "true_edges": [list(e) for e in edges],
            "policy": result["policy"], "candidate_status": result["status"],
            "candidate_sha256": digest(result), "candidate_replay": replay,
            "initialization_status": rows[0]["oracle"]["status"], "states": rows,
            "first_bad_commitment": first_failure, "oracle_nodes": oracle_nodes,
            "unknown_states": sum(r["oracle"]["status"] == "unknown" for r in rows),
            "soundness": {"status": "complete" if solutions is not None else "not_enumerated",
                          "literal_assignments": attempted if solutions is not None else 0,
                          "assignment_space_size": attempted,
                          "initial_legal_assignments": len(solutions) if solutions is not None else None,
                          "phases_checked": len(rows) if solutions is not None else 0,
                          "symmetry": "Two adjacent initialization sides are fixed to 1,2. All other names remain literal; no further symmetry reduction."}}


def source_hashes():
    """Bind all core modules and the audit/geometry code before formal execution."""
    paths = set(ROOT.glob("fourcolor/*.py")) | set(ROOT.glob("web/*.js"))
    paths.update(ROOT / p for p in (
        "scripts/audit_commit_extendibility.py", "scripts/exact_extendibility_oracle.py",
        "scripts/exhaustive_rectangular_histories.py", "scripts/exhaustive_grid_subsets.py",
        "scripts/restart-geometry.mjs", "AGENTS.md",
        "tests/test_commit_extendibility.py", "tests/test_exact_extendibility_oracle.py",
        "tests/test_exhaustive_rectangular_histories.py", "tests/test_exhaustive_grid_subsets.py",
        "docs/EXTENDIBILITY_PROTOCOL-2026-09-21.md",
        "scripts/validate_global_restart.py", "scripts/current_corpus.py",
        "scripts/validate_structural_restart.py", "scripts/validate_frontier_restart.py",
        "scripts/validate_level_sides_peer.py", "scripts/validate_relation_frontier.py",
        "scripts/analyze_line_generations.py", "scripts/validate_weighted_lines.py"))
    return {p.relative_to(ROOT).as_posix(): sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def prepare(path, width, height, max_cuts, history_limit, node_limit, assignment_limit, family="guillotine"):
    """Freeze finite scope and complete actual input list before candidate runs."""
    if node_limit < 0 or assignment_limit < 0:
        raise ValueError("resource limits must be nonnegative")
    if family == "guillotine":
        inventory = build_inventory(width=width, height=height, max_cuts=max_cuts, history_limit=history_limit)
        scope = {"family": family, "width": width, "height": height, "max_cuts": max_cuts,
                 "random_seeds": [], "scope_kind": "exhaustive finite grid guillotine histories"}
    else:
        from scripts.exhaustive_grid_subsets import build_grid_inventory
        inventory = build_grid_inventory(width=width, height=height, subset_limit=history_limit)
        scope = {"family": family, "width": width, "height": height, "random_seeds": [],
                 "scope_kind": "all interior unit-grid segment subsets, one canonical addition order per subset"}
    manifest = {"schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "policy": POLICY, "source_sha256": source_hashes(),
                "resources": {"oracle_node_limit": node_limit,
                              "literal_assignment_limit": assignment_limit,
                              "history_limit": history_limit, "workers": 1},
                "scope": scope,
                "oracle_separation": "Every candidate finishes before offline oracle examination. No oracle answer is supplied to the candidate.",
                "inventory": inventory}
    write_report(path, manifest)
    return manifest


def verify_inventory(manifest):
    """Regenerate the bounded list so omissions cannot masquerade as exhaustive."""
    scope, resources = manifest["scope"], manifest["resources"]
    if manifest["policy"] != POLICY:
        raise AssertionError("manifest names another policy")
    if scope["family"] == "guillotine":
        rebuilt = build_inventory(scope["width"], scope["height"], scope["max_cuts"],
                                  resources["history_limit"])
    elif scope["family"] == "grid-subsets":
        from scripts.exhaustive_grid_subsets import build_grid_inventory
        rebuilt = build_grid_inventory(scope["width"], scope["height"], resources["history_limit"])
    else:
        raise AssertionError("unknown input family")
    for field in ("records", "histories", "summary", "status", "generation_complete"):
        if digest(rebuilt[field]) != digest(manifest["inventory"][field]):
            raise AssertionError("manifest inventory differs from exhaustive regeneration: " + field)
    for name, expected in manifest["inventory"].get("source_sha256", {}).items():
        if sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise AssertionError("generation source changed: " + name)
    return True


def execute(manifest_path, output):
    """Run every predeclared drawing and retain each history's prefix references."""
    if output.exists():
        raise FileExistsError("refusing to overwrite existing report")
    raw = manifest_path.read_bytes()
    manifest = json.loads(gzip.decompress(raw) if manifest_path.suffix == ".gz" else raw)
    if manifest["source_sha256"] != source_hashes():
        raise AssertionError("source changed after predeclaration")
    verify_inventory(manifest)
    inventory, resources = manifest["inventory"], manifest["resources"]
    rows = []
    for start in range(0, len(inventory["records"]), 50):
        records = inventory["records"][start:start + 50]
        for record, exported in zip(records, export_geometries(records)):
            geometry, candidate = exported.get("geometry"), None
            try:
                if record["key"] != exported["key"] or exported["status"] != "geometry_ok":
                    raise AssertionError("declared legal drawing failed geometry export")
                if (manifest["scope"]["family"] == "guillotine"
                        and len(geometry["faces"]) != len(record["document"]["strokes"]) + 2):
                    raise AssertionError("guillotine cuts disagree with independently expected face count")
                candidate = restart_structural_names(geometry)
                audit = audit_candidate(geometry, candidate, node_limit=resources["oracle_node_limit"],
                                        assignment_limit=resources["literal_assignment_limit"])
            except Exception as exc:
                # A failed audit must retain its actual scene, not disappear
                # in a traceback or become a false UNSAT/complete result.
                failure = {"status": "audit_failed", "coverage": "incomplete",
                           "manifest_sha256": sha256(raw).hexdigest(), "record": record,
                           "geometry_export": exported, "candidate": candidate,
                           "completed_geometry_keys": [r["key"] for r in rows],
                           "error_type": type(exc).__name__, "error": str(exc)}
                checkpoint = output.with_name(output.name + ".failure-" + record["key"] + ".json")
                write_report(checkpoint, failure)
                raise
            row = {"key": record["key"], "geometry_sha256": digest(geometry), "audit": audit}
            if (audit["first_bad_commitment"] is not None or audit["unknown_states"]
                    or audit["initialization_status"] != "sat"):
                row.update({"geometry": geometry, "candidate": candidate})
            rows.append(row)
        print(json.dumps({"audited": len(rows), "total": len(inventory["records"]),
                          "bad_commitments": sum(r["audit"]["first_bad_commitment"] is not None for r in rows)}), flush=True)
    by_key = {r["key"]: r["audit"] for r in rows}
    history_results = [{"key": h["key"], "depth": h["depth"],
                        "all_prefixes_solved": all(by_key[k]["candidate_status"] == "solved" for k in h["prefix_keys"]),
                        "all_prefixes_exact_sat": all(all(s["oracle"]["status"] == "sat" for s in by_key[k]["states"])
                                                        for k in h["prefix_keys"])} for h in inventory["histories"]]
    summary = {"generation_status": inventory["status"],
               "drawings": len(rows), "candidate_status": dict(Counter(r["audit"]["candidate_status"] for r in rows)),
               "histories": len(history_results), "all_prefixes_solved": sum(h["all_prefixes_solved"] for h in history_results),
               "all_prefixes_exact_sat": sum(h["all_prefixes_exact_sat"] for h in history_results),
               "actual_commitments": sum(r["audit"]["candidate_replay"]["actual_commits_checked"] for r in rows),
               "bad_commitments": sum(r["audit"]["first_bad_commitment"] is not None for r in rows),
               "unknown_states": sum(r["audit"]["unknown_states"] for r in rows),
               "literal_assignments": sum(r["audit"]["soundness"]["literal_assignments"] for r in rows),
               "legal_initial_assignments": sum(r["audit"]["soundness"]["initial_legal_assignments"] or 0 for r in rows),
               "soundness_complete_drawings": sum(r["audit"]["soundness"]["status"] == "complete" for r in rows),
               "initialization_status": dict(Counter(r["audit"]["initialization_status"] for r in rows)),
               "oracle_nodes": sum(r["audit"]["oracle_nodes"] for r in rows)}
    summary["audit_status"] = ("complete" if inventory["generation_complete"]
                               and summary["unknown_states"] == 0
                               and summary["soundness_complete_drawings"] == len(rows) else "unknown")
    summary["extendibility_result"] = ("counterexample_found" if summary["bad_commitments"]
                                        else "all_declared_states_sat" if summary["audit_status"] == "complete"
                                        and all(s["oracle"]["status"] == "sat" for r in rows for s in r["audit"]["states"])
                                        else "not_all_states_established_sat")
    if manifest["source_sha256"] != source_hashes():
        raise AssertionError("source changed during execution")
    report = {"schema_version": 1, "manifest_sha256": sha256(raw).hexdigest(),
              "manifest": manifest, "drawings": rows, "history_results": history_results, "summary": summary,
              "limits": "Exhaustive only for the declared finite family and its stated histories. This is neither an arbitrary planar-map enumeration nor a general extendibility proof."}
    write_report(output, report)
    return summary


def main():
    """Separate predeclaration and execution into explicit reproducible commands."""
    parser = ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    pre = sub.add_parser("prepare")
    pre.add_argument("--manifest", type=Path, required=True)
    pre.add_argument("--family", choices=("guillotine", "grid-subsets"), default="guillotine")
    pre.add_argument("--width", type=int, default=3)
    pre.add_argument("--height", type=int, default=3)
    pre.add_argument("--max-cuts", type=int, default=5)
    pre.add_argument("--history-limit", type=int, default=1000000)
    pre.add_argument("--node-limit", type=int, default=1000000)
    pre.add_argument("--assignment-limit", type=int, default=4096)
    run = sub.add_parser("run")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.manifest, args.width, args.height, args.max_cuts,
                         args.history_limit, args.node_limit, args.assignment_limit, args.family)
        print(json.dumps({"manifest": args.manifest.name, "inventory": result["inventory"]["summary"]}))
    else:
        print(json.dumps(execute(args.manifest, args.output)))


if __name__ == "__main__":
    main()

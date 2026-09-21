"""Explain the sole archived v2 failure without running a new coloring search.

The diagnosis uses the original checked failure trace, two permutations of an
already archived v3 completion, and a fixed geometric equality-contraction
certificate. It never feeds an old coloring, retry, Kempe move, or oracle into
the frozen greedy naming policy. Output paths must be new.
"""

from argparse import ArgumentParser
from datetime import datetime, timezone
from itertools import combinations, permutations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.whole_lines import build_whole_lines
from scripts.diagnose_staged_levels_failures import (
    audit_prefix_relations, audit_witness, matches_anchors,
)
from scripts.validate_frontier_restart import file_sha, independent_geometry, read_json
from scripts.validate_global_restart import digest
from scripts.validate_level_sides_peer import verify_run

KEY = "8070783fd68de9a9dd22c6d4c8831a55c330290f4a30e2e9c8f6edb70af66132"
V2 = ROOT / "outputs/level-sides-peer-full-2026-09-19.json.gz"
V3 = ROOT / "outputs/staged-levels-full-2026-09-19.json.gz"
# Each row merges the first two current classes because both meet the same
# three mutually adjacent classes. Representatives refer to original side IDs.
PLAN = ((0, 14, (1, 11, 12)), (0, 13, (1, 12, 15)),
        (1, 3, (0, 2, 17)), (1, 8, (0, 9, 16)))
FINAL = (0, 1, 7, 16, 18)


def require(condition, message):
    """Make evidence checks effective even if assertions are optimized away."""
    if not condition:
        raise ValueError(message)


def contraction_certificate(adjacency_edges):
    """Prove side 1 != side 10 by four elementary merges and an explicit K5.

    This is a supplied finite proof plan, not a template finder or a color
    assignment algorithm. In a four-name coloring, two vertices adjacent to
    every vertex of a triangle must use the same fourth name. Contracting such
    a forced equality preserves every coloring satisfying the initial assumed
    equality. A K5 at the end therefore refutes that assumption.
    """
    edges = {tuple(sorted(edge)) for edge in adjacency_edges}
    require(all(len(edge) == 2 and edge[0] != edge[1] for edge in edges),
            "proper distinct-endpoint adjacency edges required")
    vertices = {v for edge in edges for v in edge}
    require({1, 10} <= vertices, "missing assumed-equal sides")
    classes = {v: {v} for v in vertices}
    classes[1].add(10)
    del classes[10]

    def owner(vertex):
        """Return the unique current class containing this original side."""
        return next(key for key, values in classes.items() if vertex in values)

    def edge_witness(first, second):
        """Use only a genuine original edge between two distinct classes."""
        a, b = owner(first), owner(second)
        require(a != b, "an edge cannot join a class to itself")
        choices = [edge for edge in edges if
                   (edge[0] in classes[a] and edge[1] in classes[b]) or
                   (edge[1] in classes[a] and edge[0] in classes[b])]
        require(bool(choices), f"missing class adjacency {sorted(classes[a])}-{sorted(classes[b])}")
        return {"classes": [sorted(classes[a]), sorted(classes[b])],
                "original_sides": list(min(choices))}

    steps = []
    for first, second, triangle in PLAN:
        keys = [owner(v) for v in (first, second, *triangle)]
        require(len(set(keys)) == 5, "triangle and tips must be five distinct classes")
        witnesses = [edge_witness(a, b) for a, b in combinations(triangle, 2)]
        witnesses += [edge_witness(tip, vertex)
                      for tip in (first, second) for vertex in triangle]
        step = {"tips": [sorted(classes[owner(first)]), sorted(classes[owner(second)])],
                "triangle": [sorted(classes[owner(v)]) for v in triangle],
                "edge_witnesses": witnesses,
                "rule": "two-common-neighbors-of-a-triangle-have-the-same-fourth-name"}
        a, b = owner(first), owner(second)
        classes[a].update(classes[b])
        del classes[b]
        step["merged_class"] = sorted(classes[a])
        steps.append(step)
    require(len({owner(v) for v in FINAL}) == 5, "five distinct final classes required")
    clique = {"classes": [sorted(classes[owner(v)]) for v in FINAL],
              "edge_witnesses": [edge_witness(a, b) for a, b in combinations(FINAL, 2)]}
    used_edges = sorted({tuple(row["original_sides"])
                         for item in [*steps, clique] for row in item["edge_witnesses"]})
    return {"assumed_equal": [1, 10], "palette_size": 4, "steps": steps,
            "contradiction": {"kind": "five-pairwise-adjacent-classes", **clique},
            "required_adjacencies": [list(edge) for edge in used_edges],
            "used_sides": sorted({v for edge in used_edges for v in edge}),
            "conclusion": {"sides": [1, 10], "relation": "!=",
                           "geometric_edge_added": False}}


def verify_certificate(adjacency_edges, certificate):
    """Reconstruct every contraction and reject altered premises/conclusions."""
    expected = contraction_certificate(adjacency_edges)
    require(certificate == expected, "contraction certificate differs from checked proof")
    return {"passed": True, "forced_equality_steps": len(expected["steps"]),
            "used_sides": len(expected["used_sides"]),
            "required_adjacencies": len(expected["required_adjacencies"]),
            "terminal_clique_size": 5}


def build_report():
    """Bind the proof to immutable geometry and directly checked old witnesses."""
    start_inputs = {path.name: file_sha(path) for path in (V2, V3)}
    first, third = read_json(V2), read_json(V3)
    hashes = {}
    for archive in (first, third):
        require(archive["source_sha256"] == archive["source_sha256_end"],
                "archived source hashes drifted during production")
        for name, expected in archive["source_sha256"].items():
            require(file_sha(ROOT / name) == expected, "frozen source changed: " + name)
            hashes[name] = expected
    for name in ("scripts/diagnose_v2_failure_20260921.py",
                 "scripts/diagnose_staged_levels_failures.py",
                 "tests/test_v2_failure_diagnosis.py"):
        hashes[name] = file_sha(ROOT / name)
    failed = [row for row in first["drawings"]
              if row["runs"][first["policy"]]["status"] != "solved"]
    require([row["key"] for row in failed] == [KEY], "archived unique failure changed")
    record = first["least_conflict"]
    require(record["key"] == KEY, "wrong failure geometry")
    geometry, outcome = record["geometry"], record["outcome"]
    check = verify_run(geometry, outcome)
    require(check["passed"] and len(outcome["trace"]) == 1,
            "expected independently checked single-choice failure")
    choice = outcome["trace"][0]
    require((choice["side"], choice["symbol"], choice["domain"]) == (10, 2, [2, 3, 4]),
            "fatal commitment changed")
    plane, adjacent = independent_geometry(geometry)
    model = build_whole_lines(geometry)
    edges = {(a, b) for a, row in enumerate(adjacent) for b in row if a < b}
    require((1, 10) not in edges, "conclusion should be an implicit, non-geometric relation")
    certificate = contraction_certificate(edges)
    proof_check = verify_certificate(edges, certificate)
    raw_references = []
    for a, b in certificate["required_adjacencies"]:
        witnesses = []
        for edge_id, edge in enumerate(geometry["edges"]):
            if set(plane.shores(edge_id)) != {a, b}:
                continue
            require(not edge.get("virtual"), "virtual edge cannot witness true separation")
            points = [geometry["vertices"][edge["a"]], geometry["vertices"][edge["b"]]]
            require(points[0] != points[1], "a point contact cannot witness adjacency")
            witnesses.append({"edge_id": edge_id, "endpoints": points,
                              "mother": model.edge_owner[edge_id]})
        require(bool(witnesses), "missing nonzero shared-boundary segment")
        raw_references.append({"sides": [a, b], "raw_edge_witnesses": witnesses})
    old_row = next(row for row in third["drawings"] if row["key"] == KEY)
    saved = old_row["runs"][third["policy"]]
    require(saved["status"] == "solved", "old v3 completion unavailable")
    old_check = audit_witness(geometry, plane, saved["colors"])
    witnesses = []
    for order in permutations((2, 3, 4)):
        mapping = dict(zip((1, 2, 3, 4), (1, *order)))
        colors = [mapping[color] for color in saved["colors"]]
        if not matches_anchors(plane, colors, outcome["initial_anchors_by_dart"]):
            continue
        witnesses.append({"permutation": mapping, "colors": colors,
                          "side_10_name": colors[10],
                          "direct_geometry_audit": audit_witness(geometry, plane, colors),
                          "initial_relation_audit": audit_prefix_relations(
                              colors, outcome["propagation_phases"], 0)})
    require(sorted(row["side_10_name"] for row in witnesses) == [3, 4],
            "expected an archived completion for each surviving name")
    require(all(file_sha(ROOT / name) == value for name, value in hashes.items()),
            "source changed during diagnosis")
    require(start_inputs == {path.name: file_sha(path) for path in (V2, V3)},
            "input changed during diagnosis")
    return {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "scope": "one-previously-observed-v2-failure-diagnosis",
            "key": KEY, "aliases": record["aliases"], "face_count": len(plane.faces),
            "input_sha256": start_inputs, "source_sha256": hashes,
            "source_sha256_end": hashes, "sources_unchanged": True,
            "geometry": geometry, "geometry_sha256": digest(geometry),
            "frozen_policy": first["policy"], "frozen_result_sha256": digest(outcome),
            "frozen_proof_replay": check,
            "initial_anchors_by_dart": outcome["initial_anchors_by_dart"],
            "initial_domains": outcome["propagation_phases"][0]["outcome"]["domains"],
            "first_fatal_active_choice_index_one_based": 1,
            "fatal_choice": choice, "true_extendible_names_for_side_10": [3, 4],
            "implicit_inequality_proof": certificate,
            "implicit_inequality_check": proof_check,
            "real_shared_boundary_witnesses": raw_references,
            "archived_witness_policy": third["policy"],
            "archived_witness_colors": saved["colors"],
            "archived_witness_direct_audit": old_check, "prefix_completions": witnesses,
            "production_attempts_added": 0, "color_assignment_oracle_calls": 0,
            "new_candidate_policy_tested": False,
            "limitations": ["A fixed finite implication certificate, not a complete naming rule.",
                            "No claim that all boundary relations can be represented by inequalities.",
                            "No new full-corpus completion count or originality claim."]}


def main():
    """Write only a new report, preserving all frozen evidence."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "choose a new output path")
    require(not sys.flags.optimize, "independent legacy checks require Python without -O")
    report = build_report()
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"output": args.output.name, "sha256": file_sha(args.output),
                      "first_fatal_choice": 1, "true_extendible_names": [3, 4],
                      "proof_check": report["implicit_inequality_check"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

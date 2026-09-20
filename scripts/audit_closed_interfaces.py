"""Independently audit exact coloring through single-vertex block interfaces.

The structural oracle enumerates maximal induced connected vertex subsets
without a cut vertex; it does not implement Tarjan DFS or reuse low-link data.
The feasibility oracle enumerates complete color assignments; it does not call
the frontier solver, use block decomposition, or assume the Four-Color Theorem.
All random inputs and processing orders are saved so the finite scope is clear.
"""

from argparse import ArgumentParser
from datetime import datetime, timezone
from hashlib import sha256
from itertools import combinations, product
import json
from pathlib import Path
from random import Random
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fourcolor.closed_interfaces import (
    _block_forest,
    biconnected_blocks,
    closed_interface_trace,
)

SOURCES = (
    "scripts/audit_closed_interfaces.py",
    "fourcolor/closed_interfaces.py",
    "fourcolor/orbit_frontier.py",
    "fourcolor/frontier_order.py",
)
PROBABILITIES = (0.05, 0.15, 0.30, 0.60, 0.90)


def require(condition, message):
    """Keep validation active under optimized Python; fail before publication."""
    if not condition:
        raise ValueError(message)


def source_hashes():
    """Record only repository-relative source names, never machine paths."""
    return {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}


def input_hash(case):
    """Hash exact graph constraints and the supplied processing order."""
    payload = {key: case[key] for key in ("n", "edges", "order")}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(raw).hexdigest()


def connected(vertices, edges):
    """Check induced connectivity by repeated expansion, independently of DFS."""
    if len(vertices) <= 1:
        return True
    reached = {min(vertices)}
    while True:
        enlarged = reached | {b for a, b in edges if a in reached and b in vertices}
        enlarged |= {a for a, b in edges if b in reached and a in vertices}
        if enlarged == reached:
            return reached == vertices
        reached = enlarged


def independent_blocks(n, edges):
    """Enumerate maximal induced connected sets surviving any vertex deletion.

    This exponential oracle is restricted to the declared small simple graphs.
    K2 qualifies as a bridge block. Singleton blocks are added exactly for
    isolated vertices, matching the production module's block convention.
    Self-loops are checked separately by the full-assignment coloring oracle.
    """
    candidates = []
    for size in range(2, n + 1):
        for vertices in combinations(range(n), size):
            members = set(vertices)
            if connected(members, edges) and all(
                connected(members - {vertex}, edges) for vertex in members
            ):
                candidates.append(members)
    maximal = [members for members in candidates
               if not any(members < other for other in candidates)]
    maximal += [{vertex} for vertex in range(n)
                if not any(vertex in edge for edge in edges)]
    return tuple(sorted(tuple(sorted(members)) for members in maximal))


def audit_structure(case):
    """Check blocks and the interface with the entire already assembled graph."""
    n, edges, order = (case[key] for key in ("n", "edges", "order"))
    expected = independent_blocks(n, edges)
    actual = biconnected_blocks(n, edges)
    require(actual == expected, f"block decomposition differs: {case['id']}")
    preorder, parents, ports = _block_forest(n, actual, order)
    require(sorted(preorder) == list(range(len(actual))),
            f"block forest does not visit every block exactly once: {case['id']}")
    assembled, assembly_checks = set(), []
    for index in preorder:
        overlap = set(actual[index]) & assembled
        expected_overlap = set() if parents[index] is None else {ports[index]}
        require(overlap == expected_overlap,
                f"interface with assembled prefix differs: {case['id']} block {index}")
        if parents[index] is not None:
            require(set(actual[index]) & set(actual[parents[index]]) == {ports[index]},
                    f"parent block does not share exactly its port: {case['id']}")
        assembly_checks.append({"block": index, "parent": parents[index],
                                "port": ports[index], "prefix_overlap": sorted(overlap)})
        assembled.update(actual[index])
    require(assembled == set(range(n)), f"block forest misses vertices: {case['id']}")
    return {"matched": True, "oracle_blocks": expected,
            "actual_blocks": actual, "assembly_checks": assembly_checks}


def assignment_witness(n, edges, palette):
    """Try all full assignments directly, returning the first feasible one."""
    for colors in product(range(palette), repeat=n):
        if all(colors[a] != colors[b] for a, b in edges):
            return list(colors)
    return None


def valid_witness(colors, n, edges, palette):
    """Check palette membership and every original constraint, including loops."""
    return (colors is not None and len(colors) == n
            and all(type(color) is int and 0 <= color < palette for color in colors)
            and all(colors[a] != colors[b] for a, b in edges))


def audit_feasibility(case):
    """Check four palette decisions and both independent and returned witnesses."""
    n, edges, order = (case[key] for key in ("n", "edges", "order"))
    results = []
    for palette in range(1, 5):
        expected = assignment_witness(n, edges, palette)
        actual = closed_interface_trace(n, edges, order, palette)
        feasible = expected is not None
        require(actual["feasible"] == feasible,
                f"feasibility differs: {case['id']} palette {palette}")
        if feasible:
            require(valid_witness(expected, n, edges, palette),
                    f"independent witness invalid: {case['id']} palette {palette}")
            require(valid_witness(actual["one_coloring"], n, edges, palette),
                    f"solver witness invalid: {case['id']} palette {palette}")
        else:
            require(actual["one_coloring"] is None,
                    f"infeasible result contains a witness: {case['id']} palette {palette}")
        results.append({"palette": palette, "matched": True, "feasible": feasible,
                        "oracle_witness": expected, "solver_witness": actual["one_coloring"],
                        "witness_check": "passed" if feasible else "not_applicable"})
    return results


def main():
    """Run a fixed finite audit, then exclusively create a fresh JSON report."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20260920)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    destination = args.output if args.output.is_absolute() else ROOT / args.output
    if destination.exists():
        parser.error("output exists; choose a new path")
    started = perf_counter()
    before, rng = source_hashes(), Random(args.seed)
    exhaustive, sampled, corners = [], [], []
    # The shuffle calls are part of the declared random stream, including n=0.
    for n in range(6):
        possible = list(combinations(range(n), 2))
        for mask in range(1 << len(possible)):
            edges = [edge for i, edge in enumerate(possible) if mask >> i & 1]
            order = list(range(n))
            rng.shuffle(order)
            case = {"id": f"simple-n{n}-mask{mask}", "n": n, "edges": edges,
                    "edge_mask": mask, "order": order}
            case["input_sha256"] = input_hash(case)
            case["structure"] = audit_structure(case)
            case["feasibility"] = audit_feasibility(case)
            exhaustive.append(case)
    for n in range(6, 10):
        possible = list(combinations(range(n), 2))
        for probability in PROBABILITIES:
            for repeat in range(10):
                edges = [edge for edge in possible if rng.random() < probability]
                order = list(range(n))
                rng.shuffle(order)
                case = {"id": f"sample-n{n}-p{probability:.2f}-r{repeat}",
                        "n": n, "edges": edges, "order": order,
                        "edge_probability": probability, "repeat": repeat}
                case["input_sha256"] = input_hash(case)
                case["structure"] = audit_structure(case)
                case["feasibility"] = "not_run_in_this_larger_structural_sample"
                sampled.append(case)
    corner_inputs = (
        ("selfloop_at_star_cutpoint", 6, [(0, 1), (0, 2), (0, 3), (0, 4), (0, 0)]),
        ("disconnected_edges_loop_isolates", 7, [(0, 1), (2, 3), (4, 4)]),
        ("reverse_duplicate_edges_and_isolate", 4, [(0, 1), (1, 0), (1, 2), (2, 1)]),
    )
    for name, n, edges in corner_inputs:
        case = {"id": name, "n": n, "edges": edges, "order": list(reversed(range(n)))}
        case["input_sha256"] = input_hash(case)
        case["feasibility"] = audit_feasibility(case)
        corners.append(case)
    feasibility_rows = [row for case in exhaustive + corners for row in case["feasibility"]]
    summary = {
        "exhaustive_structural_graphs": len(exhaustive),
        "sampled_structural_graphs": len(sampled),
        "structural_graphs": len(exhaustive) + len(sampled),
        "assembly_prefix_contract_graphs": len(exhaustive) + len(sampled),
        "exhaustive_feasibility_cases": 4 * len(exhaustive),
        "corner_feasibility_cases": 4 * len(corners),
        "feasibility_cases": len(feasibility_rows),
        "validated_solver_witnesses": sum(row["feasible"] for row in feasibility_rows),
        "infeasible_results_without_witness": sum(not row["feasible"] for row in feasibility_rows),
    }
    require(summary["structural_graphs"] == 1300 and summary["feasibility_cases"] == 4412,
            "declared audit scope changed")
    require(before == source_hashes(), "an input source changed during the audit")
    report = {
        "schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "passed": True, "random_seed": args.seed, "python_version": sys.version.split()[0],
        "source_sha256": before, "sources_unchanged": True, "summary": summary,
        "elapsed_seconds": perf_counter() - started,
        "scope": {
            "exhaustive_simple_graph_vertex_counts": list(range(6)),
            "one_seeded_shuffled_order_per_graph": True,
            "sampled_vertex_counts": list(range(6, 10)),
            "sampled_edge_probabilities": PROBABILITIES, "samples_per_size_probability": 10,
            "feasibility_palettes": [1, 2, 3, 4],
            "random_stream": "shuffle exhaustive orders, then sample edges and shuffle sampled orders",
            "planarity_filter": "none; correctness is checked on general constraint graphs",
        },
        "oracles": {
            "structure": "enumerate maximal induced connected sets with no cut vertex; add isolates",
            "assembly": "compare each block with the union of all earlier assembled vertices",
            "feasibility": "enumerate complete assignments and check every input inequality",
            "witnesses": "check length, integer palette range and every original edge constraint",
        },
        "evidence_boundary": [
            "Finite correctness audit, not a performance benchmark or general proof.",
            "Only one shuffled order per exhaustive graph; not all vertex permutations.",
            "The 200 larger random cases check structure and assembly interfaces, not solver feasibility.",
            "Loops are ordinary unsatisfiable vertex-coloring constraints, not ignored primal bridges.",
            "No fixed colors, lists, optimal recoloring costs or counting claims are tested.",
        ],
        "exhaustive_cases": exhaustive, "sampled_cases": sampled, "corner_cases": corners,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also protects against a concurrent report appearing.
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"passed": True, "summary": summary,
                      "report_sha256": sha256(destination.read_bytes()).hexdigest(),
                      "bytes": destination.stat().st_size}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

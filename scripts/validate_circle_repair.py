"""Bounded, deterministic experiments for even-layer repair by facial flips.

The scope is declared before execution: all even first layers of wheels with
3..9 rim vertices and prisms with 3..7 rim vertices, under three facial move
families. Every face, including the exterior, is eligible. Exact finite oracles
and explicit stalled states are retained. This script never changes an older
report or calls a naming solver, and it does not claim general termination.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from itertools import combinations
import json
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fourcolor.circle_layers import complete_second_layer
from fourcolor.circle_layer_repair import repair_first_layer
from fourcolor.embedding import PlaneMap
from scripts.circle_repair_oracles import (
    all_even_edge_sets, simple_cycle_edge_sets, oracle_minimum_repair,
)


SOURCE_FILES = (
    "scripts/validate_circle_repair.py", "scripts/circle_repair_oracles.py",
    "fourcolor/circle_layers.py", "fourcolor/circle_layer_repair.py",
    "fourcolor/embedding.py", "outputs/circle-rank-2026-09-20.json",
)
STRATEGIES = ("single-face", "single-or-edge-adjacent-pair", "single-or-any-pair")


def require(condition, message):
    """Retain validation checks when Python is run with optimization."""
    if not condition:
        raise ValueError(message)


def mask_of(selected):
    """Encode a set with stable, graph-local edge IDs."""
    return sum(1 << edge for edge in selected)


def ids_of(mask, size):
    """Decode a compact report mask using the recorded edge order."""
    return [i for i in range(size) if mask >> i & 1]


def independent_even(vertices, edges, selected):
    """Direct degree counting is independent of production validation."""
    degree = {v: 0 for v in vertices}
    for index in selected:
        a, b = edges[index]
        degree[a] += 1
        degree[b] += 1
    return all(value % 2 == 0 for value in degree.values())


def independent_bad_components(vertices, edges, selected):
    """BFS components and count their exact remaining-edge boundary cuts."""
    selected = set(selected)
    adjacency = {v: set() for v in vertices}
    for index in selected:
        a, b = edges[index]
        adjacency[a].add(b)
        adjacency[b].add(a)
    remaining = set(vertices)
    bad = []
    while remaining:
        root = min(remaining)
        remaining.remove(root)
        component, queue = {root}, [root]
        for v in queue:
            for w in sorted(adjacency[v] & remaining):
                remaining.remove(w)
                component.add(w)
                queue.append(w)
        crossing = [i for i, (a, b) in enumerate(edges)
                    if i not in selected and ((a in component) != (b in component))]
        if len(crossing) % 2:
            bad.append({"vertices": sorted(component), "remaining_cut": crossing})
    return bad


def verify_cover(vertices, edges, first, certificate):
    """Check a successful second-layer certificate without its producer's tree."""
    require(certificate["status"] == "completed", "expected a covering certificate")
    second = certificate["second_layer"]
    require(independent_even(vertices, edges, first), "first layer is not even")
    require(independent_even(vertices, edges, second), "second layer is not even")
    require(set(first) | set(second) == set(range(len(edges))), "cover misses an edge")
    return True


def family_graph(kind, rim):
    """Build standard planar wheel/prism families with an explicit embedding."""
    if kind == "wheel":
        vertices = list(range(rim + 1))
        edges = [(i, (i + 1) % rim) for i in range(rim)]
        edges += [(i, rim) for i in range(rim)]
        faces = [sorted([i, rim + i, rim + (i + 1) % rim]) for i in range(rim)]
        faces.append(list(range(rim)))
        coords = {i: (math.cos(2 * math.pi * i / rim),
                      math.sin(2 * math.pi * i / rim)) for i in range(rim)}
        coords[rim] = (0.0, 0.0)
    elif kind == "prism":
        vertices = list(range(2 * rim))
        edges = [(i, (i + 1) % rim) for i in range(rim)]
        edges += [(rim + i, rim + (i + 1) % rim) for i in range(rim)]
        edges += [(i, rim + i) for i in range(rim)]
        faces = [sorted([i, rim + i, 2 * rim + i, 2 * rim + (i + 1) % rim])
                 for i in range(rim)]
        faces += [list(range(rim)), list(range(rim, 2 * rim))]
        coords = {offset + i: (radius * math.cos(2 * math.pi * i / rim),
                              radius * math.sin(2 * math.pi * i / rim))
                  for offset, radius in ((0, 2.0), (rim, 1.0)) for i in range(rim)}
    else:
        raise ValueError("unknown graph family")
    # The rotation is recovered from distinct incident directions in these
    # straight-line planar drawings, and PlaneMap independently checks genus.
    incident = {v: [] for v in vertices}
    for i, (a, b) in enumerate(edges):
        incident[a].append(2 * i)
        incident[b].append(2 * i + 1)
    rotation = {}
    for vertex in vertices:
        x, y = coords[vertex]
        rotation[str(vertex)] = tuple(sorted(incident[vertex], key=lambda dart:
            math.atan2(coords[edges[dart // 2][1 - dart % 2]][1] - y,
                       coords[edges[dart // 2][1 - dart % 2]][0] - x)))
    plane = PlaneMap(tuple((str(a), str(b)) for a, b in edges), rotation)
    actual_faces = {tuple(sorted(dart // 2 for dart in face)) for face in plane.faces}
    require(actual_faces == {tuple(face) for face in faces}, "declared facial cycles differ")
    incidence = Counter(i for face in faces for i in face)
    require(all(incidence[i] == 2 for i in range(len(edges))), "edge lacks two faces")
    require(len(vertices) - len(edges) + len(faces) == 2, "Euler check failed")
    return {"key": f"{kind}-rim{rim}", "family": kind, "rim": rim,
            "vertices": vertices, "edges": edges, "faces": faces,
            "rotation": rotation, "plane_map_verified": True,
            "outer_face_index": rim, "cycle_rank": len(edges) - len(vertices) + 1}


def cycle_space_from_faces(graph, maximum_states=4096):
    """Enumerate the whole cycle space, certifying dimension against E-V+1.

    Spanning by all facial boundaries is checked by both evenness and the exact
    number 2**beta of distinct vectors. This avoids a 2**m edge-subset scan on a
    graph with many subdivisions while keeping the finite oracle transparent.
    """
    require(2 ** graph["cycle_rank"] <= maximum_states, "cycle-space bound exceeded")
    vectors = {0}
    for face in graph["faces"]:
        mask = mask_of(face)
        vectors |= {value ^ mask for value in tuple(vectors)}
    require(len(vectors) == 2 ** graph["cycle_rank"], "facial vectors have wrong rank")
    for value in vectors:
        require(independent_even(graph["vertices"], graph["edges"],
                                 ids_of(value, len(graph["edges"]))),
                "facial span contains an odd vector")
    return sorted(vectors)


def move_candidates(graph, strategy):
    """Record candidate facial provenance; reject neither nonadjacent pairs nor outer face."""
    faces = graph["faces"]
    records = [{"face_indices": [i], "edges": list(face)} for i, face in enumerate(faces)]
    if strategy != "single-face":
        for i, j in combinations(range(len(faces)), 2):
            shared = set(faces[i]) & set(faces[j])
            if strategy == "single-or-edge-adjacent-pair" and not shared:
                continue
            records.append({"face_indices": [i, j],
                            "edges": sorted(set(faces[i]) ^ set(faces[j]))})
    # Complementary facial choices can represent the same edge vector. The
    # production API requires distinct moves; retain all equivalent provenance.
    unique = {}
    for record in records:
        key = tuple(record["edges"])
        if key not in unique:
            unique[key] = {**record, "equivalent_face_choices": []}
        unique[key]["equivalent_face_choices"].append(record["face_indices"])
    return list(unique.values())


def tiny_direct_cover_check():
    """Compare the cut criterion with exhaustive A/B coverage on every n<=4 graph."""
    graph_count = states = pairs = 0
    for n in range(5):
        possible = list(combinations(range(n), 2))
        for graph_mask in range(1 << len(possible)):
            edges = [edge for i, edge in enumerate(possible) if graph_mask >> i & 1]
            layers = all_even_edge_sets(range(n), edges)
            full = set(range(len(edges)))
            graph_count += 1
            for first in layers:
                feasible = False
                for second in layers:
                    pairs += 1
                    feasible |= set(first) | set(second) == full
                cut_passes = not independent_bad_components(range(n), edges, first)
                require(feasible == cut_passes, "direct coverage and cut criterion disagree")
                require(complete_second_layer(range(n), edges, first)["status"] ==
                        ("completed" if feasible else "obstructed"), "producer differs")
                states += 1
    return {"passed": True, "simple_graphs": graph_count, "even_first_layers": states,
            "ordered_even_A_B_pairs_examined": pairs, "maximum_vertices": 4,
            "includes_non_bridgeless_graphs": True,
            "method": "direct-even-A/even-B-union-versus-independent-exact-cut-and-producer"}


def source_hashes():
    """Hash exact implementation and prior geometry inputs for provenance."""
    return {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def audit_compact_run(graph, initial_mask, candidates, result, q_by_mask, optimum):
    """Audit local scores against independent all-state q values and compact them."""
    edge_count = len(graph["edges"])
    current = initial_mask
    moves = [mask_of(record["edges"]) for record in candidates]
    q_trace = [q_by_mask[current]]
    selected_indices = []
    for step in result["steps"]:
        require(mask_of(step["first_layer_before"]) == current, "trace skips a state")
        scores = []
        for index, move in enumerate(moves):
            expected_q = q_by_mask[current ^ move]
            require(step["candidate_scores"][index]["q_after"] == expected_q,
                    "production candidate q differs from independent cut oracle")
            scores.append((expected_q, move.bit_count(), move.bit_count(),
                           ids_of(move, edge_count), index))
        best = min(row for row in scores if row[0] < q_by_mask[current])
        require(best[-1] == step["selected_candidate_index"], "greedy tie-break differs")
        current ^= moves[best[-1]]
        require(mask_of(step["first_layer_after"]) == current, "trace XOR differs")
        selected_indices.append(best[-1])
        q_trace.append(q_by_mask[current])
    require(current == mask_of(result["final_first_layer"]), "final layer differs")
    require(q_by_mask[current] == result["final_obstruction_count"], "final q differs")
    completed = result["status"] == "completed"
    if completed:
        verify_cover(graph["vertices"], graph["edges"], result["final_first_layer"],
                     result["completion"])
    else:
        require(q_by_mask[current] > 0, "a feasible layer was called stalled")
        for index, move in enumerate(moves):
            q_next = q_by_mask[current ^ move]
            require(q_next >= q_by_mask[current], "stalled layer has an improving move")
            require(result["terminal_candidate_scores"][index]["q_after"] == q_next,
                    "terminal score differs")
    return {
        "initial_mask": initial_mask, "final_mask": current,
        "status": result["status"], "q_trace": q_trace,
        "selected_candidate_indices": selected_indices,
        "steps": result["step_count"],
        "cumulative_flip_cost": result["cumulative_flip_cost"],
        "net_changed_cost": result["final_changed_cost"],
        "global_minimum_net_cost": optimum,
        "net_optimality_gap": result["final_changed_cost"] - optimum if completed else None,
        "cumulative_minus_minimum_net_cost": result["cumulative_flip_cost"] - optimum
        if completed else None,
    }


def analyze_family(graph):
    """Run the three declared strategies on every even layer of one plane graph."""
    vertices, edges = graph["vertices"], graph["edges"]
    masks = cycle_space_from_faces(graph)
    q = {mask: len(independent_bad_components(vertices, edges, ids_of(mask, len(edges))))
         for mask in masks}
    good = [mask for mask in masks if q[mask] == 0]
    require(bool(good), "the declared planar family has no finite two-layer solution")
    optimum = {mask: min((mask ^ target).bit_count() for target in good) for mask in masks}
    strategies = {}
    for strategy in STRATEGIES:
        candidates = move_candidates(graph, strategy)
        rows = []
        for mask in masks:
            result = repair_first_layer(vertices, edges, ids_of(mask, len(edges)),
                                        [record["edges"] for record in candidates])
            rows.append(audit_compact_run(graph, mask, candidates, result, q, optimum[mask]))
        completed = [row for row in rows if row["status"] == "completed"]
        initially_bad = [row for row in rows if row["q_trace"][0]]
        repaired_bad = [row for row in initially_bad if row["status"] == "completed"]
        strategies[strategy] = {
            "candidate_count": len(candidates), "candidates": candidates,
            "summary": {
                "all_even_starts": len(rows), "initially_feasible": len(good),
                "initially_obstructed": len(initially_bad),
                "completed": len(completed), "repaired_obstructed": len(repaired_bad),
                "stalled": len(rows) - len(completed),
                "success_rate_all_starts": len(completed) / len(rows),
                "repair_rate_obstructed_starts": len(repaired_bad) / len(initially_bad)
                if initially_bad else None,
                "completed_at_global_minimum_net_cost": sum(row["net_optimality_gap"] == 0
                                                            for row in completed),
                "maximum_net_optimality_gap": max((row["net_optimality_gap"] for row in completed),
                                                  default=None),
                "maximum_cumulative_minus_minimum_net_cost": max(
                    (row["cumulative_minus_minimum_net_cost"] for row in completed), default=None),
            },
            "starts": rows,
        }
    print(json.dumps({"graph": graph["key"], "states": len(masks), "strategies": {
        name: item["summary"]["stalled"] for name, item in strategies.items()}}), flush=True)
    return {**graph, "enumerated_even_layers": len(masks), "feasible_even_layers": len(good),
            "oracle": {"method": "full-facial-span-cycle-space-plus-independent-exact-cut",
                       "criterion_crosscheck": "all-n<=4-simple-graphs-direct-A/B-coverage",
                       "minimum_cost_object": "Hamming-distance-from-initial-A-to-any-feasible-even-A",
                       "contains_all_even_layers_verified_by_rank": True},
            "strategies": strategies}


def show_cases():
    """Retain complete witness inputs, plateau scores, and exact finite optima."""
    wheel = family_graph("wheel", 8)
    vertices, edges = wheel["vertices"], wheel["edges"]
    first = [0, 1, 4, 5, 8, 10, 12, 14]
    move1, move2 = [2, 10, 11], [6, 14, 15]
    intermediate = sorted(set(first) ^ set(move1))
    final = sorted(set(intermediate) ^ set(move2))
    trace = [len(independent_bad_components(vertices, edges, layer))
             for layer in (first, intermediate, final)]
    require(trace == [2, 2, 0], "wheel plateau trace differs")
    cycles = simple_cycle_edge_sets(vertices, edges)
    scores = [{"edges": list(cycle), "q_after": len(independent_bad_components(
        vertices, edges, set(first) ^ set(cycle)))} for cycle in cycles]
    require(len(cycles) == 57 and min(row["q_after"] for row in scores) == 2,
            "wheel simple-cycle obstruction differs")
    optimal = oracle_minimum_repair(vertices, edges, first)
    require(optimal["cost"] == 6 and optimal["tied_optima"] == 4, "wheel oracle differs")
    results = {}
    for strategy in STRATEGIES:
        candidates = move_candidates(wheel, strategy)
        result = repair_first_layer(vertices, edges, first, [item["edges"] for item in candidates])
        results[strategy] = {
            "candidate_q_histogram": dict(sorted(Counter(len(independent_bad_components(
                vertices, edges, set(first) ^ set(item["edges"]))) for item in candidates).items())),
            "result": result,
        }
    require(results[STRATEGIES[0]]["result"]["status"] == "stalled", "single faces unexpectedly solve")
    require(results[STRATEGIES[1]]["result"]["status"] == "stalled", "adjacent pairs unexpectedly solve")
    require(results[STRATEGIES[2]]["result"]["status"] == "completed", "two arbitrary faces fail")
    completion = complete_second_layer(vertices, edges, final)
    verify_cover(vertices, edges, final, completion)
    wheel_show = {
        **wheel, "initial_first_layer": first, "first_move": move1,
        "intermediate_first_layer": intermediate, "second_move": move2,
        "final_first_layer": final, "q_trace": trace,
        "first_face_index": 2, "second_face_index": 6,
        "move_faces_share_edges": False, "move_faces_shared_vertices": [8],
        "net_changed_edges": sorted(set(first) ^ set(final)), "net_cost": 6,
        "completion": completion, "independent_minimum_repair": optimal,
        "all_simple_cycle_scores": scores,
        "all_simple_cycle_q_histogram": dict(sorted(Counter(row["q_after"] for row in scores).items())),
        "strategy_results": results,
    }
    prism = family_graph("prism", 5)
    first = list(range(10))
    move = [0, 5, 10, 11]
    final = sorted(set(first) ^ set(move))
    completion = complete_second_layer(prism["vertices"], prism["edges"], final)
    verify_cover(prism["vertices"], prism["edges"], final, completion)
    prism_show = {
        **prism, "initial_first_layer": first, "move": move, "final_first_layer": final,
        "q_trace": [2, 0], "completion": completion,
        "independent_minimum_repair": oracle_minimum_repair(prism["vertices"], prism["edges"], first),
    }
    require(prism_show["independent_minimum_repair"]["cost"] == 4, "prism oracle differs")
    return {"wheel8": wheel_show, "prism5": prism_show}


def original_geometry_cases():
    """Recheck the eight earlier drawings, explicitly removing virtual edges and bridges."""
    original = json.loads((ROOT / "outputs/circle-rank-2026-09-20.json").read_text(encoding="utf-8"))
    results = []
    for case in original["results"]:
        geometry = case["geometry"]
        bridges = set(geometry["real_bridge_edge_ids"])
        kept = [i for i, edge in enumerate(geometry["edges"])
                if not edge["virtual"] and i not in bridges]
        old_to_new = {old: new for new, old in enumerate(kept)}
        vertices = list(range(len(geometry["vertices"])))
        edges = [(geometry["edges"][i]["a"], geometry["edges"][i]["b"]) for i in kept]
        source_first = case["contour_edge_ids"]["A_all_pink"]
        first = sorted(old_to_new[i] for i in source_first if i in old_to_new)
        result = repair_first_layer(vertices, edges, first, [])
        require(result["status"] == "completed" and result["step_count"] == 0,
                "an original specified layer unexpectedly needs repair")
        verify_cover(vertices, edges, first, result["completion"])
        results.append({"key": case["key"], "blue_mask": case["blue_mask"],
                        "vertices": vertices, "edges": edges,
                        "new_edge_id_to_original_geometry_edge_id": kept,
                        "excluded_real_bridges": sorted(bridges),
                        "excluded_virtual_edge_ids": [i for i, edge in enumerate(geometry["edges"])
                                                      if edge["virtual"]],
                        "source_first_layer": source_first, "first_layer": first,
                        "result": result})
    require(len(results) == 8, "the original corpus must contain all eight masks")
    return results


def subdivided_prism(rim, length):
    """Replace every base edge by a path, retaining explicit base-to-segment IDs."""
    base = family_graph("prism", rim)
    vertices = list(base["vertices"])
    edges, paths = [], []
    for a, b in base["edges"]:
        middle = []
        for _ in range(length - 1):
            middle.append(len(vertices))
            vertices.append(len(vertices))
        chain = [a] + middle + [b]
        path = []
        for u, v in zip(chain, chain[1:]):
            path.append(len(edges))
            edges.append((u, v))
        paths.append(path)
    faces = [sorted(index for old in face for index in paths[old]) for face in base["faces"]]
    first = [index for old in range(2 * rim) for index in paths[old]]
    return {"key": f"prism-rim{rim}-uniform-subdivision{length}", "vertices": vertices,
            "edges": edges, "faces": faces, "initial_first_layer": first,
            "base_edge_to_subdivision_edge_ids": paths,
            "cycle_rank": rim + 1, "rim": rim, "subdivision_length": length}


def prism_theorem_checks():
    """Check declared prism/subdivision bounds and a few deterministic weight cases."""
    rows, weighted = [], []
    for rim in range(3, 12):
        for length in (1, 2, 5, 10):
            graph = subdivided_prism(rim, length)
            vertices, edges, first = graph["vertices"], graph["edges"], graph["initial_first_layer"]
            q_initial = len(independent_bad_components(vertices, edges, first))
            require(q_initial == (2 if rim % 2 else 0), "prism initial parity differs")
            lateral_checks = []
            for i in range(rim):
                changed = sorted(set(first) ^ set(graph["faces"][i]))
                completion = complete_second_layer(vertices, edges, changed)
                verify_cover(vertices, edges, changed, completion)
                require(not independent_bad_components(vertices, edges, changed),
                        "a lateral prism flip failed")
                lateral_checks.append({"face_index": i, "changed_edges": graph["faces"][i],
                                       "q_after": 0, "unit_cost": len(graph["faces"][i])})
            expected_minimum = 4 * length if rim % 2 else 0
            oracle = oracle_minimum_repair(vertices, edges, first) if len(edges) <= 20 else None
            if oracle:
                require(oracle["cost"] == expected_minimum, "prism minimum cost differs")
            rows.append({**graph, "initial_q": q_initial, "lateral_checks": lateral_checks,
                         "expected_global_minimum_net_cost": expected_minimum,
                         "minimum_cost_basis": "full-edge-subset-oracle" if oracle else
                         "analytical-prism-lemma-not-an-exhaustive-optimality-test",
                         "independent_minimum_repair": oracle})
    for rim in (3, 5):
        graph = subdivided_prism(rim, 1)
        for offset in (0, 3, 7):
            weights = [1 + (7 * i + offset) % 11 for i in range(len(graph["edges"]))]
            face_costs = [sum(weights[i] for i in graph["faces"][face]) for face in range(rim)]
            oracle = oracle_minimum_repair(graph["vertices"], graph["edges"],
                                           graph["initial_first_layer"], costs=weights)
            require(oracle["cost"] == min(face_costs), "weighted prism optimum differs")
            result = repair_first_layer(graph["vertices"], graph["edges"],
                                        graph["initial_first_layer"], graph["faces"][:rim],
                                        edge_costs=weights)
            require(result["status"] == "completed" and result["final_changed_cost"] == oracle["cost"],
                    "weighted facial repair differs from finite optimum")
            weighted.append({"graph_key": graph["key"], "weights": weights,
                             "weight_formula": f"1 + (7 * edge_id + {offset}) % 11",
                             "lateral_face_costs": face_costs,
                             "independent_minimum_repair": oracle, "result": result})
    return {"uniform_subdivisions": rows, "positive_integer_weight_cases": weighted,
            "subdivision_cases": len(rows), "weighted_cases": len(weighted),
            "scope": "prism rim3..11, uniform edge path lengths 1,2,5,10; weights on rim3,5 L1"}


def main():
    """Run declared finite checks and write a fresh report only after they pass."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="outputs/circle-repair-2026-09-20.json")
    args = parser.parse_args()
    destination = Path(args.output)
    if not destination.is_absolute():
        destination = ROOT / destination
    require(not destination.exists(), "refusing to overwrite an existing validation report")
    before = source_hashes()
    tiny = tiny_direct_cover_check()
    families = [analyze_family(family_graph("wheel", rim)) for rim in range(3, 10)]
    families += [analyze_family(family_graph("prism", rim)) for rim in range(3, 8)]
    cases = show_cases()
    original = original_geometry_cases()
    prisms = prism_theorem_checks()
    require(before == source_hashes(), "an input source changed during validation")
    totals = {}
    for strategy in STRATEGIES:
        summaries = [graph["strategies"][strategy]["summary"] for graph in families]
        totals[strategy] = {name: sum(row[name] for row in summaries) for name in
                           ("all_even_starts", "initially_feasible", "initially_obstructed",
                            "completed", "repaired_obstructed", "stalled",
                            "completed_at_global_minimum_net_cost")}
    report = {
        "schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "passed": True, "source_sha256": before, "sources_unchanged": True,
        "random_seed": None, "randomness": "None; deterministic exhaustive finite states",
        "predeclared_scope": {
            "wheel_rim_sizes": list(range(3, 10)), "prism_rim_sizes": list(range(3, 8)),
            "starts": "all even first edge layers of each listed graph",
            "facial_moves": "all faces including the unbounded exterior; duplicate edge masks deduplicated",
            "strategies": list(STRATEGIES), "costs": "unit edge-flip weights except six declared prism weight cases",
            "maximum_cycle_space_states_per_graph": 4096,
            "subset_oracle_maximum_edges": 20,
            "planarity": "all family graphs have explicit checked genus-zero PlaneMap rotations",
            "excluded": "no random graph sampling, no unclassified graphs, no old naming-score benchmark",
        },
        "evidence_boundary": [
            "Finite rates apply only to these families, sizes, initial states and move sets.",
            "Every stalled state is retained; a stall is not impossibility of a different repair.",
            "The minimum repair oracle shares the proved cut criterion but uses independent code.",
            "Tiny exhaustive A/B coverage crosschecks that shared criterion without using it.",
            "Net changed edges and cumulative flip cost are different objectives.",
            "No general termination or global optimality theorem is inferred from observed success.",
        ],
        "tiny_direct_cover_check": tiny, "family_totals": totals, "families": families,
        "show_cases": cases, "original_eight_geometry_cases": original,
        "prism_theorem_checks": prisms,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"passed": True, "output": str(destination.relative_to(ROOT)),
                      "family_totals": totals, "bytes": destination.stat().st_size}), flush=True)


if __name__ == "__main__":
    main()

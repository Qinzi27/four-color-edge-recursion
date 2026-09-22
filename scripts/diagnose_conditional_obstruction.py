"""Diagnose a conditional planar obstruction, not a reached policy failure.

The graph is an odd bipyramid plus one leaf: nonadjacent U,V both meet every
vertex of C_(2k+1), and z is adjacent only to t0. Every four-coloring has U=V:
if their colors differ, the odd rim has only two remaining colors. Under
S={U=2,z=1}, a proposed V=1 therefore destroys all extensions. Nevertheless
V=z is possible without S, so even a complete *unconditional* pair-inequality
oracle cannot reject this equality. The current shared-triangle query indeed
returns inconclusive. This is a limitation of context-free pair questions,
not evidence that the current geometry-driven policy reaches these anchors.
The reliable global equality U=V WOULD resolve this example. It is therefore
not a counterexample to using all unconditional equalities and inequalities.

The graph rotation certifies an abstract planar embedding. No mother-line
drawing, rectangular-frame initialization, or actual policy run is supplied.
Default output is an isolated, uniquely named exploratory report. Exact
oracles are used only after the fixed proposal, never to choose or repair it.
"""

from argparse import ArgumentParser
from datetime import datetime, timezone
from hashlib import sha256
from itertools import combinations, product
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.relation_names import _domains, relation_closure
from fourcolor.structural_name_relations import refute_same_name
from scripts.exact_extendibility_oracle import solve_exact, verify_exact_result


def require(condition, message):
    """Retain checks under optimized Python."""
    if not condition:
        raise AssertionError(message)


def build_obstruction(cycle_size=5):
    """Build a labeled odd bipyramid and a combinatorial sphere embedding."""
    if type(cycle_size) is not int or cycle_size < 5 or cycle_size % 2 == 0:
        raise ValueError("cycle_size must be an odd integer at least five")
    rim = list(range(2, cycle_size + 2))
    leaf = cycle_size + 2
    edges = [(apex, vertex) for apex in (0, 1) for vertex in rim]
    edges += [(rim[i], rim[(i + 1) % cycle_size]) for i in range(cycle_size)]
    edges.append((leaf, rim[0]))
    rotation = {0: rim[:], 1: list(reversed(rim)), leaf: [rim[0]]}
    for i, vertex in enumerate(rim):
        rotation[vertex] = [0, rim[(i - 1) % cycle_size], 1, rim[(i + 1) % cycle_size]]
    # Insert the leaf into one actual angular sector at t0. A pendant edge
    # does not change the number of faces of the constraint-graph embedding.
    rotation[rim[0]].append(leaf)
    return {"n": cycle_size + 3, "cycle_size": cycle_size,
            "labels": ["U", "V"] + [f"t{i}" for i in range(cycle_size)] + ["z"],
            "edges": sorted(tuple(sorted(edge)) for edge in edges),
            "rotation_by_vertex": rotation,
            "anchors": {0: 2, leaf: 1}, "proposal": {"vertex": 1, "color": 1},
            "same_name_query": [1, leaf]}


def audit_rotation(problem):
    """Replay all oriented constraint edges and check a connected sphere map.

    This rotation belongs to the *constraint graph*, not to a primal drawing
    with whole-line scheduling metadata. Its faces certify only planarity.
    """
    edges, rotation = problem["edges"], problem["rotation_by_vertex"]
    adjacent = {v: set() for v in range(problem["n"])}
    for u, v in edges:
        adjacent[u].add(v)
        adjacent[v].add(u)
    require(set(rotation) == set(adjacent), "rotation vertex coverage differs")
    for vertex, neighbors in adjacent.items():
        require(len(rotation[vertex]) == len(neighbors)
                and set(rotation[vertex]) == neighbors, "rotation incidence differs")
    reached, pending = {0}, [0]
    while pending:
        for neighbor in adjacent[pending.pop()]:
            if neighbor not in reached:
                reached.add(neighbor)
                pending.append(neighbor)
    require(len(reached) == problem["n"], "constraint graph disconnected")
    remaining = {(u, v) for edge in edges for u, v in (edge, tuple(reversed(edge)))}
    faces = []
    while remaining:
        start = current = min(remaining)
        face = []
        while current in remaining:
            remaining.remove(current)
            face.append(current)
            u, v = current
            around = rotation[v]
            current = (v, around[(around.index(u) - 1) % len(around)])
        require(current == start, "face walk did not close at its start")
        faces.append(face)
    characteristic = problem["n"] - len(edges) + len(faces)
    require(characteristic == 2, "rotation is not a sphere embedding")
    return {"passed": True, "vertices": problem["n"], "edges": len(edges),
            "faces": faces, "euler_characteristic": characteristic,
            "scope": "abstract constraint-graph planar embedding only"}


def certify_common_odd_cycle(n, edges, first, second, cycle):
    """Validate a supplied odd common-neighbor cycle as a global EQ witness.

    If the two named vertices had different colors, their common neighbors
    could use only the other two. An odd cycle is not two-colorable, so the
    vertices must have equal colors in every proper four-coloring. This is a
    diagnostic certificate, not a new rule inserted into the current policy.
    """
    if (type(n) is not int or n < 5 or type(first) is not int or type(second) is not int
            or first == second or not 0 <= first < n or not 0 <= second < n):
        raise ValueError("two distinct known vertices and a valid graph size are required")
    cycle = tuple(cycle)
    if (len(cycle) < 3 or len(cycle) % 2 == 0
            or any(type(v) is not int or not 0 <= v < n for v in cycle)
            or len(set(cycle)) != len(cycle) or first in cycle or second in cycle):
        raise ValueError("a simple odd cycle disjoint from the two vertices is required")
    raw = {frozenset(edge) for edge in edges}
    cycle_edges = [(cycle[i], cycle[(i + 1) % len(cycle)]) for i in range(len(cycle))]
    spokes = [(apex, v) for apex in (first, second) for v in cycle]
    if any(frozenset(edge) not in raw for edge in cycle_edges + spokes):
        raise ValueError("the odd cycle or a common-neighbor spoke is missing")
    return {"status": "proved_equal", "palette_size": 4, "pair": (first, second),
            "odd_cycle": cycle, "cycle_edges": cycle_edges, "common_neighbor_edges": spokes,
            "proof": "different apex colors leave two colors for an odd common-neighbor cycle",
            "scope": "elementary unconditional equality certificate; diagnostic only; policy unchanged"}


def relation_input(problem):
    """Encode raw edges and literal commitments before using the tested closure."""
    n, anchors = problem["n"], problem["anchors"]
    edges = set(problem["edges"])
    domains = [[anchors[v]] if v in anchors else [1, 2, 3, 4] for v in range(n)]
    return [[sum(1 << (4 * (a - 1) + b - 1)
                 for a in domains[i] for b in domains[j]
                 if (a == b if i == j else a != b if tuple(sorted((i, j))) in edges else True))
             for j in range(n)] for i in range(n)]


def audit_hall_stability(problem, domains):
    """Check all clique-subset Hall tests directly on the declared domains.

    No clique from a logical inequality is introduced. This certifies that
    the current genuine-clique Hall rules have no further deletion here.
    """
    edges = set(problem["edges"])
    checked = 0
    for size in range(2, 5):
        for clique in combinations(range(problem["n"]), size):
            if not all(tuple(sorted(pair)) in edges for pair in combinations(clique, 2)):
                continue
            for subset_size in range(1, size + 1):
                for subset in combinations(clique, subset_size):
                    union = set().union(*(set(domains[v]) for v in subset))
                    require(len(union) >= len(subset), "Hall contradiction already visible")
                    if len(union) == len(subset):
                        require(all(not (set(domains[v]) & union) for v in clique if v not in subset),
                                "Hall rule still has a possible deletion")
                    checked += 1
    return {"passed": True, "clique_subsets_checked": checked, "further_deletions": 0}


def diagnose(cycle_size=5):
    """Run a bounded exhaustive diagnosis whose fixed input precedes all checks."""
    if cycle_size > 9:
        raise ValueError("diagnostic full enumeration is limited to odd cycle sizes 5,7,9")
    problem = build_obstruction(cycle_size)
    embedding = audit_rotation(problem)
    n, edges, anchors = problem["n"], problem["edges"], problem["anchors"]
    before = solve_exact(n, edges, anchors)
    after_anchors = {**anchors, 1: 1}
    after = solve_exact(n, edges, after_anchors)
    equality_anchors = {1: 1, cycle_size + 2: 1}
    unconditioned_same = solve_exact(n, edges, equality_anchors)
    exact_audits = [verify_exact_result(n, edges, fixed, result)
                    for fixed, result in ((anchors, before), (after_anchors, after),
                                          (equality_anchors, unconditioned_same))]
    require((before["status"], after["status"], unconditioned_same["status"])
            == ("sat", "unsat", "sat"), "exact statuses differ from the claimed obstruction")
    propagation = relation_closure(relation_input(problem))
    domains = _domains(propagation["relations"])
    require(not propagation["conflict"] and domains[1] == [1, 2],
            "the tested propagation no longer leaves the unsafe candidate")
    hall = audit_hall_stability(problem, domains)
    query = refute_same_name(n, edges, *problem["same_name_query"])
    require(query["status"] == "inconclusive", "the tested query no longer is inconclusive")
    same_singletons = [v for v, domain in enumerate(domains) if v != 1 and domain == [1]]
    require(same_singletons == [cycle_size + 2], "additional same-name query would be required")
    equality = certify_common_odd_cycle(n, edges, 0, 1, range(2, cycle_size + 2))

    # Full product enumeration is independent of the MRV solver and of the
    # propagation's masks. No color symmetry reduction or pruning is used.
    free = [v for v in range(n) if v not in anchors]
    target_count, counts_by_v, checked = 0, {c: 0 for c in (1, 2, 3, 4)}, 0
    for values in product((1, 2, 3, 4), repeat=len(free)):
        checked += 1
        coloring = {**anchors, **dict(zip(free, values))}
        if any(coloring[u] == coloring[v] for u, v in edges):
            continue
        target_count += 1
        counts_by_v[coloring[1]] += 1
        # Sound filtering must retain every unary and binary projection.
        for i in range(n):
            for j in range(n):
                bit = 1 << (4 * (coloring[i] - 1) + coloring[j] - 1)
                require(propagation["relations"][i][j] & bit, "closure deleted an actual solution")
    require(target_count == 2 * (2 ** cycle_size - 2) // 3
            and counts_by_v[1] == counts_by_v[3] == counts_by_v[4] == 0,
            "complete assignment enumeration differs from odd-cycle formula")
    sources = ("scripts/diagnose_conditional_obstruction.py", "scripts/exact_extendibility_oracle.py",
               "fourcolor/structural_name_relations.py", "fourcolor/relation_names.py")
    return {"schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "all_passed": True, "experiment_kind": "exploratory_abstract_conditional_obstruction",
            "problem": problem, "embedding_audit": embedding,
            "before_commit": before, "after_commit": after,
            "unconditional_same_name_witness": unconditioned_same,
            "exact_audits": exact_audits,
            "propagation": propagation, "domains_before_commit": domains,
            "hall_stability": hall, "same_name_query": query,
            "global_equality_certificate": equality,
            "complete_enumeration": {"assignments_checked": checked, "target_count": target_count,
                                     "targets_by_proposed_vertex_color": counts_by_v},
            "source_sha256": {path: sha256((ROOT / path).read_bytes()).hexdigest() for path in sources},
            "current_policy_reachability": "not_established",
            "geometric_mother_drawing": "not_supplied",
            "claims_not_made": ["failure reached by current policy", "failure of a full drawing run",
                                "novelty of the graph or implication", "general impossibility of conditional reasoning",
                                "insufficiency of all unconditional equalities plus inequalities"]}


def main():
    """Write only a new exploratory report, preserving all earlier artifacts."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--cycle-size", type=int, default=5, choices=(5, 7, 9))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = args.output or ROOT / "outputs" / "_local" / f"conditional-obstruction-{stamp}.json"
    if path.exists():
        parser.error("output exists; choose a new filename")
    report = diagnose(args.cycle_size)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"report": path.name, "all_passed": True,
                      "target_count": report["complete_enumeration"]["target_count"],
                      "current_policy_reachability": "not_established"}))


if __name__ == "__main__":
    main()

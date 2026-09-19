"""Independently validate fixed-target atomic renaming and profile old examples.

Core scheduling never searches for a colouring. This research script DOES
enumerate small colourings and legal partial states, with explicit size limits.
It cannot establish novelty, general four-colour construction, or full-history
success. Default outputs are unique and existing reports cannot be overwritten.
"""

from argparse import ArgumentParser
from datetime import datetime, timezone
from hashlib import sha256
from itertools import combinations, product
import json
from pathlib import Path
import platform
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fourcolor.strip_chain import SideClass, StripChain, split_strip_chain
from fourcolor.target_renaming import plan_target_renaming, required_atomic_batch, verify_schedule


def require(condition, message):
    """Keep scientific checks enabled even under python -O."""
    if not condition:
        raise AssertionError(message)


def proper(edges, symbols):
    """Direct endpoint comparison, independent of dependency/SCC algorithms."""
    return all(symbols[u] != symbols[v] for u, v in edges)


def partial_state_oracle(edges, initial, target, weights):
    """Solve minimax batching over every legal partial update state directly.

    Vertices use integer coordinates in this oracle. No dependency arcs or
    strong components are used. A transition updates any nonempty batch at
    once; only its endpoints need be proper. Both unit and additive costs are
    optimized separately over all such monotone paths through the subset cube.
    """
    changed = [v for v in range(len(initial)) if initial[v] != target[v]]
    count = 1 << len(changed)
    legal, members, batch_weight = [], [], []
    for mask in range(count):
        chosen = {v for j, v in enumerate(changed) if mask & (1 << j)}
        state = tuple(target[v] if v in chosen else initial[v] for v in range(len(initial)))
        legal.append(proper(edges, state))
        members.append(chosen)
        batch_weight.append(sum(weights[v] for v in chosen))
    size_dp, weight_dp = [float("inf")] * count, [float("inf")] * count
    size_dp[0] = weight_dp[0] = 0
    for mask in range(1, count):
        if not legal[mask]:
            continue
        # Every strict subset is considered, not just one-vertex predecessors.
        predecessor = (mask - 1) & mask
        while True:
            if legal[predecessor]:
                added = mask ^ predecessor
                size_dp[mask] = min(size_dp[mask], max(size_dp[predecessor], len(members[added])))
                weight_dp[mask] = min(weight_dp[mask], max(weight_dp[predecessor], batch_weight[added]))
            if predecessor == 0:
                break
            predecessor = (predecessor - 1) & mask
    return changed, legal, members, size_dp[-1], weight_dp[-1]


def exhaustive_small_graphs():
    """All 75 labelled simple graphs with 1..4 vertices, using three colours."""
    graphs = pairs = subsets = immediate_queries = 0
    for n in range(1, 5):
        possible_edges = tuple(combinations(range(n), 2))
        for edge_mask in range(1 << len(possible_edges)):
            edges = tuple(e for i, e in enumerate(possible_edges) if edge_mask & (1 << i))
            graphs += 1
            colours = [c for c in product(range(3), repeat=n) if proper(edges, c)]
            vertices = tuple(f"s{v}" for v in range(n))
            named_edges = tuple((vertices[u], vertices[v]) for u, v in edges)
            weights = tuple(v % 3 for v in range(n))  # Includes zero-cost side classes.
            for initial in colours:
                for target in colours:
                    plan = plan_target_renaming(named_edges, dict(zip(vertices, initial)),
                                                dict(zip(vertices, target)),
                                                weights=dict(zip(vertices, weights)))
                    changed, legal, members, width, weighted_width = partial_state_oracle(
                        edges, initial, target, weights)
                    require(plan.minimum_max_batch_size == width, "SCC size disagrees with subset-path oracle")
                    require(plan.minimum_max_batch_weight == weighted_width, "weighted SCC bound disagrees")
                    require(verify_schedule(plan, plan.batches), "returned batches fail endpoint verification")
                    arcs = tuple((vertices.index(u), vertices.index(v)) for u, v in plan.dependencies)
                    for is_legal, done in zip(legal, members):
                        closed = all(u not in done or v in done for u, v in arcs)
                        require(is_legal == closed, "mixed-state iff closure failed")
                    # For every seed from the initial state, intersect ALL legal
                    # updated sets containing it; a least set must itself be legal.
                    for seed in changed:
                        candidates = [done for valid, done in zip(legal, members) if valid and seed in done]
                        least = set.intersection(*candidates)
                        actual = set(required_atomic_batch(plan, (vertices[seed],)))
                        require(actual == {vertices[v] for v in least}, "immediate closure is not least")
                        require(any(valid and done == least for valid, done in zip(legal, members)),
                                "intersection is not a feasible partial update")
                        immediate_queries += 1
                    pairs += 1
                    subsets += len(legal)
    return {"labelled_simple_graphs": graphs, "vertices": [1, 4], "palette": [0, 1, 2],
            "proper_initial_target_pairs": pairs, "partial_states_checked": subsets,
            "immediate_seed_queries": immediate_queries,
            "oracle": "Direct mixed-state edge checks plus exhaustive subset-path minimax DP",
            "randomness": "none; complete enumeration in the stated bounds"}


def strip_cases():
    """Connect the existing strip theorem to SCC atomic width, including new children."""
    cases = 0
    for n in range(1, 41):
        old = StripChain(SideClass("O", 0), SideClass("A", 1),
                         tuple(SideClass(f"s{i}", 2 + i % 2) for i in range(n)))
        for position in range(1, n + 1):
            result = split_strip_chain(old, position)
            names = tuple(side.side_id for side in result.after.chain)
            full_edges = [("O", "A")]
            full_edges.extend((anchor, name) for name in names for anchor in ("O", "A"))
            full_edges.extend(zip(names, names[1:]))
            daughter_edge = tuple(result.child_ids)
            base_edges = [edge for edge in full_edges if set(edge) != set(daughter_edge)]
            initial = {"O": 0, "A": 1, **dict(zip(names, result.inherited_symbols))}
            target = {"O": 0, "A": 1, **{side.side_id: side.symbol for side in result.after.chain}}
            weights = {v: int(v in {side.side_id for side in old.chain}) for v in initial}
            plan = plan_target_renaming(base_edges, initial, target, fixed=("O", "A"),
                                        added_edges=(daughter_edge,), weights=weights)
            minimum_old = min(position - 1, n - position)
            require(plan.minimum_max_batch_size == minimum_old + 1, "strip atomic size mismatch")
            require(plan.minimum_max_batch_weight == minimum_old, "strip old-side cost mismatch")
            require(verify_schedule(plan, plan.batches), "strip schedule failed")
            cases += 1
    return {"cases": cases, "old_chain_lengths": [1, 40], "all_split_positions": True,
            "width_including_changed_child": "min(i-1,n-i)+1",
            "old_side_weight": "min(i-1,n-i)",
            "scope": "H-minus omits pending daughter edge; only final naming is committed to H-plus"}


def target_profiles(source):
    """Enumerate every fixed-exterior target on ALL old examples with <=10 sides.

    Larger examples are listed as out of scope; no sampling by repair outcome.
    Target enumeration is an explicitly separate research oracle, never the
    fixed-target production rule. Serialized new-geometry coordinates/IDs are
    used as a fixed snapshot; geometry construction is not re-proved here.
    """
    source_bytes = source.read_bytes()
    report = json.loads(source_bytes)
    results, excluded = [], []
    independent_frontier_targets = 0
    for record in report["records"]:
        initial = tuple(record["inherited"])
        n = len(initial)
        if n > 10:
            excluded.append({"seed": record["seed"], "new_side_count": n})
            continue
        snapshot = record["new_map"]
        full_edges = tuple((u, v) for u, row in enumerate(snapshot["adjacency"]) for v in row if u < v)
        daughters = tuple(record["daughters"])
        base_edges = tuple(e for e in full_edges if set(e) != set(daughters))
        require(proper(base_edges, initial), "inherited naming is not legal on H-minus")
        # Check that the recorded side adjacency is precisely induced by paired darts.
        shores = snapshot["faceOfDart"]
        derived_edges = {tuple(sorted(shores[d:d + 2])) for d in range(0, len(shores), 2)
                         if shores[d] != shores[d + 1]}
        require(derived_edges == set(full_edges), "snapshot adjacency and line shores disagree")
        outer = snapshot["outerFace"]
        names = tuple(f"s{i}" for i in range(n))
        base_named = tuple((names[u], names[v]) for u, v in base_edges)
        added_named = ((names[daughters[0]], names[daughters[1]]),)
        weights = {names[i]: int(i not in daughters and i != outer) for i in range(n)}
        candidates = []
        colors = [0] * n

        def visit(index):
            """Enumerate proper targets with prefix pruning; no bound-based truncation."""
            if index < n:
                for color in ((0,) if index == outer else range(4)):
                    if any(v < index and colors[v] == color for v in snapshot["adjacency"][index]):
                        continue
                    colors[index] = color
                    visit(index + 1)
                return
            target = tuple(colors)
            plan = plan_target_renaming(base_named, dict(zip(names, initial)), dict(zip(names, target)),
                                        fixed=(names[outer],), added_edges=added_named, weights=weights)
            require(verify_schedule(plan, plan.batches), "profile schedule failed")
            # One record is an ordered left/right name pair on a fixed new-snapshot edge.
            records_by_side = {names[i]: {d // 2 for d, side in enumerate(shores) if side == i}
                               for i in range(n)}
            peak_records = max((len(set().union(*(records_by_side[v] for v in component)))
                                for component in plan.components), default=0)
            changed_old = sum(weights[names[i]] for i in range(n) if initial[i] != target[i])
            candidates.append({"target": target, "changed_unsplit_old": changed_old,
                               "atomic_width_all_changed_sides": plan.minimum_max_batch_size,
                               "atomic_width_unsplit_old_weight": plan.minimum_max_batch_weight,
                               "peak_fixed_snapshot_line_records": peak_records})

        visit(0)
        require(candidates, "no legal final target in a previously four-colourable example")
        objectives = sorted({(c["changed_unsplit_old"], c["atomic_width_all_changed_sides"])
                             for c in candidates})
        frontier = [point for point in objectives if not any(other != point and other[0] <= point[0]
                    and other[1] <= point[1] for other in objectives)]
        if len(frontier) > 1:
            # Recheck every target in each interesting map by a DIFFERENT oracle:
            # a full Cartesian product, then subset-state DP without dependencies.
            # This does not select the main sample; all <=10-side maps remain above.
            free_positions = [v for v in range(n) if v != outer]
            expected_targets = set()
            for values in product(range(4), repeat=len(free_positions)):
                target_values = [0] * n
                for vertex, value in zip(free_positions, values):
                    target_values[vertex] = value
                if proper(full_edges, target_values):
                    expected_targets.add(tuple(target_values))
            require(expected_targets == {tuple(c["target"]) for c in candidates},
                    "prefix-pruned target enumeration missed/added a target")
            for candidate in candidates:
                _, _, _, oracle_width, oracle_weight = partial_state_oracle(
                    base_edges, initial, candidate["target"], [weights[name] for name in names])
                require(oracle_width == candidate["atomic_width_all_changed_sides"],
                        "Pareto profile width disagrees with direct-state minimax")
                require(oracle_weight == candidate["atomic_width_unsplit_old_weight"],
                        "Pareto profile weighted width disagrees with direct-state minimax")
                independent_frontier_targets += 1
        results.append({"seed": record["seed"], "new_side_count": n, "targets": len(candidates),
                        "pareto_changed_old_vs_atomic_size": frontier, "candidate_profiles": candidates})
    hard = next(row for row in results if row["seed"] == 20260927)
    require(hard["targets"] == 30, "hard-case target count drifted")
    return {"source_report": source.name, "source_sha256": sha256(source_bytes).hexdigest(),
            "selection": "All source records with at most 10 final side classes; exterior fixed to 0",
            "maximum_raw_target_space": 4 ** 9, "source_records": len(report["records"]),
            "included_records": len(results), "excluded_by_size": excluded,
            "total_legal_targets": sum(row["targets"] for row in results),
            "nontrivial_frontier_direct_oracle_targets": independent_frontier_targets,
            "multiple_pareto_points": [row["seed"] for row in results
                                       if len(row["pareto_changed_old_vs_atomic_size"]) > 1],
            "records": results}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = args.output or ROOT / "outputs" / f"target-renaming-{stamp}.json"
    if destination.exists():
        parser.error("output exists; choose a fresh filename")
    result = {"schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "python_version": platform.python_version(),
              "scope": "Fixed-target once-only atomic batches; prior colour-shift machinery; no novelty claim.",
              "small_graphs": exhaustive_small_graphs(), "strips": strip_cases(),
              "target_profiles": target_profiles(ROOT / "outputs" / "renaming-round-2026-09-18-v2.json")}
    result["source_sha256"] = {path: sha256((ROOT / path).read_bytes()).hexdigest() for path in
                               ("fourcolor/target_renaming.py", "fourcolor/strip_chain.py",
                                "scripts/validate_target_renaming.py")}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"small_graphs": result["small_graphs"], "strips": result["strips"],
                      "profile_maps": result["target_profiles"]["included_records"],
                      "profile_targets": result["target_profiles"]["total_legal_targets"],
                      "multiple_pareto_points": result["target_profiles"]["multiple_pareto_points"]}, indent=2))
    print(f"Report written: {destination.name}")


if __name__ == "__main__":
    main()

"""Compare inside/outside computation orders on a declared finite map corpus.

This is an exact boundary-relation diagnostic, not the user's line-naming
algorithm. All four labeled colors are retained. No failed case is discarded,
and no choice of the best inner root is substituted for the full comparison.
Core computations use the standard library. Existing reports are never replaced.
"""

from argparse import ArgumentParser
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fourcolor.coloring import colorings
from fourcolor.frontier_order import frontier_trace, traversal_order
from scripts.inside_out_fixtures import make_cases

METHODS = ("bfs", "dfs", "min_frontier")
LABEL_SEEDS = (None, 20260921, 20260922)
METRICS = ("peak_width", "peak_labeled_states", "peak_orbit_states", "attempted_transitions")
SOURCES = (
    "fourcolor/frontier_order.py", "fourcolor/coloring.py",
    "fourcolor/embedding.py", "scripts/inside_out_fixtures.py",
    "scripts/validate_inside_out.py", "scripts/validate_circle_repair.py",
    "tests/test_frontier_order.py", "tests/test_inside_out_fixtures.py",
    "tests/test_inside_out_experiment.py",
    "outputs/circle-rank-2026-09-20.json",
)


def require(condition, message):
    """Do not disable research checks under optimized Python."""
    if not condition:
        raise ValueError(message)


def hashes():
    """Bind the evidence to its exact inputs and executable sources."""
    return {path: sha256((ROOT / path).read_bytes()).hexdigest() for path in SOURCES}


def minimum_connected_width(n, edges, root):
    """Exhaust all connected prefixes, minimizing maximum processed frontier.

    This independent subset oracle optimizes width only, not state counts. It
    requires a nonempty connected graph and is called only for n <= 10. The
    recurrence extends every reachable subset by each adjacent unused vertex;
    hence it covers every order starting at root with connected prefixes.
    """
    neighbors = [0] * n
    for a, b in edges:
        neighbors[a] |= 1 << b
        neighbors[b] |= 1 << a
    full = (1 << n) - 1

    def width(mask):
        return sum(bool(mask >> v & 1 and neighbors[v] & (full ^ mask)) for v in range(n))

    first = 1 << root
    cost, predecessor = {first: width(first)}, {}
    for mask in range(first, full + 1):
        if mask not in cost:
            continue
        candidates = 0
        for v in range(n):
            if mask >> v & 1:
                candidates |= neighbors[v]
        candidates &= full ^ mask
        for v in range(n):
            if not candidates >> v & 1:
                continue
            target = mask | (1 << v)
            candidate = max(cost[mask], width(target))
            if candidate < cost.get(target, n + 1):
                cost[target] = candidate
                predecessor[target] = (mask, v)
    require(full in cost, "subset width oracle requires a connected graph")
    order, cursor = [], full
    while cursor != first:
        cursor, v = predecessor[cursor]
        order.append(v)
    return {"minimum_width": cost[full], "one_order": [root] + order[::-1],
            "reachable_subsets": len(cost)}


def brute_prefix_counts(n, edges, order):
    """Independently enumerate full prefix colorings, then project to boundary.

    No frontier recurrence or production canonicalization is reused. A
    partition is represented by its equal-position pairs, a second way of
    counting color-permutation orbits. This oracle is limited to n <= 7.
    """
    rows = []
    for step in range(1, n + 1):
        prefix = order[:step]
        done = set(prefix)
        boundary = sorted({a for a, b in edges if a in done and b not in done}
                          | {b for a, b in edges if b in done and a not in done})
        positions = {v: i for i, v in enumerate(prefix)}
        checks = [(positions[a], positions[b]) for a, b in edges if a in done and b in done]
        projected = set()
        for values in product(range(4), repeat=step):
            if all(values[a] != values[b] for a, b in checks):
                projected.add(tuple(values[positions[v]] for v in boundary))
        partitions = {tuple((i, j) for i in range(len(s)) for j in range(i)
                            if s[i] == s[j]) for s in projected}
        rows.append((len(boundary), len(projected), len(partitions)))
    return rows


def verify_trace(case, trace):
    """Check topology, complete color witness, and deterministic work counters."""
    n, edges, order = case["n"], case["edges"], trace["order"]
    witness = trace["one_coloring"]
    require(trace["feasible"] and len(witness) == n, "map did not produce a full witness")
    require(all(type(c) is int and 0 <= c < 4 for c in witness), "invalid color code")
    require(all(witness[a] != witness[b] for a, b in edges), "improper final witness")
    done, previous_count = set(), 1
    for v, row in zip(order, trace["rows"]):
        require(not done or any((a == v and b in done) or (b == v and a in done)
                                for a, b in edges), "prefix growth disconnected")
        done.add(v)
        expected = sorted({a for a, b in edges if a in done and b not in done}
                          | {b for a, b in edges if b in done and a not in done})
        require(row["boundary"] == expected and row["width"] == len(expected), "wrong frontier")
        require(row["attempted_transitions"] == 4 * previous_count, "wrong attempt count")
        require(0 < row["orbit_states"] <= row["labeled_states"] <= 4 ** len(expected), "invalid state counts")
        require(row["labeled_states"] <= row["accepted_transitions"] <= row["attempted_transitions"],
                "invalid accepted transition count")
        previous_count = row["labeled_states"]
    require(trace["rows"][-1]["labeled_states"] == 1, "final projection should be the empty state")


def classify(inside, outside):
    """All reported costs are minimized, so a smaller value means improvement."""
    return "better" if inside < outside else "worse" if inside > outside else "equal"


def aggregate(pairs):
    """Keep family/method/label groups separate to expose corpus sensitivity."""
    groups = defaultdict(list)
    for pair in pairs:
        groups[(pair["family"], pair["method"], pair["label_seed"])].append(pair)
    result = []
    for (family, method, seed), members in sorted(groups.items(), key=lambda item: str(item[0])):
        result.append({"family": family, "method": method, "label_seed": seed,
                       "pairs": len(members), "graphs": len({p["key"] for p in members}),
                       "metrics": {metric: {label: sum(p["comparison"][metric] == label for p in members)
                                             for label in ("better", "equal", "worse")} for metric in METRICS}})
    return result


def main():
    """Execute the frozen protocol and write a new, fully attributable report."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if output.exists():
        parser.error("output exists; choose a fresh filename")
    before, cases = hashes(), make_cases()
    results, pairs = [], []
    prefix_checks = root_count = 0
    for case in cases:
        n, edges = case["n"], case["edges"]
        require(next(colorings(n, edges), None) is not None, "independent coloring oracle disagrees")
        roots = [case["outer"]] + case["inner_candidates"]
        require(len(roots) == len(set(roots)), "root list contains duplicates")
        minima = {root: minimum_connected_width(n, edges, root) for root in roots} if n <= 10 else {}
        runs = []
        for seed in LABEL_SEEDS:
            labels = list(range(n))
            if seed is not None:
                random.Random(seed).shuffle(labels)
            inverse = {new: old for old, new in enumerate(labels)}
            relabeled = [(labels[a], labels[b]) for a, b in edges]
            for method in METHODS:
                by_root = {}
                for root in roots:
                    # Relabel only to vary tie-breaking; record all orders and
                    # witnesses in the original face IDs for direct comparison.
                    order = [inverse[v] for v in traversal_order(n, relabeled, labels[root], method)]
                    trace = frontier_trace(n, edges, order)
                    verify_trace(case, trace)
                    if root in minima:
                        require(trace["summary"]["peak_width"] >= minima[root]["minimum_width"],
                                "heuristic beats exhaustive width oracle")
                    if seed is None and method == "bfs" and n <= 7:
                        observed = [(r["width"], r["labeled_states"], r["orbit_states"]) for r in trace["rows"]]
                        require(observed == brute_prefix_counts(n, edges, order), "independent prefix relation differs")
                        prefix_checks += n
                    run = {"root": root, "role": "outer" if root == case["outer"] else "inner",
                           "method": method, "label_seed": seed, "order": order,
                           "summary": trace["summary"], "rows": trace["rows"],
                           "one_coloring": trace["one_coloring"], "feasible": trace["feasible"]}
                    runs.append(run)
                    by_root[root] = run
                    root_count += 1
                outer = by_root[case["outer"]]["summary"]
                for root in case["inner_candidates"]:
                    inner = by_root[root]["summary"]
                    pairs.append({"key": case["key"], "family": case["family"], "inner_root": root,
                                  "method": method, "label_seed": seed,
                                  "outside": {m: outer[m] for m in METRICS},
                                  "inside": {m: inner[m] for m in METRICS},
                                  "comparison": {m: classify(inner[m], outer[m]) for m in METRICS}})
        results.append({"case": case, "runs": runs,
                        "exact_connected_width": {str(k): v for k, v in minima.items()},
                        "independent_four_color_witness_exists": True})
        print(json.dumps({"completed_case": case["key"], "faces": n, "runs": len(runs)}), flush=True)
    require(hashes() == before, "sources changed during experiment")
    report = {
        "schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "passed": True, "source_sha256": before, "sources_unchanged": True,
        "protocol": {"palette": 4, "methods": METHODS, "label_seeds": LABEL_SEEDS,
                     "inner_roots": "Every fixture-declared deepest face; no best-root selection",
                     "state_handling": "All labeled states kept; orbits only counted, never used to merge pieces",
                     "work_measure": "4 attempts per previous labeled frontier state; includes rejected extensions",
                     "not_measured": ["wall-clock speedup", "mother-line repair cost", "single-state greedy completeness"],
                     "independent_prefix_oracle": "All original-label BFS roots for maps with <=7 faces",
                     "exact_width_oracle": "All connected-prefix orders from each root for maps with <=10 faces",
                     "oracle_scope": "width optimum is not a state-count or runtime optimum"},
        "counts": {"graphs": len(cases), "runs": root_count, "paired_comparisons": len(pairs),
                   "independent_prefix_checks": prefix_checks, "max_faces": max(c["n"] for c in cases),
                   "families": dict(Counter(c["family"] for c in cases))},
        "groups": aggregate(pairs), "pairs": pairs, "results": results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"passed": True, "counts": report["counts"]}), flush=True)


if __name__ == "__main__":
    main()

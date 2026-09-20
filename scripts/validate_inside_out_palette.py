"""Control palette redundancy using the exact same saved processing orders.

The main experiment fixes four available colors. Here each map is also run at
its exact chromatic number. Minimum-palette feasibility is checked independently
by the older coloring enumerator on a clique-augmented constraint graph. These
auxiliary vertices are oracle restrictions, not new faces or a new plane map.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fourcolor.coloring import colorings
from fourcolor.frontier_order import frontier_trace

METRICS = ("peak_width", "peak_labeled_states", "peak_orbit_states", "attempted_transitions")
SOURCES = ("scripts/validate_inside_out_palette.py", "fourcolor/frontier_order.py", "fourcolor/coloring.py")


def require(condition, message):
    """Preserve all scientific validation under optimized Python."""
    if not condition:
        raise ValueError(message)


def palette_witness(n, edges, palette):
    """Force colors palette..3 onto a clique adjacent to every original vertex.

    A coloring of the augmented graph restricts precisely to a proper coloring
    of the original graph with colors 0..palette-1, and every such coloring
    extends. The older independent search never calls the frontier kernel.
    """
    blockers = list(range(n, n + 4 - palette))
    augmented = list(map(tuple, edges))
    augmented += [(v, blocker) for v in range(n) for blocker in blockers]
    augmented += [(a, b) for i, a in enumerate(blockers) for b in blockers[i+1:]]
    precolored = {v: palette+i for i, v in enumerate(blockers)}
    witness = next(colorings(n+len(blockers), augmented, precolored=precolored), None)
    return list(witness[:n]) if witness is not None else None


def classify(inside, outside):
    """Compare costs under the same palette; smaller is better."""
    return "better" if inside < outside else "worse" if inside > outside else "equal"


def main():
    """Save a fresh sensitivity report; do not change the primary experiment."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; choose a new path")
    raw = args.input.read_bytes()
    original = json.loads(raw)
    require(original["passed"], "input is not a passing experiment")
    before = {p: sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES}
    results, pairs = [], []
    for entry in original["results"]:
        case = entry["case"]
        n, edges = case["n"], case["edges"]
        checks = []
        for palette in range(1, 5):
            witness = palette_witness(n, edges, palette)
            checks.append({"palette": palette, "feasible": witness is not None, "one_coloring": witness})
            if witness is not None:
                require(all(0 <= c < palette for c in witness) and
                        all(witness[a] != witness[b] for a, b in edges), "oracle witness invalid")
                break
        require(witness is not None, "no coloring in 1..4")
        # One fixed order also checks every failed smaller palette independently
        # through the frontier implementation, without introducing oracle faces.
        for check in checks:
            trace = frontier_trace(n, edges, entry["runs"][0]["order"], check["palette"])
            require(trace["feasible"] == check["feasible"], "minimum palette oracles disagree")
        runs, index = [], {}
        for old in entry["runs"]:
            trace = frontier_trace(n, edges, old["order"], palette)
            require(trace["feasible"], "fixed order lost minimum-palette feasibility")
            if palette == 4:
                require(trace["summary"] == old["summary"], "four-color control should reproduce original")
            if case["family"] == "nested-jordan-tree":
                # A nontrivial connected tree has exactly two proper 2-colorings;
                # each nonfinal connected prefix exposes their two restrictions.
                require(palette == 2 and trace["summary"]["peak_labeled_states"] == 2 and
                        trace["summary"]["peak_orbit_states"] == 1 and
                        trace["summary"]["attempted_transitions"] == 4*n-2,
                        "tree two-color invariance failed")
            row = {field: old[field] for field in ("root", "role", "method", "label_seed", "order")}
            row.update(summary=trace["summary"], one_coloring=trace["one_coloring"], rows=trace["rows"])
            runs.append(row)
            index[(old["root"], old["method"], old["label_seed"])] = row
        for run in runs:
            if run["role"] != "inner":
                continue
            outside = index[(case["outer"], run["method"], run["label_seed"])]["summary"]
            inside = run["summary"]
            pairs.append({"key": case["key"], "family": case["family"], "palette": palette,
                          "root": run["root"], "method": run["method"], "label_seed": run["label_seed"],
                          "outside": {m: outside[m] for m in METRICS},
                          "inside": {m: inside[m] for m in METRICS},
                          "comparison": {m: classify(inside[m], outside[m]) for m in METRICS}})
        results.append({"key": case["key"], "family": case["family"], "minimum_palette": palette,
                        "independent_palette_checks": checks, "runs": runs})
    require(before == {p: sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES}, "source changed")
    report = {"schema_version": 1, "passed": True,
              "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "input": {"filename": args.input.name, "sha256": sha256(raw).hexdigest()},
              "source_sha256": before,
              "scope": "Same graphs, roots, methods, labels and orders; only palette changes to exact minimum.",
              "counts": {"graphs": len(results), "runs": sum(len(r["runs"]) for r in results),
                         "paired_comparisons": len(pairs),
                         "minimum_palette_histogram": dict(Counter(r["minimum_palette"] for r in results))},
              "pairs": pairs, "results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"passed": True, "counts": report["counts"]}))


if __name__ == "__main__":
    main()

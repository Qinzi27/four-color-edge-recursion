"""Solve a supplied face-constraint graph with explicit exact interface modes.

This CLI accepts a fixed graph, not raw drawing strokes. It performs no hidden
fallback and rejects extra constraint keys instead of ignoring precolors or
lists. Run from any directory; choose a fresh output filename on each run.
"""

from argparse import ArgumentParser
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.closed_interfaces import closed_interface_trace
from fourcolor.frontier_order import frontier_trace, traversal_order
from fourcolor.orbit_frontier import orbit_frontier_trace

SOURCES = ("scripts/solve_closed_interfaces.py", "fourcolor/frontier_order.py",
           "fourcolor/orbit_frontier.py", "fourcolor/closed_interfaces.py")


def solve_input(data, mode="blocks"):
    """Validate the narrow public input contract before dispatching once."""
    allowed = {"n", "edges", "order", "palette_size", "description", "vertex_semantics"}
    if not isinstance(data, dict) or set(data) - allowed or not {"n", "edges"} <= set(data):
        raise ValueError("expected n, edges and optional order/palette_size/description/vertex_semantics; "
                         "precolors, color lists and other constraints are unsupported")
    n, edges = data["n"], data["edges"]
    palette = data.get("palette_size", 4)
    order = data.get("order")
    if order is None:
        order = traversal_order(n, edges, 0 if n else None, "bfs")
    solvers = {"named": frontier_trace, "orbit": orbit_frontier_trace,
               "blocks": closed_interface_trace}
    if mode not in solvers:
        raise ValueError("mode must be named, orbit or blocks")
    return solvers[mode](n, edges, order, palette_size=palette)


def main():
    """Write exact results, input/source hashes and a concise console summary."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", choices=("named", "orbit", "blocks"), default="blocks")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; choose a new filename")
    try:
        raw = args.input.read_bytes()
        data = json.loads(raw)
        result = solve_input(data, args.mode)
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))
    report = {
        "schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "input_sha256": sha256(raw).hexdigest(),
        "source_sha256": {p: sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES},
        "scope": "fixed ordinary graph coloring; no precolors, lists, counting or repair costs",
        "result": result,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"mode": args.mode, "feasible": result["feasible"],
                      "summary": result["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

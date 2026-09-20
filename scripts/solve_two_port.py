"""Run explicit reduction, boundary-signature, or two-terminal gluing tasks.

Inputs describe fixed ordinary constraint graphs; no drawing parser, preset
colors, color lists or repair costs are implied. Existing outputs are never
overwritten. Core algorithms use Python's standard library only.
"""

from argparse import ArgumentParser
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fourcolor.frontier_order import traversal_order
from fourcolor.interface_signatures import interface_signature, glue_two_terminal_pieces
from fourcolor.two_port_reduction import two_port_trace

SOURCES = ("scripts/solve_two_port.py", "fourcolor/interface_signatures.py",
           "fourcolor/two_port_reduction.py", "fourcolor/orbit_frontier.py",
           "fourcolor/frontier_order.py")


def solve_input(data, mode):
    """Reject unsupported constraints before choosing one declared operation."""
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    if mode == "glue":
        if not {"pieces"} <= set(data) or set(data) - {"pieces", "palette_size", "description"}:
            raise ValueError("glue expects pieces and optional palette_size/description")
        return glue_two_terminal_pieces(data["pieces"], data.get("palette_size", 4))
    allowed = {"n", "edges", "order", "palette_size", "description"}
    required = {"n", "edges"}
    if mode == "signature":
        allowed.add("terminals")
        required.add("terminals")
    elif mode != "reduce":
        raise ValueError("mode must be signature, reduce or glue")
    if not required <= set(data) or set(data) - allowed:
        raise ValueError("missing graph fields or unsupported extra constraints")
    n, edges, q = data["n"], data["edges"], data.get("palette_size", 4)
    order = data.get("order")
    if order is None:
        order = traversal_order(n, edges, 0 if n else None, "bfs")
    if mode == "signature":
        return interface_signature(n, edges, data["terminals"], q, order)
    return two_port_trace(n, edges, order, q)


def main():
    """Write a source-bound exact result without exposing machine paths."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", required=True, choices=("signature", "reduce", "glue"))
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; choose a fresh filename")
    try:
        raw = args.input.read_bytes()
        result = solve_input(json.loads(raw), args.mode)
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))
    report = {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "mode": args.mode, "input_sha256": sha256(raw).hexdigest(),
              "source_sha256": {p: sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES},
              "result": result}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"mode": args.mode, "feasible": result["feasible"],
                      "patterns": result.get("patterns"), "summary": result["summary"]}))


if __name__ == "__main__":
    main()

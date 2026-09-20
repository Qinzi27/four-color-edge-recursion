"""Audit unchanged exact programs on the nine archived v4 greedy failures.

Each solver receives only the uncolored face graph and one declared exterior-
root BFS order.  Frontier DP retains alternative boundary states; success here
is therefore NOT a repair of v4's irreversible greedy decisions.  Single-run
durations are descriptive diagnostics, never a comparative speed claim.
"""

from argparse import ArgumentParser
from collections import Counter, deque
from datetime import datetime, timezone
from hashlib import sha256
import gzip
import json
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter_ns

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.embedding import PlaneMap

ARCHIVE = "outputs/peer-batches-full-2026-09-19.json.gz"
ARCHIVE_SHA256 = "fb004374e06ee0ace87328a8559e108b23e0e9b71663e1a35158738a5e3ad543"
METHODS = ("orbit", "two_port")
SOURCES = ("scripts/check_prior_exact_failures.py", "tests/test_prior_exact_failures.py",
           "fourcolor/orbit_frontier.py", "fourcolor/two_port_reduction.py",
           "fourcolor/frontier_order.py", "fourcolor/embedding.py")


def require(condition, message):
    """Preserve audit checks under optimized Python execution."""
    if not condition:
        raise ValueError(message)


def digest(value):
    """Match the original archive's canonical UTF-8 geometry digest."""
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode("utf-8")).hexdigest()


def hashes(paths):
    """Publish repository-relative provenance without local machine paths."""
    return {path: sha256((ROOT / path).read_bytes()).hexdigest() for path in paths}


def graph_from_geometry(geometry):
    """Independently reconstruct all actual face adjacencies and the exterior.

    In this frozen screen-coordinate exporter, the exterior boundary has
    positive signed area and bounded faces have negative signed area.  Both
    that convention and the archived exterior ID are checked before BFS.
    Bridges have the same shore twice and impose no color inequality.
    """
    plane = PlaneMap(tuple((str(edge["a"]), str(edge["b"])) for edge in geometry["edges"]),
                     {str(v): tuple(darts) for v, darts in enumerate(geometry["rotation"])})
    require(tuple(geometry["faceOfDart"]) == plane.face_of_dart,
            "archived face/dart identities disagree with rotation")
    require(len(geometry["faces"]) == len(plane.faces)
            and all(set(a) == set(b) for a, b in zip(geometry["faces"], plane.faces)),
            "archived face boundaries disagree with rotation")
    areas = []
    for face in plane.faces:
        area = 0
        for dart in face:
            edge = geometry["edges"][dart // 2]
            a, b = (edge["a"], edge["b"]) if dart % 2 == 0 else (edge["b"], edge["a"])
            p, q = geometry["vertices"][a], geometry["vertices"][b]
            area += p[0] * q[1] - q[0] * p[1]
        areas.append(area)
    outer = geometry["outerFace"]
    require(type(outer) is int and 0 <= outer < len(plane.faces), "invalid exterior face")
    require([i for i, area in enumerate(areas) if area > 0] == [outer]
            and all(area != 0 for area in areas), "exterior signed-area audit failed")
    edges, bridge_ids, virtual_ids, real_ids = set(), [], [], []
    for edge_id, edge in enumerate(geometry["edges"]):
        a, b = plane.shores(edge_id)
        if edge.get("virtual"):
            require(a == b, "virtual connector must not separate faces")
            virtual_ids.append(edge_id)
            continue
        real_ids.append(edge_id)
        if a == b:
            bridge_ids.append(edge_id)
        else:
            require(geometry["vertices"][edge["a"]] != geometry["vertices"][edge["b"]],
                    "zero-length edge cannot impose face inequality")
            edges.add(tuple(sorted((a, b))))
    return {"n": len(plane.faces), "edges": [list(edge) for edge in sorted(edges)],
            "outer": outer, "signed_double_areas": areas, "real_edge_ids": real_ids,
            "real_bridge_edge_ids": bridge_ids, "virtual_edge_ids": virtual_ids}


def exterior_bfs(n, edges, outer):
    """Use ascending neighbors and deterministic residual-component roots."""
    adjacent = [set() for _ in range(n)]
    for a, b in edges:
        adjacent[a].add(b)
        adjacent[b].add(a)
    order, seen = [], set()
    for root in [outer] + [v for v in range(n) if v != outer]:
        if root in seen:
            continue
        queue = deque([root])
        seen.add(root)
        while queue:
            vertex = queue.popleft()
            order.append(vertex)
            for neighbor in sorted(adjacent[vertex]):
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
    return order


def verify_raw_witness(geometry, coloring):
    """Check every original real edge independently of either solver's checker."""
    n = len(geometry["faces"])
    require(isinstance(coloring, list) and len(coloring) == n
            and all(type(c) is int and 0 <= c < 4 for c in coloring),
            "invalid four-color witness")
    checked, bridges, virtuals = [], [], []
    for edge_id, edge in enumerate(geometry["edges"]):
        a, b = geometry["faceOfDart"][2 * edge_id:2 * edge_id + 2]
        if edge.get("virtual"):
            require(a == b, "virtual connector separates two faces")
            virtuals.append(edge_id)
        elif a == b:
            bridges.append(edge_id)
        else:
            require(coloring[a] != coloring[b], "witness violates a real shared boundary")
            checked.append(edge_id)
    return {"passed": True, "palette_size": 4, "checked_inequality_edge_ids": checked,
            "real_bridge_edge_ids": bridges, "virtual_edge_ids": virtuals,
            "all_raw_edges_accounted_for": len(checked) + len(bridges) + len(virtuals)
            == len(geometry["edges"])}


def run_one(method, problem, timeout_seconds=30):
    """Isolate one fixed solver call; timeout never triggers another order/method."""
    require(method in METHODS, "unknown exact method")
    require(type(timeout_seconds) is int and timeout_seconds > 0, "invalid timeout")
    started = perf_counter_ns()
    try:
        process = subprocess.run([sys.executable, "-X", "utf8", str(Path(__file__).resolve()),
                                  "--worker", method], input=json.dumps(problem), text=True,
                                 encoding="utf-8", capture_output=True, timeout=timeout_seconds,
                                 check=False)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "timeout_seconds": timeout_seconds,
                "process_elapsed_ns": perf_counter_ns() - started, "solver_result": None}
    elapsed = perf_counter_ns() - started
    if process.returncode != 0:
        # Do not publish stderr: Python tracebacks can disclose local paths.
        return {"status": "worker_error", "returncode": process.returncode,
                "process_elapsed_ns": elapsed, "solver_result": None}
    payload = json.loads(process.stdout)
    return {"status": "completed", "process_elapsed_ns": elapsed, **payload}


def worker(method):
    """Receive no archived colors, decisions, geometric keys or prior answers."""
    from fourcolor.orbit_frontier import orbit_frontier_trace
    from fourcolor.two_port_reduction import two_port_trace
    problem = json.load(sys.stdin)
    require(set(problem) == {"n", "edges", "order"}, "worker accepts only uncolored graph/order")
    solver = {"orbit": orbit_frontier_trace, "two_port": two_port_trace}[method]
    started = perf_counter_ns()
    result = solver(problem["n"], problem["edges"], problem["order"], palette_size=4)
    elapsed = perf_counter_ns() - started
    print(json.dumps({"solver_elapsed_ns": elapsed, "solver_result": result}))


def audit(timeout_seconds=30):
    """Check the fixed nine-case set and save witnesses, traces and immutable hashes."""
    source_before, input_before = hashes(SOURCES), hashes((ARCHIVE,))
    require(input_before[ARCHIVE] == ARCHIVE_SHA256, "frozen v4 archive bytes changed")
    archive = json.loads(gzip.decompress((ROOT / ARCHIVE).read_bytes()))
    rows = {row["key"]: row for row in archive["drawings"]}
    keys = sorted(archive["failure_keys"])
    require(len(keys) == len(set(keys)) == 9, "expected nine distinct archived v4 failures")
    require(keys == sorted(key for key, row in rows.items()
                           if row["runs"]["peer-batch-ready-sides-v4"]["status"] == "conflict"),
            "failure set disagrees with archived status records")
    records = []
    for key in keys:
        geometry = archive["detailed_examples"][key]["geometry"]
        require(digest(geometry) == rows[key]["geometry_sha256"], "frozen geometry digest changed")
        graph = graph_from_geometry(geometry)
        order = exterior_bfs(graph["n"], graph["edges"], graph["outer"])
        problem = {"n": graph["n"], "edges": graph["edges"], "order": order}
        methods = {}
        for method in METHODS:
            run = run_one(method, problem, timeout_seconds)
            if run["status"] == "completed":
                result = run["solver_result"]
                require(result["n"] == graph["n"] and result["order"] == order
                        and result["edges"] == graph["edges"] and result["palette_size"] == 4,
                        "solver reported a different problem")
                require(result["feasible"] is True, "exact method unexpectedly declared planar map infeasible")
                run["raw_witness_verification"] = verify_raw_witness(geometry, result["one_coloring"])
                run["status"] = "verified_feasible"
            methods[method] = run
        records.append({"key": key, "aliases": rows[key]["aliases"],
                        "geometry_sha256": rows[key]["geometry_sha256"], "graph": graph,
                        "order": order, "archived_v4_status": "conflict", "methods": methods})
        print(json.dumps({"cases_checked": len(records), "key": key,
                          "statuses": {name: run["status"] for name, run in methods.items()}}), flush=True)
    source_after, input_after = hashes(SOURCES), hashes((ARCHIVE,))
    require(source_before == source_after and input_before == input_after,
            "source or archived input changed during audit")
    counts = {method: dict(Counter(row["methods"][method]["status"] for row in records))
              for method in METHODS}
    return {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "passed": all(run["status"] == "verified_feasible"
                          for row in records for run in row["methods"].values()),
            "source_sha256": source_before, "source_sha256_after": source_after,
            "input_sha256": input_before, "input_sha256_after": input_after,
            "sources_unchanged": True, "inputs_unchanged": True,
            "runtime": {"python_version": platform.python_version(), "system": platform.system()},
            "protocol": {"palette_size": 4, "cases": 9, "methods": list(METHODS),
                         "calls": 18, "timeout_seconds_per_call": timeout_seconds,
                         "order": "Actual exterior-root BFS with ascending numeric neighbors; no order retries.",
                         "old_color_inputs": False, "repetitions": 1,
                         "timing_scope": "Descriptive single-run diagnostics; no speed comparison or isolated benchmark.",
                         "algorithm_scope": "Unchanged exact frontier programs retain alternative boundary states. "
                         "This checks earlier programs on v4 failures; it is not a repair of greedy v4, "
                         "a full-corpus test, a new coloring theorem, or a guarantee of bounded memory."},
            "counts": counts, "records": records}


def main():
    """Run the audit or one internal worker, preserving every earlier report."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--worker", choices=METHODS, help="Internal subprocess mode; reads graph JSON on stdin")
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--output", default="outputs/prior-exact-failures-2026-09-20.json")
    args = parser.parse_args()
    if args.worker:
        worker(args.worker)
        return
    path = Path(args.output)
    if not path.is_absolute():
        path = ROOT / path
    require(not path.exists(), "refusing to overwrite an existing report")
    report = audit(args.timeout_seconds)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"passed": report["passed"], "counts": report["counts"]}))


if __name__ == "__main__":
    main()

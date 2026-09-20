"""Benchmark exact two-port elimination against orbit DP and exact DSATUR.

The protocol is fixed before measurement: the earlier 63 plane-map fixtures
use original-label exterior-root BFS in both four and minimum palettes; eight
cycles, six ladders and six wheels use root-zero BFS in palettes 2, 3 and 4.
Extra inputs are planar constraint graphs, not claimed map-face embeddings.

DSATUR uses maximum saturation, static degree and smallest vertex ID, with
exhaustive backtracking over used names plus one new name. It has no fallback
or preprocessing and returns no full frontier trace. Different diagnostics
make this an end-to-end implementation comparison, not an isolated kernel or
state-of-the-art comparison. Degree-at-most-two peeling for q >= 3 is known;
even stronger degree-three peeling applies at q=4 but is not implemented.
"""

from argparse import ArgumentParser
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gc
from hashlib import sha256
import json
from pathlib import Path
import platform
from statistics import median
import sys
from time import perf_counter_ns
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.frontier_order import traversal_order
from scripts.benchmark_closed_interfaces import load_protocol, verify_witness, write_report

VARIANTS = ("orbit", "reduced", "dsatur")
INPUTS = (
    "outputs/inside-out-experiment-2026-09-20.json",
    "outputs/inside-out-palette-2026-09-20.json",
    "outputs/circle-rank-2026-09-20.json",
)
SOURCES = (
    "scripts/benchmark_two_port.py", "tests/test_two_port_benchmark.py",
    "fourcolor/two_port_reduction.py", "fourcolor/orbit_frontier.py",
    "fourcolor/frontier_order.py", "scripts/benchmark_closed_interfaces.py",
    "scripts/inside_out_fixtures.py", "scripts/validate_circle_repair.py",
    "fourcolor/embedding.py", "fourcolor/coloring.py",
)


def require(condition, message):
    """Use explicit checks that remain active under Python optimization."""
    if not condition:
        raise ValueError(message)


def hashes(paths):
    """Record exact repository-relative bytes without disclosing local paths."""
    return {path: sha256((ROOT / path).read_bytes()).hexdigest() for path in paths}


def dsatur_trace(n, edges, order=None, palette_size=4):
    """Independent deterministic exact coloring baseline with branch counters.

    Input normalization, search and witness storage are independent of the
    frontier implementations. Global color-name symmetry permits one unused
    color representative, while backtracking exhausts all distinct choices.
    The optional order is accepted for a common call signature but is unused.
    """
    require(type(n) is int and n >= 0, "n must be a nonnegative integer")
    require(type(palette_size) is int and 1 <= palette_size <= 4,
            "palette_size must be an integer from 1 through 4")
    adjacent = [set() for _ in range(n)]
    has_loop = False
    for edge in edges:
        require(isinstance(edge, (list, tuple)) and len(edge) == 2,
                "edges must be pairs")
        first, second = edge
        require(all(type(vertex) is int and 0 <= vertex < n for vertex in edge),
                "edge endpoint outside vertex range")
        adjacent[first].add(second)
        adjacent[second].add(first)
        has_loop = has_loop or first == second
    colors = [-1] * n
    summary = {"attempted_branches": 0, "accepted_branches": 0,
               "recursive_calls": 0, "backtracks": 0, "peak_colored_vertices": 0}

    def search(remaining, used):
        """Visit every legal canonical extension until finding one witness."""
        summary["recursive_calls"] += 1
        summary["peak_colored_vertices"] = max(summary["peak_colored_vertices"], n - remaining)
        if not remaining:
            return True
        # Degree is the original static degree, not the residual degree.
        pending = [vertex for vertex in range(n) if colors[vertex] == -1]
        vertex = max(pending, key=lambda item: (
            len({colors[neighbor] for neighbor in adjacent[item] if colors[neighbor] != -1}),
            len(adjacent[item]), -item))
        forbidden = {colors[neighbor] for neighbor in adjacent[vertex] if colors[neighbor] != -1}
        for color in range(min(palette_size, used + 1)):
            summary["attempted_branches"] += 1
            if color in forbidden:
                continue
            summary["accepted_branches"] += 1
            colors[vertex] = color
            if search(remaining - 1, max(used, color + 1)):
                return True
            colors[vertex] = -1
        summary["backtracks"] += 1
        return False

    feasible = not has_loop and search(n, 0)
    return {"feasible": feasible, "one_coloring": colors if feasible else None,
            "summary": summary}


def algorithms():
    """Import the new solver lazily so CLI help and DSATUR tests are independent."""
    from fourcolor.orbit_frontier import orbit_frontier_trace
    from fourcolor.two_port_reduction import two_port_trace
    return {"orbit": orbit_frontier_trace, "reduced": two_port_trace, "dsatur": dsatur_trace}


def extra_cases():
    """Predeclare scalable planar families and elementary chromatic certificates."""
    result = []
    for size in (3, 4, 5, 8, 16, 32, 64, 128):
        result.append({"key": f"extra-cycle-{size}", "family": "extra-cycle", "n": size,
                       "edges": [[vertex, (vertex + 1) % size] for vertex in range(size)],
                       "root": 0, "minimum_palette": 2 if size % 2 == 0 else 3,
                       "certificate": "An even cycle is bipartite; an odd cycle requires and admits three colors."})
    for length in (2, 3, 4, 8, 16, 32):
        edges = [[row * length + vertex, row * length + vertex + 1]
                 for row in range(2) for vertex in range(length - 1)]
        edges.extend([[vertex, length + vertex] for vertex in range(length)])
        result.append({"key": f"extra-ladder-2x{length}", "family": "extra-ladder", "n": 2 * length,
                       "edges": edges, "root": 0, "minimum_palette": 2,
                       "certificate": "The nonempty Cartesian product P2 x Pk is bipartite."})
    for rim in (3, 4, 5, 6, 8, 16):
        edges = [[1 + vertex, 1 + (vertex + 1) % rim] for vertex in range(rim)]
        edges.extend([[0, vertex + 1] for vertex in range(rim)])
        result.append({"key": f"extra-wheel-rim-{rim}", "family": "extra-wheel", "n": rim + 1,
                       "edges": edges, "root": 0, "minimum_palette": 3 if rim % 2 == 0 else 4,
                       "certificate": "The universal hub needs one color additional to the cycle rim."})
    for case in result:
        case["kind"] = "planar-constraint-graph"
        case["root_definition"] = "Fixed vertex 0; no exterior-face claim or best-root selection."
        case["edges"] = [list(edge) for edge in sorted({tuple(sorted(edge)) for edge in case["edges"]})]
    return result


def make_jobs(limit=None):
    """Audit immutable earlier cases and add all predeclared palette conditions."""
    jobs = []
    for entry in load_protocol():
        case = entry["case"]
        runs = [run for run in entry["runs"] if run["role"] == "outer"
                and run["method"] == "bfs" and run["label_seed"] is None]
        require(len(runs) == 1, "expected exactly one original exterior BFS")
        for mode, palette in (("four", 4), ("minimum", entry["minimum_palette"])):
            jobs.append({"case": case, "root": case["outer"], "palette_mode": mode,
                         "palette": palette, "expected_feasible": True,
                         "expected_source": "Frozen independent minimum-palette certificate.",
                         "order": runs[0]["order"], "corpus": "frozen-map"})
    for case in extra_cases():
        order = traversal_order(case["n"], case["edges"], case["root"], "bfs")
        for palette in (2, 3, 4):
            jobs.append({"case": case, "root": case["root"], "palette_mode": f"q{palette}",
                         "palette": palette, "expected_feasible": palette >= case["minimum_palette"],
                         "expected_source": case["certificate"], "order": order,
                         "corpus": "extra-planar-constraint"})
    require(len(jobs) == 186 and len({job["case"]["key"] for job in jobs}) == 83,
            "predeclared benchmark bounds changed")
    if limit is not None:
        require(type(limit) is int and 1 <= limit <= len(jobs), "invalid smoke job limit")
        jobs = jobs[:limit]
    return jobs


def call_with_order(job, solver):
    """Include BFS, complete solver preprocessing, search and witness extraction."""
    case = job["case"]
    order = traversal_order(case["n"], case["edges"], job["root"], "bfs")
    return order, solver(case["n"], case["edges"], order, palette_size=job["palette"])


def check_result(job, order, trace):
    """Check feasibility against an external certificate and verify every edge."""
    require(order == job["order"], "reconstructed BFS differs from declared order")
    require(trace["feasible"] == job["expected_feasible"], "known feasibility disagrees")
    verify_witness(job["case"], job["palette"], trace)


def check_three(job, solvers):
    """Keep native cost counters separate; none are combined into a fake cost."""
    result = {}
    for name in VARIANTS:
        order, trace = call_with_order(job, solvers[name])
        check_result(job, order, trace)
        result[name] = {"feasible": trace["feasible"], "one_coloring": trace["one_coloring"],
                        "summary": trace["summary"]}
    return result


def rotated_variants(repeat, job_index):
    """Balance the first, middle and last solver across each three rounds."""
    offset = (repeat + job_index) % len(VARIANTS)
    return VARIANTS[offset:] + VARIANTS[:offset]


def measure_job(job, solvers, repeats=3, job_index=0, clock=perf_counter_ns):
    """Warm once, time rotated runs, then separately trace each solver's memory."""
    require(not tracemalloc.is_tracing(), "timing must run outside tracemalloc")
    require(type(repeats) is int and repeats >= 3 and repeats % 3 == 0,
            "repeats must be a positive multiple of three")
    for name in VARIANTS:
        order, trace = call_with_order(job, solvers[name])
        check_result(job, order, trace)
        del trace
    rounds, raw = [], {name: [] for name in VARIANTS}
    for repeat in range(repeats):
        ordering, times = rotated_variants(repeat, job_index), {}
        for name in ordering:
            started = clock()
            order, trace = call_with_order(job, solvers[name])
            elapsed = clock() - started
            require(elapsed >= 0, "nonmonotonic timer")
            check_result(job, order, trace)
            times[name] = elapsed
            raw[name].append(elapsed)
            del trace
        rounds.append({"algorithm_order": list(ordering), "elapsed_ns": times})
    memory = {}
    for name in VARIANTS:
        gc.collect()
        tracemalloc.start()
        try:
            order, trace = call_with_order(job, solvers[name])
            current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        check_result(job, order, trace)
        memory[name] = {"current_traced_bytes": current, "peak_traced_bytes": peak}
        del trace
    return {"rounds": rounds,
            "timing_summary": {name: {"raw_ns": raw[name], "median_ns": median(raw[name]),
                                      "minimum_ns": min(raw[name]), "maximum_ns": max(raw[name])}
                               for name in VARIANTS}, "memory": memory}


def comparison(candidate, reference):
    """Timing and traced-allocation measures both have smaller-is-better direction."""
    return "better" if candidate < reference else "worse" if candidate > reference else "equal"


def aggregate(records):
    """Retain slower cases, negative palettes and separate family/palette conditions."""
    grouped = defaultdict(list)
    for row in records:
        grouped[(row["family"], row["palette_mode"])].append(row)
    result = []
    for (family, mode), members in sorted(grouped.items()):
        comparisons = {}
        for candidate, reference in (("reduced", "orbit"), ("reduced", "dsatur"), ("orbit", "dsatur")):
            item = {}
            for section, metric in (("timing_summary", "median_ns"), ("memory", "peak_traced_bytes")):
                counts = Counter(comparison(row[section][candidate][metric], row[section][reference][metric])
                                 for row in members)
                item[metric] = {outcome: counts[outcome] for outcome in ("better", "equal", "worse")}
            ratios = [row["timing_summary"][reference]["median_ns"] /
                      row["timing_summary"][candidate]["median_ns"] for row in members
                      if row["timing_summary"][candidate]["median_ns"]]
            item["median_of_paired_time_ratios"] = median(ratios) if ratios else None
            comparisons[f"{candidate}_vs_{reference}"] = item
        result.append({"family": family, "palette_mode": mode, "jobs": len(members),
                       "feasible_jobs": sum(row["expected_feasible"] for row in members),
                       "comparisons": comparisons})
    return result


def main():
    """Run immutable evidence generation after verifying exact input and source bytes."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, help="first N jobs, labeled as a smoke run")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 3 or args.repeats % 3:
        parser.error("repeats must be at least three and divisible by three")
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if output.exists():
        parser.error("output exists; select a fresh filename")
    source_before, input_before = hashes(SOURCES), hashes(INPUTS)
    jobs, solvers = make_jobs(args.limit), algorithms()
    records = []
    # Complete deterministic checks before any performance measurement.
    for job in jobs:
        case = job["case"]
        records.append({"key": case["key"], "family": case["family"], "n": case["n"],
                        **{key: job[key] for key in ("root", "palette_mode", "palette", "order", "corpus",
                                                    "expected_feasible", "expected_source")},
                        "variants": check_three(job, solvers)})
    print(json.dumps({"correctness_jobs": len(records), "passed": True}), flush=True)
    for index, (job, row) in enumerate(zip(jobs, records)):
        row.update(measure_job(job, solvers, args.repeats, index))
        if (index + 1) % 20 == 0 or index + 1 == len(jobs):
            print(json.dumps({"timed_jobs": index + 1, "total": len(jobs)}), flush=True)
    source_after, input_after = hashes(SOURCES), hashes(INPUTS)
    require(source_after == source_before and input_after == input_before,
            "source or input bytes changed during the benchmark")
    report = {
        "schema_version": 1, "passed": True, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_sha256": source_before, "source_sha256_after": source_after,
        "input_sha256": input_before, "input_sha256_after": input_after,
        "sources_unchanged": True, "inputs_unchanged": True,
        "protocol": {
            "full_corpus": args.limit is None, "smoke_limit": args.limit, "variants": list(VARIANTS),
            "orders": "Only original exterior BFS on 63 frozen maps; root-zero BFS on every extra graph.",
            "extra_families": "Cycles n=3,4,5,8,16,32,64,128; ladders 2xk k=2,3,4,8,16,32; wheels rim=3,4,5,6,8,16.",
            "palettes": "Frozen maps: q=4 and independently certified minimum. Extras: every q in 2,3,4, including infeasible.",
            "repeats": args.repeats, "warmups_per_variant_per_job": 1,
            "timing": "perf_counter_ns; rotated order balanced each three rounds; BFS plus entire solver API including preprocessing and witness.",
            "dsatur": "Independent exact maximum-saturation/static-degree/smallest-ID branching; used colors plus at most one new name; no fallback; BFS rebuilt but unused.",
            "diagnostic_difference": "Orbit and reduced APIs retain native trace output; DSATUR returns branch counters and one witness, with no full frontier trace.",
            "memory": "One separate tracemalloc run for every job and variant; Python traced allocations, not RSS; excluded from timing.",
            "excluded": "Source/input hashing, fixture loading, oracle certificates, validation, JSON serialization and minimum-palette determination.",
            "cost_counters": "Keep residual attempted_transitions, relation operations and reconstruction_attempts separate; DSATUR branches are not frontier-state counts.",
            "state_scope": "Reduced peak_states describes the residual core only; zero is an empty core, not zero total work or memory.",
            "known_reduction": "Degree-at-most-two peeling at q>=3 is known; degree-at-most-three peeling at q=4 is stronger and not implemented here.",
            "limits": ["Finite engineering comparison, not an originality or asymptotic-speed theorem",
                       "No pinned CPU or hardware isolation; three timings are descriptive, not significance evidence",
                       "Repeated palettes and timings are not independent random graph samples",
                       "DSATUR is this documented reference implementation, not a best-known optimized library",
                       "Extra graphs have known planar constructions but are not supplied as plane-map embeddings",
                       "No new theorem on general Four-Color completion or the original irreversible line-side naming rule"],
        },
        "runtime": {"python": platform.python_version(), "implementation": platform.python_implementation(),
                    "system": platform.system(), "machine": platform.machine(), "gc_enabled": gc.isenabled()},
        "counts": {"graphs": len({row["key"] for row in records}), "jobs": len(records),
                   "max_vertices": max(row["n"] for row in records),
                   "feasible_jobs": sum(row["expected_feasible"] for row in records),
                   "infeasible_jobs": sum(not row["expected_feasible"] for row in records),
                   "correctness_solver_calls": len(records) * 3,
                   "timed_solver_calls": len(records) * 3 * args.repeats,
                   "separate_memory_calls": len(records) * 3},
        "cases": list({job["case"]["key"]: job["case"] for job in jobs}.values()),
        "groups": aggregate(records), "records": records,
    }
    write_report(output, report)
    print(json.dumps({"passed": True, "counts": report["counts"]}), flush=True)


if __name__ == "__main__":
    main()

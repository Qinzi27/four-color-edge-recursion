"""Compare three exact coloring diagnostics on frozen face-adjacency inputs.

This is a within-project engineering comparison, not a benchmark against the
best known coloring algorithms. Every saved order is checked with four colors
and with the independently certified minimum palette. Only original-label BFS
orders are timed; all deepest roots are retained. Timing includes rebuilding
that BFS order and each solver's own preprocessing, witness and trace work.

The block solver reports local retained states, not the full graph's frontier
relation. Its feasibility and final witness are compared with the other two
solvers, while prefix orbit counts are compared only for the two unsplit
frontier solvers. Tracemalloc runs separately and measures traced Python
allocations, not resident process memory. Reports are never overwritten.
"""

from argparse import ArgumentParser
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gc
from hashlib import sha256
import json
from pathlib import Path
import platform
import random
from statistics import median
import sys
from time import perf_counter_ns
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.frontier_order import frontier_trace, traversal_order
from scripts.inside_out_fixtures import make_cases

VARIANTS = ("labeled", "orbit", "closed_interface")
MODES = ("four", "minimum")
INPUTS = (
    "outputs/inside-out-experiment-2026-09-20.json",
    "outputs/inside-out-palette-2026-09-20.json",
)
SOURCES = (
    "scripts/benchmark_closed_interfaces.py",
    "tests/test_closed_interface_benchmark.py",
    "fourcolor/frontier_order.py",
    "fourcolor/orbit_frontier.py",
    "fourcolor/closed_interfaces.py",
    "fourcolor/embedding.py",
    "fourcolor/coloring.py",
    "scripts/inside_out_fixtures.py",
    "scripts/validate_inside_out.py",
    "scripts/validate_inside_out_palette.py",
    "scripts/validate_circle_repair.py",
    "outputs/circle-rank-2026-09-20.json",
)
RUN_FIELDS = ("root", "role", "method", "label_seed", "order")


def require(condition, message):
    """Keep validation active when Python is invoked with optimization."""
    if not condition:
        raise ValueError(message)


def algorithms():
    """Load the new implementations without importing them for CLI help."""
    from fourcolor.orbit_frontier import orbit_frontier_trace
    from fourcolor.closed_interfaces import closed_interface_trace
    return {"labeled": frontier_trace, "orbit": orbit_frontier_trace,
            "closed_interface": closed_interface_trace}


def hashes(paths):
    """Identify exact repository-relative source and report bytes."""
    return {path: sha256((ROOT / path).read_bytes()).hexdigest() for path in paths}


def run_key(run):
    """Identify an order without confusing repeated roots across methods."""
    return run["root"], run["method"], run["label_seed"]


def reproduce_order(case, run):
    """Rebuild tie-breaking labels before returning original face IDs."""
    n = case["n"]
    labels = list(range(n))
    if run["label_seed"] is not None:
        random.Random(run["label_seed"]).shuffle(labels)
    inverse = {new: old for old, new in enumerate(labels)}
    relabeled = [(labels[a], labels[b]) for a, b in case["edges"]]
    return [inverse[v] for v in traversal_order(
        n, relabeled, labels[run["root"]], run["method"])]


def load_protocol(limit=None):
    """Audit saved orders against regenerated fixtures before any comparison.

    The minimum palette is evidence from the previous independent oracle, not
    a free result of this benchmark. Smaller failed palettes and a valid
    minimum-palette witness must be present in that frozen report.
    """
    original, control = [json.loads((ROOT / path).read_text(encoding="utf-8"))
                         for path in INPUTS]
    require(original["passed"] and control["passed"], "input report did not pass")
    require(control["input"]["sha256"] == hashes(INPUTS)[INPUTS[0]],
            "minimum-palette report belongs to different original bytes")
    cases = make_cases()
    original_by_key = {entry["case"]["key"]: entry for entry in original["results"]}
    control_by_key = {entry["key"]: entry for entry in control["results"]}
    require(len(original_by_key) == len(original["results"]) == len(cases),
            "original case keys are duplicated or missing")
    require(len(control_by_key) == len(control["results"]) == len(cases),
            "control case keys are duplicated or missing")
    require(set(original_by_key) == set(control_by_key) == {case["key"] for case in cases},
            "input reports disagree on case keys")
    result = []
    for case in cases:
        old, minimum = original_by_key[case["key"]], control_by_key[case["key"]]
        require(old["case"] == case, "regenerated fixture differs from frozen case")
        q = minimum["minimum_palette"]
        checks = minimum["independent_palette_checks"]
        require(type(q) is int and 1 <= q <= 4, "invalid certified palette")
        require([check["palette"] for check in checks] == list(range(1, q + 1)),
                "incomplete independent minimum-palette checks")
        require([check["feasible"] for check in checks] == [False] * (q - 1) + [True],
                "independent palette certificate is inconsistent")
        verify_witness(case, q, {"feasible": True, "one_coloring": checks[-1]["one_coloring"]})
        expected = {(root, method, seed)
                    for root in [case["outer"]] + case["inner_candidates"]
                    for method in ("bfs", "dfs", "min_frontier")
                    for seed in (None, 20260921, 20260922)}
        minimum_by_run = {run_key(run): run for run in minimum["runs"]}
        require(len(minimum_by_run) == len(minimum["runs"]) == len(old["runs"])
                and {run_key(run) for run in old["runs"]} == set(minimum_by_run) == expected,
                "saved protocol lost, duplicated, or added an order")
        for run in old["runs"]:
            require(run["role"] == ("outer" if run["root"] == case["outer"] else "inner"),
                    "incorrect saved root role")
            require(run["order"] == reproduce_order(case, run), "saved order does not reproduce")
            require(all(run[field] == minimum_by_run[run_key(run)][field] for field in RUN_FIELDS),
                    "palette control uses a different order")
        result.append({"case": case, "minimum_palette": q, "runs": old["runs"],
                       "minimum_runs": minimum_by_run})
    require(len(cases) == 63 and sum(len(entry["runs"]) for entry in result) == 1917,
            "declared full corpus bounds changed")
    if limit is not None:
        require(type(limit) is int and 1 <= limit <= len(result), "limit must be within corpus size")
        result = result[:limit]
    return result


def verify_witness(case, palette, trace):
    """Independently check the returned coloring against every input edge."""
    witness = trace["one_coloring"]
    if not trace["feasible"]:
        require(witness is None, "infeasible solver returned a witness")
        return
    require(isinstance(witness, list) and len(witness) == case["n"], "wrong witness size")
    require(all(type(color) is int and 0 <= color < palette for color in witness),
            "witness has invalid palette values")
    require(all(witness[a] != witness[b] for a, b in case["edges"]),
            "witness violates an edge")


def comparison(left, right):
    """All recorded costs have smaller-is-better direction."""
    return "better" if left < right else "worse" if left > right else "equal"


def compact_trace(variant, trace):
    """Expose a common retained-state peak while keeping native counters."""
    summary = dict(trace["summary"])
    if variant == "labeled":
        summary["peak_states"] = summary["peak_labeled_states"]
    return {"feasible": trace["feasible"], "one_coloring": trace["one_coloring"],
            "summary": summary}


def check_three(case, run, palette, solvers, saved=None):
    """Compare exact feasibility and the two equivalent prefix relations."""
    traces = {name: solvers[name](case["n"], case["edges"], run["order"], palette_size=palette)
              for name in VARIANTS}
    for trace in traces.values():
        verify_witness(case, palette, trace)
    require(len({trace["feasible"] for trace in traces.values()}) == 1,
            "solver feasibility disagreement")
    # The frozen map corpus has an independently checked witness in each
    # tested palette; rejecting it is a bug rather than a new negative result.
    require(traces["labeled"]["feasible"], "certified feasible case was rejected")
    old, orbit = traces["labeled"], traces["orbit"]
    require(len(old["rows"]) == len(orbit["rows"]) == case["n"], "missing prefix rows")
    for previous, current in zip(old["rows"], orbit["rows"]):
        require(previous["boundary"] == current["boundary"], "orbit solver changed the order frontier")
        require(previous["orbit_states"] == current["orbit_states"], "prefix orbit count differs")
    if saved is not None:
        require(old["summary"] == saved["summary"] and old["rows"] == saved["rows"],
                "labeled baseline no longer reproduces frozen report")
    return {"variants": {name: compact_trace(name, trace) for name, trace in traces.items()},
            "prefix_orbit_counts": [row["orbit_states"] for row in orbit["rows"]],
            "prefix_orbit_counts_verified": True}


def rotated_variants(round_index, job_index=0):
    """Balance each solver's first/second/third position across three rounds."""
    offset = (round_index + job_index) % len(VARIANTS)
    return VARIANTS[offset:] + VARIANTS[:offset]


def call_with_order(case, run, palette, solver):
    """Timeable unit: regenerate the order and run the complete public API."""
    order = reproduce_order(case, run)
    trace = solver(case["n"], case["edges"], order, palette_size=palette)
    return order, trace


def measure_job(case, run, palette, solvers, repeats, job_index=0, clock=perf_counter_ns):
    """Record raw times, followed by a separate outer-root memory run.

    Validation and JSON serialization are outside the clock. Order building,
    solver preprocessing, transitions, reconstruction and full trace creation
    are inside it. All three public APIs retain their native diagnostics; this
    does not isolate transition kernels or exclude labeled-orbit counting cost.
    """
    require(not tracemalloc.is_tracing(), "wall-clock measurement cannot run under tracemalloc")
    for name in VARIANTS:
        order, trace = call_with_order(case, run, palette, solvers[name])
        require(order == run["order"], "timed order differs from saved order")
        verify_witness(case, palette, trace)
        del trace
    rounds, by_name = [], {name: [] for name in VARIANTS}
    for repeat in range(repeats):
        ordering = rotated_variants(repeat, job_index)
        measurements = {}
        for name in ordering:
            started = clock()
            order, trace = call_with_order(case, run, palette, solvers[name])
            elapsed = clock() - started
            require(elapsed >= 0, "non-monotonic clock")
            require(order == run["order"], "timed order changed")
            verify_witness(case, palette, trace)
            require(trace["feasible"], "timed solver rejected a certified case")
            measurements[name] = elapsed
            by_name[name].append(elapsed)
            del trace
        rounds.append({"repeat": repeat, "algorithm_order": list(ordering), "elapsed_ns": measurements})
    summaries = {name: {"median_ns": median(values), "minimum_ns": min(values), "maximum_ns": max(values)}
                 for name, values in by_name.items()}
    memory = {}
    if run["role"] == "outer":
        for name in VARIANTS:
            # Starting tracing separately excludes the in-memory input corpus
            # and previously built traces, which are common setup outside scope.
            tracemalloc.start()
            try:
                order, trace = call_with_order(case, run, palette, solvers[name])
                current, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            require(order == run["order"], "memory order changed")
            verify_witness(case, palette, trace)
            memory[name] = {"current_traced_bytes": current, "peak_traced_bytes": peak}
            del trace
    return {"rounds": rounds, "timing_summary": summaries,
            "memory": memory,
            "median_time_ratio_labeled_over_variant": {
                name: summaries["labeled"]["median_ns"] / summaries[name]["median_ns"]
                if summaries[name]["median_ns"] else None for name in VARIANTS[1:]}}


def groups(records, performance=False):
    """Keep family and palette conditions separate, including regressions."""
    grouped = defaultdict(list)
    for record in records:
        grouped[(record["family"], record["palette_mode"])].append(record)
    result = []
    for (family, mode), members in sorted(grouped.items()):
        item = {"family": family, "palette_mode": mode, "records": len(members),
                "graphs": len({row["key"] for row in members}), "comparisons": {}}
        # The third comparison isolates the extra benefit or overhead of
        # articulation decomposition after global color symmetry is removed.
        comparisons = (("orbit", "labeled", "orbit"),
                       ("closed_interface", "labeled", "closed_interface"),
                       ("closed_interface_vs_orbit", "orbit", "closed_interface"))
        for label, reference, variant in comparisons:
            measures = ("median_ns",) if performance else ("peak_states", "attempted_transitions")
            item["comparisons"][label] = {"reference": reference, "candidate": variant}
            for metric in measures:
                counts = Counter()
                for row in members:
                    summaries = row["timing_summary"] if performance else {
                        name: value["summary"] for name, value in row["variants"].items()}
                    counts[comparison(summaries[variant][metric], summaries[reference][metric])] += 1
                item["comparisons"][label][metric] = {outcome: counts[outcome] for outcome in ("better", "equal", "worse")}
            if performance:
                ratios = [row["timing_summary"][reference]["median_ns"]
                          / row["timing_summary"][variant]["median_ns"]
                          for row in members if row["timing_summary"][variant]["median_ns"]]
                item["comparisons"][label]["median_of_paired_time_ratios"] = median(ratios) if ratios else None
        result.append(item)
    return result


def write_report(output, report):
    """Use exclusive creation so a concurrent run cannot overwrite evidence."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def main():
    """Execute the declared corpus with attributable sources and raw timings."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--limit", type=int, help="first N fixtures for a clearly marked smoke run")
    args = parser.parse_args()
    if args.repeats < 3 or args.repeats % 3:
        parser.error("repeats must be a positive multiple of 3, at least 3")
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if output.exists():
        parser.error("output exists; choose a fresh filename")
    before, inputs = hashes(SOURCES), hashes(INPUTS)
    corpus, solvers = load_protocol(args.limit), algorithms()
    records, performance, case_records = [], [], []
    for entry in corpus:
        case = entry["case"]
        case_records.append({"case": case, "minimum_palette": entry["minimum_palette"]})
        for run in entry["runs"]:
            for mode in MODES:
                palette = 4 if mode == "four" else entry["minimum_palette"]
                saved = run if mode == "four" else entry["minimum_runs"][run_key(run)]
                context = {"key": case["key"], "family": case["family"],
                           "palette_mode": mode, "palette": palette,
                           **{field: run[field] for field in RUN_FIELDS}}
                records.append({**context, **check_three(case, run, palette, solvers, saved)})
        print(json.dumps({"validated_case": case["key"], "orders": len(entry["runs"])}), flush=True)
    # Run performance after deterministic checks. No tracemalloc or independent
    # oracle executes inside a wall-clock interval. Repeated q=4 conditions are
    # kept, and explicitly are not counted as independent graphs or evidence.
    for entry in corpus:
        case = entry["case"]
        for run in entry["runs"]:
            if run["method"] != "bfs" or run["label_seed"] is not None:
                continue
            for mode in MODES:
                palette = 4 if mode == "four" else entry["minimum_palette"]
                context = {"key": case["key"], "family": case["family"],
                           "palette_mode": mode, "palette": palette,
                           **{field: run[field] for field in RUN_FIELDS}}
                measured = measure_job(case, run, palette, solvers, args.repeats, len(performance))
                performance.append({**context, **measured})
        print(json.dumps({"timed_case": case["key"]}), flush=True)
    require(hashes(SOURCES) == before and hashes(INPUTS) == inputs,
            "source or input bytes changed during the benchmark")
    report = {
        "schema_version": 1, "passed": True,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_sha256": before, "input_sha256": inputs, "sources_unchanged": True,
        "scope": "Finite within-project exact-coloring diagnostic comparison; not a state-of-the-art solver claim.",
        "protocol": {
            "variants": list(VARIANTS), "palette_modes": list(MODES),
            "smoke_limit": args.limit, "full_corpus": args.limit is None,
            "deterministic_orders": "All saved roots, BFS/DFS/min_frontier, original and two fixed label shuffles.",
            "timed_orders": "Original-label BFS from exterior and EVERY declared deepest face; no best-root selection.",
            "repeats": args.repeats, "warmups_per_job_per_variant": 1,
            "algorithm_order": "Rotate variant order by repeat plus job index, balanced over each three rounds.",
            "timed_scope": "Rebuild BFS order, full solver public API including preprocessing, witnesses and native trace diagnostics.",
            "outside_timing": "Fixture/report loading, validation, source hashing, JSON serialization, minimum-palette oracle and memory tracing.",
            "memory_scope": "One separate tracemalloc call per exterior-root job per variant; incremental Python traced peak, NOT RSS.",
            "state_scope": "Labeled/orbit are global-prefix states; closed-interface peak counts states in a single local block, not the global relation.",
            "palette_control_cost": "Exact minimum palettes are imported from a prior independent oracle; computing them is excluded and not claimed free in production.",
            "limits": ["At most 17 faces; no asymptotic timing inference", "No DSATUR or specialist coloring baseline",
                       "Repeated roots, labels, palettes and timing rounds are not independent random graph samples",
                       "No pinned hardware, isolated CPU or significance claim; all timing ratios are descriptive",
                       "Native diagnostics differ; the labeled implementation also computes orbit counts for reporting"],
        },
        "runtime": {"python": platform.python_version(), "implementation": platform.python_implementation(),
                    "system": platform.system(), "machine": platform.machine(), "gc_enabled": gc.isenabled(),
                    "clock": "perf_counter_ns"},
        "counts": {"graphs": len(corpus), "max_faces": max(entry["case"]["n"] for entry in corpus),
                   "saved_orders": sum(len(entry["runs"]) for entry in corpus),
                   "deterministic_jobs": len(records), "deterministic_solver_calls": len(records) * len(VARIANTS),
                   "prefix_orbit_checks": sum(len(row["prefix_orbit_counts"]) for row in records),
                   "timed_jobs": len(performance), "raw_timing_calls": len(performance) * args.repeats * len(VARIANTS),
                   "separate_memory_calls": sum(bool(row["memory"]) for row in performance) * len(VARIANTS),
                   "families": dict(Counter(entry["case"]["family"] for entry in corpus))},
        "cases": case_records,
        "deterministic": {"groups": groups(records), "records": records},
        "performance": {"groups": groups(performance, performance=True), "records": performance},
    }
    write_report(output, report)
    print(json.dumps({"passed": True, "counts": report["counts"]}), flush=True)


if __name__ == "__main__":
    main()

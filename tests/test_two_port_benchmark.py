"""Independent DSATUR oracle and reproducible benchmark protocol checks."""

from collections import Counter
from itertools import combinations, product
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import benchmark_two_port as benchmark


def assignment_oracle(n, edges, palette):
    """Exhaust all named assignments without heuristic order or symmetry pruning."""
    return any(all(colors[first] != colors[second] for first, second in edges)
               for colors in product(range(palette), repeat=n))


class TwoPortBenchmarkTests(unittest.TestCase):
    """Check negative cases and measurement meaning independently of reduction code."""

    def test_dsatur_matches_full_assignments_for_all_graphs_up_to_four_vertices(self):
        """All 76 simple labeled graphs and palettes 1..4 yield 304 decisions."""
        cases = 0
        for n in range(5):
            possible = list(combinations(range(n), 2))
            for mask in range(1 << len(possible)):
                edges = [edge for bit, edge in enumerate(possible) if mask & (1 << bit)]
                for palette in range(1, 5):
                    with self.subTest(n=n, mask=mask, palette=palette):
                        result = benchmark.dsatur_trace(n, edges, palette_size=palette)
                        self.assertEqual(result["feasible"], assignment_oracle(n, edges, palette))
                        benchmark.verify_witness({"n": n, "edges": edges}, palette, result)
                        self.assertNotIn("peak_states", result["summary"])
                        self.assertNotIn("rows", result)
                    cases += 1
        self.assertEqual(cases, 304)

    def test_dsatur_handles_loops_parallel_edges_and_validates_palette(self):
        """A self-inequality is infeasible, while duplicate constraints do not matter."""
        self.assertFalse(benchmark.dsatur_trace(1, [(0, 0)], palette_size=4)["feasible"])
        single = benchmark.dsatur_trace(2, [(0, 1)], palette_size=2)
        repeated = benchmark.dsatur_trace(2, [(1, 0), (0, 1), (0, 1)], palette_size=2)
        self.assertEqual(single, repeated)
        for n, edges, palette in ((True, [], 2), (2, [(0, 2)], 2), (1, [], True), (1, [], 5)):
            with self.subTest(n=n, edges=edges, palette=palette), self.assertRaises(ValueError):
                benchmark.dsatur_trace(n, edges, palette_size=palette)

    def test_predeclared_protocol_keeps_negative_palettes_and_every_old_outer_root(self):
        """No root, family, palette or regression is selected after seeing outcomes."""
        jobs = benchmark.make_jobs()
        self.assertEqual(len(jobs), 186)
        self.assertEqual(len({job["case"]["key"] for job in jobs}), 83)
        self.assertEqual(Counter(job["corpus"] for job in jobs),
                         {"frozen-map": 126, "extra-planar-constraint": 60})
        self.assertEqual(sum(not job["expected_feasible"] for job in jobs), 10)
        self.assertEqual(max(job["case"]["n"] for job in jobs), 128)
        for job in jobs:
            if job["corpus"] == "frozen-map":
                self.assertEqual(job["root"], job["case"]["outer"])
            else:
                self.assertEqual(job["root"], 0)
                self.assertEqual(job["case"]["kind"], "planar-constraint-graph")
                result = benchmark.dsatur_trace(job["case"]["n"], job["case"]["edges"],
                                                palette_size=job["palette"])
                benchmark.check_result(job, job["order"], result)

    def test_measurement_includes_order_and_separates_memory(self):
        """Each solver has warmup + 3 clocks + separate memory; BFS is in every call."""
        job = {"case": {"n": 3, "edges": [[0, 1], [1, 2]]}, "root": 0,
               "palette": 2, "order": [0, 1, 2], "expected_feasible": True}
        calls, traced = Counter(), Counter()
        solvers = {}
        for name in benchmark.VARIANTS:
            def tracked(n, edges, order, palette_size, _name=name):
                """Use a real exact solver while instrumenting the harness contract."""
                calls[_name] += 1
                traced[_name] += benchmark.tracemalloc.is_tracing()
                return benchmark.dsatur_trace(n, edges, order, palette_size)
            solvers[name] = tracked
        ticks = iter(range(0, 1800, 100))

        def fake_clock():
            """Every measured call takes a synthetic 100 ns outside tracemalloc."""
            self.assertFalse(benchmark.tracemalloc.is_tracing())
            return next(ticks)

        with patch.object(benchmark, "traversal_order", wraps=benchmark.traversal_order) as build:
            measured = benchmark.measure_job(job, solvers, clock=fake_clock)
            self.assertEqual(build.call_count, 15)
        self.assertEqual(calls, {name: 5 for name in benchmark.VARIANTS})
        self.assertEqual(traced, {name: 1 for name in benchmark.VARIANTS})
        for position in range(3):
            self.assertEqual({row["algorithm_order"][position] for row in measured["rounds"]},
                             set(benchmark.VARIANTS))
        for name in benchmark.VARIANTS:
            self.assertEqual(measured["timing_summary"][name]["raw_ns"], [100, 100, 100])
            self.assertGreater(measured["memory"][name]["peak_traced_bytes"], 0)
        self.assertFalse(benchmark.tracemalloc.is_tracing())

    def test_aggregation_retains_regressions_and_different_measure_units(self):
        """Branch or relation counters cannot accidentally become timing costs."""
        rows = []
        for mode, reduced, feasible in (("q2", 2, False), ("q2", 8, True), ("q3", 4, True)):
            rows.append({"family": "test", "palette_mode": mode, "expected_feasible": feasible,
                         "timing_summary": {name: {"median_ns": value} for name, value in
                                            zip(benchmark.VARIANTS, (4, reduced, 2))},
                         "memory": {name: {"peak_traced_bytes": value * 10} for name, value in
                                    zip(benchmark.VARIANTS, (4, reduced, 2))}})
        groups = {row["palette_mode"]: row for row in benchmark.aggregate(rows)}
        self.assertEqual(groups["q2"]["comparisons"]["reduced_vs_orbit"]["median_ns"],
                         {"better": 1, "equal": 0, "worse": 1})
        self.assertEqual(groups["q2"]["feasible_jobs"], 1)
        self.assertEqual(groups["q3"]["comparisons"]["reduced_vs_dsatur"]["median_ns"],
                         {"better": 0, "equal": 0, "worse": 1})

    def test_checker_rejects_false_feasibility_and_output_never_overwrites(self):
        """Protect negative certificates and existing report bytes."""
        job = {"case": {"n": 3, "edges": [[0, 1], [1, 2], [0, 2]]}, "root": 0,
               "palette": 2, "order": [0, 1, 2], "expected_feasible": False}
        with self.assertRaisesRegex(ValueError, "known feasibility"):
            benchmark.check_result(job, job["order"], {"feasible": True, "one_coloring": [0, 1, 0]})
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "report.json"
            benchmark.write_report(output, {"passed": True})
            previous = output.read_bytes()
            with self.assertRaises(FileExistsError):
                benchmark.write_report(output, {"passed": False})
            self.assertEqual(previous, output.read_bytes())


if __name__ == "__main__":
    unittest.main()

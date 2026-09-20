"""Audit the benchmark protocol, comparison semantics and measurement scope."""

from collections import Counter
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import benchmark_closed_interfaces as benchmark


class ClosedInterfaceBenchmarkTests(unittest.TestCase):
    """Exercise scientific harness failures rather than duplicate solver code."""

    def setUp(self):
        """A rooted face path gives a small but nontrivial frontier relation."""
        self.case = {"key": "test-path", "family": "test", "n": 5,
                     "edges": [[0, 1], [1, 2], [2, 3], [3, 4]],
                     "outer": 2, "inner_candidates": [0, 4]}
        self.run = {"root": 2, "role": "outer", "method": "bfs", "label_seed": None,
                    "order": [2, 1, 3, 0, 4]}

    def test_frozen_corpus_has_every_declared_order_and_root(self):
        """The benchmark must not select only roots or examples that improve."""
        corpus = benchmark.load_protocol()
        self.assertEqual(len(corpus), 63)
        self.assertEqual(sum(len(entry["runs"]) for entry in corpus), 1917)
        timed = [run for entry in corpus for run in entry["runs"]
                 if run["method"] == "bfs" and run["label_seed"] is None]
        self.assertEqual(len(timed), 213)
        self.assertEqual(Counter(run["role"] for run in timed), {"outer": 63, "inner": 150})
        self.assertEqual(Counter(entry["minimum_palette"] for entry in corpus), {2: 44, 3: 12, 4: 7})

    def test_three_solvers_compare_prefix_orbits_but_not_block_prefixes(self):
        """Single-block counts are not mislabeled as the global relation."""
        result = benchmark.check_three(self.case, self.run, 4, benchmark.algorithms())
        self.assertEqual(result["prefix_orbit_counts"], [1, 1, 2, 1, 1])
        self.assertTrue(result["prefix_orbit_counts_verified"])
        self.assertEqual(result["variants"]["labeled"]["summary"]["peak_states"], 16)
        self.assertEqual(result["variants"]["orbit"]["summary"]["peak_states"], 2)
        self.assertEqual(result["variants"]["closed_interface"]["summary"]["block_count"], 4)
        solvers = benchmark.algorithms()
        real_orbit = solvers["orbit"]

        def corrupted_orbit(*args, **kwargs):
            """Simulate a subtle missed state despite a still-valid witness."""
            trace = real_orbit(*args, **kwargs)
            trace["rows"][2]["orbit_states"] = 1
            return trace

        solvers["orbit"] = corrupted_orbit
        with self.assertRaisesRegex(ValueError, "prefix orbit count differs"):
            benchmark.check_three(self.case, self.run, 4, solvers)

    def test_witness_checker_catches_invalid_colorings_and_false_payloads(self):
        """Feasibility flags alone cannot certify the returned map coloring."""
        benchmark.verify_witness(self.case, 2, {"feasible": True, "one_coloring": [0, 1, 0, 1, 0]})
        for witness in ([0, 0, 0, 0, 0], [0, 1], [0, 1, 2, 1, 0], [False, 1, 0, 1, 0]):
            with self.subTest(witness=witness), self.assertRaises(ValueError):
                benchmark.verify_witness(self.case, 2, {"feasible": True, "one_coloring": witness})
        with self.assertRaises(ValueError):
            benchmark.verify_witness(self.case, 2, {"feasible": False, "one_coloring": [0, 1, 0, 1, 0]})

    def test_measurement_rebuilds_order_and_separates_memory(self):
        """Instrument the harness to check included work and tracing exclusion."""
        calls, events = Counter(), []
        solvers = benchmark.algorithms()
        for name, solver in list(solvers.items()):
            def tracked(n, edges, order, palette_size, _name=name, _solver=solver):
                """Record solver invocation and whether this is a memory call."""
                calls[_name] += 1
                events.append(("solver", _name, benchmark.tracemalloc.is_tracing()))
                return _solver(n, edges, order, palette_size=palette_size)
            solvers[name] = tracked
        ticks = iter(range(0, 1800, 100))

        def fake_clock():
            """Each measured call takes exactly 100 synthetic nanoseconds."""
            self.assertFalse(benchmark.tracemalloc.is_tracing())
            events.append(("clock",))
            return next(ticks)

        with patch.object(benchmark, "reproduce_order", wraps=benchmark.reproduce_order) as build:
            result = benchmark.measure_job(self.case, self.run, 4, solvers, 3, clock=fake_clock)
            # Each variant: one warmup, three timed calls, one separate memory call.
            self.assertEqual(build.call_count, 15)
        self.assertEqual(calls, {name: 5 for name in benchmark.VARIANTS})
        self.assertEqual(sum(event[0] == "solver" and event[2] for event in events), 3)
        for round_row in result["rounds"]:
            self.assertEqual(set(round_row["algorithm_order"]), set(benchmark.VARIANTS))
            self.assertEqual(round_row["elapsed_ns"], {name: 100 for name in benchmark.VARIANTS})
        for position in range(3):
            self.assertEqual({row["algorithm_order"][position] for row in result["rounds"]},
                             set(benchmark.VARIANTS))
        self.assertEqual(result["median_time_ratio_labeled_over_variant"], {"orbit": 1, "closed_interface": 1})
        for record in result["memory"].values():
            self.assertGreater(record["peak_traced_bytes"], 0)
            self.assertGreaterEqual(record["peak_traced_bytes"], record["current_traced_bytes"])
        self.assertFalse(benchmark.tracemalloc.is_tracing())

    def test_groups_keep_regressions_and_palette_conditions(self):
        """Aggregation must not conceal slower or larger-state results."""
        records = []
        for mode, costs in (("four", (2, 8)), ("four", (4, 4)), ("minimum", (6, 2))):
            variants = {name: {"summary": {"peak_states": value, "attempted_transitions": value}}
                        for name, value in zip(benchmark.VARIANTS, (4, *costs))}
            records.append({"key": "test", "family": "test", "palette_mode": mode, "variants": variants})
        groups = {group["palette_mode"]: group for group in benchmark.groups(records)}
        self.assertEqual(groups["four"]["comparisons"]["orbit"]["peak_states"],
                         {"better": 1, "equal": 1, "worse": 0})
        self.assertEqual(groups["four"]["comparisons"]["closed_interface"]["peak_states"],
                         {"better": 0, "equal": 1, "worse": 1})
        self.assertEqual(groups["minimum"]["comparisons"]["orbit"]["peak_states"],
                         {"better": 0, "equal": 0, "worse": 1})

    def test_report_creation_never_overwrites_existing_evidence(self):
        """Exclusive creation protects old reports, including concurrent runs."""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            benchmark.write_report(output, {"passed": True})
            before = output.read_bytes()
            with self.assertRaises(FileExistsError):
                benchmark.write_report(output, {"passed": False})
            self.assertEqual(output.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

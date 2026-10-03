"""Synthetic privacy, recursion, and saved-profile schema checks; no production."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import cProfile
import json
import pstats
import sysconfig
import unittest

from scripts.quaternary_profile_stats import profile_rows, summarize_rows, validate_rows


ROOT = Path(__file__).resolve().parents[1]


def recursion(depth):
    """A nontrivial recursive call edge distinguishes cc from nc reliably."""
    return recursion(depth - 1) + 1 if depth else 0


def synthetic_profile():
    """Profile only an in-memory control, never the coloring implementation."""
    profiler = cProfile.Profile()
    profiler.runcall(recursion, 5)
    return profiler


def fixture():
    """Provide a hand-checkable two-node caller graph with overlapping times."""
    caller = {"file": "scripts/a.py", "line": 1, "function": "outer",
              "primitive_calls": 1, "total_calls": 1, "self_seconds": 1.0, "cumulative_seconds": 4.0}
    callee = {"file": "scripts/b.py", "line": 2, "function": "inner",
              "primitive_calls": 1, "total_calls": 1, "self_seconds": 3.0, "cumulative_seconds": 3.0}
    edge = {**caller, "self_seconds": 3.0, "cumulative_seconds": 3.0}
    return [{**caller, "callers": []}, {**callee, "callers": [edge]}]


class ProfileStatsTests(unittest.TestCase):
    """Keep diagnostic call accounting separate from benchmark speed claims."""

    def test_real_recursive_function_and_edges_use_distinct_tuple_orders(self):
        profiler = synthetic_profile()
        raw = pstats.Stats(profiler).stats
        rows = profile_rows(profiler, ROOT)
        row = next(row for row in rows if row["function"] == "recursion")
        key = next(key for key in raw if key[2] == "recursion")
        self.assertEqual((row["primitive_calls"], row["total_calls"]), raw[key][:2])
        self.assertEqual(row["primitive_calls"], 1)
        self.assertEqual(row["total_calls"], 6)
        edge = next(edge for edge in row["callers"] if edge["function"] == "recursion")
        original = raw[key][4][key]
        self.assertEqual((edge["total_calls"], edge["primitive_calls"]), original[:2])
        self.assertGreater(edge["total_calls"], edge["primitive_calls"])
        self.assertTrue(validate_rows(rows)["passed"])

    def test_self_time_is_additive_and_cumulative_ranking_is_not_summed(self):
        rows = fixture()
        summary = summarize_rows(rows)
        self.assertEqual(summary["total_self_seconds"], 4.0)
        self.assertEqual(summary["total_calls"], 2)
        self.assertEqual(summary["top_self"][0]["function"], "inner")
        self.assertEqual(summary["top_cumulative"][0]["function"], "outer")
        self.assertNotIn("total_cumulative_seconds", summary)
        self.assertEqual(summary["top_self"][0]["callers"], rows[1]["callers"])
        self.assertEqual(sum(x["self_seconds"] for x in summary["by_module"]), 4.0)
        summary["top_self"][0]["callers"].clear()
        self.assertEqual(len(rows[1]["callers"]), 1)

    def test_normalizes_repository_stdlib_builtins_generated_and_external_files(self):
        stdlib = Path(sysconfig.get_path("stdlib"))
        files = [str(ROOT / "scripts" / "fake.py"), str(stdlib / "copy.py"), "~", "<string>",
                 str(ROOT.parent / "private" / "secret.py")]
        stats = {(file, i, "fn" + str(i)): (1, 1, .01, .01, {}) for i, file in enumerate(files)}
        with patch("scripts.quaternary_profile_stats.pstats.Stats", return_value=SimpleNamespace(stats=stats)):
            rows = profile_rows(object(), ROOT)
        normalized = {row["function"]: row["file"] for row in rows}
        self.assertEqual(normalized["fn0"], "scripts/fake.py")
        self.assertEqual(normalized["fn1"], "<stdlib>/copy.py")
        self.assertEqual(normalized["fn2"], "<builtins>")
        self.assertEqual(normalized["fn3"], "<generated>/string")
        self.assertRegex(normalized["fn4"], r"^<external>/[0-9a-f]{20}$")
        self.assertNotIn("private", json.dumps(rows))
        self.assertNotIn(str(ROOT), json.dumps(rows))

    def test_function_and_generated_file_names_do_not_leak_paths_or_addresses(self):
        names = ["<built-in method C:\\private\\token.py>", "<object at 0xABCDEF1234>", "<object at 0x12>",
                 "<function /private/token.py>", "bad\nname"]
        stats = {("<generated /private/token.py>", i, name): (1, 1, 0., 0., {})
                 for i, name in enumerate(names)}
        with patch("scripts.quaternary_profile_stats.pstats.Stats", return_value=SimpleNamespace(stats=stats)):
            rows = profile_rows(object(), ROOT)
        exported = json.dumps(rows)
        for private in ("private", "token.py", "0xABCDEF1234", "0x12", "bad\\nname"):
            self.assertNotIn(private, exported)
        self.assertTrue(validate_rows(rows)["passed"])

    def test_non_cprofile_caller_scalar_is_rejected_instead_of_fabricated(self):
        key = ("~", 0, "caller")
        stats = {key: (1, 1, 0., 0., {key: 1})}
        with patch("scripts.quaternary_profile_stats.pstats.Stats", return_value=SimpleNamespace(stats=stats)):
            with self.assertRaisesRegex(ValueError, "four-counter"):
                profile_rows(object(), ROOT)

    def test_bool_nan_infinity_negative_and_counter_order_are_rejected(self):
        for field, values in {
                "line": [True, -1, 1.5], "primitive_calls": [True, -1, 2],
                "total_calls": [False, -1, 0], "self_seconds": [True, -1, float("nan"), float("inf"), 10 ** 1000, 5.0],
                "cumulative_seconds": [False, -1, float("nan"), float("inf"), .5]}.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    rows = fixture(); rows[0][field] = value
                    with self.assertRaises(ValueError): validate_rows(rows)

    def test_saved_paths_and_function_names_are_fail_closed(self):
        for value in ("/private/a.py", "C:/private/a.py", "../private/a.py", "a/../b.py",
                      "a\\b.py", "a//b.py", "<external>/private", "<stdlib>/../../a.py"):
            rows = fixture(); rows[0]["file"] = value
            with self.subTest(path=value), self.assertRaises(ValueError): validate_rows(rows)
        for value in ("C:\\private", "/private/a", "address 0x12345678", "a\nb"):
            rows = fixture(); rows[0]["function"] = value
            with self.subTest(function=value), self.assertRaises(ValueError): validate_rows(rows)

    def test_unknown_duplicate_missing_and_reordered_fields_are_rejected(self):
        variants = []
        rows = fixture(); rows[0]["extra"] = 1; variants.append(rows)
        rows = fixture(); del rows[0]["function"]; variants.append(rows)
        rows = fixture(); rows.append(deepcopy(rows[0])); variants.append(rows)
        rows = fixture(); rows[1]["callers"].append(deepcopy(rows[1]["callers"][0])); variants.append(rows)
        rows = fixture(); rows[1]["callers"][0]["function"] = "missing"; variants.append(rows)
        variants.append(list(reversed(fixture())))
        for rows in variants:
            with self.assertRaises(ValueError): validate_rows(rows)

    def test_round_trip_has_deterministic_sorted_rows_and_caller_edges(self):
        profiler = synthetic_profile()
        a = profile_rows(profiler, ROOT)
        b = profile_rows(profiler, ROOT)
        self.assertEqual(a, b)
        self.assertEqual(validate_rows(a), validate_rows(json.loads(json.dumps(a))))
        self.assertEqual(summarize_rows(a), summarize_rows(json.loads(json.dumps(a))))

    def test_empty_profile_archive_and_small_floating_error_are_allowed(self):
        self.assertEqual(validate_rows([]), {"passed": True, "function_count": 0, "caller_edge_count": 0})
        self.assertEqual(summarize_rows([])["total_self_seconds"], 0.)
        rows = fixture(); rows[1]["self_seconds"] = 3.000000000001
        self.assertTrue(validate_rows(rows)["passed"])


if __name__ == "__main__":
    unittest.main()

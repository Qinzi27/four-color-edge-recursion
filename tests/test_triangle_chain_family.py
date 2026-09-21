"""Independent geometry and complete small-coloring checks for the strip family."""

from copy import deepcopy
import unittest

from fourcolor.kempe_split import single_kempe_split
from fourcolor.triangle_chain_family import build_staggered_strip, verify_staggered_geometry


class TriangleChainFamilyTests(unittest.TestCase):
    def test_exact_geometry_and_guillotine_history(self):
        """Pairwise coordinates and cut replay certify the proposed realizations."""
        for m in (1, 2, 3, 7, 50):
            with self.subTest(m=m):
                family = build_staggered_strip(m)
                audit = verify_staggered_geometry(family)
                self.assertTrue(audit["passed"])
                self.assertEqual(audit["rectangles"], 6 * m + 3)
                self.assertEqual(audit["cuts_replayed"], 6 * m + 2)
                costs = [row["changed_old_sides"]
                         for row in family["certificate"]["targets"]]
                self.assertEqual(costs, [2*m, 5*m+1, 5*m+1, 5*m+1, 5*m+1, 2*m])

    def test_small_complete_target_oracle(self):
        """Backtracking over all four colors independently finds exactly six targets."""
        family = build_staggered_strip(1)
        p = family["problem"]
        edges = p["edges"] + [p["daughters"]]
        adjacency = {v: set() for v in p["initial"]}
        for u, v in edges:
            adjacency[u].add(v)
            adjacency[v].add(u)
        order = sorted((v for v in adjacency if v != "r"),
                       key=lambda v: -len(adjacency[v]))
        target = {"r": 0}
        found = []

        def visit(position):
            """Enumerate proper targets without using periodicity or certificate data."""
            if position == len(order):
                found.append(dict(target))
                return
            v = order[position]
            for color in range(4):
                if all(target.get(u) != color for u in adjacency[v]):
                    target[v] = color
                    visit(position + 1)
                    del target[v]

        visit(0)
        key = lambda colors: tuple(colors[v] for v in p["initial"])
        self.assertEqual({key(t) for t in found},
                         {key(row["target"]) for row in family["certificate"]["targets"]})
        self.assertEqual(len(found), 6)
        costs = [sum(w for v, w in p["weights"].items()
                     if t[v] != p["initial"][v]) for t in found]
        self.assertEqual(min(costs), 2)

    def test_one_kempe_step_can_still_change_many_old_sides(self):
        """The cost lower bound does not imply a growing number of Kempe steps."""
        for m in (1, 2, 5):
            p = build_staggered_strip(m)["problem"]
            result = single_kempe_split(p["edges"], p["initial"], p["daughters"],
                                       fixed=p["fixed"], weights=p["weights"])
            self.assertEqual(result["status"], "repaired")
            self.assertEqual(result["selected"]["changed_weight"], 2 * m)

    def test_reject_invalid_parameter(self):
        for value in (0, -1, True, 1.5, "2", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                build_staggered_strip(value)

    def test_detect_tampered_inputs(self):
        """Coordinates, cut history, constraints, colors and weights are checked."""
        original = build_staggered_strip(1)
        for kind in ("rectangle", "cut", "edge", "color", "weight"):
            family = deepcopy(original)
            if kind == "rectangle":
                family["rectangles"]["v0"][0] = -2
            elif kind == "cut":
                family["guillotine_steps"][-1]["at"] = 2
            elif kind == "edge":
                family["problem"]["edges"].pop()
            elif kind == "color":
                family["problem"]["initial"]["v0"] = 0
            else:
                family["problem"]["weights"]["v0"] = 1
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                verify_staggered_geometry(family)


if __name__ == "__main__":
    unittest.main()

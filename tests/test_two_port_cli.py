"""Check that the explicit command modes do not silently change constraints."""

import unittest

from scripts.solve_two_port import solve_input


class TwoPortCliTests(unittest.TestCase):
    """A declared interface and a graph feasibility task are different outputs."""

    def test_graph_modes(self):
        data = {"n": 3, "edges": [[0, 1], [1, 2]], "palette_size": 2}
        self.assertTrue(solve_input(data, "reduce")["feasible"])
        result = solve_input({**data, "terminals": [0, 2]}, "signature")
        self.assertEqual(result["patterns"], [[0, 0]])
        self.assertEqual(solve_input({"pieces": [], "palette_size": 1}, "glue")["mask"], 1)

    def test_reject_unknown_fields_and_missing_interfaces(self):
        for data, mode in (({"n": 2, "edges": [], "precolored": {0: 0}}, "reduce"),
                           ({"n": 2, "edges": []}, "signature"),
                           ({"pieces": [], "extra_cross_edges": [[2, 3]]}, "glue"),
                           ([], "reduce")):
            with self.assertRaises(ValueError):
                solve_input(data, mode)


if __name__ == "__main__":
    unittest.main()

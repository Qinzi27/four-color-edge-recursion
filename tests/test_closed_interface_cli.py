"""Guard the user-facing constraint contract against silently lost inputs."""

import unittest

from scripts.solve_closed_interfaces import solve_input


class ClosedInterfaceCliTests(unittest.TestCase):
    """The same input must mean the same coloring problem in all modes."""

    def test_all_modes_and_generated_order(self):
        data = {"n": 3, "edges": [[0, 1], [1, 2], [2, 0]], "palette_size": 3}
        for mode in ("named", "orbit", "blocks"):
            self.assertTrue(solve_input(data, mode)["feasible"])
            self.assertFalse(solve_input({**data, "palette_size": 2}, mode)["feasible"])

    def test_reject_unhandled_constraints(self):
        for extra in ({"precolored": {0: 0}}, {"lists": [[0]]}, {"color_cost": [1, 2]}):
            with self.assertRaises(ValueError):
                solve_input({"n": 1, "edges": [], **extra})
        for data in ([], {}, {"n": 2}):
            with self.assertRaises(ValueError):
                solve_input(data)

    def test_empty_and_explicit_invalid_order(self):
        self.assertEqual(solve_input({"n": 0, "edges": []})["one_coloring"], [])
        with self.assertRaises(ValueError):
            solve_input({"n": 2, "edges": [], "order": [0, 0]})


if __name__ == "__main__":
    unittest.main()

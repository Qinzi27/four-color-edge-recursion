"""Audit face semantics and declared experimental bounds of inside-out cases."""

from collections import Counter, deque
import unittest

from fourcolor.embedding import PlaneMap
from scripts.inside_out_fixtures import make_cases


class InsideOutFixtureTests(unittest.TestCase):
    """Check the fixtures against geometry and independent elementary counts."""

    @classmethod
    def setUpClass(cls):
        """Generate the declared corpus once; generation never edits reports."""
        cls.cases = make_cases()
        cls.by_key = {case["key"]: case for case in cls.cases}

    def test_scope_and_all_deepest_starts(self):
        """BFS independently checks that no inconvenient deepest start was dropped."""
        self.assertEqual(Counter(case["family"] for case in self.cases), {
            "original-blue-subsets": 8, "nested-jordan-tree": 37,
            "wheel-face-dual": 7, "prism-face-dual": 5,
            "rectangular-cell-map": 6,
        })
        self.assertEqual(max(case["n"] for case in self.cases), 17)
        for case in self.cases:
            with self.subTest(case=case["key"]):
                n = case["n"]
                self.assertEqual(case["edges"],
                                 [list(edge) for edge in sorted(set(map(tuple, case["edges"])))])
                adjacent = [set() for _ in range(n)]
                for a, b in case["edges"]:
                    self.assertLess(a, b)
                    adjacent[a].add(b)
                    adjacent[b].add(a)
                distances = {case["outer"]: 0}
                pending = deque([case["outer"]])
                while pending:
                    current = pending.popleft()
                    for neighbor in adjacent[current]:
                        if neighbor not in distances:
                            distances[neighbor] = distances[current] + 1
                            pending.append(neighbor)
                self.assertEqual(len(distances), n)
                self.assertEqual(case["depths"], [distances[i] for i in range(n)])
                self.assertEqual(case["inner_candidates"],
                                 [i for i in range(n) if distances[i] == max(distances.values())])

    def test_plane_evidence_yields_faces_not_primal_vertices(self):
        """Reconstruct every stored rotation and derive face inequalities anew."""
        for case in self.cases:
            geometry = case["geometry"]
            if geometry["kind"] != "verified-connected-plane-map":
                continue
            with self.subTest(case=case["key"]):
                plane = PlaneMap(tuple(map(tuple, geometry["primal_edges"])),
                                 geometry["primal_rotation"])
                self.assertEqual(case["n"], len(plane.faces))
                self.assertEqual(geometry["face_darts"], [list(face) for face in plane.faces])
                actual = set()
                for edge in range(len(plane.edges)):
                    a, b = plane.shores(edge)
                    if a != b:
                        actual.add(tuple(sorted((a, b))))
                self.assertEqual(case["edges"], [list(edge) for edge in sorted(actual)])
                self.assertEqual(geometry["euler"]["V_minus_E_plus_F"], 2)

    def test_nesting_constructive_counts_and_five_face_path(self):
        """Nested loops have tree duals and a disconnected-primal Euler formula."""
        for case in self.cases:
            if case["family"] != "nested-jordan-tree":
                continue
            with self.subTest(case=case["key"]):
                self.assertEqual(len(case["edges"]), case["n"] - 1)
                euler = case["geometry"]["euler"]
                self.assertEqual(euler["V"] - euler["E"] + euler["F"],
                                 1 + euler["components"])
        path = self.by_key["nested-arms-2-2"]
        self.assertEqual(path["n"], 5)
        self.assertEqual(path["edges"], [[0, 1], [0, 3], [1, 2], [3, 4]])
        self.assertEqual(path["inner_candidates"], [2, 4])

    def test_grid_cell_counts_and_exterior(self):
        """Cell-neighbor edges plus distinct boundary cells give the dual count."""
        for case in self.cases:
            if case["family"] != "rectangular-cell-map":
                continue
            geometry = case["geometry"]
            rows = geometry["grid_cell_rows"]
            columns = geometry["grid_cell_columns"]
            with self.subTest(case=case["key"]):
                self.assertEqual(case["n"], rows * columns + 1)
                self.assertEqual(len(case["edges"]), 2 * rows * columns + rows + columns - 4)
                exterior_degree = sum(case["outer"] in edge for edge in case["edges"])
                self.assertEqual(exterior_degree, 2 * rows + 2 * columns - 4)

    def test_original_bridge_subsets_preserve_region_adjacency(self):
        """The seven open cases are four-face stars; closure adds a fifth face."""
        for mask in range(8):
            case = self.by_key[f"circle-rank-mask-{mask}"]
            with self.subTest(mask=mask):
                self.assertEqual(case["n"], 5 if mask == 7 else 4)
                self.assertEqual(len(case["edges"]), 7 if mask == 7 else 3)
                self.assertEqual(len(case["inner_candidates"]), 2)
                self.assertEqual(max(case["depths"]), 2)


if __name__ == "__main__":
    unittest.main()

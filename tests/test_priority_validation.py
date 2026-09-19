"""Focused tamper tests for unrestricted line-side naming certificates."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fourcolor.embedding import PlaneMap
from scripts.validate_priority_names import audit_run, exclusive_output, symbols_from_names


def parallel_map() -> PlaneMap:
    """Five parallel edges bound five sides; distinct names 1..5 are legal."""
    return PlaneMap(tuple(('u', 'v') for _ in range(5)),
                    {'u': (0, 2, 4, 6, 8), 'v': (9, 7, 5, 3, 1)})


def names_for(plane: PlaneMap, symbols: tuple[int, ...]) -> list[list[int]]:
    """Generate a test certificate directly from a known side assignment."""
    return [[symbols[left], symbols[right]] for left, right in
            (plane.shores(edge) for edge in range(len(plane.edges)))]


def simple_run() -> tuple[dict, dict]:
    """Construct a two-side certificate without invoking the tested JS code."""
    plane = PlaneMap((('0', '1'), ('0', '1')), {'0': (0, 2), '1': (3, 1)})
    geometry = {'vertices': [[0, 0], [1, 0]],
                'edges': [{'a': 0, 'b': 1, 'virtual': False} for _ in range(2)],
                'rotation': [[0, 2], [3, 1]], 'faces': [list(face) for face in plane.faces],
                'faceOfDart': list(plane.face_of_dart), 'outerFace': 0,
                'original': {'vertices': 2, 'edges': 2, 'components': 1}}
    run = {'symbols': [1, 2], 'names': names_for(plane, (1, 2)), 'paletteSize': 2,
           'withinFour': True, 'backtracks': 0, 'first_fifth': None,
           'trace': [{'side': 1, 'symbol': 2, 'forbidden': [1], 'depth': 1, 'rank': 1}]}
    return geometry, run


class PriorityValidationTests(unittest.TestCase):
    """A fifth name is a rule failure, not a malformed coloring certificate."""

    def test_legal_five_names_are_accepted(self):
        plane = parallel_map()
        symbols = (1, 2, 3, 4, 5)
        self.assertEqual(symbols_from_names(plane, names_for(plane, symbols)), symbols)

    def test_inconsistent_shores_are_rejected(self):
        plane = parallel_map()
        names = names_for(plane, (1, 2, 3, 4, 5))
        names[-1][0] = 6
        with self.assertRaisesRegex(AssertionError, 'shore mismatch'):
            symbols_from_names(plane, names)

    def test_separator_equal_names_are_rejected(self):
        plane = parallel_map()
        with self.assertRaisesRegex(AssertionError, 'separator'):
            symbols_from_names(plane, names_for(plane, (1, 1, 1, 1, 1)))

    def test_bridge_has_one_side_name(self):
        plane = PlaneMap((('u', 'v'),), {'u': (0,), 'v': (1,)})
        self.assertEqual(symbols_from_names(plane, [[5, 5]]), (5,))
        with self.assertRaisesRegex(AssertionError, 'shore mismatch|bridge'):
            symbols_from_names(plane, [[5, 6]])

    def test_positive_integer_names_exclude_bools_and_zero(self):
        plane = parallel_map()
        original = names_for(plane, (1, 2, 3, 4, 5))
        for invalid in (True, 0, -1, 2.5):
            names = deepcopy(original)
            names[0][0] = invalid
            with self.assertRaisesRegex(AssertionError, 'positive integer'):
                symbols_from_names(plane, names)

    def test_existing_output_is_preserved(self):
        with TemporaryDirectory() as directory:
            target = Path(directory) / 'priority.json'
            exclusive_output({'first': True}, target)
            before = target.read_bytes()
            with self.assertRaises(FileExistsError):
                exclusive_output({'replacement': True}, target)
            self.assertEqual(target.read_bytes(), before)

    def test_greedy_trace_is_independently_checked(self):
        geometry, run = simple_run()
        self.assertEqual(audit_run(geometry, run)['steps'], 1)
        run['trace'][0]['forbidden'] = []
        with self.assertRaisesRegex(AssertionError, 'forbidden'):
            audit_run(geometry, run)

    def test_fifth_event_cannot_be_fabricated(self):
        geometry, run = simple_run()
        run['first_fifth'] = {'step': 1, **run['trace'][0]}
        with self.assertRaisesRegex(AssertionError, 'fifth-name'):
            audit_run(geometry, run)


if __name__ == '__main__':
    unittest.main()

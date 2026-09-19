"""Persisted tamper regressions for the independent research-report checker."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.validate_renaming import (
    audit_dependency_certificate, audit_hard_case, audit_move, audit_record,
    exclusive_output, validate_report,
)

ROOT = Path(__file__).resolve().parents[1]


class RenamingValidationTests(unittest.TestCase):
    """Do not let a self-consistent JSON success flag substitute for evidence."""

    @classmethod
    def setUpClass(cls):
        """Read the fixed finite report once, rebuilding the hard case afresh."""
        cls.report = json.loads((ROOT / 'outputs/renaming-round-2026-09-18-v2.json').read_text(encoding='utf-8'))
        cls.row = next(row for row in cls.report['records'] if row['seed'] == 20260927)
        cls.checked = audit_record(cls.row)
        cls.hard = cls.report['hard_case']

    def test_saved_report_is_independently_valid(self):
        summary = validate_report(self.report)
        self.assertTrue(summary['all_passed'])
        self.assertEqual(summary['reconstructed_maps'], 320)
        self.assertEqual(summary['witnesses_checked'], 167)
        self.assertEqual(summary['hard_case']['minimum_split_stage_swaps'], 3)
        self.assertEqual(summary['hard_case']['reachable_H_assignments'], 78)
        self.assertEqual(summary['hard_case']['dependency_execution_order'], [9, 2, 3])

    def test_source_hash_tampering_is_rejected(self):
        report = {**self.report, 'source_sha256': '0' * 64}
        with self.assertRaisesRegex(AssertionError, 'hash'):
            validate_report(report)

    def test_partial_component_is_rejected(self):
        adjacency = (frozenset({1}), frozenset({0, 2}), frozenset({1}))
        with self.assertRaisesRegex(AssertionError, 'complete'):
            audit_move(adjacency, (0, 1, 0), 0, [0, 1], [2], [0, 1, 1])

    def test_missing_dependency_is_rejected(self):
        proof = deepcopy(self.hard['dependency'])
        proof['dependencies'][0]['blockers'] = []
        with self.assertRaisesRegex(AssertionError, 'dependencies'):
            audit_dependency_certificate(self.row, self.checked, proof, tuple(self.hard['minimum']['colors']))

    def test_corrupt_line_name_is_rejected(self):
        proof = deepcopy(self.hard['dependency'])
        proof['names'][0][0] = (proof['names'][0][0] + 1) % 4
        with self.assertRaises(AssertionError):
            audit_dependency_certificate(self.row, self.checked, proof, tuple(self.hard['minimum']['colors']))

    def test_false_shortest_depth_is_rejected(self):
        hard = deepcopy(self.hard)
        hard['bfs']['depth'] = 2
        with self.assertRaisesRegex(AssertionError, 'shortest'):
            audit_hard_case(self.row, self.checked, hard)

    def test_existing_output_is_preserved(self):
        with TemporaryDirectory() as directory:
            target = Path(directory) / 'independent.json'
            exclusive_output({'first': True}, target)
            before = target.read_bytes()
            with self.assertRaises(FileExistsError):
                exclusive_output({'replacement': True}, target)
            self.assertEqual(target.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()

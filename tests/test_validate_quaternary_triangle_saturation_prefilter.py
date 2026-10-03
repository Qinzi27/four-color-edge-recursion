"""Synthetic runner calibration before the formal paired experiment freeze."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import validate_quaternary_triangle_saturation_prefilter as runner
from tests.test_quaternary_triangle_saturation import triangle_document


class PrefilterRunnerTests(unittest.TestCase):
    """Test complete equivalence, work replay, failure retention and pair timing."""

    @classmethod
    def setUpClass(cls):
        """Use one small synthetic raw graph, never the saved formal population."""
        cls.raw = triangle_document()
        cls.expected = runner.solve_triangle_saturation(cls.raw)
        cls.entry = {'scenario': 'fixture', 'raw_document': cls.raw, 'result': cls.expected,
                     'policy': 'triangle-saturation', 'execution': 'audited'}
        cls.record = {'key': 'fixture', 'geometry': None, 'scenes': [{'id': 'fixture'}]}

    def test_inventory_generation_performs_no_discovery(self):
        """All formal rule identities are fixed without evaluating a detector."""
        with patch.object(runner, 'find_triangle_saturations', side_effect=AssertionError), \
             patch.object(runner, 'find_triangle_saturations_prefilter', side_effect=AssertionError):
            cases = runner.rule_cases()
        self.assertEqual(len(cases), 6120)
        self.assertEqual(len({r['id'] for r in cases}), 6120)
        self.assertEqual(sum(r['family'] == 'gate-target-domain-cube' for r in cases), 4608)
        self.assertTrue(any(not r['domains'][-1] for r in cases))

    def test_paired_order_and_only_call_timing(self):
        """Balanced AB/BA order is explicit and each call gets its own duration."""
        calls = []
        def old():
            calls.append('old')
            return {'value': 1}
        def new():
            calls.append('new')
            return {'value': 1}
        with patch.object(runner, 'perf_counter', side_effect=range(8)):
            result, times = runner.paired(old, new, {'value': 1}, 0)
        self.assertEqual(calls, ['old', 'new', 'new', 'old'])
        self.assertEqual(result, {'value': 1})
        self.assertTrue(all(t['old_seconds'] == t['new_seconds'] == 1 for t in times))
        runner.verify_timing(times, result, 0)

    def test_pair_parity_and_saved_type_checks(self):
        """Reversed order, bool durations and omitted repetitions cannot pass."""
        _, times = runner.paired(lambda: {}, lambda: {}, {}, 1)
        self.assertEqual(times[0]['order'], ['new', 'old'])
        runner.verify_timing(times, {}, 1)
        for field, value in (('new_seconds', True), ('new_seconds', float('nan')),
                             ('new_sha256', 'changed'), ('order', ['old', 'new'])):
            bad = deepcopy(times)
            bad[0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(AssertionError):
                runner.verify_timing(bad, {}, 1)

    def test_full_output_mismatch_preserves_actual_and_expected(self):
        """A first differing trace is retained instead of only its hash/error."""
        with self.assertRaises(runner.EquivalenceMismatch) as caught:
            runner.paired(lambda: {'good': 1}, lambda: {'bad': 2}, {'good': 1}, 0)
        self.assertEqual(caught.exception.evidence['actual'], {'bad': 2})
        with TemporaryDirectory() as folder:
            runner.record_failure(Path(folder), 'freeze', {'fixture': 1}, caught.exception)
            files = list(Path(folder).glob('failure-*.json.gz'))
            self.assertEqual(len(files), 1)
            saved = runner.read_report(files[0])
            self.assertFalse(saved['complete'])
            self.assertEqual(saved['evidence']['expected'], {'good': 1})

    def test_recorded_work_matches_the_real_instrumented_producer(self):
        """Separate call-input replay records the same work as live telemetry."""
        live = []
        result = runner.solve_prefilter_triangle_saturation(self.raw, work_log=live)
        replay = runner.measure_work(result, producer=True)
        self.assertEqual([r['telemetry'] for r in replay], live)
        with patch.object(runner, 'find_triangle_saturations_prefilter', side_effect=AssertionError):
            runner.check_work(result, replay, producer=True)

    def test_saved_work_rejects_missing_calls_and_altered_counts(self):
        """No detector invocation may disappear during aggregation."""
        work = runner.measure_work(self.expected, producer=True)
        self.assertTrue(work)
        with self.assertRaises(AssertionError):
            runner.check_work(self.expected, work[:-1], producer=True)
        bad = deepcopy(work)
        bad[0]['telemetry']['statistics']['triangles_enumerated'] += 1
        with self.assertRaises(AssertionError):
            runner.check_work(self.expected, bad, producer=True)

    def test_rule_batch_and_saved_check_without_detectors(self):
        """Evaluate one small calibration; declaration-wide evaluation waits."""
        case = {'id': 'fixture', 'document': self.raw,
                'domains': [[1, 2, 3, 4] for _ in self.raw['sides']], 'equal_names': []}
        rows = runner.rule_batch([case])
        with patch.object(runner, 'find_triangle_saturations', side_effect=AssertionError), \
             patch.object(runner, 'find_triangle_saturations_prefilter', side_effect=AssertionError):
            runner.verify_rules([case], rows)
        bad = deepcopy(rows)
        bad[0]['input_sha256'] = 'changed'
        with self.assertRaises(AssertionError):
            runner.verify_rules([case], bad)

    def test_drawing_saved_replay_never_runs_producers_or_propagators(self):
        """A synthetic end-to-end drawing retains its whole returned envelope."""
        context = ([self.entry], {})
        with patch.object(runner, 'context', return_value=context):
            saved = runner.run_drawing({}, self.record, 0)
            with patch.object(runner, 'solve_triangle_saturation', side_effect=AssertionError), \
                 patch.object(runner, 'solve_prefilter_triangle_saturation', side_effect=AssertionError), \
                 patch.object(runner, 'propagate_saturation_contacts', side_effect=AssertionError), \
                 patch.object(runner, 'propagate_prefilter_contacts', side_effect=AssertionError), \
                 patch.object(runner, 'find_triangle_saturations_prefilter', side_effect=AssertionError):
                runner.verify_drawing({}, self.record, saved, 0)
        self.assertEqual(saved['runs'][0]['result'], self.expected)

    def test_drawing_coverage_and_full_nested_output_are_required(self):
        """An equal final color list cannot conceal a missing nested phase."""
        with patch.object(runner, 'context', return_value=([self.entry], {})):
            saved = runner.run_drawing({}, self.record, 0)
            omitted = deepcopy(saved)
            omitted['runs'] = []
            with self.assertRaises(AssertionError):
                runner.verify_drawing({}, self.record, omitted, 0)
            saved['runs'][0]['result']['run']['phases'][0]['kind'] = 'tampered'
            with self.assertRaises(AssertionError):
                runner.verify_drawing({}, self.record, saved, 0)

    def test_summary_keeps_actual_work_and_clock_totals_separate(self):
        """Two paired repetitions do not multiply one-execution work counts."""
        with patch.object(runner, 'context', return_value=([self.entry], {})):
            saved = runner.run_drawing({}, self.record, 0)
        summary = runner.summary([runner.compact(saved)], [])
        self.assertEqual(summary['production']['items'], 1)
        self.assertEqual(len(summary['production']['paired_repetitions']), 2)
        self.assertEqual(summary['production']['detector_calls'], len(saved['runs'][0]['work']))
        self.assertEqual(summary['diagnostics']['items'], 0)


if __name__ == '__main__':
    unittest.main()

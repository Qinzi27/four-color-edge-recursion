"""Calibrate profiling scope, equivalence and saved replay on synthetic inputs."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import validate_quaternary_triangle_saturation_profile as runner
from tests.test_quaternary_triangle_saturation import triangle_document


class ProducerProfileTests(unittest.TestCase):
    """Check genuine producer profiling and adversarial saved telemetry."""

    @classmethod
    def setUpClass(cls):
        """Use a small named fixture, never the frozen formal population."""
        cls.raw = triangle_document()
        cls.expected = runner.previous.solve_prefilter_triangle_saturation(cls.raw)
        cls.scene = {'id': 'fixture', 'index': 0, 'faces': len(cls.raw['sides']),
                     'stratum': runner.stratum(len(cls.raw['sides'])),
                     'envelope_sha256': runner.digest(cls.expected), 'raw_sha256': runner.digest(cls.raw)}
        cls.profile_result = runner.measured_scene(cls.raw, None, cls.expected, cls.scene)

    def test_full_producer_is_profiled_and_input_is_unchanged(self):
        """The profile includes the actual entrypoint and preserves its trace."""
        runner.verify_scene(self.profile_result, self.scene, self.expected)
        self.assertEqual(self.profile_result['order'], ['plain', 'profile'])
        self.assertEqual(self.profile_result['result'], self.expected)
        self.assertTrue(self.profile_result['functions'])
        self.assertGreater(self.profile_result['profile_seconds'], 0)

    def test_alternating_order_has_no_semantic_effect(self):
        """Both orders are exercised before the measured corpus is frozen."""
        scene = {**self.scene, 'index': 1}
        result = runner.measured_scene(self.raw, None, self.expected, scene)
        self.assertEqual(result['order'], ['profile', 'plain'])
        runner.verify_scene(result, scene, self.expected)

    def test_wrong_complete_output_retains_evidence(self):
        """A partial or changed result cannot pass merely by matching colors."""
        with patch.object(runner.previous, 'solve_prefilter_triangle_saturation', return_value={'colors': []}):
            with self.assertRaises(runner.previous.EquivalenceMismatch) as caught:
                runner.measured_scene(self.raw, None, self.expected, self.scene)
        self.assertEqual(caught.exception.evidence['actual'], {'colors': []})

    def test_saved_corruptions_are_rejected_without_producer(self):
        """Hashes, times, scene identities and full traces are independently bound."""
        changes = [('plain_seconds', True), ('profile_seconds', float('nan')),
                   ('plain_sha256', 'bad'), ('faces', 99), ('index', 1),
                   ('order', ['profile', 'plain']), ('functions', [])]
        with patch.object(runner.previous, 'solve_prefilter_triangle_saturation', side_effect=AssertionError('rerun')):
            for field, value in changes:
                bad = deepcopy(self.profile_result)
                bad[field] = value
                with self.subTest(field=field), self.assertRaises((AssertionError, ValueError)):
                    runner.verify_scene(bad, self.scene, self.expected)
            bad = deepcopy(self.profile_result)
            bad['result']['run']['phases'][0]['kind'] = 'changed'
            with self.assertRaises(AssertionError):
                runner.verify_scene(bad, self.scene, self.expected)

    def test_original_side_strata_include_boundaries(self):
        """Size groups are deterministic and reject booleans or empty inputs."""
        self.assertEqual([runner.stratum(n) for n in (1, 4, 5, 8, 9, 12, 13, 100)],
                         ['1-4', '1-4', '5-8', '5-8', '9-12', '9-12', '13+', '13+'])
        for value in (0, -1, True, 4.0):
            with self.assertRaises(AssertionError):
                runner.stratum(value)

    def test_omitted_functions_do_not_pass_by_retaining_only_root(self):
        """Bind complete exported coverage to the profiler snapshot counters."""
        bad = deepcopy(self.profile_result)
        bad['functions'] = [r for r in bad['functions'] if r['function'] == 'solve_prefilter_triangle_saturation']
        for row in bad['functions']:
            row['callers'] = []
        with self.assertRaises(AssertionError):
            runner.verify_scene(bad, self.scene, self.expected)
        for field in ('function_count', 'total_calls', 'primitive_calls', 'self_seconds'):
            bad = deepcopy(self.profile_result)
            bad['profile_totals'][field] += 1
            with self.subTest(field=field), self.assertRaises(AssertionError):
                runner.verify_scene(bad, self.scene, self.expected)

    def test_merging_separate_profiles_adds_calls_and_exclusive_seconds(self):
        """Merge by full function identity and preserve all caller edges."""
        rows = self.profile_result['functions']
        merged = runner.merge_rows([rows, rows])
        for original, new in zip(rows, merged):
            self.assertEqual(new['function'], original['function'])
            for field in runner.FIELDS:
                self.assertEqual(new[field], 2 * original[field])
            for old_caller, new_caller in zip(original['callers'], new['callers']):
                for field in runner.FIELDS:
                    self.assertEqual(new_caller[field], 2 * old_caller[field])

    def test_summary_reconciles_scope_and_plain_profile_time(self):
        """Never label profiling overhead as algorithm acceleration."""
        items = runner.compact({'key': 'fixture', 'runs': [self.profile_result]})
        result = runner.summary(items)
        self.assertEqual(result['all']['scenes'], 1)
        self.assertEqual(result['all']['plain_seconds'], self.profile_result['plain_seconds'])
        self.assertEqual(sum(result[s]['scenes'] for s in runner.STRATA), 1)
        self.assertEqual(result['all']['functions'], self.profile_result['functions'])
        self.assertNotIn('result', items[0])

    def test_saved_drawing_rejects_omitted_scene(self):
        """Excluded and eligible drawing records require exact declared coverage."""
        row = {'key': 'fixture', 'scenes': [self.scene]}
        m = {'input_sha256': {runner.ARCHIVES[0]: 'bound'}}
        with patch.object(runner, 'load_parent', return_value=[{'result': self.expected}]), \
             patch.object(runner.previous, 'solve_prefilter_triangle_saturation', side_effect=AssertionError('rerun')):
            runner.verify_drawing(m, row, {'key': 'fixture', 'runs': [self.profile_result]})
            with self.assertRaises(AssertionError):
                runner.verify_drawing(m, row, {'key': 'fixture', 'runs': []})

    def test_complete_saved_check_has_no_live_profile_or_producer(self):
        """Replay a literal small checkpoint with live execution disabled."""
        row = {'key': 'fixture', 'scenes': [self.scene]}
        saved = {'key': 'fixture', 'runs': [self.profile_result]}
        m = {'source_sha256': {}, 'counts': {'scenes': 1}, 'records': [row],
             'input_sha256': {runner.ARCHIVES[0]: 'parent'}, 'environment': runner.environment()}
        with TemporaryDirectory() as folder:
            root = Path(folder)
            manifest, report, output = (root / n for n in ('manifest.json', 'report.json', 'check.json'))
            runner.write_atomic(manifest, m)
            mh = runner.checksum(manifest)
            checkpoint = root / 'checkpoint.json'
            runner.write_atomic(checkpoint, {'manifest_sha256': mh, 'record_sha256': runner.digest(row), 'result': saved})
            r = {'version': runner.VERSION, 'manifest_sha256': mh, 'checkpoints': [{'fixture': True}],
                 'summary': runner.summary(runner.compact(saved)),
                 'execution': {'workers': 1, 'oracle_searches': 0, 'resumed_drawings': 0,
                               'wall_seconds': 1.0, 'environment': runner.environment()}}
            runner.write_atomic(report, r)
            with patch.object(runner, 'bound_manifest', return_value=m), \
                 patch.object(runner, 'sources', return_value={}), \
                 patch.object(runner, 'bound_reference', return_value=runner.read_report(checkpoint)), \
                 patch.object(runner, 'load_parent', return_value=[{'result': self.expected}]), \
                 patch.object(runner, 'profile_rows', side_effect=AssertionError('live profile')), \
                 patch.object(runner.previous, 'solve_prefilter_triangle_saturation', side_effect=AssertionError('producer')):
                result = runner.check(manifest, report, output)
            self.assertTrue(result['passed'])
            self.assertEqual(result['producer_reruns'], 0)

    def test_valid_completed_checkpoint_resumes_without_producing(self):
        """A valid complete drawing is replayed, while a changed binding fails."""
        row = {'key': 'fixture', 'scenes': [self.scene]}
        m = {'source_sha256': {}, 'records': [row], 'environment': runner.environment(),
             'input_sha256': {runner.ARCHIVES[0]: 'parent'}}
        with TemporaryDirectory() as folder:
            root = Path(folder)
            manifest, output = root / 'manifest.json', root / 'run.json.gz'
            runner.write_atomic(manifest, m)
            checkpoint = root / 'run-checkpoints' / '000-fixture.json.gz'
            saved = {'manifest_sha256': runner.checksum(manifest), 'record_sha256': runner.digest(row),
                     'result': {'key': 'fixture', 'runs': [self.profile_result]}}
            runner.write_atomic(checkpoint, saved)
            with patch.object(runner, 'bound_manifest', return_value=m), \
                 patch.object(runner, 'sources', return_value={}), \
                 patch.object(runner, 'load_parent', return_value=[{'result': self.expected}]), \
                 patch.object(runner, 'reference', side_effect=lambda p: {'test_name': p.name}), \
                 patch.object(runner, 'measured_scene', side_effect=AssertionError('rerun')):
                runner.execute(manifest, output)
                self.assertEqual(runner.read_report(output)['execution']['resumed_drawings'], 1)
                bad_output = root / 'bad.json.gz'
                bad_path = root / 'bad-checkpoints' / '000-fixture.json.gz'
                runner.write_atomic(bad_path, {**saved, 'record_sha256': 'changed'})
                with self.assertRaises(AssertionError):
                    runner.execute(manifest, bad_output)


if __name__ == '__main__':
    unittest.main()

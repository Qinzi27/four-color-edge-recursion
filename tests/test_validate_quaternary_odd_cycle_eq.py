"""Check paired experiment bookkeeping with tiny and synthetic cases only."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import validate_quaternary_odd_cycle_eq as experiment


class OddCycleEqExperimentTests(unittest.TestCase):
    """Future geometric holdouts are not run by the comparison unit fixtures."""

    def tiny_row(self):
        """A small raw triangle checks producer/auditor sequencing cheaply."""
        raw = {'sides': ['a', 'b', 'c'], 'anchors': {'a': 1}, 'lines': [
            {'id': str(i), 'kind': 'separator', 'left': a, 'right': b}
            for i, (a, b) in enumerate([('a', 'b'), ('b', 'c'), ('a', 'c')])]}
        return experiment.classify({'key': 'tiny', 'kind': 'abstract', 'document': raw})

    def test_both_producers_finish_before_either_audit(self):
        order = []
        functions = {name: getattr(experiment, name) for name in (
            'solve_triangle_eq', 'solve_odd_cycle_eq', 'audit_triangle_eq', 'audit_odd_cycle_eq')}

        def record(name):
            """Record actual helper invocation, while retaining real validation."""
            def wrapped(*args, **kwargs):
                order.append(name)
                return functions[name](*args, **kwargs)
            return wrapped

        with patch.multiple(experiment, **{name: record(name) for name in functions}):
            row = experiment.run_record(self.tiny_row())
        self.assertEqual(order, list(functions))
        self.assertEqual([r['execution'] for r in row['runs']], ['audited', 'audited'])
        self.assertEqual(experiment.comparison(*row['runs']), 'both_success')
        self.assertEqual(experiment.underlying(row['runs'][0]), experiment.underlying(row['runs'][1]))

    def test_producer_failure_retains_other_policy_and_raw_case(self):
        with patch.object(experiment, 'solve_odd_cycle_eq', side_effect=RuntimeError('interrupted')):
            row = experiment.run_record(self.tiny_row())
        self.assertEqual(len(row['runs']), 2)
        self.assertEqual(row['runs'][0]['execution'], 'audited')
        self.assertEqual(row['runs'][1]['execution'], 'producer_error')
        self.assertIn('raw_document', row['runs'][1])
        self.assertEqual(experiment.comparison(*row['runs']), 'unresolved_or_initial_unsat')

    def test_unknown_and_unsafe_are_not_success_from_terminal_status(self):
        entry = experiment.run_record(self.tiny_row())['runs'][0]
        altered = deepcopy(entry)
        altered['audit']['oracle_unknown'] = 1
        self.assertEqual(experiment.quality(altered), 'unknown')
        self.assertEqual(experiment.comparison(entry, altered), 'unresolved_or_initial_unsat')
        altered = deepcopy(entry)
        altered['audit']['commitment_counts']['unsafe'] = 1
        self.assertEqual(experiment.quality(altered), 'unsafe')
        self.assertEqual(experiment.comparison(entry, altered), 'regression')
        self.assertEqual(experiment.comparison(altered, entry), 'repair')

    def test_geometry_exclusion_retained_without_producer_call(self):
        raw = {'key': 'bad', 'kind': 'geometry', 'document': {'strokes': []}}
        exported = {'key': 'bad', 'status': 'geometry_error', 'errors': ['precision']}
        row = experiment.classify(raw, exported)
        self.assertEqual(row['eligibility'], 'geometry_error')
        self.assertEqual(row['error'], ['precision'])
        with patch.object(experiment, 'solve_triangle_eq', side_effect=AssertionError('unexpected')):
            self.assertEqual(experiment.run_record(row)['runs'], [])

    def test_prior_exclusion_cannot_be_silently_reclassified(self):
        prior = {'eligibility': 'geometry_audit_error', 'error': 'bad contact',
                 'export': {'key': 'prior', 'status': 'geometry_ok', 'geometry': {}}}
        raw = {'key': 'prior', 'kind': 'geometry', 'document': {}, 'prior_record': prior}
        row = experiment.classify(raw, prior['export'])
        self.assertEqual(row['eligibility'], 'geometry_audit_error')
        with self.assertRaises(AssertionError):
            experiment.classify(raw, {'key': 'prior', 'status': 'geometry_error'})

    def test_overlapping_populations_do_not_duplicate_runs_or_history_prefixes(self):
        """One shared drawing belongs to two populations but has four runs total."""
        row = self.tiny_row()
        row['original']['populations'] = ['regression-triangle', 'fresh-declared']
        row['original']['new_key_against_archives'] = False
        row['original']['holdout_metadata'] = {'families': ['synthetic']}
        row['scenarios'] = [{'id': mode, 'anchors': {'a': 1}}
                            for mode in ('one-bounded-anchor', 'legacy-frame-anchors')]
        saved = experiment.run_record(row)
        history = {'id': 'fixture-history', 'prefix_keys': ['tiny', 'tiny']}
        manifest = {'records': [row], 'inventory': {
            'holdout': {'histories': [history]}, 'regression_histories': [history]}}
        summary = experiment.summarize([saved], manifest)
        self.assertEqual(len(saved['runs']), 4)
        self.assertEqual(summary['comparison_counts'], {'both_success': 2})
        for population in ('all-records', 'regression-triangle', 'fresh-declared'):
            for policy in experiment.POLICIES:
                self.assertEqual(summary['groups'][population + '/' + policy]['runs'], 2)
        self.assertEqual(len(summary['histories']), 8)
        self.assertTrue(all(h['qualities'] == ['success', 'success']
                            for h in summary['histories']))
        self.assertTrue(all(p['additional_eq_count'] == 0 for p in summary['paired']))

    def test_identical_eq_trace_mismatch_retained_as_uncompleted(self):
        """An equivalence guard failure keeps the evidence instead of dropping it."""
        real_same = experiment.same

        def reject_identity(first, second, label):
            if label == 'identical-EQ behavior changed':
                raise AssertionError('fixture identity mismatch')
            return real_same(first, second, label)

        with patch.object(experiment, 'same', side_effect=reject_identity):
            saved = experiment.run_record(self.tiny_row())
        self.assertEqual(saved['runs'][1]['execution'], 'equivalence_error')
        self.assertIn('result', saved['runs'][1])
        self.assertIn('audit', saved['runs'][1])
        self.assertEqual(experiment.comparison(*saved['runs']), 'unresolved_or_initial_unsat')

    def test_saved_checker_rejects_rehashed_coverage_and_summary_tampering(self):
        """Byte hashes alone cannot make omitted policy evidence or false totals valid."""
        row = self.tiny_row()
        row['original'].update(populations=['fixture'], new_key_against_archives=False)
        saved = experiment.run_record(row)
        manifest = {'records': [row], 'source_sha256': {'fixture': 'fixed'},
                    'inventory': {'holdout': {'histories': []}, 'regression_histories': []}}
        for mutation in ('none', 'coverage', 'summary'):
            with self.subTest(mutation=mutation), TemporaryDirectory(dir=experiment.ROOT / 'outputs') as directory:
                base = Path(directory)
                manifest_path, report_path = base / 'manifest.json', base / 'report.json'
                experiment.write_report(manifest_path, manifest)
                manifest_hash = experiment.checksum(manifest_path)
                altered = deepcopy(saved)
                if mutation == 'coverage':
                    altered['runs'].pop()
                checkpoint, rule_path = base / 'checkpoint.json', base / 'rule.json'
                experiment.write_report(checkpoint, {'manifest_sha256': manifest_hash,
                    'record_sha256': experiment.digest(row), 'row': altered})
                experiment.write_report(rule_path, {'manifest_sha256': manifest_hash,
                                                    'result': {'fixture': True}})

                def reference(path):
                    """Bind even deliberately mutated artifacts to their actual bytes."""
                    return {'path': path.relative_to(experiment.ROOT).as_posix(),
                            'sha256': experiment.checksum(path)}

                summary = experiment.summarize([saved], manifest)
                if mutation == 'summary':
                    summary['comparison_counts']['both_success'] = 99
                experiment.write_report(report_path, {'schema_version': 1, 'version': experiment.VERSION,
                    'manifest_sha256': manifest_hash, 'rule_evidence': reference(rule_path),
                    'checkpoints': [reference(checkpoint)], 'summary': summary})
                with patch.object(experiment, 'bound_manifest', return_value=manifest), \
                        patch.object(experiment, 'sources', return_value=manifest['source_sha256']), \
                        patch.object(experiment, 'check_rule_soundness', return_value={'fixture': True}), \
                        patch.object(experiment, 'solve_triangle_eq', side_effect=AssertionError('producer rerun')), \
                        patch.object(experiment, 'solve_odd_cycle_eq', side_effect=AssertionError('producer rerun')), \
                        patch('scripts.audit_quaternary_odd_cycle_eq.solve_exact', side_effect=AssertionError('oracle rerun')), \
                        patch('scripts.audit_quaternary_triangle_eq.solve_exact', side_effect=AssertionError('oracle rerun')):
                    if mutation == 'none':
                        counts = experiment.check(manifest_path, report_path, base / 'check.json')
                        self.assertEqual(counts['audited_runs'], 2)
                    else:
                        with self.assertRaises(AssertionError):
                            experiment.check(manifest_path, report_path, base / 'check.json')


if __name__ == '__main__':
    unittest.main()

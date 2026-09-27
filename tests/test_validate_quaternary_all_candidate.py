"""Exercise experiment sequencing and saved evidence binding on tiny fixtures."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import validate_quaternary_all_candidate as experiment


class AllCandidateExperimentTests(unittest.TestCase):
    """Fresh formal drawings are never colored in runner unit tests."""

    def tiny_row(self):
        """A triangle needs actual choices without expensive graph searches."""
        raw = {'sides': ['a', 'b', 'c'], 'anchors': {'a': 1}, 'lines': [
            {'id': str(i), 'kind': 'separator', 'left': a, 'right': b}
            for i, (a, b) in enumerate([('a', 'b'), ('b', 'c'), ('a', 'c')])]}
        return experiment.classify({'key': 'tiny', 'kind': 'abstract', 'document': raw,
            'populations': ['fixture'], 'new_key_against_archives': False})

    def manifest(self, row):
        """The tiny census uses the same summary shape as the frozen run."""
        return {'records': [row], 'source_sha256': {'fixture': 'fixed'},
                'inventory': {'holdout': {'histories': []}, 'regression_histories': []}}

    def test_producers_finish_before_oracle_audits(self):
        order = []
        names = ('solve_odd_cycle_eq', 'solve_all_candidate_low_color',
                 'audit_odd_cycle_eq', 'audit_all_candidates')
        functions = {name: getattr(experiment, name) for name in names}

        def tracked(name):
            """Retain actual validation while recording the call boundary."""
            def wrapper(*args, **kwargs):
                order.append(name)
                return functions[name](*args, **kwargs)
            return wrapper

        with patch.multiple(experiment, **{n: tracked(n) for n in names}):
            saved = experiment.run_record(self.tiny_row())
        self.assertEqual(order, list(names))
        self.assertEqual([e['execution'] for e in saved['runs']], ['audited', 'audited'])
        self.assertEqual([e['result']['run']['probe_limit'] for e in saved['runs']], [8192, 8192])

    def test_failure_is_kept_and_never_becomes_success(self):
        with patch.object(experiment, 'solve_all_candidate_low_color', side_effect=RuntimeError('fixture')):
            saved = experiment.run_record(self.tiny_row())
        compact = experiment.compact_row(saved)
        self.assertEqual(compact['runs'][1]['quality'], 'uncompleted')
        summary = experiment.summarize([compact], self.manifest(self.tiny_row()))
        self.assertEqual(summary['comparison_counts'], {'unresolved_or_initial_unsat': 1})

    def test_exclusion_does_not_call_producer(self):
        row = {'key': 'bad', 'eligibility': 'geometry_error', 'scenarios': []}
        with patch.object(experiment, 'solve_odd_cycle_eq', side_effect=AssertionError('unexpected')):
            self.assertEqual(experiment.run_record(row)['runs'], [])

    def test_shared_populations_do_not_duplicate_total_runs(self):
        row = self.tiny_row()
        row['original']['populations'] = ['regression-odd', 'fresh-declared']
        compact = experiment.compact_row(experiment.run_record(row))
        summary = experiment.summarize([compact], self.manifest(row))
        self.assertEqual(summary['comparison_counts'], {'both_success': 1})
        for population in ('all-records', 'regression-odd', 'fresh-declared'):
            for policy in experiment.POLICIES:
                self.assertEqual(summary['groups'][population + '/' + policy]['runs'], 1)

    def test_saved_checker_rejects_rehashed_omission_and_false_totals(self):
        row = self.tiny_row()
        saved = experiment.run_record(row)
        manifest = self.manifest(row)
        for mutation in ('none', 'coverage', 'summary'):
            with self.subTest(mutation=mutation), TemporaryDirectory(dir=experiment.ROOT / 'outputs') as directory:
                base = Path(directory)
                manifest_path, report_path, checkpoint = base / 'manifest.json', base / 'report.json', base / 'case.json'
                experiment.write_report(manifest_path, manifest)
                manifest_hash = experiment.checksum(manifest_path)
                altered = deepcopy(saved)
                if mutation == 'coverage':
                    altered['runs'].pop()
                experiment.write_report(checkpoint, {'manifest_sha256': manifest_hash,
                    'record_sha256': experiment.digest(row), 'row': altered})
                summary = experiment.summarize([experiment.compact_row(saved)], manifest)
                if mutation == 'summary':
                    summary['comparison_counts']['both_success'] = 999
                experiment.write_report(report_path, {'schema_version': 1, 'version': experiment.VERSION,
                    'manifest_sha256': manifest_hash, 'checkpoints': [{
                        'path': checkpoint.relative_to(experiment.ROOT).as_posix(),
                        'sha256': experiment.checksum(checkpoint)}], 'summary': summary})
                with patch.object(experiment, 'bound_manifest', return_value=manifest), \
                        patch.object(experiment, 'sources', return_value=manifest['source_sha256']), \
                        patch('scripts.audit_quaternary_all_candidate.solve_exact', side_effect=AssertionError('search rerun')), \
                        patch('scripts.audit_quaternary_odd_cycle_eq.solve_exact', side_effect=AssertionError('search rerun')):
                    if mutation == 'none':
                        counts = experiment.check(manifest_path, report_path, base / 'check.json')
                        self.assertEqual(counts['audited_runs'], 2)
                    else:
                        with self.assertRaises(AssertionError):
                            experiment.check(manifest_path, report_path, base / 'check.json')


if __name__ == '__main__':
    unittest.main()

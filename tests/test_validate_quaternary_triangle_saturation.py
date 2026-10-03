"""Exercise experiment sequencing and saved evidence binding on tiny fixtures."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import validate_quaternary_triangle_saturation as experiment


class TriangleSaturationExperimentTests(unittest.TestCase):
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
        return {'records': [row], 'source_sha256': {'fixture': 'fixed'}, 'gap_inventory': {'groups': []},
                'rule_declaration': {'inventory': [], 'inventory_sha256': experiment.digest([]),
                                     'production_oracle_or_propagation_performed': False},
                'inventory': {'holdout': {'histories': []}, 'regression_histories': []}}

    def test_producers_finish_before_oracle_audits(self):
        order = []
        names = ('solve_conditional_diamond', 'solve_triangle_saturation',
                 'audit_conditional_diamond', 'audit_triangle_saturation')
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
        with patch.object(experiment, 'solve_triangle_saturation', side_effect=RuntimeError('fixture')):
            saved = experiment.run_record(self.tiny_row())
        compact = experiment.compact_row(saved)
        self.assertEqual(compact['runs'][1]['quality'], 'uncompleted')
        summary = experiment.summarize([compact], self.manifest(self.tiny_row()))
        self.assertEqual(summary['comparison_counts'], {'unresolved_or_initial_unsat': 1})

    def test_exclusion_does_not_call_producer(self):
        row = {'key': 'bad', 'eligibility': 'geometry_error', 'scenarios': []}
        with patch.object(experiment, 'solve_conditional_diamond', side_effect=AssertionError('unexpected')):
            self.assertEqual(experiment.run_record(row)['runs'], [])

    def test_shared_populations_do_not_duplicate_total_runs(self):
        row = self.tiny_row()
        row['original']['populations'] = ['regression-all-candidate', 'fresh-declared']
        compact = experiment.compact_row(experiment.run_record(row))
        summary = experiment.summarize([compact], self.manifest(row))
        self.assertEqual(summary['comparison_counts'], {'both_success': 1})
        for population in ('all-records', 'regression-all-candidate', 'fresh-declared'):
            for policy in experiment.POLICIES:
                self.assertEqual(summary['groups'][population + '/' + policy]['runs'], 1)

    def test_rule_declaration_does_not_run_the_learner(self):
        """Preparation binds an input census before any rule outcome exists."""
        with patch.object(experiment, 'rule_inventory', return_value=[]), \
                patch.object(experiment, 'check_saved_gaps', return_value={'passed': True, 'complete': True}), \
                        patch.object(experiment, 'check_rule_soundness', side_effect=AssertionError('premature rule run')), \
                patch.object(experiment, 'solve_triangle_saturation', side_effect=AssertionError('premature producer')):
            declaration = experiment.rule_declaration()
        self.assertEqual(declaration['inventory_sha256'], experiment.digest([]))
        self.assertFalse(declaration['production_oracle_or_propagation_performed'])

    def test_baseline_identity_does_not_normalize_any_field(self):
        """A silently restored 512 limit must fail this experiment's identity check."""
        row = self.tiny_row()
        baseline = experiment.solve_conditional_diamond(row['original']['document'], probe_limit=8192)
        prior = deepcopy(row)
        with TemporaryDirectory(dir=experiment.ROOT / 'outputs') as directory:
            base = Path(directory)
            archive, checkpoint = base / 'old-manifest.json', base / 'old-case.json'
            experiment.write_report(archive, {'fixture': True})
            experiment.write_report(checkpoint, {
                'manifest_sha256': experiment.checksum(archive),
                'record_sha256': experiment.digest(prior),
                'row': {'runs': [{'scenario': 'single-anchor-input-order',
                                  'policy': 'conditional-diamond', 'result': baseline}]}})
            row['original']['prior_record'] = prior
            row['original']['archive_reference'] = {
                'path': checkpoint.relative_to(experiment.ROOT).as_posix(),
                'sha256': experiment.checksum(checkpoint)}
            with patch.object(experiment, 'ARCHIVE', archive.relative_to(experiment.ROOT).as_posix()):
                result = experiment.archived_baseline(row, 'single-anchor-input-order', baseline)
                self.assertTrue(result['matches_exactly'])
                changed = deepcopy(baseline)
                changed['run']['probe_limit'] = 512
                with self.assertRaises(AssertionError):
                    experiment.archived_baseline(row, 'single-anchor-input-order', changed)

    def test_geometry_exclusions_are_separate_from_producer_failures(self):
        """A complete declared history can contain explicitly ineligible prefixes."""
        ready = self.tiny_row()
        ready['scenarios'][0]['id'] = 'one-bounded-anchor'
        compact = experiment.compact_row(experiment.run_record(ready))
        legacy = deepcopy(compact['runs'])
        for entry in legacy:
            entry['scenario'] = 'legacy-frame-anchors'
        compact['runs'].extend(legacy)
        bad = {'key': 'excluded', 'eligibility': 'geometry_audit_error', 'scenarios': [],
               'original': {'populations': ['fresh-declared']}}
        history = {'id': 'tiny-history', 'prefix_keys': [ready['key'], bad['key']]}
        manifest = self.manifest(ready)
        manifest['records'].append(bad)
        manifest['inventory']['holdout']['histories'] = [history]
        summary = experiment.summarize([compact, {'key': bad['key'], 'eligibility': bad['eligibility'],
                                                  'runs': []}], manifest)
        self.assertEqual(len(summary['histories']), 4)
        for item in summary['histories']:
            self.assertEqual(item['excluded_prefix_count'], 1)
            self.assertEqual(item['producer_uncompleted_prefix_count'], 0)
            self.assertEqual(item['failed_prefix_count'], 0)
            self.assertFalse(item['all_declared_prefixes_successful'])

    def test_learning_and_candidate_changes_are_separate_metrics(self):
        """Compact evidence must retain inference counts independently of choices."""
        row = self.tiny_row()
        compact = experiment.compact_row(experiment.run_record(row))
        summary = experiment.summarize([compact], self.manifest(row))
        pair = summary['paired'][0]
        self.assertIn('initial_removed_candidates', pair)
        self.assertIn('initial_added_candidates', pair)
        self.assertEqual(pair['initial_candidate_reduction'], len(pair['initial_removed_candidates']))
        self.assertIn('logical_neq_query_count', summary['groups']['all-records/triangle-saturation'])
        self.assertEqual(summary['paired_changes']['all-records']['audited_pairs'], 1)

    def test_saved_checker_rejects_rehashed_omission_and_false_totals(self):
        row = self.tiny_row()
        saved = experiment.run_record(row)
        manifest = self.manifest(row)
        for mutation in ('none', 'coverage', 'summary', 'rule-binding'):
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
                rule_path = base / 'rule.json'
                experiment.write_report(rule_path, {'manifest_sha256': manifest_hash,
                    'rule_declaration_sha256': ('wrong' if mutation == 'rule-binding'
                                               else experiment.digest(manifest['rule_declaration'])),
                    'result': {'input_inventory_sha256': manifest['rule_declaration']['inventory_sha256']}})
                gap_path = base / 'gaps.json'
                experiment.write_report(gap_path, {'manifest_sha256': manifest_hash, 'result': {'fixture': True}})
                summary = experiment.summarize([experiment.compact_row(saved)], manifest)
                if mutation == 'summary':
                    summary['comparison_counts']['both_success'] = 999
                experiment.write_report(report_path, {'schema_version': 1, 'version': experiment.VERSION,
                    'rule_evidence': {'path': rule_path.relative_to(experiment.ROOT).as_posix(),
                                      'sha256': experiment.checksum(rule_path)},
                    'rule_evidence_check': {'passed': True},
                    'gap_evidence': {'path': gap_path.relative_to(experiment.ROOT).as_posix(), 'sha256': experiment.checksum(gap_path)},
                    'gap_evidence_check': {'passed': True, 'complete': True},
                    'manifest_sha256': manifest_hash, 'checkpoints': [{
                        'path': checkpoint.relative_to(experiment.ROOT).as_posix(),
                        'sha256': experiment.checksum(checkpoint)}], 'summary': summary})
                with patch.object(experiment, 'bound_manifest', return_value=manifest), \
                        patch.object(experiment, 'sources', return_value=manifest['source_sha256']), \
                        patch.object(experiment, 'check_saved_rule_soundness', return_value={'passed': True}), \
                        patch.object(experiment, 'check_saved_gaps', return_value={'passed': True, 'complete': True}), \
                        patch.object(experiment, 'check_rule_soundness', side_effect=AssertionError('rule learner rerun')), \
                        patch('scripts.audit_quaternary_conditional_diamond.solve_exact', side_effect=AssertionError('search rerun')), \
                        patch('scripts.audit_quaternary_triangle_saturation.solve_exact', side_effect=AssertionError('search rerun')):
                    if mutation == 'none':
                        counts = experiment.check(manifest_path, report_path, base / 'check.json')
                        self.assertEqual(counts['audited_runs'], 2)
                    else:
                        with self.assertRaises(AssertionError):
                            experiment.check(manifest_path, report_path, base / 'check.json')


if __name__ == '__main__':
    unittest.main()

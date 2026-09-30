"""Test offline scan inventory binding, coverage and summaries on tiny fixtures."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import validate_quaternary_logical_neq_candidate_scan as experiment
from scripts.quaternary_logical_neq_low_color import solve_logical_neq


class LogicalNeqCandidateScanExperimentTests(unittest.TestCase):
    """No archived candidate oracle queries are used during these unit tests."""

    def fixture(self):
        """A tiny triangle has actual persistent choices and no residual gap."""
        raw = {'sides': ['A', 'B', 'C'], 'anchors': {'A': 1}, 'lines': [
            {'id': str(i), 'kind': 'separator', 'left': a, 'right': b}
            for i, (a, b) in enumerate([('A', 'B'), ('B', 'C'), ('A', 'C')])]}
        envelope = solve_logical_neq(raw)
        targets = experiment.candidate_inventory(raw, envelope['run'])
        scenario = {'id': 'synthetic-single', 'raw_document_sha256': experiment.digest(raw),
                    'envelope_sha256': experiment.digest(envelope), 'audit_sha256': experiment.digest({}),
                    'inventory': targets, 'inventory_sha256': experiment.digest(targets)}
        record = {'key': 'tiny', 'kind': 'abstract', 'eligibility': 'ready',
                  'archive_populations': ['fixture'], 'scenarios': [scenario]}
        entry = {'scenario': scenario['id'], 'policy': 'logical-neq', 'raw_document': raw,
                 'result': envelope, 'audit': {}}
        return record, entry

    def test_prepare_freezes_targets_without_new_queries(self):
        record, _ = self.fixture()
        with TemporaryDirectory(dir=experiment.ROOT / 'outputs') as directory, \
                patch.object(experiment, 'sources', return_value={'fixture': 'source'}), \
                patch.object(experiment, 'EXPECTED_COUNTS', experiment.inventory_counts([record])), \
                patch.object(experiment, 'archive_records', return_value=[record]) as archived, \
                patch.object(experiment, 'checksum', return_value='archive'), \
                patch.object(experiment, 'scan_candidates', side_effect=AssertionError('query before freeze')):
            path = Path(directory) / 'manifest.json'
            counts = experiment.prepare(path)
            saved = experiment.read_report(path)
        archived.assert_called_once_with(verify_saved=True)
        self.assertEqual(counts['runs'], 1)
        self.assertEqual(saved['new_oracle_queries_before_freeze'], 0)
        self.assertEqual(saved['records'][0]['scenarios'][0]['inventory'], record['scenarios'][0]['inventory'])

    def test_binding_rejects_different_old_envelope(self):
        record, entry = self.fixture()
        record['archive_reference'] = {'path': 'synthetic', 'sha256': 'synthetic'}
        altered = deepcopy(entry)
        altered['result']['oracle_feedback_to_producer'] = True
        with patch.object(experiment, 'bound_reference', return_value={'row': {'runs': [altered]}}):
            with self.assertRaises(AssertionError):
                experiment.load_entry(record, record['scenarios'][0])

    def test_error_and_exclusion_are_retained(self):
        record, entry = self.fixture()
        with patch.object(experiment, 'load_entry', return_value=entry), \
                patch.object(experiment, 'scan_candidates', side_effect=RuntimeError('fixture budget failure')):
            saved = experiment.run_record(record)
        self.assertEqual(saved['runs'][0]['execution'], 'error')
        self.assertIn('fixture budget failure', saved['runs'][0]['error'])
        excluded = {'key': 'excluded', 'kind': 'geometry', 'eligibility': 'geometry_error', 'scenarios': []}
        with patch.object(experiment, 'load_entry', side_effect=AssertionError('excluded queried')):
            empty = experiment.run_record(excluded)
        summary = experiment.summarize([saved, empty], {'records': [record, excluded]})
        self.assertEqual(summary['groups']['all']['errors'], 1)
        self.assertEqual(summary['eligibility'], {'ready': 1, 'geometry_error': 1})

    def test_saved_checker_binds_coverage_and_reconstructs_summary(self):
        record, entry = self.fixture()
        with patch.object(experiment, 'load_entry', return_value=entry):
            saved = experiment.run_record(record)
        self.assertEqual(saved['runs'][0]['execution'], 'checked')
        manifest = {'records': [record], 'source_sha256': {'fixture': 'fixed'}}
        for mutation in ('none', 'omit', 'summary'):
            with self.subTest(mutation=mutation), TemporaryDirectory(dir=experiment.ROOT / 'outputs') as directory:
                base = Path(directory)
                manifest_path, report_path = base / 'manifest.json', base / 'report.json'
                experiment.write_report(manifest_path, manifest)
                frozen_hash = experiment.checksum(manifest_path)
                altered = deepcopy(saved)
                if mutation == 'omit':
                    altered['runs'].clear()
                checkpoint = base / 'checkpoint.json'
                experiment.write_report(checkpoint, {'manifest_sha256': frozen_hash,
                    'record_sha256': experiment.digest(record), 'row': altered})
                summary = experiment.summarize([saved], manifest)
                if mutation == 'summary':
                    summary['groups']['all']['checked'] = 99
                experiment.write_report(report_path, {'schema_version': 1, 'version': experiment.VERSION,
                    'manifest_sha256': frozen_hash, 'checkpoints': [{
                        'path': checkpoint.relative_to(experiment.ROOT).as_posix(),
                        'sha256': experiment.checksum(checkpoint)}], 'summary': summary})
                with patch.object(experiment, 'bound_manifest', return_value=manifest), \
                        patch.object(experiment, 'sources', return_value=manifest['source_sha256']), \
                        patch.object(experiment, 'load_entry', return_value=entry), \
                        patch.object(experiment, 'scan_candidates', side_effect=AssertionError('scan rerun')):
                    if mutation == 'none':
                        counts = experiment.check(manifest_path, report_path, base / 'checked.json')
                        self.assertEqual(counts['checked'], 1)
                    else:
                        with self.assertRaises(AssertionError):
                            experiment.check(manifest_path, report_path, base / 'checked.json')

    def test_compaction_preserves_residual_gaps_and_population_denominators(self):
        """Discarding large certificates must not discard a negative result."""
        record, entry = self.fixture()
        record['archive_populations'] = ['fresh-declared', 'fresh-new-key']
        with patch.object(experiment, 'load_entry', return_value=entry):
            saved = experiment.run_record(record)
        # Supply a synthetic negative only to the summarizer, not the verifier.
        target = saved['runs'][0]['scan']['states'][0]['targets'][0]
        target['status'] = 'unsupported'
        complete = experiment.summarize([saved], {'records': [record]})
        reduced = experiment.compact_row(saved)
        self.assertEqual(experiment.summarize([reduced], {'records': [record]}), complete)
        self.assertEqual(len(complete['first_unsupported_per_run']), 1)
        self.assertEqual(complete['groups']['population/fresh-new-key']['runs'], 1)
        self.assertNotIn('oracle_records', reduced['runs'][0]['scan'])

    def test_source_census_counts_cannot_drift_before_freeze(self):
        """The separately counted obligations must agree before any search."""
        record, _ = self.fixture()
        with TemporaryDirectory(dir=experiment.ROOT / 'outputs') as directory, \
                patch.object(experiment, 'sources', return_value={'fixture': 'source'}), \
                patch.object(experiment, 'EXPECTED_COUNTS', {'runs': 999}), \
                patch.object(experiment, 'archive_records', return_value=[record]), \
                patch.object(experiment, 'checksum', return_value='archive'):
            path = Path(directory) / 'manifest.json'
            with self.assertRaises(AssertionError):
                experiment.prepare(path)
            self.assertFalse(path.exists())

    def test_resume_rejects_corrupted_scenario_coverage_before_new_queries(self):
        """A bound checkpoint shell cannot hide a missing saved scenario."""
        record, _ = self.fixture()
        manifest = {'records': [record], 'source_sha256': {'fixture': 'fixed'}}
        with TemporaryDirectory(dir=experiment.ROOT / 'outputs') as directory:
            base = Path(directory)
            manifest_path, output = base / 'manifest.json', base / 'result.json.gz'
            experiment.write_report(manifest_path, manifest)
            checkpoints = base / 'result-checkpoints'
            checkpoints.mkdir()
            experiment.write_report(checkpoints / '000-tiny.json.gz', {
                'manifest_sha256': experiment.checksum(manifest_path),
                'record_sha256': experiment.digest(record),
                'row': {'key': 'tiny', 'eligibility': 'ready', 'runs': []}})
            with patch.object(experiment, 'bound_manifest', return_value=manifest), \
                    patch.object(experiment, 'run_record', side_effect=AssertionError('new query')):
                with self.assertRaisesRegex(AssertionError, 'scenario coverage'):
                    experiment.execute(manifest_path, output)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()

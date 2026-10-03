"""Small synthetic checks for archive binding and interruption-safe scans."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import validate_quaternary_triangle_saturation_support as runner
from scripts.quaternary_triangle_saturation_low_color import solve_saturation_contacts
from scripts.quaternary_triangle_saturation_support_scan import scan_support, support_inventory
from tests.test_quaternary_logical_neq_pair_scan import triangular_bipyramid


class SupportRunnerTests(unittest.TestCase):
    """No formal corpus query is issued by these fixture-only tests."""

    @classmethod
    def setUpClass(cls):
        """Use one tiny abstract scene with genuine joint-only obstructions."""
        cls.raw = triangular_bipyramid()
        cls.fixture_run = solve_saturation_contacts(cls.raw, decision_limit=0)
        cls.scan = scan_support(cls.raw, cls.fixture_run)
        cls.entry = {'scenario': 'fixture', 'execution': 'audited', 'policy': runner.POLICY,
                     'raw_document': cls.raw, 'result': {'run': cls.fixture_run},
                     'audit': {'oracle_records': []}}
        inv = support_inventory(cls.raw, cls.fixture_run)
        cls.record = {'key': 'fixture', 'kind': 'abstract', 'eligibility': 'ready',
            'populations': ['fixture'], 'old_scans': {}, 'conditional_reference': None,
            'production_reference': {'path': 'outputs/fixture.json', 'sha256': 'bytes'},
            'production_record_sha256': 'record', 'scenarios': [{
                'id': 'fixture', 'raw_document_sha256': runner.digest(cls.raw),
                'envelope_sha256': runner.digest(cls.entry['result']),
                'audit_sha256': runner.digest(cls.entry['audit']),
                'inventory_sha256': runner.digest(inv), 'inventory_counts': runner.target_counts(inv)}]}
        cls.manifest = {'records': [cls.record], 'histories': [],
                        'archive_manifest_hashes': {'production': 'freeze'},
                        'conditional_parts': {'upstream': {'path': 'outputs/old.json', 'sha256': 'old'}}}

    def context(self):
        """Only the test loader is substituted; scanner and checker stay real."""
        return patch.object(runner, 'load_context', return_value=([self.entry], {}, None))

    def test_full_synthetic_scan_and_saved_replay_without_search(self):
        """A saved-only check must not invoke fresh search or propagation."""
        with self.context():
            row = runner.run_record(self.manifest, self.record)
        self.assertEqual(row['runs'][0]['execution'], 'checked')
        with self.context(), patch.object(runner, 'scan_support', side_effect=AssertionError), \
             patch('scripts.quaternary_triangle_saturation_support_scan.solve_exact', side_effect=AssertionError), \
             patch('scripts.quaternary_triangle_saturation_support_scan.propagate_saturation_contacts', side_effect=AssertionError):
            runner.verify_row(self.manifest, self.record, row)
        summary = runner.summarize([runner.compact_row(row)], self.manifest)
        self.assertEqual(len(summary['unsupported_targets']), 12)
        self.assertEqual(summary['groups']['new-scanned']['checked'], 1)

    def test_errors_are_saved_as_incomplete_not_passes(self):
        """An exception remains explicit even if a drawing checkpoint exists."""
        with self.context(), patch.object(runner, 'scan_support', side_effect=RuntimeError('fixture failure')):
            row = runner.run_record(self.manifest, self.record)
        with self.context():
            runner.verify_row(self.manifest, self.record, row)
        summary = runner.summarize([runner.compact_row(row)], self.manifest)
        self.assertEqual(summary['groups']['all']['errors'], 1)
        self.assertEqual(summary['groups']['all']['checked'], 0)

    def test_replay_rejects_missing_scenario_before_loading(self):
        """Deleting an obligation cannot manufacture an all-pass subset."""
        with patch.object(runner, 'load_context', side_effect=AssertionError('should not load')) as load:
            with self.assertRaisesRegex(AssertionError, 'scenario coverage'):
                runner.verify_row(self.manifest, self.record, {'key': 'fixture', 'eligibility': 'ready', 'runs': []})
            load.assert_not_called()

    def test_current_context_is_loaded_once_and_all_hashes_bound(self):
        """Each drawing reads its compressed source once, across all scenes."""
        saved = {'manifest_sha256': 'freeze', 'record_sha256': 'record',
                 'row': {'key': 'fixture', 'eligibility': 'ready', 'runs': [self.entry]}}
        with patch.object(runner, 'bound_reference', return_value=saved) as load:
            entries, old, conditionals = runner.load_context(self.manifest, self.record)
        self.assertEqual(len(entries), 1)
        self.assertEqual(load.call_count, 1)
        bad = deepcopy(self.record)
        bad['scenarios'][0]['inventory_sha256'] = 'altered'
        with patch.object(runner, 'bound_reference', return_value=saved), self.assertRaises(AssertionError):
            runner.load_context(self.manifest, bad)

    def test_pool_priority_and_saved_origin(self):
        """Raw source locators remain separate from records and query premises."""
        entry = deepcopy(self.entry)
        entry['audit']['oracle_records'] = [self.scan['oracle_records'][0]]
        record = deepcopy(self.record)
        record['old_scans'] = {kind: {'reference': {'path': 'outputs/' + kind, 'sha256': kind}}
                               for kind in ('unary', 'pair')}
        old = {kind: {'fixture': {'oracle_records': [self.scan['oracle_records'][1]]}}
               for kind in ('unary', 'pair')}
        sources, conditions = runner.pools(record, entry, old, None)
        self.assertEqual([s['source']['kind'] for s in sources],
                         ['production-audit', 'unary-scan', 'pair-scan'])
        self.assertEqual(conditions, [])

    def test_atomic_publish_never_overwrites(self):
        """The final filename appears only after the complete payload is closed."""
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'fixture.json.gz'
            runner.write_atomic(path, {'first': True})
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                runner.write_atomic(path, {'second': True})
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(runner.read_report(path), {'first': True})

    def test_interrupted_pending_does_not_block_new_complete_checkpoint(self):
        """Unknown leftover temporary bytes are preserved and never resumed."""
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'fixture.json.gz'
            pending = Path(folder) / '.pending-interrupted-fixture.json.gz'
            pending.write_bytes(b'incomplete')
            runner.write_atomic(path, {'complete': True})
            self.assertEqual(pending.read_bytes(), b'incomplete')
            self.assertEqual(runner.read_report(path), {'complete': True})

    def test_resume_replays_good_checkpoint_without_new_run(self):
        """A complete checkpoint is verified again, not trusted by existence."""
        with TemporaryDirectory(dir=runner.ROOT / 'outputs') as folder, self.context():
            runner.init_worker(self.manifest, 'manifest', folder)
            first = runner.work_record(0)
            with patch.object(runner, 'run_record', side_effect=AssertionError('new run')):
                resumed = runner.work_record(0)
            self.assertFalse(first[-1])
            self.assertTrue(resumed[-1])
            self.assertEqual(first[1:3], resumed[1:3])

    def test_resume_rejects_changed_manifest(self):
        """A same-name checkpoint from another experiment is never reused."""
        with TemporaryDirectory(dir=runner.ROOT / 'outputs') as folder, self.context():
            runner.init_worker(self.manifest, 'first', folder)
            runner.work_record(0)
            runner.init_worker(self.manifest, 'other', folder)
            with self.assertRaisesRegex(AssertionError, 'resume manifest'):
                runner.work_record(0)

    def test_exclusions_survive_inventory_counts(self):
        """Ineligible geometry is kept in denominators without invented runs."""
        excluded = {'key': 'excluded', 'eligibility': 'geometry_error', 'scenarios': [], 'old_scans': {}}
        counts = runner.inventory_counts([self.record, excluded])
        self.assertEqual(counts['records'], 2)
        self.assertEqual(counts['runs'], 1)
        self.assertEqual(counts['eligibility']['geometry_error'], 1)

    def test_conditional_parts_bind_parent_rows_exactly(self):
        """All original positions must occur once; same-sized substitutions fail."""
        rows = [{'key': 'fixture', 'execution': 'checked', 'number': i} for i in range(1814)]
        original = {'manifest_sha256': 'freeze', 'result': {'rows': rows}}
        part = {'upstream': 'parent', 'key': 'fixture',
                'entries': [{'row_index': i, 'row': r} for i, r in enumerate(rows)]}
        manifest = {'archive_manifest_hashes': {'production': 'freeze'},
                    'conditional_parts': {'row_count': 1814, 'upstream': 'parent', 'parts': {'fixture': 'part'}}}
        with patch.object(runner, 'bound_reference', side_effect=lambda ref: original if ref == 'parent' else part):
            runner.verify_conditional_parts(manifest)
            bad = deepcopy(part)
            bad['entries'][10]['row'] = rows[11]
            with patch.object(runner, 'bound_reference', side_effect=lambda ref: original if ref == 'parent' else bad), \
                 self.assertRaisesRegex(AssertionError, 'extracted conditional row'):
                runner.verify_conditional_parts(manifest)

    def test_prequery_census_binds_each_scene_not_just_totals(self):
        """Hash binding catches swapped source scenes even if counts agree."""
        scene = self.record['scenarios'][0]
        other = {'key': 'fixture', 'scenario': 'fixture', 'checkpoint': self.record['production_reference'],
                 'counts': scene['inventory_counts'],
                 **{k: scene[k] for k in ('raw_document_sha256', 'envelope_sha256', 'audit_sha256')}}
        census = {'runs': [other], 'bindings': {}}
        runner.bind_census([self.record], census)
        census['runs'][0]['audit_sha256'] = 'different'
        with self.assertRaisesRegex(AssertionError, 'independent scene audit'):
            runner.bind_census([self.record], census)

    def test_sparse_prequery_zero_counts_are_explicitly_zero(self):
        """A missing Counter entry means zero, but cannot hide a positive target."""
        record = deepcopy(self.record)
        scene = record['scenarios'][0]
        scene['inventory_counts'] = {'single_targets': 0, 'pair_targets': 0}
        other = {'key': 'fixture', 'scenario': 'fixture', 'checkpoint': record['production_reference'],
                 'counts': {}, **{k: scene[k] for k in
                 ('raw_document_sha256', 'envelope_sha256', 'audit_sha256')}}
        census = {'runs': [other], 'bindings': {}}
        runner.bind_census([record], census)
        scene['inventory_counts']['pair_targets'] = 1
        with self.assertRaisesRegex(AssertionError, 'pair_targets'):
            runner.bind_census([record], census)


if __name__ == '__main__':
    unittest.main()

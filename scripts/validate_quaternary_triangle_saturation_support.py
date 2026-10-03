"""Freeze, resume and verify offline unary/binary support with exact-proof reuse.

The already checked coloring producer is never rerun. Archive byte bindings
preserve its previously audited provenance; this experiment reconstructs new
state obligations and independently verifies every used raw exact certificate.
Each drawing is a bounded, exclusively written checkpoint and worker task.
"""

from argparse import ArgumentParser
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
import json
import os
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.check_quaternary_reachability import checksum
from scripts.check_quaternary_reachability_artifacts import same
from scripts.validate_global_restart import digest, write_report
from scripts.validate_quaternary_contacts_v2 import read_report, require
from scripts.validate_quaternary_triangle_saturation import sources as previous_sources
from scripts.quaternary_triangle_saturation_support_scan import support_inventory, scan_support
from scripts.check_quaternary_triangle_saturation_support_scan import check_support_scan

VERSION = 'quaternary-triangle-saturation-support-experiment-v1'
POLICY = 'triangle-saturation'
PREFIX = 'outputs/quaternary-triangle-saturation-'
ARCHIVES = {
    'production': (PREFIX + 'manifest-2026-10-01.json.gz', PREFIX + '2026-10-01.json.gz',
                   PREFIX + 'artifact-check-2026-10-01.json'),
    'unary': ('outputs/quaternary-logical-neq-candidate-scan-manifest-2026-09-29.json.gz',
              'outputs/quaternary-logical-neq-candidate-scan-2026-09-29.json.gz',
              'outputs/quaternary-logical-neq-candidate-scan-check-2026-09-29.json'),
    'pair': ('outputs/quaternary-logical-neq-pair-scan-manifest-2026-09-29.json.gz',
             'outputs/quaternary-logical-neq-pair-scan-2026-09-29.json.gz',
             'outputs/quaternary-logical-neq-pair-scan-check-2026-09-29.json'),
}
CENSUS = 'outputs/quaternary-triangle-saturation-support-prequery-inventory-2026-10-03.json'
PROTOCOL = 'docs/QUATERNARY_TRIANGLE_SATURATION_SUPPORT_PROTOCOL-2026-10-03.md'
INPUT_PATHS = tuple(p for names in ARCHIVES.values() for p in names) + (CENSUS,)
NEW_SOURCES = ('scripts/quaternary_triangle_saturation_support_scan.py',
               'tests/test_quaternary_triangle_saturation_support_scan.py',
               'scripts/check_quaternary_triangle_saturation_support_scan.py',
               'tests/test_check_quaternary_triangle_saturation_support_scan.py',
               'scripts/validate_quaternary_triangle_saturation_support.py',
               'tests/test_validate_quaternary_triangle_saturation_support.py', PROTOCOL)
RESOURCES = {'node_limit': 200000, 'workers': 2}
WORKER = None


def write_atomic(path, payload):
    """Publish complete bytes without overwriting; preserve interrupted parts.

    A hard link within the same directory publishes only a closed file and
    fails if the final name already exists. Only our own completed temporary
    link is removed; stale interrupted parts are ignored, never overwritten.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.parent / ('.pending-' + uuid4().hex + '-' + path.name)
    write_report(pending, payload)
    os.link(pending, path)
    pending.unlink()


def sources():
    """Retain all 272 prior source bytes and freeze only additive scan files."""
    previous = previous_sources()
    same(previous, read_report(ROOT / ARCHIVES['production'][0])['source_sha256'],
         'previous frozen source chain changed')
    return {**previous, **{name: checksum(ROOT / name) for name in NEW_SOURCES}}


def reference(path):
    """Describe only a real repository-local output, using portable paths."""
    path = path.resolve()
    require(path.is_relative_to(ROOT / 'outputs'), 'reference outside outputs')
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': checksum(path)}


def bound_reference(ref):
    """Fail closed on changed artifacts before parsing their contents."""
    path = (ROOT / ref['path']).resolve()
    require(path.is_relative_to(ROOT / 'outputs'), 'artifact outside outputs')
    same(checksum(path), ref['sha256'], 'artifact bytes changed')
    return read_report(path)


def archive_bundles():
    """Bind successful prior audits without rerunning their coloring workflows."""
    bundles = {}
    for kind, (mp, rp, cp) in ARCHIVES.items():
        manifest, report, checked = [read_report(ROOT / p) for p in (mp, rp, cp)]
        for data in (report, checked):
            same(data['manifest_sha256'], checksum(ROOT / mp), kind + ' manifest binding')
        same(checked['report_sha256'], checksum(ROOT / rp), kind + ' report binding')
        same(checked['source_sha256'], manifest['source_sha256'], kind + ' source binding')
        require(all(checked.get(k) is True for k in
                    ('passed', 'eligible_executions_complete', 'exact_queries_conclusive')),
                kind + ' prior evidence incomplete')
        require(len(manifest['records']) == len(report['checkpoints']), kind + ' coverage differs')
        by_key = {}
        for old, ref in zip(manifest['records'], report['checkpoints']):
            require(old['key'] not in by_key, 'duplicate archive key')
            by_key[old['key']] = (old, ref)
        bundles[kind] = {'manifest': manifest, 'report': report, 'by_key': by_key,
                         'manifest_sha256': checksum(ROOT / mp)}
    return bundles


def target_counts(inventory):
    """Keep literal obligation counts distinct from states and graph records."""
    states = inventory['states']
    return {'persistent_states': len(states),
            'single_targets': sum(len(s['single_targets']) for s in states),
            'pair_targets': sum(len(s['pair_targets']) for s in states),
            'eligible_side_pairs': sum(s['eligible_side_pair_count'] for s in states),
            'cartesian_color_pairs': sum(s['cartesian_target_count'] for s in states),
            'states_without_singles': sum(not s['single_targets'] for s in states),
            'states_without_pairs': sum(not s['pair_targets'] for s in states)}


def selected_entries(saved, record, *, production=True):
    """Require complete ordered scenario coverage, not just one matching row."""
    row = saved['row']
    same([row['key'], row['eligibility']], [record['key'], record['eligibility']], 'row identity')
    entries = [e for e in row['runs'] if not production or e['policy'] == POLICY]
    same([e['scenario'] for e in entries], [s['id'] for s in record['scenarios']], 'scenario coverage')
    return entries


def extract_conditionals(bundles, directory):
    """Split old certified diagnostics once; no new propagation or exact search.

    Full row indices and the original compressed checksum retain the parent
    provenance. A worker loads only its drawing's part. Preparation retries may
    reuse an identical completed part but can never overwrite a different one.
    """
    upstream = bundles['production']['report']['gap_evidence']
    saved = bound_reference(upstream)
    same(saved['manifest_sha256'], bundles['production']['manifest_sha256'], 'gap freeze')
    rows = saved['result']['rows']
    require(len(rows) == 1814 and all(r['execution'] == 'checked' for r in rows), 'gap census incomplete')
    grouped = {}
    for i, row in enumerate(rows):
        grouped.setdefault(row['key'], []).append({'row_index': i, 'row': row})
    parts = {}
    for key, selected in grouped.items():
        payload = {'upstream': upstream, 'key': key, 'entries': selected}
        path = directory / (key + '.json.gz')
        if path.exists():
            same(read_report(path), payload, 'existing conditional part differs')
        else:
            write_atomic(path, payload)
        parts[key] = reference(path)
    return {'upstream': upstream, 'row_count': len(rows), 'parts': parts}


def build_records(bundles, conditionals):
    """Rebuild every new target list from the current saved producer once."""
    rows = []
    for number, (key, (old, ref)) in enumerate(bundles['production']['by_key'].items()):
        saved = bound_reference(ref)
        same(saved['manifest_sha256'], bundles['production']['manifest_sha256'], 'production freeze')
        same(saved['record_sha256'], digest(old), 'production record binding')
        row = {'key': key, 'kind': old['original']['kind'], 'eligibility': old['eligibility'],
               'populations': old['original']['populations'], 'scenarios': old['scenarios'],
               'production_reference': ref, 'production_record_sha256': digest(old),
               'conditional_reference': conditionals['parts'].get(key), 'old_scans': {}}
        for kind in ('unary', 'pair'):
            if key in bundles[kind]['by_key']:
                previous, previous_ref = bundles[kind]['by_key'][key]
                row['old_scans'][kind] = {'reference': previous_ref,
                    'record_sha256': digest(previous), 'scenario_ids': [s['id'] for s in previous['scenarios']]}
        entries = selected_entries(saved, row)
        row['scenarios'] = []
        for entry in entries:
            require(entry['execution'] == 'audited', 'production execution incomplete')
            inventory = support_inventory(entry['raw_document'], entry['result']['run'])
            row['scenarios'].append({'id': entry['scenario'],
                'raw_document_sha256': digest(entry['raw_document']),
                'envelope_sha256': digest(entry['result']), 'audit_sha256': digest(entry['audit']),
                'inventory_sha256': digest(inventory), 'inventory_counts': target_counts(inventory)})
        rows.append(row)
        if (number + 1) % 50 == 0:
            print(json.dumps({'stage': 'freeze_inventory', 'records': number + 1}), flush=True)
    return rows


def inventory_counts(records):
    """Retain exclusions; successful histories do not erase excluded prefixes."""
    counts = {'records': len(records), 'eligibility': dict(Counter(r['eligibility'] for r in records)),
              'runs': sum(len(r['scenarios']) for r in records)}
    for key in target_counts({'states': []}):
        counts[key] = sum(s['inventory_counts'][key] for r in records for s in r['scenarios'])
    counts['old_scan_runs'] = sum(len(r['scenarios']) for r in records if 'pair' in r['old_scans'])
    counts['new_scan_runs'] = counts['runs'] - counts['old_scan_runs']
    return counts


def bind_census(records, census):
    """Bind independent per-scene enumeration, not only the grand totals."""
    lookup = {(r['key'], r['scenario']): r for r in census['runs']}
    require(len(lookup) == len(census['runs']), 'duplicate independent census scene')
    expected = {(r['key'], s['id']) for r in records for s in r['scenarios']}
    same(sorted(lookup), sorted(expected), 'independent scene coverage')
    for record in records:
        for scenario in record['scenarios']:
            other = lookup[record['key'], scenario['id']]
            for field in ('raw_document_sha256', 'envelope_sha256', 'audit_sha256'):
                same(scenario[field], other[field], 'independent scene ' + field)
            same(record['production_reference'], other['checkpoint'], 'independent checkpoint')
            for key, value in scenario['inventory_counts'].items():
                # The independent Counter omits zero-valued scene categories.
                same(value, other['counts'].get(key, 0), 'independent scene count ' + key)
    for ref in census['bindings'].values():
        same(checksum(ROOT / ref['path']), ref['sha256'], 'independent input bytes')


def prepare(path):
    """Freeze code, declared obligations and source shards before new queries."""
    require(not path.exists(), 'manifest exists; choose a new filename')
    before = sources()
    inputs = {name: checksum(ROOT / name) for name in INPUT_PATHS}
    bundles = archive_bundles()
    directory = path.parent / (path.name.removesuffix('.json.gz') + '-inputs')
    conditionals = extract_conditionals(bundles, directory)
    records = build_records(bundles, conditionals)
    counts = inventory_counts(records)
    census = read_report(ROOT / CENSUS)
    # The independently enumerated reference uses these same denominator names.
    same(counts, census['counts'], 'independent pre-query census differs')
    bind_census(records, census)
    same(before, sources(), 'source drift during preparation')
    same(inputs, {name: checksum(ROOT / name) for name in INPUT_PATHS}, 'input drift')
    previous = bundles['production']['manifest']
    manifest = {'schema_version': 1, 'version': VERSION, 'source_sha256': before,
        'input_sha256': inputs, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'archive_manifest_hashes': {k: v['manifest_sha256'] for k, v in bundles.items()},
        'records': records, 'counts': counts, 'resources': RESOURCES,
        'conditional_parts': conditionals,
        'histories': [('fresh-declared', h) for h in previous['inventory']['holdout']['histories']]
                   + [('regression-conditional-diamond', h) for h in previous['inventory']['regression_histories']],
        'producer_reruns': 0, 'new_oracle_queries_before_freeze': 0,
        'producer_trace_scope': 'Reuse hash-bound previously checked production; reconstruct event chain and current obligations.'}
    write_atomic(path, manifest)
    return counts


def bound_manifest(path):
    """Bind frozen sources and prior successful checks without batch recomputation."""
    manifest = read_report(path)
    same([manifest['schema_version'], manifest['version']], [1, VERSION], 'manifest schema')
    same(manifest['source_sha256'], sources(), 'source drift after freeze')
    same(manifest['input_sha256'], {name: checksum(ROOT / name) for name in INPUT_PATHS}, 'input drift')
    same(manifest['resources'], RESOURCES, 'resource drift')
    same(manifest['counts'], inventory_counts(manifest['records']), 'manifest counts')
    same(manifest['counts'], read_report(ROOT / CENSUS)['counts'], 'independent census drift')
    bind_census(manifest['records'], read_report(ROOT / CENSUS))
    require(manifest['producer_reruns'] == manifest['new_oracle_queries_before_freeze'] == 0,
            'freeze activity differs')
    bundles = archive_bundles()
    for kind, bundle in bundles.items():
        for name, expected in bundle['manifest']['source_sha256'].items():
            same(manifest['source_sha256'].get(name), expected, kind + ' prior source ancestry')
    same(manifest['conditional_parts']['upstream'], bundles['production']['report']['gap_evidence'],
         'conditional upstream substitution')
    same(manifest['archive_manifest_hashes'], {k: v['manifest_sha256'] for k, v in bundles.items()},
         'archive manifest identity')
    same([r['key'] for r in manifest['records']], list(bundles['production']['by_key']), 'record coverage')
    for record in manifest['records']:
        original, ref = bundles['production']['by_key'][record['key']]
        same(record['production_reference'], ref, 'production reference substitution')
        same(record['production_record_sha256'], digest(original), 'production record substitution')
        same([record['kind'], record['eligibility'], record['populations']],
             [original['original']['kind'], original['eligibility'], original['original']['populations']],
             'record scope differs')
        same([s['id'] for s in record['scenarios']], [s['id'] for s in original['scenarios']], 'scenario census')
        expected_old = {}
        for kind in ('unary', 'pair'):
            if record['key'] in bundles[kind]['by_key']:
                old, old_ref = bundles[kind]['by_key'][record['key']]
                expected_old[kind] = {'reference': old_ref, 'record_sha256': digest(old),
                                     'scenario_ids': [s['id'] for s in old['scenarios']]}
        same(record['old_scans'], expected_old, 'old scan reference substitution')
        same(record['conditional_reference'], manifest['conditional_parts']['parts'].get(record['key']),
             'conditional part substitution')
    previous = bundles['production']['manifest']
    same(manifest['histories'], [['fresh-declared', h] for h in previous['inventory']['holdout']['histories']]
         + [['regression-conditional-diamond', h] for h in previous['inventory']['regression_histories']],
         'history coverage')
    return manifest


def verify_conditional_parts(manifest):
    """Once per command, verify every extracted row against its original bytes."""
    parts = manifest['conditional_parts']
    require(parts['row_count'] == 1814, 'conditional row denominator differs')
    original = bound_reference(parts['upstream'])
    same(original['manifest_sha256'], manifest['archive_manifest_hashes']['production'],
         'conditional original freeze')
    rows = original['result']['rows']
    require(len(rows) == 1814 and all(r['execution'] == 'checked' for r in rows),
            'conditional original census incomplete')
    same(sorted(parts['parts']), sorted({r['key'] for r in rows}), 'conditional drawing coverage')
    seen = set()
    for key, ref in parts['parts'].items():
        saved = bound_reference(ref)
        same(saved['upstream'], parts['upstream'], 'conditional parent substitution')
        same(saved['key'], key, 'conditional drawing identity')
        for entry in saved['entries']:
            i = entry['row_index']
            require(type(i) is int and 0 <= i < len(rows) and i not in seen, 'conditional duplicate/index')
            same(entry['row'], rows[i], 'extracted conditional row differs')
            same(entry['row']['key'], key, 'conditional row belongs to another graph')
            seen.add(i)
    same(sorted(seen), list(range(len(rows))), 'conditional part coverage')


def load_context(manifest, record):
    """Load each compressed producer/scan/conditional file once per drawing."""
    production = bound_reference(record['production_reference'])
    same(production['manifest_sha256'], manifest['archive_manifest_hashes']['production'], 'producer freeze')
    same(production['record_sha256'], record['production_record_sha256'], 'producer record')
    entries = selected_entries(production, record)
    for entry, scenario in zip(entries, record['scenarios']):
        require(entry['execution'] == 'audited', 'producer was not audited')
        for field, expected in [('raw_document', 'raw_document_sha256'), ('result', 'envelope_sha256'),
                                 ('audit', 'audit_sha256')]:
            same(digest(entry[field]), scenario[expected], 'producer ' + field + ' binding')
        current = support_inventory(entry['raw_document'], entry['result']['run'])
        same(digest(current), scenario['inventory_sha256'], 'complete new inventory binding')
        same(target_counts(current), scenario['inventory_counts'], 'new inventory counts')
    old_scans = {}
    for kind, item in record['old_scans'].items():
        saved = bound_reference(item['reference'])
        same(saved['manifest_sha256'], manifest['archive_manifest_hashes'][kind], 'old scan freeze')
        same(saved['record_sha256'], item['record_sha256'], 'old scan record')
        same([saved['row']['key'], saved['row']['eligibility']],
             [record['key'], record['eligibility']], 'old scan identity')
        same([e['scenario'] for e in saved['row']['runs']], item['scenario_ids'], 'old scenario coverage')
        require(all(e['execution'] == 'checked' for e in saved['row']['runs']), 'old scan incomplete')
        old_scans[kind] = {e['scenario']: e['scan'] for e in saved['row']['runs']}
    conditional = bound_reference(record['conditional_reference']) if record['conditional_reference'] else None
    if conditional is not None:
        same(conditional['key'], record['key'], 'conditional context drawing')
        same(conditional['upstream'], manifest['conditional_parts']['upstream'], 'conditional context parent')
    for entry in entries:
        for kind, scans in old_scans.items():
            if entry['scenario'] in scans:
                same(scans[entry['scenario']]['raw_document'], entry['raw_document'],
                     kind + ' raw graph identity')
    return entries, old_scans, conditional


def pools(record, entry, old_scans, conditional):
    """Provide literal source records; support labels are always recomputed."""
    oracle, conditions = [], []
    scenario = entry['scenario']
    for kind, ref, records in [('production-audit', record['production_reference'], entry['audit']['oracle_records'])] + [
            (kind + '-scan', record['old_scans'][kind]['reference'], old_scans[kind][scenario]['oracle_records'])
            for kind in ('unary', 'pair') if kind in old_scans and scenario in old_scans[kind]]:
        for i, item in enumerate(records):
            oracle.append({'source': {'kind': kind, **ref, 'key': record['key'],
                                      'scenario': scenario, 'record_index': i}, 'record': item})
    if conditional is not None:
        for item in conditional['entries']:
            row = item['row']
            if row['target']['scenario'] != scenario:
                continue
            outcome = row['outcome']
            conditions.append({'source': {'kind': 'saturation-conditional',
                **record['conditional_reference'], 'upstream': conditional['upstream'],
                'key': record['key'], 'scenario': scenario, 'row_index': item['row_index']},
                'conditional': {'input': outcome['original_input'], 'outcome': outcome,
                    'trace_audit': row['verification'],
                    'status': 'conditional_refuted' if outcome['status'] == 'conflict' else 'conditional_inconclusive'}})
    return oracle, conditions


def compact_row(row):
    """Do not keep all full certificates in the coordinator's resident memory."""
    compact = {'key': row['key'], 'eligibility': row['eligibility'], 'runs': []}
    for entry in row['runs']:
        data = {k: v for k, v in entry.items() if k not in ('scan', 'verification')}
        if entry['execution'] == 'checked':
            scan = entry['scan']
            data['summary'] = scan['summary']
            data['unsupported'] = []
            for state in scan['states']:
                for family in ('single', 'pair'):
                    for number, target in enumerate(state[family + '_targets']):
                        if target['status'] == 'unsupported':
                            condition = scan['conditional_records'][target['conditional_index']]
                            data['unsupported'].append({'family': family, 'state_index': state['state_index'],
                                'phase': state['phase'], 'target_index': number,
                                'sides': target.get('sides', [target.get('side')]),
                                'symbols': target.get('symbols', [target.get('symbol')]),
                                'conditional_status': condition['status']})
        compact['runs'].append(data)
    return compact


def run_record(manifest, record):
    """Run only new raw queries or new conditional proofs; never color a graph."""
    entries, old_scans, conditional = load_context(manifest, record)
    row = {'key': record['key'], 'eligibility': record['eligibility'], 'runs': []}
    for entry in entries:
        result = {'scenario': entry['scenario'], 'execution': 'error'}
        row['runs'].append(result)
        oracle, conditions = pools(record, entry, old_scans, conditional)
        start = perf_counter()
        try:
            scan = scan_support(entry['raw_document'], entry['result']['run'],
                node_limit=RESOURCES['node_limit'], oracle_sources=oracle, conditional_sources=conditions)
            result['scan'] = scan
            result['scan_seconds'] = perf_counter() - start
            start = perf_counter()
            result['verification'] = check_support_scan(entry['raw_document'], entry['result']['run'], scan,
                node_limit=RESOURCES['node_limit'], oracle_sources=oracle, conditional_sources=conditions)
            result['check_seconds'] = perf_counter() - start
            result['execution'] = 'checked'
        except Exception as error:
            result['error'] = f'{type(error).__name__}: {error}'
    return row


def verify_row(manifest, record, row):
    """Resume and final replay check the full obligations and source origins."""
    same([row['key'], row['eligibility']], [record['key'], record['eligibility']], 'saved row identity')
    same([e['scenario'] for e in row['runs']], [s['id'] for s in record['scenarios']], 'scenario coverage')
    entries, old_scans, conditional = load_context(manifest, record)
    for original, saved in zip(entries, row['runs']):
        if saved['execution'] != 'checked':
            require(saved['execution'] == 'error' and isinstance(saved.get('error'), str), 'invalid incomplete row')
            continue
        oracle, conditions = pools(record, original, old_scans, conditional)
        checked = check_support_scan(original['raw_document'], original['result']['run'], saved['scan'],
            node_limit=RESOURCES['node_limit'], oracle_sources=oracle, conditional_sources=conditions)
        same(checked, saved['verification'], 'saved scan verification differs')


def _merge(target, values):
    """Recursively add integer summary counters without merging scope strings."""
    for key, value in values.items():
        if isinstance(value, dict):
            _merge(target.setdefault(key, {}), value)
        elif type(value) is int:
            target[key] = target.get(key, 0) + value
        else:
            raise AssertionError('unexpected non-counter summary: ' + key)


def summarize(rows, manifest):
    """Separate single support, joint support, conditional detection and costs."""
    originals = {r['key']: r for r in manifest['records']}
    groups, unsupported = {}, []
    for row in rows:
        original = originals[row['key']]
        labels = ['all', 'old-scanned' if 'pair' in original['old_scans'] else 'new-scanned']
        labels += ['population/' + p for p in original['populations']]
        for entry in row['runs']:
            for label in labels:
                total = groups.setdefault(label, {'runs': 0, 'checked': 0, 'errors': 0,
                    'scan_seconds': 0.0, 'check_seconds': 0.0, 'summary': {}})
                total['runs'] += 1
                if entry['execution'] != 'checked':
                    total['errors'] += 1
                    continue
                total['checked'] += 1
                total['scan_seconds'] += entry.get('scan_seconds', 0)
                total['check_seconds'] += entry.get('check_seconds', 0)
                _merge(total['summary'], entry['summary'])
            if entry['execution'] == 'checked':
                unsupported.extend({'key': row['key'], 'scenario': entry['scenario'], **item}
                                   for item in entry['unsupported'])
    lookup = {(r['key'], e['scenario']): e for r in rows for e in r['runs']}
    histories = []
    for population, history in manifest['histories']:
        for scenario in ('one-bounded-anchor', 'legacy-frame-anchors'):
            states = [lookup[(key, scenario)]['execution'] if originals[key]['eligibility'] == 'ready'
                      else originals[key]['eligibility'] for key in history['prefix_keys']]
            histories.append({'population': population, 'id': history['id'], 'scenario': scenario,
                'prefix_count': len(states), 'checked_prefixes': states.count('checked'),
                'excluded_prefixes': sum(originals[k]['eligibility'] != 'ready' for k in history['prefix_keys']),
                'complete': all(s == 'checked' for s in states)})
    return {'groups': groups, 'unsupported_targets': unsupported, 'histories': histories,
            'eligibility': dict(Counter(r['eligibility'] for r in rows)), 'compact_records': rows,
            'scope': 'Offline current-state support census; no feedback to the producer, no general completeness claim.'}


def init_worker(manifest, manifest_hash, directory):
    """Install the immutable per-command context once in each spawned worker."""
    global WORKER
    WORKER = manifest, manifest_hash, Path(directory)


def work_record(number):
    """Exclusive drawing checkpoint; interrupted complete files are replayed."""
    manifest, manifest_hash, directory = WORKER
    record = manifest['records'][number]
    path = directory / f'{number:03d}-{record["key"][:12]}.json.gz'
    reused = path.exists()
    if reused:
        saved = read_report(path)
        same(saved['manifest_sha256'], manifest_hash, 'resume manifest binding')
        same(saved['record_sha256'], digest(record), 'resume record binding')
        row = saved['row']
        verify_row(manifest, record, row)
    else:
        row = run_record(manifest, record)
        write_atomic(path, {'manifest_sha256': manifest_hash, 'record_sha256': digest(record), 'row': row})
    return number, reference(path), compact_row(row), reused


def execute(manifest_path, output):
    """Run a fixed two-worker census, returning compact rows to the coordinator."""
    require(not output.exists(), 'report exists; choose a new filename')
    manifest = bound_manifest(manifest_path)
    verify_conditional_parts(manifest)
    directory = output.parent / (output.name.removesuffix('.json.gz') + '-checkpoints')
    directory.mkdir(parents=True, exist_ok=True)
    completed, resumed = {}, 0
    start = perf_counter()
    with ProcessPoolExecutor(max_workers=RESOURCES['workers'], initializer=init_worker,
                             initargs=(manifest, checksum(manifest_path), str(directory))) as pool:
        futures = [pool.submit(work_record, i) for i in range(len(manifest['records']))]
        for future in as_completed(futures):
            number, ref, row, reused = future.result()
            completed[number] = ref, row
            resumed += int(reused)
            print(json.dumps({'completed_drawings': len(completed), 'total': len(futures),
                'record': number, 'resumed': reused,
                'executions': [e['execution'] for e in row['runs']]}, ensure_ascii=False), flush=True)
    same(manifest['source_sha256'], sources(), 'source drift during scan')
    refs, rows = zip(*(completed[i] for i in range(len(manifest['records']))))
    report = {'schema_version': 1, 'version': VERSION, 'manifest_sha256': checksum(manifest_path),
              'checkpoints': list(refs), 'summary': summarize(list(rows), manifest),
              'execution': {'workers': RESOURCES['workers'], 'resumed_drawings': resumed,
                            'wall_seconds': perf_counter() - start, 'producer_reruns': 0}}
    write_atomic(output, report)
    return report['summary']['groups']['all']


def check(manifest_path, report_path, output):
    """Replay saved queries and traces only, never rerun producer or search."""
    require(not output.exists(), 'check exists; choose a new filename')
    manifest, report = bound_manifest(manifest_path), read_report(report_path)
    verify_conditional_parts(manifest)
    same([report['schema_version'], report['version']], [1, VERSION], 'report schema')
    same(report['manifest_sha256'], checksum(manifest_path), 'report freeze')
    require(len(report['checkpoints']) == len(manifest['records']), 'checkpoint coverage')
    rows = []
    for i, (ref, record) in enumerate(zip(report['checkpoints'], manifest['records'])):
        saved = bound_reference(ref)
        same(saved['manifest_sha256'], checksum(manifest_path), 'checkpoint freeze')
        same(saved['record_sha256'], digest(record), 'checkpoint record')
        verify_row(manifest, record, saved['row'])
        rows.append(compact_row(saved['row']))
        if (i + 1) % 25 == 0:
            print(json.dumps({'checked_drawings': i + 1, 'total': len(manifest['records'])}), flush=True)
    summary = summarize(rows, manifest)
    same(report['summary'], summary, 'summary reconstruction')
    same(manifest['source_sha256'], sources(), 'source drift during check')
    total = summary['groups']['all']
    values = total['summary']
    complete = total['errors'] == 0
    result = {'passed': True, 'eligible_executions_complete': complete,
        'all_base_states_sat': complete and values['base_status_counts']['unsat'] == 0
            and values['base_status_counts']['unknown'] == 0,
        'exact_queries_conclusive': complete and values['oracle_status_counts']['unknown'] == 0,
        'all_single_candidates_supported': complete and values['single']['status_counts']['unsupported'] == 0
            and values['single']['status_counts']['unknown'] == 0 and values['single']['status_counts']['preexisting_unsat'] == 0,
        'all_pair_candidates_supported': complete and values['pair']['status_counts']['unsupported'] == 0
            and values['pair']['status_counts']['unknown'] == 0 and values['pair']['status_counts']['preexisting_unsat'] == 0,
        'all_unsupported_conditionally_refuted': complete and values['conditional_status_counts']['conditional_inconclusive'] == 0,
        'counts': total, 'manifest_sha256': checksum(manifest_path), 'report_sha256': checksum(report_path),
        'source_sha256': sources(), 'producer_reruns': 0, 'propagation_reruns': 0, 'oracle_search_reruns': 0}
    write_atomic(output, result)
    return {k: v for k, v in result.items() if k != 'source_sha256'}


def main():
    """Separate preparation, resumable execution and independent saved checking."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'run', 'check'))
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(args.manifest.resolve())
    elif args.command == 'run':
        require(args.output is not None, '--output required')
        result = execute(args.manifest.resolve(), args.output.resolve())
    else:
        require(args.output is not None and args.report is not None, '--report and --output required')
        result = check(args.manifest.resolve(), args.report.resolve(), args.output.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()

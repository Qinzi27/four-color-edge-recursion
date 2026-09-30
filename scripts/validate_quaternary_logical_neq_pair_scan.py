"""Freeze and scan jointly allowed color pairs on already saved logical-NEQ runs.

The producer is never rerun or informed by this offline diagnostic. All actual
persistent states and candidate targets are fixed before any new exact query.
Archived exclusions remain records. A hypothetical pair that includes the next
actual choice is not an actual simultaneous commitment.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.check_quaternary_logical_neq_pair_scan import check_pair_scan
from scripts.check_quaternary_reachability import checksum
from scripts.check_quaternary_reachability_artifacts import same
from scripts.quaternary_logical_neq_pair_scan import pair_inventory, scan_pairs
from scripts.validate_global_restart import digest, write_report
from scripts.validate_quaternary_contacts_v2 import read_report
from scripts import validate_quaternary_logical_neq_candidate_scan as unary_archive
from scripts.validate_quaternary_logical_neq_candidate_scan import sources as previous_sources

VERSION = 'quaternary-logical-neq-pair-experiment-v1'
ARCHIVE_MANIFEST = 'outputs/quaternary-logical-neq-candidate-scan-manifest-2026-09-29.json.gz'
ARCHIVE_REPORT = 'outputs/quaternary-logical-neq-candidate-scan-2026-09-29.json.gz'
ARCHIVE_CHECK = 'outputs/quaternary-logical-neq-candidate-scan-check-2026-09-29.json'
PREQUERY_CENSUS = 'outputs/quaternary-logical-neq-pair-prequery-inventory-2026-09-29.json'
INPUT_PATHS = (ARCHIVE_MANIFEST, ARCHIVE_REPORT, ARCHIVE_CHECK, PREQUERY_CENSUS)
PROTOCOL = 'docs/QUATERNARY_LOGICAL_NEQ_PAIR_SCAN_PROTOCOL-2026-09-29.md'
NEW_SOURCES = ('scripts/quaternary_logical_neq_pair_scan.py', 'tests/test_quaternary_logical_neq_pair_scan.py',
               'scripts/check_quaternary_logical_neq_pair_scan.py', 'tests/test_check_quaternary_logical_neq_pair_scan.py',
               'scripts/validate_quaternary_logical_neq_pair_scan.py',
               'tests/test_validate_quaternary_logical_neq_pair_scan.py', PROTOCOL)
RESOURCES = {'node_limit': 200000}
EXPECTED_COUNTS = {'records': 477,
                   'eligibility': {'geometry_error': 12, 'ready': 428, 'geometry_audit_error': 37},
                   'runs': 855, 'persistent_states': 4518, 'eligible_side_pairs': 72984,
                   'pair_targets': 670916, 'cartesian_color_pairs': 746006, 'states_without_pairs': 1500}


def require(condition, message):
    """Reject incomplete or mismatched evidence even with Python optimization."""
    if not condition:
        raise AssertionError(message)


def sources():
    """Preserve all 208 prior sources and bind the separate diagnostic version."""
    hashes = previous_sources()
    same(hashes, read_report(ROOT / ARCHIVE_MANIFEST)['source_sha256'], 'old source chain changed')
    hashes.update({name: checksum(ROOT / name) for name in NEW_SOURCES})
    return hashes


def bound_reference(reference):
    """Require repository-relative, hash-bound output files before loading."""
    path = (ROOT / reference['path']).resolve()
    require(path.is_relative_to(ROOT / 'outputs'), 'artifact outside outputs')
    same(checksum(path), reference['sha256'], 'artifact bytes changed')
    return read_report(path)


def target_counts(inventory):
    """Compact counts accompany a hash of every ordered literal pair target."""
    states = inventory['states']
    return {'persistent_states': len(states),
            'eligible_side_pairs': sum(s['eligible_side_pair_count'] for s in states),
            'pair_targets': sum(len(s['targets']) for s in states),
            'cartesian_color_pairs': sum(s['cartesian_target_count'] for s in states),
            'states_without_pairs': sum(not s['targets'] for s in states)}


def bind_inventory(inventory, scenario):
    """Counts alone are insufficient: bind complete metadata and ordered targets."""
    same(digest(inventory), scenario['inventory_sha256'], 'complete pair inventory differs')
    same(target_counts(inventory), scenario['inventory_counts'], 'pair inventory counts differ')


def archive_records(*, verify_saved):
    """Replay prior unary evidence; bind producer bytes without rerunning it.

    The unary manifest checker validates the producer/geometry provenance and
    target identities. Its successful saved check binds the older trace audits.
    Only prior unary SAT/UNSAT evidence is replayed here, not rule enumeration.
    """
    manifest = unary_archive.bound_manifest(ROOT / ARCHIVE_MANIFEST)
    report, checked = [read_report(ROOT / name) for name in (ARCHIVE_REPORT, ARCHIVE_CHECK)]
    same([report['schema_version'], report['version']], [1, unary_archive.VERSION], 'unary report version')
    for obj, label in ((report, 'report'), (checked, 'check')):
        same(obj['manifest_sha256'], checksum(ROOT / ARCHIVE_MANIFEST), 'unary ' + label + ' manifest')
    same(checked['report_sha256'], checksum(ROOT / ARCHIVE_REPORT), 'unary checked report')
    same(checked['source_sha256'], manifest['source_sha256'], 'unary checked source')
    require(all(checked.get(k) is True for k in ('passed', 'eligible_executions_complete',
            'exact_queries_conclusive', 'all_scanned_candidates_supported')), 'unary evidence incomplete')
    same(checked['counts']['checked'], 855, 'unary checked run coverage')
    require(len(report['checkpoints']) == len(manifest['records']), 'unary checkpoint coverage')
    census = read_report(ROOT / PREQUERY_CENSUS)
    same(census['source_manifest'], {'path': ARCHIVE_MANIFEST, 'sha256': checksum(ROOT / ARCHIVE_MANIFEST)},
         'pre-query census source')
    same(census['counts'], EXPECTED_COUNTS, 'pre-query census counts')
    by_run = {(r['key'], r['scenario']): r for r in census['runs']}
    require(len(by_run) == len(census['runs']) == EXPECTED_COUNTS['runs'], 'census duplicate or missing run')
    records = []
    for old, reference in zip(manifest['records'], report['checkpoints']):
        checkpoint = bound_reference(reference)
        same(checkpoint['manifest_sha256'], checksum(ROOT / ARCHIVE_MANIFEST), 'unary checkpoint freeze')
        same(checkpoint['record_sha256'], digest(old), 'unary checkpoint original record')
        row = checkpoint['row']
        same([row['key'], row['eligibility']], [old['key'], old['eligibility']], 'unary row identity')
        same([r['scenario'] for r in row['runs']], [s['id'] for s in old['scenarios']], 'unary scenarios')
        record = {k: old[k] for k in ('key', 'kind', 'eligibility', 'archive_reference', 'archive_populations')}
        record.update(single_scan_reference=reference, scenarios=[])
        for saved, scenario in zip(row['runs'], old['scenarios']):
            require(saved['execution'] == 'checked', 'unary scenario not checked')
            entry = unary_archive.load_entry(old, scenario)
            same(saved['scan']['inventory'], scenario['inventory'], 'unary frozen targets')
            if verify_saved:
                verified = unary_archive.check_candidate_scan(entry['raw_document'], entry['result']['run'],
                    saved['scan'], **manifest['resources'])
                same(verified, saved['verification'], 'unary saved certificate verification')
            inventory = pair_inventory(entry['raw_document'], entry['result']['run'])
            counts = target_counts(inventory)
            prior = by_run[(old['key'], scenario['id'])]
            same(prior['checkpoint'], old['archive_reference'], 'census producer reference')
            same(counts, {k: prior[k] for k in counts}, 'independent pair census')
            item = {k: scenario[k] for k in ('id', 'raw_document_sha256', 'envelope_sha256', 'audit_sha256')}
            item.update(inventory_sha256=digest(inventory), inventory_counts=counts,
                        single_scan_sha256=digest(saved['scan']))
            record['scenarios'].append(item)
        records.append(record)
    return records


def inventory_counts(records):
    """Count canonical unordered unresolved face pairs and allowed color tuples."""
    total = {'records': len(records), 'eligibility': dict(Counter(r['eligibility'] for r in records)),
             'runs': sum(len(r['scenarios']) for r in records)}
    for key in ('persistent_states', 'eligible_side_pairs', 'pair_targets',
                'cartesian_color_pairs', 'states_without_pairs'):
        total[key] = sum(s['inventory_counts'][key] for r in records for s in r['scenarios'])
    return total


def prepare(path):
    """Verify history evidence and freeze literal targets before new queries."""
    require(not path.exists(), 'manifest exists; choose a new name')
    hashes = sources()
    inputs = {name: checksum(ROOT / name) for name in INPUT_PATHS}
    records = archive_records(verify_saved=True)
    same(hashes, sources(), 'sources changed during preparation')
    same(inputs, {name: checksum(ROOT / name) for name in INPUT_PATHS}, 'archive changed during preparation')
    counts = inventory_counts(records)
    same(counts, EXPECTED_COUNTS, 'inventory differs from independent pre-query census')
    manifest = {'schema_version': 1, 'version': VERSION, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
                'source_sha256': hashes, 'input_sha256': inputs, 'records': records,
                'resources': RESOURCES, 'counts': counts,
                'producer_reruns': 0, 'new_oracle_queries_before_freeze': 0,
                'old_unary_evidence_replayed': True}
    write_report(path, manifest)
    return manifest['counts']


def bound_manifest(path):
    """Rebuild the target list from frozen archived traces without querying."""
    manifest = read_report(path)
    same([manifest['schema_version'], manifest['version']], [1, VERSION], 'scan manifest version differs')
    same(manifest['source_sha256'], sources(), 'scan sources changed')
    same(manifest['input_sha256'], {n: checksum(ROOT / n) for n in INPUT_PATHS}, 'archive changed')
    same(manifest['resources'], RESOURCES, 'scan resource limit changed')
    same(manifest['records'], archive_records(verify_saved=False), 'frozen targets changed')
    same(manifest['counts'], inventory_counts(manifest['records']), 'scan inventory counts differ')
    same(manifest['counts'], EXPECTED_COUNTS, 'predeclared census differs')
    require(manifest['producer_reruns'] == 0 and manifest['new_oracle_queries_before_freeze'] == 0
            and manifest['old_unary_evidence_replayed'] is True, 'pre-freeze activity claims differ')
    return manifest


def load_entry(record, scenario):
    """Bind the precise old producer envelope to its scanned input and targets."""
    saved = bound_reference(record['archive_reference'])['row']
    matches = [r for r in saved['runs'] if r['policy'] == 'logical-neq' and r['scenario'] == scenario['id']]
    require(len(matches) == 1, 'missing or repeated archived scenario')
    entry = matches[0]
    for field, name in (('raw_document', 'raw_document_sha256'), ('result', 'envelope_sha256'),
                        ('audit', 'audit_sha256')):
        same(digest(entry[field]), scenario[name], 'archived ' + field + ' changed')
    return entry


def check_unary_consistency(scan):
    """The frozen upstream census has a SAT witness for every endpoint.

    A fresh UNKNOWN does not contradict that archive. A verified endpoint
    UNSAT would contradict it and must remain a failed research run, not be
    presented as a newly found joint-only obstruction.
    """
    require(scan['summary']['single_support_counts']['has_unsupported_single'] == 0,
            'pair endpoint UNSAT contradicts frozen unary SAT evidence')


def run_record(record):
    """Retain scan errors with their fixed input, rather than silently skipping."""
    saved = {'key': record['key'], 'eligibility': record['eligibility'], 'runs': []}
    for scenario in record['scenarios']:
        entry = load_entry(record, scenario)
        result = {'scenario': scenario['id'], 'execution': 'error'}
        try:
            scan = scan_pairs(entry['raw_document'], entry['result']['run'], **RESOURCES)
            result['scan'] = scan
            bind_inventory(scan['inventory'], scenario)
            result['verification'] = check_pair_scan(entry['raw_document'], entry['result']['run'], scan, **RESOURCES)
            check_unary_consistency(scan)
            result['execution'] = 'checked'
        except Exception as error:
            result['error'] = f'{type(error).__name__}: {error}'
        saved['runs'].append(result)
    return saved


def _add_counts(total, values):
    """Add nested count dictionaries while retaining zero-valued categories."""
    for name, value in values.items():
        if isinstance(value, dict):
            _add_counts(total.setdefault(name, {}), value)
        elif type(value) is int:
            total[name] = total.get(name, 0) + value
        else:
            raise AssertionError('non-count value in scan summary: ' + name)


def summarize(rows, manifest):
    """Separate geometry/abstract and modes; preserve each earliest residual gap."""
    original = {r['key']: r for r in manifest['records']}
    groups, firsts = {}, []
    for row in rows:
        kind = original[row['key']]['kind']
        for entry in row['runs']:
            labels = ['all', kind, kind + '/' + entry['scenario']]
            labels += ['population/' + p for p in original[row['key']]['archive_populations']]
            for label in dict.fromkeys(labels):
                group = groups.setdefault(label, {'runs': 0, 'checked': 0, 'errors': 0, 'metrics': {}})
                group['runs'] += 1
                if entry['execution'] == 'checked':
                    group['checked'] += 1
                    _add_counts(group['metrics'], entry['scan']['summary'])
                else:
                    group['errors'] += 1
            if entry['execution'] == 'checked':
                gaps = [(state, target) for state in entry['scan']['states'] for target in state['targets']
                        if target['status'] == 'unsupported']
                if gaps:
                    state, target = gaps[0]
                    firsts.append({'key': row['key'], 'kind': kind, 'scenario': entry['scenario'],
                        'state_index': state['state_index'], 'phase': state['phase'],
                        'sides': target['sides'], 'symbols': target['symbols'],
                        'category': target['category'], 'next_action': target['next_action'],
                        'single_support': target['single_support']})
    return {'groups': groups, 'first_unsupported_per_run': firsts,
            'eligibility': dict(Counter(row['eligibility'] for row in rows)),
            'scope': 'First means event order within each saved run, then side/color order; '
                     'not a globally minimal graph or a probability sample.'}


def compact_row(row):
    """Retain aggregate counts and unsupported identities, not all oracle trees.

    Full evidence remains in exclusive checkpoints. This bounds memory while
    collecting thousands of state queries and their repeated SAT witnesses.
    """
    compact = {'key': row['key'], 'eligibility': row['eligibility'], 'runs': []}
    for entry in row['runs']:
        item = {'scenario': entry['scenario'], 'execution': entry['execution']}
        if entry['execution'] == 'checked':
            gaps = []
            for state in entry['scan']['states']:
                targets = [{k: t[k] for k in ('sides', 'symbols', 'status', 'category', 'next_action', 'single_support')}
                           for t in state['targets'] if t['status'] == 'unsupported']
                if targets:
                    gaps.append({'state_index': state['state_index'], 'phase': state['phase'],
                                 'targets': targets})
            item['scan'] = {'summary': entry['scan']['summary'], 'states': gaps}
        compact['runs'].append(item)
    return compact


def execute(manifest_path, output):
    """Save one exclusive checkpoint per old drawing, including exclusions."""
    require(not output.exists(), 'result exists; choose a new name')
    manifest = bound_manifest(manifest_path)
    frozen_hash = checksum(manifest_path)
    directory = output.parent / (output.name.removesuffix('.json.gz') + '-checkpoints')
    directory.mkdir(parents=True, exist_ok=True)
    rows, references = [], []
    for number, record in enumerate(manifest['records']):
        path = directory / f'{number:03d}-{record["key"][:12]}.json.gz'
        if path.exists():
            checkpoint = read_report(path)
            same(checkpoint['manifest_sha256'], frozen_hash, 'checkpoint freeze differs')
            same(checkpoint['record_sha256'], digest(record), 'checkpoint target inventory differs')
            row = checkpoint['row']
            same([row['key'], row['eligibility']], [record['key'], record['eligibility']],
                 'resumed checkpoint identity differs')
            same([r['scenario'] for r in row['runs']], [s['id'] for s in record['scenarios']],
                 'resumed checkpoint scenario coverage differs')
        else:
            row = run_record(record)
            write_report(path, {'manifest_sha256': frozen_hash, 'record_sha256': digest(record), 'row': row})
        rows.append(compact_row(row))
        references.append({'path': path.relative_to(ROOT).as_posix(), 'sha256': checksum(path)})
        print(json.dumps({'completed': number + 1, 'total': len(manifest['records']),
                          'executions': [r['execution'] for r in row['runs']]}, ensure_ascii=False), flush=True)
    same(manifest['source_sha256'], sources(), 'source changed during scan')
    report = {'schema_version': 1, 'version': VERSION, 'manifest_sha256': frozen_hash,
              'checkpoints': references, 'summary': summarize(rows, manifest)}
    write_report(output, report)
    return report['summary']['groups']


def check(manifest_path, report_path, output):
    """Verify all saved exact trees, target coverage and conditional traces."""
    require(not output.exists(), 'check output exists; choose a new name')
    manifest, report = bound_manifest(manifest_path), read_report(report_path)
    same([report['schema_version'], report['version']], [1, VERSION], 'report version differs')
    same(report['manifest_sha256'], checksum(manifest_path), 'report freeze differs')
    require(len(report['checkpoints']) == len(manifest['records']), 'scan checkpoint coverage differs')
    rows, counts = [], Counter()
    for record, reference in zip(manifest['records'], report['checkpoints']):
        checkpoint = bound_reference(reference)
        same(checkpoint['manifest_sha256'], checksum(manifest_path), 'checkpoint freeze differs')
        same(checkpoint['record_sha256'], digest(record), 'checkpoint targets differ')
        row = checkpoint['row']
        same([row['key'], row['eligibility']], [record['key'], record['eligibility']], 'scan record differs')
        same([r['scenario'] for r in row['runs']], [s['id'] for s in record['scenarios']], 'scan scenario coverage differs')
        for saved, scenario in zip(row['runs'], record['scenarios']):
            counts['runs'] += 1
            if saved['execution'] != 'checked':
                counts['incomplete'] += 1
                continue
            entry = load_entry(record, scenario)
            bind_inventory(saved['scan']['inventory'], scenario)
            verification = check_pair_scan(entry['raw_document'], entry['result']['run'], saved['scan'], **RESOURCES)
            check_unary_consistency(saved['scan'])
            same(saved['verification'], verification, 'saved scan verification differs')
            counts['checked'] += 1
            counts['oracle_records'] += len(saved['scan']['oracle_records'])
            counts['unknown_queries'] += saved['scan']['summary']['oracle_status_counts']['unknown']
            counts['unknown_targets'] += saved['scan']['summary']['target_status_counts']['unknown']
            counts['unsupported_targets'] += saved['scan']['summary']['target_status_counts']['unsupported']
            counts['preexisting_unsat_targets'] += saved['scan']['summary']['target_status_counts']['preexisting_unsat']
            counts['unsat_base_states'] += saved['scan']['summary']['base_status_counts']['unsat']
            counts['unsupported_including_next_commit'] += saved['scan']['summary']['next_action_counts']['includes_next_commit']['unsupported']
            counts['joint_only_unsupported'] += saved['scan']['summary']['single_support_counts']['both_supported']
            counts['conditional_inconclusive'] += saved['scan']['summary']['conditional_counts']['conditional_inconclusive']
        rows.append(compact_row(row))
    same(report['summary'], summarize(rows, manifest), 'scan summary reconstruction differs')
    same(manifest['source_sha256'], sources(), 'source changed during check')
    result = {'passed': True, 'eligible_executions_complete': counts['incomplete'] == 0,
              'exact_queries_conclusive': counts['incomplete'] == 0 and counts['unknown_queries'] == 0,
              'all_scanned_pairs_supported': not any(counts[k] for k in (
                  'incomplete', 'unknown_queries', 'unsupported_targets',
                  'preexisting_unsat_targets', 'unsat_base_states')),
              'producer_reruns': 0, 'oracle_search_reruns': 0, 'conditional_propagation_reruns': 0,
              'manifest_sha256': checksum(manifest_path), 'report_sha256': checksum(report_path),
              'counts': dict(counts), 'source_sha256': sources(),
              'scope': 'Saved evidence integrity, not universal extension or candidate completeness.'}
    write_report(output, result)
    return result['counts']


def main():
    """Separate pre-query freeze, offline scan and search-free evidence replay."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'run', 'check'))
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(args.manifest.resolve())
    else:
        require(args.output is not None, '--output required')
        if args.command == 'run':
            result = execute(args.manifest.resolve(), args.output.resolve())
        else:
            require(args.report is not None, '--report required')
            result = check(args.manifest.resolve(), args.report.resolve(), args.output.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

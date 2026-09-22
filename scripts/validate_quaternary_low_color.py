"""Freeze and compare low-color commitment with and without trial propagation.

Every producer finishes before its offline audit starts. The two policies share
input anchors, geometry, scheduling and ordinary pair propagation. Complete
traces and exact evidence are saved in exclusive checkpoint files; the main
report keeps compact summaries and hashes instead of duplicating those files.
"""

from argparse import ArgumentParser
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.validate_global_restart import digest, export_geometries, write_report
from scripts.validate_quaternary_contacts_v2 import read_report
from scripts.validate_quaternary_geometry import (
    PRIMARY, LEGACY, source_hashes as geometry_sources, standard_scenarios,
)

BASE = 'outputs/quaternary-geometry-manifest-2026-09-21.json.gz'
PROTOCOL = 'docs/QUATERNARY_LOW_COLOR_PROTOCOL-2026-09-22.md'
POLICIES = ('plain', 'guarded')
ADDED_SOURCES = (
    'scripts/quaternary_low_color.py', 'scripts/audit_quaternary_low_color.py',
    'scripts/quaternary_low_color_inputs.py', 'scripts/validate_quaternary_low_color.py',
    'tests/test_quaternary_low_color.py', 'tests/test_quaternary_low_color_audit.py',
    'tests/test_quaternary_low_color_inputs.py', 'tests/test_quaternary_low_color_experiment.py',
    PROTOCOL,
)


def require(condition, message):
    """Keep file-integrity and evidence checks active in optimized Python."""
    if not condition:
        raise AssertionError(message)


def file_hash(path):
    """Hash exact source or compressed artifact bytes."""
    return sha256(Path(path).read_bytes()).hexdigest()


def sources():
    """Verify the old frozen source set, then bind this separate experiment."""
    from scripts.quaternary_low_color_inputs import SOURCE_FILES
    hashes = geometry_sources()
    frozen = read_report(ROOT / BASE)
    require(hashes == frozen['source_sha256'], 'old geometry sources changed')
    hashes.update({name: file_hash(ROOT / name) for name in set(ADDED_SOURCES) | set(SOURCE_FILES)})
    return hashes


def inventory():
    """Retain all old drawings and add predetermined unseen-history inputs."""
    from scripts.quaternary_low_color_inputs import build_holdout
    old, holdout = read_report(ROOT / BASE), build_holdout()
    old_keys = {r['key'] for r in old['records']}
    records = {}
    for row in old['records']:
        records[row['key']] = {
            'key': row['key'], 'document': row['document'], 'families': list(row['families']),
            'geometry': row['geometry'], 'geometry_sha256': row['geometry_sha256'],
            'new_geometry': False, 'holdout_aliases': [],
            'scenarios': [s for s in row['scenarios']
                          if s['id'] in (PRIMARY, LEGACY) or 'first-commit' in s['id']],
        }
    for row in holdout['records']:
        key = row['key']
        if key not in records:
            records[key] = {'key': key, 'document': row['document'], 'families': [],
                            'new_geometry': key not in old_keys, 'holdout_aliases': []}
        saved = records[key]
        require(saved['document'] == row['document'], 'same key has different input')
        saved['families'] = sorted(set(saved['families']) | set(row['families']))
        saved['holdout_aliases'] = row['aliases']
    histories = [{'id': f'grid-{i}', 'family': 'grid-subsets', **h}
                 for i, h in enumerate(old['grid_histories'])] + holdout['histories']
    return {'records': [records[k] for k in sorted(records)], 'histories': histories,
            'generation': holdout['generation'], 'old_distinct_drawings': len(old_keys)}


def prepare(path):
    """Bind actual inputs and sources before either new policy is executed."""
    require(not path.exists(), 'manifest exists; choose a new name')
    hashes, original_hash = sources(), file_hash(ROOT / BASE)
    selected = inventory()
    new = [r for r in selected['records'] if 'geometry' not in r]
    for offset in range(0, len(new), 64):
        batch = new[offset:offset + 64]
        exported = export_geometries(batch)
        require(len(exported) == len(batch), 'geometry export omitted drawings')
        for row, exported_row in zip(batch, exported):
            require(exported_row['status'] == 'geometry_ok' and row['key'] == exported_row['key'],
                    'a predeclared drawing has invalid geometry')
            row['geometry'] = exported_row['geometry']
            row['geometry_sha256'] = digest(row['geometry'])
            row['scenarios'] = standard_scenarios(row['geometry'], {'extra_scenarios': []})
    counts = {'drawings': len(selected['records']),
              'new_geometry': sum(r['new_geometry'] for r in selected['records']),
              'scenarios_per_policy': sum(len(r['scenarios']) for r in selected['records']),
              'histories': len(selected['histories']),
              'prefix_references': sum(len(h['prefix_keys']) for h in selected['histories'])}
    counts['policy_runs'] = counts['scenarios_per_policy'] * len(POLICIES)
    manifest = {'schema_version': 1, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
                **selected, 'counts': counts, 'policies': list(POLICIES),
                'resources': {'workers': 4, 'batch_size': 16, 'assignment_limit': 262144,
                              'node_limit': 200000, 'decision_limit': 128, 'probe_limit': 512},
                'source_sha256': hashes, 'input_artifact_sha256': {BASE: original_hash},
                'producer_runs_during_prepare': 0, 'oracle_runs_during_prepare': 0,
                'scope': 'Known regression inventory plus fixed new construction histories; '
                         'paired policies, original colors never supplied, no cross-policy rescue.'}
    require(hashes == sources() and original_hash == file_hash(ROOT / BASE), 'freeze inputs drifted')
    write_report(path, manifest)
    return counts


def run_record(payload):
    """Produce both complete policy runs first; then audit them independently."""
    from scripts.quaternary_low_color import solve_low_color
    from scripts.audit_quaternary_low_color import audit_low_color
    row, limits = payload
    completed, adapted, candidates, current, audit = [], None, {}, None, None
    try:
        require(digest(row['geometry']) == row['geometry_sha256'], 'geometry hash mismatch')
        for scenario in row['scenarios']:
            current = {'scenario': scenario['id'], 'stage': 'adapt'}
            adapted, candidates, audit = None, {}, None
            adapted = adapt_exported_geometry(row['geometry'], anchors=scenario['anchors'],
                                              drawing=row['document'])
            document = adapted['contact_document']
            candidates, production_times = {}, {}
            for policy in POLICIES:
                current = {'scenario': scenario['id'], 'policy': policy, 'stage': 'produce'}
                start = perf_counter()
                candidates[policy] = solve_low_color(
                    document, geometry=row['geometry'], probe=policy == 'guarded',
                    decision_limit=limits['decision_limit'], probe_limit=limits['probe_limit'])
                production_times[policy] = perf_counter() - start
            for policy in POLICIES:
                current = {'scenario': scenario['id'], 'policy': policy, 'stage': 'audit'}
                audit = None
                start = perf_counter()
                outcome = candidates[policy]
                audit = audit_low_color(document, outcome, geometry=row['geometry'], adapted=adapted,
                                        assignment_limit=limits['assignment_limit'],
                                        node_limit=limits['node_limit'])
                require(audit['passed'], 'independent auditor rejected evidence')
                if 'expected_raw_status' in scenario:
                    actual = audit['oracle_records'][audit['initial_oracle_index']]['result']['status']
                    require(actual in (scenario['expected_raw_status'], 'unknown'),
                            'historical initialization has opposite exact status')
                completed.append({'scenario': scenario['id'], 'policy': policy,
                                  'anchors': scenario['anchors'], 'outcome': outcome, 'audit': audit,
                                  'producer_seconds': production_times[policy],
                                  'audit_seconds': perf_counter() - start})
        return {'key': row['key'], 'geometry_sha256': row['geometry_sha256'],
                'new_geometry': row['new_geometry'], 'families': row['families'], 'runs': completed}
    except Exception as error:
        # Algorithmic conflicts are normal results. Only evidence/implementation
        # errors stop a batch, preserving both completed and interrupted scenes.
        return {'failed': True, 'key': row['key'], 'input': row, 'current': current,
                'adapted': adapted, 'candidates': candidates, 'completed_runs': completed,
                'audit': audit,
                'error_type': type(error).__name__, 'error': str(error)}


def compact_run(run):
    """Reference complete checkpoint evidence while retaining useful counters."""
    result, audit = run['outcome'], run['audit']
    initial = audit['oracle_records'][audit['initial_oracle_index']]['result']['status']
    return {'scenario': run['scenario'], 'policy': run['policy'], 'anchors': run['anchors'],
            'status': result['status'], 'reason': result['reason'], 'choices': result['choices'],
            'probes': result['probes'], 'rejections': result['rejections'],
            'initial_oracle_status': initial, 'commitment_counts': audit['commitment_counts'],
            'rejection_counts': audit['rejection_counts'], 'oracle_unknown': audit['oracle_unknown'],
            'first_bad_commitment_found': audit['first_bad_commitment'] is not None,
            'audit_passed': audit['passed'], 'full_enumeration': audit['full_enumeration'],
            'phase_count': audit['phase_count'], 'trace_steps_checked': audit['trace_steps_checked'],
            'producer_seconds': run['producer_seconds'], 'audit_seconds': run['audit_seconds'],
            'outcome_sha256': digest(result), 'audit_sha256': digest(audit)}


def validate_manifest(manifest):
    """Rebuild the declared input selection without running a coloring policy."""
    require(manifest['source_sha256'] == sources(), 'sources drifted since freeze')
    require(all(file_hash(ROOT / name) == value
                for name, value in manifest['input_artifact_sha256'].items()), 'input archive changed')
    expected = inventory()
    require(manifest['histories'] == expected['histories']
            and manifest['generation'] == expected['generation'], 'history or generation declaration altered')
    require(manifest['policies'] == list(POLICIES), 'policy list changed')
    require(manifest['resources'] == {'workers': 4, 'batch_size': 16, 'assignment_limit': 262144,
                                     'node_limit': 200000, 'decision_limit': 128, 'probe_limit': 512},
            'predeclared resource bounds altered')
    require(len(manifest['records']) == len(expected['records']), 'input inventory coverage differs')
    for saved, original in zip(manifest['records'], expected['records']):
        require(all(saved.get(name) == value for name, value in original.items()),
                'manifest changed a source drawing, family or scenario')
        require(digest(saved['geometry']) == saved['geometry_sha256'], 'geometry digest differs')
        expected_scenarios = original.get('scenarios')
        if expected_scenarios is None:
            expected_scenarios = standard_scenarios(saved['geometry'], {'extra_scenarios': []})
        require(saved['scenarios'] == expected_scenarios, 'scenario anchors differ')
    counts = {'drawings': len(expected['records']),
              'new_geometry': sum(r['new_geometry'] for r in expected['records']),
              'scenarios_per_policy': sum(len(r['scenarios']) for r in manifest['records']),
              'histories': len(expected['histories']),
              'prefix_references': sum(len(h['prefix_keys']) for h in expected['histories'])}
    counts['policy_runs'] = counts['scenarios_per_policy'] * len(POLICIES)
    require(manifest['counts'] == counts, 'declared counts differ from complete inventory')


def summarize(records, manifest):
    """Keep policy, initialization and new-versus-known input scopes separate."""
    scopes = {'all': records, 'known': [r for r in records if not r['new_geometry']],
              'new_geometry': [r for r in records if r['new_geometry']]}
    summary = {'scopes': {}, 'all_audits_passed': True}
    for scope, rows in scopes.items():
        groups, comparisons = {}, {}
        for row in rows:
            for run in row['runs']:
                groups.setdefault(run['scenario'] + '/' + run['policy'], []).append(run)
            for scenario in {r['scenario'] for r in row['runs']}:
                pair = {r['policy']: r for r in row['runs'] if r['scenario'] == scenario}
                a, b = pair['plain'], pair['guarded']
                if a['initial_oracle_status'] != 'sat' or b['initial_oracle_status'] != 'sat':
                    category = 'initialization_not_verified_sat'
                elif 'incomplete' in (a['status'], b['status']):
                    category = 'unfinished'
                elif a['status'] == b['status'] == 'solved':
                    category = 'both_solved'
                elif a['status'] != 'solved' and b['status'] == 'solved':
                    category = 'guarded_only_solved'
                elif a['status'] == 'solved' and b['status'] != 'solved':
                    category = 'plain_only_solved'
                else:
                    category = 'neither_solved'
                comparisons.setdefault(scenario, Counter())[category] += 1
        aggregates = {}
        for name, runs in groups.items():
            commitments, rejections = Counter(), Counter()
            for run in runs:
                commitments.update(run['commitment_counts'])
                rejections.update(run['rejection_counts'])
            aggregates[name] = {'runs': len(runs), 'statuses': dict(Counter(r['status'] for r in runs)),
                                'initial_oracle_statuses': dict(Counter(r['initial_oracle_status'] for r in runs)),
                                'commitment_counts': dict(commitments), 'rejection_counts': dict(rejections),
                                'full_enumeration': dict(Counter(r['full_enumeration']['status'] for r in runs))}
            for field in ('choices', 'probes', 'rejections', 'oracle_unknown', 'phase_count',
                          'trace_steps_checked', 'producer_seconds', 'audit_seconds'):
                aggregates[name][field] = sum(r[field] for r in runs)
            aggregates[name]['first_bad_commitment_cases'] = sum(r['first_bad_commitment_found'] for r in runs)
        summary['scopes'][scope] = {'drawings': len(rows), 'groups': aggregates,
                                    'paired_completion': {k: dict(v) for k, v in comparisons.items()}}
    index = {r['key']: r for r in records}
    history_stats = {}
    for history in manifest['histories']:
        for mode in (PRIMARY, LEGACY):
            for policy in POLICIES:
                key = history['family'] + '/' + mode + '/' + policy
                tally = history_stats.setdefault(key, Counter())
                runs = [next(r for r in index[p]['runs'] if r['scenario'] == mode and r['policy'] == policy)
                        for p in history['prefix_keys']]
                tally['histories'] += 1
                tally['prefix_references'] += len(runs)
                tally['all_prefixes_solved'] += all(r['status'] == 'solved' for r in runs)
                tally['all_prefixes_audited'] += all(r['audit_passed'] for r in runs)
                tally['all_prefixes_commitments_verified_safe'] += all(
                    r['initial_oracle_status'] == 'sat' and not r['oracle_unknown']
                    and not r['first_bad_commitment_found'] for r in runs)
    summary['histories'] = {k: dict(v) for k, v in history_stats.items()}
    summary['all_audits_passed'] = all(r['audit_passed'] for row in records for r in row['runs'])
    return summary


def execute(manifest_path, output, checkpoint_dir):
    """Save every scene exactly once and preserve evidence on an audit error."""
    require(not output.exists() and not checkpoint_dir.exists(), 'use new output/checkpoint names')
    manifest = read_report(manifest_path)
    manifest_hash = file_hash(manifest_path)
    validate_manifest(manifest)
    require(len(manifest['records']) == manifest['counts']['drawings'], 'wrong drawing count')
    require(len({r['key'] for r in manifest['records']}) == len(manifest['records']), 'duplicate drawings')
    checkpoint_dir.mkdir(parents=True, exist_ok=False)
    records, parts = [], []
    limits, start = manifest['resources'], perf_counter()
    provenance = {'manifest_path': manifest_path.resolve().relative_to(ROOT).as_posix(),
                  'manifest_sha256': manifest_hash, 'resources': limits,
                  'checkpoint_directory': checkpoint_dir.resolve().relative_to(ROOT).as_posix()}
    with ProcessPoolExecutor(max_workers=limits['workers']) as pool:
        for offset in range(0, len(manifest['records']), limits['batch_size']):
            batch = manifest['records'][offset:offset + limits['batch_size']]
            try:
                results = list(pool.map(run_record, [(r, limits) for r in batch]))
            except Exception as error:
                write_report(checkpoint_dir / 'failure.json', {**provenance, 'status': 'incomplete', 'offset': offset,
                             'input_keys': [r['key'] for r in batch], 'error': str(error)})
                raise
            failures = [r for r in results if r.get('failed')]
            if failures:
                write_report(checkpoint_dir / 'failure.json', {**provenance, 'status': 'incomplete', 'offset': offset,
                             'completed_drawings': len(records), 'batch_results': results})
                raise AssertionError('scene audit failed: ' + failures[0]['error'])
            require([r['key'] for r in results] == [r['key'] for r in batch], 'worker coverage differs')
            part = checkpoint_dir / f'part-{len(parts):05d}.json.gz'
            write_report(part, results)
            parts.append({'filename': part.name, 'sha256': file_hash(part), 'drawings': len(results)})
            records.extend({k: v for k, v in row.items() if k != 'runs'} |
                           {'checkpoint': part.name, 'runs': [compact_run(r) for r in row['runs']]}
                           for row in results)
            if len(parts) % 4 == 0 or len(records) == len(manifest['records']):
                print(json.dumps({'checked_drawings': len(records), 'total': len(manifest['records'])}), flush=True)
    require(file_hash(manifest_path) == manifest_hash and manifest['source_sha256'] == sources(),
            'manifest or sources changed during execution')
    require(all(file_hash(ROOT / n) == h for n, h in manifest['input_artifact_sha256'].items()),
            'input artifact changed during execution')
    require(sum(len(r['runs']) for r in records) == manifest['counts']['policy_runs'], 'missing policy runs')
    summary = summarize(records, manifest)
    report = {'schema_version': 1, **provenance, 'manifest_filename': manifest_path.name,
              'manifest_sha256': manifest_hash, 'source_sha256': manifest['source_sha256'],
              'counts': manifest['counts'], 'records': records, 'checkpoint_hashes': parts,
              'summary': summary, 'wall_seconds_before_final_write': perf_counter() - start,
              'scope': manifest['scope']}
    write_report(output, report)
    return {'counts': report['counts'], 'summary': summary}


def main():
    """Expose freeze, formal run and raw drawing demonstration as separate actions."""
    parser = ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    prep = subs.add_parser('prepare')
    prep.add_argument('--manifest', type=Path, required=True)
    run = subs.add_parser('run')
    run.add_argument('--manifest', type=Path, required=True)
    run.add_argument('--output', type=Path, required=True)
    run.add_argument('--checkpoint-dir', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.manifest) if args.command == 'prepare' else execute(
        args.manifest, args.output, args.checkpoint_dir)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()

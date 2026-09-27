"""Freeze and compare all-candidate refutation with the unchanged odd-EQ policy.

Both producers finish before offline auditing. Full traces live in individual
checkpoints; only compact measurements are accumulated to bound runner memory.
Every old geometry exclusion and every declared fresh prefix remains visible.
"""

from argparse import ArgumentParser
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_quaternary_all_candidate import audit_all_candidates, check_all_candidate_artifacts
from scripts.audit_quaternary_odd_cycle_eq import audit_odd_cycle_eq, check_odd_cycle_eq_artifacts
from scripts.check_quaternary_reachability import checksum
from scripts.check_quaternary_reachability_artifacts import same
from scripts.quaternary_all_candidate_inputs import build_all_candidate_holdout
from scripts.quaternary_all_candidate_low_color import solve_all_candidate_low_color
from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.quaternary_odd_cycle_eq_low_color import solve_odd_cycle_eq
from scripts.validate_global_restart import digest, export_geometries, write_report
from scripts.validate_quaternary_contacts_v2 import read_report
from scripts.validate_quaternary_candidate_scan import sources as previous_sources
from scripts.validate_quaternary_odd_cycle_eq import classify, quality, comparison

VERSION = 'quaternary-all-candidate-experiment-v1'
ARCHIVE = 'outputs/quaternary-odd-cycle-eq-manifest-2026-09-24.json.gz'
ARCHIVE_REPORT = 'outputs/quaternary-odd-cycle-eq-2026-09-24.json.gz'
SCAN_MANIFEST = 'outputs/quaternary-candidate-scan-manifest-2026-09-24.json.gz'
INPUT_PATHS = (ARCHIVE, ARCHIVE_REPORT, SCAN_MANIFEST)
PROTOCOL = 'docs/QUATERNARY_ALL_CANDIDATE_PROTOCOL-2026-09-26.md'
POLICIES = ('odd-cycle-eq', 'all-candidate')
RESOURCES = {'face_limit': 40, 'decision_limit': 128, 'probe_limit': 8192,
             'assignment_limit': 262144, 'node_limit': 200000}
NEW_SOURCES = ('scripts/quaternary_all_candidate_low_color.py',
               'tests/test_quaternary_all_candidate_low_color.py',
               'scripts/audit_quaternary_all_candidate.py',
               'tests/test_audit_quaternary_all_candidate.py',
               'scripts/quaternary_all_candidate_inputs.py',
               'tests/test_quaternary_all_candidate_inputs.py',
               'scripts/validate_quaternary_all_candidate.py',
               'tests/test_validate_quaternary_all_candidate.py', PROTOCOL)


def require(condition, message):
    """Scientific integrity checks must also run under Python optimization."""
    if not condition:
        raise AssertionError(message)


def sources():
    """Bind the complete frozen 177-source chain before extending it."""
    hashes = previous_sources()
    same(hashes, read_report(ROOT / SCAN_MANIFEST)['source_sha256'], 'old source chain changed')
    hashes.update({name: checksum(ROOT / name) for name in NEW_SOURCES})
    return hashes


def inventory():
    """Deduplicate literal drawings without concealing overlapping populations."""
    old, report = read_report(ROOT / ARCHIVE), read_report(ROOT / ARCHIVE_REPORT)
    same(report['manifest_sha256'], checksum(ROOT / ARCHIVE), 'archive binding differs')
    require(len(old['records']) == len(report['checkpoints']), 'archive coverage differs')
    records, by_key = [], {}
    for previous, reference in zip(old['records'], report['checkpoints']):
        original = previous['original']
        row = {'key': previous['key'], 'kind': original['kind'], 'document': original['document'],
               'populations': ['regression-odd'], 'new_key_against_archives': False,
               'prior_record': previous, 'archive_reference': reference}
        records.append(row)
        by_key[row['key']] = row
    holdout = build_all_candidate_holdout()
    for generated in holdout['records']:
        key = generated['key']
        if key not in by_key:
            row = {'key': key, 'kind': 'geometry', 'document': generated['document'],
                   'populations': [], 'new_key_against_archives': True}
            records.append(row)
            by_key[key] = row
        row = by_key[key]
        same(row['document'], generated['document'], 'drawing key collision')
        row['populations'].append('fresh-declared')
        row['holdout_metadata'] = generated
    return {'records': records, 'holdout': holdout,
            'regression_histories': [*old['inventory']['regression_histories'],
                                     *old['inventory']['holdout']['histories']]}


def inventory_counts(rows, chosen):
    """Report drawing counts separately from correlated prefix references."""
    scenes = sum(len(r['scenarios']) for r in rows)
    return {'records': len(rows), 'geometry_records': sum(r['original']['kind'] == 'geometry' for r in rows),
            'eligibility': dict(Counter(r['eligibility'] for r in rows)),
            'paired_scenarios': scenes, 'policy_runs': 2 * scenes,
            'holdout_drawings': len(chosen['holdout']['records']),
            'new_keys': sum(r['original']['new_key_against_archives'] for r in rows),
            'holdout_histories': len(chosen['holdout']['histories']),
            'holdout_prefix_references': sum(len(h['prefix_keys']) for h in chosen['holdout']['histories'])}


def prepare(path):
    """Freeze sources, inputs, geometry and common limits before either policy."""
    require(not path.exists(), 'manifest exists; choose another name')
    hashes, chosen = sources(), inventory()
    inputs = {name: checksum(ROOT / name) for name in INPUT_PATHS}
    needs_export = [r for r in chosen['records'] if r['kind'] == 'geometry' and 'prior_record' not in r]
    exports = export_geometries(needs_export)
    require(len(exports) == len(needs_export), 'missing geometry export')
    by_key = {r['key']: e for r, e in zip(needs_export, exports)}
    rows = [classify(r, r['prior_record']['export'] if 'prior_record' in r else by_key.get(r['key']))
            for r in chosen['records']]
    same(hashes, sources(), 'source drift during preparation')
    same(inputs, {name: checksum(ROOT / name) for name in INPUT_PATHS}, 'archive drift')
    manifest = {'schema_version': 1, 'version': VERSION, 'source_sha256': hashes,
                'input_sha256': inputs, 'inventory': chosen, 'records': rows,
                'resources': RESOURCES, 'policies': list(POLICIES),
                'counts': inventory_counts(rows, chosen),
                'created_at_utc': datetime.now(timezone.utc).isoformat(),
                'producer_runs_during_prepare': 0, 'oracle_runs_during_prepare': 0}
    write_report(path, manifest)
    return manifest['counts']


def bound_manifest(path):
    """Reconstruct the full declared census and admission without coloring."""
    manifest = read_report(path)
    same([manifest['schema_version'], manifest['version']], [1, VERSION], 'manifest version differs')
    same(manifest['source_sha256'], sources(), 'source drift after freeze')
    same(manifest['input_sha256'], {n: checksum(ROOT / n) for n in INPUT_PATHS}, 'archive drift')
    same(manifest['inventory'], inventory(), 'input inventory drift')
    same(manifest['resources'], RESOURCES, 'resource drift')
    same(manifest['policies'], list(POLICIES), 'policy drift')
    require(len(manifest['records']) == len(manifest['inventory']['records']), 'drawing coverage differs')
    for row, original in zip(manifest['records'], manifest['inventory']['records']):
        same(row, classify(original, row['export']), 'admission differs')
    same(manifest['counts'], inventory_counts(manifest['records'], manifest['inventory']), 'counts differ')
    same([manifest['producer_runs_during_prepare'], manifest['oracle_runs_during_prepare']], [0, 0],
         'freeze contract differs')
    return manifest


def archived_baseline(row, scenario, envelope):
    """Only the declared budget is normalized when checking old trace identity."""
    reference = row['original'].get('archive_reference')
    if reference is None:
        return None
    path = (ROOT / reference['path']).resolve()
    require(path.is_relative_to(ROOT / 'outputs'), 'old artifact outside outputs')
    same(checksum(path), reference['sha256'], 'old checkpoint bytes changed')
    stored = read_report(path)
    same(stored['manifest_sha256'], checksum(ROOT / ARCHIVE), 'old checkpoint freeze differs')
    same(stored['record_sha256'], digest(row['original']['prior_record']), 'old input differs')
    old = next(r['result'] for r in stored['row']['runs']
               if r['scenario'] == scenario and r['policy'] == 'odd-cycle-eq')
    normalized = deepcopy(envelope)
    normalized['run']['probe_limit'] = old['run']['probe_limit']
    same(normalized, old, 'baseline behavior changed beyond declared budget')
    return {'matches_after_budget_normalization': True, 'old_probe_limit': old['run']['probe_limit'],
            'new_probe_limit': envelope['run']['probe_limit'], 'archived_envelope_sha256': digest(old)}


def run_record(row):
    """Retain failed runs; do not audit until both producers have finished."""
    saved = {'key': row['key'], 'eligibility': row['eligibility'], 'runs': []}
    if row['eligibility'] != 'ready':
        return saved
    geometry = row['export']['geometry'] if row['original']['kind'] == 'geometry' else None
    for scenario in row['scenarios']:
        adapted = (adapt_exported_geometry(geometry, anchors=scenario['anchors'],
                   drawing=row['original']['document']) if geometry is not None else None)
        raw = adapted['contact_document'] if adapted else row['original']['document']
        pair = []
        for policy in POLICIES:
            entry = {'scenario': scenario['id'], 'policy': policy, 'raw_document': raw,
                     'adapted': adapted, 'execution': 'producer_error'}
            pair.append(entry)
            saved['runs'].append(entry)
            start = perf_counter()
            try:
                producer = solve_odd_cycle_eq if policy == POLICIES[0] else solve_all_candidate_low_color
                entry['result'] = producer(raw, geometry=geometry, decision_limit=RESOURCES['decision_limit'],
                                           probe_limit=RESOURCES['probe_limit'])
                entry['execution'] = 'produced'
            except Exception as error:
                entry['error'] = f'{type(error).__name__}: {error}'
            entry['producer_seconds'] = perf_counter() - start
        for entry in pair:
            if entry['execution'] != 'produced':
                continue
            start = perf_counter()
            try:
                auditor = audit_odd_cycle_eq if entry['policy'] == POLICIES[0] else audit_all_candidates
                entry['audit'] = auditor(raw, entry['result'], geometry=geometry, adapted=adapted,
                    assignment_limit=RESOURCES['assignment_limit'], node_limit=RESOURCES['node_limit'])
                if entry['policy'] == POLICIES[0]:
                    entry['archived_baseline'] = archived_baseline(row, scenario['id'], entry['result'])
                entry['execution'] = 'audited'
            except Exception as error:
                entry['execution'] = 'audit_error'
                entry['error'] = f'{type(error).__name__}: {error}'
            entry['audit_seconds'] = perf_counter() - start
    return saved


def compact_row(row):
    """Keep auditable measurements, with full evidence in the bound checkpoint."""
    result = {'key': row['key'], 'eligibility': row['eligibility'], 'runs': []}
    for entry in row['runs']:
        data = {k: entry[k] for k in ('scenario', 'policy', 'execution', 'producer_seconds')}
        data.update(quality=quality(entry), audit_seconds=entry.get('audit_seconds', 0))
        if 'error' in entry:
            data['error'] = entry['error']
        if entry['execution'] == 'audited':
            run, audit = entry['result']['run'], entry['audit']
            data.update(status=run['status'], choices=run['choices'], probes=run['probes'],
                rejections=run['rejections'], phases=len(run['phases']),
                trace_steps=audit['trace_steps_checked'], commitments=audit['commitment_counts'],
                probe_counts=audit.get('probe_counts', {}), rejection_counts=audit['rejection_counts'],
                oracle_statuses=dict(Counter(r['result']['status'] for r in audit['oracle_records'])),
                enumeration=audit['full_enumeration'],
                commit_sequence=[[e['side'], e['symbol']] for e in run['events'] if e['kind'] == 'commit'],
                rejected_candidates=[[e['side'], e['symbol'], e['before_phase']]
                                     for e in run['events'] if e['kind'] == 'reject'],
                final_colors=run['colors'], archived_baseline=entry.get('archived_baseline'))
        result['runs'].append(data)
    return result


def summarize(rows, manifest):
    """Separate proof integrity, completion, actual commitments and trial costs."""
    originals = {r['key']: r['original'] for r in manifest['records']}
    populations = sorted({p for r in originals.values() for p in r['populations']})
    groups, pairs = {}, []
    for population in ['all-records', *populations]:
        for policy in POLICIES:
            selected = [e for row in rows if population == 'all-records'
                        or population in originals[row['key']]['populations']
                        for e in row['runs'] if e['policy'] == policy]
            total = {'runs': len(selected), 'qualities': dict(Counter(e['quality'] for e in selected))}
            audited = [e for e in selected if e['execution'] == 'audited']
            total['audited'] = len(audited)
            for field in ('choices', 'probes', 'rejections', 'phases', 'trace_steps', 'producer_seconds', 'audit_seconds'):
                total[field] = sum(e.get(field, 0) for e in selected)
            total['max_probes_per_run'] = max((e['probes'] for e in audited), default=0)
            for field in ('commitments', 'probe_counts', 'rejection_counts', 'oracle_statuses'):
                combined = Counter()
                for entry in audited:
                    combined.update(entry[field])
                total[field] = dict(combined)
            total['enumeration'] = dict(Counter(e['enumeration']['status'] for e in audited))
            groups[population + '/' + policy] = total
    for row in rows:
        for scene in sorted({e['scenario'] for e in row['runs']}):
            a, b = [next(e for e in row['runs'] if e['scenario'] == scene and e['policy'] == p) for p in POLICIES]
            qa, qb = a['quality'], b['quality']
            category = ('unresolved_or_initial_unsat' if any(q in ('uncompleted', 'unknown', 'initial_unsat') for q in (qa, qb))
                        else 'both_success' if qa == qb == 'success' else 'repair' if qb == 'success'
                        else 'regression' if qa == 'success' else 'persistent_failure')
            item = {'key': row['key'], 'scenario': scene, 'comparison': category,
                    'populations': originals[row['key']]['populations']}
            if a['execution'] == b['execution'] == 'audited':
                item.update(choice_difference=b['choices'] - a['choices'], probe_difference=b['probes'] - a['probes'],
                    same_commit_sequence=a['commit_sequence'] == b['commit_sequence'],
                    same_final_colors=a['final_colors'] == b['final_colors'],
                    all_candidate_rejections=b['rejected_candidates'])
            pairs.append(item)
    lookup = {row['key']: row for row in rows}
    histories = []
    for population, collection in [('fresh-declared', manifest['inventory']['holdout']['histories']),
                                   ('regression-odd', manifest['inventory']['regression_histories'])]:
        for history in collection:
            for scenario in ('one-bounded-anchor', 'legacy-frame-anchors'):
                for policy in POLICIES:
                    statuses = [next(e['quality'] for e in lookup[k]['runs'] if e['scenario'] == scenario and e['policy'] == policy)
                                if lookup[k]['eligibility'] == 'ready' else lookup[k]['eligibility'] for k in history['prefix_keys']]
                    histories.append({'population': population, 'id': history['id'], 'scenario': scenario,
                        'policy': policy, 'qualities': statuses,
                        'all_declared_prefixes_successful': all(s == 'success' for s in statuses)})
    return {'groups': groups, 'paired': pairs, 'comparison_counts': dict(Counter(p['comparison'] for p in pairs)),
            'histories': histories, 'eligibility': dict(Counter(r['eligibility'] for r in rows)),
            'compact_records': rows,
            'scope': 'Correlated prefixes; every prefix restarts. Finite paired evidence, not completeness or speed proof.'}


def execute(manifest_path, output):
    """Exclusive per-map checkpoints allow interruption without rerunning old maps."""
    require(not output.exists(), 'result exists; use a unique name')
    manifest, references, rows = bound_manifest(manifest_path), [], []
    manifest_hash = checksum(manifest_path)
    directory = output.parent / (output.name.removesuffix('.json.gz') + '-checkpoints')
    directory.mkdir(parents=True, exist_ok=True)
    for number, record in enumerate(manifest['records']):
        path = directory / f'{number:03d}-{record["key"][:12]}.json.gz'
        if path.exists():
            stored = read_report(path)
            same(stored['manifest_sha256'], manifest_hash, 'checkpoint freeze differs')
            same(stored['record_sha256'], digest(record), 'checkpoint input differs')
            row = stored['row']
        else:
            row = run_record(record)
            write_report(path, {'manifest_sha256': manifest_hash, 'record_sha256': digest(record), 'row': row})
        rows.append(compact_row(row))
        references.append({'path': path.relative_to(ROOT).as_posix(), 'sha256': checksum(path)})
        print(json.dumps({'completed': number + 1, 'total': len(manifest['records']),
                          'qualities': [e['quality'] for e in rows[-1]['runs']]}, ensure_ascii=False), flush=True)
    same(manifest['source_sha256'], sources(), 'source drift during production')
    report = {'schema_version': 1, 'version': VERSION, 'manifest_sha256': manifest_hash,
              'checkpoints': references, 'summary': summarize(rows, manifest)}
    write_report(output, report)
    return report['summary']['groups']


def check(manifest_path, report_path, output):
    """Recheck all saved traces and exact certificates, with no new search."""
    require(not output.exists(), 'check output exists; use a unique name')
    manifest, report = bound_manifest(manifest_path), read_report(report_path)
    same([report['schema_version'], report['version']], [1, VERSION], 'report version differs')
    same(report['manifest_sha256'], checksum(manifest_path), 'report freeze differs')
    require(len(report['checkpoints']) == len(manifest['records']), 'checkpoint coverage differs')
    rows, counts = [], Counter()
    for reference, record in zip(report['checkpoints'], manifest['records']):
        path = (ROOT / reference['path']).resolve()
        require(path.is_relative_to(ROOT / 'outputs'), 'checkpoint outside outputs')
        same(checksum(path), reference['sha256'], 'checkpoint bytes changed')
        saved = read_report(path)
        same(saved['manifest_sha256'], checksum(manifest_path), 'checkpoint freeze differs')
        same(saved['record_sha256'], digest(record), 'checkpoint input differs')
        row = saved['row']
        same([row['key'], row['eligibility']], [record['key'], record['eligibility']], 'record identity differs')
        same([(e['scenario'], e['policy']) for e in row['runs']],
             [(s['id'], p) for s in record['scenarios'] for p in POLICIES], 'policy coverage differs')
        geometry = record['export']['geometry'] if record['original']['kind'] == 'geometry' and record['eligibility'] == 'ready' else None
        for entry in row['runs']:
            counts['runs'] += 1
            if entry['execution'] != 'audited':
                counts['incomplete_executions'] += 1
                continue
            scene = next(s for s in record['scenarios'] if s['id'] == entry['scenario'])
            adapted = (adapt_exported_geometry(geometry, anchors=scene['anchors'], drawing=record['original']['document'])
                       if geometry is not None else None)
            raw = adapted['contact_document'] if adapted else record['original']['document']
            same(entry['raw_document'], raw, 'raw query input differs')
            same(entry['adapted'], adapted, 'adapter differs')
            checker = check_odd_cycle_eq_artifacts if entry['policy'] == POLICIES[0] else check_all_candidate_artifacts
            checker(raw, entry['result'], entry['audit'], RESOURCES, geometry=geometry, adapted=adapted)
            if entry['policy'] == POLICIES[0]:
                same(entry['archived_baseline'], archived_baseline(record, scene['id'], entry['result']), 'old comparison differs')
            counts['audited_runs'] += 1
            counts['oracle_records'] += len(entry['audit']['oracle_records'])
            counts['oracle_unknown'] += entry['audit']['oracle_unknown']
            counts['phases'] += entry['audit']['phase_count']
            counts['unsafe_commitments'] += entry['audit']['commitment_counts']['unsafe']
        rows.append(compact_row(row))
    same(report['summary'], summarize(rows, manifest), 'summary reconstruction differs')
    same(manifest['source_sha256'], sources(), 'source drift during check')
    result = {'passed': True, 'eligible_executions_complete': counts['incomplete_executions'] == 0,
              'exact_queries_conclusive': counts['incomplete_executions'] == 0 and counts['oracle_unknown'] == 0,
              'counts': dict(counts), 'source_sha256': sources(),
              'manifest_sha256': checksum(manifest_path), 'report_sha256': checksum(report_path),
              'producer_reruns': 0, 'oracle_search_reruns': 0, 'propagation_reruns': 0}
    write_report(output, result)
    return result['counts']


def main():
    """Expose separate freezing, paired execution, and certificate replay."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'run', 'check'))
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        answer = prepare(args.manifest.resolve())
    else:
        require(args.output is not None, '--output required')
        if args.command == 'run':
            answer = execute(args.manifest.resolve(), args.output.resolve())
        else:
            require(args.report is not None, '--report required')
            answer = check(args.manifest.resolve(), args.report.resolve(), args.output.resolve())
    print(json.dumps(answer, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

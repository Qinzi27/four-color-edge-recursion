"""Freeze and compare conditional triangle saturation with the diamond policy.

Both producers finish before offline auditing. Full traces live in individual
checkpoints; only compact measurements are accumulated to bound runner memory.
Every old geometry exclusion and every declared fresh prefix remains visible.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_quaternary_conditional_diamond import audit_conditional_diamond, check_conditional_diamond_artifacts
from scripts.audit_quaternary_triangle_saturation import audit_triangle_saturation, check_triangle_saturation_artifacts
from scripts.check_quaternary_reachability import checksum
from scripts.check_quaternary_reachability_artifacts import same
from scripts.check_triangle_saturation_rule_soundness import (
    rule_inventory, check_rule_soundness, check_saved_rule_soundness,
)
from scripts.quaternary_triangle_saturation_inputs import build_triangle_saturation_holdout
from scripts.quaternary_conditional_diamond_low_color import solve_conditional_diamond
from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.quaternary_triangle_saturation_low_color import solve_triangle_saturation
from scripts.validate_global_restart import digest, export_geometries, write_report
from scripts.validate_quaternary_contacts_v2 import read_report
from scripts.validate_quaternary_conditional_diamond import sources as previous_sources
from scripts.quaternary_triangle_saturation_gap_check import gap_inventory, run_gaps, check_saved_gaps, phase_metrics
from scripts.validate_quaternary_odd_cycle_eq import classify, quality

VERSION = 'quaternary-triangle-saturation-experiment-v1'
ARCHIVE = 'outputs/quaternary-conditional-diamond-manifest-2026-09-30.json.gz'
ARCHIVE_REPORT = 'outputs/quaternary-conditional-diamond-2026-09-30.json.gz'
PAIR_MANIFEST = 'outputs/quaternary-logical-neq-pair-scan-manifest-2026-09-29.json.gz'
PAIR_REPORT = 'outputs/quaternary-logical-neq-pair-scan-2026-09-29.json.gz'
PAIR_CHECK = 'outputs/quaternary-logical-neq-pair-scan-check-2026-09-29.json'
ARCHIVE_CHECK = 'outputs/quaternary-conditional-diamond-artifact-check-2026-09-30.json'
INPUT_PATHS = (ARCHIVE, ARCHIVE_REPORT, ARCHIVE_CHECK, PAIR_MANIFEST, PAIR_REPORT, PAIR_CHECK)
PROTOCOL = 'docs/QUATERNARY_TRIANGLE_SATURATION_PROTOCOL-2026-10-01.md'
POLICIES = ('conditional-diamond', 'triangle-saturation')
RESOURCES = {'face_limit': 40, 'decision_limit': 128, 'probe_limit': 8192,
             'assignment_limit': 262144, 'node_limit': 200000}
NEW_SOURCES = ('scripts/quaternary_triangle_saturation.py',
               'scripts/quaternary_triangle_saturation_contacts.py',
               'scripts/quaternary_triangle_saturation_low_color.py',
               'tests/test_quaternary_triangle_saturation.py',
               'tests/test_quaternary_triangle_saturation_contacts.py',
               'tests/test_quaternary_triangle_saturation_low_color.py',
               'scripts/check_quaternary_triangle_saturation.py',
               'scripts/audit_quaternary_triangle_saturation.py',
               'tests/test_check_quaternary_triangle_saturation.py',
               'tests/test_audit_quaternary_triangle_saturation.py',
               'scripts/check_triangle_saturation_rule_soundness.py',
               'tests/test_triangle_saturation_rule_soundness.py',
               'scripts/quaternary_triangle_saturation_inputs.py',
               'tests/test_quaternary_triangle_saturation_inputs.py',
               'scripts/quaternary_triangle_saturation_gap_check.py',
               'tests/test_quaternary_triangle_saturation_gap_check.py',
               'scripts/validate_quaternary_triangle_saturation.py',
               'tests/test_validate_quaternary_triangle_saturation.py', PROTOCOL)


def require(condition, message):
    """Scientific integrity checks must also run under Python optimization."""
    if not condition:
        raise AssertionError(message)


def sources():
    """Bind the complete frozen 253-source chain before extending it."""
    hashes = previous_sources()
    same(hashes, read_report(ROOT / ARCHIVE)['source_sha256'], 'old source chain changed')
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
               'populations': ['regression-conditional-diamond'], 'new_key_against_archives': False,
               'prior_record': previous, 'archive_reference': reference}
        records.append(row)
        require(row['key'] not in by_key, 'duplicate archived input key')
        by_key[row['key']] = row
    holdout = build_triangle_saturation_holdout()
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
        row['populations'].append('fresh-new-key' if row['new_key_against_archives']
                                  else 'fresh-overlap')
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
            'fresh_new_key_scenarios': sum(len(r['scenarios']) for r in rows
                                           if 'fresh-new-key' in r['original']['populations']),
            'fresh_overlap_records': sum('fresh-overlap' in r['original']['populations'] for r in rows),
            'fresh_overlap_scenarios': sum(len(r['scenarios']) for r in rows
                                           if 'fresh-overlap' in r['original']['populations']),
            'holdout_histories': len(chosen['holdout']['histories']),
            'holdout_prefix_references': sum(len(h['prefix_keys']) for h in chosen['holdout']['histories'])}


def rule_declaration():
    """Freeze the literal rule inputs without learning or coloring them."""
    declared = rule_inventory()
    return {'inventory': declared, 'inventory_sha256': digest(declared),
            'production_oracle_or_propagation_performed': False}


def prepare(path):
    """Freeze sources, inputs, geometry and common limits before either policy."""
    require(not path.exists(), 'manifest exists; choose another name')
    hashes, chosen, rules = sources(), inventory(), rule_declaration()
    gaps = gap_inventory()
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
                'rule_declaration': rules, 'gap_inventory': gaps,
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
    same(manifest['rule_declaration'], rule_declaration(), 'rule declaration drift')
    same(manifest['gap_inventory'], gap_inventory(), 'old diagnostic targets drift')
    require(len(manifest['records']) == len(manifest['inventory']['records']), 'drawing coverage differs')
    for row, original in zip(manifest['records'], manifest['inventory']['records']):
        same(row, classify(original, row['export']), 'admission differs')
    same(manifest['counts'], inventory_counts(manifest['records'], manifest['inventory']), 'counts differ')
    same([manifest['producer_runs_during_prepare'], manifest['oracle_runs_during_prepare']], [0, 0],
         'freeze contract differs')
    return manifest


def archived_baseline(row, scenario, envelope):
    """The old budget already matches; require complete envelope identity."""
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
               if r['scenario'] == scenario and r['policy'] == 'conditional-diamond')
    same(envelope, old, 'baseline envelope changed')
    return {'matches_exactly': True, 'old_probe_limit': old['run']['probe_limit'],
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
                producer = solve_conditional_diamond if policy == POLICIES[0] else solve_triangle_saturation
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
                auditor = audit_conditional_diamond if entry['policy'] == POLICIES[0] else audit_triangle_saturation
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
            learning = entry['result']['learning']
            equalities = learning['equalities']
            inequalities = learning['inequalities']
            initial = run['phases'][0]['outcome']
            data.update(status=run['status'], choices=run['choices'], probes=run['probes'],
                rejections=run['rejections'], phases=len(run['phases']),
                trace_steps=audit['trace_steps_checked'], commitments=audit['commitment_counts'],
                probe_counts=audit.get('probe_counts', {}), rejection_counts=audit['rejection_counts'],
                oracle_statuses=dict(Counter(r['result']['status'] for r in audit['oracle_records'])),
                enumeration=audit['full_enumeration'],
                commit_sequence=[[e['side'], e['symbol']] for e in run['events'] if e['kind'] == 'commit'],
                rejected_candidates=[[e['side'], e['symbol'], e['before_phase']]
                                     for e in run['events'] if e['kind'] == 'reject'],
                final_colors=run['colors'], archived_baseline=entry.get('archived_baseline'),
                events_sha256=digest(run['events']),
                logical_eq_pair_count=len(equalities['equal_names']),
                logical_neq_pair_count=len(inequalities['different_names']) if inequalities else 0,
                logical_neq_query_count=len(inequalities['queries']) if inequalities else 0,
                logical_neq_certificate_checks=audit.get('logical_neq_check', {}).get('query_count', 0),
                logical_neq_forced_merges_checked=audit.get('logical_neq_check', {}).get('forced_merges_checked', 0),
                logical_neq_learning_stats=inequalities['stats'] if inequalities else {},
                oracle_record_count=len(audit['oracle_records']),
                oracle_nodes=sum(record['result']['nodes'] for record in audit['oracle_records']),
                initial_side_order=initial['side_order'], initial_domains=initial['domains'],
                initial_candidate_count=sum(len(values) for values in initial['domains']),
                propagation_rounds=0)
            for phase in run['phases']:
                for metric, value in phase_metrics(phase['outcome']).items():
                    data[metric] = data.get(metric, 0) + value
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
            for field in ('choices', 'probes', 'rejections', 'phases', 'trace_steps', 'producer_seconds',
                          'audit_seconds', 'logical_eq_pair_count', 'logical_neq_pair_count',
                          'logical_neq_query_count', 'logical_neq_certificate_checks',
                          'logical_neq_forced_merges_checked', 'oracle_record_count', 'oracle_nodes',
                          'initial_candidate_count', 'wheel_checks', 'wheel_conflicts', 'wheel_edges_examined',
                          'propagation_rounds', 'conditional_eq_pairs', 'diamond_checks', 'diamond_certificates',
                          'diamond_pairs_examined', 'diamond_pairs_with_offdiagonal', 'diamond_palettes_examined',
                          'diamond_common_edges_examined', 'diamond_certificates_found',
                          'saturation_rounds', 'saturation_added_rounds', 'saturation_removed_candidates',
                          'triangle_checks', 'triangle_certificates', 'triangle_classes_examined',
                          'triangle_palettes_examined', 'triangle_triangles_examined',
                          'triangle_physical_witness_edges', 'triangle_certificates_found'):
                total[field] = sum(e.get(field, 0) for e in selected)
            total['max_probes_per_run'] = max((e['probes'] for e in audited), default=0)
            for field in ('commitments', 'probe_counts', 'rejection_counts', 'oracle_statuses'):
                combined = Counter()
                for entry in audited:
                    combined.update(entry[field])
                total[field] = dict(combined)
            total['enumeration'] = dict(Counter(e['enumeration']['status'] for e in audited))
            total['runs_with_logical_neq'] = sum(e['logical_neq_pair_count'] > 0 for e in audited)
            enumeration_totals = Counter()
            for entry in audited:
                if entry['enumeration']['status'] == 'run':
                    for field in ('literal_assignments_checked', 'initial_legal_assignments',
                                  'phase_checks', 'legal_assignments_preserved'):
                        enumeration_totals[field] += entry['enumeration'][field]
            total['enumeration_totals'] = dict(enumeration_totals)
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
                same(a['initial_side_order'], b['initial_side_order'], 'paired initial side order differs')
                removed = [[side, name] for side, old, new in zip(
                    a['initial_side_order'], a['initial_domains'], b['initial_domains'])
                    for name in sorted(set(old) - set(new))]
                added = [[side, name] for side, old, new in zip(
                    a['initial_side_order'], a['initial_domains'], b['initial_domains'])
                    for name in sorted(set(new) - set(old))]
                item.update(choice_difference=b['choices'] - a['choices'], probe_difference=b['probes'] - a['probes'],
                    same_commit_sequence=a['commit_sequence'] == b['commit_sequence'],
                    same_final_colors=a['final_colors'] == b['final_colors'],
                    same_events=a['events_sha256'] == b['events_sha256'],
                    new_policy_rejections=b['rejected_candidates'],
                    logical_neq_pair_count=b['logical_neq_pair_count'],
                    initial_removed_candidates=removed, initial_added_candidates=added,
                    initial_candidate_reduction=len(removed), initial_candidate_addition=len(added))
            pairs.append(item)
    lookup = {row['key']: row for row in rows}
    histories = []
    for population, collection in [('fresh-declared', manifest['inventory']['holdout']['histories']),
                                   ('regression-conditional-diamond', manifest['inventory']['regression_histories'])]:
        for history in collection:
            for scenario in ('one-bounded-anchor', 'legacy-frame-anchors'):
                for policy in POLICIES:
                    statuses = [next(e['quality'] for e in lookup[k]['runs'] if e['scenario'] == scenario and e['policy'] == policy)
                                if lookup[k]['eligibility'] == 'ready' else lookup[k]['eligibility'] for k in history['prefix_keys']]
                    histories.append({'population': population, 'id': history['id'], 'scenario': scenario,
                        'policy': policy, 'qualities': statuses,
                        'excluded_prefix_count': sum(lookup[k]['eligibility'] != 'ready'
                                                     for k in history['prefix_keys']),
                        'producer_uncompleted_prefix_count': statuses.count('uncompleted'),
                        'failed_prefix_count': sum(s in ('unsafe', 'conflict') for s in statuses),
                        'unknown_prefix_count': statuses.count('unknown'),
                        'all_declared_prefixes_successful': all(s == 'success' for s in statuses)})
    changes = {}
    for population in ['all-records', *populations]:
        selected = [p for p in pairs if population == 'all-records' or population in p['populations']]
        completed = [p for p in selected if 'initial_candidate_reduction' in p]
        changes[population] = {
            'paired_scenarios': len(selected), 'audited_pairs': len(completed),
            'initial_removed_candidate_references': sum(p['initial_candidate_reduction'] for p in completed),
            'initial_added_candidate_references': sum(p['initial_candidate_addition'] for p in completed),
            'pairs_with_initial_reduction': sum(p['initial_candidate_reduction'] > 0 for p in completed),
            'pairs_with_same_commit_sequence': sum(p['same_commit_sequence'] for p in completed),
            'pairs_with_same_final_colors': sum(p['same_final_colors'] for p in completed),
            'pairs_with_same_events': sum(p['same_events'] for p in completed),
            'comparison_counts': dict(Counter(p['comparison'] for p in selected)),
        }
    return {'groups': groups, 'paired': pairs, 'paired_changes': changes,
            'comparison_counts': dict(Counter(p['comparison'] for p in pairs)),
            'histories': histories, 'eligibility': dict(Counter(r['eligibility'] for r in rows)),
            'compact_records': rows,
            'scope': 'Correlated prefixes; every prefix restarts. Finite paired evidence, not completeness or speed proof.'}


def verify_rule_checkpoint(saved, manifest, manifest_hash):
    """Bind saved rule evidence to its predeclared raw graph inventory."""
    same(saved['manifest_sha256'], manifest_hash, 'rule checkpoint freeze differs')
    same(saved['rule_declaration_sha256'], digest(manifest['rule_declaration']),
         'rule checkpoint declaration differs')
    same(saved['result']['input_inventory_sha256'], manifest['rule_declaration']['inventory_sha256'],
         'rule evidence inventory differs')
    checked = check_saved_rule_soundness(saved['result'])
    require(checked['passed'] is True, 'saved rule evidence did not pass')
    return checked


def execute(manifest_path, output):
    """Exclusive per-map checkpoints allow interruption without rerunning old maps."""
    require(not output.exists(), 'result exists; use a unique name')
    manifest, references, rows = bound_manifest(manifest_path), [], []
    manifest_hash = checksum(manifest_path)
    directory = output.parent / (output.name.removesuffix('.json.gz') + '-checkpoints')
    directory.mkdir(parents=True, exist_ok=True)
    # The rule census is declared in prepare; learning on those inputs begins
    # only here. Resumption replays the saved result without another learner run.
    rule_path = directory / 'rule-soundness.json.gz'
    rule_exists = rule_path.exists()
    if rule_exists:
        saved_rule = read_report(rule_path)
    else:
        saved_rule = {'manifest_sha256': manifest_hash,
                      'rule_declaration_sha256': digest(manifest['rule_declaration']),
                      'result': check_rule_soundness()}
    rule_check = verify_rule_checkpoint(saved_rule, manifest, manifest_hash)
    if not rule_exists:
        write_report(rule_path, saved_rule)
    rule_reference = {'path': rule_path.relative_to(ROOT).as_posix(), 'sha256': checksum(rule_path)}
    print(json.dumps({'stage': 'rule-soundness', 'passed': rule_check['passed']}), flush=True)
    gap_path = directory / 'known-pair-gaps.json.gz'
    if gap_path.exists():
        saved_gaps = read_report(gap_path)
    else:
        saved_gaps = {'manifest_sha256': manifest_hash, 'result': run_gaps(manifest['gap_inventory'])}
        write_report(gap_path, saved_gaps)
    same(saved_gaps['manifest_sha256'], manifest_hash, 'gap checkpoint freeze differs')
    gap_check = check_saved_gaps(manifest['gap_inventory'], saved_gaps['result'])
    gap_reference = {'path': gap_path.relative_to(ROOT).as_posix(), 'sha256': checksum(gap_path)}
    print(json.dumps({'stage': 'known-pair-gaps', 'counts': gap_check['counts']}), flush=True)
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
              'rule_evidence': rule_reference, 'rule_evidence_check': rule_check,
              'gap_evidence': gap_reference, 'gap_evidence_check': gap_check,
              'checkpoints': references, 'summary': summarize(rows, manifest)}
    write_report(output, report)
    return report['summary']['groups']


def check(manifest_path, report_path, output):
    """Recheck all saved traces and exact certificates, with no new search."""
    require(not output.exists(), 'check output exists; use a unique name')
    manifest, report = bound_manifest(manifest_path), read_report(report_path)
    same([report['schema_version'], report['version']], [1, VERSION], 'report version differs')
    same(report['manifest_sha256'], checksum(manifest_path), 'report freeze differs')
    rule_path = (ROOT / report['rule_evidence']['path']).resolve()
    require(rule_path.is_relative_to(ROOT / 'outputs'), 'rule checkpoint outside outputs')
    same(checksum(rule_path), report['rule_evidence']['sha256'], 'rule checkpoint bytes changed')
    rule_check = verify_rule_checkpoint(read_report(rule_path), manifest, checksum(manifest_path))
    same(report['rule_evidence_check'], rule_check, 'rule check summary differs')
    gap_path = (ROOT / report['gap_evidence']['path']).resolve()
    require(gap_path.is_relative_to(ROOT / 'outputs'), 'gap checkpoint outside outputs')
    same(checksum(gap_path), report['gap_evidence']['sha256'], 'gap checkpoint bytes changed')
    saved_gaps = read_report(gap_path)
    same(saved_gaps['manifest_sha256'], checksum(manifest_path), 'gap checkpoint freeze differs')
    gap_check = check_saved_gaps(manifest['gap_inventory'], saved_gaps['result'])
    same(report['gap_evidence_check'], gap_check, 'gap check summary differs')
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
            checker = check_conditional_diamond_artifacts if entry['policy'] == POLICIES[0] else check_triangle_saturation_artifacts
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
              'diagnostic_executions_complete': gap_check['complete'],
              'counts': dict(counts), 'source_sha256': sources(),
              'rule_evidence_check': rule_check, 'gap_evidence_check': gap_check,
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

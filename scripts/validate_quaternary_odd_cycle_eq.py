"""Paired, frozen comparison of triangle EQ with certified common odd-cycle EQ.

All inputs and failed geometric admissions remain visible. New input generation
never consults colors; the two producers finish before either offline oracle.
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

from scripts.audit_quaternary_geometry import audit_geometry
from scripts.audit_quaternary_triangle_eq import audit_triangle_eq, check_triangle_eq_artifacts
from scripts.audit_quaternary_odd_cycle_eq import audit_odd_cycle_eq, check_odd_cycle_eq_artifacts
from scripts.check_quaternary_reachability import checksum
from scripts.check_quaternary_reachability_artifacts import same
from scripts.check_odd_cycle_eq_rule_soundness import check_rule_soundness
from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.quaternary_odd_cycle_eq_inputs import build_odd_cycle_holdout
from scripts.quaternary_triangle_eq_low_color import solve_triangle_eq
from scripts.quaternary_odd_cycle_eq_low_color import solve_odd_cycle_eq
from scripts.validate_global_restart import digest, export_geometries, write_report
from scripts.validate_quaternary_contacts_v2 import read_report
from scripts.validate_quaternary_geometry import standard_scenarios
from scripts.validate_quaternary_triangle_eq import sources as previous_sources

VERSION = 'quaternary-odd-cycle-eq-experiment-v1'
TRIANGLE_MANIFEST = 'outputs/quaternary-triangle-eq-manifest-2026-09-23.json.gz'
PROTOCOL = 'docs/QUATERNARY_ODD_CYCLE_EQ_PROTOCOL-2026-09-24.md'
INPUT_PATHS = (TRIANGLE_MANIFEST,)
POLICIES = ('triangle-eq', 'odd-cycle-eq')
RESOURCES = {'face_limit': 40, 'decision_limit': 128, 'probe_limit': 512,
             'assignment_limit': 262144, 'node_limit': 200000}
NEW_SOURCES = (
    'scripts/quaternary_odd_cycle_eq.py', 'tests/test_quaternary_odd_cycle_eq.py',
    'scripts/quaternary_odd_cycle_eq_low_color.py', 'tests/test_quaternary_odd_cycle_eq_low_color.py',
    'scripts/audit_quaternary_odd_cycle_eq.py', 'tests/test_quaternary_odd_cycle_eq_audit.py',
    'scripts/quaternary_odd_cycle_eq_inputs.py', 'tests/test_quaternary_odd_cycle_eq_inputs.py',
    'scripts/check_odd_cycle_eq_rule_soundness.py',
    'scripts/validate_quaternary_odd_cycle_eq.py', 'tests/test_validate_quaternary_odd_cycle_eq.py', PROTOCOL,
)


def require(condition, message):
    """Scientific validation cannot disappear with python -O."""
    if not condition:
        raise AssertionError(message)


def sources():
    """Verify every old frozen source before adding this separate version."""
    from scripts.quaternary_odd_cycle_eq_inputs import SOURCE_PATHS
    hashes = previous_sources()
    same(hashes, read_report(ROOT / TRIANGLE_MANIFEST)['source_sha256'], 'old source chain changed')
    hashes.update({name: checksum(ROOT / name) for name in set(NEW_SOURCES) | set(SOURCE_PATHS)})
    return hashes


def inventory():
    """Keep every old input/exclusion and label all new prefixes before coloring."""
    old = read_report(ROOT / TRIANGLE_MANIFEST)
    old_keys = {r['key'] for r in old['records']}
    holdout = build_odd_cycle_holdout()
    records, by_key = [], {}
    for previous in old['records']:
        original = previous['original']
        row = {'key': previous['key'], 'kind': original['kind'],
               'document': original['document'], 'populations': ['regression-triangle'],
               'new_key_against_archives': False, 'prior_record': previous}
        # Preserve the earlier population labels as provenance, not new samples.
        row['prior_populations'] = original['populations']
        records.append(row)
        by_key[row['key']] = row
    for generated in holdout['records']:
        key, document = generated['key'], generated['document']
        if key not in by_key:
            row = {'key': key, 'kind': 'geometry', 'document': document,
                   'populations': [], 'new_key_against_archives': key not in old_keys}
            records.append(row)
            by_key[key] = row
        row = by_key[key]
        same(row['document'], document, 'stroke-set digest collision')
        row['populations'].append('fresh-declared')
        row['holdout_metadata'] = generated
    return {'records': records, 'holdout': holdout,
            'regression_histories': [*old['inventory']['regression_histories'],
                                     *old['inventory']['holdout']['histories']],
            'known_geometry_keys': sum(r['original']['kind'] == 'geometry' for r in old['records']),
            'scope': 'New-key comparison uses the immediate triangle archive; '
                     'family/prefix overlap does not establish independent samples.'}


def classify(original, exported=None):
    """Geometry/size exclusions are explicit and never become color failures."""
    row = {'key': original['key'], 'original': original, 'export': exported,
           'eligibility': 'ready', 'scenarios': [], 'error': None}
    if original['kind'] == 'abstract':
        row['scenarios'] = [{'id': 'single-anchor-input-order',
                             'anchors': original['document']['anchors']}]
        return row
    prior = original.get('prior_record')
    if prior:
        same(exported, prior['export'], 'archived regression geometry export changed')
    if prior and prior['eligibility'] != 'ready':
        row['eligibility'], row['error'] = prior['eligibility'], prior['error']
        return row
    same(exported['key'], original['key'], 'geometry export changed key')
    if exported['status'] != 'geometry_ok':
        row['eligibility'], row['error'] = 'geometry_error', exported.get('errors')
        return row
    geometry = exported['geometry']
    row['geometry_sha256'] = digest(geometry)
    try:
        adapted = adapt_exported_geometry(geometry, drawing=original['document'])
        row['geometry_audit'], _ = audit_geometry(geometry, adapted)
        if len(geometry['faces']) > RESOURCES['face_limit']:
            row['eligibility'], row['error'] = 'face_budget_exceeded', 'more than forty faces'
        else:
            row['scenarios'] = standard_scenarios(geometry, {'extra_scenarios': []})
    except (ValueError, AssertionError, KeyError, TypeError) as error:
        row['eligibility'], row['error'] = 'geometry_audit_error', str(error)
    return row


def prepare(path):
    """Freeze exact input metadata, geometry and policies before comparison."""
    require(not path.exists(), 'manifest exists; choose a new name')
    hashes, chosen = sources(), inventory()
    input_hashes = {name: checksum(ROOT / name) for name in INPUT_PATHS}
    needs_export = [r for r in chosen['records'] if r['kind'] == 'geometry' and 'prior_record' not in r]
    exported = export_geometries(needs_export)
    require(len(exported) == len(needs_export), 'geometry export omitted an input')
    new_exports = {r['key']: value for r, value in zip(needs_export, exported)}
    rows = []
    for original in chosen['records']:
        value = (original['prior_record']['export'] if 'prior_record' in original
                 else new_exports.get(original['key']))
        rows.append(classify(original, value))
    same(hashes, sources(), 'source drift during freeze')
    same(input_hashes, {name: checksum(ROOT / name) for name in INPUT_PATHS}, 'input drift during freeze')
    counts = inventory_counts(rows, chosen)
    manifest = {'schema_version': 1, 'version': VERSION, 'source_sha256': hashes,
                'input_sha256': input_hashes, 'inventory': chosen, 'records': rows,
                'resources': RESOURCES, 'policies': list(POLICIES), 'counts': counts,
                'created_at_utc': datetime.now(timezone.utc).isoformat(),
                'producer_runs_during_prepare': 0, 'oracle_runs_during_prepare': 0}
    write_report(path, manifest)
    return counts


def inventory_counts(rows, chosen):
    """Reconstruct every declared coverage counter from the literal inventory."""
    return {'records': len(rows), 'geometry_records': sum(r['original']['kind'] == 'geometry' for r in rows),
              'eligibility': dict(Counter(r['eligibility'] for r in rows)),
              'paired_scenarios': sum(len(r['scenarios']) for r in rows),
              'policy_runs': 2 * sum(len(r['scenarios']) for r in rows),
              'holdout_drawings': len(chosen['holdout']['records']),
              'holdout_histories': len(chosen['holdout']['histories']),
              'holdout_prefix_references': sum(len(h['prefix_keys']) for h in chosen['holdout']['histories'])}


def bound_manifest(path):
    """Rebuild inputs and independently re-audit the frozen real contacts."""
    manifest = read_report(path)
    same(manifest['schema_version'], 1, 'manifest schema differs')
    same(manifest['version'], VERSION, 'experiment version drift')
    same(manifest['source_sha256'], sources(), 'source drift after freeze')
    same(manifest['input_sha256'], {n: checksum(ROOT / n) for n in INPUT_PATHS}, 'input archive drift')
    same(manifest['inventory'], inventory(), 'declared input drift')
    same(manifest['resources'], RESOURCES, 'resource drift')
    same(manifest['policies'], list(POLICIES), 'policy drift')
    originals = manifest['inventory']['records']
    require(len(originals) == len(manifest['records']), 'drawing coverage differs')
    for row, original in zip(manifest['records'], originals):
        same(row, classify(original, row['export']), 'geometry admission or anchors changed')
    same(manifest['counts'], inventory_counts(manifest['records'], manifest['inventory']), 'manifest counters differ')
    same([manifest['producer_runs_during_prepare'], manifest['oracle_runs_during_prepare']], [0, 0],
         'pre-freeze production claims differ')
    return manifest


def underlying(entry):
    """The EQ wrapper keeps the unchanged producer trace in a named child."""
    return entry['result']['run']


def run_record(row):
    """Retain both policies even when one fails or the subsequent audit fails."""
    saved = {'key': row['key'], 'eligibility': row['eligibility'], 'runs': []}
    if row['eligibility'] != 'ready':
        return saved
    geometry = row['export']['geometry'] if row['original']['kind'] == 'geometry' else None
    for scenario in row['scenarios']:
        try:
            adapted = (adapt_exported_geometry(geometry, anchors=scenario['anchors'], drawing=row['original']['document'])
                       if geometry is not None else None)
        except Exception as error:
            saved['runs'].extend({'scenario': scenario['id'], 'policy': policy,
                                   'execution': 'adapt_error', 'producer_seconds': 0,
                                   'error': f'{type(error).__name__}: {error}'} for policy in POLICIES)
            continue
        document = adapted['contact_document'] if adapted else row['original']['document']
        pair = []
        for policy in POLICIES:
            entry = {'scenario': scenario['id'], 'policy': policy,
                     'raw_document': document, 'adapted': adapted, 'execution': 'producer_error'}
            saved['runs'].append(entry)
            pair.append(entry)
            start = perf_counter()
            try:
                function = solve_triangle_eq if policy == 'triangle-eq' else solve_odd_cycle_eq
                entry['result'] = function(document, geometry=geometry,
                                            decision_limit=RESOURCES['decision_limit'], probe_limit=RESOURCES['probe_limit'])
                entry['execution'] = 'produced'
            except Exception as error:
                entry['error'] = f'{type(error).__name__}: {error}'
            entry['producer_seconds'] = perf_counter() - start
        # Only now may independent exact information be obtained.
        for entry in pair:
            if entry['execution'] != 'produced':
                continue
            start = perf_counter()
            try:
                auditor = audit_triangle_eq if entry['policy'] == 'triangle-eq' else audit_odd_cycle_eq
                entry['audit'] = auditor(document, entry['result'], geometry=geometry, adapted=adapted,
                                         assignment_limit=RESOURCES['assignment_limit'], node_limit=RESOURCES['node_limit'])
                entry['execution'] = 'audited'
            except Exception as error:
                entry['execution'] = 'audit_error'
                entry['error'] = f'{type(error).__name__}: {error}'
            entry['audit_seconds'] = perf_counter() - start
        if all(entry['execution'] == 'audited' for entry in pair):
            try:
                require(set(map(tuple, pair[0]['result']['learning']['equal_names'])).issubset(
                    set(map(tuple, pair[1]['result']['learning']['equal_names']))), 'old EQ omitted')
            except AssertionError as error:
                pair[1]['execution'], pair[1]['error'] = 'equivalence_error', str(error)
            if pair[0]['result']['learning']['equal_names'] == pair[1]['result']['learning']['equal_names']:
                try:
                    same(underlying(pair[0]), underlying(pair[1]), 'identical-EQ behavior changed')
                except AssertionError as error:
                    pair[1]['execution'], pair[1]['error'] = 'equivalence_error', str(error)
    return saved


def quality(entry):
    """A final status alone cannot hide an unsafe commitment or unknown audit."""
    if entry['execution'] != 'audited':
        return 'uncompleted'
    audit, result = entry['audit'], underlying(entry)
    if audit['oracle_records'][audit['initial_oracle_index']]['result']['status'] == 'unsat':
        return 'initial_unsat'
    if audit['first_bad_commitment'] is not None or audit['commitment_counts']['unsafe']:
        return 'unsafe'
    if audit['oracle_unknown'] or audit['commitment_counts']['unknown']:
        return 'unknown'
    if result['status'] == 'incomplete':
        return 'uncompleted'
    return 'success' if result['status'] == 'solved' else 'conflict'


def comparison(old, new):
    """Classify repair/regression only when neither side has missing evidence."""
    a, b = quality(old), quality(new)
    if any(q in ('uncompleted', 'unknown', 'initial_unsat') for q in (a, b)):
        return 'unresolved_or_initial_unsat'
    if a == b == 'success':
        return 'both_success'
    if b == 'success':
        return 'repair'
    if a == 'success':
        return 'regression'
    return 'persistent_failure'


def summarize(rows, manifest):
    """Report unique-run metrics separately from overlapping family references."""
    originals = {r['key']: r['original'] for r in manifest['records']}
    populations = sorted({p for raw in originals.values() for p in raw['populations']})
    groups, paired, strata = {}, [], {}
    for row in rows:
        raw = originals[row['key']]
        labels = [*raw['populations'], *('fresh-family:' + family for family in
                  raw.get('holdout_metadata', {}).get('families', []))]
        for entry in row['runs']:
            for label in labels:
                key = label + '/' + entry['scenario'] + '/' + entry['policy']
                total = strata.setdefault(key, Counter())
                total['runs'] += 1
                total['quality_' + quality(entry)] += 1
                total['producer_seconds'] += entry['producer_seconds']
                total['audit_seconds'] += entry.get('audit_seconds', 0)
                if entry['execution'] == 'audited':
                    result, audit = underlying(entry), entry['audit']
                    total.update({'choices': result['choices'], 'probes': result['probes'],
                                  'rejections': result['rejections'], 'phases': audit['phase_count'],
                                  'trace_steps': audit['trace_steps_checked']})
                    total.update(audit['commitment_counts'])
                    if entry['policy'] in POLICIES:
                        count = len(entry['result']['learning']['certificates'])
                        total['runs_with_EQ'] += bool(count)
                        total['certificate_references'] += count
    for population in ['all-records', *populations]:
        selected = [r for row in rows if population == 'all-records'
                    or population in originals[row['key']]['populations'] for r in row['runs']]
        for policy in POLICIES:
            runs = [r for r in selected if r['policy'] == policy]
            audited = [r for r in runs if r['execution'] == 'audited']
            counts, oracle_states = Counter(), Counter()
            for entry in audited:
                counts.update(entry['audit']['commitment_counts'])
                oracle_states.update(record['result']['status'] for record in entry['audit']['oracle_records'])
            groups[population + '/' + policy] = {
                'runs': len(runs), 'audited': len(audited),
                'statuses': dict(Counter(underlying(r)['status'] for r in runs if 'result' in r)),
                'qualities': dict(Counter(quality(r) for r in runs)), 'commitments': dict(counts),
                'rejections': sum(underlying(r)['rejections'] for r in audited),
                'phases': sum(r['audit']['phase_count'] for r in audited),
                'trace_steps': sum(r['audit']['trace_steps_checked'] for r in audited),
                'oracle_statuses': dict(oracle_states),
                'enumeration': dict(Counter(r['audit']['full_enumeration']['status'] for r in audited)),
                'producer_seconds': sum(r['producer_seconds'] for r in runs),
                'audit_seconds': sum(r.get('audit_seconds', 0) for r in runs),
                'runs_with_EQ': sum(bool(r['result']['learning']['equal_names']) for r in audited) if policy in POLICIES else 0,
                'certificate_references': sum(len(r['result']['learning']['certificates']) for r in audited) if policy in POLICIES else 0}
    for row in rows:
        by_scene = {}
        for entry in row['runs']:
            by_scene.setdefault(entry['scenario'], {})[entry['policy']] = entry
        for scenario, entries in by_scene.items():
            old, new = entries['triangle-eq'], entries['odd-cycle-eq']
            pair = {'key': row['key'], 'scenario': scenario,
                    'populations': originals[row['key']]['populations'],
                    'new_key_against_archives': originals[row['key']]['new_key_against_archives'],
                    'comparison': comparison(old, new), 'old_quality': quality(old), 'new_quality': quality(new)}
            if old['execution'] == new['execution'] == 'audited':
                a, b = underlying(old), underlying(new)
                pair.update(choice_difference=b['choices'] - a['choices'],
                            phase_difference=len(b['phases']) - len(a['phases']),
                            initial_unary_candidates_removed=sum(len(x) - len(y) for x, y in zip(
                                a['phases'][0]['outcome']['domains'], b['phases'][0]['outcome']['domains'])),
                            eq_count=len(new['result']['learning']['equal_names']),
                            additional_eq_count=len(new['result']['learning']['equal_names']) - len(old['result']['learning']['equal_names']),
                            new_cycle_lengths=[len(c['cycle']) for c in new['result']['learning']['certificates']])
            paired.append(pair)
    by_key = {row['key']: row for row in rows}
    histories = []
    history_sets = [('fresh-declared', manifest['inventory']['holdout']['histories']),
                    ('regression-triangle', manifest['inventory']['regression_histories'])]
    for population, declared in history_sets:
        for history in declared:
            for mode in ('one-bounded-anchor', 'legacy-frame-anchors'):
                for policy in POLICIES:
                    states = []
                    for key in history['prefix_keys']:
                        row = by_key[key]
                        states.append(quality(next(r for r in row['runs'] if r['scenario'] == mode and r['policy'] == policy))
                                      if row['eligibility'] == 'ready' else row['eligibility'])
                    histories.append({'population': population, 'id': history['id'], 'scenario': mode,
                                      'policy': policy, 'qualities': states, 'terminal_quality': states[-1],
                                      'all_declared_prefixes_successful': all(s == 'success' for s in states)})
    return {'groups': groups, 'strata': {name: dict(values) for name, values in strata.items()},
            'paired': paired, 'comparison_counts': dict(Counter(p['comparison'] for p in paired)),
            'histories': histories, 'eligibility': dict(Counter(r['eligibility'] for r in rows)),
            'population_overlap_warning': 'Family/population references may share drawings; all-records is deduplicated.'}


def execute(manifest_path, output):
    """One exclusive checkpoint per input makes completed work resumable."""
    require(not output.exists(), 'result exists; choose a new name')
    manifest = bound_manifest(manifest_path)
    manifest_hash = checksum(manifest_path)
    directory = output.parent / (output.name.removesuffix('.json.gz') + '-checkpoints')
    directory.mkdir(parents=True, exist_ok=True)
    rule_path = directory / 'rule-soundness.json.gz'
    if rule_path.exists():
        rule = read_report(rule_path)
        same(rule['manifest_sha256'], manifest_hash, 'rule check belongs to another freeze')
    else:
        rule = {'manifest_sha256': manifest_hash, 'result': check_rule_soundness()}
        write_report(rule_path, rule)
    rows, references = [], []
    for number, row in enumerate(manifest['records']):
        path = directory / f'{number:03d}-{row["key"][:12]}.json.gz'
        if path.exists():
            stored = read_report(path)
            same(stored['manifest_sha256'], manifest_hash, 'checkpoint manifest differs')
            same(stored['record_sha256'], digest(row), 'checkpoint input differs')
            saved = stored['row']
        else:
            saved = run_record(row)
            write_report(path, {'manifest_sha256': manifest_hash, 'record_sha256': digest(row), 'row': saved})
        rows.append(saved)
        references.append({'path': path.relative_to(ROOT).as_posix(), 'sha256': checksum(path)})
        print(json.dumps({'completed': number + 1, 'total': len(manifest['records']),
                          'eligibility': row['eligibility'], 'kind': row['original']['kind'],
                          'qualities': [quality(run) for run in saved['runs']]}, ensure_ascii=False), flush=True)
    same(manifest['source_sha256'], sources(), 'source drift during run')
    report = {'schema_version': 1, 'version': VERSION, 'manifest_sha256': manifest_hash,
              'rule_evidence': {'path': rule_path.relative_to(ROOT).as_posix(), 'sha256': checksum(rule_path)},
              'checkpoints': references, 'summary': summarize(rows, manifest)}
    write_report(output, report)
    return {'comparison_counts': report['summary']['comparison_counts'], 'groups': report['summary']['groups']}


def check(manifest_path, report_path, output):
    """Recheck saved raw-problem evidence, without new coloring or oracle search."""
    require(not output.exists(), 'check output exists; choose a new name')
    manifest, report = bound_manifest(manifest_path), read_report(report_path)
    same([report['schema_version'], report['version']], [1, VERSION], 'report schema or version differs')
    same(report['manifest_sha256'], checksum(manifest_path), 'result manifest differs')
    require(len(report['checkpoints']) == len(manifest['records']), 'checkpoint coverage differs')

    def bound_reference(reference):
        """Hashes and containment bind each saved artifact before parsing."""
        path = (ROOT / reference['path']).resolve()
        require(path.is_relative_to(ROOT / 'outputs'), 'artifact outside outputs')
        same(checksum(path), reference['sha256'], 'saved bytes changed')
        value = read_report(path)
        same(value['manifest_sha256'], checksum(manifest_path), 'artifact freeze differs')
        return value

    rule = bound_reference(report['rule_evidence'])
    same(rule['result'], check_rule_soundness(), 'finite literal rule enumeration differs')
    rows, counts = [], Counter()
    for reference, original in zip(report['checkpoints'], manifest['records']):
        saved = bound_reference(reference)
        same(saved['record_sha256'], digest(original), 'checkpoint raw input differs')
        row = saved['row']
        same([row['key'], row['eligibility']], [original['key'], original['eligibility']], 'record identity differs')
        expected = [(scene['id'], policy) for scene in original['scenarios'] for policy in POLICIES]
        same([(r['scenario'], r['policy']) for r in row['runs']], expected, 'policy/scenario coverage differs')
        geometry = original['export']['geometry'] if original['original']['kind'] == 'geometry' and original['eligibility'] == 'ready' else None
        for entry in row['runs']:
            counts['runs'] += 1
            if entry['execution'] != 'audited':
                counts['execution_incomplete'] += 1
                continue
            scenario = next(s for s in original['scenarios'] if s['id'] == entry['scenario'])
            adapted = (adapt_exported_geometry(geometry, anchors=scenario['anchors'], drawing=original['original']['document'])
                       if geometry is not None else None)
            document = adapted['contact_document'] if adapted else original['original']['document']
            same(entry['adapted'], adapted, 'raw adapter differs')
            same(entry['raw_document'], document, 'raw oracle problem differs')
            artifact_checker = (check_triangle_eq_artifacts if entry['policy'] == 'triangle-eq'
                                else check_odd_cycle_eq_artifacts)
            artifact_checker(document, entry['result'], entry['audit'], RESOURCES,
                             geometry=geometry, adapted=adapted)
            counts['oracle_records'] += len(entry['audit']['oracle_records'])
            counts['phases'] += entry['audit']['phase_count']
            counts['unsafe_commitments'] += entry['audit']['commitment_counts']['unsafe']
            counts['audited_runs'] += 1
        for scenario in original['scenarios']:
            pair = [r for r in row['runs'] if r['scenario'] == scenario['id']]
            if all(r['execution'] == 'audited' for r in pair):
                require(set(map(tuple, pair[0]['result']['learning']['equal_names'])).issubset(
                    set(map(tuple, pair[1]['result']['learning']['equal_names']))), 'saved old EQ omitted')
            if all(r['execution'] == 'audited' for r in pair) and pair[0]['result']['learning']['equal_names'] == pair[1]['result']['learning']['equal_names']:
                same(underlying(pair[0]), underlying(pair[1]), 'saved identical-EQ behavior differs')
        rows.append(row)
    same(report['summary'], summarize(rows, manifest), 'summary reconstruction differs')
    same(manifest['source_sha256'], sources(), 'sources changed during check')
    result = {'passed': True, 'scope': 'Evidence integrity is distinct from strategy success.',
              'eligible_executions_complete': counts['execution_incomplete'] == 0,
              'producer_rerun': False, 'oracle_search_rerun': False, 'literal_rule_enumeration_repeated': True,
              'manifest_sha256': checksum(manifest_path), 'report_sha256': checksum(report_path),
              'counts': dict(counts), 'source_sha256': sources()}
    write_report(output, result)
    return result['counts']


def main():
    """Separate freeze, paired experiment and saved-certificate verification."""
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

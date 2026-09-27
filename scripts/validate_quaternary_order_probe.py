"""Freeze, run and recheck a bounded mother-order experiment.

The coloring producer is unchanged. Input feasibility is frozen before coloring;
every invalid drawing stays in the manifest. Exact oracles are posterior only.
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
from scripts.audit_quaternary_low_color import audit_low_color
from scripts.audit_quaternary_order_probe import diagnose_order, check_saved_schedule
from scripts.check_quaternary_reachability import checksum, sources as previous_sources
from scripts.check_quaternary_reachability_artifacts import check_certificates, same
from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.quaternary_low_color import solve_low_color
from scripts.quaternary_reroot_inputs import build_reroot_inventory, identify_reroot
from scripts.quaternary_root_support_inputs import build_support_inventory, inspect_support_geometry
from scripts.validate_global_restart import digest, export_geometries, write_report
from scripts.validate_quaternary_contacts_v2 import read_report
from scripts.validate_quaternary_geometry import standard_scenarios

OLD_MANIFEST = 'outputs/quaternary-reachability-manifest-2026-09-22.json.gz'
PROTOCOL = 'docs/QUATERNARY_ORDER_PROBE_PROTOCOL-2026-09-23.md'
VERSION = 'quaternary-order-probe-v1'
RESOURCES = {'face_limit': 40, 'decision_limit': 128, 'probe_limit': 512,
             'assignment_limit': 262144, 'node_limit': 200000}
MODES = ('one-bounded-anchor', 'legacy-frame-anchors')
NEW_SOURCES = (
    'scripts/validate_quaternary_order_probe.py', 'tests/test_validate_quaternary_order_probe.py',
    'scripts/audit_quaternary_order_probe.py', 'tests/test_quaternary_order_probe.py',
    'scripts/check_quaternary_reachability_artifacts.py',
    'tests/test_quaternary_reachability_artifacts.py', PROTOCOL,
    'scripts/audit_retained_blocks.py', 'scripts/check_quaternary_low_color_artifacts.py',
    'scripts/compare_local_marks.py', 'scripts/validate_local_reuse.py',
    'scripts/validate_retained_profiles.py',
)


def require(condition, message):
    """Assertions remain active under optimized Python."""
    if not condition:
        raise AssertionError(message)


def sources():
    """Bind the old 129-file chain and every additional local dependency."""
    from scripts.quaternary_reroot_inputs import SOURCE_PATHS as reroot_sources
    from scripts.quaternary_root_support_inputs import SOURCE_PATHS as support_sources
    hashes = previous_sources()
    same(hashes, read_report(ROOT / OLD_MANIFEST)['source_sha256'], 'old sources changed')
    paths = set(NEW_SOURCES) | set(reroot_sources) | set(support_sources)
    hashes.update({name: checksum(ROOT / name) for name in paths})
    return hashes


def inventories():
    """Rebuild the declared drawings without querying colors or an oracle."""
    return {'reroot': build_reroot_inventory(), 'support': build_support_inventory()}


def inspect_record(family, original, exported):
    """Retain unsupported geometry and topology failures as explicit records."""
    same(exported['key'], original['key'], 'export reordered input')
    row = {'family': family, 'original': original, 'key': original['key'],
           'export': exported, 'eligibility': 'geometry_error', 'role_mapping': None,
           'scenarios': [], 'error': None}
    if exported['status'] != 'geometry_ok':
        row['error'] = exported.get('errors', exported.get('error', 'geometry export failed'))
        return row
    geometry = exported['geometry']
    row['geometry_sha256'] = digest(geometry)
    try:
        adapted = adapt_exported_geometry(geometry, drawing=original['document'])
        row['geometry_audit'], _ = audit_geometry(geometry, adapted)
    except (ValueError, AssertionError, KeyError, TypeError) as error:
        row['eligibility'], row['error'] = 'geometry_audit_error', str(error)
        return row
    if len(geometry['faces']) > RESOURCES['face_limit']:
        row['eligibility'], row['error'] = 'face_budget_exceeded', 'more than forty faces'
        return row
    try:
        if family == 'reroot':
            row['inspection'] = identify_reroot(geometry, original['target'])
            row['role_mapping'] = row['inspection']['labels']
        else:
            row['inspection'] = inspect_support_geometry(geometry, original)
            mapping = row['inspection']['role_mapping']
            row['role_mapping'] = mapping['labels'] if mapping else None
        row['scenarios'] = standard_scenarios(geometry, {'extra_scenarios': []})
    except (ValueError, AssertionError, KeyError, TypeError) as error:
        row['eligibility'], row['error'] = 'topology_or_schedule_error', str(error)
        return row
    row['eligibility'] = 'ready'
    return row


def prepare(path):
    """Save the exact geometry and actual anchors before any producer run."""
    from scripts.quaternary_reroot_inputs import export_reroot_geometries
    require(not path.exists(), 'manifest exists; choose a new path')
    hashes, inventory = sources(), inventories()
    rows = []
    for family, values in inventory.items():
        records = values['records']
        exported = (export_reroot_geometries(records) if family == 'reroot'
                    else export_geometries(records))
        require(len(exported) == len(records), 'export omitted a drawing')
        rows.extend(inspect_record(family, a, b) for a, b in zip(records, exported))
    require(len(rows) == 44, 'declared input count changed')
    same(hashes, sources(), 'sources changed during freeze')
    manifest = {'schema_version': 1, 'version': VERSION,
                'created_at_utc': datetime.now(timezone.utc).isoformat(),
                'source_sha256': hashes, 'input_sha256': {OLD_MANIFEST: checksum(ROOT / OLD_MANIFEST)},
                'inventory': inventory, 'records': rows, 'resources': RESOURCES,
                'producer_runs_during_prepare': 0,
                'eligibility_counts': dict(Counter(r['eligibility'] for r in rows))}
    write_report(path, manifest)
    return manifest['eligibility_counts']


def bound_manifest(path):
    """Check frozen inputs and source bytes before production or rechecking."""
    manifest = read_report(path)
    same(manifest['version'], VERSION, 'version changed')
    same(manifest['resources'], RESOURCES, 'resources changed')
    same(manifest['source_sha256'], sources(), 'source drift after freeze')
    same(manifest['inventory'], inventories(), 'generated input drift')
    same(manifest['input_sha256'], {OLD_MANIFEST: checksum(ROOT / OLD_MANIFEST)}, 'old manifest changed')
    declared = [(family, original) for family, inv in manifest['inventory'].items()
                for original in inv['records']]
    # JSON sort order can reorder families: identity, not dict iteration, binds rows.
    expected = {(family, original['key']): original for family, original in declared}
    require(len(expected) == len(manifest['records']) == 44, 'duplicate or missing drawing')
    seen = set()
    for row in manifest['records']:
        identity = (row['family'], row['key'])
        require(identity in expected and identity not in seen, 'invalid drawing identity')
        seen.add(identity)
        same(row, inspect_record(row['family'], expected[identity], row['export']),
             'frozen geometry classification differs')
    same(manifest['eligibility_counts'], dict(Counter(r['eligibility'] for r in manifest['records'])),
         'eligibility counters differ')
    return manifest


def run_record(row, resources):
    """Finish both actual runs before their posterior oracle audits.

    Exceptions remain evidence of an incomplete execution. A mathematical
    conflict returned by the producer is an ordinary recorded result.
    """
    saved = {'family': row['family'], 'key': row['key'],
             'eligibility': row['eligibility'], 'runs': []}
    if row['eligibility'] != 'ready':
        return saved
    geometry = row['export']['geometry']
    for scenario in row['scenarios']:
        run = {'scenario': scenario['id'], 'execution': 'producer_error'}
        saved['runs'].append(run)
        start = perf_counter()
        try:
            adapted = adapt_exported_geometry(geometry, anchors=scenario['anchors'],
                                              drawing=row['original']['document'])
            run['adapted'] = adapted
            run['result'] = solve_low_color(adapted['contact_document'], geometry=geometry, probe=True,
                                            decision_limit=resources['decision_limit'],
                                            probe_limit=resources['probe_limit'])
            run['execution'] = 'produced'
        except Exception as error:
            run['error'] = f'{type(error).__name__}: {error}'
        run['producer_seconds'] = perf_counter() - start
    # No audit outcome can be consulted by a producer above.
    for run in saved['runs']:
        if run['execution'] != 'produced':
            continue
        start = perf_counter()
        try:
            document = run['adapted']['contact_document']
            run['audit'] = audit_low_color(document, run['result'], geometry=geometry,
                                          adapted=run['adapted'], assignment_limit=resources['assignment_limit'],
                                          node_limit=resources['node_limit'])
            run['diagnostic'] = diagnose_order(document, run['result'], run['audit'],
                                               geometry=geometry, role_mapping=row['role_mapping'])
            run['execution'] = 'audited'
        except Exception as error:
            run['execution'] = 'audit_error'
            run['error'] = f'{type(error).__name__}: {error}'
        run['audit_seconds'] = perf_counter() - start
    return saved


def summary(rows, manifest):
    """Separate unique inputs, terminal references and declared short histories."""
    groups = {}
    index = {(row['family'], row['key']): row for row in rows}
    for family in manifest['inventory']:
        for mode in MODES:
            selected = [r for row in rows if row['family'] == family for r in row['runs']
                        if r['scenario'] == mode]
            checked = [r for r in selected if r['execution'] == 'audited']
            counts, scan = Counter(), Counter()
            for run in checked:
                counts.update(run['audit']['commitment_counts'])
                scan.update(run['diagnostic']['motif_scan']['counts'])
            groups[family + '/' + mode] = {
                'attempted_runs': len(selected), 'audited_runs': len(checked),
                'execution': dict(Counter(r['execution'] for r in selected)),
                'statuses': dict(Counter(r['result']['status'] for r in selected if 'result' in r)),
                'commitments': dict(counts), 'motif_counts': dict(scan),
                'rejections': sum(r['result']['rejections'] for r in checked),
                'oracle_unknown': sum(r['audit']['oracle_unknown'] for r in checked),
                'phases': sum(r['audit']['phase_count'] for r in checked),
                'trace_steps': sum(r['audit']['trace_steps_checked'] for r in checked),
                'initial_statuses': dict(Counter(r['diagnostic']['initial_exact_status'] for r in checked)),
                'mapped_runs': sum(r['diagnostic']['role_mapping'] is not None for r in checked),
                'runs_with_K4_commit_before_E': sum(bool(r['diagnostic']['K4_commits_before_E_singleton'])
                                                  for r in checked),
                'producer_seconds': sum(r['producer_seconds'] for r in selected),
                'audit_seconds': sum(r.get('audit_seconds', 0) for r in selected),
                'enumeration_statuses': dict(Counter(r['audit']['full_enumeration']['status'] for r in checked)),
            }

    def status(family, key, mode):
        """A missing execution cannot be mistaken for a successful prefix."""
        row = index[family, key]
        if row['eligibility'] != 'ready':
            return row['eligibility']
        run = next(r for r in row['runs'] if r['scenario'] == mode)
        return run['result']['status'] if run['execution'] == 'audited' else run['execution']

    terminal, histories = {}, []
    for family, inv in manifest['inventory'].items():
        cases = inv.get('cases', inv['records'])
        for mode in MODES:
            terminal[family + '/' + mode] = dict(Counter(status(family, c['key'], mode) for c in cases))
        for history in inv.get('histories', []):
            for mode in MODES:
                states = [status(family, key, mode) for key in history['prefix_keys']]
                histories.append({'family': family, 'id': history['id'], 'scenario': mode,
                                  'statuses': states, 'all_declared_prefixes_solved': all(s == 'solved' for s in states)})
    return {'groups': groups, 'terminal_case_statuses': terminal, 'short_histories': histories,
            'eligibility': dict(Counter(r['eligibility'] for r in rows)),
            'producer_oracle_separation': 'both modes finish production per drawing before either audit'}


def execute(manifest_path, output):
    """Keep one exclusive checkpoint per frozen drawing and save the aggregate."""
    from scripts.quaternary_reroot_inputs import export_reroot_geometries
    require(not output.exists(), 'output exists; choose a new path')
    manifest = bound_manifest(manifest_path)
    manifest_hash = checksum(manifest_path)
    # Re-export geometry only, including invalid cases; do not resample inputs.
    for family, inventory in manifest['inventory'].items():
        exported = (export_reroot_geometries(inventory['records']) if family == 'reroot'
                    else export_geometries(inventory['records']))
        same(exported, [r['export'] for r in manifest['records'] if r['family'] == family],
             'geometry export changed after freeze')
    checkpoint_dir = output.parent / (output.name.removesuffix('.json.gz') + '-checkpoints')
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    rows, checkpoints = [], []
    for number, row in enumerate(manifest['records']):
        path = checkpoint_dir / f'{number:03d}-{row["family"]}-{row["key"][:12]}.json.gz'
        if path.exists():
            stored = read_report(path)
            same(stored['manifest_sha256'], manifest_hash, 'checkpoint belongs to another manifest')
            same(stored['record_sha256'], digest(row), 'checkpoint input differs')
            saved = stored['row']
        else:
            saved = run_record(row, manifest['resources'])
            write_report(path, {'manifest_sha256': manifest_hash, 'record_sha256': digest(row), 'row': saved})
        rows.append(saved)
        checkpoints.append({'path': path.relative_to(ROOT).as_posix(), 'sha256': checksum(path)})
        print(json.dumps({'completed': number + 1, 'total': len(manifest['records']),
                          'family': row['family'], 'eligibility': row['eligibility'],
                          'runs': [(r['scenario'], r['execution'], r.get('result', {}).get('status'))
                                   for r in saved['runs']]}, ensure_ascii=False), flush=True)
    same(manifest['source_sha256'], sources(), 'sources changed during execution')
    report = {'schema_version': 1, 'version': VERSION, 'manifest_sha256': manifest_hash,
              'checkpoints': checkpoints, 'summary': summary(rows, manifest)}
    write_report(output, report)
    return report['summary']


def check(manifest_path, report_path, output):
    """Recheck saved certificates, traces, diagnostics and coverage; no search."""
    require(not output.exists(), 'check output exists; choose a new path')
    manifest, report = bound_manifest(manifest_path), read_report(report_path)
    same(report['manifest_sha256'], checksum(manifest_path), 'report manifest differs')
    require(len(report['checkpoints']) == len(manifest['records']), 'checkpoint count differs')
    rows, counts = [], Counter()
    for reference, original in zip(report['checkpoints'], manifest['records']):
        path = (ROOT / reference['path']).resolve()
        require(path.is_relative_to(ROOT / 'outputs'), 'checkpoint outside outputs')
        same(checksum(path), reference['sha256'], 'checkpoint bytes changed')
        saved = read_report(path)
        same(saved['manifest_sha256'], checksum(manifest_path), 'checkpoint manifest changed')
        same(saved['record_sha256'], digest(original), 'checkpoint drawing changed')
        row = saved['row']
        same([row[k] for k in ('family', 'key', 'eligibility')],
             [original[k] for k in ('family', 'key', 'eligibility')], 'checkpoint identity changed')
        same([r['scenario'] for r in row['runs']], [s['id'] for s in original['scenarios']], 'mode coverage differs')
        for run, scenario in zip(row['runs'], original['scenarios']):
            counts['attempted_runs'] += 1
            if run['execution'] != 'audited':
                counts['incomplete_execution'] += 1
                continue
            geometry = original['export']['geometry']
            adapted = adapt_exported_geometry(geometry, anchors=scenario['anchors'], drawing=original['original']['document'])
            same(run['adapted'], adapted, 'saved raw adapter changed')
            geometric, _ = audit_geometry(geometry, adapted)
            same(run['audit']['geometry'], geometric, 'saved geometry check changed')
            check_saved_schedule(adapted['contact_document'], run['result'], geometry, RESOURCES)
            cert = check_certificates(adapted['contact_document'], run['result'], run['audit'], RESOURCES)
            counts['oracle_records'] += cert['oracle_records']
            counts['phases'] += cert['phases']
            counts['unsafe_commitments'] += cert['unsafe_commitments']
            same(run['diagnostic'], diagnose_order(adapted['contact_document'], run['result'], run['audit'],
                                                   geometry=geometry, role_mapping=original['role_mapping']),
                 'saved diagnostic changed')
            counts['audited_runs'] += 1
        rows.append(row)
    same(report['summary'], summary(rows, manifest), 'summary differs')
    same(manifest['source_sha256'], sources(), 'source drift during artifact check')
    result = {'passed': True, 'scope': 'saved evidence integrity, not algorithm completeness',
              'eligible_executions_complete': counts['incomplete_execution'] == 0,
              'producer_rerun': False, 'oracle_search_rerun': False,
              'manifest_sha256': checksum(manifest_path), 'report_sha256': checksum(report_path),
              'counts': dict(counts), 'source_sha256': sources()}
    write_report(output, result)
    return result['counts']


def main():
    """Three explicit commands keep freezing separate from actual production."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'run', 'check'))
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    manifest = args.manifest.resolve()
    if args.command == 'prepare':
        result = prepare(manifest)
    else:
        require(args.output is not None, '--output required')
        if args.command == 'run':
            result = execute(manifest, args.output.resolve())
        else:
            require(args.report is not None, '--report required')
            result = check(manifest, args.report.resolve(), args.output.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

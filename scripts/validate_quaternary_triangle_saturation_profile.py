"""Locate costs of the frozen prefilter producer without changing decisions.

Each declared scene gets one plain call and one cProfile call in alternating
order. Complete outputs must match the bound, already audited archive. Saved
replay verifies identities and arithmetic; it cannot remeasure historical time.
"""

from argparse import ArgumentParser
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from math import fsum, isclose, isfinite
from pathlib import Path
from time import perf_counter
import cProfile
import json
import platform
import pstats
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import validate_quaternary_triangle_saturation_prefilter as previous
from scripts.quaternary_profile_stats import profile_rows, validate_rows, summarize_rows

VERSION = 'quaternary-triangle-saturation-profile-v1'
ARCHIVES = tuple('outputs/quaternary-triangle-saturation-prefilter-' + suffix for suffix in (
    'manifest-2026-10-03.json.gz', '2026-10-03.json.gz', 'check-2026-10-03.json'))
NEW_SOURCES = (
    'scripts/quaternary_profile_stats.py', 'tests/test_quaternary_profile_stats.py',
    'scripts/validate_quaternary_triangle_saturation_profile.py',
    'tests/test_validate_quaternary_triangle_saturation_profile.py',
    'docs/QUATERNARY_TRIANGLE_SATURATION_PROFILE_PROTOCOL-2026-10-03.md')
RESOURCES = {'workers': 1, 'plain_calls_per_scene': 1, 'profile_calls_per_scene': 1,
             'decision_limit': 128, 'probe_limit': 8192, 'oracle_searches': 0,
             'subcalls': True, 'builtins': True, 'warmup_calls': 0}
STRATA = ('1-4', '5-8', '9-12', '13+')
FIELDS = ('primitive_calls', 'total_calls', 'self_seconds', 'cumulative_seconds')
same, require, digest = previous.same, previous.require, previous.digest
read_report, checksum = previous.read_report, previous.checksum
write_atomic, reference, bound_reference = previous.write_atomic, previous.reference, previous.bound_reference


def environment():
    """Record portable execution metadata, never usernames or runtime paths."""
    return {'python_version': platform.python_version(), 'implementation': platform.python_implementation(),
            'system': platform.system(), 'machine': platform.machine(),
            'wall_timer': 'time.perf_counter', 'profile_timer': 'cProfile default'}


def stratum(faces):
    """Use original side count, never the number of contracted EQ classes."""
    require(type(faces) is int and faces >= 1, 'invalid original side count')
    return '1-4' if faces <= 4 else '5-8' if faces <= 8 else '9-12' if faces <= 12 else '13+'


def sources():
    """Preserve all 290 previous frozen files and bind five profiling files."""
    return {**previous.sources(), **{p: checksum(ROOT / p) for p in NEW_SOURCES}}


def upstream():
    """Validate the prior completed experiment before selecting any inputs."""
    m = previous.bound_manifest(ROOT / ARCHIVES[0])
    report, check = [read_report(ROOT / p) for p in ARCHIVES[1:]]
    mh = checksum(ROOT / ARCHIVES[0])
    same([report['manifest_sha256'], check['manifest_sha256']], [mh, mh], 'upstream manifest')
    same(check['report_sha256'], checksum(ROOT / ARCHIVES[1]), 'upstream report')
    same(check['source_sha256'], m['source_sha256'], 'upstream source')
    require(all(check.get(k) is True for k in ('passed', 'all_producer_outputs_exactly_equal',
        'all_conditional_outputs_exactly_equal', 'all_rule_evidence_verified', 'all_actual_work_verified')),
        'incomplete upstream check')
    same(len(report['checkpoints']), len(m['records']), 'upstream coverage')
    return m, report


def load_parent(row, parent_manifest_hash):
    """Load complete frozen producer outputs and bind their original inputs."""
    saved = bound_reference(row['prefilter_reference'])
    same([saved['manifest_sha256'], saved['record_sha256']],
         [parent_manifest_hash, row['prefilter_record_sha256']], 'parent checkpoint binding')
    result = saved['result']
    same(result['key'], row['key'], 'parent graph key')
    same([r['scenario'] for r in result['runs']], [s['id'] for s in row['scenes']], 'parent scene coverage')
    for run, scene in zip(result['runs'], row['scenes']):
        same(digest(run['result']), scene['envelope_sha256'], 'parent full envelope')
        raw = run['result']['original_input']
        same(digest(raw), scene['raw_sha256'], 'parent raw input')
        same(len(raw['sides']), scene['faces'], 'original face count')
    return result['runs']


def records_from(parent, report):
    """Declare every production input without executing any coloring code."""
    records, index = [], 0
    mh = checksum(ROOT / ARCHIVES[0])
    for old, ref in zip(parent['records'], report['checkpoints']):
        row = {'key': old['key'], 'eligibility': old['eligibility'], 'geometry': old['geometry'],
               'prefilter_reference': ref, 'prefilter_record_sha256': digest(old), 'scenes': []}
        saved = bound_reference(ref)
        same([saved['manifest_sha256'], saved['record_sha256']], [mh, digest(old)], 'input source')
        same(saved['result']['key'], old['key'], 'input graph')
        same([r['scenario'] for r in saved['result']['runs']], [s['id'] for s in old['scenes']], 'input scenes')
        for scene, run in zip(old['scenes'], saved['result']['runs']):
            raw, result = run['result']['original_input'], run['result']
            same([digest(raw), digest(result)], [scene['raw_sha256'], scene['envelope_sha256']], 'input identity')
            faces = len(raw['sides'])
            row['scenes'].append({'id': scene['id'], 'raw_sha256': scene['raw_sha256'],
                'envelope_sha256': scene['envelope_sha256'], 'faces': faces,
                'stratum': stratum(faces), 'index': index})
            index += 1
        records.append(row)
    return records


def inventory(records):
    """Count declared records, exclusions and correlated scene strata."""
    return {'drawings': len(records), 'eligibility': dict(Counter(r['eligibility'] for r in records)),
            'scenes': sum(len(r['scenes']) for r in records),
            'strata': dict(Counter(s['stratum'] for r in records for s in r['scenes']))}


def prepare(path):
    """Freeze sources, environment and all inputs before formal profiling."""
    require(not path.exists(), 'manifest exists')
    before, inputs = sources(), {p: checksum(ROOT / p) for p in ARCHIVES}
    parent, report = upstream()
    records = records_from(parent, report)
    counts = inventory(records)
    same([counts['drawings'], counts['scenes']], [537, 975], 'declared population')
    same(before, sources(), 'source changed during prepare')
    manifest = {'version': VERSION, 'schema_version': 1, 'source_sha256': before,
        'input_sha256': inputs, 'records': records, 'counts': counts, 'resources': RESOURCES,
        'environment': environment(), 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'producer_runs_before_freeze': 0, 'oracle_searches_before_freeze': 0}
    write_atomic(path, manifest)
    return counts


def bound_manifest(path):
    """Check immutable inputs and scope without producer or oracle reruns."""
    m = read_report(path)
    same([m['schema_version'], m['version']], [1, VERSION], 'profile manifest schema')
    same(m['source_sha256'], sources(), 'source drift')
    same(m['input_sha256'], {p: checksum(ROOT / p) for p in ARCHIVES}, 'input drift')
    same(m['resources'], RESOURCES, 'resource drift')
    same([m['producer_runs_before_freeze'], m['oracle_searches_before_freeze']], [0, 0], 'freeze activity')
    parent, report = upstream()
    same(m['records'], records_from(parent, report), 'scope or input substitution')
    same(m['counts'], inventory(m['records']), 'inventory reconstruction')
    return m


def measured_scene(raw, geometry, expected, scene):
    """Profile only the producer call; copies and comparisons stay outside."""
    order = ['plain', 'profile'] if scene['index'] % 2 == 0 else ['profile', 'plain']
    saved = {'scenario': scene['id'], 'index': scene['index'], 'faces': scene['faces'],
             'stratum': scene['stratum'], 'order': order}
    output = None
    for mode in order:
        # Release earlier results and prepare independent inputs before timing.
        output = None
        document, shape = deepcopy(raw), deepcopy(geometry)
        profiler = cProfile.Profile(subcalls=True, builtins=True) if mode == 'profile' else None
        start = perf_counter()
        if profiler is not None:
            profiler.enable()
        try:
            output = previous.solve_prefilter_triangle_saturation(document, geometry=shape,
                decision_limit=128, probe_limit=8192, work_log=None)
        finally:
            if profiler is not None:
                profiler.disable()
        saved[mode + '_seconds'] = perf_counter() - start
        previous.equal_output(output, expected, {'mode': mode, 'scene': scene})
        saved[mode + '_sha256'] = digest(output)
        same(document, raw, 'producer mutated input')
        same(shape, geometry, 'producer mutated geometry')
        if profiler is not None:
            # Bind exported coverage to the profiler's own snapshot totals.
            stats = pstats.Stats(profiler)
            saved['profile_totals'] = {'function_count': len(stats.stats), 'total_calls': stats.total_calls,
                'primitive_calls': stats.prim_calls, 'self_seconds': stats.total_tt}
            saved['functions'] = profile_rows(profiler, ROOT)
    # The last complete output suffices because both calls were compared above.
    saved['result'] = output
    return saved


def verify_scene(run, scene, expected):
    """Validate saved full output and telemetry; never run the implementation."""
    require(set(run) == {'scenario', 'index', 'faces', 'stratum', 'order', 'plain_seconds',
                        'profile_seconds', 'plain_sha256', 'profile_sha256', 'functions',
                        'profile_totals', 'result'}, 'scene fields')
    for target, source in (('scenario', 'id'), ('index', 'index'), ('faces', 'faces'), ('stratum', 'stratum')):
        same(run[target], scene[source], 'scene ' + target)
    same(run['order'], ['plain', 'profile'] if scene['index'] % 2 == 0 else ['profile', 'plain'], 'order')
    same(run['result'], expected, 'complete output')
    for mode in ('plain', 'profile'):
        value = run[mode + '_seconds']
        require(type(value) in (int, float) and isfinite(value) and value >= 0, 'invalid wall time')
        same(run[mode + '_sha256'], digest(expected), 'timed output hash')
    validate_rows(run['functions'])
    totals = run['profile_totals']
    require(set(totals) == {'function_count', 'total_calls', 'primitive_calls', 'self_seconds'}, 'profile totals fields')
    for field in ('function_count', 'total_calls', 'primitive_calls'):
        require(type(totals[field]) is int and totals[field] >= 0, 'invalid profile total')
    same(totals['function_count'], len(run['functions']), 'all profile functions exported')
    for field in ('total_calls', 'primitive_calls'):
        same(totals[field], sum(r[field] for r in run['functions']), 'profile call sum')
    require(type(totals['self_seconds']) in (int, float) and isfinite(totals['self_seconds'])
            and totals['self_seconds'] >= 0, 'invalid profile self total')
    require(isclose(totals['self_seconds'], fsum(r['self_seconds'] for r in run['functions']),
                    rel_tol=1e-9, abs_tol=1e-9), 'profile self sum differs from snapshot')
    roots = [r for r in run['functions'] if r['file'] ==
             'scripts/quaternary_triangle_saturation_prefilter_low_color.py'
             and r['function'] == 'solve_prefilter_triangle_saturation']
    require(len(roots) == 1 and roots[0]['total_calls'] == roots[0]['primitive_calls'] == 1,
            'profile must contain exactly one complete producer call')
    # A generous clock-rounding tolerance permits finite timer resolution only.
    require(sum(r['self_seconds'] for r in run['functions']) <= run['profile_seconds'] + 1e-6,
            'profile self time exceeds measured wall time')


def verify_drawing(m, row, saved):
    """Validate coverage against the parent, including excluded empty records."""
    original = load_parent(row, m['input_sha256'][ARCHIVES[0]])
    require(set(saved) == {'key', 'runs'}, 'drawing fields')
    same(saved['key'], row['key'], 'drawing identity')
    same(len(saved['runs']), len(row['scenes']), 'scene count')
    for run, scene, parent in zip(saved['runs'], row['scenes'], original):
        verify_scene(run, scene, parent['result'])


def merge_rows(groups):
    """Add exclusive counters and caller edges by full portable identity.

    Cumulative seconds can be aggregated across distinct executions for the
    same function, but cannot be added across nested functions as a time budget.
    """
    merged = {}
    def identity(row):
        return row['file'], row['line'], row['function']
    def add(target, row):
        for field in FIELDS:
            target[field] += row[field]
    def empty(row):
        return {**{k: row[k] for k in ('file', 'line', 'function')}, **dict.fromkeys(FIELDS, 0)}
    for rows in groups:
        for row in rows:
            item = merged.setdefault(identity(row), {**empty(row), 'callers': {}})
            add(item, row)
            for caller in row['callers']:
                add(item['callers'].setdefault(identity(caller), empty(caller)), caller)
    result = []
    for key in sorted(merged):
        row = merged[key]
        row['callers'] = [row['callers'][k] for k in sorted(row['callers'])]
        result.append(row)
    validate_rows(result)
    return result


def compact(saved):
    """Discard large semantic envelopes after each checked drawing."""
    return [{'drawing_key': saved['key'], **{k: v for k, v in r.items() if k != 'result'}}
            for r in saved['runs']]


def summary(items):
    """Keep plain wall, profiled wall and exclusive profile budgets separate."""
    out = {}
    for label in ('all',) + STRATA:
        selected = [i for i in items if label == 'all' or i['stratum'] == label]
        plain = sum(i['plain_seconds'] for i in selected)
        profiled = sum(i['profile_seconds'] for i in selected)
        rows = merge_rows(i['functions'] for i in selected)
        out[label] = {'scenes': len(selected), 'drawings': len({i['drawing_key'] for i in selected}),
            'plain_seconds': plain, 'profile_seconds': profiled,
            'profile_over_plain': profiled / plain if plain else None,
            'order_counts': dict(Counter('/'.join(i['order']) for i in selected)),
            'function_statistics': summarize_rows(rows), 'functions': rows}
    return out


def execute(manifest_path, output):
    """Run one worker with atomic per-drawing checkpoints and explicit failures."""
    require(not output.exists(), 'report exists')
    m = bound_manifest(manifest_path)
    same(m['environment'], environment(), 'execution environment changed')
    mh, refs, items, resumed = checksum(manifest_path), [], [], 0
    directory = output.parent / (output.name.removesuffix('.json.gz') + '-checkpoints')
    start = perf_counter()
    for number, row in enumerate(m['records']):
        path = directory / f'{number:03d}-{row["key"][:12]}.json.gz'
        if path.exists():
            saved = read_report(path)
            same([saved['manifest_sha256'], saved['record_sha256']], [mh, digest(row)], 'resume binding')
            verify_drawing(m, row, saved['result'])
            resumed += 1
        else:
            try:
                original = load_parent(row, m['input_sha256'][ARCHIVES[0]])
                runs = [measured_scene(parent['result']['original_input'], row['geometry'], parent['result'], scene)
                        for parent, scene in zip(original, row['scenes'])]
                result = {'key': row['key'], 'runs': runs}
                verify_drawing(m, row, result)
                saved = {'manifest_sha256': mh, 'record_sha256': digest(row), 'result': result}
                write_atomic(path, saved)
            except Exception as error:
                previous.record_failure(directory, mh, {'drawing_index': number, 'record': row}, error)
                raise
        refs.append(reference(path))
        items.extend(compact(saved['result']))
        if (number + 1) % 25 == 0 or number + 1 == len(m['records']):
            print(json.dumps({'completed_drawings': number + 1, 'total': len(m['records'])}), flush=True)
    same(m['source_sha256'], sources(), 'source drift during execution')
    report = {'version': VERSION, 'manifest_sha256': mh, 'checkpoints': refs, 'summary': summary(items),
        'execution': {'workers': 1, 'resumed_drawings': resumed, 'wall_seconds': perf_counter() - start,
                      'environment': environment(), 'oracle_searches': 0}}
    write_atomic(output, report)
    return {k: {n: v for n, v in row.items() if n not in ('functions', 'function_statistics')}
            for k, row in report['summary'].items()}


def check(manifest_path, report_path, output):
    """Check saved identity/coverage and sums, without executing profiled code."""
    require(not output.exists(), 'check exists')
    m, r = bound_manifest(manifest_path), read_report(report_path)
    mh = checksum(manifest_path)
    same([r['version'], r['manifest_sha256']], [VERSION, mh], 'report binding')
    same(len(r['checkpoints']), len(m['records']), 'drawing coverage')
    e = r['execution']
    require(set(e) == {'workers', 'resumed_drawings', 'wall_seconds', 'environment', 'oracle_searches'}, 'execution fields')
    same([e['workers'], e['oracle_searches'], e['environment']], [1, 0, m['environment']], 'execution conditions')
    require(type(e['resumed_drawings']) is int and 0 <= e['resumed_drawings'] <= len(m['records']), 'resume count')
    require(type(e['wall_seconds']) in (float, int) and isfinite(e['wall_seconds']) and e['wall_seconds'] >= 0,
            'invalid run wall time')
    items = []
    for row, ref in zip(m['records'], r['checkpoints']):
        saved = bound_reference(ref)
        same([saved['manifest_sha256'], saved['record_sha256']], [mh, digest(row)], 'checkpoint binding')
        verify_drawing(m, row, saved['result'])
        items.extend(compact(saved['result']))
    same(r['summary'], summary(items), 'summary reconstruction')
    same(len(items), m['counts']['scenes'], 'complete scene coverage')
    same(m['source_sha256'], sources(), 'source drift during check')
    result = {'passed': True, 'manifest_sha256': mh, 'report_sha256': checksum(report_path),
        'source_sha256': m['source_sha256'], 'counts': m['counts'], 'all_full_outputs_equal': True,
        'profile_arithmetic_verified': True, 'producer_reruns': 0, 'oracle_searches': 0,
        'scope': 'Saved output identity and profile arithmetic only; historical times not remeasured.'}
    write_atomic(output, result)
    return {k: v for k, v in result.items() if k != 'source_sha256'}


def main():
    """Separate frozen declaration, live measurement and saved replay."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'run', 'check'))
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(args.manifest.resolve())
    elif args.command == 'run':
        require(args.output is not None, '--output required')
        result = execute(args.manifest.resolve(), args.output.resolve())
    else:
        require(args.report is not None and args.output is not None, '--report and --output required')
        result = check(args.manifest.resolve(), args.report.resolve(), args.output.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

"""Freeze and compare an equivalent saturation implementation, without oracles.

All timed producers run sequentially in balanced AB/BA pairs. Full returned
JSON must equal the already audited archive, including legacy-equivalent work
counters. Actual prefilter work is measured separately on the recorded detector
inputs, avoiding telemetry overhead in either timed producer.
"""

from argparse import ArgumentParser
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from itertools import product
from math import isfinite
from pathlib import Path
from statistics import median
from time import perf_counter
from uuid import uuid4
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.check_quaternary_reachability import checksum
from scripts.check_quaternary_reachability_artifacts import same
from scripts.check_triangle_saturation_rule_soundness import rule_inventory
from scripts.quaternary_triangle_saturation import find_triangle_saturations
from scripts.quaternary_triangle_saturation_contacts import propagate_saturation_contacts
from scripts.quaternary_triangle_saturation_low_color import solve_triangle_saturation
from scripts.quaternary_triangle_saturation_prefilter import find_triangle_saturations_prefilter
from scripts.quaternary_triangle_saturation_prefilter_contacts import propagate_prefilter_contacts
from scripts.quaternary_triangle_saturation_prefilter_low_color import solve_prefilter_triangle_saturation
from scripts.check_quaternary_triangle_saturation_prefilter import check_prefilter_work
from scripts.validate_global_restart import digest
from scripts.validate_quaternary_contacts_v2 import read_report, require
from scripts.validate_quaternary_triangle_saturation_support import (
    sources as previous_sources, reference, bound_reference, write_atomic,
)

VERSION = 'quaternary-triangle-saturation-prefilter-experiment-v1'
PROTOCOL = 'docs/QUATERNARY_TRIANGLE_SATURATION_PREFILTER_PROTOCOL-2026-10-03.md'
ARCHIVES = {
    'production': ('outputs/quaternary-triangle-saturation-manifest-2026-10-01.json.gz',
                   'outputs/quaternary-triangle-saturation-2026-10-01.json.gz',
                   'outputs/quaternary-triangle-saturation-artifact-check-2026-10-01.json'),
    'support': ('outputs/quaternary-triangle-saturation-support-manifest-2026-10-03.json.gz',
                'outputs/quaternary-triangle-saturation-support-2026-10-03.json.gz',
                'outputs/quaternary-triangle-saturation-support-check-2026-10-03.json'),
}
INPUT_PATHS = tuple(p for paths in ARCHIVES.values() for p in paths)
NEW_SOURCES = tuple('scripts/' + name + '.py' for name in (
    'quaternary_triangle_saturation_prefilter', 'quaternary_triangle_saturation_prefilter_contacts',
    'quaternary_triangle_saturation_prefilter_low_color', 'check_quaternary_triangle_saturation_prefilter',
    'validate_quaternary_triangle_saturation_prefilter')) + tuple('tests/test_' + name + '.py' for name in (
    'quaternary_triangle_saturation_prefilter', 'quaternary_triangle_saturation_prefilter_contacts',
    'quaternary_triangle_saturation_prefilter_low_color', 'check_quaternary_triangle_saturation_prefilter',
    'validate_quaternary_triangle_saturation_prefilter')) + (PROTOCOL,)
RESOURCES = {'workers': 1, 'paired_repetitions': 2, 'decision_limit': 128, 'probe_limit': 8192,
             'oracle_searches': 0, 'rule_batch_size': 128}


class EquivalenceMismatch(AssertionError):
    """Carry the first differing full output so it is not lost on failure."""

    def __init__(self, expected, actual, context):
        super().__init__('full output equivalence failed: ' + str(context))
        self.evidence = {'expected': expected, 'actual': actual, 'context': context}


def equal_output(actual, expected, context):
    """Use strict JSON equality and preserve differing mathematical evidence."""
    try:
        same(actual, expected, 'full output equivalence')
    except AssertionError as error:
        raise EquivalenceMismatch(expected, actual, context) from error


def record_failure(directory, manifest_hash, context, error):
    """Save an exclusive failure artifact; it can never masquerade as success."""
    path = directory / ('failure-' + uuid4().hex + '.json.gz')
    write_atomic(path, {'manifest_sha256': manifest_hash, 'context': context,
                       'error': type(error).__name__ + ': ' + str(error),
                       'evidence': getattr(error, 'evidence', None), 'complete': False})


def inventory_counts(records):
    """Compute denominators from the frozen whole-drawing inventory."""
    return {'drawings': len(records), 'eligibility': dict(Counter(r['eligibility'] for r in records)),
            'scenes': sum(len(r['scenes']) for r in records),
            'diagnostics': sum(sum(r['diagnostic_counts'].values()) for r in records),
            'production_detector_calls': sum(s['detector_calls'] for r in records for s in r['scenes']),
            'rule_cases': len(rule_cases())}


def sources():
    """All 279 previous source bytes remain part of the reproducibility chain."""
    old = previous_sources()
    same(old, read_report(ROOT / ARCHIVES['support'][0])['source_sha256'], 'old source chain')
    return {**old, **{name: checksum(ROOT / name) for name in NEW_SOURCES}}


def archives():
    """Require prior completed evidence; false all-pair support is intentional."""
    out = {}
    for kind, paths in ARCHIVES.items():
        manifest, report, check = [read_report(ROOT / p) for p in paths]
        for saved in (report, check):
            same(saved['manifest_sha256'], checksum(ROOT / paths[0]), 'upstream manifest')
        same(check['report_sha256'], checksum(ROOT / paths[1]), 'upstream report')
        same(check['source_sha256'], manifest['source_sha256'], 'upstream sources')
        require(all(check.get(k) is True for k in ('passed', 'eligible_executions_complete',
                                                  'exact_queries_conclusive')), 'incomplete upstream')
        require(len(manifest['records']) == len(report['checkpoints']), 'upstream coverage')
        out[kind] = {'manifest': manifest, 'report': report, 'check': check,
                     'manifest_sha256': checksum(ROOT / paths[0])}
    same([r['key'] for r in out['production']['manifest']['records']],
         [r['key'] for r in out['support']['manifest']['records']], 'archive graph correspondence')
    for name in ARCHIVES['production']:
        same(out['support']['manifest']['input_sha256'][name], checksum(ROOT / name),
             'production ancestry of support scan')
    return out


def rule_cases():
    """Declare 1,512 old cases and 4,608 explicit gate/target-domain cases.

    Nine K4 quotient realizations (one literal K4 and eight target EQ lifts)
    each cross four excluded colors, eight neighbor exclusion masks, and all
    sixteen target domains. Some literal inputs repeat earlier cases; these
    are declaration references, never claims of distinct independent graphs.
    """
    rows = deepcopy(rule_inventory())
    templates = [r for r in rows if r['id'] == 'saturation-mask-3f-omit-1'
                 or (r['family'] == 'five-vertex-target-eq-lifts'
                     and r['domain_pattern'] == 'triangle-triple-target-full' and r['excluded_color'] == 1)]
    require(len(templates) == 9, 'rule template coverage')
    for number, template in enumerate(templates):
        for q, neighbors, target in product(range(1, 5), range(8), range(16)):
            domains = [[c for c in range(1, 5) if not (neighbors & (1 << i)) or c != q]
                       for i in range(3)]
            target_domain = [c for c in range(1, 5) if target & (1 << (c - 1))]
            domains += [list(target_domain) for _ in template['document']['sides'][3:]]
            rows.append({'id': f'gate-{number}-{q}-{neighbors}-{target}', 'family': 'gate-target-domain-cube',
                         'document': deepcopy(template['document']), 'domains': domains,
                         'equal_names': deepcopy(template['equal_names'])})
    return rows


def detector_inputs(result, *, producer):
    """Retain exact call order through all saved phases and saturation rounds."""
    outcomes = [p['outcome'] for p in result['run']['phases']] if producer else [result]
    calls = []
    for outcome in outcomes:
        for step in outcome['triangle_saturation']['rounds']:
            if step['triangle_check'] is not None:
                base = step['outcome']
                calls.append((step['document'], base['domains'], base['equal_names'], step['triangle_check']))
    return calls


def measure_work(result, *, producer):
    """Replay detector inputs only, outside timers; check each work certificate."""
    rows = []
    for document, domains, eq, expected in detector_inputs(result, producer=producer):
        log = []
        same(find_triangle_saturations_prefilter(document, domains, eq, work_log=log), expected,
             'recorded detector output differs')
        require(len(log) == 1, 'detector telemetry coverage')
        checked = check_prefilter_work(document, domains, eq, expected, log[0])
        rows.append({'telemetry': log[0], 'verification': checked})
    return rows


def check_work(result, rows, *, producer):
    """Saved verification calls no detector, propagator, or producer."""
    calls = detector_inputs(result, producer=producer)
    require(len(calls) == len(rows), 'work call coverage')
    for (document, domains, eq, evidence), row in zip(calls, rows):
        same(check_prefilter_work(document, domains, eq, evidence, row['telemetry']),
             row['verification'], 'saved work check')


def entries(saved, key, scenes):
    """Require every declared production scene, including preserved exclusions."""
    same(saved['row']['key'], key, 'production row key')
    selected = [e for e in saved['row']['runs'] if e['policy'] == 'triangle-saturation']
    same([e['scenario'] for e in selected], scenes, 'production scene coverage')
    require(all(e['execution'] == 'audited' for e in selected), 'unaudited producer')
    return selected


def diagnostic_part(saved):
    """Extract only full conditional records, excluding the large SAT pool."""
    return [{'scenario': e['scenario'], 'conditionals': e['scan']['conditional_records']}
            for e in saved['row']['runs'] if e['scan']['conditional_records']]


def prepare(path):
    """Bind all paired inputs before running either new implementation path."""
    require(not path.exists(), 'manifest exists')
    before, bundles = sources(), archives()
    inputs = {p: checksum(ROOT / p) for p in INPUT_PATHS}
    prod, support = bundles['production'], bundles['support']
    directory = path.parent / (path.name.removesuffix('.json.gz') + '-inputs')
    records = []
    compact = {r['key']: r for r in support['report']['summary']['compact_records']}
    for i, original in enumerate(prod['manifest']['records']):
        pref, sref = prod['report']['checkpoints'][i], support['report']['checkpoints'][i]
        saved = bound_reference(pref)
        same(saved['manifest_sha256'], prod['manifest_sha256'], 'production freeze')
        same(saved['record_sha256'], digest(original), 'production input')
        scenes = entries(saved, original['key'], [s['id'] for s in original['scenarios']])
        row = {'key': original['key'], 'eligibility': original['eligibility'],
               'production_reference': pref, 'production_record_sha256': digest(original),
               'support_reference': sref, 'support_record_sha256': digest(support['manifest']['records'][i]),
               'geometry': original['export']['geometry'] if original['eligibility'] == 'ready'
                   and original['original']['kind'] == 'geometry' else None,
               'scenes': [{'id': e['scenario'], 'raw_sha256': digest(e['raw_document']),
                           'envelope_sha256': digest(e['result']), 'audit_sha256': digest(e['audit']),
                           'detector_calls': len(detector_inputs(e['result'], producer=True))} for e in scenes],
               'diagnostic_part': None, 'diagnostic_counts': {}}
        expected = {e['scenario']: e['summary']['conditional_record_count']
                    for e in compact[row['key']]['runs'] if e['summary']['conditional_record_count']}
        if expected:
            ssaved = bound_reference(sref)
            same(ssaved['manifest_sha256'], support['manifest_sha256'], 'support freeze')
            same(ssaved['record_sha256'], row['support_record_sha256'], 'support input')
            part = {'upstream': sref, 'key': row['key'], 'scenes': diagnostic_part(ssaved)}
            same({e['scenario']: len(e['conditionals']) for e in part['scenes']}, expected, 'diagnostic coverage')
            pp = directory / (row['key'] + '.json.gz')
            if pp.exists():
                same(read_report(pp), part, 'existing input shard')
            else:
                write_atomic(pp, part)
            row['diagnostic_part'], row['diagnostic_counts'] = reference(pp), expected
        records.append(row)
        if (i + 1) % 50 == 0:
            print(json.dumps({'prepare_drawings': i + 1}), flush=True)
    rules = rule_cases()
    counts = inventory_counts(records)
    same([counts['drawings'], counts['scenes'], counts['diagnostics'], counts['rule_cases']],
         [537, 975, 1846, 6120], 'declared population')
    same(before, sources(), 'source drift during preparation')
    same(inputs, {p: checksum(ROOT / p) for p in INPUT_PATHS}, 'input drift')
    manifest = {'schema_version': 1, 'version': VERSION, 'source_sha256': before, 'input_sha256': inputs,
                'archive_hashes': {k: b['manifest_sha256'] for k, b in bundles.items()}, 'records': records,
                'resources': RESOURCES, 'counts': counts, 'rules_sha256': digest(rules),
                'histories': support['report']['summary']['histories'],
                'created_at_utc': datetime.now(timezone.utc).isoformat(),
                'producer_or_detector_runs_before_freeze': 0, 'oracle_searches_before_freeze': 0}
    write_atomic(path, manifest)
    return counts


def bound_manifest(path):
    """Bind sources, input census and saved geometry without recoloring."""
    m = read_report(path)
    same([m['schema_version'], m['version']], [1, VERSION], 'manifest schema')
    same(m['source_sha256'], sources(), 'source drift')
    same(m['input_sha256'], {p: checksum(ROOT / p) for p in INPUT_PATHS}, 'input drift')
    same(m['resources'], RESOURCES, 'resource drift')
    same(m['counts'], inventory_counts(m['records']), 'inventory counts')
    same(m['rules_sha256'], digest(rule_cases()), 'rule declaration')
    same([m['producer_or_detector_runs_before_freeze'], m['oracle_searches_before_freeze']], [0, 0], 'freeze activity')
    bundles = archives()
    same(m['archive_hashes'], {k: b['manifest_sha256'] for k, b in bundles.items()}, 'archive hashes')
    prod, support = bundles['production'], bundles['support']
    same([r['key'] for r in m['records']], [r['key'] for r in prod['manifest']['records']], 'drawing coverage')
    same(m['histories'], support['report']['summary']['histories'], 'history scope')
    compact_rows = {r['key']: r for r in support['report']['summary']['compact_records']}
    for i, row in enumerate(m['records']):
        old = prod['manifest']['records'][i]
        same(row['eligibility'], old['eligibility'], 'eligibility')
        same(row['production_reference'], prod['report']['checkpoints'][i], 'production origin')
        same(row['support_reference'], support['report']['checkpoints'][i], 'support origin')
        same(row['production_record_sha256'], digest(old), 'old production record')
        same(row['support_record_sha256'], digest(support['manifest']['records'][i]), 'old support record')
        same([s['id'] for s in row['scenes']], [s['id'] for s in old['scenarios']], 'scene census')
        geometry = old['export']['geometry'] if old['eligibility'] == 'ready' and old['original']['kind'] == 'geometry' else None
        same(row['geometry'], geometry, 'geometry substitution')
        expected_conditions = {e['scenario']: e['summary']['conditional_record_count']
            for e in compact_rows[row['key']]['runs'] if e['summary']['conditional_record_count']}
        same(row['diagnostic_counts'], expected_conditions, 'conditional census substitution')
        require((row['diagnostic_part'] is not None) == bool(expected_conditions), 'conditional shard missing')
    return m


def context(m, row, *, check_source_part=False):
    """Read production once per drawing; conditionals use small frozen shards."""
    saved = bound_reference(row['production_reference'])
    same(saved['manifest_sha256'], m['archive_hashes']['production'], 'production checkpoint freeze')
    same(saved['record_sha256'], row['production_record_sha256'], 'production checkpoint input')
    original = entries(saved, row['key'], [s['id'] for s in row['scenes']])
    for entry, scene in zip(original, row['scenes']):
        for value, key in ((entry['raw_document'], 'raw_sha256'), (entry['result'], 'envelope_sha256'),
                           (entry['audit'], 'audit_sha256')):
            same(digest(value), scene[key], 'scene bytes ' + key)
        same(len(detector_inputs(entry['result'], producer=True)), scene['detector_calls'], 'detector call census')
    diagnostics = {}
    if row['diagnostic_part'] is not None:
        part = bound_reference(row['diagnostic_part'])
        same([part['upstream'], part['key']], [row['support_reference'], row['key']], 'conditional origin')
        same({e['scenario']: len(e['conditionals']) for e in part['scenes']}, row['diagnostic_counts'], 'conditional counts')
        if check_source_part:
            ssaved = bound_reference(row['support_reference'])
            same(ssaved['manifest_sha256'], m['archive_hashes']['support'], 'support checkpoint freeze')
            same(ssaved['record_sha256'], row['support_record_sha256'], 'support checkpoint input')
            same(part['scenes'], diagnostic_part(ssaved), 'conditional source bodies')
        diagnostics = {e['scenario']: e['conditionals'] for e in part['scenes']}
    else:
        same(row['diagnostic_counts'], {}, 'missing conditional part')
    return original, diagnostics


def paired(old, new, expected, parity):
    """Time calls only; compare complete outputs after each call, outside timers."""
    timings, first_new = [], None
    expected_hash = digest(expected)
    for repeat in range(RESOURCES['paired_repetitions']):
        order = ['old', 'new'] if (repeat + parity) % 2 == 0 else ['new', 'old']
        record = {'repeat': repeat, 'order': order}
        for name in order:
            # Drop the preceding large trace outside the measured call. The
            # first new output remains intentionally retained for the artifact.
            outcome = None
            start = perf_counter()
            outcome = old() if name == 'old' else new()
            record[name + '_seconds'] = perf_counter() - start
            equal_output(outcome, expected, {'implementation': name, 'repeat': repeat, 'parity': parity})
            record[name + '_sha256'] = digest(outcome)
            same(record[name + '_sha256'], expected_hash, 'paired output hash')
            if name == 'new' and first_new is None:
                first_new = outcome
        timings.append(record)
    return first_new, timings


def verify_timing(timings, expected, parity):
    """Saved durations are nonnegative telemetry, not independently rerun clocks."""
    require(len(timings) == RESOURCES['paired_repetitions'], 'timing coverage')
    for repeat, row in enumerate(timings):
        same(sorted(row), sorted(('repeat', 'order', 'old_seconds', 'new_seconds', 'old_sha256', 'new_sha256')), 'timing fields')
        same(row['repeat'], repeat, 'timing repeat')
        same(row['order'], ['old', 'new'] if (repeat + parity) % 2 == 0 else ['new', 'old'], 'timing order')
        for name in ('old', 'new'):
            value = row[name + '_seconds']
            require(type(value) in (int, float) and isfinite(value) and value >= 0, 'invalid timing')
            same(row[name + '_sha256'], digest(expected), 'timing output identity')


def run_drawing(m, row, number):
    """Run fixed paired producers and all saved conditionals, never search colors."""
    original, diagnostics = context(m, row)
    runs = []
    for j, entry in enumerate(original):
        raw, geometry = entry['raw_document'], row['geometry']
        kwargs = {'geometry': geometry, 'decision_limit': RESOURCES['decision_limit'],
                  'probe_limit': RESOURCES['probe_limit']}
        result, timings = paired(lambda: solve_triangle_saturation(raw, **kwargs),
            lambda: solve_prefilter_triangle_saturation(raw, **kwargs), entry['result'], number + j)
        item = {'scenario': entry['scenario'], 'result': result, 'timings': timings,
                'work': measure_work(result, producer=True), 'diagnostics': []}
        for k, previous in enumerate(diagnostics.get(entry['scenario'], [])):
            document = previous['input']
            outcome, times = paired(lambda: propagate_saturation_contacts(document),
                lambda: propagate_prefilter_contacts(document), previous['outcome'], number + j + k)
            item['diagnostics'].append({'index': k, 'input_sha256': digest(document), 'outcome': outcome,
                                       'timings': times, 'work': measure_work(outcome, producer=False)})
        runs.append(item)
    return {'key': row['key'], 'runs': runs}


def verify_drawing(m, row, saved, number):
    """Bind complete new outputs to old proved inputs and verify actual-work claims."""
    original, diagnostics = context(m, row, check_source_part=True)
    same(saved['key'], row['key'], 'new checkpoint key')
    same([r['scenario'] for r in saved['runs']], [s['id'] for s in row['scenes']], 'saved scene coverage')
    for j, (entry, run) in enumerate(zip(original, saved['runs'])):
        same(run['result'], entry['result'], 'saved full producer equivalence')
        verify_timing(run['timings'], entry['result'], number + j)
        check_work(run['result'], run['work'], producer=True)
        old_conditions = diagnostics.get(entry['scenario'], [])
        require(len(run['diagnostics']) == len(old_conditions), 'saved conditional coverage')
        for k, (previous, new) in enumerate(zip(old_conditions, run['diagnostics'])):
            same([new['index'], new['input_sha256']], [k, digest(previous['input'])], 'conditional identity')
            same(new['outcome'], previous['outcome'], 'saved full conditional equivalence')
            verify_timing(new['timings'], previous['outcome'], number + j + k)
            check_work(new['outcome'], new['work'], producer=False)


def rule_batch(cases):
    """Compare literal rule inputs only after their generator/hash is frozen."""
    results = []
    for case in cases:
        args = case['document'], case['domains'], case['equal_names']
        baseline, log = find_triangle_saturations(*args), []
        new = find_triangle_saturations_prefilter(*args, work_log=log)
        equal_output(new, baseline, {'rule': case})
        require(len(log) == 1, 'rule telemetry coverage')
        results.append({'id': case['id'], 'input_sha256': digest(case), 'evidence': new,
                        'baseline_sha256': digest(baseline), 'telemetry': log[0],
                        'verification': check_prefilter_work(*args, new, log[0])})
    return results


def verify_rules(cases, rows):
    """Check saved rule evidence without either detector implementation."""
    require(len(cases) == len(rows), 'rule coverage')
    for case, row in zip(cases, rows):
        same([row['id'], row['input_sha256']], [case['id'], digest(case)], 'rule identity')
        same(row['baseline_sha256'], digest(row['evidence']), 'rule baseline equality')
        same(check_prefilter_work(case['document'], case['domains'], case['equal_names'],
                                 row['evidence'], row['telemetry']), row['verification'], 'rule work verification')


def compact(saved):
    """Collect only workload and paired timing records, leaving traces on disk."""
    out = {'production': [], 'diagnostics': []}
    for run in saved['runs']:
        for family, items in (('production', [run]), ('diagnostics', run['diagnostics'])):
            for item in items:
                counts = Counter()
                for work in item['work']:
                    counts.update(work['telemetry']['statistics'])
                out[family].append({'timings': item['timings'], 'detector_calls': len(item['work']),
                                    'statistics': dict(counts)})
    return out


def summary(compacts, rule_rows):
    """Report actual work separately from compatibility counters and timing."""
    out = {}
    for family in ('production', 'diagnostics'):
        items = [item for row in compacts for item in row[family]]
        counts = Counter()
        for item in items:
            counts.update(item['statistics'])
        repetitions = []
        for repeat in range(RESOURCES['paired_repetitions']):
            old = sum(i['timings'][repeat]['old_seconds'] for i in items)
            new = sum(i['timings'][repeat]['new_seconds'] for i in items)
            repetitions.append({'repeat': repeat, 'old_seconds': old, 'new_seconds': new,
                                'new_over_old': new / old if old else None})
        ratios = [median(t['new_seconds'] for t in i['timings']) / median(t['old_seconds'] for t in i['timings'])
                  for i in items if median(t['old_seconds'] for t in i['timings']) > 0]
        out[family] = {'items': len(items), 'detector_calls': sum(i['detector_calls'] for i in items),
                       'work': dict(counts), 'paired_repetitions': repetitions,
                       'median_item_ratio': median(ratios) if ratios else None}
    counts = Counter()
    for row in rule_rows:
        counts.update(row['telemetry']['statistics'])
    out['rules'] = {'cases': len(rule_rows), 'work': dict(counts),
                    'certificates': sum(len(r['evidence']['certificates']) for r in rule_rows)}
    return out


def execute(manifest_path, output):
    """Sequential timing with resumable drawing/rule shards and atomic writes."""
    require(not output.exists(), 'report exists')
    m = bound_manifest(manifest_path)
    mh = checksum(manifest_path)
    directory = output.parent / (output.name.removesuffix('.json.gz') + '-checkpoints')
    refs, compacts, resumed = [], [], 0
    start = perf_counter()
    for i, row in enumerate(m['records']):
        path = directory / f'{i:03d}-{row["key"][:12]}.json.gz'
        reused = path.exists()
        if reused:
            saved = read_report(path)
            same([saved['manifest_sha256'], saved['record_sha256']], [mh, digest(row)], 'resume binding')
            verify_drawing(m, row, saved['result'], i)
            resumed += 1
        else:
            try:
                result = run_drawing(m, row, i)
            except Exception as error:
                record_failure(directory, mh, {'drawing_index': i, 'record': row}, error)
                raise
            saved = {'manifest_sha256': mh, 'record_sha256': digest(row), 'result': result}
            write_atomic(path, saved)
        refs.append(reference(path))
        compacts.append(compact(saved['result']))
        print(json.dumps({'completed_drawings': i + 1, 'total': len(m['records']), 'resumed': reused}), flush=True)
    cases, rrefs, rrows = rule_cases(), [], []
    for begin in range(0, len(cases), RESOURCES['rule_batch_size']):
        batch = cases[begin:begin + RESOURCES['rule_batch_size']]
        path = directory / f'rules-{begin:05d}.json.gz'
        if path.exists():
            saved = read_report(path)
            same([saved['manifest_sha256'], saved['input_sha256']], [mh, digest(batch)], 'rule resume')
            verify_rules(batch, saved['rows'])
        else:
            try:
                result = rule_batch(batch)
            except Exception as error:
                record_failure(directory, mh, {'rule_begin': begin, 'inputs': batch}, error)
                raise
            saved = {'manifest_sha256': mh, 'input_sha256': digest(batch), 'rows': result}
            write_atomic(path, saved)
        rrefs.append(reference(path))
        rrows.extend(saved['rows'])
    same(m['source_sha256'], sources(), 'source drift during run')
    report = {'schema_version': 1, 'version': VERSION, 'manifest_sha256': mh,
              'checkpoints': refs, 'rule_checkpoints': rrefs, 'summary': summary(compacts, rrows),
              'execution': {'workers': 1, 'resumed_drawings': resumed, 'wall_seconds': perf_counter() - start,
                            'new_oracle_searches': 0, 'timing_scope': 'sequential producers only; telemetry replay outside timers'}}
    write_atomic(output, report)
    return report['summary']


def check(manifest_path, report_path, output):
    """Replay immutable outputs and work arithmetic only; never time new runs."""
    require(not output.exists(), 'check exists')
    m, report = bound_manifest(manifest_path), read_report(report_path)
    mh = checksum(manifest_path)
    same([report['schema_version'], report['version'], report['manifest_sha256']], [1, VERSION, mh], 'report identity')
    execution = report['execution']
    same(sorted(execution), sorted(('workers', 'resumed_drawings', 'wall_seconds', 'new_oracle_searches',
                                   'timing_scope')), 'execution fields')
    same([execution['workers'], execution['new_oracle_searches'], execution['timing_scope']],
         [1, 0, 'sequential producers only; telemetry replay outside timers'], 'execution declarations')
    require(type(execution['resumed_drawings']) is int and 0 <= execution['resumed_drawings'] <= len(m['records']),
            'resume count invalid')
    require(type(execution['wall_seconds']) in (int, float) and isfinite(execution['wall_seconds'])
            and execution['wall_seconds'] >= 0, 'wall timing invalid')
    require(len(report['checkpoints']) == len(m['records']), 'checkpoint coverage')
    compacts = []
    for i, (row, ref) in enumerate(zip(m['records'], report['checkpoints'])):
        saved = bound_reference(ref)
        same([saved['manifest_sha256'], saved['record_sha256']], [mh, digest(row)], 'checkpoint binding')
        verify_drawing(m, row, saved['result'], i)
        compacts.append(compact(saved['result']))
        if (i + 1) % 25 == 0:
            print(json.dumps({'checked_drawings': i + 1}), flush=True)
    cases, rrows = rule_cases(), []
    require(len(report['rule_checkpoints']) == (len(cases) + RESOURCES['rule_batch_size'] - 1) // RESOURCES['rule_batch_size'], 'rule shard coverage')
    for index, ref in enumerate(report['rule_checkpoints']):
        batch = cases[index * RESOURCES['rule_batch_size']:(index + 1) * RESOURCES['rule_batch_size']]
        saved = bound_reference(ref)
        same([saved['manifest_sha256'], saved['input_sha256']], [mh, digest(batch)], 'rule shard binding')
        verify_rules(batch, saved['rows'])
        rrows.extend(saved['rows'])
    same(report['summary'], summary(compacts, rrows), 'summary reconstruction')
    same(m['source_sha256'], sources(), 'source drift during saved check')
    result = {'passed': True, 'all_producer_outputs_exactly_equal': True,
              'all_conditional_outputs_exactly_equal': True, 'all_rule_evidence_verified': True,
              'all_actual_work_verified': True, 'manifest_sha256': mh, 'report_sha256': checksum(report_path),
              'source_sha256': sources(), 'summary': report['summary'],
              'producer_reruns': 0, 'propagation_reruns': 0, 'detector_reruns': 0, 'oracle_searches': 0,
              'scope': 'Saved equivalence/work audit; prior exact/production audits inherited by complete output identity. Timings not rerun.'}
    write_atomic(output, result)
    return {k: v for k, v in result.items() if k != 'source_sha256'}


def main():
    """Keep declaration, measured execution, and saved replay distinct."""
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
        require(args.report is not None and args.output is not None, '--report and --output required')
        result = check(args.manifest.resolve(), args.report.resolve(), args.output.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()

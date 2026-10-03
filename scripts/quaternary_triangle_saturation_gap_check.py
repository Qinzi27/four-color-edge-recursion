"""Replay all old joint-only negative trials against conditional triangle saturation.

This diagnostic retains raw base-SAT, singleton-SAT and pair-UNSAT proofs.
They are offline evidence, never premises for the propagation routine.
"""

from collections import Counter
from copy import deepcopy

from scripts.audit_quaternary_conditional_diamond import audit_diamond_contacts
from scripts.audit_quaternary_triangle_saturation import audit_saturation_contacts
from scripts.quaternary_triangle_saturation_contacts import propagate_saturation_contacts
from scripts.quaternary_conditional_diamond_gap_check import phase_metrics as diamond_phase_metrics
from scripts.quaternary_odd_wheel_gap_check import ROOT, bound_reference, _target
from scripts.check_quaternary_reachability import checksum
from scripts.check_quaternary_reachability_artifacts import same
from scripts.validate_global_restart import digest
from scripts.validate_quaternary_contacts_v2 import read_report, require

VERSION = 'quaternary-triangle-saturation-known-pair-diagnostics-v1'
MANIFEST = 'outputs/quaternary-conditional-diamond-manifest-2026-09-30.json.gz'
REPORT = 'outputs/quaternary-conditional-diamond-2026-09-30.json.gz'
CHECK = 'outputs/quaternary-conditional-diamond-artifact-check-2026-09-30.json'


def identity(key, target):
    """Identify the literal old trial, without substituting another hypothesis."""
    return (key, target['scenario'], target['state_index'], target['target_index'])


def gap_inventory():
    """Bind all saved previous diagnostics; no propagation or new search."""
    manifest, report, checked = [read_report(ROOT / p) for p in (MANIFEST, REPORT, CHECK)]
    require(all(checked[k] is True for k in ('passed', 'eligible_executions_complete',
                'exact_queries_conclusive', 'diagnostic_executions_complete')), 'old check incomplete')
    same(checked['manifest_sha256'], checksum(ROOT / MANIFEST), 'old check manifest')
    same(checked['report_sha256'], checksum(ROOT / REPORT), 'old check report')
    same(checked['source_sha256'], manifest['source_sha256'], 'old check sources')
    same(report['manifest_sha256'], checksum(ROOT / MANIFEST), 'old report manifest')
    saved = bound_reference(report['gap_evidence'])
    same(saved['manifest_sha256'], checksum(ROOT / MANIFEST), 'old diagnostic freeze')
    same(saved['result']['inventory_sha256'], digest(manifest['gap_inventory']), 'old targets binding')
    same([(r['key'], r['target']) for r in saved['result']['rows']],
         [(g['key'], t) for g in manifest['gap_inventory']['groups'] for t in g['targets']],
         'old diagnostic coverage')
    lookup = {identity(r['key'], r['target']): r for r in saved['result']['rows']}
    require(len(lookup) == len(saved['result']['rows']), 'duplicate diagnostic identity')
    groups, counts = [], Counter()
    for group in manifest['gap_inventory']['groups']:
        new_group = deepcopy(group)
        for item in new_group['targets']:
            previous = lookup[identity(group['key'], item)]
            require(previous['execution'] == 'checked', 'old diagnostic incomplete')
            item['diamond_baseline_status'] = previous['outcome']['status']
            item['diamond_baseline_outcome_sha256'] = digest(previous['outcome'])
            counts[item['diamond_baseline_status']] += 1
        groups.append(new_group)
    same(dict(counts), {'conflict': 1812, 'underdetermined': 2}, 'old diagnostic denominator')
    return {'version': VERSION, 'groups': groups, 'counts': dict(counts),
            'baseline_reference': report['gap_evidence'],
            'input_hashes': {p: checksum(ROOT / p) for p in (MANIFEST, REPORT, CHECK)},
            'propagation_runs_before_freeze': 0, 'oracle_searches_before_freeze': 0}


def baseline_lookup(inventory):
    """Load compact previous diagnostic outcomes once per replay."""
    rows = bound_reference(inventory['baseline_reference'])['result']['rows']
    lookup = {identity(r['key'], r['target']): r for r in rows}
    require(len(lookup) == len(rows), 'duplicate baseline trial')
    same(list(lookup), [identity(g['key'], t) for g in inventory['groups'] for t in g['targets']],
         'baseline identity coverage')
    return lookup


def bind_baseline(key, item, conditional, lookup):
    """Recheck the previous diamond proof on exactly the original trial input."""
    previous = lookup[identity(key, item)]
    expected = {k: v for k, v in item.items() if not k.startswith('diamond_baseline_')}
    same(previous['target'], expected, 'baseline original target')
    require(previous['execution'] == 'checked', 'baseline incomplete')
    outcome = previous['outcome']
    same([outcome['status'], digest(outcome)],
         [item['diamond_baseline_status'], item['diamond_baseline_outcome_sha256']], 'baseline outcome binding')
    same(audit_diamond_contacts(conditional['input'], outcome), previous['verification'], 'old diamond audit')
    return outcome


def phase_metrics(outcome):
    """Count every outer round and all nested diamond/wheel work references."""
    closure = outcome.get('triangle_saturation')
    if closure is None:
        return diamond_phase_metrics(outcome)
    rounds = closure['rounds']
    values = Counter(saturation_rounds=len(rounds),
                     saturation_added_rounds=len(rounds) - 1,
                     saturation_removed_candidates=len(closure['removed_candidates']))
    for step in rounds:
        values.update(diamond_phase_metrics(step['outcome']))
        check = step['triangle_check']
        values['triangle_checks'] += int(check is not None)
        values['triangle_certificates'] += len((check or {}).get('certificates', []))
        for key, number in (check or {}).get('statistics', {}).items():
            values['triangle_' + key] += number
    return dict(values)


def summarize(rows):
    """Separate newly refuted residuals, persistent cases and regressions."""
    counts, residuals, repairs = Counter(), [], []
    for row in rows:
        counts['targets'] += 1
        if row['execution'] != 'checked':
            counts['errors'] += 1
            continue
        counts['checked'] += 1
        old, new = row['target']['diamond_baseline_status'], row['outcome']['status']
        counts['new_' + new] += 1
        repaired = old == 'underdetermined' and new == 'conflict'
        counts['repaired'] += int(repaired)
        counts['persistent_inconclusive'] += int(old == 'underdetermined' and new != 'conflict')
        counts['regressions'] += int(old == 'conflict' and new != 'conflict')
        counts.update(phase_metrics(row['outcome']))
        if new != 'conflict':
            residuals.append({'key': row['key'], **row['target']})
        if repaired:
            repairs.append({'key': row['key'], **row['target'],
                            'removed_candidates': row['outcome']['triangle_saturation']['removed_candidates']})
    return {'counts': dict(counts), 'residuals': residuals, 'repairs': repairs}


def run_gaps(inventory):
    """Evaluate the frozen trials; never make a persistent producer commitment."""
    rows, lookup = [], baseline_lookup(inventory)
    for group in inventory['groups']:
        saved = bound_reference(group['reference'])
        for item in group['targets']:
            old = _target(saved, item)
            baseline = bind_baseline(group['key'], item, old, lookup)
            row = {'key': group['key'], 'target': item, 'execution': 'error'}
            try:
                outcome = propagate_saturation_contacts(deepcopy(old['input']))
                row['outcome'] = outcome
                row['verification'] = audit_saturation_contacts(old['input'], outcome)
                same(outcome['triangle_saturation']['rounds'][0]['outcome'], baseline, 'first round differs')
                require(outcome['status'] != 'solved', 'solved contradicts raw UNSAT')
                row['execution'] = 'checked'
            except Exception as error:
                row['error'] = f'{type(error).__name__}: {error}'
            rows.append(row)
    return {'version': VERSION, 'inventory_sha256': digest(inventory), 'rows': rows,
            'summary': summarize(rows), 'oracle_searches': 0, 'producer_runs': 0,
            'scope': 'Old-path negative pair diagnostics; not a census of new-policy candidates.'}


def check_saved_gaps(inventory, result):
    """Independently verify saved conditional batches without any new searches."""
    same(result['version'], VERSION, 'diagnostic version')
    same(result['inventory_sha256'], digest(inventory), 'diagnostic freeze')
    same([(r['key'], r['target']) for r in result['rows']],
         [(g['key'], t) for g in inventory['groups'] for t in g['targets']], 'target coverage')
    same([result['oracle_searches'], result['producer_runs']], [0, 0], 'diagnostic isolation')
    offset, lookup = 0, baseline_lookup(inventory)
    for group in inventory['groups']:
        saved = bound_reference(group['reference'])
        for item in group['targets']:
            row = result['rows'][offset]
            offset += 1
            old = _target(saved, item)
            baseline = bind_baseline(group['key'], item, old, lookup)
            if row['execution'] != 'checked':
                require(row['execution'] == 'error' and isinstance(row.get('error'), str), 'invalid error row')
                continue
            same(audit_saturation_contacts(old['input'], row['outcome']), row['verification'], 'triangle saturation replay')
            same(row['outcome']['triangle_saturation']['rounds'][0]['outcome'], baseline, 'first round differs')
            require(row['outcome']['status'] != 'solved', 'saved solved contradicts raw UNSAT')
    same(result['summary'], summarize(result['rows']), 'diagnostic summary')
    return {'passed': True, 'complete': result['summary']['counts'].get('errors', 0) == 0,
            **result['summary'], 'propagation_reruns': 0, 'oracle_search_reruns': 0}

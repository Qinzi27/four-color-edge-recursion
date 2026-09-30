"""Compare the new rule on every previously saved unsupported pair trial.

The targets are a diagnostic regression set, not an online choice policy.
Only the declared propagation function runs here; old exact evidence is
verified, never searched again or supplied to a producer as a premise.
"""

from collections import Counter
from copy import deepcopy
from pathlib import Path

from scripts.audit_quaternary_logical_neq import audit_logical_contacts
from scripts.audit_quaternary_odd_wheel import audit_wheel_contacts
from scripts.check_quaternary_reachability import checksum
from scripts.check_quaternary_reachability_artifacts import same
from scripts.exact_extendibility_oracle import verify_exact_result
from scripts.quaternary_logical_neq_contacts import MODEL as BASE_MODEL
from scripts.quaternary_odd_wheel_contacts import propagate_wheel_contacts
from scripts.validate_global_restart import digest
from scripts.validate_quaternary_contacts_v2 import read_report, require


ROOT = Path(__file__).resolve().parents[1]
VERSION = 'quaternary-odd-wheel-known-pair-diagnostics-v1'
MANIFEST = 'outputs/quaternary-logical-neq-pair-scan-manifest-2026-09-29.json.gz'
REPORT = 'outputs/quaternary-logical-neq-pair-scan-2026-09-29.json.gz'
CHECK = 'outputs/quaternary-logical-neq-pair-scan-check-2026-09-29.json'


def bound_reference(reference):
    """Read a portable evidence reference only after checking its exact bytes."""
    path = (ROOT / reference['path']).resolve()
    require(path.is_relative_to(ROOT / 'outputs'), 'gap evidence outside outputs')
    same(checksum(path), reference['sha256'], 'gap source checkpoint hash differs')
    return read_report(path)


def gap_inventory():
    """Freeze all 1814 old negative trials without running propagation/search.

    The prior successful check binds the full 673002-record archive. This
    preparation binds those exact artifacts and every checkpoint; execution
    additionally replays the exact evidence used by each selected trial.
    """
    manifest, report, checked = [read_report(ROOT / p) for p in (MANIFEST, REPORT, CHECK)]
    require(checked['passed'] is True and checked['eligible_executions_complete'] is True
            and checked['exact_queries_conclusive'] is True, 'incomplete upstream evidence')
    same(checked['manifest_sha256'], checksum(ROOT / MANIFEST), 'upstream check manifest')
    same(checked['report_sha256'], checksum(ROOT / REPORT), 'upstream check report')
    same(report['manifest_sha256'], checksum(ROOT / MANIFEST), 'upstream report manifest')
    same(checked['source_sha256'], manifest['source_sha256'], 'upstream check sources')
    require(len(report['checkpoints']) == len(manifest['records']), 'old checkpoint coverage')
    groups, counts = [], Counter()
    for record, reference in zip(manifest['records'], report['checkpoints']):
        saved = bound_reference(reference)
        same(saved['manifest_sha256'], checksum(ROOT / MANIFEST), 'old pair freeze')
        same(saved['record_sha256'], digest(record), 'old pair record binding')
        row = saved['row']
        same([row['key'], row['eligibility']], [record['key'], record['eligibility']], 'old identity')
        same([r['scenario'] for r in row['runs']], [s['id'] for s in record['scenarios']], 'old scenarios')
        targets = []
        for run in row['runs']:
            require(run['execution'] == 'checked', 'old pair run incomplete')
            for state in run['scan']['states']:
                for number, target in enumerate(state['targets']):
                    if target['status'] != 'unsupported':
                        continue
                    conditional = target['conditional']
                    require(target['single_support'] == 'both_supported', 'endpoint evidence missing')
                    item = {'scenario': run['scenario'], 'state_index': state['state_index'],
                            'target_index': number, 'phase': state['phase'],
                            'sides': target['sides'], 'symbols': target['symbols'],
                            'old_status': conditional['status'],
                            'input_sha256': digest(conditional['input']),
                            'old_outcome_sha256': digest(conditional['outcome'])}
                    targets.append(item)
                    counts[conditional['status']] += 1
        if targets:
            groups.append({'key': row['key'], 'reference': reference, 'targets': targets})
    same(dict(counts), {'conditional_refuted': 1803, 'conditional_inconclusive': 11},
         'predeclared old pair denominator differs')
    return {'version': VERSION, 'groups': groups, 'counts': dict(counts),
            'input_hashes': {p: checksum(ROOT / p) for p in (MANIFEST, REPORT, CHECK)},
            'propagation_runs_before_freeze': 0, 'oracle_searches_before_freeze': 0}


def _target(saved, item):
    """Reconstruct literal raw premises and replay all four old query roles."""
    matches = [r for r in saved['row']['runs'] if r['scenario'] == item['scenario']]
    require(len(matches) == 1, 'missing diagnostic scenario')
    scan = matches[0]['scan']
    state = scan['states'][item['state_index']]
    target = state['targets'][item['target_index']]
    conditional = target['conditional']
    same([state['state_index'], state['phase'], target['sides'], target['symbols']],
         [item['state_index'], item['phase'], item['sides'], item['symbols']], 'gap identity')
    require(target['status'] == 'unsupported' and target['single_support'] == 'both_supported',
            'diagnostic is not a saved joint-only negative')
    same(conditional['status'], item['old_status'], 'old conditional status')
    same(digest(conditional['input']), item['input_sha256'], 'conditional input changed')
    same(digest(conditional['outcome']), item['old_outcome_sha256'], 'old outcome changed')
    old_audit = audit_logical_contacts(conditional['input'], conditional['outcome'])
    same(old_audit, conditional['trace_audit'], 'old conditional replay differs')
    raw = scan['raw_document']
    sides = raw['sides']
    position = {s: i for i, s in enumerate(sides)}
    edges = sorted({tuple(sorted((position[e['left']], position[e['right']])))
                    for e in raw['lines'] if e['kind'] == 'separator'})
    fixed = dict(state['anchors'])
    extra = dict(zip((position[s] for s in target['sides']), target['symbols']))
    roles = [(state['base_oracle_index'], fixed, 'sat'),
             (target['pair_oracle_index'], {**fixed, **extra}, 'unsat')]
    require(len(target['single_oracle_indices']) == 2, 'single query coverage')
    roles.extend((reference, {**fixed, vertex: color}, 'sat') for reference, (vertex, color)
                 in zip(target['single_oracle_indices'], extra.items()))
    for reference, anchors, status in roles:
        evidence = scan['oracle_records'][reference]
        same(evidence['input'], {'n': len(sides), 'edges': [list(e) for e in edges],
                                'anchors': [list(p) for p in sorted(anchors.items())]}, 'raw query premises')
        same(evidence['result']['status'], status, 'old query status')
        verified = verify_exact_result(len(sides), edges, anchors, evidence['result'])
        same(verified, evidence['verification'], 'old exact proof replay differs')
    return conditional


def _base_outcome(outcome):
    """The added rule must leave the complete frozen binary closure unchanged."""
    base = deepcopy(outcome)
    base['status'] = base.pop('base_status')
    base.pop('wheel_check')
    base['model'] = BASE_MODEL
    return base


def summarize(rows):
    """Report old repaired/persistent negatives separately from execution errors."""
    counts = Counter()
    residuals = []
    for row in rows:
        counts['targets'] += 1
        if row['execution'] != 'checked':
            counts['errors'] += 1
            continue
        counts['checked'] += 1
        new_status = row['outcome']['status']
        old_status = row['target']['old_status']
        counts['new_' + new_status] += 1
        counts['repaired'] += int(old_status == 'conditional_inconclusive' and new_status == 'conflict')
        counts['persistent_inconclusive'] += int(old_status == 'conditional_inconclusive' and new_status != 'conflict')
        counts['regressions'] += int(old_status == 'conditional_refuted' and new_status != 'conflict')
        check = row['outcome']['wheel_check']
        counts['wheel_checks'] += int(check is not None)
        counts['wheel_certificates'] += int(bool(check and check['certificate']))
        counts['wheel_edges_examined'] += (check or {}).get('statistics', {}).get('edges_examined', 0)
        if new_status != 'conflict':
            residuals.append({'key': row['key'], **row['target']})
    return {'counts': dict(counts), 'residuals': residuals}


def run_gaps(inventory):
    """Run independent trial documents without making any actual commitments."""
    rows = []
    for group in inventory['groups']:
        saved = bound_reference(group['reference'])
        for item in group['targets']:
            old = _target(saved, item)
            row = {'key': group['key'], 'target': item, 'execution': 'error'}
            try:
                outcome = propagate_wheel_contacts(deepcopy(old['input']))
                row['outcome'] = outcome
                row['verification'] = audit_wheel_contacts(old['input'], outcome)
                same(_base_outcome(outcome), old['outcome'], 'base binary closure changed')
                require(outcome['status'] != 'solved', 'solved contradicts raw UNSAT')
                row['execution'] = 'checked'
            except Exception as error:
                row['error'] = f'{type(error).__name__}: {error}'
            rows.append(row)
    return {'version': VERSION, 'inventory_sha256': digest(inventory), 'rows': rows,
            'summary': summarize(rows), 'oracle_searches': 0, 'producer_runs': 0,
            'scope': 'Saved old-path negative trials only; not a candidate census of new producer states.'}


def check_saved_gaps(inventory, result):
    """Recheck saved proofs, coverage and classifications without propagation."""
    same(result['version'], VERSION, 'diagnostic version')
    same(result['inventory_sha256'], digest(inventory), 'diagnostic freeze')
    expected = [(g['key'], item) for g in inventory['groups'] for item in g['targets']]
    same([(r['key'], r['target']) for r in result['rows']], expected, 'diagnostic target coverage')
    same([result['oracle_searches'], result['producer_runs']], [0, 0], 'diagnostic isolation')
    offset = 0
    for group in inventory['groups']:
        saved = bound_reference(group['reference'])
        for item in group['targets']:
            row = result['rows'][offset]
            offset += 1
            old = _target(saved, item)
            if row['execution'] != 'checked':
                require(row['execution'] == 'error' and isinstance(row.get('error'), str), 'invalid error row')
                continue
            same(audit_wheel_contacts(old['input'], row['outcome']), row['verification'], 'wheel replay')
            same(_base_outcome(row['outcome']), old['outcome'], 'base binary closure changed')
            require(row['outcome']['status'] != 'solved', 'saved solved contradicts raw UNSAT')
    same(result['summary'], summarize(result['rows']), 'diagnostic summary')
    return {'passed': True, 'complete': result['summary']['counts'].get('errors', 0) == 0,
            **result['summary'], 'propagation_reruns': 0, 'oracle_search_reruns': 0}

"""Independently replay saved two-face support evidence without any search.

The enclosing experiment audits the frozen producer and its learned relation
proofs. Here the old independent event-chain checker is reused, but pair
inventory reconstruction is literal and independent of the pair scanner.
All exact premises are physical separator edges and actual anchors plus the
specified one or two hypothetical assignments. Learned relations are retained
only when replaying an unsupported pair's saved conditional propagation.
"""

from copy import deepcopy

from scripts.audit_quaternary_logical_neq import audit_logical_contacts
from scripts.check_quaternary_logical_neq_candidate_scan import (
    _integer, _persistent_states, _require, _same,
)
from scripts.exact_extendibility_oracle import verify_exact_result
from scripts.validate_quaternary_contacts_v2 import check_matrix


VERSION = 'quaternary-logical-neq-pair-scan-v1'
CHECK_VERSION = 'quaternary-logical-neq-pair-scan-saved-check-v1'
# Scope strings are an explicit, checked component of the evidence contract.
INVENTORY_SCOPE = ('Initial phase and every persistent event after-phase; rejected trial phases '
                   'excluded; both endpoints unresolved; i < j; only saved final binary-relation '
                   'pairs within the endpoint domains.')
SCOPE = ('Offline joint support of retained two-face candidates in a frozen run; exact queries '
         'use original separator edges and actual commitments only. Including the next chosen '
         'literal is not a joint commitment; UNKNOWN is not UNSAT.')
CATEGORIES = ('both_min', 'one_min', 'neither_min')
ACTIONS = ('includes_next_commit', 'includes_next_reject', 'not_next_choice')
TARGET_STATUSES = ('supported', 'unsupported', 'unknown', 'preexisting_unsat')
EXACT_STATUSES = ('sat', 'unsat', 'unknown')
SINGLE_SUPPORT = ('both_supported', 'has_unsupported_single', 'unknown_single')


def _inventory(document, run):
    """List retained directed color pairs only once, with side indices i < j.

    The full matrix is checked before inspecting bits. In particular a domain
    Cartesian product is not a retained pair relation, and reversing the bit
    order silently changes which face receives which hypothetical color.
    """
    sides, index, snapshots = _persistent_states(document, run)
    states, events, n = [], run['events'], len(sides)
    for state_index, (phase_number, after_event, committed) in enumerate(snapshots):
        next_event = state_index if state_index < len(events) else None
        event = events[next_event] if next_event is not None else None
        outcome = run['phases'][phase_number]['outcome']
        domains, matrix = outcome['domains'], outcome['relations']
        check_matrix(matrix, n, 'persistent pair relation matrix')
        for i, domain in enumerate(domains):
            _same(matrix[i][i], sum(1 << (5 * (color - 1)) for color in domain),
                  'persistent relation diagonal and domain')
            for j, other in enumerate(domains):
                allowed = sum(1 << (4 * (a - 1) + b - 1) for a in domain for b in other)
                _require(matrix[i][j] & ~allowed == 0,
                         'persistent relation contains a color outside its domain')
        targets, pair_count, cartesian_count = [], 0, 0
        for i in range(n):
            if len(domains[i]) <= 1:
                continue
            for j in range(i + 1, n):
                if len(domains[j]) <= 1:
                    continue
                pair_count += 1
                cartesian_count += len(domains[i]) * len(domains[j])
                for a in domains[i]:
                    for b in domains[j]:
                        if not matrix[i][j] & (1 << (4 * (a - 1) + b - 1)):
                            continue
                        minimum_count = int(a == min(domains[i])) + int(b == min(domains[j]))
                        category = ('neither_min', 'one_min', 'both_min')[minimum_count]
                        includes_next = event is not None and (
                            (event['side'] == sides[i] and event['symbol'] == a)
                            or (event['side'] == sides[j] and event['symbol'] == b))
                        action = (('includes_next_commit' if event['kind'] == 'commit'
                                   else 'includes_next_reject') if includes_next
                                  else 'not_next_choice')
                        targets.append({'side_indices': [i, j], 'sides': [sides[i], sides[j]],
                                        'symbols': [a, b], 'category': category,
                                        'next_action': action})
        states.append({'state_index': state_index, 'phase': phase_number,
                       'after_event_index': after_event,
                       'anchors': [[v, c] for v, c in sorted(committed.items())],
                       'next_event_index': next_event, 'propagation_status': outcome['status'],
                       'eligible_side_pair_count': pair_count,
                       'cartesian_target_count': cartesian_count, 'targets': targets})
    return {'states': states, 'scope': INVENTORY_SCOPE}, sides, index


def _summary(states, records):
    """Recount pair support separately from next-action membership and singles."""
    summary = {
        'state_count': len(states), 'target_count': 0, 'no_target_state_count': 0,
        'eligible_side_pair_count': 0, 'cartesian_target_count': 0,
        'base_status_counts': dict.fromkeys(EXACT_STATUSES, 0),
        'target_status_counts': dict.fromkeys(TARGET_STATUSES, 0),
        'category_counts': {key: dict.fromkeys(TARGET_STATUSES, 0) for key in CATEGORIES},
        'next_action_counts': {key: dict.fromkeys(TARGET_STATUSES, 0) for key in ACTIONS},
        'conditional_counts': {'conditional_refuted': 0, 'conditional_inconclusive': 0},
        'single_support_counts': dict.fromkeys(SINGLE_SUPPORT, 0),
        'unsupported_state_count': 0, 'oracle_record_count': len(records),
        'oracle_status_counts': dict.fromkeys(EXACT_STATUSES, 0),
    }
    for record in records:
        summary['oracle_status_counts'][record['result']['status']] += 1
    for state in states:
        base = records[state['base_oracle_index']]['result']['status']
        summary['base_status_counts'][base] += 1
        summary['target_count'] += len(state['targets'])
        summary['no_target_state_count'] += int(not state['targets'])
        summary['eligible_side_pair_count'] += state['eligible_side_pair_count']
        summary['cartesian_target_count'] += state['cartesian_target_count']
        summary['unsupported_state_count'] += int(any(
            target['status'] == 'unsupported' for target in state['targets']))
        for target in state['targets']:
            status = target['status']
            summary['target_status_counts'][status] += 1
            summary['category_counts'][target['category']][status] += 1
            summary['next_action_counts'][target['next_action']][status] += 1
            if target['conditional'] is not None:
                summary['conditional_counts'][target['conditional']['status']] += 1
                summary['single_support_counts'][target['single_support']] += 1
    return summary


def check_pair_scan(document, run, scan, *, node_limit=200000):
    """Bind complete saved pair coverage and replay certificates with no search.

    A SAT witness for one endpoint alone cannot support a joint assignment.
    Nor can a valid result obtained from a stronger inferred premise certify
    the requested raw problem. Every cached query must be used and unique.
    """
    _integer(node_limit, 'node limit')
    inventory, sides, index = _inventory(document, run)
    _require(isinstance(scan, dict) and set(scan) == {
        'schema_version', 'version', 'raw_document', 'inventory', 'node_limit', 'states',
        'oracle_records', 'summary', 'oracle_feedback_to_producer', 'scope'},
        'unexpected or missing pair scan fields')
    _same(scan['schema_version'], 1, 'scan schema version')
    _same(scan['version'], VERSION, 'scan version')
    _same(scan['raw_document'], document, 'scan original raw input')
    _same(scan['inventory'], inventory, 'complete retained pair inventory')
    _same(scan['node_limit'], node_limit, 'scan node limit')
    _same(scan['scope'], SCOPE, 'scan scope')
    _require(scan['oracle_feedback_to_producer'] is False, 'offline evidence fed back to producer')
    edges = sorted({tuple(sorted((index[line['left']], index[line['right']])))
                    for line in document['lines'] if line['kind'] == 'separator'})
    records, signatures = scan['oracle_records'], set()
    _require(isinstance(records, list), 'oracle records must be an array')
    for record in records:
        _require(isinstance(record, dict) and set(record) == {'input', 'result', 'verification'},
                 'unexpected saved oracle record fields')
        data = record['input']
        _require(isinstance(data, dict) and set(data) == {'n', 'edges', 'anchors'},
                 'oracle input contains non-raw premises')
        _same(data['n'], len(sides), 'oracle side count')
        _same(data['edges'], [list(edge) for edge in edges], 'oracle original separator edges')
        anchors, fixed = data['anchors'], {}
        _require(isinstance(anchors, list), 'oracle anchors must be an ordered array')
        for pair in anchors:
            _require(isinstance(pair, list) and len(pair) == 2, 'invalid oracle anchor pair')
            vertex, color = pair
            _require(type(vertex) is int and 0 <= vertex < len(sides)
                     and type(color) is int and color in (1, 2, 3, 4),
                     'invalid oracle anchor literal')
            _require(vertex not in fixed, 'duplicate oracle anchor')
            fixed[vertex] = color
        _same(anchors, [[v, c] for v, c in sorted(fixed.items())], 'canonical oracle anchor order')
        signature = tuple(sorted(fixed.items()))
        _require(signature not in signatures, 'duplicate exact query record')
        signatures.add(signature)
        _same(record['result']['node_limit'], node_limit, 'oracle record node limit')
        verification = verify_exact_result(len(sides), edges, fixed, record['result'])
        _same(record['verification'], verification, 'saved exact certificate verification')

    referenced, conditional_probes, conditional_trace_steps, singles_checked = set(), 0, 0, 0

    def evidence(reference, expected_fixed):
        """Only the precise original commitments and hypotheses bind a query."""
        _integer(reference, 'oracle reference')
        _require(reference < len(records), 'oracle reference outside saved records')
        record = records[reference]
        _same(record['input']['anchors'], [[v, c] for v, c in sorted(expected_fixed.items())],
              'actual commitment and pair/single binding')
        referenced.add(reference)
        return record['result']['status']

    states = scan['states']
    _require(isinstance(states, list) and len(states) == len(inventory['states']),
             'missing or extra persistent scan state')
    for expected_state, state in zip(inventory['states'], states):
        _require(isinstance(state, dict) and set(state) == set(expected_state) | {'base_oracle_index'},
                 'unexpected persistent scan state fields')
        for field in set(expected_state) - {'targets'}:
            _same(state[field], expected_state[field], 'persistent scan ' + field)
        base_fixed = dict(expected_state['anchors'])
        base_status = evidence(state['base_oracle_index'], base_fixed)
        targets = state['targets']
        _require(isinstance(targets, list) and len(targets) == len(expected_state['targets']),
                 'missing or extra retained pair target')
        for expected_target, target in zip(expected_state['targets'], targets):
            _require(isinstance(target, dict) and set(target) == set(expected_target)
                     | {'pair_oracle_index', 'status', 'conditional',
                        'single_oracle_indices', 'single_support'},
                     'unexpected retained pair target fields')
            for field in expected_target:
                _same(target[field], expected_target[field], 'retained pair target ' + field)
            fixed = dict(base_fixed)
            fixed.update(zip(target['side_indices'], target['symbols']))
            trial_status = evidence(target['pair_oracle_index'], fixed)
            status = ('preexisting_unsat' if base_status == 'unsat' else
                      'unknown' if 'unknown' in (base_status, trial_status) else
                      'unsupported' if trial_status == 'unsat' else 'supported')
            _same(target['status'], status, 'pair support classification')
            conditional = target['conditional']
            if status != 'unsupported':
                _require(conditional is None and target['single_oracle_indices'] is None
                         and target['single_support'] is None,
                         'unsupported-only diagnostics attached to another target status')
                continue
            single_refs = target['single_oracle_indices']
            _require(isinstance(single_refs, list) and len(single_refs) == 2,
                     'missing unsupported pair single-endpoint evidence')
            single_statuses = []
            for vertex, color, reference in zip(
                    target['side_indices'], target['symbols'], single_refs):
                single_fixed = dict(base_fixed)
                single_fixed[vertex] = color
                single_statuses.append(evidence(reference, single_fixed))
                singles_checked += 1
            single_support = ('has_unsupported_single' if 'unsat' in single_statuses else
                              'unknown_single' if 'unknown' in single_statuses else 'both_supported')
            _same(target['single_support'], single_support, 'single-endpoint support classification')
            _require(isinstance(conditional, dict)
                     and set(conditional) == {'input', 'outcome', 'trace_audit', 'status'},
                     'missing unsupported pair conditional evidence')
            trial_input = deepcopy(run['phases'][state['phase']]['document'])
            trial_input.setdefault('anchors', {}).update(zip(target['sides'], target['symbols']))
            _same(conditional['input'], trial_input, 'conditional persistent phase and pair premise')
            trace_check = audit_logical_contacts(trial_input, conditional['outcome'])
            _same(conditional['trace_audit'], trace_check, 'conditional saved trace audit')
            _require(conditional['outcome']['status'] in ('conflict', 'underdetermined'),
                     'unsupported raw pair cannot have a complete conditional coloring')
            conditional_status = ('conditional_refuted' if conditional['outcome']['status'] == 'conflict'
                                  else 'conditional_inconclusive')
            _same(conditional['status'], conditional_status, 'conditional rejection classification')
            conditional_probes += 1
            conditional_trace_steps += trace_check['trace_steps_checked']
    _require(referenced == set(range(len(records))), 'hidden unused oracle evidence')
    summary = _summary(states, records)
    _same(scan['summary'], summary, 'complete pair scan summary')
    return {'passed': True, 'check_version': CHECK_VERSION, 'summary': summary,
            'persistent_states_checked': len(states), 'target_count': summary['target_count'],
            'oracle_records': len(records), 'oracle_statuses': summary['oracle_status_counts'],
            'conditional_probes_checked': conditional_probes,
            'conditional_trace_steps_checked': conditional_trace_steps,
            'single_endpoint_queries_checked': singles_checked,
            'producer_runs': 0, 'oracle_searches': 0, 'propagation_runs': 0}

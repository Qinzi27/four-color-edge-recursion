"""Scan raw single and pair support after a saved saturation run has stopped.

The source pools contain archived evidence, not extra mathematical premises.
Exact queries use only original physical separator edges and actual anchors.
The scanner shares raw queries across base/single/pair obligations and replays
only certificates actually used. Conditional diagnostics are local, cached by
complete input, and never become producer choices or persistent commitments.
"""

from copy import deepcopy

from scripts.audit_quaternary_geometry import _same
from scripts.audit_quaternary_logical_neq import logical_metadata
from scripts.audit_quaternary_triangle_saturation import audit_saturation_contacts
from scripts.exact_extendibility_oracle import solve_exact, verify_exact_result
from scripts.quaternary_triangle_saturation_contacts import propagate_saturation_contacts
from scripts.validate_global_restart import digest
from scripts.validate_quaternary_contacts_v2 import check_domains, check_matrix, raw_metadata, require

VERSION = 'quaternary-triangle-saturation-support-scan-v1'
INVENTORY_SCOPE = ('Initial and every actual persistent after-phase; unresolved single candidates '
                   'and matrix-allowed unordered face pairs; rejected trial phases excluded.')
SCOPE = ('Offline support census of saved triangle-saturation states; exact premises are original '
         'separator edges and actual commitments plus hypotheses only; no oracle feedback to production.')
SINGLE_CATEGORIES = ('scheduled_min', 'same_side_other', 'other_side_min', 'other_side_other')
SINGLE_ACTIONS = ('actual_commit', 'actual_rejected_trial', 'not_selected')
PAIR_CATEGORIES = ('both_min', 'one_min', 'neither_min')
PAIR_ACTIONS = ('includes_next_commit', 'includes_next_reject', 'not_next_choice')
TARGET_STATUSES = ('supported', 'unsupported', 'unknown', 'preexisting_unsat')
ORACLE_STATUSES = ('sat', 'unsat', 'unknown')
CONDITIONAL_STATUSES = ('conditional_refuted', 'conditional_inconclusive')
SINGLE_SUPPORT_STATUSES = ('both_supported', 'has_unsupported_single', 'unknown_single')


def _single_inventory(document, run):
    """Reconstruct persistent states and their candidate obligations in order.

    This validates event continuity and exact document changes without running
    the producer or oracle. Independent trace, EQ/NEQ and geometric schedule
    validation remain the accompanying frozen-run auditor's responsibility.
    A resource-limited terminal state is still included; without a next actual
    event its candidates are classified as other-side, not as scheduled.
    """
    sides, _, _ = raw_metadata(document)
    require(not document.get('states') and not document.get('equal_names')
            and 'different_names' not in document,
            'candidate scan requires original NEQ and anchors only')
    index = {side: number for number, side in enumerate(sides)}
    require(type(run.get('schema_version')) is int and run['schema_version'] == 1
            and run.get('policy') == 'quaternary-low-color-triangle-saturation-conditional-v1',
            'candidate scan requires an unwrapped frozen low-color run')
    require(run.get('probe') is True and run.get('oracle_feedback_to_producer') is False
            and run.get('old_colors_read') is False and type(run.get('backtracks')) is int
            and run['backtracks'] == 0, 'invalid frozen production mode')
    original = run['original_input']
    logical_metadata(original)
    _same({key: value for key, value in original.items() if key not in ('equal_names', 'different_names')},
          {key: value for key, value in document.items() if key not in ('equal_names', 'different_names')},
          'producer differs from raw input beyond learned EQ/NEQ')
    phases, events = run['phases'], run['events']
    require(isinstance(phases, list) and bool(phases) and isinstance(events, list),
            'missing producer phases or events')
    require(phases[0]['kind'] == 'main', 'initial phase is not persistent')
    _same(phases[0]['document'], original, 'initial producer phase')
    committed = {index[side]: color for side, color in document.get('anchors', {}).items()}
    persistent = [(0, None, deepcopy(committed))]
    current, consumed = 0, 1

    def phase_check(number, expected_document):
        """Bind exact phase assumptions and their recorded domain identities."""
        require(type(number) is int and 0 <= number < len(phases), 'invalid phase index')
        phase = phases[number]
        logical_metadata(phase['document'])
        _same(phase['document'], expected_document, 'persistent/trial phase assumptions')
        _same(phase['outcome']['original_input'], phase['document'], 'phase outcome input')
        _same(phase['outcome']['side_order'], sides, 'phase outcome side order')
        check_domains(phase['outcome']['domains'], len(sides), 'candidate phase domains')
        require(phase['outcome']['status'] in ('underdetermined', 'solved', 'conflict'),
                'unknown propagation status')

    phase_check(0, original)
    for event_number, event in enumerate(events):
        require(type(event['before_phase']) is int and event['before_phase'] == current,
                'event does not continue latest persistent phase')
        before = phases[current]
        require(before['outcome']['status'] == 'underdetermined',
                'event follows terminal propagation')
        side, symbol = event['side'], event['symbol']
        require(side in index and type(symbol) is int and symbol in (1, 2, 3, 4),
                'invalid candidate identity or literal')
        candidates = before['outcome']['domains'][index[side]]
        require(len(candidates) > 1 and symbol == min(candidates),
                'actual event is not an unresolved low-name choice')
        _same(event['candidates_before'], candidates, 'event candidate domain')
        require(index[side] not in committed, 'event overwrites an actual commitment')
        trial_document = deepcopy(before['document'])
        trial_document.setdefault('anchors', {})[side] = symbol
        require(consumed < len(phases), 'event trial phase missing')
        require(type(event['trial_phase']) is int and event['trial_phase'] == consumed
                and phases[consumed]['kind'] == 'trial', 'invalid conditional trial phase')
        phase_check(consumed, trial_document)
        proposed = consumed
        consumed += 1
        if event['kind'] == 'commit':
            require(phases[proposed]['outcome']['status'] != 'conflict',
                    'guarded producer committed a refuted trial')
            committed[index[side]] = symbol
            expected_after = proposed
        elif event['kind'] == 'reject':
            require(phases[proposed]['outcome']['status'] == 'conflict',
                    'rejection lacks a conditional contradiction')
            rejected_document = deepcopy(before['document'])
            remaining = [color for color in candidates if color != symbol]
            marker = '2' if len(remaining) == 1 else '1'
            # Supplied singleton restrictions are marker 2, not explicit anchors.
            rejected_document.setdefault('states', {})[side] = ''.join(
                marker if color in remaining else '0' for color in (1, 2, 3, 4))
            require(consumed < len(phases) and phases[consumed]['kind'] == 'main',
                    'persistent post-rejection phase missing')
            phase_check(consumed, rejected_document)
            expected_after = consumed
            consumed += 1
        else:
            raise AssertionError('unknown producer event kind')
        require(type(event['after_phase']) is int and event['after_phase'] == expected_after,
                'event after-phase differs from actual state transition')
        current = expected_after
        _same(phases[current]['document'].get('anchors', {}),
              {sides[vertex]: color for vertex, color in committed.items()},
              'persistent phase anchors are not exactly actual commitments')
        persistent.append((current, event_number, deepcopy(committed)))
    require(consumed == len(phases), 'unconsumed producer phase')
    require(type(run['final_phase']) is int and run['final_phase'] == current,
            'wrong final persistent phase')

    states = []
    for state_number, (phase_number, after_event, fixed) in enumerate(persistent):
        next_event = state_number if state_number < len(events) else None
        next_choice = events[next_event] if next_event is not None else None
        outcome = phases[phase_number]['outcome']
        targets = []
        for side_number, candidates in enumerate(outcome['domains']):
            if len(candidates) <= 1:
                continue
            side = sides[side_number]
            for color in candidates:
                is_selected_side = next_choice is not None and next_choice['side'] == side
                category = (('scheduled_min' if color == min(candidates) else 'same_side_other')
                            if is_selected_side else
                            ('other_side_min' if color == min(candidates) else 'other_side_other'))
                action = 'not_selected'
                if is_selected_side and color == next_choice['symbol']:
                    action = ('actual_commit' if next_choice['kind'] == 'commit'
                              else 'actual_rejected_trial')
                targets.append({'side_index': side_number, 'side': side, 'symbol': color,
                                'category': category, 'action': action})
        states.append({'state_index': state_number, 'phase': phase_number,
                       'after_event_index': after_event,
                       'anchors': [list(pair) for pair in sorted(fixed.items())],
                       'next_event_index': next_event, 'propagation_status': outcome['status'],
                       'targets': targets})
    return {'states': states, 'scope': INVENTORY_SCOPE}


def support_inventory(document, run):
    """Bind actual states and enumerate all retained unary/binary obligations.

    A changed relation matrix changes the inventory even when commitments and
    final coloring agree. Its raw exact query can nevertheless reuse identical
    archived evidence; the state hashes retain the distinction explicitly.
    """
    inherited = _single_inventory(document, run)
    sides, n = document['sides'], len(document['sides'])
    for state in inherited['states']:
        phase = run['phases'][state['phase']]
        outcome = phase['outcome']
        domains, matrix = outcome['domains'], outcome['relations']
        check_matrix(matrix, n, 'support inventory relations')
        for i, domain in enumerate(domains):
            require(matrix[i][i] == sum(1 << (5 * (color - 1)) for color in domain),
                    'support inventory diagonal differs from domain')
            for j, other in enumerate(domains):
                allowed = sum(1 << (4 * (a - 1) + b - 1) for a in domain for b in other)
                require(matrix[i][j] & ~allowed == 0, 'relation exceeds endpoint domains')
        state['single_targets'] = state.pop('targets')
        state['phase_document_sha256'] = digest(phase['document'])
        for key in ('domains', 'relations', 'equal_names', 'different_names'):
            state[key + '_sha256'] = digest(outcome[key])
        next_event = state['next_event_index']
        event = run['events'][next_event] if next_event is not None else None
        targets, eligible, cartesian = [], 0, 0
        for i, first in enumerate(domains):
            if len(first) <= 1:
                continue
            for j in range(i + 1, n):
                second = domains[j]
                if len(second) <= 1:
                    continue
                eligible += 1
                cartesian += len(first) * len(second)
                for a in first:
                    for b in second:
                        if not matrix[i][j] & (1 << (4 * (a - 1) + b - 1)):
                            continue
                        minima = int(a == min(first)) + int(b == min(second))
                        action = 'not_next_choice'
                        if event is not None and (event['side'], event['symbol']) in (
                                (sides[i], a), (sides[j], b)):
                            action = ('includes_next_commit' if event['kind'] == 'commit'
                                      else 'includes_next_reject')
                        targets.append({'side_indices': [i, j], 'sides': [sides[i], sides[j]],
                                        'symbols': [a, b], 'category':
                                        ('neither_min', 'one_min', 'both_min')[minima],
                                        'next_action': action})
        state.update(pair_targets=targets, eligible_side_pair_count=eligible,
                     cartesian_target_count=cartesian)
    return inherited


def _source_index(sources, field):
    """Choose the first identical-input source and reject ambiguous locators.

    Pools are provenance-bound by the enclosing experiment. Here source bodies
    are indexed without replaying unused evidence. A reused body is verified
    below exactly once, on first demand. Origin order is part of the contract.
    """
    require(isinstance(sources, (list, tuple)), 'source pool must be ordered')
    indexed, locations = {}, {}
    for entry in sources:
        require(isinstance(entry, dict) and set(entry) == {'source', field},
                'unexpected source entry fields')
        require(isinstance(entry['source'], dict) and bool(entry['source']),
                'source requires a nonempty provenance locator')
        body = entry[field]
        expected = ({'input', 'result', 'verification'} if field == 'record' else
                    {'input', 'outcome', 'trace_audit', 'status'})
        require(isinstance(body, dict) and set(body) == expected, 'unexpected source body fields')
        location, body_hash = digest(entry['source']), digest(body)
        require(location not in locations or locations[location] == body_hash,
                'one source locator binds different evidence')
        locations[location] = body_hash
        indexed.setdefault(digest(body['input']), entry)
    return indexed


def summarize_states(states, oracle_records, conditional_records):
    """Separate obligations, actual actions, cached evidence and measured work."""
    def target_summary(categories, action_key, actions):
        """Create all zero-valued categories so missing work stays visible."""
        return {'target_count': 0, 'status_counts': dict.fromkeys(TARGET_STATUSES, 0),
                'category_counts': {k: dict.fromkeys(TARGET_STATUSES, 0) for k in categories},
                action_key: {k: dict.fromkeys(TARGET_STATUSES, 0) for k in actions},
                'conditional_counts': dict.fromkeys(CONDITIONAL_STATUSES, 0),
                'unsupported_state_count': 0}

    summary = {'state_count': len(states), 'no_single_target_state_count': 0,
               'no_pair_target_state_count': 0, 'eligible_side_pair_count': 0,
               'cartesian_target_count': 0, 'base_status_counts': dict.fromkeys(ORACLE_STATUSES, 0),
               'single': target_summary(SINGLE_CATEGORIES, 'action_counts', SINGLE_ACTIONS),
               'pair': target_summary(PAIR_CATEGORIES, 'next_action_counts', PAIR_ACTIONS),
               'oracle_record_count': len(oracle_records),
               'oracle_status_counts': dict.fromkeys(ORACLE_STATUSES, 0),
               'oracle_origin_counts': {'new': 0, 'reused': 0},
               'oracle_node_counts': {'new': 0, 'reused': 0},
               'conditional_record_count': len(conditional_records),
               'conditional_origin_counts': {'new': 0, 'reused': 0},
               'conditional_status_counts': dict.fromkeys(CONDITIONAL_STATUSES, 0)}
    summary['pair']['single_support_counts'] = dict.fromkeys(SINGLE_SUPPORT_STATUSES, 0)
    for record in oracle_records:
        origin = 'new' if record['origin'] is None else 'reused'
        summary['oracle_origin_counts'][origin] += 1
        summary['oracle_node_counts'][origin] += record['result']['nodes']
        summary['oracle_status_counts'][record['result']['status']] += 1
    for record in conditional_records:
        summary['conditional_origin_counts']['new' if record['origin'] is None else 'reused'] += 1
        summary['conditional_status_counts'][record['status']] += 1
    for state in states:
        base = oracle_records[state['base_oracle_index']]['result']['status']
        summary['base_status_counts'][base] += 1
        summary['eligible_side_pair_count'] += state['eligible_side_pair_count']
        summary['cartesian_target_count'] += state['cartesian_target_count']
        for kind in ('single', 'pair'):
            targets, group = state[kind + '_targets'], summary[kind]
            summary['no_' + kind + '_target_state_count'] += int(not targets)
            group['target_count'] += len(targets)
            group['unsupported_state_count'] += int(any(t['status'] == 'unsupported' for t in targets))
            for target in targets:
                status = target['status']
                group['status_counts'][status] += 1
                group['category_counts'][target['category']][status] += 1
                action = 'action' if kind == 'single' else 'next_action'
                group[action + '_counts'][target[action]][status] += 1
                reference = target['conditional_index']
                if reference is not None:
                    group['conditional_counts'][conditional_records[reference]['status']] += 1
                if kind == 'pair' and target['single_support'] is not None:
                    group['single_support_counts'][target['single_support']] += 1
    return summary


def scan_support(document, run, *, node_limit=200000, oracle_sources=(),
                 conditional_sources=(), progress=None):
    """Evaluate a frozen scene without rerunning its producer or losing sources.

    The enclosing runner provides scene checkpoints for interruption recovery.
    Every unique raw query first tries the ordered archive pool; only a missing
    query invokes solve_exact. All literal certificates are checked even when
    cached. The same rule applies to conditional propagation inputs. UNKNOWN
    remains unresolved and cannot justify deleting a candidate or a color pair.
    """
    require(type(node_limit) is int and node_limit >= 0, 'invalid support oracle node limit')
    require(progress is None or callable(progress), 'progress callback is not callable')
    inventory = support_inventory(document, run)
    sides = document['sides']
    index = {side: i for i, side in enumerate(sides)}
    edges = sorted({tuple(sorted((index[line['left']], index[line['right']])))
                    for line in document['lines'] if line['kind'] == 'separator'})
    oracle_pool = _source_index(oracle_sources, 'record')
    conditional_pool = _source_index(conditional_sources, 'conditional')
    records, cache, diagnostics, diagnostic_cache = [], {}, [], {}

    def exact(fixed):
        """Reuse only a complete original adjacency and literal-anchor query."""
        query = {'n': len(sides), 'edges': [list(pair) for pair in edges],
                 'anchors': [list(pair) for pair in sorted(fixed.items())]}
        signature = digest(query)
        if signature in cache:
            return cache[signature]
        source = oracle_pool.get(signature)
        if source is None:
            result = solve_exact(len(sides), edges, fixed, node_limit=node_limit)
            checked = verify_exact_result(len(sides), edges, fixed, result)
            record = {'input': query, 'result': result, 'verification': checked, 'origin': None}
        else:
            old = source['record']
            _same(old['input'], query, 'source exact query')
            _same(old['result']['node_limit'], node_limit, 'source exact node budget')
            checked = verify_exact_result(len(sides), edges, fixed, old['result'])
            _same(checked, old['verification'], 'source exact verification')
            record = {**deepcopy(old), 'origin': deepcopy(source['source'])}
        cache[signature] = len(records)
        records.append(record)
        return cache[signature]

    def conditional(state, hypotheses):
        """Cache the complete scoped conditional input, never just its colors."""
        proposal = deepcopy(run['phases'][state['phase']]['document'])
        proposal.setdefault('anchors', {}).update(hypotheses)
        signature = digest(proposal)
        if signature in diagnostic_cache:
            return diagnostic_cache[signature]
        source = conditional_pool.get(signature)
        if source is None:
            outcome = propagate_saturation_contacts(proposal)
            checked = audit_saturation_contacts(proposal, outcome)
            require(outcome['status'] in ('conflict', 'underdetermined'),
                    'conditional solved witness contradicts verified raw UNSAT')
            status = ('conditional_refuted' if outcome['status'] == 'conflict'
                      else 'conditional_inconclusive')
            entry = {'input': proposal, 'outcome': outcome, 'trace_audit': checked,
                     'status': status, 'origin': None}
        else:
            old = source['conditional']
            _same(old['input'], proposal, 'source conditional input')
            checked = audit_saturation_contacts(proposal, old['outcome'])
            _same(checked, old['trace_audit'], 'source conditional audit')
            require(old['outcome']['status'] in ('conflict', 'underdetermined'),
                    'conditional solved witness contradicts verified raw UNSAT')
            expected = ('conditional_refuted' if old['outcome']['status'] == 'conflict'
                        else 'conditional_inconclusive')
            _same(old['status'], expected, 'source conditional status')
            entry = {**deepcopy(old), 'origin': deepcopy(source['source'])}
        diagnostic_cache[signature] = len(diagnostics)
        diagnostics.append(entry)
        return diagnostic_cache[signature]

    def classify(base, child):
        """A bad base or exhausted search is not a newly disproved hypothesis."""
        if base == 'unsat':
            return 'preexisting_unsat'
        if base == 'unknown' or child == 'unknown':
            return 'unknown'
        return 'supported' if child == 'sat' else 'unsupported'

    states = deepcopy(inventory['states'])
    for state in states:
        fixed = dict(state['anchors'])
        state['base_oracle_index'] = exact(fixed)
        base = records[state['base_oracle_index']]['result']['status']
        for target in state['single_targets']:
            ref = exact({**fixed, target['side_index']: target['symbol']})
            status = classify(base, records[ref]['result']['status'])
            target.update(candidate_oracle_index=ref, status=status, conditional_index=None)
            if status == 'unsupported':
                target['conditional_index'] = conditional(state, {target['side']: target['symbol']})
        for target in state['pair_targets']:
            hypotheses = dict(zip(target['side_indices'], target['symbols']))
            ref = exact({**fixed, **hypotheses})
            status = classify(base, records[ref]['result']['status'])
            target.update(pair_oracle_index=ref, status=status, conditional_index=None,
                          single_oracle_indices=None, single_support=None)
            if status != 'unsupported':
                continue
            singles = [exact({**fixed, vertex: color}) for vertex, color in hypotheses.items()]
            single_status = [records[i]['result']['status'] for i in singles]
            target['single_oracle_indices'] = singles
            target['single_support'] = ('has_unsupported_single' if 'unsat' in single_status else
                                        'unknown_single' if 'unknown' in single_status else 'both_supported')
            target['conditional_index'] = conditional(state, dict(zip(target['sides'], target['symbols'])))
        if progress is not None:
            progress({'kind': 'state_complete', 'state_index': state['state_index'],
                      'state_count': len(states), 'oracle_records': len(records),
                      'conditional_records': len(diagnostics)})
    return {'schema_version': 1, 'version': VERSION, 'raw_document': deepcopy(document),
            'inventory': inventory, 'node_limit': node_limit, 'states': states,
            'oracle_records': records, 'conditional_records': diagnostics,
            'summary': summarize_states(states, records, diagnostics),
            'oracle_feedback_to_producer': False, 'scope': SCOPE}


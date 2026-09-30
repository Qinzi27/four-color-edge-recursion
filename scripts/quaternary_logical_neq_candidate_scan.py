"""Post-run support checks for every candidate in actually reached states.

The frozen producer has already terminated before this module is called. Its
domains decide which hypotheses to inspect, but never restrict the exact
oracle: that oracle sees only original separator edges and explicit anchors
plus actual commitments. A rejected trial is not a persistent state, whereas a
committed trial is. Learned EQ/NEQ, singleton deductions and rejected candidates
are deliberately absent from every exact premise.
"""

from copy import deepcopy

from scripts.audit_quaternary_geometry import _same
from scripts.audit_quaternary_logical_neq import audit_logical_contacts, logical_metadata
from scripts.exact_extendibility_oracle import solve_exact, verify_exact_result
from scripts.quaternary_logical_neq_contacts import propagate_logical_contacts
from scripts.validate_quaternary_contacts_v2 import check_domains, raw_metadata, require


VERSION = 'quaternary-logical-neq-candidate-scan-v1'
INVENTORY_SCOPE = ('Initial phase and every persistent event after-phase; rejected trial '
                   'phases excluded; explicit anchors plus actual commitments only.')
SCOPE = ('Offline candidates of one completed frozen run; exact queries use original '
         'separator edges and actual commitments only. Unsupported candidates do not '
         'imply an unsafe actual commitment; UNKNOWN is not UNSAT.')
CATEGORIES = ('scheduled_min', 'same_side_other', 'other_side_min', 'other_side_other')
ACTIONS = ('actual_commit', 'actual_rejected_trial', 'not_selected')
TARGET_STATUSES = ('supported', 'unsupported', 'unknown', 'preexisting_unsat')
ORACLE_STATUSES = ('sat', 'unsat', 'unknown')
CONDITIONAL_STATUSES = ('conditional_refuted', 'conditional_inconclusive')


def candidate_inventory(document, run):
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
            and run.get('policy') == 'quaternary-low-color-logical-neq-conditional-v1',
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


def summarize_states(states, oracle_records):
    """Count obligations separately from cached exact queries and actual actions."""
    summary = {'state_count': len(states), 'target_count': 0, 'no_target_state_count': 0,
               'base_status_counts': dict.fromkeys(ORACLE_STATUSES, 0),
               'target_status_counts': dict.fromkeys(TARGET_STATUSES, 0),
               'category_counts': {key: dict.fromkeys(TARGET_STATUSES, 0) for key in CATEGORIES},
               'action_counts': {key: dict.fromkeys(TARGET_STATUSES, 0) for key in ACTIONS},
               'conditional_counts': dict.fromkeys(CONDITIONAL_STATUSES, 0),
               'unsupported_state_count': 0, 'oracle_record_count': len(oracle_records),
               'oracle_status_counts': dict.fromkeys(ORACLE_STATUSES, 0)}
    for record in oracle_records:
        summary['oracle_status_counts'][record['result']['status']] += 1
    for state in states:
        summary['base_status_counts'][oracle_records[state['base_oracle_index']]['result']['status']] += 1
        summary['target_count'] += len(state['targets'])
        summary['no_target_state_count'] += int(not state['targets'])
        summary['unsupported_state_count'] += int(any(
            target['status'] == 'unsupported' for target in state['targets']))
        for target in state['targets']:
            status = target['status']
            summary['target_status_counts'][status] += 1
            summary['category_counts'][target['category']][status] += 1
            summary['action_counts'][target['action']][status] += 1
            if target['conditional'] is not None:
                summary['conditional_counts'][target['conditional']['status']] += 1
    return summary


def scan_candidates(document, run, *, node_limit=200000):
    """Audit all stored unresolved candidates after an immutable producer run.

    SAT bases and UNSAT children establish unsupported candidates. Each such
    child is then checked by one conditional propagation for diagnosis only;
    this cannot alter the saved producer run or its future decisions. An UNSAT
    base is a preexisting failure, never evidence that a later candidate newly
    destroyed extendibility. Unknown bases remain unknown even if a child is
    conclusive. Identical raw-anchor queries share one verified certificate.
    """
    require(type(node_limit) is int and node_limit >= 0, 'invalid candidate oracle node limit')
    inventory = candidate_inventory(document, run)
    sides = document['sides']
    index = {side: number for number, side in enumerate(sides)}
    edges = sorted({tuple(sorted((index[line['left']], index[line['right']])))
                    for line in document['lines'] if line['kind'] == 'separator'})
    records, cache = [], {}

    def exact(fixed):
        """Cache precisely original raw adjacency plus literal fixed anchors."""
        signature = tuple(sorted(fixed.items()))
        if signature not in cache:
            evidence = solve_exact(len(sides), edges, fixed, node_limit=node_limit)
            verified = verify_exact_result(len(sides), edges, fixed, evidence)
            cache[signature] = len(records)
            records.append({'input': {'n': len(sides), 'edges': [list(pair) for pair in edges],
                                      'anchors': [list(pair) for pair in signature]},
                            'result': evidence, 'verification': verified})
        return cache[signature]

    states = deepcopy(inventory['states'])
    for state in states:
        fixed = dict(state['anchors'])
        state['base_oracle_index'] = exact(fixed)
        base_status = records[state['base_oracle_index']]['result']['status']
        for target in state['targets']:
            child = {**fixed, target['side_index']: target['symbol']}
            target['candidate_oracle_index'] = exact(child)
            child_status = records[target['candidate_oracle_index']]['result']['status']
            if base_status == 'unsat':
                classification = 'preexisting_unsat'
            elif base_status == 'unknown' or child_status == 'unknown':
                classification = 'unknown'
            else:
                classification = 'supported' if child_status == 'sat' else 'unsupported'
            target.update(status=classification, conditional=None)
            if classification == 'unsupported':
                proposal = deepcopy(run['phases'][state['phase']]['document'])
                proposal.setdefault('anchors', {})[target['side']] = target['symbol']
                outcome = propagate_logical_contacts(proposal)
                audited = audit_logical_contacts(proposal, outcome)
                require(outcome['status'] != 'solved',
                        'conditional solved witness contradicts verified raw UNSAT')
                conditional_status = ('conditional_refuted' if outcome['status'] == 'conflict'
                                      else 'conditional_inconclusive')
                target['conditional'] = {'input': proposal, 'outcome': outcome,
                                         'trace_audit': audited, 'status': conditional_status}
    return {'schema_version': 1, 'version': VERSION, 'raw_document': deepcopy(document),
            'inventory': inventory, 'node_limit': node_limit, 'states': states,
            'oracle_records': records, 'summary': summarize_states(states, records),
            'oracle_feedback_to_producer': False, 'scope': SCOPE}

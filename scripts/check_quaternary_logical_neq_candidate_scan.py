"""Replay saved candidate support evidence without search or propagation.

The producer and its learned EQ/NEQ certificates are checked separately by the
experiment runner. This checker independently reconstructs all persistent
states and candidate queries from that frozen run. Exact evidence is bound to
original physical NEQ edges and actual commitments, never inferred singletons,
logical EQ/NEQ, or candidate deletions. Saved conditional probes are replayed by
the independent literal-set trace auditor; they never update the producer.
"""

from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_quaternary_logical_neq import audit_logical_contacts, logical_metadata
from scripts.exact_extendibility_oracle import verify_exact_result
from scripts.validate_quaternary_contacts_v2 import check_domains, raw_metadata


VERSION = 'quaternary-logical-neq-candidate-scan-v1'
CHECK_VERSION = 'quaternary-logical-neq-candidate-scan-saved-check-v1'
INVENTORY_SCOPE = ('Initial phase and every persistent event after-phase; rejected trial phases '
                   'excluded; explicit anchors plus actual commitments only.')
SCOPE = ('Offline candidates of one completed frozen run; exact queries use original separator '
         'edges and actual commitments only. Unsupported candidates do not imply an unsafe '
         'actual commitment; UNKNOWN is not UNSAT.')
CATEGORIES = ('scheduled_min', 'same_side_other', 'other_side_min', 'other_side_other')
ACTIONS = ('actual_commit', 'actual_rejected_trial', 'not_selected')
TARGET_STATUSES = ('supported', 'unsupported', 'unknown', 'preexisting_unsat')
EXACT_STATUSES = ('sat', 'unsat', 'unknown')


def _require(condition, message):
    """Keep rejection active when Python assertions are disabled."""
    if not condition:
        raise ValueError(message)


def _same(actual, expected, label):
    """Compare JSON literally, including boolean versus integer distinctions."""
    _require(json.dumps(actual, sort_keys=True, allow_nan=False)
             == json.dumps(expected, sort_keys=True, allow_nan=False), label + ' differs')


def _integer(value, label, *, minimum=0):
    """Forbid boolean aliases for integer phase and evidence identities."""
    _require(type(value) is int and value >= minimum, label + ' is not a valid integer')
    return value


def _state_word(candidates):
    """Encode rejection restrictions independently of the producer encoder."""
    marker = '2' if len(candidates) == 1 else '1'
    return ''.join(marker if color in candidates else '0' for color in (1, 2, 3, 4))


def _persistent_states(document, run):
    """Reconstruct actual anchor history and exclude rejected trial phases.

    A committed trial becomes the next persistent state even though its stored
    phase kind remains ``trial``. Rejections preserve actual anchor commitments
    and create a new main phase containing only the proved local deletion.
    """
    sides, _, _ = raw_metadata(document)
    _require(not document.get('states') and not document.get('equal_names')
             and 'different_names' not in document,
             'candidate scan requires raw NEQ and explicit anchors only')
    index = {side: i for i, side in enumerate(sides)}
    _require(isinstance(run, dict), 'run must be an object')
    _same(run['schema_version'], 1, 'frozen producer schema')
    _same(run['policy'], 'quaternary-low-color-logical-neq-conditional-v1', 'frozen producer policy')
    _require(run['oracle_feedback_to_producer'] is False and run['old_colors_read'] is False,
             'invalid frozen producer input mode')
    _same(run['backtracks'], 0, 'frozen producer backtracks')
    original = run['original_input']
    logical_metadata(original)
    expected_original = deepcopy(document)
    for relation in ('equal_names', 'different_names'):
        if relation in original:
            expected_original[relation] = deepcopy(original[relation])
    _same(original, expected_original, 'producer raw input except separately certified EQ/NEQ')
    phases, events = run['phases'], run['events']
    _require(isinstance(phases, list) and bool(phases) and isinstance(events, list),
             'missing producer phases or events')
    _require(phases[0]['kind'] == 'main', 'initial phase is not persistent')
    _same(phases[0]['document'], original, 'initial phase input')
    _require(run['probe'] is True, 'logical-NEQ producer must use guarded probes')
    for phase in phases:
        logical_metadata(phase['document'])
        _same(phase['outcome']['original_input'], phase['document'], 'saved phase outcome input')
        _same(phase['outcome']['side_order'], sides, 'saved phase side order')
        check_domains(phase['outcome']['domains'], len(sides), 'saved phase domains')
        _require(phase['outcome']['status'] in ('solved', 'conflict', 'underdetermined'),
                 'invalid saved propagation status')
    committed = {index[side]: color for side, color in document.get('anchors', {}).items()}
    snapshots = [(0, None, deepcopy(committed))]
    current, consumed, choices, rejections, probes = 0, 1, 0, 0, 0
    for event_number, event in enumerate(events):
        _integer(event['before_phase'], 'event before phase')
        _require(event['before_phase'] == current, 'event does not continue persistent phase')
        before = phases[current]
        _require(before['outcome']['status'] == 'underdetermined', 'event after terminal phase')
        side, symbol, kind = event['side'], event['symbol'], event['kind']
        _require(side in index and type(symbol) is int and symbol in (1, 2, 3, 4),
                 'invalid event side or symbol')
        candidates = before['outcome']['domains'][index[side]]
        _require(index[side] not in committed, 'event overwrites actual commitment')
        _require(len(candidates) > 1 and symbol == min(candidates),
                 'actual action is not a lowest unresolved candidate')
        _same(event['candidates_before'], candidates, 'actual event candidate domain')
        _require(kind in ('commit', 'reject'), 'unknown actual event kind')
        proposal = deepcopy(before['document'])
        proposal.setdefault('anchors', {})[side] = symbol
        if run['probe']:
            _integer(event['trial_phase'], 'event trial phase')
            _require(event['trial_phase'] == consumed and consumed < len(phases),
                     'missing or reused trial phase')
            _require(phases[consumed]['kind'] == 'trial', 'wrong trial phase kind')
            _same(phases[consumed]['document'], proposal, 'trial phase assumptions')
            trial = consumed
            consumed += 1
            probes += 1
        else:
            _require(event['trial_phase'] is None, 'unprobed run contains trial reference')
            trial = None
        if kind == 'reject':
            _require(run['probe'] and phases[trial]['outcome']['status'] == 'conflict',
                     'actual rejection lacks conflicting trial')
            expected_after = deepcopy(before['document'])
            remaining = [color for color in candidates if color != symbol]
            expected_after.setdefault('states', {})[side] = _state_word(remaining)
            _require(consumed < len(phases) and phases[consumed]['kind'] == 'main',
                     'missing persistent phase after rejection')
            _same(phases[consumed]['document'], expected_after, 'post-rejection assumptions')
            current, consumed = consumed, consumed + 1
            rejections += 1
        else:
            if run['probe']:
                _require(phases[trial]['outcome']['status'] != 'conflict',
                         'conflicting trial was committed')
                current = trial
            else:
                _require(consumed < len(phases) and phases[consumed]['kind'] == 'main',
                         'missing unprobed committed phase')
                _same(phases[consumed]['document'], proposal, 'unprobed commitment assumptions')
                current, consumed = consumed, consumed + 1
            committed[index[side]] = symbol
            choices += 1
        _integer(event['after_phase'], 'event after phase')
        _require(event['after_phase'] == current, 'event after phase mismatch')
        _same(phases[current]['document'].get('anchors', {}),
              {sides[vertex]: color for vertex, color in committed.items()},
              'persistent actual anchors')
        snapshots.append((current, event_number, deepcopy(committed)))
    _require(consumed == len(phases), 'unreferenced producer phase')
    _same(run['final_phase'], current, 'final persistent phase')
    for field, expected in (('choices', choices), ('rejections', rejections), ('probes', probes)):
        _same(run[field], expected, 'actual ' + field)
    return sides, index, snapshots


def _inventory(document, run):
    """Independently enumerate every unresolved face/color at every prefix."""
    sides, index, snapshots = _persistent_states(document, run)
    events, states = run['events'], []
    for state_index, (phase_number, after_event, committed) in enumerate(snapshots):
        next_event = state_index if state_index < len(events) else None
        event = events[next_event] if next_event is not None else None
        phase = run['phases'][phase_number]
        targets = []
        for side_index, candidates in enumerate(phase['outcome']['domains']):
            if len(candidates) <= 1:
                continue
            side = sides[side_index]
            for symbol in candidates:
                chosen_side = event is not None and event['side'] == side
                category = ('scheduled_min' if symbol == min(candidates) else 'same_side_other') \
                    if chosen_side else ('other_side_min' if symbol == min(candidates)
                                         else 'other_side_other')
                action = (('actual_commit' if event['kind'] == 'commit'
                           else 'actual_rejected_trial') if category == 'scheduled_min'
                          else 'not_selected')
                targets.append({'side_index': side_index, 'side': side, 'symbol': symbol,
                                'category': category, 'action': action})
        states.append({'state_index': state_index, 'phase': phase_number,
                       'after_event_index': after_event,
                       'anchors': [[vertex, color] for vertex, color in sorted(committed.items())],
                       'next_event_index': next_event,
                       'propagation_status': phase['outcome']['status'], 'targets': targets})
    return {'states': states, 'scope': INVENTORY_SCOPE}, sides, index


def _summary(states, oracle_records):
    """Recount report claims independently; UNKNOWN remains a separate class."""
    summary = {
        'state_count': len(states), 'target_count': 0, 'no_target_state_count': 0,
        'base_status_counts': {status: 0 for status in EXACT_STATUSES},
        'target_status_counts': {status: 0 for status in TARGET_STATUSES},
        'category_counts': {category: {status: 0 for status in TARGET_STATUSES}
                            for category in CATEGORIES},
        'action_counts': {action: {status: 0 for status in TARGET_STATUSES}
                          for action in ACTIONS},
        'conditional_counts': {'conditional_refuted': 0, 'conditional_inconclusive': 0},
        'unsupported_state_count': 0, 'oracle_record_count': len(oracle_records),
        'oracle_status_counts': {status: 0 for status in EXACT_STATUSES},
    }
    for record in oracle_records:
        summary['oracle_status_counts'][record['result']['status']] += 1
    for state in states:
        base_status = oracle_records[state['base_oracle_index']]['result']['status']
        summary['base_status_counts'][base_status] += 1
        summary['no_target_state_count'] += not state['targets']
        summary['target_count'] += len(state['targets'])
        summary['unsupported_state_count'] += any(target['status'] == 'unsupported'
                                                  for target in state['targets'])
        for target in state['targets']:
            status = target['status']
            summary['target_status_counts'][status] += 1
            summary['category_counts'][target['category']][status] += 1
            summary['action_counts'][target['action']][status] += 1
            if target['conditional'] is not None:
                summary['conditional_counts'][target['conditional']['status']] += 1
    return summary


def check_candidate_scan(document, run, scan, *, node_limit=200000):
    """Validate a saved scan with zero producer, oracle-search, or propagation calls.

    ``run`` is the underlying low-color result, already independently checked by
    the enclosing experiment. This additional check reconstructs all candidate
    requests and their precise raw premises; it does not infer correctness from
    a SAT/UNSAT status label or from an independently valid stronger query.
    """
    _integer(node_limit, 'node limit')
    expected_inventory, sides, index = _inventory(document, run)
    _require(isinstance(scan, dict) and set(scan) == {
        'schema_version', 'version', 'raw_document', 'inventory', 'node_limit', 'states',
        'oracle_records', 'summary', 'oracle_feedback_to_producer', 'scope'},
        'unexpected or missing candidate scan fields')
    _same(scan['schema_version'], 1, 'scan schema version')
    _same(scan['version'], VERSION, 'scan version')
    _same(scan['raw_document'], document, 'scan original raw input')
    _same(scan['inventory'], expected_inventory, 'complete persistent candidate inventory')
    _same(scan['node_limit'], node_limit, 'scan node limit')
    _same(scan['scope'], SCOPE, 'scan scope')
    _require(scan['oracle_feedback_to_producer'] is False, 'offline evidence fed back to producer')
    edges = sorted({tuple(sorted((index[line['left']], index[line['right']])))
                    for line in document['lines'] if line['kind'] == 'separator'})
    records = scan['oracle_records']
    _require(isinstance(records, list), 'oracle records must be an array')
    verified, signatures = [], {}
    for record_index, record in enumerate(records):
        _require(isinstance(record, dict) and set(record) == {'input', 'result', 'verification'},
                 'unexpected saved oracle record fields')
        data = record['input']
        _require(isinstance(data, dict) and set(data) == {'n', 'edges', 'anchors'},
                 'oracle input contains non-raw premises')
        _same(data['n'], len(sides), 'oracle side count')
        _same(data['edges'], [list(edge) for edge in edges], 'oracle original separator edges')
        anchors = data['anchors']
        _require(isinstance(anchors, list), 'oracle anchors must be an ordered array')
        fixed = {}
        for pair in anchors:
            _require(isinstance(pair, list) and len(pair) == 2, 'invalid oracle anchor pair')
            vertex, color = pair
            _require(type(vertex) is int and 0 <= vertex < len(sides)
                     and type(color) is int and color in (1, 2, 3, 4),
                     'invalid oracle anchor literal')
            _require(vertex not in fixed, 'duplicate oracle anchor')
            fixed[vertex] = color
        _same(anchors, [[vertex, color] for vertex, color in sorted(fixed.items())],
              'canonical oracle anchor order')
        key = tuple(sorted(fixed.items()))
        _require(key not in signatures, 'duplicate exact query record')
        signatures[key] = record_index
        _same(record['result']['node_limit'], node_limit, 'oracle record node limit')
        certificate_check = verify_exact_result(len(sides), edges, fixed, record['result'])
        _same(record['verification'], certificate_check, 'saved exact certificate verification')
        verified.append(certificate_check)

    referenced, conditional_probes, conditional_trace_steps = set(), 0, 0

    def evidence(reference, expected_anchors):
        """A valid certificate for a stronger premise must still be rejected."""
        _integer(reference, 'oracle reference')
        _require(reference < len(records), 'oracle reference outside saved records')
        record = records[reference]
        _same(record['input']['anchors'], expected_anchors, 'actual commitment and candidate binding')
        referenced.add(reference)
        return record['result']['status']

    states = scan['states']
    _require(isinstance(states, list) and len(states) == len(expected_inventory['states']),
             'missing or extra persistent scan state')
    for expected_state, state in zip(expected_inventory['states'], states):
        _require(isinstance(state, dict) and set(state) == set(expected_state) | {'base_oracle_index'},
                 'unexpected persistent scan state fields')
        for field in set(expected_state) - {'targets'}:
            _same(state[field], expected_state[field], 'persistent scan ' + field)
        base_status = evidence(state['base_oracle_index'], expected_state['anchors'])
        targets = state['targets']
        _require(isinstance(targets, list) and len(targets) == len(expected_state['targets']),
                 'missing or extra retained candidate target')
        for expected_target, target in zip(expected_state['targets'], targets):
            _require(isinstance(target, dict) and set(target) == set(expected_target)
                     | {'candidate_oracle_index', 'status', 'conditional'},
                     'unexpected retained candidate target fields')
            for field in expected_target:
                _same(target[field], expected_target[field], 'retained target ' + field)
            fixed = dict(expected_state['anchors'])
            fixed[target['side_index']] = target['symbol']
            trial_status = evidence(target['candidate_oracle_index'],
                                    [[vertex, color] for vertex, color in sorted(fixed.items())])
            status = ('preexisting_unsat' if base_status == 'unsat' else
                      'unknown' if 'unknown' in (base_status, trial_status) else
                      'unsupported' if trial_status == 'unsat' else 'supported')
            _same(target['status'], status, 'candidate support classification')
            conditional = target['conditional']
            if status != 'unsupported':
                _require(conditional is None, 'conditional probe without a proved unsupported target')
                continue
            _require(isinstance(conditional, dict)
                     and set(conditional) == {'input', 'outcome', 'trace_audit', 'status'},
                     'missing unsupported candidate conditional evidence')
            trial_input = deepcopy(run['phases'][state['phase']]['document'])
            trial_input.setdefault('anchors', {})[target['side']] = target['symbol']
            _same(conditional['input'], trial_input, 'conditional persistent phase and target premise')
            trace_check = audit_logical_contacts(trial_input, conditional['outcome'])
            _same(conditional['trace_audit'], trace_check, 'conditional saved trace audit')
            _require(conditional['outcome']['status'] in ('conflict', 'underdetermined'),
                     'unsupported raw candidate cannot have a complete conditional coloring')
            conditional_status = ('conditional_refuted' if conditional['outcome']['status'] == 'conflict'
                                  else 'conditional_inconclusive')
            _same(conditional['status'], conditional_status, 'conditional rejection classification')
            conditional_probes += 1
            conditional_trace_steps += trace_check['trace_steps_checked']
    _require(referenced == set(range(len(records))), 'hidden unused oracle evidence')
    summary = _summary(states, records)
    _same(scan['summary'], summary, 'complete candidate scan summary')
    return {'passed': True, 'check_version': CHECK_VERSION, 'summary': summary,
            'persistent_states_checked': len(states), 'target_count': summary['target_count'],
            'oracle_records': len(records), 'oracle_statuses': summary['oracle_status_counts'],
            'conditional_probes_checked': conditional_probes,
            'conditional_trace_steps_checked': conditional_trace_steps,
            'producer_runs': 0, 'oracle_searches': 0, 'propagation_runs': 0}

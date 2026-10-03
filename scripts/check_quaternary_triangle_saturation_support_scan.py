"""Independently replay all saved unary and binary support obligations.

The enclosing runner binds the already audited frozen producer archive once.
This checker reconstructs its actual event/commitment chain, inventories every
retained literal and pair, and replays only unique raw exact certificates and
conditional trace certificates. It performs no producer, propagation or exact
search call. Learned relations never become raw oracle premises.
"""

from copy import deepcopy
from hashlib import sha256
import json

from scripts.audit_quaternary_logical_neq import logical_metadata
from scripts.check_quaternary_triangle_saturation import audit_saturation_contacts
from scripts.exact_extendibility_oracle import verify_exact_result
from scripts.validate_quaternary_contacts_v2 import check_domains, check_matrix, raw_metadata


VERSION = 'quaternary-triangle-saturation-support-scan-v1'
CHECK_VERSION = 'quaternary-triangle-saturation-support-saved-check-v1'
INNER_POLICY = 'quaternary-low-color-triangle-saturation-conditional-v1'
EXACT_STATUSES = ('sat', 'unsat', 'unknown')
TARGET_STATUSES = ('supported', 'unsupported', 'unknown', 'preexisting_unsat')
SINGLE_CATEGORIES = ('scheduled_min', 'same_side_other', 'other_side_min', 'other_side_other')
SINGLE_ACTIONS = ('actual_commit', 'actual_rejected_trial', 'not_selected')
PAIR_CATEGORIES = ('both_min', 'one_min', 'neither_min')
PAIR_ACTIONS = ('includes_next_commit', 'includes_next_reject', 'not_next_choice')
SINGLE_SUPPORT = ('both_supported', 'has_unsupported_single', 'unknown_single')
CONDITIONAL_STATUSES = ('conditional_refuted', 'conditional_inconclusive')
INVENTORY_SCOPE = ('Initial and every actual persistent after-phase; unresolved single candidates '
                   'and matrix-allowed unordered face pairs; rejected trial phases excluded.')
SCOPE = ('Offline support census of saved triangle-saturation states; exact premises are '
         'original separator edges and actual commitments plus hypotheses only; '
         'no oracle feedback to production.')


def _digest(value):
    """Hash the independent canonical JSON view, including domains and masks."""
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False).encode('utf-8')).hexdigest()


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
    _same(run['policy'], 'quaternary-low-color-triangle-saturation-conditional-v1', 'frozen producer policy')
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


def support_inventory(document, run):
    """Reconstruct all obligations independently of the scanner's inventory.

    Only actual anchors enter each raw query. Full hashes also bind the saved
    phase assumptions, domains and matrix so matching final colors cannot
    masquerade as matching intermediate states.
    """
    sides, index, snapshots = _persistent_states(document, run)
    events, states, n = run['events'], [], len(sides)
    for state_index, (phase_number, after_event, fixed) in enumerate(snapshots):
        phase = run['phases'][phase_number]
        outcome = phase['outcome']
        domains, matrix = outcome['domains'], outcome['relations']
        check_matrix(matrix, n, 'persistent support relation matrix')
        for i, domain in enumerate(domains):
            _same(matrix[i][i], sum(1 << (5 * (color - 1)) for color in domain),
                  'persistent diagonal and domain')
            for j, other in enumerate(domains):
                allowed = sum(1 << (4 * (a - 1) + b - 1) for a in domain for b in other)
                _require(matrix[i][j] & ~allowed == 0, 'relation exceeds endpoint domains')
        next_event = state_index if state_index < len(events) else None
        event = events[next_event] if next_event is not None else None
        singles, pairs, eligible, cartesian = [], [], 0, 0
        for i, domain in enumerate(domains):
            if len(domain) <= 1:
                continue
            for a in domain:
                chosen = event is not None and event['side'] == sides[i]
                category = ('scheduled_min' if a == min(domain) else 'same_side_other') \
                    if chosen else ('other_side_min' if a == min(domain) else 'other_side_other')
                action = (('actual_commit' if event['kind'] == 'commit'
                           else 'actual_rejected_trial') if category == 'scheduled_min'
                          else 'not_selected')
                singles.append({'side_index': i, 'side': sides[i], 'symbol': a,
                                'category': category, 'action': action})
            for j in range(i + 1, n):
                other = domains[j]
                if len(other) <= 1:
                    continue
                eligible += 1
                cartesian += len(domain) * len(other)
                for a in domain:
                    for b in other:
                        if not matrix[i][j] & (1 << (4 * (a - 1) + b - 1)):
                            continue
                        minima = int(a == min(domain)) + int(b == min(other))
                        category = ('neither_min', 'one_min', 'both_min')[minima]
                        includes = event is not None and (
                            (event['side'] == sides[i] and event['symbol'] == a)
                            or (event['side'] == sides[j] and event['symbol'] == b))
                        action = (('includes_next_commit' if event['kind'] == 'commit'
                                   else 'includes_next_reject') if includes else 'not_next_choice')
                        pairs.append({'side_indices': [i, j], 'sides': [sides[i], sides[j]],
                                      'symbols': [a, b], 'category': category, 'next_action': action})
        states.append({'state_index': state_index, 'phase': phase_number,
                       'after_event_index': after_event,
                       'anchors': [[v, c] for v, c in sorted(fixed.items())],
                       'next_event_index': next_event, 'propagation_status': outcome['status'],
                       'phase_document_sha256': _digest(phase['document']),
                       'domains_sha256': _digest(domains),
                       'relations_sha256': _digest(matrix),
                       'equal_names_sha256': _digest(outcome['equal_names']),
                       'different_names_sha256': _digest(outcome['different_names']),
                       'eligible_side_pair_count': eligible, 'cartesian_target_count': cartesian,
                       'single_targets': singles, 'pair_targets': pairs})
    return {'states': states, 'scope': INVENTORY_SCOPE}


def _summary(states, records, conditionals):
    """Recount scientific outcomes separately from cached work and provenance."""
    single = {'target_count': 0, 'status_counts': dict.fromkeys(TARGET_STATUSES, 0),
              'category_counts': {x: dict.fromkeys(TARGET_STATUSES, 0) for x in SINGLE_CATEGORIES},
              'action_counts': {x: dict.fromkeys(TARGET_STATUSES, 0) for x in SINGLE_ACTIONS},
              'conditional_counts': dict.fromkeys(CONDITIONAL_STATUSES, 0),
              'unsupported_state_count': 0}
    pair = {'target_count': 0, 'status_counts': dict.fromkeys(TARGET_STATUSES, 0),
            'category_counts': {x: dict.fromkeys(TARGET_STATUSES, 0) for x in PAIR_CATEGORIES},
            'next_action_counts': {x: dict.fromkeys(TARGET_STATUSES, 0) for x in PAIR_ACTIONS},
            'conditional_counts': dict.fromkeys(CONDITIONAL_STATUSES, 0),
            'single_support_counts': dict.fromkeys(SINGLE_SUPPORT, 0), 'unsupported_state_count': 0}
    summary = {'state_count': len(states), 'no_single_target_state_count': 0,
               'no_pair_target_state_count': 0, 'eligible_side_pair_count': 0,
               'cartesian_target_count': 0, 'base_status_counts': dict.fromkeys(EXACT_STATUSES, 0),
               'single': single, 'pair': pair, 'oracle_record_count': len(records),
               'oracle_status_counts': dict.fromkeys(EXACT_STATUSES, 0),
               'oracle_origin_counts': {'new': 0, 'reused': 0},
               'oracle_node_counts': {'new': 0, 'reused': 0},
               'conditional_record_count': len(conditionals),
               'conditional_origin_counts': {'new': 0, 'reused': 0},
               'conditional_status_counts': dict.fromkeys(CONDITIONAL_STATUSES, 0)}
    for record in records:
        origin = 'new' if record['origin'] is None else 'reused'
        summary['oracle_origin_counts'][origin] += 1
        summary['oracle_node_counts'][origin] += record['result']['nodes']
        summary['oracle_status_counts'][record['result']['status']] += 1
    for conditional in conditionals:
        origin = 'new' if conditional['origin'] is None else 'reused'
        summary['conditional_origin_counts'][origin] += 1
        summary['conditional_status_counts'][conditional['status']] += 1
    for state in states:
        summary['base_status_counts'][records[state['base_oracle_index']]['result']['status']] += 1
        for field in ('eligible_side_pair_count', 'cartesian_target_count'):
            summary[field] += state[field]
        for name, section, action_key in (('single', single, 'action'), ('pair', pair, 'next_action')):
            targets = state[name + '_targets']
            summary['no_' + name + '_target_state_count'] += int(not targets)
            section['target_count'] += len(targets)
            section['unsupported_state_count'] += int(any(t['status'] == 'unsupported' for t in targets))
            for target in targets:
                status = target['status']
                section['status_counts'][status] += 1
                section['category_counts'][target['category']][status] += 1
                section[action_key + '_counts'][target[action_key]][status] += 1
                if target['conditional_index'] is not None:
                    section['conditional_counts'][conditionals[target['conditional_index']]['status']] += 1
                if name == 'pair' and target['single_support'] is not None:
                    section['single_support_counts'][target['single_support']] += 1
    return summary


def _source_index(sources, payload_name, payload_fields):
    """Index exact input content using first source, rejecting locator aliases.

    Unused historical pool entries are allowed; they are not reported as new
    evidence. The enclosing runner binds the source checkpoint bytes.
    """
    _require(isinstance(sources, (tuple, list)), 'source pool must be a sequence')
    origins, inputs = {}, {}
    for item in sources:
        _require(isinstance(item, dict) and set(item) == {'source', payload_name},
                 'invalid source pool entry')
        locator, payload = item['source'], item[payload_name]
        _require(isinstance(locator, dict) and bool(locator), 'source locator must be a nonempty object')
        _require(isinstance(payload, dict) and set(payload) == payload_fields,
                 'source payload fields differ')
        token = json.dumps(locator, sort_keys=True, allow_nan=False)
        if token in origins:
            _same(payload, origins[token], 'duplicate locator evidence')
        else:
            origins[token] = payload
        signature = _digest(payload['input'])
        if signature in inputs:
            _same(payload['input'], inputs[signature]['payload']['input'], 'source input hash collision')
        else:
            inputs[signature] = {'origin': locator, 'payload': payload}
    return inputs


def _bind_origin(record, pool):
    """A reported reuse must be the exact first eligible saved source record."""
    available = pool.get(_digest(record['input']))
    if available is None:
        _require(record['origin'] is None, 'reuse origin has no matching source query')
    else:
        _same(record['origin'], available['origin'], 'reuse origin does not use first matching source')
        _same({k: v for k, v in record.items() if k != 'origin'}, available['payload'],
              'reused evidence differs from bound source')


def check_support_scan(document, run, scan, *, node_limit=200000,
                       oracle_sources=(), conditional_sources=()):
    """Replay complete support coverage without rerunning any search or rule.

    Every unique raw certificate and conditional trace is checked once. Each
    target then binds only its precise raw premises and saved conditional input.
    The producer's full trace is already hash-bound to its prior saved audit by
    the enclosing runner, rather than repeated for each hypothetical target.
    """
    _integer(node_limit, 'node limit')
    inventory = support_inventory(document, run)
    _require(isinstance(scan, dict) and set(scan) == {
        'schema_version', 'version', 'raw_document', 'inventory', 'node_limit', 'states',
        'oracle_records', 'conditional_records', 'summary', 'oracle_feedback_to_producer', 'scope'},
        'unexpected support scan fields')
    for field, value in (('schema_version', 1), ('version', VERSION), ('raw_document', document),
                         ('inventory', inventory), ('node_limit', node_limit), ('scope', SCOPE)):
        _same(scan[field], value, 'support scan ' + field)
    _require(scan['oracle_feedback_to_producer'] is False, 'offline evidence fed back to producer')
    oracle_pool = _source_index(oracle_sources, 'record', {'input', 'result', 'verification'})
    conditional_pool = _source_index(conditional_sources, 'conditional',
                                     {'input', 'outcome', 'trace_audit', 'status'})
    sides = document['sides']
    index = {side: i for i, side in enumerate(sides)}
    edges = sorted({tuple(sorted((index[line['left']], index[line['right']])))
                    for line in document['lines'] if line['kind'] == 'separator'})
    records, signatures = scan['oracle_records'], set()
    _require(isinstance(records, list), 'oracle records must be an array')
    for record in records:
        _require(isinstance(record, dict) and set(record) == {'input', 'result', 'verification', 'origin'},
                 'unexpected oracle record fields')
        data = record['input']
        _require(isinstance(data, dict) and set(data) == {'n', 'edges', 'anchors'},
                 'oracle input contains non-raw premises')
        _same(data['n'], len(sides), 'raw oracle side count')
        _same(data['edges'], [list(edge) for edge in edges], 'raw oracle physical edges')
        fixed = {}
        _require(isinstance(data['anchors'], list), 'oracle anchors must be an ordered array')
        for literal in data['anchors']:
            _require(isinstance(literal, list) and len(literal) == 2, 'invalid oracle literal')
            vertex, color = literal
            _require(type(vertex) is int and 0 <= vertex < len(sides)
                     and type(color) is int and color in (1, 2, 3, 4), 'invalid oracle literal')
            _require(vertex not in fixed, 'duplicate oracle anchor')
            fixed[vertex] = color
        _same(data['anchors'], [[v, c] for v, c in sorted(fixed.items())], 'canonical raw anchors')
        signature = tuple(sorted(fixed.items()))
        _require(signature not in signatures, 'duplicate raw query evidence')
        signatures.add(signature)
        _bind_origin(record, oracle_pool)
        _same(record['result']['node_limit'], node_limit, 'raw oracle node limit')
        verified = verify_exact_result(len(sides), edges, fixed, record['result'])
        _same(record['verification'], verified, 'saved exact certificate verification')
    conditionals, conditional_inputs, trace_steps = scan['conditional_records'], set(), 0
    _require(isinstance(conditionals, list), 'conditional records must be an array')
    for conditional in conditionals:
        _require(isinstance(conditional, dict) and set(conditional) == {
            'input', 'outcome', 'trace_audit', 'status', 'origin'}, 'unexpected conditional record fields')
        signature = _digest(conditional['input'])
        _require(signature not in conditional_inputs, 'duplicate conditional input')
        conditional_inputs.add(signature)
        _bind_origin(conditional, conditional_pool)
        audited = audit_saturation_contacts(conditional['input'], conditional['outcome'])
        _same(conditional['trace_audit'], audited, 'conditional saved trace audit')
        _require(conditional['outcome']['status'] in ('conflict', 'underdetermined'),
                 'unsupported conditional cannot be solved')
        expected = ('conditional_refuted' if conditional['outcome']['status'] == 'conflict'
                    else 'conditional_inconclusive')
        _same(conditional['status'], expected, 'conditional rejection classification')
        trace_steps += audited['trace_steps_checked']
    used, used_conditionals, endpoint_references = set(), set(), 0

    def evidence(reference, fixed):
        """Bind a precise base, unary, or joint raw query in constant lookup time."""
        _integer(reference, 'oracle reference')
        _require(reference < len(records), 'oracle reference outside evidence')
        _same(records[reference]['input']['anchors'], [[v, c] for v, c in sorted(fixed.items())],
              'actual commitments and hypothesis binding')
        used.add(reference)
        return records[reference]['result']['status']

    def conditional_evidence(reference, phase, names, colors):
        """Conditional traces retain the actual phase's proved local premises."""
        _integer(reference, 'conditional reference')
        _require(reference < len(conditionals), 'conditional reference outside evidence')
        trial = deepcopy(run['phases'][phase]['document'])
        trial.setdefault('anchors', {}).update(zip(names, colors))
        _same(conditionals[reference]['input'], trial, 'conditional phase and hypothesis binding')
        used_conditionals.add(reference)

    states = scan['states']
    _require(isinstance(states, list) and len(states) == len(inventory['states']),
             'missing or extra persistent support state')
    for state, expected_state in zip(states, inventory['states']):
        _require(isinstance(state, dict) and set(state) == set(expected_state) | {'base_oracle_index'},
                 'unexpected persistent support state fields')
        for field in set(expected_state) - {'single_targets', 'pair_targets'}:
            _same(state[field], expected_state[field], 'persistent support ' + field)
        fixed = dict(expected_state['anchors'])
        base_status = evidence(state['base_oracle_index'], fixed)
        for kind in ('single', 'pair'):
            targets = state[kind + '_targets']
            expected_targets = expected_state[kind + '_targets']
            _require(isinstance(targets, list) and len(targets) == len(expected_targets),
                     'missing or extra ' + kind + ' target')
            added = {'status', 'conditional_index'} | (
                {'candidate_oracle_index'} if kind == 'single' else
                {'pair_oracle_index', 'single_oracle_indices', 'single_support'})
            for target, expected_target in zip(targets, expected_targets):
                _require(isinstance(target, dict) and set(target) == set(expected_target) | added,
                         'unexpected ' + kind + ' target fields')
                for field in expected_target:
                    _same(target[field], expected_target[field], kind + ' target ' + field)
                vertices = [target['side_index']] if kind == 'single' else target['side_indices']
                colors = [target['symbol']] if kind == 'single' else target['symbols']
                names = [target['side']] if kind == 'single' else target['sides']
                hypotheses = dict(zip(vertices, colors))
                reference = target['candidate_oracle_index' if kind == 'single' else 'pair_oracle_index']
                child_status = evidence(reference, {**fixed, **hypotheses})
                status = ('preexisting_unsat' if base_status == 'unsat' else
                          'unknown' if 'unknown' in (base_status, child_status) else
                          'unsupported' if child_status == 'unsat' else 'supported')
                _same(target['status'], status, kind + ' support classification')
                if status != 'unsupported':
                    _require(target['conditional_index'] is None, 'conditional for a supported/unknown target')
                    if kind == 'pair':
                        _require(target['single_oracle_indices'] is None and target['single_support'] is None,
                                 'endpoint diagnosis without an unsupported pair')
                    continue
                conditional_evidence(target['conditional_index'], state['phase'], names, colors)
                if kind == 'pair':
                    singles = target['single_oracle_indices']
                    _require(isinstance(singles, list) and len(singles) == 2, 'missing pair endpoint evidence')
                    statuses = [evidence(ref, {**fixed, vertex: color})
                                for vertex, color, ref in zip(vertices, colors, singles)]
                    expected = ('has_unsupported_single' if 'unsat' in statuses else
                                'unknown_single' if 'unknown' in statuses else 'both_supported')
                    _same(target['single_support'], expected, 'pair single-endpoint classification')
                    endpoint_references += 2
    _require(used == set(range(len(records))), 'hidden unused exact evidence')
    _require(used_conditionals == set(range(len(conditionals))), 'hidden unused conditional evidence')
    summary = _summary(states, records, conditionals)
    _same(scan['summary'], summary, 'complete support summary')
    return {'passed': True, 'check_version': CHECK_VERSION, 'summary': summary,
            'persistent_states_checked': len(states),
            'single_targets_checked': summary['single']['target_count'],
            'pair_targets_checked': summary['pair']['target_count'],
            'oracle_records': len(records), 'oracle_statuses': summary['oracle_status_counts'],
            'conditional_records_checked': len(conditionals),
            'conditional_trace_steps_checked': trace_steps,
            'single_endpoint_queries_checked': endpoint_references,
            'producer_runs': 0, 'oracle_searches': 0, 'propagation_runs': 0}



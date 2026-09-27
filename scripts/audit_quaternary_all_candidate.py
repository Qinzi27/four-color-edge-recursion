"""Independently replay all-candidate sweeps, raw witnesses and exact certificates.

Temporary probes do not change persistent commitments or invoke the geometric
scheduler; certified deletions can affect later scheduled commitments.
This auditor reconstructs every scan in input-side/literal order, permits a
commitment only after a complete stable sweep, and binds its reused trial to
that sweep. Learned EQ, propagated domains and failed-candidate restrictions
are never premises of the raw exact oracle. The saved checker uses this same
independent reconstruction with stored certificates instead of oracle search.
"""

from collections import Counter
from copy import deepcopy
from itertools import product
from math import prod
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.global_restart import current_segments
from fourcolor.level_sides import level_metadata
from fourcolor.whole_lines import build_whole_lines
from scripts.audit_quaternary_geometry import audit_bounded_contacts, audit_geometry, _same
from scripts.audit_quaternary_low_color import _preserved, _selection
from scripts.exact_extendibility_oracle import solve_exact, verify_exact_result
from scripts.quaternary_odd_cycle_eq import verify_odd_cycle_equalities
from scripts.validate_quaternary_contacts_v2 import expected_state, raw_metadata, require

POLICY = 'quaternary-low-color-all-candidate-v1'
AUDIT_VERSION = 'quaternary-low-color-all-candidate-audit-v1'
ORACLE_SCOPE = 'original_real_neq_initial_anchors_and_actual_commitments_only'


def _bind(document, envelope, geometry, adapted):
    """Bind certified EQ, physical geometry, and the producer's resource contract."""
    require(not document.get('states') and not document.get('equal_names'),
            'all-candidate raw input requires NEQ and anchors only; states/EQ unsupported')
    require(type(envelope['schema_version']) is int and envelope['schema_version'] == 1
            and envelope['policy'] == POLICY, 'wrong all-candidate envelope schema')
    require(envelope['oracle_feedback_to_producer'] is False
            and envelope['old_colors_read'] is False, 'invalid envelope production mode')
    _same(envelope['original_input'], document, 'original raw input')
    equality_check = verify_odd_cycle_equalities(document, envelope['learning'])
    require(equality_check['passed'] is True, 'odd-cycle equality verification failed')
    augmented = deepcopy(document)
    if envelope['learning']['equal_names']:
        augmented['equal_names'] = deepcopy(envelope['learning']['equal_names'])
    _same(envelope['augmented_input'], augmented, 'augmented equality input')
    result = envelope['run']
    _same(result['original_input'], augmented, 'producer augmented input')
    require(type(result['schema_version']) is int and result['schema_version'] == 1
            and result['policy'] == POLICY, 'wrong all-candidate producer schema')
    require(result['probe'] is True and type(result['backtracks']) is int
            and result['backtracks'] == 0 and result['oracle_feedback_to_producer'] is False
            and result['old_colors_read'] is False, 'invalid producer mode')
    for field in ('decision_limit', 'probe_limit'):
        require(type(result[field]) is int and result[field] >= 0, 'invalid producer resource limit')
    sides, domains, _ = raw_metadata(document)
    index = {side: i for i, side in enumerate(sides)}
    edges = sorted({tuple(sorted((index[line['left']], index[line['right']])))
                    for line in document['lines'] if line['kind'] == 'separator'})
    require((geometry is None) == (adapted is None), 'geometry and adapted required together')
    geometry_check, context = None, None
    if geometry is not None:
        _same(adapted['contact_document'], document, 'raw geometry adapter input')
        geometry_check, actual_edges = audit_geometry(geometry, adapted)
        require(actual_edges == edges, 'raw graph and geometry edge coverage differs')
        model = build_whole_lines(geometry)
        require(sides == ['S' + str(i) for i in range(len(model.plane_map.faces))],
                'geometry requires original ordered side identities')
        context = model, current_segments(model), level_metadata(model)
    require(result['schedule'] == ('mother-peer-with-frame-only-fallback-v1' if context else
                                   'first-unresolved-input-order-v1'), 'schedule label differs')
    return augmented, result, equality_check, sides, domains, edges, geometry_check, context


def _reconstruct(augmented, result, sides, context):
    """Reconstruct complete sweeps and raw assumptions without producer helpers.

    A conflict stops the sweep immediately. A successful trial is only a probe;
    all remaining candidates must be examined before the selected cached trial
    can become persistent. A partial sweep cannot authorize a commitment.
    """
    phases, events = result['phases'], result['events']
    require(isinstance(phases, list) and bool(phases) and isinstance(events, list),
            'missing propagation phases or events')
    require(phases[0]['kind'] == 'main', 'initial phase must be main')
    _same(phases[0]['document'], augmented, 'initial augmented phase')
    index = {side: i for i, side in enumerate(sides)}
    committed = {index[side]: color for side, color in augmented.get('anchors', {}).items()}
    phase_fixed = {0: dict(committed)}
    event_fixed = []
    current, consumed, position = 0, 1, 0
    choices, probes, rejections, started, completed = 0, 0, 0, 0, 0
    stop = None

    def event_at():
        """Fail if a complete sweep or promised transition is omitted."""
        require(position < len(events), 'missing event or incomplete sweep coverage')
        event = events[position]
        require(type(event['before_phase']) is int and event['before_phase'] == current,
                'event does not reference latest persistent phase')
        return event

    def identity(event, side_index, symbol, candidates):
        """Check literal target ordering and the exact previous domain."""
        require(event['side'] == sides[side_index] and type(event['symbol']) is int
                and event['symbol'] == symbol, 'candidate sweep order or identity differs')
        _same(event['candidates_before'], candidates, 'candidate domain before event')

    while phases[current]['outcome']['status'] == 'underdetermined':
        if choices >= result['decision_limit']:
            stop = 'decision-limit-exhausted'
            break
        started += 1
        before = phases[current]['outcome']
        inventory = [(i, color) for i, values in enumerate(before['domains'])
                     if len(values) > 1 for color in sorted(values)]
        require(bool(inventory), 'underdetermined outcome has no unresolved candidates')
        cache, rejected = {}, False
        for selected, symbol in inventory:
            if probes >= result['probe_limit']:
                stop = 'probe-limit-exhausted'
                break
            event = event_at()
            candidates = before['domains'][selected]
            identity(event, selected, symbol, candidates)
            require(event['selection'] is None, 'scan event carries commitment scheduler metadata')
            require(type(event['trial_phase']) is int and event['trial_phase'] == consumed
                    and consumed < len(phases), 'trial phase omitted, reused, or out of order')
            trial = phases[consumed]
            require(trial['kind'] == 'trial', 'candidate requires trial phase')
            proposed = deepcopy(phases[current]['document'])
            proposed.setdefault('anchors', {})[sides[selected]] = symbol
            _same(trial['document'], proposed, 'trial assumptions')
            trial_fixed = {**committed, selected: symbol}
            phase_fixed[consumed] = trial_fixed
            trial_phase = consumed
            consumed += 1
            probes += 1
            before_phase = current
            if trial['outcome']['status'] == 'conflict':
                require(event['kind'] == 'reject' and event['extension_claim'] == 'refuted',
                        'conflict must immediately reject and restart the sweep')
                restricted = deepcopy(phases[current]['document'])
                remaining = [color for color in candidates if color != symbol]
                restricted.setdefault('states', {})[sides[selected]] = expected_state(remaining, False)['quaternary']
                require(consumed < len(phases) and phases[consumed]['kind'] == 'main',
                        'rejection requires a new persistent main phase')
                _same(phases[consumed]['document'], restricted, 'post-rejection restrictions')
                current = consumed
                phase_fixed[current] = dict(committed)
                consumed += 1
                rejections += 1
                rejected = True
            else:
                require(event['kind'] == 'probe', 'surviving trial must be a probe event')
                claim = 'complete-witness' if trial['outcome']['status'] == 'solved' else 'inconclusive'
                require(event['extension_claim'] == claim, 'probe overstates its extension evidence')
                cache[(selected, symbol)] = trial_phase
            require(type(event['after_phase']) is int and event['after_phase'] == current,
                    'scan changes persistent phase incorrectly')
            event_fixed.append((dict(committed), trial_fixed, dict(committed)))
            position += 1
            if rejected:
                break
            require(current == before_phase, 'surviving probe changed the persistent phase')
        if stop:
            break
        if rejected:
            continue
        completed += 1
        event = event_at()
        selected, selection = _selection(sides, before['domains'], context)
        candidates = before['domains'][selected]
        symbol = min(candidates)
        identity(event, selected, symbol, candidates)
        require(event['kind'] == 'commit', 'complete stable sweep must be followed by commitment')
        selection.update(side_id=sides[selected], candidate_order=candidates)
        _same(event['selection'], selection, 'commitment scheduler metadata')
        trial_phase = cache[(selected, symbol)]
        require(type(event['trial_phase']) is int and event['trial_phase'] == trial_phase,
                'commit must reuse the selected trial from the current completed sweep')
        current = trial_phase
        claim = 'complete-witness' if phases[current]['outcome']['status'] == 'solved' else 'inconclusive'
        require(event['extension_claim'] == claim, 'commitment overstates extension evidence')
        require(type(event['after_phase']) is int and event['after_phase'] == current,
                'commitment must persist exactly its cached trial')
        proposed_fixed = {**committed, selected: symbol}
        event_fixed.append((dict(committed), proposed_fixed, proposed_fixed))
        committed = proposed_fixed
        choices += 1
        position += 1
    require(position == len(events), 'unconsumed event or event after terminal/resource stop')
    require(consumed == len(phases), 'unreferenced propagation phase')
    require(type(result['final_phase']) is int and result['final_phase'] == current,
            'final persistent phase differs')
    for field, expected in (('choices', choices), ('probes', probes), ('rejections', rejections),
                            ('sweeps_started', started), ('sweeps_completed', completed)):
        require(type(result[field]) is int and result[field] == expected, 'incorrect event/sweep telemetry: ' + field)
    require(len(phases) == 1 + probes + rejections and len(events) == probes + choices,
            'propagation-call accounting differs')
    final = phases[current]['outcome']
    for field in ('name_states', 'domains', 'colors'):
        _same(result[field], final[field], 'final ' + field)
    if stop:
        require(result['status'] == 'incomplete' and result['reason'] == stop,
                'resource stop mislabeled')
    else:
        require(final['status'] in ('solved', 'conflict') and result['status'] == final['status'],
                'terminal status differs')
        expected_reason = ('complete-coloring-verified' if final['status'] == 'solved'
                           else 'propagation-conflict-under-current-commitments')
        require(result['reason'] == expected_reason, 'terminal reason differs')
    require(set(phase_fixed) == set(range(len(phases))), 'raw phase assumption coverage differs')
    return phase_fixed, event_fixed


def _audit(document, envelope, *, geometry, adapted, assignment_limit, node_limit, saved_records=None):
    """Build the same evidence from fresh search or strictly bound saved records."""
    for value in (assignment_limit, node_limit):
        require(type(value) is int and value >= 0, 'invalid independent audit resource limit')
    augmented, result, eq, sides, domains, edges, geometric, context = _bind(
        document, envelope, geometry, adapted)
    phase_fixed, event_fixed = _reconstruct(augmented, result, sides, context)
    phases = result['phases']
    phase_audits = [audit_bounded_contacts(phase['document'], phase['outcome']) for phase in phases]
    records, cache = [], {}

    def raw_oracle(fixed):
        """First-use order and exact raw signatures bind every reused certificate."""
        signature = tuple(sorted(fixed.items()))
        if signature in cache:
            return cache[signature]
        raw = {'n': len(sides), 'edges': [list(edge) for edge in edges],
               'anchors': [list(pair) for pair in signature]}
        if saved_records is None:
            evidence = solve_exact(len(sides), edges, fixed, node_limit=node_limit)
            verified = verify_exact_result(len(sides), edges, fixed, evidence)
            record = {'input': raw, 'result': evidence, 'verification': verified}
        else:
            require(len(records) < len(saved_records), 'missing saved oracle certificate')
            record = saved_records[len(records)]
            _same(record['input'], raw, 'saved oracle raw graph or commitment binding')
            require(type(record['input']['n']) is int, 'oracle vertex count is not an integer')
            require(type(record['result']['node_limit']) is int and record['result']['node_limit'] == node_limit,
                    'saved oracle resource budget differs')
            verified = verify_exact_result(len(sides), edges, fixed, record['result'])
            _same(record['verification'], verified, 'saved exact certificate verification')
        require(verified['passed'] is True, 'exact certificate verification failed')
        cache[signature] = len(records)
        records.append(record)
        return cache[signature]

    initial_oracle = raw_oracle(phase_fixed[0])
    commitments = dict.fromkeys(('safe', 'unsafe', 'unknown', 'preexisting_unsat'), 0)
    rejections = dict.fromkeys(('exact_unsat', 'unknown'), 0)
    probes = dict.fromkeys(('supported', 'unsupported', 'unknown', 'preexisting_unsat'), 0)
    steps, first_bad = [], None
    for number, (event, assumptions) in enumerate(zip(result['events'], event_fixed)):
        before_index, trial_index, after_index = (raw_oracle(fixed) for fixed in assumptions)
        b = records[before_index]['result']['status']
        t = records[trial_index]['result']['status']
        a = records[after_index]['result']['status']
        if event['kind'] == 'reject':
            require(t != 'sat', 'rejected trial has a complete raw witness')
            extension = 'refuted'
            rejections['exact_unsat' if t == 'unsat' else 'unknown'] += 1
        elif event['kind'] == 'probe':
            extension = ('preexisting_unsat' if b == 'unsat' else 'unknown' if 'unknown' in (b, t)
                         else 'unsupported' if t == 'unsat' else 'supported')
            probes[extension] += 1
        else:
            extension = ('preexisting_unsat' if b == 'unsat' else 'unknown' if 'unknown' in (b, t)
                         else 'unsafe' if t == 'unsat' else 'safe')
            commitments[extension] += 1
        step = {'event_index': number, **{field: event[field] for field in
                ('kind', 'side', 'symbol', 'before_phase', 'trial_phase', 'after_phase')},
                'before_oracle_index': before_index, 'trial_oracle_index': trial_index,
                'after_oracle_index': after_index, 'before_status': b, 'trial_status': t,
                'after_status': a, 'extendibility': extension}
        steps.append(step)
        if extension == 'unsafe' and first_bad is None:
            first_bad = {**step, 'event': deepcopy(event), 'before': deepcopy(records[before_index]),
                         'after': deepcopy(records[after_index])}
    # Each allocated trial/main phase has one unambiguous raw commitment set.
    size = prod(len(values) for values in domains)
    enumerate_all = size <= assignment_limit
    initial_legal = ([values for values in product(*domains)
                      if all(values[a] != values[b] for a, b in edges)] if enumerate_all else None)
    preserved_count = 0
    for number, phase in enumerate(phases):
        fixed = phase_fixed[number]
        oracle_index = raw_oracle(fixed)
        oracle = records[oracle_index]['result']
        if enumerate_all:
            legal = [values for values in initial_legal
                     if all(values[side] == color for side, color in fixed.items())]
            _preserved(phase['outcome'], legal)
            preserved_count += len(legal)
            if oracle['status'] != 'unknown':
                require(bool(legal) == (oracle['status'] == 'sat'), 'raw enumeration and oracle disagree')
        if oracle['status'] == 'sat':
            _preserved(phase['outcome'], [oracle['witness']])
    if saved_records is not None:
        require(len(records) == len(saved_records), 'unreferenced or duplicate oracle certificate')
    final = phases[result['final_phase']]['outcome']
    if final['colors'] is not None:
        values = [final['colors'][side] for side in sides]
        require(all(values[i] in domains[i] for i in range(len(sides)))
                and all(values[a] != values[b] for a, b in edges), 'final colors violate original raw constraints')
    return {'passed': True, 'audit_version': AUDIT_VERSION, 'geometry': geometric,
            'odd_cycle_eq_check': eq, 'phase_count': len(phases), 'phase_audits': phase_audits,
            'trace_steps_checked': sum(item['trace_steps_checked'] for item in phase_audits),
            'initial_oracle_index': initial_oracle, 'oracle_records': records, 'steps': steps,
            'first_bad_commitment': first_bad, 'commitment_counts': commitments,
            'rejection_counts': rejections, 'probe_counts': probes,
            'oracle_unknown': sum(record['result']['status'] == 'unknown' for record in records),
            'full_enumeration': {'status': 'run' if enumerate_all else 'not_run',
                'reason': None if enumerate_all else 'initial_assignment_product_exceeds_limit',
                'assignment_product': size, 'assignment_limit': assignment_limit,
                'literal_assignments_checked': size if enumerate_all else 0,
                'initial_legal_assignments': len(initial_legal) if enumerate_all else None,
                'phase_checks': len(phases) if enumerate_all else 0,
                'legal_assignments_preserved': preserved_count},
            'oracle_scope': ORACLE_SCOPE, 'oracle_feedback_to_producer': False,
            'schedule_audit': ('shared_mother_peer_selector_with_explicit_frame_fallback' if context
                               else 'independent_first_unresolved_input_order'),
            'sweep_audit': 'independent_complete_input_side_then_literal_sweep_with_restart_on_rejection',
            'scope': 'Evidence integrity is separate from commitment safety. Unsupported surviving probes '
                     'are inference gaps, not failed commitments. UNKNOWN is not safe or UNSAT.'}


def audit_all_candidates(document, envelope, *, geometry=None, adapted=None,
                         assignment_limit=262144, node_limit=200000):
    """Audit a completed producer run, querying only the independent raw oracle."""
    return _audit(document, envelope, geometry=geometry, adapted=adapted,
                  assignment_limit=assignment_limit, node_limit=node_limit)


def check_all_candidate_artifacts(document, envelope, audit, resources, *, geometry=None, adapted=None):
    """Replay saved traces/certificates without propagation, producer or exact search."""
    for field in ('decision_limit', 'probe_limit', 'assignment_limit', 'node_limit'):
        require(type(resources[field]) is int and resources[field] >= 0, 'invalid saved resource limit')
    require(envelope['run']['decision_limit'] == resources['decision_limit']
            and envelope['run']['probe_limit'] == resources['probe_limit'], 'producer limits differ')
    expected = _audit(document, envelope, geometry=geometry, adapted=adapted,
                      assignment_limit=resources['assignment_limit'], node_limit=resources['node_limit'],
                      saved_records=audit['oracle_records'])
    _same(audit, expected, 'saved all-candidate audit reconstruction')
    statuses = Counter(record['result']['status'] for record in audit['oracle_records'])
    return {'passed': True, 'odd_cycle_eq_check': expected['odd_cycle_eq_check'], 'producer_runs': 0,
            'oracle_searches': 0, 'propagation_runs': 0, 'oracle_records': len(audit['oracle_records']),
            'oracle_statuses': dict(statuses), 'phases': audit['phase_count'],
            'unsafe_commitments': audit['commitment_counts']['unsafe']}

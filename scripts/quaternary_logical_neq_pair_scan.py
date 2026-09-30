"""Inspect simultaneous two-face support after a frozen producer has stopped.

Each obligation is allowed by the saved binary relation and both endpoint
domains. Exact queries contain only physical separator edges and actual
commitments plus the two proposed colors. A pair containing the next chosen
literal is not a joint commitment: the frozen algorithm chooses one face at
a time, and this diagnostic never changes that algorithm.
"""

from copy import deepcopy

from scripts.audit_quaternary_logical_neq import audit_logical_contacts
from scripts.exact_extendibility_oracle import solve_exact, verify_exact_result
from scripts.quaternary_logical_neq_candidate_scan import candidate_inventory
from scripts.quaternary_logical_neq_contacts import propagate_logical_contacts
from scripts.validate_quaternary_contacts_v2 import check_matrix, require


VERSION = 'quaternary-logical-neq-pair-scan-v1'
INVENTORY_SCOPE = ('Initial phase and every persistent event after-phase; rejected trial '
                   'phases excluded; both endpoints unresolved; i < j; only saved final '
                   'binary-relation pairs within the endpoint domains.')
SCOPE = ('Offline joint support of retained two-face candidates in a frozen run; exact '
         'queries use original separator edges and actual commitments only. Including '
         'the next chosen literal is not a joint commitment; UNKNOWN is not UNSAT.')
CATEGORIES = ('both_min', 'one_min', 'neither_min')
NEXT_ACTIONS = ('includes_next_commit', 'includes_next_reject', 'not_next_choice')
TARGET_STATUSES = ('supported', 'unsupported', 'unknown', 'preexisting_unsat')
ORACLE_STATUSES = ('sat', 'unsat', 'unknown')
CONDITIONAL_STATUSES = ('conditional_refuted', 'conditional_inconclusive')
SINGLE_SUPPORT_STATUSES = ('both_supported', 'has_unsupported_single', 'unknown_single')


def pair_inventory(document, run):
    """Bind saved persistent states and enumerate their directed color pairs.

    The old inventory validates anchor provenance and the event/phase chain.
    Its unary targets are discarded. Matrix shape, transpose direction, domain
    diagonals and containment are checked before any pair can become a target.
    This routine performs no production, propagation or oracle search.
    """
    inherited = candidate_inventory(document, run)
    states = deepcopy(inherited['states'])
    sides, size = document['sides'], len(document['sides'])
    for state in states:
        outcome = run['phases'][state['phase']]['outcome']
        domains, matrix = outcome['domains'], outcome['relations']
        check_matrix(matrix, size, 'pair inventory final relations')
        for i, domain in enumerate(domains):
            require(matrix[i][i] == sum(1 << (5 * (a - 1)) for a in domain),
                    'pair inventory diagonal does not match domain')
            for j, other in enumerate(domains):
                allowed = sum(1 << (4 * (a - 1) + b - 1) for a in domain for b in other)
                require(matrix[i][j] & ~allowed == 0,
                        'pair inventory relation exceeds endpoint domains')
        next_event = state['next_event_index']
        event = run['events'][next_event] if next_event is not None else None
        targets, eligible, cartesian = [], 0, 0
        for i, first in enumerate(domains):
            if len(first) <= 1:
                continue
            for j in range(i + 1, size):
                second = domains[j]
                if len(second) <= 1:
                    continue
                eligible += 1
                cartesian += len(first) * len(second)
                for a in first:
                    for b in second:
                        if not matrix[i][j] & (1 << (4 * (a - 1) + b - 1)):
                            continue
                        minima = int(a == first[0]) + int(b == second[0])
                        category = ('neither_min', 'one_min', 'both_min')[minima]
                        action = 'not_next_choice'
                        if event is not None and (event['side'], event['symbol']) in (
                                (sides[i], a), (sides[j], b)):
                            action = ('includes_next_commit' if event['kind'] == 'commit'
                                      else 'includes_next_reject')
                        targets.append({'side_indices': [i, j], 'sides': [sides[i], sides[j]],
                                        'symbols': [a, b], 'category': category,
                                        'next_action': action})
        state.update(targets=targets, eligible_side_pair_count=eligible,
                     cartesian_target_count=cartesian)
    return {'states': states, 'scope': INVENTORY_SCOPE}


def summarize_states(states, oracle_records):
    """Count pair obligations, endpoint diagnoses, and cached exact records."""
    summary = {'state_count': len(states), 'target_count': 0, 'no_target_state_count': 0,
               'eligible_side_pair_count': 0, 'cartesian_target_count': 0,
               'base_status_counts': dict.fromkeys(ORACLE_STATUSES, 0),
               'target_status_counts': dict.fromkeys(TARGET_STATUSES, 0),
               'category_counts': {key: dict.fromkeys(TARGET_STATUSES, 0) for key in CATEGORIES},
               'next_action_counts': {key: dict.fromkeys(TARGET_STATUSES, 0) for key in NEXT_ACTIONS},
               'conditional_counts': dict.fromkeys(CONDITIONAL_STATUSES, 0),
               'single_support_counts': dict.fromkeys(SINGLE_SUPPORT_STATUSES, 0),
               'unsupported_state_count': 0, 'oracle_record_count': len(oracle_records),
               'oracle_status_counts': dict.fromkeys(ORACLE_STATUSES, 0)}
    for record in oracle_records:
        summary['oracle_status_counts'][record['result']['status']] += 1
    for state in states:
        summary['base_status_counts'][oracle_records[state['base_oracle_index']]['result']['status']] += 1
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
            if target['single_support'] is not None:
                summary['single_support_counts'][target['single_support']] += 1
    return summary


def scan_pairs(document, run, *, node_limit=200000):
    """Save complete exact support evidence for every retained pair.

    Unsupported means a SAT base and an UNSAT conjunction. Separate one-color
    queries then distinguish a true joint obstruction from an already bad
    endpoint. Conditional propagation adds both hypotheses to the saved
    persistent document, preserving logical premises solely for diagnosis.
    It never returns a deletion or rescue color to the frozen producer.
    """
    require(type(node_limit) is int and node_limit >= 0, 'invalid pair oracle node limit')
    inventory = pair_inventory(document, run)
    sides = document['sides']
    index = {side: number for number, side in enumerate(sides)}
    edges = sorted({tuple(sorted((index[line['left']], index[line['right']])))
                    for line in document['lines'] if line['kind'] == 'separator'})
    records, cache = [], {}

    def exact(fixed):
        """Cache only identical raw-adjacency and literal-anchor queries."""
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
            hypotheses = dict(zip(target['side_indices'], target['symbols']))
            target['pair_oracle_index'] = exact({**fixed, **hypotheses})
            child_status = records[target['pair_oracle_index']]['result']['status']
            if base_status == 'unsat':
                classification = 'preexisting_unsat'
            elif base_status == 'unknown' or child_status == 'unknown':
                classification = 'unknown'
            else:
                classification = 'supported' if child_status == 'sat' else 'unsupported'
            target.update(status=classification, conditional=None,
                          single_oracle_indices=None, single_support=None)
            if classification != 'unsupported':
                continue
            singles = [exact({**fixed, vertex: color}) for vertex, color in hypotheses.items()]
            single_statuses = [records[reference]['result']['status'] for reference in singles]
            target['single_oracle_indices'] = singles
            target['single_support'] = ('has_unsupported_single' if 'unsat' in single_statuses
                                        else 'unknown_single' if 'unknown' in single_statuses
                                        else 'both_supported')
            proposal = deepcopy(run['phases'][state['phase']]['document'])
            proposal.setdefault('anchors', {}).update(zip(target['sides'], target['symbols']))
            outcome = propagate_logical_contacts(proposal)
            audited = audit_logical_contacts(proposal, outcome)
            require(outcome['status'] != 'solved',
                    'conditional solved witness contradicts verified raw pair UNSAT')
            conditional_status = ('conditional_refuted' if outcome['status'] == 'conflict'
                                  else 'conditional_inconclusive')
            target['conditional'] = {'input': proposal, 'outcome': outcome,
                                     'trace_audit': audited, 'status': conditional_status}
    return {'schema_version': 1, 'version': VERSION, 'raw_document': deepcopy(document),
            'inventory': inventory, 'node_limit': node_limit, 'states': states,
            'oracle_records': records, 'summary': summarize_states(states, records),
            'oracle_feedback_to_producer': False, 'scope': SCOPE}

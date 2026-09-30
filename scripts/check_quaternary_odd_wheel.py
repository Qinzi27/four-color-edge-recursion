"""Independently check domain-restricted odd-wheel conflicts.

The certificate is a real-edge odd wheel whose vertices all exclude one common
color. Its center consumes one of the remaining three colors, leaving at most
two for its odd rim. This proves a conflict under the supplied domains only.
The contact wrapper first replays the frozen literal relation trace to establish
those domains. No detector, color search, or producer function is imported.
"""

from copy import deepcopy

from scripts.audit_quaternary_geometry import _same
from scripts.audit_quaternary_logical_neq import audit_logical_contacts, logical_metadata
from scripts.scan_low_color_obstruction_states import digest
from scripts.validate_quaternary_contacts_v2 import check_domains, require


VERSION = 'quaternary-domain-odd-wheel-v1'
MODEL = 'quaternary-odd-wheel-contact-relations-v1'
STATISTICS = {'palettes_examined', 'centers_examined', 'eligible_neighbor_sets',
              'bfs_components', 'vertices_visited', 'edges_examined', 'odd_cycles_found'}


def _has_restricted_wheel(adjacency, domains):
    """Decide the pattern independently using stack-based two-coloring.

    A center's eligible neighborhood contains an odd cycle exactly when its
    induced real-edge graph is not bipartite. This only certifies completeness
    of this finite pattern search, never satisfiability of the whole problem.
    """
    for excluded in range(1, 5):
        eligible = {i for i, values in enumerate(domains) if excluded not in values}
        for center in eligible:
            neighbors = adjacency[center] & eligible
            parity = {}
            for start in neighbors:
                if start in parity:
                    continue
                parity[start] = 0
                stack = [start]
                while stack:
                    vertex = stack.pop()
                    for other in adjacency[vertex] & neighbors:
                        if other not in parity:
                            parity[other] = 1 - parity[vertex]
                            stack.append(other)
                        elif parity[other] == parity[vertex]:
                            return True
    return False


def check_odd_wheel(document, domains, check):
    """Verify a literal witness or independently validate its declared absence.

    Domain provenance belongs to ``audit_wheel_contacts``; a standalone call
    establishes only the combinatorial statement for these supplied domains.
    Work counters are type/bounds checked, not replayed as detector telemetry.
    """
    sides, _, _ = logical_metadata(document)
    check_domains(domains, len(sides), 'wheel domains')
    require(isinstance(check, dict) and set(check) ==
            {'version', 'raw_document_sha256', 'domains_sha256', 'certificate', 'statistics'},
            'wheel check fields differ')
    require(check['version'] == VERSION, 'wheel check version differs')
    _same(check['raw_document_sha256'], digest(document), 'wheel document hash')
    _same(check['domains_sha256'], digest(domains), 'wheel domains hash')
    statistics = check['statistics']
    require(isinstance(statistics, dict) and set(statistics) == STATISTICS
            and all(type(value) is int and value >= 0 for value in statistics.values()),
            'wheel statistics require literal nonnegative integers')
    require(statistics['palettes_examined'] <= 4
            and statistics['centers_examined'] <= 4 * len(sides), 'wheel counter bounds differ')
    positions = {side: i for i, side in enumerate(sides)}
    adjacency = [set() for _ in sides]
    for line in document['lines']:
        if line['kind'] == 'separator':
            a, b = positions[line['left']], positions[line['right']]
            adjacency[a].add(b)
            adjacency[b].add(a)
    certificate = check['certificate']
    if certificate is None:
        require(statistics['odd_cycles_found'] == 0, 'absent wheel has positive cycle count')
        require(not _has_restricted_wheel(adjacency, domains), 'omitted restricted odd wheel')
    else:
        require(isinstance(certificate, dict) and set(certificate) ==
                {'center', 'rim', 'excluded_color'}, 'wheel certificate fields differ')
        center, rim, excluded = (certificate['center'], certificate['rim'],
                                 certificate['excluded_color'])
        require(isinstance(center, str) and center in positions, 'unknown wheel center')
        require(isinstance(rim, list) and len(rim) >= 3 and len(rim) % 2 == 1
                and all(isinstance(side, str) and side in positions for side in rim)
                and len(set(rim)) == len(rim) and center not in rim,
                'rim must be odd, distinct, known, and exclude its center')
        require(type(excluded) is int and 1 <= excluded <= 4, 'invalid excluded color literal')
        vertices = [positions[center]] + [positions[side] for side in rim]
        require(all(excluded not in domains[i] for i in vertices),
                'wheel does not share an excluded color')
        require(all(positions[side] in adjacency[positions[center]] for side in rim),
                'wheel spoke is not a real separator')
        require(all(positions[rim[(i + 1) % len(rim)]] in adjacency[positions[side]]
                    for i, side in enumerate(rim)), 'wheel rim edge is not a real separator')
        require(statistics['odd_cycles_found'] == 1, 'present wheel cycle count differs')
    found = certificate is not None
    return {'passed': True, 'found': found, 'certificate_checked': found,
            'absence_checked': not found,
            'telemetry_scope': 'literal_bounds_only_not_detector_work_replay',
            'scope': 'Conflict under supplied domains; absence means no declared real-edge '
                     'common-excluded-color odd wheel, not global satisfiability.'}


def audit_wheel_contacts(document, outcome):
    """Replay frozen propagation before accepting the added conflict claim.

    All old domains, matrices, state encodings and traces must pass unchanged.
    A wheel may change only an underdetermined base status into conflict.
    """
    require(isinstance(outcome, dict) and outcome.get('model') == MODEL
            and 'base_status' in outcome and 'wheel_check' in outcome,
            'wrong wheel contact producer')
    base = deepcopy(outcome)
    base['model'] = 'quaternary-logical-neq-contact-relations-v1'
    base['status'] = base.pop('base_status')
    wheel = base.pop('wheel_check')
    # This independent literal replay establishes every final-domain exclusion.
    audited = audit_logical_contacts(document, base)
    if base['status'] == 'underdetermined':
        wheel_audit = check_odd_wheel(document, base['domains'], wheel)
        status = 'conflict' if wheel_audit['found'] else base['status']
    else:
        require(wheel is None, 'terminal base propagation must not carry a wheel check')
        wheel_audit, status = None, base['status']
    require(outcome['status'] == status, 'wheel status differs from certified rule')
    return {**audited, 'base_status': base['status'], 'wheel_check': wheel_audit,
            'status': status,
            'complete_assignment_preservation':
                'literal_pair_composition_then_real_edge_common_excluded_color_odd_wheel'}

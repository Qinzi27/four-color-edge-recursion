"""Independently replay common-three-color diamond equality certificates.

The physical edge a-b uses two distinct names. When a,b,u,v all exclude the
same fourth name, their four physical spokes force u and v to use the third
name. These are conditional local equalities, not new physical edges or
global color-independent facts. Neither the detector nor color search is
imported here; completeness is checked by an independent direct enumeration.
"""

from copy import deepcopy
from itertools import combinations

from scripts.audit_quaternary_geometry import _same
from scripts.audit_quaternary_logical_neq import logical_metadata
from scripts.check_quaternary_odd_wheel import audit_wheel_contacts
from scripts.scan_low_color_obstruction_states import digest
from scripts.validate_quaternary_contacts_v2 import check_domains, check_matrix, require


VERSION = 'quaternary-conditional-diamond-eq-v1'
MODEL = 'quaternary-conditional-diamond-contact-relations-v1'
CLOSURE_VERSION = 'quaternary-conditional-diamond-closure-v1'
STATISTICS = {'pairs_examined', 'pairs_with_offdiagonal', 'palettes_examined',
              'common_edges_examined', 'certificates_found'}


def check_conditional_diamonds(document, domains, relations, evidence):
    """Validate literal premises, every witness, and full eligible-pair coverage.

    This standalone interface proves the rule under the supplied domains.
    Their derivation is established separately by ``audit_diamond_contacts``.
    Work counters are bounded telemetry; the detector's search is not replayed.
    """
    sides, _, _ = logical_metadata(document)
    n = len(sides)
    check_domains(domains, n, 'diamond domains')
    check_matrix(relations, n, 'diamond relations')
    for i in range(n):
        require(relations[i][i] == sum(1 << (5 * (c - 1)) for c in domains[i]),
                'diamond diagonal disagrees with domain')
        for j in range(n):
            allowed = sum(1 << (4 * (a - 1) + b - 1)
                          for a in domains[i] for b in domains[j])
            require(relations[i][j] & ~allowed == 0,
                    'diamond relation exceeds endpoint domain product')
    require(isinstance(evidence, dict) and set(evidence) ==
            {'version', 'raw_document_sha256', 'domains_sha256', 'relations_sha256',
             'certificates', 'statistics'}, 'diamond evidence fields differ')
    require(evidence['version'] == VERSION, 'diamond version differs')
    for key, value in [('raw_document_sha256', document), ('domains_sha256', domains),
                       ('relations_sha256', relations)]:
        _same(evidence[key], digest(value), 'diamond ' + key)
    statistics = evidence['statistics']
    require(isinstance(statistics, dict) and set(statistics) == STATISTICS
            and all(type(value) is int and value >= 0 for value in statistics.values()),
            'diamond statistics require literal nonnegative integers')
    limit = n * (n - 1) // 2
    require(statistics['pairs_examined'] == limit
            and statistics['pairs_with_offdiagonal'] <= limit
            and statistics['palettes_examined'] <= 4 * statistics['pairs_with_offdiagonal']
            and statistics['common_edges_examined'] <= 4 * limit * limit,
            'diamond counter bounds differ')
    positions = {side: i for i, side in enumerate(sides)}
    edges = {tuple(sorted((positions[line['left']], positions[line['right']])))
             for line in document['lines'] if line['kind'] == 'separator'}
    # Enumerate physical base edges first, unlike the detector's pair-first
    # neighborhood scan. A set records existence, not a preferred witness.
    eligible = set()
    offdiagonal = {(i, j) for i, j in combinations(range(n), 2)
                   if relations[i][j] & ~0x8421}
    require(statistics['pairs_with_offdiagonal'] == len(offdiagonal),
            'diamond offdiagonal count differs')
    for a, b in edges:
        common = [v for v in range(n) if v not in (a, b)
                  and tuple(sorted((a, v))) in edges and tuple(sorted((b, v))) in edges]
        for u, v in combinations(common, 2):
            if (u, v) in offdiagonal and any(all(q not in domains[w] for w in (a, b, u, v))
                                            for q in range(1, 5)):
                eligible.add((u, v))
    certificates = evidence['certificates']
    require(isinstance(certificates, list), 'diamond certificates must be an array')
    actual = []
    for certificate in certificates:
        require(isinstance(certificate, dict) and set(certificate) ==
                {'pair', 'edge', 'excluded_color'}, 'diamond certificate fields differ')
        pair, edge, q = (certificate['pair'], certificate['edge'], certificate['excluded_color'])
        require(all(isinstance(item, list) and len(item) == 2
                    and all(isinstance(side, str) and side in positions for side in item)
                    for item in (pair, edge)), 'diamond requires known endpoint pairs')
        u, v = [positions[side] for side in pair]
        a, b = [positions[side] for side in edge]
        require(u < v and a < b and len({u, v, a, b}) == 4,
                'diamond pairs require ordered distinct identities')
        require(type(q) is int and 1 <= q <= 4, 'diamond invalid excluded color')
        require(all(q not in domains[w] for w in (a, b, u, v)),
                'diamond does not share an excluded color')
        require(all(tuple(sorted(p)) in edges for p in ((a, b), (a, u), (a, v), (b, u), (b, v))),
                'diamond witness edge is not a real separator')
        require((u, v) in offdiagonal, 'diamond pair has no offdiagonal relation')
        actual.append((u, v))
    require(actual == sorted(eligible), 'diamond eligible pair coverage or order differs')
    require(statistics['certificates_found'] == len(actual), 'diamond certificate count differs')
    return {'passed': True, 'certificates_checked': len(actual),
            'eligible_pairs_checked': len(eligible), 'absence_checked': not actual,
            'telemetry_scope': 'literal_bounds_only_not_detector_work_replay',
            'scope': 'Conditional equality under supplied domains, from five real separator edges.'}


def audit_diamond_contacts(document, outcome):
    """Check every closure round and the final projection without propagation.

    Only a complete certified EQ batch may be appended to the next round.
    Anchors, states, physical contacts and global learned NEQ remain exact.
    No equality from a different call or hypothetical trial is trusted here.
    """
    require(isinstance(outcome, dict) and outcome.get('model') == MODEL
            and 'conditional_eq' in outcome, 'wrong diamond contact producer')
    closure = outcome['conditional_eq']
    require(isinstance(closure, dict) and set(closure) == {'version', 'rounds', 'equal_names'}
            and closure['version'] == CLOSURE_VERSION, 'diamond closure fields differ')
    rounds = closure['rounds']
    require(isinstance(rounds, list) and bool(rounds), 'diamond closure requires rounds')
    n = len(document['sides'])
    require(len(rounds) <= n * (n - 1) // 2 + 1, 'diamond closure exceeds finite pair bound')
    expected, derived, audits = deepcopy(document), [], []
    for number, row in enumerate(rounds):
        require(isinstance(row, dict) and set(row) == {'document', 'outcome', 'diamond_check'},
                'diamond round fields differ')
        _same(row['document'], expected, 'diamond round input mutation differs')
        audited = audit_wheel_contacts(row['document'], row['outcome'])
        check = row['diamond_check']
        if row['outcome']['status'] == 'underdetermined':
            checked = check_conditional_diamonds(row['document'], row['outcome']['domains'],
                                                 row['outcome']['relations'], check)
            pairs = [certificate['pair'] for certificate in check['certificates']]
        else:
            require(check is None, 'terminal diamond round must skip detector')
            checked, pairs = None, []
        audits.append({'wheel_audit': audited, 'diamond_check': checked})
        if pairs:
            require(number + 1 < len(rounds), 'diamond closure omitted a certified batch')
            require(all(pair not in derived for pair in pairs), 'diamond closure repeated an EQ pair')
            expected = deepcopy(row['document'])
            expected.setdefault('equal_names', []).extend(deepcopy(pairs))
            derived.extend(deepcopy(pairs))
        else:
            require(number + 1 == len(rounds), 'diamond closure continues after terminal or empty batch')
    _same(closure['equal_names'], derived, 'diamond local equality summary differs')
    projection = deepcopy(rounds[-1]['outcome'])
    projection['model'] = MODEL
    projection['original_input'] = deepcopy(document)
    projection['conditional_eq'] = deepcopy(closure)
    _same(outcome, projection, 'diamond final projection differs')
    return {**audits[-1]['wheel_audit'],
            'trace_steps_checked': sum(row['wheel_audit']['trace_steps_checked'] for row in audits),
            'conditional_eq': {'version': CLOSURE_VERSION, 'rounds': audits,
                               'equal_names': derived, 'round_count': len(rounds),
                               'certificates_checked': len(derived)},
            'complete_assignment_preservation':
                'each_literal_round_then_physical_common_three_color_diamond_EQ_batch'}

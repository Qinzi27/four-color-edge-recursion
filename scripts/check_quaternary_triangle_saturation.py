"""Independently check three-color triangles on conditional equality classes.

Every quotient edge requires an original physical separator witness. Equality
classes and domains are premises here; the enclosing audit separately replays
their derivation. Logical NEQ, point contacts and oracle results are never
substituted for any of the six physical edges. This module imports no detector.
"""

from copy import deepcopy
from itertools import combinations
from math import comb

from scripts.audit_quaternary_geometry import _same
from scripts.audit_quaternary_logical_neq import logical_metadata
from scripts.check_quaternary_conditional_diamond import audit_diamond_contacts
from scripts.scan_low_color_obstruction_states import digest
from scripts.validate_quaternary_contacts_v2 import check_domains, expected_state, require


VERSION = 'quaternary-triangle-saturation-v1'
MODEL = 'quaternary-triangle-saturation-contact-relations-v1'
CLOSURE_VERSION = 'quaternary-triangle-saturation-closure-v1'
STATISTICS = {'classes_examined', 'palettes_examined', 'triangles_examined',
              'physical_witness_edges', 'certificates_found'}


def check_triangle_saturations(document, domains, equal_names, evidence):
    """Check class premises, each deletion and complete eligible-target coverage.

    Triangle-first enumeration is independent of the detector's target-first
    worklist. Any valid triangle and excluded color may witness a target; a
    complete single-certificate batch, ordered by representative, is required.
    Work counters are bounded telemetry, not a replay of detector operations.
    """
    sides, _, _ = logical_metadata(document)
    n, positions = len(sides), {side: i for i, side in enumerate(sides)}
    check_domains(domains, n, 'triangle saturation domains')
    require(isinstance(equal_names, list), 'triangle equality list required')
    # Connected components give the transitive EQ closure without importing
    # either the producer's union-find or its quotient-graph helper.
    links = [set() for _ in sides]
    for pair in equal_names:
        require(isinstance(pair, list) and len(pair) == 2
                and all(isinstance(side, str) and side in positions for side in pair),
                'triangle equality requires known identities')
        a, b = (positions[side] for side in pair)
        links[a].add(b)
        links[b].add(a)
    classes, owner, seen = [], {}, set()
    for first in range(n):
        if first in seen:
            continue
        pending, members = [first], set()
        while pending:
            current = pending.pop()
            if current not in members:
                members.add(current)
                pending.extend(links[current] - members)
        group = sorted(members)
        require(all(domains[v] == domains[first] for v in group),
                'triangle equality class has unequal domains')
        classes.append(group)
        seen.update(members)
        owner.update({v: first for v in group})
    representatives = [group[0] for group in classes]
    physical = {tuple(sorted((positions[line['left']], positions[line['right']])))
                for line in document['lines'] if line['kind'] == 'separator'}
    require(all(owner[a] != owner[b] for a, b in physical),
            'triangle physical edge lies within an equality class')
    quotient = {tuple(sorted((owner[a], owner[b]))) for a, b in physical}
    require(isinstance(evidence, dict) and set(evidence) ==
            {'version', 'raw_document_sha256', 'domains_sha256', 'equal_names_sha256',
             'classes', 'certificates', 'statistics'}, 'triangle evidence fields differ')
    require(evidence['version'] == VERSION, 'triangle version differs')
    for key, value in [('raw_document_sha256', document), ('domains_sha256', domains),
                       ('equal_names_sha256', equal_names)]:
        _same(evidence[key], digest(value), 'triangle ' + key)
    _same(evidence['classes'], [[sides[v] for v in group] for group in classes],
          'triangle equality classes differ')
    stats = evidence['statistics']
    require(isinstance(stats, dict) and set(stats) == STATISTICS
            and all(type(value) is int and value >= 0 for value in stats.values()),
            'triangle statistics require literal nonnegative integers')
    k = len(classes)
    require(stats['classes_examined'] == k and stats['palettes_examined'] <= 4 * k
            and stats['triangles_examined'] <= 4 * k * (comb(k - 1, 3) if k >= 4 else 0),
            'triangle work counter bounds differ')
    eligible = set()
    for triangle in combinations(representatives, 3):
        if not all(tuple(sorted(edge)) in quotient for edge in combinations(triangle, 2)):
            continue
        for q in range(1, 5):
            if any(q in domains[v] for v in triangle):
                continue
            for target in representatives:
                if target not in triangle and any(c != q for c in domains[target]) and all(
                        tuple(sorted((target, v))) in quotient for v in triangle):
                    eligible.add(target)
    certificates = evidence['certificates']
    require(isinstance(certificates, list), 'triangle certificates must be an array')
    actual, removed_count = [], 0
    for certificate in certificates:
        require(isinstance(certificate, dict) and set(certificate) ==
                {'target', 'triangle', 'excluded_color', 'removed_colors', 'edges'},
                'triangle certificate fields differ')
        target, triangle = certificate['target'], certificate['triangle']
        require(isinstance(target, str) and target in positions
                and positions[target] in representatives, 'triangle target must be a representative')
        require(isinstance(triangle, list) and len(triangle) == 3
                and all(isinstance(side, str) and side in positions for side in triangle),
                'triangle requires three known representatives')
        t, vertices = positions[target], [positions[side] for side in triangle]
        require(vertices == sorted(set(vertices)) and all(v in representatives for v in vertices)
                and t not in vertices, 'triangle needs four ordered distinct classes')
        q = certificate['excluded_color']
        require(type(q) is int and 1 <= q <= 4, 'triangle invalid excluded color')
        require(all(q not in domains[v] for v in vertices), 'triangle palette does not exclude color')
        removed = certificate['removed_colors']
        require(isinstance(removed, list) and bool(removed)
                and all(type(c) is int for c in removed)
                and removed == [c for c in domains[t] if c != q],
                'triangle deleted candidates differ')
        witnesses = certificate['edges']
        require(isinstance(witnesses, list) and len(witnesses) == 6,
                'triangle needs exactly six physical witnesses')
        a, b, c = vertices
        pairs = [(a, b), (a, c), (b, c), (t, a), (t, b), (t, c)]
        for witness, pair in zip(witnesses, pairs):
            require(isinstance(witness, list) and len(witness) == 2
                    and all(isinstance(side, str) and side in positions for side in witness),
                    'triangle witness requires known endpoints')
            u, v = [positions[side] for side in witness]
            require(tuple(sorted((u, v))) in physical, 'triangle witness is not a real separator')
            require((owner[u], owner[v]) == pair,
                    'triangle physical witness joins wrong equality classes')
        actual.append(t)
        removed_count += len(removed)
    require(actual == sorted(eligible), 'triangle eligible target coverage or order differs')
    require(stats['certificates_found'] == len(actual)
            and stats['physical_witness_edges'] == 6 * len(actual),
            'triangle certificate or witness count differs')
    return {'passed': True, 'certificates_checked': len(actual),
            'eligible_targets_checked': len(eligible), 'removed_candidates_checked': removed_count,
            'equality_classes_checked': k, 'absence_checked': not actual,
            'telemetry_scope': 'literal_bounds_only_not_detector_work_replay',
            'scope': 'Conditional domain deletion from a common-three-color triangle and six real edge witnesses.'}


def audit_saturation_contacts(document, outcome):
    """Replay every diamond round before trusting each saturation deletion batch.

    A batch updates only representative candidate state words. The next call
    recomputes its local diamond EQ; no learned local EQ is carried between
    outer rounds. Exact input/projection binding rejects hypothetical leakage.
    """
    require(isinstance(outcome, dict) and outcome.get('model') == MODEL
            and 'triangle_saturation' in outcome, 'wrong triangle saturation producer')
    closure = outcome['triangle_saturation']
    require(isinstance(closure, dict) and set(closure) == {'version', 'rounds', 'removed_candidates'}
            and closure['version'] == CLOSURE_VERSION, 'triangle closure fields differ')
    rounds = closure['rounds']
    require(isinstance(rounds, list) and bool(rounds), 'triangle closure requires rounds')
    n = len(document['sides'])
    require(len(rounds) <= 4 * n + 1, 'triangle closure exceeds finite candidate bound')
    expected, derived, audits = deepcopy(document), [], []
    for number, row in enumerate(rounds):
        require(isinstance(row, dict) and set(row) == {'document', 'outcome', 'triangle_check'},
                'triangle round fields differ')
        _same(row['document'], expected, 'triangle round input mutation differs')
        audited = audit_diamond_contacts(row['document'], row['outcome'])
        base, check = row['outcome'], row['triangle_check']
        if base['status'] == 'underdetermined':
            checked = check_triangle_saturations(row['document'], base['domains'],
                                                 base['equal_names'], check)
            certificates = check['certificates']
        else:
            require(check is None, 'terminal saturation round must skip detector')
            checked, certificates = None, []
        audits.append({'diamond_audit': audited, 'triangle_check': checked})
        if certificates:
            require(number + 1 < len(rounds), 'triangle closure omitted a certified batch')
            expected = deepcopy(row['document'])
            for certificate in certificates:
                target, removed = certificate['target'], certificate['removed_colors']
                index = document['sides'].index(target)
                remaining = [c for c in base['domains'][index] if c not in removed]
                expected.setdefault('states', {})[target] = expected_state(remaining, False)['quaternary']
                for c in removed:
                    require([target, c] not in derived, 'triangle closure repeated a deletion')
                    derived.append([target, c])
        else:
            require(number + 1 == len(rounds), 'triangle closure continues after terminal or empty batch')
    _same(closure['removed_candidates'], derived, 'triangle deletion summary differs')
    projection = deepcopy(rounds[-1]['outcome'])
    projection['model'] = MODEL
    projection['original_input'] = deepcopy(document)
    projection['triangle_saturation'] = deepcopy(closure)
    _same(outcome, projection, 'triangle final projection differs')
    return {**audits[-1]['diamond_audit'],
            'trace_steps_checked': sum(row['diamond_audit']['trace_steps_checked'] for row in audits),
            'triangle_saturation': {'version': CLOSURE_VERSION, 'rounds': audits,
                                    'removed_candidates': derived, 'round_count': len(rounds),
                                    'certificates_checked': sum((row['triangle_check'] or {}).get(
                                        'certificates_checked', 0) for row in audits)},
            'complete_assignment_preservation':
                'all_inner_diamond_rounds_then_physical_quotient_triangle_deletion_batch'}

"""Independently replay saved necessary-condition prefilter work accounting.

The existing certificate checker validates conditional mathematical premises.
This additional checker establishes deterministic certificate/witness choice
and exact work counters from physical adjacency, without calling a detector,
propagator or exact solver. Skipped triples are counted combinatorially.
"""

from itertools import combinations
from math import comb

from scripts.audit_quaternary_geometry import _same
from scripts.check_quaternary_triangle_saturation import check_triangle_saturations
from scripts.scan_low_color_obstruction_states import digest
from scripts.validate_quaternary_contacts_v2 import require


IMPLEMENTATION = 'quaternary-triangle-saturation-prefilter-v1'
WORK_KEYS = {'eligible_palette_checks', 'neighbor_membership_tests',
             'skipped_palette_checks', 'triangles_skipped', 'triangles_enumerated'}


def _quotient(document, equal_names):
    """Rebuild EQ connected components and all literal directed witnesses.

    Representative indices are the minimum side positions, not face IDs and
    not the detector's consecutive class numbers. Physical edges are retained
    as sets of possible oriented endpoints so their least witness can be
    checked independently of input line ordering.
    """
    sides = document['sides']
    positions = {side: i for i, side in enumerate(sides)}
    links = {i: set() for i in range(len(sides))}
    for a, b in equal_names:
        i, j = positions[a], positions[b]
        links[i].add(j)
        links[j].add(i)
    remaining, owner, representatives = set(links), {}, []
    while remaining:
        first = min(remaining)
        component, frontier = set(), {first}
        while frontier:
            component.update(frontier)
            frontier = set().union(*(links[v] for v in frontier)) - component
        remaining -= component
        representatives.append(first)
        owner.update({v: first for v in component})
    neighbors = {v: set() for v in representatives}
    witnesses = {}
    for line in document['lines']:
        if line['kind'] != 'separator':
            continue
        u, v = positions[line['left']], positions[line['right']]
        a, b = owner[u], owner[v]
        neighbors[a].add(b)
        neighbors[b].add(a)
        witnesses.setdefault((a, b), set()).add((u, v))
        witnesses.setdefault((b, a), set()).add((v, u))
    return representatives, neighbors, witnesses


def _triple_rank(neighbors, triangle):
    """Return the one-based rank in lexicographic combinations(neighbors, 3).

    Count earlier first and second positions, then earlier third positions.
    This derives legacy attempted work without enumerating rejected triples.
    """
    n = len(neighbors)
    i, j, k = (neighbors.index(vertex) for vertex in triangle)
    return (1 + sum(comb(n - a - 1, 2) for a in range(i))
            + sum(n - b - 1 for b in range(i + 1, j)) + k - j - 1)


def check_prefilter_work(document, domains, equal_names, evidence, telemetry):
    """Check saved certificate semantics, deterministic order and exact counts.

    The prefilter skips an eligible target/palette precisely when fewer than
    three physical-neighbor EQ classes exclude the palette's omitted color.
    Other palettes retain the original full-neighbor enumeration and early
    stopping order. Legacy triangle counters include both actual and skipped
    iterations; separate telemetry records the new actual work.
    """
    mathematical = check_triangle_saturations(document, domains, equal_names, evidence)
    require(isinstance(telemetry, dict) and set(telemetry) ==
            {'implementation', 'raw_document_sha256', 'domains_sha256',
             'equal_names_sha256', 'statistics'}, 'prefilter telemetry fields differ')
    require(telemetry['implementation'] == IMPLEMENTATION,
            'prefilter implementation differs')
    for key, value in [('raw_document_sha256', document), ('domains_sha256', domains),
                       ('equal_names_sha256', equal_names)]:
        _same(telemetry[key], digest(value), 'prefilter ' + key)
    stats = telemetry['statistics']
    require(isinstance(stats, dict) and set(stats) == WORK_KEYS
            and all(type(value) is int and value >= 0 for value in stats.values()),
            'prefilter statistics require literal nonnegative integers')

    representatives, adjacency, witnesses = _quotient(document, equal_names)
    # Triangle-first discovery independently finds every qualifying target.
    # Picking the least (color, triple) reproduces the specified order without
    # repeating the producer's target-first rejection loop.
    first = {}
    for triangle in combinations(representatives, 3):
        a, b, c = triangle
        if b not in adjacency[a] or c not in adjacency[a] or c not in adjacency[b]:
            continue
        targets = adjacency[a] & adjacency[b] & adjacency[c]
        for q in range(1, 5):
            if any(q in domains[v] for v in triangle):
                continue
            for target in targets:
                if any(color != q for color in domains[target]):
                    candidate = (q, triangle)
                    if target not in first or candidate < first[target]:
                        first[target] = candidate

    sides = document['sides']
    expected_certificates = []
    for target in sorted(first):
        q, triangle = first[target]
        a, b, c = triangle
        pairs = [(a, b), (a, c), (b, c), (target, a), (target, b), (target, c)]
        expected_certificates.append({
            'target': sides[target], 'triangle': [sides[v] for v in triangle],
            'excluded_color': q,
            'removed_colors': [color for color in domains[target] if color != q],
            'edges': [[sides[u], sides[v]] for u, v in
                      (min(witnesses[pair]) for pair in pairs)],
        })
    _same(evidence['certificates'], expected_certificates,
          'prefilter deterministic first certificate or physical witness differs')

    expected = {key: 0 for key in WORK_KEYS}
    palettes = 0
    for target in representatives:
        ordered_neighbors = sorted(adjacency[target])
        degree = len(ordered_neighbors)
        total = comb(degree, 3) if degree >= 3 else 0
        success = first.get(target)
        for q in range(1, (success[0] if success else 4) + 1):
            palettes += 1
            if not any(color != q for color in domains[target]):
                continue
            expected['eligible_palette_checks'] += 1
            expected['neighbor_membership_tests'] += degree
            excluding = sum(q not in domains[v] for v in ordered_neighbors)
            if excluding < 3:
                expected['skipped_palette_checks'] += 1
                expected['triangles_skipped'] += total
            else:
                expected['triangles_enumerated'] += (
                    _triple_rank(ordered_neighbors, success[1])
                    if success is not None and q == success[0] else total)
    _same(stats, expected, 'prefilter exact work counters differ')
    _same(evidence['statistics'], {
        'classes_examined': len(representatives), 'palettes_examined': palettes,
        'triangles_examined': expected['triangles_skipped'] + expected['triangles_enumerated'],
        'physical_witness_edges': 6 * len(first), 'certificates_found': len(first),
    }, 'prefilter exact legacy counters differ')
    return {
        'passed': True, 'implementation': IMPLEMENTATION,
        'equality_classes_checked': mathematical['equality_classes_checked'],
        'certificates_checked': mathematical['certificates_checked'],
        'palette_checks_checked': palettes, 'statistics': expected,
        'detector_reruns': 0, 'producer_reruns': 0,
        'scope': 'saved_conditional_certificates_and_exact_deterministic_prefilter_work',
    }

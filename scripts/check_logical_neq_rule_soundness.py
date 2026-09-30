"""Exhaust all edge subgraphs of one six-face logical-NEQ control family.

The fixed graph is K4(u,a,b,c), with v adjacent to a,b,c and w adjacent to
u,b,c. Its 12 physical edges yield exactly 4096 labeled subgraphs. All 4096
literal four-name assignments are examined for every subgraph, without any
vertex/color symmetry quotient. This checks the rule implementation, not
geometric construction histories or the complete low-color algorithm.
"""

from hashlib import sha256
from itertools import combinations, product
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_quaternary_logical_neq import verify_logical_inequalities
from scripts.quaternary_logical_neq import learn_logical_inequalities
from scripts.validate_structural_restart import audit_refutation

VERSION = 'quaternary-logical-neq-finite-soundness-v1'
SIDES = ('u', 'a', 'b', 'c', 'v', 'w')
BASE_EDGES = tuple(sorted((*combinations(range(4), 2), (1, 4), (2, 4), (3, 4),
                           (0, 5), (2, 5), (3, 5))))


def _require(condition, message):
    """Keep research integrity checks active under optimized Python."""
    if not condition:
        raise AssertionError(message)


def _digest(value):
    """Match the runner's portable canonical JSON hash."""
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False).encode('utf8')).hexdigest()


def _same(actual, expected, label):
    """Reject JSON boolean/integer aliasing in frozen evidence."""
    _require(json.dumps(actual, sort_keys=True, allow_nan=False) ==
             json.dumps(expected, sort_keys=True, allow_nan=False), label + ' differs')


def rule_inventory():
    """Declare every edge mask and its complete raw document before evaluation."""
    return [{'id': f'logical-neq-six-side-{mask:04x}', 'edge_mask': mask,
             'document': {'sides': list(SIDES), 'lines': [
                 {'id': f'E{bit}', 'left': SIDES[a], 'right': SIDES[b], 'kind': 'separator'}
                 for bit, (a, b) in enumerate(BASE_EDGES) if mask & (1 << bit)]}}
            for mask in range(1 << len(BASE_EDGES))]


def _evaluate(records, saved_rows=None):
    """Evaluate a supplied inventory; subset use is reserved for unit fixtures.

    Scalar raw-edge equality produces each assignment's forbidden-edge mask.
    Sharing these masks across graphs does not reduce the assignment census.
    Saved verification replays every query certificate, including saturation
    for inconclusive queries, and literal legality without running the learner.
    """
    assignments = list(product((1, 2, 3, 4), repeat=len(SIDES)))
    forbidden = [sum(1 << bit for bit, (a, b) in enumerate(BASE_EDGES) if values[a] == values[b])
                 for values in assignments]
    _require(saved_rows is None or len(saved_rows) == len(records), 'saved rule graph coverage differs')
    rows = []
    for number, record in enumerate(records):
        raw, mask = record['document'], record['edge_mask']
        edges = [edge for bit, edge in enumerate(BASE_EDGES) if mask & (1 << bit)]
        eligible = [(a, b) for a in range(6) for b in range(a + 1, 6) if (a, b) not in edges]
        if saved_rows is None:
            learning = learn_logical_inequalities(raw)
            checked = verify_logical_inequalities(raw, learning)
            positive = [query for query in learning['queries'] if query['result']['status'] == 'proved_different']
            learning_hash = _digest(learning)
            _require(checked['query_count'] == len(eligible), 'learner pair coverage differs')
        else:
            saved = saved_rows[number]
            learning = saved['learning']
            verify_logical_inequalities(raw, learning)
            positive = [query for query in learning['queries'] if query['result']['status'] == 'proved_different']
            learning_hash = _digest(learning)
        targets = []
        for query in positive:
            _require(isinstance(query, dict) and set(query) == {'pair', 'result'}, 'positive proof fields differ')
            pair = query['pair']
            _require(isinstance(pair, list) and len(pair) == 2 and all(side in SIDES for side in pair),
                     'invalid positive proof sides')
            a, b = (SIDES.index(side) for side in pair)
            _require((a, b) in eligible, 'positive proof is not a canonical raw nonedge')
            certificate = query['result']
            _same(certificate['assumed_equal'], [a, b], 'positive proof hypothesis')
            _require(certificate['status'] == 'proved_different', 'positive proof not a refutation')
            audit_refutation(6, edges, a, b, certificate)
            targets.append((a, b))
        _require(targets == sorted(set(targets)), 'positive proof order or uniqueness differs')
        legal = [list(values) for values, bad in zip(assignments, forbidden) if not bad & mask]
        for values in legal:
            _require(all(values[a] != values[b] for a, b in targets),
                     'logical inequality removed a complete legal raw coloring')
        witness = next((values for values in legal if values[4] == values[5]), None)
        unproved = [{'pair': [SIDES[a], SIDES[b]],
                     'same_color_witness': next((values for values in legal if values[a] == values[b]), None)}
                    for a, b in eligible if (a, b) not in targets]
        target_proved = (4, 5) in targets
        _require(not target_proved or witness is None, 'target proof conflicts with literal same-color witness')
        row = {'id': record['id'], 'edge_mask': mask, 'vertex_count': 6, 'edge_count': len(edges),
               'raw_document_sha256': _digest(raw), 'learning_sha256': learning_hash,
               'literal_assignments_checked': len(assignments), 'legal_assignments': len(legal),
               'legal_assignments_sha256': _digest(legal), 'eligible_pairs': len(eligible),
               'certificate_count': len(targets), 'inconclusive_count': len(eligible) - len(targets),
               'different_names': [[SIDES[a], SIDES[b]] for a, b in targets],
               'learning': learning, 'neq_projection_checks': len(legal) * len(targets),
               'inconclusive_pair_witnesses': unproved,
               'rule_coverage_gaps': sum(bool(legal) and row['same_color_witness'] is None for row in unproved),
               'target_inequality_proved': target_proved, 'same_color_target_witness': witness,
               'target_inference_gap': bool(legal) and witness is None and not target_proved}
        if saved_rows is not None:
            _same(saved_rows[number], row, 'saved literal rule evidence')
        rows.append(row)
    return rows


def _report(records, rows):
    """Keep finite coverage, nonvacuous positives and missed implications separate."""
    return {'schema_version': 1, 'version': VERSION, 'passed': True,
            'scope': {'side_order': list(SIDES), 'palette': [1, 2, 3, 4],
                'base_edges': [list(edge) for edge in BASE_EDGES], 'anchors': {},
                'graph_scope': 'All labeled edge subgraphs of the declared six-side 12-edge graph',
                'assignment_order': 'Lexicographic literal product of four names over six sides',
                'color_symmetry_reduction': False, 'vertex_symmetry_reduction': False,
                'planarity_filter': False, 'oracle_used': False, 'coloring_producer_used': False,
                'saved_check': 'Re-enumerate raw assignments and verify every saved nonedge query '
                               'certificate including inconclusive saturation, without rerunning learner',
                'boundary': 'Finite implication implementation check, not all graphs, geometry, '
                            'reachable states, algorithm completeness or originality'},
            'graph_count': len(rows),
            'graph_assignment_pairs': sum(row['literal_assignments_checked'] for row in rows),
            'total_legal_assignments': sum(row['legal_assignments'] for row in rows),
            'graphs_without_legal_assignments': sum(row['legal_assignments'] == 0 for row in rows),
            'graphs_with_certificates': sum(row['certificate_count'] > 0 for row in rows),
            'certificate_count': sum(row['certificate_count'] for row in rows),
            'neq_projection_checks': sum(row['neq_projection_checks'] for row in rows),
            'negative_control_witnesses': sum(row['same_color_target_witness'] is not None for row in rows),
            'target_inference_gaps': sum(row['target_inference_gap'] for row in rows),
            'rule_coverage_gaps': sum(row['rule_coverage_gaps'] for row in rows),
            'input_inventory_sha256': _digest(records), 'per_graph': rows,
            'per_graph_sha256': _digest(rows)}


def check_rule_soundness():
    """Run the entire predeclared finite experiment only after source freezing."""
    records = rule_inventory()
    return _report(records, _evaluate(records))


def check_saved_rule_soundness(report):
    """Recheck stored positive evidence and all 16777216 graph-assignment pairs."""
    records = rule_inventory()
    rows = _evaluate(records, report['per_graph'])
    _same(report, _report(records, rows), 'saved complete rule report')
    return {'passed': True, 'graph_count': len(rows),
            'graph_assignment_pairs': sum(row['literal_assignments_checked'] for row in rows),
            'positive_certificates_checked': sum(row['certificate_count'] for row in rows),
            'learner_runs': 0, 'oracle_searches': 0, 'coloring_producer_runs': 0}

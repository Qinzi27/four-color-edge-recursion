"""Shrink a same-state weighted-line counterexample without changing its rule.

This is a diagnostic search over DELETED INPUT STROKES, not part of the naming
algorithm. Both compared naming branches use the unchanged constraints policy,
smallest-symbol commitment, and no backtracking. The bad branch must conflict
within the selected whole-line batch; a successful branch must have a checked
complete certificate. No claim of globally minimal geometry is made.
"""

from argparse import ArgumentParser
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path
import subprocess
import sys
from time import monotonic


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.whole_lines import build_whole_lines, propagate_candidates
from fourcolor.weighted_lines import line_metadata, priority_candidates, run_weighted_lines


class GeometryWorker:
    """Use one read-only Node process to rebuild each finite candidate drawing."""

    def __init__(self):
        source = """
import {createInterface} from 'node:readline';
import {buildMap} from './web/engine.js';
for await (const line of createInterface({input:process.stdin})) {
  try {
    const map=buildMap(JSON.parse(line));
    console.log(JSON.stringify({vertices:map.vertices,edges:map.edges,
      rotation:map.rotation,faceOfDart:map.faceOfDart,outerFace:map.outerFace}));
  } catch(error) { console.log(JSON.stringify({error:error.message})); }
}
"""
        self.process = subprocess.Popen(
            ['node', '--input-type=module', '-e', source], cwd=ROOT,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding='utf-8')

    def build(self, document):
        """Return geometry only; no coloring solver is called by Node."""
        self.process.stdin.write(json.dumps(document) + '\n')
        self.process.stdin.flush()
        return json.loads(self.process.stdout.readline())

    def close(self):
        """End the task-owned helper without affecting any shared process."""
        self.process.stdin.close()
        self.process.wait(timeout=10)


def counterexample(document, worker):
    """Look along the forward trace for two highest-weight branches at one state."""
    geometry = worker.build(document)
    if 'error' in geometry:
        return None
    model = build_whole_lines(geometry)
    plane = model.plane_map
    # Avoid manufacturing the example by leaving dangling strokes after deletion.
    if any(plane.shores(i)[0] == plane.shores(i)[1]
           for i, edge in enumerate(geometry['edges']) if not edge['virtual']):
        return None
    baseline = run_weighted_lines(model, 'constraints')
    frame = next(line for line in model.lines if line['id'] == 'frame')
    first = frame['spans'][0]['dart']
    anchors, prefix = {first: [1], first ^ 1: [2]}, []
    metadata = line_metadata(model)
    for original_step in baseline['trace']:
        before = propagate_candidates(model, anchors)
        candidates = priority_candidates(metadata, before['domains'], 'constraints')
        maximum = max(row['weight'] for row in candidates)
        tied = [row['line'] for row in candidates if row['weight'] == maximum]
        if len(tied) > 1:
            branches = [run_weighted_lines(model, 'constraints',
                        forced_prefix=tuple(prefix + [line])) for line in tied]
            good = next((branch for branch in branches if branch['status'] == 'solved'), None)
            bad = next((branch for branch in branches if branch['status'] == 'conflict'
                        and len(branch['trace']) == len(prefix) + 1), None)
            if good is not None and bad is not None:
                certificate = [domain[0] for domain in good['domains']]
                assert plane.check_coloring([color - 1 for color in certificate])
                assert good['trace'][:len(prefix)] == bad['trace'][:len(prefix)]
                return {'document': document, 'geometry': geometry,
                        'whole_lines': model.lines,
                        'same_state': {'common_prefix': prefix,
                            'anchors_by_dart': anchors,
                            'domains': before['domains'], 'all_weights': candidates,
                            'highest_weight': maximum, 'tied_lines': tied},
                        'success_branch': good, 'immediate_conflict_branch': bad,
                        'certificate': certificate,
                        'checks': {'same_starting_state': True,
                            'both_lines_tied_highest': True,
                            'conflict_inside_selected_line_batch': True,
                            'complete_coloring_verified': True,
                            'no_dangling_real_edges': True}}
        for decision in original_step['decisions']:
            anchors[decision['dart']] = [decision['symbol']]
        prefix.append(original_step['line'])
    return None


def independent_completion_check(model, anchors):
    """Diagnostically search completions without calling candidate propagation.

    This independent oracle never drives a naming choice. It only checks the
    final bad-branch constraints, distinguishing a real unextendable commitment
    from a later scheduling failure. Its enumeration is explicitly NOT part of
    the proposed no-backtracking whole-line algorithm.
    """
    plane = model.plane_map
    domains = [set((1, 2, 3, 4)) for _ in plane.faces]
    for dart, values in anchors.items():
        domains[plane.face_of_dart[int(dart)]].intersection_update(values)
    adjacent = [set() for _ in domains]
    for edge in range(len(plane.edges)):
        a, b = plane.shores(edge)
        if a != b:
            adjacent[a].add(b)
            adjacent[b].add(a)
    colors, nodes = [None] * len(domains), 0

    def visit():
        """Small exact DFS using only explicit adjacency and anchor constraints."""
        nonlocal nodes
        nodes += 1
        selected, available = None, None
        for side, color in enumerate(colors):
            if color is not None:
                continue
            candidates = domains[side] - {colors[other] for other in adjacent[side]}
            if not candidates:
                return False
            if selected is None or len(candidates) < len(available):
                selected, available = side, candidates
        if selected is None:
            return True
        for symbol in sorted(available):
            colors[selected] = symbol
            if visit():
                return True
        colors[selected] = None
        return False

    exists = visit()
    return {'has_completion': exists, 'search_nodes': nodes,
            'method': 'independent exact adjacency DFS; diagnostic only, not naming algorithm'}


def main():
    """Delete input batches, recomputing both branches after every deletion."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', default='guillotine-20260916')
    parser.add_argument('--seconds', type=float, default=120)
    parser.add_argument('--max-delete-batch', type=int, default=3,
                        choices=(1, 2, 3, 4),
                        help='Diagnostic batch deletion size; unrelated to naming decisions')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output exists; choose a new path to preserve prior evidence')
    fixtures = json.loads(subprocess.check_output(
        ['node', 'scripts/whole-line-fixtures.mjs', '--emit'], cwd=ROOT,
        encoding='utf-8'))
    record = next(row for row in fixtures['records'] if row['id'] == args.fixture)
    started, checks, deletions = monotonic(), 0, []
    worker = GeometryWorker()
    try:
        document = record['document']
        proof = counterexample(document, worker)
        if proof is None:
            raise ValueError('source fixture did not reproduce the required branch witness')
        original_count = len(document['strokes'])
        while monotonic() - started < args.seconds:
            changed = False
            for batch in range(1, args.max_delete_batch + 1):
                for removed in combinations(range(len(document['strokes'])), batch):
                    if monotonic() - started >= args.seconds:
                        break
                    trial = {**document, 'strokes': [stroke for i, stroke in
                             enumerate(document['strokes']) if i not in removed]}
                    candidate = counterexample(trial, worker)
                    checks += 1
                    if candidate is not None:
                        deletions.append({'removed_current_indices': list(removed),
                            'removed_strokes': [document['strokes'][i] for i in removed],
                            'remaining_strokes': len(trial['strokes'])})
                        document, proof, changed = trial, candidate, True
                        break
                if changed:
                    break
            if not changed:
                break
    finally:
        worker.close()
    independent = independent_completion_check(build_whole_lines(proof['geometry']),
                        proof['immediate_conflict_branch']['anchors_by_dart'])
    assert independent['has_completion'] is False
    proof['independent_conflict_check'] = independent
    report = {'schema_version': 1, 'source_fixture': args.fixture,
              'policy': 'constraints', 'diagnostic': 'input-stroke batch deletion only',
              'max_delete_batch': args.max_delete_batch,
              'original_strokes': original_count, 'remaining_strokes': len(document['strokes']),
              'candidate_geometry_checks': checks, 'deletion_trace': deletions,
              'elapsed_seconds': round(monotonic() - started, 3),
              'minimality_claim': False,
              'scope': 'Counterexample to fixed-smallest-symbol/no-renaming tie safety, not to four-colorability or all renaming models.',
              'source_sha256': {name: sha256((ROOT / name).read_bytes()).hexdigest()
                  for name in ('fourcolor/whole_lines.py', 'fourcolor/weighted_lines.py',
                               'scripts/find_weighted_counterexample.py', 'web/engine.js')},
              'proof': proof}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
    print(json.dumps({'strokes': report['remaining_strokes'], 'checks': checks,
                      'seconds': report['elapsed_seconds'], 'output': str(args.output)}))


if __name__ == '__main__':
    main()

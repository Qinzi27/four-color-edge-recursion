"""Independently validate unrestricted positive-integer line-side certificates.

Python rebuilds side orbits from the rotation system. It checks proper names,
including legal five-name outputs, without solving or supplying an assignment.
This validates finite executions, not a universal four-name bound.
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fourcolor.embedding import PlaneMap  # noqa: E402

POLICIES = ('boundary', 'layer-constraint', 'constraint-layer')
DIRECTIONS = ('clockwise', 'counterclockwise')


def require(condition: bool, message: str) -> None:
    """Do not disable certificate validation under Python's -O switch."""
    if not condition:
        raise AssertionError(message)


def reconstruct(item: dict) -> PlaneMap:
    """Rebuild all turn-defined side walks instead of trusting saved faces."""
    plane = PlaneMap(tuple((str(edge['a']), str(edge['b'])) for edge in item['edges']),
                     {str(i): tuple(darts) for i, darts in enumerate(item['rotation'])})
    require(plane.faces == tuple(tuple(face) for face in item['faces']), 'side walks differ')
    require(plane.face_of_dart == tuple(item['faceOfDart']), 'dart-side identities differ')
    original = item['original']
    require(original['vertices'] - original['edges'] + len(plane.faces)
            == 1 + original['components'], 'real-geometry Euler identity failed')
    require(len(plane.vertices) - len(plane.edges) + len(plane.faces) == 2,
            'augmented Euler identity failed')
    require(len(item['vertices']) == len(plane.vertices), 'vertex count differs')
    require(type(item['outerFace']) is int and 0 <= item['outerFace'] < len(plane.faces),
            'invalid exterior index')
    for edge_id, edge in enumerate(item['edges']):
        if edge['virtual']:
            require(plane.shores(edge_id)[0] == plane.shores(edge_id)[1],
                    'virtual connection is not a bridge')
    return plane


def symbols_from_names(plane: PlaneMap, names: Sequence[Sequence[int]]) -> tuple[int, ...]:
    """Recover positive names through every shore; do not cap the palette at four."""
    require(len(names) == len(plane.edges), 'wrong number of line names')
    symbols: list[int | None] = [None] * len(plane.faces)
    for edge_id, pair in enumerate(names):
        require(len(pair) == 2, 'directed line needs two names')
        left, right = plane.shores(edge_id)
        for side, symbol in zip((left, right), pair):
            require(type(symbol) is int and symbol >= 1, 'name is not a positive integer')
            require(symbols[side] is None or symbols[side] == symbol,
                    'shore mismatch within one side orbit')
            symbols[side] = symbol
        if left == right:
            require(pair[0] == pair[1], 'bridge shores must have the same name')
        else:
            require(pair[0] != pair[1], 'real separator has equal names')
    require(all(symbol is not None for symbol in symbols), 'unnamed side orbit')
    return tuple(int(symbol) for symbol in symbols if symbol is not None)


def adjacency_from_plane(plane: PlaneMap) -> tuple[frozenset[int], ...]:
    """Treat point contact and bridges as nonadjacent side pairs."""
    neighbors: list[set[int]] = [set() for _ in plane.faces]
    for edge_id in range(len(plane.edges)):
        left, right = plane.shores(edge_id)
        if left != right:
            neighbors[left].add(right)
            neighbors[right].add(left)
    return tuple(frozenset(row) for row in neighbors)


def audit_run(geometry: dict, run: dict, plane: PlaneMap | None = None) -> dict:
    """Check the final certificate and replay the no-retry naming decisions."""
    plane = reconstruct(geometry) if plane is None else plane
    symbols = symbols_from_names(plane, run['names'])
    require(symbols == tuple(run['symbols']), 'reported side symbols differ from line names')
    outer = geometry['outerFace']
    require(symbols[outer] == 1, 'exterior is not anchored at one')
    palette = len(set(symbols))
    require(run['paletteSize'] == palette, 'palette count differs')
    require(run['withinFour'] is (palette <= 4), 'withinFour flag differs')
    require(run['backtracks'] == 0, 'unexpected backtracking')
    adjacency = adjacency_from_plane(plane)
    depth = [-1] * len(plane.faces)
    depth[outer] = 0
    queue = deque([outer])
    while queue:
        current = queue.popleft()
        for neighbor in adjacency[current]:
            if depth[neighbor] == -1:
                depth[neighbor] = depth[current] + 1
                queue.append(neighbor)
    require(all(value >= 0 for value in depth), 'disconnected side adjacency')
    assigned = {outer: 1}
    ranks = {0}
    first_fifth = None
    for index, step in enumerate(run['trace']):
        side, symbol = step['side'], step['symbol']
        require(type(side) is int and 0 <= side < len(plane.faces), 'invalid trace side')
        require(side not in assigned, 'trace names one side more than once')
        forbidden = sorted({assigned[neighbor] for neighbor in adjacency[side] if neighbor in assigned})
        require(step['forbidden'] == forbidden, 'trace forbidden names differ')
        smallest = 1
        while smallest in forbidden:
            smallest += 1
        require(type(symbol) is int and symbol == smallest, 'trace did not choose the minimum available name')
        require(symbol == symbols[side], 'trace and final side names differ')
        require(step['depth'] == depth[side], 'trace exterior depth differs')
        rank = step['rank']
        require(type(rank) is int and 0 < rank < len(plane.faces) and rank not in ranks,
                'trace rank is not a unique non-exterior rank')
        ranks.add(rank)
        assigned[side] = symbol
        if symbol > 4 and first_fifth is None:
            first_fifth = {'step': index + 1, **step}
    require(len(assigned) == len(plane.faces), 'trace omits a side')
    require(run['first_fifth'] == first_fifth, 'first fifth-name event differs')
    return {'palette': palette, 'within_four': palette <= 4, 'steps': len(run['trace'])}


def validate_report(report: dict) -> dict:
    """Audit all six fixed variants and retain every rule counterexample."""
    require(report['schema_version'] == 1, 'unsupported schema')
    require(report['policies'] == list(POLICIES), 'policy corpus differs')
    require(report['directions'] == list(DIRECTIONS), 'direction corpus differs')
    sources = {'web/priority-names.js', 'web/engine.js', 'web/cases.js',
               'scripts/construction-experiments.mjs', 'scripts/priority-experiments.mjs'}
    require(set(report['source_sha256']) == sources, 'missing or unexpected source hash')
    for source, digest in report['source_sha256'].items():
        require(hashlib.sha256((ROOT / source).read_bytes()).hexdigest() == digest,
                'source hash mismatch: ' + source)
    records = report['records']
    require(len(records) == 252, 'expected seven galleries, two teaching, three targeted and 240 generated maps')
    require(len({row['id'] for row in records}) == len(records), 'duplicate map id')
    generated = [row for row in records if row['seed'] is not None]
    require([row['seed'] for row in generated] == list(range(20260908, 20261148)),
            'generated seeds are not the complete consecutive corpus')
    expected_families = {'gallery': 7, 'teaching': 2, 'targeted': 3, 'guillotine': 160,
                         'nested-rings-and-bridges': 40, 'boundary-fan': 40}
    require({family: sum(row['family'] == family for row in records) for family in expected_families}
            == expected_families, 'family counts differ')
    run_count = step_count = more_than_four = 0
    expected_variants = [(policy, direction) for policy in POLICIES for direction in DIRECTIONS]
    checked_by_variant = {variant: [] for variant in expected_variants}
    for row in records:
        try:
            plane = reconstruct(row['geometry'])
            require([(run['policy'], run['direction']) for run in row['runs']] == expected_variants,
                    'missing, reordered, or duplicate variant')
            for run in row['runs']:
                checked = audit_run(row['geometry'], run, plane)
                run_count += 1
                step_count += checked['steps']
                more_than_four += not checked['within_four']
                checked_by_variant[(run['policy'], run['direction'])].append((row, run, checked))
        except (AssertionError, ValueError) as error:
            raise AssertionError(f"{row['id']}: {error}") from error
    require(len(report['summaries']) == len(expected_variants), 'summary variant count differs')
    for summary, variant in zip(report['summaries'], expected_variants):
        require((summary['policy'], summary['direction']) == variant, 'summary variant differs')
        checked = checked_by_variant[variant]
        failures = [(row, run) for row, run, check in checked if not check['within_four']]
        palettes: dict[str, int] = {}
        for _, _, check in checked:
            key = str(check['palette'])
            palettes[key] = palettes.get(key, 0) + 1
        require(summary['maps'] == len(checked) and summary['more_than_four'] == len(failures)
                and summary['within_four'] == len(checked) - len(failures), 'summary counts differ')
        require(summary['palette_counts'] == palettes, 'summary palette counts differ')
        require(summary['maximum_palette'] == max(check['palette'] for _, _, check in checked),
                'summary maximum palette differs')
        require(summary['counterexample_ids'] == [row['id'] for row, _ in failures],
                'counterexample list omits or changes failures')
        first = None if not failures else {'id': failures[0][0]['id'],
            'seed': failures[0][0]['seed'], **failures[0][1]['first_fifth']}
        require(summary['first_counterexample'] == first, 'first counterexample summary differs')
    return {'all_certificates_valid': True, 'reconstructed_maps': len(records),
            'independently_checked_runs': run_count, 'greedy_steps_checked': step_count,
            'runs_using_more_than_four': more_than_four,
            'scope': 'Independent rotation-orbit, shore, Euler and greedy-trace validation; no coloring solver and no universal bound.'}


def exclusive_output(report: dict, target: Path) -> None:
    """Keep dated research outputs immutable; require a new path for reruns."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write('\n')


def main() -> None:
    """Run JavaScript, validate all certificates in Python, and save evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('outputs/priority-names-2026-09-18.json'))
    args = parser.parse_args()
    target = args.output if args.output.is_absolute() else ROOT / args.output
    if target.exists():
        raise FileExistsError(f'Refusing to overwrite {target.name}; choose a new --output path')
    process = subprocess.run(['node', 'scripts/priority-experiments.mjs', '--emit'], cwd=ROOT,
                             capture_output=True, text=True, encoding='utf-8', check=True)
    report = json.loads(process.stdout)
    checked = validate_report(report)
    report['independent_validation'] = {**checked, 'python': platform.python_version()}
    exclusive_output(report, target)
    # Full traces and counterexample IDs remain in the artifact, not terminal noise.
    compact = [{key: row[key] for key in ('policy', 'direction', 'maps', 'within_four',
                'more_than_four', 'maximum_palette', 'palette_counts')}
               for row in report['summaries']]
    print(json.dumps({'validation': checked, 'summaries': compact}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

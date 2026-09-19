"""Independently audit finite, explicitly enumerative renaming diagnostics.

The browser does not call this program.  Python rebuilds side walks from the
rotation system, derives symbols from ordered line names, and enumerates whole
two-symbol components independently of the JavaScript research oracle.  Finite
successes and bounded-search failures are not a proof of universal termination.
"""
from __future__ import annotations

import argparse
from collections import deque
from datetime import date
from itertools import combinations
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fourcolor.embedding import PlaneMap, vertex_defects  # noqa: E402

Symbols = tuple[int, ...]
Adjacency = tuple[frozenset[int], ...]


def require(condition: bool, message: str) -> None:
    """Keep validation active even when Python is invoked with ``-O``."""
    if not condition:
        raise AssertionError(message)


def adjacency_from_plane(plane: PlaneMap) -> Adjacency:
    """Recover distinct-side adjacency from primal edges, ignoring bridges."""
    neighbors: list[set[int]] = [set() for _ in plane.faces]
    for edge_id in range(len(plane.edges)):
        left, right = plane.shores(edge_id)
        if left != right:
            neighbors[left].add(right)
            neighbors[right].add(left)
    return tuple(frozenset(row) for row in neighbors)


def suspend_daughter_constraint(adjacency: Adjacency, daughters: Sequence[int]) -> Adjacency:
    """Construct H by removing the NEW daughter adjacency, not an old edge."""
    require(len(daughters) == 2 and daughters[0] != daughters[1], "two distinct daughters required")
    first, second = daughters
    require(second in adjacency[first] and first in adjacency[second], "daughters must be adjacent")
    return tuple(frozenset(v for v in row if {i, v} != {first, second})
                 for i, row in enumerate(adjacency))


def proper(adjacency: Adjacency, symbols: Sequence[int], outer: int) -> bool:
    """Check explicit 0..3 symbols and the fixed exterior without a solver."""
    return (len(symbols) == len(adjacency)
            and all(type(symbol) is int and 0 <= symbol <= 3 for symbol in symbols)
            and symbols[outer] == 0
            and all(symbols[u] != symbols[v]
                    for u, row in enumerate(adjacency) for v in row))


def component_moves(adjacency: Adjacency, symbols: Symbols, outer: int):
    """Yield every complete two-symbol component excluding the anchored exterior.

    This explicitly enumerates repair choices for an independent diagnostic;
    it is not claimed to be the user's desired choice-without-search algorithm.
    """
    for pair in combinations(range(4), 2):
        unvisited = {u for u, symbol in enumerate(symbols) if symbol in pair}
        while unvisited:
            component = {min(unvisited)}
            pending = deque(component)
            unvisited.difference_update(component)
            while pending:
                current = pending.popleft()
                for neighbor in sorted(adjacency[current] & unvisited):
                    component.add(neighbor)
                    unvisited.remove(neighbor)
                    pending.append(neighbor)
            if outer in component:
                continue
            # One outer conditional ensures all nonmembers keep their names.
            changed = tuple((pair[0] ^ pair[1] ^ symbol) if u in component else symbol
                            for u, symbol in enumerate(symbols))
            yield pair, tuple(sorted(component)), changed


def audit_move(adjacency: Adjacency, before: Symbols, outer: int,
               pair: Sequence[int], component: Sequence[int], after: Sequence[int]) -> Symbols:
    """Reject partial components, changed outsiders, and exterior relabeling."""
    require(proper(adjacency, before, outer), "swap starts from an invalid state")
    require(len(pair) == 2 and pair[0] != pair[1]
            and all(type(symbol) is int and symbol in range(4) for symbol in pair), "invalid pair")
    require(len(component) == len(set(component)) and bool(component), "component has duplicate/no vertices")
    expected_component = tuple(sorted(component))
    expected_pair = tuple(sorted(pair))
    matches = [changed for actual_pair, actual_component, changed
               in component_moves(adjacency, before, outer)
               if actual_pair == expected_pair and actual_component == expected_component]
    require(len(matches) == 1, "reported vertices are not one complete eligible component")
    result = tuple(after)
    require(result == matches[0], "swap altered an outsider or did not swap the full component")
    require(proper(adjacency, result, outer), "swap failed to preserve active constraints")
    return result


def symbols_from_names(plane: PlaneMap, names: Sequence[Sequence[int]]) -> Symbols:
    """Read symbols from shores without trusting a reported color vector."""
    require(len(names) == len(plane.edges), "wrong number of ordered line names")
    symbols: list[int | None] = [None] * len(plane.faces)
    for edge_id, pair in enumerate(names):
        require(len(pair) == 2, "a directed line needs two side names")
        for face, symbol in zip(plane.shores(edge_id), pair):
            require(type(symbol) is int and symbol in range(4), "line name outside 0..3")
            require(symbols[face] is None or symbols[face] == symbol, "inconsistent names on one side orbit")
            symbols[face] = symbol
    require(all(symbol is not None for symbol in symbols), "unnamed side orbit")
    return tuple(int(symbol) for symbol in symbols if symbol is not None)


def audit_xor(plane: PlaneMap, symbols: Symbols) -> None:
    """Check final proper names through primal defects and dual integration."""
    require(plane.check_coloring(symbols), "invalid final proper coloring")
    differences = plane.differences(symbols)
    require(all(defect == 0 for defect in vertex_defects(plane, differences).values()), "nonzero primal vertex defect")
    require(plane.integrate(differences) == tuple(symbol ^ symbols[0] for symbol in symbols),
            "dual XOR integration differs from the side-name certificate")


def reconstruct(item: dict) -> tuple[PlaneMap, Adjacency, list[tuple[float, ...]]]:
    """Derive rotation orbits, rectangle geometry, adjacency and Euler afresh."""
    plane = PlaneMap(tuple((str(edge['a']), str(edge['b'])) for edge in item['edges']),
                     {str(i): tuple(darts) for i, darts in enumerate(item['rotation'])})
    require(plane.faces == tuple(tuple(face) for face in item['faces']), "face walks differ")
    require(plane.face_of_dart == tuple(item['faceOfDart']), "dart-side identities differ")
    adjacency = adjacency_from_plane(plane)
    require(adjacency == tuple(frozenset(row) for row in item['adjacency']), "adjacency differs")
    original = item['original']
    require(original['vertices'] - original['edges'] + len(plane.faces)
            == 1 + original['components'], "real-geometry Euler identity failed")
    require(original['components'] == 1, "diagnostic only covers connected rectangular maps")
    require(len(item['vertices']) == len(plane.vertices) == original['vertices'], "vertex count differs")
    require(len(plane.edges) == original['edges'], "edge count differs")
    for edge_id, edge in enumerate(item['edges']):
        require(not edge['virtual'], "this diagnostic does not cover virtual bridges")
        require(plane.shores(edge_id)[0] != plane.shores(edge_id)[1], "rectangular family has no bridges")
        first, second = (item['vertices'][edge[key]] for key in ('a', 'b'))
        require(first[0] == second[0] or first[1] == second[1], "non-axis-aligned edge")
    boxes = []
    outer_candidates = []
    for face_id, darts in enumerate(plane.faces):
        points = [item['vertices'][int(plane.edges[dart // 2][dart % 2])] for dart in darts]
        xs, ys = zip(*points)
        box = (min(xs), max(xs), min(ys), max(ys))
        area = -sum(first[0] * second[1] - second[0] * first[1]
                    for first, second in zip(points, points[1:] + points[:1])) / 2
        if area < 0:
            outer_candidates.append(face_id)
        if face_id != item['outerFace']:
            require(abs(area - (box[1] - box[0]) * (box[3] - box[2])) < 1e-5,
                    "bounded side is not a positive rectangular orbit")
            require(all(x in box[:2] or y in box[2:] for x, y in points), "nonrectangular boundary")
        boxes.append(box)
    require(outer_candidates == [item['outerFace']], "exterior identification differs")
    return plane, adjacency, boxes


def frozen_extension(adjacency: Adjacency, inherited: Symbols,
                     daughters: Sequence[int]) -> Symbols | None:
    """Independently apply the published frozen two-contact tie-breaking rule."""
    require(inherited[daughters[0]] == inherited[daughters[1]], "daughters must initially inherit one name")
    options = []
    for child in daughters:
        external = {inherited[neighbor] for neighbor in adjacency[child] if neighbor not in daughters}
        available = sorted(set(range(4)) - external - {inherited[child]})
        if len(external) <= 2 and available:
            options.append((len(external), child, available[0]))
    if not options:
        return None
    _, child, symbol = min(options)
    result = list(inherited)
    result[child] = symbol
    return tuple(result)


def first_post_swap(adjacency: Adjacency, inherited: Symbols, outer: int,
                    daughters: Sequence[int]) -> Symbols | None:
    """Test existence of one split-stage component that separates daughters."""
    for _pair, component, changed in component_moves(adjacency, inherited, outer):
        if sum(child in component for child in daughters) == 1:
            return changed
    return None


def audit_witness(row: dict, witness: dict, old_adj: Adjacency,
                  new_adj: Adjacency, relaxed: Adjacency, plane: PlaneMap) -> None:
    """Replay B/C/BC/BFS operations and derive final colors only from names."""
    old_symbols = tuple(row['old_colors'])
    current: Symbols | None = None
    old_outer, new_outer = row['old_map']['outerFace'], row['new_map']['outerFace']
    for move in witness['moves']:
        if move['stage'] == 'old':
            require(current is None, "cannot return to the pre-split stage")
            require(tuple(move['before']) == old_symbols, "old-stage input differs")
            old_symbols = audit_move(old_adj, old_symbols, old_outer,
                                     move['pair'], move['component'], move['after'])
        elif move['stage'] == 'split':
            if current is None:
                current = tuple(old_symbols[parent] for parent in row['parents'])
            require(tuple(move['before']) == current, "split-stage input differs")
            current = audit_move(relaxed, current, new_outer,
                                 move['pair'], move['component'], move['after'])
        else:
            raise AssertionError("unknown operation stage")
    if current is None:
        inherited = tuple(old_symbols[parent] for parent in row['parents'])
        current = frozen_extension(new_adj, inherited, row['daughters'])
        require(current is not None, "B witness does not permit the frozen split")
    from_names = symbols_from_names(plane, witness['names'])
    require(from_names == current == tuple(witness['colors']), "final line names disagree with replay")
    require(proper(new_adj, from_names, new_outer), "final witness violates a restored constraint")
    audit_xor(plane, from_names)


def audit_record(row: dict) -> dict:
    """Recompute geometric lineage and all bounded repair-existence categories."""
    old_plane, old_adj, old_boxes = reconstruct(row['old_map'])
    new_plane, new_adj, new_boxes = reconstruct(row['new_map'])
    old_outer, new_outer = row['old_map']['outerFace'], row['new_map']['outerFace']
    old_symbols = symbols_from_names(old_plane, row['old_names'])
    require(old_symbols == tuple(row['old_colors']), "old line names disagree with colors")
    require(proper(old_adj, old_symbols, old_outer), "old names are invalid")
    audit_xor(old_plane, old_symbols)
    parents = []
    for face, box in enumerate(new_boxes):
        if face == new_outer:
            parents.append(old_outer)
            continue
        x, y = (box[0] + box[1]) / 2, (box[2] + box[3]) / 2
        hits = [parent for parent, old_box in enumerate(old_boxes)
                if parent != old_outer and old_box[0] < x < old_box[1]
                and old_box[2] < y < old_box[3]]
        require(len(hits) == 1, "new rectangle does not have a unique old parent")
        parents.append(hits[0])
    require(parents == row['parents'], "geometric parents differ")
    multiplicities = [parents.count(parent) for parent in range(len(old_plane.faces))]
    require(multiplicities.count(2) == 1 and all(count in (1, 2) for count in multiplicities),
            "not one elementary split")
    parent = multiplicities.index(2)
    daughters = [face for face, old in enumerate(parents) if old == parent]
    require(parent == row['parent'] and daughters == row['daughters'], "daughter identities differ")
    quotient = {tuple(sorted((parents[u], parents[v])))
                for u, neighbors in enumerate(new_adj) for v in neighbors if parents[u] != parents[v]}
    old_edges = {tuple(sorted((u, v))) for u, neighbors in enumerate(old_adj) for v in neighbors}
    require(quotient == old_edges, "split changed an unrelated old adjacency")
    relaxed = suspend_daughter_constraint(new_adj, daughters)
    require(relaxed == tuple(frozenset(neighbors) for neighbors in row['relaxed']), "H is not the daughter-deleted graph")
    inherited = tuple(old_symbols[parent] for parent in parents)
    require(inherited == tuple(row['inherited']) and proper(relaxed, inherited, new_outer), "invalid inherited H state")
    require(frozen_extension(new_adj, inherited, daughters) is None, "source state was not blocked")
    before_states = [changed for _pair, _component, changed
                     in component_moves(old_adj, old_symbols, old_outer)]
    exists_b = any(frozen_extension(new_adj, tuple(state[p] for p in parents), daughters) is not None
                   for state in before_states)
    exists_c = first_post_swap(relaxed, inherited, new_outer, daughters) is not None
    exists_bc = not (exists_b or exists_c) and any(
        first_post_swap(relaxed, tuple(state[p] for p in parents), new_outer, daughters) is not None
        for state in before_states)
    expected_stages = {'B': ['old'], 'C': ['split'], 'BC': ['old', 'split']}
    for method, exists in [('B', exists_b), ('C', exists_c), ('BC', exists_bc)]:
        witness = row[method]
        require((witness is not None) == exists, f"{method} repair-existence mismatch")
        if witness is not None:
            require(witness['method'] == method, "witness method differs")
            require([move['stage'] for move in witness['moves']] == expected_stages[method], "wrong witness stages")
            audit_witness(row, witness, old_adj, new_adj, relaxed, new_plane)
    return {'seed': row['seed'], 'B': exists_b, 'C': exists_c, 'BC': exists_bc,
            'old_adj': old_adj, 'new_adj': new_adj, 'relaxed': relaxed, 'new_plane': new_plane}


def all_assignments(adjacency: Adjacency, outer: int):
    """Independent bounded assignment oracle, NEVER used in production marking."""
    require(len(adjacency) <= 10, "assignment oracle is limited to ten side spaces")
    colors = [-1] * len(adjacency)

    def visit(index: int):
        """Assign fixed numerical side order with only already-assigned tests."""
        if index == len(colors):
            yield tuple(colors)
            return
        for symbol in (range(1) if index == outer else range(4)):
            if all(colors[neighbor] != symbol for neighbor in adjacency[index] if neighbor < index):
                colors[index] = symbol
                yield from visit(index + 1)
        colors[index] = -1

    yield from visit(0)


def audit_dependency_certificate(row: dict, checked: dict, certificate: dict,
                                 minimum_colors: Symbols) -> list[int]:
    """Check supplied targets and their full blocking DAG; do not discover them."""
    inherited = tuple(row['inherited'])
    outer, relaxed, new_adj = row['new_map']['outerFace'], checked['relaxed'], checked['new_adj']
    targets = {}
    for change in certificate['changes']:
        side, symbol = change['side'], change['symbol']
        require(type(side) is int and 0 <= side < len(inherited) and side != outer,
                "invalid or anchored change target")
        require(type(symbol) is int and 0 <= symbol <= 3 and symbol != inherited[side],
                "invalid or unchanged target symbol")
        require(side not in targets, "duplicate change target")
        targets[side] = symbol
    final = tuple(targets.get(side, symbol) for side, symbol in enumerate(inherited))
    require(proper(new_adj, final, outer), "supplied dependency target is not a valid final assignment")
    dependencies = {side: {neighbor for neighbor in relaxed[side] if inherited[neighbor] == symbol}
                    for side, symbol in targets.items()}
    reported_dependencies = {}
    for item in certificate['dependencies']:
        require(item['side'] not in reported_dependencies, "duplicate dependency row")
        require(len(item['blockers']) == len(set(item['blockers'])), "duplicate blocking side")
        reported_dependencies[item['side']] = set(item['blockers'])
    require(reported_dependencies == dependencies, "blocking dependencies are incomplete or incorrect")
    require(all(blockers <= targets.keys() for blockers in dependencies.values()), "unchanged side blocks a target")
    current, completed, order = inherited, set(), []
    for step in certificate['steps']:
        side = step['side']
        require(side in targets and side not in completed, "unknown or repeated dependency step")
        require(dependencies[side] <= completed, "dependency step precedes one of its blockers")
        require(tuple(step['before']) == current and step['from'] == current[side], "dependency step input differs")
        require(step['to'] == targets[side], "dependency step uses the wrong target")
        changed = tuple(targets[side] if face == side else symbol for face, symbol in enumerate(current))
        require(tuple(step['after']) == changed, "dependency step changed another side")
        require(proper(relaxed, changed, outer), "dependency step violates H constraints")
        current = changed
        completed.add(side)
        order.append(side)
    require(completed == targets.keys() and current == final, "dependency execution did not finish")
    from_names = symbols_from_names(checked['new_plane'], certificate['names'])
    require(from_names == tuple(certificate['colors']) == final == minimum_colors,
            "dependency witness differs from its targets or the minimum-change witness")
    audit_xor(checked['new_plane'], from_names)
    return order


def audit_hard_case(row: dict, checked: dict, reported: dict) -> dict:
    """Exhaust the small H component and independently certify shortest depth."""
    outer = row['new_map']['outerFace']
    old_adj, new_adj, relaxed = (checked[key] for key in ('old_adj', 'new_adj', 'relaxed'))
    start = tuple(row['inherited'])
    layers: list[list[Symbols]] = [[start]]
    seen = {start}
    # These limits belong to the independent checker, not the search result.
    while True:
        next_layer = []
        for state in layers[-1]:
            for _pair, _component, changed in component_moves(relaxed, state, outer):
                if changed not in seen:
                    seen.add(changed)
                    next_layer.append(changed)
                    require(len(seen) <= 50000, "independent state budget exceeded; no conclusion")
        if not next_layer:
            break
        layers.append(next_layer)
        require(len(layers) <= 20, "independent depth budget exceeded; no conclusion")
    goals_by_depth = [[state for state in layer if proper(new_adj, state, outer)] for layer in layers]
    goal_depths = [depth for depth, states in enumerate(goals_by_depth) if states]
    require(bool(goal_depths), "no repair in independently exhausted H component")
    minimum_depth = min(goal_depths)
    bfs = reported['bfs']
    require(bfs['status'] == 'found' and bfs['depth'] == minimum_depth, "shortest repair depth differs")
    require(bfs['layer_counts'] == [len(layer) for layer in layers[:minimum_depth + 1]], "BFS layer counts differ")
    require(bfs['visited'] == sum(bfs['layer_counts']), "BFS visited count differs")
    require(bfs['goal_count'] == len(goals_by_depth[minimum_depth]), "minimum-layer goal count differs")
    require(minimum_depth <= bfs['max_depth'] and bfs['visited'] <= bfs['max_states'], "reported search exceeds its bounds")
    require(bfs['witness']['method'] == 'split-BFS'
            and len(bfs['witness']['moves']) == minimum_depth
            and all(move['stage'] == 'split' for move in bfs['witness']['moves']), "wrong BFS witness scope")
    audit_witness(row, bfs['witness'], old_adj, new_adj, relaxed, checked['new_plane'])
    assignments = list(all_assignments(new_adj, outer))
    require(bool(assignments), "assignment oracle found no proper final state")
    costs = {state: sum(symbol != row['old_colors'][row['parents'][face]]
                       for face, symbol in enumerate(state) if row['parents'][face] != row['parent'])
             for state in assignments}
    minimum_cost = min(costs.values())
    minimizers = [state for state, cost in costs.items() if cost == minimum_cost]
    minimum = reported['minimum']
    require(minimum['proper_assignments'] == len(assignments), "proper-assignment count differs")
    require(minimum['minimum_changed_unsplit'] == minimum_cost, "minimum old-side change count differs")
    require(minimum['minimizers'] == len(minimizers), "minimizer count differs")
    minimum_names = symbols_from_names(checked['new_plane'], minimum['names'])
    require(minimum_names == tuple(minimum['colors']) and minimum_names in minimizers, "invalid minimum-change witness")
    audit_xor(checked['new_plane'], minimum_names)
    dependency_order = audit_dependency_certificate(row, checked, reported['dependency'], minimum_names)
    h_assignments = set(all_assignments(relaxed, outer))
    require(seen <= h_assignments, "BFS reached an invalid H assignment")
    return {'seed': row['seed'], 'minimum_split_stage_swaps': minimum_depth,
            'goal_layer_count': len(goals_by_depth[minimum_depth]),
            'exhausted_component_layer_counts': [len(layer) for layer in layers],
            'reachable_H_assignments': len(seen), 'all_proper_H_assignments': len(h_assignments),
            'reachable_component_equals_all_H_assignments': seen == h_assignments,
            'proper_final_assignments': len(assignments), 'minimum_changed_unsplit': minimum_cost,
            'minimum_change_witnesses': len(minimizers), 'dependency_execution_order': dependency_order}


def validate_report(report: dict) -> dict:
    """Reject incorrect presence/absence claims as well as invalid witnesses."""
    require(report['schema_version'] == 1, "unsupported report schema")
    expected_source = 'outputs/construction-validation-2026-09-08.json'
    require(report['source_report'] == expected_source, "unexpected source report")
    source_bytes = (ROOT / expected_source).read_bytes()
    require(report['source_hash_normalization'] == 'UTF-8 text, CRLF normalized to LF',
            "unexpected source text normalization")
    # Git may check out LF as CRLF on Windows: certify identical source text,
    # without allowing other whitespace or source-data changes to go unnoticed.
    canonical_source = source_bytes.replace(b'\r\n', b'\n')
    require(report['source_sha256'] == hashlib.sha256(canonical_source).hexdigest(), "source provenance hash differs")
    source_rows = {row['seed']: row for row in json.loads(source_bytes)['records'] if row['family'] == 'guillotine'}
    records = report['records']
    require([row['seed'] for row in records] == list(range(20260908, 20261068)), "unexpected seeds/order")
    checked = []
    for row in records:
        try:
            source = source_rows[row['seed']]
            require(source['outcome'] == 'blocked' and source['replay']['operations'] == row['operations']
                    and source['rejected']['points'] == row['pending']
                    and source['final_names'] == row['old_names'], "source first-blocked record differs")
            checked.append(audit_record(row))
        except (AssertionError, ValueError, TypeError, KeyError, IndexError) as error:
            raise AssertionError(f"seed {row['seed']}: {error}") from error
    counts = {'total': len(checked), 'B': sum(row['B'] for row in checked),
              'C': sum(row['C'] for row in checked),
              'intersection': sum(row['B'] and row['C'] for row in checked),
              'union': sum(row['B'] or row['C'] for row in checked),
              'BC_extra': sum(row['BC'] for row in checked),
              'remaining': sum(not (row['B'] or row['C'] or row['BC']) for row in checked)}
    require(counts == report['counts'], "summary counts differ from independently recomputed diagnostics")
    hard_seed = report['hard_case']['seed']
    matches = [index for index, row in enumerate(records) if row['seed'] == hard_seed]
    require(len(matches) == 1, "hard-case seed is not unique")
    index = matches[0]
    hard = audit_hard_case(records[index], checked[index], report['hard_case'])
    return {'schema_version': 1, 'all_passed': True, 'python': platform.python_version(),
            'scope': 'Independent finite first-blocked-state validation; not completed histories or a non-search rule.',
            'source_sha256': report['source_sha256'],
            'source_hash_normalization': report['source_hash_normalization'], 'counts': counts,
            'reconstructed_maps': 2 * len(records),
            'witnesses_checked': sum(row[key] is not None for row in records for key in ('B', 'C', 'BC')) + 3,
            'hard_case': hard}


def exclusive_output(summary: dict, requested: Path | None) -> Path:
    """Preserve older reports; a default rerun receives a fresh numbered path."""
    base = requested or Path('outputs') / f'renaming-validation-{date.today().isoformat()}.json'
    if not base.is_absolute():
        base = ROOT / base
    base.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1000):
        candidate = base if attempt == 0 else base.with_name(f'{base.stem}-{attempt:03d}{base.suffix}')
        try:
            with candidate.open('x', encoding='utf-8') as handle:
                json.dump(summary, handle, ensure_ascii=False, indent=2)
                handle.write('\n')
            return candidate
        except FileExistsError:
            if requested is not None:
                raise
    raise FileExistsError("could not reserve a fresh report name")


def main() -> None:
    """Read a saved report or capture Node's JSON without modifying its output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, help='Existing rename-diagnostics JSON; otherwise invoke node --emit')
    parser.add_argument('--output', type=Path, help='New independent summary path; existing files are never replaced')
    args = parser.parse_args()
    if args.input:
        source = args.input if args.input.is_absolute() else ROOT / args.input
        # Preserve original newline bytes so the provenance digest describes
        # the actual input file rather than a platform-normalized text copy.
        raw = source.read_bytes().decode('utf-8')
    else:
        result = subprocess.run(['node', 'scripts/rename-diagnostics.mjs', '--emit'], cwd=ROOT,
                                check=True, capture_output=True, text=True, encoding='utf-8')
        raw = result.stdout
    summary = validate_report(json.loads(raw))
    summary['input_report_sha256'] = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    output = exclusive_output(summary, args.output)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    # The saved JSON stays portable; a local path is only printed for the user.
    print(f'Independent report: {output}')


if __name__ == '__main__':
    main()

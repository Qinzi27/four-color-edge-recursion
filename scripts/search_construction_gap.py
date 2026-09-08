"""Bounded abstract-dual research oracle, NOT the production marker algorithm.

Enumerates colorings and backtracks over safe contractions. This is deliberately
separate from web/construction.js, which never imports or invokes this script.
A simple-dual witness does not certify a geometrically allowed anchored path.
"""
from __future__ import annotations
import argparse
from functools import lru_cache
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fourcolor.coloring import colorings, canonical_colors  # noqa: E402


@lru_cache(None)
def reverse_chain(n, edges, colors, minimum=False, fixed_outer=False):
    """Return contractions in changing vertex indices, or None if exhausted."""
    if n == (2 if fixed_outer else 1):
        return () if not fixed_outer or colors == (0, 1) else None
    adjacency = [set() for _ in range(n)]
    for u, v in edges:
        adjacency[u].add(v)
        adjacency[v].add(u)
    for u in range(1 if fixed_outer else 0, n):
        for v in sorted(adjacency[u]):
            if fixed_outer and v == 0:
                continue
            # Merge v into u; all other labels are frozen.
            if any(w != u and colors[w] == colors[u] for w in adjacency[v]):
                continue
            available = set(range(4)) - {colors[w] for w in adjacency[v]}
            if minimum and colors[v] != min(available):
                continue
            kept = [w for w in range(n) if w != v]
            index = {w: i for i, w in enumerate(kept)}
            new_edges = set()
            for x, y in edges:
                x = u if x == v else x
                y = u if y == v else y
                if x != y:
                    new_edges.add(tuple(sorted((index[x], index[y]))))
            tail = reverse_chain(n-1, tuple(sorted(new_edges)), tuple(colors[w] for w in kept), minimum, fixed_outer)
            if tail is not None:
                return ((u, v),) + tail
    return None


def generated_graphs(rng, n):
    """20 proposals per size, 80 edge-flip proposals, labeled-edge-set dedup."""
    seen = set()
    for _sample in range(20):
        faces = [(0, 1, 2), (0, 3, 1), (1, 3, 2), (2, 3, 0)]
        # Triangle insertion preserves the sphere triangulation.
        for v in range(4, n):
            x, y, z = faces.pop(rng.randrange(len(faces)))
            faces.extend([(x, y, v), (y, z, v), (z, x, v)])
        for _step in range(80):
            edge_faces = {}
            for i, face in enumerate(faces):
                for j in range(3):
                    edge = tuple(sorted((face[j], face[(j+1) % 3])))
                    edge_faces.setdefault(edge, []).append(i)
            # Dictionary insertion order and rejected proposals matter to seed replay.
            edge = rng.choice(list(edge_faces))
            ids = edge_faces[edge]
            if len(ids) != 2:
                continue
            p = next(v for v in faces[ids[0]] if v not in edge)
            q = next(v for v in faces[ids[1]] if v not in edge)
            if p == q or tuple(sorted((p, q))) in edge_faces:
                continue
            faces[ids[0]] = (p, q, edge[0])
            faces[ids[1]] = (q, p, edge[1])
        edges = tuple(sorted({tuple(sorted((face[j], face[(j+1) % 3]))) for face in faces for j in range(3)}))
        assert len(edges) == 3*n-6
        if edges not in seen:
            seen.add(edges)
            yield edges


def verify_chain(n, edges, colors, chain):
    """Independent witness replay with explicit vertex blocks, no search calls."""
    blocks = [{i} for i in range(n)]
    current = {i: colors[i] for i in range(n)}
    edges = set(edges)
    for u, v in chain:
        assert u != 0 and v != 0 and tuple(sorted((u, v))) in edges
        neighbors = {b if a == v else a for a, b in edges if v in (a, b)}
        assert colors[v] == min(set(range(4)) - {colors[w] for w in neighbors})
        recolored = list(colors)
        recolored[v] = recolored[u]
        assert all(a in (u, v) and b in (u, v) or recolored[a] != recolored[b] for a, b in edges)
        # Preserve old block membership to make returned changing indices auditable.
        blocks[u] |= blocks[v]
        blocks.pop(v)
        kept = [i for i in range(n) if i != v]
        index = {old: new for new, old in enumerate(kept)}
        mapped = {(u if a == v else a, u if b == v else b) for a, b in edges}
        edges = {tuple(sorted((index[a], index[b]))) for a, b in mapped if a != b}
        colors = tuple(colors[i] for i in kept)
        n -= 1
        for i, block in enumerate(blocks):
            for old in block:
                current[old] = colors[i]
    assert n == 2 and colors == (0, 1) and edges == {(0, 1)}
    assert blocks[0] == {0}


def run_search():
    """The sampled graph collection is fixed; all failed states are counted."""
    rng = random.Random(20260908)
    rows, records = [], []
    for n in range(4, 13):
        row = dict(n=n, graphs=0, canonical_colorings=0, colorings_without_relaxed_chain=0,
                   graphs_without_relaxed_chain=0, graphs_without_fixed_outer_minimum_chain=0)
        for edges in generated_graphs(rng, n):
            row['graphs'] += 1
            states = sorted({canonical_colors(c) for c in colorings(n, edges)})
            row['canonical_colorings'] += len(states)
            relaxed_ok = strict_ok = False
            witness = None
            for colors in states:
                relaxed = reverse_chain(n, edges, colors)
                strict = reverse_chain(n, edges, colors, True, True)
                row['colorings_without_relaxed_chain'] += relaxed is None
                relaxed_ok |= relaxed is not None
                strict_ok |= strict is not None
                if strict is not None:
                    verify_chain(n, edges, colors, strict)
                    if witness is None:
                        witness = {'colors': colors, 'contractions': strict}
            row['graphs_without_relaxed_chain'] += not relaxed_ok
            row['graphs_without_fixed_outer_minimum_chain'] += not strict_ok
            records.append({'n': n, 'edges': edges, 'canonical_colorings': len(states), 'witness': witness})
        rows.append(row)
    totals = {key: sum(row[key] for row in rows) for key in rows[0] if key != 'n'}
    assert totals == {'graphs': 147, 'canonical_colorings': 478, 'colorings_without_relaxed_chain': 1,
                      'graphs_without_relaxed_chain': 0, 'graphs_without_fixed_outer_minimum_chain': 0}
    return {'seed': 20260908, 'vertex_range': [4, 12], 'proposals_per_size': 20, 'flip_proposals': 80,
            'deduplication': 'labeled edge sets within each size; not graph isomorphism',
            'color_normalization': 'first-occurrence global renaming; minimum tests only on these concrete labels',
            'scope': 'Abstract-dual research oracle only. Shared-boundary path geometry and production child tie-breaking NOT certified. NOT a new proof.',
            'rows': rows, 'totals': totals, 'records': records}


def main():
    """Write a portable research report, separately from production certificates."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('outputs/reverse-merge-search-2026-09-08.json'))
    args = parser.parse_args()
    report = run_search()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report['totals'], indent=2))


if __name__ == '__main__':
    main()

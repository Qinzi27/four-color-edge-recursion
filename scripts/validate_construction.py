"""Independently reconstruct every committed JS line-name certificate in Python.

The Python core receives edges and rotations, derives its own side walks, reads
symbols FROM ordered line names, and checks adjacency, Euler and XOR integration.
No Python coloring oracle supplies colors to the production JavaScript algorithm.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fourcolor.embedding import PlaneMap, vertex_defects  # noqa: E402


def validate_snapshot(item: dict) -> None:
    """Read symbols from shores without trusting JavaScript's region coloring."""
    plane = PlaneMap(
        tuple((str(e['a']), str(e['b'])) for e in item['edges']),
        {str(i): tuple(darts) for i, darts in enumerate(item['rotation'])},
    )
    assert plane.face_of_dart == tuple(item['faceOfDart'])
    assert plane.faces == tuple(tuple(f) for f in item['faces'])
    colors = [None] * len(plane.faces)
    for i, name in enumerate(item['names']):
        for side, face in enumerate(plane.shores(i)):
            symbol = name[side]
            assert symbol in range(4)
            assert colors[face] is None or colors[face] == symbol
            colors[face] = symbol
        if item['edges'][i]['virtual']:
            assert plane.shores(i)[0] == plane.shores(i)[1]
    assert plane.check_coloring(colors)
    differences = plane.differences(colors)
    assert all(d == 0 for d in vertex_defects(plane, differences).values())
    assert plane.integrate(differences) == tuple(c ^ colors[0] for c in colors)
    original = item['original']
    assert original['vertices'] - original['edges'] + len(plane.faces) == 1 + original['components']


def main() -> None:
    """Save a portable report; optional output keeps older reports intact."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('outputs/construction-validation-2026-09-08.json'))
    args = parser.parse_args()
    result = subprocess.run(['node', 'scripts/construction-experiments.mjs', '--emit'], cwd=ROOT, capture_output=True, text=True, encoding='utf-8', check=True)
    report = json.loads(result.stdout)
    snapshots = report.pop('snapshots')
    for item in snapshots:
        try:
            validate_snapshot(item)
        except AssertionError as error:
            raise AssertionError(f"{item['id']} step {item['step']}") from error
    report.update(python=platform.python_version(), independent_line_name_certificates=len(snapshots), all_passed=True)
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'all_passed': True, 'certificates': len(snapshots), 'families': report['families']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

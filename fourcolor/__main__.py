"""Run reproducible examples with ``python -m fourcolor demo``."""

from __future__ import annotations

import argparse
import json
from math import isinf

from .coloring import boundary_signature, colorings
from .embedding import vertex_defects
from .examples import dangling_triangle_map, tetrahedron_map, triangle_map
from .history import replay, tetrahedron_history
from .repair import Edge, Parallel, Series, minimum_repair, repair_table


def demo() -> dict:
    """Compute small examples, including an intentional inconsistent proposal."""
    tetrahedron = tetrahedron_map()
    colors = (0, 1, 2, 3)
    deltas = tetrahedron.differences(colors)
    recovered = tetrahedron.integrate(deltas)
    assert recovered == colors
    defects = vertex_defects(tetrahedron, deltas)
    assert not any(defects.values())
    face_edges = tuple(tetrahedron.shores(i) for i in range(len(tetrahedron.edges)))

    dangling = dangling_triangle_map()
    dangling_deltas = dangling.differences((0, 1))
    assert dangling_deltas[3] == 0
    assert dangling.integrate(dangling_deltas) == (0, 1)
    try:
        triangle_map().integrate((1, 1, 2))
    except ValueError as error:
        conflict = str(error)
    else:
        raise AssertionError("inconsistent dual paths were not rejected")

    repair_cases = {}
    for name, expr in {
        "two_parallel_different_labels": Parallel(Edge(1), Edge(2)),
        "three_parallel_balanced_labels": Parallel(Edge(1), Parallel(Edge(2), Edge(3))),
        "path_with_bridges": Series(Edge(1), Edge(2)),
    }.items():
        cost, witness = minimum_repair(expr)
        repair_cases[name] = {
            "terminal_defect_costs": ["infinity" if isinf(value) else int(value)
                                      for value in repair_table(expr)],
            "balanced_root_cost": "infinity" if isinf(cost) else cost,
            "witness_labels": witness,
        }

    initial, operations = tetrahedron_history()
    constructed, construction_logs = replay(initial, operations)
    constructed_face_edges = tuple(constructed.shores(i) for i in range(len(constructed.edges)))
    constructed_colors = next(colorings(len(constructed.faces), constructed_face_edges))
    assert constructed.check_coloring(constructed_colors)
    assert len(set(constructed_colors)) == 4
    return {
        "status": "verified examples; not a new proof of the Four Color Theorem",
        "tetrahedron": {
            "vertices": len(tetrahedron.vertices), "edges": len(tetrahedron.edges),
            "faces": len(tetrahedron.faces), "face_boundaries": tetrahedron.faces,
            "colors": colors, "differences": deltas,
            "recovered_colors": recovered, "vertex_defects": defects,
            "labeled_colorings": sum(1 for _ in colorings(4, face_edges)),
            "boundary_signature_size": len(boundary_signature(4, face_edges, (0, 1, 2))),
        },
        "dangling_edge": {"face_count": len(dangling.faces),
                          "shores": dangling.shores(3), "differences": dangling_deltas},
        "inconsistent_triangle_difference_proposal": {"differences": (1, 1, 2),
                                                       "rejection": conflict},
        "series_parallel_flow_repair": repair_cases,
        "recursive_construction": {
            "face_counts": [len(initial.faces)] + [entry["after"]["faces"] for entry in construction_logs],
            "operations": operations, "history": construction_logs,
            "final_face_colors": constructed_colors,
            "final_color_count": len(set(constructed_colors)),
        },
    }


def main() -> None:
    """Dispatch a deliberately small CLI without external dependencies."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("demo",))
    parser.parse_args()
    print(json.dumps(demo(), indent=2, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()

"""Run bounded independent validation and save a machine-readable report.

Run from any working directory with ``python scripts/validate.py``. Only Python
standard-library modules are required; no absolute machine paths are recorded.
These finite checks support implementation correctness, not a universal theorem.
"""

from argparse import ArgumentParser
from datetime import datetime, timezone
from itertools import product
import io
import json
from pathlib import Path
import platform
import random
import sys
import unittest


# Resolve imports relative to this script, never the caller's current directory.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from fourcolor.embedding import vertex_defects
from fourcolor.coloring import boundary_signature
from fourcolor.examples import tetrahedron_map
from fourcolor.history import replay, tetrahedron_history
from fourcolor.repair import Edge, Parallel, Series, minimum_repair, realize, repair_table
from tests.oracles import brute_colorings, brute_repair_table, random_expression, xor_defects
from tests.test_embedding import face_assignment_is_proper
from tests.test_history import apply_operation


SEED = 20260906


def enumerate_tetrahedron():
    """Record every four-face coloring and every nonzero six-edge assignment."""
    plane_map = tetrahedron_map()
    proper = []
    for colors in product(range(4), repeat=len(plane_map.faces)):
        expected = face_assignment_is_proper(plane_map, colors)
        if plane_map.check_coloring(colors) != expected:
            raise AssertionError("Tetrahedron coloring disagrees with edge-by-edge oracle")
        if expected:
            proper.append(colors)
    balanced = 0
    vertex_index = {vertex: i for i, vertex in enumerate(plane_map.vertices)}
    integer_edges = tuple((vertex_index[u], vertex_index[v]) for u, v in plane_map.edges)
    for labels in product((1, 2, 3), repeat=len(plane_map.edges)):
        expected_defects = xor_defects(len(vertex_index), integer_edges, labels)
        if tuple(vertex_defects(plane_map, labels).values()) != expected_defects:
            raise AssertionError("Vertex defects disagree with endpoint-incidence oracle")
        if not any(expected_defects):
            reconstructed = plane_map.integrate(labels)
            if not face_assignment_is_proper(plane_map, reconstructed):
                raise AssertionError("Balanced nonzero assignment did not integrate properly")
            balanced += 1
    return {
        "vertices": len(plane_map.vertices),
        "edges": len(plane_map.edges),
        "faces": len(plane_map.faces),
        "face_assignments_examined": 4 ** len(plane_map.faces),
        "proper_face_colorings": len(proper),
        "nonzero_edge_assignments_examined": 3 ** len(plane_map.edges),
        "balanced_nonzero_edge_assignments": balanced,
    }


def enumerate_repair_cases():
    """Count exact finite cases while comparing all four terminal-flow states."""
    groups = {"triangle_all_initial_labels": [], "theta_all_initial_labels": [], "seeded_random": []}
    for a, b, c in product((1, 2, 3), repeat=3):
        groups["triangle_all_initial_labels"].append(Parallel(Edge(a), Series(Edge(b), Edge(c))))
        groups["theta_all_initial_labels"].append(Parallel(Parallel(Edge(a), Edge(b)), Edge(c)))
    rng = random.Random(SEED)
    for _ in range(30):
        groups["seeded_random"].append(random_expression(rng, rng.randint(1, 7)))
    summary = {}
    for name, expressions in groups.items():
        feasible = 0
        candidate_labelings = 0
        maximum_edges = 0
        for expression in expressions:
            n, edges, original, terminals = realize(expression)
            expected, _ = brute_repair_table(n, edges, original, terminals)
            if tuple(repair_table(expression)) != expected:
                raise AssertionError(f"Flow repair recurrence mismatch in {name}")
            if minimum_repair(expression)[0] != expected[0]:
                raise AssertionError(f"Flow repair optimum mismatch in {name}")
            feasible += expected[0] != float("inf")
            candidate_labelings += 3 ** len(edges)
            maximum_edges = max(maximum_edges, len(edges))
        summary[name] = {
            "instances": len(expressions),
            "terminal_states_compared": 4 * len(expressions),
            "candidate_labelings_enumerated": candidate_labelings,
            "maximum_edges": maximum_edges,
            "zero_defect_feasible_instances": feasible,
            "zero_defect_infeasible_instances": len(expressions) - feasible,
        }
    return summary


def validate_recursive_construction():
    """Record the original split-history idea as a reproducible concrete trace."""
    initial, operations = tetrahedron_history()
    final, logs = replay(initial, operations)
    maps = [initial]
    for operation in operations:
        maps.append(apply_operation(maps[-1], operation))
    if final.faces != maps[-1].faces or final.edges != maps[-1].edges:
        raise AssertionError("History replay disagrees with elementary-operation dispatch")
    states = []
    for step, plane_map in enumerate(maps):
        count = sum(
            face_assignment_is_proper(plane_map, colors)
            for colors in product(range(4), repeat=len(plane_map.faces))
        )
        states.append({
            "step": step,
            "vertices": len(plane_map.vertices),
            "edges": len(plane_map.edges),
            "faces": len(plane_map.faces),
            "proper_face_colorings": count,
        })
    return {
        "example": "triangle -> dangling interior edge -> first closure -> tetrahedral map",
        "states": states,
        "operations": list(operations),
        "face_lineage_events_checked": len(logs),
    }


def validate_precoloring_obstruction():
    """Show exactly why one fixed proper boundary is not a sufficient state."""
    rim = ((0, 1), (1, 2), (2, 3), (3, 0))
    wheel = rim + tuple((vertex, 4) for vertex in range(4))
    proper_rims = brute_colorings(4, rim)
    extensions = brute_colorings(5, wheel)
    signature = set(boundary_signature(5, wheel, (0, 1, 2, 3)))
    if signature != {colors[:4] for colors in extensions}:
        raise AssertionError("Wheel boundary signature disagrees with exhaustive coloring oracle")
    obstruction = (0, 1, 2, 3)
    if obstruction not in proper_rims or obstruction in signature:
        raise AssertionError("Expected proper-but-nonextendable wheel rim not reproduced")
    return {
        "graph": "four-cycle rim with one hub adjacent to all four rim vertices",
        "proper_rim_colorings": len(proper_rims),
        "extendable_rim_colorings": len(signature),
        "nonextendable_proper_rim_colorings": len(proper_rims - signature),
        "total_proper_four_colorings": len(extensions),
        "nonextendable_rim_example": list(obstruction),
        "valid_full_coloring_example": [0, 1, 0, 1, 2],
        "meaning": "Failure of this fixed boundary precoloring, not failure of four-colorability.",
    }


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPOSITORY_ROOT / "outputs" / "validation.json")
    arguments = parser.parse_args()
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(REPOSITORY_ROOT / "tests"), top_level_dir=str(REPOSITORY_ROOT))
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    print(stream.getvalue(), end="")
    report = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "random_seed": SEED,
        "scope": "Finite implementation checks only; not an exhaustive check of planar graphs or a new proof of the Four Color Theorem.",
        "unittest": {
            "tests_run": result.testsRun,
            "failures": len(result.failures),
            "errors": len(result.errors),
            "skipped": len(result.skipped),
            "passed": result.wasSuccessful(),
        },
    }
    if result.wasSuccessful():
        report["tetrahedron_exhaustive"] = enumerate_tetrahedron()
        report["series_parallel_repair"] = enumerate_repair_cases()
        report["recursive_construction"] = validate_recursive_construction()
        report["precoloring_obstruction"] = validate_precoloring_obstruction()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Validation report written.")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())

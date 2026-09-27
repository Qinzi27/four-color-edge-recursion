"""Exhaust the declared five-side scope of the shared-triangle equality rule.

All 2^10 labeled simple graphs on five sides and all 4^5 complete assignments
are checked. This is a finite implementation check of an elementary known
implication, not a proof of completeness, global extendibility or planarity.
No coloring oracle, domain propagator, producer choices or anchor is consulted.
The caller is responsible for freezing sources and saving unique artifacts.
"""

from hashlib import sha256
from itertools import combinations, product
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.quaternary_triangle_eq import learn_triangle_equalities, verify_triangle_equalities


VERSION = "quaternary-shared-triangle-finite-soundness-v1"


def _digest(value):
    """Hash deterministic portable JSON, with no wall clock or machine paths."""
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode("utf-8")).hexdigest()


def check_rule_soundness():
    """Return exact counts and per-graph evidence for the fixed exhaustive run.

    Graph bits follow lexicographic unordered vertex pairs; assignment tuples
    follow lexicographic products of names 1..4. The learner/checker identify
    certified pairs, but legality and equality conclusions are checked using
    ordinary integer comparisons on every assignment against the original
    raw lines. Assignments are not quotiented by color or vertex symmetry.
    """
    sides = [f"S{i}" for i in range(5)]
    side_index = {name: index for index, name in enumerate(sides)}
    possible_edges = list(combinations(range(5), 2))
    assignments = list(product((1, 2, 3, 4), repeat=5))
    per_graph = []
    total_legal = 0
    graphs_with_certificates = 0
    certificate_count = 0
    certified_legal = 0
    eq_projection_checks = 0
    graph_assignment_pairs = 0
    graphs_without_legal_assignments = 0
    for graph_mask in range(1 << len(possible_edges)):
        edges = [edge for bit, edge in enumerate(possible_edges) if graph_mask & (1 << bit)]
        document = {"sides": list(sides), "lines": [
            {"id": f"E{i}", "left": sides[first], "right": sides[second], "kind": "separator"}
            for i, (first, second) in enumerate(edges)]}
        learned = learn_triangle_equalities(document)
        verified = verify_triangle_equalities(document, learned)
        if verified.get("passed") is not True:
            raise ValueError(f"shared-triangle certificate verification failed for graph {graph_mask}")

        # Resolve these indices directly from literal raw records, independently
        # of the learner's adjacency sets and verifier's boolean matrix.
        raw_neq = [(side_index[line["left"]], side_index[line["right"]])
                   for line in document["lines"]]
        logical_pairs = [(side_index[a], side_index[e]) for a, e in learned["equal_names"]]
        legal_assignments = []
        graph_eq_checks = 0
        for colors in assignments:
            graph_assignment_pairs += 1
            if not all(colors[first] != colors[second] for first, second in raw_neq):
                continue
            legal_assignments.append(list(colors))
            for first, second in logical_pairs:
                graph_eq_checks += 1
                if colors[first] != colors[second]:
                    # Preserve the exact finite witness in the exception; never
                    # silently discard a failed graph or mark unknown as sound.
                    raise ValueError(f"unsound EQ on graph {graph_mask}: "
                                     f"{sides[first]}={sides[second]}, colors={colors}")
        count = len(legal_assignments)
        certificates = len(learned["certificates"])
        if certificates:
            graphs_with_certificates += 1
            certified_legal += count
        if not count:
            graphs_without_legal_assignments += 1
        total_legal += count
        certificate_count += certificates
        eq_projection_checks += graph_eq_checks
        per_graph.append({"graph_mask": graph_mask, "edge_count": len(edges),
                          "raw_document_sha256": learned["raw_document_sha256"],
                          "learning_sha256": _digest(learned),
                          "literal_assignments_checked": len(assignments),
                          "legal_assignments": count,
                          "legal_assignments_sha256": _digest(legal_assignments),
                          "equal_names": learned["equal_names"],
                          "certificate_count": certificates,
                          "eq_projection_checks": graph_eq_checks})
    return {"schema_version": 1, "version": VERSION, "passed": True,
            "scope": {"vertex_count": 5, "side_order": sides,
                      "palette": [1, 2, 3, 4],
                      "graph_bit_order": [list(edge) for edge in possible_edges],
                      "graph_scope": "Every labeled simple undirected graph on five vertices",
                      "assignment_order": "Lexicographic full product of names 1..4 over side_order",
                      "anchors": {}, "color_symmetry_reduction": False,
                      "vertex_symmetry_reduction": False,
                      "planarity_filter": False, "oracle_used": False,
                      "boundary": "Finite rule implementation soundness only; includes nonplanar "
                                  "and uncolorable abstract graphs and does not certify a full algorithm."},
            "graph_count": len(per_graph), "assignments_per_graph": len(assignments),
            "graph_assignment_pairs": graph_assignment_pairs,
            "total_legal_assignments": total_legal,
            "graphs_without_legal_assignments": graphs_without_legal_assignments,
            "graphs_with_certificates": graphs_with_certificates,
            "certificate_count": certificate_count,
            "legal_assignments_in_certified_graphs": certified_legal,
            "eq_projection_checks": eq_projection_checks,
            "assignment_inventory_sha256": _digest([list(values) for values in assignments]),
            "per_graph": per_graph, "per_graph_sha256": _digest(per_graph)}

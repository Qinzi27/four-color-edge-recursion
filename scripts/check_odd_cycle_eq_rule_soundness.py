"""Exhaust fixed odd/even two-apex-cycle families and single-edge deletions.

The predeclared scope is rim lengths 3, 4, 5, 6, 7. For each length k, check
the graph with two nonadjacent apices, both joined to every cycle vertex,
and each of its 3k single-edge deletions. All 80 labeled input graphs and all
literal four-name assignments on each graph are checked without color or
vertex symmetry reduction. This is not enumeration of all graphs on at most
nine vertices, geometric realizations, or algorithm-reachable states.

Direct raw-edge scalar comparisons provide legality; no oracle, propagation
engine, low-color choices or target colors are used. The caller must freeze
sources before saving a unique formal artifact.
"""

from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.quaternary_odd_cycle_eq import learn_odd_cycle_equalities, verify_odd_cycle_equalities


VERSION = "quaternary-shared-odd-cycle-finite-soundness-v1"
RIM_LENGTHS = (3, 4, 5, 6, 7)


def _digest(value):
    """Hash portable deterministic JSON without clocks or local machine paths."""
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode("utf-8")).hexdigest()


def rule_inventory():
    """Declare every labeled raw graph before evaluating any assignment.

    Side order is A, E, R0, ..., R(k-1). Edges are lexicographically ordered
    index pairs, so the deletion index unambiguously identifies one rim or
    spoke edge. Graphs are distinct as labeled raw graphs; no isomorphism
    reduction is performed or claimed.
    """
    records = []
    for length in RIM_LENGTHS:
        sides = ["A", "E"] + [f"R{i}" for i in range(length)]
        edges = sorted({tuple(sorted((2 + i, 2 + (i + 1) % length))) for i in range(length)}
                       | {(apex, rim + 2) for apex in range(2) for rim in range(length)})
        for deletion in (None, *range(len(edges))):
            selected = [edge for i, edge in enumerate(edges) if i != deletion]
            document = {"sides": sides, "lines": [
                {"id": f"edge-{i}", "left": sides[first], "right": sides[second], "kind": "separator"}
                for i, (first, second) in enumerate(selected)]}
            records.append({"id": f"two-apex-cycle-{length}-" + (
                "full" if deletion is None else f"delete-{deletion:02d}"),
                "rim_length": length, "deleted_edge": None if deletion is None else list(edges[deletion]),
                "document": document})
    return records


def check_rule_soundness():
    """Return deterministic evidence for every graph-assignment pair.

    Assignment products are traversed once per vertex count, but each literal
    assignment is tested against every graph of that count. A raw-edge bit
    mask avoids repeated scalar comparisons for shared edges. It is merely
    an exhaustive legality test, not a coloring search or symmetry quotient.
    Complete legal assignment lists are hashed independently for each graph.
    """
    inventory = rule_inventory()
    per_graph = []
    for length in RIM_LENGTHS:
        records = [record for record in inventory if record["rim_length"] == length]
        sides = records[0]["document"]["sides"]
        positions = {side: i for i, side in enumerate(sides)}
        raw_edges = [(positions[line["left"]], positions[line["right"]])
                     for line in records[0]["document"]["lines"]]
        raw_edge_positions = {edge: i for i, edge in enumerate(raw_edges)}
        work = []
        for record in records:
            document = record["document"]
            learned = learn_odd_cycle_equalities(document)
            verify_odd_cycle_equalities(document, learned)
            selected = [(positions[line["left"]], positions[line["right"]])
                        for line in document["lines"]]
            graph_mask = sum(1 << raw_edge_positions[edge] for edge in selected)
            logical_pairs = [(positions[a], positions[e]) for a, e in learned["equal_names"]]
            work.append({"record": record, "learned": learned, "graph_mask": graph_mask,
                         "logical_pairs": logical_pairs, "legal": [], "checks": 0,
                         "unequal_apices_witness": None})
        literal_count = 0
        for colors in product((1, 2, 3, 4), repeat=len(sides)):
            literal_count += 1
            forbidden = sum(1 << bit for bit, (first, second) in enumerate(raw_edges)
                            if colors[first] == colors[second])
            for graph in work:
                if forbidden & graph["graph_mask"]:
                    continue
                graph["legal"].append(list(colors))
                if colors[0] != colors[1] and graph["unequal_apices_witness"] is None:
                    graph["unequal_apices_witness"] = list(colors)
                for first, second in graph["logical_pairs"]:
                    graph["checks"] += 1
                    if colors[first] != colors[second]:
                        raise ValueError(f"unsound odd-cycle EQ on {graph['record']['id']}: "
                                         f"{sides[first]}={sides[second]}, colors={colors}")
        for graph in work:
            record, learned = graph["record"], graph["learned"]
            expected_apex_eq = record["deleted_edge"] is None and length % 2 == 1
            if (["A", "E"] in learned["equal_names"]) != expected_apex_eq:
                raise ValueError(f"declared apex-control classification failed: {record['id']}")
            if (graph["unequal_apices_witness"] is None) != expected_apex_eq:
                raise ValueError(f"literal apex-control witness failed: {record['id']}")
            per_graph.append({"id": record["id"], "rim_length": length,
                              "deleted_edge": record["deleted_edge"],
                              "vertex_count": len(sides), "edge_count": len(record["document"]["lines"]),
                              "raw_document_sha256": learned["raw_document_sha256"],
                              "learning_sha256": _digest(learned),
                              "literal_assignments_checked": literal_count,
                              "legal_assignments": len(graph["legal"]),
                              "legal_assignments_sha256": _digest(graph["legal"]),
                              "equal_names": learned["equal_names"],
                              "certificate_count": len(learned["certificates"]),
                              "certificate_lengths": [len(item["cycle"]) for item in learned["certificates"]],
                              "eq_projection_checks": graph["checks"],
                              "expected_apex_equality": expected_apex_eq,
                              "unequal_apices_witness": graph["unequal_apices_witness"]})
    return {"schema_version": 1, "version": VERSION, "passed": True,
            "scope": {"rim_lengths": list(RIM_LENGTHS), "palette": [1, 2, 3, 4],
                      "graph_scope": "Two-apex cycle graphs and every single rim/spoke edge deletion",
                      "side_order": "A,E,R0,...,R(k-1)",
                      "assignment_order": "Lexicographic full product of names 1..4 over side_order",
                      "anchors": {}, "color_symmetry_reduction": False,
                      "vertex_symmetry_reduction": False, "planarity_filter": False,
                      "oracle_used": False,
                      "boundary": "Finite rule implementation check on the declared 80 graphs, "
                                  "not all graphs, geometry, reachable states or full algorithm soundness."},
            "graph_count": len(per_graph),
            "graph_assignment_pairs": sum(row["literal_assignments_checked"] for row in per_graph),
            "total_legal_assignments": sum(row["legal_assignments"] for row in per_graph),
            "graphs_without_legal_assignments": sum(row["legal_assignments"] == 0 for row in per_graph),
            "graphs_with_certificates": sum(row["certificate_count"] > 0 for row in per_graph),
            "certificate_count": sum(row["certificate_count"] for row in per_graph),
            "legal_assignments_in_certified_graphs": sum(row["legal_assignments"] for row in per_graph
                                                        if row["certificate_count"]),
            "eq_projection_checks": sum(row["eq_projection_checks"] for row in per_graph),
            "negative_control_witnesses": sum(row["unequal_apices_witness"] is not None for row in per_graph),
            "input_inventory_sha256": _digest(inventory),
            "per_graph": per_graph, "per_graph_sha256": _digest(per_graph)}

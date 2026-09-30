"""Learn unconditional logical NEQ from original real separator constraints.

This adapter reuses the frozen structural same-name refuter; it does not
introduce a new refutation theorem or add physical geometry. Every original
nonedge is queried once, and inconclusive closures are retained alongside
proved inequalities. Anchors bind the input hash but never enter discovery.
"""

from itertools import combinations

from fourcolor.structural_name_relations import refute_same_name
from scripts.quaternary_contact_model import _validate
from scripts.quaternary_odd_cycle_eq import _digest, _require


VERSION = "quaternary-raw-logical-inequalities-v1"


def learn_logical_inequalities(document):
    """Query each unordered nonadjacent pair using only raw physical NEQ.

    Side input order fixes pair ordering. Parallel separator lines collapse
    to one undirected constraint; bridges and point contacts contribute none.
    Supplied nonempty domains or EQ are outside this raw-graph entry, and the
    old validator rejects ``different_names`` even when empty. No learned
    relation, color, candidate domain, or previous query feeds the next query.

    There is no face-count cutoff here; the experiment runner declares its
    eligible size range before learning. A singleton input has no pair queries.
    Certificate validation is deliberately in a separate independent auditor.
    """
    sides, _ = _validate(document)
    _require(not document.get("states"), "raw inequality learning rejects external states")
    _require(not document.get("equal_names"), "raw inequality learning rejects supplied equal_names")
    index = {side: i for i, side in enumerate(sides)}
    edges = set()
    separators = bridges = 0
    for line in document["lines"]:
        if line["kind"] == "bridge":
            bridges += 1
            continue
        separators += 1
        edges.add(tuple(sorted((index[line["left"]], index[line["right"]]))))
    original_edges = sorted(edges)
    queries, different_names = [], []
    for first, second in combinations(range(len(sides)), 2):
        if (first, second) in edges:
            continue
        pair = [sides[first], sides[second]]
        result = refute_same_name(len(sides), original_edges, first, second)
        queries.append({"pair": pair, "result": result})
        if result["status"] == "proved_different":
            different_names.append(list(pair))
    return {"version": VERSION, "raw_document_sha256": _digest(document),
            "different_names": different_names, "queries": queries,
            "stats": {"side_count": len(sides), "neq_edge_count": len(edges),
                      "separator_line_count": separators, "bridge_line_count": bridges,
                      "point_contact_count": len(document.get("point_contacts", [])),
                      "eligible_pairs": len(queries), "proved_different": len(different_names),
                      "inconclusive": len(queries) - len(different_names)}}

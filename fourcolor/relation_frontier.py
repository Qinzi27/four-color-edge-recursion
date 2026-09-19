"""Reuse ordered-pair filtering in the current geometry-only restart rule.

This is an integration experiment, not a new cycle decomposition or a new
four-color proof. Mother IDs and interval scheduling are unchanged. The
existing Hall filter and existing binary relation filter alternate before
each irreversible greedy name choice. No color is tried and then retracted.
Relations on nonadjacent shores are auxiliary compatibility records, not
additional lines in the drawing. The fixed palette is an input assumption.
"""

from .closed_support import supported_cycle_units
from .frontier_restart import frontier_priorities, neighbor_sets, propagate_hall, small_cliques
from .global_restart import current_segments
from .relation_names import _domains, initial_relations, relation_closure
from .whole_lines import build_whole_lines


POLICY = "tight-hall-relations"


def propagate_frontier_relations(model, anchors, cliques=None):
    """Shrink unary domains and binary pairs to a joint necessary fixed point.

    A compatible complete assignment survives every Hall deletion and every
    relational composition deletion. Repeating their conjunction therefore
    remains sound. Nonempty output does NOT certify a complete assignment.
    Derived domain constraints are temporary filter inputs, never commitments.
    Preserve the pair matrix between rounds: rebuilding it from projections
    alone would lose the very correlations this integration is meant to keep.
    """
    cliques = small_cliques(neighbor_sets(model)) if cliques is None else cliques
    work_anchors = {dart: list(values) for dart, values in anchors.items()}
    relations = None
    phases = []
    revisions = 0
    while True:
        hall = propagate_hall(model, work_anchors, cliques)
        permitted = initial_relations(model, hall["domains"])
        if relations is None:
            relations = permitted
        else:
            relations = [[old & allowed for old, allowed in zip(row, bounds)]
                         for row, bounds in zip(relations, permitted)]
        # Hall conflicts need no expensive pair propagation to be certified.
        filtered = ({"relations": relations, "trace": [], "revisions": 0,
                     "conflict": True} if hall["status"] == "conflict"
                    else relation_closure(relations))
        phases.append({"hall_input_anchors": work_anchors,
                       "hall_status": hall["status"], "hall_domains": hall["domains"],
                       "hall_trace": hall["trace"], "hall_conflict": hall.get("hall_conflict"),
                       "relation_input": relations, "relation_trace": filtered["trace"],
                       "relation_conflict": filtered["conflict"]})
        relations = filtered["relations"]
        revisions += filtered["revisions"]
        domains = _domains(relations)
        if filtered["conflict"]:
            status = "conflict"
            break
        if domains == hall["domains"]:
            status = "solved" if all(len(d) == 1 for d in domains) else "underdetermined"
            break
        # Each repeat loses at least one unary candidate, hence at most 4n
        # repeats. Use one representative per shore, preserving all intervals.
        work_anchors = {face[0]: list(domain)
                        for face, domain in zip(model.plane_map.faces, domains)}
    return {"status": status, "domains": domains, "relations": relations,
            "phases": phases, "revisions": revisions,
            "hall_conflict": hall.get("hall_conflict"),
            "backtracks": 0, "choices": 0, "palette": [1, 2, 3, 4]}


def restart_relation_frontier_names(geometry):
    """Keep tight-hall scheduling unchanged; strengthen only its pre-choice filter.

    Every call starts at exterior 1 / first interior 2, ignoring former names.
    The pre-existing closed-support tie-break is unchanged; no new loop search
    or loop grouping is introduced. An unsuccessful greedy run stays a failure
    of this strategy, not a claim that the original uncolored map is impossible.
    """
    model = build_whole_lines(geometry)
    frame = next((line for line in model.lines if line["id"] == "frame"), None)
    if frame is None:
        raise ValueError("restart requires an explicit rectangular outer frame")
    first = frame["spans"][0]["dart"]
    anchors = {first: [1], first ^ 1: [2]}
    initial = dict(anchors)
    units = current_segments(model)
    by_id = {unit["id"]: unit for unit in units}
    neighbors = neighbor_sets(model)
    cliques = small_cliques(neighbors)
    outcome = propagate_frontier_relations(model, anchors, cliques)
    # Keep proof phases for EVERY decision, not just the final coloring.
    propagations = [{"anchors_by_dart": dict(anchors), "outcome": outcome}]
    trace = []
    while outcome["status"] == "underdetermined":
        support = supported_cycle_units(model, outcome["domains"], units)
        rows = frontier_priorities(units, outcome["domains"], neighbors, support, degree=True)
        if not rows:
            raise AssertionError("unresolved shore has no real-line occurrence")
        highest = max(row["priority"] for row in rows)
        tied = sorted((r for r in rows if r["priority"] == highest),
                      key=lambda r: (r["mother"], by_id[r["unit"]]["t0"]))
        chosen = tied[0]
        domain = outcome["domains"][chosen["side"]]
        used = {d[0] for d in outcome["domains"] if len(d) == 1}
        symbol = min(domain, key=lambda c: (c not in used, c))
        trace.append({**chosen, "domain": domain, "used_names": sorted(used),
                      "symbol": symbol, "tied_units": [r["unit"] for r in tied],
                      "choice_kind": "greedy-not-a-proved-safe-extension"})
        anchors[chosen["dart"]] = [symbol]
        outcome = propagate_frontier_relations(model, anchors, cliques)
        propagations.append({"anchors_by_dart": dict(anchors), "outcome": outcome})
    return {"status": outcome["status"], "policy": POLICY, "domains": outcome["domains"],
            "anchors_by_dart": anchors, "initial_anchors_by_dart": initial,
            "units": units, "trace": trace, "choices": len(trace), "backtracks": 0,
            "relations": outcome["relations"], "propagation_phases": propagations,
            "hall_conflict": outcome["hall_conflict"],
            "colors": [d[0] for d in outcome["domains"]] if outcome["status"] == "solved" else None,
            "old_colors_read": False, "local_budget": None,
            "scope": "Existing pair filter integrated into geometry restart; no assignment retries; four is given."}

"""A geometry-only v2 extension that checks proposed reuse by structural proof.

The historical v2 schedule and minimum-name choice remain the baseline. Before
committing a proposed reuse, this policy can refute equality with an already
singleton side using only the real adjacency graph. A proved inequality enters
the logical matrix; it is never drawn as a new geometric edge. Failure to find
a refutation is inconclusive, so the remaining greedy step is still unproved.
"""

from .frontier_restart import neighbor_sets, propagate_hall, small_cliques
from .global_restart import current_segments
from .level_sides import effective_boundary, level_metadata
from .level_sides_peer import select_peer_occurrence
from .relation_names import _domains, initial_relations, relation_closure, transpose
from .structural_name_relations import refute_same_name
from .whole_lines import build_whole_lines


POLICY = "mother-peer-structural-reuse-v1"
NEQ = sum(1 << (4 * a + b) for a in range(4) for b in range(4) if a != b)


def propagate_structural_relations(model, anchors, cliques, learned_pairs):
    """Alternate the old Hall/pair closure with proved, persistent inequalities.

The producer never invents Hall cliques from auxiliary inequalities. All Hall
steps still use genuine shared boundaries. Each loop preserves every complete
coloring consistent with the commitments and the supplied proved relations.
"""
    work_anchors = {dart: list(values) for dart, values in anchors.items()}
    relations, phases, revisions = None, [], 0
    while True:
        hall = propagate_hall(model, work_anchors, cliques)
        permitted = initial_relations(model, hall["domains"])
        before = permitted if relations is None else [
            [old & allowed for old, allowed in zip(row, bounds)]
            for row, bounds in zip(relations, permitted)]
        relations = [row[:] for row in before]
        structural_trace = []
        for a, b in learned_pairs:
            old = relations[a][b]
            after = old & NEQ
            if after != old:
                structural_trace.append({"pair": [a, b], "before": old,
                                         "after": after, "removed": old ^ after})
                relations[a][b], relations[b][a] = after, transpose(after)
        impossible = hall["status"] == "conflict" or any(not mask for row in relations for mask in row)
        filtered = ({"relations": relations, "trace": [], "revisions": 0, "conflict": True}
                    if impossible else relation_closure(relations))
        phases.append({"hall_input_anchors": work_anchors, "hall_status": hall["status"],
                       "hall_domains": hall["domains"], "hall_trace": hall["trace"],
                       "hall_conflict": hall.get("hall_conflict"),
                       "pre_structural_relations": before, "structural_trace": structural_trace,
                       "relation_input": relations, "relation_trace": filtered["trace"],
                       "relation_conflict": filtered["conflict"]})
        relations = filtered["relations"]
        revisions += filtered["revisions"]
        domains = _domains(relations)
        if filtered["conflict"]:
            status = "conflict"
            break
        if domains == hall["domains"]:
            status = "solved" if all(len(domain) == 1 for domain in domains) else "underdetermined"
            break
        work_anchors = {face[0]: list(domain) for face, domain in zip(model.plane_map.faces, domains)}
    return {"status": status, "domains": domains, "relations": relations, "phases": phases,
            "revisions": revisions, "hall_conflict": hall.get("hall_conflict"),
            "learned_pairs": [list(pair) for pair in learned_pairs],
            "backtracks": 0, "choices": 0, "palette": [1, 2, 3, 4]}


def restart_structural_names(geometry, *, structural=True):
    """Run one declared policy from current geometry, with no prior color input.

At each proposal, check all other singleton sides bearing the proposed name,
in side-ID order. Stop at the first proved inequality, propagate it, and select
again. Cache each unordered graph query, including inconclusive outcomes. The
unchecked/surviving minimum is committed once; a later conflict ends the run.
This is explicit equality-hypothesis testing, not unconditional propagation.
"""
    if type(structural) is not bool:
        raise ValueError("structural must be a boolean")
    model = build_whole_lines(geometry)
    levels, units = level_metadata(model), current_segments(model)
    adjacent = neighbor_sets(model)
    cliques = small_cliques(adjacent)
    frame = next(line for line in model.lines if line["id"] == "frame")
    first = frame["spans"][0]["dart"]
    anchors = {first: [1], first ^ 1: [2]}
    initial = dict(anchors)
    edges = sorted({tuple(sorted(model.plane_map.shores(edge)))
                    for edge in range(len(model.plane_map.edges))
                    if len(set(model.plane_map.shores(edge))) == 2})
    boundary_sources = [{"pair": list(pair), "raw_edge_ids": [
        edge for edge in range(len(model.plane_map.edges))
        if tuple(sorted(model.plane_map.shores(edge))) == pair]} for pair in edges]
    learned, queries, cache, events, trace = [], [], {}, [], []
    outcome = propagate_structural_relations(model, anchors, cliques, learned)
    calls = [{"anchors_by_dart": dict(anchors), "learned_pairs": [], "outcome": outcome}]
    while outcome["status"] == "underdetermined":
        selected = select_peer_occurrence(model, units, levels, outcome["domains"])
        side, dart = selected["side"], selected["dart"]
        domain = outcome["domains"][side]
        symbol = min(domain)
        boundary = effective_boundary(model, outcome["domains"], side)
        proposal = {**selected, "domain": list(domain), "symbol": symbol, "boundary": boundary,
                    "choice_kind": "greedy-not-a-proved-safe-extension"}
        checks, proved = [], None
        if structural:
            for other, values in enumerate(outcome["domains"]):
                if other == side or values != [symbol]:
                    continue
                pair = tuple(sorted((side, other)))
                was_cached = pair in cache
                if not was_cached:
                    certificate = refute_same_name(len(adjacent), edges, *pair)
                    cache[pair] = len(queries)
                    queries.append({"pair": list(pair), "certificate": certificate})
                index = cache[pair]
                certificate = queries[index]["certificate"]
                checks.append({"other_side": other, "pair": list(pair),
                               "query_index": index, "cached": was_cached})
                if certificate["status"] == "proved_different":
                    if pair in learned:
                        raise AssertionError("learned inequality did not remove an equal singleton pair")
                    proved = pair
                    learned.append(pair)
                    break
        if proved is None:
            kind = "commit"
            trace.append(proposal)
            anchors[dart] = [symbol]
        else:
            kind = "learn_relation"
        events.append({"kind": kind, "proposal": proposal, "checks": checks,
                       "learned_pair": list(proved) if proved is not None else None})
        outcome = propagate_structural_relations(model, anchors, cliques, learned)
        calls.append({"anchors_by_dart": dict(anchors),
                      "learned_pairs": [list(pair) for pair in learned], "outcome": outcome})
    return {"policy": POLICY if structural else POLICY + "-disabled",
            "status": outcome["status"], "structural": structural,
            "levels": levels, "units": units,
            "unranked_mothers": sorted(name for name, info in levels.items() if info["level"] is None),
            "initial_anchors_by_dart": initial, "anchors_by_dart": anchors,
            "trace": trace, "choices": len(trace), "events": events,
            "propagation_phases": calls, "proof_queries": queries,
            "learned_pairs": [list(pair) for pair in learned],
            "geometric_edge_sources": boundary_sources,
            "domains": outcome["domains"], "relations": outcome["relations"],
            "hall_conflict": outcome["hall_conflict"],
            "colors": [domain[0] for domain in outcome["domains"]] if outcome["status"] == "solved" else None,
            "old_colors_read": False, "backtracks": 0, "local_budget": None,
            "statistics": {"unique_structural_queries": len(queries),
                           "query_checks": sum(len(event["checks"]) for event in events),
                           "cache_hits": sum(check["cached"] for event in events for check in event["checks"]),
                           "learned_relations": len(learned)},
            "scope": "v2 schedule with explicit same-name structural hypotheses before commitment; "
                     "no coloring search or Kempe rescue, no general completion guarantee; four names are input"}

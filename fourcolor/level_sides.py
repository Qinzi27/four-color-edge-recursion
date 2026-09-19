"""Experimental mother-level scheduling with current boundary provenance.

Levels preserve geometric dependency, never permanent ancestral color bans.
This candidate orders complete current mothers, NOT historical drawing steps.
Completing a shallow mother's profile can name a deep subdivision touching it.
The palette and sound Hall/pair filters are inherited experimental assumptions;
no completeness or safe-greedy-extension theorem is claimed.
"""

from collections import defaultdict

from .closed_support import supported_cycle_units
from .frontier_restart import frontier_priorities, neighbor_sets, small_cliques
from .global_restart import current_segments
from .relation_frontier import propagate_frontier_relations
from .whole_lines import build_whole_lines

POLICY = "mother-level-current-sides-v1"


def level_metadata(model):
    """Synchronous double-end support; frame=1, ambiguous parents stay plural.

    Only true endpoints of a maximal straight mother define its dependencies.
    T/X contacts inside a mother do not break its identity or raise its level.
    This duplicates neither a coloring nor a history: geometry is the sole input.
    """
    owners = defaultdict(set)
    for edge, mother in model.edge_owner.items():
        for vertex in model.plane_map.edges[edge]:
            owners[vertex].add(mother)
    result = {}
    for line in model.lines:
        name = line["id"]
        contacts = [[], []]
        if name != "frame":
            first, last = line["spans"][0]["dart"], line["spans"][-1]["dart"]
            vertices = [model.plane_map.edges[first // 2][first % 2],
                        model.plane_map.edges[last // 2][1 - last % 2]]
            contacts = [sorted(owners[v] - {name}) for v in vertices]
        result[name] = {"level": 1 if name == "frame" else None,
                        "parents": [[], []], "endpoint_contacts": contacts,
                        "endpoints": line["endpoints"]}
    if "frame" not in result:
        raise ValueError("level naming requires an explicit frame")
    while True:
        additions = {}
        for name, info in result.items():
            if info["level"] is not None:
                continue
            known = [[p for p in port if result[p]["level"] is not None]
                     for port in info["endpoint_contacts"]]
            if not all(known):
                continue
            lowest = [min(result[p]["level"] for p in port) for port in known]
            parents = [sorted(p for p in port if result[p]["level"] == value)
                       for port, value in zip(known, lowest)]
            additions[name] = {**info, "parents": parents, "level": 1 + max(lowest)}
        if not additions:
            return result
        result.update(additions)


def effective_boundary(model, domains, side):
    """Trace ALL real opposite intervals of one connected side, not just ports.

    Direct bans arise only from current singleton neighbors. Auxiliary Hall /
    relation deductions may forbid additional names; their proofs are retained
    in propagation_phases. An internal neighbor named 1 still forbids 1.
    """
    if not 0 <= side < len(domains):
        raise ValueError("side is outside current geometry")
    sources, forbidden = [], set()
    for line in model.lines:
        for span in line["spans"]:
            a, b = span["left_side"], span["right_side"]
            if a == b or side not in (a, b):
                continue
            other = b if side == a else a
            values = list(domains[other])
            sources.append({"edge": span["edge"], "mother": line["id"],
                            "interval": [span["t0"], span["t1"]],
                            "neighbor": other, "neighbor_domain": values})
            if len(values) == 1:
                forbidden.add(values[0])
    local = sorted(set(range(1, 5)) - forbidden)
    return {"sources": sources, "direct_forbidden": sorted(forbidden),
            "local_candidates": local,
            "derived_exclusions": sorted(set(local) - set(domains[side])),
            "one_allowed": 1 in domains[side]}


def mother_order(info):
    """Numerical top-to-bottom/left-to-right convention, not a geometric invariant."""
    points = sorted((p[1], p[0]) for p in info["endpoints"])
    return (info["level"], tuple(points))


def select_level_occurrence(model, units, levels, domains):
    """Finish the first unfinished internal mother before later mother stages.

    Frame is only the root anchor, not a task to color every exterior neighbor.
    Within the chosen whole mother retain existing local urgency criteria.
    This is one fixed ordering; no direction/phase/line is retried on conflict.
    """
    neighbors = neighbor_sets(model)
    support = supported_cycle_units(model, domains, units)
    rows = [r for r in frontier_priorities(units, domains, neighbors, support, degree=True)
            if r["mother"] != "frame"]
    if not rows:
        raise AssertionError("unresolved side has no internal mother occurrence")
    mother = min({r["mother"] for r in rows}, key=lambda name: mother_order(levels[name]))
    eligible = [r for r in rows if r["mother"] == mother]
    best = max(r["priority"] for r in eligible)
    by_id = {u["id"]: u for u in units}
    tied = sorted((r for r in eligible if r["priority"] == best),
                  key=lambda r: (by_id[r["unit"]]["t0"], r["dart"]))
    return {**tied[0], "tied_units": [r["unit"] for r in tied],
            "level": levels[mother]["level"], "parents": levels[mother]["parents"]}


def restart_level_side_names(geometry):
    """One geometry-only deterministic attempt with no old color input or retry."""
    model = build_whole_lines(geometry)
    levels = level_metadata(model)
    unranked = sorted(name for name, info in levels.items() if info["level"] is None)
    if unranked:
        return {"status": "outside_scope", "policy": POLICY, "levels": levels,
                "unranked_mothers": unranked, "trace": [], "choices": 0,
                "backtracks": 0, "old_colors_read": False, "colors": None,
                "reason": "double-end geometric support cannot be rooted; not an impossibility claim"}
    frame = next(line for line in model.lines if line["id"] == "frame")
    first = frame["spans"][0]["dart"]
    anchors = {first: [1], first ^ 1: [2]}
    initial = dict(anchors)
    units = current_segments(model)
    cliques = small_cliques(neighbor_sets(model))
    outcome = propagate_frontier_relations(model, anchors, cliques)
    phases = [{"anchors_by_dart": dict(anchors), "outcome": outcome}]
    trace = []
    while outcome["status"] == "underdetermined":
        selected = select_level_occurrence(model, units, levels, outcome["domains"])
        side, dart = selected["side"], selected["dart"]
        domain = outcome["domains"][side]
        boundary = effective_boundary(model, outcome["domains"], side)
        if not set(domain) <= set(boundary["local_candidates"]):
            raise AssertionError("propagated candidate contradicts current boundary")
        symbol = min(domain)
        trace.append({**selected, "domain": list(domain), "symbol": symbol,
                      "boundary": boundary,
                      "choice_kind": "greedy-not-a-proved-safe-extension"})
        anchors[dart] = [symbol]
        outcome = propagate_frontier_relations(model, anchors, cliques)
        phases.append({"anchors_by_dart": dict(anchors), "outcome": outcome})
    return {"status": outcome["status"], "policy": POLICY, "domains": outcome["domains"],
            "levels": levels, "unranked_mothers": [], "units": units,
            "initial_anchors_by_dart": initial, "anchors_by_dart": anchors,
            "trace": trace, "choices": len(trace), "backtracks": 0,
            "old_colors_read": False, "local_budget": None,
            "relations": outcome["relations"], "propagation_phases": phases,
            "hall_conflict": outcome["hall_conflict"],
            "colors": [d[0] for d in outcome["domains"]] if outcome["status"] == "solved" else None,
            "scope": "Experimental level-first current-profile scheduling; four is input; no retries."}

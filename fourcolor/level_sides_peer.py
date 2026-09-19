"""Provisional peer scheduling when geometric inheritance has no rooted level.

The user's clarification makes levels descriptive scheduling metadata, not a
prerequisite for naming a valid drawing. Known levels keep the frozen v1 order;
unranked mothers enter a later deterministic peer group. This group is NOT a
proved equal level, so their mathematical level remains None. No new roots,
loop decomposition, recoloring rescue, or alternative-name search is added.
"""

from .closed_support import supported_cycle_units
from .frontier_restart import frontier_priorities, neighbor_sets, small_cliques
from .global_restart import current_segments
from .level_sides import effective_boundary, level_metadata
from .relation_frontier import propagate_frontier_relations
from .whole_lines import build_whole_lines


POLICY = "mother-level-peer-sides-v2"


def peer_mother_order(info):
    """Known generations first; unranked peers use the same numerical geometry.

    Assigning a common scheduling bucket does not assign a fictitious common
    generation. The second key is ignored within the unranked-peer bucket.
    """
    points = tuple(sorted((point[1], point[0]) for point in info["endpoints"]))
    level = info["level"]
    return (1, 0, points) if level is None else (0, level, points)


def select_peer_occurrence(model, units, levels, domains):
    """Select one unfinished mother without making rooted ancestry mandatory.

    Within a mother the frozen v1 local urgency and interval conventions are
    retained. Selection groups describe this provisional scheduler only.
    """
    neighbors = neighbor_sets(model)
    support = supported_cycle_units(model, domains, units)
    rows = [row for row in frontier_priorities(units, domains, neighbors, support, degree=True)
            if row["mother"] != "frame"]
    if not rows:
        raise AssertionError("unresolved side has no internal mother occurrence")
    mother = min({row["mother"] for row in rows},
                 key=lambda name: peer_mother_order(levels[name]))
    eligible = [row for row in rows if row["mother"] == mother]
    best = max(row["priority"] for row in eligible)
    by_id = {unit["id"]: unit for unit in units}
    tied = sorted((row for row in eligible if row["priority"] == best),
                  key=lambda row: (by_id[row["unit"]]["t0"], row["dart"]))
    level = levels[mother]["level"]
    return {**tied[0], "tied_units": [row["unit"] for row in tied],
            "level": level, "parents": levels[mother]["parents"],
            "selection_group": "unranked-peer" if level is None else "rooted"}


def restart_level_peer_names(geometry):
    """One geometry-only attempt; unranked lines do not reject the whole map.

    All current boundary constraints and Hall/pair deductions are unchanged.
    Bridges still have one side twice and introduce no inequality. A conflict
    remains a failure of this greedy commitment path, not map impossibility.
    """
    model = build_whole_lines(geometry)
    levels = level_metadata(model)
    unranked = sorted(name for name, info in levels.items() if info["level"] is None)
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
        selected = select_peer_occurrence(model, units, levels, outcome["domains"])
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
            "levels": levels, "unranked_mothers": unranked, "units": units,
            "initial_anchors_by_dart": initial, "anchors_by_dart": anchors,
            "trace": trace, "choices": len(trace), "backtracks": 0,
            "old_colors_read": False, "local_budget": None,
            "relations": outcome["relations"], "propagation_phases": phases,
            "hall_conflict": outcome["hall_conflict"],
            "colors": [domain[0] for domain in outcome["domains"]]
            if outcome["status"] == "solved" else None,
            "scope": "Provisional rooted-then-unranked-peer scheduling; unknown levels stay None; "
                     "four is input; no retries or invented equal-level theorem."}

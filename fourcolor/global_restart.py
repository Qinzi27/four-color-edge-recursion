"""Rebuild current line priorities and discard ALL previous color commitments.

Qinzi27's restart clarification is different from extending a frozen coloring.
This module takes geometry only; there is no old-color argument or local budget.
The shared-mother variant interprets 'two sides' as two geometric end ports.
It is retained only as an overly strong control after the user's clarification.
The current default uses an established primal loop as a tie preference AFTER
current naming constraints, not a universally proved algorithm.
"""

from .weighted_lines import run_weighted_lines
from .whole_lines import build_whole_lines, propagate_candidates


POLICIES = ("whole-constraints", "segment-constraints", "shared-mother", "closed-support")
POSITION_TOLERANCE = 1e-9


def current_segments(model):
    """Index present junction intervals while retaining each WHOLE mother ID.

    Real T/X contacts split scheduling intervals; harmless degree-two vertices
    do not. The frame keeps its fixed parameter origin as a reading convention.
    Virtual island connectors neither become mothers nor add attachment ports.
    Same-mother means BOTH endpoint contact sets equal the same singleton.
    Merely touching the frame once, or having equal colors, does not qualify.
    This preference applies to internal units only; frame intervals are root
    bookkeeping rather than children of an internal mother (explicit convention).
    """
    units = []
    for mother in model.lines:
        events = mother["events"]

        def endpoint_contacts(t):
            """Include every other mother at this port, not an arbitrary one."""
            if mother["closed"] and abs(t - 1) <= POSITION_TOLERANCE:
                t = 0
            return sorted({port[0] for event in events
                           if abs(event["t"] - t) <= POSITION_TOLERANCE
                           for port in event["ports_ccw"] if port[0] != mother["id"]})

        groups, group = [], []
        for span in mother["spans"]:
            if group and any(abs(span["t0"] - e["t"]) <= POSITION_TOLERANCE for e in events):
                groups.append(group)
                group = []
            group.append(span)
        if group:
            groups.append(group)
        for spans in groups:
            t0, t1 = spans[0]["t0"], spans[-1]["t1"]
            contacts = [endpoint_contacts(t0), endpoint_contacts(t1)]
            same = mother["id"] != "frame" and len(contacts[0]) == 1 and contacts[0] == contacts[1]
            seen, occurrences = set(), []
            for span in spans:
                for dart in (span["dart"], span["dart"] ^ 1):
                    side = model.plane_map.face_of_dart[dart]
                    if side not in seen:
                        seen.add(side)
                        occurrences.append((side, dart))
            units.append({"id": mother["id"] + "@" + format(t0, ".12g") + ":" + format(t1, ".12g"),
                          "mother": mother["id"], "t0": t0, "t1": t1,
                          "endpoint_mothers": contacts, "same_single_mother": bool(same),
                          "frame_endpoint_count": sum("frame" in ids for ids in contacts),
                          "edges": [span["edge"] for span in spans], "occurrences": occurrences})
    if len({unit["id"] for unit in units}) != len(units):
        raise ValueError("current segment IDs collide at the parameter precision")
    return units


def current_priorities(units, domains, shared_first=True, cycle_support=None):
    """Recompute effective bans on DISTINCT still-unresolved shore identities.

    Geometry attachment and named constraints are intentionally separate fields.
    Counting 4-|D| does not count duplicate bans or all possible global logical
    implications. It measures only bans established by the current propagation.
    """
    rows = []
    for unit in units:
        unresolved = [s for s, _ in unit["occurrences"] if len(domains[s]) > 1]
        if not unresolved:
            continue
        constraint_weight = sum(4 - len(domains[s]) for s in unresolved)
        row = {"unit": unit["id"], "mother": unit["mother"],
                     "unresolved_shores": unresolved,
                     "same_single_mother": unit["same_single_mother"],
                     "constraint_weight": constraint_weight,
                     "priority": (int(shared_first and unit["same_single_mother"]), constraint_weight)}
        if cycle_support is not None:
            support = cycle_support[unit["id"]]
            # A shared established loop is only a tie preference AFTER current
            # constraints, not a requirement to fix a same-mother pair first.
            row.update({"priority": (constraint_weight, int(support["supported"])),
                        "closed_support": support})
        rows.append(row)
    return rows


def run_segment_restart(model, shared_first=True, closed_tie=False):
    """One geometry-only restart: one commitment, propagate, then re-prioritize.

    Only the external shore and one incident internal shore are anchored 1/2.
    This fixes a harmless global name permutation, not every inner frame shore.
    Each selected occurrence reuses a used candidate if possible, then the least
    number. No alternate name, order, phase, or previously saved coloring is tried.
    A conflict discards the proposed coloring as a whole; domains are diagnostic.
    """
    frame = next((line for line in model.lines if line["id"] == "frame"), None)
    if frame is None:
        raise ValueError("restart requires an explicit rectangular outer frame")
    first = frame["spans"][0]["dart"]
    anchors = {first: [1], first ^ 1: [2]}
    initial_anchors = dict(anchors)
    units = current_segments(model)
    by_id = {u["id"]: u for u in units}
    outcome = propagate_candidates(model, anchors)
    trace = []
    while outcome["status"] == "underdetermined":
        support = None
        if closed_tie:
            from .closed_support import supported_cycle_units
            support = supported_cycle_units(model, outcome["domains"], units)
        rows = current_priorities(units, outcome["domains"], shared_first, support)
        if not rows:
            raise AssertionError("unresolved shore has no real line occurrence")
        highest = max(row["priority"] for row in rows)
        tied = sorted((r for r in rows if r["priority"] == highest),
                      key=lambda r: (r["mother"], by_id[r["unit"]]["t0"]))
        chosen = tied[0]
        unit = by_id[chosen["unit"]]
        side, dart = next((s, d) for s, d in unit["occurrences"] if len(outcome["domains"][s]) > 1)
        domain = outcome["domains"][side]
        used = {d[0] for d in outcome["domains"] if len(d) == 1}
        symbol = min(domain, key=lambda c: (c not in used, c))
        trace.append({**chosen, "tied_units": [r["unit"] for r in tied],
                      "dart": dart, "side": side, "domain": domain,
                      "used_names": sorted(used), "symbol": symbol})
        anchors[dart] = [symbol]
        outcome = propagate_candidates(model, anchors)
    return {"status": outcome["status"], "domains": outcome["domains"],
            "anchors_by_dart": anchors, "initial_anchors_by_dart": initial_anchors,
            "units": units, "trace": trace, "choices": len(trace), "backtracks": 0,
            "conflict_propagation": outcome["trace"] if outcome["status"] == "conflict" else [],
            "colors": [d[0] for d in outcome["domains"]] if outcome["status"] == "solved" else None,
            "old_colors_read": False, "local_budget": None,
            "scope": "One fresh geometry; no alternative candidate retry; four is the input palette."}


def restart_line_names(geometry, policy="closed-support"):
    """Public API: reconstruct the current mother/interval model from geometry.

    Call this after EACH added line with the entire resulting drawing. In
    particular, do not replay the old insertion order into an incremental
    colorer and call that a global restart. The old policy is an explicit control.
    """
    if policy not in POLICIES:
        raise ValueError("unknown global restart policy")
    model = build_whole_lines(geometry)
    if policy == "whole-constraints":
        result = run_weighted_lines(model, "constraints")
        result.update({"colors": [d[0] for d in result["domains"]] if result["status"] == "solved" else None,
                       "old_colors_read": False, "local_budget": None})
    else:
        result = run_segment_restart(model, shared_first=policy == "shared-mother",
                                     closed_tie=policy == "closed-support")
    result["policy"] = policy
    return result

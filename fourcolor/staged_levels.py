"""Stage-scoped initialization with optional mother-level scheduling.

The frame's historical (1, 2) label is not an immutable color on the final
top-left shore. Start with external 1 only, select ONE frame-adjacent retained
shore at the first eligible complete mother, and normalize that shore to 2.
All subsequent scheduling and Hall/pair filtering are the frozen v2 rules.
No alternate anchor, color, or schedule is tried after a conflict.

This is a geometry-only current-profile algorithm, not a reconstruction of a
unique drawing history. Four remains the supplied palette, not a proved bound.
"""

from .closed_support import supported_cycle_units
from .frontier_restart import neighbor_sets, small_cliques
from .global_restart import current_segments
from .level_sides import effective_boundary, level_metadata
from .level_sides_peer import peer_mother_order, select_peer_occurrence
from .relation_frontier import propagate_frontier_relations
from .whole_lines import build_whole_lines


POLICY = "stage-anchored-level-sides-v3"


def frame_contacts(model):
    """List real, positive-length frame edges incident with each inner shore."""
    frame = next(line for line in model.lines if line["id"] == "frame")
    outside = model.plane_map.face_of_dart[frame["spans"][0]["dart"]]
    contacts = {}
    for span in frame["spans"]:
        left, right = model.plane_map.shores(span["edge"])
        if left == right or outside not in (left, right):
            raise ValueError("frame must separate its external and internal shores")
        side = right if left == outside else left
        contacts.setdefault(side, []).append(span["edge"])
    return {side: sorted(edges) for side, edges in contacts.items()}


def select_initial_retained(model, units, levels, domains):
    """Choose the first retained name from geometry and outside-only domains.

True two-ended frame contact is necessary for the through-mother case. A
candidate also needs a nonbridge interval with a shore sharing a REAL frame
edge: mere point contact cannot justify exclusion of external color 1.
Within the chosen mother, use the previous local urgency keys, restricting
only the candidate shore occurrences. Compute q over all unresolved shores.

If no such through mother exists, use the conventional first inner frame
shore. This declared geometry case handles empty frames, islands, bridges and
bent cuts; it is not a retry after a failed coloring or a claim of rooted depth.
"""
    contact_edges = frame_contacts(model)
    adjacent = neighbor_sets(model)
    supports = supported_cycle_units(model, domains, units)
    eligible_units = [unit for unit in units if unit["mother"] != "frame"
                      and all("frame" in port for port in
                              levels[unit["mother"]]["endpoint_contacts"])
                      and len(unit["occurrences"]) > 1
                      and any(side in contact_edges and len(domains[side]) > 1
                              for side, _ in unit["occurrences"])]
    mothers = sorted({u["mother"] for u in eligible_units},
                     key=lambda name: (peer_mother_order(levels[name]), name))

    def row_for(unit, candidates):
        """Retain v2 occurrence order on ties, then the v2 interval tie key."""
        def score(side):
            """Use only current domains, never stored colors or solver trials."""
            return (4 - len(domains[side]),
                    sum(len(domains[n]) > 1 for n in adjacent[side]))
        side, dart = max(candidates, key=lambda pair: score(pair[0]))
        unresolved = [s for s, _ in unit["occurrences"] if len(domains[s]) > 1]
        q = sum(4 - len(domains[s]) for s in unresolved)
        level = levels[unit["mother"]]["level"]
        return {"unit": unit["id"], "mother": unit["mother"], "side": side,
                "dart": dart, "unresolved_shores": unresolved,
                "urgency": score(side)[0], "unresolved_neighbors": score(side)[1],
                "constraint_weight": q,
                "including_named_weight": sum(4 - len(domains[s]) for s, _ in unit["occurrences"]),
                "closed_support": supports[unit["id"]],
                "priority": score(side) + (q, int(supports[unit["id"]]["supported"])),
                "level": level, "parents": levels[unit["mother"]]["parents"],
                "selection_group": "initial-retained",
                "frame_boundary_edges": contact_edges[side]}

    if mothers:
        mother = mothers[0]
        rows = [row_for(unit, [(side, dart) for side, dart in unit["occurrences"]
                              if side in contact_edges and len(domains[side]) > 1])
                for unit in eligible_units if unit["mother"] == mother]
        highest = max(row["priority"] for row in rows)
        by_id = {unit["id"]: unit for unit in units}
        ties = sorted((row for row in rows if row["priority"] == highest),
                      key=lambda row: (by_id[row["unit"]]["t0"], row["dart"]))
        selected = {**ties[0], "tied_units": [row["unit"] for row in ties]}
        mode = "first-through-mother-retained-side"
    else:
        frame = next(line for line in model.lines if line["id"] == "frame")
        dart = frame["spans"][0]["dart"] ^ 1
        side = model.plane_map.face_of_dart[dart]
        unit = next(unit for unit in units if unit["mother"] == "frame"
                    and dart // 2 in unit["edges"])
        selected = {**row_for(unit, [(side, dart)]), "tied_units": [unit["id"]]}
        mode = "frame-interior-no-eligible-through-mother"
    return selected, {"mode": mode, "eligible_mothers": mothers,
                      "mother": selected["mother"], "side": selected["side"],
                      "dart": selected["dart"],
                      "frame_boundary_edges": list(selected["frame_boundary_edges"]),
                      "domain_before": list(domains[selected["side"]]),
                      "symbol": 2, "historical_frame_pair": [1, 2],
                      "coarse_split_pair_unordered": [2, 3] if mothers else None,
                      "birth_pair_is_not_a_final_profile_constraint": True}


def restart_staged_level_names(geometry):
    """Run exactly one deterministic initialization and coloring attempt.

Only one inner 2 is introduced at initialization. Since it shares a frame
edge, outside-only symmetry leaves its domain exactly {2,3,4}. Choosing 2
normalizes interchangeable unused names; later greedy choices do not inherit
this general safety claim. Intermediate T/X contacts never truncate a mother.
"""
    model = build_whole_lines(geometry)
    levels = level_metadata(model)
    units = current_segments(model)
    frame = next(line for line in model.lines if line["id"] == "frame")
    first = frame["spans"][0]["dart"]
    anchors = {first: [1]}
    initial = dict(anchors)
    cliques = small_cliques(neighbor_sets(model))
    outcome = propagate_frontier_relations(model, anchors, cliques)
    phases = [{"anchors_by_dart": dict(anchors), "outcome": outcome}]
    if outcome["status"] != "underdetermined":
        raise AssertionError("valid framed map must admit outside-only normalization")
    selected, initialization = select_initial_retained(model, units, levels, outcome["domains"])
    initialization.update(outside_dart=first,
                          outside_side=model.plane_map.face_of_dart[first],
                          prebound_final_inner_anchor=False)
    trace = []
    while outcome["status"] == "underdetermined":
        is_initial = not trace
        if not is_initial:
            selected = select_peer_occurrence(model, units, levels, outcome["domains"])
        side, dart = selected["side"], selected["dart"]
        domain = outcome["domains"][side]
        if is_initial and domain != [2, 3, 4]:
            raise AssertionError("initial retained shore lost unused-name symmetry")
        boundary = effective_boundary(model, outcome["domains"], side)
        if not set(domain) <= set(boundary["local_candidates"]):
            raise AssertionError("propagated candidate contradicts current boundary")
        symbol = min(domain)
        trace.append({**selected, "domain": list(domain), "symbol": symbol,
                      "boundary": boundary,
                      "choice_kind": "initial-retained-name" if is_initial else
                                     "greedy-not-a-proved-safe-extension"})
        anchors[dart] = [symbol]
        outcome = propagate_frontier_relations(model, anchors, cliques)
        phases.append({"anchors_by_dart": dict(anchors), "outcome": outcome})
    return {"status": outcome["status"], "policy": POLICY, "domains": outcome["domains"],
            "levels": levels, "unranked_mothers": sorted(
                name for name, info in levels.items() if info["level"] is None),
            "units": units, "initialization": initialization,
            "initial_anchors_by_dart": initial, "anchors_by_dart": anchors,
            "trace": trace, "choices": len(trace), "backtracks": 0,
            "old_colors_read": False, "local_budget": None,
            "relations": outcome["relations"], "propagation_phases": phases,
            "hall_conflict": outcome["hall_conflict"],
            "colors": [domain[0] for domain in outcome["domains"]]
            if outcome["status"] == "solved" else None,
            "scope": "Geometry-only stage-scoped inner normalization plus frozen optional "
                     "mother-level scheduling; four is input; no retries or old colors. "
                     "No claim that historical coarse profiles are replayed uniquely."}

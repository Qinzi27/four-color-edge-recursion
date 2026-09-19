"""Activate mother peers together; postpone unfinished coarse-side commitments.

Qinzi27's peer-batch clarification is stronger than sorting whole mothers by
level. Erasing not-yet-active separators groups final sides into coarse cells.
Only singleton cells receive subsequent greedy names. The sole early naming
exception is the previously proved exterior-preserving normalization to 2.
No colors are imposed equally on all descendants of an unfinished coarse cell.
This supplies a deterministic scheduler, NOT a general four-color algorithm.
"""

from .closed_support import supported_cycle_units
from .frontier_restart import neighbor_sets, small_cliques
from .global_restart import current_segments
from .level_sides import effective_boundary, level_metadata
from .level_sides_peer import peer_mother_order
from .relation_frontier import propagate_frontier_relations
from .staged_levels import select_initial_retained
from .whole_lines import build_whole_lines


POLICY = "peer-batch-ready-sides-v4"


def build_batch_geometry(model, levels):
    """Build the coarse-to-fine partition from geometry alone.

    Equal known levels activate simultaneously. Unknown levels remain None in
    the ancestry metadata, but share one final scheduling bucket. Merging over
    inactive edges is done in the FINAL dual adjacency; the removed edges are
    primal separators. Bridges/virtual connectors cannot merge distinct sides.

    A final side is a singleton coarse cell exactly when all its nonbridge
    boundary edges are active. Its ready stage is therefore their maximum.
    """
    known = [info["level"] for info in levels.values() if info["level"] is not None]
    unranked = max(known) + 1 if any(info["level"] is None for info in levels.values()) else None
    activation = {name: info["level"] if info["level"] is not None else unranked
                  for name, info in levels.items()}
    size = len(model.plane_map.faces)
    ready = [1] * size
    separators = []
    for edge, mother in model.edge_owner.items():
        first, second = model.plane_map.shores(edge)
        if first == second:
            continue
        stage = activation[mother]
        ready[first] = max(ready[first], stage)
        ready[second] = max(ready[second], stage)
        separators.append((first, second, stage))
    stages, previously_ready = [], set()
    for stage in sorted(set(activation.values())):
        parent = list(range(size))

        def root(side):
            """Compress geometric equivalence only, never candidate colors."""
            while parent[side] != side:
                parent[side] = parent[parent[side]]
                side = parent[side]
            return side

        for first, second, born in separators:
            if born > stage:
                a, b = root(first), root(second)
                parent[max(a, b)] = min(a, b)
        cells = {}
        for side in range(size):
            cells.setdefault(root(side), []).append(side)
        coarse = sorted(cells.values())
        complete = sorted(cell[0] for cell in coarse if len(cell) == 1)
        if complete != [side for side, born in enumerate(ready) if born <= stage]:
            raise AssertionError("boundary-readiness and erased-edge partition disagree")
        stages.append({"stage": stage,
                       "new_mothers": sorted(name for name, born in activation.items() if born == stage),
                       "active_mothers": sorted(name for name, born in activation.items() if born <= stage),
                       "coarse_cells": coarse, "ready_sides": complete,
                       "newly_ready_sides": sorted(set(complete) - previously_ready)})
        previously_ready = set(complete)
    return {"mother_stages": activation, "unranked_stage": unranked,
            "stages": stages, "side_ready_stage": ready}


def select_ready_occurrence(model, units, levels, batch_geometry, domains):
    """Apply the batch gate BEFORE per-unit urgency and whole-mother ties.

    The gate uses only fixed geometry and which domains remain unresolved.
    q keeps its old definition over ALL unresolved occurrences in the unit,
    including a deeper side which is not itself eligible for commitment yet.
    The complete final-map Hall/pair constraints are never hidden by the gate.
    """
    ready = batch_geometry["side_ready_stage"]
    active = min(ready[side] for side, values in enumerate(domains) if len(values) > 1)
    eligible = {side for side, values in enumerate(domains) if len(values) > 1 and ready[side] == active}
    neighbors = neighbor_sets(model)
    supports = supported_cycle_units(model, domains, units)
    rows = []
    for unit in units:
        if unit["mother"] == "frame":
            continue
        candidates = [(side, dart) for side, dart in unit["occurrences"] if side in eligible]
        if not candidates:
            continue

        def individual(side):
            """Count distinct still-unresolved neighbors, not endpoint ports."""
            return 4 - len(domains[side]), sum(len(domains[n]) > 1 for n in neighbors[side])

        side, dart = max(candidates, key=lambda item: individual(item[0]))
        unknown = [s for s, _ in unit["occurrences"] if len(domains[s]) > 1]
        q = sum(4 - len(domains[s]) for s in unknown)
        support = supports[unit["id"]]
        rows.append({"unit": unit["id"], "mother": unit["mother"], "side": side, "dart": dart,
                     "unresolved_shores": unknown, "urgency": individual(side)[0],
                     "unresolved_neighbors": individual(side)[1], "constraint_weight": q,
                     "including_named_weight": sum(4 - len(domains[s]) for s, _ in unit["occurrences"]),
                     "closed_support": support, "priority": individual(side) + (q, int(support["supported"])),
                     "ready_stage": ready[side], "active_stage": active,
                     "eligible_side_ids": sorted(eligible), "coarse_cell": [side]})
    if not rows:
        raise AssertionError("an unresolved ready side has no internal mother occurrence")
    mother = min({row["mother"] for row in rows}, key=lambda name: (peer_mother_order(levels[name]), name))
    same_mother = [row for row in rows if row["mother"] == mother]
    highest = max(row["priority"] for row in same_mother)
    by_id = {unit["id"]: unit for unit in units}
    tied = sorted((row for row in same_mother if row["priority"] == highest),
                  key=lambda row: (by_id[row["unit"]]["t0"], row["dart"]))
    return {**tied[0], "tied_units": [row["unit"] for row in tied],
            "level": levels[mother]["level"], "parents": levels[mother]["parents"],
            "selection_group": "unranked-peer" if levels[mother]["level"] is None else "rooted"}


def restart_peer_batch_names(geometry):
    """Run one deterministic attempt with one safe early normalization.

    Retain v3's initialization unchanged to isolate batch scheduling. Its one
    retained side can be deeper than stage 2; this is explicitly a naming-gauge
    choice justified by global permutation, not a completed coarse coloring.
    Every later active choice respects the minimum unresolved ready stage.
    """
    model = build_whole_lines(geometry)
    levels = level_metadata(model)
    units = current_segments(model)
    batch_geometry = build_batch_geometry(model, levels)
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
    initialization.update(outside_dart=first, outside_side=model.plane_map.face_of_dart[first],
                          prebound_final_inner_anchor=False)
    trace = []
    while outcome["status"] == "underdetermined":
        is_initial = not trace
        if not is_initial:
            selected = select_ready_occurrence(model, units, levels, batch_geometry, outcome["domains"])
        side, dart = selected["side"], selected["dart"]
        domain = outcome["domains"][side]
        if is_initial and domain != [2, 3, 4]:
            raise AssertionError("initial retained shore lost unused-name symmetry")
        boundary = effective_boundary(model, outcome["domains"], side)
        if not set(domain) <= set(boundary["local_candidates"]):
            raise AssertionError("propagated candidate contradicts current boundary")
        symbol = min(domain)
        trace.append({**selected, "domain": list(domain), "symbol": symbol, "boundary": boundary,
                      "choice_kind": "initial-retained-name" if is_initial else
                                     "greedy-not-a-proved-safe-extension"})
        anchors[dart] = [symbol]
        outcome = propagate_frontier_relations(model, anchors, cliques)
        phases.append({"anchors_by_dart": dict(anchors), "outcome": outcome})
    return {"status": outcome["status"], "policy": POLICY, "domains": outcome["domains"],
            "levels": levels, "unranked_mothers": sorted(name for name, info in levels.items()
                                                         if info["level"] is None),
            "units": units, "batch_geometry": batch_geometry, "initialization": initialization,
            "initial_anchors_by_dart": initial, "anchors_by_dart": anchors,
            "trace": trace, "choices": len(trace), "backtracks": 0, "old_colors_read": False,
            "local_budget": None, "relations": outcome["relations"], "propagation_phases": phases,
            "hall_conflict": outcome["hall_conflict"],
            "colors": [values[0] for values in outcome["domains"]] if outcome["status"] == "solved" else None,
            "scope": "Geometry-only equal-level activation, singleton coarse-cell readiness, "
                     "and one prior safe normalization. No coarse-descendant equality constraints, "
                     "old colors, probes, retries or backtracking. Four remains an input palette."}

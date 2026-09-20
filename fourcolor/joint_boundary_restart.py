"""Separate v4 scheduling experiment with certified local boundary filtering.

The original peer_batches module stays frozen. Only propagation changes here:
Hall and path consistency alternate with an explicit local conditional filter.
No candidate is committed by the local checks, and no whole-map solver or old
coloring supplies an answer. A surviving greedy choice can still be unsafe.
"""

from .frontier_restart import neighbor_sets, propagate_hall, small_cliques
from .global_restart import current_segments
from .joint_boundary import filter_boundary_books, find_boundary_books
from .level_sides import effective_boundary, level_metadata
from .peer_batches import build_batch_geometry, select_ready_occurrence
from .relation_names import _domains, initial_relations, relation_closure
from .staged_levels import select_initial_retained
from .whole_lines import build_whole_lines


def propagate_joint_boundary(model, anchors, cliques=None, books=None, mode="joint"):
    """Preserve all completions while reaching a joint shrinking fixed point.

    Conditional cases concern at most one adjacent internal pair and its common
    neighbors. They are explicit local probes, not a no-probing v4 algorithm.
    Pair correlations survive subsequent Hall rounds. Every continued round
    deletes a domain value or relation bit, so the iteration terminates.
    """
    if mode not in ("domains", "joint"):
        raise ValueError("mode must be domains or joint")
    cliques = small_cliques(neighbor_sets(model)) if cliques is None else cliques
    certified_books = find_boundary_books(model)
    if books is not None and books != certified_books:
        raise ValueError("book cache must match actual geometric shared edges")
    books = certified_books
    work_anchors = {dart: list(values) for dart, values in anchors.items()}
    relations = None
    phases, revisions, statistics = [], 0, {}
    while True:
        hall = propagate_hall(model, work_anchors, cliques)
        permitted = initial_relations(model, hall["domains"])
        relations = permitted if relations is None else [
            [old & allowed for old, allowed in zip(row, bounds)]
            for row, bounds in zip(relations, permitted)]
        relation_input = relations
        filtered = ({"relations": relations, "trace": [], "revisions": 0,
                     "conflict": True} if hall["status"] == "conflict"
                    else relation_closure(relations))
        revisions += filtered["revisions"]
        relations = filtered["relations"]
        joint = None if filtered["conflict"] else filter_boundary_books(relations, books, mode=mode)
        if joint is not None:
            relations = joint["relations"]
            for key, value in joint["statistics"].items():
                statistics[key] = statistics.get(key, 0) + value
        phases.append({"hall_input_anchors": work_anchors,
                       "hall_status": hall["status"], "hall_domains": hall["domains"],
                       "hall_trace": hall["trace"], "hall_conflict": hall.get("hall_conflict"),
                       "relation_input": relation_input, "relation_trace": filtered["trace"],
                       "relation_conflict": filtered["conflict"], "boundary_filter": joint})
        domains = _domains(relations)
        if filtered["conflict"] or joint["conflict"]:
            status = "conflict"
            break
        if not joint["changed"] and domains == hall["domains"]:
            status = "solved" if all(len(d) == 1 for d in domains) else "underdetermined"
            break
        work_anchors = {face[0]: list(domain)
                        for face, domain in zip(model.plane_map.faces, domains)}
    return {"status": status, "domains": domains, "relations": relations,
            "phases": phases, "revisions": revisions, "statistics": statistics,
            "books": books, "mode": mode, "hall_conflict": hall.get("hall_conflict"),
            "backtracks": 0, "choices": 0, "palette": [1, 2, 3, 4]}


def restart_joint_boundary_names(geometry, mode="joint"):
    """Keep v4's initialization, selector and min(domain); change only filtering.

    Both ablation modes run from geometry alone. Stronger propagation can change
    subsequent priorities; this does not promise fewer conflicts on every map.
    Full transcripts retain every permanent choice and every local probe.
    """
    model = build_whole_lines(geometry)
    levels = level_metadata(model)
    units = current_segments(model)
    batch_geometry = build_batch_geometry(model, levels)
    books = find_boundary_books(model)
    frame = next(line for line in model.lines if line["id"] == "frame")
    first = frame["spans"][0]["dart"]
    anchors, initial = {first: [1]}, {first: [1]}
    cliques = small_cliques(neighbor_sets(model))
    outcome = propagate_joint_boundary(model, anchors, cliques, books, mode)
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
        outcome = propagate_joint_boundary(model, anchors, cliques, books, mode)
        phases.append({"anchors_by_dart": dict(anchors), "outcome": outcome})
    statistics = {}
    for phase in phases:
        for key, value in phase["outcome"]["statistics"].items():
            statistics[key] = statistics.get(key, 0) + value
    return {"status": outcome["status"], "policy": "peer-batch-boundary-" + mode + "-pilot",
            "mode": mode, "domains": outcome["domains"], "statistics": statistics,
            "levels": levels, "unranked_mothers": sorted(name for name, info in levels.items()
                                                         if info["level"] is None),
            "units": units, "batch_geometry": batch_geometry, "initialization": initialization,
            "initial_anchors_by_dart": initial, "anchors_by_dart": anchors,
            "trace": trace, "choices": len(trace), "backtracks": 0, "old_colors_read": False,
            "local_budget": "at most 12 internal color pairs per book per sweep" if mode == "joint" else
                            "six two-color palettes per book per sweep",
            "relations": outcome["relations"], "propagation_phases": phases,
            "hall_conflict": outcome["hall_conflict"],
            "colors": [values[0] for values in outcome["domains"]] if outcome["status"] == "solved" else None,
            "scope": "Frozen v4 scheduling plus local boundary filtering; explicit local conditional "
                     "cases in joint mode, no whole-map color enumeration, retries or backtracking. "
                     "This is a bounded pilot, not a complete four-coloring algorithm."}

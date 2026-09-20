"""Controlled reuse of earlier initialization, scheduling and proved relations.

This experiment never changes the frozen v2/v3/v4 implementations. The three
switches are selected before a run, not after a failure. A coloring is never
borrowed from another strategy. Template matching enumerates face identities,
not trial color assignments; each conclusion has its original geometric proof.
"""

from .frontier_restart import neighbor_sets, propagate_hall, small_cliques
from .global_restart import current_segments
from .implicit_inequality import verify_implicit_inequality
from .level_sides import effective_boundary, level_metadata
from .level_sides_peer import select_peer_occurrence
from .peer_batches import build_batch_geometry, select_ready_occurrence
from .prior_rule_reuse import certified_pair_relations, intersect_certified_relations
from .relation_names import _domains, initial_relations, relation_closure
from .staged_levels import select_initial_retained
from .whole_lines import build_whole_lines


def propagate_prior_operations(model, anchors, cliques, certificates):
    """Run the original Hall/pair closure with fixed proved inequalities added.

    Required certificates must already have been checked against the geometry
    by the caller. They constrain existing name pairs; neither Hall cliques nor
    the drawn adjacency are changed. Existing correlations survive Hall rounds.
    """
    work_anchors = {dart: list(values) for dart, values in anchors.items()}
    relations, phases, revisions, removed = None, [], 0, 0
    while True:
        hall = propagate_hall(model, work_anchors, cliques)
        permitted = initial_relations(model, hall["domains"])
        before = permitted if relations is None else [
            [old & allowed for old, allowed in zip(row, bounds)]
            for row, bounds in zip(relations, permitted)]
        implicit = intersect_certified_relations(before, certificates)
        relations = implicit["relations"]
        removed += sum((event["before"] ^ event["after"]).bit_count() * 2
                       for event in implicit["trace"])
        filtered = ({"relations": relations, "trace": [], "revisions": 0,
                     "conflict": True} if hall["status"] == "conflict" or implicit["conflict"]
                    else relation_closure(relations))
        phases.append({"hall_input_anchors": work_anchors,
                       "hall_status": hall["status"], "hall_domains": hall["domains"],
                       "hall_trace": hall["trace"], "hall_conflict": hall.get("hall_conflict"),
                       "pre_implicit_relations": before, "implicit_filter": implicit,
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
        work_anchors = {face[0]: list(domain)
                        for face, domain in zip(model.plane_map.faces, domains)}
    return {"status": status, "domains": domains, "relations": relations,
            "phases": phases, "revisions": revisions,
            "statistics": {"template_relation_bits_removed": removed},
            "implicit_certificates": certificates, "hall_conflict": hall.get("hall_conflict"),
            "backtracks": 0, "choices": 0, "palette": [1, 2, 3, 4]}


def restart_prior_operation_names(geometry, initialization="retained", schedule="ready",
                                  implicit=False, certificates=None):
    """Run one declared member of the 2 x 2 x 2 comparison, without fallback.

    frame/peer/plain reproduces v2; retained/peer/plain reproduces v3;
    retained/ready/plain reproduces v4. A supplied certificate cache avoids
    repeating structural matching; every certificate is still verified here.
    The comparison runner separately checks that its cache is the complete
    deterministic finder output, rather than a hand-selected favorable subset.
    """
    if initialization not in ("frame", "retained") or schedule not in ("peer", "ready"):
        raise ValueError("unknown initialization or schedule")
    if type(implicit) is not bool:
        raise ValueError("implicit must be a boolean")
    if not implicit:
        if certificates:
            raise ValueError("plain mode cannot accept additional inequalities")
        certificates = []
    elif certificates is None:
        certificates = certified_pair_relations(geometry)
    else:
        certificates = list(certificates)
    for certificate in certificates:
        verify_implicit_inequality(geometry, certificate)
    model = build_whole_lines(geometry)
    levels, units = level_metadata(model), current_segments(model)
    batch = build_batch_geometry(model, levels)
    frame = next(line for line in model.lines if line["id"] == "frame")
    first = frame["spans"][0]["dart"]
    anchors = {first: [1]}
    if initialization == "frame":
        anchors[first ^ 1] = [2]
    initial = dict(anchors)
    cliques = small_cliques(neighbor_sets(model))
    outcome = propagate_prior_operations(model, anchors, cliques, certificates)
    phases = [{"anchors_by_dart": dict(anchors), "outcome": outcome}]
    initialization_record = None
    if initialization == "retained":
        if outcome["status"] != "underdetermined":
            raise AssertionError("valid framed map must admit outside-only normalization")
        selected, initialization_record = select_initial_retained(model, units, levels, outcome["domains"])
        initialization_record.update(outside_dart=first,
                                     outside_side=model.plane_map.face_of_dart[first],
                                     prebound_final_inner_anchor=False)
    trace = []
    while outcome["status"] == "underdetermined":
        first_retained = initialization == "retained" and not trace
        if not first_retained:
            selected = (select_peer_occurrence(model, units, levels, outcome["domains"])
                        if schedule == "peer" else
                        select_ready_occurrence(model, units, levels, batch, outcome["domains"]))
        side, dart = selected["side"], selected["dart"]
        domain = outcome["domains"][side]
        if first_retained and domain != [2, 3, 4]:
            raise AssertionError("first retained side lost unused-name symmetry")
        boundary = effective_boundary(model, outcome["domains"], side)
        if not set(domain) <= set(boundary["local_candidates"]):
            raise AssertionError("propagated candidate contradicts current boundary")
        symbol = min(domain)
        trace.append({**selected, "domain": list(domain), "symbol": symbol, "boundary": boundary,
                      "choice_kind": "initial-retained-name" if first_retained else
                                     "greedy-not-a-proved-safe-extension"})
        anchors[dart] = [symbol]
        outcome = propagate_prior_operations(model, anchors, cliques, certificates)
        phases.append({"anchors_by_dart": dict(anchors), "outcome": outcome})
    mode = "implicit" if implicit else "plain"
    return {"status": outcome["status"],
            "policy": f"prior-operations-{initialization}-{schedule}-{mode}",
            "initialization_mode": initialization, "schedule": schedule, "implicit": implicit,
            "domains": outcome["domains"], "relations": outcome["relations"],
            "levels": levels, "units": units, "batch_geometry": batch,
            "unranked_mothers": sorted(name for name, info in levels.items() if info["level"] is None),
            "initialization": initialization_record, "initial_anchors_by_dart": initial,
            "anchors_by_dart": anchors, "trace": trace, "choices": len(trace),
            "propagation_phases": phases, "implicit_certificates": certificates,
            "statistics": {"template_relation_bits_removed": sum(
                phase["outcome"]["statistics"]["template_relation_bits_removed"] for phase in phases)},
            "hall_conflict": outcome["hall_conflict"], "backtracks": 0,
            "old_colors_read": False, "local_budget": None,
            "colors": [domain[0] for domain in outcome["domains"]] if outcome["status"] == "solved" else None,
            "scope": "One preselected combination of historical operations and geometry-certified "
                     "inequalities; no color probes, whole-map solver, retries or selected old answer. "
                     "Success on diagnostics is not a full-corpus or universal guarantee."}

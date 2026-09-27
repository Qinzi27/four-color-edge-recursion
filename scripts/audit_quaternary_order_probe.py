"""Describe a completed guarded run without selecting colors or querying an oracle.

The independent low-color audit is an input, not an internal solver. This layer
binds its event and raw-constraint references before joining exact extension
statuses to structural risk patterns. Shared frozen scanner helpers are report
code only. A geometric role is a current global face, never a claim that an old
region retains its identity after a new segment has split it.
"""

from collections import Counter
from copy import deepcopy

from fourcolor.global_restart import current_segments
from fourcolor.level_sides import level_metadata
from fourcolor.whole_lines import build_whole_lines
from scripts.audit_quaternary_low_color import _selection
from scripts.scan_low_color_obstruction_states import (
    digest, persistent_phases, raw_graph, require, scan_run, triangle_bipyramids,
)


DIAGNOSTIC_VERSION = "quaternary-order-posthoc-v1"
EXTENSIONS = ("safe", "unsafe", "unknown", "preexisting_unsat")


def check_saved_schedule(document, result, geometry, resources):
    """Recheck saved choices with frozen scheduler helpers and no color search.

    This is a shared-code check of the declared scheduling convention, not an
    independent mathematical safety oracle. The caller separately replays the
    relation traces and verifies exact certificates. ``geometry=None`` supports
    old abstract fixtures; actual geometry runs must supply their saved geometry.
    """
    require(digest(result["original_input"]) == digest(document), "schedule original input differs")
    require(type(result["schema_version"]) is int and result["schema_version"] == 1
            and result["policy"] == "quaternary-low-color-conditional-propagation-v1",
            "saved producer schema/policy differs")
    require(result["probe"] is True and result["oracle_feedback_to_producer"] is False
            and result["old_colors_read"] is False and type(result["backtracks"]) is int
            and result["backtracks"] == 0, "saved producer mode contract differs")
    for name in ("decision_limit", "probe_limit"):
        require(type(result[name]) is int and result[name] >= 0
                and type(resources[name]) is int and result[name] == resources[name],
                "saved producer resource limit differs: " + name)
    expected_schedule = ("mother-peer-with-frame-only-fallback-v1" if geometry is not None
                         else "first-unresolved-input-order-v1")
    require(result["schedule"] == expected_schedule, "saved schedule label differs")
    sides, edges = _edges(document)
    context = None
    if geometry is not None:
        raw_sides, raw_edges, raw_lines = raw_graph(geometry)
        require(sides == raw_sides and edges == raw_edges, "saved schedule geometry identities differ")
        require(digest(sorted(document["lines"], key=lambda row: row["id"]))
                == digest(sorted(raw_lines, key=lambda row: row["id"])),
                "saved schedule physical contacts differ")
        model = build_whole_lines(geometry)
        require(sides == [f"S{i}" for i in range(len(model.plane_map.faces))],
                "saved schedule model face order differs")
        context = model, current_segments(model), level_metadata(model)
    persistent_phases(result)
    choices, probes, rejects = 0, 0, 0
    for event in result["events"]:
        require(choices < resources["decision_limit"] and probes < resources["probe_limit"],
                "saved event after resource exhaustion")
        before = result["phases"][event["before_phase"]]["outcome"]
        require(before["status"] == "underdetermined" and before["side_order"] == sides,
                "saved selection after terminal phase or different side order")
        selected, expected = _selection(sides, before["domains"], context)
        candidates = before["domains"][selected]
        expected.update(side_id=sides[selected], candidate_order=candidates)
        require(digest(event["selection"]) == digest(expected), "saved scheduler metadata differs")
        require(event["side"] == sides[selected] and type(event["symbol"]) is int
                and len(candidates) > 1 and event["symbol"] == min(candidates)
                and event["candidates_before"] == candidates, "saved low-color selection differs")
        probes += 1
        if event["kind"] == "commit":
            choices += 1
        else:
            rejects += 1
    for name, actual in (("choices", choices), ("probes", probes), ("rejections", rejects)):
        require(type(result[name]) is int and result[name] == actual, "saved schedule telemetry differs")
    final = result["phases"][result["final_phase"]]["outcome"]
    if final["status"] == "underdetermined":
        require(choices == resources["decision_limit"] or probes == resources["probe_limit"],
                "saved run stopped before declared resource limit")
        reason = "decision-limit-exhausted" if choices == resources["decision_limit"] else "probe-limit-exhausted"
        require(result["status"] == "incomplete" and result["reason"] == reason,
                "saved resource stop mislabeled")
    else:
        require(final["status"] in ("solved", "conflict") and result["status"] == final["status"],
                "saved terminal status differs")
        reason = ("complete-coloring-verified" if final["status"] == "solved"
                  else "propagation-conflict-under-current-commitments")
        require(result["reason"] == reason, "saved terminal reason differs")
    return {"passed": True, "schedule": expected_schedule, "events_checked": len(result["events"]),
            "producer_rerun": False, "oracle_search_rerun": False,
            "scope": "Frozen scheduler helpers check scheduling metadata; exact safety is checked separately."}


def _edges(document):
    """Read true NEQ contacts without interpreting a displayed color label."""
    sides = document["sides"]
    require(isinstance(sides, list) and len(set(sides)) == len(sides), "invalid side identities")
    index = {side: i for i, side in enumerate(sides)}
    edges = set()
    for line in document["lines"]:
        require(line["left"] in index and line["right"] in index, "unknown contact side")
        a, b = index[line["left"]], index[line["right"]]
        require(line["kind"] in ("separator", "bridge"), "unknown contact kind")
        require((a == b) == (line["kind"] == "bridge"), "bridge/separator identity differs")
        if a != b:
            edges.add(tuple(sorted((a, b))))
    return sides, sorted(edges)


def _bind_audit(document, result, audit, edges):
    """Bind every exact-status reference to raw edges and actual commitments.

    Certificates and propagation traces have already been verified by the
    supplied auditor. This function checks their references and input binding;
    it does not rerun that verification or promote UNKNOWN to a safe decision.
    """
    require(result["original_input"] == document, "producer original input differs")
    require(audit.get("passed") is True, "a completed passing integrity audit is required")
    require(audit.get("audit_version") == "quaternary-low-color-audit-v1", "unsupported audit version")
    require(audit.get("oracle_feedback_to_producer") is False, "oracle feedback not allowed")
    require(not document.get("states") and not document.get("equal_names"),
            "original supplied domains/EQ unsupported by this exact audit")
    sides = document["sides"]
    index = {side: i for i, side in enumerate(sides)}
    phases, events, steps = result["phases"], result["events"], audit["steps"]
    require(len(steps) == len(events), "audit event count differs")
    require(audit["phase_count"] == len(phases), "audit phase count differs")
    require(len(audit["phase_audits"]) == len(phases), "audit phase evidence count differs")
    require(phases[0]["kind"] == "main" and phases[0]["document"] == document,
            "initial persistent document differs")
    for phase, phase_audit in zip(phases, audit["phase_audits"]):
        require(phase_audit["passed"] is True and phase_audit["status"] == phase["outcome"]["status"]
                and phase_audit["trace_steps_checked"] == len(phase["outcome"]["trace"]),
                "phase audit status/trace count differs")
    records = audit["oracle_records"]
    fixed = {index[side]: color for side, color in document.get("anchors", {}).items()}

    def bound_status(record_index, anchors):
        """Check a reference against precisely the original graph and prefix."""
        require(type(record_index) is int and 0 <= record_index < len(records), "invalid oracle reference")
        record = records[record_index]
        expected = {"n": len(sides), "edges": [list(edge) for edge in edges],
                    "anchors": [list(pair) for pair in sorted(anchors.items())]}
        require(record["input"] == expected, "oracle input does not match original graph and commitments")
        status = record["result"]["status"]
        require(status in ("sat", "unsat", "unknown"), "invalid exact status")
        return status

    initial_status = bound_status(audit["initial_oracle_index"], fixed)
    counts = Counter({name: 0 for name in EXTENSIONS})
    rejects = Counter({"exact_unsat": 0, "unknown": 0})
    first_bad = None
    bound_steps = []
    for number, (event, step) in enumerate(zip(events, steps)):
        require(step["event_index"] == number, "audit event index differs")
        for key in ("kind", "side", "symbol", "before_phase", "trial_phase", "after_phase"):
            require(step[key] == event[key], "audit event field differs: " + key)
        side = index[event["side"]]
        before = phases[event["before_phase"]]["outcome"]
        candidates = before["domains"][side]
        require(event["candidates_before"] == candidates and len(candidates) > 1
                and event["symbol"] == min(candidates), "event minimum/domain binding differs")
        selection = event["selection"]
        require(selection["side"] == side and selection["side_id"] == event["side"]
                and selection["candidate_order"] == candidates, "selection binding differs")
        trial_document = deepcopy(phases[event["before_phase"]]["document"])
        trial_document.setdefault("anchors", {})[event["side"]] = event["symbol"]
        require(phases[event["trial_phase"]]["document"] == trial_document, "trial document binding differs")
        before_status = bound_status(step["before_oracle_index"], fixed)
        proposed = {**fixed, side: event["symbol"]}
        trial_status = bound_status(step["trial_oracle_index"], proposed)
        after_fixed = proposed if event["kind"] == "commit" else fixed
        after_status = bound_status(step["after_oracle_index"], after_fixed)
        require(step["before_status"] == before_status and step["after_status"] == after_status,
                "audit status does not match referenced evidence")
        if event["kind"] == "commit":
            expected_claim = ("complete-witness" if phases[event["after_phase"]]["outcome"]["status"]
                              == "solved" else "inconclusive")
            require(event["extension_claim"] == expected_claim, "commit extension claim differs")
            extension = ("preexisting_unsat" if before_status == "unsat" else
                         "unknown" if "unknown" in (before_status, after_status) else
                         "unsafe" if after_status == "unsat" else "safe")
            counts[extension] += 1
            fixed = proposed
            if extension == "unsafe" and first_bad is None:
                first_bad = number
        else:
            require(event["kind"] == "reject" and trial_status != "sat", "rejected candidate has SAT evidence")
            require(after_status == before_status, "rejection changed exact commitment status")
            after_document = deepcopy(phases[event["before_phase"]]["document"])
            remaining = [color for color in candidates if color != event["symbol"]]
            word = "".join(("2" if len(remaining) == 1 else "1") if color in remaining else "0"
                           for color in (1, 2, 3, 4))
            after_document.setdefault("states", {})[event["side"]] = word
            require(phases[event["after_phase"]]["document"] == after_document,
                    "post-rejection document binding differs")
            require(event["extension_claim"] == "refuted", "rejection claim differs")
            extension = "refuted"
            rejects["exact_unsat" if trial_status == "unsat" else "unknown"] += 1
        require(step["extendibility"] == extension, "audit extension classification differs")
        bound_steps.append({**deepcopy(step), "trial_status": trial_status})
    require(dict(counts) == audit["commitment_counts"], "audit commitment counts differ")
    require(dict(rejects) == audit["rejection_counts"], "audit rejection counts differ")
    require(audit["oracle_unknown"] == sum(row["result"]["status"] == "unknown" for row in records),
            "audit unknown count differs")
    if first_bad is None:
        require(audit["first_bad_commitment"] is None, "spurious first unsafe commitment")
    else:
        saved = audit["first_bad_commitment"]
        require(saved is not None and saved["event_index"] == first_bad
                and saved["event"] == events[first_bad], "first unsafe commitment binding differs")
        step = steps[first_bad]
        require(saved["before"] == records[step["before_oracle_index"]]
                and saved["after"] == records[step["after_oracle_index"]],
                "first unsafe certificates differ")
    return initial_status, bound_steps


def diagnose_order(document, result, audit, *, geometry=None, role_mapping=None):
    """Join a completed guarded run to exact audit statuses and current roles.

    ``role_mapping`` is a direct dictionary such as ``{"A": 5, "E": 2}``.
    Values index ``document['sides']`` even when names are not S0, S1, etc.
    A missing mapping remains unavailable; no lineage is inferred for regions
    split by added strokes. All matches and histograms are retained, untruncated.
    """
    sides, edges = _edges(document)
    require(result["original_input"] == document, "producer original input differs")
    persistent = persistent_phases(result)
    for phase in result["phases"]:
        outcome = phase["outcome"]
        require(outcome["side_order"] == sides and len(outcome["domains"]) == len(sides),
                "phase side identities differ")
        require(all(domain == sorted(set(domain)) and all(type(c) is int and 1 <= c <= 4 for c in domain)
                    for domain in outcome["domains"]), "invalid phase domain")
    geometry_bound = False
    if geometry is not None:
        geometric_sides, geometric_edges, geometric_lines = raw_graph(geometry)
        require(geometric_sides == sides and geometric_edges == edges, "geometry adjacency binding differs")
        require(sorted(document["lines"], key=lambda row: row["id"])
                == sorted(geometric_lines, key=lambda row: row["id"]), "geometry atomic contact binding differs")
        geometry_bound = True
    initial_status, steps = _bind_audit(document, result, audit, edges)
    roles = None if role_mapping is None else deepcopy(role_mapping)
    if roles is not None:
        require(isinstance(roles, dict) and all(isinstance(name, str) and name
                and type(face) is int and 0 <= face < len(sides) for name, face in roles.items()),
                "role mapping must contain current face indices")
        require(len(set(roles.values())) == len(roles), "distinct roles must refer to distinct faces")
    motifs = triangle_bipyramids(len(sides), edges)
    # Each oriented motif contributes at most two matches per persistent phase.
    scanned = scan_run(result, motifs, {}, detail_limit=2 * len(motifs) * len(persistent))
    for matches in scanned["matches"].values():
        for row in matches:
            number = row["next_event"]
            row["exact_step"] = deepcopy(steps[number]) if number is not None else None
            row["structural_match_is_exact_failure"] = bool(number is not None and
                row["selected_now"] and steps[number]["extendibility"] == "unsafe")

    persistent_positions = {phase: position for position, (phase, _) in enumerate(persistent)}
    first_singleton = {} if roles is not None else None
    states = []
    for phase, next_event in persistent:
        outcome = result["phases"][phase]["outcome"]
        domains = ({name: list(outcome["domains"][face]) for name, face in roles.items()}
                   if roles is not None else None)
        if domains is not None:
            for name, domain in domains.items():
                if len(domain) == 1 and name not in first_singleton:
                    first_singleton[name] = phase
        exact_index = (audit["initial_oracle_index"] if phase == 0 else
                       steps[persistent_positions[phase] - 1]["after_oracle_index"])
        states.append({"phase": phase, "next_event": next_event,
                       "phase_kind": result["phases"][phase]["kind"],
                       "propagation_status": outcome["status"], "role_domains": domains,
                       "exact_oracle_index": exact_index,
                       "exact_status": audit["oracle_records"][exact_index]["result"]["status"]})
    if first_singleton is not None:
        first_singleton = {name: first_singleton.get(name) for name in roles}
    e_observed = roles is not None and "E" in roles
    e_first = first_singleton.get("E") if e_observed else None
    e_position = persistent_positions[e_first] if e_first is not None else None
    event_rows, commit_order, before_e = [], [], []
    for number, (event, step) in enumerate(zip(result["events"], steps)):
        selected_roles = ([name for name, face in roles.items() if sides[face] == event["side"]]
                          if roles is not None else None)
        row = {"event_index": number, "event": deepcopy(event), "exact_step": deepcopy(step),
               "selected_roles": selected_roles, "selection": deepcopy(event["selection"]),
               "mother": event["selection"].get("mother"),
               "selection_group": event["selection"].get("selection_group"),
               "selection_reason": event["selection"].get("reason")}
        row["before_first_E_singleton"] = (e_position is None or
            persistent_positions[event["before_phase"]] < e_position) if e_observed else None
        event_rows.append(row)
        if event["kind"] == "commit":
            commit_order.append(deepcopy(row))
            if row["before_first_E_singleton"] and any(name in ("P", "Q", "X", "Y")
                                                       for name in selected_roles or []):
                before_e.append(deepcopy(row))
    return {"schema_version": 1, "diagnostic_version": DIAGNOSTIC_VERSION,
            "input_sha256": digest(document), "result_sha256": digest(result), "audit_sha256": digest(audit),
            "passed": True, "geometry_adjacency_bound": geometry_bound,
            "sides": list(sides), "raw_edges": [list(edge) for edge in edges],
            "role_mapping": roles, "first_singleton_phase": first_singleton,
            "initial_exact_status": initial_status, "persistent_states": states,
            "events": event_rows, "commitment_order": commit_order,
            "K4_commits_before_E_singleton": before_e,
            "E_singleton_observed": e_first is not None if e_observed else None,
            "motifs": motifs, "motif_scan": scanned,
            "exact_commitment_counts": deepcopy(audit["commitment_counts"]),
            "exact_rejection_counts": deepcopy(audit["rejection_counts"]),
            "oracle_unknown": audit["oracle_unknown"],
            "producer_or_oracle_called": False, "oracle_feedback_to_producer": False,
            "scope": {"risk": "Structural matches alone are not exact unsafe commitments.",
                "singleton": "A propagated domain of size one; no displayed representative is used.",
                "before_E": "Commit before-phase precedes E's first persistent singleton; if never observed, all commits qualify.",
                "mapping": "Roles belong only to this current input; no face lineage across split drawings is inferred.",
                "binding": "References and raw inputs are checked here; supplied audit verified traces and exact certificates.",
                "geometry": "Optional raw shores are bound; geometric construction and scheduler helpers are not recomputed here."}}

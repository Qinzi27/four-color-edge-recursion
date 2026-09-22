"""Post-run checks of low-color commitments, with no oracle feedback.

Every propagation trace is replayed by the frozen literal-set auditor. The
exact oracle receives only original physical NEQ edges and explicit initial or
committed colors, never candidate exclusions learned by the tested method.
Original nonempty states/EQ are deliberately rejected in this first experiment.
The geometric scheduler is shared with the producer and is explicitly not an
independent correctness oracle. Soundness and exact extension checks are separate.
"""

from copy import deepcopy
from itertools import product
from math import prod
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.global_restart import current_segments
from fourcolor.level_sides import level_metadata
from fourcolor.level_sides_peer import select_peer_occurrence
from fourcolor.whole_lines import build_whole_lines
from scripts.audit_quaternary_geometry import audit_bounded_contacts, audit_geometry, _same
from scripts.exact_extendibility_oracle import solve_exact, verify_exact_result
from scripts.validate_quaternary_contacts_v2 import expected_state, raw_metadata, require

AUDIT_VERSION = "quaternary-low-color-audit-v1"


def _preserved(outcome, assignments):
    """Check every retained raw solution against unary and ordered-pair output."""
    for values in assignments:
        require(outcome["status"] != "conflict", "propagation lost a raw complete solution")
        for i, a in enumerate(values):
            require(a in outcome["domains"][i], "propagation lost a raw solution color")
            for j, b in enumerate(values):
                require(outcome["relations"][i][j] & (1 << (4 * (a - 1) + b - 1)),
                        "propagation lost a raw solution pair")


def _selection(sides, domains, context):
    """Validate only the documented scheduling convention, with shared helpers."""
    if context is None:
        side = next(i for i, values in enumerate(domains) if len(values) > 1)
        return side, {"side": side, "selection_group": "input-order",
                      "schedule": "first-unresolved-input-order-v1",
                      "reason": "first-unresolved-input-side"}
    model, units, levels = context
    internal = any(unit["mother"] != "frame" and any(len(domains[i]) > 1
                   for i, _ in unit["occurrences"]) for unit in units)
    if internal:
        expected = select_peer_occurrence(model, units, levels, domains)
        expected.update(schedule="mother-peer-with-frame-only-fallback-v1",
                        reason="existing-mother-peer-internal-occurrence")
        return expected["side"], expected
    side = next(i for i, values in enumerate(domains) if len(values) > 1)
    occurrences = [(unit["id"], dart) for unit in units if unit["mother"] == "frame"
                   for face, dart in unit["occurrences"] if face == side]
    require(bool(occurrences), "unresolved geometry side has no frame occurrence")
    unit, dart = occurrences[0]
    return side, {"side": side, "dart": dart, "mother": "frame", "unit": unit,
                  "selection_group": "frame-only-fallback",
                  "schedule": "mother-peer-with-frame-only-fallback-v1",
                  "reason": "no-unresolved-internal-occurrence"}


def audit_low_color(document, result, *, geometry=None, adapted=None,
                    assignment_limit=262144, node_limit=200000):
    """Return independently verified evidence, including unsafe choices as data.

    ``passed`` concerns evidence/trace integrity; ``commitment_counts.unsafe``
    separately counts SAT-to-UNSAT commitments. UNKNOWN never counts as safe.
    Exact certificates are deduplicated in ``oracle_records`` and referenced by
    indices. The first unsafe commitment additionally contains full evidence.
    """
    require(type(assignment_limit) is int and assignment_limit >= 0, "invalid assignment limit")
    require(type(node_limit) is int and node_limit >= 0, "invalid oracle node limit")
    sides, initial_domains, _ = raw_metadata(document)
    require(not document.get("states") and not document.get("equal_names"),
            "low-color audit v1 supports original NEQ and anchors only; states/EQ unsupported")
    require((geometry is None) == (adapted is None), "geometry and adapted must be supplied together")
    index = {side: i for i, side in enumerate(sides)}
    edges = sorted({tuple(sorted((index[line["left"]], index[line["right"]])))
                    for line in document["lines"] if line["kind"] == "separator"})
    geometry_check, context = None, None
    if geometry is not None:
        _same(adapted["contact_document"], document, "adapter contact input")
        geometry_check, actual_edges = audit_geometry(geometry, adapted)
        require(edges == actual_edges, "geometry audit and raw edges disagree")
        model = build_whole_lines(geometry)
        require(sides == ["S" + str(i) for i in range(len(model.plane_map.faces))],
                "geometric schedule requires global ordered side IDs")
        context = model, current_segments(model), level_metadata(model)
    _same(result["original_input"], document, "low-color original input")
    require(type(result["schema_version"]) is int and result["schema_version"] == 1
            and result["policy"] == "quaternary-low-color-conditional-propagation-v1", "wrong producer schema")
    require(result["schedule"] == ("mother-peer-with-frame-only-fallback-v1" if context else
            "first-unresolved-input-order-v1"), "incorrect schedule label")
    require(type(result["probe"]) is bool and type(result["backtracks"]) is int
            and result["backtracks"] == 0 and result["oracle_feedback_to_producer"] is False
            and result["old_colors_read"] is False, "invalid production mode")
    for name in ("decision_limit", "probe_limit"):
        require(type(result[name]) is int and result[name] >= 0, "invalid production resource limit")
    phases, events = result["phases"], result["events"]
    require(isinstance(phases, list) and bool(phases) and isinstance(events, list), "missing phases/events")
    require(phases[0]["kind"] == "main", "initial phase must be persistent")
    _same(phases[0]["document"], document, "initial propagation document")
    phase_audits = [audit_bounded_contacts(phase["document"], phase["outcome"]) for phase in phases]
    size = prod(len(values) for values in initial_domains)
    enumerate_all = size <= assignment_limit
    legal = ([values for values in product(*initial_domains)
              if all(values[a] != values[b] for a, b in edges)] if enumerate_all else None)
    legal_count = len(legal) if enumerate_all else None
    phase_checks, preserved_count = 0, 0
    oracle_records, oracle_cache = [], {}

    def raw_oracle(fixed):
        """Cache ONLY raw graph plus actual commitment signatures, not phase domains."""
        key = tuple(sorted(fixed.items()))
        if key not in oracle_cache:
            evidence = solve_exact(len(sides), edges, fixed, node_limit=node_limit)
            verified = verify_exact_result(len(sides), edges, fixed, evidence)
            oracle_cache[key] = len(oracle_records)
            oracle_records.append({"input": {"n": len(sides), "edges": [list(p) for p in edges],
                                            "anchors": [list(p) for p in key]},
                                   "result": evidence, "verification": verified})
        return oracle_cache[key]

    def check_phase(phase_number, current_legal, oracle_index):
        """Use exhaustive raw solutions and, separately, a raw oracle witness."""
        nonlocal phase_checks, preserved_count
        outcome = phases[phase_number]["outcome"]
        evidence = oracle_records[oracle_index]["result"]
        if enumerate_all:
            _preserved(outcome, current_legal)
            phase_checks += 1
            preserved_count += len(current_legal)
            if evidence["status"] != "unknown":
                require(bool(current_legal) == (evidence["status"] == "sat"),
                        "complete enumeration and raw oracle disagree")
        if evidence["status"] == "sat":
            _preserved(outcome, [evidence["witness"]])

    committed = {index[side]: color for side, color in document.get("anchors", {}).items()}
    initial_oracle = raw_oracle(committed)
    check_phase(0, legal, initial_oracle)
    current_phase, consumed = 0, 1
    choices, probes, rejections = 0, 0, 0
    commitment_counts = {"safe": 0, "unsafe": 0, "unknown": 0, "preexisting_unsat": 0}
    rejection_counts = {"exact_unsat": 0, "unknown": 0}
    steps, first_bad = [], None
    for event_number, event in enumerate(events):
        require(choices < result["decision_limit"], "event after decision limit")
        before_phase = current_phase
        before = phases[before_phase]["outcome"]
        require(before["status"] == "underdetermined", "event after terminal propagation status")
        require(type(event["before_phase"]) is int and event["before_phase"] == before_phase,
                "event does not continue latest persistent phase")
        side, symbol = event["side"], event["symbol"]
        require(side in index and type(symbol) is int, "invalid selected identity or literal")
        selected, expected_selection = _selection(sides, before["domains"], context)
        require(index[side] == selected, "side violates declared schedule")
        candidates = before["domains"][selected]
        require(symbol == min(candidates) and len(candidates) > 1, "choice is not minimum unresolved color")
        _same(event["candidates_before"], candidates, "event candidates")
        selection = event["selection"]
        require(selection["side"] == selected and selection["side_id"] == side,
                "selection identity mismatch")
        _same(selection["candidate_order"], candidates, "selection low-color order")
        expected_selection.update(side_id=side, candidate_order=candidates)
        _same(selection, expected_selection, "scheduler metadata")
        before_oracle = raw_oracle(committed)
        trial_fixed = {**committed, selected: symbol}
        trial_oracle = raw_oracle(trial_fixed)
        trial_legal = [values for values in legal if values[selected] == symbol] if enumerate_all else None
        trial_document = deepcopy(phases[before_phase]["document"])
        trial_document.setdefault("anchors", {})[side] = symbol
        if result["probe"]:
            require(probes < result["probe_limit"], "trial after probe limit")
            require(type(event["trial_phase"]) is int and event["trial_phase"] == consumed,
                    "trial phase omitted, reused, or out of order")
            require(consumed < len(phases) and phases[consumed]["kind"] == "trial", "wrong trial phase kind")
            _same(phases[consumed]["document"], trial_document, "trial assumptions")
            check_phase(consumed, trial_legal, trial_oracle)
            trial_phase = consumed
            consumed += 1
            probes += 1
        else:
            require(event["trial_phase"] is None, "unprobed event has trial")
            trial_phase = None
        kind = event["kind"]
        require(kind in ("reject", "commit"), "unsupported event")
        if kind == "reject":
            require(result["probe"] and phases[trial_phase]["outcome"]["status"] == "conflict",
                    "candidate rejection lacks a proved propagation conflict")
            require(event["extension_claim"] == "refuted", "rejection claim mismatch")
            require(not trial_legal if enumerate_all else True, "rejection removed a raw legal coloring")
            status = oracle_records[trial_oracle]["result"]["status"]
            require(status != "sat", "rejected trial has a complete raw witness")
            rejection_counts["exact_unsat" if status == "unsat" else "unknown"] += 1
            rejections += 1
            after_document = deepcopy(phases[before_phase]["document"])
            remaining = [color for color in candidates if color != symbol]
            after_document.setdefault("states", {})[side] = expected_state(remaining, False)["quaternary"]
            require(consumed < len(phases) and phases[consumed]["kind"] == "main", "missing post-rejection main")
            _same(phases[consumed]["document"], after_document, "post-rejection restrictions")
            current_phase = consumed
            consumed += 1
            after_oracle = before_oracle
            check_phase(current_phase, legal, after_oracle)
            extension = "refuted"
        else:
            choices += 1
            if result["probe"]:
                require(phases[trial_phase]["outcome"]["status"] != "conflict", "conflicting trial was committed")
                current_phase = trial_phase
            else:
                require(consumed < len(phases) and phases[consumed]["kind"] == "main", "missing committed phase")
                _same(phases[consumed]["document"], trial_document, "commitment assumptions")
                current_phase = consumed
                consumed += 1
                check_phase(current_phase, trial_legal, trial_oracle)
            claim = (("complete-witness" if phases[current_phase]["outcome"]["status"] == "solved"
                     else "inconclusive") if result["probe"] else "unchecked")
            require(event["extension_claim"] == claim, "commitment overstates extension evidence")
            committed, legal = trial_fixed, trial_legal
            after_oracle = trial_oracle
            before_status = oracle_records[before_oracle]["result"]["status"]
            after_status = oracle_records[after_oracle]["result"]["status"]
            extension = ("preexisting_unsat" if before_status == "unsat" else
                         "unknown" if "unknown" in (before_status, after_status) else
                         "unsafe" if after_status == "unsat" else "safe")
            commitment_counts[extension] += 1
        require(type(event["after_phase"]) is int and event["after_phase"] == current_phase,
                "wrong post-event phase index")
        step = {"event_index": event_number, "kind": kind, "side": side, "symbol": symbol,
                "before_phase": before_phase, "trial_phase": trial_phase, "after_phase": current_phase,
                "before_oracle_index": before_oracle, "trial_oracle_index": trial_oracle,
                "after_oracle_index": after_oracle,
                "before_status": oracle_records[before_oracle]["result"]["status"],
                "after_status": oracle_records[after_oracle]["result"]["status"],
                "extendibility": extension}
        steps.append(step)
        if extension == "unsafe" and first_bad is None:
            first_bad = {**step, "event": deepcopy(event),
                         "before": deepcopy(oracle_records[before_oracle]),
                         "after": deepcopy(oracle_records[after_oracle])}
    require(consumed == len(phases), "unreferenced propagation phases")
    require(type(result["final_phase"]) is int and result["final_phase"] == current_phase, "wrong final phase")
    final = phases[current_phase]["outcome"]
    require(all(type(result[name]) is int for name in ("choices", "probes", "rejections"))
            and result["choices"] == choices and result["probes"] == probes and result["rejections"] == rejections,
            "incorrect event telemetry")
    for name in ("name_states", "domains", "colors"):
        _same(result[name], final[name], "final " + name)
    if final["status"] == "underdetermined":
        require(choices == result["decision_limit"] or (result["probe"] and probes == result["probe_limit"]),
                "unexplained early stop")
        require(result["status"] == "incomplete" and result["reason"] ==
                ("decision-limit-exhausted" if choices == result["decision_limit"]
                 else "probe-limit-exhausted"), "budget exhaustion mislabeled")
    else:
        require(result["status"] == final["status"], "terminal status mismatch")
        require(result["reason"] == ("complete-coloring-verified" if final["status"] == "solved"
                else "propagation-conflict-under-current-commitments"), "terminal reason mismatch")
    if final["colors"] is not None:
        values = [final["colors"][side] for side in sides]
        require(all(values[i] in initial_domains[i] for i in range(len(sides)))
                and all(values[a] != values[b] for a, b in edges), "final colors violate raw constraints")
    return {"passed": True, "audit_version": AUDIT_VERSION, "geometry": geometry_check,
            "phase_count": len(phases), "phase_audits": phase_audits,
            "trace_steps_checked": sum(row["trace_steps_checked"] for row in phase_audits),
            "initial_oracle_index": initial_oracle, "oracle_records": oracle_records, "steps": steps,
            "first_bad_commitment": first_bad, "commitment_counts": commitment_counts,
            "rejection_counts": rejection_counts,
            "oracle_unknown": sum(row["result"]["status"] == "unknown" for row in oracle_records),
            "full_enumeration": {"status": "run" if enumerate_all else "not_run",
                "reason": None if enumerate_all else "initial_assignment_product_exceeds_limit",
                "assignment_product": size, "assignment_limit": assignment_limit,
                "literal_assignments_checked": size if enumerate_all else 0,
                "initial_legal_assignments": legal_count, "phase_checks": phase_checks,
                "legal_assignments_preserved": preserved_count},
            "oracle_scope": "original_real_neq_initial_anchors_and_actual_commitments_only",
            "oracle_feedback_to_producer": False,
            "schedule_audit": "shared_mother_peer_selector_with_explicit_frame_fallback" if context
                              else "independent_first_unresolved_input_order",
            "scope": "Passed audits can contain unsafe commitments; unknown is not safe or UNSAT."}

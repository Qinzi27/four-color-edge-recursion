"""Preserve frozen low-name decisions while using the equivalent prefilter.

This is an implementation optimization, not a new inference policy. The narrow
copied loops deliberately return the old policy/version fields and complete
semantic envelopes. ``IMPLEMENTATION_VERSION`` and external ``work_log`` identify
the optimized implementation without changing the frozen result language.
"""

from copy import deepcopy

from scripts.quaternary_contact_model import NameState
from scripts.quaternary_logical_neq import learn_logical_inequalities
from scripts.quaternary_triangle_saturation_prefilter_contacts import propagate_prefilter_contacts
from scripts.quaternary_low_color import (
    ABSTRACT_SCHEDULE, GEOMETRIC_SCHEDULE, _require, _schedule_context,
    _select_side,
)
from scripts.quaternary_odd_cycle_eq import learn_odd_cycle_equalities
from scripts.quaternary_triangle_saturation_low_color import INNER_POLICY, POLICY


IMPLEMENTATION_VERSION = "quaternary-low-color-triangle-saturation-prefilter-v1"


def solve_prefilter_contacts(document, *, geometry=None, decision_limit=128,
                             probe_limit=8192, work_log=None):
    """Keep actual choices, rejected trials and all nested semantic traces.

    Every propagation call receives the same optional caller-owned telemetry
    list. Its rows never influence selection, domains, learned facts or limits.
    The old bounded loop remains explicit rather than mutating another module's
    global propagator; independently running old/new versions is therefore safe.
    """
    if work_log is not None and not isinstance(work_log, list):
        raise ValueError("work_log must be a list or None")
    for name, value in (("decision_limit", decision_limit), ("probe_limit", probe_limit)):
        _require(type(value) is int and value >= 0, f"{name} must be a nonnegative integer")
    work = deepcopy(document)
    initial = propagate_prefilter_contacts(work, work_log=work_log)
    context = _schedule_context(work, geometry)
    sides = list(work["sides"])
    phases = [{"kind": "main", "document": deepcopy(work), "outcome": initial}]
    events, current, choices, probes, rejections = [], 0, 0, 0, 0
    stop_reason = None
    while phases[current]["outcome"]["status"] == "underdetermined":
        if choices >= decision_limit:
            stop_reason = "decision-limit-exhausted"
            break
        if probes >= probe_limit:
            stop_reason = "probe-limit-exhausted"
            break
        outcome = phases[current]["outcome"]
        selection = _select_side(sides, outcome["domains"], context)
        side = selection["side_id"]
        candidates = list(outcome["name_states"][side]["candidates"])
        symbol = min(candidates)
        proposal = deepcopy(work)
        proposal.setdefault("anchors", {})[side] = symbol
        proposed_outcome = propagate_prefilter_contacts(proposal, work_log=work_log)
        proposed_index = len(phases)
        phases.append({"kind": "trial", "document": deepcopy(proposal), "outcome": proposed_outcome})
        event = {"side": side, "symbol": symbol, "candidates_before": candidates,
                 "selection": selection, "before_phase": current, "trial_phase": proposed_index}
        probes += 1
        if proposed_outcome["status"] == "conflict":
            work.setdefault("states", {})[side] = NameState.from_candidates(
                name for name in candidates if name != symbol).to_quaternary()
            current = len(phases)
            phases.append({"kind": "main", "document": deepcopy(work),
                           "outcome": propagate_prefilter_contacts(work, work_log=work_log)})
            event.update(kind="reject", after_phase=current, extension_claim="refuted")
            rejections += 1
        else:
            work, current = proposal, proposed_index
            claim = "complete-witness" if proposed_outcome["status"] == "solved" else "inconclusive"
            event.update(kind="commit", after_phase=current, extension_claim=claim)
            choices += 1
        events.append(event)
    final = phases[current]["outcome"]
    status = "incomplete" if stop_reason is not None else final["status"]
    reason = stop_reason or ("complete-coloring-verified" if status == "solved"
                             else "propagation-conflict-under-current-commitments")
    return {"schema_version": 1, "policy": INNER_POLICY, "probe": True,
            "schedule": GEOMETRIC_SCHEDULE if context is not None else ABSTRACT_SCHEDULE,
            "original_input": deepcopy(document), "phases": phases, "events": events,
            "final_phase": current, "status": status, "reason": reason,
            "colors": deepcopy(final["colors"]), "name_states": deepcopy(final["name_states"]),
            "domains": deepcopy(final["domains"]), "choices": choices, "probes": probes,
            "rejections": rejections, "backtracks": 0,
            "decision_limit": decision_limit, "probe_limit": probe_limit,
            "oracle_feedback_to_producer": False, "old_colors_read": False,
            "scope": "Chosen-side one-level conditional propagation with raw-certified logical "
                     "relations and low-name preference; no committed-color rollback or oracle "
                     "feedback. Surviving non-complete trials remain inconclusive."}


def solve_prefilter_triangle_saturation(document, *, geometry=None, decision_limit=128,
                                        probe_limit=8192, work_log=None):
    """Run unchanged independent raw learners and the optimized inner loop.

    Learners see only the original graph. Explicit logical fields do not become
    physical separator edges, and neither oracle answers nor old colors enter
    production. The complete old envelope remains available for literal replay
    comparison, including every rejected trial and every retained commitment.
    """
    if work_log is not None and not isinstance(work_log, list):
        raise ValueError("work_log must be a list or None")
    original = deepcopy(document)
    equalities = learn_odd_cycle_equalities(original)
    inequalities = learn_logical_inequalities(original)
    augmented = deepcopy(original)
    if equalities["equal_names"]:
        augmented["equal_names"] = deepcopy(equalities["equal_names"])
    if inequalities["different_names"]:
        augmented["different_names"] = deepcopy(inequalities["different_names"])
    run = solve_prefilter_contacts(augmented, geometry=geometry,
                                  decision_limit=decision_limit, probe_limit=probe_limit,
                                  work_log=work_log)
    return {"schema_version": 1, "policy": POLICY, "original_input": original,
            "learning": {"equalities": equalities, "inequalities": inequalities},
            "augmented_input": augmented, "run": run,
            "oracle_feedback_to_producer": False, "old_colors_read": False}

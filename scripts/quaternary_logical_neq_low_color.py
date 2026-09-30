"""Certified raw-graph logical NEQ with the original guarded low-name choice.

The inner decision loop is a separately versioned copy of the guarded branch
in ``quaternary_low_color.solve_low_color``. Only its contact propagator and
policy identifier change; selection, rejection, resource limits and committed
color persistence keep that contract. The all-candidate scan is not used.
"""

from copy import deepcopy

from scripts.quaternary_contact_model import NameState
from scripts.quaternary_logical_neq import learn_logical_inequalities
from scripts.quaternary_logical_neq_contacts import propagate_logical_contacts
from scripts.quaternary_low_color import (
    ABSTRACT_SCHEDULE, GEOMETRIC_SCHEDULE, _require, _schedule_context,
    _select_side,
)
from scripts.quaternary_odd_cycle_eq import learn_odd_cycle_equalities


POLICY = "quaternary-low-color-logical-neq-v1"
INNER_POLICY = "quaternary-low-color-logical-neq-conditional-v1"


def solve_logical_contacts(document, *, geometry=None, decision_limit=128, probe_limit=8192):
    """Keep chosen-side/minimum-color trials, with explicit logical premises.

    Every failed trial has a complete propagation trace. Rejection narrows
    only its side's supplied state using the current propagated domain; it
    does not add an explicit anchor. Surviving trials are committed without
    rollback and remain inconclusive unless they give a complete coloring.
    """
    for name, value in (("decision_limit", decision_limit), ("probe_limit", probe_limit)):
        _require(type(value) is int and value >= 0, f"{name} must be a nonnegative integer")
    work = deepcopy(document)
    initial = propagate_logical_contacts(work)
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
        proposed_outcome = propagate_logical_contacts(proposal)
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
                           "outcome": propagate_logical_contacts(work)})
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


def solve_logical_neq(document, *, geometry=None, decision_limit=128, probe_limit=8192):
    """Learn EQ and logical NEQ independently from the same original graph.

    Neither learner sees the other's results. Learned pairs are additional
    logical fields; ``lines`` and physical side identities remain unchanged.
    No old coloring, oracle answer or learned edge feeds structural discovery.
    """
    original = deepcopy(document)
    equalities = learn_odd_cycle_equalities(original)
    inequalities = learn_logical_inequalities(original)
    augmented = deepcopy(original)
    if equalities["equal_names"]:
        augmented["equal_names"] = deepcopy(equalities["equal_names"])
    if inequalities["different_names"]:
        augmented["different_names"] = deepcopy(inequalities["different_names"])
    run = solve_logical_contacts(augmented, geometry=geometry,
                                 decision_limit=decision_limit, probe_limit=probe_limit)
    return {"schema_version": 1, "policy": POLICY, "original_input": original,
            "learning": {"equalities": equalities, "inequalities": inequalities},
            "augmented_input": augmented, "run": run,
            "oracle_feedback_to_producer": False, "old_colors_read": False}

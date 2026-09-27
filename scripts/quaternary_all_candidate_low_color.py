"""Probe all unresolved candidates before each guarded low-name commitment.

This separate version retains the original side identities, mother-line side
schedule and certified raw-graph odd-cycle equalities. A sweep tests every
remaining name on every unresolved side in input order. Only a replayable
propagation contradiction permits a deletion. A deletion restarts the sweep;
an uninterrupted full sweep permits the existing scheduler to choose its
lowest available name. Surviving trials remain inconclusive unless solved.
"""

from copy import deepcopy

from scripts.quaternary_contact_model import NameState, propagate_contacts
from scripts.quaternary_low_color import (
    ABSTRACT_SCHEDULE, GEOMETRIC_SCHEDULE, _require, _schedule_context,
    _select_side,
)
from scripts.quaternary_odd_cycle_eq import learn_odd_cycle_equalities


POLICY = "quaternary-low-color-all-candidate-v1"


def solve_all_candidate_contacts(document, *, geometry=None, decision_limit=128,
                                 probe_limit=8192):
    """Run one-level failed-candidate elimination to a sweep fixed point.

    ``decision_limit`` counts actual commitments. ``probe_limit`` counts every
    trial propagation, including surviving trials that are not selected. A
    partially completed sweep cannot authorize a commitment. If the last
    available probe completes a sweep, its cached chosen trial can still be
    committed without another propagation. The cache is discarded whenever a
    persistent phase changes, including after a rejection.

    The inner entry accepts the contact language including candidate states;
    the public raw-graph wrapper below restricts external states and equalities.
    Every trial is retained, even when its outcome is a complete coloring and
    it is not the scheduled choice. No oracle or committed-color rollback is
    used. A rejected candidate is represented by an unanchored state, not by a
    new explicit color commitment.
    """
    for name, value in (("decision_limit", decision_limit), ("probe_limit", probe_limit)):
        _require(type(value) is int and value >= 0, f"{name} must be a nonnegative integer")
    work = deepcopy(document)
    initial = propagate_contacts(work)
    context = _schedule_context(work, geometry)
    sides = list(work["sides"])
    phases = [{"kind": "main", "document": deepcopy(work), "outcome": initial}]
    events = []
    current = choices = probes = rejections = 0
    sweeps_started = sweeps_completed = 0
    stop_reason = None

    while phases[current]["outcome"]["status"] == "underdetermined":
        if choices >= decision_limit:
            stop_reason = "decision-limit-exhausted"
            break
        sweeps_started += 1
        outcome = phases[current]["outcome"]
        # An inventory belongs to exactly one persistent state. Never continue
        # scanning a stale inventory after a rejection narrows other domains.
        inventory = [(side, list(domain)) for side, domain in zip(sides, outcome["domains"])
                     if len(domain) > 1]
        cached_trials = {}
        rejected = False
        for side, candidates in inventory:
            for symbol in sorted(candidates):
                if probes >= probe_limit:
                    stop_reason = "probe-limit-exhausted"
                    break
                proposal = deepcopy(work)
                proposal.setdefault("anchors", {})[side] = symbol
                proposed_outcome = propagate_contacts(proposal)
                trial = len(phases)
                phases.append({"kind": "trial", "document": deepcopy(proposal),
                               "outcome": proposed_outcome})
                probes += 1
                event = {"side": side, "symbol": symbol,
                         "candidates_before": list(candidates), "selection": None,
                         "before_phase": current, "trial_phase": trial}
                if proposed_outcome["status"] == "conflict":
                    # The saved trial is the certificate for this sole new
                    # input restriction. Keep all prior restrictions/anchors.
                    work.setdefault("states", {})[side] = NameState.from_candidates(
                        name for name in candidates if name != symbol).to_quaternary()
                    current = len(phases)
                    phases.append({"kind": "main", "document": deepcopy(work),
                                   "outcome": propagate_contacts(work)})
                    event.update(kind="reject", after_phase=current,
                                 extension_claim="refuted")
                    rejections += 1
                    rejected = True
                else:
                    event.update(kind="probe", after_phase=current,
                                 extension_claim=("complete-witness"
                                                  if proposed_outcome["status"] == "solved"
                                                  else "inconclusive"))
                    cached_trials[(side, symbol)] = trial
                events.append(event)
                if rejected:
                    break
            if rejected or stop_reason is not None:
                break
        if stop_reason is not None:
            break
        if rejected:
            continue

        sweeps_completed += 1
        selection = _select_side(sides, outcome["domains"], context)
        side = selection["side_id"]
        candidates = list(outcome["name_states"][side]["candidates"])
        symbol = min(candidates)
        trial = cached_trials[(side, symbol)]
        chosen = phases[trial]
        events.append({"kind": "commit", "side": side, "symbol": symbol,
                       "candidates_before": candidates, "selection": selection,
                       "before_phase": current, "trial_phase": trial,
                       "after_phase": trial,
                       "extension_claim": ("complete-witness"
                                           if chosen["outcome"]["status"] == "solved"
                                           else "inconclusive")})
        # Commit the exact previously recorded trial; this incurs no additional
        # propagation and does not quietly spend or reset the probe budget.
        work, current = deepcopy(chosen["document"]), trial
        choices += 1

    final = phases[current]["outcome"]
    status = "incomplete" if stop_reason is not None else final["status"]
    reason = stop_reason or ("complete-coloring-verified" if status == "solved"
                             else "propagation-conflict-under-current-commitments")
    return {"schema_version": 1, "policy": POLICY, "probe": True,
            "schedule": GEOMETRIC_SCHEDULE if context is not None else ABSTRACT_SCHEDULE,
            "original_input": deepcopy(document), "phases": phases, "events": events,
            "final_phase": current, "status": status, "reason": reason,
            "colors": deepcopy(final["colors"]), "name_states": deepcopy(final["name_states"]),
            "domains": deepcopy(final["domains"]), "choices": choices, "probes": probes,
            "rejections": rejections, "backtracks": 0,
            "sweeps_started": sweeps_started, "sweeps_completed": sweeps_completed,
            "decision_limit": decision_limit, "probe_limit": probe_limit,
            "oracle_feedback_to_producer": False, "old_colors_read": False,
            "scope": "All unresolved candidates receive one-level conditional propagation "
                     "before a low-name commitment; restart after each certified rejection. "
                     "No committed-color rollback or oracle feedback. Surviving non-complete "
                     "trials are inconclusive, not safe-extension proofs."}


def solve_all_candidate_low_color(document, *, geometry=None, decision_limit=128,
                                  probe_limit=8192):
    """Learn raw odd-cycle EQ once and run the separately versioned full sweep.

    Equalities are logical constraints; they never merge geometric face IDs.
    The learner rejects externally supplied nonempty candidate states or EQ.
    Learning and all trial evidence are saved for offline independent checking.
    """
    original = deepcopy(document)
    learning = learn_odd_cycle_equalities(original)
    augmented = deepcopy(original)
    if learning["equal_names"]:
        augmented["equal_names"] = deepcopy(learning["equal_names"])
    run = solve_all_candidate_contacts(augmented, geometry=geometry,
                                       decision_limit=decision_limit, probe_limit=probe_limit)
    return {"schema_version": 1, "policy": POLICY, "original_input": original,
            "learning": learning, "augmented_input": augmented, "run": run,
            "oracle_feedback_to_producer": False, "old_colors_read": False}

"""Low-name commitments with optional one-hypothesis contact propagation.

The four-name palette and geometric side schedule are inputs/conventions. A
failed trial proves only that its proposed name is impossible under the current
commitments; a surviving trial is inconclusive unless it supplies a complete
verified coloring. No oracle, alternative coloring search, or rollback is used.
"""

from copy import deepcopy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.global_restart import current_segments
from fourcolor.level_sides import level_metadata
from fourcolor.level_sides_peer import select_peer_occurrence
from fourcolor.whole_lines import build_whole_lines
from scripts.quaternary_contact_model import NameState, propagate_contacts


POLICY = "quaternary-low-color-conditional-propagation-v1"
GEOMETRIC_SCHEDULE = "mother-peer-with-frame-only-fallback-v1"
ABSTRACT_SCHEDULE = "first-unresolved-input-order-v1"


def _require(condition, message):
    """Reject malformed inputs without relying on removable assertions."""
    if not condition:
        raise ValueError(message)


def _schedule_context(document, geometry):
    """Validate the exact global-side/real-edge map before using geometry."""
    if geometry is None:
        return None
    _require(isinstance(geometry, dict), "geometry must be an exported object")
    model = build_whole_lines(geometry)
    expected_sides = [f"S{i}" for i in range(len(model.plane_map.faces))]
    _require(document["sides"] == expected_sides,
             "geometric side order must match global faces S0..S(n-1)")
    expected_faces = [model.plane_map.face_of_dart[d]
                      for d in range(2 * len(geometry["edges"]))]
    _require(geometry.get("faceOfDart") == expected_faces
             and all(type(value) is int for value in geometry["faceOfDart"]),
             "exported face identities do not match the geometry rotation")
    expected_lines = []
    for edge_id, edge in enumerate(geometry["edges"]):
        if edge.get("virtual", False):
            continue
        left, right = (f"S{expected_faces[2 * edge_id + offset]}" for offset in (0, 1))
        expected_lines.append({"id": f"E{edge_id}", "left": left, "right": right,
                               "kind": "bridge" if left == right else "separator"})
    _require(sorted(document["lines"], key=lambda row: row["id"])
             == sorted(expected_lines, key=lambda row: row["id"]),
             "contact lines must match every real atomic edge and its orientation")
    return model, current_segments(model), level_metadata(model)


def _select_side(sides, domains, context):
    """Keep the old internal-mother scheduler, with an explicit frame fallback.

    The old two-anchor initialization already fixed the exterior side. A single
    anchor can leave that frame-only side unresolved, so it needs a recorded
    fallback after all unresolved internal occurrences have disappeared.
    """
    unresolved = [i for i, domain in enumerate(domains) if len(domain) > 1]
    _require(bool(unresolved), "selection requires an unresolved side")
    if context is None:
        side = unresolved[0]
        selected = {"side": side, "selection_group": "input-order",
                    "schedule": ABSTRACT_SCHEDULE,
                    "reason": "first-unresolved-input-side"}
    else:
        model, units, levels = context
        internal = any(len(domains[side]) > 1 for unit in units if unit["mother"] != "frame"
                       for side, _ in unit["occurrences"])
        if internal:
            selected = deepcopy(select_peer_occurrence(model, units, levels, domains))
            selected.update(schedule=GEOMETRIC_SCHEDULE,
                            reason="existing-mother-peer-internal-occurrence")
            side = selected["side"]
        else:
            side = unresolved[0]
            frame_occurrences = [(unit["id"], dart) for unit in units if unit["mother"] == "frame"
                                 for face, dart in unit["occurrences"] if face == side]
            _require(bool(frame_occurrences), "unresolved geometric side has no mother occurrence")
            unit, dart = frame_occurrences[0]
            selected = {"side": side, "dart": dart, "mother": "frame", "unit": unit,
                        "selection_group": "frame-only-fallback", "schedule": GEOMETRIC_SCHEDULE,
                        "reason": "no-unresolved-internal-occurrence"}
    selected.update(side_id=sides[side], candidate_order=list(domains[side]))
    return selected


def solve_low_color(document, *, geometry=None, probe=True, decision_limit=128, probe_limit=512):
    """Commit the smallest current name, optionally rejecting refuted proposals.

    Resource limits are nonnegative integers. ``decision_limit`` bounds actual
    commitments; reaching it stops before the next attempt. ``probe_limit``
    bounds trial propagation calls and is irrelevant when ``probe=False``.
    Every phase retains its complete literal input and propagation trace.
    Trials change only one anchor. A rejection changes only that side's supplied
    state to its previous propagated domain minus the refuted name; all other
    input restrictions remain intact. Committed anchors are never withdrawn.
    """
    _require(type(probe) is bool, "probe must be boolean")
    for name, value in (("decision_limit", decision_limit), ("probe_limit", probe_limit)):
        _require(type(value) is int and value >= 0, f"{name} must be a nonnegative integer")
    work = deepcopy(document)
    initial = propagate_contacts(work)  # Also validates the complete contact language.
    context = _schedule_context(work, geometry)
    sides = list(work["sides"])
    phases = [{"kind": "main", "document": deepcopy(work), "outcome": initial}]
    events, current, choices, probes, rejections = [], 0, 0, 0, 0
    stop_reason = None
    while phases[current]["outcome"]["status"] == "underdetermined":
        if choices >= decision_limit:
            stop_reason = "decision-limit-exhausted"
            break
        if probe and probes >= probe_limit:
            stop_reason = "probe-limit-exhausted"
            break
        outcome = phases[current]["outcome"]
        selection = _select_side(sides, outcome["domains"], context)
        side = selection["side_id"]
        candidates = list(outcome["name_states"][side]["candidates"])
        symbol = min(candidates)
        proposal = deepcopy(work)
        proposal.setdefault("anchors", {})[side] = symbol
        proposed_outcome = propagate_contacts(proposal)
        proposed_index = len(phases)
        phases.append({"kind": "trial" if probe else "main",
                       "document": deepcopy(proposal), "outcome": proposed_outcome})
        event = {"side": side, "symbol": symbol, "candidates_before": candidates,
                 "selection": selection, "before_phase": current,
                 "trial_phase": proposed_index if probe else None}
        if probe:
            probes += 1
        if probe and proposed_outcome["status"] == "conflict":
            # Only a replayable propagation contradiction authorizes deletion.
            # Reuse the previous propagated domain, never widen supplied states.
            work.setdefault("states", {})[side] = NameState.from_candidates(
                name for name in candidates if name != symbol).to_quaternary()
            current = len(phases)
            phases.append({"kind": "main", "document": deepcopy(work),
                           "outcome": propagate_contacts(work)})
            event.update(kind="reject", after_phase=current, extension_claim="refuted")
            rejections += 1
        else:
            work, current = proposal, proposed_index
            claim = ("complete-witness" if proposed_outcome["status"] == "solved"
                     else "inconclusive") if probe else "unchecked"
            event.update(kind="commit", after_phase=current, extension_claim=claim)
            choices += 1
        events.append(event)
    final = phases[current]["outcome"]
    status = "incomplete" if stop_reason is not None else final["status"]
    reason = stop_reason or ("complete-coloring-verified" if status == "solved"
                             else "propagation-conflict-under-current-commitments")
    return {"schema_version": 1, "policy": POLICY, "probe": probe,
            "schedule": GEOMETRIC_SCHEDULE if context is not None else ABSTRACT_SCHEDULE,
            "original_input": deepcopy(document), "phases": phases, "events": events,
            "final_phase": current, "status": status, "reason": reason,
            "colors": deepcopy(final["colors"]), "name_states": deepcopy(final["name_states"]),
            "domains": deepcopy(final["domains"]), "choices": choices, "probes": probes,
            "rejections": rejections, "backtracks": 0,
            "decision_limit": decision_limit, "probe_limit": probe_limit,
            "oracle_feedback_to_producer": False, "old_colors_read": False,
            "scope": "One-level conditional propagation with low-name preference; no committed "
                     "color rollback, oracle feedback, Hall filter, or structural refutation. "
                     "Surviving non-complete trials are inconclusive, not safe-extension proofs."}

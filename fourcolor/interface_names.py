"""One certified release of a movable shared interface after current naming.

Common boundary identities are real constraints, not automatically immutable
anchors. Only the exterior is permanently fixed. This policy preserves every
success of current_names and adds ONE deterministic interface-release attempt
when its companion domain is empty. No alternative releases are searched.
"""

from collections import Counter

from .anchor_forest import _state_adjacency
from .current_names import _names, _renamed, attempt_current_cut
from .inherited_names import RectSide, RectState
from .retained_profiles import _finish_event, _validate_state


def _restore(payload):
    """Recreate a legal uncommitted normalization without experiment imports."""
    return RectState(payload["width"], payload["height"], tuple(
        RectSide(s["id"], tuple(s["bounds"]), s["symbol"]) for s in payload["sides"]),
        tuple(tuple(tuple(p) for p in cut) for cut in payload["cuts"]))


def attempt_interface_cut(state, points, max_old_sides=3):
    """Preserve prior successes; if Q is empty, release one redundant shared ban.

    A candidate v is the sole carrier of its current name in common interfaces
    J. Its target t must already occur on another J member and be legal across
    every old boundary of v. Thus c(J) loses exactly one name without gaining
    another; the mother name and outside1 stay fixed. The move may INCREASE a
    numeric name, which is necessary in some elementary examples.

    Prior release-touched sides and this interface consume the budget first.
    The subsequent patch receives the remaining budget; overlap is conservatively
    double-counted, so this policy does NOT promise minimum old-side changes.
    Any failure leaves the exact original input object untouched.
    """
    first = attempt_current_cut(state, points, max_old_sides=max_old_sides)
    if first["status"] != "blocked" or first["event"]["reason"] != "no_companion_with_common_interfaces_fixed":
        return first
    previous = first["event"]
    working = _restore(previous["normalization_preview"])
    _validate_state(working)
    names, graph = _names(working), _state_adjacency(working)
    bounds = {s.id: s.bounds for s in working.sides}
    common = {row["id"] for row in previous["fixed_common_interfaces"]}
    counts = Counter(names[v] for v in common)
    touched = {row["id"] for row in previous["release_trace"]}
    choices, rows = [], []
    for vertex in sorted(common - {"outside"}):
        neighbors = {names[v] for v in graph[vertex]}
        targets = sorted(set(counts) - {names[vertex]} - neighbors) if counts[names[vertex]] == 1 else []
        budget_ok = len(touched | {vertex}) <= max_old_sides
        rows.append({"id": vertex, "current": names[vertex], "common_name_multiplicity": counts[names[vertex]],
                     "neighbor_names": {v: names[v] for v in sorted(graph[vertex])},
                     "targets": targets, "budget_ok": budget_ok})
        if budget_ok:
            choices.extend((target, bounds[vertex], vertex) for target in targets)
    event = {**previous, "shared_release_attempted": True, "shared_release_candidates": rows}

    def reject(reason):
        """Diagnostics are tentative and cannot leak into the committed map."""
        event["reason"] = reason
        return {"status": "blocked", "state": state, "event": event}

    if not choices:
        return reject("no_safe_shared_interface_release")
    target, _, vertex = min(choices)
    assigned = {**names, vertex: target}
    released = _renamed(working, assigned)
    _validate_state(released)
    before_common, after_common = set(counts), {assigned[v] for v in common}
    if len(after_common) != len(before_common) - 1 or not after_common < before_common:
        raise AssertionError("shared release did not remove exactly one ban")
    charged = touched | {vertex}
    event["shared_release"] = {"id": vertex, "before": names[vertex], "after": target,
                               "common_names_before": sorted(before_common),
                               "common_names_after": sorted(after_common),
                               "precharged_old_ids": sorted(charged)}
    # There was no eligible pair in the first attempt. This is the only possible
    # parity attempt in this branch; no second target or companion is retried.
    # Use the validated cut: a caller's one-shot iterator was already consumed.
    following = attempt_current_cut(released, previous["cut"], max_old_sides=max_old_sides - len(charged), release=False)
    event["after_shared_release_event"] = following["event"]
    if following["status"] != "split":
        return reject("after_shared_release/" + following["event"]["reason"])
    final = following["state"]
    _validate_state(final)
    parent = previous["parent"]
    event.update({"method": "shared_interface_release", "reason": None})
    _finish_event(event, state, final, parent, (parent + ".l", parent + ".r"))
    event["changed_old_count"] = len(event["changed_old_sides"])
    if event["changed_old_count"] > max_old_sides or "actual_inherit" not in event:
        raise AssertionError("shared release violated budget or inherited parent name")
    return {"status": "split", "state": final, "event": event}

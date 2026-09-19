"""Current-boundary naming with bounded reuse and a pinned exterior.

This is a separately versioned policy, not a replacement of old experiment
records. No candidate coloring combinations, alternative pairs, or histories
are searched. A refusal is a limit of this policy, not a fifth-color theorem.
"""

from collections import deque

from .anchor_forest import _state_adjacency
from .current_geometry import propose_rect_split
from .inherited_names import RectSide, RectState, state_payload
from .local_reuse import PALETTE, solve_two_name_patch
from .retained_profiles import _finish_event, _validate_state


def _names(state):
    """Current symbols are separate from geometric IDs and birth history."""
    return {"outside": 1, **{side.id: side.symbol for side in state.sides}}


def _renamed(state, names):
    """Rebuild immutable side records without changing any mother line."""
    return RectState(state.width, state.height, tuple(
        RectSide(side.id, side.bounds, names[side.id]) for side in state.sides), state.cuts)


def _direct_candidates(proposed, graph, names, children, inherited):
    """Read ALL old boundaries; a point contact alone never enters graph."""
    used, rows, choices = set(names.values()), [], []
    for side in sorted((s for s in proposed.sides if s.id in children), key=lambda s: s.bounds):
        neighbors = graph[side.id] - set(children)
        retained = sorted({names[v] for v in neighbors})
        allowed = sorted(PALETTE - set(retained) - {inherited})
        rows.append({"child_id": side.id, "bounds": side.bounds,
                     "old_neighbor_ids": sorted(neighbors), "R": retained,
                     "available_names": allowed})
        choices.extend((t not in used, t, side.bounds, side.id) for t in allowed)
    return rows, min(choices) if choices else None


def release_neighbor_names(state, parent_id, max_old_sides=3):
    """Make bounded, strictly decreasing REUSE moves near the split parent.

    Only complete current neighbor restrictions are used. Targets must already
    occur in the current map, so a release cannot introduce a color. At most k
    distinct old sides are touched; revisiting one of them can only decrease
    its integer name. Sum of names strictly decreases, with at most 3k moves.
    This is neither a global minimum coloring nor a complete renaming method.
    """
    if type(max_old_sides) is not int or max_old_sides < 0:
        raise ValueError("nonnegative integer old-side budget required")
    _validate_state(state)
    graph, names = _state_adjacency(state), _names(state)
    if parent_id not in graph or parent_id == "outside":
        raise ValueError("parent must be a known internal side")
    bounds = {s.id: s.bounds for s in state.sides}
    eligible = graph[parent_id] - {"outside"}
    touched, trace = set(), []
    initial_sum = sum(names.values())
    while True:
        choices = []
        for vertex in eligible:
            if vertex not in touched and len(touched) >= max_old_sides:
                continue
            banned = {names[v] for v in graph[vertex]}
            allowed = (PALETTE & set(names.values())) - banned
            choices.extend((t, bounds[vertex], vertex) for t in allowed if t < names[vertex])
        if not choices:
            break
        target, _, vertex = min(choices)
        before = names[vertex]
        trace.append({"id": vertex, "before": before, "after": target,
                      "neighbor_names": {v: names[v] for v in sorted(graph[vertex])}})
        names[vertex] = target
        touched.add(vertex)
    result = _renamed(state, names)
    _validate_state(result)
    budget_blocked = sorted(v for v in eligible if v not in touched
                            and len(touched) >= max_old_sides
                            and any(t < names[v] for t in
                                    (PALETTE & set(names.values())) - {names[w] for w in graph[v]}))
    if len(trace) > 3 * max_old_sides:
        raise AssertionError("strict descent exceeded its proved bound")
    return {"state": result, "touched_ids": sorted(touched), "trace": trace,
            "eligible_ids": sorted(eligible), "potential_before": initial_sum,
            "potential_after": sum(names.values()),
            "stop_reason": "budget_limited" if budget_blocked else "locally_stable",
            "budget_blocked_ids": budget_blocked,
            "scope": "bounded strict reuse descent; not global minimality or a full restart"}


def attempt_current_cut(state, points, max_old_sides=3, release=True):
    """Try direct naming, bounded release, then one pinned two-name patch.

    The outside is always fixed1, but internal names may also be1. A two-name
    patch stops at the outside and receives its boundary pin; touching it is
    not itself a rejection. The budget counts the UNION of release-touched
    old sides and patch old members, including members eventually unchanged.
    Failed operations roll back all tentative renames and the proposed cut.
    """
    if type(max_old_sides) is not int or max_old_sides < 0 or type(release) is not bool:
        raise ValueError("nonnegative integer budget and boolean release flag required")
    geometry = propose_rect_split(state, points)
    if geometry["status"] != "proposed":
        return geometry
    proposed, raw = geometry["proposed_state"], geometry["event"]
    parent = raw["parent"]
    children = (parent + ".l", parent + ".r")
    inherited = _names(state)[parent]
    graph = _state_adjacency(proposed)
    working, names, touched = state, _names(state), set()
    rows, choice = _direct_candidates(proposed, graph, names, children, inherited)
    event = {"method": "current_direct", "cut": raw["cut"], "parent": parent, "s": inherited,
             "endpoint_incidence": raw["endpoint_incidence"], "initial_candidates": rows,
             "max_old_sides": max_old_sides, "release_enabled": release,
             "release_trace": [], "selection_order": ["new_name_introduction", "numeric_name", "bounds"]}

    def blocked(reason):
        """Keep diagnostics but never commit only part of the operation."""
        event.update({"reason": reason, "candidates": rows,
                      "normalization_preview": state_payload(working),
                      "scope": "this deterministic policy and budget only"})
        return {"status": "blocked", "state": state, "event": event}

    if choice is None and release:
        lowering = release_neighbor_names(state, parent, max_old_sides)
        working, touched = lowering["state"], set(lowering["touched_ids"])
        names = _names(working)
        event["release_trace"] = lowering["trace"]
        event["release_stop_reason"] = lowering["stop_reason"]
        event["release_budget_blocked_ids"] = lowering["budget_blocked_ids"]
        event["release_potential"] = [lowering["potential_before"], lowering["potential_after"]]
        rows, choice = _direct_candidates(proposed, graph, names, children, inherited)
        if choice is not None:
            event["method"] = "current_release_direct"
    event["candidates"] = rows
    if choice is not None:
        introduced, target, _, new_id = choice
        assigned = {v: names[v] for v in graph if v not in children}
        assigned.update({v: target if v == new_id else inherited for v in children})
        event.update({"target": target, "introduced_new_name": introduced, "new_name_child": new_id})
    else:
        common = set(rows[0]["old_neighbor_ids"]) & set(rows[1]["old_neighbor_ids"])
        options = sorted(PALETTE - {inherited} - {names[v] for v in common})
        event["fixed_common_interfaces"] = [{"id": v, "name": names[v]} for v in sorted(common)]
        if not options:
            return blocked("no_companion_with_common_interfaces_fixed")
        companion = options[0]
        pair, patch, queue = (inherited, companion), set(children), deque(sorted(children))
        draft = {v: inherited if v in children else names[v] for v in graph}
        event["pair"] = sorted(pair)
        while queue:
            vertex = queue.popleft()
            for other in sorted(graph[vertex]):
                # The exterior remains a fixed boundary constraint in graph.
                if other == "outside" or other in patch or draft[other] not in pair:
                    continue
                patch.add(other)
                if len(touched | (patch - set(children))) > max_old_sides:
                    event.update({"rejection_members": sorted(patch),
                                  "release_touched_ids": sorted(touched),
                                  "rejection_members_complete": False})
                    return blocked("local_budget_exceeded")
                queue.append(other)
        old_cost_names = {v: name for v, name in _names(state).items() if v != parent}
        certificate = solve_two_name_patch(graph, draft, patch, pair, old_cost_names)
        event["patch_certificate"] = certificate
        if certificate["status"] != "renamed":
            return blocked(certificate["reason"])
        assigned = certificate["names"]
        event["method"] = "current_pinned_parity"
        event["patch_old_member_count"] = len(patch - set(children))
    final = _renamed(proposed, assigned)
    _validate_state(final)
    _finish_event(event, state, final, parent, children)
    event["changed_old_count"] = len(event["changed_old_sides"])
    if event["changed_old_count"] > max_old_sides or "actual_inherit" not in event:
        raise AssertionError("old-side budget or single-child inheritance violated")
    return {"status": "split", "state": final, "event": event}

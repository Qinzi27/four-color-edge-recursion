"""Complete-boundary inheritance, with a certified strip-family extension.

This is a testable completion proposal, not a claim to encode the user's whole
theory or to prove four-colorability. Geometry is restricted to rectangular
straight cuts. The positive mex is UNBOUNDED: a proposed fifth name is recorded
as a frozen-old-name obstruction, not declared globally unavoidable.

Optional synchronization is a separate policy. It applies only after exact
geometric recognition of the same two-anchor K2 join P_n family before/after
the cut, then invokes the existing deterministic prefix/suffix exchange rule.
There is no assignment enumeration, search fallback or opportunistic retry.
"""

from math import isfinite

from .inherited_names import (
    EPS, RectSide, RectState, _frame_segments, _shared, attempt_cut,
    boundary_contacts, choose_inherited_name, find_conflicts, line_profiles,
)
from .strip_chain import SideClass, StripChain, split_strip_chain


def _near(first, second):
    """Use the same explicit geometric tolerance as the rectangle adapter."""
    return abs(first - second) < EPS


def _segment_interval(segment):
    """Represent an axis-aligned segment by axis, fixed coordinate, interval."""
    (x0, y0), (x1, y1) = segment
    if _near(x0, x1) and not _near(y0, y1):
        return "vertical", x0, min(y0, y1), max(y0, y1)
    if _near(y0, y1) and not _near(x0, x1):
        return "horizontal", y0, min(x0, x1), max(x0, x1)
    raise ValueError("historical cuts must be nonzero axis-aligned segments")


def _covered(segment, sources):
    """Check collinear interval coverage, without raster sampling or graph DFS."""
    axis, fixed, start, stop = _segment_interval(segment)
    intervals = []
    for source in sources:
        other_axis, other_fixed, low, high = _segment_interval(source)
        if axis == other_axis and _near(fixed, other_fixed):
            intervals.append((low, high))
    reached = start
    for low, high in sorted(intervals):
        if high < reached - EPS:
            continue
        if low > reached + EPS:
            break
        reached = max(reached, high)
        if reached >= stop - EPS:
            return True
    return False


def _validate_state(state):
    """Reject malformed geometry, conflicting old names and names above four.

    These are the experiment's input preconditions, not a palette assumption
    used by mex. Historical lines must match the actual rectangular boundaries.
    """
    if not isinstance(state, RectState):
        raise ValueError("state must be a RectState")
    if any(isinstance(value, bool) or not isinstance(value, (int, float))
           or not isfinite(value) or value <= 0 for value in (state.width, state.height)):
        raise ValueError("state frame dimensions must be positive and finite")
    if not state.sides:
        raise ValueError("state must contain at least one rectangular side")
    seen, area = set(), 0.0
    boundaries = []
    for index, side in enumerate(state.sides):
        if not isinstance(side, RectSide):
            raise ValueError("every old side must be a RectSide")
        if (not isinstance(side.id, str) or not side.id.strip()
                or side.id == "outside" or side.id in seen):
            raise ValueError("old side IDs must be unique nonblank strings distinct from outside")
        seen.add(side.id)
        if type(side.symbol) is not int or not 1 <= side.symbol <= 4:
            raise ValueError("old state must use positive integer names at most four")
        if len(side.bounds) != 4 or any(
                isinstance(value, bool) or not isinstance(value, (int, float))
                or not isfinite(value) for value in side.bounds):
            raise ValueError("old side bounds must contain four finite coordinates")
        x0, y0, x1, y1 = side.bounds
        if not (0 <= x0 < x1 <= state.width and 0 <= y0 < y1 <= state.height
                and x1 - x0 > EPS and y1 - y0 > EPS):
            raise ValueError("old rectangles must be positive and inside the frame")
        area += (x1 - x0) * (y1 - y0)
        for other in state.sides[:index]:
            u0, v0, u1, v1 = other.bounds
            if min(x1, u1) - max(x0, u0) > EPS and min(y1, v1) - max(y0, v0) > EPS:
                raise ValueError("old rectangle interiors overlap")
            common = _shared(side.bounds, other.bounds)
            if common:
                boundaries.append(common)
    tolerance = EPS * max(1, state.width, state.height) * max(1, len(state.sides))
    if abs(area - state.width * state.height) > tolerance:
        raise ValueError("old rectangles do not tile the frame")
    if find_conflicts(state.sides, state.width, state.height):
        raise ValueError("old state already has a naming conflict")
    for cut in state.cuts:
        if (len(cut) != 2 or any(len(point) != 2 for point in cut)
                or any(isinstance(value, bool) or not isinstance(value, (int, float))
                       or not isfinite(value) for point in cut for value in point)):
            raise ValueError("historical cuts require two finite endpoint pairs")
        _segment_interval(cut)
        if any(not (0 <= x <= state.width and 0 <= y <= state.height) for x, y in cut):
            raise ValueError("historical cut lies outside the frame")
    if any(not _covered(boundary, state.cuts) for boundary in boundaries):
        raise ValueError("an old internal rectangle boundary has no historical line")
    frame = _frame_segments((0, 0, state.width, state.height), state.width, state.height)
    if any(not _covered(cut, boundaries + frame) for cut in state.cuts):
        raise ValueError("a historical line crosses an old rectangle interior")


def _profiles(state):
    """Keep ordered shore names distinct from their unordered display type."""
    return {mother: [{"segment": span["segment"], "pair": tuple(span["pair"]),
                      "type": tuple(sorted(span["pair"]))} for span in spans]
            for mother, spans in line_profiles(state).items()}


def _adjacency(state):
    """Derive every positive-length inequality, including the exterior anchor."""
    edges = set()
    for index, side in enumerate(state.sides):
        if _frame_segments(side.bounds, state.width, state.height):
            edges.add(tuple(sorted(("outside", side.id))))
        for other in state.sides[index + 1:]:
            if _shared(side.bounds, other.bounds):
                edges.add(tuple(sorted((side.id, other.id))))
    return edges


def _geometric_chain(sides, axis):
    """Recognize one contiguous horizontal/vertical band in geometric order."""
    if not sides:
        return None
    longitudinal, transverse = ((0, 2), (1, 3)) if axis == "horizontal" else ((1, 3), (0, 2))
    reference = sides[0].bounds
    if any(not all(_near(side.bounds[index], reference[index]) for index in transverse)
           for side in sides):
        return None
    ordered = sorted(sides, key=lambda side: side.bounds[longitudinal[0]])
    if any(not _near(left.bounds[longitudinal[1]], right.bounds[longitudinal[0]])
           for left, right in zip(ordered, ordered[1:])):
        return None
    return ordered


def _family_edges(anchor_id, chain):
    """Exact K2 join P_n edges, not a degree-based or visual approximation."""
    edges = {tuple(sorted(("outside", anchor_id)))}
    for side in chain:
        edges.add(tuple(sorted(("outside", side.id))))
        edges.add(tuple(sorted((anchor_id, side.id))))
    edges.update(tuple(sorted((left.id, right.id))) for left, right in zip(chain, chain[1:]))
    return edges


def _recognize_transition(before, proposed, parent_id, child_ids):
    """Require one unique unchanged anchor and the same certified path split."""
    old_by_id = {side.id: side for side in before.sides}
    new_by_id = {side.id: side for side in proposed.sides}
    old_edges, new_edges = _adjacency(before), _adjacency(proposed)
    expected_ids = (set(old_by_id) - {parent_id}) | set(child_ids)
    if set(new_by_id) != expected_ids:
        return None, "new side identities are not exactly one old side split into two"
    if any(new_by_id[key] != side for key, side in old_by_id.items() if key != parent_id):
        return None, "geometry proposal changed an unsplit old side"
    candidates = []
    for anchor in before.sides:
        if anchor.id == parent_id:
            continue
        for axis in ("horizontal", "vertical"):
            old_chain = _geometric_chain([side for side in before.sides if side.id != anchor.id], axis)
            new_chain = _geometric_chain([side for side in proposed.sides if side.id != anchor.id], axis)
            if old_chain is None or new_chain is None:
                continue
            if old_edges != _family_edges(anchor.id, old_chain) or new_edges != _family_edges(anchor.id, new_chain):
                continue
            old_ids = [side.id for side in old_chain]
            new_ids = [side.id for side in new_chain]
            index = old_ids.index(parent_id)
            geometric_children = [side.id for side in new_chain if side.id in child_ids]
            if (len(geometric_children) != 2
                    or new_ids != old_ids[:index] + geometric_children + old_ids[index + 1:]):
                continue
            candidates.append({"anchor": anchor, "axis": axis, "old_chain": old_chain,
                               "new_chain": new_chain, "split_index": index + 1,
                               "child_ids": tuple(geometric_children),
                               "old_edges": sorted(old_edges), "new_edges": sorted(new_edges)})
    if len(candidates) != 1:
        return None, ("no certified geometric two-anchor strip transition" if not candidates else
                      "more than one possible unchanged geometric anchor; no anchor is guessed")
    return candidates[0], None


def _finish_event(event, before, after, parent_id, child_ids):
    """Rebuild every line occurrence after names change, retaining mother IDs."""
    old = {side.id: side for side in before.sides}
    new = {side.id: side for side in after.sides}
    changed = [{"id": side.id, "before": old[side.id].symbol, "after": side.symbol}
               for side in after.sides if side.id in old and side.symbol != old[side.id].symbol]
    profiles_before, profiles_after = _profiles(before), _profiles(after)
    event.update({"changed_old_sides": changed, "changed_old_side_ids": [row["id"] for row in changed],
                  "line_profiles_before": profiles_before, "line_profiles_after": profiles_after,
                  "profile_changes": [{"mother": mother, "before": profiles_before.get(mother, []),
                                       "after": profiles_after.get(mother, [])}
                                      for mother in dict.fromkeys([*profiles_before, *profiles_after])
                                      if profiles_before.get(mother) != profiles_after.get(mother)],
                  "new_line_pair": [new[key].symbol for key in child_ids],
                  "new_line_type": sorted(new[key].symbol for key in child_ids),
                  "conflicts": find_conflicts(after.sides, after.width, after.height)})
    inherited = old[parent_id].symbol
    same = [label for label, key in zip(("left", "right"), child_ids) if new[key].symbol == inherited]
    if len(same) == 1:
        event["actual_inherit"] = same[0]
        event["new_name"] = next(new[key].symbol for key in child_ids if new[key].symbol != inherited)


def attempt_profile_cut(state, points, inherit="left", synchronize=False):
    """Attempt full-boundary mex, optionally synchronizing a recognized strip.

    ``inherit`` is relative to the input stroke's direction, with screen y down.
    A successful bounded-mex step never renames old sides. Only a mex above four
    can trigger the separate minimum-old-change strip policy; that policy may
    choose a different inherited child, recorded explicitly as actual_inherit.

    Return statuses are split, blocked_sync_required, and outside_scope. Blocked
    states remain unchanged, while proposed_state retains the unbounded-mex
    diagnostic. Invalid/conflicting old states raise ValueError. No blocked
    result claims that a fifth name is necessary after permitted renaming.
    """
    if inherit not in ("left", "right"):
        raise ValueError("inherit must be left or right")
    if type(synchronize) is not bool:
        raise ValueError("synchronize must be a boolean")
    _validate_state(state)

    # Reuse ONLY the rectangle/port construction. Its endpoint-only proposed
    # names, selected t, conflict status and repair diagnostics are discarded.
    geometry = attempt_cut(state, points, inherit=inherit)
    if geometry["status"] == "outside_scope":
        return {"status": "outside_scope", "state": state,
                "event": {"method": "complete_boundary_mex", "reason": geometry["event"]["reason"],
                          "requested_inherit": inherit, "inherit": inherit,
                          "scope": "one axis-aligned cut across one rectangular side"}}
    raw_event = geometry["event"]
    parent_id = raw_event["parent"]
    parent = next(side for side in state.sides if side.id == parent_id)
    child_ids = (parent_id + ".l", parent_id + ".r")
    if set(child_ids) & {side.id for side in state.sides}:
        return {"status": "outside_scope", "state": state,
                "event": {"method": "complete_boundary_mex", "reason": "child side identities are not fresh",
                          "requested_inherit": inherit, "inherit": inherit}}
    geometric = geometry["proposed_state"]
    untouched = tuple(side for side in state.sides if side.id != parent_id)
    new_id = child_ids[1 if inherit == "left" else 0]
    new_child = next(side for side in geometric.sides if side.id == new_id)
    contacts = boundary_contacts(new_child, untouched, state.width, state.height)
    retained = sorted({contact["symbol"] for contact in contacts})
    t = choose_inherited_name(parent.symbol, retained)
    children = tuple(RectSide(side.id, side.bounds, t if side.id == new_id else parent.symbol)
                     for side in geometric.sides if side.id in child_ids)
    proposed = RectState(state.width, state.height, untouched + children, geometric.cuts)
    event = {"method": "complete_boundary_mex", "cut": raw_event["cut"], "parent": parent_id,
             "inherited_name": parent.symbol, "s": parent.symbol, "requested_inherit": inherit,
             "inherit": inherit, "ports": raw_event["ports"],
             "endpoint_retained": raw_event["endpoint_retained"],
             "contacts": contacts, "full_boundary_retained": retained, "R": retained, "t": t,
             "diagnostic_new_name": t, "new_name": t,
             "sync_requested": synchronize, "sync_attempted": False,
             "scope": "complete boundary restrictions for this rectangular cut; not a general four-color proof"}
    _finish_event(event, state, proposed, parent_id, child_ids)
    if event["conflicts"]:
        raise AssertionError("complete-boundary mex unexpectedly violated an old-boundary constraint")
    if t <= 4:
        _validate_state(proposed)
        return {"status": "split", "state": proposed, "proposed_state": proposed, "event": event}

    event["blocked_reason"] = "frozen old names make this mex exceed four; synchronization is required"
    if not synchronize:
        return {"status": "blocked_sync_required", "state": state,
                "proposed_state": proposed, "event": event}
    event["sync_attempted"] = True
    family, reason = _recognize_transition(state, proposed, parent_id, child_ids)
    if family is None:
        event["sync_scope_reason"] = reason
        return {"status": "blocked_sync_required", "state": state,
                "proposed_state": proposed, "event": event}

    anchor = family["anchor"]
    abstract = StripChain(SideClass("outside", 0), SideClass(anchor.id, anchor.symbol - 1),
                          tuple(SideClass(side.id, side.symbol - 1) for side in family["old_chain"]))
    exchange = split_strip_chain(abstract, family["split_index"], child_ids=family["child_ids"])
    assigned = {side.side_id: side.symbol + 1 for side in exchange.after.chain}
    synchronized = RectState(state.width, state.height,
                             tuple(RectSide(side.id, side.bounds, assigned.get(side.id, side.symbol))
                                   for side in proposed.sides), proposed.cuts)
    _validate_state(synchronized)
    event["method"] = "verified_strip_sync"
    event["diagnostic_blocked_reason"] = event.pop("blocked_reason")
    event["scope"] = "verified same-anchor geometric K2 join P_n split only; unsupported maps remain blocked"
    event["synchronization"] = {
        "axis": family["axis"], "anchor_id": anchor.id, "anchor_symbol": anchor.symbol,
        "outside_symbol": 1, "old_chain": [side.id for side in family["old_chain"]],
        "new_chain": [side.id for side in family["new_chain"]],
        "split_index": family["split_index"], "geometric_child_ids": list(family["child_ids"]),
        "old_edges": family["old_edges"], "new_edges": family["new_edges"],
        "exact_adjacency_checked": True, "swapped_segment": exchange.swapped_segment,
        "swapped_geometric_side": (exchange.swapped_segment if family["axis"] == "horizontal" else
                                   "up" if exchange.swapped_segment == "left" else "down"),
        "swapped_ids": list(exchange.swapped_ids),
        "changed_old_ids": list(exchange.changed_old_ids),
        "minimum_old_changes": min(family["split_index"] - 1,
                                   len(family["old_chain"]) - family["split_index"]),
        "tie_rule": "geometric left/up", "anchors_preserved": True,
    }
    _finish_event(event, state, synchronized, parent_id, child_ids)
    if event["conflicts"]:
        raise AssertionError("verified strip synchronization produced a naming conflict")
    return {"status": "split", "state": synchronized, "proposed_state": synchronized,
            "diagnostic_proposed_state": proposed, "event": event}

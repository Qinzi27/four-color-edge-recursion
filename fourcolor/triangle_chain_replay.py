"""Replay existing naming policies on genuine staggered-strip cut histories.

The geometric family supplies only rectangle boundaries and a last pending cut.
Its hand-specified difficult coloring is never used to choose a policy name.
Each run starts with the existing single-rectangle initial state and stops at
the first unsuccessful transaction.  This adapter adds no coloring search,
Kempe repair, retry with a different inheritance direction, or hidden fallback.
"""

from __future__ import annotations

from copy import deepcopy

from .anchor_forest import attempt_forest_cut
from .inherited_names import initial_state
from .retained_profiles import attempt_profile_cut
from .triangle_chain_family import verify_staggered_geometry


POLICIES = {
    "plain": ["fourcolor.inherited_names.initial_state",
              "fourcolor.retained_profiles.attempt_profile_cut(synchronize=False)"],
    "strip": ["fourcolor.inherited_names.initial_state",
              "fourcolor.retained_profiles.attempt_profile_cut(synchronize=True)"],
    "forest": ["fourcolor.inherited_names.initial_state",
               "fourcolor.anchor_forest.attempt_forest_cut"],
}


def build_history_variant(family, *, row_order="lower_first",
                          horizontal_reverse=False, vertical_reverse=False,
                          isolate_order="left_to_right"):
    """Return valid cuts in family coordinates, preserving its final geometry.

    Rows may be completed in either order.  Within each row, peel rectangles
    from its left or right end, keeping the union of v0 and v2 intact until the
    final cut.  Direction flags reverse stroke endpoints, not the geometry.
    Every entry retains exact parent/child bounds for an independent replay.
    """
    if row_order not in ("lower_first", "upper_first"):
        raise ValueError("row_order must be lower_first or upper_first")
    if isolate_order not in ("left_to_right", "right_to_left"):
        raise ValueError("isolate_order must be left_to_right or right_to_left")
    if type(horizontal_reverse) is not bool or type(vertical_reverse) is not bool:
        raise ValueError("stroke reversal flags must be booleans")
    verify_staggered_geometry(family)
    bounds = family["bounds"][:]
    daughters = family["problem"]["daughters"]
    before = {key: box[:] for key, box in family["rectangles"].items()
              if key not in daughters}
    before["parent"] = family["parent_rectangle"][:]
    active, history = {"box": bounds}, []

    def cut(parent, axis, at, children, *, final=False):
        """Split one actual active box and retain exact geometry evidence."""
        box = active.pop(parent)
        coordinate = 0 if axis == "x" else 2
        if not box[coordinate] < at < box[coordinate + 1]:
            raise AssertionError("variant cut is not inside its active parent")
        first, second = box[:], box[:]
        first[coordinate + 1], second[coordinate] = at, at
        if axis == "x":
            points = [[at, box[2]], [at, box[3]]]
            reverse = vertical_reverse
        else:
            points = [[box[0], at], [box[1], at]]
            reverse = horizontal_reverse
        if reverse:
            points.reverse()
        active.update(zip(children, (first, second)))
        history.append({"step": len(history) + 1, "parent": parent,
                        "parent_bounds": box, "axis": axis, "at": at,
                        "children": list(children),
                        "children_bounds": [first, second],
                        "points": points, "is_final_split": final})

    cut("box", "y", 1, ("row_lower", "row_upper"))
    rows = (("lower", 0), ("upper", 1))
    if row_order == "upper_first":
        rows = rows[::-1]
    reverse = isolate_order == "right_to_left"
    for row, y in rows:
        pieces = sorted((key for key, box in before.items() if box[2] == y),
                        key=lambda key: before[key][0], reverse=reverse)
        source = f"row_{row}"
        for index, side in enumerate(pieces[:-1]):
            remainder = (pieces[-1] if index == len(pieces) - 2 else
                         f"remainder_{row}_{index}")
            at = before[side][0 if reverse else 1]
            children = (remainder, side) if reverse else (side, remainder)
            cut(source, "x", at, children)
            source = remainder
    cut("parent", "x", 1, daughters, final=True)
    if active != family["rectangles"]:
        raise AssertionError("history variant changed the final rectangles")
    return history


def _state_snapshot(state, offset):
    """Convert positive-name RectState data to literal 0..3 family coordinates."""
    left, bottom = offset

    def integer(value):
        """This exact-coordinate family must not silently round new geometry."""
        result = int(value)
        if result != value:
            raise AssertionError("policy geometry left the exact integer family")
        return result

    return {"exterior_color": 0, "rectangles": [
        {"id": side.id,
         "bounds": [integer(side.bounds[0] + left), integer(side.bounds[2] + left),
                    integer(side.bounds[1] + bottom), integer(side.bounds[3] + bottom)],
         "color": side.symbol - 1}
        for side in state.sides],
        "cuts": [[[point[0] + left, point[1] + bottom] for point in segment]
                 for segment in state.cuts]}


def _inherited_final(family, snapshot):
    """Read the reached old state's names; never import family.initial colors."""
    by_bounds = {tuple(side["bounds"]): side["color"]
                 for side in snapshot["rectangles"]}
    daughters = family["problem"]["daughters"]
    parent = tuple(family["parent_rectangle"])
    if parent not in by_bounds:
        raise AssertionError("final old state is missing the pending parent")
    result = {"r": 0}
    for side, bounds in family["rectangles"].items():
        key = parent if side in daughters else tuple(bounds)
        if key not in by_bounds:
            raise AssertionError("final old state has a missing rectangle")
        result[side] = by_bounds[key]
    if len(by_bounds) != len(family["rectangles"]) - 1:
        raise AssertionError("final old state has unexpected rectangles")
    return result


def replay_staggered_history(family, *, policy="forest", inherit="left",
                              row_order="lower_first", horizontal_reverse=False,
                              vertical_reverse=False, isolate_order="left_to_right"):
    """Replay one deterministic existing policy, stopping without fallback.

    ``cost_old_changes`` is cumulative changed UNSPLIT old identities across
    committed operations, not the final split's optimum and not a net distance
    from the first rectangle.  All exported colors are source names minus one;
    diagnostic event fields keep their existing positive-name convention.
    """
    if policy not in POLICIES:
        raise ValueError("policy must be plain, strip, or forest")
    if inherit not in ("left", "right"):
        raise ValueError("inherit must be left or right")
    variant = {"row_order": row_order, "isolate_order": isolate_order,
               "horizontal_reverse": horizontal_reverse,
               "vertical_reverse": vertical_reverse}
    history = build_history_variant(family, **variant)
    left, right, bottom, top = family["bounds"]
    offset = left, bottom
    state = initial_state(width=right - left, height=top - bottom)
    initial = _state_snapshot(state, offset)
    events, inherited_final = [], None
    status, stop_reason, block_step = "completed", None, None
    for step in history:
        before = _state_snapshot(state, offset)
        matches = [side for side in before["rectangles"]
                   if side["bounds"] == step["parent_bounds"]]
        if len(matches) != 1:
            raise AssertionError("geometric cut has no unique current policy parent")
        if step["is_final_split"]:
            inherited_final = _inherited_final(family, before)
        points = [[x - left, y - bottom] for x, y in step["points"]]
        if policy == "forest":
            outcome = attempt_forest_cut(state, points, inherit=inherit)
        else:
            outcome = attempt_profile_cut(state, points, inherit=inherit,
                                          synchronize=policy == "strip")
        succeeded = outcome["status"] == "split"
        if not succeeded and outcome["state"] is not state:
            raise AssertionError("a stopped policy changed its committed state")
        next_state = outcome["state"]
        after = _state_snapshot(next_state, offset)
        old_by_id = {side["id"]: side for side in before["rectangles"]}
        changed = [{"id": side["id"], "before": old_by_id[side["id"]]["color"],
                    "after": side["color"]}
                   for side in after["rectangles"] if side["id"] in old_by_id
                   and side["color"] != old_by_id[side["id"]]["color"]]
        diagnostic = {key: deepcopy(value) for key, value in outcome["event"].items()
                      if key not in ("line_profiles_before", "line_profiles_after",
                                     "profile_changes")}
        events.append({"step": step["step"], "operation": deepcopy(step),
                       "status": "split" if succeeded else "blocked",
                       "source_status": outcome["status"], "method": diagnostic["method"],
                       "before": before, "after": after,
                       "actual_parent": matches[0],
                       "actual_children": [side for side in after["rectangles"]
                                           if side["id"] not in old_by_id],
                       "changed_old_sides": changed,
                       "cost_old_changes": len(changed),
                       "diagnostic_positive_names": diagnostic})
        if not succeeded:
            status, block_step = "blocked", step["step"]
            stop_reason = (diagnostic.get("forest_scope_reason") or
                           diagnostic.get("sync_scope_reason") or
                           diagnostic.get("blocked_reason") or diagnostic.get("reason"))
            break
        state = next_state
    return {"family": family["family"], "m": family["m"], "policy": policy,
            "inherit": inherit, "variant": variant, "history": history,
            "source_exact_rule_ids": POLICIES[policy][:],
            "color_convention": "exported color = source positive name - 1",
            "scope": "actual policy replay from one rectangle; no repair fallback",
            "status": status, "stop_step": block_step, "stop_reason": stop_reason,
            "intended_steps": len(history), "committed_steps": len(state.cuts),
            "reached_final_parent": inherited_final is not None,
            "inherited_at_final_if_reached": inherited_final,
            "cost_old_changes": sum(event["cost_old_changes"] for event in events),
            "maximum_step_old_changes": max((event["cost_old_changes"] for event in events), default=0),
            "initial_state": initial, "last_valid_state": _state_snapshot(state, offset),
            "final_state": _state_snapshot(state, offset),
            "trace": events}

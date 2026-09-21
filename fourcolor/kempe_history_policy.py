"""An explicit continuous-history extension using one cost-selected Kempe swap.

The existing forest policy is always tried first, unchanged.  Only an actual
blocked transaction invokes single_kempe_split on its genuine new geometry.
This is a separately named experimental policy, not a change to the published
rule.  It neither searches Kempe sequences nor uses an endpoint-coloring oracle.
When one complete component cannot repair the cut, the history still stops.
"""

from __future__ import annotations

from copy import deepcopy

from .anchor_forest import attempt_forest_cut
from .inherited_names import RectSide, RectState, initial_state
from .kempe_split import single_kempe_split
from .retained_profiles import _adjacency, _finish_event, _validate_state
from .triangle_chain_replay import (
    _inherited_final, _state_snapshot, build_history_variant,
)


POLICY = "forest_then_single_kempe_cost"


def attempt_kempe_history_cut(state, points, inherit="left"):
    """Keep every forest-policy success; repair only its actual blocked cuts.

    Source RectState names are 1..4, while the Kempe core uses literal 0..3.
    Weights count changed UNSPLIT old side identities; both new daughters and
    the exterior have weight zero.  No line-record metadata is synthesized.
    """
    previous = attempt_forest_cut(state, points, inherit=inherit)
    if previous["status"] != "blocked_sync_required":
        return previous
    event = deepcopy(previous["event"])
    proposed = previous["proposed_state"]
    parent_id = event["parent"]
    old = {side.id: side for side in state.sides}
    daughters = [parent_id + ".l", parent_id + ".r"]
    new = {side.id: side for side in proposed.sides}
    if set(new) != (set(old) - {parent_id}) | set(daughters):
        raise AssertionError("candidate geometry is not exactly the pending split")
    if any(new[key] != side for key, side in old.items() if key != parent_id):
        raise AssertionError("blocked geometry changed an unsplit old side")
    if proposed.cuts != state.cuts + (tuple(tuple(p) for p in points),):
        raise AssertionError("candidate geometry does not retain the real cut history")

    # Discard the diagnostic fifth-name assignment.  Both daughters inherit
    # their actual old parent's name on H; only their new mutual edge is absent.
    initial = {"outside": 0, **{
        side.id: (old[parent_id].symbol if side.id in daughters else old[side.id].symbol) - 1
        for side in proposed.sides}}
    edges = [list(edge) for edge in sorted(_adjacency(proposed))
             if set(edge) != set(daughters)]
    problem = {"edges": edges, "initial": initial, "daughters": daughters,
               "fixed": ["outside"],
               "weights": {key: int(key != "outside" and key not in daughters)
                           for key in initial}}
    repair = single_kempe_split(**problem)
    event.update({"kempe_attempted": True, "kempe_status": repair["status"],
                  "diagnostic_previous_method": previous["event"]["method"]})
    extra = {"repair_problem": problem, "repair_result": repair,
             # This entry uses native RectState coordinate order.  The public
             # history adapter converts it to the common family-box convention.
             "repair_rect_state_boxes": {side.id: list(side.bounds) for side in proposed.sides}}
    if repair["selected"] is None:
        event["kempe_stop_reason"] = "no_eligible_single_complete_component"
        return {**previous, **extra, "event": event}

    target = repair["selected"]["target"]
    after = RectState(proposed.width, proposed.height,
                      tuple(RectSide(side.id, side.bounds, target[side.id] + 1)
                            for side in proposed.sides), proposed.cuts)
    _validate_state(after)
    for field in ("blocked_reason", "sync_scope_reason", "forest_scope_reason"):
        if field in event:
            event["diagnostic_" + field] = event.pop(field)
    event.update({"method": "single_kempe_cost",
                  "scope": "single complete two-color component after unchanged forest policy stops",
                  "minimum_change_claim": "only among eligible single-component swaps",
                  "selected_component": list(repair["selected"]["component"]),
                  "selected_color_pair_zero_based": list(repair["selected"]["pair"]),
                  "selected_old_side_cost": repair["selected"]["changed_weight"]})
    _finish_event(event, state, after, parent_id, daughters)
    event["requested_inherit_changed"] = event.get("actual_inherit") != inherit
    if event["conflicts"]:
        raise AssertionError("repaired line profiles contain a naming conflict")
    if len(event["changed_old_sides"]) != repair["selected"]["changed_weight"]:
        raise AssertionError("literal old identity cost differs from Kempe cost")
    return {"status": "split", "state": after, "proposed_state": after,
            "diagnostic_proposed_state": proposed, "event": event, **extra}


def replay_kempe_history(family, *, inherit="left", row_order="lower_first",
                         horizontal_reverse=False, vertical_reverse=False,
                         isolate_order="left_to_right"):
    """Replay the explicitly extended policy from the original single rectangle.

    The supplied difficult initial coloring is never installed.  Repair inputs,
    all six attempts, all admissible candidates, and the chosen target are kept
    so an independent driver can audit every actual state transition.
    """
    if inherit not in ("left", "right"):
        raise ValueError("inherit must be left or right")
    variant = {"row_order": row_order, "isolate_order": isolate_order,
               "horizontal_reverse": horizontal_reverse,
               "vertical_reverse": vertical_reverse}
    history = build_history_variant(family, **variant)
    left, right, bottom, top = family["bounds"]
    offset = left, bottom
    state = initial_state(width=right - left, height=top - bottom)
    start = _state_snapshot(state, offset)
    trace, inherited_final = [], None
    status, stop_step, stop_reason = "completed", None, None
    for operation in history:
        before = _state_snapshot(state, offset)
        matches = [side for side in before["rectangles"]
                   if side["bounds"] == operation["parent_bounds"]]
        if len(matches) != 1:
            raise AssertionError("history has no unique actual parent")
        if operation["is_final_split"]:
            inherited_final = _inherited_final(family, before)
        points = [[x - left, y - bottom] for x, y in operation["points"]]
        outcome = attempt_kempe_history_cut(state, points, inherit=inherit)
        succeeded = outcome["status"] == "split"
        if not succeeded and outcome["state"] is not state:
            raise AssertionError("stalled extended policy changed committed names")
        after = _state_snapshot(outcome["state"], offset)
        old = {side["id"]: side for side in before["rectangles"]}
        changed = [{"id": side["id"], "before": old[side["id"]]["color"],
                    "after": side["color"]}
                   for side in after["rectangles"] if side["id"] in old
                   and old[side["id"]]["color"] != side["color"]]
        diagnostic = {key: deepcopy(value) for key, value in outcome["event"].items()
                      if key not in ("line_profiles_before", "line_profiles_after", "profile_changes")}
        entry = {"step": operation["step"], "status": "split" if succeeded else "blocked",
                 "source_status": outcome["status"], "operation": deepcopy(operation),
                 "before": before, "after": after, "actual_parent": matches[0],
                 "actual_children": [side for side in after["rectangles"] if side["id"] not in old],
                 "method": diagnostic["method"], "changed_old_sides": changed,
                 "cost_old_changes": len(changed), "diagnostic_positive_names": diagnostic}
        if "repair_problem" in outcome:
            entry["repair_problem"] = outcome["repair_problem"]
            entry["repair_result"] = outcome["repair_result"]
            entry["repair_boxes"] = {
                key: [box[0] + left, box[2] + left, box[1] + bottom, box[3] + bottom]
                for key, box in outcome["repair_rect_state_boxes"].items()}
        trace.append(entry)
        if not succeeded:
            status, stop_step = "blocked", operation["step"]
            stop_reason = (diagnostic.get("kempe_stop_reason") or diagnostic.get("forest_scope_reason")
                           or diagnostic.get("blocked_reason") or diagnostic.get("reason"))
            break
        state = outcome["state"]
    final = _state_snapshot(state, offset)
    return {"family": family["family"], "m": family["m"], "policy": POLICY,
            "inherit": inherit, "variant": variant, "history": history,
            "source_exact_rule_ids": ["fourcolor.inherited_names.initial_state",
                "fourcolor.anchor_forest.attempt_forest_cut", "fourcolor.kempe_split.single_kempe_split"],
            "color_convention": "exported color = source positive name - 1",
            "scope": "explicit forest-then-single-Kempe continuous policy; no multistep search",
            "status": status, "stop_step": stop_step, "stop_reason": stop_reason,
            "intended_steps": len(history), "committed_steps": len(state.cuts),
            "reached_final_parent": inherited_final is not None,
            "inherited_at_final_if_reached": inherited_final,
            "cost_old_changes": sum(entry["cost_old_changes"] for entry in trace),
            "maximum_step_old_changes": max((entry["cost_old_changes"] for entry in trace), default=0),
            "kempe_repair_attempts": sum("repair_result" in entry for entry in trace),
            "kempe_repair_successes": sum(entry["method"] == "single_kempe_cost" for entry in trace),
            "initial_state": start, "final_state": final, "last_valid_state": deepcopy(final),
            "trace": trace}

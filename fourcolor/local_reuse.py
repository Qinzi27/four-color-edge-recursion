"""Reuse-first rectangle splits and certified, bounded two-name patches.

The patch theorem is complete only for a GIVEN patch and GIVEN pair with its
exterior fixed. The automatic patch/pair selection below is a deliberately
bounded policy, not a complete four-color solver or global minimum coloring.
No assignments are searched: structural parity and boundary pins fix each
component up to one binary phase. Geometry and mother-line identities persist.
"""

from collections import deque

from .anchor_forest import _copy_simple_adjacency, _state_adjacency
from .inherited_names import RectSide, RectState, attempt_cut
from .retained_profiles import _finish_event, _validate_state

PALETTE = frozenset((1, 2, 3, 4))


def _tree_path(first, second, parents):
    """Return the unique recorded tree path between same-component vertices."""
    def ancestors(vertex):
        path = []
        while vertex is not None:
            path.append(vertex)
            vertex = parents[vertex]
        return path

    left, right = ancestors(first), ancestors(second)
    indices = {vertex: i for i, vertex in enumerate(left)}
    j = next(i for i, vertex in enumerate(right) if vertex in indices)
    return left[:indices[right[j]] + 1] + list(reversed(right[:j]))


def solve_two_name_patch(adjacency, names, patch, pair, old_names=None):
    """Solve a fixed-boundary common-two-name subproblem with certificates.

    ``old_names`` identifies the old, unsplit sides counted in the change cost.
    Missing entries (e.g. the new daughters) have zero cost. With no argument,
    all patch members count. Outside remains 1 and cannot belong to the patch.
    A blocked result means THIS patch/pair cannot work with this fixed boundary.
    It does not mean four-name coloring or a different patch is impossible.
    """
    graph = _copy_simple_adjacency(adjacency)
    names, patch, pair = dict(names), set(patch), tuple(pair)
    if (set(names) != set(graph) or names.get("outside") != 1
            or any(type(c) is not int or c not in PALETTE for c in names.values())):
        raise ValueError("every side needs a name in 1..4 and outside must be 1")
    if not patch or not patch <= set(graph) or "outside" in patch:
        raise ValueError("patch must be nonempty, known, and exclude outside")
    if (len(pair) != 2 or len(set(pair)) != 2
            or any(type(c) is not int or c not in PALETTE for c in pair)):
        raise ValueError("pair must contain two distinct names in 1..4")
    pair = tuple(sorted(pair))
    old = {v: names[v] for v in patch} if old_names is None else dict(old_names)
    if (not set(old) <= set(graph)
            or any(type(c) is not int or c not in PALETTE for c in old.values())):
        raise ValueError("cost references must be known side names in 1..4")
    if any(names[v] == names[w] for v in graph if v not in patch
           for w in graph[v] if w not in patch):
        raise ValueError("the fixed exterior already contains a conflict")

    parity, parents, components = {}, {}, []
    final = dict(names)
    for root in sorted(patch):
        if root in parity:
            continue
        parity[root], parents[root] = 0, None
        queue, members = deque([root]), []
        while queue:
            vertex = queue.popleft()
            members.append(vertex)
            for other in sorted(graph[vertex] & patch):
                if other not in parity:
                    parity[other], parents[other] = 1 - parity[vertex], vertex
                    queue.append(other)
                elif parity[other] == parity[vertex]:
                    cycle = _tree_path(vertex, other, parents) + [vertex]
                    return {"status": "blocked", "reason": "odd_cycle_in_patch",
                            "pair": pair, "patch": sorted(patch), "odd_cycle": cycle,
                            "scope": "infeasible only for this fixed patch and pair"}

        # Map each fixed boundary restriction to a component phase; two opposite
        # demands constitute a concise infeasibility witness, not a search miss.
        allowed, pins = {0, 1}, []
        for vertex in sorted(members):
            for other in sorted(graph[vertex] - patch):
                if names[other] not in pair:
                    continue
                phase = 1 ^ pair.index(names[other]) ^ parity[vertex]
                pin = {"vertex": vertex, "outside_neighbor": other,
                       "outside_name": names[other], "required_phase": phase}
                pins.append(pin)
                allowed &= {phase}
                if not allowed:
                    previous = next(p for p in pins if p["required_phase"] != phase)
                    return {"status": "blocked", "reason": "boundary_phase_conflict",
                            "pair": pair, "patch": sorted(patch),
                            "conflicting_pins": [previous, pin],
                            "connecting_path": _tree_path(previous["vertex"], vertex, parents),
                            "parity": {v: parity[v] for v in sorted(members)},
                            "scope": "infeasible only with the declared fixed boundary"}
        costs = {phase: sum(pair[parity[v] ^ phase] != old[v]
                            for v in members if v in old) for phase in (0, 1)}
        chosen = min(allowed, key=lambda phase: (costs[phase], phase))
        for vertex in members:
            final[vertex] = pair[parity[vertex] ^ chosen]
        components.append({"root": root, "members": sorted(members),
                           "parity": {v: parity[v] for v in sorted(members)},
                           "boundary_pins": pins, "allowed_phases": sorted(allowed),
                           "old_change_costs": costs, "chosen_phase": chosen})

    if any(final[v] == final[w] for v in graph for w in graph[v]):
        raise AssertionError("patch certificate did not satisfy every real boundary")
    changed = sorted(v for v in patch if v in old and old[v] != final[v])
    return {"status": "renamed", "names": final, "pair": pair, "patch": sorted(patch),
            "components": components, "changed_old_ids": changed,
            "minimum_old_changes_in_fixed_patch_pair": len(changed),
            "scope": "minimum old-side changes only with this patch, pair, and exterior fixed"}


def attempt_local_cut(state, points, max_old_sides=3, repair=True):
    """Make one reuse-first decision, then at most one declared local repair.

    Direct candidates are ranked by (new-name introduction, name, child bounds).
    If both sets are empty, shared OLD NEIGHBOR IDENTITIES are fixed interfaces;
    the smallest remaining nonoutside companion q is chosen once. The complete
    {s,q} component containing the two daughters is followed, up to the stated
    number of old sides. An oversized component is rejected, never truncated
    and exchanged. This is structural traversal, not coloring enumeration.
    """
    if type(max_old_sides) is not int or max_old_sides < 0 or type(repair) is not bool:
        raise ValueError("a nonnegative integer budget and boolean repair flag are required")
    _validate_state(state)
    geometry = attempt_cut(state, points, inherit="left")
    if geometry["status"] == "outside_scope":
        return {"status": "outside_scope", "state": state, "event": geometry["event"]}
    proposed, parent_id = geometry["proposed_state"], geometry["event"]["parent"]
    old = {"outside": 1, **{side.id: side.symbol for side in state.sides}}
    child_ids = (parent_id + ".l", parent_id + ".r")
    if set(child_ids) & set(old):
        raise ValueError("new daughter identities must be fresh")
    s, used = old[parent_id], set(old.values())
    graph = _state_adjacency(proposed)
    children = sorted((side for side in proposed.sides if side.id in child_ids), key=lambda c: c.bounds)
    if len(children) != 2:
        raise AssertionError("one cut must produce exactly two daughter identities")
    rows, candidates = [], []
    for child in children:
        contacts = graph[child.id] - set(child_ids)
        retained = sorted({old[v] for v in contacts})
        available = sorted(PALETTE - set(retained) - {s})
        rows.append({"child_id": child.id, "bounds": child.bounds,
                     "old_neighbor_ids": sorted(contacts), "R": retained,
                     "available_names": available})
        candidates.extend(((name not in used, name, child.bounds, child.id) for name in available))
    event = {"method": "reuse_first_direct", "parent": parent_id, "s": s,
             "cut": geometry["event"]["cut"], "candidates": rows,
             "selection_order": ["new_name_introduction", "numeric_name", "child_bounds"],
             "repair_attempted": False, "max_old_sides": max_old_sides}
    if candidates:
        introduced, target, _, new_id = min(candidates)
        assigned = {v: old[v] for v in graph if v not in child_ids}
        assigned.update({v: target if v == new_id else s for v in child_ids})
        event.update({"target": target, "introduced_new_name": introduced, "new_name_child": new_id})
    else:
        event["reason"] = "both_direct_domains_empty"
        if not repair:
            return {"status": "blocked", "state": state, "event": event}
        event["repair_attempted"] = True
        common = set(rows[0]["old_neighbor_ids"]) & set(rows[1]["old_neighbor_ids"])
        options = sorted(PALETTE - {s, 1} - {old[v] for v in common})
        event["fixed_common_interfaces"] = [{"id": v, "name": old[v]} for v in sorted(common)]
        if not options:
            event["reason"] = "no_companion_with_common_interfaces_fixed"
            return {"status": "blocked", "state": state, "event": event}
        q, patch, queue = options[0], set(child_ids), deque(sorted(child_ids))
        event["pair"] = sorted((s, q))
        draft = {v: s if v in child_ids else old[v] for v in graph}
        while queue:
            vertex = queue.popleft()
            for other in sorted(graph[vertex]):
                if other in patch or draft[other] not in (s, q):
                    continue
                # Interior name1 is legal, but its component can reach exterior
                # name1 through a q-side. Never treat the fixed exterior as an
                # editable patch member or let a legal input raise downstream.
                if other == "outside":
                    event.update({"reason": "fixed_outside_reached",
                                  "rejection_edge": [vertex, other],
                                  "rejection_members": sorted(patch),
                                  "rejection_members_complete": False})
                    return {"status": "blocked", "state": state, "event": event}
                patch.add(other)
                if len(patch - set(child_ids)) > max_old_sides:
                    event.update({"reason": "local_budget_exceeded",
                                  "rejection_members": sorted(patch),
                                  "rejection_members_complete": False})
                    return {"status": "blocked", "state": state, "event": event}
                queue.append(other)
        fixed_old = {v: old[v] for v in graph if v in old}
        certificate = solve_two_name_patch(graph, draft, patch, (s, q), fixed_old)
        event["patch_certificate"] = certificate
        if certificate["status"] != "renamed":
            event["reason"] = certificate["reason"]
            return {"status": "blocked", "state": state, "event": event}
        assigned = certificate["names"]
        event["method"] = "bounded_two_name_parity"
        event.pop("reason")

    final = RectState(state.width, state.height,
                      tuple(RectSide(side.id, side.bounds, assigned[side.id]) for side in proposed.sides),
                      proposed.cuts)
    _validate_state(final)
    _finish_event(event, state, final, parent_id, child_ids)
    event["changed_old_count"] = len(event["changed_old_sides"])
    return {"status": "split", "state": final, "event": event}

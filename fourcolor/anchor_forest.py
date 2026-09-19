"""Canonical two-anchor linear-forest synchronization after the fixed policy.

The previous complete-boundary/straight-strip policy is called unchanged.
Only its blocked transitions enter this wider, explicitly recognized family:
the exterior and one unique unsplit old side are universal adjacent anchors,
and deleting both leaves a disjoint union of paths and isolated vertices.

Both anchors keep their old names. Each residual path starts at its smaller
lexicographic endpoint and alternates the two remaining names, beginning with
the smaller name. This is one deterministic construction, not enumeration of
colorings, not a minimum-change claim, and not a general four-color algorithm.
Its path phases may rename unsplit old sides and change the inherited child.
"""

from collections.abc import Mapping

from .inherited_names import RectSide, RectState
from .retained_profiles import (
    _adjacency, _finish_event, _validate_state, attempt_profile_cut,
)


def _copy_simple_adjacency(adjacency):
    """Validate/copy a complete simple undirected graph of side identities."""
    if not isinstance(adjacency, Mapping) or "outside" not in adjacency:
        raise ValueError("adjacency must be a mapping containing the exterior outside")
    if any(not isinstance(vertex, str) or not vertex.strip() for vertex in adjacency):
        raise ValueError("side identities must be nonblank strings")
    graph = {}
    for vertex, values in adjacency.items():
        if isinstance(values, (str, bytes)):
            raise ValueError("each neighbor collection must contain side identities")
        try:
            neighbors = set(values)
        except TypeError as error:
            raise ValueError("neighbor collections must be iterable side identities") from error
        if any(not isinstance(other, str) or other not in adjacency for other in neighbors):
            raise ValueError("every neighbor must name a vertex in the complete graph")
        if vertex in neighbors:
            raise ValueError("self-loops are outside a simple side-adjacency graph")
        graph[vertex] = neighbors
    if any(vertex not in graph[other] for vertex, neighbors in graph.items() for other in neighbors):
        raise ValueError("complete side adjacency must be undirected")
    return graph


def recognize_anchor_paths(adjacency, anchor):
    """Return canonical residual paths iff the graph is K2 join a linear forest.

    Both outside and anchor must meet EVERY other side. Residual degrees above
    two and cycles of either parity are rejected. Isolated sides are one-vertex
    paths. Structural endpoint walking is not coloring search: there is only
    one onward neighbor after removing the predecessor. Missing/unusable anchor
    IDs return None; malformed adjacency raises ValueError.
    """
    graph = _copy_simple_adjacency(adjacency)
    if not isinstance(anchor, str) or anchor == "outside" or anchor not in graph:
        return None
    vertices = set(graph)
    if graph["outside"] != vertices - {"outside"} or graph[anchor] != vertices - {anchor}:
        return None
    anchors = {"outside", anchor}
    residual = {vertex: neighbors - anchors for vertex, neighbors in graph.items()
                if vertex not in anchors}
    if any(len(neighbors) > 2 for neighbors in residual.values()):
        return None

    remaining, paths = set(residual), []
    while remaining:
        endpoints = [vertex for vertex in remaining if len(residual[vertex]) <= 1]
        if not endpoints:
            return None  # Every remaining degree is two: a cycle, not a path.
        vertex, previous, path = min(endpoints), None, []
        while True:
            if vertex not in remaining:
                return None
            remaining.remove(vertex)
            path.append(vertex)
            onward = residual[vertex] - ({previous} if previous is not None else set())
            if not onward:
                break
            if len(onward) != 1:
                return None
            previous, vertex = vertex, next(iter(onward))
        paths.append(path)
    return sorted(paths, key=lambda path: path[0])


def _state_adjacency(state):
    """Recover all real rectangle contacts, never merging equally named sides."""
    graph = {"outside": set(), **{side.id: set() for side in state.sides}}
    for first, second in _adjacency(state):
        graph[first].add(second)
        graph[second].add(first)
    return graph


def _serialized_adjacency(graph):
    """Keep the complete graph in portable deterministic explanatory evidence."""
    return {vertex: sorted(graph[vertex]) for vertex in sorted(graph)}


def _verify_assignment(graph, symbols):
    """Check all recognized constraints before publishing the new state."""
    if set(symbols) != set(graph) or symbols.get("outside") != 1:
        raise AssertionError("canonical naming omitted a side or changed the exterior")
    if any(type(symbol) is not int or not 1 <= symbol <= 4 for symbol in symbols.values()):
        raise AssertionError("canonical two-anchor construction exceeded its four-name bound")
    if any(symbols[first] == symbols[second]
           for first, neighbors in graph.items() for second in neighbors):
        raise AssertionError("canonical naming violates a recognized boundary constraint")


def attempt_forest_cut(state, points, inherit="left"):
    """Preserve old successes; extend only previously blocked legal cuts.

    The public return schema is the previous split / blocked_sync_required /
    outside_scope schema. A blocked result retains the original state object.
    Successful forest synchronization has a valid final proposed_state and a
    separate diagnostic_proposed_state containing the original unbounded mex.
    The diagnostic t is never used as an argument that a fifth name is necessary.
    """
    previous = attempt_profile_cut(state, points, inherit=inherit, synchronize=True)
    event = dict(previous["event"])
    event["forest_attempted"] = False
    result = {**previous, "event": event}
    if previous["status"] != "blocked_sync_required":
        return result

    event["forest_attempted"] = True
    proposed = previous["proposed_state"]
    parent_id = event["parent"]
    child_ids = (parent_id + ".l", parent_id + ".r")
    old_by_id = {side.id: side for side in state.sides}
    new_by_id = {side.id: side for side in proposed.sides}
    # The unchanged old adapter guarantees these identities. Check the contract
    # rather than accidentally accepting an arbitrary graph replacement.
    if set(new_by_id) != (set(old_by_id) - {parent_id}) | set(child_ids):
        raise AssertionError("the geometric proposal is not exactly one old side split")
    if any(new_by_id[key] != side for key, side in old_by_id.items() if key != parent_id):
        raise AssertionError("the frozen-mex proposal modified an unsplit old side")

    old_graph, new_graph = _state_adjacency(state), _state_adjacency(proposed)
    event["old_adjacency"] = _serialized_adjacency(old_graph)
    event["new_adjacency"] = _serialized_adjacency(new_graph)
    candidates = []
    for anchor in sorted(state.sides, key=lambda side: side.id):
        if anchor.id == parent_id:
            continue
        new_paths = recognize_anchor_paths(new_graph, anchor.id)
        if new_paths is not None:
            candidates.append({"id": anchor.id, "symbol": anchor.symbol, "bounds": anchor.bounds,
                               "old_paths": recognize_anchor_paths(old_graph, anchor.id),
                               "new_paths": new_paths})
    event["candidate_anchors"] = candidates
    event["forest_candidate_count"] = len(candidates)
    if len(candidates) != 1:
        if len(candidates) > 1:
            reason = "multiple_anchors_not_chosen"
        elif new_graph["outside"] != set(new_graph) - {"outside"}:
            reason = "outside_not_adjacent_to_every_side"
        else:
            reason = "no_uncut_old_dual_anchor_linear_forest"
        event["forest_scope_reason"] = reason
        event["scope"] = ("No supported unique fixed-anchor linear-forest synchronization; "
                          "this is not an impossibility certificate for four names.")
        return result

    candidate = candidates[0]
    anchor_id, anchor_symbol = candidate["id"], candidate["symbol"]
    remaining_names = sorted({1, 2, 3, 4} - {1, anchor_symbol})
    if len(remaining_names) != 2:
        raise AssertionError("the universal anchor must differ from exterior name 1")
    symbols = {"outside": 1, anchor_id: anchor_symbol}
    for path in candidate["new_paths"]:
        for index, side_id in enumerate(path):
            symbols[side_id] = remaining_names[index % 2]
    _verify_assignment(new_graph, symbols)
    synchronized = RectState(proposed.width, proposed.height,
                             tuple(RectSide(side.id, side.bounds, symbols[side.id])
                                   for side in proposed.sides), proposed.cuts)
    _validate_state(synchronized)

    # Preserve the fifth-name and strip-rejection diagnostics without presenting
    # them as a current block after the broader recognized rule has succeeded.
    if "blocked_reason" in event:
        event["diagnostic_blocked_reason"] = event.pop("blocked_reason")
    if "sync_scope_reason" in event:
        event["diagnostic_strip_scope_reason"] = event.pop("sync_scope_reason")
    event.update({
        "method": "verified_anchor_forest_sync",
        "scope": ("Recognized complete K2-joined linear forest, fixed exterior and unique old anchor; "
                  "no guarantee for maps outside this family or for all later cuts."),
        "anchors": {"outside": 1, anchor_id: anchor_symbol},
        "paths": candidate["new_paths"], "remaining_names": remaining_names,
        "symbols_by_side": symbols,
        "path_start_rule": "lexicographically smaller endpoint; isolated vertex starts itself",
        "phase_rule": "smallest remaining name at every path start, then alternate",
        "minimum_change_claim": False,
        "inheritance_policy": "Only the two anchors are fixed; canonical path phases may change inherited child.",
    })
    _finish_event(event, state, synchronized, parent_id, child_ids)
    inherited_name = old_by_id[parent_id].symbol
    retained_children = [label for label, key in zip(("left", "right"), child_ids)
                         if symbols[key] == inherited_name]
    event["actual_inherit"] = retained_children[0] if len(retained_children) == 1 else None
    event["requested_inherit_changed"] = event["actual_inherit"] != inherit
    event["new_name"] = (next(symbols[key] for key in child_ids if symbols[key] != inherited_name)
                         if len(retained_children) == 1 else None)
    if event["conflicts"]:
        raise AssertionError("recognized anchor-forest synchronization produced a conflict")
    return {"status": "split", "state": synchronized, "proposed_state": synchronized,
            "diagnostic_proposed_state": proposed, "event": event}

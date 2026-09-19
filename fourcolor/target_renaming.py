"""Schedule atomic renamings toward an already supplied proper target.

Vertices denote side-consistency classes of an abstract inequality graph,
not primal geometric vertices or individual line-side records. This module
does not find a target coloring. Each changed class moves directly to its
target symbol exactly once, with old edges checked *between* atomic batches.
Added edges are committed only after the target has been reached.

The dependency digraph is the known colour-shift digraph construction (see
arXiv:2204.07928v3, Definition 4). Strongly connected components describe the
smallest possible maximum atomic batch in this restricted scheduling model;
this is not a claim of a new general graph-coloring theorem.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class TargetRenamingPlan:
    """Immutable input copies and a deterministic dependency-first schedule.

``dependencies`` contains (u, v) when v must finish no later than u.
``components`` partitions only the changed classes, in vertex input order.
``batches`` uses one SCC per batch; independent SCCs may also be merged.
Thus this schedule minimizes the largest batch, not the number of batches:
without a capacity restriction, all changed classes can always move at once.
"""

    vertices: tuple[str, ...]
    initial_symbols: tuple[int, ...]
    target_symbols: tuple[int, ...]
    base_edges: tuple[tuple[str, str], ...]
    added_edges: tuple[tuple[str, str], ...]
    fixed_ids: tuple[str, ...]
    changed_ids: tuple[str, ...]
    dependencies: tuple[tuple[str, str], ...]
    components: tuple[tuple[str, ...], ...]
    batches: tuple[tuple[str, ...], ...]
    weights: tuple[int, ...]
    minimum_max_batch_size: int
    minimum_max_batch_weight: int


def _copy_symbols(symbols: Mapping[str, int], label: str) -> dict[str, int]:
    """Copy a nonempty symbol mapping without conflating bools with integers."""
    if not isinstance(symbols, Mapping) or not symbols:
        raise ValueError(f"{label} must be a nonempty mapping")
    copied = dict(symbols)
    if any(not isinstance(vertex, str) or not vertex.strip() for vertex in copied):
        raise ValueError("vertex IDs must be nonblank strings")
    if any(type(symbol) is not int or not 0 <= symbol <= 3 for symbol in copied.values()):
        raise ValueError("symbols must be integers in 0..3, excluding bools")
    return copied


def _edges(
    edges: Iterable[tuple[str, str]], positions: Mapping[str, int], label: str
) -> tuple[tuple[str, str], ...]:
    """Normalize undirected duplicate edges while retaining first-seen order."""
    if isinstance(edges, (str, bytes)):
        raise ValueError(f"{label} must be an iterable of endpoint pairs")
    normalized: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    try:
        for edge in edges:
            if isinstance(edge, (str, bytes)):
                raise ValueError(f"{label} must contain endpoint pairs")
            pair = tuple(edge)
            if len(pair) != 2:
                raise ValueError("every edge must have exactly two endpoints")
            left, right = pair
            if (not isinstance(left, str) or not isinstance(right, str)
                    or left not in positions or right not in positions):
                raise ValueError("edge endpoints must be known vertex IDs")
            if left == right:
                raise ValueError("self-loops are not allowed")
            if positions[left] > positions[right]:
                left, right = right, left
            canonical = (left, right)
            if canonical not in seen:
                normalized.append(canonical)
                seen.add(canonical)
    except TypeError as error:
        raise ValueError(f"{label} must be an iterable of endpoint pairs") from error
    return tuple(normalized)


def _fixed_ids(fixed: Iterable[str], vertices: tuple[str, ...]) -> tuple[str, ...]:
    """Validate fixed class identities, normalize duplicates, and copy them."""
    if isinstance(fixed, (str, bytes)):
        raise ValueError("fixed must be an iterable of vertex IDs, not one string")
    known = set(vertices)
    try:
        supplied = tuple(fixed)
    except TypeError as error:
        raise ValueError("fixed must be an iterable of vertex IDs") from error
    if any(not isinstance(vertex, str) or vertex not in known for vertex in supplied):
        raise ValueError("fixed must contain only known vertex IDs")
    fixed_set = set(supplied)
    return tuple(vertex for vertex in vertices if vertex in fixed_set)


def _is_proper(symbols: Mapping[str, int], edges: Iterable[tuple[str, str]]) -> bool:
    """Check actual inequality constraints, independent of dependency data."""
    return all(symbols[left] != symbols[right] for left, right in edges)


def _strong_components(
    vertices: tuple[str, ...], dependencies: tuple[tuple[str, str], ...]
) -> tuple[tuple[tuple[str, ...], ...], dict[str, int]]:
    """Run iterative Kosaraju in O(V+E), avoiding Python recursion limits."""
    outgoing = {vertex: [] for vertex in vertices}
    incoming = {vertex: [] for vertex in vertices}
    for source, target in dependencies:
        outgoing[source].append(target)
        incoming[target].append(source)

    # Explicit iterator frames reproduce depth-first finishing order in O(E).
    visited: set[str] = set()
    finished: list[str] = []
    for start in vertices:
        if start in visited:
            continue
        visited.add(start)
        stack = [(start, iter(outgoing[start]))]
        while stack:
            vertex, neighbors = stack[-1]
            neighbor = next(neighbors, None)
            if neighbor is None:
                finished.append(vertex)
                stack.pop()
            elif neighbor not in visited:
                visited.add(neighbor)
                stack.append((neighbor, iter(outgoing[neighbor])))

    raw_component: dict[str, int] = {}
    for start in reversed(finished):
        if start in raw_component:
            continue
        component_id = len(raw_component)
        raw_component[start] = component_id
        pending = [start]
        while pending:
            vertex = pending.pop()
            for neighbor in incoming[vertex]:
                if neighbor not in raw_component:
                    raw_component[neighbor] = component_id
                    pending.append(neighbor)

    # Stable component/member ordering uses a linear scan, not string sorting.
    grouped: dict[int, list[str]] = {}
    for vertex in vertices:
        grouped.setdefault(raw_component[vertex], []).append(vertex)
    components = tuple(tuple(group) for group in grouped.values())
    membership = {vertex: index for index, group in enumerate(components) for vertex in group}
    return components, membership


def plan_target_renaming(
    edges: Iterable[tuple[str, str]],
    initial: Mapping[str, int],
    target: Mapping[str, int],
    *,
    fixed: Iterable[str] = (),
    added_edges: Iterable[tuple[str, str]] = (),
    weights: Mapping[str, int] | None = None,
) -> TargetRenamingPlan:
    """Find an optimal maximum-size atomic schedule for a *fixed* target.

Both initial and target must be proper on ``edges``. Only the target must
be proper on ``added_edges``. Nonnegative integer weights, when supplied,
must cover every vertex exactly. The default weight is one per vertex.

For a completed set X, old-edge legality holds exactly when X contains
every dependency of its members. Hence an SCC cannot be split across
batches. Processing sink SCCs first meets the resulting size and weighted
lower bounds. This computes no new symbols, intermediate colors, geometry,
or target choices. Runtime and storage are O(V+E) under ordinary hash costs.
"""
    before = _copy_symbols(initial, "initial")
    after = _copy_symbols(target, "target")
    vertices = tuple(before)
    if set(before) != set(after):
        raise ValueError("initial and target must have exactly the same vertex IDs")
    positions = {vertex: index for index, vertex in enumerate(vertices)}
    base = _edges(edges, positions, "edges")
    added = _edges(added_edges, positions, "added_edges")
    fixed_tuple = _fixed_ids(fixed, vertices)
    if any(before[vertex] != after[vertex] for vertex in fixed_tuple):
        raise ValueError("fixed vertices cannot change their symbols")
    if not _is_proper(before, base):
        raise ValueError("initial symbols must be proper on the base edges")
    if not _is_proper(after, base + added):
        raise ValueError("target symbols must be proper on base and added edges")
    if weights is None:
        costs = {vertex: 1 for vertex in vertices}
    else:
        if not isinstance(weights, Mapping) or set(weights) != set(vertices):
            raise ValueError("weights must cover every vertex exactly")
        costs = dict(weights)
        if any(type(cost) is not int or cost < 0 for cost in costs.values()):
            raise ValueError("weights must be nonnegative integers, excluding bools")

    changed = tuple(vertex for vertex in vertices if before[vertex] != after[vertex])
    changed_set = set(changed)
    arcs: list[tuple[str, str]] = []
    for left, right in base:
        # An unchanged endpoint cannot block a changed endpoint: properness of
        # the final target would already exclude that color equality.
        if left in changed_set and right in changed_set:
            if after[left] == before[right]:
                arcs.append((left, right))
            if after[right] == before[left]:
                arcs.append((right, left))
    dependencies = tuple(arcs)
    components, membership = _strong_components(changed, dependencies)

    outgoing = [set() for _ in components]
    incoming: list[list[int]] = [[] for _ in components]
    for source, target_vertex in dependencies:
        source_component, target_component = membership[source], membership[target_vertex]
        if source_component != target_component and target_component not in outgoing[source_component]:
            outgoing[source_component].add(target_component)
            incoming[target_component].append(source_component)
    remaining = [len(neighbors) for neighbors in outgoing]
    ready = deque(index for index, count in enumerate(remaining) if count == 0)
    batches: list[tuple[str, ...]] = []
    while ready:
        component = ready.popleft()
        batches.append(components[component])
        for dependent in incoming[component]:
            remaining[dependent] -= 1
            if remaining[dependent] == 0:
                ready.append(dependent)

    return TargetRenamingPlan(
        vertices=vertices,
        initial_symbols=tuple(before[vertex] for vertex in vertices),
        target_symbols=tuple(after[vertex] for vertex in vertices),
        base_edges=base,
        added_edges=added,
        fixed_ids=fixed_tuple,
        changed_ids=changed,
        dependencies=dependencies,
        components=components,
        batches=tuple(batches),
        weights=tuple(costs[vertex] for vertex in vertices),
        minimum_max_batch_size=max((len(group) for group in components), default=0),
        minimum_max_batch_weight=max(
            (sum(costs[vertex] for vertex in group) for group in components), default=0
        ),
    )


def verify_schedule(plan: TargetRenamingPlan, batches: Iterable[Iterable[str]]) -> bool:
    """Independently replay nonempty atomic batches and check actual edges.

Every changed vertex must occur exactly once; unchanged/fixed vertices must
not occur. Base edges are checked before and after each batch. Added edges
are checked at completion, so their initial conflicts are permitted. The
empty schedule is valid exactly when there are no changes. Dependency/SCC
metadata and claimed optimum values are deliberately not used as an oracle.
"""
    if not isinstance(plan, TargetRenamingPlan) or isinstance(batches, (str, bytes)):
        return False
    try:
        if (len(set(plan.vertices)) != len(plan.vertices)
                or len(plan.initial_symbols) != len(plan.vertices)
                or len(plan.target_symbols) != len(plan.vertices)):
            return False
        current = _copy_symbols(dict(zip(plan.vertices, plan.initial_symbols)), "initial")
        target = _copy_symbols(dict(zip(plan.vertices, plan.target_symbols)), "target")
        positions = {vertex: index for index, vertex in enumerate(plan.vertices)}
        base = _edges(plan.base_edges, positions, "base_edges")
        added = _edges(plan.added_edges, positions, "added_edges")
        fixed = _fixed_ids(plan.fixed_ids, plan.vertices)
        changed = {vertex for vertex in plan.vertices if current[vertex] != target[vertex]}
        if (set(plan.changed_ids) != changed or len(plan.changed_ids) != len(changed)
                or any(vertex in changed for vertex in fixed)
                or not _is_proper(current, base) or not _is_proper(target, base + added)):
            return False
        seen: set[str] = set()
        for batch in batches:
            if isinstance(batch, (str, bytes)):
                return False
            group = tuple(batch)
            if not group:
                return False
            for vertex in group:
                if not isinstance(vertex, str) or vertex not in changed or vertex in seen:
                    return False
                seen.add(vertex)
            # Commit every assignment before inspecting edges; conflicts within
            # an uncommitted partial batch are not intermediate model states.
            for vertex in group:
                current[vertex] = target[vertex]
            if not _is_proper(current, base):
                return False
        return seen == changed and current == target and _is_proper(current, added)
    except (TypeError, ValueError, KeyError):
        return False


def required_atomic_batch(
    plan: TargetRenamingPlan,
    requested: Iterable[str],
    *,
    completed: Iterable[str] = (),
) -> tuple[str, ...]:
    """Return the unique smallest legal next batch containing requested IDs.

The target stays fixed and no temporary colors are allowed. ``completed``
must be a changed-vertex subset whose actual mixed state is proper on the
base graph. Requested vertices must be changed and still unfinished. Their
dependency-reachability closure among unfinished vertices is both necessary
and sufficient. An empty request returns an empty batch after validation.

This is a different question from minimizing the largest batch of a whole
schedule: in u -> v -> w, singleton batches w, v, u suffice, but requesting
u in the *next* batch forces v and w into that same batch. Runtime is O(V+E).
"""
    if not isinstance(plan, TargetRenamingPlan):
        raise ValueError("plan must be a TargetRenamingPlan")
    # Replay a single all-at-once step to validate the actual graph endpoints
    # and symbol data without trusting supplied dependency/SCC metadata.
    all_at_once = (plan.changed_ids,) if plan.changed_ids else ()
    if not verify_schedule(plan, all_at_once):
        raise ValueError("plan does not describe a valid fixed-target problem")
    changed = set(plan.changed_ids)

    def copy_subset(values: Iterable[str], label: str) -> set[str]:
        """Copy identity iterables, rejecting nonchanged or nonstring values."""
        if isinstance(values, (str, bytes)):
            raise ValueError(f"{label} must be an iterable of changed vertex IDs")
        try:
            copied = tuple(values)
        except TypeError as error:
            raise ValueError(f"{label} must be an iterable of changed vertex IDs") from error
        if any(not isinstance(vertex, str) or vertex not in changed for vertex in copied):
            raise ValueError(f"{label} must contain only changed vertex IDs")
        return set(copied)

    done = copy_subset(completed, "completed")
    required = copy_subset(requested, "requested")
    if required & done:
        raise ValueError("requested vertices must not already be completed")
    before = dict(zip(plan.vertices, plan.initial_symbols))
    target = dict(zip(plan.vertices, plan.target_symbols))
    current = {vertex: target[vertex] if vertex in done else before[vertex] for vertex in plan.vertices}
    if not _is_proper(current, plan.base_edges):
        raise ValueError("completed must describe a proper intermediate base-graph state")

    # Reconstruct dependencies from symbols/edges, so this helper shares the
    # verifier's independence from potentially edited explanatory metadata.
    remaining = changed - done
    outgoing: dict[str, list[str]] = {vertex: [] for vertex in remaining}
    for left, right in plan.base_edges:
        if left in remaining and right in remaining:
            if target[left] == before[right]:
                outgoing[left].append(right)
            if target[right] == before[left]:
                outgoing[right].append(left)
    pending = list(required)
    while pending:
        vertex = pending.pop()
        for dependency in outgoing[vertex]:
            if dependency not in required:
                required.add(dependency)
                pending.append(dependency)
    return tuple(vertex for vertex in plan.vertices if vertex in required)

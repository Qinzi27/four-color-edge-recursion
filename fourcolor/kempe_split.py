"""Certify and rank single Kempe swaps for one pending daughter constraint.

Vertices are side-consistency classes in an inequality graph, not geometric
vertices or individual line-side records. The initial coloring must already
be proper on H, with the new daughter edge absent. This module examines the
six complete two-color components rooted at the two equally colored daughters.
It does not search sequences of colorings or solve stalled cases by a fallback.

The swap operation already occurs in the repository's renaming diagnostics.
The additional interface supplies all eligible targets, explicit costs, and
fixed-target SCC scheduling certificates. Optimality is only within this
single-swap family, never over all proper colorings or all repair sequences.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .target_renaming import plan_target_renaming, verify_schedule


def _copy_daughters(daughters: Iterable[str], vertices: tuple[str, ...]) -> tuple[str, str]:
    """Require two distinct known IDs, preserving their supplied seed order."""
    if isinstance(daughters, (str, bytes)):
        raise ValueError("daughters must contain two distinct known vertex IDs")
    try:
        copied = tuple(daughters)
    except TypeError as error:
        raise ValueError("daughters must contain two distinct known vertex IDs") from error
    if (len(copied) != 2
            or any(not isinstance(vertex, str) or vertex not in vertices for vertex in copied)
            or copied[0] == copied[1]):
        raise ValueError("daughters must contain two distinct known vertex IDs")
    return copied


def _copy_records(
    records: Mapping[str, Iterable[str]] | None, vertices: tuple[str, ...]
) -> dict[str, tuple[str, ...]] | None:
    """Copy complete record associations, deduplicating in iterable order.

    A record may belong to several sides: writes are measured by a union,
    not by the sum of per-side counts or by changed XOR edge differences.
    """
    if records is None:
        return None
    if not isinstance(records, Mapping) or set(records) != set(vertices):
        raise ValueError("records_by_side must cover every vertex exactly")
    copied = {}
    for vertex in vertices:
        supplied = records[vertex]
        if isinstance(supplied, (str, bytes)):
            raise ValueError("each records_by_side value must be an iterable of record IDs")
        try:
            values = tuple(supplied)
        except TypeError as error:
            raise ValueError("each records_by_side value must be an iterable of record IDs") from error
        if any(not isinstance(record, str) or not record.strip() for record in values):
            raise ValueError("record IDs must be nonblank strings")
        copied[vertex] = tuple(dict.fromkeys(values))
    return copied


def single_kempe_split(
    edges: Iterable[tuple[str, str]],
    initial: Mapping[str, int],
    daughters: Iterable[str],
    *,
    fixed: Iterable[str] = (),
    weights: Mapping[str, int] | None = None,
    records_by_side: Mapping[str, Iterable[str]] | None = None,
) -> dict:
    """Return all certified single-swap repairs and the least-cost member.

    ``initial`` is a complete proper 0..3 coloring of ``edges``. The two
    daughters are distinct, equally colored, and not already adjacent.
    Each attempt swaps one *complete* component of H induced by their color
    and one alternative color. Components meeting the other daughter or any
    fixed side are reported as blocked. Singleton components are included.

    Candidates are ranked by changed weight, changed side count, changed
    record-union count, input-index component tuple, and color pair. Omitted
    record metadata is reported as None, not as zero observed writes, and
    contributes the same neutral key to every candidate. All side/member
    orders follow ``initial``; record IDs follow the supplied iterable order.

    For a single connected two-color component K, every internal edge gives
    both dependency directions. Its one SCC is K, so the fixed-target optimum
    peak batch size and weight are |K| and weight(K). The existing planner
    derives this certificate, and its independent replay checks actual edges.

    There are exactly six component attempts. With four fixed colors, graph
    work is O(V+E), plus O(R) for supplied record associations, under ordinary
    hashing costs. No planar embedding is assumed or certified by this API.
    """
    # A no-change plan reuses the existing strict input validator, including
    # bool rejection, complete weights, edge normalization, and fixed IDs.
    baseline = plan_target_renaming(edges, initial, initial, fixed=fixed, weights=weights)
    vertices = baseline.vertices
    before = dict(zip(vertices, baseline.initial_symbols))
    base = baseline.base_edges
    fixed_ids = baseline.fixed_ids
    costs = dict(zip(vertices, baseline.weights))
    children = _copy_daughters(daughters, vertices)
    if before[children[0]] != before[children[1]]:
        raise ValueError("daughters must initially have the same color")
    if any(set(edge) == set(children) for edge in base):
        raise ValueError("the pending daughter edge must be absent from edges")
    records = _copy_records(records_by_side, vertices)
    adjacency = {vertex: [] for vertex in vertices}
    for left, right in base:
        adjacency[left].append(right)
        adjacency[right].append(left)
    positions = {vertex: index for index, vertex in enumerate(vertices)}
    inherited_color = before[children[0]]
    attempts = []
    candidates = []

    for seed in children:
        other = children[1] if seed == children[0] else children[0]
        for alternative in range(4):
            if alternative == inherited_color:
                continue
            pair = tuple(sorted((inherited_color, alternative)))
            reached = {seed}
            pending = [seed]
            while pending:
                vertex = pending.pop()
                for neighbor in adjacency[vertex]:
                    if neighbor not in reached and before[neighbor] in pair:
                        reached.add(neighbor)
                        pending.append(neighbor)
            component = tuple(vertex for vertex in vertices if vertex in reached)
            fixed_hits = tuple(vertex for vertex in fixed_ids if vertex in reached)
            blocked = []
            if other in reached:
                blocked.append("contains_other_daughter")
            if fixed_hits:
                blocked.append("contains_fixed_side")
            attempts.append({"seed": seed, "pair": pair, "component": component,
                             "blocked_reasons": tuple(blocked), "fixed_hits": fixed_hits})
            if blocked:
                continue

            target = {vertex: (inherited_color ^ alternative ^ color)
                      if vertex in reached else color for vertex, color in before.items()}
            plan = plan_target_renaming(base, before, target, fixed=fixed_ids,
                                        added_edges=[children], weights=costs)
            if not verify_schedule(plan, plan.batches):
                raise RuntimeError("generated Kempe target failed independent schedule replay")
            # This is an invariant of a complete connected Kempe component,
            # including a singleton; a mismatch must not yield a certificate.
            if plan.components != (component,):
                raise RuntimeError("Kempe component and fixed-target SCC certificate disagree")
            changed_records = (None if records is None else tuple(dict.fromkeys(
                record for vertex in component for record in records[vertex])))
            candidates.append({
                "seed": seed, "pair": pair, "component": component, "target": target,
                "changed_weight": sum(costs[vertex] for vertex in component),
                "changed_side_count": len(component),
                "changed_record_ids": changed_records,
                "changed_record_count": None if changed_records is None else len(changed_records),
                "dependencies": plan.dependencies, "components": plan.components,
                "batches": plan.batches,
                "minimum_max_batch_size": plan.minimum_max_batch_size,
                "minimum_max_batch_weight": plan.minimum_max_batch_weight,
            })

    # At most six keys are compared, so even tuple comparisons remain linear
    # in graph size. Input indices avoid lexical-ID ordering surprises.
    candidates.sort(key=lambda candidate: (
        candidate["changed_weight"], candidate["changed_side_count"],
        candidate["changed_record_count"] if records is not None else 0,
        tuple(positions[vertex] for vertex in candidate["component"]), candidate["pair"],
    ))
    return {
        "status": "repaired" if candidates else "stalled",
        "optimality_scope": "single_complete_two_color_component_swap",
        "candidates": candidates, "selected": candidates[0] if candidates else None,
        "attempts": attempts, "vertices": vertices, "initial": before,
        "base_edges": base, "daughters": children, "fixed": fixed_ids,
        "weights": costs, "records_by_side": records,
    }

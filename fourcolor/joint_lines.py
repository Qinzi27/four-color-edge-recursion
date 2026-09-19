"""Non-branching joint constraints scheduled by whole drawn lines.

The old fixed-minimum experiment remains in weighted_lines.py as a baseline.
Here a line's priority schedules CHECKS, never an arbitrary naming decision.
Only singleton inequality and two-name joint occupancy remove candidates.
Four symbols are an input palette, not a consequence of these rules.
"""

from __future__ import annotations

import random

from .weighted_lines import POLICIES, TIE_BREAKS, line_metadata
from .whole_lines import WholeLineModel


PALETTE = frozenset((1, 2, 3, 4))


def _weight(metadata: dict, domains: list[set[int]], line: str, policy: str) -> int:
    """Retain the three experimental weights, including fully named lines.

    A fully named source line may still constrain a common neighboring shore,
    so unlike the greedy baseline it must not disappear from the worklist.
    """
    if policy == "connections":
        return len(metadata["contacts"][line])
    if policy == "constraints":
        return sum(4 - len(domains[side]) for side, _ in metadata["occurrences"][line]
                   if len(domains[side]) > 1)
    depth = metadata["depths"][line]
    return -depth if depth is not None else -len(metadata["order"])


def run_joint_lines(model: WholeLineModel, policy="constraints", tie_break="forward",
                    seed=None, anchors=None, symbol_symmetry=False) -> dict:
    """Reach a sound candidate fixed point without trial assignments or DFS.

    None anchors means outside=1/first inside=2; an explicit dictionary (even
    empty) supplies ALL initial anchors, addressed by oriented darts. Original
    multi-valued anchors are honored and never replaced by an old coloring.

    If enabled, symbol_symmetry fixes only a representative of globally
    interchangeable unused symbols, AFTER strict propagation reaches closure.
    This preserves existence, not every labeled completion. Its trace is kept
    separate from logically forced removals. Otherwise underdetermined states
    remain underdetermined; they do not certify that a completion exists.
    """
    if policy not in POLICIES or tie_break not in TIE_BREAKS:
        raise ValueError("unknown policy or tie break")
    if tie_break == "random" and type(seed) is not int:
        raise ValueError("random tie breaks require an explicit integer seed")
    if type(symbol_symmetry) is not bool:
        raise ValueError("symbol_symmetry must be a boolean")
    metadata = line_metadata(model)
    plane = model.plane_map
    if anchors is None:
        frame = next(line for line in model.lines if line["id"] == "frame")
        first = frame["spans"][0]["dart"]
        anchors = {first: [1], first ^ 1: [2]}
    if not isinstance(anchors, dict):
        raise ValueError("anchors must be a dictionary of dart candidate lists")
    domains = [set(PALETTE) for _ in plane.faces]
    initial_anchors = {}
    for dart, candidates in anchors.items():
        if type(dart) is not int or not 0 <= dart < len(plane.face_of_dart):
            raise ValueError("anchor dart out of range")
        values = list(candidates)
        if any(type(c) is not int or c not in PALETTE for c in values):
            raise ValueError("anchor symbol outside supplied palette")
        initial_anchors[dart] = sorted(set(values))
        domains[plane.face_of_dart[dart]].intersection_update(values)
    initial_domains = [sorted(d) for d in domains]

    # Every inequality has an actual primal edge as witness. A bridge has one
    # side identity twice and creates NO inequality, even if it is a drawn line.
    neighbors = [set() for _ in domains]
    witnesses = {}
    for edge in range(len(plane.edges)):
        a, b = plane.shores(edge)
        if a == b:
            continue
        if edge not in model.edge_owner:
            raise ValueError("an inequality edge must belong to a real whole line")
        neighbors[a].add(b)
        neighbors[b].add(a)
        witnesses.setdefault(tuple(sorted((a, b))), edge)
    line_edges = {line["id"]: [span["edge"] for span in line["spans"]]
                  for line in model.lines}
    rng = random.Random(seed)
    trace, schedule = [], []
    random_draws = 0
    dirty = set(metadata["order"])

    def select(lines):
        """Select only among equal highest current weights in the worklist."""
        nonlocal random_draws
        weights = {line: _weight(metadata, domains, line, policy)
                   for line in metadata["order"] if line in lines}
        highest = max(weights.values())
        tied = [line for line, weight in weights.items() if weight == highest]
        if tie_break == "reverse":
            chosen = tied[-1]
        elif tie_break == "random" and len(tied) > 1:
            chosen = rng.choice(tied)
            random_draws += 1
        else:
            chosen = tied[0]
        return chosen, highest, tied

    def remove(line, rule, sources, target, symbols, edges, **extra):
        """Record the exact premises BEFORE mutating the target candidates."""
        removed = domains[target] & symbols
        if not removed:
            return
        event = {"rule": rule, "line": line, "sources": list(sources),
                 "source_domains": [sorted(domains[s]) for s in sources],
                 "target": target, "before": sorted(domains[target]),
                 "removed": sorted(removed), "witness_edges": list(edges), **extra}
        domains[target].difference_update(removed)
        event["after"] = sorted(domains[target])
        trace.append(event)

    while all(domains):
        if dirty:
            chosen, weight, tied = select(dirty)
            dirty.remove(chosen)
            start = len(trace)
            for edge in line_edges[chosen]:
                a, b = plane.shores(edge)
                if a == b:
                    continue
                # Singleton propagation handles the union-size-one conflict as
                # well: two adjacent equal singletons make one domain empty.
                for source, target in ((a, b), (b, a)):
                    if len(domains[source]) == 1:
                        remove(chosen, "singleton", [source], target,
                               domains[source], [edge])
                    if not domains[target]:
                        break
                if not domains[a] or not domains[b]:
                    break
                occupied = domains[a] | domains[b]
                if len(occupied) == 2:
                    # a != b is essential: merely having a common neighbor is
                    # NOT enough to conclude that both symbols are occupied.
                    for target in sorted(neighbors[a] & neighbors[b]):
                        remove(chosen, "pair-occupancy", [a, b], target, occupied,
                               [edge, witnesses[tuple(sorted((a, target)))],
                                witnesses[tuple(sorted((b, target)))]])
                        if not domains[target]:
                            break
                if not all(domains):
                    break
            schedule.append({"line": chosen, "weight": weight, "tied_lines": tied,
                             "trace_start": start, "trace_end": len(trace)})
            if len(trace) != start:
                # Conservative dependency invalidation guarantees fairness.
                # It rechecks constraints, never enumerates color assignments.
                dirty = set(metadata["order"])
            continue

        if not symbol_symmetry or all(len(d) == 1 for d in domains):
            break
        used = {next(iter(d)) for d in domains if len(d) == 1}
        unused = PALETTE - used
        # Inspect ALL domains, not just the candidate being normalized. An
        # asymmetric supplied list-anchor could otherwise make this unsound.
        invariant = all(not (d & unused) or unused <= d for d in domains)
        if len(unused) < 2 or not invariant:
            break
        eligible = {line: [(side, dart) for side, dart in metadata["occurrences"][line]
                           if domains[side] == unused] for line in metadata["order"]}
        eligible = {line: occurrences for line, occurrences in eligible.items() if occurrences}
        if not eligible:
            break
        chosen, weight, tied = select(eligible)
        side, dart = eligible[chosen][0]
        symbol = min(unused)
        start = len(trace)
        remove(chosen, "symbol-symmetry", [], side, unused - {symbol}, [],
               unused=sorted(unused), used=sorted(used), dart=dart,
               canonical_symbol=symbol)
        schedule.append({"line": chosen, "weight": weight, "tied_lines": tied,
                         "trace_start": start, "trace_end": len(trace),
                         "phase": "symbol-symmetry"})
        dirty = set(metadata["order"])

    status = ("conflict" if not all(domains) else
              "solved" if all(len(d) == 1 for d in domains) else "underdetermined")
    symmetry_steps = [event for event in trace if event["rule"] == "symbol-symmetry"]
    return {"status": status, "domains": [sorted(d) for d in domains],
            "initial_domains": initial_domains, "anchors_by_dart": initial_anchors,
            "palette": sorted(PALETTE), "policy": policy, "tie_break": tie_break,
            "seed": seed if tie_break == "random" else None,
            "symbol_symmetry": symbol_symmetry, "trace": trace, "schedule": schedule,
            "symmetry_choices": len(symmetry_steps), "choices": len(symmetry_steps),
            "non_symmetry_choices": 0, "backtracks": 0, "random_draws": random_draws,
            "removed_candidates": sum(len(event["removed"]) for event in trace),
            "scope": "Whole-line singleton and adjacent-pair occupancy closure; optional global unused-symbol normalization, never trial naming."}

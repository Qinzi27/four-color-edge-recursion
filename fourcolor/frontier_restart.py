"""Experimental line-side urgency and small-clique candidate filtering.

This keeps Qinzi27's geometry-only restart and whole-mother interval names.
The urgency idea is related to minimum remaining values / DSATUR; the optional
Hall filter is a restricted all-different propagator, NOT a new theorem or a
full implementation of Regin's matching algorithm. Four is an input palette.
No alternate assignment is tried and no previous coloring is accepted.
"""

from itertools import combinations

from .closed_support import supported_cycle_units
from .global_restart import current_segments
from .whole_lines import build_whole_lines, propagate_candidates


POLICIES = ("anchored-pressure", "tight-frontier", "tight-degree", "tight-hall")


def neighbor_sets(model):
    """Deduplicate actual opposite shores; bridges add no inequality to self."""
    neighbors = [set() for _ in model.plane_map.faces]
    for edge in range(len(model.plane_map.edges)):
        a, b = model.plane_map.shores(edge)
        if a != b:
            neighbors[a].add(b)
            neighbors[b].add(a)
    return neighbors


def small_cliques(neighbors):
    """Find only genuine pairwise-adjacent triples/quads, not arbitrary cycles.

    A primal junction is not itself an all-different constraint: at an X,
    opposite shores can reuse a name. These cliques belong to the shore
    adjacency graph (the loopless simple dual), not the primal drawing.
    """
    cliques = []
    for a, adjacent in enumerate(neighbors):
        for b in sorted(v for v in adjacent if v > a):
            common = adjacent & neighbors[b]
            for c in sorted(v for v in common if v > b):
                cliques.append((a, b, c))
                for d in sorted(v for v in common & neighbors[c] if v > c):
                    cliques.append((a, b, c, d))
    return sorted(cliques)


def propagate_hall(model, anchors, cliques=None):
    """Apply sound necessary conditions to a fixed point, never color branches.

    In a true clique K, all members of S must have distinct names. If their
    candidate union U is too small, these anchors are inconsistent. If |U|=|S|,
    S must exhaust U, so K minus S cannot use U. Subsets have size at most four;
    enumerating these constraint subsets is NOT enumerating color assignments.
    Consistency of these local checks does not imply global extendibility.
    """
    base = propagate_candidates(model, anchors)
    if base["status"] == "conflict":
        return base
    domains = [set(d) for d in base["domains"]]
    neighbors = neighbor_sets(model)
    cliques = small_cliques(neighbors) if cliques is None else cliques
    # A caller-supplied cache must never add an unsound all-different relation.
    for clique in cliques:
        if len(set(clique)) != len(clique) or len(clique) not in (3, 4):
            raise ValueError("expected a distinct three/four-shore clique")
        if any(not 0 <= v < len(domains) for v in clique):
            raise ValueError("clique shore out of range")
        if any(b not in neighbors[a] for a, b in combinations(clique, 2)):
            raise ValueError("Hall constraint requires pairwise shared boundaries")
    trace = list(base["trace"])
    conflict = None
    changed = True
    while changed and all(domains) and conflict is None:
        changed = False
        # The explicit repeat-scan keeps the small-filter proof transparent.
        for a, adjacent in enumerate(neighbors):
            if len(domains[a]) != 1:
                continue
            for b in sorted(adjacent):
                removed = domains[b] & domains[a]
                if removed:
                    domains[b] -= removed
                    changed = True
                    trace.append({"rule": "singleton", "from_side": a,
                                  "to_side": b, "removed": sorted(removed)})
                    if not domains[b]:
                        break
            if not all(domains):
                break
        if not all(domains):
            break
        for clique in cliques:
            for size in range(2, len(clique) + 1):
                for subset in combinations(clique, size):
                    union = set().union(*(domains[v] for v in subset))
                    if len(union) < size:
                        conflict = {"rule": "hall-deficiency", "clique": list(clique),
                                    "subset": list(subset), "union": sorted(union),
                                    "subset_domains": [sorted(domains[v]) for v in subset]}
                        trace.append(conflict)
                        break
                    if len(union) != size:
                        continue
                    for other in clique:
                        if other in subset:
                            continue
                        removed = domains[other] & union
                        if removed:
                            trace.append({"rule": "hall-reservation", "clique": list(clique),
                                          "subset": list(subset), "union": sorted(union),
                                          "subset_domains": [sorted(domains[v]) for v in subset],
                                          "to_side": other, "removed": sorted(removed)})
                            domains[other] -= union
                            changed = True
                    if not all(domains):
                        break
                if conflict is not None or not all(domains):
                    break
            if conflict is not None or not all(domains):
                break
    status = ("conflict" if conflict is not None or not all(domains) else
              "solved" if all(len(d) == 1 for d in domains) else "underdetermined")
    return {"status": status, "domains": [sorted(d) for d in domains], "trace": trace,
            "hall_conflict": conflict, "backtracks": 0, "choices": 0, "palette": [1, 2, 3, 4]}


def frontier_priorities(units, domains, neighbors, cycle_support, degree=False,
                        anchored=False):
    """Score the most urgent occurrence of each current mother interval first.

    Old q aggregates unresolved sides and can tie two loose sides with one
    tight side. Urgency is instead 4-|D| of the selected occurrence. The
    optional degree counts DISTINCT unresolved adjacent shore identities, not
    duplicate boundary edges, already known colors, or endpoint colors.
    """
    rows = []
    for unit in units:
        unknown = [(s, d) for s, d in unit["occurrences"] if len(domains[s]) > 1]
        if not unknown:
            continue

        def individual(side):
            """No color candidate is tested while calculating a scheduling key."""
            urgency = 4 - len(domains[side])
            residual = sum(len(domains[n]) > 1 for n in neighbors[side])
            return (urgency, residual) if degree else (urgency,)

        # max is stable: same individual score retains geometric occurrence order.
        side, dart = (unknown[0] if anchored else
                      max(unknown, key=lambda item: individual(item[0])))
        q = sum(4 - len(domains[s]) for s, _ in unknown)
        q_all = sum(4 - len(domains[s]) for s, _ in unit["occurrences"])
        support = cycle_support[unit["id"]]
        priority = ((q_all, int(support["supported"])) if anchored else
                    individual(side) + (q, int(support["supported"])))
        rows.append({"unit": unit["id"], "mother": unit["mother"],
                     "side": side, "dart": dart, "unresolved_shores": [s for s, _ in unknown],
                     "urgency": 4 - len(domains[side]),
                     "unresolved_neighbors": sum(len(domains[n]) > 1 for n in neighbors[side]),
                     "constraint_weight": q, "including_named_weight": q_all,
                     "closed_support": support, "priority": priority})
    return rows


def restart_frontier_names(geometry, policy="tight-hall"):
    """One fresh deterministic run; retain failure, no retry or oracle fallback.

    Call on the entire current geometry after each new stroke. Whole lines and
    their local sides remain the naming/output objects. The scheduling pressure
    is derived from shore adjacency, which is mathematically dual-graph data;
    presenting it through lines is not claimed as an independent new principle.
    """
    if policy not in POLICIES:
        raise ValueError("unknown frontier policy")
    model = build_whole_lines(geometry)
    frame = next((line for line in model.lines if line["id"] == "frame"), None)
    if frame is None:
        raise ValueError("restart requires an explicit rectangular outer frame")
    first = frame["spans"][0]["dart"]
    anchors = {first: [1], first ^ 1: [2]}
    initial = dict(anchors)
    units = current_segments(model)
    by_id = {unit["id"]: unit for unit in units}
    neighbors = neighbor_sets(model)
    cliques = small_cliques(neighbors) if policy == "tight-hall" else []

    def propagate():
        """Re-derive only from current-run commitments, not former geometry colors."""
        return (propagate_hall(model, anchors, cliques) if policy == "tight-hall"
                else propagate_candidates(model, anchors))

    outcome = propagate()
    trace = []
    hall_events = sum(row.get("rule") == "hall-reservation" for row in outcome["trace"])
    while outcome["status"] == "underdetermined":
        support = supported_cycle_units(model, outcome["domains"], units)
        rows = frontier_priorities(units, outcome["domains"], neighbors, support,
                                   degree=policy in ("tight-degree", "tight-hall"),
                                   anchored=policy == "anchored-pressure")
        if not rows:
            raise AssertionError("unresolved shore has no real-line occurrence")
        highest = max(row["priority"] for row in rows)
        tied = sorted((r for r in rows if r["priority"] == highest),
                      key=lambda r: (r["mother"], by_id[r["unit"]]["t0"]))
        chosen = tied[0]
        domain = outcome["domains"][chosen["side"]]
        used = {d[0] for d in outcome["domains"] if len(d) == 1}
        symbol = min(domain, key=lambda c: (c not in used, c))
        trace.append({**chosen, "domain": domain, "used_names": sorted(used), "symbol": symbol,
                      "tied_units": [r["unit"] for r in tied]})
        anchors[chosen["dart"]] = [symbol]
        outcome = propagate()
        hall_events += sum(row.get("rule") == "hall-reservation" for row in outcome["trace"])
    return {"status": outcome["status"], "policy": policy, "domains": outcome["domains"],
            "anchors_by_dart": anchors, "initial_anchors_by_dart": initial,
            "units": units, "trace": trace, "choices": len(trace), "backtracks": 0,
            "propagation_trace": outcome["trace"], "hall_conflict": outcome.get("hall_conflict"),
            "hall_derivation_events_including_recomputations": hall_events,
            "conflict_propagation": outcome["trace"] if outcome["status"] == "conflict" else [],
            "colors": [d[0] for d in outcome["domains"]] if outcome["status"] == "solved" else None,
            "old_colors_read": False, "local_budget": None,
            "scope": "Experimental fixed four-name palette; no alternative assignment retries."}

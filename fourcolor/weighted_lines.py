"""Experimental whole-line scheduling with three explicit priority definitions.

The geometry is fixed and old names are cleared. This tests a COMBINED rule:
choose a highest-weight whole line, scan its ordered shore profile, commit the
smallest available symbol, then propagate. It never retries a color or a line.
It is not a proof about all possible renaming rules or about four-colorability.
"""

from collections import deque
import random

from .whole_lines import WholeLineModel, propagate_candidates


POLICIES = ("connections", "constraints", "outer-layer")
TIE_BREAKS = ("forward", "reverse", "random")


def line_metadata(model: WholeLineModel) -> dict:
    """Count distinct line contacts, ordered distinct shores and frame distances.

    No atomic-span multiplicity contributes to weights. A disconnected island
    has no contact path to the frame; depth=None, below every rooted line.
    These BFS depths are an explicit geometric proxy, NOT a claimed unique
    historical mother/child genealogy. Virtual connectors never count as lines.
    """
    contacts, occurrences = {}, {}
    for line in model.lines:
        identifier = line["id"]
        contacts[identifier] = sorted({port[0] for event in line["events"]
                                      for port in event["ports_ccw"] if port[0] != identifier})
        seen, ordered = set(), []
        for span in line["spans"]:
            for dart in (span["dart"], span["dart"] ^ 1):
                side = model.plane_map.face_of_dart[dart]
                if side not in seen:
                    seen.add(side)
                    ordered.append((side, dart))
        occurrences[identifier] = ordered
    if "frame" not in contacts:
        raise ValueError("weighted restart requires an explicit frame")
    depths = {identifier: None for identifier in contacts}
    depths["frame"] = 0
    queue = deque(["frame"])
    while queue:
        identifier = queue.popleft()
        for other in contacts[identifier]:
            if depths[other] is None:
                depths[other] = depths[identifier] + 1
                queue.append(other)
    return {"contacts": contacts, "occurrences": occurrences, "depths": depths,
            "order": [line["id"] for line in model.lines]}


def priority_candidates(metadata: dict, domains: list, policy: str) -> list[dict]:
    """Recompute weights for WHOLE lines that still have at least one unknown.

    constraints = sum(4 - candidate_count) over distinct unresolved shores.
    Thus forbidding one symbol twice does not create two independent bans.
    outer-layer uses -depth, so larger priorities still mean earlier processing.
    """
    if policy not in POLICIES:
        raise ValueError("unknown whole-line policy")
    rows = []
    for identifier in metadata["order"]:
        unknown = [side for side, _ in metadata["occurrences"][identifier] if len(domains[side]) > 1]
        if not unknown:
            continue
        if policy == "connections":
            weight = len(metadata["contacts"][identifier])
        elif policy == "constraints":
            weight = sum(4 - len(domains[side]) for side in unknown)
        else:
            depth = metadata["depths"][identifier]
            weight = -depth if depth is not None else -len(metadata["order"])
        rows.append({"line": identifier, "weight": weight})
    return rows


def run_weighted_lines(model: WholeLineModel, policy: str, tie_break="forward",
                       seed=None, forced_prefix=()) -> dict:
    """Run one irreversible schedule; preserve the first conflict and its trace.

    Randomness only selects between equally highest-weight LINES. The symbol
    rule and within-line direction never change. ``forced_prefix`` is a test
    hook: every specified line must be tied highest at that exact state. It
    cannot force a lower-priority line or retry a failed choice.
    """
    if policy not in POLICIES or tie_break not in TIE_BREAKS:
        raise ValueError("unknown policy or tie break")
    if tie_break == "random" and type(seed) is not int:
        raise ValueError("random tie breaks require an explicit integer seed")
    metadata = line_metadata(model)
    frame = next(line for line in model.lines if line["id"] == "frame")
    first = frame["spans"][0]["dart"]
    anchors = {first: [1], first ^ 1: [2]}
    outcome = propagate_candidates(model, anchors)
    rng = random.Random(seed)
    trace, random_draws = [], 0
    while outcome["status"] == "underdetermined":
        candidates = priority_candidates(metadata, outcome["domains"], policy)
        if not candidates:
            raise RuntimeError("unknown shore is absent from real whole lines")
        highest = max(row["weight"] for row in candidates)
        tied = [row["line"] for row in candidates if row["weight"] == highest]
        index = len(trace)
        if index < len(forced_prefix):
            chosen = forced_prefix[index]
            if chosen not in tied:
                raise ValueError("forced line is not among the highest-weight ties")
        elif len(tied) == 1 or tie_break == "forward":
            chosen = tied[0]
        elif tie_break == "reverse":
            chosen = tied[-1]
        else:
            chosen = rng.choice(tied)
            random_draws += 1
        step = {"line": chosen, "weight": highest, "tied_lines": tied, "decisions": []}
        # The line is one scheduling unit. Attachment points do not restart the
        # scheduler. Propagation may fill remote shores before they are visited.
        for side, dart in metadata["occurrences"][chosen]:
            domain = outcome["domains"][side]
            if len(domain) <= 1:
                continue
            used = {ds[0] for ds in outcome["domains"] if len(ds) == 1}
            symmetry_only = set(domain) == {1, 2, 3, 4} - used
            symbol = min(domain)
            anchors[dart] = [symbol]
            outcome = propagate_candidates(model, anchors)
            step["decisions"].append({"dart": dart, "side": side, "domain": domain,
                                      "symbol": symbol, "symmetry_only": symmetry_only})
            if outcome["status"] == "conflict":
                break
        trace.append(step)
    if len(forced_prefix) > len(trace):
        raise ValueError("forced prefix extends past the terminal state")
    return {"status": outcome["status"], "policy": policy, "tie_break": tie_break,
            "seed": seed if tie_break == "random" else None, "trace": trace,
            "domains": outcome["domains"], "anchors_by_dart": anchors,
            "conflict_propagation": outcome["trace"] if outcome["status"] == "conflict" else [],
            "choices": sum(len(step["decisions"]) for step in trace),
            "non_symmetry_choices": sum(not d["symmetry_only"] for step in trace for d in step["decisions"]),
            "random_draws": random_draws, "backtracks": 0,
            "scope": "Fixed smallest-symbol commitment; no renaming of committed symbols within a run."}

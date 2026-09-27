"""Certify equal names from an odd cycle of original common NEQ neighbors.

If nonadjacent A and E had different names, every common neighbor would lose
both names and have at most two available. An odd cycle cannot use only two
names, hence A = E in every legal four-name assignment. This elementary known
implication generalizes the shared-triangle rule; it does not prove complete
equality inference, stepwise extendibility, or a new Four-Color Theorem.

Only original separator NEQ edges support certificates. Bridges, point
contacts, learned EQ, domains and color choices never enter discovery. Equal
names remain logical relations between distinct physical side identities.
"""

from collections import deque
from hashlib import sha256
from itertools import combinations
import json

from scripts.quaternary_contact_model import _validate


VERSION = "quaternary-shared-odd-cycle-equality-v1"


def _require(condition, message):
    """Reject invalid evidence even when Python assertions are disabled."""
    if not condition:
        raise ValueError(message)


def _digest(document):
    """Bind all literal input fields, including anchors and contact metadata."""
    return sha256(json.dumps(document, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode("utf-8")).hexdigest()


def _normalize_cycle(cycle):
    """Choose the least side-index tuple among rotations and both directions."""
    candidates = []
    for direction in (list(cycle), list(reversed(cycle))):
        candidates.extend(tuple(direction[i:] + direction[:i]) for i in range(len(direction)))
    return list(min(candidates))


def _odd_cycle(neighbors, common):
    """Find one deterministic witness, preferring the first common triangle.

    The fallback breadth-first forest visits roots and neighbors in side
    order. A same-level-parity edge closes a simple odd cycle through the
    endpoints' lowest common ancestor. It is not promised to be shortest.
    """
    vertices = sorted(common)
    for triangle in combinations(vertices, 3):
        if all(v in neighbors[u] for u, v in combinations(triangle, 2)):
            return list(triangle)
    allowed = set(vertices)
    parents, depths = {}, {}
    for root in vertices:
        if root in parents:
            continue
        parents[root], depths[root] = None, 0
        queue = deque([root])
        while queue:
            first = queue.popleft()
            for second in sorted(neighbors[first] & allowed):
                if second not in parents:
                    parents[second], depths[second] = first, depths[first] + 1
                    queue.append(second)
                elif (depths[first] - depths[second]) % 2 == 0:
                    # The tree paths have a common root because this original
                    # graph edge lies within the currently explored component.
                    first_path, ancestor = [], first
                    while ancestor is not None:
                        first_path.append(ancestor)
                        ancestor = parents[ancestor]
                    first_positions = {vertex: i for i, vertex in enumerate(first_path)}
                    second_path, ancestor = [], second
                    while ancestor not in first_positions:
                        second_path.append(ancestor)
                        ancestor = parents[ancestor]
                    cycle = first_path[:first_positions[ancestor] + 1] + list(reversed(second_path))
                    return _normalize_cycle(cycle)
    return None


def learn_odd_cycle_equalities(document):
    """Return one original-edge witness for every eligible nonbipartite pair.

    Side order determines pair order, triangle priority, BFS traversal and
    cycle normalization. Parallel separators count as one NEQ edge. Learning
    is one pass over the raw graph and never feeds learned EQ back into it.
    Nonempty external states/equal_names are outside this raw entry point.
    """
    sides, _ = _validate(document)
    _require(not document.get("states"), "raw equality learning rejects external states")
    _require(not document.get("equal_names"), "raw equality learning rejects supplied equal_names")
    index = {side: i for i, side in enumerate(sides)}
    neighbors = [set() for _ in sides]
    edges = set()
    separators = bridges = 0
    for line in document["lines"]:
        if line["kind"] == "bridge":
            bridges += 1
            continue
        separators += 1
        first, second = index[line["left"]], index[line["right"]]
        neighbors[first].add(second)
        neighbors[second].add(first)
        edges.add(tuple(sorted((first, second))))
    equal_names, certificates = [], []
    eligible_apex_pairs = 0
    for first, second in combinations(range(len(sides)), 2):
        if second in neighbors[first]:
            continue
        eligible_apex_pairs += 1
        cycle = _odd_cycle(neighbors, neighbors[first] & neighbors[second])
        if cycle is not None:
            pair = [sides[first], sides[second]]
            equal_names.append(pair)
            certificates.append({"apices": list(pair), "cycle": [sides[v] for v in cycle]})
    return {"version": VERSION, "raw_document_sha256": _digest(document),
            "equal_names": equal_names, "certificates": certificates,
            "stats": {"side_count": len(sides), "neq_edge_count": len(edges),
                      "separator_line_count": separators, "bridge_line_count": bridges,
                      "point_contact_count": len(document.get("point_contacts", [])),
                      "eligible_apex_pairs": eligible_apex_pairs,
                      "certificate_count": len(certificates)}}


def verify_odd_cycle_equalities(document, learned):
    """Check raw witnesses and complete pair coverage without calling discovery.

    The checker rebuilds a boolean matrix and uses an independent depth-first
    two-label test to determine which common-neighbor graphs are nonbipartite.
    It checks every certificate edge directly, including the closing rim edge.
    Any valid simple odd witness in canonical rotation/direction is accepted;
    it does not replicate the learner's triangle priority or BFS witness choice.
    This covers the declared rule, not all logically implied equalities.
    """
    sides, _ = _validate(document)
    _require(not document.get("states"), "raw certificate check rejects external states")
    _require(not document.get("equal_names"), "raw certificate check rejects supplied equal_names")
    _require(isinstance(learned, dict) and set(learned) == {
        "version", "raw_document_sha256", "equal_names", "certificates", "stats"},
        "equality result fields differ")
    _require(learned["version"] == VERSION, "equality rule version differs")
    _require(learned["raw_document_sha256"] == _digest(document), "raw document digest differs")
    _require(isinstance(learned["equal_names"], list)
             and isinstance(learned["certificates"], list), "equality evidence must be arrays")
    positions = {side: i for i, side in enumerate(sides)}
    n = len(sides)
    adjacent = [[False] * n for _ in range(n)]
    separator_count = bridge_count = 0
    for row in document["lines"]:
        if row["kind"] == "separator":
            separator_count += 1
            left, right = positions[row["left"]], positions[row["right"]]
            adjacent[left][right] = adjacent[right][left] = True
        else:
            bridge_count += 1

    expected_pairs, nonedges = [], 0
    for first in range(n):
        for second in range(first + 1, n):
            if adjacent[first][second]:
                continue
            nonedges += 1
            common = [i for i in range(n) if adjacent[first][i] and adjacent[second][i]]
            labels = [None] * n
            bipartite = True
            for start in common:
                if not bipartite:
                    break
                if labels[start] is not None:
                    continue
                labels[start] = 0
                stack = [start]
                while stack and bipartite:
                    current = stack.pop()
                    for other in common:
                        if not adjacent[current][other]:
                            continue
                        if labels[other] is None:
                            labels[other] = 1 - labels[current]
                            stack.append(other)
                        elif labels[other] == labels[current]:
                            bipartite = False
                            break
            if not bipartite:
                expected_pairs.append([sides[first], sides[second]])
    _require(learned["equal_names"] == expected_pairs,
             "equality pairs are missing, extra, duplicated or noncanonical")
    _require(len(learned["certificates"]) == len(expected_pairs), "certificate count differs")
    for pair, certificate in zip(expected_pairs, learned["certificates"]):
        _require(isinstance(certificate, dict) and set(certificate) == {"apices", "cycle"},
                 "odd-cycle certificate fields differ")
        _require(certificate["apices"] == pair, "certificate apex order differs")
        cycle = certificate["cycle"]
        _require(isinstance(cycle, list) and len(cycle) >= 3 and len(cycle) % 2 == 1
                 and all(isinstance(side, str) and side in positions for side in cycle),
                 "witness must be an odd cycle of known sides")
        _require(len(set(cycle)) == len(cycle) and not set(pair).intersection(cycle),
                 "cycle repeats a side or contains an apex")
        sequence = [positions[side] for side in cycle]
        # Canonical orientation can be checked locally for a simple cycle:
        # its unique least vertex must start it; its lesser neighbor comes next.
        _require(sequence[0] == min(sequence) and sequence[1] < sequence[-1],
                 "cycle rotation or direction is noncanonical")
        apices = [positions[side] for side in pair]
        _require(all(adjacent[apex][vertex] for apex in apices for vertex in sequence),
                 "cycle vertex lacks an original separator to an apex")
        _require(all(adjacent[sequence[i]][sequence[(i + 1) % len(sequence)]]
                     for i in range(len(sequence))), "cycle lacks an original rim separator")
    expected_stats = {"side_count": n,
                      "neq_edge_count": sum(adjacent[i][j] for i in range(n) for j in range(i + 1, n)),
                      "separator_line_count": separator_count, "bridge_line_count": bridge_count,
                      "point_contact_count": len(document.get("point_contacts", [])),
                      "eligible_apex_pairs": nonedges, "certificate_count": len(expected_pairs)}
    _require(isinstance(learned["stats"], dict) and learned["stats"] == expected_stats
             and all(type(value) is int for value in learned["stats"].values()),
             "equality statistics differ")
    return {"passed": True, "version": VERSION, "raw_document_sha256": _digest(document),
            "certificate_count": len(expected_pairs),
            "scope": "Every witness is a simple odd cycle and all its rim/spoke edges are "
                     "original separator NEQ edges. Every nonadjacent apex pair with a "
                     "nonbipartite common-neighbor graph has one normalized witness. "
                     "No claim of complete equality inference or global extendibility."}

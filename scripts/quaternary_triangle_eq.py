"""Certify one elementary four-name equality from original separator edges.

If three pairwise adjacent sides B, C, D are each adjacent to both A and E,
then B, C, D use three distinct names. In a palette of exactly four names,
both A and E must use the remaining name. Thus A = E in every legal coloring.
This is a known local implication, not a completeness or extendibility claim.

This version considers only distinct, nonadjacent apex pairs. Its witnesses
use original separator NEQ edges, never point contacts, bridges, candidate
domains, existing EQ relations, commitments, a target coloring, or an oracle.
The graph schema itself does not prove that a drawing realizes its contacts.
Equal names do not merge physical face identities or add geometric edges.
"""

from hashlib import sha256
from itertools import combinations
import json

from scripts.quaternary_contact_model import _validate


VERSION = "quaternary-shared-triangle-equality-v1"


def _require(condition, message):
    """Keep input and certificate rejection active under Python optimization."""
    if not condition:
        raise ValueError(message)


def _digest(document):
    """Bind every literal raw field, including declared anchors and contacts."""
    return sha256(json.dumps(document, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode("utf-8")).hexdigest()


def learn_triangle_equalities(document):
    """Return deterministic, one-pass EQ certificates without changing input.

    ``document['sides']`` fixes identity order. For each nonadjacent unordered
    apex pair, only the lexicographically first common triangle in that order
    is recorded. Parallel separator lines count as one NEQ edge. No learned
    equality is fed back into discovery, so there is no hidden iterative rule.
    Empty states/equal_names are accepted; nonempty values are rejected to keep
    this raw-graph entry point distinct from externally constrained states.
    """
    sides, _ = _validate(document)
    _require(not document.get("states"), "raw equality learning rejects external states")
    _require(not document.get("equal_names"), "raw equality learning rejects supplied equal_names")
    index = {side: i for i, side in enumerate(sides)}
    neighbors = [set() for _ in sides]
    edges = set()
    separators = 0
    bridges = 0
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
        for rim in combinations(sorted(neighbors[first] & neighbors[second]), 3):
            if all(v in neighbors[u] for u, v in combinations(rim, 2)):
                apices = [sides[first], sides[second]]
                equal_names.append(apices)
                certificates.append({"apices": list(apices),
                                     "rim": [sides[vertex] for vertex in rim]})
                break
    return {"version": VERSION, "raw_document_sha256": _digest(document),
            "equal_names": equal_names, "certificates": certificates,
            "stats": {"side_count": len(sides), "neq_edge_count": len(edges),
                      "separator_line_count": separators, "bridge_line_count": bridges,
                      "point_contact_count": len(document.get("point_contacts", [])),
                      "eligible_apex_pairs": eligible_apex_pairs,
                      "certificate_count": len(certificates)}}


def verify_triangle_equalities(document, learned):
    """Independently check certificate soundness, canonical choice and coverage.

    This checker shares the contact-schema validator and canonical JSON hash,
    but not the learner's adjacency construction or common-neighbor search.
    A separately built boolean matrix checks all nine edges of every possible
    five-side witness. It validates complete coverage of this rule, not that
    the rule finds all equalities implied by a graph. It never searches colors.
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
    separator_count = 0
    bridge_count = 0
    for row in document["lines"]:
        if row["kind"] == "separator":
            separator_count += 1
            left, right = positions[row["left"]], positions[row["right"]]
            adjacent[left][right] = True
            adjacent[right][left] = True
        else:
            bridge_count += 1

    expected_pairs, expected_certificates = [], []
    nonedges = 0
    for first in range(n):
        for second in range(first + 1, n):
            if adjacent[first][second]:
                continue
            nonedges += 1
            witness = None
            # Enumerating all triples (rather than intersecting neighbor sets)
            # keeps the certificate checker distinct from the producer path.
            for b in range(n):
                if witness is not None:
                    break
                for c in range(b + 1, n):
                    if witness is not None:
                        break
                    for d in range(c + 1, n):
                        if len({first, second, b, c, d}) != 5:
                            continue
                        if (adjacent[first][b] and adjacent[first][c]
                                and adjacent[first][d] and adjacent[second][b]
                                and adjacent[second][c] and adjacent[second][d]
                                and adjacent[b][c] and adjacent[b][d] and adjacent[c][d]):
                            witness = [sides[b], sides[c], sides[d]]
                            break
            if witness is not None:
                pair = [sides[first], sides[second]]
                expected_pairs.append(pair)
                expected_certificates.append({"apices": list(pair), "rim": witness})
    _require(learned["equal_names"] == expected_pairs,
             "equality pairs are missing, extra, duplicated or noncanonical")
    _require(learned["certificates"] == expected_certificates,
             "triangle certificates are missing, invalid or noncanonical")
    expected_stats = {"side_count": n,
                      "neq_edge_count": sum(adjacent[i][j] for i in range(n) for j in range(i + 1, n)),
                      "separator_line_count": separator_count, "bridge_line_count": bridge_count,
                      "point_contact_count": len(document.get("point_contacts", [])),
                      "eligible_apex_pairs": nonedges,
                      "certificate_count": len(expected_certificates)}
    _require(isinstance(learned["stats"], dict) and learned["stats"] == expected_stats
             and all(type(value) is int for value in learned["stats"].values()),
             "equality statistics differ")
    return {"passed": True, "version": VERSION, "raw_document_sha256": _digest(document),
            "certificate_count": len(expected_certificates),
            "scope": "Every selected witness has nine original separator NEQ edges; "
                     "all nonadjacent apex pairs have their first witness or none. "
                     "No claim of complete equality inference or global extendibility."}

"""Find conditionally equal opposite vertices around a real common edge.

If four distinct vertices share a palette of at most three names, the two
ends of a physical common edge consume two different names. Both common
neighbors must use the remaining name, and hence are equal. Domains are
premises whose sound derivation belongs to the independent closure audit;
neither logical EQ nor logical NEQ is treated as a physical separator.
"""

import hashlib
import json

from fourcolor.relation_names import transpose
from scripts.quaternary_logical_neq_contacts import _validate_logical


VERSION = "quaternary-conditional-diamond-eq-v1"
STATISTIC_KEYS = (
    "pairs_examined", "pairs_with_offdiagonal", "palettes_examined",
    "common_edges_examined", "certificates_found",
)
DIAGONAL_MASK = sum(1 << (5 * (color - 1)) for color in (1, 2, 3, 4))


def _digest(value):
    """Bind literal JSON data including the complete current phase premises."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False).encode("utf-8")).hexdigest()


def _validate_state(sides, domains, relations):
    """Reject malformed or inconsistent domain/matrix evidence before discovery.

    This checks representation and domain containment, not a derivation of
    the matrix or domains. The independent auditor replays that derivation.
    Empty domains are accepted literally, although production scans only
    nonterminal states.
    """
    n = len(sides)
    if not isinstance(domains, list) or len(domains) != n:
        raise ValueError("domains must be a side-aligned array")
    for domain in domains:
        if (not isinstance(domain, list)
                or any(type(color) is not int or color not in (1, 2, 3, 4)
                       for color in domain)
                or domain != sorted(set(domain))):
            raise ValueError("each domain must be a sorted unique array of integer names 1..4")
    if (not isinstance(relations, list) or len(relations) != n
            or any(not isinstance(row, list) or len(row) != n for row in relations)):
        raise ValueError("relations must be a square side-aligned matrix")
    for i, row in enumerate(relations):
        for j, mask in enumerate(row):
            if type(mask) is not int or not 0 <= mask <= 65535:
                raise ValueError("relation entries must be integer masks in 0..65535")
            allowed = sum(1 << (4 * (a - 1) + b - 1)
                          for a in domains[i] for b in domains[j])
            if mask & ~allowed:
                raise ValueError("relation contains a name outside its endpoint domains")
            if i == j and mask != sum(1 << (5 * (a - 1)) for a in domains[i]):
                raise ValueError("diagonal relation must exactly encode its domain")
    for i in range(n):
        for j in range(i + 1, n):
            if relations[j][i] != transpose(relations[i][j]):
                raise ValueError("opposite relation entries must be transposes")


def find_conditional_diamonds(document, domains, relations):
    """Return one deterministic certificate for each still non-EQ pair.

    Pairs follow literal input-index order. For each pair, colors 1..4 are
    tried in order, then sorted physical common-neighbor edges. Already
    diagonal-only relations are skipped, even when no explicit EQ is stored.
    The four vertices must be distinct. An additional real edge between the
    opposite vertices is allowed: the resulting equality implies conflict.
    """
    sides, _ = _validate_logical(document)
    _validate_state(sides, domains, relations)
    index = {side: i for i, side in enumerate(sides)}
    adjacency = [set() for _ in sides]
    for line in document["lines"]:
        if line["kind"] == "separator":
            first, second = index[line["left"]], index[line["right"]]
            adjacency[first].add(second)
            adjacency[second].add(first)
    statistics = {key: 0 for key in STATISTIC_KEYS}
    certificates = []
    for first in range(len(sides)):
        for second in range(first + 1, len(sides)):
            statistics["pairs_examined"] += 1
            if not relations[first][second] & ~DIAGONAL_MASK:
                continue
            statistics["pairs_with_offdiagonal"] += 1
            common = sorted(adjacency[first] & adjacency[second] - {first, second})
            common_edges = [(a, b) for position, a in enumerate(common)
                            for b in common[position + 1:] if b in adjacency[a]]
            certificate = None
            for excluded in (1, 2, 3, 4):
                statistics["palettes_examined"] += 1
                if excluded in domains[first] or excluded in domains[second]:
                    continue
                for a, b in common_edges:
                    statistics["common_edges_examined"] += 1
                    if excluded not in domains[a] and excluded not in domains[b]:
                        certificate = {"pair": [sides[first], sides[second]],
                                       "edge": [sides[a], sides[b]],
                                       "excluded_color": excluded}
                        break
                if certificate is not None:
                    break
            if certificate is not None:
                certificates.append(certificate)
                statistics["certificates_found"] += 1
    return {"version": VERSION, "raw_document_sha256": _digest(document),
            "domains_sha256": _digest(domains), "relations_sha256": _digest(relations),
            "certificates": certificates, "statistics": statistics}

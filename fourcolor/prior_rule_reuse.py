"""Reuse the archived nine-side lemma as a necessary binary name constraint.

Only geometry chooses the certificates: no previous failure key, chosen color,
or completed coloring is an input.  The conclusion concerns face color names;
it does not insert a primal edge, a dual adjacency, or a new drawing segment.
This module neither selects colors nor proves that nonempty relations extend.
"""

from .implicit_inequality import (
    KIND, REQUIRED_EDGES, VERTICES, _adjacency,
    find_implicit_inequality, verify_implicit_inequality,
)
from .relation_names import transpose


UNEQUAL_MASK = 0x7BDE
_CONCLUSION_KIND = "derived-name-relation-not-geometric-edge"


def certified_pair_relations(geometry):
    """Find and verify one certificate per nonadjacent unordered face pair.

    Both orientations of the existing asymmetric template matcher are tried,
    stopping at the first match.  Numeric face order fixes the whole search.
    Actual adjacencies already require unequal names, so matching them cannot
    strengthen the existing matrix and they are deliberately omitted.  The
    private adjacency helper repeats the archived geometry validation without
    changing its rules; the public verifier authenticates every returned proof.
    """
    adjacent, _ = _adjacency(geometry)
    certificates = []
    for first in range(len(adjacent)):
        for second in range(first + 1, len(adjacent)):
            if second in adjacent[first]:
                continue
            certificate = find_implicit_inequality(geometry, first, second)
            if certificate is None:
                certificate = find_implicit_inequality(geometry, second, first)
            if certificate is not None:
                verify_implicit_inequality(geometry, certificate)
                certificates.append(certificate)
    return certificates


def _require(condition, message):
    """Keep input checks enabled even when Python assertions are disabled."""
    if not condition:
        raise ValueError(message)


def _validated_matrix(matrix):
    """Copy a four-name relation matrix after checking its usual invariants."""
    _require(isinstance(matrix, (list, tuple)) and len(matrix) > 0,
             "relation matrix must be nonempty and square")
    n = len(matrix)
    _require(all(isinstance(row, (list, tuple)) and len(row) == n for row in matrix),
             "relation matrix must be nonempty and square")
    _require(all(type(value) is int and 0 <= value <= 65535
                 for row in matrix for value in row),
             "relation entries must be 16-bit nonnegative integers")
    for i in range(n):
        _require(not matrix[i][i] & ~0x8421, "self-relations must be diagonal")
        _require(all(matrix[j][i] == transpose(matrix[i][j]) for j in range(n)),
                 "opposite relations must be transposes")
    return [list(row) for row in matrix]


def _validated_target(certificate, n):
    """Check proof shape and target identities, without claiming geometry proof.

    This is not a substitute for ``verify_implicit_inequality``: raw edge IDs
    can be authenticated only against the original geometry.  The calling
    experiment should generate certificates once with ``certified_pair_relations``
    and reuse that verified list throughout its propagation rounds.
    """
    _require(isinstance(certificate, dict) and set(certificate) == {
        "kind", "palette_size", "mapping", "required_adjacencies", "conclusion"},
        "invalid implicit-inequality certificate shape")
    _require(certificate["kind"] == KIND and type(certificate["palette_size"]) is int
             and certificate["palette_size"] == 4, "invalid certificate kind or palette")
    mapping = certificate["mapping"]
    _require(isinstance(mapping, dict) and set(mapping) == set(VERTICES),
             "certificate requires exactly nine template vertices")
    _require(all(type(value) is int and 0 <= value < n for value in mapping.values()),
             "certificate side identity is outside the relation matrix")
    _require(len(set(mapping.values())) == len(VERTICES),
             "certificate side identities must be distinct")
    required = certificate["required_adjacencies"]
    _require(isinstance(required, list) and len(required) == len(REQUIRED_EDGES),
             "certificate requires nineteen adjacency witnesses")
    for witness, (first, second) in zip(required, REQUIRED_EDGES):
        _require(isinstance(witness, dict) and set(witness) == {
            "vertices", "sides", "raw_edge_ids"}, "invalid adjacency witness shape")
        _require(witness["vertices"] == [first, second]
                 and isinstance(witness["sides"], list)
                 and all(type(side) is int for side in witness["sides"])
                 and witness["sides"] == [mapping[first], mapping[second]],
                 "adjacency witness does not match its template mapping")
        edge_ids = witness["raw_edge_ids"]
        _require(isinstance(edge_ids, list) and len(edge_ids) > 0
                 and all(type(edge) is int and edge >= 0 for edge in edge_ids)
                 and len(set(edge_ids)) == len(edge_ids),
                 "adjacency witness requires distinct nonnegative raw edge IDs")
    target = [mapping["A"], mapping["B"]]
    conclusion = certificate["conclusion"]
    _require(isinstance(conclusion, dict) and isinstance(conclusion.get("sides"), list)
             and all(type(side) is int for side in conclusion["sides"])
             and conclusion == {
        "sides": target, "relation": "!=", "kind": _CONCLUSION_KIND},
        "certificate conclusion differs from its template mapping")
    return target


def intersect_certified_relations(matrix, certificates):
    """Intersect verified conclusions with both directions of existing pairs.

    The input matrix and certificates are unchanged.  This step only deletes
    equal-name pairs at certified targets; ordinary relation/Hall closure must
    subsequently propagate the consequences to other pairs and unary domains.
    Trace indices refer to the supplied certificate list, so each deletion can
    be replayed and related to the original nineteen-edge geometry evidence.
    """
    relations = _validated_matrix(matrix)
    _require(isinstance(certificates, (list, tuple)), "certificates must be a list or tuple")
    # Validate the entire batch first, including certificates after a conflict.
    targets = [_validated_target(certificate, len(relations)) for certificate in certificates]
    # A geometric proof can strengthen this matrix only when the matrix also
    # contains every inequality used by that proof.  Without this check, an
    # otherwise valid certificate could be misapplied to an unrelated CSP.
    for certificate in certificates:
        for witness in certificate["required_adjacencies"]:
            first, second = witness["sides"]
            _require(not relations[first][second] & 0x8421,
                     "certificate inequality premise is missing from relation matrix")
    trace = []
    for index, (first, second) in enumerate(targets):
        before = relations[first][second]
        after = before & UNEQUAL_MASK
        if after == before:
            continue
        relations[first][second] = after
        relations[second][first] = transpose(after)
        trace.append({"certificate_index": index, "sides": [first, second],
                      "kind": _CONCLUSION_KIND, "relation": "!=",
                      "before": before, "after": after, "removed": before ^ after})
    return {"relations": relations, "trace": trace, "changed": bool(trace),
            "conflict": any(value == 0 for row in relations for value in row)}

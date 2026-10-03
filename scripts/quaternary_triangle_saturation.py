"""Certify a fourth name from a physical triangle in explicit equality classes.

Three pairwise adjacent classes restricted to the same three-name palette
must occupy every name in that palette. A distinct class adjacent to all
three can therefore use only the excluded fourth name. Equality classes are
logical bookkeeping: every quotient adjacency retains a literal physical
separator witness, and face identities and original lines stay unchanged.
"""

import hashlib
import itertools
import json

from scripts.quaternary_logical_neq_contacts import _validate_logical


VERSION = "quaternary-triangle-saturation-v1"
STATISTIC_KEYS = (
    "classes_examined", "palettes_examined", "triangles_examined",
    "physical_witness_edges", "certificates_found",
)


def _digest(value):
    """Bind the complete literal phase input, including conditional premises."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False).encode("utf-8")).hexdigest()


def _classes(sides, domains, equal_names):
    """Validate literal domains and construct deterministic explicit EQ classes.

    Derived domains in one equality class must already agree. Requiring that
    invariant avoids silently substituting an unaudited intersection for a
    representative domain. Duplicate, reversed and self EQs retain the frozen
    input language's harmless semantics. Empty domains are accepted literally;
    the production caller only scans nonterminal propagation outcomes.
    """
    if not isinstance(domains, list) or len(domains) != len(sides):
        raise ValueError("domains must be a side-aligned array")
    for domain in domains:
        if (not isinstance(domain, list)
                or any(type(color) is not int or color not in (1, 2, 3, 4) for color in domain)
                or domain != sorted(set(domain))):
            raise ValueError("domains must contain sorted unique integer names 1..4")
    index = {side: i for i, side in enumerate(sides)}
    if not isinstance(equal_names, list):
        raise ValueError("equal_names must be an array")
    parent = list(range(len(sides)))

    def root(i):
        """Find a class root without introducing new physical identities."""
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for pair in equal_names:
        if (not isinstance(pair, list) or len(pair) != 2
                or any(not isinstance(side, str) or side not in index for side in pair)):
            raise ValueError("each equality requires two known side references")
        a, b = sorted((root(index[pair[0]]), root(index[pair[1]])))
        parent[b] = a
    groups = {}
    for i in range(len(sides)):
        groups.setdefault(root(i), []).append(i)
    classes = sorted(groups.values(), key=lambda group: group[0])
    for group in classes:
        if any(domains[i] != domains[group[0]] for i in group):
            raise ValueError("all members of an equality class must have the same domain")
    return classes


def find_triangle_saturations(document, domains, equal_names):
    """Find one deterministic useful saturation certificate per target class.

    The supplied equality list comes from the final audited diamond round;
    it may contain conditional EQs absent from the root phase document.
    Only literal separator edges supply witnesses. Neither logical NEQ nor
    point contact may substitute for one of the six necessary adjacencies.
    """
    sides, _ = _validate_logical(document)
    classes = _classes(sides, domains, equal_names)
    index = {side: i for i, side in enumerate(sides)}
    owner = {i: group for group, members in enumerate(classes) for i in members}
    witnesses = {}
    for line in document["lines"]:
        if line["kind"] != "separator":
            continue
        i, j = index[line["left"]], index[line["right"]]
        a, b = owner[i], owner[j]
        if a == b:
            raise ValueError("a physical separator cannot lie inside an equality class")
        for first, second, left, right in ((a, b, i, j), (b, a, j, i)):
            key, pair = (first, second), (left, right)
            if key not in witnesses or pair < witnesses[key]:
                witnesses[key] = pair
    adjacency = [{other for other in range(len(classes)) if (target, other) in witnesses}
                 for target in range(len(classes))]
    statistics = {key: 0 for key in STATISTIC_KEYS}
    certificates = []
    for target, group in enumerate(classes):
        statistics["classes_examined"] += 1
        certificate = None
        for excluded in (1, 2, 3, 4):
            statistics["palettes_examined"] += 1
            removed = [color for color in domains[group[0]] if color != excluded]
            if not removed:
                continue
            for a, b, c in itertools.combinations(sorted(adjacency[target]), 3):
                statistics["triangles_examined"] += 1
                if ((a, b) not in witnesses or (a, c) not in witnesses or (b, c) not in witnesses
                        or any(excluded in domains[classes[i][0]] for i in (a, b, c))):
                    continue
                edge_classes = ((a, b), (a, c), (b, c), (target, a), (target, b), (target, c))
                certificate = {
                    "target": sides[group[0]],
                    "triangle": [sides[classes[i][0]] for i in (a, b, c)],
                    "excluded_color": excluded, "removed_colors": removed,
                    "edges": [[sides[i], sides[j]] for i, j in
                              (witnesses[pair] for pair in edge_classes)],
                }
                break
            if certificate is not None:
                break
        if certificate is not None:
            certificates.append(certificate)
            statistics["certificates_found"] += 1
            statistics["physical_witness_edges"] += 6
    return {"version": VERSION, "raw_document_sha256": _digest(document),
            "domains_sha256": _digest(domains), "equal_names_sha256": _digest(equal_names),
            "classes": [[sides[i] for i in group] for group in classes],
            "certificates": certificates, "statistics": statistics}

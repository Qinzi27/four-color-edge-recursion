"""A certified nine-side pattern implying an additional inequality of names.

This module does not color a map and is NOT imported by the frozen v4 solver.
It matches geometry only. Its conclusion is a logical name relation between
existing side IDs, never a new primal edge, split, endpoint or mother line.
The elementary implication is valid for a palette of at most four names; no
claim of novelty or complete pattern coverage is made.
"""

from .embedding import PlaneMap


VERTICES = ("O", "A", "B", "p", "q", "r", "s", "t", "u")
REQUIRED_EDGES = tuple(tuple(pair.split()) for pair in (
    "O A", "O B", "O p", "A p", "O q", "B q", "p q", "r p", "r q", "r A",
    "s r", "s A", "t O", "t B", "t s", "u B", "u r", "u s", "u t"))
KIND = "nine-side-two-triangle-implicit-inequality"


def _require(condition, message):
    """Keep certificate validation active under optimized Python as well."""
    if not condition:
        raise ValueError(message)


def _adjacency(geometry):
    """Reconstruct actual shared-boundary edges, excluding virtuals and bridges."""
    plane = PlaneMap(tuple((str(edge["a"]), str(edge["b"])) for edge in geometry["edges"]),
                     {str(vertex): tuple(darts) for vertex, darts in enumerate(geometry["rotation"])})
    _require(tuple(geometry["faceOfDart"]) == plane.face_of_dart, "side/dart identities differ")
    _require({frozenset(face) for face in geometry["faces"]} ==
             {frozenset(face) for face in plane.faces}, "side orbit geometry differs")
    adjacent, references = [set() for _ in plane.faces], {}
    for index, edge in enumerate(geometry["edges"]):
        a, b = plane.shores(index)
        _require(not edge.get("virtual") or a == b, "virtual connector separates sides")
        if a == b:
            continue
        _require(geometry["vertices"][edge["a"]] != geometry["vertices"][edge["b"]],
                 "zero-length edge cannot certify shared boundary")
        adjacent[a].add(b)
        adjacent[b].add(a)
        references.setdefault(tuple(sorted((a, b))), []).append(index)
    return adjacent, references


def _certificate(adjacent, references, mapping):
    """Check distinct vertices and emit all nineteen real-edge witnesses."""
    _require(set(mapping) == set(VERTICES), "exactly nine named template vertices required")
    _require(all(type(value) is int and 0 <= value < len(adjacent) for value in mapping.values()),
             "invalid side identity")
    _require(len(set(mapping.values())) == 9, "template side identities must be distinct")
    required = []
    for first, second in REQUIRED_EDGES:
        a, b = mapping[first], mapping[second]
        _require(b in adjacent[a], "missing required adjacency: " + first + "-" + second)
        required.append({"vertices": [first, second], "sides": [a, b],
                         "raw_edge_ids": list(references[tuple(sorted((a, b)))])})
    return {"kind": KIND, "palette_size": 4,
            "mapping": {name: mapping[name] for name in VERTICES},
            "required_adjacencies": required,
            "conclusion": {"sides": [mapping["A"], mapping["B"]], "relation": "!=",
                           "kind": "derived-name-relation-not-geometric-edge"}}


def certify_implicit_inequality(geometry, mapping):
    """Certify a supplied embedding of the fixed implication template.

    Proof: if A=B=a and O=o, p,q exhaust the other two names, forcing r=o.
    Then adjacent s,t again exhaust those two names; u sees all four via
    B,r,s,t, which is impossible. Thus A and B cannot share a name.
    """
    adjacent, references = _adjacency(geometry)
    return _certificate(adjacent, references, mapping)


def verify_implicit_inequality(geometry, certificate):
    """Reject altered conclusions, repeated sides and forged edge witnesses."""
    expected = certify_implicit_inequality(geometry, certificate["mapping"])
    _require(certificate == expected, "implicit-inequality certificate differs from raw geometry")
    return {"passed": True, "template_vertices": 9, "required_adjacencies": 19,
            "conclusion": expected["conclusion"]}


def _find_mapping(adjacent, first, second):
    """Find the first injective template mapping by common-neighbor intersections.

    The enumerated objects are side IDs occupying graph-template positions,
    not assignments of color names. Every order is fixed by numeric side ID.
    """
    _require(type(first) is int and type(second) is int and first != second
             and 0 <= first < len(adjacent) and 0 <= second < len(adjacent), "invalid target side pair")
    for o in sorted(adjacent[first] & adjacent[second]):
        used_o = {first, second, o}
        for p in sorted((adjacent[o] & adjacent[first]) - used_o):
            used_p = used_o | {p}
            for q in sorted((adjacent[o] & adjacent[second] & adjacent[p]) - used_p):
                used_q = used_p | {q}
                for r in sorted((adjacent[p] & adjacent[q] & adjacent[first]) - used_q):
                    used_r = used_q | {r}
                    for s in sorted((adjacent[r] & adjacent[first]) - used_r):
                        used_s = used_r | {s}
                        for t in sorted((adjacent[o] & adjacent[second] & adjacent[s]) - used_s):
                            used_t = used_s | {t}
                            available = (adjacent[second] & adjacent[r] & adjacent[s] & adjacent[t]) - used_t
                            if available:
                                return dict(zip(VERTICES, (o, first, second, p, q, r, s, t, min(available))))
    return None


def find_implicit_inequality(geometry, first, second):
    """Return one independently checkable template certificate, or no match.

    A missing match says only that this one fixed pattern was not found in
    this orientation; it does not certify equal-name extendibility. Reverse
    the two requested sides explicitly if that orientation is also required.
    """
    adjacent, references = _adjacency(geometry)
    mapping = _find_mapping(adjacent, first, second)
    return None if mapping is None else _certificate(adjacent, references, mapping)

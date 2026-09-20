"""Geometry-certified common boundaries and bounded conditional filtering.

Two adjacent face variables U,D and their common neighbors T form a ``book``
of triangles in the loopless dual graph. In every proper four-coloring, T uses
at most two colors. This is a necessary local constraint, not a completion
certificate for the entire map. Extra edges or auxiliary relations are kept.

``domains`` applies only the unary AtMostNValue(T,2) filter. ``joint`` explicitly
conditions on at most twelve ordered colors for U,D and joins the resulting
local path-consistency supports. This is bounded conditional reasoning, not
the old branch-free v4 rule. Neither mode commits a color or retries a whole
map. The caller must interleave this single scan with its other propagators.
"""

from itertools import combinations

from .relation_names import relation_closure, transpose


EQUAL = 0x8421
UNEQUAL = 0xFFFF ^ EQUAL


def find_boundary_books(model):
    """Return every real adjacent pair with at least three common face shores.

    Each required adjacency carries all its original primal edge IDs. Bridges
    have the same face on both sides and cannot witness an inequality. The
    records describe dual constraints; they do not insert lines in the map.
    """
    plane = model.plane_map
    neighbors = [set() for _ in plane.faces]
    witnesses = {}
    for edge in range(len(plane.edges)):
        first, second = plane.shores(edge)
        if first == second:
            continue
        pair = tuple(sorted((first, second)))
        witnesses.setdefault(pair, []).append(edge)
        neighbors[first].add(second)
        neighbors[second].add(first)
    books = []
    for first, second in sorted(witnesses):
        boundary = sorted(neighbors[first] & neighbors[second])
        if len(boundary) < 3:
            continue
        required = {(first, second)}
        required.update(tuple(sorted((core, shore)))
                        for core in (first, second) for shore in boundary)
        books.append({"internal": [first, second], "boundary": boundary,
                      "edge_witnesses": [
                          {"sides": list(pair), "raw_edge_ids": list(witnesses[pair])}
                          for pair in sorted(required)]})
    return books


def _copy_matrix(matrix):
    """Validate the same public mask format as path consistency, without running it."""
    if not isinstance(matrix, (list, tuple)) or not matrix:
        raise ValueError("relation matrix must be nonempty and square")
    n = len(matrix)
    if any(not isinstance(row, (list, tuple)) or len(row) != n for row in matrix):
        raise ValueError("relation matrix must be nonempty and square")
    if any(type(mask) is not int or not 0 <= mask <= 65535
           for row in matrix for mask in row):
        raise ValueError("relation entries must be 16-bit nonnegative integers")
    for i in range(n):
        if matrix[i][i] & ~EQUAL:
            raise ValueError("self-relations must be diagonal")
        if any(matrix[j][i] != transpose(matrix[i][j]) for j in range(n)):
            raise ValueError("opposite relations must be transposes")
    return [list(row) for row in matrix]


def _validate_books(books, relations):
    """Reject malformed caches and require all triangle inequalities in input.

    This API has no geometry parameter, so optional raw-edge metadata is only
    structurally checked here. Geometry provenance must be obtained by calling
    ``find_boundary_books(model)`` or independently replaying those witnesses.
    Sound filtering needs the stated inequalities, which are checked directly.
    """
    if not isinstance(books, (list, tuple)):
        raise ValueError("books must be a sequence")
    n = len(relations)
    result = []
    seen = set()
    for book in books:
        if not isinstance(book, dict) or set(book) - {"internal", "boundary", "edge_witnesses"}:
            raise ValueError("book must contain internal and boundary identities")
        internal, boundary = book.get("internal"), book.get("boundary")
        if (not isinstance(internal, (list, tuple)) or len(internal) != 2
                or not isinstance(boundary, (list, tuple)) or len(boundary) < 3):
            raise ValueError("book needs two internal and at least three boundary shores")
        vertices = list(internal) + list(boundary)
        if any(type(v) is not int or not 0 <= v < n for v in vertices):
            raise ValueError("book shore identities must be integers in range")
        if len(set(vertices)) != len(vertices):
            raise ValueError("book shore identities must be distinct")
        first, second = internal
        required = {tuple(sorted((first, second)))}
        required.update(tuple(sorted((core, shore))) for core in internal for shore in boundary)
        if any(relations[a][b] & EQUAL for a, b in required):
            raise ValueError("book requires unequal internal and spoke relations")
        identity = (tuple(sorted(internal)), tuple(sorted(boundary)))
        if identity in seen:
            raise ValueError("duplicate book cache entry")
        seen.add(identity)
        if "edge_witnesses" in book:
            entries = book["edge_witnesses"]
            if not isinstance(entries, (list, tuple)) or len(entries) != len(required):
                raise ValueError("edge witnesses must cover exactly the required adjacencies")
            covered, used_edges = set(), set()
            for entry in entries:
                if not isinstance(entry, dict) or set(entry) != {"sides", "raw_edge_ids"}:
                    raise ValueError("invalid edge witness record")
                sides, edges = entry["sides"], entry["raw_edge_ids"]
                if (not isinstance(sides, (list, tuple)) or len(sides) != 2
                        or any(type(v) is not int for v in sides)):
                    raise ValueError("invalid edge witness side pair")
                pair = tuple(sides)
                if pair not in required or pair in covered:
                    raise ValueError("edge witnesses must cover exactly the required adjacencies")
                if (not isinstance(edges, (list, tuple)) or not edges
                        or any(type(edge) is not int or edge < 0 for edge in edges)
                        or len(set(edges)) != len(edges) or used_edges.intersection(edges)):
                    raise ValueError("edge witnesses need distinct nonnegative raw edge IDs")
                covered.add(pair)
                used_edges.update(edges)
        result.append(vertices)
    return result


def _colors(diagonal):
    """Decode one diagonal domain using display colors 1,2,3,4."""
    return [color for color in range(1, 5) if diagonal & (1 << (5 * (color - 1)))]


def filter_boundary_books(relations, books, mode="joint"):
    """Perform one sound scan without modifying inputs or claiming completeness.

    A joint event records its local input and every conditional closure output.
    Each branch is independently replayable with ``relation_closure``; only
    surviving branch matrices contribute to the union. Every complete input
    assignment belongs to its actual U,D branch, so none of its pairs can be
    removed. Even a nonempty branch need not certify a full-map extension.

    Statistics count directed matrix bits (both orientations) and count unary
    values separately. ``local_revisions`` is the existing closure's attempted
    triple-revision count. Book scans can need repetition after global closure.
    """
    if mode not in ("domains", "joint"):
        raise ValueError("mode must be domains or joint")
    matrix = _copy_matrix(relations)
    vertices_by_book = _validate_books(books, matrix)
    statistics = {"book_checks": 0, "conditional_cases": 0, "local_revisions": 0,
                  "relation_bits_removed": 0, "domain_values_removed": 0,
                  "palette_checks": 0}
    events = []
    conflict = any(mask == 0 for row in matrix for mask in row)
    changed = False
    for index, vertices in enumerate(vertices_by_book):
        if conflict:
            break
        statistics["book_checks"] += 1
        local = [[matrix[a][b] for b in vertices] for a in vertices]
        event = {"book_index": index, "mode": mode, "vertices": list(vertices),
                 "input_relations": local, "updates": []}
        if mode == "domains":
            domains = [_colors(local[i][i]) for i in range(2, len(vertices))]
            supported = [set() for _ in domains]
            event["palettes"] = []
            for palette in combinations(range(1, 5), 2):
                statistics["palette_checks"] += 1
                intersections = [set(domain).intersection(palette) for domain in domains]
                viable = all(intersections)
                event["palettes"].append({"colors": list(palette), "supported": viable})
                if viable:
                    for union, values in zip(supported, intersections):
                        union.update(values)
            allowed = [list(row) for row in local]
            for i, values in enumerate(supported, 2):
                allowed[i][i] = sum(1 << (5 * (color - 1)) for color in values)
        else:
            event["branches"] = []
            allowed = [[0] * len(vertices) for _ in vertices]
            for first in _colors(local[0][0]):
                for second in _colors(local[1][1]):
                    bit = 1 << (4 * (first - 1) + second - 1)
                    if not local[0][1] & bit:
                        continue
                    statistics["conditional_cases"] += 1
                    branch = [list(row) for row in local]
                    branch[0][0] = 1 << (5 * (first - 1))
                    branch[1][1] = 1 << (5 * (second - 1))
                    outcome = relation_closure(branch)
                    statistics["local_revisions"] += outcome["revisions"]
                    event["branches"].append({
                        "colors": [first, second],
                        "status": "conflict" if outcome["conflict"] else "consistent",
                        "relations": outcome["relations"], "revisions": outcome["revisions"],
                        "deletion_events": len(outcome["trace"])})
                    if not outcome["conflict"]:
                        for i, row in enumerate(outcome["relations"]):
                            for j, mask in enumerate(row):
                                allowed[i][j] |= mask
        # Update an unordered entry once, then mirror its transpose. The local
        # branch union preserves converse symmetry; this also handles diagonals.
        for i, first in enumerate(vertices):
            for j in range(i, len(vertices)):
                second = vertices[j]
                before = matrix[first][second]
                after = before & allowed[i][j]
                if after != before:
                    changed = True
                    removed = before ^ after
                    count = removed.bit_count()
                    statistics["relation_bits_removed"] += count * (1 if i == j else 2)
                    if i == j:
                        statistics["domain_values_removed"] += count
                    event["updates"].append({"sides": [first, second], "before": before,
                                             "after": after, "removed": removed})
                    matrix[first][second] = after
                    matrix[second][first] = transpose(after)
        conflict = any(mask == 0 for row in matrix for mask in row)
        event["conflict"] = conflict
        events.append(event)
    return {"relations": matrix, "changed": changed, "conflict": conflict,
            "events": events, "statistics": statistics}

"""Ordered shore-name relations and path-consistency filtering, without DFS.

Whole lines retain their geometry and ordered spans. Relations for nonadjacent
shore identities are auxiliary compatibility records, NOT new drawn lines.
The matrix filter is a standard constraint-consistency method, not a new proof
of four-colorability. Nonempty relations need not have a global completion.
"""

from collections import deque

from .joint_lines import _weight, run_joint_lines
from .weighted_lines import line_metadata


def pairs(mask):
    """Decode a 4 by 4 relation mask into positive display-name pairs."""
    return [[a + 1, b + 1] for a in range(4) for b in range(4)
            if mask & (1 << (4 * a + b))]


def transpose(mask):
    """Reverse a directed line-side relation by exchanging its two names."""
    return sum(1 << (4 * b + a) for a in range(4) for b in range(4)
               if mask & (1 << (4 * a + b)))


def compose(left, right):
    """Boolean relational product: keep (a,b) if SOME middle name supports it."""
    right_rows = [(right >> (4 * c)) & 15 for c in range(4)]
    result = 0
    for a in range(4):
        middle = (left >> (4 * a)) & 15
        supported = 0
        for c in range(4):
            if middle & (1 << c):
                supported |= right_rows[c]
        result |= supported << (4 * a)
    return result


def initial_relations(model, domains):
    """Encode actual separations, equal self-relations and otherwise no bans."""
    n = len(domains)
    adjacency = {tuple(sorted(model.plane_map.shores(e))) for e in range(len(model.plane_map.edges))
                 if len(set(model.plane_map.shores(e))) == 2}
    result = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            result[i][j] = sum(1 << (4 * (a - 1) + b - 1) for a in domains[i] for b in domains[j]
                               if (a == b if i == j else
                                   a != b if tuple(sorted((i, j))) in adjacency else True))
    return result


def relation_closure(matrix):
    """Return an independently replayable shrinking matrix fixed point.

    Each changed entry requeues both orientations. Revising through repeated
    indices also projects unsupported values out of diagonal domains; stopping
    after only distinct triples would miss this. All entries have at most 16
    bits, so deletion and therefore worklist reactivation are finite.
    """
    relations = [list(row) for row in matrix]
    n = len(relations)
    if not n or any(len(row) != n for row in relations):
        raise ValueError("relation matrix must be nonempty and square")
    if any(type(value) is not int or not 0 <= value <= 65535 for row in relations for value in row):
        raise ValueError("relation entries must be 16-bit nonnegative integers")
    for i in range(n):
        if relations[i][i] & ~0x8421:
            raise ValueError("self-relations must be diagonal")
        if any(relations[j][i] != transpose(relations[i][j]) for j in range(n)):
            raise ValueError("opposite relations must be transposes")
    queue = deque((i, j) for i in range(n) for j in range(n))
    pending = set(queue)
    trace = []
    revisions = 0
    conflict = any(value == 0 for row in relations for value in row)

    def revise(i, j, k):
        """Intersect R_ij with R_ik composed with R_kj, then mirror it."""
        nonlocal revisions, conflict
        revisions += 1
        before, left, right = relations[i][j], relations[i][k], relations[k][j]
        after = before & compose(left, right)
        if after == before:
            return
        trace.append({"i": i, "j": j, "via": k, "before": before,
                      "left": left, "right": right, "after": after,
                      "removed": before ^ after})
        relations[i][j] = after
        relations[j][i] = transpose(after)
        for item in ((i, j), (j, i)):
            if item not in pending:
                pending.add(item)
                queue.append(item)
        conflict = after == 0

    while queue and not conflict:
        i, j = queue.popleft()
        pending.remove((i, j))
        for k in range(n):
            revise(i, k, j)
            if conflict:
                break
            revise(k, j, i)
            if conflict:
                break
    return {"relations": relations, "trace": trace, "conflict": conflict,
            "revisions": revisions}


def _domains(relations):
    """Read unary candidates from diagonal relations, not arbitrary row unions."""
    return [[a + 1 for a in range(4) if row[i] & (1 << (5 * a))]
            for i, row in enumerate(relations)]


def _permuted(mask, permutation):
    """Transform both names under one global palette permutation."""
    return sum(1 << (4 * permutation[a] + permutation[b]) for a in range(4) for b in range(4)
               if mask & (1 << (4 * a + b)))


def run_relation_names(model, policy="constraints", anchors=None, symbol_symmetry=False):
    """Extend strict whole-line closure with ordered name-pair compatibility.

    The first stage uses the existing whole-line priority (fixed forward ties).
    The second stage uses a deterministic relation worklist; it is not secretly
    a highest-weight drawn-line traversal. Optional unused-symbol normalization
    checks every RELATION, not merely its unary projections. No trial color,
    branch retry or target-coloring oracle is used.
    """
    if type(symbol_symmetry) is not bool:
        raise ValueError("symbol_symmetry must be a boolean")
    base = run_joint_lines(model, policy=policy, anchors=anchors)
    relations = initial_relations(model, base["domains"])
    initial = [list(row) for row in relations]
    phases, normalizations = [], []
    metadata = line_metadata(model)
    total_revisions = 0
    while True:
        result = relation_closure(relations)
        relations = result["relations"]
        total_revisions += result["revisions"]
        phases.append(result["trace"])
        domains = _domains(relations)
        if result["conflict"] or not symbol_symmetry or all(len(d) == 1 for d in domains):
            break
        used = {d[0] for d in domains if len(d) == 1}
        unused = sorted({1, 2, 3, 4} - used)
        if len(unused) < 2:
            break
        # Transpositions with one fixed unused symbol generate all permutations
        # of that set. Check the binary records too, including non-edge ones.
        invariant = True
        for other in unused[1:]:
            permutation = list(range(4))
            a, b = unused[0] - 1, other - 1
            permutation[a], permutation[b] = b, a
            if any(_permuted(mask, permutation) != mask for row in relations for mask in row):
                invariant = False
                break
        if not invariant:
            break
        eligible = []
        for line in model.lines:
            hits = [(s, dart) for s, dart in metadata["occurrences"][line["id"]] if domains[s] == unused]
            if hits:
                # Match the previous default's constraint-count scheduling for
                # representative selection; alternative priorities stay explicit.
                weight = _weight(metadata, [set(d) for d in domains], line["id"], policy)
                eligible.append((weight, line["id"], hits[0]))
        if not eligible:
            break
        highest = max(row[0] for row in eligible)
        _, line, (side, dart) = next(row for row in eligible if row[0] == highest)
        symbol = unused[0]
        before = relations[side][side]
        relations[side][side] = 1 << (5 * (symbol - 1))
        normalizations.append({"line": line, "side": side, "dart": dart, "unused": unused,
                               "symbol": symbol, "before": before, "after": relations[side][side]})
    status = ("conflict" if result["conflict"] else
              "solved" if all(len(d) == 1 for d in domains) else "underdetermined")
    profiles = [{"id": line["id"], "spans": [{"dart": s["dart"], "t0": s["t0"], "t1": s["t1"],
                  "left_side": s["left_side"], "right_side": s["right_side"],
                  "pairs": pairs(relations[s["left_side"]][s["right_side"]])} for s in line["spans"]]}
                for line in model.lines]
    return {"status": status, "policy": policy, "symbol_symmetry": symbol_symmetry,
            "domains": domains, "relations": relations, "initial_relations": initial,
            "base": base, "phases": phases, "normalizations": normalizations,
            "profiles": profiles, "revisions": total_revisions,
            "choices": len(normalizations), "non_symmetry_choices": 0, "backtracks": 0,
            "scope": "Ordered name-pair path consistency; auxiliary non-edge relations are not drawn lines; nonempty closure is not a completion certificate."}

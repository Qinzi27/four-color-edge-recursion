"""A genuine guillotine rectangle family with unbounded endpoint recoloring.

The graph vertices below denote rectangle side-consistency classes, not the
geometric corners of those rectangles.  The exterior class ``r`` is fixed at
color zero.  Every rectangle touches the exterior, so its available colors are
1, 2, 3.  The construction specifies a legal initial coloring; it does NOT claim
that the project's historical greedy naming algorithm produces that coloring.

For m >= 1, the final rectangle adjacency graph is P_(6m+3)^2.  Consecutive
triangles force a final coloring to be periodic modulo three.  The two long
sides of the initial coloring use permutations (1,2,3) and (3,2,1).  Each
residue class has m old rectangles on each side, plus the middle old rectangle
v1.  The six possible final costs are 2m, 5m+1, 5m+1, 5m+1, 5m+1, 2m.
Thus the least number of changed old classes is exactly 2m.  A single complete
1/3 Kempe component attains that endpoint, illustrating that a short path need
not have bounded support.  This elementary constructed-family argument is not
a novelty claim or a statement about the frozen first-blocked snapshots.
"""

from __future__ import annotations

from itertools import combinations, permutations


def build_staggered_strip(m: int) -> dict:
    """Return H, an explicit coloring, rectangles, and a guillotine history.

    Rectangles use [xmin, xmax, ymin, ymax] with exact integer coordinates.
    ``guillotine_steps`` cuts one currently existing rectangle at a time; the
    last step splits the parent of v0 and v2.  No files are written.
    """
    if isinstance(m, bool) or not isinstance(m, int) or m < 1:
        raise ValueError("m must be a positive integer")
    lower, upper = -3 * m, 3 * m + 2
    indices = range(lower, upper + 1)
    index_by_side = {f"v{i}": i for i in indices}
    rectangles = {
        f"v{i}": [max(lower, i - 1), min(upper, i + 1),
                   1 if i % 2 == 0 else 0, 2 if i % 2 == 0 else 1]
        for i in indices
    }
    initial = {"r": 0}
    for side, index in index_by_side.items():
        initial[side] = ((1, 2, 3)[index % 3] if index <= 0 else
                         2 if index == 1 else (3, 2, 1)[index % 3])
    daughters = ["v0", "v2"]
    # Formula-generated constraints are independently checked from coordinates
    # by verify_staggered_geometry, rather than reused by its adjacency oracle.
    edges = [["r", side] for side in index_by_side]
    edges.extend([f"v{i}", f"v{j}"] for i in indices
                 for j in (i + 1, i + 2)
                 if j <= upper and (i, j) != (0, 2))
    weights = {side: int(side != "r" and side not in daughters)
               for side in initial}

    # First cut the two rows, then isolate their rectangles from left to right.
    # Keep the daughter union intact until the final, pending vertical cut.
    parent_rectangle = [-1, 3, 1, 2]
    before = {side: box for side, box in rectangles.items()
              if side not in daughters}
    before["parent"] = parent_rectangle
    steps = [{"parent": "box", "axis": "y", "at": 1,
              "children": ["row_lower", "row_upper"]}]
    for row, y in (("lower", 0), ("upper", 1)):
        pieces = sorted((side for side, box in before.items() if box[2] == y),
                        key=lambda side: before[side][0])
        active = f"row_{row}"
        for position, side in enumerate(pieces[:-1]):
            remainder = (pieces[-1] if position == len(pieces) - 2 else
                         f"remainder_{row}_{position}")
            steps.append({"parent": active, "axis": "x",
                          "at": before[side][1],
                          "children": [side, remainder]})
            active = remainder
    steps.append({"parent": "parent", "axis": "x", "at": 1,
                  "children": daughters[:]})

    targets = []
    for colors in permutations((1, 2, 3)):
        target = {"r": 0, **{side: colors[index % 3]
                             for side, index in index_by_side.items()}}
        cost = sum(weight for side, weight in weights.items()
                   if target[side] != initial[side])
        targets.append({"residue_colors": list(colors), "target": target,
                        "changed_old_sides": cost})
    return {
        "family": "two_row_staggered_guillotine_strip", "m": m,
        "scope": "specified legal initial coloring; historical greedy reachability unproved",
        "problem": {"edges": edges, "initial": initial, "daughters": daughters,
                    "fixed": ["r"], "weights": weights},
        "bounds": [lower, upper, 0, 2], "rectangles": rectangles,
        "index_by_side": index_by_side, "parent_rectangle": parent_rectangle,
        "guillotine_steps": steps,
        "certificate": {
            "modulo_classes": [[side for side, i in index_by_side.items()
                                if i % 3 == residue] for residue in range(3)],
            "targets": targets, "minimum_old_cost": 2 * m,
            "old_side_count": 6 * m + 1,
            "proof": "shared-edge triangles force equal colors three indices apart",
        },
    }


def _shared_segment(a: list[int], b: list[int]) -> bool:
    """Recognize a positive-length common side; a corner contact is excluded."""
    ax, bx, ay, by = a
    cx, dx, cy, dy = b
    return (((bx == cx or dx == ax) and min(by, dy) > max(ay, cy)) or
            ((by == cy or dy == ay) and min(bx, dx) > max(ax, cx)))


def verify_staggered_geometry(family: dict) -> dict:
    """Independently audit coordinates, all cuts, H, and the supplied coloring.

    Reconstructing adjacency scans rectangle pairs and does not rely on index
    distances, residue classes, or target certificates.  It verifies an exact
    geometric input and a legal initial coloring, not the old greedy policy.
    Invalid certificates raise ValueError.  The quadratic pair scan is a
    validation procedure, not an asserted efficient coloring algorithm.
    """
    bounds = family["bounds"]
    rectangles = family["rectangles"]
    problem = family["problem"]
    if (len(bounds) != 4 or any(type(x) is not int for x in bounds)
            or bounds[0] >= bounds[1] or bounds[2] >= bounds[3]):
        raise ValueError("invalid bounding rectangle")
    left, right, bottom, top = bounds
    total_area = 0
    for side, box in rectangles.items():
        if (len(box) != 4 or any(type(x) is not int for x in box)
                or not left <= box[0] < box[1] <= right
                or not bottom <= box[2] < box[3] <= top):
            raise ValueError(f"invalid rectangle: {side}")
        total_area += (box[1] - box[0]) * (box[3] - box[2])
    actual = set()
    for (u, a), (v, b) in combinations(rectangles.items(), 2):
        if min(a[1], b[1]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[2], b[2]):
            raise ValueError("rectangle interiors overlap")
        if _shared_segment(a, b):
            actual.add(frozenset((u, v)))
    if total_area != (right - left) * (top - bottom):
        raise ValueError("rectangles do not fill the bounding box")
    for side, box in rectangles.items():
        if box[0] == left or box[1] == right or box[2] == bottom or box[3] == top:
            actual.add(frozenset(("r", side)))

    # Replay every cut geometrically, including the final pending split.
    active = {"box": bounds[:]}
    steps = family["guillotine_steps"]
    for position, step in enumerate(steps):
        parent, axis, at = step["parent"], step["axis"], step["at"]
        children = step["children"]
        if parent not in active or axis not in ("x", "y") or type(at) is not int:
            raise ValueError("invalid cut source, axis, or coordinate")
        if (len(children) != 2 or len(set(children)) != 2
                or any(child in active for child in children)):
            raise ValueError("invalid cut children")
        box = active.pop(parent)
        coordinate = 0 if axis == "x" else 2
        if not box[coordinate] < at < box[coordinate + 1]:
            raise ValueError("cut is not interior to its parent rectangle")
        first, second = box[:], box[:]
        first[coordinate + 1] = at
        second[coordinate] = at
        active[children[0]], active[children[1]] = first, second
        if position == len(steps) - 1:
            if box != family["parent_rectangle"] or children != problem["daughters"]:
                raise ValueError("the last cut does not split the specified daughters")
    if active != rectangles:
        raise ValueError("guillotine leaves differ from the supplied rectangles")

    daughters = problem["daughters"]
    pending = frozenset(daughters)
    if len(daughters) != 2 or len(pending) != 2 or pending not in actual:
        raise ValueError("invalid pending daughter edge")
    supplied = [frozenset(edge) for edge in problem["edges"]]
    if (len(supplied) != len(set(supplied))
            or set(supplied) != actual - {pending}):
        raise ValueError("H does not match geometric adjacency minus the pending edge")
    initial = problem["initial"]
    vertices = {"r", *rectangles}
    if (set(initial) != vertices or any(type(c) is not int or c not in range(4)
                                       for c in initial.values())
            or problem["fixed"] != ["r"] or initial["r"] != 0):
        raise ValueError("invalid initial coloring or fixed exterior")
    if initial[daughters[0]] != initial[daughters[1]]:
        raise ValueError("daughters do not inherit the same parent color")
    if any(len({initial[v] for v in edge}) != 2 for edge in supplied):
        raise ValueError("initial coloring is improper on H")
    expected_weights = {side: int(side != "r" and side not in daughters)
                        for side in vertices}
    if problem["weights"] != expected_weights:
        raise ValueError("costs do not count precisely the unsplit old sides")
    return {"passed": True, "rectangles": len(rectangles),
            "geometric_edges_including_exterior": len(actual),
            "cuts_replayed": len(steps), "area": total_area,
            "historical_greedy_initial_state_reachability": "not_checked"}

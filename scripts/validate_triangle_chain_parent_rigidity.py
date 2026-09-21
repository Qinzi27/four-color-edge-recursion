"""Independently enumerate the last OLD parent map of the rectangle family.

Geometric shared segments construct the graph; a separate two-tree edge
certificate and a generic literal-color enumeration check its rigidity.  These
checks do not replay or extend any naming policy, and do not claim that a
particular policy reaches this geometry for every parameter.
"""

from argparse import ArgumentParser
from datetime import datetime, timezone
from hashlib import sha256
from itertools import combinations, permutations
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.triangle_chain_family import build_staggered_strip, verify_staggered_geometry


def require(condition, message):
    """Keep audit conditions active even under python -O."""
    if not condition:
        raise AssertionError(message)


def parent_graph(family):
    """Derive the genuine unsplit parent graph from positive-length contacts."""
    verify_staggered_geometry(family)
    daughters = family["problem"]["daughters"]
    rectangles = {side: box[:] for side, box in family["rectangles"].items()
                  if side not in daughters}
    rectangles["parent"] = family["parent_rectangle"][:]
    bounds = family["bounds"]
    edges = set()
    for side, box in rectangles.items():
        if box[0] == bounds[0] or box[1] == bounds[1] or box[2] == bounds[2] or box[3] == bounds[3]:
            edges.add(tuple(sorted(("r", side))))
    for (u, a), (v, b) in combinations(rectangles.items(), 2):
        require(not (min(a[1], b[1]) > max(a[0], b[0])
                     and min(a[3], b[3]) > max(a[2], b[2])), "old rectangles overlap")
        vertical = ((a[1] == b[0] or b[1] == a[0])
                    and min(a[3], b[3]) > max(a[2], b[2]))
        horizontal = ((a[3] == b[2] or b[3] == a[2])
                      and min(a[1], b[1]) > max(a[0], b[0]))
        if vertical or horizontal:
            edges.add(tuple(sorted((u, v))))
    require(sum((b[1] - b[0]) * (b[3] - b[2]) for b in rectangles.values())
            == (bounds[1] - bounds[0]) * (bounds[3] - bounds[2]), "old rectangles do not tile frame")
    require(all(tuple(sorted(("r", side))) in edges for side in rectangles), "old exterior not universal")
    return {"rectangles": rectangles, "vertices": ["r", *sorted(rectangles)],
            "edges": [list(edge) for edge in sorted(edges)]}


def two_tree_certificate(m):
    """Give each new interior vertex and its already adjacent parent edge."""
    steps = []
    for index in range(-1, -3 * m - 1, -1):
        anchors = (["parent", "v1"] if index == -1 else ["parent", "v-1"] if index == -2
                   else [f"v{index + 1}", f"v{index + 2}"])
        steps.append({"vertex": f"v{index}", "edge": anchors})
    for index in range(3, 3 * m + 3):
        anchors = (["parent", "v1"] if index == 3 else ["parent", "v3"] if index == 4
                   else [f"v{index - 1}", f"v{index - 2}"])
        steps.append({"vertex": f"v{index}", "edge": anchors})
    return {"root_edge": ["parent", "v1"], "steps": steps}


def verify_two_tree(graph, certificate):
    """Verify all attachments and exact equality to the independent geometric graph."""
    root = certificate["root_edge"]
    require(len(root) == 2 and len(set(root)) == 2 and "r" not in root, "invalid root edge")
    seen, built = set(root), {frozenset(root)}
    for step in certificate["steps"]:
        vertex, anchors = step["vertex"], step["edge"]
        require(vertex not in seen and vertex != "r", "attachment vertex not fresh")
        require(len(anchors) == 2 and len(set(anchors)) == 2
                and set(anchors) <= seen and frozenset(anchors) in built, "attachment edge not present")
        built.update(frozenset((vertex, anchor)) for anchor in anchors)
        seen.add(vertex)
    actual = {frozenset(edge) for edge in graph["edges"] if "r" not in edge}
    require(seen == set(graph["vertices"]) - {"r"}, "certificate omits old vertices")
    require(built == actual, "two-tree edges differ from true rectangle contacts")
    return {"passed": True, "interior_vertices": len(seen), "interior_edges": len(actual),
            "attachments": len(certificate["steps"])}


def enumerate_literal_parent_colors(graph, *, max_nodes=200000):
    """Enumerate all proper 0..3 assignments with r=0 using only raw edges.

    This independent oracle uses neither the two-tree attachment order nor the
    supplied alpha coloring.  A finite cap returns unknown with observed
    witnesses, never an exact count or an impossibility claim.
    """
    if type(max_nodes) is not int or max_nodes < 0:
        raise ValueError("max_nodes must be a nonnegative integer")
    vertices = graph["vertices"]
    adjacency = {v: set() for v in vertices}
    for u, v in graph["edges"]:
        adjacency[u].add(v)
        adjacency[v].add(u)
    stack, targets, nodes = [{"r": 0}], [], 0
    while stack:
        if nodes >= max_nodes:
            return {"status": "unknown", "target_count": None, "targets_seen": len(targets),
                    "targets": targets, "nodes": nodes, "max_nodes": max_nodes}
        partial = stack.pop()
        nodes += 1
        if len(partial) == len(vertices):
            targets.append({v: partial[v] for v in vertices})
            continue
        choices = []
        for position, vertex in enumerate(vertices):
            if vertex not in partial:
                forbidden = {partial[n] for n in adjacency[vertex] if n in partial}
                available = [color for color in range(4) if color not in forbidden]
                choices.append((len(available), position, vertex, available))
        _, _, vertex, available = min(choices)
        for color in reversed(available):
            stack.append({**partial, vertex: color})
    return {"status": "exact", "target_count": len(targets), "targets_seen": len(targets),
            "targets": targets, "nodes": nodes, "max_nodes": max_nodes}


def validate_parameter(m):
    """Check real old geometry, all six colorings, and every final-split cost."""
    family = build_staggered_strip(m)
    graph = parent_graph(family)
    certificate = two_tree_certificate(m)
    structural = verify_two_tree(graph, certificate)
    enumeration = enumerate_literal_parent_colors(graph)
    require(enumeration["status"] == "exact" and enumeration["target_count"] == 6,
            "old parent coloring enumeration did not return exactly six")
    reference = {side: color for side, color in family["problem"]["initial"].items()
                 if side not in family["problem"]["daughters"]}
    reference["parent"] = family["problem"]["initial"]["v0"]
    reference_permutations = []
    for colors in permutations((1, 2, 3)):
        mapping = dict(enumerate((0,) + colors))
        reference_permutations.append({v: mapping[color] for v, color in reference.items()})
    require(all(target in reference_permutations for target in enumeration["targets"]),
            "a genuine old coloring is not a global permutation of alpha")
    costs = []
    for old in enumeration["targets"]:
        inherited = {side: old["parent"] if side in ("v0", "v2") else old[side]
                     for side in family["problem"]["initial"]}
        values = [sum(weight for side, weight in family["problem"]["weights"].items()
                      if inherited[side] != target["target"][side])
                  for target in family["certificate"]["targets"]]
        require(sorted(values) == [2 * m, 2 * m] + [5 * m + 1] * 4,
                "endpoint cost spectrum changed under global old-color permutation")
        costs.append({"old_colors": old, "six_final_costs": values, "minimum_old_cost": min(values)})
    return {"m": m, "parent_graph": graph, "two_tree_certificate": certificate,
            "structural_audit": structural, "literal_enumeration": enumeration,
            "all_old_colorings_equivalent_to_alpha": True, "cost_checks": costs,
            "scope": "old-state rigidity and endpoint cost; no policy reachability claim"}


def main():
    """Save a unique finite certificate report without altering frozen reports."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("choose a new filename; existing research reports are preserved")
    sources = ["fourcolor/triangle_chain_family.py", "scripts/validate_triangle_chain_parent_rigidity.py",
               "tests/test_triangle_chain_parent_rigidity.py"]
    hashes = {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in sources}
    rows = [validate_parameter(m) for m in range(1, 9)]
    require(hashes == {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in sources},
            "source changed during validation")
    report = {"schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "python_version": platform.python_version(), "parameters": list(range(1, 9)),
              "all_passed": True, "source_sha256": hashes, "unchanged_at_end": True,
              "records": rows, "scope": "finite independent checks accompanying a general two-tree proof"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"parameters": list(range(1, 9)), "all_passed": True,
                      "old_colorings_each": 6, "nodes": [r["literal_enumeration"]["nodes"] for r in rows]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

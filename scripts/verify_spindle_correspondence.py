"""Independently verify the nine-side template's Moser-spindle correspondence.

This standard-library check identifies the two nonadjacent vertices A and B.
That quotient operation is not contraction of a real edge, need not preserve
planarity, and does not modify a map or any frozen production naming solver.
The bounded color enumerations below validate these fixed small graphs only.
"""

from argparse import ArgumentParser
from datetime import datetime, timezone
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# This import is only compared with the independent literal below. No producer
# edges or producer verification functions drive the graph computations.
from fourcolor.implicit_inequality import REQUIRED_EDGES


TEMPLATE_VERTICES = ("O", "A", "B", "p", "q", "r", "s", "t", "u")
TEMPLATE_EDGES = (
    ("O", "A"), ("O", "B"), ("O", "p"), ("A", "p"),
    ("O", "q"), ("B", "q"), ("p", "q"), ("r", "p"),
    ("r", "q"), ("r", "A"), ("s", "r"), ("s", "A"),
    ("t", "O"), ("t", "B"), ("t", "s"), ("u", "B"),
    ("u", "r"), ("u", "s"), ("u", "t"),
)

# Only the mathematical edge set is recorded from SageMath's official
# MoserSpindle documentation/source; no implementation is copied or required.
SAGE_SPINDLE_EDGES = (
    (0, 1), (0, 4), (0, 6), (1, 2), (1, 5), (2, 3),
    (2, 5), (3, 4), (3, 5), (3, 6), (4, 6),
)
SPINDLE_MAPPING = {"O": 0, "p": 4, "q": 6, "r": 3,
                   "s": 2, "t": 1, "u": 5}
FOUR_COLOR_WITNESS = {"O": 1, "p": 2, "q": 3, "r": 1,
                      "s": 2, "u": 3, "t": 4}


def require(condition, message):
    """Keep verification active even when Python runs with optimization."""
    if not condition:
        raise ValueError(message)


def edge_set(edges):
    """Represent an undirected simple graph by sorted endpoint pairs."""
    return {tuple(sorted(edge)) for edge in edges}


def enumerate_colorings(vertices, edges, palette_size, equality_pair=None):
    """Count every assignment independently, optionally tracking equal targets.

    Explicit assignment bounds are returned for reproducibility. This function
    does not search production maps or feed assignments into a naming solver.
    """
    positions = {vertex: index for index, vertex in enumerate(vertices)}
    indexed_edges = tuple((positions[a], positions[b]) for a, b in sorted(edges))
    target = (tuple(positions[v] for v in equality_pair)
              if equality_pair is not None else None)
    checked = valid = equal_valid = 0
    for colors in product(range(1, palette_size + 1), repeat=len(vertices)):
        checked += 1
        if all(colors[a] != colors[b] for a, b in indexed_edges):
            valid += 1
            if target is not None and colors[target[0]] == colors[target[1]]:
                equal_valid += 1
    result = {"palette_size": palette_size, "vertex_count": len(vertices),
              "assignments_checked": checked, "proper_colorings": valid}
    if target is not None:
        result.update({"equality_pair": list(equality_pair),
                       "proper_colorings_with_equal_targets": equal_valid})
    return result


def source_hashes():
    """Bind the report to this script and the compared frozen template module."""
    paths = ("scripts/verify_spindle_correspondence.py",
             "fourcolor/implicit_inequality.py")
    return {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in paths}


def build_report():
    """Prove the exact quotient structure and check finite coloring claims."""
    before = source_hashes()
    original = edge_set(TEMPLATE_EDGES)
    require(len(original) == 19, "independent template must have nineteen edges")
    require(original == edge_set(REQUIRED_EDGES), "production template differs")
    require(("A", "B") not in original, "identification targets must be nonadjacent")

    # Identifying A and B coalesces O-A and O-B into one O-a edge. No other
    # edge duplicates arise, so nineteen original edges become eighteen.
    identification = {v: ("a" if v in {"A", "B"} else v)
                      for v in TEMPLATE_VERTICES}
    quotient_vertices = tuple(sorted(set(identification.values())))
    quotient_edges = edge_set((identification[x], identification[y])
                              for x, y in original)
    require(all(x != y for x, y in quotient_edges), "quotient has a loop")
    require(len(quotient_vertices) == 8 and len(quotient_edges) == 18,
            "unexpected quotient size")
    apex_neighbors = {y if x == "a" else x for x, y in quotient_edges
                      if "a" in (x, y)}
    remainder_vertices = tuple(v for v in quotient_vertices if v != "a")
    require(apex_neighbors == set(remainder_vertices), "a must be universal")
    remainder_edges = {edge for edge in quotient_edges if "a" not in edge}
    require(len(remainder_vertices) == 7 and len(remainder_edges) == 11,
            "unexpected seven-vertex remainder size")

    # Check an explicit isomorphism, not merely matching graph sizes or a name.
    require(set(SPINDLE_MAPPING) == set(remainder_vertices), "mapping domain differs")
    require(set(SPINDLE_MAPPING.values()) == set(range(7)), "mapping is not bijective")
    mapped_edges = edge_set((SPINDLE_MAPPING[x], SPINDLE_MAPPING[y])
                            for x, y in remainder_edges)
    require(mapped_edges == edge_set(SAGE_SPINDLE_EDGES),
            "explicit correspondence does not match the official spindle edges")

    three = enumerate_colorings(remainder_vertices, remainder_edges, 3)
    four = enumerate_colorings(remainder_vertices, remainder_edges, 4)
    require(three["assignments_checked"] == 3 ** 7 and three["proper_colorings"] == 0,
            "seven-vertex remainder unexpectedly admits three colors")
    require(four["assignments_checked"] == 4 ** 7 and four["proper_colorings"] > 0,
            "seven-vertex remainder must admit four colors")
    require(set(FOUR_COLOR_WITNESS) == set(remainder_vertices), "witness domain differs")
    require(set(FOUR_COLOR_WITNESS.values()) == {1, 2, 3, 4}, "witness palette differs")
    require(all(FOUR_COLOR_WITNESS[x] != FOUR_COLOR_WITNESS[y]
                for x, y in remainder_edges), "explicit four-color witness is invalid")
    nine = enumerate_colorings(TEMPLATE_VERTICES, original, 4, ("A", "B"))
    require(nine["assignments_checked"] == 4 ** 9,
            "nine-side enumeration does not cover its declared bound")
    require(nine["proper_colorings"] == 312,
            "independent nine-side coloring count differs from expected 312")
    require(nine["proper_colorings_with_equal_targets"] == 0,
            "nine-side implication failed")
    require(source_hashes() == before, "verification sources changed during the run")

    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "passed": True,
        "purpose": "Independent fixed-graph correspondence and coloring check",
        "source_sha256": before,
        "source_hashes_unchanged": True,
        "sources": [{
            "title": "SageMath official MoserSpindle graph documentation and generator",
            "checked_date": "2026-09-19",
            "documentation_url": "https://doc.sagemath.org/html/en/reference/graphs/sage/graphs/generators/smallgraphs.html#sage.graphs.generators.smallgraphs.MoserSpindle",
            "source_url": "https://raw.githubusercontent.com/sagemath/sage/refs/heads/develop/src/sage/graphs/generators/smallgraphs.py",
            "copied_material": "Mathematical eleven-edge graph set only; no SageMath code",
            "retrieval_scope": "Source edge set independently checked during research; this script makes no network requests",
        }],
        "reproducibility": {
            "randomness": "None; exhaustive deterministic enumeration",
            "random_seed": None,
            "graph_scope": "One nine-vertex nineteen-edge template and its fixed seven-vertex remainder",
            "assignment_bounds": {"remainder_three_colors": 3 ** 7,
                                  "remainder_four_colors": 4 ** 7,
                                  "original_four_colors": 4 ** 9},
        },
        "original_template": {"vertices": list(TEMPLATE_VERTICES),
                              "edges": sorted(original),
                              "production_edge_set_equal": True},
        "quotient": {
            "operation": "Identify nonadjacent A and B as a; deduplicate undirected edges",
            "identification": identification,
            "vertices": list(quotient_vertices), "edges": sorted(quotient_edges),
            "vertex_count": 8, "edge_count": 18,
            "universal_vertex": "a", "universal_neighbors": sorted(apex_neighbors),
            "graph_description": "K1 join Moser spindle",
            "chromatic_number": 5,
            "interpretation": "Vertex identification is not contraction of an existing edge and need not preserve planarity",
        },
        "remainder": {
            "vertices": list(remainder_vertices), "edges": sorted(remainder_edges),
            "vertex_count": 7, "edge_count": 11,
            "mapping_to_sage_vertices": SPINDLE_MAPPING,
            "mapped_edges": sorted(mapped_edges),
            "sage_spindle_edges": sorted(edge_set(SAGE_SPINDLE_EDGES)),
            "exact_edge_set_equal": True,
            "three_color_enumeration": three, "four_color_enumeration": four,
            "explicit_four_color_witness": FOUR_COLOR_WITNESS,
            "explicit_witness_valid": True, "chromatic_number": 4,
        },
        "original_four_color_enumeration": nine,
        "direct_proof": [
            "In three colors, the diamond on O,p,q,r forces O=r because adjacent p,q use two distinct colors.",
            "The diamond on r,s,u,t similarly forces r=t because adjacent s,u use two distinct colors.",
            "The real edge O-t forbids O=t, so the seven-vertex remainder is not three-colorable.",
            "The explicit four-color witness proves that the remainder has chromatic number exactly four.",
            "The universal vertex a requires a fifth color in the quotient; conversely adding one fresh color suffices.",
            "Any proper four-coloring of the original with A=B would induce a proper four-coloring of this quotient, which is impossible.",
        ],
        "production_solver_changed": False,
        "limits": [
            "This is an application and exact structural correspondence of an established graph, not a new Moser-spindle discovery.",
            "The quotient is an abstract proof device, not a modified input map or new geometric edge.",
            "Finite enumeration checks this one template only and proves no general naming algorithm complete.",
            "No assignments are supplied to any frozen naming solver and no failed map is repaired here.",
            "The report does not claim that all constraints in the research framework are equivalent to this one template.",
        ],
    }


def main():
    """Write one new report, resolving relative output paths from the repo root."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path,
                        help="New JSON report path; relative paths use the repository root")
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if output.exists():
        parser.error("output already exists; choose a new report path")
    report = build_report()
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also prevents overwriting if another process creates
    # the destination after the early existence check.
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"passed": report["passed"], "quotient_vertices": 8,
                      "quotient_edges": 18, "exact_spindle_isomorphism": True,
                      "original_valid_four_colorings": 312,
                      "original_valid_equal_targets": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()

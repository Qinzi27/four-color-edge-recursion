"""Check eight schematic circle/connector maps without changing a naming solver.

The pink contours are the frame and two rectangular islands. Blue connectors
are tested in every subset. Green contour layers are auxiliary mathematical
records, not extra map edges or an exact tracing of the user's original image.
Only the standard library and the existing Node geometry exporter are used.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
BLUE = (((0, 280), (180, 280)), ((300, 280), (600, 280)),
        ((720, 280), (900, 280)))
MACRO_EDGES = ((0, 1), (1, 2), (2, 0))
ROLE_POINTS = {"outer": (-10, -10), "left_island": (240, 240),
               "right_island": (660, 240), "upper": (450, 80),
               "lower": (450, 500)}
SOURCE_FILES = ("scripts/validate_circle_rank.py", "scripts/restart-geometry.mjs",
                "web/engine.js")
SOURCES = (
    {"title": "Huggett and Moffatt, Bipartite partial duals and circuits in medial graphs",
     "url": "https://arxiv.org/pdf/1106.4189", "location": "Section 3, Theorem 4",
     "used_for": "Even-degree components and bipartite planar region duals"},
    {"title": "Jeff Erickson, Euler's formula for planar maps",
     "url": "https://jeffe.cs.illinois.edu/teaching/compgeom/2021/scribbles/02-25-prep.pdf",
     "location": "Page 1", "used_for": "n-m+F=1+c and bridge deletion"},
    {"title": "CGAL 2D Arrangements official manual",
     "url": "https://doc.cgal.org/latest/Arrangement_on_surface_2/index.html",
     "location": "Basic Arrangements: DCEL and edge insertion",
     "used_for": "Multiple face boundary components; joining components versus splitting a face"},
)


def require(condition, message):
    """Keep all checks active under optimized Python."""
    if not condition:
        raise ValueError(message)


def rectangle(x0, y0, x1, y1):
    """Return four consistently ordered strokes around one island."""
    points = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    return [{"a": a, "b": b} for a, b in zip(points, points[1:] + points[:1])]


def make_cases():
    """Enumerate all eight masks, preserving the eight island source indices."""
    islands = rectangle(180, 180, 300, 390) + rectangle(600, 180, 720, 390)
    return [{"key": f"circle-rank-mask-{mask}", "includeFacePoints": True,
             "document": {"frame": {"width": 900, "height": 600},
                          "strokes": islands + [{"a": BLUE[i][0], "b": BLUE[i][1]}
                                                 for i in range(3) if mask & (1 << i)]}}
            for mask in range(8)]


def components(vertices, edges):
    """Count components by BFS, preserving isolated vertices and parallel edges."""
    adjacent = {v: set() for v in vertices}
    for a, b in edges:
        adjacent[a].add(b)
        adjacent[b].add(a)
    unseen, count = set(vertices), 0
    while unseen:
        count += 1
        queue = [min(unseen)]
        unseen.remove(queue[0])
        for v in queue:
            for w in sorted(adjacent[v] & unseen):
                unseen.remove(w)
                queue.append(w)
    return count


def graph_metrics(vertices, edges):
    """Record cycle rank; this rank is independent-cycle count, not depth."""
    count = components(vertices, edges)
    return {"V": len(vertices), "E": len(edges), "C": count,
            "beta": len(edges) - len(vertices) + count}


def inside(point, polygon):
    """Use odd-even ray crossing; repeated bridge traversals cancel in parity."""
    x, y = point
    parity = False
    for (ax, ay), (bx, by) in zip(polygon, polygon[1:] + polygon[:1]):
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            parity = not parity
    return parity


def identify_roles(geometry, full):
    """Locate all semantic roles from face polygons without relying on face IDs."""
    outer = geometry["outerFace"]
    roles = {}
    for role, point in ROLE_POINTS.items():
        hits = [i for i, polygon in enumerate(geometry["face_points"])
                if i != outer and inside(point, polygon)]
        require(len(hits) <= 1, f"sample belongs to multiple bounded faces: {role}")
        roles[role] = hits[0] if hits else outer
    require(roles["outer"] == outer, "exterior sample was misclassified")
    require(len({roles[k] for k in ("outer", "left_island", "right_island", "upper")}) == 4,
            "island and background samples must identify different faces")
    require((roles["upper"] != roles["lower"]) == full,
            "only the complete connector cycle separates upper and lower")
    require(set(roles.values()) == set(range(len(geometry["faces"]))),
            "role samples must cover every actual face")
    return roles


def coloring_counts(face_count, dual_edges):
    """Exhaust every labelled assignment for palettes 1..4, including exterior."""
    rows = []
    for size in range(1, 5):
        valid, witness = 0, None
        for colors in product(range(1, size + 1), repeat=face_count):
            if all(colors[a] != colors[b] for a, b in dual_edges):
                valid += 1
                if witness is None:
                    witness = list(colors)
        rows.append({"palette_size": size, "assignments_checked": size ** face_count,
                     "proper_colorings": valid, "one_witness_by_face_id": witness})
    first = next(row for row in rows if row["proper_colorings"])
    return {"minimum_colors": first["palette_size"], "counts": rows,
            "minimum_palette_witness_by_face_id": first["one_witness_by_face_id"]}


def boundary_edges(geometry, face):
    """Reduce a facial walk mod 2, so doubled slit/bridge edges disappear."""
    return {edge for edge, count in Counter(d // 2 for d in geometry["faces"][face]).items()
            if count % 2}


def even_degrees(geometry, ids):
    """Return every vertex degree for an auxiliary contour edge set."""
    degree = [0] * len(geometry["vertices"])
    for i in ids:
        edge = geometry["edges"][i]
        degree[edge["a"]] += 1
        degree[edge["b"]] += 1
    require(all(value % 2 == 0 for value in degree), "contour is not Eulerian")
    return degree


def gf2_rank(edge_sets):
    """Compute binary incidence-vector rank using tiny integer bitset elimination."""
    basis = {}
    for edges in edge_sets:
        vector = sum(1 << edge for edge in edges)
        while vector:
            pivot = vector.bit_length() - 1
            if pivot not in basis:
                basis[pivot] = vector
                break
            vector ^= basis[pivot]
    return len(basis)


def analyze(item, exported, mask):
    """Cross-check topology, dual coloring, and explicit two-bit contour labels."""
    require(exported["key"] == item["key"] and exported["status"] == "geometry_ok",
            f"geometry export failed: {exported}")
    geometry, full = exported["geometry"], mask == 7
    real = {i: (e["a"], e["b"]) for i, e in enumerate(geometry["edges"]) if not e["virtual"]}
    vertices = sorted({v for edge in real.values() for v in edge})
    primal = graph_metrics(vertices, list(real.values()))
    # The BFS oracle never uses face IDs: remove each real edge independently.
    bridges = {i for i in real if components(vertices, [e for j, e in real.items() if j != i])
               > primal["C"]}
    shores = geometry["faceOfDart"]
    same_shore = {i for i in real if shores[2 * i] == shores[2 * i + 1]}
    require(bridges == same_shore == set(geometry["real_bridge_edge_ids"]),
            "independent bridge oracle disagrees with face shores")
    require(all(shores[2 * i] == shores[2 * i + 1] for i, e in enumerate(geometry["edges"])
                if e["virtual"]), "virtual connector unexpectedly separates faces")
    selected = [i for i in range(3) if mask & (1 << i)]
    macro = graph_metrics(list(range(3)), [MACRO_EDGES[i] for i in selected])
    faces = len(geometry["faces"])
    require(faces == primal["beta"] + 1 == 4 + macro["beta"], "Euler/rank check failed")
    require(faces == (5 if full else 4), "unexpected face count")
    dual = sorted({tuple(sorted((shores[2 * i], shores[2 * i + 1])))
                   for i in real if i not in bridges})
    coloring = coloring_counts(faces, dual)
    require(coloring["minimum_colors"] == (3 if full else 2), "unexpected face chromatic number")
    roles = identify_roles(geometry, full)
    pink = {i for i in real if geometry["edges"][i]["frame"] or
            any(source < 8 for source in geometry["edges"][i]["sources"])}
    pink_cycles = [{i for i in pink if geometry["edges"][i]["frame"]}]
    pink_cycles += [{i for i in pink if any(start <= s < start + 4
                     for s in geometry["edges"][i]["sources"])} for start in (0, 4)]
    upper = boundary_edges(geometry, roles["upper"]) if full else set()
    lower = boundary_edges(geometry, roles["lower"]) if full else set()
    degrees_a, degrees_b = even_degrees(geometry, pink), even_degrees(geometry, upper)
    require((pink | upper) == set(real) - bridges, "contours must cover exactly all nonbridges")
    require(not (pink | upper) & bridges, "a bridge lies in an auxiliary contour")
    # Face bits are independently measured by crossings of contour segments.
    bits = {}
    for role, point in ROLE_POINTS.items():
        parity = []
        for edge_ids in (pink, upper):
            # A ray crosses each undirected contour segment at most once.
            count = 0
            for i in edge_ids:
                (ax, ay), (bx, by) = (geometry["vertices"][geometry["edges"][i][v]] for v in ("a", "b"))
                x, y = point
                if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
                    count += 1
            parity.append(count % 2)
        bits[role] = parity
        expected = [0, 0] if role in ("outer", "left_island", "right_island") else [1, int(full and role == "upper")]
        require(parity == expected, f"unexpected auxiliary bits at {role}")
    face_bits = {roles[role]: value for role, value in bits.items()}
    require(all(face_bits[a] != face_bits[b] for a, b in dual), "two-bit labels fail a real boundary")
    relations = None
    if full:
        require(lower ^ upper == pink, "lower XOR upper must equal the three pink cycles")
        require(gf2_rank(pink_cycles + [upper]) == 4, "four contour vectors must be independent")
        relations = {"lower_xor_upper_equals_all_pink": True,
                     "pink_three_plus_upper_gf2_rank": 4,
                     "lower_boundary_edge_ids": sorted(lower)}
    flags = [{"edge_id": i, "a": e["a"], "b": e["b"], "virtual": e["virtual"],
              "frame": e["frame"], "sources": e["sources"], "is_real_bridge": i in bridges,
              "shore_face_ids": shores[2 * i:2 * i + 2], "in_contour_A": i in pink,
              "in_contour_B": i in upper} for i, e in enumerate(geometry["edges"])]
    return {"key": item["key"], "blue_mask": mask, "blue_connector_ids": selected,
            "input_document": item["document"], "geometry": geometry,
            "input_source_meaning": {"0_to_3": "left island", "4_to_7": "right island",
                                     "blue_source_to_connector": {str(8 + j): i for j, i in enumerate(selected)}},
            "real_primal": {**primal, "vertex_ids": vertices, "edge_ids": sorted(real),
                            "bridge_edge_ids": sorted(bridges), "bridges_match_shores": True},
            "circle_connection_graph_H": {**macro, "vertices": ["frame", "left_island", "right_island"],
                                          "edges": [list(MACRO_EDGES[i]) for i in selected]},
            "F": faces, "euler_checked": True, "simple_dual_edges": dual,
            "coloring": coloring, "role_sample_points": ROLE_POINTS, "role_face_ids": roles,
            "role_bits": bits, "face_bits": face_bits,
            "contour_edge_ids": {"A_all_pink": sorted(pink), "B_upper_boundary": sorted(upper),
                                 "pink_cycles": [sorted(s) for s in pink_cycles]},
            "contour_degrees": {"A": degrees_a, "B": degrees_b},
            "edge_flags": flags, "full_case_relations": relations, "passed": True}


def hashes():
    """Bind the report to the small verifier and the geometry exporter sources."""
    return {path: sha256((ROOT / path).read_bytes()).hexdigest() for path in SOURCE_FILES}


def main():
    """Run the declared finite experiment once and exclusively create its report."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if output.exists():
        parser.error("output already exists; choose a new report path")
    before, cases = hashes(), make_cases()
    process = subprocess.run(["node", str(ROOT / "scripts/restart-geometry.mjs")], cwd=ROOT,
                             input=json.dumps({"cases": cases}), capture_output=True,
                             text=True, encoding="utf-8", check=True)
    exported = json.loads(process.stdout)
    require(exported["schema_version"] == 1 and len(exported["results"]) == 8,
            "unexpected geometry export schema or count")
    results = [analyze(item, row, mask) for mask, (item, row) in
               enumerate(zip(cases, exported["results"]))]
    require(hashes() == before, "sources changed during verification")
    report = {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "passed": True, "source_sha256": before, "sources_unchanged": True,
              "sources": SOURCES, "source_access_date": "2026-09-20",
              "coordinate_system": exported["coordinate_system"], "engine_limits": exported["engine_limits"],
              "bounds": {"blue_subsets": 8, "maximum_faces": 5, "palettes": [1, 2, 3, 4],
                         "maximum_assignments_per_palette": 4 ** 5,
                         "total_assignments_checked": sum(sum(c["assignments_checked"] for c in r["coloring"]["counts"]) for r in results)},
              "random_seed": None, "randomness": "None; exhaustive deterministic masks and small assignments",
              "assumptions": ["900 by 600 schematic frame and two disjoint rectangular islands",
                              "Two distinct blue contact points per circle when all three connectors are present",
                              "Green A/B contour layers are auxiliary records, not added geometry",
                              "This is a schematic test, not an exact tracing of a user image",
                              "Bridge status is recomputed for each current map; virtual connectors are excluded",
                              "No production naming solver or complete archived corpus is run or modified"],
              "results": results}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"passed": True, "cases": len(results),
                      "summary": [{"mask": r["blue_mask"], "F": r["F"], "beta": r["real_primal"]["beta"],
                                   "chi": r["coloring"]["minimum_colors"]} for r in results]}))


if __name__ == "__main__":
    main()

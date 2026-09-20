"""Independently validate small interface relations and declared-piece gluing.

The oracle enumerates complete named color assignments. It does not call the
producer's partition generator, contraction routine or elimination solver.
Its equality-pair encoding compares partitions without reusing restricted-
growth labels. Old reports and sources are read only; output creation refuses
overwrite, and repository-relative source/input hashes bracket the whole run.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from itertools import combinations, product
import json
from pathlib import Path
from random import Random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.interface_signatures import interface_signature, glue_two_terminal_pieces
from scripts.inside_out_fixtures import make_cases

SOURCES = (
    "scripts/validate_interface_signatures.py",
    "fourcolor/interface_signatures.py", "fourcolor/two_port_reduction.py",
    "fourcolor/orbit_frontier.py", "fourcolor/frontier_order.py",
    "scripts/inside_out_fixtures.py", "scripts/validate_circle_repair.py",
    "scripts/circle_repair_oracles.py", "fourcolor/circle_layers.py",
    "fourcolor/circle_layer_repair.py", "fourcolor/embedding.py",
)
INPUTS = ("outputs/circle-rank-2026-09-20.json",)
SEED = 20260920


def require(condition, message):
    """Retain all scientific checks when Python optimization is enabled."""
    if not condition:
        raise ValueError(message)


def hashes(names):
    """Hash original bytes while exposing repository-relative paths only."""
    return {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in names}


def digest(value):
    """Give serialized inputs a stable, whitespace-independent identifier."""
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(raw).hexdigest()


def equality_pairs(colors):
    """Encode equality by index pairs, independently of producer RGS labels."""
    return tuple((i, j) for i in range(len(colors)) for j in range(i)
                 if colors[i] == colors[j])


def legal_assignments(n, edges, palette):
    """Enumerate every complete named assignment without pruning or a solver."""
    return [colors for colors in product(range(palette), repeat=n)
            if all(colors[a] != colors[b] for a, b in edges)]


def check_signature(n, edges, terminals, palette, order, legal=None):
    """Check projected assignments, equality classes and every returned witness."""
    if legal is None:
        legal = legal_assignments(n, edges, palette)
    projected = {tuple(colors[v] for v in terminals) for colors in legal}
    expected = {equality_pairs(colors) for colors in projected}
    actual = interface_signature(n, edges, terminals, palette, order)
    require({equality_pairs(pattern) for pattern in actual["patterns"]} == expected,
            "interface equality relation differs from full-assignment oracle")
    require(actual["named_boundary_assignments"] == len(projected),
            "named boundary count differs from full-assignment oracle")
    require(actual["feasible"] == bool(legal), "interface feasibility differs")
    witnesses, witness_checks = [], 0
    legal_set = set(legal)
    for query in actual["queries"]:
        pattern, witness = query["pattern"], query["one_coloring"]
        require(query["feasible"] == (equality_pairs(pattern) in expected),
                "partition query feasibility differs")
        if query["feasible"]:
            require(tuple(witness) in legal_set, "query witness is not a legal full coloring")
            require(tuple(witness[v] for v in terminals) == tuple(pattern),
                    "query witness does not realize its ordered terminal pattern")
            witness_checks += 1
        else:
            require(witness is None, "infeasible partition contains a witness")
        witnesses.append({"pattern": pattern, "feasible": query["feasible"],
                          "one_coloring": witness})
    payload = {"n": n, "edges": edges, "terminals": list(terminals),
               "palette_size": palette, "order": list(order)}
    return {"input_sha256": digest(payload), "palette_size": palette,
            "terminals": list(terminals), "matched": True,
            "feasible": actual["feasible"], "patterns": actual["patterns"],
            "named_boundary_assignments": len(projected),
            "full_legal_assignments": len(legal),
            "oracle_projected_assignments_sha256": digest(sorted(projected)),
            "pattern_queries": len(actual["queries"]),
            "witness_checks": witness_checks, "witnesses": witnesses}


def exhaustive_small_graphs():
    """Audit all 76 simple graphs through four vertices and all port subsets."""
    graphs, records = [], []
    for n in range(5):
        possible = list(combinations(range(n), 2))
        order = list(reversed(range(n)))
        for mask in range(1 << len(possible)):
            edges = [list(edge) for bit, edge in enumerate(possible) if mask >> bit & 1]
            key = f"simple-n{n}-mask{mask}"
            graphs.append({"key": key, "n": n, "edges": edges, "order": order,
                           "edge_mask": mask, "edge_mask_order": [list(e) for e in possible]})
            for palette in range(1, 5):
                legal = legal_assignments(n, edges, palette)
                for arity in range(min(3, n) + 1):
                    for subset in combinations(range(n), arity):
                        ports = tuple(reversed(subset))
                        records.append({"graph": key,
                                        **check_signature(n, edges, ports, palette, order, legal)})
    require(len(graphs) == 76 and len(records) == 4140, "exhaustive scope changed")
    return {"graphs": graphs, "records": records,
            "counts": {"graphs": len(graphs), "signature_calls": len(records),
                       "partition_queries": sum(row["pattern_queries"] for row in records),
                       "witness_checks": sum(row["witness_checks"] for row in records)}}


def book_graph(k):
    """Make K2 joined to k independent terminals, numbered terminals first."""
    return [[k, k + 1]] + [[port, inner] for port in range(k) for inner in (k, k + 1)]


def audit_book_family():
    """Enumerate boundary and internal colors separately to check the formula."""
    records, counterexample = [], None
    for k in range(1, 7):
        n, edges = k + 2, book_graph(k)
        for palette in range(1, 5):
            extendable, by_distinct, checked_internal = set(), {}, 0
            for boundary in product(range(palette), repeat=k):
                distinct = len(set(boundary))
                extensions = 0
                for first, second in product(range(palette), repeat=2):
                    colors = boundary + (first, second)
                    extensions += all(colors[a] != colors[b] for a, b in edges)
                    checked_internal += 1
                predicted = max(0, palette - distinct) * max(0, palette - distinct - 1)
                require(extensions == predicted, "book internal extension multiplicity differs")
                require(bool(extensions) == (distinct <= palette - 2),
                        "book extension criterion differs")
                row = by_distinct.setdefault(distinct, {"named_assignments": 0,
                                                       "extendable_assignments": 0,
                                                       "extensions_per_assignment": extensions})
                row["named_assignments"] += 1
                row["extendable_assignments"] += bool(extensions)
                if extensions:
                    extendable.add(boundary)
            orbits = {equality_pairs(boundary) for boundary in extendable}
            q4 = None
            if palette == 4:
                q4 = {"predicted_orbits": 2 ** (k - 1),
                      "predicted_named_assignments": 6 * 2 ** k - 8}
                require(len(orbits) == q4["predicted_orbits"]
                        and len(extendable) == q4["predicted_named_assignments"],
                        "four-color closed form differs")
            api = check_signature(n, edges, list(range(k)), palette,
                                  list(reversed(range(n)))) if k <= 3 else None
            if api is not None:
                require(api["named_boundary_assignments"] == len(extendable),
                        "book API and boundary/internal enumeration disagree")
            payload = {"k": k, "n": n, "edges": edges, "palette_size": palette,
                       "terminals": list(range(k)), "internal": [k, k + 1]}
            records.append({**payload, "input_sha256": digest(payload), "matched": True,
                            "boundary_assignments_checked": palette ** k,
                            "full_assignments_checked": checked_internal,
                            "named_boundary_assignments": len(extendable),
                            "orbit_count": len(orbits), "by_distinct_colors": by_distinct,
                            "four_color_closed_form": q4, "api_check": api})
            if k == 3 and palette == 4:
                pairs = []
                for a, b in combinations(range(k), 2):
                    projection = sorted({(colors[a], colors[b]) for colors in extendable})
                    require(len(projection) == 16, "book3 pair projection is not universal")
                    pairs.append({"ports": [a, b], "named_pairs": projection,
                                  "named_pair_count": len(projection), "mask": "ALL"})
                require((0, 1, 2) not in extendable, "all-distinct book3 assignment extends")
                counterexample = {"k": k, "palette_size": palette,
                                  "named_boundary_assignments": len(extendable),
                                  "pair_projections": pairs, "forbidden_assignment": [0, 1, 2],
                                  "forbidden_assignment_extendable": False,
                                  "reason": "Both adjacent internal vertices have only color 3 left."}
    return {"records": records, "three_port_counterexample": counterexample,
            "counts": {"graph_palette_conditions": len(records),
                       "signature_calls": sum(row["api_check"] is not None for row in records),
                       "full_assignments_checked": sum(row["full_assignments_checked"] for row in records)}}


def audit_original_fixture():
    """Connect the abstract book3 exactly to the frozen original drawing IDs."""
    cases = make_cases()
    matches = [case for case in cases if case["key"] == "circle-rank-mask-7"]
    require(len(matches) == 1, "original all-blue fixture missing or duplicated")
    case = matches[0]
    degrees = Counter(vertex for edge in case["edges"] for vertex in edge)
    ports = [vertex for vertex in range(case["n"]) if degrees[vertex] == 2]
    internal = [vertex for vertex in range(case["n"]) if degrees[vertex] != 2]
    require(case["n"] == 5 and ports == [0, 3, 4] and internal == [1, 2],
            "original book3 face identifiers changed")
    mapping = ports + internal
    mapped = sorted(tuple(sorted((mapping[a], mapping[b]))) for a, b in book_graph(3))
    require(mapped == sorted(tuple(sorted(edge)) for edge in case["edges"]),
            "original face constraints are not exactly the claimed book3")
    checks = [check_signature(case["n"], case["edges"], ports, palette,
                              list(reversed(range(case["n"])))) for palette in range(1, 5)]
    return {"key": case["key"], "n": case["n"], "edges": case["edges"],
            "terminals_original_face_ids": ports, "internal_original_face_ids": internal,
            "book_vertex_to_original_face": mapping,
            "role_face_ids": case["geometry"]["role_face_ids"],
            "original_fixture_sha256": digest(case),
            "fixture_collection_sha256": digest(cases), "fixture_collection_count": len(cases),
            "source_report": case["geometry"]["source_report"],
            "source_case_key": case["geometry"]["source_case_key"],
            "blue_mask": case["geometry"]["blue_mask"],
            "exact_edge_identity_verified": True, "checks": checks}


def audit_random_gluing():
    """Check saved random declared pieces against exhaustive assembled graphs."""
    rng, inputs, records = Random(SEED), [], []
    for index in range(80):
        pieces = []
        for _ in range(rng.randrange(4)):
            n = rng.randrange(2, 5)
            edges = [list(edge) for edge in combinations(range(n), 2) if rng.random() < 0.5]
            pieces.append({"n": n, "edges": edges, "terminals": rng.sample(range(n), 2)})
        key = f"random-glue-{index}"
        inputs.append({"key": key, "pieces": pieces, "pieces_sha256": digest(pieces)})
        for palette in range(1, 5):
            actual = glue_two_terminal_pieces(pieces, palette)
            # Build an independent global-ID mapping from the declared input,
            # rather than accepting the producer's assembled graph as oracle.
            next_vertex, edges = 2, set()
            for piece in pieces:
                mapping = {piece["terminals"][0]: 0, piece["terminals"][1]: 1}
                for vertex in range(piece["n"]):
                    if vertex not in mapping:
                        mapping[vertex] = next_vertex
                        next_vertex += 1
                edges.update(tuple(sorted((mapping[a], mapping[b]))) for a, b in piece["edges"])
            require(actual["n"] == next_vertex and actual["edges"] == [list(e) for e in sorted(edges)],
                    "producer assembled a different declared-piece graph")
            legal = legal_assignments(next_vertex, sorted(edges), palette)
            expected = 0
            for colors in legal:
                expected |= 1 if colors[0] == colors[1] else 2
            require(actual["mask"] == expected and actual["feasible"] == bool(legal),
                    "glued relation differs from exhaustive assignments")
            if legal:
                require(tuple(actual["one_coloring"]) in set(legal), "glued witness invalid")
            else:
                require(actual["one_coloring"] is None, "infeasible gluing has a witness")
            require(actual["summary"]["gluing_search_calls"] == 0,
                    "gluing reports an extra search call")
            records.append({"input": key, "palette_size": palette,
                            "input_sha256": digest({"pieces": pieces, "palette_size": palette}),
                            "n": next_vertex, "edges": [list(e) for e in sorted(edges)],
                            "matched": True, "mask": expected, "feasible": bool(legal),
                            "full_assignments_checked": palette ** next_vertex,
                            "full_legal_assignments": len(legal),
                            "piece_masks": [row["mask"] for row in actual["pieces"]],
                            "one_coloring": actual["one_coloring"],
                            "pattern_queries": actual["summary"]["pattern_queries"],
                            "gluing_search_calls": actual["summary"]["gluing_search_calls"]})
    return {"seed": SEED, "inputs": inputs, "records": records,
            "counts": {"piece_collections": len(inputs), "gluing_calls": len(records),
                       "full_assignments_checked": sum(row["full_assignments_checked"] for row in records)}}


def main():
    """Run the fixed protocol and create one fresh, auditable report."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="Fresh JSON output; an existing file is never overwritten")
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    if output.exists():
        parser.error("output exists; choose a fresh filename")
    before_sources, before_inputs = hashes(SOURCES), hashes(INPUTS)
    exhaustive = exhaustive_small_graphs()
    print(json.dumps({"stage": "exhaustive", **exhaustive["counts"]}), flush=True)
    family = audit_book_family()
    original = audit_original_fixture()
    gluing = audit_random_gluing()
    require(hashes(SOURCES) == before_sources and hashes(INPUTS) == before_inputs,
            "source or input bytes changed during validation")
    report = {"schema_version": 1, "passed": True,
              "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "source_sha256": before_sources, "input_sha256": before_inputs,
              "sources_unchanged": True, "inputs_unchanged": True,
              "protocol": {"small_graphs": "All simple graphs n=0..4, q=1..4, all terminal subsets of arity 0..3.",
                           "orders": "Reverse vertex order and reverse terminal-subset order.",
                           "oracle": "Complete named assignments and equality-pair encoding; no producer pattern generator.",
                           "book_family": "K2 joined to k independent terminals, k=1..6, q=1..4; all internal and boundary colors.",
                           "gluing": "80 fixed-seed collections of zero to three pieces, each n=2..4, four palettes.",
                           "scope": "Finite correctness audit; no timing, novelty or general coloring-theorem claim.",
                           "boundary_count": "Distinct extendable named boundary assignments, not full coloring multiplicities."},
              "counts": {"exhaustive_signature_calls": exhaustive["counts"]["signature_calls"],
                         "book_signature_calls": family["counts"]["signature_calls"],
                         "original_fixture_signature_calls": len(original["checks"]),
                         "random_gluing_calls": gluing["counts"]["gluing_calls"]},
              "exhaustive_small_graphs": exhaustive, "book_family": family,
              "original_fixture": original, "random_gluing": gluing}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"passed": True, "counts": report["counts"],
                      "report_sha256": sha256(output.read_bytes()).hexdigest()}), flush=True)


if __name__ == "__main__":
    main()

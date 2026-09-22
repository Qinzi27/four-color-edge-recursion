"""Posterior geometry/contact audit without making a production name choice.

Face walks are reconstructed here from coordinate rotations, rather than using
the adapter's PlaneMap. Literal set composition replays every propagation step.
Small inputs additionally use the frozen exhaustive v2 audit. The independent
exact oracle receives only real shared-edge adjacency and ORIGINAL singleton
restrictions; its result never feeds back into the producer.

Shared boundaries: Node still supplies the planarized vertices/edges, and the
whole-line grouping metadata is checked with the existing build_whole_lines.
This is a finite precision audit (1e-5 pixels), not an exact real-arithmetic
planarizer or a proof that path consistency decides global four-colorability.
"""

from collections import defaultdict
from hashlib import sha256
from itertools import combinations, product
import json
from math import atan2, hypot, isfinite, prod
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.whole_lines import build_whole_lines
from scripts.exact_extendibility_oracle import solve_exact, verify_exact_result
from scripts.validate_quaternary_contacts_v2 import (
    audit_document, check_domains, check_matrix, check_state, expected_state,
    raw_metadata, require,
)

AUDIT_VERSION = "quaternary-real-geometry-audit-v1"
EPS = 1e-5


def _digest(value):
    """Match stored JSON digests without importing a geometry transformation."""
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")).hexdigest()


def _same(actual, expected, label):
    """JSON equality distinguishes booleans from integers in evidence records."""
    require(json.dumps(actual, sort_keys=True, allow_nan=False)
            == json.dumps(expected, sort_keys=True, allow_nan=False), label + " differs")


def _components(edges):
    """Count components without treating virtual-only vertices as real ones."""
    neighbors = defaultdict(set)
    for edge in edges:
        neighbors[edge["a"]].add(edge["b"])
        neighbors[edge["b"]].add(edge["a"])
    unseen, result = set(neighbors), []
    while unseen:
        reached, queue = {min(unseen)}, [min(unseen)]
        while queue:
            for other in neighbors[queue.pop()] - reached:
                reached.add(other)
                queue.append(other)
        unseen -= reached
        result.append(sorted(reached))
    return result, len(neighbors)


def _on_segment(point, first, last):
    """Return a projected parameter only for points on a finite drawn segment."""
    dx, dy = last[0] - first[0], last[1] - first[1]
    length = hypot(dx, dy)
    t = ((point[0] - first[0]) * dx + (point[1] - first[1]) * dy) / length**2
    distance = abs(dx * (point[1] - first[1]) - dy * (point[0] - first[0])) / length
    return t if distance <= EPS and -EPS / length <= t <= 1 + EPS / length else None


def _check_intersections(points, edges):
    """Reject un-noded crossings, endpoint-on-edge contacts and overlaps."""
    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    for first, second in combinations(edges, 2):
        ends_a, ends_b = (first["a"], first["b"]), (second["a"], second["b"])
        a, b = (points[v] for v in ends_a)
        c, d = (points[v] for v in ends_b)
        shared = set(ends_a) & set(ends_b)
        for vertex in set(ends_a) - shared:
            require(_on_segment(points[vertex], c, d) is None, "un-noded contact/overlap")
        for vertex in set(ends_b) - shared:
            require(_on_segment(points[vertex], a, b) is None, "un-noded contact/overlap")
        if not shared:
            require(not (cross(a, b, c) * cross(a, b, d) < 0
                         and cross(c, d, a) * cross(c, d, b) < 0), "un-noded proper crossing")


def _face_walks(rotation, darts):
    """Walk mathematical left shores via the predecessor of the reverse dart."""
    predecessor = {}
    for outgoing in rotation:
        row = [dart for dart in outgoing if dart in darts]
        for i, dart in enumerate(row):
            predecessor[dart] = row[i - 1]
    used, walks = set(), []
    for start in sorted(darts):
        if start in used:
            continue
        dart, walk = start, []
        while dart not in used:
            used.add(dart)
            walk.append(dart)
            dart = predecessor[dart ^ 1]
        require(dart == start, "boundary walk does not close at its own start")
        walks.append(walk)
    require(used == darts, "boundary walks omit darts")
    return walks


def _check_drawing_sources(geometry, adapted):
    """Check input echo and per-stroke coverage; do not read any archived color."""
    drawing = adapted["drawing"]
    if drawing is None:
        require(adapted["geometry_input"] is None and adapted["drawing_sha256"] is None
                and adapted["geometry_key"] is None, "missing drawing has nonempty provenance")
        return False
    require(isinstance(drawing, dict) and isinstance(drawing.get("strokes"), list), "invalid drawing")
    require(adapted["drawing_sha256"] == _digest(drawing), "drawing digest mismatch")
    expected = {"frame": {"width": 900, "height": 600}, "strokes": [
        {"a": stroke["a"], "b": stroke["b"]} for stroke in drawing["strokes"]]}
    _same(adapted["geometry_input"], expected, "geometry input excludes old names")
    undirected = sorted({tuple(sorted((tuple(s["a"]), tuple(s["b"])))) for s in expected["strokes"]})
    require(adapted["geometry_key"] == _digest({"frame": expected["frame"], "undirected_stroke_set": undirected}),
            "geometry key differs from original stroke set")
    _same(adapted["ignored_drawing_fields"],
          sorted(set(drawing) - {"frame", "schemaVersion", "strokes"}), "ignored drawing fields")
    intervals = defaultdict(list)
    for edge in geometry["edges"]:
        for source in edge["sources"]:
            require(source < len(expected["strokes"]), "source stroke identity outside input")
            stroke = expected["strokes"][source]
            parameters = [_on_segment(geometry["vertices"][edge[end]], stroke["a"], stroke["b"])
                          for end in ("a", "b")]
            require(None not in parameters, "atomic edge is off its stated source stroke")
            intervals[source].append(sorted(parameters))
    for source, stroke in enumerate(expected["strokes"]):
        length = hypot(stroke["b"][0] - stroke["a"][0], stroke["b"][1] - stroke["a"][1])
        require(length > 0, "zero-length source stroke")
        cursor = 0.0
        for first, last in sorted(intervals[source]):
            require(first <= cursor + EPS / length, "source stroke has an uncovered interval")
            cursor = max(cursor, last)
        require(cursor >= 1 - EPS / length, "source stroke not covered")
    return True


def audit_geometry(geometry, adapted):
    """Independently rebuild true contacts and compare the entire adapter record."""
    require(isinstance(geometry, dict), "geometry must be an object")
    points, edges = geometry["vertices"], geometry["edges"]
    require(isinstance(points, list) and bool(points) and isinstance(edges, list), "invalid graph arrays")
    require(all(isinstance(p, list) and len(p) == 2
                and all(type(x) in (int, float) and isfinite(x) for x in p)
                and 0 <= p[0] <= 900 and 0 <= p[1] <= 600 for p in points), "invalid frame coordinates")
    require(len({tuple(p) for p in points}) == len(points), "duplicate coordinate vertices")
    outgoing, real_ids, virtual_ids, unordered = [[] for _ in points], [], [], set()
    for i, edge in enumerate(edges):
        require(all(type(edge[v]) is int and 0 <= edge[v] < len(points) for v in ("a", "b"))
                and edge["a"] != edge["b"], "invalid atomic endpoints")
        require(type(edge["virtual"]) is bool and type(edge["frame"]) is bool, "nonstrict edge flags")
        require(isinstance(edge["sources"], list)
                and all(type(v) is int and v >= 0 for v in edge["sources"])
                and len(set(edge["sources"])) == len(edge["sources"]), "invalid stroke references")
        pair = tuple(sorted((edge["a"], edge["b"])))
        require(pair not in unordered, "duplicate atomic edge")
        unordered.add(pair)
        outgoing[edge["a"]].append(2 * i)
        outgoing[edge["b"]].append(2 * i + 1)
        (virtual_ids if edge["virtual"] else real_ids).append(i)
        require(not edge["virtual"] or (not edge["frame"] and not edge["sources"]),
                "virtual connector claims physical provenance")
        require(edge["virtual"] or edge["frame"] or bool(edge["sources"]), "unattributed real edge")
        if edge["frame"]:
            a, b = points[edge["a"]], points[edge["b"]]
            require((a[0] == b[0] and a[0] in (0, 900))
                    or (a[1] == b[1] and a[1] in (0, 600)), "frame edge is not on rectangular boundary")
    _check_intersections(points, edges)
    require(len(geometry["rotation"]) == len(points), "rotation vertex count differs")
    coordinate_rotation = []
    for vertex, darts in enumerate(outgoing):
        def angle(dart):
            edge = edges[dart // 2]
            other = edge["a"] if dart % 2 else edge["b"]
            return atan2(-(points[other][1] - points[vertex][1]), points[other][0] - points[vertex][0])
        ordered = sorted(darts, key=angle)
        supplied = geometry["rotation"][vertex]
        require(isinstance(supplied, list) and all(type(d) is int for d in supplied)
                and len(supplied) == len(ordered) and set(supplied) == set(ordered), "rotation dart incidence differs")
        require(bool(ordered), "isolated augmented vertex")
        start = ordered.index(supplied[0])
        require(supplied == ordered[start:] + ordered[:start], "coordinate cyclic rotation differs")
        coordinate_rotation.append(ordered)
    walks = _face_walks(coordinate_rotation, set(range(2 * len(edges))))
    labels = [-1] * (2 * len(edges))
    for face, walk in enumerate(walks):
        for dart in walk:
            labels[dart] = face
    _same(geometry["faces"], walks, "global face walks")
    _same(geometry["faceOfDart"], labels, "global dart-side IDs")
    components, vertex_count = _components(edges)
    require(len(components) == 1 and vertex_count - len(edges) + len(walks) == 2,
            "augmented graph is not a connected plane embedding")
    areas = []
    for walk in walks:
        polygon = [points[edges[d // 2]["b" if d % 2 else "a"]] for d in walk]
        areas.append(-sum(a[0] * b[1] - b[0] * a[1]
                          for a, b in zip(polygon, polygon[1:] + polygon[:1])) / 2)
    outer = [i for i, area in enumerate(areas) if area < -EPS]
    require(len(outer) == 1 and type(geometry["outerFace"]) is int
            and geometry["outerFace"] == outer[0], "outer face differs from coordinate orientation")
    require(all(abs(area) > EPS for area in areas)
            and abs(areas[outer[0]] + 900 * 600) <= 0.1, "outer boundary/region area differs from frame")
    require(all(labels[2 * i] == labels[2 * i + 1] for i in virtual_ids), "virtual connector separates regions")
    real_components, real_vertices = _components([edges[i] for i in real_ids])
    original = geometry["original"]
    require(all(type(original[k]) is int and original[k] > 0 for k in ("vertices", "edges", "components")),
            "invalid original Euler counts")
    require(len(walks) == len(real_ids) - real_vertices + len(real_components) + 1
            == original["edges"] - original["vertices"] + original["components"] + 1
            and original["components"] == len(real_components), "real disconnected Euler count differs")
    sides = [f"S{i}" for i in range(len(walks))]
    _same(adapted["geometry"], geometry, "adapter geometry echo")
    require(adapted["geometry_sha256"] == _digest(geometry), "geometry digest mismatch")
    require(type(adapted["schema_version"]) is int and adapted["schema_version"] == 1
            and adapted["status"] == "adapted" and adapted["old_colors_read"] is False
            and type(adapted["choices"]) is int and adapted["choices"] == 0
            and type(adapted["propagation_runs"]) is int and adapted["propagation_runs"] == 0,
            "adapter made choices or claims another schema")
    _same(adapted["side_order"], sides, "adapter side order")
    require(adapted["outer_side_id"] == sides[outer[0]], "adapter outer side differs")
    doc = adapted["contact_document"]
    raw_metadata(doc)
    require(set(doc) == {"sides", "lines", "anchors", "states", "point_contacts"},
            "geometry adapter introduced extra logical constraints")
    _same(doc["sides"], sides, "contact side identities")
    expected_lines = [{"id": f"E{i}", "left": sides[labels[2 * i]], "right": sides[labels[2 * i + 1]],
                       "kind": "bridge" if labels[2 * i] == labels[2 * i + 1] else "separator"}
                      for i in real_ids]
    _same(doc["lines"], expected_lines, "atomic physical contact coverage/direction")
    adjacent = {tuple(sorted((labels[2 * i], labels[2 * i + 1]))) for i in real_ids
                if labels[2 * i] != labels[2 * i + 1]}
    # Both shores of every incident real edge are used independently of the
    # producer's outgoing-left-only convention; point pairs impose no NEQ.
    vertices, witnesses = [], defaultdict(list)
    for vertex, rotation in enumerate(geometry["rotation"]):
        real_darts = [d for d in rotation if not edges[d // 2]["virtual"]]
        incident = sorted({labels[d ^ flip] for d in real_darts for flip in (0, 1)})
        pure = [p for p in combinations(incident, 2) if p not in adjacent]
        for pair in pure:
            witnesses[pair].append(vertex)
        vertices.append({"vertex": vertex, "point": points[vertex], "real_outgoing_darts_ccw": real_darts,
                         "incident_side_ids": [sides[i] for i in incident],
                         "globally_point_only_pairs": [[sides[a], sides[b]] for a, b in pure]})
    point_records = [{"sides": [sides[a], sides[b]], "vertices": vs} for (a, b), vs in sorted(witnesses.items())]
    _same(adapted["vertex_contacts"], vertices, "vertex contact provenance")
    _same(adapted["point_contact_provenance"], point_records, "point-only pairs")
    _same(doc["point_contacts"], [{"sides": row["sides"]} for row in point_records], "point-contact echo")
    real_walks = []
    for walk in _face_walks(coordinate_rotation, {d for i in real_ids for d in (2 * i, 2 * i + 1)}):
        region_ids = {labels[d] for d in walk}
        require(len(region_ids) == 1, "real boundary mixes global regions")
        face = region_ids.pop()
        real_walks.append({"id": f"W{len(real_walks)}", "region_id": sides[face], "face_index": face,
                           "darts": walk, "edge_ids": [d // 2 for d in walk]})
    _same(adapted["real_boundary_walks"], real_walks, "real boundary walks")
    regions = [{"id": sides[i], "face_index": i, "is_outer": i == outer[0],
                "augmented_boundary_darts": walk,
                "real_boundary_walk_ids": [w["id"] for w in real_walks if w["face_index"] == i]}
               for i, walk in enumerate(walks)]
    _same(adapted["regions"], regions, "global regions retain all boundary components")
    _same(adapted["real_components"], real_components, "real components")
    # This existing whole-line implementation is explicitly a SHARED check.
    mothers = build_whole_lines(geometry)
    _same(adapted["whole_lines"], mothers.lines, "shared whole-line grouping")
    spans = {span["edge"]: (line["id"], span) for line in mothers.lines for span in line["spans"]}
    provenance, virtual = [], []
    for i, edge in enumerate(edges):
        evidence = {"edge_id": i, "dart": 2 * i, "tail_vertex": edge["a"], "head_vertex": edge["b"],
                    "a": points[edge["a"]], "b": points[edge["b"]],
                    "left_side": sides[labels[2 * i]], "right_side": sides[labels[2 * i + 1]],
                    "frame": edge["frame"], "virtual": edge["virtual"],
                    "source_stroke_indices": edge["sources"]}
        if edge["virtual"]:
            virtual.append(evidence)
        else:
            mother, span = spans[i]
            evidence.update(line_id=f"E{i}", mother_id=mother, mother_span=span)
            if adapted["drawing"] is not None:
                evidence["source_strokes"] = [{"index": s, **adapted["geometry_input"]["strokes"][s]}
                                              for s in edge["sources"]]
            provenance.append(evidence)
    _same(adapted["atomic_edge_provenance"], provenance, "physical edge provenance")
    _same(adapted["virtual_connectors"], virtual, "virtual connector provenance")
    sources_checked = _check_drawing_sources(geometry, adapted)
    _same(adapted["validation"], {"python_global_face_orbits_match": True,
          "real_euler_region_count": len(sides), "original_component_count": len(real_components),
          "real_edge_count": len(real_ids), "real_boundary_walk_count": len(real_walks),
          "source_stroke_coverage_checked": sources_checked}, "adapter validation metadata")
    return {"passed": True, "faces": len(sides), "real_edges": len(real_ids), "virtual_edges": len(virtual_ids),
            "true_adjacencies": len(adjacent), "point_only_pairs": len(point_records),
            "real_components": len(real_components), "real_boundary_walks": len(real_walks),
            "coordinate_rotation_outer_and_crossings_checked": True, "source_coverage_checked": sources_checked,
            "precision_pixels": EPS, "shared_checks": ["Node planarization input", "whole-line grouping metadata"]}, sorted(adjacent)


def _pairs(mask):
    """Decode literal ordered pairs without producer composition helpers."""
    return {(a, b) for a, b in product((1, 2, 3, 4), repeat=2) if mask & (1 << (4 * (a - 1) + b - 1))}


def _mask(pairs):
    """Encode an independently derived literal set for evidence comparison."""
    return sum(1 << (4 * (a - 1) + b - 1) for a, b in pairs)


def audit_bounded_contacts(document, outcome):
    """Audit all metadata and replay sound set deletions without assignment enumeration."""
    sides, initial_domains, sources = raw_metadata(document)
    n, index = len(sides), {s: i for i, s in enumerate(sides)}
    require(type(outcome["schema_version"]) is int and outcome["schema_version"] == 1
            and outcome["model"] == "quaternary-contact-relations-v1", "wrong contact producer")
    _same(outcome["original_input"], document, "contact original input")
    _same(outcome["side_order"], sides, "contact side order")
    require(type(outcome["choices"]) is int and outcome["choices"] == 0
            and type(outcome["backtracks"]) is int and outcome["backtracks"] == 0
            and outcome["representatives_are_assignments"] is False, "representative became a commitment")
    check_domains(outcome["initial_domains"], n, "initial domains")
    check_domains(outcome["domains"], n, "final domains")
    require(outcome["initial_domains"] == initial_domains, "initial domains differ")
    check_matrix(outcome["initial_relations"], n, "initial relations")
    check_matrix(outcome["relations"], n, "final relations")
    unequal = {tuple(sorted((index[l["left"]], index[l["right"]]))) for l in document["lines"] if l["kind"] == "separator"}
    equal = {tuple(sorted((index[a], index[b]))) for a, b in document.get("equal_names", [])}
    current = [[{(a, b) for a in initial_domains[i] for b in initial_domains[j]
                 if (i != j or a == b) and (tuple(sorted((i, j))) not in unequal or a != b)
                 and (tuple(sorted((i, j))) not in equal or a == b)} for j in range(n)] for i in range(n)]
    require(outcome["initial_relations"] == [[_mask(p) for p in row] for row in current], "wrong initial constraints")
    trace = outcome["trace"]
    require(isinstance(trace, list) and type(outcome["revisions"]) is int
            and outcome["revisions"] >= len(trace), "trace exceeds attempted revision count")
    for step in trace:
        require(not any(not pairs for row in current for pairs in row), "trace continues after a conflict")
        require(isinstance(step, dict) and set(step) == {"i", "j", "via", "before", "left", "right", "after", "removed"}
                and all(type(v) is int for v in step.values()), "malformed trace step")
        i, j, k = step["i"], step["j"], step["via"]
        require(all(0 <= v < n for v in (i, j, k)), "trace side outside input")
        before, left, right = current[i][j], current[i][k], current[k][j]
        require((step["before"], step["left"], step["right"]) == (_mask(before), _mask(left), _mask(right)),
                "trace premises differ from current literal relations")
        after = before & {(a, b) for a, c in left for other, b in right if c == other}
        require(after != before and step["after"] == _mask(after)
                and step["removed"] == _mask(before - after), "trace deletion is not exact set composition")
        current[i][j] = after
        current[j][i] = {(b, a) for a, b in after}
    require(outcome["relations"] == [[_mask(p) for p in row] for row in current], "final matrix is not the replayed trace")
    conflict = any(not p for row in current for p in row)
    if not conflict:
        # Every retained pair must have a supporting literal intermediate name.
        for i, j, k in product(range(n), repeat=3):
            require(all(any((a, c) in current[i][k] and (c, b) in current[k][j] for c in (1, 2, 3, 4))
                        for a, b in current[i][j]), "nonconflict result is not a set-relation fixed point")
    domains = [sorted(a for a, b in current[i][i] if a == b) for i in range(n)]
    require(outcome["domains"] == domains, "domains differ from diagonal relations")
    for key in ("initial_states", "name_states", "explicit_anchor_sources"):
        require(isinstance(outcome[key], dict) and set(outcome[key]) == set(sides), "wrong state/source identity coverage")
    _same(outcome["explicit_anchor_sources"], sources, "explicit anchor source records")
    for i, side in enumerate(sides):
        check_state(outcome["initial_states"][side], expected_state(initial_domains[i], sources[side]), "initial state")
        check_state(outcome["name_states"][side], expected_state(domains[i], sources[side]), "final state")
    status = "conflict" if conflict else "solved" if all(len(d) == 1 for d in domains) else "underdetermined"
    require(outcome["status"] == status, "status is not the literal singleton/empty classification")
    _same(outcome["point_contacts"], document.get("point_contacts", []), "point echo")
    _same(outcome["equal_names"], document.get("equal_names", []), "logical EQ echo")
    require(isinstance(outcome["lines"], list) and len(outcome["lines"]) == len(document["lines"]), "line count differs")
    for source, line in zip(document["lines"], outcome["lines"]):
        require(all(line[k] == v for k, v in source.items()), "line identity/direction differs")
        expected = current[index[source["left"]]][index[source["right"]]]
        for view, pairs, left, right in ((line, expected, source["left"], source["right"]),
                (line["reverse"], {(b, a) for a, b in expected}, source["right"], source["left"])):
            require(view["left"] == left and view["right"] == right, "reverse side identity differs")
            require(type(view["relation_mask"]) is int and view["relation_mask"] == _mask(pairs), "line mask differs")
            _same(view["allowed_pairs"], [list(p) for p in sorted(pairs)], "line literal pairs")
            word = view["relation_code"]
            require(isinstance(word, str) and len(word) == 8 and all(c in "0123" for c in word)
                    and int(word, 4) == _mask(pairs), "packed directed relation differs")
    if status == "solved":
        colors = [d[0] for d in domains]
        _same(outcome["colors"], dict(zip(sides, colors)), "solved colors")
        require(all(colors[i] in initial_domains[i] for i in range(n))
                and all(colors[a] != colors[b] for a, b in unequal)
                and all(colors[a] == colors[b] for a, b in equal), "solved colors violate original constraints")
    else:
        require(outcome["colors"] is None, "unresolved display exported as a coloring")
    return {"passed": True, "metadata_passed": True, "trace_audit": "independent_literal_set_replay",
            "trace_steps_checked": len(trace), "final_fixed_point": "not_required_after_conflict" if conflict else "checked",
            "attempted_revision_telemetry": "lower_bound_checked_not_worklist_replayed",
            "complete_assignment_preservation": "sound_each_step_by_existential_pair_composition",
            "status": status}


def audit_run(geometry, adapted, outcome, *, assignment_limit=1048576, node_limit=200000):
    """Return compact checks plus the complete posterior oracle certificate.

    The assignment threshold counts the product of ORIGINAL domains, before
    propagation. A node-budget exhaustion is UNKNOWN, never evidence of UNSAT.
    Non-singleton restricted input words are supported by the model, but the
    adjacency-only oracle then solves a relaxation; this distinction is explicit.
    """
    require(type(assignment_limit) is int and assignment_limit >= 0, "invalid assignment limit")
    require(type(node_limit) is int and node_limit >= 0, "invalid oracle node limit")
    geometry_audit, true_edges = audit_geometry(geometry, adapted)
    document = adapted["contact_document"]
    sides, initial_domains, _ = raw_metadata(document)
    bounded = audit_bounded_contacts(document, outcome)
    size = prod(len(d) for d in initial_domains)
    if size <= assignment_limit:
        exhaustive = {**audit_document(document, outcome), "producer_status": outcome["status"], "status": "run"}
    else:
        exhaustive = {"status": "not_run", "reason": "initial_assignment_product_exceeds_limit",
                      "literal_assignments_checked": 0, "legal_assignments": None, "one_witness": None}
    anchors = {i: d[0] for i, d in enumerate(initial_domains) if len(d) == 1}
    oracle = solve_exact(len(sides), true_edges, anchors, node_limit=node_limit)
    verified = verify_exact_result(len(sides), true_edges, anchors, oracle)
    exact_scope = all(len(d) in (1, 4) for d in initial_domains)
    witness = oracle["witness"]
    contact_witness = witness is not None and all(witness[i] in d for i, d in enumerate(initial_domains))
    if contact_witness:
        require(outcome["status"] != "conflict", "producer rejected an independently valid complete coloring")
        for i, a in enumerate(witness):
            require(a in outcome["domains"][i], "producer lost oracle witness color")
            for j, b in enumerate(witness):
                require((a, b) in _pairs(outcome["relations"][i][j]), "producer lost oracle witness ordered pair")
    if exhaustive["status"] == "run" and exact_scope and oracle["status"] != "unknown":
        require((exhaustive["legal_assignments"] > 0) == (oracle["status"] == "sat"),
                "offline oracle and independent complete enumeration disagree")
    return {"passed": True, "audit_version": AUDIT_VERSION, "geometry": geometry_audit,
            "bounded_metadata_trace": bounded, "assignment_product": size, "assignment_limit": assignment_limit,
            "full_enumeration": exhaustive, "oracle": oracle, "oracle_verification": verified,
            "oracle_scope": "original_contacts_and_singleton_inputs" if exact_scope else "relaxation_ignoring_nonsingleton_domain_restrictions",
            "oracle_input": {"n": len(sides), "edges": [list(p) for p in true_edges],
                             "anchors": [[i, c] for i, c in sorted(anchors.items())]},
            "oracle_witness_satisfies_all_input_domains": contact_witness if witness is not None else None,
            "oracle_feedback_to_producer": False,
            "scope": "Finite geometry conversion and sound relation filtering; underdetermined is not a global extension claim."}

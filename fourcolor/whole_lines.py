"""Whole drawn lines with ordered shores and line-to-line attachment records.

This adapter does NOT terminate a mother line at a T or X junction. Interior
lines are maximal connected collinear runs in the already planarized drawing;
the rectangular frame is one explicit closed line. Bends other than the frame
require a future user-supplied continuation policy. No color determines a line
ID. Atomic edges, side-continuation orbits, and whole lines remain distinct.

Candidate propagation is a necessary-condition filter, not a complete coloring
algorithm. Four is an INPUT palette, never a conclusion of this module.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from math import hypot, isfinite

from .embedding import PlaneMap


GEOMETRY_TOLERANCE = 1e-5  # Pixels; imported vertices are rounded to 1e-6 pixels.


@dataclass
class WholeLineModel:
    """Keep the validated topology and reversible whole-line indexing together."""

    plane_map: PlaneMap
    lines: list[dict]
    virtual_edges: tuple[int, ...]
    edge_owner: dict[int, str]


def _point_key(point):
    """Use geometric endpoints rather than input edge numbers as straight IDs."""
    return ",".join(format(value, ".9g") for value in point)


def build_whole_lines(geometry: dict) -> WholeLineModel:
    """Recover complete straight runs without using supplied face IDs or colors.

    ``geometry`` uses the web engine's vertices, edges and CCW rotation schema.
    Virtual island connectors are retained as topology metadata, never promoted
    to mother lines. Collinear overlaps have already been unioned by planarize.
    A gap is not crossed. Ambiguous near-collinear continuation is rejected.
    """
    points = [tuple(point) for point in geometry["vertices"]]
    if any(len(p) != 2 or any(not isfinite(x) for x in p) for p in points):
        raise ValueError("finite two-dimensional coordinates required")
    edges = geometry["edges"]
    plane = PlaneMap(tuple((str(e["a"]), str(e["b"])) for e in edges),
                     {str(v): tuple(ds) for v, ds in enumerate(geometry["rotation"])})
    if len(points) != len(plane.vertices):
        raise ValueError("coordinate and rotation vertex counts differ")
    virtual = tuple(i for i, e in enumerate(edges) if e.get("virtual", False))
    frame = [i for i, e in enumerate(edges) if e.get("frame", False)]
    real = [i for i, e in enumerate(edges) if i not in virtual and i not in frame]
    if any(plane.shores(i)[0] != plane.shores(i)[1] for i in virtual):
        raise ValueError("a virtual connector must have the same shore on both sides")
    parent = {i: i for i in real}

    def root(i):
        """Disjoint-set compression merges geometry, not naming decisions."""
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    incident = defaultdict(list)
    for i in real:
        e = edges[i]
        if points[e["a"]] == points[e["b"]]:
            raise ValueError("zero-length geometric edge")
        incident[e["a"]].append(i)
        incident[e["b"]].append(i)
    for vertex, members in incident.items():
        vectors = {}
        for i in members:
            e = edges[i]
            other = e["b"] if e["a"] == vertex else e["a"]
            vectors[i] = tuple(b - a for a, b in zip(points[vertex], points[other]))
        for i in members:
            u = vectors[i]
            candidates = []
            for j in members:
                v = vectors[j]
                cross = abs(u[0] * v[1] - u[1] * v[0])
                if (i != j and sum(a * b for a, b in zip(u, v)) < 0
                        and cross <= GEOMETRY_TOLERANCE * min(hypot(*u), hypot(*v))):
                    candidates.append(j)
            if len(candidates) > 1:
                raise ValueError("ambiguous near-collinear continuation")
            if candidates:
                parent[root(i)] = root(candidates[0])

    groups = defaultdict(list)
    for i in real:
        groups[root(i)].append(i)
    records = []

    def make_record(identifier, members, coordinate, closed, endpoints):
        """Orient each atomic edge along its whole line and retain every span."""
        spans = []
        for i in members:
            e = edges[i]
            ta, tb = coordinate(points[e["a"]]), coordinate(points[e["b"]])
            if closed and abs(ta - tb) > 0.5:
                # The chosen frame origin is both t=0 and t=1.
                if ta == 0:
                    ta = 1.0
                if tb == 0:
                    tb = 1.0
            dart = 2 * i + (ta > tb)
            spans.append({"edge": i, "dart": dart, "t0": min(ta, tb), "t1": max(ta, tb),
                          "left_side": plane.face_of_dart[dart],
                          "right_side": plane.face_of_dart[dart ^ 1]})
        spans.sort(key=lambda s: s["t0"])
        if not spans or abs(spans[0]["t0"]) > 1e-7 or abs(spans[-1]["t1"] - 1) > 1e-7:
            raise ValueError("whole line does not cover its declared extent")
        if any(abs(a["t1"] - b["t0"]) > 1e-7 for a, b in zip(spans, spans[1:])):
            raise ValueError("whole line has a gap or overlapping spans")
        records.append({"id": identifier, "closed": closed, "endpoints": endpoints,
                        "spans": spans, "events": [],
                        "sources": sorted({s for i in members for s in edges[i].get("sources", [])})})

    for members in groups.values():
        vertices = {v for i in members for v in (edges[i]["a"], edges[i]["b"])}
        start, end = min(points[v] for v in vertices), max(points[v] for v in vertices)
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = hypot(dx, dy)
        if any(abs(dx * (points[v][1] - start[1]) - dy * (points[v][0] - start[0]))
               > GEOMETRY_TOLERANCE * length for v in vertices):
            raise ValueError("local continuation accumulated into a nonstraight line")
        def coordinate(p):
            """Normalized position along the full geometric support."""
            return ((p[0] - start[0]) * dx + (p[1] - start[1]) * dy) / length**2
        make_record("L:" + _point_key(start) + ">" + _point_key(end), members,
                    coordinate, False, [list(start), list(end)])

    if frame:
        width = max(p[0] for p in points)
        height = max(p[1] for p in points)
        perimeter = 2 * (width + height)
        def frame_coordinate(p):
            """Clockwise on screen: the external shore is on the left."""
            x, y = p
            if y == 0:
                distance = x
            elif x == width:
                distance = width + y
            elif y == height:
                distance = 2 * width + height - x
            elif x == 0:
                distance = perimeter - y
            else:
                raise ValueError("frame edge lies off rectangular frame")
            return distance / perimeter
        make_record("frame", frame, frame_coordinate, True, [[0, 0], [0, 0]])
    records.sort(key=lambda line: (line["id"] != "frame", line["id"]))
    owner = {span["edge"]: line["id"] for line in records for span in line["spans"]}

    # A junction stores the cyclic order of outgoing LINE PORTS. It has no color.
    # Repeated occurrences of one line are its continuation, not new mother IDs.
    ports = {}
    for line in records:
        for span in line["spans"]:
            ports[span["dart"]] = (line["id"], "+", span["t0"])
            ports[span["dart"] ^ 1] = (line["id"], "-", span["t1"])
    for vertex, darts in enumerate(geometry["rotation"]):
        real_ports = [ports[d] for d in darts if d in ports]
        if len({p[0] for p in real_ports}) <= 1:
            continue
        for line in records:
            own = [p for p in real_ports if p[0] == line["id"]]
            if own:
                line["events"].append({"t": own[0][2] % 1 if line["closed"] else own[0][2],
                                       "point": list(points[vertex]),
                                       "ports_ccw": [[p[0], p[1]] for p in real_ports]})
    for line in records:
        line["events"].sort(key=lambda event: event["t"])
    return WholeLineModel(plane, records, virtual, owner)


def encode_profiles(model: WholeLineModel, dart_values: list) -> dict:
    """Attach arbitrary labels/domains to ordered line spans, without assigning.

    Equal adjacent labels are NOT merged: side identity, attachment positions,
    and even degree-two subdivision metadata must remain recoverable.
    """
    if len(dart_values) != 2 * len(model.plane_map.edges):
        raise ValueError("one shore value per dart required")
    return {"lines": {line["id"]: [
        {"t0": span["t0"], "t1": span["t1"], "dart": span["dart"],
         "left": dart_values[span["dart"]], "right": dart_values[span["dart"] ^ 1]}
        for span in line["spans"]] for line in model.lines},
        "virtual": {str(i): dart_values[2 * i:2 * i + 2] for i in model.virtual_edges}}


def decode_profiles(model: WholeLineModel, encoded: dict) -> list:
    """Expand an unmodified profile certificate; reject dropped/moved intervals."""
    if set(encoded["lines"]) != {line["id"] for line in model.lines}:
        raise ValueError("line identity mismatch")
    values = [None] * (2 * len(model.plane_map.edges))
    for line in model.lines:
        supplied = encoded["lines"][line["id"]]
        if len(supplied) != len(line["spans"]):
            raise ValueError("profile interval missing")
        for original, entry in zip(line["spans"], supplied):
            if any(entry[k] != original[k] for k in ("dart", "t0", "t1")):
                raise ValueError("profile geometry mismatch")
            values[entry["dart"]], values[entry["dart"] ^ 1] = entry["left"], entry["right"]
    if set(encoded["virtual"]) != {str(i) for i in model.virtual_edges}:
        raise ValueError("virtual connector metadata mismatch")
    for i in model.virtual_edges:
        pair = encoded["virtual"][str(i)]
        if len(pair) != 2:
            raise ValueError("virtual connector requires two shore values")
        values[2 * i:2 * i + 2] = pair
    return values


def reverse_profile(profile: list[dict]) -> list[dict]:
    """Read the SAME whole line backwards: reverse order AND exchange shores."""
    return [{"t0": 1 - s["t1"], "t1": 1 - s["t0"], "dart": s["dart"] ^ 1,
             "left": s["right"], "right": s["left"]} for s in reversed(profile)]


def propagate_candidates(model: WholeLineModel, anchors: dict[int, list[int]],
                         palette=(1, 2, 3, 4)) -> dict:
    """Propagate equality plus singleton inequality constraints, without choices.

    Anchors address oriented line-side occurrences (darts), not colored points.
    Side-continuation equivalence classes are DERIVED from the rotation system;
    mathematically they coincide with faces. This is not hidden new mathematics.
    Empty => supplied constraints conflict; multi-valued => underdetermined,
    not a promise that a completion exists. No backtracking, no branch search.
    """
    palette_values = tuple(palette)
    if not palette_values or any(type(c) is not int or c <= 0 for c in palette_values):
        raise ValueError("palette requires positive integer symbols")
    allowed = set(palette_values)
    plane = model.plane_map
    domains = [set(allowed) for _ in plane.faces]
    for dart, candidates in anchors.items():
        if type(dart) is not int or not 0 <= dart < len(plane.face_of_dart):
            raise ValueError("anchor dart out of range")
        if any(type(c) is not int or c not in allowed for c in candidates):
            raise ValueError("anchor symbol outside supplied palette")
        domains[plane.face_of_dart[dart]].intersection_update(candidates)
    neighbors = [[] for _ in domains]
    for edge in range(len(plane.edges)):
        a, b = plane.shores(edge)
        if a != b:
            neighbors[a].append((b, edge))
            neighbors[b].append((a, edge))
    queue = deque(i for i, domain in enumerate(domains) if len(domain) == 1)
    trace = []
    while queue and all(domains):
        side = queue.popleft()
        symbol = next(iter(domains[side]))
        for other, edge in neighbors[side]:
            if symbol in domains[other]:
                domains[other].remove(symbol)
                trace.append({"from_side": side, "to_side": other, "edge": edge,
                              "whole_line": model.edge_owner.get(edge), "removed": symbol})
                if len(domains[other]) == 1:
                    queue.append(other)
                if not domains[other]:
                    break
    status = ("conflict" if not all(domains) else
              "solved" if all(len(d) == 1 for d in domains) else "underdetermined")
    return {"status": status, "domains": [sorted(d) for d in domains],
            "trace": trace, "backtracks": 0, "choices": 0, "palette": sorted(allowed)}


def restart_with_symbol_symmetry(model: WholeLineModel) -> dict:
    """Restart from the frame and remove ONLY unused-symbol permutation ties.

    This restricted extension of propagation is not arbitrary greedy choice.
    If a shore's entire domain is precisely the set of still-unused symbols,
    naming that occurrence with the smallest such symbol is without loss of
    generality: any completion can be globally permuted to this representative,
    fixing all already-used symbols. Domains mixing used and unused symbols
    are never decided this way. No supplied old coloring is accepted here.

    Geometry-only line order breaks ties between eligible occurrences. This
    removes equivalent color-name duplicates, not graph-isomorphism duplicates.
    Undertermination remains possible; existence is never inferred from domains.
    """
    frame = next((line for line in model.lines if line["id"] == "frame"), None)
    if frame is None:
        raise ValueError("a rectangular frame is required for this restart")
    first = frame["spans"][0]["dart"]
    anchors = {first: [1], first ^ 1: [2]}
    steps = []
    while True:
        result = propagate_candidates(model, anchors)
        if result["status"] != "underdetermined":
            break
        used = {domain[0] for domain in result["domains"] if len(domain) == 1}
        unused = set(result["palette"]) - used
        chosen = None
        if len(unused) > 1:
            for line in model.lines:
                for span in line["spans"]:
                    for dart in (span["dart"], span["dart"] ^ 1):
                        side = model.plane_map.face_of_dart[dart]
                        if set(result["domains"][side]) == unused:
                            chosen = (line["id"], dart, side)
                            break
                    if chosen is not None:
                        break
                if chosen is not None:
                    break
        if chosen is None:
            break
        line_id, dart, side = chosen
        symbol = min(unused)
        anchors[dart] = [symbol]
        steps.append({"whole_line": line_id, "dart": dart, "side": side,
                      "equivalent_unused_symbols": sorted(unused), "canonical_symbol": symbol,
                      "rule": "global unused-symbol permutation; no coloring branch tried"})
    return {**result, "symmetry_steps": steps, "anchors_by_dart": anchors,
            "choices": len(steps), "symmetry_choices": len(steps), "non_symmetry_choices": 0}

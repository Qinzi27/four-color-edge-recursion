"""Test the proposed two-port retained-side rule on rectangular histories.

Names are positive integers, not a preselected four-color palette. Rectangles
encode connected line sides for this restricted geometry, not a face-priority
coloring algorithm. Failed attempts never alter the input or select a fallback.
"""

from dataclasses import dataclass
from math import isfinite

EPS = 1e-7


@dataclass(frozen=True)
class RectSide:
    """One connected named side; its ID is not its name."""

    id: str
    bounds: tuple[float, float, float, float]
    symbol: int


@dataclass(frozen=True)
class RectState:
    """Immutable successful history; cuts retain their input direction."""

    width: float
    height: float
    sides: tuple[RectSide, ...]
    cuts: tuple[tuple[tuple[float, float], tuple[float, float]], ...] = ()


def initial_state(width=900, height=600):
    """Anchor the outer closed mother line with outside 1 and inside 2."""
    if any(isinstance(v, bool) or not isinstance(v, (int, float))
           or not isfinite(v) or v <= 0 for v in (width, height)):
        raise ValueError("positive finite canvas dimensions required")
    return RectState(width, height, (RectSide("root", (0, 0, width, height), 2),))


def choose_inherited_name(s, retained):
    """Positive mex of retained names and the inherited name, without a cap."""
    values = tuple(retained) + (s,)
    if any(type(v) is not int or v < 1 for v in values):
        raise ValueError("names must be positive integers (not booleans)")
    forbidden = set(values)
    value = 1
    while value in forbidden:
        value += 1
    return value


def _near(a, b):
    return abs(a - b) < EPS


def _shared(a, b):
    """Return a positive-length common boundary, never a corner contact."""
    x0, y0, x1, y1 = a
    u0, v0, u1, v1 = b
    lo, hi = max(y0, v0), min(y1, v1)
    if hi - lo > EPS:
        if _near(x1, u0):
            return ((x1, lo), (x1, hi))
        if _near(u1, x0):
            return ((x0, lo), (x0, hi))
    lo, hi = max(x0, u0), min(x1, u1)
    if hi - lo > EPS:
        if _near(y1, v0):
            return ((lo, y1), (hi, y1))
        if _near(v1, y0):
            return ((lo, y0), (hi, y0))
    return None


def _frame_segments(bounds, width, height):
    x0, y0, x1, y1 = bounds
    segments = []
    if _near(x0, 0):
        segments.append(((x0, y0), (x0, y1)))
    if _near(x1, width):
        segments.append(((x1, y0), (x1, y1)))
    if _near(y0, 0):
        segments.append(((x0, y0), (x1, y0)))
    if _near(y1, height):
        segments.append(((x0, y1), (x1, y1)))
    return segments


def boundary_contacts(side, others, width, height):
    """Enumerate actual old-boundary restrictions for diagnostic use only."""
    contacts = [{"side": "outside", "symbol": 1, "segment": segment}
                for segment in _frame_segments(side.bounds, width, height)]
    for other in others:
        segment = _shared(side.bounds, other.bounds)
        if segment:
            contacts.append({"side": other.id, "symbol": other.symbol,
                             "segment": segment})
    return contacts


def find_conflicts(sides, width, height):
    """Check every real boundary using arbitrary positive names."""
    conflicts = []
    for index, side in enumerate(sides):
        for contact in boundary_contacts(side, sides[index + 1:], width, height):
            if side.symbol == contact["symbol"]:
                conflicts.append({"side": side.id, "other": contact["side"],
                                  "symbol": side.symbol, "segment": contact["segment"]})
    return conflicts


def _interior_on_segment(point, segment):
    (x, y), ((a, b), (c, d)) = point, segment
    return ((_near(a, c) and _near(x, a) and min(b, d) + EPS < y < max(b, d) - EPS)
            or (_near(b, d) and _near(y, b) and min(a, c) + EPS < x < max(a, c) - EPS))


def _port(state, parent, point, axis):
    """Identify the local opposing side and physical mother at one endpoint."""
    x, y = point
    on_frame = _near(x, 0) or _near(x, state.width) or _near(y, 0) or _near(y, state.height)
    if on_frame:
        return {"point": point, "mother": "frame", "retained_side": "outside", "symbol": 1}
    neighbors = [side for side in state.sides if side.id != parent.id
                 and (segment := _shared(parent.bounds, side.bounds))
                 and _interior_on_segment(point, segment)]
    # Old junctions and ambiguous continuation choices are not invented here.
    mothers = [index for index, cut in enumerate(state.cuts)
               if _interior_on_segment(point, cut)
               and ((_near(cut[0][1], cut[1][1]) and axis == "vertical")
                    or (_near(cut[0][0], cut[1][0]) and axis == "horizontal"))]
    if len(neighbors) != 1 or len(mothers) != 1:
        return None
    other = neighbors[0]
    return {"point": point, "mother": f"cut-{mothers[0] + 1}",
            "retained_side": other.id, "symbol": other.symbol}


def attempt_cut(state, points, inherit="left"):
    """Apply endpoint-only mex once; audit, but do not repair, its result.

    Left/right are geometric relative to the input stroke, with screen y down.
    Scope: one axis-aligned cut between opposite interiors of one rectangle.
    Unsupported geometry is distinct from a naming contradiction.
    """
    if inherit not in ("left", "right"):
        raise ValueError("inherit must be left or right")

    def outside(reason):
        return {"status": "outside_scope", "state": state,
                "event": {"reason": reason, "inherit": inherit}}

    try:
        cut = tuple(tuple(point) for point in points)
        if len(cut) != 2 or any(len(p) != 2 for p in cut):
            return outside("exactly two endpoints required")
        if any(isinstance(v, bool) or not isinstance(v, (int, float))
               or not isfinite(v) for p in cut for v in p):
            return outside("finite numeric coordinates required")
    except TypeError:
        return outside("two coordinate pairs required")
    (a, b), (c, d) = cut
    axis = "vertical" if _near(a, c) and not _near(b, d) else (
        "horizontal" if _near(b, d) and not _near(a, c) else None)
    if axis is None:
        return outside("nonzero axis-aligned cut required")
    candidates = []
    for side in state.sides:
        x0, y0, x1, y1 = side.bounds
        if axis == "vertical":
            fits = x0 + EPS < a < x1 - EPS and _near(min(b, d), y0) and _near(max(b, d), y1)
        else:
            fits = y0 + EPS < b < y1 - EPS and _near(min(a, c), x0) and _near(max(a, c), x1)
        if fits:
            candidates.append(side)
    if len(candidates) != 1:
        return outside("cut must traverse exactly one rectangular side")
    parent = candidates[0]
    ports = [_port(state, parent, point, axis) for point in cut]
    if any(port is None for port in ports):
        return outside("endpoint mother/retained side is not uniquely defined")
    retained = sorted({port["symbol"] for port in ports})
    t = choose_inherited_name(parent.symbol, retained)
    x0, y0, x1, y1 = parent.bounds
    if axis == "vertical":
        low, high = (x0, y0, a, y1), (a, y0, x1, y1)
        left, right = (high, low) if d > b else (low, high)
    else:
        low, high = (x0, y0, x1, b), (x0, b, x1, y1)
        left, right = (low, high) if c > a else (high, low)
    children = tuple(RectSide(f"{parent.id}.{label[0]}", bounds,
                             parent.symbol if inherit == label else t)
                     for label, bounds in (("left", left), ("right", right)))
    untouched = tuple(side for side in state.sides if side.id != parent.id)
    proposed = untouched + children
    conflicts = find_conflicts(proposed, state.width, state.height)
    diagnostics = []
    for label, child in zip(("left", "right"), children):
        contacts = boundary_contacts(child, untouched, state.width, state.height)
        full = sorted({item["symbol"] for item in contacts})
        repaired = choose_inherited_name(parent.symbol, full)
        alternative = tuple(RectSide(item.id, item.bounds,
                                     repaired if item.id == child.id else parent.symbol)
                            for item in children)
        diagnostics.append({"new_name_side": label, "contacts": contacts,
                            "full_boundary_retained": full,
                            "missing_from_ports": sorted(set(full) - set(retained)),
                            "diagnostic_new_name": repaired,
                            "diagnostic_conflicts": find_conflicts(untouched + alternative,
                                                                    state.width, state.height)})
    next_state = RectState(state.width, state.height, proposed, state.cuts + (cut,))
    event = {"cut": cut, "parent": parent.id, "inherited_name": parent.symbol,
             "inherit": inherit, "ports": ports, "endpoint_retained": retained,
             "new_name": t, "new_line_pair": [children[0].symbol, children[1].symbol],
             "conflicts": conflicts, "boundary_diagnostics": diagnostics}
    return {"status": "conflict" if conflicts else "split",
            "state": state if conflicts else next_state,
            "proposed_state": next_state, "event": event}


def state_payload(state):
    """Portable geometry/oracle input with no private machine paths."""
    return {"width": state.width, "height": state.height, "cuts": state.cuts,
            "sides": [{"id": side.id, "bounds": side.bounds, "symbol": side.symbol}
                      for side in state.sides]}


def line_profiles(state):
    """Recompute local side pairs along intact historical mother strokes.

    The geometric mother identity is preserved through later T junctions;
    its local current pair is not assumed equal to its historical first pair.
    """
    def symbol_at(x, y):
        matches = [side.symbol for side in state.sides
                   if side.bounds[0] < x < side.bounds[2] and side.bounds[1] < y < side.bounds[3]]
        return matches[0] if len(matches) == 1 else 1

    frame = (((0, 0), (state.width, 0)), ((state.width, 0), (state.width, state.height)),
             ((state.width, state.height), (0, state.height)), ((0, state.height), (0, 0)))
    paths = [("frame", path) for path in frame] + [(f"cut-{i + 1}", path)
                                                            for i, path in enumerate(state.cuts)]
    profiles = {}
    for mother, ((a, b), (c, d)) in paths:
        vertical = _near(a, c)
        start, end = (b, d) if vertical else (a, c)
        bounds = {start, end}
        for side in state.sides:
            x0, y0, x1, y1 = side.bounds
            touches_line = (x0 - EPS <= a <= x1 + EPS) if vertical else (y0 - EPS <= b <= y1 + EPS)
            if touches_line:
                bounds.update(v for v in ((y0, y1) if vertical else (x0, x1))
                              if min(start, end) < v < max(start, end))
        ordered = sorted(bounds, reverse=end < start)
        for lo, hi in zip(ordered, ordered[1:]):
            mid = (lo + hi) / 2
            x, y = (a, mid) if vertical else (mid, b)
            # Smaller than every current rectangle width/height, not an arbitrary raster.
            delta = min(min(s.bounds[2] - s.bounds[0], s.bounds[3] - s.bounds[1])
                        for s in state.sides) / 1000
            nx, ny = ((1 if end > start else -1), 0) if vertical else (0, (-1 if end > start else 1))
            pair = (symbol_at(x + delta * nx, y + delta * ny),
                    symbol_at(x - delta * nx, y - delta * ny))
            segment = ((a, lo), (a, hi)) if vertical else ((lo, b), (hi, b))
            profiles.setdefault(mother, []).append({"segment": segment, "pair": pair})
    return profiles

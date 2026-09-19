"""Current-geometry rectangular splits, including existing junction endpoints.

This adapter proposes geometry only. It never selects a new name, a retained
color set, or an inherited child. Both new side drafts carry their parent's
name; that deliberately uncommitted draft must not be treated as a coloring.

Closed-set endpoint incidence records every touching old mother and side.
Those records express geometric ownership, NOT additional inequality rules:
two side regions meeting only at a point need not have different names.
The previous geometry module is left unchanged for reproducibility.
"""

from math import isfinite

from .inherited_names import EPS, RectSide, RectState
from .retained_profiles import _validate_state


def _near(first, second):
    """Use the existing rectangle model's explicit geometric tolerance."""
    return abs(first - second) < EPS


def _closed_on_segment(point, segment):
    """Include both ends of a nonzero axis-aligned segment in incidence."""
    (x, y), ((a, b), (c, d)) = point, segment
    if _near(a, c):
        return _near(x, a) and min(b, d) - EPS <= y <= max(b, d) + EPS
    if _near(b, d):
        return _near(y, b) and min(a, c) - EPS <= x <= max(a, c) + EPS
    return False


def _position(point, segment):
    """Distinguish touching an old endpoint from touching an edge interior."""
    return ("endpoint" if any(_near(point[0], end[0]) and _near(point[1], end[1])
                              for end in segment) else "interior")


def _rectangle_edges(bounds):
    """Keep all four directed bounding segments, even at corner incidence."""
    x0, y0, x1, y1 = bounds
    return (("top", ((x0, y0), (x1, y0))),
            ("right", ((x1, y0), (x1, y1))),
            ("bottom", ((x1, y1), (x0, y1))),
            ("left", ((x0, y1), (x0, y0))))


def _endpoint_incidence(state, point):
    """Record all incidences without choosing a unique mother or opposing side."""
    mothers = []
    for edge_name, segment in _rectangle_edges((0, 0, state.width, state.height)):
        if _closed_on_segment(point, segment):
            mothers.append({"id": "frame", "is_frame": True, "frame_edge": edge_name,
                            "segment": segment, "position": _position(point, segment)})
    for index, segment in enumerate(state.cuts):
        if _closed_on_segment(point, segment):
            mothers.append({"id": f"cut-{index + 1}", "is_frame": False,
                            "segment": segment, "position": _position(point, segment)})
    sides = []
    for side in state.sides:
        touched = [{"edge": edge_name, "segment": segment,
                    "position": _position(point, segment)}
                   for edge_name, segment in _rectangle_edges(side.bounds)
                   if _closed_on_segment(point, segment)]
        if touched:
            sides.append({"id": side.id, "symbol": side.symbol, "bounds": side.bounds,
                          "boundary_segments": touched,
                          "contact_position": "corner" if len(touched) > 1 else "edge_interior"})
    return {"point": point, "incident_mothers": mothers,
            "frame_segments": [mother for mother in mothers if mother["is_frame"]],
            "incident_old_sides": sides, "closed_incidence_only": True,
            "creates_color_constraint": False}


def propose_rect_split(state, points):
    """Return an uncommitted same-name split, including T-to-X junction cuts.

    Input state validation is unchanged: a valid named rectangular tiling with
    complete historical lines is required. A proposed nonzero axis-aligned cut
    must cross exactly one rectangle between opposite boundary interiors. Its
    ends may be existing junctions of several old mothers/opposing side regions.

    ``child_ids`` and the two appended children are ordered left, right relative
    to the INPUT direction in screen-y-down geometry. Existing cuts/side objects
    are preserved. Endpoints already within EPS of the parent boundary are
    normalized onto that boundary; input_cut separately retains the supplied cut.

    A proposed result returns state=old and proposed_state=draft. The two child
    names are both s and are intentionally not independently color-audited here.
    Unsupported geometry returns outside_scope without mutating the old state.
    """
    _validate_state(state)

    def outside(reason):
        """Unsupported geometry is not a naming contradiction or failed repair."""
        return {"status": "outside_scope", "state": state,
                "event": {"reason": reason, "geometry_only": True,
                          "scope": "one nonzero axis-aligned cut through one rectangular side"}}

    try:
        raw_cut = tuple(tuple(point) for point in points)
    except TypeError:
        return outside("two coordinate pairs required")
    if len(raw_cut) != 2 or any(len(point) != 2 for point in raw_cut):
        return outside("exactly two endpoints required")
    if any(isinstance(value, bool) or not isinstance(value, (int, float))
           or not isfinite(value) for point in raw_cut for value in point):
        return outside("finite numeric coordinates required")
    (a, b), (c, d) = raw_cut
    # Reject actual oblique input instead of silently inventing its direction.
    axis = ("vertical" if a == c and abs(d - b) > EPS else
            "horizontal" if b == d and abs(c - a) > EPS else None)
    if axis is None:
        return outside("nonzero axis-aligned cut required")

    candidates = []
    for side in state.sides:
        x0, y0, x1, y1 = side.bounds
        fits = (x0 + EPS < a < x1 - EPS and _near(min(b, d), y0) and _near(max(b, d), y1)
                if axis == "vertical" else
                y0 + EPS < b < y1 - EPS and _near(min(a, c), x0) and _near(max(a, c), x1))
        if fits:
            candidates.append(side)
    if len(candidates) != 1:
        return outside("cut must traverse exactly one rectangular side between opposite boundaries")
    parent = candidates[0]
    child_ids = (parent.id + ".l", parent.id + ".r")
    if set(child_ids) & {side.id for side in state.sides}:
        return outside("child side identities are not fresh")

    x0, y0, x1, y1 = parent.bounds
    if axis == "vertical":
        cut = ((a, y0), (a, y1)) if d > b else ((a, y1), (a, y0))
        low, high = (x0, y0, a, y1), (a, y0, x1, y1)
        left, right = (high, low) if d > b else (low, high)
    else:
        cut = ((x0, b), (x1, b)) if c > a else ((x1, b), (x0, b))
        low, high = (x0, y0, x1, b), (x0, b, x1, y1)
        left, right = (low, high) if c > a else (high, low)
    incidence = [_endpoint_incidence(state, point) for point in cut]
    # Every boundary is certified by the old state validator. This defensive
    # check does not reduce multiple incidences to one arbitrarily chosen source.
    if any(not record["incident_mothers"] for record in incidence):
        return outside("an endpoint has no recorded old mother or frame incidence")
    children = (RectSide(child_ids[0], left, parent.symbol),
                RectSide(child_ids[1], right, parent.symbol))
    untouched = tuple(side for side in state.sides if side.id != parent.id)
    draft = RectState(state.width, state.height, untouched + children, state.cuts + (cut,))
    return {"status": "proposed", "state": state, "proposed_state": draft,
            "event": {"cut": cut, "input_cut": raw_cut, "axis": axis, "parent": parent.id,
                      "inherited_name": parent.symbol, "child_ids": child_ids,
                      "child_by_side": {"left": child_ids[0], "right": child_ids[1]},
                      "endpoint_incidence": incidence, "geometry_only": True,
                      "committed": False, "draft_naming": "both children retain the parent name pending a separate naming rule",
                      "scope": "closed geometric endpoint incidence; point contact creates no additional inequality"}}

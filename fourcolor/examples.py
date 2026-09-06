"""Small, explicitly embedded maps for demonstrations and regression checks."""

from .embedding import PlaneMap


def triangle_map() -> PlaneMap:
    """A triangle with one bounded and one unbounded face."""
    return PlaneMap(
        edges=(("A", "B"), ("B", "C"), ("C", "A")),
        rotation={"A": (0, 5), "B": (2, 1), "C": (4, 3)},
    )


def dangling_triangle_map() -> PlaneMap:
    """A triangle with an interior dangling edge A--D; still only two faces."""
    return PlaneMap(
        edges=(("A", "B"), ("B", "C"), ("C", "A"), ("A", "D")),
        rotation={"A": (0, 6, 5), "B": (2, 1), "C": (4, 3), "D": (7,)},
    )


def tetrahedron_map() -> PlaneMap:
    """An outer triangle ABC with central vertex O, giving four adjacent faces."""
    return PlaneMap(
        edges=(("A", "B"), ("B", "C"), ("C", "A"),
               ("A", "O"), ("B", "O"), ("C", "O")),
        rotation={"A": (0, 6, 5), "B": (2, 8, 1),
                  "C": (4, 10, 3), "O": (11, 7, 9)},
    )

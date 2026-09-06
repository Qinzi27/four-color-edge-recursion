# API conventions / 程序约定

The core uses Python 3.10+ and only the standard library. All commands below
run from the repository root. Integer colors are `0,1,2,3`, encoding two-bit
vectors; visual color names `1,2,3,4` are not the program's numeric color domain.

## Plane maps

```python
from fourcolor.examples import tetrahedron_map, dangling_triangle_map
from fourcolor.embedding import vertex_defects
from fourcolor.coloring import colorings

plane_map = tetrahedron_map()
adjacencies = [plane_map.shores(e) for e in range(len(plane_map.edges))]
# A bridge yields (f,f), which is NOT a proper-color constraint on a face.
constraints = [(a, b) for a, b in adjacencies if a != b]
colors = next(colorings(len(plane_map.faces), constraints))
assert plane_map.check_coloring(colors)
deltas = plane_map.differences(colors)
reconstructed = plane_map.integrate(deltas)
assert plane_map.check_coloring(reconstructed)
assert all(value == 0 for value in vertex_defects(plane_map, deltas).values())
```

`PlaneMap(edges, rotation)` takes edges with string vertex IDs. For edge `i=(u,v)`,
dart `2*i` leaves `u`, and dart `2*i+1` leaves `v`. `rotation[v]` lists all outgoing
darts at vertex `v` in counterclockwise order. The next dart of a left-face walk
is the predecessor of the reversed dart in that rotation. Face IDs are assigned
by traversal and are local to a particular map instance, not persistent geometric names.

The constructor checks incidence, connectivity, and the sphere Euler equation.
This is validation of a combinatorial embedding, not of arbitrary supplied
straight-line coordinates; no coordinates are required. Parallel edges, loops,
bridges, and the single-vertex map are part of the representation.

`shores(i)` returns the faces of darts `2*i` and `2*i+1` in that order.
`integrate(deltas)` rejects inconsistent differences, zero differences between
different faces, and nonzero differences on a same-face edge. It fixes a root
face to `0`; resulting numeric colors may differ from the original by a uniform XOR.
It raises `ValueError` on failure, rather than returning an independently certified
minimum conflict core. `vertex_defects` counts both darts of a loop.

## Replayable recursive construction

```python
from fourcolor.history import tetrahedron_history, replay, extend, close_split

initial, operations = tetrahedron_history()
final_map, events = replay(initial, operations)
assert (len(final_map.vertices), len(final_map.edges), len(final_map.faces)) == (4, 6, 4)
```

`extend(map, corner_dart, new_vertex)` appends an edge to a fresh vertex.
`close_split(map, start_dart, end_dart)` joins two distinct corner occurrences
of the same face. A corner is identified by an outgoing boundary dart; each
new outgoing dart is inserted immediately after its selected corner in CCW
rotation order. Distinct corners at the same vertex are permitted and can
produce a loop. The resulting embedding and expected face change are checked.

All operations return new maps and preserve existing edge/dart IDs. Face IDs
may change. `replay(initial, operations)` returns the final map and an event
tuple with before/after counts, the selected parent face, and `face_descendants`
mapping each old face ID to its resulting face IDs by old-dart membership.
These step-local mappings together with the initial embedding and full operation
sequence provide replayable provenance; colors are not persistent face identifiers.

Operations are JSON-compatible dictionaries:

```python
operations = (
    {"kind": "extend", "corner": 0, "vertex": "O"},
    {"kind": "close_split", "start": 7, "end": 2},
    {"kind": "close_split", "start": 8, "end": 4},
)
```

This particular sequence starts from `triangle_map()`. Operation validity is
relative to the current embedding, so the same IDs are not universal geometric
coordinates. The corner-based API needs at least one edge; it does not extend
the isolated-vertex base case, insert into an edge interior, or choose/recolor
faces automatically. Each update revalidates the whole small map, so a long
construction is not claimed to run in overall linear time.

## Exact vertex-coloring and boundary signatures

```python
from fourcolor.coloring import boundary_signature, canonical_colors

# In this module vertices denote regions when coloring a region-adjacency graph.
signatures = boundary_signature(3, [(0, 1), (1, 2), (2, 0)], (0, 1, 2))
assert len(signatures) == 24
assert canonical_colors((3, 1, 3, 2)) == (0, 1, 0, 2)
```

`colorings(n, edges, precolored=None)` enumerates complete labeled four-colorings
of a graph with vertices `0,...,n-1`. `boundary_signature(n,edges,boundary)`
projects them onto the ordered boundary. These are exhaustive small-instance
reference routines, not a polynomial-time general planar four-color algorithm.
Loops in a vertex-coloring graph make proper coloring impossible. Do not pass a
bridge's dual self-loop as a face constraint: remove such same-face pairs first.

`canonical_colors` keeps only the equality pattern in a tuple, modulo a global
permutation of the four color names. Do not canonicalize two pieces independently
and then compare the numeric labels without aligning their permutations. The
gluing theorem is documented as an exact set operation; a generic decomposition
engine and canonical-state composition API are not implemented in this release.

## Series-parallel flow repair

`Edge(label)`, `Series(left,right)`, and `Parallel(left,right)` describe a
two-terminal graph. Each leaf is a separate edge occurrence. Initial leaf labels
must be `1,2,3`; all repaired labels are also nonzero. The module does not take an
arbitrary graph and recognize or find its decomposition.

- `repair_table(expr)` returns the four costs for terminal XOR defects `q=0,1,2,3`.
- `minimum_repair(expr)` returns `(cost, edge_labels)` for `q=0`; infeasible
  instances return `(math.inf, ())`. The labels follow the left-to-right leaf order.
- `realize(expr)` returns `(n, edges, original_labels, (source,target))` for
  independent checking, with separate internal vertices for the two child networks.

Both terminals remain distinct. Enforcing their defects to be zero is different
from identifying the terminals into one vertex. The latter is not the root
operation of this API. A single edge is infeasible for a nowhere-zero balanced
flow, although the corresponding one-edge plane map has a perfectly valid one-face
coloring with difference zero. These statements concern different target constraints.

## Execution limits

Boundary coloring enumeration and brute-force validation are deliberately bounded
small-instance tools. The coloring enumerator uses recursive backtracking; large
graphs can exceed its intended time, memory, or interpreter-stack limits.
SP cost computation, realization, and witness traversal use explicit stacks and
support deeply nested expressions. The recurrence has linear arithmetic-operation
count in the supplied expression's leaf count; integer costs require logarithmic
bit length. Reusing a Python expression object denotes repeated edge occurrences
when realizing a graph, so a compact shared expression can describe a much larger
expanded output.

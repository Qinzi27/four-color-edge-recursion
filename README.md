# Four-Color Edge Recursion

**Recursive left/right face-color descriptions of plane maps, boundary signatures,
and verifiable Klein-four-group flow repair.**

[中文说明](README.zh-CN.md) · [Mathematical foundations](docs/FOUNDATIONS.en.md) · [数学基础](docs/FOUNDATIONS.md)
· [Research questions](docs/RESEARCH_PLAN.md) · [Related work](docs/RELATED_WORK.md)

[![Validation](https://github.com/Qinzi27/four-color-edge-recursion/actions/workflows/validate.yml/badge.svg)](https://github.com/Qinzi27/four-color-edge-recursion/actions/workflows/validate.yml)

[Open the public map lab](https://qinzi27.github.io/four-color-edge-recursion/)
· [Recursive model explainer](https://qinzi27.github.io/four-color-edge-recursion/model.html)
· [Method fidelity and literature audit](docs/METHOD_REVIEW-2026-09-07.md)

The public GitHub Pages site does not require a GitHub or ChatGPT account. Its
automatic coloring is a **comparison baseline**, not a complete implementation
of an as-yet-unspecified recursive color-inheritance rule.

This project develops Qinzi27's idea of describing a directed boundary by the
colors on its two sides, `(1,2)`, and recording successive region splits with
expressions such as `(1,(2,3))`. The research goal is to understand what extra
boundary information makes such recursion correct, composable, and checkable.

The repository provides a precise foundation and small exact algorithms. **It does
not claim a new proof of the Four-Color Theorem or established novelty for the
underlying notation, flow equivalence, or dynamic-programming principles.**

![Directed sides, split history, and a closed-walk consistency test](docs/figures/model.svg)

## What the model records

For a directed edge, record both face identity and color:

$$\sigma(e)=\langle(f_L,c_L)\mid(f_R,c_R)\rangle.$$

Reversing the direction swaps the sides. The expression `(1,(2,3))` describes a
split history; it is not the two-side label of a single resulting edge. The new
segments carry `(1,2)`, `(1,3)`, and `(2,3)`. An unfinished dangling segment has
the same face on both sides and creates no new region.

Encode four colors as $K=\mathbb Z_2\times\mathbb Z_2=\{00,01,10,11\}$ and set
$d(e)=c_L\oplus c_R$. A labeling reconstructs consistent face colors precisely
when its XOR around every **dual** closed walk is zero, with nonzero differences
on boundaries between distinct faces. A bridge must have difference zero.
The familiar nowhere-zero-flow formulation applies after restricting to
bridgeless plane graphs. See the proofs and scope in [Foundations](docs/FOUNDATIONS.md).

## Included results and their scope

| Component | Included | Scope / status |
| --- | --- | --- |
| Plane-map representation | Darts, rotation systems, face traversal, Euler validation | Finite connected cellular embeddings on the sphere |
| Recursive construction | Extend / CloseSplit operations and face-descendant logs | Given boundary corners; topology replay, not automatic recoloring |
| Color/difference equivalence | Reconstruction and primal vertex-defect checks | Elementary proofs; known algebraic principle |
| Boundary extension signatures | All extendable assignments and exact gluing formula | Exact enumeration is exponential; not a scalable general solver |
| Recursive stacked triangulations | Unique extension after fixing a root triangle | An elementary known restricted-class result |
| Minimum-change flow repair | Four-state series/parallel recursion with an optimal witness | Two-terminal series-parallel networks with a supplied expression |
| Independent validation | Exhaustive small instances and seeded checks against separate oracles | Finite evidence, never a proof for every planar graph |
| General recursive four-coloring | Explicit research questions and missing obligations | Open within this project; no general construction algorithm supplied |

The repair state $q$ is the XOR of labels at **each terminal vertex**, not a color
difference between two terminals. Series composition adds equal-state costs;
parallel composition minimizes over pairs with XOR $q$. Root state $q=0$ asks
for balance at all vertices. This distinction matters when reproducing the recurrence.

## Run locally

### Interactive map lab (v0.2)

Draw straight boundaries or load seven deterministic teaching maps. Crossings,
islands, nested regions and dangling edges are handled explicitly. Inspect each
directed edge's left/right face markers and export JSON or SVG.

The web app uses **direct candidate-mask selection, not backtracking or coloring
enumeration**. Each face is assigned at most once per run. An empty candidate set
is reported as `blocked`, never as evidence that a fifth color is necessary.
An eight-vertex planar regression fixture demonstrates that this greedy rule is
not complete. The earlier Python enumeration baseline is not called by the app.

```sh
# Node.js 20+; the web app has no third-party dependencies.
npm run dev
npm test
npm run build
python scripts/validate_web.py
```

Open the local URL printed by `npm run dev`. See [web reproduction and algorithm
contract](docs/WEB_APP.md). Public source does not automatically grant access to
an independently hosted site; site sharing is controlled separately.

Python 3.10 or newer is sufficient. The core has no third-party dependencies.
From the repository root:

```sh
python -m fourcolor demo
python -m unittest discover -s tests -v
python scripts/validate.py
```

The validation command writes [outputs/validation.json](outputs/validation.json),
including the seed, bounded case counts, runtime version, and pass/fail results.
The checked-in report records one run; rerunning regenerates it for your environment.
CI independently repeats the checks on Windows and Linux.

Minimal flow-repair example:

```python
from fourcolor.repair import Edge, Parallel, minimum_repair

# Three parallel edges form a theta network. Initially all labels are 01.
# To balance each degree-three terminal, the three nonzero labels must differ.
network = Parallel(Parallel(Edge(1), Edge(1)), Edge(1))
cost, repaired = minimum_repair(network)
assert cost == 2
assert set(repaired) == {1, 2, 3}
```

In Python, colors `0,1,2,3` encode `00,01,10,11`; the visual labels `1,2,3,4`
are display names. `Edge(label)` in the repair module takes a nonzero input
label `1,2,3`. [API notes](docs/API.md) explain representation and input limits.

Replay the initiating construction:

```python
from fourcolor.history import tetrahedron_history, replay

initial, operations = tetrahedron_history()
final_map, log = replay(initial, operations)
assert len(initial.faces) == 2
assert len(final_map.faces) == 4
# Each event retains before/after counts and the old-to-new face relationship.
```

One useful negative example is a four-cycle with a central vertex joined to all
four rim vertices. A rim precolored `0,1,2,3` cannot extend to the center, although
the same graph is three-colorable. Thus a valid intermediate coloring need not
extend without recoloring. The foundations and tests include this obstruction.

## Explore the diagrams

Download/clone the repository and open [docs/explainer.html](docs/explainer.html)
in a browser. It runs offline and lets you inspect direction reversal, splitting,
and closed-walk consistency. GitHub displays HTML source; the SVG above renders
directly in this README. The [original conversation diagram](four-color-edge-explainer.html)
is preserved as historical source.

## Research and attribution

Qinzi27 proposed the initiating left/right color-pair and nested-splitting idea.
Definitions, literature mapping, proofs, and implementation were developed with
AI assistance and require ordinary mathematical review. No priority claim is
made for known results. Reviewers are especially welcome to provide a precise
counterexample, a missing reference, or a smaller sufficient boundary state.

Start with [Related work](docs/RELATED_WORK.md) and the machine-readable
[bibliography](references.bib). Relevant areas include **four-color theorem,
four-colour theorem, planar graph coloring, plane maps, Tait coloring,
nowhere-zero flows, precoloring extension, tree decomposition, and recursive
boundary signatures**.

Use [CITATION.cff](CITATION.cff) and include the commit you used when citing an
experiment. Publication on GitHub provides a public, versioned research record;
it is not peer review or a certification of novelty.

## Reuse and contributions

This version is public for inspection. No open-source reuse license has yet been
selected by the maintainer. See [REUSE.md](REUSE.md) and
[CONTRIBUTING.md](CONTRIBUTING.md).

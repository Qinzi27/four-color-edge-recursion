# Four-Color Edge Recursion

**Recursive left/right face-color descriptions of plane maps, boundary signatures,
and verifiable Klein-four-group flow repair.**

[中文说明](README.zh-CN.md) · [Mathematical foundations](docs/FOUNDATIONS.en.md) · [数学基础](docs/FOUNDATIONS.md)
· [Research questions](docs/RESEARCH_PLAN.md) · [Related work](docs/RELATED_WORK.md)

## Research progress — 2026-09-20

**Starting inside can provably reduce the required interface on a specified graph
class; it does not guarantee a faster general coloring method.**

- **Proved scope:** for two nested-circle arms, each at least two face-adjacency
  steps long, the optimal interface width over connected-prefix orders is **2
  from the exterior versus 1 from an innermost end**. This is a fixed-start
  optimum, not just a favorable traversal example.
- **Matched experiments:** 63 maps, **1,917 runs with four available colors**, plus
  **1,917 minimum-palette runs using exactly the same orders**. Improvements and
  regressions are both retained.
- **An important control:** all 891 minimum-palette runs on the 37 nested trees
  retain a peak of just **two labeled states**. Their four-color state-count
  advantage disappears at two colors, while the interface-width result remains.

These are restricted proofs and independent diagnostics. They do not establish a
universal speedup or an improvement to the original greedy mother-line algorithm.

[Proofs, experiments and limits](docs/INSIDE_OUT_EXPERIMENT-2026-09-20.md)
· [Current comparison figure](docs/figures/inside-out-2026-09-20-v2/inside-out.png)
· [Circle-layer repairs and counterexamples](docs/CIRCLE_LAYER_REPAIR-2026-09-20.md)
· [Circle rank and two-layer formulation](docs/CIRCLE_RANK-2026-09-20.md)

## Why study this idea?

**Which boundary relations must a line-side construction retain so that a locally legal naming decision still admits a complete coloring?**
Qinzi27's initiating idea describes regions through the left/right names of directed
lines and tracks each complete construction line (a *mother line*) as its sides are
subdivided. The research question is precise: **when does “no conflict now” imply
“a completion still exists”?**

The project currently supports three concrete uses:

- **Explain and replay constructions:** distinguish line identity, face identity,
  current names and split history, and inspect the justification for each decision.
- **Extract conditions from failures:** locate the first non-extendable commitment,
  retain legal comparator witnesses and certify local implications. A nine-side
  inequality lemma already provides independently checkable certificates.
- **Compare rules and identify provable scope:** record both repairs and regressions
  on fixed inputs, and investigate sufficient boundary states, safe choices and
  the extent of synchronized renaming.

These are usable tools for rule experiments, counterexample analysis and teaching.
**No general speed advantage, smaller sufficient representation for the mother-line
method, or completeness guarantee has been established.**

### Has related work already been done?

**Yes; some underlying principles directly overlap with prior work.** Close
precedents include [Kauffman's map-color reformulations](https://homepages.math.uic.edu/~kauffman/MapReform.pdf),
[Cooper–Rowland–Zeilberger's binary-tree grammar](https://sites.math.rutgers.edu/~zeilberg/mamarim/mamarimPDF/4ct.pdf)
and [Dvořák–Lidický's boundary-coloring extension counts](https://arxiv.org/html/1907.04066v2).
Ordered pairs, parentheses, trees, Klein-four differences and boundary states are
therefore not novelty claims. Equivalence of the complete mother-line state and
operations to an existing method still requires an explicit correspondence; a
bounded literature search cannot certify originality.

One concrete correspondence is now verified: identifying the two supposedly equal
sides of the nine-side lemma produces `K₁ ∨ Moser spindle`. The lemma thus applies a
[classical four-chromatic graph](https://doc.sagemath.org/html/en/reference/graphs/sage/graphs/generators/smallgraphs.html#sage.graphs.generators.smallgraphs.MoserSpindle);
the project's work is its extraction and certification in actual failure cases,
not discovery of that fixed obstruction.

A potential new contribution would be a theorem for a specified graph class:
**a smaller sufficient interface, a guaranteed safe choice, or a new bound on
renaming.** At present, this is a **reproducible framework for line-side recursive
naming and experiments with construction rules**.

**Frozen baseline snapshot (2026-09-19):** v4 completes 7060 of 7069 deduplicated
inputs in the existing corpus, with nine conflicts. It repairs all four v3 failures
but introduces nine regressions. The nine-side lemma excludes the recorded fatal
candidate in three cases; it is not integrated into v4 and does not establish that
those maps are solved. These counts are neither a random-map success probability
nor a universal proof.

[Detailed research value, precedents and next-step criteria (中文)](docs/RESEARCH_VALUE-2026-09-19.md)
· [Earlier frozen-rule experiments and failure evidence](docs/PEER_BATCH_RESULTS-2026-09-19.md)

## Complete research archive

[Chronological methods, results and obstructions (中文)](docs/RESEARCH_HISTORY-2026-09-19.md)
· [English research history](docs/RESEARCH_HISTORY.en.md)
· [Reproduce from a clean checkout](docs/REPRODUCING_RESEARCH.md)

The historical archive below records the research through 2026-09-19; the
2026-09-20 additions are linked above. It covers changing definitions,
implementations, finite experiments, repaired examples, remaining obstructions,
and regressions. Different versions and test denominators must not be combined.
There is no new general proof or uniformly successful candidate algorithm.
Historical statements such as “not uploaded” describe the status at that stage;
this archive publishes the preserved work. The interactive website remains the
earlier construction lab, not an interface to the latest Python candidates.

Earlier frozen baseline (2026-09-19): [peer-batch geometry, full rerun and implicit inequalities](docs/PEER_BATCH_RESULTS-2026-09-19.md).
The frozen v4 solves 7060/7069 drawings, repairing all four v3 failures but introducing
nine regressions. It is not a uniformly stronger replacement or a general method.
All prefixes succeed for 358/363 histories; 362 final maps and 301/302 static references
succeed. Independent full-corpus audits pass; failures remain preserved.
A [proved nine-side implication](docs/IMPLICIT_INEQUALITY-2026-09-19.md) can exclude
the fatal candidate in 3/9 new failures. It is not integrated into v4 and does not
establish that those three maps have been rerun successfully.
Run a single drawing with `python scripts/name_peer_batch_map.py examples/peer-batch-five-lines.json --output outputs/my-peer-example.json`.
The output preserves interval-wise mother-line names and independently checked proofs.
No website replacement or publication; all prior evidence remains intact.

Previous unified algorithm (2026-09-19): [stage-scoped initialization and optional mother levels](docs/STAGED_LEVEL_RESULTS-2026-09-19.md).
One frozen v3 reruns all 7069 maps: 7065 solved, four conflicts, no scope rejection.
All 6113 original-cohort maps now succeed, including the blue-anchor case, but four
previously solved prefixes in one later-seed history regress. Every prefix succeeds
for 362/363 histories; all 363 final maps and 302 static references succeed.
[Theoretical conflict dossier](docs/STAGED_LEVEL_CONFLICTS-2026-09-19.md) preserves
the first fatal decisions, exact relation contradictions, and independent legal
witnesses for the next round. Initialization is safe; later greedy completion is
not proved. Independent aggregate/proof audits, 489 Python and 107 Node tests pass.
Old evidence and the website are preserved; no GitHub publication.

Previous direction (2026-09-19): implementation frozen at the user's request.
[Mathematical method draft](docs/MATHEMATICAL_METHOD-2026-09-19.md) separates
birth labels, current mother-line profiles and stage-scoped anchors;
[literature comparison](docs/RELATED_WORK_UPDATE-2026-09-19.md) identifies prior
tree-grammar/boundary-state work and the remaining safe-choice conjecture.
A later one-map anchor diagnosis is not a new full-corpus result. No novelty or
universal-completeness claim, solver change, or publication is made in this update.

Previous complete rerun (2026-09-19): [levels are auxiliary, not an eligibility gate](docs/LEVEL_SIDES_FULL-2026-09-19.md).
After the user's clarification, frozen v2 independently reruns all 7069 maps:
7068 solved, one conflict, no level-based rejection. All six prior failures are
repaired, but one previously solved map regresses. Every prefix succeeds for
362/363 histories; all 363 final maps and 302 static references succeed.
Exact blank/valid-comparator diagrams and independent audits are saved. This is
not complete success or a universal proof. All 457 Python and 107 Node tests pass.
No website replacement or GitHub publication.

Previous six-case test (2026-09-19): [mother-level stages and current-side constraints](docs/LEVEL_SIDE_RULES-2026-09-19.md).
One fixed level/whole-mother scheduling candidate solves all six prior regressions,
with 64 active choices including 20 uses of name 1; independent proofs and boundary
checks pass. This does not reproduce every handwritten mark: the highlighted strip
receives 3. That stage had NOT rerun all 7069 maps; see the later full results above. All 427 Python tests passed;
exact output diagrams are saved. The old core and website are not replaced.

Previous retrospective analysis (2026-09-19): [same-name mothers, generations and sibling positions](docs/LINE_GENERATIONS-2026-09-19.md).
Six regressions and 36 known-success controls confirm that whole lines with the
same directed (2,3) pair can have different geometric support depths. Three first
trajectory divergences in regressions involve shallower old choices; the other
three have equal depths, parents and ancestry counts but different positions.
This is diagnostic evidence, not a new ordering's success test. No solver or website change.

Previous local clarification (2026-09-19): [minimum-number choice audit](docs/MINIMUM_NAME_AUDIT-2026-09-19.md).
All 39,301 active choices across 7069 inputs already choose their smallest candidate.
With scheduling and filtering fixed, replacing reuse-first by `min(D)` leaves the
runs unchanged: 7063 solved, six blocked. The displayed D map succeeds on a fresh
restart; its frozen-name illustration is not a new failure. No solver or website change.

Previous full validation (2026-09-19): [complete frozen-rule corpus replay](docs/RELATION_FRONTIER_FULL-2026-09-19.md).
The current rule solves 7063/7069 distinct inputs, every prefix of 359/363 histories,
all 363 final drawings, and all 302 static cases. It fixes 268 prior failures but
regresses on six previously solved intermediate drawings. Their old valid colorings
remain available; greedy commitment, not four-colorability, fails. Full input coverage,
baseline reproduction, certificates and independent summary audit pass. No retuning,
fallback solver, general completeness claim, or website update.

Previous diagnostic stage (2026-09-19): [preserve side-name compatibility before committing names](docs/RELATION_FRONTIER-2026-09-19.md).
The existing pair filter now integrates with geometry-only restarts, keeping
mother identities, intervals, and the priority formula unchanged. No new cycle
grouping is introduced. The ninth-cut regression loses its fatal candidate
before commitment, without backtracking or importing an old coloring.
All 307 predeclared known-case diagnostics complete, including 135 regressions
and 135 success controls. This stage did not rerun the full 7069 drawings;
the subsequent complete replay is linked above. These diagnostics do not establish
completeness. No website update.

Earlier this round (2026-09-19): [line-side urgency, local candidate reservation and full replay](docs/FRONTIER_RULES-2026-09-19.md).
Using established constraint-filtering ideas, the best new candidate solves 5881/6113
existing drawings and every prefix of 244/323 histories (baseline: 5638 and 199).
It completes 24/40 predeclared new-seed histories (baseline: 9), but regresses on
135 previously solved existing drawings. All failures and a new six-cut example
are retained. The 35,345 independent checks include conflicts, not only successful
colorings. No general proof, novelty claim, or website update.

Earlier local research (2026-09-18): [restart after EVERY added line; current constraints and closed-cycle support](docs/GLOBAL_RESTART-2026-09-18.md).
The previously stopped seventh cut now recolors automatically. Across 323 declared
histories and every geometric prefix, the closure-assisted proposal completes
all prefixes of 199 histories and the final drawing of 264; these are different
counts. The constraint-only control completes 200 full histories, so the closure
tie preference has not demonstrated an overall improvement. No website update.

Earlier local research: [current side names, shared-interface release, conditional proofs and full replay](docs/CURRENT_NAMING_RULES-2026-09-18.md).
On 323 deduplicated declared histories, the bounded rule completes 18, blocks on
219, and marks 86 outside its rectangular adapter. The wider-budget control
completes 95, with 142 still blocked. All 17,491 initial/committed-state checks
pass; 302 static topology checks are reported separately, not as coloring success.
This is a local research implementation, not a general proof or a website update.

Earlier [continuous dual-anchor experiment](docs/ANCHOR_FOREST_CONTINUATION-2026-09-18.md):
all 85 earlier first-block repairs now continue, adding 228 committed steps, but
all 360 general rectangular runs eventually block again; all 80 strip runs finish.
At 60 new stops, a common anchor exists only in a newly created child side.

Local research update (2026-09-18): [retained-side inheritance and equivalent line types](docs/RETAINED_PROFILE_SYNTHESIS-2026-09-18.md).
The supplied 3|4|3 sketch now has a reproducible full-boundary naming and verified
two-anchor strip synchronization model. All 80 strip-history runs complete;
360 general rectangular-history runs still block. A separate broader dual-anchor
audit certifies a one-step repair at 85 of those blocks, without continuing their
remaining histories. This is not a general proof
and is not yet wired into the public website described below.

[![Validation](https://github.com/Qinzi27/four-color-edge-recursion/actions/workflows/validate.yml/badge.svg)](https://github.com/Qinzi27/four-color-edge-recursion/actions/workflows/validate.yml)

[Open the line-first construction lab](https://qinzi27.github.io/four-color-edge-recursion/rules.html)
· [Old comparison baseline](https://qinzi27.github.io/four-color-edge-recursion/)
· [Recursive model explainer](https://qinzi27.github.io/four-color-edge-recursion/model.html)
· [Method fidelity and literature audit](docs/METHOD_REVIEW-2026-09-07.md)

The public GitHub Pages site does not require a GitHub or ChatGPT account.
The new **line-first construction lab** commits only anchored paths or independent
loops, reads existing symbols from directed line names, and applies a proved
two-contact extension rule without coloring enumeration or backtracking.
It stops with a certificate when a frozen precoloring cannot extend. The old
face-greedy interface remains a clearly labeled comparison baseline.

The general successful-order gap remains unresolved. A four-step example shows
that one input history blocks while another history of the same target map works.
There are 13 replayable gallery cases and 240 consecutively seeded generated maps;
160 guillotine histories block, whereas 80 ring/fan cases complete. Python independently
validates 2,569 committed-state certificates, not universal success.
See [proved rule, counterexample and reproduction](docs/CONSTRUCTION_RULES-2026-09-08.md)
and the [machine-readable experiment report](outputs/construction-validation-2026-09-08.json).

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

### Line-first lab and comparison baseline

Run `npm run dev` and open `/rules.html` under the printed URL. Replay gallery
operations, draw anchored polylines or independent loops, inspect ordered line
names, and export/import auditable JSON. `python scripts/validate_construction.py`
repeats the finite experiments and independent Python checks. Every incomplete or
blocked operation preserves all committed names. This is a restricted implementation
proposal, not a claim that the initiating notation uniquely determines tie-breaking.

The older root page remains available for comparison:

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

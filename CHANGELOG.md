# Changelog

## 2026-09-19 — Complete research archive and reproducibility

- Published the accumulated research chronology, bilingual navigation, mathematical
  notes, implementations, original map inputs, conflict certificates, and full
  experiment/checkpoint records. See [research history](docs/RESEARCH_HISTORY-2026-09-19.md).
- Preserved negative results and initialization corrections: v3 completes
  7065/7069 drawings; v4 completes 7060/7069, fixes all four v3 failures and
  introduces nine regressions. Different methods are not combined into a success claim.
- Recorded the proved nine-side implicit-inequality template and its 3/9 coverage
  of the fatal v4 decisions, separately from full-map coloring success.
- Added an [external reproduction guide](docs/REPRODUCING_RESEARCH.md), optional
  Pillow test dependency, complete JavaScript regression checks, and byte-preserving
  Git attributes for hash-bound research evidence.
- Kept private attachments and local workflow metadata out of the public archive.
  This publication does not change the frozen algorithms or the website's default method.
- Ten early JSON reports had previously been normalized by Git. Their verified
  working-file bytes are now stored without EOL conversion; parsed mathematical
  contents are unchanged. The publication-index check checks every evidence blob.

## 2026-09-07 — Public Pages and method-fidelity clarification

- Added GitHub Pages deployment of validated static assets and the theory explainer.
- Clearly labeled the greedy marker rule as a comparison baseline, not the
  initiating author's fully specified recursive construction.
- Added a literature/provenance review and a frozen-precoloring face-split
  obstruction. Node regression coverage now contains 23 tests.

## 0.2.0 — 2026-09-07

- Added a dependency-free interactive drawing website with seven original cases.
- Planarized intersections/overlaps; handled disconnected and nested boundaries
  using invisible, face-preserving bridges; retained the external frame face.
- Implemented direct four-bit marker selection, with no backtracking or enumeration,
  following the initiating author's requirement. Candidate exhaustion is explicit.
- Added JSON replay/certificates, SVG export, directed-shore inspection, and undo.
- Added 22 Node tests, including a planar greedy obstruction, and 37 independent
  Python/web certificate comparisons. Existing mathematical core remains unchanged.
- Browser interaction and actual WebMCP-context validation have not been performed.

## 0.1.0 — 2026-09-06

Initial public research foundation for Qinzi27's recursive edge-side model.

- Formal connected plane-map model with darts, rotations, face IDs, and bridge handling.
- Elementary proofs of dual path consistency, face potentials, boundary relation gluing,
  rooted stacked-triangulation extension, and restricted minimum-repair formulas.
- Reproducible Extend / CloseSplit construction with a replayable operation history.
- Exact small-instance coloring enumeration and boundary projection.
- Four-state minimum Hamming repair for two-terminal series-parallel nonzero V4 flows.
- Independent finite validation, cross-platform CI, bilingual introductions, and diagrams.
- Explicit remaining research questions and prior-work attribution.

This version supplies a research baseline. It does not claim a new general proof
of the Four-Color Theorem or established novelty for the basic results.

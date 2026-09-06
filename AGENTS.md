# AGENTS.md

This is a reproducible mathematical research project about recursive edge-side
descriptions of plane-map four-coloring. The initiating idea belongs to Qinzi27.

- Write explanatory comments and docstrings in all scripts.
- Keep face identifiers, face colors, primal edges, dual edges, and split-history
  nodes distinct. A dangling edge does not split a face.
- A bridge has the same face on both sides and therefore color difference zero.
  Nowhere-zero flow statements require the explicitly stated bridgeless scope.
- Specify whether a closed walk belongs to the primal graph or the dual graph.
- Separate proved elementary/known results, conjectures, and finite experiments.
  Do not call this repository a new proof of the Four-Color Theorem.
- Preserve the original explanatory fragment and all user-authored work.
- Use Python 3.10+ and the standard library for the core; avoid unnecessary dependencies.
- Save reproducible generated validation reports in outputs/ and figures in docs/figures/.
- Keep random seeds, graph families, size bounds, and independent oracle results explicit.
- Before changing mathematical logic, explain the reason; keep changes small and reviewable.
- Run python -m unittest discover -s tests -v and python scripts/validate.py.
- Do not publish private machine paths, credentials, memory files, or conversation logs.
- Do not add or change a reuse license without the maintainer's authorization.

"""Small exact probability experiments for directed line-side names.

The input contains only dart likelihoods and junction rotations. Topological
side orbits come from the existing line-name auditor, never supplied faces.
This module adds a statistical model; it does not change the construction
rules or claim a new inference algorithm or Four-Color Theorem proof.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import product
from math import exp, fsum, isfinite, log, log1p

from .line_names import audit_line_names


@dataclass(frozen=True)
class InferenceResult:
    """Exact marginals and a complete MAP assignment for a bounded model.

    ``state_count`` counts configurations BEFORE inequality and zero-weight
    filtering: q**dart_count for independent, q**orbit_count otherwise. Only
    joint actually enumerates this count. The other two modes are analytic.
    ``log_partition`` is log of the sum of unnormalized likelihood products
    over legal configurations. It excludes any normalized prior constant,
    so it is not a marginal likelihood for comparing the three models.
    """

    dart_marginals: tuple[tuple[float, ...], ...]
    map_labels: tuple[int, ...]
    log_partition: float
    state_count: int
    side_orbits: tuple[tuple[int, ...], ...]


def _logadd(first: float, second: float) -> float:
    """Add two nonnegative weights represented by logarithms, including zero."""
    if first == float("-inf"):
        return second
    if second == float("-inf"):
        return first
    upper, lower = max(first, second), min(first, second)
    return upper + log1p(exp(lower - upper))


def _logsum(values: Sequence[float]) -> float:
    """Stable log-sum-exp without multiplying small input likelihoods."""
    largest = max(values)
    if largest == float("-inf"):
        return largest
    return largest + log(fsum(exp(value - largest) for value in values))


def _likelihood_rows(likelihoods: Sequence[Sequence[float]]) -> tuple[tuple[float, ...], ...]:
    """Copy rectangular finite likelihoods and reject ambiguous empty palettes."""
    try:
        supplied_rows = tuple(likelihoods)
        if any(isinstance(row, (str, bytes)) for row in supplied_rows):
            raise ValueError("a likelihood row must be numeric entries, not a string")
        rows = tuple(tuple(float(value) for value in row) for row in supplied_rows)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("likelihoods must be a rectangular numeric matrix") from error
    if not rows or len(rows[0]) < 2:
        raise ValueError("at least one dart row and a palette of size q >= 2 are required")
    if len(rows) % 2 or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError("likelihoods require two dart rows per edge and a shared palette")
    if any(not isfinite(value) or value < 0 for row in rows for value in row):
        raise ValueError("likelihoods must be nonnegative and finite")
    if any(not any(row) for row in rows):
        raise ValueError("each dart must have at least one positive likelihood")
    return rows


def infer_names(
    rotation: Sequence[Sequence[int]],
    likelihoods: Sequence[Sequence[float]],
    mode: str = "joint",
    max_states: int = 65536,
) -> InferenceResult:
    """Infer line-side symbols under three explicitly different models.

    Row d is L_d(k), the likelihood of an observation at dart d conditional
    on label k in range(q). Rows need not sum to one. The model assumes
    conditionally independent observations and a uniform prior over valid
    assignments for the chosen mode. Its unnormalized weight is
    indicator[valid(x)] * product_d L_d(x_d). Correlated/repeated observations
    must not be passed as independent measurements without justification.

    independent: no symbol constraints; normalize each dart separately.
    orbit: continuing sides share a symbol; normalize each orbit's product.
    joint: also require different symbols across genuine separators. Bridge
    darts belong to the same orbit and never create an inequality constraint.

    All modes require a connected plane rotation system checked by the
    existing auditor. Empty dart inputs are rejected because q is not given
    separately. Only joint enumerates assignments, with q**orbit_count <=
    max_states as a hard cap even when constraints could prune assignments.
    Thus this is a tiny-instance oracle, not a scalable inference method.

    MAP means one complete highest-weight assignment, not separate marginal
    argmax labels (which need not jointly satisfy the rules). Ties use the
    first lexicographic assignment in deterministic dart/orbit order.
    """
    if mode not in ("independent", "orbit", "joint"):
        raise ValueError("mode must be independent, orbit, or joint")
    if type(max_states) is not int or max_states < 1:
        raise ValueError("max_states must be a positive integer")
    rows = _likelihood_rows(likelihoods)
    dart_count, palette_size = len(rows), len(rows[0])
    audit = audit_line_names(rotation, ((None, None),) * (dart_count // 2))
    orbits = audit.side_orbits
    groups = tuple((dart,) for dart in range(dart_count)) if mode == "independent" else orbits
    state_count = palette_size ** len(groups)
    if mode == "joint" and state_count > max_states:
        raise ValueError(f"joint needs {state_count} raw states, exceeding max_states={max_states}")

    # Reduce per-dart evidence to an orbit potential while staying in log space.
    negative_infinity = float("-inf")
    log_rows = tuple(tuple(log(value) if value else negative_infinity for value in row)
                     for row in rows)
    potentials = tuple(tuple(fsum(log_rows[dart][label] for dart in group)
                             for label in range(palette_size)) for group in groups)
    group_of_dart = [0] * dart_count
    for group_id, group in enumerate(groups):
        for dart in group:
            group_of_dart[dart] = group_id

    if mode != "joint":
        normalizers = tuple(_logsum(potential) for potential in potentials)
        if any(value == negative_infinity for value in normalizers):
            raise ValueError("no positive-weight assignment satisfies the selected constraints")
        group_marginals = tuple(tuple(exp(value - normalizer) for value in potential)
                                for potential, normalizer in zip(potentials, normalizers))
        best = tuple(max(range(palette_size), key=potential.__getitem__)
                     for potential in potentials)
        log_partition = fsum(normalizers)
    else:
        # A bridge creates no separator factor; parallel constraints are deduplicated.
        separators = tuple(sorted({tuple(sorted((group_of_dart[dart], group_of_dart[dart ^ 1])))
                                   for dart in range(0, dart_count, 2)
                                   if group_of_dart[dart] != group_of_dart[dart ^ 1]}))
        log_marginals = [[negative_infinity] * palette_size for _ in groups]
        log_partition, best_weight, best = negative_infinity, negative_infinity, None
        for assignment in product(range(palette_size), repeat=len(groups)):
            if any(assignment[left] == assignment[right] for left, right in separators):
                continue
            weight = fsum(potential[label] for potential, label in zip(potentials, assignment))
            if weight == negative_infinity:
                continue
            log_partition = _logadd(log_partition, weight)
            for group_id, label in enumerate(assignment):
                log_marginals[group_id][label] = _logadd(log_marginals[group_id][label], weight)
            if best is None or weight > best_weight:
                best_weight, best = weight, assignment
        if best is None:
            raise ValueError("no positive-weight assignment satisfies the selected constraints")
        group_marginals = tuple(tuple(exp(value - log_partition) for value in marginal)
                                for marginal in log_marginals)

    return InferenceResult(
        dart_marginals=tuple(group_marginals[group_of_dart[dart]] for dart in range(dart_count)),
        map_labels=tuple(best[group_of_dart[dart]] for dart in range(dart_count)),
        log_partition=log_partition,
        state_count=state_count,
        side_orbits=orbits,
    )

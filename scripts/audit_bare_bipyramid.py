"""Exhaust all partial color commitments on the bare triangular bipyramid.

This is a finite audit of the five-vertex graph K5 minus A--E, with no
external candidate lists, extra vertices, embedding, or mother-line schedule.
Literal complete assignments are the independent reference; they never choose
a candidate for the producer. Every color at every uncommitted vertex is tried.

Structural reason for the expected result: B,C,D form a triangle, so every
proper four-coloring has A=E, with that common color absent from B,C,D.
For an extendible partial commitment, an illegal next color either conflicts
with an already committed neighbor, or assigns different colors to A and E.
In the latter case B,C,D have at most two available colors; binary path
consistency refutes a triangle with two colors. Consequently every surviving
trial on the bare graph extends, independently of the next-vertex schedule.
This conclusion does not extend to external list restrictions or larger maps.
"""

from collections import Counter
from itertools import product

from scripts.quaternary_contact_model import propagate_contacts


SIDES = ("A", "B", "C", "D", "E")
EDGES = ((1, 2), (1, 3), (2, 3),
         (0, 1), (0, 2), (0, 3), (4, 1), (4, 2), (4, 3))


def bare_document(values):
    """Create only literal real-edge inequalities and singleton commitments.

    A zero means uncommitted; no supplied candidate-state word is generated.
    """
    if len(values) != 5 or any(type(c) is not int or not 0 <= c <= 4 for c in values):
        raise ValueError("five integer commitment entries in 0..4 are required")
    return {"sides": list(SIDES),
            "lines": [{"id": f"E{i}", "left": SIDES[a], "right": SIDES[b],
                       "kind": "separator"} for i, (a, b) in enumerate(EDGES)],
            "anchors": {side: color for side, color in zip(SIDES, values) if color},
            "states": {}}


def literal_solutions():
    """Independently inspect every one of the 4**5 complete assignments."""
    return [values for values in product((1, 2, 3, 4), repeat=5)
            if all(values[a] != values[b] for a, b in EDGES)]


def _require(condition, message):
    """Keep failed finite claims visible even under Python optimization."""
    if not condition:
        raise AssertionError(message)


def audit_bare_bipyramid(*, max_examples=3):
    """Audit all 5**5 partial vectors and all trials after extendible vectors.

    The independent solution set filters the population of extendible input
    commitments. Within each such input, the producer sees all four colors at
    every uncommitted vertex, including colors its initial propagation removes.
    No independent solution, safe candidate, or next-vertex advice is supplied
    to propagation. Compact evidence keeps example counts bounded.
    """
    if type(max_examples) is not int or max_examples < 0:
        raise ValueError("max_examples must be a nonnegative integer")
    solutions = literal_solutions()
    _require(len(solutions) == 24, "bare graph must have 24 literal four-colorings")
    _require(all(values[0] == values[4] for values in solutions),
             "bare graph solution must give A and E the same color")
    counts = Counter()
    examples = []
    for values in product((0, 1, 2, 3, 4), repeat=5):
        counts["partial_commitments_enumerated"] += 1
        legal = [assignment for assignment in solutions
                 if all(color == 0 or assignment[i] == color
                        for i, color in enumerate(values))]
        if not legal:
            counts["nonextendible_partial_commitments_outside_trial_population"] += 1
            continue
        counts["extendible_partial_commitments"] += 1
        original = propagate_contacts(bare_document(values))
        _require(original["status"] != "conflict", "extendible initial state was rejected")
        for vertex, committed in enumerate(values):
            if committed:
                continue
            for color in (1, 2, 3, 4):
                trial_values = list(values)
                trial_values[vertex] = color
                # Run every literal trial before classifying its exact outcome.
                trial = propagate_contacts(bare_document(trial_values))
                after = [assignment for assignment in legal if assignment[vertex] == color]
                refuted = trial["status"] == "conflict"
                counts["all_literal_trials"] += 1
                counts["extendible_trials" if after else "nonextendible_trials"] += 1
                counts["trial_conflicts" if refuted else "trial_survivors"] += 1
                was_candidate = color in original["domains"][vertex]
                if was_candidate:
                    counts["propagated_candidate_trials"] += 1
                    if not after:
                        counts["nonextendible_propagated_candidate_trials"] += 1
                if len(original["domains"][vertex]) > 1 and was_candidate:
                    counts["unresolved_candidate_trials"] += 1
                    if not after:
                        counts["nonextendible_unresolved_candidate_trials"] += 1
                _require(bool(after) != refuted,
                         f"trial classification differs at {values}, {SIDES[vertex]}={color}")
                if not after and was_candidate and len(examples) < max_examples:
                    examples.append({"commitment_vector": list(values),
                                     "side": SIDES[vertex], "color": color,
                                     "domain_before": original["domains"][vertex],
                                     "solutions_before": len(legal),
                                     "solutions_after": 0, "producer_status": trial["status"]})
    return {"schema_version": 1, "audit_version": "bare-bipyramid-all-partial-commitments-v1",
            "passed": True, "sides": list(SIDES),
            "edges": [[SIDES[a], SIDES[b]] for a, b in EDGES],
            "complete_assignments_enumerated": 4 ** 5,
            "complete_legal_assignments": len(solutions), "counts": dict(counts),
            "refuted_candidate_examples": examples,
            "wrong_trial_classifications": 0, "oracle_feedback_to_producer": False,
            "external_candidate_states": False, "geometry_or_mother_schedule_checked": False,
            "scope": "Bare five-vertex graph; all literal partial commitments and every "
                     "uncommitted-vertex/color trial after extendible commitments. "
                     "No reachability or completeness claim for larger graphs."}

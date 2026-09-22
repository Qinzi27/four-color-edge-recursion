"""Audit a discovered single-anchor obstruction with only real NEQ edges.

Attach the planar graph K4(P,Q,X,Y) plus triangle AXY to a bare triangular
bipyramid at its vertex A, and attach leaf Z to the opposite apex E. The
attachment at one vertex preserves planarity. This establishes abstract graph
planarity, not a region-map realization or the production mother-line schedule.

With input-order scheduling Z,P,Q,X,A,B,C,D,E,Y and initial Z=1, the guarded
low-color producer commits P=1,Q=2,X=3 before A=1. At that point the previously
external lists A={1,2}, E={2,3,4} have arisen from real inequalities and actual
commitments. A=1 destroys every full coloring despite its inconclusive trial.
This is a development-discovered diagnostic, never a blind or held-out input.
"""

from hashlib import sha256
from itertools import product
import json

from scripts.audit_quaternary_low_color import audit_low_color
from scripts.quaternary_low_color import solve_low_color


SIDES = ("Z", "P", "Q", "X", "A", "B", "C", "D", "E", "Y")
EDGES = (("B", "C"), ("B", "D"), ("C", "D"),
         ("A", "B"), ("A", "C"), ("A", "D"),
         ("E", "B"), ("E", "C"), ("E", "D"),
         ("P", "Q"), ("P", "X"), ("P", "Y"),
         ("Q", "X"), ("Q", "Y"), ("X", "Y"),
         ("A", "X"), ("A", "Y"), ("E", "Z"))
PREFIXES = ({}, {"Z": 1}, {"Z": 1, "P": 1},
            {"Z": 1, "P": 1, "Q": 2},
            {"Z": 1, "P": 1, "Q": 2, "X": 3},
            {"Z": 1, "P": 1, "Q": 2, "X": 3, "A": 1})


def lifted_document():
    """Return the exact ten-side input with one anchor and no external lists."""
    return {"sides": list(SIDES),
            "lines": [{"id": f"E{i}", "left": a, "right": b, "kind": "separator"}
                      for i, (a, b) in enumerate(EDGES)],
            "anchors": {"Z": 1}, "states": {}}


def _require(condition, message):
    """Make failed scientific assertions fatal even under Python optimization."""
    if not condition:
        raise AssertionError(message)


def literal_prefix_evidence(document):
    """Independently enumerate all 4**10 literal assignments, including Z!=1.

    This is deliberately separate from the producer's relation propagation and
    the exact oracle. It reads only raw endpoints and explicit prefix anchors.
    All complete legal assignments are inspected without symmetry reduction.
    """
    _require(document == lifted_document(), "literal diagnostic input differs")
    sides = document["sides"]
    index = {side: i for i, side in enumerate(sides)}
    edges = [(index[line["left"]], index[line["right"]]) for line in document["lines"]]
    legal, checked = [], 0
    for values in product((1, 2, 3, 4), repeat=len(sides)):
        checked += 1
        if all(values[a] != values[b] for a, b in edges):
            legal.append(values)
    rows = []
    for fixed in PREFIXES:
        matches = [values for values in legal
                   if all(values[index[side]] == color for side, color in fixed.items())]
        rows.append({"commitments": dict(fixed), "legal_assignment_count": len(matches),
                     "first_witness": dict(zip(sides, matches[0])) if matches else None})
    _require(checked == 1048576, "incomplete literal enumeration")
    _require([row["legal_assignment_count"] for row in rows] == [864, 216, 36, 12, 6, 0],
             "unexpected literal prefix counts")
    before = [dict(zip(sides, values)) for values in legal
              if all(values[index[side]] == color for side, color in PREFIXES[-2].items())]
    return {"passed": True, "cartesian_assignments_checked": checked,
            "symmetry_reduction": False, "prefixes": rows,
            "all_six_witnesses_before_first_bad_commitment": before,
            "complete_unanchored_legal_assignments_sha256": sha256(
                json.dumps(legal, separators=(",", ":")).encode("utf-8")).hexdigest(),
            "oracle_or_propagation_used_for_enumeration": False}


def audit_lifted_bipyramid():
    """Finish the producer first, then verify every phase and actual commitment.

    The reused independent low-color auditor enumerates the 4**9 assignments
    satisfying initial Z=1, replays all traces, and saves SAT witnesses and full
    verified UNSAT search trees for the first bad commitment. The additional
    literal enumeration visits 4**10 assignments, independently including the
    unanchored count. Neither audit supplies choices or rescue to the producer.
    """
    document = lifted_document()
    result = solve_low_color(document, probe=True, decision_limit=128, probe_limit=512)
    # Both independent checks run only after the entire producer run completes.
    audit = audit_low_color(document, result, assignment_limit=262144, node_limit=200000)
    exhaustive = literal_prefix_evidence(document)
    commitments = [event for event in result["events"] if event["kind"] == "commit"]
    _require([(event["side"], event["symbol"]) for event in commitments]
             == [("P", 1), ("Q", 2), ("X", 3), ("A", 1)],
             "actual low-color commitments changed")
    _require(result["status"] == "conflict" and result["colors"] is None
             and result["schedule"] == "first-unresolved-input-order-v1"
             and result["oracle_feedback_to_producer"] is False,
             "unexpected producer mode or terminal result")
    _require(audit["commitment_counts"] ==
             {"safe": 3, "unsafe": 1, "unknown": 0, "preexisting_unsat": 0},
             "wrong first-error or extendibility classification")
    _require(audit["oracle_unknown"] == 0 and audit["full_enumeration"]["status"] == "run"
             and audit["full_enumeration"]["initial_legal_assignments"] == 216,
             "incomplete independent audit")
    first_bad = audit["first_bad_commitment"]
    _require(first_bad["event_index"] == 3 and first_bad["side"] == "A"
             and first_bad["symbol"] == 1 and first_bad["before_status"] == "sat"
             and first_bad["after_status"] == "unsat", "unexpected first unsafe commitment")
    before_phase = result["phases"][first_bad["before_phase"]]
    domains = dict(zip(SIDES, before_phase["outcome"]["domains"]))
    _require(domains["A"] == [1, 2] and domains["E"] == [2, 3, 4]
             and all(domains[side] == [1, 2, 3, 4] for side in ("B", "C", "D")),
             "external-domain obstruction was not generated by commitments")
    return {"schema_version": 1, "audit_version": "lifted-bipyramid-single-anchor-v1",
            "passed": True, "input_role": "development-discovered-diagnostic",
            "document": document, "result": result, "audit": audit,
            "independent_literal_enumeration": exhaustive,
            "domains_before_first_bad_commitment": domains,
            "planarity_argument": "K5-AE is planar; K4(P,Q,X,Y) plus triangle AXY "
                "is planar by gluing along XY. Attach that component to the core "
                "only at A, then add leaf Z at E.",
            "geometry_realization_checked": False, "mother_schedule_reachability_checked": False,
            "external_candidate_states": False, "oracle_feedback_to_producer": False,
            "scope": "Single-anchor, original NEQ edges, actual guarded low-color commitments, "
                "abstract input-order scheduling. Graph-planar diagnostic, not yet a failure "
                "of the real-map mother-line schedule and not a held-out experiment."}

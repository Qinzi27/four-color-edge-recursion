"""Exhaust declared literal graph/domain cases for triangle color saturation.

The declaration covers all labeled four-vertex graphs and eight explicit-EQ
five-vertex lifts of K4. Each case visits all 4**n literal assignments before
filtering real edges, explicit equalities, and domains. Saved checking never
calls the detector, propagation, or an exact-search oracle.
"""

from hashlib import sha256
from itertools import combinations, product
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.quaternary_triangle_saturation import find_triangle_saturations
from scripts.check_quaternary_triangle_saturation import check_triangle_saturations

VERSION = "quaternary-triangle-saturation-finite-soundness-v1"
SIDES = ("a", "b", "c", "t")
LIFT_SIDES = ("a", "b", "c", "t0", "t1")
BASE_EDGES = tuple(combinations(range(4), 2))


def _require(condition, message):
    """Keep scientific checks active under optimized execution."""
    if not condition:
        raise AssertionError(message)


def _digest(value):
    """Hash canonical literal JSON without borrowing detector utilities."""
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode("utf-8")).hexdigest()


def _same(actual, expected, label):
    """Reject omitted fields, altered types, and bool/int aliases."""
    _require(json.dumps(actual, sort_keys=True, allow_nan=False) ==
             json.dumps(expected, sort_keys=True, allow_nan=False), label + " differs")


def _document(sides, edges):
    """Keep only literal physical separator edges in the source document."""
    return {"sides": list(sides), "lines": [
        {"id": f"E{i}", "left": sides[a], "right": sides[b], "kind": "separator"}
        for i, (a, b) in enumerate(edges)]}


def _domain_patterns(side_count):
    """Declare 21 patterns, with uniform domains in any lifted target class."""
    for excluded in range(1, 5):
        triple = [color for color in range(1, 5) if color != excluded]
        yield (f"omit-{excluded}", "triangle-triple-target-full", excluded, None,
               [list(triple) for _ in range(3)] + [[1, 2, 3, 4] for _ in range(side_count - 3)])
    for relaxed, side in enumerate(SIDES[:3]):
        for excluded in range(1, 5):
            triple = [color for color in range(1, 5) if color != excluded]
            domains = [list(triple) for _ in range(3)] + [[1, 2, 3, 4] for _ in range(side_count - 3)]
            domains[relaxed] = [1, 2, 3, 4]
            yield (f"relax-{side}-omit-{excluded}", "one-triangle-vertex-relaxed-control",
                   excluded, side, domains)
    yield ("four-colors", "all-four-color-control", None, None,
           [[1, 2, 3, 4] for _ in range(side_count)])
    for excluded in range(1, 5):
        triple = [color for color in range(1, 5) if color != excluded]
        yield (f"all-triple-omit-{excluded}", "all-triple-vacuity-control", excluded, None,
               [list(triple) for _ in range(side_count)])


def rule_inventory():
    """Declare 1,512 cases without invoking discovery, propagation, or search."""
    records = []
    for mask in range(64):
        edges = [edge for bit, edge in enumerate(BASE_EDGES) if mask & (1 << bit)]
        document = _document(SIDES, edges)
        for suffix, pattern, excluded, relaxed, domains in _domain_patterns(4):
            records.append({"id": f"saturation-mask-{mask:02x}-{suffix}",
                            "family": "all-four-vertex-simple-graphs", "domain_pattern": pattern,
                            "edge_mask": mask, "endpoint_mask": None, "excluded_color": excluded,
                            "relaxed_side": relaxed, "document": document,
                            "equal_names": [], "domains": domains})
    for mask in range(8):
        # The target class has two literal members. Each of the three incident
        # physical edges independently chooses its target endpoint, retaining
        # the six-edge K4 quotient but not inventing any literal contact.
        edges = [(0, 1), (0, 2), (1, 2)]
        edges.extend((vertex, 3 + ((mask >> vertex) & 1)) for vertex in range(3))
        document = _document(LIFT_SIDES, edges)
        for suffix, pattern, excluded, relaxed, domains in _domain_patterns(5):
            records.append({"id": f"saturation-eq-lift-{mask}-{suffix}",
                            "family": "five-vertex-target-eq-lifts", "domain_pattern": pattern,
                            "edge_mask": None, "endpoint_mask": mask, "excluded_color": excluded,
                            "relaxed_side": relaxed, "document": document,
                            "equal_names": [["t0", "t1"]], "domains": domains})
    return records


def _domain_product_size(domains):
    """Count domain tuples before filtering physical edges or explicit EQ."""
    total = 1
    for domain in domains:
        total *= len(domain)
    return total


def _evaluate(records, saved_rows=None):
    """Check every deleted literal against original-constraint legal assignments.

    No quotient assignment substitutes for literal enumeration: the five-point
    family visits 1,024 tuples, including those violating the explicit EQ. Raw
    legality can be cached across domain patterns, but each case's denominator
    remains 4**n. Unsupported, unreported literals are counted separately from
    supported negative witnesses and from vacuous domain-UNSAT cases.
    """
    _require(saved_rows is None or len(saved_rows) == len(records), "saved finite case coverage differs")
    assignments_by_size, raw_cache, rows = {}, {}, []
    for number, record in enumerate(records):
        document, domains, equal_names = record["document"], record["domains"], record["equal_names"]
        sides = document["sides"]
        edges = [(sides.index(line["left"]), sides.index(line["right"])) for line in document["lines"]]
        equalities = [(sides.index(first), sides.index(second)) for first, second in equal_names]
        assignments = assignments_by_size.setdefault(len(sides), list(product((1, 2, 3, 4), repeat=len(sides))))
        raw_key = _digest([document, equal_names])
        if raw_key not in raw_cache:
            raw_cache[raw_key] = [all(values[a] != values[b] for a, b in edges) and
                                  all(values[a] == values[b] for a, b in equalities)
                                  for values in assignments]
        raw_legal, domain_legal = [], []
        for values, valid in zip(assignments, raw_cache[raw_key]):
            if valid:
                raw_legal.append(list(values))
                if all(value in domain for value, domain in zip(values, domains)):
                    domain_legal.append(list(values))
        _require(raw_legal, "declared original physical graph plus EQ has no four-color witness")
        evidence = (find_triangle_saturations(document, domains, equal_names) if saved_rows is None
                    else saved_rows[number]["evidence"])
        checked = check_triangle_saturations(document, domains, equal_names, evidence)
        _require(checked["passed"], "independent saturation audit failed")
        classes = {members[0]: members for members in evidence["classes"]}
        removed = {side: set() for side in sides}
        for certificate in evidence["certificates"]:
            for side in classes[certificate["target"]]:
                removed[side].update(certificate["removed_colors"])
        deletion_checks, nonreported_checks = [], []
        for index, side in enumerate(sides):
            for color in domains[index]:
                supported = [values for values in domain_legal if values[index] == color]
                if color in removed[side]:
                    _require(not supported, "a certified deletion removed a legal original-constraint coloring")
                    deletion_checks.append({"side": side, "color": color,
                                            "legal_assignments_checked": len(domain_legal),
                                            "violations": len(supported), "vacuous_domain_unsat": not domain_legal})
                else:
                    nonreported_checks.append({"side": side, "color": color,
                                               "support_witness": supported[0] if supported else None,
                                               "unsupported_but_not_reported": bool(domain_legal) and not supported,
                                               "domain_unsat": not domain_legal})
        row = {
            "id": record["id"], "family": record["family"], "domain_pattern": record["domain_pattern"],
            "edge_mask": record["edge_mask"], "endpoint_mask": record["endpoint_mask"],
            "excluded_color": record["excluded_color"], "relaxed_side": record["relaxed_side"],
            "side_count": len(sides), "edge_count": len(edges), "raw_document_sha256": _digest(document),
            "equal_names_sha256": _digest(equal_names), "domains_sha256": _digest(domains),
            "evidence_sha256": _digest(evidence), "literal_assignments_checked": len(assignments),
            "domain_assignment_universe": _domain_product_size(domains),
            "raw_legal_assignments": len(raw_legal), "domain_legal_assignments": len(domain_legal),
            "domain_legal_assignments_sha256": _digest(domain_legal),
            "raw_four_color_witness": raw_legal[0], "domain_legal_witness": domain_legal[0] if domain_legal else None,
            "domain_unsat": not domain_legal, "certificates": len(evidence["certificates"]),
            "certified_literal_deletions": len(deletion_checks),
            "nonvacuous_literal_deletions": sum(not check["vacuous_domain_unsat"] for check in deletion_checks),
            "vacuous_literal_deletions": sum(check["vacuous_domain_unsat"] for check in deletion_checks),
            "deletion_checks": deletion_checks, "nonreported_literal_checks": nonreported_checks,
            "missed_unsupported_literals": sum(check["unsupported_but_not_reported"] for check in nonreported_checks),
            "evidence": evidence,
        }
        if saved_rows is not None:
            _same(saved_rows[number], row, "saved finite case")
        rows.append(row)
    return rows


def _report(records, rows):
    """Separate preservation, effective deletions, vacuity, and missing inference."""
    return {
        "schema_version": 1, "version": VERSION, "passed": True,
        "scope": {
            "palette": [1, 2, 3, 4], "four_vertex_side_order": list(SIDES),
            "lifted_side_order": list(LIFT_SIDES), "base_edges": [list(edge) for edge in BASE_EDGES],
            "main_case_scope": "all 64 labeled four-vertex simple graphs times 21 domain patterns",
            "lift_scope": "eight five-vertex K4 quotient lifts: target t0=t1 and all three incident-edge endpoint choices",
            "domain_patterns": "4 triangle triples with full target, 12 single-triangle-vertex relaxations, 1 all-full, 4 all-triple",
            "assignment_scope": "all 4**n literal tuples per case, then original physical-edge, explicit-EQ, and domain filtering",
            "color_symmetry_reduction": False, "vertex_symmetry_reduction": False,
            "quotient_assignment_enumeration_substituted": False,
            "oracle_used": False, "propagation_used": False, "coloring_producer_used": False,
            "domain_premises": "explicit restrictions; not algorithm reachability or proof of production domain provenance",
            "raw_witness_scope": "original physical edges plus explicit EQ, before domain restrictions",
            "saved_check": "literal assignment enumeration and independent certificate coverage checker without detector",
            "boundary": "not all nonempty domains, general EQ partitions, lifted graph families, plane-map histories, reachable states, or completeness",
        },
        "case_count": len(rows), "distinct_raw_graphs": len({row["raw_document_sha256"] for row in rows}),
        "four_vertex_cases": sum(row["side_count"] == 4 for row in rows),
        "eq_lift_cases": sum(row["side_count"] == 5 for row in rows),
        "main_cases": sum(row["domain_pattern"] == "triangle-triple-target-full" for row in rows),
        "control_cases": sum(row["domain_pattern"] != "triangle-triple-target-full" for row in rows),
        "case_assignment_pairs": sum(row["literal_assignments_checked"] for row in rows),
        "domain_assignment_pairs": sum(row["domain_assignment_universe"] for row in rows),
        "positive_certificates": sum(row["certificates"] for row in rows),
        "cases_with_certificates": sum(row["certificates"] > 0 for row in rows),
        "nonvacuous_literal_deletions": sum(row["nonvacuous_literal_deletions"] for row in rows),
        "vacuous_literal_deletions": sum(row["vacuous_literal_deletions"] for row in rows),
        "domain_unsat_cases": sum(row["domain_unsat"] for row in rows),
        "domain_sat_cases": sum(not row["domain_unsat"] for row in rows),
        "raw_four_color_witnesses": sum(row["raw_four_color_witness"] is not None for row in rows),
        "missed_unsupported_literals": sum(row["missed_unsupported_literals"] for row in rows),
        "support_witnesses_for_undeleted_literals": sum(check["support_witness"] is not None for row in rows
                                                        for check in row["nonreported_literal_checks"]),
        "deletion_violations": sum(check["violations"] for row in rows for check in row["deletion_checks"]),
        "input_inventory_sha256": _digest(records), "per_case": rows, "per_case_sha256": _digest(rows),
    }


def check_rule_soundness():
    """Execute the complete declared census only after input and source freeze."""
    records = rule_inventory()
    return _report(records, _evaluate(records))


def check_saved_rule_soundness(report):
    """Re-enumerate original literal assignments without discovery or search."""
    records = rule_inventory()
    rows = _evaluate(records, report["per_case"])
    _same(report, _report(records, rows), "saved complete rule report")
    return {"passed": True, "case_count": len(rows),
            "case_assignment_pairs": sum(row["literal_assignments_checked"] for row in rows),
            "positive_certificates_checked": sum(row["certificates"] for row in rows),
            "literal_deletions_checked": sum(row["certified_literal_deletions"] for row in rows),
            "cases_without_certificates": sum(row["certificates"] == 0 for row in rows),
            "domain_unsat_cases": sum(row["domain_unsat"] for row in rows),
            "detector_runs": 0, "oracle_searches": 0, "coloring_producer_runs": 0}

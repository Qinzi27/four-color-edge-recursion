"""Exhaust declared four-vertex graph/domain cases using literal assignments.

All 64 labeled simple graphs are crossed with four common three-color domains,
16 single-vertex relaxations, and one all-four-color control. This checks the
implemented conditional equality rule, not all nonempty domain combinations,
reachable states, or algorithm completeness. Saved replay never runs discovery.
"""

from hashlib import sha256
from itertools import combinations, product
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.quaternary_conditional_diamond import find_conditional_diamonds
from scripts.check_quaternary_conditional_diamond import check_conditional_diamonds

VERSION = "quaternary-conditional-diamond-finite-soundness-v1"
SIDES = ("a", "b", "u", "v")
BASE_EDGES = tuple(combinations(range(4), 2))


def _require(condition, message):
    """Keep evidence checks active under optimized Python execution."""
    if not condition:
        raise AssertionError(message)


def _digest(value):
    """Hash literal JSON independently of detector utilities."""
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode("utf-8")).hexdigest()


def _same(actual, expected, label):
    """Reject extra keys, value changes, and bool/int type aliasing."""
    _require(json.dumps(actual, sort_keys=True, allow_nan=False) ==
             json.dumps(expected, sort_keys=True, allow_nan=False), label + " differs")


def _document(edges):
    """Use separator edges only; no learned relation enters a raw graph."""
    return {"sides": list(SIDES), "lines": [
        {"id": f"E{i}", "left": SIDES[a], "right": SIDES[b], "kind": "separator"}
        for i, (a, b) in enumerate(edges)]}


def _relations(domains, edges):
    """Build only unary Cartesian products and physical inequalities, without PC.

    The diagonal is literal identity restricted to each domain. Off-diagonal
    bit 4*(a-1)+(b-1) is allowed unless a physical edge requires a != b.
    """
    edge_set = {tuple(sorted(edge)) for edge in edges}
    matrix = []
    for i, first_domain in enumerate(domains):
        row = []
        for j, second_domain in enumerate(domains):
            mask = 0
            for first in first_domain:
                for second in second_domain:
                    if i == j and first != second:
                        continue
                    if tuple(sorted((i, j))) in edge_set and first == second:
                        continue
                    mask |= 1 << (4 * (first - 1) + second - 1)
            row.append(mask)
        matrix.append(row)
    return matrix


def rule_inventory():
    """Declare all 1,344 cases before any detector or truth-table evaluation."""
    records = []
    for mask in range(64):
        edges = [edge for bit, edge in enumerate(BASE_EDGES) if mask & (1 << bit)]
        document = _document(edges)
        for excluded in range(1, 5):
            domains = [[color for color in range(1, 5) if color != excluded] for _ in SIDES]
            records.append({"id": f"diamond-mask-{mask:02x}-omit-{excluded}",
                            "family": "all-four-vertex-simple-graphs-common-triple",
                            "edge_mask": mask, "excluded_color": excluded,
                            "relaxed_side": None, "document": document,
                            "domains": domains, "relations": _relations(domains, edges)})
        for relaxed, side in enumerate(SIDES):
            for excluded in range(1, 5):
                domains = [[color for color in range(1, 5) if color != excluded] for _ in SIDES]
                domains[relaxed] = [1, 2, 3, 4]
                records.append({"id": f"diamond-mask-{mask:02x}-relax-{side}-omit-{excluded}",
                                "family": "one-vertex-relaxed-control", "edge_mask": mask,
                                "excluded_color": excluded, "relaxed_side": side,
                                "document": document, "domains": domains,
                                "relations": _relations(domains, edges)})
        domains = [[1, 2, 3, 4] for _ in SIDES]
        records.append({"id": f"diamond-mask-{mask:02x}-four-colors",
                        "family": "all-four-color-control", "edge_mask": mask,
                        "excluded_color": None, "relaxed_side": None,
                        "document": document, "domains": domains,
                        "relations": _relations(domains, edges)})
    return records


def _domain_product_size(domains):
    """Count domain tuples before raw edge filtering."""
    total = 1
    for domain in domains:
        total *= len(domain)
    return total


def _evaluate(records, saved_rows=None):
    """Independently enumerate legality and every reported equality's effect.

    Full 4**4 tuples are visited per case. Reusing the assignment table and raw
    edge legality across a graph's domain cases does not reduce the denominator.
    A missing equality is never called wrong: save an unequal witness when one
    exists, and otherwise distinguish logical entailment from domain UNSAT.
    """
    _require(saved_rows is None or len(saved_rows) == len(records), "saved finite case coverage differs")
    assignments = list(product((1, 2, 3, 4), repeat=4))
    raw_cache, rows = {}, []
    for number, record in enumerate(records):
        document, domains, relations = record["document"], record["domains"], record["relations"]
        edges = [(SIDES.index(line["left"]), SIDES.index(line["right"]))
                 for line in document["lines"]]
        graph_key = tuple(edges)
        if graph_key not in raw_cache:
            raw_cache[graph_key] = [all(values[a] != values[b] for a, b in edges)
                                    for values in assignments]
        raw_legal, domain_legal = [], []
        for values, valid in zip(assignments, raw_cache[graph_key]):
            if valid:
                raw_legal.append(list(values))
                if all(value in domain for value, domain in zip(values, domains)):
                    domain_legal.append(list(values))
        _require(raw_legal, "declared raw graph has no four-color witness")
        evidence = (find_conditional_diamonds(document, domains, relations) if saved_rows is None
                    else saved_rows[number]["evidence"])
        checked = check_conditional_diamonds(document, domains, relations, evidence)
        _require(checked["passed"], "independent diamond audit failed")
        reported = {tuple(SIDES.index(side) for side in certificate["pair"])
                    for certificate in evidence["certificates"]}
        equality_checks, nonreported_checks = [], []
        for first, second in BASE_EDGES:
            unequal = [values for values in domain_legal if values[first] != values[second]]
            pair = [SIDES[first], SIDES[second]]
            if (first, second) in reported:
                _require(not unequal, "a certified equality removed a domain-legal raw coloring")
                equality_checks.append({"pair": pair, "legal_assignments_checked": len(domain_legal),
                                        "violations": len(unequal), "vacuous_domain_unsat": not domain_legal})
            else:
                nonreported_checks.append({"pair": pair, "unequal_witness": unequal[0] if unequal else None,
                                           "entailed_but_not_reported": bool(domain_legal) and not unequal,
                                           "domain_unsat": not domain_legal})
        row = {
            "id": record["id"], "family": record["family"], "edge_mask": record["edge_mask"],
            "excluded_color": record["excluded_color"], "relaxed_side": record["relaxed_side"],
            "side_count": 4, "edge_count": len(edges), "raw_document_sha256": _digest(document),
            "domains_sha256": _digest(domains), "relations_sha256": _digest(relations),
            "evidence_sha256": _digest(evidence), "literal_assignments_checked": len(assignments),
            "domain_assignment_universe": _domain_product_size(domains),
            "raw_legal_assignments": len(raw_legal), "domain_legal_assignments": len(domain_legal),
            "domain_legal_assignments_sha256": _digest(domain_legal),
            "raw_four_color_witness": raw_legal[0], "domain_legal_witness": domain_legal[0] if domain_legal else None,
            "domain_unsat": not domain_legal, "certified_equalities": len(equality_checks),
            "nonvacuous_equalities": sum(not check["vacuous_domain_unsat"] for check in equality_checks),
            "vacuous_equalities": sum(check["vacuous_domain_unsat"] for check in equality_checks),
            "equality_checks": equality_checks, "nonreported_pair_checks": nonreported_checks,
            "missed_entailed_equalities": sum(check["entailed_but_not_reported"] for check in nonreported_checks),
            "evidence": evidence,
        }
        if saved_rows is not None:
            _same(saved_rows[number], row, "saved finite case")
        rows.append(row)
    return rows


def _report(records, rows):
    """Separate finite preservation from effectiveness and missing inference."""
    return {
        "schema_version": 1, "version": VERSION, "passed": True,
        "scope": {
            "side_order": list(SIDES), "palette": [1, 2, 3, 4],
            "base_edges": [list(edge) for edge in BASE_EDGES],
            "main_case_scope": "all 64 labeled four-vertex simple graphs times four common excluded colors",
            "controls": "each graph times four relaxed vertices times four excluded colors, plus all-four-color domains",
            "assignment_scope": "all 256 literal four-color tuples per case, then domain and raw-edge filtering",
            "initial_relations": "domain Cartesian products, exact identity diagonals, and direct physical NEQ only; no PC",
            "color_symmetry_reduction": False, "vertex_symmetry_reduction": False,
            "oracle_used": False, "propagation_used": False, "coloring_producer_used": False,
            "domain_premises": "explicit restrictions, not claims of algorithm reachability; production derivations audited separately",
            "saved_check": "literal assignment enumeration and independent certificate/absence checking without detector",
            "boundary": "not all nonempty domains, general derived matrices, plane-map histories, reachable states, or completeness",
        },
        "case_count": len(rows), "distinct_raw_graphs": len({row["raw_document_sha256"] for row in rows}),
        "main_cases": sum(row["family"] == "all-four-vertex-simple-graphs-common-triple" for row in rows),
        "control_cases": sum(row["family"] != "all-four-vertex-simple-graphs-common-triple" for row in rows),
        "case_assignment_pairs": sum(row["literal_assignments_checked"] for row in rows),
        "domain_assignment_pairs": sum(row["domain_assignment_universe"] for row in rows),
        "positive_certificates": sum(row["certified_equalities"] for row in rows),
        "cases_with_certificates": sum(row["certified_equalities"] > 0 for row in rows),
        "nonvacuous_equalities": sum(row["nonvacuous_equalities"] for row in rows),
        "vacuous_equalities": sum(row["vacuous_equalities"] for row in rows),
        "domain_unsat_cases": sum(row["domain_unsat"] for row in rows),
        "domain_sat_cases": sum(not row["domain_unsat"] for row in rows),
        "raw_four_color_witnesses": sum(row["raw_four_color_witness"] is not None for row in rows),
        "missed_entailed_equalities": sum(row["missed_entailed_equalities"] for row in rows),
        "unequal_counterexample_witnesses": sum(check["unequal_witness"] is not None for row in rows
                                               for check in row["nonreported_pair_checks"]),
        "equality_violations": sum(check["violations"] for row in rows for check in row["equality_checks"]),
        "input_inventory_sha256": _digest(records), "per_case": rows, "per_case_sha256": _digest(rows),
    }


def check_rule_soundness():
    """Run the complete declared census only after inputs and source freeze."""
    records = rule_inventory()
    return _report(records, _evaluate(records))


def check_saved_rule_soundness(report):
    """Re-enumerate saved cases, never calling discovery or exact search."""
    records = rule_inventory()
    rows = _evaluate(records, report["per_case"])
    _same(report, _report(records, rows), "saved complete rule report")
    return {"passed": True, "case_count": len(rows),
            "case_assignment_pairs": sum(row["literal_assignments_checked"] for row in rows),
            "positive_certificates_checked": sum(row["certified_equalities"] for row in rows),
            "cases_without_certificates": sum(row["certified_equalities"] == 0 for row in rows),
            "domain_unsat_cases": sum(row["domain_unsat"] for row in rows),
            "detector_runs": 0, "oracle_searches": 0, "coloring_producer_runs": 0}

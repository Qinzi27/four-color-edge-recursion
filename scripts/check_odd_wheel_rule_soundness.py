"""Exhaust a declared physical wheel family against literal color assignments.

The main census is all 1,024 labeled edge subsets of a five-rim wheel, crossed
with each of four omitted colors. Each case checks all 4**6 assignments; the
three-color domain test is separate from raw-edge legality. Controls relax
one vertex or use an even rim. This is not all six-vertex graphs or all domains.
"""

from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.quaternary_odd_wheel import find_odd_wheel
from scripts.check_quaternary_odd_wheel import check_odd_wheel

VERSION = "quaternary-odd-wheel-finite-soundness-v1"
SIDES = ("center", "r0", "r1", "r2", "r3", "r4")
BASE_EDGES = tuple(sorted([(0, i) for i in range(1, 6)] +
                          [tuple(sorted((i, 1 + i % 5))) for i in range(1, 6)]))


def _require(condition, message):
    """Retain evidence checks when Python optimization is enabled."""
    if not condition:
        raise AssertionError(message)


def _digest(value):
    """Hash canonical JSON, independently of the detector helper."""
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode("utf-8")).hexdigest()


def _same(actual, expected, label):
    """Reject changed values, extra fields, and bool/int aliasing."""
    _require(json.dumps(actual, sort_keys=True, allow_nan=False) ==
             json.dumps(expected, sort_keys=True, allow_nan=False), label + " differs")


def _document(sides, edges):
    """Encode actual shared-boundary inequalities only, without fake contacts."""
    return {"sides": list(sides), "lines": [
        {"id": f"E{i}", "left": sides[a], "right": sides[b], "kind": "separator"}
        for i, (a, b) in enumerate(edges)]}


def rule_inventory():
    """Declare all edge masks, omitted colors and SAT controls without search."""
    records = []
    for mask in range(1 << len(BASE_EDGES)):
        edges = [edge for bit, edge in enumerate(BASE_EDGES) if mask & (1 << bit)]
        for excluded in range(1, 5):
            palette = [color for color in range(1, 5) if color != excluded]
            records.append({"id": f"wheel5-mask-{mask:03x}-omit-{excluded}",
                            "family": "all-wheel5-edge-subgraphs", "edge_mask": mask,
                            "excluded_color": excluded, "relaxed_side": None,
                            "document": _document(SIDES, edges),
                            "domains": [list(palette) for _ in SIDES]})
    even_sides = ("center", *(f"r{i}" for i in range(6)))
    even_edges = sorted([(0, i) for i in range(1, 7)] +
                        [tuple(sorted((i, 1 + i % 6))) for i in range(1, 7)])
    for excluded in range(1, 5):
        palette = [color for color in range(1, 5) if color != excluded]
        records.append({"id": f"wheel6-even-omit-{excluded}",
                        "family": "even-rim-control", "edge_mask": None,
                        "excluded_color": excluded, "relaxed_side": None,
                        "document": _document(even_sides, even_edges),
                        "domains": [list(palette) for _ in even_sides]})
        for index, side in enumerate(SIDES):
            domains = [list(palette) for _ in SIDES]
            domains[index] = [1, 2, 3, 4]
            records.append({"id": f"wheel5-relax-{side}-omit-{excluded}",
                            "family": "one-vertex-relaxed-control", "edge_mask": 1023,
                            "excluded_color": excluded, "relaxed_side": side,
                            "document": _document(SIDES, BASE_EDGES), "domains": domains})
    return records


def _evaluate(records, saved_rows=None):
    """Enumerate raw and domain legality; subsets are unit fixtures only.

    Exact assignment tables and raw-legality masks are shared for repeated raw
    graphs. Every case still traverses its entire literal assignment universe.
    Saved verification never invokes the detector, propagation or an oracle.
    """
    _require(saved_rows is None or len(saved_rows) == len(records),
             "saved finite case coverage differs")
    assignment_cache, raw_cache, rows = {}, {}, []
    for number, record in enumerate(records):
        document, domains = record["document"], record["domains"]
        sides = document["sides"]
        count = len(sides)
        if count not in assignment_cache:
            assignment_cache[count] = list(product((1, 2, 3, 4), repeat=count))
        assignments = assignment_cache[count]
        edges = [(sides.index(line["left"]), sides.index(line["right"]))
                 for line in document["lines"]]
        key = (count, tuple(edges))
        if key not in raw_cache:
            raw_cache[key] = [all(values[a] != values[b] for a, b in edges)
                              for values in assignments]
        raw_legality = raw_cache[key]
        domain_legal, raw_legal_count, raw_witness = [], 0, None
        for values, raw_legal in zip(assignments, raw_legality):
            if raw_legal:
                raw_legal_count += 1
                if raw_witness is None:
                    raw_witness = list(values)
                if all(value in domain for value, domain in zip(values, domains)):
                    domain_legal.append(list(values))
        evidence = (find_odd_wheel(document, domains) if saved_rows is None
                    else saved_rows[number]["evidence"])
        checked = check_odd_wheel(document, domains, evidence)
        _require(checked["passed"], "independent wheel audit failed")
        found = evidence["certificate"] is not None
        _require(not found or not domain_legal,
                 "wheel conflict removed a domain-legal complete raw coloring")
        # Raw witnesses make positive controls nonvacuous: only the restrictions
        # are inconsistent, not the original four-colorable graph.
        _require(raw_witness is not None, "declared raw graph has no four-color witness")
        row = {"id": record["id"], "family": record["family"],
               "edge_mask": record["edge_mask"], "excluded_color": record["excluded_color"],
               "relaxed_side": record["relaxed_side"], "side_count": count,
               "edge_count": len(edges), "raw_document_sha256": _digest(document),
               "domains_sha256": _digest(domains), "evidence_sha256": _digest(evidence),
               "literal_assignments_checked": len(assignments),
               "domain_assignment_universe": _domain_product_size(domains),
               "raw_legal_assignments": raw_legal_count,
               "domain_legal_assignments": len(domain_legal),
               "domain_legal_assignments_sha256": _digest(domain_legal),
               "raw_four_color_witness": raw_witness,
               "domain_legal_witness": domain_legal[0] if domain_legal else None,
               "conflict_certified": found, "missed_domain_unsat": not found and not domain_legal,
               "evidence": evidence}
        if saved_rows is not None:
            _same(saved_rows[number], row, "saved finite case")
        rows.append(row)
    return rows


def _domain_product_size(domains):
    """Count literal tuples allowed by domains before checking physical edges."""
    count = 1
    for domain in domains:
        count *= len(domain)
    return count


def _report(records, rows):
    """Keep implementation soundness, missed cases and finite scope separate."""
    return {"schema_version": 1, "version": VERSION, "passed": True,
            "scope": {"main_side_order": list(SIDES), "palette": [1, 2, 3, 4],
                      "base_edges": [list(edge) for edge in BASE_EDGES],
                      "main_case_scope": "1024 labeled edge subsets of one five-rim wheel times four common excluded colors",
                      "controls": "four even six-rim controls and 24 single-vertex domain relaxations",
                      "assignment_scope": "all literal four-color tuples for each case, then domain and raw-edge filtering",
                      "color_symmetry_reduction": False, "vertex_symmetry_reduction": False,
                      "oracle_used": False, "propagation_used": False, "coloring_producer_used": False,
                      "domain_premises": "explicit test restrictions; their derivation in actual algorithm states is separately audited",
                      "saved_check": "re-enumerate assignments and independently check saved certificate or absence without detector",
                      "boundary": "not all graphs, all domain restrictions, plane-map histories, reachable algorithm states, or algorithm completeness"},
            "case_count": len(rows),
            "distinct_raw_graphs": len({row["raw_document_sha256"] for row in rows}),
            "main_cases": sum(row["family"] == "all-wheel5-edge-subgraphs" for row in rows),
            "control_cases": sum(row["family"] != "all-wheel5-edge-subgraphs" for row in rows),
            "case_assignment_pairs": sum(row["literal_assignments_checked"] for row in rows),
            "domain_assignment_pairs": sum(row["domain_assignment_universe"] for row in rows),
            "positive_certificates": sum(row["conflict_certified"] for row in rows),
            "negative_domain_witnesses": sum(row["domain_legal_witness"] is not None for row in rows),
            "raw_four_color_witnesses": sum(row["raw_four_color_witness"] is not None for row in rows),
            "missed_domain_unsat": sum(row["missed_domain_unsat"] for row in rows),
            "input_inventory_sha256": _digest(records), "per_case": rows,
            "per_case_sha256": _digest(rows)}


def check_rule_soundness():
    """Run the full declared census only after sources and inputs are frozen."""
    records = rule_inventory()
    return _report(records, _evaluate(records))


def check_saved_rule_soundness(report):
    """Replay every saved rule case without rerunning discovery or search."""
    records = rule_inventory()
    rows = _evaluate(records, report["per_case"])
    _same(report, _report(records, rows), "saved complete rule report")
    return {"passed": True, "case_count": len(rows),
            "case_assignment_pairs": sum(row["literal_assignments_checked"] for row in rows),
            "positive_certificates_checked": sum(row["conflict_certified"] for row in rows),
            "absence_checks": sum(not row["conflict_certified"] for row in rows),
            "detector_runs": 0, "oracle_searches": 0, "coloring_producer_runs": 0}

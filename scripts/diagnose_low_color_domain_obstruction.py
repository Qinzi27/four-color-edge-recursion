"""Preserve an external-domain obstruction outside the frozen geometry corpus.

This post-design diagnostic neither changes the low-color policy nor establishes
reachability from its one-anchor/two-anchor geometric initializations. It uses
the abstract input-order schedule and two explicitly supplied candidate sets.
The full Cartesian product is enumerated after the producer finishes; no exact
solver or enumerated assignment feeds back into the producer.
"""

from argparse import ArgumentParser
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_quaternary_geometry import audit_bounded_contacts
from scripts.quaternary_low_color import solve_low_color


def require(condition, message):
    """Keep diagnostic failures visible when Python runs with optimization."""
    if not condition:
        raise AssertionError(message)


def same(actual, expected, message):
    """Compare JSON evidence without conflating booleans and integer colors."""
    require(json.dumps(actual, sort_keys=True, allow_nan=False)
            == json.dumps(expected, sort_keys=True, allow_nan=False), message)


def source_hashes():
    """Bind this script and every actually imported local Python dependency."""
    names = {Path(__file__).resolve()}
    for module in list(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if filename:
            path = Path(filename).resolve()
            if path.is_relative_to(ROOT) and path.suffix == ".py":
                names.add(path)
    return {path.relative_to(ROOT).as_posix(): sha256(path.read_bytes()).hexdigest()
            for path in sorted(names)}


def obstruction_document():
    """Use K5 minus A--E: BCD is a triangle and A/E touch all three vertices."""
    edges = [("B", "C"), ("B", "D"), ("C", "D")]
    edges += [(apex, base) for apex in ("A", "E") for base in ("B", "C", "D")]
    return {"sides": ["A", "B", "C", "D", "E"],
            "lines": [{"id": f"E{i}", "left": a, "right": b, "kind": "separator"}
                      for i, (a, b) in enumerate(edges)],
            "anchors": {}, "states": {"A": "1100", "E": "0111"}}


def unary_allows(document, assignment):
    """Read original literal digits directly, independently of NameState."""
    return (all(assignment[side] == color for side, color in document.get("anchors", {}).items())
            and all(word[assignment[side] - 1] != "0"
                    for side, word in document.get("states", {}).items()))


def enumerate_document(document):
    """Visit all 4**5 assignments with no symmetry quotient or SAT oracle."""
    count, unary_count, legal = 0, 0, []
    for values in product((1, 2, 3, 4), repeat=len(document["sides"])):
        count += 1
        assignment = dict(zip(document["sides"], values))
        if not unary_allows(document, assignment):
            continue
        unary_count += 1
        if (all(assignment[line["left"]] != assignment[line["right"]]
                for line in document["lines"] if line["kind"] == "separator")
                and all(assignment[a] == assignment[b] for a, b in document.get("equal_names", []))):
            legal.append(assignment)
    return {"cartesian_assignments_checked": count,
            "assignments_satisfying_unary_inputs": unary_count,
            "legal_assignment_count": len(legal), "legal_assignments": legal}


def filter_commitments(assignments, commitments):
    """Filter the ORIGINAL complete legal set only by actual/trial commitments."""
    return [assignment for assignment in assignments
            if all(assignment[side] == name for side, name in commitments.items())]


def check_projections(outcome, assignments):
    """Check every complete solution against initial, changed and final pairs.

    The separately reused auditor verifies each trace's premises/composition.
    Here literal complete solutions must retain their projections through every
    changed pair as well, rather than using final completion as a substitute.
    """
    checks = 0
    sides = outcome["side_order"]
    for assignment in assignments:
        values = [assignment[side] for side in sides]
        for matrix in (outcome["initial_relations"], outcome["relations"]):
            for i, a in enumerate(values):
                for j, b in enumerate(values):
                    require(matrix[i][j] & (1 << (4 * (a - 1) + b - 1)),
                            "complete solution projection was removed")
                    checks += 1
        for step in outcome["trace"]:
            a, b = values[step["i"]], values[step["j"]]
            require(step["after"] & (1 << (4 * (a - 1) + b - 1)),
                    "trace removed a complete solution projection")
            checks += 1
        require(all(value in outcome["domains"][i] for i, value in enumerate(values)),
                "final domain removed a complete solution")
    return {"passed": True, "complete_solutions_checked": len(assignments),
            "pair_projection_checks": checks,
            "empty_solution_set_checks_are_vacuous": not bool(assignments)}


def audit_diagnostic(document, result):
    """Replay the wrapper transitions and independently enumerate every phase."""
    same(result["original_input"], document, "original input changed")
    require(result["probe"] is True and result["schedule"] == "first-unresolved-input-order-v1",
            "diagnostic requires guarded abstract input-order scheduling")
    initial = enumerate_document(document)
    originals = initial["legal_assignments"]
    require(initial["cartesian_assignments_checked"] == 1024 and len(originals) == 6,
            "unexpected original exhaustive domain result")
    phases, event_checks, phase_checks = result["phases"], [], []
    commitments, work, current, next_index = {}, deepcopy(document), 0, 1

    def phase_check(index, expected_document, expected_kind, expected_solutions):
        """Reject injected restrictions and confirm all original solutions survive."""
        phase = phases[index]
        same(phase["document"], expected_document, "phase document transition differs")
        require(phase["kind"] == expected_kind, "phase kind differs")
        bounded = audit_bounded_contacts(phase["document"], phase["outcome"])
        exhaustive = enumerate_document(phase["document"])
        same(exhaustive["legal_assignments"], expected_solutions,
             "phase restrictions changed the original commitment-filtered legal set")
        projections = check_projections(phase["outcome"], expected_solutions)
        phase_checks.append({"phase": index, "kind": expected_kind,
                             "bounded_trace_audit": bounded, "full_enumeration": exhaustive,
                             "complete_assignment_projection_preservation": projections})
        return exhaustive["legal_assignments"]

    phase_check(0, work, "main", originals)
    for event_index, event in enumerate(result["events"]):
        require(event["before_phase"] == current, "event has wrong persistent starting phase")
        side, symbol = event["side"], event["symbol"]
        before = filter_commitments(originals, commitments)
        domains = phases[current]["outcome"]["domains"]
        index = next(i for i, domain in enumerate(domains) if len(domain) > 1)
        require(side == document["sides"][index] and symbol == min(domains[index]),
                "event violates input-order or low-name preference")
        same(event["candidates_before"], domains[index], "candidate record differs")
        trial_document, trial_commitments = deepcopy(work), dict(commitments)
        trial_document.setdefault("anchors", {})[side] = symbol
        trial_commitments[side] = symbol
        trial_solutions = filter_commitments(originals, trial_commitments)
        require(event["trial_phase"] == next_index, "trial phase is not sequential")
        phase_check(next_index, trial_document, "trial", trial_solutions)
        trial_index = next_index
        next_index += 1
        if event["kind"] == "reject":
            require(phases[trial_index]["outcome"]["status"] == "conflict"
                    and not trial_solutions and event["extension_claim"] == "refuted",
                    "rejection lacks both trace refutation and exhaustive confirmation")
            retained = [name for name in domains[index] if name != symbol]
            marker = "2" if len(retained) == 1 else "1"
            work.setdefault("states", {})[side] = "".join(
                marker if name in retained else "0" for name in (1, 2, 3, 4))
            require(event["after_phase"] == next_index, "rejection main phase is not sequential")
            phase_check(next_index, work, "main", before)
            current, next_index = next_index, next_index + 1
            after = before
        else:
            require(event["kind"] == "commit" and event["after_phase"] == trial_index
                    and phases[trial_index]["outcome"]["status"] != "conflict",
                    "unexpected accepted trial")
            claim = ("complete-witness" if phases[trial_index]["outcome"]["status"] == "solved"
                     else "inconclusive")
            require(event["extension_claim"] == claim, "accepted trial overstates its evidence")
            work, commitments, current = trial_document, trial_commitments, trial_index
            after = trial_solutions
        event_checks.append({"event": event_index, "kind": event["kind"], "side": side,
                             "symbol": symbol, "before_legal_assignment_count": len(before),
                             "before_legal_assignments": before,
                             "after_legal_assignment_count": len(after), "after_legal_assignments": after,
                             "trial_legal_assignment_count": len(trial_solutions),
                             "trial_legal_assignments": trial_solutions,
                             "unsafe_commit": event["kind"] == "commit" and bool(before) and not after})
    require(next_index == len(phases) and result["final_phase"] == current,
            "phase coverage is incomplete")
    unsafe = [event for event in event_checks if event["unsafe_commit"]]
    require(len(unsafe) == 1 and unsafe[0]["event"] == 0
            and unsafe[0]["side"] == "A" and unsafe[0]["symbol"] == 1,
            "expected first unsafe commit not confirmed")
    require(result["status"] == "conflict" and result["colors"] is None
            and result["backtracks"] == 0 and result["oracle_feedback_to_producer"] is False,
            "unexpected final producer classification")
    return {"passed": True, "initial_enumeration": initial, "phases": phase_checks,
            "events": event_checks, "first_unsafe_commit": unsafe[0],
            "all_phase_documents_and_solution_projections_checked": True,
            "trace_steps_independently_checked": sum(
                phase["bounded_trace_audit"]["trace_steps_checked"] for phase in phase_checks),
            "total_cartesian_assignments_checked": sum(
                phase["full_enumeration"]["cartesian_assignments_checked"] for phase in phase_checks),
            "exact_oracle_called": False, "oracle_feedback_to_producer": False}


def diagnose():
    """Produce a complete reproducible development diagnostic, never a rescue."""
    sources = source_hashes()
    document = obstruction_document()
    result = solve_low_color(document, probe=True, decision_limit=128, probe_limit=512)
    audit = audit_diagnostic(document, result)  # All enumeration is posterior.
    same(source_hashes(), sources, "source dependencies changed during diagnosis")
    return {"schema_version": 1, "diagnostic_version": "low-color-external-domain-obstruction-v1",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "diagnostic_status": "expected-unsafe-commit-confirmed", "audit_passed": True,
            "source_sha256": sources, "original_input": document, "result": result, "audit": audit,
            "enumeration_scope": {"side_count": 5, "palette": [1, 2, 3, 4],
                "cartesian_assignments_per_phase": 1024, "symmetry_quotient": False,
                "sampling": False, "all_initial_legal_assignments_saved": True},
            "mathematical_explanation": [
                "BCD is a triangle, so its three names are distinct. A and E both touch all of BCD "
                "and therefore must share the remaining fourth name in every complete coloring.",
                "Input A in {1,2} and E in {2,3,4} consequently force A=E=2. The six solutions "
                "are all permutations of {1,3,4} on B,C,D.",
                "After A=1, B,C,D,E form K4 with only {2,3,4}. There is no complete coloring, "
                "but each unequal pair has a third-name support, so path consistency can survive.",
                "The contact graph is planar: place A on one side of triangle BCD and E on its "
                "other side on the sphere, connecting each apex to all triangle vertices. "
                "This triangular-bipyramid construction is a planarity argument, not an exported drawing."],
            "scope": {"formal_geometry_experiment": False, "post_design_development_diagnostic": True,
                "external_domain_restrictions": {"A": [1, 2], "E": [2, 3, 4]},
                "schedule": "first-unresolved-input-order-v1", "geometry_adapter_input": False,
                "one_anchor_initialization_reachability": "not_established",
                "two_anchor_initialization_reachability": "not_established",
                "mother_peer_geometric_history_reachability": "not_established",
                "no_changes_to_frozen_policy_or_corpus": True,
                "claim": "Conditional path-consistency survival does not certify safe extension "
                         "for arbitrary supplied candidate domains; this does not refute the "
                         "current formally tested geometric initialization and reachable-state scope."}}


def main():
    """Write one new artifact exclusively; reruns must select a fresh filename."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="outputs/quaternary-low-color-domain-obstruction-2026-09-22.json")
    args = parser.parse_args()
    target = Path(args.output)
    if not target.is_absolute():
        target = ROOT / target
    if target.exists():
        raise FileExistsError("diagnostic output already exists; choose a new --output path")
    report = diagnose()
    with target.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"output": args.output, "audit_passed": report["audit_passed"],
                      "producer_status": report["result"]["status"],
                      "initial_solutions": report["audit"]["initial_enumeration"]["legal_assignment_count"],
                      "first_commit_solutions": report["audit"]["first_unsafe_commit"]["after_legal_assignment_count"],
                      "phases_checked": len(report["audit"]["phases"]),
                      "sources_bound": len(report["source_sha256"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()

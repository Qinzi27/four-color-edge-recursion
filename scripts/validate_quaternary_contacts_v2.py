"""Strengthen contact metadata checks without changing the frozen v1 model.

The finite inventory and the independent mathematical checker are reused from
v1. This new audit adds strict literal-state, anchor-provenance, directed-line
identity and bounded-matrix checks. It does not import the producer's state
encoder to validate itself, and it does not monkeypatch either version.

The relation trace is retained but NOT replayed step by step. Checked claims
are canonical metadata, exact initial constraints, initial-to-final shrinking,
the final fixed point and preservation of complete literal assignments.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from itertools import product
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.quaternary_contact_model import propagate_contacts
from scripts.validate_global_restart import digest, write_report
from scripts.validate_quaternary_contacts import (
    EXAMPLES, audit_document as audit_mathematics, build_inventory, document_for,
    read_report, reference_input, sources as v1_sources,
)


AUDIT_VERSION = "quaternary-contact-metadata-audit-v2"
SUPPLEMENT = "docs/QUATERNARY_CONTACT_AUDIT_V2-2026-09-21.md"
AUDIT_SCOPE = {
    "metadata": "independent canonical state words, literal anchors and their sources, masks, identities and echoes",
    "mathematics": "unchanged v1 complete-assignment preservation and independent set-relation final closure",
    "matrix": "strict 16-bit shape/types, diagonals, transposes, exact raw initial constraints and final subset",
    "trace": "not_replayed; no claim of independent validation of every intermediate trace step",
}


def require(condition, message):
    """Keep evidence rejection active under python -O."""
    if not condition:
        raise AssertionError(message)


def parse_state_word(word):
    """Decode input state semantics independently of the producer's NameState."""
    require(isinstance(word, str) and len(word) == 4 and all(c in "0123" for c in word),
            "state word must have exactly four base-four digits")
    nonzero = [c for c in word if c != "0"]
    require(not nonzero or (len(nonzero) == 1 and nonzero[0] in "23")
            or (len(nonzero) >= 2 and set(nonzero) == {"1"}),
            "state word has noncanonical candidate/derived/anchor markers")
    return [color for color, marker in enumerate(word, 1) if marker != "0"], "3" in word


def expected_state(domain, explicit_anchor):
    """Construct the expected six metadata fields using literal digits only.

    Contradictory restrictions produce 0000 and anchored=False, while their
    explicit source records remain present. An input singleton marked 2 is a
    supplied restriction, not an explicit anchor or a newly proved theorem.
    """
    anchored = bool(explicit_anchor) and bool(domain)
    marker = "3" if anchored else "2" if len(domain) == 1 else "1"
    word = "".join(marker if color in domain else "0" for color in (1, 2, 3, 4))
    return {"code": int(word, 4), "quaternary": word, "candidates": list(domain),
            "candidate_mask": sum(2 ** (color - 1) for color in domain),
            "representative": min(domain) if domain else None, "anchored": anchored}


def raw_metadata(document):
    """Check the input language and derive ordered explicit-anchor provenance."""
    require(isinstance(document, dict)
            and {"sides", "lines"} <= set(document)
            and set(document) <= {"sides", "lines", "anchors", "states", "point_contacts", "equal_names"},
            "unexpected contact-document fields")
    sides = document["sides"]
    require(isinstance(sides, list) and bool(sides)
            and all(isinstance(s, str) and bool(s.strip()) for s in sides)
            and len(set(sides)) == len(sides), "invalid or repeated side identities")
    known = set(sides)
    valid_side = lambda value: isinstance(value, str) and value in known
    anchors, states = document.get("anchors", {}), document.get("states", {})
    require(isinstance(anchors, dict) and isinstance(states, dict), "anchors/states must be objects")
    require(all(valid_side(side) and type(color) is int and color in (1, 2, 3, 4)
                for side, color in anchors.items()), "invalid raw explicit anchor")
    require(all(valid_side(side) for side in states), "state has unknown side")
    source_records, domains = {}, []
    for side in sides:
        domain, supplied_anchor = parse_state_word(states.get(side, "1111"))
        records = ([{"source": "states", "name": domain[0]}] if supplied_anchor else [])
        if side in anchors:
            records.append({"source": "anchors", "name": anchors[side]})
            domain = [color for color in domain if color == anchors[side]]
        source_records[side] = records
        domains.append(domain)
    lines = document["lines"]
    require(isinstance(lines, list), "lines must be an array")
    line_ids = set()
    for line in lines:
        require(isinstance(line, dict) and set(line) == {"id", "left", "right", "kind"},
                "invalid raw line fields")
        identifier = line["id"]
        require(isinstance(identifier, str) and bool(identifier.strip()) and identifier not in line_ids,
                "invalid or repeated line identity")
        line_ids.add(identifier)
        require(valid_side(line["left"]) and valid_side(line["right"])
                and line["kind"] in ("separator", "bridge"), "invalid raw line contact")
        require((line["left"] == line["right"]) == (line["kind"] == "bridge"),
                "bridge and separator side-identity semantics differ")
    contacts, equalities = document.get("point_contacts", []), document.get("equal_names", [])
    require(isinstance(contacts, list) and isinstance(equalities, list), "contact/EQ arrays required")
    for contact in contacts:
        require(isinstance(contact, dict) and set(contact) == {"sides"}
                and isinstance(contact["sides"], list) and len(contact["sides"]) == 2
                and all(valid_side(s) for s in contact["sides"]), "invalid point contact")
    for pair in equalities:
        require(isinstance(pair, list) and len(pair) == 2 and all(valid_side(s) for s in pair),
                "invalid logical equality")
    return sides, domains, source_records


def check_domains(domains, n, label):
    """Reject booleans, duplicates and reordered candidate metadata."""
    require(isinstance(domains, list) and len(domains) == n, label + " has wrong shape")
    for domain in domains:
        require(isinstance(domain, list)
                and all(type(c) is int and c in (1, 2, 3, 4) for c in domain)
                and domain == sorted(set(domain)), label + " has invalid names")


def check_matrix(matrix, n, label):
    """Check width, symmetry of direction reversal and diagonal identities."""
    require(isinstance(matrix, list) and len(matrix) == n
            and all(isinstance(row, list) and len(row) == n for row in matrix),
            label + " has wrong square shape")
    require(all(type(mask) is int and 0 <= mask < 65536 for row in matrix for mask in row),
            label + " must contain literal 16-bit integers, excluding bools")
    for i in range(n):
        require(matrix[i][i] & ~0x8421 == 0, label + " contains a nondiagonal self relation")
        for j in range(n):
            # Explicit source/destination bit positions, not producer transpose.
            reverse = sum(1 << (4 * b + a) for a, b in product(range(4), repeat=2)
                          if matrix[i][j] & (1 << (4 * a + b)))
            require(matrix[j][i] == reverse, label + " violates directed transpose consistency")


def check_state(item, expected, label):
    """Validate types before equality so Python True cannot impersonate 1."""
    require(isinstance(item, dict) and set(item) == set(expected), label + " has wrong fields")
    require(type(item["code"]) is int and type(item["candidate_mask"]) is int
            and type(item["anchored"]) is bool,
            label + " has invalid code, candidate-mask or anchored types")
    require(item["representative"] is None or type(item["representative"]) is int,
            label + " representative must not be bool")
    check_domains([item["candidates"]], 1, label + " candidates")
    parse_state_word(item["quaternary"])
    require(item == expected, label + " canonical metadata differs from raw constraints")


def audit_document(document, result):
    """Add metadata checks while retaining v1's full independent math audit."""
    sides, initial_domains, source_records = raw_metadata(document)
    n = len(sides)
    require(isinstance(result, dict), "result must be an object")
    require(type(result["schema_version"]) is int and result["schema_version"] == 1
            and result["model"] == "quaternary-contact-relations-v1", "wrong producer schema/model")
    require(result["side_order"] == sides and result["original_input"] == document,
            "source input or side identity changed")
    require(type(result["choices"]) is int and result["choices"] == 0
            and type(result["backtracks"]) is int and result["backtracks"] == 0
            and result["representatives_are_assignments"] is False,
            "display representatives were treated as commitments")
    require(result["status"] in ("conflict", "solved", "underdetermined"), "invalid producer status")
    check_domains(result["initial_domains"], n, "initial domains")
    check_domains(result["domains"], n, "final domains")
    require(result["initial_domains"] == initial_domains, "wrong literal initial domains")
    check_matrix(result["initial_relations"], n, "initial relation matrix")
    check_matrix(result["relations"], n, "final relation matrix")
    _, _, different, equal = reference_input(document)
    expected_initial = [[sum(1 << (4 * (a - 1) + b - 1)
                             for a in initial_domains[i] for b in initial_domains[j]
                             if (i != j or a == b)
                             and (tuple(sorted((i, j))) not in different or a != b)
                             and (tuple(sorted((i, j))) not in equal or a == b))
                         for j in range(n)] for i in range(n)]
    require(result["initial_relations"] == expected_initial, "initial matrix differs from raw contacts")
    require(all(not (result["relations"][i][j] & ~expected_initial[i][j])
                for i, j in product(range(n), repeat=2)), "final matrix added an initially forbidden pair")
    final_domains = [[color for color in (1, 2, 3, 4)
                      if result["relations"][i][i] & (1 << (5 * (color - 1)))] for i in range(n)]
    require(result["domains"] == final_domains, "final domain array differs from diagonal relations")
    for field in ("initial_states", "name_states", "explicit_anchor_sources"):
        require(isinstance(result[field], dict) and set(result[field]) == set(sides),
                field + " has missing or extra side identities")
    # Strict names/types in provenance also reject bool==1 comparisons.
    for side in sides:
        actual_sources = result["explicit_anchor_sources"][side]
        require(isinstance(actual_sources, list)
                and all(isinstance(item, dict) and set(item) == {"source", "name"}
                        and type(item["name"]) is int and item["name"] in (1, 2, 3, 4)
                        for item in actual_sources), "invalid explicit anchor-source metadata")
        require(actual_sources == source_records[side], "explicit anchor provenance differs")
    for i, side in enumerate(sides):
        check_state(result["initial_states"][side], expected_state(initial_domains[i], source_records[side]),
                    "initial state " + side)
        check_state(result["name_states"][side], expected_state(final_domains[i], source_records[side]),
                    "final state " + side)
    has_empty_relation = any(mask == 0 for row in result["relations"] for mask in row)
    expected_status = ("conflict" if has_empty_relation else "solved"
                       if all(len(domain) == 1 for domain in final_domains) else "underdetermined")
    require(result["status"] == expected_status, "status differs from empty relations/singleton classification")
    require(result["point_contacts"] == document.get("point_contacts", [])
            and result["equal_names"] == document.get("equal_names", []), "point-contact/EQ echo changed")
    require(isinstance(result["lines"], list) and len(result["lines"]) == len(document["lines"]),
            "line coverage differs")
    for source, line in zip(document["lines"], result["lines"]):
        require(isinstance(line, dict) and isinstance(line.get("reverse"), dict), "missing reverse line view")
        require(line["reverse"].get("left") == source["right"]
                and line["reverse"].get("right") == source["left"], "reverse line identities differ")
        for view in (line, line["reverse"]):
            require(type(view["relation_mask"]) is int and 0 <= view["relation_mask"] < 65536,
                    "line relation must be a literal 16-bit mask")
            require(isinstance(view["allowed_pairs"], list)
                    and all(isinstance(pair, list) and len(pair) == 2
                            and all(type(c) is int and c in (1, 2, 3, 4) for c in pair)
                            for pair in view["allowed_pairs"]), "line pair metadata has invalid literal names")
    if result["colors"] is not None:
        require(isinstance(result["colors"], dict) and set(result["colors"]) == set(sides)
                and all(type(c) is int and c in (1, 2, 3, 4) for c in result["colors"].values()),
                "complete coloring must contain literal integer names")
    mathematical = audit_mathematics(document, result)
    return {**mathematical, "audit_version": AUDIT_VERSION, "metadata_passed": True,
            "trace_audit": "not_replayed", "initial_to_final_matrix_subset": True}


def sources():
    """Keep every v1 dependency and add only the versioned metadata audit."""
    result = v1_sources()
    for name in ("scripts/validate_quaternary_contacts_v2.py",
                 "tests/test_quaternary_contact_metadata.py", SUPPLEMENT):
        result[name] = sha256((ROOT / name).read_bytes()).hexdigest()
    return result


def prepare(path):
    """Freeze the unchanged v1 inventory and the additional audit source set."""
    inventory = build_inventory()
    manifest = {"schema_version": 2, "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "audit_version": AUDIT_VERSION, "audit_scope": AUDIT_SCOPE,
                "source_sha256": sources(), "input_cases": inventory,
                "scope": {"max_variables": 4, "max_literal_assignments_per_case": 256,
                          "color_symmetry_reduction": False, "random_seeds": [], "workers": 1,
                          "kind": "unchanged v1 exhaustive finite abstract contact models"},
                "counts": dict(Counter(record["family"] for record in inventory))}
    write_report(path, manifest)
    return manifest["counts"]


def execute(manifest_path, output):
    """Retain failed scenes, preserve v1 artifacts, and run no hidden choices."""
    require(not output.exists(), "output exists; choose a new filename")
    manifest = read_report(manifest_path)
    require(manifest["audit_version"] == AUDIT_VERSION and manifest["audit_scope"] == AUDIT_SCOPE,
            "manifest names another audit contract")
    require(manifest["source_sha256"] == sources(), "sources changed after predeclaration")
    inventory = build_inventory()
    require(inventory == manifest["input_cases"], "manifest changed the frozen finite inventory")
    rows, examples, counts = [], [], Counter()
    assignments = legal = 0
    for ordinal, record in enumerate(inventory):
        document, result = document_for(record), None
        try:
            result = propagate_contacts(document)
            audit = audit_document(document, result)
        except Exception as error:
            failure = {"status": "failed", "coverage": "incomplete", "audit_version": AUDIT_VERSION,
                       "ordinal": ordinal, "case": record, "document": document, "result": result,
                       "completed_cases": len(rows), "error": str(error)}
            write_report(output.with_name(output.name + ".failure.json"), failure)
            raise
        counts[result["status"]] += 1
        assignments += audit["literal_assignments_checked"]
        legal += audit["legal_assignments"]
        rows.append({"ordinal": ordinal, "result_sha256": digest(result), "audit": audit})
        if record["family"] == "example":
            examples.append({**record["example"], "result": result, "audit": audit})
        if len(rows) % 5000 == 0:
            print(json.dumps({"checked": len(rows), "total": len(inventory), "audit_version": AUDIT_VERSION}), flush=True)
    require(manifest["source_sha256"] == sources(), "source changed during formal execution")
    summary = {"all_passed": True, "audit_version": AUDIT_VERSION, "cases": len(rows),
               "families": manifest["counts"], "statuses": dict(counts),
               "literal_assignments_checked": assignments, "legal_assignments_preserved": legal,
               "underdetermined_without_extensions": sum(row["audit"]["status"] == "underdetermined"
                                                           and row["audit"]["legal_assignments"] == 0 for row in rows)}
    report = {"schema_version": 2, "manifest_sha256": sha256(manifest_path.read_bytes()).hexdigest(),
              "manifest": manifest, "audit_scope": AUDIT_SCOPE, "summary": summary,
              "cases": rows, "examples": examples,
              "limits": "Canonical metadata and final mathematical behavior on the same bounded v1 inventory. Trace not replayed; no general completion or speed claim."}
    write_report(output, report)
    return summary


def main():
    """Use explicit new paths for predeclaration, execution and a single example."""
    parser = ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    pre = commands.add_parser("prepare")
    pre.add_argument("--manifest", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    demo = commands.add_parser("example")
    demo.add_argument("--id", default="two-neighbors-same-minimum")
    demo.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.manifest)
    elif args.command == "run":
        result = execute(args.manifest, args.output)
    else:
        examples = json.loads((ROOT / EXAMPLES).read_text(encoding="utf-8"))["cases"]
        example = next((item for item in examples if item["id"] == args.id), None)
        if example is None:
            parser.error("unknown example id")
        outcome = propagate_contacts(example["document"])
        audit = audit_document(example["document"], outcome)
        write_report(args.output, {**example, "result": outcome, "audit": audit, "audit_scope": AUDIT_SCOPE})
        result = {"id": example["id"], "status": outcome["status"], "audit": audit}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

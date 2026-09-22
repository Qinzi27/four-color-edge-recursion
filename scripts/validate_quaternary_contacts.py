"""Exhaustively audit the new display/candidate distinction on small contacts.

The reference checker reads raw input constraints, enumerates literal complete
assignments and uses ordinary sets for relational closure. It does not call the
production bit-mask composer or its domain decoder. This is a finite contact
model experiment, not an enumeration of all drawings or construction histories.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from itertools import combinations, product
import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.quaternary_contact_model import propagate_contacts
from scripts.validate_global_restart import digest, write_report

EXAMPLES = "examples/quaternary-contact-prototype-2026-09-21.json"
PROTOCOL = "docs/QUATERNARY_CONTACT_PROTOCOL-2026-09-21.md"


def require(condition, message):
    """Retain all checks under optimized Python as well."""
    if not condition:
        raise AssertionError(message)


def mask_word(mask):
    """Encode a declared candidate subset independently of NameState."""
    values = [color for color in range(1, 5) if mask & (1 << (color - 1))]
    marker = "2" if len(values) == 1 else "1"
    return "".join(marker if color in values else "0" for color in range(1, 5))


def build_inventory():
    """Declare all small graph/anchor combinations, domain stresses and examples."""
    records = []
    for n in range(1, 5):
        for edge_mask in range(1 << (n * (n - 1) // 2)):
            for names in product(range(5), repeat=n):
                records.append({"family": "simple", "n": n, "edge_mask": edge_mask,
                                "anchor_names": list(names)})
    for kind in ("separator", "equal_names", "point"):
        for first, second in product(range(16), repeat=2):
            records.append({"family": "domain-pair", "kind": kind, "masks": [first, second]})
    records.extend({"family": "bridge", "mask": mask} for mask in range(16))
    examples = json.loads((ROOT / EXAMPLES).read_text(encoding="utf-8"))
    records.extend({"family": "example", "example": example} for example in examples["cases"])
    return records


def document_for(record):
    """Reconstruct exactly the predeclared contact document from its finite recipe."""
    family = record["family"]
    if family == "example":
        return record["example"]["document"]
    if family == "simple":
        sides = [f"s{i}" for i in range(record["n"])]
        edges = list(combinations(sides, 2))
        return {"sides": sides,
                "anchors": {side: color for side, color in zip(sides, record["anchor_names"]) if color},
                "lines": [{"id": f"e{i}", "left": a, "right": b, "kind": "separator"}
                          for i, (a, b) in enumerate(edges) if record["edge_mask"] & (1 << i)]}
    if family == "bridge":
        return {"sides": ["A"], "states": {"A": mask_word(record["mask"])},
                "lines": [{"id": "bridge", "left": "A", "right": "A", "kind": "bridge"}]}
    document = {"sides": ["A", "B"], "states": {side: mask_word(mask)
                for side, mask in zip(("A", "B"), record["masks"])}, "lines": []}
    if record["kind"] == "separator":
        document["lines"] = [{"id": "ab", "left": "A", "right": "B", "kind": "separator"}]
    elif record["kind"] == "equal_names":
        document["equal_names"] = [["A", "B"]]
    else:
        document["point_contacts"] = [{"sides": ["A", "B"]}]
    return document


def reference_input(document):
    """Read candidate words and actual constraints without producer helpers."""
    sides = document["sides"]
    index = {side: i for i, side in enumerate(sides)}
    domains = []
    for side in sides:
        word = document.get("states", {}).get(side, "1111")
        allowed = {color for color, digit in enumerate(word, 1) if digit != "0"}
        if side in document.get("anchors", {}):
            allowed &= {document["anchors"][side]}
        domains.append(allowed)
    different, equal = set(), set()
    for line in document["lines"]:
        pair = tuple(sorted((index[line["left"]], index[line["right"]])))
        if line["kind"] == "separator":
            different.add(pair)
        else:
            require(pair[0] == pair[1], "a bridge must have one geometric side identity")
    for a, b in document.get("equal_names", []):
        equal.add(tuple(sorted((index[a], index[b]))))
    return sides, domains, different, equal


def reference_relations(domains, different, equal):
    """Construct literal ordered pairs and compute their set-theoretic closure."""
    n = len(domains)
    relations = [[{(a, b) for a in domains[i] for b in domains[j]
                   if (i != j or a == b)
                   and (tuple(sorted((i, j))) not in different or a != b)
                   and (tuple(sorted((i, j))) not in equal or a == b)}
                  for j in range(n)] for i in range(n)]
    while True:
        if any(not pairs for row in relations for pairs in row):
            return relations, True
        changed = False
        for i, j, k in product(range(n), repeat=3):
            possible = {(a, c) for a, middle in relations[i][k]
                        for other, c in relations[k][j] if middle == other}
            narrowed = relations[i][j] & possible
            if narrowed != relations[i][j]:
                relations[i][j] = narrowed
                changed = True
        if not changed:
            return relations, False


def audit_document(document, result):
    """Check every retained literal solution and a separate relational fixed point."""
    sides, domains, different, equal = reference_input(document)
    n = len(sides)
    require(result["original_input"] == document, "original input was changed")
    require(result["choices"] == result["backtracks"] == 0
            and result["representatives_are_assignments"] is False, "a hidden commitment was introduced")
    require(result["side_order"] == sides, "side order/identity changed")
    require(result["initial_domains"] == [sorted(d) for d in domains], "initial restriction was misread")
    decoded = [[{(a, b) for a, b in product(range(1, 5), repeat=2)
                 if mask & (1 << (4 * (a - 1) + b - 1))} for mask in row]
               for row in result["relations"]]
    reference, impossible = reference_relations(domains, different, equal)
    require((result["status"] == "conflict") == impossible, "producer/reference conflict differs")
    if not impossible:
        require(decoded == reference, "producer/reference fixed point differs")
    assignments, legal, witness = 0, 0, None
    for colors in product(*(sorted(d) for d in domains)):
        assignments += 1
        if (any(colors[a] == colors[b] for a, b in different)
                or any(colors[a] != colors[b] for a, b in equal)):
            continue
        legal += 1
        witness = list(colors) if witness is None else witness
        for i, side in enumerate(sides):
            require(colors[i] in result["name_states"][side]["candidates"], "lost a valid unary color")
            for j in range(n):
                require((colors[i], colors[j]) in decoded[i][j], "lost a valid ordered pair")
    for i, side in enumerate(sides):
        item = result["name_states"][side]
        domain = item["candidates"]
        require(domain == sorted(a for a, b in decoded[i][i] if a == b), "state and diagonal differ")
        require(item["representative"] == (min(domain) if domain else None), "incorrect display representative")
        word = item["quaternary"]
        require(len(word) == 4 and all(c in "0123" for c in word), "invalid four-digit word")
        require(int(word, 4) == item["code"], "base-four integer and display differ")
        require([c for c, digit in enumerate(word, 1) if digit != "0"] == domain, "word loses candidates")
    require(len(result["lines"]) == len(document["lines"]), "line coverage differs")
    index = {side: i for i, side in enumerate(sides)}
    for source, line in zip(document["lines"], result["lines"]):
        require(all(line[key] == value for key, value in source.items()), "line direction/identity changed")
        actual = decoded[index[source["left"]]][index[source["right"]]]
        reverse = {(b, a) for a, b in actual}
        for view, expected in ((line, actual), (line["reverse"], reverse)):
            require(view["allowed_pairs"] == [list(pair) for pair in sorted(expected)], "line pair list differs")
            expected_mask = sum(1 << (4 * (a - 1) + b - 1) for a, b in expected)
            require(view["relation_mask"] == expected_mask, "line relation mask differs")
            word = view["relation_code"]
            require(len(word) == 8 and all(c in "0123" for c in word)
                    and int(word, 4) == expected_mask, "packed eight-digit relation differs")
    if result["status"] == "solved":
        require(all(len(result["name_states"][s]["candidates"]) == 1 for s in sides)
                and legal == 1, "solved does not have one actual valid assignment")
        require(result["colors"] == dict(zip(sides, witness)), "solved colors are not the actual witness")
    else:
        require(result["colors"] is None, "an unresolved representative was exported as a coloring")
    if result["status"] == "conflict":
        require(legal == 0, "false conflict removes an actual solution")
    return {"passed": True, "literal_assignments_checked": assignments, "legal_assignments": legal,
            "one_witness": witness, "status": result["status"],
            "representatives_are_complete_assignment": (all(len(result["name_states"][s]["candidates"]) == 1
                                                             for s in sides) and legal == 1)}


def sources():
    """Bind the frozen implementation, reference, examples and their unit checks."""
    names = {p.relative_to(ROOT).as_posix() for p in ROOT.glob("fourcolor/*.py")}
    names.update(("scripts/quaternary_contact_model.py", "scripts/validate_quaternary_contacts.py",
                  "scripts/validate_global_restart.py", "tests/test_quaternary_contact_model.py",
                  "tests/test_quaternary_contact_audit.py", EXAMPLES, PROTOCOL))
    return {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in sorted(names)}


def read_report(path):
    """Read plain or deterministic gzip JSON without changing its evidence."""
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def prepare(path):
    """Freeze all finite model recipes before any formal producer run."""
    inventory = build_inventory()
    manifest = {"schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "source_sha256": sources(), "input_cases": inventory,
                "scope": {"max_variables": 4, "max_literal_assignments_per_case": 256,
                          "color_symmetry_reduction": False, "random_seeds": [], "workers": 1,
                          "kind": "exhaustive finite abstract contact models, not whole map histories"},
                "counts": dict(Counter(r["family"] for r in inventory))}
    write_report(path, manifest)
    return manifest["counts"]


def execute(manifest_path, output):
    """Run all frozen cases; keep a full failed scene if any check rejects it."""
    require(not output.exists(), "output exists; choose a new filename")
    manifest = read_report(manifest_path)
    require(manifest["source_sha256"] == sources(), "sources changed after predeclaration")
    inventory = build_inventory()
    require(inventory == manifest["input_cases"], "manifest omitted or changed finite inputs")
    rows, examples = [], []
    counts, assignments, legal = Counter(), 0, 0
    for ordinal, record in enumerate(inventory):
        document, result = document_for(record), None
        try:
            result = propagate_contacts(document)
            audit = audit_document(document, result)
        except Exception as exc:
            failure = {"status": "failed", "coverage": "incomplete", "ordinal": ordinal,
                       "case": record, "document": document, "result": result,
                       "completed_cases": len(rows), "error": str(exc)}
            write_report(output.with_name(output.name + ".failure.json"), failure)
            raise
        counts[result["status"]] += 1
        assignments += audit["literal_assignments_checked"]
        legal += audit["legal_assignments"]
        rows.append({"ordinal": ordinal, "result_sha256": digest(result), "audit": audit})
        if record["family"] == "example":
            examples.append({**record["example"], "result": result, "audit": audit})
        if len(rows) % 5000 == 0:
            print(json.dumps({"checked": len(rows), "total": len(inventory)}), flush=True)
    require(manifest["source_sha256"] == sources(), "source changed during formal execution")
    summary = {"all_passed": True, "cases": len(rows), "families": manifest["counts"],
               "statuses": dict(counts), "literal_assignments_checked": assignments,
               "legal_assignments_preserved": legal,
               "underdetermined_without_extensions": sum(row["audit"]["status"] == "underdetermined"
                                                           and row["audit"]["legal_assignments"] == 0 for row in rows)}
    report = {"schema_version": 1, "manifest_sha256": sha256(manifest_path.read_bytes()).hexdigest(),
              "manifest": manifest, "summary": summary, "cases": rows, "examples": examples,
              "limits": "This checks candidate semantics and contact propagation on the declared small models. No general completion or speed claim; no min-name commitment."}
    write_report(output, report)
    return summary


def main():
    """Separate predeclaration, formal execution, and a reviewable single example."""
    parser = ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    pre = sub.add_parser("prepare")
    pre.add_argument("--manifest", type=Path, required=True)
    run = sub.add_parser("run")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    demo = sub.add_parser("example")
    demo.add_argument("--id", default="two-neighbors-same-minimum")
    demo.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.manifest)
    elif args.command == "run":
        result = execute(args.manifest, args.output)
    else:
        rows = json.loads((ROOT / EXAMPLES).read_text(encoding="utf-8"))["cases"]
        row = next((r for r in rows if r["id"] == args.id), None)
        if row is None:
            parser.error("unknown example id")
        outcome = propagate_contacts(row["document"])
        audit = audit_document(row["document"], outcome)
        write_report(args.output, {**row, "result": outcome, "audit": audit})
        result = {"id": row["id"], "status": outcome["status"], "audit": audit}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

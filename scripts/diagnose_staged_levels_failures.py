"""Bounded post-run diagnostics from six renamings of archived legal witnesses.

This script never invokes the production naming algorithm or searches new
assignments. It preserves exterior 1 and enumerates only the six permutations
of the three non-exterior names 2/3/4 in one OLD valid v2 coloring. A surviving witness proves
extendibility of a particular current decision prefix. Absence of such a
permuted old witness does NOT prove that prefix has no other completion.
"""

from argparse import ArgumentParser
from datetime import datetime, timezone
from itertools import permutations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.line_names import audit_line_names
from scripts.validate_frontier_restart import file_sha, independent_geometry, read_json
from scripts.validate_global_restart import digest
from scripts.validate_relation_frontier import decode
from scripts.validate_staged_levels import POLICY, verify_run


def source_hashes():
    """Bind this explanation to the independent checker and its local helpers."""
    paths = (
        "scripts/diagnose_staged_levels_failures.py", "scripts/validate_staged_levels.py",
        "scripts/validate_level_sides_peer.py", "scripts/validate_relation_frontier.py",
        "scripts/validate_frontier_restart.py", "scripts/validate_global_restart.py",
        "scripts/analyze_line_generations.py", "fourcolor/embedding.py",
        "fourcolor/line_names.py", "fourcolor/whole_lines.py", "fourcolor/global_restart.py",
        "fourcolor/closed_support.py",
    )
    return {path: file_sha(ROOT / path) for path in paths}


def audit_witness(geometry, plane, colors):
    """Directly check every raw primal edge and every oriented side orbit."""
    assert len(colors) == len(plane.faces)
    assert all(type(color) is int and color in (1, 2, 3, 4) for color in colors)
    assert colors[geometry["outerFace"]] == 1
    separators = 0
    for edge in range(len(plane.edges)):
        first, second = plane.shores(edge)
        if first != second:
            assert colors[first] != colors[second]
            separators += 1
        if geometry["edges"][edge].get("virtual"):
            assert first == second
    names = [(str(colors[first]), str(colors[second]))
             for first, second in (plane.shores(edge) for edge in range(len(plane.edges)))]
    audit = audit_line_names(geometry["rotation"], names)
    assert audit.status == "consistent"
    return {"passed": True, "shore_count": len(colors), "edge_count": len(names),
            "separator_edges_checked": separators, "side_orbits_checked": len(audit.side_orbits),
            "line_names_sha256": digest(names)}


def matches_anchors(plane, colors, anchors):
    """Compare against active commitments without using any narrowed domain."""
    return all(colors[plane.face_of_dart[int(dart)]] in allowed
               for dart, allowed in anchors.items())


def audit_prefix_relations(colors, phases, prefix):
    """A genuine completion must survive all certified domains and pair masks."""
    relation_checks = 0
    for phase in phases[:prefix + 1]:
        outcome = phase["outcome"]
        assert outcome["status"] != "conflict"
        assert all(color in domain for color, domain in zip(colors, outcome["domains"]))
        for first, row in enumerate(outcome["relations"]):
            for second, mask in enumerate(row):
                assert (colors[first], colors[second]) in decode(mask)
                relation_checks += 1
    return {"passed": True, "propagation_calls_checked": prefix + 1,
            "ordered_pair_memberships_checked": relation_checks}


def terminal_conflict_summary(result):
    """Expose an empty pair relation even when every unary domain is nonempty."""
    outcome = result["propagation_phases"][-1]["outcome"]
    phase = outcome["phases"][-1]
    event = phase["relation_trace"][-1] if phase["relation_trace"] else None
    decoded = None if event is None else {
        **event, "decoded_pairs": {name: sorted(decode(event[name]))
                                    for name in ("before", "left", "right", "after", "removed")}}
    return {"hall_status": phase["hall_status"], "hall_conflict": phase["hall_conflict"],
            "empty_unary_sides": [side for side, values in enumerate(outcome["domains"]) if not values],
            "empty_ordered_side_relations": [[i, j] for i, row in enumerate(outcome["relations"])
                                             for j, mask in enumerate(row) if mask == 0],
            "last_relation_derivation": decoded,
            "index_meaning": "i, j, and via are current side identities, not mother-line names."}


def diagnose(record):
    """Locate a first fatal choice only when all previous choices have a witness."""
    geometry, result = record["geometry"], record["outcome"]
    assert result["status"] == "conflict"
    certificate = verify_run(geometry, result)
    assert certificate["passed"]
    plane, _ = independent_geometry(geometry)
    previous = record["previous_result"]
    base = {"key": record["key"], "aliases": record.get("aliases", []),
            "face_count": record["face_count"], "candidate_policy": result["policy"],
            "choices": result["choices"], "initialization": result["initialization"],
            "conflict_proof_replayed": certificate,
            "terminal_conflict": terminal_conflict_summary(result),
            "production_attempts_added": 0, "diagnostic_old_colors_read": True}
    if previous.get("status") != "solved" or previous.get("colors") is None:
        return {**base, "status": "no-archived-legal-witness",
                "first_fatal_choice_proved": False,
                "reason": "No old completed coloring available; no assignment solver was added."}
    old = previous["colors"]
    old_audit = audit_witness(geometry, plane, old)
    candidates = []
    for order in permutations((2, 3, 4)):
        mapping = dict(zip((1, 2, 3, 4), (1, *order)))
        colors = [mapping[color] for color in old]
        audit_witness(geometry, plane, colors)
        assert matches_anchors(plane, colors, result["initial_anchors_by_dart"])
        prefix = 0
        for step in result["trace"]:
            if colors[step["side"]] != step["symbol"]:
                break
            prefix += 1
        assert prefix < len(result["trace"]), "valid witness contradicts checked final conflict"
        candidates.append({"permutation": mapping, "colors": colors,
                           "matched_active_choice_prefix": prefix})
    best = max(candidates, key=lambda item: item["matched_active_choice_prefix"])
    prefix = best["matched_active_choice_prefix"]
    assert prefix >= 1, "an exterior-preserving renaming must normalize the first retained shore"
    witness_audit = audit_witness(geometry, plane, best["colors"])
    relation_audit = audit_prefix_relations(best["colors"], result["propagation_phases"], prefix)
    for call in result["propagation_phases"][:prefix + 1]:
        assert matches_anchors(plane, best["colors"], call["anchors_by_dart"])
    terminal_is_first = prefix == len(result["trace"]) - 1
    last = result["trace"][-1]
    return {**base, "status": "terminal-choice-proved-first-fatal" if terminal_is_first else
                             "fatal-position-not-localized-by-old-witness-permutations",
            "archived_policy": previous.get("policy"), "archived_witness_audit": old_audit,
            "permutations_examined": len(candidates),
            "permutation_prefix_lengths": [{"permutation": row["permutation"],
                                             "matched_active_choice_prefix": row["matched_active_choice_prefix"]}
                                            for row in candidates],
            "longest_witnessed_active_prefix": prefix,
            "first_fatal_choice_proved": terminal_is_first,
            "first_fatal_choice_index_one_based": len(result["trace"]) if terminal_is_first else None,
            "witness": {**best, "geometry_audit": witness_audit, "prefix_relation_audit": relation_audit},
            "terminal_choice": {"index_one_based": len(result["trace"]), **last},
            "witness_terminal_side_name": best["colors"][last["side"]],
            "interpretation": (
                "Every earlier active decision has this explicit legal completion; the certified final "
                "conflict therefore begins at the terminal commitment."
                if terminal_is_first else
                "A valid old-witness permutation survives only this prefix. Other completions may survive "
                "longer; the first fatal choice has not been proved.")}


def main():
    """Write a new evidence file, refusing replacement or optimized assertions."""
    if not __debug__:
        raise SystemExit("This proof-checking diagnostic requires Python without -O.")
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite an existing diagnosis report.")
    start_hashes = source_hashes()
    sources, records = [], {}
    for path in args.input:
        payload = read_json(path)
        inventory = payload["drawings"] if "drawings" in payload else payload["records"]
        expected = {row["key"] for row in inventory if row["runs"][POLICY]["status"] == "conflict"}
        detailed_failures = {key for key, row in payload["detailed_examples"].items()
                             if row["outcome"]["status"] == "conflict"}
        assert detailed_failures == expected, "some failed drawing has no complete diagnostic certificate"
        sources.append({"filename": path.name, "sha256": file_sha(path),
                        "full_corpus_run": payload.get("full_corpus_run", False),
                        "failed_inventory_records": len(expected),
                        "all_failed_records_have_full_certificates": True})
        for key, record in payload["detailed_examples"].items():
            if record["outcome"]["status"] != "conflict":
                continue
            if key in records:
                assert records[key] == record
            records[key] = record
    diagnoses = [diagnose(records[key]) for key in sorted(records)]
    end_hashes = source_hashes()
    assert end_hashes == start_hashes, "diagnostic/checker/helper code changed during explanation"
    report = {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "sources": sources, "method": "six-exterior-preserving-permutations-of-archived-v2-witness",
              "source_sha256": start_hashes, "source_sha256_end": end_hashes,
              "source_hashes_unchanged": True,
              "production_attempts_added": 0, "failure_records_examined": len(diagnoses),
              "terminal_choice_proved_first_fatal": sum(r["first_fatal_choice_proved"] for r in diagnoses),
              "records": diagnoses,
              "limitations": [
                  "Post-run explanation, not a new solver, successful production retry, or unseen test.",
                  "Only six global renamings of one archived legal witness are considered per map.",
                  "No surviving old-witness permutation does not imply no other completion exists.",
                  "A conflict concerns the current fixed commitments, not the map's four-colorability.",
              ]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({key: report[key] for key in (
        "failure_records_examined", "terminal_choice_proved_first_fatal", "production_attempts_added")},
        ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

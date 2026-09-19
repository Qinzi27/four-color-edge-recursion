"""Explain frozen v4 failures using archived legal v3 witnesses only.

This post-run diagnostic never invokes a production restart, retries a failed
name, or changes an algorithm. Six exterior-preserving permutations can prove
an earlier prefix extendible; their absence cannot prove non-extendibility.
Checkpoint-directory input is explicitly a partial snapshot, never full stats.
"""

from argparse import ArgumentParser
from datetime import datetime, timezone
from itertools import permutations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.global_restart import current_segments
from fourcolor.level_sides import level_metadata
from fourcolor.level_sides_peer import select_peer_occurrence
from fourcolor.whole_lines import build_whole_lines
from scripts.diagnose_staged_levels_failures import (
    audit_prefix_relations, audit_witness, matches_anchors, terminal_conflict_summary,
)
from scripts.validate_frontier_restart import file_sha, independent_geometry, read_json
from scripts.validate_global_restart import digest
from scripts.validate_peer_batches import verify_run
from scripts.validate_peer_batches_full import POLICY, source_hashes as production_hashes
from scripts.validate_relation_frontier_full import failure_rank, require


def source_hashes():
    """Freeze all original producer/checker files plus diagnostic helper code."""
    hashes = production_hashes()
    for name in ("scripts/diagnose_peer_batch_failures.py", "scripts/diagnose_staged_levels_failures.py"):
        hashes[name] = file_sha(ROOT / name)
    return hashes


def gate_context(geometry, result):
    """Compare one preterminal scheduling decision, not another coloring run.

    The ungated v3 selector is inspected on the SAME preterminal domains. Its
    output does not prove a successful counterfactual trajectory. Full final-
    map constraints remain present even for a side deferred by the ready gate.
    """
    step = result["trace"][-1]
    domains = result["propagation_phases"][-2]["outcome"]["domains"]
    model = build_whole_lines(geometry)
    earlier = select_peer_occurrence(model, current_segments(model), level_metadata(model), domains)
    ready = result["batch_geometry"]["side_ready_stage"]
    active = step.get("active_stage")
    deferred = [side for side, values in enumerate(domains)
                if len(values) > 1 and active is not None and ready[side] > active]
    boundary = step["boundary"]["sources"]
    return {
        "preterminal_domains": domains,
        "active_stage": active,
        "selected_ready_stage": ready[step["side"]],
        "ungated_selector_only": {**earlier, "domain": domains[earlier["side"]],
                                  "minimum_name": min(domains[earlier["side"]]),
                                  "ready_stage": ready[earlier["side"]]},
        "ungated_choice_was_deferred": earlier["side"] in deferred,
        "deferred_side_ids": deferred,
        "selected_side_deferred_neighbors": sorted({row["neighbor"] for row in boundary
                                                       if row["neighbor"] in deferred}),
        "stage_partition_sizes": [{"stage": row["stage"],
                                    "coarse_cell_sizes": [len(cell) for cell in row["coarse_cells"]],
                                    "newly_ready_sides": row["newly_ready_sides"]}
                                   for row in result["batch_geometry"]["stages"]],
        "interpretation": "Readiness is geometric, not a guarantee that the minimum domain name extends; "
                          "deferred sides still participate in every Hall/pair propagation phase.",
        "production_restarts_added": 0,
    }


def diagnose(record):
    """Use a legal prefix witness plus the checked contradiction to localize failure."""
    geometry, result, previous = record["geometry"], record["outcome"], record["previous_result"]
    require(result["status"] == "conflict", "diagnosis requires a stored failed attempt")
    check = verify_run(geometry, result)
    require(check["passed"], "failure proof did not replay")
    plane, _ = independent_geometry(geometry)
    base = {"key": record["key"], "aliases": record["aliases"], "face_count": record["face_count"],
            "candidate_policy": POLICY, "choices": result["choices"],
            "initialization": result["initialization"], "conflict_proof_replayed": check,
            "terminal_conflict": terminal_conflict_summary(result),
            "gate_context": gate_context(geometry, result), "production_attempts_added": 0,
            "diagnostic_old_colors_read": True, "archived_policy": previous.get("policy"),
            "terminal_choice": {"index_one_based": len(result["trace"]), **result["trace"][-1]}}
    if previous.get("status") != "solved" or previous.get("colors") is None:
        return {**base, "status": "no-archived-legal-witness", "first_fatal_choice_proved": False}
    old = previous["colors"]
    old_audit = audit_witness(geometry, plane, old)
    witnesses = []
    for order in permutations((2, 3, 4)):
        mapping = dict(zip((1, 2, 3, 4), (1, *order)))
        colors = [mapping[color] for color in old]
        audit_witness(geometry, plane, colors)
        require(matches_anchors(plane, colors, result["initial_anchors_by_dart"]), "exterior anchor mismatch")
        prefix = 0
        for step in result["trace"]:
            if colors[step["side"]] != step["symbol"]:
                break
            prefix += 1
        require(prefix < len(result["trace"]), "legal witness contradicts certified final conflict")
        witnesses.append({"permutation": mapping, "colors": colors,
                          "matched_active_choice_prefix": prefix})
    best = max(witnesses, key=lambda item: item["matched_active_choice_prefix"])
    prefix = best["matched_active_choice_prefix"]
    require(prefix >= 1, "one retained-side normalization must have a renamed witness")
    witness_audit = audit_witness(geometry, plane, best["colors"])
    relation_audit = audit_prefix_relations(best["colors"], result["propagation_phases"], prefix)
    for call in result["propagation_phases"][:prefix + 1]:
        require(matches_anchors(plane, best["colors"], call["anchors_by_dart"]), "witness prefix mismatch")
    localized = prefix == len(result["trace"]) - 1
    return {**base, "status": "terminal-choice-proved-first-fatal" if localized else
                             "first-fatal-position-not-localized-by-six-witnesses",
            "archived_witness_audit": old_audit, "permutations_examined": len(witnesses),
            "permutation_prefix_lengths": [{"permutation": row["permutation"],
                                             "matched_active_choice_prefix": row["matched_active_choice_prefix"]}
                                            for row in witnesses],
            "longest_witnessed_active_prefix": prefix, "first_fatal_choice_proved": localized,
            "first_fatal_choice_index_one_based": len(result["trace"]) if localized else None,
            "witness": {**best, "geometry_audit": witness_audit, "prefix_relation_audit": relation_audit},
            "witness_terminal_side_name": best["colors"][result["trace"][-1]["side"]],
            "interpretation": "All earlier decisions have this legal completion; the terminal commitment "
                              "is the first fatal choice." if localized else
                              "A witness survives this prefix only; other completions may survive longer."}


def main():
    """Snapshot completed checkpoints or read a final report; never replace evidence."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append")
    parser.add_argument("--parts-directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not sys.flags.optimize, "proof diagnosis requires Python without -O")
    require(not args.output.exists(), "choose a new diagnosis output")
    require(bool(args.input) != bool(args.parts_directory), "use either --input or --parts-directory")
    hashes = source_hashes()
    # Only files with an already-written checksum sidecar enter this immutable
    # snapshot; later full-run progress cannot change its denominator.
    paths = sorted(path for path in args.parts_directory.glob("part-*.json.gz")
                   if path.with_suffix(path.suffix + ".sha256.json").is_file()) if args.parts_directory else args.input
    require(bool(paths), "no completed input evidence")
    sources, records, input_keys = [], {}, set()
    for path in paths:
        checksum = file_sha(path)
        if args.parts_directory:
            require(read_json(path.with_suffix(path.suffix + ".sha256.json")) ==
                    {"filename": path.name, "sha256": checksum}, "checkpoint checksum mismatch")
        payload = read_json(path)
        inventory = payload.get("drawings", payload.get("records"))
        require(inventory is not None, "input lacks drawing inventory")
        expected = {row["key"] for row in inventory if row["runs"][POLICY]["status"] == "conflict"}
        details = {key: value for key, value in payload["detailed_examples"].items()
                   if value["outcome"]["status"] == "conflict"}
        require(set(details) == expected, "failed input lacks a complete certificate")
        input_keys.update(row["key"] for row in inventory)
        sources.append({"filename": path.name, "sha256": checksum,
                        "full_corpus_run": payload.get("full_corpus_run", False),
                        "failed_inventory_records": len(expected)})
        for key, detail in details.items():
            require(key not in records or records[key] == detail, "duplicate failure certificates differ")
            records[key] = detail
    diagnoses = [diagnose(row) for row in sorted(records.values(), key=failure_rank)]
    require(source_hashes() == hashes, "diagnostic source changed during run")
    require(all(file_sha(path) == source["sha256"] for path, source in zip(paths, sources)),
            "input source changed during diagnosis")
    report = {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "partial-checkpoint-snapshot" if args.parts_directory else "declared-input-reports",
              "full_corpus_statistics": False, "sources": sources,
              "input_unique_drawings_snapshot": len(input_keys),
              "method": "six-exterior-preserving-renamings-of-archived-v3-witness",
              "source_sha256": hashes, "source_sha256_end": hashes,
              "source_hashes_unchanged": True, "production_attempts_added": 0,
              "failure_records_examined": len(diagnoses),
              "terminal_choice_proved_first_fatal": sum(row["first_fatal_choice_proved"] for row in diagnoses),
              "records": diagnoses,
              "research_candidates_not_applied": [
                  {"kind": "conditional-candidate-exclusion", "implementation_status": "not implemented in v4",
                   "premise": "The current Hall/pair filter is sound: every genuine completion survives it.",
                   "rule": "If filtering A together with the temporary assumption X_F=a yields a checked "
                           "contradiction, delete a from D_F before any permanent commitment.",
                   "proof": "Let Omega(A) be all valid full colorings satisfying current anchors A. A checked "
                            "sound-filter contradiction under X_F=a implies Omega(A) intersect {X_F=a} is "
                            "empty. Thus deleting a preserves every completion of A.",
                   "boundary": "This is explicitly conditional probing, not mere renaming or a new ordering. "
                               "It can be bounded to individual names without enumerating full colorings, "
                               "but it may still leave globally unsupported names and proves no universal success."},
                  {"kind": "higher-order-boundary-support", "implementation_status": "unproved research route",
                   "rule": "Retain jointly allowed boundary triples (a,b,c), rather than only independent "
                           "single-name domains and pair projections; remove a tuple only with a checked reason.",
                   "boundary": "Pairwise supports need not give a common joint support. Triple tables require "
                               "an explicit sound update/checking rule and still do not imply global completeness."},
                  {"kind": "conditional-Hall-certificate", "implementation_status": "candidate certificate form",
                   "rule": "Under X_F=a, propagate only justified exclusions to temporary domains D'_v. For a "
                           "clique Q, if the union of D'_v over v in Q has size less than |Q|, reject a.",
                   "boundary": "The inequality is a valid contradiction certificate, not evidence that this "
                               "simple check detects the present examples or adds power beyond existing Hall rules."},
              ],
              "limits": ["Post-run explanation only; no altered rules or successful production retries.",
                         "Six renamed old witnesses are not an exhaustive assignment search.",
                         "No surviving old witness does not prove the absence of another legal completion.",
                         "A conflict rejects this commitment path, not the four-colorability of the map.",
                         "Ready-gate versus ungated selector is a same-state comparison, not a second run."]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({key: report[key] for key in (
        "scope", "input_unique_drawings_snapshot", "failure_records_examined", "terminal_choice_proved_first_fatal")},
                     ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

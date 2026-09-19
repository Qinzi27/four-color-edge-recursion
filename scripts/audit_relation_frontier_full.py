"""Independently audit saved full-library counts, identities, and provenance.

Only the standard library is imported. No coloring policy, geometry exporter,
or producer summary function is called. Mathematical certificate replay stays
with the separately recorded validation run; this audit verifies that its
results were preserved, counted, and compared without changing denominators.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import json
from math import fsum, isclose
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXISTING = "existing-corpus"
HELDOUT = "new-seeds-20261901-20261940"
CLOSED = "closed-support"
HALL = "tight-hall"
RELATION = "tight-hall-relations"
POLICIES = (CLOSED, HALL, RELATION)
GROUPS = ("combined", EXISTING, HELDOUT)


def verify(condition, message):
    """Use explicit assertions even if Python was launched with optimization."""
    if not condition:
        raise AssertionError(message)


def read_report(path):
    """Read immutable evidence and hash its actual plain/compressed bytes."""
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data), sha256(data).hexdigest()


def digest(value):
    """Reconstruct the portable JSON identity without producer imports."""
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")).hexdigest()


def unique_index(rows, fields):
    """Reject duplicates instead of silently overwriting them in dictionaries."""
    indexed = {tuple(row[field] for field in fields): row for row in rows}
    verify(len(indexed) == len(rows), "duplicate index: " + "/".join(fields))
    return indexed


def pair_counts(pairs):
    """Compute paired wins AND regressions from actual success indicators."""
    counts = Counter((bool(a), bool(b)) for a, b in pairs)
    return {"both_solved": counts[(True, True)], "improved": counts[(False, True)],
            "regressed": counts[(True, False)], "both_not_solved": counts[(False, False)]}


def recount(records, histories, statics, policies=POLICIES):
    """Rebuild every reported denominator/status from drawing-level outcomes.

    This function is deliberately usable on small synthetic inputs; full-corpus
    size assertions live in audit(), so arithmetic tests need no solver run.
    """
    indexed = unique_index(records, ("key",))
    by_key = {key[0]: row for key, row in indexed.items()}
    unique_index(histories, ("key",))
    unique_index(statics, ("key",))
    verify(len(set(policies)) == len(policies), "duplicate policies")
    history_rows = {}
    for history in histories:
        verify(bool(history["prefix_keys"]), "empty history")
        for policy in policies:
            statuses = [by_key[key]["runs"][policy]["status"] for key in history["prefix_keys"]]
            failed = [i for i, status in enumerate(statuses) if status != "solved"]
            history_rows[(history["key"], policy)] = {
                "key": history["key"], "policy": policy, "family": history["family"],
                "cohort": history["cohort"], "statuses": statuses,
                "all_prefixes_solved": not failed,
                "first_failed_prefix": min(failed) if failed else None,
                "solved_again_after_failure": [i for i in range(1, len(statuses))
                                               if statuses[i - 1] != "solved" and statuses[i] == "solved"],
                "final_status": statuses[-1]}
    summaries, closed_pairs, hall_pairs = [], [], []
    for group in GROUPS:
        drawings = [row for row in records if group == "combined" or group in row["cohorts"]]
        sequences = [row for row in histories if group == "combined" or row["cohort"] == group]
        static_rows = [row for row in statics if group == "combined" or row["cohort"] == group]
        for policy in policies:
            rows = [history_rows[(h["key"], policy)] for h in sequences]
            families = {}
            for row in rows:
                family = families.setdefault(row["family"], {"histories": 0, "all_prefixes_solved": 0,
                                                            "final_status": Counter()})
                family["histories"] += 1
                family["all_prefixes_solved"] += row["all_prefixes_solved"]
                family["final_status"][row["final_status"]] += 1
            summaries.append({
                "cohort": group, "policy": policy, "distinct_drawing_count": len(drawings),
                "distinct_drawings": dict(Counter(r["runs"][policy]["status"] for r in drawings)),
                "verification": dict(Counter(r["runs"][policy].get("verification", {}).get("method", "not-run")
                                             for r in drawings)),
                "runtime_seconds": fsum(r["runs"][policy].get("runtime_seconds", 0.0) for r in drawings),
                "hall_active_drawings": sum(r["runs"][policy].get("hall_derivation_events_including_recomputations", 0) > 0
                                            for r in drawings),
                "hall_derivation_events_including_recomputations": sum(r["runs"][policy].get(
                    "hall_derivation_events_including_recomputations", 0) for r in drawings),
                "hall_explicit_deficiency_drawings": sum(bool(r["runs"][policy].get("hall_conflict")) for r in drawings),
                "history_count": len(rows), "history_prefix_references": sum(len(h["prefix_keys"]) for h in sequences),
                "all_prefixes": {"all_solved": sum(r["all_prefixes_solved"] for r in rows),
                                 "has_failure": sum(not r["all_prefixes_solved"] for r in rows)},
                "history_final_status": dict(Counter(r["final_status"] for r in rows)),
                "history_families": families, "static_count": len(static_rows),
                "static_status": dict(Counter(by_key[r["geometry_key"]]["runs"][policy]["status"] for r in static_rows))})

        def paired(baseline, candidate):
            """Keep drawing, all-prefix, terminal, and static comparisons distinct."""
            return {"cohort": group, "baseline": baseline, "candidate": candidate,
                    "distinct_drawings": pair_counts((r["runs"][baseline]["status"] == "solved",
                                                      r["runs"][candidate]["status"] == "solved") for r in drawings),
                    "all_history_prefixes": pair_counts((history_rows[(h["key"], baseline)]["all_prefixes_solved"],
                                                         history_rows[(h["key"], candidate)]["all_prefixes_solved"])
                                                        for h in sequences),
                    "history_final": pair_counts((history_rows[(h["key"], baseline)]["final_status"] == "solved",
                                                   history_rows[(h["key"], candidate)]["final_status"] == "solved")
                                                  for h in sequences),
                    "static_final": pair_counts((by_key[s["geometry_key"]]["runs"][baseline]["status"] == "solved",
                                                  by_key[s["geometry_key"]]["runs"][candidate]["status"] == "solved")
                                                 for s in static_rows)}
        closed_pairs.extend(paired(CLOSED, p) for p in policies if p != CLOSED)
        hall_pairs.append(paired(HALL, RELATION))
    return {"history_results": list(history_rows.values()), "summary": summaries,
            "paired_comparisons": closed_pairs, "paired_vs_hall": hall_pairs}


def check_recount(report):
    """Compare independently derived tables; tolerate only summation roundoff."""
    rebuilt = recount(report["drawings"], report["histories"], report["static_inputs"], report["policies"])
    for field, keys in (("history_results", ("key", "policy")),
                        ("paired_comparisons", ("cohort", "baseline", "candidate")),
                        ("paired_vs_hall", ("cohort", "baseline", "candidate"))):
        verify(unique_index(report[field], keys) == unique_index(rebuilt[field], keys),
               "independent recount mismatch: " + field)
    saved = unique_index(report["summary"], ("cohort", "policy"))
    expected = unique_index(rebuilt["summary"], ("cohort", "policy"))
    verify(set(saved) == set(expected), "summary cohort/policy combinations")
    for key, row in expected.items():
        verify({field: saved[key][field] for field in row if field != "runtime_seconds"}
               == {field: value for field, value in row.items() if field != "runtime_seconds"},
               "summary arithmetic mismatch: " + str(key))
        verify(isclose(saved[key]["runtime_seconds"], row["runtime_seconds"], rel_tol=1e-12, abs_tol=1e-9),
               "runtime sum mismatch: " + str(key))
    return rebuilt


def check_checkpoint_assembly(report, input_path):
    """Check immutable batch bytes and their exact assembly, without solving."""
    execution = report["execution"]
    directory = execution["checkpoint_directory"]
    verify(Path(directory).name == directory and directory not in ("", ".", ".."), "checkpoint directory must be a basename")
    checkpoint_root = input_path.parent / directory
    manifest, manifest_sha = read_report(checkpoint_root / "manifest.json")
    for field in ("source_evidence", "diagnostic_evidence", "source_sha256", "policies", "smoke_limit"):
        verify(manifest[field] == report[field], "checkpoint manifest drift: " + field)
    keys = [row["key"] for row in report["drawings"]]
    verify(manifest["selected_keys"] == keys, "checkpoint selection/assembled order")
    size = execution["batch_size"]
    verify(type(size) is int and size > 0 and manifest["batch_size"] == size, "checkpoint batch size")
    verify(type(execution["workers"]) is int and 1 <= execution["workers"] <= 8, "worker count")
    count = (len(keys) + size - 1) // size
    expected_names = {f"part-{index:05d}.json.gz" for index in range(count)}
    verify(set(execution["part_sha256"]) == expected_names, "missing or extra checkpoint parts")
    diagnostic_matches, detailed, failures = 0, {}, []
    for index in range(count):
        name = f"part-{index:05d}.json.gz"
        path = checkpoint_root / name
        piece, value = read_report(path)
        verify(value == execution["part_sha256"][name], "checkpoint bytes changed: " + name)
        checksum, _ = read_report(path.with_suffix(path.suffix + ".sha256.json"))
        verify(checksum == {"filename": name, "sha256": value}, "checkpoint saved checksum: " + name)
        verify(piece["index"] == index, "checkpoint index")
        verify(piece["records"] == report["drawings"][index * size:(index + 1) * size],
               "checkpoint/full record mismatch: " + name)
        diagnostic_matches += piece["diagnostic_exact_reproductions"]
        verify(not set(detailed) & set(piece["detailed_examples"]), "duplicate named detail between batches")
        detailed.update(piece["detailed_examples"])
        if piece["least_failure"] is not None:
            failures.append(piece["least_failure"])
    verify(diagnostic_matches == report["diagnostic_exact_reproductions"], "checkpoint diagnostic count")
    verify(detailed == report["detailed_examples"], "named example assembly")
    least = min(failures, key=lambda row: (row["face_count"], len(row["document"]["strokes"]), row["key"])) if failures else None
    verify(least == report["least_failure"], "least failure assembly")
    return {"checkpoint_parts_matched": count, "checkpoint_manifest_sha256": manifest_sha}


def audit(input_path, summary_path, source_path, diagnostic_path):
    """Audit a full run only; never rerun naming or turn flags into new proofs."""
    report, report_sha = read_report(input_path)
    small, small_sha = read_report(summary_path)
    source, source_sha = read_report(source_path)
    diagnostic, diagnostic_sha = read_report(diagnostic_path)
    verify(report["full_corpus_run"] is True and report["smoke_limit"] is None, "not a full run")
    verify(report["unseen_holdout"] is False, "known corpus must not be described as unseen")
    verify(report["policies"] == list(POLICIES), "expected exactly three frozen policies")
    verify(small["input"] == {"filename": input_path.name, "sha256": report_sha}, "summary input identity")
    for field, value in small.items():
        if field in report:
            verify(value == report[field], "small/full mismatch: " + field)
    for field, path, value in (("source_evidence", source_path, source_sha),
                               ("diagnostic_evidence", diagnostic_path, diagnostic_sha)):
        verify(report[field]["filename"] == path.name and report[field]["sha256"] == value,
               "evidence identity: " + field)
    sources = report["source_sha256"]
    verify(sources == report["source_sha256_end"] and report["source_hashes_unchanged"] is True,
           "source hashes changed during full run")
    verify({name: sha256((ROOT / name).read_bytes()).hexdigest() for name in sources} == sources,
           "current source bytes differ from recorded full run")
    for older in (source, diagnostic):
        verify(older["source_sha256"] == older["source_sha256_end"], "earlier source start/end mismatch")
        for name, value in older["source_sha256"].items():
            # The old corpus also hashes its generators, which are not rerun
            # here. Verify those bytes separately; the new 16-file runtime
            # manifest must contain all 15 diagnostic algorithm/checker files.
            verify(sha256((ROOT / name).read_bytes()).hexdigest() == value, "earlier source bytes changed: " + name)
            if older is diagnostic or name in sources:
                verify(name in sources and sources[name] == value, "frozen runtime source missing or changed: " + name)

    records, histories, statics = report["drawings"], report["histories"], report["static_inputs"]
    by_key = {key[0]: row for key, row in unique_index(records, ("key",)).items()}
    old = {key[0]: row for key, row in unique_index(source["drawings"], ("key",)).items()}
    verify(set(by_key) == set(old) and len(records) == 7069, "same 7069 source drawings required")
    verify(histories == source["histories"] and statics == source["static_inputs"], "history/static identity changed")
    verify(len(histories) == 363 and len(statics) == 302, "history/static denominators")
    by_history = {key[0]: row for key, row in unique_index(histories, ("key",)).items()}
    unique_index(statics, ("key",))
    old_keys = {r["key"] for r in records if EXISTING in r["cohorts"]}
    new_keys = {r["key"] for r in records if HELDOUT in r["cohorts"]}
    verify(len(old_keys) == 6113 and len(new_keys) == 961 and len(old_keys & new_keys) == 5,
           "6113/961/5 cohort denominator mismatch")
    verify(old_keys | new_keys == set(by_key), "unclassified cohort drawings")
    verify(sum(len(h["prefix_keys"]) for h in histories) == 7678, "prefix references")
    verify(sum(h["cohort"] == EXISTING for h in histories) == 323, "existing history count")
    verify(sorted(h["seed"] for h in histories if h["cohort"] == HELDOUT) == list(range(20261901, 20261941)),
           "same 40 formerly new histories required")
    verify(all(len(h["prefix_keys"]) == 25 for h in histories if h["cohort"] == HELDOUT), "new prefix lengths")
    verify(all(s["cohort"] == EXISTING for s in statics), "static cohort changed")
    expected_aliases = Counter((key, "history_prefix", h["key"], step)
                               for h in histories for step, key in enumerate(h["prefix_keys"]))
    expected_aliases.update((s["geometry_key"], "static", s["key"], None) for s in statics)
    aliases = Counter()
    replay_totals = Counter()
    for row in records:
        key, prior = row["key"], old[row["key"]]
        # Every original source field, not merely labels, must survive unchanged.
        verify({field: row[field] for field in prior if field != "runs"}
               == {field: value for field, value in prior.items() if field != "runs"},
               "source drawing metadata drift: " + key)
        document = row["document"]
        strokes = sorted({tuple(sorted((tuple(s["a"]), tuple(s["b"])))) for s in document["strokes"]})
        verify(digest({"frame": document["frame"], "undirected_stroke_set": strokes}) == key, "drawing hash")
        verify(row["geometry_status"] == "geometry_ok" and row["topology_checked"] is True, "geometry certificate flags")
        verify(set(row["runs"]) == set(POLICIES), "missing/extra policy")
        cohort_from_aliases = set()
        for alias in row["aliases"]:
            if alias["kind"] == "history_prefix":
                aliases[(key, "history_prefix", alias["history"], alias["step"])] += 1
                cohort_from_aliases.add(by_history[alias["history"]]["cohort"])
            else:
                verify(alias["kind"] == "static", "unknown alias kind")
                aliases[(key, "static", alias["source"], None)] += 1
                cohort_from_aliases.add(EXISTING)
        verify(set(row["cohorts"]) == cohort_from_aliases, "cohort/alias disagreement")
        for policy in POLICIES:
            run = row["runs"][policy]
            verify(run["status"] in ("solved", "conflict"), "unclassified outcome")
            verify(run["independent_check_passed"] is True and run["verification"]["passed"] is True,
                   "missing independent verification flag")
            verify(run["backtracks"] == 0 and run["old_colors_read"] is False and run["local_budget"] is None,
                   "no-backtrack/restart contract metadata")
            if run["status"] == "solved":
                verify(run["domains"] == [[c] for c in run["colors"]]
                       and len(run["colors"]) == row["face_count"]
                       and all(type(c) is int and c in (1, 2, 3, 4) for c in run["colors"]),
                       "completed-domain metadata")
            else:
                verify(run["colors"] is None, "conflict has purported coloring")
                if policy in (CLOSED, HALL):
                    verify(run["verification"]["certificate"]["certified"] is True, "baseline conflict certificate")
            if policy in (CLOSED, HALL):
                for field in ("status", "domains", "anchors_by_dart", "colors", "trace_sha256"):
                    verify(run[field] == prior["runs"][policy][field], "frozen baseline result drift: " + field)
            else:
                certificate = run["verification"]
                verify(certificate["method"] == "independent-set-Hall-and-composition-proof-replay",
                       "new-rule verifier identity")
                verify(certificate["propagations"] == run["choices"] + 1, "one proof after every commitment")
                phase_hash = run["propagation_phases_sha256"]
                verify(isinstance(phase_hash, str) and len(phase_hash) == 64
                       and all(c in "0123456789abcdef" for c in phase_hash), "missing full phase identity")
                replay_totals.update({field: value for field, value in certificate.items() if type(value) is int})
    verify(aliases == expected_aliases and sum(aliases.values()) == 7980, "source alias preservation")
    verify(report["independent_checks"] == 21207, "three independent checks per drawing")
    verify(report["baseline_exact_reproductions"] == 14138, "two baseline reproductions per drawing")
    verify(report["diagnostic_exact_reproductions"] == 307, "all diagnostic reproductions recorded")
    if "replay_totals" in report:
        verify(dict(replay_totals) == report["replay_totals"], "replay totals arithmetic")

    # Compare deterministic state and all certificate identities, excluding time.
    diagnostic_rows = unique_index(diagnostic["drawings"], ("key",))
    verify(len(diagnostic_rows) == diagnostic["drawings_checked"] == 307, "diagnostic overlap count")
    matched_fields = ("status", "policy", "domains", "anchors_by_dart", "colors", "choices", "backtracks",
                      "old_colors_read", "local_budget", "trace_sha256", "propagation_phases_sha256", "verification")
    for (key,), row in diagnostic_rows.items():
        verify(row["geometry_sha256"] == by_key[key]["geometry_sha256"], "diagnostic geometry identity")
        for field in matched_fields:
            verify(row["runs"][RELATION][field] == by_key[key]["runs"][RELATION][field],
                   "diagnostic result/certificate drift: " + field)
    rebuilt = check_recount(report)
    verify(len(rebuilt["summary"]) == 9 and len(rebuilt["history_results"]) == 1089
           and len(rebuilt["paired_comparisons"]) == 6 and len(rebuilt["paired_vs_hall"]) == 3,
           "summary/history/paired row count")
    for name, actual in (("distinct_drawings", len(records)), ("history_prefix_references", 7678),
                         ("static_references", 302)):
        if name in small:
            verify(small[name] == actual, "small report denominator: " + name)
    remaining = sorted((r for r in records if r["runs"][RELATION]["status"] != "solved"),
                       key=lambda r: (r["face_count"], len(r["document"]["strokes"]), r["key"]))
    expected_failure = remaining[0]["key"] if remaining else None
    verify((report["least_failure"]["key"] if report["least_failure"] else None) == expected_failure,
           "least failure must use declared face-count/stroke-count/key order")
    verify(small["least_failure_key"] == expected_failure, "summary least-failure identity")
    checkpoint_checks = check_checkpoint_assembly(report, input_path)
    return {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "audit_passed": True, "algorithm_rerun": False,
            "auditor_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "inputs": [{"filename": path.name, "sha256": value} for path, value in (
                (input_path, report_sha), (summary_path, small_sha),
                (source_path, source_sha), (diagnostic_path, diagnostic_sha))],
            "checks": {"current_source_hashes_matched": len(sources), "distinct_drawings": len(records),
                       "source_baseline_results_exactly_reproduced": 2 * len(records),
                       "diagnostic_results_and_phase_hashes_exactly_reproduced": len(diagnostic_rows),
                       "history_prefix_references": 7678, "static_references": 302, "alias_references": 7980,
                       "stored_verified_results": report["independent_checks"],
                       "history_rows_recomputed": len(rebuilt["history_results"]),
                       "summary_rows_recomputed": len(rebuilt["summary"]),
                       "paired_closed_rows_recomputed": len(rebuilt["paired_comparisons"]),
                       "paired_hall_rows_recomputed": len(rebuilt["paired_vs_hall"]),
                       **checkpoint_checks},
            "cohort_denominators": {EXISTING: {"drawings": 6113, "histories": 323, "prefixes": 6678, "statics": 302},
                                    HELDOUT: {"drawings": 961, "histories": 40, "prefixes": 1000, "statics": 0},
                                    "overlap": 5, "combined_drawings": 7069},
            "replay_totals": dict(replay_totals), "recomputed_summary": rebuilt["summary"],
            "recomputed_pairs_closed": rebuilt["paired_comparisons"],
            "recomputed_pairs_hall": rebuilt["paired_vs_hall"],
            "smallest_remaining": [{"key": r["key"], "aliases": r["aliases"],
                                     "input_strokes": len(r["document"]["strokes"]),
                                     "faces_including_exterior": r["face_count"]} for r in remaining[:5]],
            "limits": ["This read-only audit does not rerun geometric or mathematical certificates.",
                       "Recorded verification flags are provenance, not a new proof of satisfiability.",
                       "All groups are now known corpus data; no unseen holdout is claimed.",
                       "Five shared drawings are counted once in the union, not twice.",
                       "Success on this finite corpus is not a proof for all plane maps."]}


def main():
    """Write only a fresh audit log; all four source inputs stay read-only."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=ROOT / "outputs/frontier-restart-all-2026-09-19.json.gz")
    parser.add_argument("--diagnostic", type=Path, default=ROOT / "outputs/relation-frontier-diagnostic-2026-09-19.json.gz")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("choose a new audit output; do not overwrite evidence")
    result = audit(args.input, args.summary, args.source, args.diagnostic)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"audit_passed": result["audit_passed"], "checks": result["checks"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Recheck saved low-color artifacts without running a producer or an oracle.

Byte hashes, coverage, compact/full bindings and summary totals are checked.
Every stored exact-oracle result is independently verified against its original
real adjacency and reconstructed commitments. Propagation traces, scheduling
and exhaustive assignment audits are NOT executed again by this checker.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.exact_extendibility_oracle import verify_exact_result
from scripts.validate_global_restart import digest, write_report
from scripts.validate_quaternary_contacts_v2 import read_report
from scripts.validate_quaternary_low_color import compact_run, summarize, validate_manifest


def require(condition, message):
    """Keep certificate checks enabled when Python optimization is requested."""
    if not condition:
        raise AssertionError(message)


def file_hash(path):
    """Bind exact bytes, including the compressed artifact representation."""
    return sha256(Path(path).read_bytes()).hexdigest()


def portable(path):
    """Only publish project-relative locations, never local machine paths."""
    return Path(path).resolve().relative_to(ROOT).as_posix()


def project_path(name):
    """Resolve a portable saved reference only inside the project directory."""
    require(isinstance(name, str) and not Path(name).is_absolute(), "nonportable saved path")
    result = (ROOT / name).resolve()
    result.relative_to(ROOT)
    return result


def check_file_set(hashes, label):
    """Check every original source or input byte hash without replacing files."""
    require(isinstance(hashes, dict) and hashes, f"missing {label} hashes")
    for name, expected in hashes.items():
        require(file_hash(project_path(name)) == expected, f"{label} hash changed: {name}")


def raw_contacts(saved):
    """Read true inequalities straight from frozen real-edge shore identities.

    This check shares the saved planarized geometry. It does not independently
    recompute geometric intersections, rotations or global face identities.
    """
    geometry = saved["geometry"]
    n = len(geometry["faces"])
    require(digest(geometry) == saved["geometry_sha256"], "saved geometry digest changed")
    require(len(geometry["faceOfDart"]) == 2 * len(geometry["edges"]), "incomplete dart faces")
    lines, edges = [], set()
    for number, edge in enumerate(geometry["edges"]):
        if edge["virtual"]:
            continue
        a, b = geometry["faceOfDart"][2 * number:2 * number + 2]
        require(type(a) is int and type(b) is int and 0 <= a < n and 0 <= b < n,
                "invalid global face identity")
        lines.append({"id": f"E{number}", "left": f"S{a}", "right": f"S{b}",
                      "kind": "bridge" if a == b else "separator"})
        if a != b:
            edges.add(tuple(sorted((a, b))))
    return [f"S{i}" for i in range(n)], lines, [list(pair) for pair in sorted(edges)]


def check_run(saved, scenario, run, resources):
    """Reconstruct commitment inputs and verify all stored exact certificates."""
    result, audit = run["outcome"], run["audit"]
    sides, lines, edges = raw_contacts(saved)
    side_index = {side: i for i, side in enumerate(sides)}
    require(run["scenario"] == scenario["id"] and run["anchors"] == scenario["anchors"],
            "run scenario/anchors differ from frozen input")
    require(run["policy"] in ("plain", "guarded") and
            result["probe"] is (run["policy"] == "guarded"), "policy/probe binding differs")
    require(result["decision_limit"] == resources["decision_limit"] and
            result["probe_limit"] == resources["probe_limit"], "producer budget changed")
    require(audit["passed"] is True and result["oracle_feedback_to_producer"] is False and
            audit["oracle_feedback_to_producer"] is False, "audit or no-feedback contract differs")
    original = result["original_input"]
    require(original["sides"] == sides and original["lines"] == lines and
            original["anchors"] == scenario["anchors"] and not original.get("states") and
            not original.get("equal_names"), "producer input differs from original real contacts")
    phases, events, steps = result["phases"], result["events"], audit["steps"]
    require(bool(phases) and phases[0]["document"] == original, "wrong initial phase input")
    require(len(events) == len(steps), "event-to-step coverage differs")
    require(audit["phase_count"] == len(phases) == len(audit["phase_audits"]), "phase count differs")
    require(audit["trace_steps_checked"] == sum(a["trace_steps_checked"] for a in audit["phase_audits"]),
            "stored trace summary differs")
    records, referenced, status_counts = audit["oracle_records"], set(), Counter()
    require(isinstance(records, list) and bool(records), "missing raw oracle records")
    signatures = set()
    for item in records:
        raw = item["input"]
        anchors = raw["anchors"]
        require(raw["n"] == len(sides) and raw["edges"] == edges, "oracle graph differs from real contacts")
        require(all(isinstance(pair, list) and len(pair) == 2 for pair in anchors), "malformed anchors")
        fixed = dict(anchors)
        require(len(fixed) == len(anchors) and anchors == [list(p) for p in sorted(fixed.items())],
                "duplicate or noncanonical oracle anchors")
        signature = tuple(tuple(p) for p in anchors)
        require(signature not in signatures, "duplicate oracle cache signature")
        signatures.add(signature)
        require(item["result"]["node_limit"] == resources["node_limit"], "oracle budget differs")
        verified = verify_exact_result(raw["n"], edges, fixed, item["result"])
        require(verified == item["verification"] and verified["passed"], "stored certificate verification differs")
        status_counts[item["result"]["status"]] += 1

    def oracle_at(number, expected_anchors):
        """Bind each step reference to precisely the actual cumulative promises."""
        require(type(number) is int and 0 <= number < len(records), "oracle index outside records")
        referenced.add(number)
        item = records[number]
        require(item["input"]["anchors"] == [list(p) for p in sorted(expected_anchors.items())],
                "oracle input imported extra restrictions or omitted a commitment")
        return item

    committed = {side_index[side]: color for side, color in scenario["anchors"].items()}
    initial = oracle_at(audit["initial_oracle_index"], committed)
    initial_status = initial["result"]["status"]
    if "expected_raw_status" in scenario:
        require(initial_status in (scenario["expected_raw_status"], "unknown"),
                "historical initial state has opposite conclusive status")
    commitments = {"safe": 0, "unsafe": 0, "unknown": 0, "preexisting_unsat": 0}
    rejections = {"exact_unsat": 0, "unknown": 0}
    first_bad, current_phase, probes, rejection_events = None, 0, 0, 0
    s10_events = []
    for event_number, (event, step) in enumerate(zip(events, steps)):
        require(step["event_index"] == event_number, "step order differs")
        for field in ("kind", "side", "symbol", "before_phase", "trial_phase", "after_phase"):
            require(step[field] == event[field], "step/event field differs: " + field)
        require(event["before_phase"] == current_phase, "event skips current persistent phase")
        for field in ("before_phase", "after_phase"):
            require(type(event[field]) is int and 0 <= event[field] < len(phases), "invalid phase reference")
        side, symbol = event["side"], event["symbol"]
        require(side in side_index and type(symbol) is int and 1 <= symbol <= 4, "invalid commitment literal")
        before = phases[current_phase]["outcome"]
        require(before["status"] == "underdetermined", "event after terminal phase")
        candidates = before["domains"][side_index[side]]
        require(event["candidates_before"] == candidates and len(candidates) > 1 and symbol == min(candidates),
                "step no longer represents low-color preference")
        require(side_index[side] not in committed, "commitment overwrites an earlier explicit name")
        proposed = {**committed, side_index[side]: symbol}
        before_oracle = oracle_at(step["before_oracle_index"], committed)
        trial_oracle = oracle_at(step["trial_oracle_index"], proposed)
        before_status, trial_status = before_oracle["result"]["status"], trial_oracle["result"]["status"]
        if result["probe"]:
            trial_phase = event["trial_phase"]
            require(type(trial_phase) is int and 0 <= trial_phase < len(phases) and
                    phases[trial_phase]["kind"] == "trial", "missing guarded trial phase")
            require(phases[trial_phase]["document"]["anchors"] ==
                    {sides[i]: c for i, c in proposed.items()}, "trial phase anchors differ")
            probes += 1
        else:
            require(event["trial_phase"] is None, "plain policy unexpectedly used trial propagation")
        if event["kind"] == "reject":
            require(result["probe"] and phases[event["trial_phase"]]["outcome"]["status"] == "conflict",
                    "rejection lacks a recorded propagation conflict")
            require(trial_status != "sat", "rejected name has a verified raw witness")
            extension = "refuted"
            rejections["exact_unsat" if trial_status == "unsat" else "unknown"] += 1
            rejection_events += 1
        else:
            require(event["kind"] == "commit", "unsupported event kind")
            extension = ("preexisting_unsat" if before_status == "unsat" else
                         "unknown" if "unknown" in (before_status, trial_status) else
                         "unsafe" if trial_status == "unsat" else "safe")
            commitments[extension] += 1
            committed = proposed
        after_oracle = oracle_at(step["after_oracle_index"], committed)
        require(step["before_status"] == before_status and
                step["after_status"] == after_oracle["result"]["status"] and
                step["extendibility"] == extension, "step status/classification differs")
        current_phase = event["after_phase"]
        require(phases[current_phase]["document"]["anchors"] ==
                {sides[i]: c for i, c in committed.items()}, "persistent anchors differ")
        if extension == "unsafe" and first_bad is None:
            first_bad = {**step, "event": event, "before": before_oracle, "after": after_oracle}
        if side == "S10":
            s10_events.append({"event_index": event_number, "kind": event["kind"],
                               "symbol": symbol, "candidates_before": candidates,
                               "before_status": before_status, "trial_status": trial_status,
                               "after_status": after_oracle["result"]["status"], "extendibility": extension})
    require(referenced == set(range(len(records))), "unreferenced stored oracle evidence")
    require(audit["commitment_counts"] == commitments and audit["rejection_counts"] == rejections,
            "exact step counters differ")
    require(audit["oracle_unknown"] == status_counts["unknown"], "unknown oracle count differs")
    require(audit["first_bad_commitment"] == first_bad, "first unsafe commitment evidence/link differs")
    require(result["choices"] == sum(commitments.values()) and result["probes"] == probes and
            result["rejections"] == rejection_events, "producer event telemetry differs")
    require(result["final_phase"] == current_phase, "final phase reference differs")
    final = phases[current_phase]["outcome"]
    for name in ("name_states", "domains", "colors"):
        require(result[name] == final[name], "final phase binding differs: " + name)
    require(result["status"] == ("incomplete" if final["status"] == "underdetermined" else final["status"]),
            "final status binding differs")
    if result["status"] == "solved":
        colors = [result["colors"][side] for side in sides]
        require(all(type(c) is int and 1 <= c <= 4 for c in colors) and
                all(colors[a] != colors[b] for a, b in edges) and
                all(colors[i] == c for i, c in committed.items()), "final color witness violates raw graph")
    diagnostic = None
    if "first-commit" in scenario["id"]:
        diagnostic = {"key": saved["key"], "scenario": scenario["id"], "policy": run["policy"],
                      "initial_oracle_status": initial_status, "final_status": result["status"],
                      "initial_S10": phases[0]["outcome"]["name_states"].get("S10"),
                      "final_S10": result["name_states"].get("S10"), "S10_events": s10_events,
                      "choices": result["choices"], "probes": probes, "rejections": rejection_events,
                      "first_bad_event_index": None if first_bad is None else first_bad["event_index"]}
    return {"oracle_statuses": dict(status_counts), "oracle_records": len(records),
            "steps": len(steps), "first_bad_cases": int(first_bad is not None),
            "final_colorings": int(result["status"] == "solved"), "diagnostic": diagnostic}


def check_artifacts(manifest_path, report_path, checkpoint_dir):
    """Read each checkpoint once and reverify every persisted exact certificate."""
    manifest_path, report_path, checkpoint_dir = map(Path, (manifest_path, report_path, checkpoint_dir))
    manifest_hash, report_hash, checker_hash = (file_hash(manifest_path), file_hash(report_path), file_hash(__file__))
    manifest, report = read_report(manifest_path), read_report(report_path)
    require(manifest["schema_version"] == report["schema_version"] == 1, "unsupported report schema")
    require(report["manifest_sha256"] == manifest_hash and
            project_path(report["manifest_path"]) == manifest_path.resolve(), "manifest binding differs")
    require(report["manifest_filename"] == manifest_path.name, "manifest filename differs")
    require(project_path(report["checkpoint_directory"]) == checkpoint_dir.resolve(), "checkpoint directory differs")
    require(report["source_sha256"] == manifest["source_sha256"] and report["counts"] == manifest["counts"] and
            report["resources"] == manifest["resources"] and report["scope"] == manifest["scope"],
            "report declaration differs from frozen manifest")
    check_file_set(manifest["source_sha256"], "source")
    check_file_set(manifest["input_artifact_sha256"], "input")
    # This shared helper only reconstructs the deterministic input inventory and
    # checks provenance. It does not call either policy or the exact solver.
    validate_manifest(manifest)
    saved_records, declared_parts = manifest["records"], report["checkpoint_hashes"]
    require(len({r["key"] for r in saved_records}) == len(saved_records), "duplicate manifest drawings")
    batch_size = manifest["resources"]["batch_size"]
    expected_parts = [f"part-{i:05d}.json.gz" for i in range((len(saved_records) + batch_size - 1) // batch_size)]
    require([p["filename"] for p in declared_parts] == expected_parts, "checkpoint part coverage/order differs")
    require(sorted(p.name for p in checkpoint_dir.glob("part-*.json.gz")) == expected_parts,
            "missing or extra checkpoint part")
    require(not (checkpoint_dir / "failure.json").exists(), "failure scene exists beside purported complete report")
    counts, statuses, rebuilt, diagnostics = Counter(), Counter(), [], []
    for part_number, part in enumerate(declared_parts):
        path = checkpoint_dir / part["filename"]
        require(file_hash(path) == part["sha256"], "checkpoint byte hash differs")
        rows = read_report(path)
        expected = saved_records[part_number * batch_size:(part_number + 1) * batch_size]
        require(len(rows) == part["drawings"] == len(expected), "checkpoint batch size differs")
        for row, saved in zip(rows, expected):
            require(not row.get("failed"), "failed scene appears as a completed checkpoint")
            require(row["key"] == saved["key"] and row["geometry_sha256"] == saved["geometry_sha256"] and
                    row["families"] == saved["families"] and row["new_geometry"] == saved["new_geometry"],
                    "checkpoint drawing binding differs")
            expected_pairs = [(s["id"], p) for s in saved["scenarios"] for p in manifest["policies"]]
            require([(r["scenario"], r["policy"]) for r in row["runs"]] == expected_pairs,
                    "checkpoint scenario/policy coverage differs")
            scenarios = {s["id"]: s for s in saved["scenarios"]}
            for run in row["runs"]:
                checked = check_run(saved, scenarios[run["scenario"]], run, manifest["resources"])
                counts["policy_runs"] += 1
                for field in ("oracle_records", "steps", "first_bad_cases", "final_colorings"):
                    counts[field] += checked[field]
                statuses.update(checked["oracle_statuses"])
                if checked["diagnostic"] is not None:
                    diagnostics.append(checked["diagnostic"])
            rebuilt.append({k: v for k, v in row.items() if k != "runs"} |
                           {"checkpoint": part["filename"], "runs": [compact_run(r) for r in row["runs"]]})
        counts["drawings"] += len(rows)
        counts["checkpoint_parts"] += 1
        require(file_hash(path) == part["sha256"], "checkpoint changed while checking")
        if (part_number + 1) % 16 == 0 or part_number + 1 == len(declared_parts):
            print(json.dumps({"artifact_drawings_checked": counts["drawings"],
                              "total": len(saved_records)}), flush=True)
    require(counts["drawings"] == manifest["counts"]["drawings"] and
            counts["policy_runs"] == manifest["counts"]["policy_runs"], "overall coverage differs")
    require(rebuilt == report["records"], "compact report does not exactly bind all full checkpoint runs")
    require(summarize(rebuilt, manifest) == report["summary"], "recomputed summary differs")
    require(len(diagnostics) == 4, "expected two historical S10 states times two policies")
    check_file_set(manifest["source_sha256"], "source")
    check_file_set(manifest["input_artifact_sha256"], "input")
    require(file_hash(manifest_path) == manifest_hash and file_hash(report_path) == report_hash and
            file_hash(__file__) == checker_hash, "checker or input changed during artifact verification")
    return {
        "schema_version": 1, "passed": True, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "manifest_path": portable(manifest_path), "manifest_sha256": manifest_hash,
        "report_path": portable(report_path), "report_sha256": report_hash,
        "checkpoint_directory": portable(checkpoint_dir), "checkpoint_hashes": declared_parts,
        "checker_source_sha256": {portable(__file__): checker_hash},
        "source_files_checked": len(manifest["source_sha256"]),
        "input_artifacts_checked": len(manifest["input_artifact_sha256"]),
        "counts": dict(counts), "oracle_statuses_reverified": dict(statuses),
        "summary_recomputed": True, "compact_full_bindings_checked": True,
        "original_graph_and_commitment_inputs_reconstructed": True,
        "first_bad_evidence_relinked": True, "historical_S10_states": diagnostics,
        "producer_runs": 0, "oracle_search_runs": 0,
        "scope": "Saved-artifact and exact-certificate recheck; shared frozen input-inventory, compacting and summary helpers; saved planarized geometry shared; no new producer run, oracle search, propagation-trace replay, scheduler validation or full assignment enumeration. Unknown remains inconclusive.",
    }


def main():
    """Write one new portable JSON result only after the complete recheck passes."""
    parser = ArgumentParser(description=__doc__)
    for name in ("manifest", "report", "checkpoint-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "checker output exists; choose a new filename")
    report = check_artifacts(args.manifest, args.report, args.checkpoint_dir)
    write_report(args.output, report)
    print(json.dumps({"passed": report["passed"], "counts": report["counts"],
                      "oracle_statuses_reverified": report["oracle_statuses_reverified"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

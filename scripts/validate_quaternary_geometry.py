"""Freeze and audit quaternary contacts on actual archived planar drawings.

Geometry export and every input anchor are fixed before the new producer runs.
The producer only propagates; exact completion is an offline audit and never
supplies a choice. Historical full colors are a separately labelled roundtrip
input, not a solution discovered by this prototype.
"""

from argparse import ArgumentParser
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.whole_lines import build_whole_lines
from scripts.current_corpus import stroke_set_key
from scripts.quaternary_contact_model import propagate_contacts
from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.validate_global_restart import canonical_document, digest, export_geometries, write_report
from scripts.validate_quaternary_contacts_v2 import read_report, sources as contact_sources

GRID = "outputs/extendibility-grid-subsets-manifest-2026-09-21.json"
ARCHIVED = "outputs/prior-operations-factorial-2026-09-20.json.gz"
COMPLETE = "outputs/structural-restart-full-2026-09-21.json.gz"
REGRESSIONS = "examples/quaternary-real-regressions-2026-09-21.json"
PROTOCOL = "docs/QUATERNARY_GEOMETRY_PROTOCOL-2026-09-21.md"
PRIMARY = "one-bounded-anchor"
LEGACY = "legacy-frame-anchors"
ROUNDTRIP = "archived-complete-certificate"
MODES = (PRIMARY, LEGACY)
POLICY = "mother-peer-structural-reuse-v1"


def require(condition, message):
    """Reject incomplete or changed evidence even if Python assertions are off."""
    if not condition:
        raise AssertionError(message)


def file_hash(name):
    """Hash only a repository-relative source or input path."""
    return sha256((ROOT / name).read_bytes()).hexdigest()


def source_hashes():
    """Keep old sources fixed and bind the adapter, auditor and experiment."""
    current = contact_sources()
    for archive in (GRID, COMPLETE):
        frozen = read_report(ROOT / archive)["source_sha256"]
        for name, expected in frozen.items():
            actual = file_hash(name)
            require(actual == expected, "frozen dependency changed: " + name)
            current[name] = actual
    for name in ("scripts/quaternary_geometry_adapter.py", "scripts/audit_quaternary_geometry.py",
                 "scripts/validate_quaternary_geometry.py", "tests/test_quaternary_geometry_adapter.py",
                 "tests/test_quaternary_geometry_audit.py", "tests/test_quaternary_geometry_experiment.py",
                 "scripts/exact_extendibility_oracle.py", PROTOCOL, REGRESSIONS):
        current[name] = file_hash(name)
    return current


def input_inventory():
    """Select the whole small corpus and all 49 fixed historical controls."""
    grid = read_report(ROOT / GRID)["inventory"]
    prior = read_report(ROOT / ARCHIVED)
    full = read_report(ROOT / COMPLETE)
    regressions = read_report(ROOT / REGRESSIONS)
    require(grid["generation_complete"] and len(grid["records"]) == 4096, "wrong grid inventory")
    require(len(prior["records"]) == 49 and len(full["drawings"]) == 7069, "wrong archived inventory")
    old_by_key = {row["key"]: row for row in full["drawings"]}
    records = {}

    def insert(key, drawing, family):
        document = canonical_document(drawing)
        require(stroke_set_key(document) == key, "drawing key differs")
        if key not in records:
            records[key] = {"key": key, "document": document, "families": [], "extra_scenarios": []}
        row = records[key]
        require(row["document"] == document, "same key has a different drawing")
        if family not in row["families"]:
            row["families"].append(family)
        return row

    for saved in grid["records"]:
        row = insert(saved["key"], saved["document"], "grid-subsets")
        row["subset_mask"] = saved["subset_mask"]
    for saved in prior["records"]:
        old = old_by_key[saved["key"]]
        row = insert(saved["key"], old["document"], "historical-controls")
        require(saved["geometry_sha256"] == old["geometry_sha256"], "old geometry archives disagree")
        outcome = old["runs"][POLICY]
        require(outcome["status"] == "solved", "archived complete certificate missing")
        row.update(expected_geometry_sha256=old["geometry_sha256"],
                   archived_colors=outcome["colors"], failure_cohorts=saved["failure_cohorts"],
                   historical_statuses={policy: result["status"] for policy, result in old["runs"].items()})
    for case in regressions["cases"]:
        key = stroke_set_key(canonical_document(case["drawing"]))
        row = insert(key, case["drawing"], "historical-commitment-diagnostic")
        row["extra_scenarios"].append({"id": case["id"], "anchors": case["anchors"],
                                       "expected_raw_status": case["expected_raw_status"],
                                       "source_case_id": case["id"]})
    histories = [{"key": h["key"], "prefix_keys": h["prefix_keys"]} for h in grid["histories"]]
    return {"records": [records[key] for key in sorted(records)], "grid_histories": histories,
            "selection": "all 4096 grid masks, all 49 frozen historical controls, all named commitment diagnostics",
            "deduplication": "canonical input stroke set; no face-graph isomorphism or segmentation reduction"}


def standard_scenarios(geometry, saved):
    """Separate one bounded anchor from old two-anchor and supplied-result tests."""
    n, outer = len(geometry["faces"]), geometry["outerFace"]
    bounded = next(side for side in range(n) if side != outer)
    model = build_whole_lines(geometry)
    frame = next(line for line in model.lines if line["id"] == "frame")
    first = frame["spans"][0]["dart"]
    legacy = {f"S{model.plane_map.face_of_dart[first]}": 1,
              f"S{model.plane_map.face_of_dart[first ^ 1]}": 2}
    require(len(legacy) == 2, "frame sides must be different")
    scenarios = [{"id": PRIMARY, "anchors": {f"S{bounded}": 1}},
                 {"id": LEGACY, "anchors": legacy}]
    if "archived_colors" in saved:
        require(len(saved["archived_colors"]) == n, "old color identities changed")
        scenarios.append({"id": ROUNDTRIP,
                          "anchors": {f"S{i}": color for i, color in enumerate(saved["archived_colors"])},
                          "expected_raw_status": "sat", "expected_producer_status": "solved"})
    scenarios.extend(saved["extra_scenarios"])
    require(len({row["id"] for row in scenarios}) == len(scenarios), "duplicate scenario identity")
    return scenarios


def prepare(path, *, workers=4, batch_size=32, assignment_limit=262144, node_limit=200000):
    """Export geometry and freeze actual anchors before any prototype run."""
    require(not path.exists(), "manifest exists; choose a new path")
    require(all(type(v) is int and v > 0 for v in (workers, batch_size, assignment_limit, node_limit)),
            "resource bounds must be positive literal integers")
    hashes = source_hashes()
    inputs = {name: file_hash(name) for name in (GRID, ARCHIVED, COMPLETE, REGRESSIONS)}
    inventory = input_inventory()
    rows = []
    for start in range(0, len(inventory["records"]), 128):
        batch = inventory["records"][start:start + 128]
        for saved, exported in zip(batch, export_geometries(batch)):
            require(exported["status"] == "geometry_ok" and exported["key"] == saved["key"],
                    "input geometry rejected or replaced")
            geometry = exported["geometry"]
            checksum = digest(geometry)
            if "expected_geometry_sha256" in saved:
                require(checksum == saved["expected_geometry_sha256"], "archived geometry changed")
            rows.append({**saved, "geometry": geometry, "geometry_sha256": checksum,
                         "scenarios": standard_scenarios(geometry, saved)})
    require(len(rows) == len(inventory["records"]), "geometry export omitted inputs")
    require(hashes == source_hashes() and inputs == {name: file_hash(name) for name in inputs},
            "sources or inputs changed during predeclaration")
    counts = {"distinct_drawings": len(rows), "scenarios": sum(len(row["scenarios"]) for row in rows),
              "families": dict(Counter(f for row in rows for f in row["families"])),
              "modes": dict(Counter(s["id"] for row in rows for s in row["scenarios"])),
              "grid_history_count": len(inventory["grid_histories"]),
              "grid_prefix_references": sum(len(h["prefix_keys"]) for h in inventory["grid_histories"])}
    manifest = {"schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "source_sha256": hashes, "input_artifact_sha256": inputs,
                "resources": {"workers": workers, "batch_size": batch_size,
                              "assignment_limit": assignment_limit, "node_limit": node_limit},
                "selection": inventory["selection"], "deduplication": inventory["deduplication"],
                "counts": counts, "records": rows, "grid_histories": inventory["grid_histories"],
                "producer_runs_during_prepare": 0, "oracle_runs_during_prepare": 0}
    write_report(path, manifest)
    return counts


def run_record(payload):
    """Audit one geometry and its separately declared input restrictions."""
    from scripts.audit_quaternary_geometry import audit_run
    saved, resources = payload
    geometry = saved["geometry"]
    require(digest(geometry) == saved["geometry_sha256"], "frozen geometry corrupted")
    runs, details = [], []
    for scenario in saved["scenarios"]:
        adapted = outcome = audit = None
        try:
            adapted = adapt_exported_geometry(geometry, anchors=scenario["anchors"], drawing=saved["document"])
            start = perf_counter()
            outcome = propagate_contacts(adapted["contact_document"])
            production_seconds = perf_counter() - start
            start = perf_counter()
            audit = audit_run(geometry, adapted, outcome, assignment_limit=resources["assignment_limit"],
                              node_limit=resources["node_limit"])
            audit_seconds = perf_counter() - start
            require(audit["passed"], "geometry or contact audit rejected output")
            if "expected_raw_status" in scenario:
                require(audit["oracle"]["status"] == scenario["expected_raw_status"],
                        "named control has a different exact status")
            if "expected_producer_status" in scenario:
                require(outcome["status"] == scenario["expected_producer_status"], "complete input roundtrip failed")
        except Exception as error:
            # Return, rather than discard, the exact scene rejected in a worker.
            # The parent saves the whole completed batch and stops this version.
            return {"failed": True, "key": saved["key"], "scenario": scenario,
                    "document": saved["document"], "geometry": geometry, "adapted": adapted,
                    "outcome": outcome, "audit": audit, "completed_runs": runs,
                    "error_type": type(error).__name__, "error": str(error)}
        runs.append({"id": scenario["id"], "anchors": scenario["anchors"], "status": outcome["status"],
                     "name_states": outcome["name_states"], "colors": outcome["colors"],
                     "choices": outcome["choices"], "backtracks": outcome["backtracks"],
                     "producer_seconds": production_seconds, "audit_seconds": audit_seconds,
                     "producer_sha256": digest(outcome), "adapted_sha256": digest(adapted), "audit": audit})
        if ("historical-controls" in saved["families"] or saved.get("subset_mask") in (0, 4095)
                or "source_case_id" in scenario):
            details.append({"id": scenario["id"], "adapted": adapted, "outcome": outcome, "audit": audit})
    require(digest(geometry) == saved["geometry_sha256"], "producer or audit changed geometry")
    return {"key": saved["key"], "families": saved["families"], "geometry_sha256": saved["geometry_sha256"],
            "face_count": len(geometry["faces"]), "real_edges": sum(not e["virtual"] for e in geometry["edges"]),
            "virtual_connectors": sum(e["virtual"] for e in geometry["edges"]),
            "real_bridges": len(geometry["real_bridge_edge_ids"]), "runs": runs, "detailed": details}


def summarize(rows, manifest):
    """Keep completion, oracle conformance and supplied-certificate checks apart."""
    by_mode = {}
    for mode in manifest["counts"]["modes"]:
        runs = [r for row in rows for r in row["runs"] if r["id"] == mode]
        by_mode[mode] = {"cases": len(runs), "producer_statuses": dict(Counter(r["status"] for r in runs)),
                         "oracle_statuses": dict(Counter(r["audit"]["oracle"]["status"] for r in runs)),
                         "checks_passed": sum(r["audit"]["passed"] for r in runs),
                         "full_enumeration": dict(Counter(r["audit"]["full_enumeration"]["status"] for r in runs)),
                         "literal_assignments_checked": sum(r["audit"]["full_enumeration"]["literal_assignments_checked"] for r in runs),
                         "legal_assignments_preserved": sum(r["audit"]["full_enumeration"]["legal_assignments"] or 0 for r in runs),
                         "trace_steps_independently_checked": sum(r["audit"]["bounded_metadata_trace"]["trace_steps_checked"] for r in runs),
                         "oracle_unknown": sum(r["audit"]["oracle"]["status"] == "unknown" for r in runs),
                         "producer_seconds": sum(r["producer_seconds"] for r in runs),
                         "audit_seconds": sum(r["audit_seconds"] for r in runs)}
    by_key = {row["key"]: row for row in rows}
    histories = {}
    for mode in MODES:
        passed = complete = 0
        for history in manifest["grid_histories"]:
            prefix_runs = [next(r for r in by_key[key]["runs"] if r["id"] == mode)
                           for key in history["prefix_keys"]]
            passed += all(r["audit"]["passed"] for r in prefix_runs)
            complete += all(r["status"] == "solved" for r in prefix_runs)
        histories[mode] = {"histories": len(manifest["grid_histories"]),
                           "all_prefixes_checked": passed, "all_prefixes_colored": complete}
    return {"all_checks_passed": all(r["audit"]["passed"] for row in rows for r in row["runs"]),
            "distinct_drawings": len(rows), "modes": by_mode, "grid_histories": histories,
            "face_count_range": [min(r["face_count"] for r in rows), max(r["face_count"] for r in rows)],
            "drawings_with_real_bridges": sum(r["real_bridges"] > 0 for r in rows),
            "drawings_with_virtual_connectors": sum(r["virtual_connectors"] > 0 for r in rows)}


def execute(manifest_path, output, checkpoint_dir):
    """Write exclusive completed batches and retain the first failed scene."""
    require(not output.exists() and not checkpoint_dir.exists(), "choose new report/checkpoint paths")
    manifest_hash = sha256(manifest_path.read_bytes()).hexdigest()
    manifest = read_report(manifest_path)
    require(manifest["source_sha256"] == source_hashes(), "sources drifted after freeze")
    require(all(file_hash(name) == expected for name, expected in manifest["input_artifact_sha256"].items()),
            "input artifact changed after freeze")
    require(manifest["counts"]["distinct_drawings"] == len(manifest["records"]), "wrong declared count")
    inventory = input_inventory()
    require(manifest["grid_histories"] == inventory["grid_histories"], "manifest altered history prefixes")
    require([r["key"] for r in manifest["records"]] == [r["key"] for r in inventory["records"]],
            "manifest changed the predeclared geometry selection")
    for frozen, original in zip(manifest["records"], inventory["records"]):
        require(all(frozen.get(key) == value for key, value in original.items()), "manifest altered a source input")
        require(frozen["geometry_sha256"] == digest(frozen["geometry"]), "frozen geometry hash differs")
        require(frozen["scenarios"] == standard_scenarios(frozen["geometry"], original),
                "manifest altered an input anchor scenario")
    checkpoint_dir.mkdir(parents=True, exist_ok=False)
    resources = manifest["resources"]
    rows, parts = [], []
    start = perf_counter()
    with ProcessPoolExecutor(max_workers=resources["workers"]) as pool:
        for offset in range(0, len(manifest["records"]), resources["batch_size"]):
            batch = manifest["records"][offset:offset + resources["batch_size"]]
            try:
                piece = list(pool.map(run_record, [(row, resources) for row in batch]))
            except Exception as error:
                write_report(checkpoint_dir / "failure.json", {"status": "failed", "coverage": "incomplete",
                             "offset": offset, "input_keys": [r["key"] for r in batch],
                             "completed_drawings": len(rows), "error": str(error)})
                raise
            require([r["key"] for r in piece] == [r["key"] for r in batch], "worker coverage mismatch")
            failures = [item for item in piece if item.get("failed")]
            if failures:
                write_report(checkpoint_dir / "failure.json", {"status": "failed", "coverage": "incomplete",
                             "offset": offset, "completed_drawings_in_previous_batches": len(rows),
                             "first_failed_key": failures[0]["key"], "batch_results": piece})
                raise AssertionError("formal scene rejected: " + failures[0]["key"]
                                     + "/" + failures[0]["scenario"]["id"] + ": " + failures[0]["error"])
            part = checkpoint_dir / f"part-{len(parts):05d}.json.gz"
            write_report(part, piece)
            parts.append({"filename": part.name, "sha256": sha256(part.read_bytes()).hexdigest()})
            rows.extend(piece)
            if len(parts) % 8 == 0 or len(rows) == len(manifest["records"]):
                print(json.dumps({"checked_drawings": len(rows), "total": len(manifest["records"])}), flush=True)
    require(manifest["source_sha256"] == source_hashes(), "sources changed during formal run")
    require(all(file_hash(name) == expected for name, expected in manifest["input_artifact_sha256"].items()),
            "input artifact changed during formal run")
    require(sha256(manifest_path.read_bytes()).hexdigest() == manifest_hash, "manifest changed during formal run")
    summary = summarize(rows, manifest)
    write_report(output, {"schema_version": 1, "manifest_filename": manifest_path.name,
                          "manifest_sha256": manifest_hash,
                          "source_sha256": manifest["source_sha256"], "summary": summary,
                          "records": rows, "checkpoint_hashes": parts,
                          "wall_seconds": perf_counter() - start,
                          "scope": "Candidate propagation on declared real geometries; offline oracle never supplies a producer choice. Supplied complete certificates are separate roundtrip tests."})
    return summary


def run_drawing(document, mode=PRIMARY, *, assignment_limit=262144, node_limit=200000):
    """Run one actual drawing with a declared initialization and no old colors."""
    from scripts.audit_quaternary_geometry import audit_run
    require(mode in MODES, "unknown initialization mode")
    canonical = canonical_document(document)
    key = stroke_set_key(canonical)
    exported = export_geometries([{"key": key, "document": canonical}])[0]
    require(exported["status"] == "geometry_ok", "drawing geometry rejected: " + str(exported.get("errors")))
    geometry = exported["geometry"]
    scenario = next(s for s in standard_scenarios(geometry, {"extra_scenarios": []}) if s["id"] == mode)
    adapted = adapt_exported_geometry(geometry, anchors=scenario["anchors"], drawing=canonical)
    outcome = propagate_contacts(adapted["contact_document"])
    audit = audit_run(geometry, adapted, outcome, assignment_limit=assignment_limit, node_limit=node_limit)
    return {"schema_version": 1, "original_input": document, "drawing": canonical,
            "canonicalization": "undirected stroke-set sorting/deduplication before geometry; provenance indices refer to the canonical drawing",
            "key": key, "initialization": scenario,
            "geometry": geometry, "geometry_sha256": digest(geometry), "adapted": adapted,
            "outcome": outcome, "audit": audit,
            "ignored_top_level_fields": sorted(set(document) - {"frame", "strokes"}),
            "scope": "One candidate-propagation attempt. Oracle witness is offline evidence, not producer coloring."}


def main():
    """Expose frozen-corpus execution; old source/output paths are read only."""
    require(not sys.flags.optimize, "run without -O for legacy geometry checks")
    parser = ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    pre = commands.add_parser("prepare")
    pre.add_argument("--manifest", type=Path, required=True)
    pre.add_argument("--workers", type=int, default=4)
    run = commands.add_parser("run")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--checkpoint-dir", type=Path, required=True)
    single = commands.add_parser("map")
    single.add_argument("input", type=Path)
    single.add_argument("--mode", choices=MODES, default=PRIMARY)
    single.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.manifest, workers=args.workers)
    elif args.command == "run":
        result = execute(args.manifest, args.output, args.checkpoint_dir)
    else:
        require(not args.output.exists(), "choose a new output path")
        hashes, input_hash = source_hashes(), sha256(args.input.read_bytes()).hexdigest()
        document = json.loads(args.input.read_text(encoding="utf-8-sig"))
        report = run_drawing(document, args.mode)
        require(hashes == source_hashes() and input_hash == sha256(args.input.read_bytes()).hexdigest(),
                "source or input changed during single-map run")
        report.update(source_sha256=hashes, input_sha256=input_hash)
        write_report(args.output, report)
        result = {"producer_status": report["outcome"]["status"], "oracle_status": report["audit"]["oracle"]["status"],
                  "checks_passed": report["audit"]["passed"], "output": args.output.name}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

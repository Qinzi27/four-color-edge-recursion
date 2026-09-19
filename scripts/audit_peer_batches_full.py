"""Independently audit the peer-batch full-corpus experiment.

Recount every stored result and reference, rehash every checkpoint, reconstruct
all geometry, and directly validate every completed coloring and line orbit.
All saved failure/diagnostic proofs are replayed; only a declared hash sample
plus the forty fixed diagnostics is newly solved. This is NOT a second full solve.
The producer's summarizer and initialization-summary functions are not imported.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.peer_batches import restart_peer_batch_names
from scripts.validate_frontier_restart import (
    file_sha, independent_geometry, json_value, read_json, verify_result,
)
from scripts.validate_global_restart import digest, export_geometries, write_report
from scripts.validate_peer_batches import independent_batches, verify_run
from scripts.analyze_line_generations import derive_generations, extract_whole_contacts
from fourcolor.whole_lines import build_whole_lines

POLICY = "peer-batch-ready-sides-v4"
BASELINE = "stage-anchored-level-sides-v3"
SOURCE_SHA256 = "87250016644ba5c9c25573e0894af563eb451cd43915c11bad73927308af4910"
SELECTION_SHA256 = "fcf7338222accfce47c6ee1963beaacb6079868f6910124c463a0bafefb38b8a"
COHORTS = ("combined", "existing-corpus", "new-seeds-20261901-20261940")
MODES = ("first-through-mother-retained-side", "frame-interior-no-eligible-through-mother")


def require(condition, reason):
    """Keep audit guards active independently of Python assertion optimization."""
    if not condition:
        raise AssertionError(reason)


def paired(values):
    """Recompute paired success counts without the producer's counting helper."""
    result = dict(both_solved=0, improved=0, regressed=0, both_not_solved=0)
    for old, new in values:
        result["both_solved" if old and new else "improved" if new else
               "regressed" if old else "both_not_solved"] += 1
    return result


def audit_summaries(report):
    """Reconstruct all drawing/history/static totals and status transitions."""
    rows = report["drawings"]
    by_key = {row["key"]: row for row in rows}
    require(len(by_key) == len(rows), "duplicate drawing key")
    policies = (BASELINE, POLICY)
    histories = []
    for policy in policies:
        for source in report["histories"]:
            states = [by_key[key]["runs"][policy]["status"] for key in source["prefix_keys"]]
            require(bool(states), "empty history")
            incomplete = [i for i, status in enumerate(states) if status != "solved"]
            histories.append({"key": source["key"], "cohort": source["cohort"], "policy": policy,
                "statuses": states, "all_prefixes_solved": not incomplete,
                "first_non_solved_prefix": incomplete[0] if incomplete else None,
                "recoveries": [{"prefix": i, "from": states[i - 1]} for i in range(1, len(states))
                               if states[i] == "solved" and states[i - 1] != "solved"],
                "final_status": states[-1]})
    require(report["history_results"] == histories, "history accounting mismatch")
    indexed = {(entry["key"], entry["policy"]): entry for entry in histories}
    require(len(indexed) == len(histories), "duplicate history/policy key")
    summaries, comparisons = [], []
    for cohort in COHORTS:
        drawings = [r for r in rows if cohort == "combined" or cohort in r["cohorts"]]
        sequences = [h for h in report["histories"] if cohort == "combined" or h["cohort"] == cohort]
        statics = [s for s in report["static_inputs"] if cohort == "combined" or s["cohort"] == cohort]
        for policy in policies:
            states = [indexed[(h["key"], policy)] for h in sequences]
            summaries.append({"cohort": cohort, "policy": policy, "distinct_drawings": len(drawings),
                "statuses": dict(Counter(r["runs"][policy]["status"] for r in drawings)),
                "histories": len(sequences),
                "history_prefix_references": sum(len(h["prefix_keys"]) for h in sequences),
                "all_prefixes_solved": sum(h["all_prefixes_solved"] for h in states),
                "histories_with_conflict": sum("conflict" in h["statuses"] for h in states),
                "history_final_status": dict(Counter(h["final_status"] for h in states)),
                "static_references": len(statics),
                "static_status": dict(Counter(by_key[s["geometry_key"]]["runs"][policy]["status"]
                                               for s in statics))})
        pairs = [(r["runs"][BASELINE]["status"], r["runs"][POLICY]["status"]) for r in drawings]
        transitions = Counter(pairs)
        comparisons.append({"cohort": cohort, "baseline": BASELINE, "candidate": POLICY,
            "baseline_newly_rerun": False,
            "distinct_drawings": paired((a == "solved", b == "solved") for a, b in pairs),
            "status_transitions": [{"baseline_status": a, "candidate_status": b, "count": count}
                                   for (a, b), count in sorted(transitions.items())],
            "all_history_prefixes": paired((indexed[(h["key"], BASELINE)]["all_prefixes_solved"],
                                             indexed[(h["key"], POLICY)]["all_prefixes_solved"])
                                            for h in sequences),
            "history_final": paired((indexed[(h["key"], BASELINE)]["final_status"] == "solved",
                                      indexed[(h["key"], POLICY)]["final_status"] == "solved")
                                     for h in sequences),
            "static_final": paired((by_key[s["geometry_key"]]["runs"][BASELINE]["status"] == "solved",
                                     by_key[s["geometry_key"]]["runs"][POLICY]["status"] == "solved")
                                    for s in statics),
            "regression_keys": [r["key"] for r in drawings
                                if r["runs"][BASELINE]["status"] == "solved"
                                and r["runs"][POLICY]["status"] != "solved"]})
    require(report["summary"] == summaries, "drawing/history/static totals mismatch")
    require(report["paired_comparisons"] == comparisons, "paired status transitions mismatch")
    return summaries, comparisons


def audit_initialization_summary(report):
    """Recount retained symbols and modes directly from each compact result."""
    modes, symbols, selections = Counter(), Counter(), []
    for row in report["drawings"]:
        run = row["runs"][POLICY]
        init, first = run["initialization"], run["initial_retained_choice"]
        require(init["mode"] in MODES, "unexpected initialization mode")
        require(first == {"choice_kind": "initial-retained-name", "mother": init["mother"],
                          "side": init["side"], "dart": init["dart"],
                          "domain": [2, 3, 4], "symbol": 2}, "retained choice metadata mismatch")
        require(init["symbol"] == 2 and init["domain_before"] == [2, 3, 4], "initial-name contract changed")
        require(init["prebound_final_inner_anchor"] is False, "premature inner anchor claimed")
        require(init["historical_frame_pair"] == [1, 2]
                and init["birth_pair_is_not_a_final_profile_constraint"] is True,
                "historical label misrepresented as current constraint")
        through = init["mode"] == MODES[0]
        require(bool(init["eligible_mothers"]) == through, "initial mother eligibility mismatch")
        require(init["coarse_split_pair_unordered"] == ([2, 3] if through else None),
                "coarse split meaning changed")
        require((init["mother"] != "frame") == through, "wrong mother for initialization mode")
        require(init["frame_boundary_edges"] == sorted(set(init["frame_boundary_edges"]))
                and bool(init["frame_boundary_edges"]), "missing real-frame evidence")
        require({name: run["initial_trace"][name] for name in first} == first,
                "full initial trace disagrees with compact choice")
        modes[init["mode"]] += 1
        symbols[str(first["symbol"])] += 1
        selections.append({"key": row["key"], "mode": init["mode"],
                           "retained_choice": first, "status": run["status"]})
    expected = {"mode_counts": dict(modes), "retained_symbol_counts": dict(symbols),
                "retained_two_count": symbols.get("2", 0), "selections": selections}
    require(report["initialization_summary"] == expected, "initialization totals mismatch")
    return expected


def batch_counts(batches, initial_side, choices, active_counts):
    """Recount geometry fields independently of the producer's compactor."""
    stages = batches["stages"]
    return {
        "stage_count": len(stages), "unranked_stage": batches["unranked_stage"],
        "mother_stage_counts": dict(Counter(str(s) for s in batches["mother_stages"].values())),
        "ready_side_stage_counts": dict(Counter(str(s) for s in batches["side_ready_stage"])),
        "active_stage_choice_counts": active_counts,
        "ready_choices": choices - 1,
        "coarse_cell_counts": {str(stage["stage"]): len(stage["coarse_cells"]) for stage in stages},
        "max_peer_batch_size": max(len(stage["new_mothers"]) for stage in stages),
        "nontrivial_peer_stages": sum(len(stage["new_mothers"]) > 1 for stage in stages),
        "max_unfinished_cell_size": max(len(cell) for stage in stages for cell in stage["coarse_cells"]),
        "initial_retained_ready_stage": batches["side_ready_stage"][initial_side],
    }


def check_batch_geometry(compact, batches, trace=None):
    """Bind every geometry batch hash; replay trace counts when a proof exists.

    For compact-only inputs, active-stage histogram bounds are checked but the
    exact scheduler is not freshly replayed. All stored full proofs and the
    declared fresh sample receive that stronger independent check separately.
    """
    require(compact["batch_geometry_sha256"] == digest(batches), "batch geometry hash mismatch")
    active = compact["batch_geometry_summary"]["active_stage_choice_counts"]
    allowed = {str(stage["stage"]) for stage in batches["stages"]}
    require(set(active) <= allowed and all(type(value) is int and value > 0 for value in active.values()),
            "invalid active-stage histogram")
    require(sum(active.values()) == compact["choices"] - 1, "active-stage choice total mismatch")
    if trace is not None:
        require(active == dict(Counter(str(step["active_stage"]) for step in trace[1:])),
                "active-stage histogram disagrees with full trace")
    expected = batch_counts(batches, compact["initialization"]["side"], compact["choices"], active)
    require(compact["batch_geometry_summary"] == expected, "batch summary differs from geometry")


def audit_batch_summary(report):
    """Recount stage totals from all compact records without producer helpers."""
    rows = report["drawings"]
    stages, active, ready, mothers = Counter(), Counter(), Counter(), Counter()
    totals = Counter()
    for row in rows:
        counts = row["runs"][POLICY]["batch_geometry_summary"]
        stages[str(counts["stage_count"])] += 1
        active.update(counts["active_stage_choice_counts"])
        ready.update(counts["ready_side_stage_counts"])
        mothers.update(counts["mother_stage_counts"])
        totals["ready_choices"] += counts["ready_choices"]
        totals["drawings_with_unranked_stage"] += int(counts["unranked_stage"] is not None)
        totals["drawings_with_peer_batch"] += int(counts["nontrivial_peer_stages"] > 0)
        totals["nontrivial_peer_stages"] += counts["nontrivial_peer_stages"]
    expected = {"distinct_drawings": len(rows), "stage_count_distribution": dict(stages),
                "active_stage_choice_counts": dict(active), "ready_side_stage_counts": dict(ready),
                "mother_stage_counts": dict(mothers), **dict(totals)}
    require(report["batch_geometry_summary"] == expected, "aggregate batch counts mismatch")
    return expected


def audit_selection(selection, previous, source_evidence):
    """Verify frozen diagnostics and geometry-only provenance without a solver."""
    content = {name: selection[name] for name in ("selected_keys", "roles", "controls", "failed_histories")}
    require(digest(content) == selection["selection_sha256"] == SELECTION_SHA256,
            "fixed forty-case selection changed")
    require(selection["source_evidence"] == source_evidence and selection["reference_policy"] == BASELINE,
            "selection source binding mismatch")
    require(selection["unseen_holdout"] is False and selection["production_solver_executed"] is False
            and selection["old_colors_read"] is False, "selection provenance overstated")
    require(selection["selection_script_sha256"] == file_sha(ROOT / "scripts/select_batch_diagnostics.py"),
            "selection script no longer matches")
    for name, checksum in selection["preserved_theory_evidence"].items():
        require(file_sha(ROOT / name) == checksum, "preserved theoretical evidence changed")
    keys = selection["selected_keys"]
    require(len(keys) == len(set(keys)) == 40 and set(keys) <= previous.keys(), "diagnostic coverage mismatch")
    require([row["key"] for row in selection["drawings"]] == keys, "diagnostic geometry order mismatch")
    for row in selection["drawings"]:
        prior = previous[row["key"]]
        for field in ("document", "aliases", "cohorts", "geometry_sha256", "face_count",
                      "real_bridge_count", "virtual_connector_count"):
            require(row[field] == prior[field], "diagnostic input changed: " + field)
        require(row["reference_status"] == prior["runs"][BASELINE]["status"], "diagnostic status changed")
        require(row["roles"] == selection["roles"][row["key"]], "diagnostic roles changed")
        require("colors" not in row and "runs" not in row, "old colors included in diagnostic geometry")
    require(selection["counts"] == {"distinct_drawings": 40, "current_failures": 4,
                "prior_diagnostics": 7, "failed_history_prefix_references": 25,
                "successful_controls": 8, "reference_statuses": {"solved": 36, "conflict": 4}},
            "diagnostic count denominator changed")
    return set(keys)


def native_certificate(value, field=None):
    """Restore only known integer-dart maps before checking native-result hashes.

    JSON storage changes integer keys to strings; sort_keys then has a different
    order for darts 2 and 10. Restoring these documented maps is not a rerun or
    mathematical alteration. Color/domain arrays remain unchanged.
    """
    maps = {"anchors_by_dart", "initial_anchors_by_dart", "hall_input_anchors"}
    if isinstance(value, dict):
        return {(int(key) if field in maps else key): native_certificate(item, key)
                for key, item in value.items()}
    if isinstance(value, list):
        return [native_certificate(item) for item in value]
    return value


def check_compact_certificate(compact, complete, verification):
    """Bind saved full certificates to compact commitments and proof digests."""
    native = native_certificate(complete)
    for name in ("status", "policy", "choices", "backtracks", "old_colors_read", "colors",
                 "unranked_mothers", "initialization", "initial_anchors_by_dart", "domains",
                 "anchors_by_dart", "local_budget", "hall_conflict"):
        require(json_value(compact[name]) == json_value(complete[name]), "compact/full differs: " + name)
    require(digest(native) == compact["raw_result_sha256"], "full native-result hash mismatch")
    for source, target in (("trace", "trace_sha256"), ("levels", "levels_sha256"),
                           ("batch_geometry", "batch_geometry_sha256"),
                           ("propagation_phases", "propagation_phases_sha256")):
        require(digest(native[source]) == compact[target], "certificate hash mismatch: " + source)
    trace = complete["trace"]
    require(json_value(compact["initial_trace"]) == json_value(trace[0]), "initial trace changed")
    require(compact["initial_retained_choice"] == {name: trace[0][name] for name in (
        "choice_kind", "mother", "side", "dart", "domain", "symbol")}, "initial compact choice changed")
    check_batch_geometry(compact, native["batch_geometry"], trace)
    expected = {"active_one_choices": sum(step["symbol"] == 1 for step in trace),
                "direct_one_bans": sum(1 in step["boundary"]["direct_forbidden"] for step in trace),
                "derived_one_bans": sum(1 in step["boundary"]["derived_exclusions"] for step in trace)}
    require(all(compact[name] == value for name, value in expected.items()), "trace event totals differ")
    require(json_value(verification) == compact["verification"] and verification["passed"],
            "independent certificate replay differs")


def audit_checkpoints(report, folder):
    """Rehash every part and sidecar and reconstruct exact ordered coverage."""
    declared = report["execution"]["part_sha256"]
    files = sorted(folder.glob("part-*.json.gz"))
    manifest = read_json(folder / "manifest.json")
    batch_size = report["execution"]["batch_size"]
    require(type(batch_size) is int and batch_size >= 1, "invalid checkpoint batch size")
    count = (len(report["drawings"]) + batch_size - 1) // batch_size
    require(len(files) == len(declared) == count, "checkpoint count mismatch")
    require([path.name for path in files] == [f"part-{i:05d}.json.gz" for i in range(count)]
            and set(declared) == {path.name for path in files}, "checkpoint filename inventory mismatch")
    require(manifest["selected_keys"] == [row["key"] for row in report["drawings"]], "manifest keys changed")
    require(manifest["smoke_limit"] is None and manifest["batch_size"] == batch_size, "manifest scope changed")
    for field in ("source_evidence", "selection_evidence", "source_sha256", "policy", "baseline",
                  "baseline_newly_rerun", "diagnostic_keys", "old_failure_keys"):
        require(manifest[field] == report[field], "manifest binding changed: " + field)
    combined, details, hashes, diagnostics = [], {}, {}, 0
    rank = lambda row: (row["face_count"], len(row["document"]["strokes"]), row["key"])
    for index, path in enumerate(files):
        checksum = file_sha(path)
        require(checksum == declared[path.name], "checkpoint bytes changed: " + path.name)
        require(read_json(path.with_suffix(path.suffix + ".sha256.json")) ==
                {"filename": path.name, "sha256": checksum}, "checkpoint sidecar mismatch")
        part = read_json(path)
        expected = report["drawings"][index * batch_size:(index + 1) * batch_size]
        require(part["index"] == index and part["records"] == expected, "checkpoint content/order mismatch")
        require(not set(details).intersection(part["detailed_examples"]), "duplicate detailed certificate")
        combined.extend(part["records"])
        details.update(part["detailed_examples"])
        expected_diagnostics = sum(row["key"] in report["diagnostic_keys"] for row in expected)
        require(part["diagnostics_checked"] == expected_diagnostics, "batch diagnostic count mismatch")
        diagnostics += expected_diagnostics
        failures = [part["detailed_examples"][row["key"]] for row in expected
                    if row["runs"][POLICY]["status"] == "conflict"]
        require(part["least_conflict"] == (min(failures, key=rank) if failures else None),
                "checkpoint least failure mismatch")
        hashes[path.name] = checksum
    require(combined == report["drawings"] and details == report["detailed_examples"],
            "checkpoint aggregate content mismatch")
    require(diagnostics == report["diagnostics_checked"], "checkpoint diagnostic coverage mismatch")
    failures = [row for row in report["drawings"] if row["runs"][POLICY]["status"] == "conflict"]
    least = details[min(failures, key=rank)["key"]] if failures else None
    require(least == report["least_conflict"], "global least failure mismatch")
    return {"checkpoints_checked": len(files), "checkpoint_records_checked": len(combined),
            "diagnostics_checked": diagnostics, "hashes": hashes}


def audit_anchor_geometry(geometry, compact, plane):
    """Check all stored initial anchors against real frame edges, not point contact."""
    init = compact["initialization"]
    first = init["outside_dart"]
    require(type(first) is int and 0 <= first < len(plane.face_of_dart), "invalid outside dart")
    require(init["outside_side"] == geometry["outerFace"] == plane.face_of_dart[first],
            "exterior anchor refers to another side")
    require(json_value(compact["initial_anchors_by_dart"]) == {str(first): [1]}, "extra initial anchor")
    require(geometry["edges"][first // 2].get("frame", False), "exterior anchor not on real frame")
    side, dart = init["side"], init["dart"]
    require(type(dart) is int and 0 <= dart < len(plane.face_of_dart)
            and plane.face_of_dart[dart] == side and side != geometry["outerFace"], "retained side/dart mismatch")
    require(compact["anchors_by_dart"].get(str(first), compact["anchors_by_dart"].get(first)) == [1]
            and compact["anchors_by_dart"].get(str(dart), compact["anchors_by_dart"].get(dart)) == [2],
            "initial commitments absent from final anchors")
    edges = []
    for index, edge in enumerate(geometry["edges"]):
        if not edge.get("frame", False):
            continue
        a, b = plane.shores(index)
        if side in (a, b) and geometry["outerFace"] in (a, b) and a != b:
            require(not edge.get("virtual", False)
                    and geometry["vertices"][edge["a"]] != geometry["vertices"][edge["b"]],
                    "initialization cites zero-length or virtual frame edge")
            edges.append(index)
    require(edges == init["frame_boundary_edges"] and bool(edges), "stored real-frame adjacency is false")


def audit_geometries_and_samples(report, batch_size=200):
    """Check every stored success; re-solve only smallest-hash sample/diagnostics.

    All failed paths and predeclared diagnostic paths get complete proof replay
    from saved certificates. This does not search for a repair or alternative.
    """
    require(type(batch_size) is int and batch_size >= 1, "invalid geometry audit batch size")
    rows = report["drawings"]
    sample_keys = set(sorted(row["key"] for row in rows)[:15]) | set(report["diagnostic_keys"])
    details = report["detailed_examples"]
    successes, failures, edge_references, shore_references = 0, 0, 0, 0
    samples, proofs, geometry_records = [], [], []
    for start in range(0, len(rows), batch_size):
        batch = rows[start:start + batch_size]
        exports = export_geometries(batch)
        require(len(exports) == len(batch), "geometry export dropped drawings")
        for row, exported in zip(batch, exports):
            key, compact = row["key"], row["runs"][POLICY]
            require(exported["key"] == key and exported["status"] == "geometry_ok", "geometry export failed")
            geometry = exported["geometry"]
            require(digest(geometry) == row["geometry_sha256"], "reconstructed geometry hash mismatch")
            plane, adjacent = independent_geometry(geometry)
            require(len(plane.faces) == row["face_count"], "reported side count mismatch")
            audit_anchor_geometry(geometry, compact, plane)
            model = build_whole_lines(geometry)
            contacts, _ = extract_whole_contacts(model)
            generations = derive_generations(contacts)
            levels = {line["id"]: {
                "level": None if generations[line["id"]]["depth"] is None else
                         generations[line["id"]]["depth"] + 1,
                "parents": generations[line["id"]]["parents"],
                "endpoint_contacts": contacts[line["id"]], "endpoints": line["endpoints"],
            } for line in model.lines}
            require(digest(levels) == compact["levels_sha256"], "independent level geometry hash mismatch")
            check_batch_geometry(compact, independent_batches(model, levels))
            if compact["status"] == "solved":
                check = verify_result(geometry, compact, (plane, adjacent))
                require(check["passed"] and check == compact["verification"]["final_legality"],
                        "stored coloring or independent orbit certificate is invalid")
                successes += 1
                edge_references += check["edge_count"]
                shore_references += check["shore_count"]
            else:
                failures += 1
                require(key in details, "failed drawing lacks full certificate")
            if key in details:
                detail = details[key]
                require(detail["geometry"] == geometry and detail["key"] == key, "detail geometry changed")
                for name in ("document", "aliases", "face_count"):
                    require(detail[name] == row[name], "detail input metadata changed")
                require(detail["previous_result"] == row["runs"][BASELINE], "detail archived v3 changed")
                require(detail["is_predeclared_diagnostic"] is (key in report["diagnostic_keys"]),
                        "detail diagnostic membership changed")
                check = verify_run(geometry, detail["outcome"])
                require(json_value(check) == detail["verification"], "detail proof replay mismatch")
                check_compact_certificate(compact, detail["outcome"], check)
                proofs.append({"key": key, "status": compact["status"], "verification": check})
            if key in sample_keys:
                fresh = restart_peer_batch_names(geometry)
                check = verify_run(geometry, fresh)
                check_compact_certificate(compact, fresh, check)
                if key in details:
                    require(json_value(fresh) == details[key]["outcome"], "fresh/stored detailed path differs")
                samples.append({"key": key, "status": fresh["status"], "choices": fresh["choices"],
                                "raw_result_sha256": digest(fresh), "verification": check})
            geometry_records.append({"key": key, "geometry_sha256": row["geometry_sha256"],
                                     "status": compact["status"]})
        print({"audit_geometry_checked": min(start + batch_size, len(rows)), "total": len(rows),
               "stored_successes_checked": successes, "fresh_sample_runs": len(samples)}, flush=True)
    require(len(samples) == len(sample_keys), "fresh sample coverage incomplete")
    require(len(proofs) == len(details), "saved proof coverage incomplete")
    return {"geometries_reconstructed": len(geometry_records),
            "geometry_status_manifest_sha256": digest(geometry_records),
            "stored_successes_color_and_line_orbits_checked": successes,
            "stored_failures_with_full_proof_replay": failures,
            "success_edge_references_checked": edge_references,
            "success_shore_references_checked": shore_references,
            "initial_frame_anchor_geometry_checked": len(rows),
            "independent_level_and_batch_geometry_checked": len(rows),
            "saved_certificate_replay": {"count": len(proofs), "records": proofs},
            "fresh_sample_replay": {"selection": "15 lexicographically smallest geometry keys plus all 40 fixed diagnostics",
                                    "sample_size": len(samples), "sample_keys": sorted(sample_keys),
                                    "records": samples}}


def main():
    """Fail closed on missing/altered evidence and write a new audit artifact."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "outputs/peer-batches-full-2026-09-19.json.gz")
    parser.add_argument("--summary", type=Path, default=ROOT / "outputs/peer-batches-full-summary-2026-09-19.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--geometry-batch-size", type=int, default=200)
    args = parser.parse_args()
    require(not sys.flags.optimize, "certificate checking requires Python without -O")
    require(not args.output.exists(), "choose a new audit output; existing evidence is preserved")
    report, small = read_json(args.report), read_json(args.summary)
    report_sha = file_sha(args.report)
    require(report["policy"] == POLICY and report["baseline"] == BASELINE, "policy binding changed")
    require(report["full_corpus_run"] is True and report["smoke_limit"] is None, "partial run is not full evidence")
    require(report["unseen_holdout"] is False and report["baseline_newly_rerun"] is False,
            "experiment provenance misstated")
    require(report["source_evidence"]["sha256"] == SOURCE_SHA256, "source is not frozen v3 full corpus")
    require(report["source_sha256"] == report["source_sha256_end"] and report["source_hashes_unchanged"] is True,
            "sources changed during original run")
    for name, checksum in report["source_sha256"].items():
        require(file_sha(ROOT / name) == checksum, "current source no longer matches run: " + name)
    inputs = {}
    for name in ("source_evidence", "selection_evidence"):
        path = args.report.parent / report[name]["filename"]
        require(file_sha(path) == report[name]["sha256"], "input bytes changed: " + name)
        inputs[name] = read_json(path)
    old = inputs["source_evidence"]
    require(old["policy"] == BASELINE and len(old["source_sha256"]) == 26,
            "baseline policy/source inventory changed")
    require(old["source_sha256"] == old["source_sha256_end"]
            and len(report["source_sha256"]) == 30
            and all(report["source_sha256"].get(name) == checksum
                    for name, checksum in old["source_sha256"].items()),
            "new source inventory does not preserve frozen baseline files")
    previous = {row["key"]: row for row in old["drawings"]}
    diagnostics = audit_selection(inputs["selection_evidence"], previous, report["source_evidence"])
    rows = report["drawings"]
    require(len(rows) == len({row["key"] for row in rows}) == 7069, "drawing denominator mismatch")
    require([row["key"] for row in rows] == sorted(previous), "drawing keys/order changed")
    require(report["histories"] == old["histories"] and len(report["histories"]) == 363, "history inventory changed")
    require(report["static_inputs"] == old["static_inputs"] and len(report["static_inputs"]) == 302,
            "static inventory changed")
    require(sum(len(h["prefix_keys"]) for h in report["histories"]) == 7678, "prefix denominator mismatch")
    counts = [sum(cohort in row["cohorts"] for row in rows) for cohort in COHORTS[1:]]
    require(counts == [6113, 961] and sum(len(row["cohorts"]) == 2 for row in rows) == 5,
            "cohort membership counts changed")
    old_failures = {key for key, row in previous.items() if row["runs"][BASELINE]["status"] != "solved"}
    require(len(old_failures) == 4 and old_failures <= diagnostics, "old failure coverage changed")
    require(report["diagnostic_keys"] == sorted(diagnostics) and report["diagnostics_checked"] == 40,
            "forty-diagnostic coverage changed")
    require(report["old_failure_keys"] == sorted(old_failures), "old failure inventory changed")
    failures, totals = set(), Counter()
    for row in rows:
        prior = previous[row["key"]]
        require({k: v for k, v in row.items() if k != "runs"} ==
                {k: v for k, v in prior.items() if k != "runs"}, "input document/metadata changed")
        require(set(row["runs"]) == {BASELINE, POLICY}, "unexpected policies in compact record")
        require(row["runs"][BASELINE] == prior["runs"][BASELINE], "archived v3 result changed")
        candidate = row["runs"][POLICY]
        require(candidate["status"] in ("solved", "conflict") and candidate["policy"] == POLICY, "invalid candidate status")
        require(candidate["independent_check_passed"] is True and candidate["verification"]["passed"] is True,
                "unverified drawing")
        require(candidate["backtracks"] == 0 and candidate["old_colors_read"] is False
                and candidate["local_budget"] is None, "retry/old-color contract violated")
        require(1 <= candidate["choices"] < row["face_count"], "invalid commitment count")
        require((candidate["colors"] is not None) == (candidate["status"] == "solved"), "status/color mismatch")
        if candidate["status"] != "solved":
            failures.add(row["key"])
        totals.update({k: v for k, v in candidate["verification"].items() if type(v) is int})
    require(report["failure_keys"] == sorted(failures), "failure inventory mismatch")
    require(set(report["detailed_examples"]) == failures | diagnostics, "full failure/diagnostic certificates missing")
    require(report["independent_checks"] == 7069 and report["replay_totals"] == dict(totals), "proof totals mismatch")
    summaries, comparisons = audit_summaries(report)
    initialization = audit_initialization_summary(report)
    batch_summary = audit_batch_summary(report)
    expected_small = {k: v for k, v in report.items() if k not in (
        "drawings", "histories", "static_inputs", "history_results", "detailed_examples",
        "least_conflict", "initialization_summary")}
    expected_small.update({"input": {"filename": args.report.name, "sha256": report_sha},
        "distinct_drawings": 7069, "history_prefix_references": 7678, "static_references": 302,
        "initialization_summary": {k: v for k, v in initialization.items() if k != "selections"}})
    least = report["least_conflict"]
    expected_small["least_conflict"] = {k: least[k] for k in ("key", "face_count", "aliases")} if least else None
    require(small == expected_small, "standalone summary artifact disagrees")
    checkpoints = audit_checkpoints(report, args.report.parent / report["execution"]["checkpoint_directory"])
    geometry = audit_geometries_and_samples(report, args.geometry_batch_size)
    for name, checksum in report["source_sha256"].items():
        require(file_sha(ROOT / name) == checksum, "source changed during independent audit: " + name)
    require(file_sha(args.report) == report_sha, "report bytes changed during audit")
    result = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "passed": True,
        "report": {"filename": args.report.name, "sha256": report_sha},
        "audit_script_sha256": file_sha(Path(__file__)), "stored_drawings_checked": 7069,
        "histories_checked": 363, "history_prefix_references_checked": 7678, "static_references_checked": 302,
        "source_files_checked": len(report["source_sha256"]), "source_hashes_unchanged": True,
        "archived_v3_records_copied_exactly": 7069, "summary": summaries, "paired_comparisons": comparisons,
        "initialization_summary": {k: v for k, v in initialization.items() if k != "selections"},
        "batch_geometry_summary": batch_summary,
        "replay_totals": dict(totals), "checkpoint_audit": checkpoints, "geometry_audit": geometry,
        "limits": ["Every stored completed coloring and line orbit was independently rechecked on reconstructed geometry.",
                   "All failures and forty fixed diagnostics received full saved-certificate proof replay.",
                   "Only the declared hash sample plus forty diagnostics were newly solved; this is not a second full solve.",
                   "The audit imports no producer summary/counting function; it reuses independent proof/geometry checkers.",
                   "Finite already-inspected corpus, not all plane maps; four is an input palette."]}
    write_report(args.output, result)
    print({"passed": True, "drawings": 7069, "parts": checkpoints["checkpoints_checked"],
           "fresh_sample_size": geometry["fresh_sample_replay"]["sample_size"],
           "sha256": file_sha(args.output)}, flush=True)


if __name__ == "__main__":
    main()

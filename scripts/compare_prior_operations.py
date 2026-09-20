"""Replay earlier choices in a fixed eight-mode diagnostic factorial experiment.

All frozen v2/v3/v4 failures and the forty already selected v4 controls are
included before a new run is observed. Each policy runs once on every drawing;
this script never constructs a per-map portfolio or selects favorable outputs.
The old full-corpus rates and this deliberately selected subset stay separate.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.global_restart import current_segments
from fourcolor.prior_operation_restart import restart_prior_operation_names
from fourcolor.prior_rule_reuse import certified_pair_relations
from fourcolor.whole_lines import build_whole_lines
from scripts.analyze_line_generations import derive_generations, extract_whole_contacts
from scripts.validate_frontier_restart import (
    anchored_domains, complete_subsets, file_sha, independent_geometry, json_value, read_json,
)
from scripts.validate_global_restart import digest, write_report
from scripts.validate_joint_boundary import check_coloring
from scripts.validate_level_sides_peer import audit_choice
from scripts.validate_peer_batches import independent_batches, independent_choice
from scripts.validate_relation_frontier import (
    allowed_relations, check_relational_fixed_point, decode, decoded_matrix, replay_hall,
)
from scripts.validate_staged_levels import audit_boundary, independent_initial_selection

ARCHIVES = {
    "v2": ("outputs/level-sides-peer-full-2026-09-19.json.gz",
           "5085627be22653ea9b6ea13de5ff851c452a8c702996ee6eda0672d2d72eca07"),
    "v3": ("outputs/staged-levels-full-2026-09-19.json.gz",
           "87250016644ba5c9c25573e0894af563eb451cd43915c11bad73927308af4910"),
    "v4": ("outputs/peer-batches-full-2026-09-19.json.gz",
           "fb004374e06ee0ace87328a8559e108b23e0e9b71663e1a35158738a5e3ad543"),
}
MODES = tuple({"initialization": initial, "schedule": schedule, "implicit": implicit}
              for initial, schedule, implicit in product(
                  ("frame", "retained"), ("peer", "ready"), (False, True)))
BASELINE_MODES = {"frame-peer-plain": "v2", "retained-peer-plain": "v3",
                  "retained-ready-plain": "v4"}
OUTCOME_FIELDS = ("status", "domains", "relations", "phases", "revisions",
                  "hall_conflict", "backtracks", "choices", "palette")
PHASE_FIELDS = ("hall_input_anchors", "hall_status", "hall_domains", "hall_trace",
                "hall_conflict", "relation_input", "relation_trace", "relation_conflict")
TEMPLATE_VERTICES = ("O", "A", "B", "p", "q", "r", "s", "t", "u")
# These nineteen premises are transcribed from the elementary proof, rather
# than imported from the production template finder or certificate validator.
TEMPLATE_EDGES = tuple(tuple(pair.split()) for pair in (
    "O A", "O B", "O p", "A p", "O q", "B q", "p q", "r p", "r q", "r A",
    "s r", "s A", "t O", "t B", "t s", "u B", "u r", "u s", "u t"))
NEW_SOURCES = (
    "fourcolor/prior_operation_restart.py", "fourcolor/implicit_inequality.py",
    "fourcolor/prior_rule_reuse.py", "scripts/compare_prior_operations.py",
    "tests/test_compare_prior_operations.py", "tests/test_prior_operation_restart.py",
    "tests/test_prior_rule_reuse.py", "tests/test_implicit_inequality.py", "scripts/validate_joint_boundary.py",
    "fourcolor/joint_boundary.py", "fourcolor/joint_boundary_restart.py",
)


def require(condition, message):
    """Reject altered evidence even when imported by another script."""
    if not condition:
        raise ValueError(message)


def mode_name(mode):
    """Give every predeclared factor combination one stable identifier."""
    return "-".join((mode["initialization"], mode["schedule"],
                     "implicit" if mode["implicit"] else "plain"))


def select_inventory(archives):
    """Union all historical failures with the forty already fixed controls."""
    inventories, failures = {}, {}
    for version, archive in archives.items():
        require(archive["full_corpus_run"] is True, "historical input is not a full run")
        inventory = {row["key"]: row for row in archive["drawings"]}
        require(len(inventory) == len(archive["drawings"]) == 7069,
                "historical corpus size or unique keys changed")
        inventories[version] = inventory
        failures[version] = {key for key, row in inventory.items()
                             if row["runs"][archive["policy"]]["status"] != "solved"}
    require(set(inventories["v2"]) == set(inventories["v3"]) == set(inventories["v4"]),
            "baseline geometry inventories differ")
    require({name: len(keys) for name, keys in failures.items()} == {"v2": 1, "v3": 4, "v4": 9},
            "frozen failure inventory changed")
    controls = set(archives["v4"]["diagnostic_keys"])
    require(len(controls) == 40 and not controls & failures["v4"], "v4 control selection changed")
    selected = set.union(controls, *failures.values())
    require(len(selected) == 49 and selected == set(archives["v4"]["detailed_examples"]),
            "all historical failures must be covered by the fixed 49 detailed geometries")
    return sorted(selected), inventories, failures, controls


def check_template_certificates(plane, adjacent, certificates):
    """Check distinct face identities and all nineteen genuine boundary edges."""
    pairs = []
    for certificate in certificates:
        mapping = certificate["mapping"]
        require(set(mapping) == set(TEMPLATE_VERTICES)
                and len(set(mapping.values())) == 9
                and all(type(side) is int and 0 <= side < len(adjacent)
                        for side in mapping.values()), "invalid nine-side template mapping")
        witnesses = []
        for first, second in TEMPLATE_EDGES:
            a, b = mapping[first], mapping[second]
            require(b in adjacent[a], "template premise lacks a real boundary")
            edge_ids = [edge for edge in range(len(plane.edges))
                        if set(plane.shores(edge)) == {a, b}]
            require(bool(edge_ids), "template premise lacks geometric edge witnesses")
            witnesses.append({"vertices": [first, second], "sides": [a, b],
                              "raw_edge_ids": edge_ids})
        expected = {"kind": "nine-side-two-triangle-implicit-inequality", "palette_size": 4,
                    "mapping": {name: mapping[name] for name in TEMPLATE_VERTICES},
                    "required_adjacencies": witnesses,
                    "conclusion": {"sides": [mapping["A"], mapping["B"]], "relation": "!=",
                                   "kind": "derived-name-relation-not-geometric-edge"}}
        require(certificate == expected, "template certificate differs from independent geometry")
        pairs.append(tuple(certificate["conclusion"]["sides"]))
    require(len({tuple(sorted(pair)) for pair in pairs}) == len(pairs),
            "duplicate certificate for the same unordered conclusion")
    return pairs


def replay_implicit(relations, result, certificates):
    """Reconstruct the exact inequality deletions without using production masks."""
    work = [[set(entry) for entry in row] for row in relations]
    expected, removed = [], 0
    for certificate in certificates:
        for witness in certificate["required_adjacencies"]:
            a, b = witness["sides"]
            require(all(x != y for x, y in work[a][b]), "missing inequality premise in matrix")
    for index, certificate in enumerate(certificates):
        a, b = certificate["conclusion"]["sides"]
        before = work[a][b]
        after = {(x, y) for x, y in before if x != y}
        if after != before:
            expected.append((index, a, b, before, after))
            removed += len(before - after)
            work[a][b], work[b][a] = after, {(y, x) for x, y in after}
    require(len(result["trace"]) == len(expected), "implicit deletion event count differs")
    for event, (index, a, b, before, after) in zip(result["trace"], expected):
        require(event["certificate_index"] == index and event["sides"] == [a, b],
                "implicit event targets a different certificate")
        require(event["kind"] == "derived-name-relation-not-geometric-edge"
                and event["relation"] == "!=", "implicit event claim differs")
        require(decode(event["before"]) == before and decode(event["after"]) == after
                and decode(event["removed"]) == before - after,
                "implicit event deletes the wrong name pairs")
    require(decoded_matrix(result["relations"], len(work)) == work,
            "implicit output matrix differs")
    require(result["changed"] is bool(expected)
            and result["conflict"] is any(not entry for row in work for entry in row),
            "implicit change or conflict flag differs")
    return work, Counter(implicit_events=len(expected), implicit_pair_bits_removed=removed)


def replay_propagation(plane, adjacent, anchors, outcome, certificates, subsets):
    """Replay original Hall/pair steps with certified inequalities inserted."""
    require(outcome["implicit_certificates"] == certificates, "phase template cache differs")
    require(outcome["backtracks"] == outcome["choices"] == 0
            and outcome["palette"] == [1, 2, 3, 4], "propagation made an active choice")
    domains, previous, stats = anchored_domains(plane, anchors), None, Counter()
    require(bool(outcome["phases"]), "missing propagation phases")
    for index, phase in enumerate(outcome["phases"]):
        require(anchored_domains(plane, phase["hall_input_anchors"]) == domains,
                "Hall input domains differ")
        if index == 0:
            require(json_value(phase["hall_input_anchors"]) == json_value(anchors),
                    "initial Hall anchors differ")
        hall_domains, hall_conflict, events = replay_hall(plane, adjacent, domains, phase, subsets)
        stats["hall_events"] += events
        permitted = allowed_relations(hall_domains, adjacent)
        relations = permitted if previous is None else [
            [previous[i][j] & permitted[i][j] for j in range(len(domains))]
            for i in range(len(domains))]
        require(relations == decoded_matrix(phase["pre_implicit_relations"], len(domains)),
                "pre-template relation input differs")
        relations, counts = replay_implicit(relations, phase["implicit_filter"], certificates)
        stats.update(counts)
        require(relations == decoded_matrix(phase["relation_input"], len(domains)),
                "pair closure input differs")
        if hall_conflict or any(not entry for row in relations for entry in row):
            require(not phase["relation_trace"], "pair events after an established conflict")
        for event in phase["relation_trace"]:
            require(all(entry for row in relations for entry in row), "pair event after conflict")
            i, j, k = event["i"], event["j"], event["via"]
            before, left, right = relations[i][j], relations[i][k], relations[k][j]
            require(decode(event["before"]) == before and decode(event["left"]) == left
                    and decode(event["right"]) == right, "pair event operands differ")
            supported = {(a, b) for a, c in left for middle, b in right if c == middle}
            after = before & supported
            require(after != before and decode(event["after"]) == after
                    and decode(event["removed"]) == before - after, "pair deletion differs")
            relations[i][j], relations[j][i] = after, {(b, a) for a, b in after}
            stats["relation_events"] += 1
            stats["pair_bits_removed"] += len(before - after)
        conflict = hall_conflict or any(not entry for row in relations for entry in row)
        require(phase["relation_conflict"] is conflict, "phase conflict differs")
        domains = [{a for a, b in relations[i][i]} for i in range(len(domains))]
        if not conflict:
            check_relational_fixed_point(relations)
        if index + 1 < len(outcome["phases"]):
            require(not conflict and domains != hall_domains, "unnecessary propagation repeat")
        else:
            require(conflict or domains == hall_domains, "propagation ended before fixed point")
        previous = relations
        stats["propagation_rounds"] += 1
    expected = "conflict" if conflict else "solved" if all(len(d) == 1 for d in domains) else "underdetermined"
    require(outcome["status"] == expected and outcome["domains"] == [sorted(d) for d in domains],
            "propagation status or domains differ")
    require(decoded_matrix(outcome["relations"], len(domains)) == relations,
            "propagation final pair matrix differs")
    require(outcome["hall_conflict"] == outcome["phases"][-1]["hall_conflict"],
            "final Hall certificate differs")
    require(outcome["statistics"] == {
        "template_relation_bits_removed": 2 * stats["implicit_pair_bits_removed"]},
        "propagation removal statistics differ")
    return [sorted(d) for d in domains], stats


def verify_run(geometry, result, mode):
    """Independently check the chosen historical operations and every deduction."""
    require(not sys.flags.optimize, "independent legacy checkers require Python without -O")
    require(result["initialization_mode"] == mode["initialization"]
            and result["schedule"] == mode["schedule"] and result["implicit"] is mode["implicit"],
            "run factor metadata differs")
    require(result["policy"] == "prior-operations-" + mode_name(mode), "run policy differs")
    plane, adjacent = independent_geometry(geometry)
    certificates = result["implicit_certificates"]
    require(mode["implicit"] or not certificates, "plain mode contains implicit constraints")
    check_template_certificates(plane, adjacent, certificates)
    model = build_whole_lines(geometry)
    contacts, _ = extract_whole_contacts(model)
    generations = derive_generations(contacts)
    levels = {line["id"]: {
        "level": None if generations[line["id"]]["depth"] is None else generations[line["id"]]["depth"] + 1,
        "parents": generations[line["id"]]["parents"], "endpoint_contacts": contacts[line["id"]],
        "endpoints": line["endpoints"]} for line in model.lines}
    require(result["levels"] == levels, "generation metadata differs")
    require(result["unranked_mothers"] == sorted(name for name, item in levels.items()
                                                if item["level"] is None), "unknown levels differ")
    batches = independent_batches(model, levels)
    if mode["schedule"] == "ready":
        require(json_value(result["batch_geometry"]) == json_value(batches), "ready batches differ")
    units = current_segments(model)
    require(json_value(result["units"]) == json_value(units), "current segments differ")
    frame = next(line for line in model.lines if line["id"] == "frame")
    first = frame["spans"][0]["dart"]
    anchors = {first: [1]}
    if mode["initialization"] == "frame":
        anchors[first ^ 1] = [2]
        require(result["initialization"] is None, "frame mode has retained initialization metadata")
    require(plane.face_of_dart[first] == geometry["outerFace"], "outside face identity differs")
    require(json_value(result["initial_anchors_by_dart"]) == json_value(anchors), "initial anchors differ")
    require(result["backtracks"] == 0 and result["old_colors_read"] is False
            and result["local_budget"] is None, "run used retries or archived names")
    trace, calls = result["trace"], result["propagation_phases"]
    require(len(calls) == len(trace) + 1 == result["choices"] + 1, "active choice count differs")
    previous, totals, subsets = None, Counter(), complete_subsets(adjacent)
    for index, call in enumerate(calls):
        if index:
            step = trace[index - 1]
            require(plane.face_of_dart[step["dart"]] == step["side"], "chosen dart and side differ")
            if index == 1 and mode["initialization"] == "retained":
                selected, initial_mode, eligible = independent_initial_selection(
                    model, units, levels, contacts, previous, adjacent)
                for name, value in selected.items():
                    require(json_value(step[name]) == json_value(value), "retained selection differs: " + name)
                require(step["choice_kind"] == "initial-retained-name" and step["symbol"] == 2
                        and step["domain"] == [2, 3, 4], "retained normalization differs")
                expected_initialization = {
                    "mode": initial_mode, "eligible_mothers": eligible,
                    "mother": selected["mother"], "side": selected["side"], "dart": selected["dart"],
                    "frame_boundary_edges": selected["frame_boundary_edges"],
                    "domain_before": [2, 3, 4], "symbol": 2, "historical_frame_pair": [1, 2],
                    "coarse_split_pair_unordered": [2, 3] if eligible else None,
                    "birth_pair_is_not_a_final_profile_constraint": True,
                    "outside_dart": first, "outside_side": geometry["outerFace"],
                    "prebound_final_inner_anchor": False}
                require(result["initialization"] == expected_initialization,
                        "retained initialization summary differs")
            else:
                require(step["choice_kind"] == "greedy-not-a-proved-safe-extension", "unsafe greedy claim")
                if mode["schedule"] == "peer":
                    audit_choice(model, units, levels, previous, adjacent, step)
                else:
                    selected = independent_choice(model, units, levels, batches, previous, adjacent)
                    for name, value in selected.items():
                        require(json_value(step[name]) == json_value(value), "ready selection differs: " + name)
            require(step["domain"] == previous[step["side"]]
                    and step["symbol"] == min(step["domain"]), "greedy color or domain differs")
            audit_boundary(model, previous, step["side"], step["boundary"])
            anchors[step["dart"]] = [step["symbol"]]
        require(json_value(call["anchors_by_dart"]) == json_value(anchors), "phase anchors differ")
        previous, stats = replay_propagation(plane, adjacent, anchors, call["outcome"], certificates, subsets)
        totals.update(stats)
        if index < len(trace):
            require(call["outcome"]["status"] == "underdetermined", "active choice after terminal phase")
    require(result["status"] in ("solved", "conflict"), "unexpected terminal status")
    require(json_value(result["anchors_by_dart"]) == json_value(anchors), "final commitments differ")
    for field in ("status", "domains", "relations", "hall_conflict"):
        require(result[field] == calls[-1]["outcome"][field], "run and final propagation differ: " + field)
    legality = check_coloring(plane, adjacent, result["colors"], anchors) if result["status"] == "solved" else None
    require(legality is not None or result["colors"] is None, "conflict contains a coloring")
    require(result["statistics"] == {
        "template_relation_bits_removed": 2 * totals["implicit_pair_bits_removed"]},
        "run removal statistics differ")
    return {"passed": True, "method": "independent-geometry-schedule-and-set-proof-replay",
            "certificate_count": len(certificates), "real_edge_premises_checked": 19 * len(certificates),
            "active_choices": len(trace), "final_legality": legality, "statistics": dict(totals),
            "claim": "checked-complete-coloring" if legality else "checked-greedy-commitment-conflict"}


def old_propagation_projection(calls):
    """Remove only new descriptive evidence when comparing a plain run to history."""
    projected = []
    for call in calls:
        outcome = {name: call["outcome"][name] for name in OUTCOME_FIELDS}
        outcome["phases"] = [{name: phase[name] for name in PHASE_FIELDS}
                             for phase in outcome["phases"]]
        projected.append({"anchors_by_dart": call["anchors_by_dart"], "outcome": outcome})
    return projected


def check_baseline_reproduction(run, historical):
    """Compare choices, deductions, domains, anchors and names with frozen bytes."""
    require(digest(run["trace"]) == historical["trace_sha256"], "historical trace was not reproduced")
    require(digest(old_propagation_projection(run["propagation_phases"]))
            == historical["propagation_phases_sha256"], "historical propagation was not reproduced")
    for field in ("status", "domains", "colors", "choices", "hall_conflict", "anchors_by_dart"):
        require(json_value(run[field]) == json_value(historical[field]), "historical value differs: " + field)
    return {"passed": True, "trace_exact": True, "propagation_phases_exact": True,
            "final_status_domains_colors_commitments_exact": True}


def summarize(records):
    """Report every fixed-policy improvement and regression, never oracle selection."""
    summaries = []
    for mode in MODES:
        name = mode_name(mode)
        for reference in ("v2", "v3", "v4"):
            comparisons = Counter((row["historical"][reference]["status"], row["runs"][name]["status"])
                                  for row in records)
            summaries.append({"mode": name, "reference": reference, "drawings": len(records),
                              "statuses": dict(Counter(row["runs"][name]["status"] for row in records)),
                              "fixed_failures": comparisons[("conflict", "solved")],
                              "regressions": comparisons[("solved", "conflict")],
                              "fixed_keys": [row["key"] for row in records if row["historical"][reference]["status"] == "conflict"
                                             and row["runs"][name]["status"] == "solved"],
                              "regression_keys": [row["key"] for row in records if row["historical"][reference]["status"] == "solved"
                                                  and row["runs"][name]["status"] == "conflict"],
                              "failure_keys": [row["key"] for row in records if row["runs"][name]["status"] == "conflict"]})
            summaries[-1]["failure_aliases"] = [
                {"key": row["key"], "aliases": row.get("aliases", [])}
                for row in records if row["runs"][name]["status"] == "conflict"]
    contrasts = []
    for mode in MODES:
        if mode["implicit"]:
            continue
        before, after = mode_name(mode), mode_name({**mode, "implicit": True})
        counts = Counter((row["runs"][before]["status"], row["runs"][after]["status"]) for row in records)
        contrasts.append({"before": before, "after": after,
                          "fixed_failures": counts[("conflict", "solved")],
                          "regressions": counts[("solved", "conflict")],
                          "both_solved": counts[("solved", "solved")],
                          "both_conflict": counts[("conflict", "conflict")]})
    return {"policy_comparisons": summaries, "implicit_factor_contrasts": contrasts,
            "full_corpus_run": False, "unseen_holdout": False,
            "per_map_policy_selection": False}


def source_hashes(archives):
    """Freeze every historical dependency and every new producer/checker."""
    expected = {}
    for archive in archives.values():
        for name, sha in archive["source_sha256"].items():
            require(name not in expected or expected[name] == sha, "historical source hashes disagree")
            expected[name] = sha
    hashes = {name: file_sha(ROOT / name) for name in sorted(set(expected) | set(NEW_SOURCES))}
    require(all(hashes[name] == sha for name, sha in expected.items()), "a frozen historical source changed")
    return hashes


def build_report(limit=None):
    """Run the declared factorial only after validating all archived evidence."""
    require(limit is None or type(limit) is int and limit > 0, "smoke limit must be positive")
    archives = {}
    for version, (name, expected_sha) in ARCHIVES.items():
        require(file_sha(ROOT / name) == expected_sha, "historical archive hash changed: " + version)
        archives[version] = read_json(ROOT / name)
    keys, inventories, failures, controls = select_inventory(archives)
    hashes, records, totals = source_hashes(archives), [], Counter()
    started = perf_counter()
    for number, key in enumerate(keys if limit is None else keys[:limit], 1):
        detail = archives["v4"]["detailed_examples"][key]
        geometry = detail["geometry"]
        for version in archives:
            require(digest(geometry) == inventories[version][key]["geometry_sha256"],
                    "historical geometry bytes differ: " + version)
        historical = {version: inventories[version][key]["runs"][archive["policy"]]
                      for version, archive in archives.items()}
        row = {"key": key, "aliases": detail["aliases"], "face_count": detail["face_count"],
               "geometry": geometry, "geometry_sha256": digest(geometry),
               "failure_cohorts": [version for version in archives if key in failures[version]],
               "prior_v4_diagnostic_control": key in controls,
               "historical": historical, "runs": {}}
        # A single fixed geometry-only finder supplies the same complete list
        # to all four implicit modes. No outcomes or old coloring enter it.
        certificates = certified_pair_relations(geometry)
        row["geometry_certificate_count"] = len(certificates)
        for mode in MODES:
            name = mode_name(mode)
            result = restart_prior_operation_names(
                geometry, **mode, certificates=certificates if mode["implicit"] else None)
            require(result["implicit_certificates"] == (certificates if mode["implicit"] else []),
                    "run omitted or changed a geometry-selected certificate")
            verification = verify_run(geometry, result, mode)
            verification["complete_geometry_certificate_cache_matched"] = True
            baseline_check = (check_baseline_reproduction(result, historical[BASELINE_MODES[name]])
                              if name in BASELINE_MODES else None)
            totals.update(verification["statistics"])
            row["runs"][name] = {"status": result["status"], "outcome": result,
                                  "verification": verification, "baseline_reproduction": baseline_check}
        records.append(row)
        print({"checked": number, "selected": len(keys),
               "solved": {mode_name(mode): sum(r["runs"][mode_name(mode)]["status"] == "solved" for r in records)
                          for mode in MODES}}, flush=True)
    end_hashes = {name: file_sha(ROOT / name) for name in hashes}
    require(hashes == end_hashes, "producer or checker changed during the experiment")
    require(all(file_sha(ROOT / path) == sha for path, sha in ARCHIVES.values()), "input changed during experiment")
    return {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "experiment": "Fixed 2x2x2 restoration of prior initialization, scheduling and certified inequality",
            "inputs": {version: {"filename": Path(path).name, "sha256": sha} for version, (path, sha) in ARCHIVES.items()},
            "source_sha256": hashes, "source_sha256_end": end_hashes, "source_hashes_unchanged": True,
            "declared_modes": list(MODES), "declared_selection_keys": keys, "selection_sha256": digest(keys),
            "declared_drawings": len(keys), "checked_drawings": len(records),
            "smoke_limit": limit, "full_declared_diagnostic_run": limit is None,
            "full_corpus_run": False, "unseen_holdout": False,
            "historical_failure_keys": {name: sorted(values) for name, values in failures.items()},
            "historical_full_corpus": {version: {"drawings": len(inventory), "statuses": dict(Counter(
                row["runs"][archives[version]["policy"]]["status"] for row in inventory.values()))}
                for version, inventory in inventories.items()},
            "baseline_exact_reproductions": 3 * len(records), "independent_run_checks": 8 * len(records),
            "proof_replay_totals": dict(totals), "summary": summarize(records), "records": records,
            "wall_seconds_including_independent_checks": perf_counter() - started,
            "limits": ["All cases were selected from previously examined results; no unseen holdout is claimed.",
                       "Historical full-corpus counts are separate from this 49-drawing diagnostic.",
                       "Every mode is fixed for every map; there is no per-map best-result combination.",
                       "The implicit rule matches a known nineteen-edge template, not all implied inequalities.",
                       "Every run uses four given names, one greedy trajectory and no color-search retries.",
                       "A conflict certifies incompatible chosen commitments, not a non-four-colorable plane map.",
                       "Runtime includes audit work and is not an algorithm speed benchmark."]}


def main():
    """Write a complete transcript and a compact summary to two fresh paths."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--limit", type=int, help="Explicit smoke subset; omit for all 49 diagnostic drawings")
    args = parser.parse_args()
    if args.output.exists() or args.summary.exists() or args.output.resolve() == args.summary.resolve():
        parser.error("choose two distinct fresh output paths")
    if args.limit is not None and args.limit < 1:
        parser.error("smoke limit must be positive")
    report = build_report(args.limit)
    write_report(args.output, report)
    summary = {key: value for key, value in report.items() if key not in ("records", "source_sha256_end")}
    summary["transcript"] = {"filename": args.output.name, "sha256": file_sha(args.output)}
    write_report(args.summary, summary)
    print({"output": args.output.name, "checked_drawings": report["checked_drawings"],
           "independent_run_checks": report["independent_run_checks"]}, flush=True)


if __name__ == "__main__":
    main()

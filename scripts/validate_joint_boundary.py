"""Compare two book-boundary filters on 49 already-inspected v4 geometries.

The nine frozen first-fatal states and the new complete greedy trajectories are
different experiments. Archived legal witnesses are read by this checker only,
never supplied to a production filter or restart. No full-corpus success rate
or speedup is estimated from this deliberately selected diagnostic subset.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations, product
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.global_restart import current_segments
from fourcolor.joint_boundary import find_boundary_books, filter_boundary_books
from fourcolor.joint_boundary_restart import (
    propagate_joint_boundary, restart_joint_boundary_names,
)
from fourcolor.whole_lines import build_whole_lines
from scripts.analyze_line_generations import derive_generations, extract_whole_contacts
from scripts.validate_frontier_restart import (
    anchored_domains, complete_subsets, file_sha, independent_geometry, json_value, read_json,
)
from scripts.validate_global_restart import digest, write_report
from scripts.validate_peer_batches import independent_batches, independent_choice
from scripts.validate_relation_frontier import (
    allowed_relations, check_relational_fixed_point, decode, decoded_matrix, replay_hall,
)
from scripts.validate_staged_levels import audit_boundary, independent_initial_selection

BASELINE = "peer-batch-ready-sides-v4"
MODES = ("domains", "joint")
REPORT = ROOT / "outputs/peer-batches-full-2026-09-19.json.gz"
REPORT_SHA = "fb004374e06ee0ace87328a8559e108b23e0e9b71663e1a35158738a5e3ad543"
DIAGNOSIS = ROOT / "outputs/peer-batches-failure-diagnosis-2026-09-19.json"
DIAGNOSIS_SHA = "fbddf644e5d3bd9a7fa1b38c8b7258b53ecbfbba40f767ff140edabc3bc70a67"
NEW_SOURCES = (
    "fourcolor/joint_boundary.py", "fourcolor/joint_boundary_restart.py",
    "scripts/validate_joint_boundary.py", "tests/test_joint_boundary_experiment.py",
    "scripts/validate_peer_batches.py", "scripts/validate_staged_levels.py",
    "scripts/analyze_line_generations.py", "scripts/validate_frontier_restart.py",
    "scripts/validate_global_restart.py",
    "scripts/validate_relation_frontier.py",
    "tests/test_joint_boundary.py", "tests/test_joint_boundary_restart.py",
    "tests/test_joint_boundary_cli.py", "scripts/name_joint_boundary_map.py",
)


def require(condition, message):
    """Keep experiment validation active even if this module is imported with -O."""
    if not condition:
        raise ValueError(message)


def select_inventory(report, diagnosis):
    """Fix all nine failures and all forty prior diagnostics, without outcome tuning."""
    require(report["full_corpus_run"] and report["policy"] == BASELINE,
            "expected the frozen full v4 archive")
    failures, controls = set(report["failure_keys"]), set(report["diagnostic_keys"])
    require(len(failures) == 9 and len(controls) == 40 and not failures & controls,
            "the fixed nine-plus-forty selection changed")
    require(set(report["detailed_examples"]) == failures | controls,
            "the archive must contain exactly the declared full details")
    diagnosed = {row["key"]: row for row in diagnosis["records"]}
    require(len(diagnosed) == len(diagnosis["records"]) and set(diagnosed) == failures,
            "diagnosis must cover every failure exactly once")
    details = report["detailed_examples"]
    for key in sorted(failures | controls):
        detail = details[key]
        require(detail["key"] == key, "detail key mismatch")
        require(detail["outcome"]["status"] == ("conflict" if key in failures else "solved"),
                "frozen control/failure status changed")
        if key in failures:
            require(diagnosed[key]["first_fatal_choice_proved"], "unproved fatal position")
    return sorted(failures | controls), failures, controls, diagnosed


def check_coloring(plane, adjacent, colors, anchors):
    """Check actual shared-boundary inequalities and all declared dart commitments."""
    require(isinstance(colors, list) and len(colors) == len(adjacent), "wrong coloring length")
    require(all(type(color) is int and 1 <= color <= 4 for color in colors),
            "colors must be positive names 1..4")
    require(all(colors[a] != colors[b] for a, row in enumerate(adjacent) for b in row),
            "coloring violates an actual shared boundary")
    require(all(colors[plane.face_of_dart[int(dart)]] in allowed
                for dart, allowed in anchors.items()), "coloring violates a commitment")
    return {"passed": True, "vertices": len(colors),
            "real_dual_edges": sum(map(len, adjacent)) // 2,
            "anchor_darts": len(anchors)}


def witness_survives(colors, outcome):
    """Independently verify a known legal completion survives every unary/pair result."""
    n = len(colors)
    require(len(outcome["domains"]) == n and len(outcome["relations"]) == n,
            "witness and outcome sizes differ")
    require(all(color in outcome["domains"][side] for side, color in enumerate(colors)),
            "a known legal completion lost a unary value")
    for a in range(n):
        require(len(outcome["relations"][a]) == n, "relation matrix must be square")
        for b in range(n):
            bit = 1 << (4 * (colors[a] - 1) + colors[b] - 1)
            require(outcome["relations"][a][b] & bit,
                    "a known legal completion lost a binary pair")
    return {"passed": True, "unary_values": n, "ordered_pairs": n * n}


def independent_book_scopes(adjacent):
    """Find all nontrivial K2 joins by independent shared-neighbor set intersections."""
    return [[a, b, *sorted(adjacent[a] & adjacent[b])]
            for a in range(len(adjacent)) for b in sorted(adjacent[a])
            if a < b and len(adjacent[a] & adjacent[b]) >= 3]


def exhaustive_local_projection(relations, scope):
    """Enumerate a declared small book only; never solve the surrounding map.

    This deliberately slow oracle checks conditioned local path consistency.
    It is not called by either production restart and is capped at eight local
    vertices so larger future geometries cannot silently trigger a whole-map
    assignment enumeration.
    """
    require(2 <= len(scope) <= 8 and len(scope) == len(set(scope)),
            "local oracle requires 2..8 distinct scoped vertices")
    domains = [[c for c in range(1, 5)
                if relations[side][side] & (1 << (5 * (c - 1)))] for side in scope]
    projected = [[0] * len(scope) for _ in scope]
    assignments = survivors = 0
    for colors in product(*domains):
        assignments += 1
        if any(not relations[a][b] & (1 << (4 * (colors[i] - 1) + colors[j] - 1))
               for i, a in enumerate(scope) for j, b in enumerate(scope) if i < j):
            continue
        survivors += 1
        for i, color_a in enumerate(colors):
            for j, color_b in enumerate(colors):
                projected[i][j] |= 1 << (4 * (color_a - 1) + color_b - 1)
    return {"scope": scope, "assignments_examined": assignments,
            "surviving_assignments": survivors, "projected_relations": projected}


def source_hashes(report):
    """Include every frozen baseline producer and the new producer/checker files."""
    names = sorted(set(report["source_sha256"]) | set(NEW_SOURCES))
    hashes = {name: file_sha(ROOT / name) for name in names}
    require(all(hashes[name] == expected for name, expected in report["source_sha256"].items()),
            "a frozen baseline source changed")
    return hashes


def independent_books(plane, adjacent):
    """Rebuild all geometric edge witnesses without using the production finder."""
    books = []
    for scope in independent_book_scopes(adjacent):
        a, b, *boundary = scope
        needed = {(a, b)} | {tuple(sorted((core, shore)))
                             for core in (a, b) for shore in boundary}
        witnesses = []
        for pair in sorted(needed):
            edges = [edge for edge in range(len(plane.edges))
                     if tuple(sorted(plane.shores(edge))) == pair]
            require(bool(edges), "book adjacency has no real separating edge")
            witnesses.append({"sides": list(pair), "raw_edge_ids": edges})
        books.append({"internal": [a, b], "boundary": boundary, "edge_witnesses": witnesses})
    return books


def set_closure(matrix):
    """Compute local path consistency using sets and full sweeps, independently.

    No production bit operations or worklist are used. The common greatest
    shrinking fixed point is unique; conflicting runs may stop at different
    first empty entries, so only conflict status is compared in that case.
    """
    relations = [[set(entry) for entry in row] for row in matrix]
    n = len(relations)
    if any(not entry for row in relations for entry in row):
        return relations, True
    changed = True
    while changed:
        changed = False
        for i in range(n):
            for j in range(i, n):
                for k in range(n):
                    supported = {(a, b) for a, c in relations[i][k]
                                 for middle, b in relations[k][j] if c == middle}
                    after = relations[i][j] & supported
                    if after != relations[i][j]:
                        changed = True
                        relations[i][j] = after
                        relations[j][i] = {(b, a) for a, b in after}
                        if not after:
                            return relations, True
    return relations, False


def encode_pairs(values):
    """Encode a checker set for exact portable transcript comparisons only."""
    return sum(1 << (4 * (a - 1) + b - 1) for a, b in values)


def replay_boundary(relations, books, result, mode):
    """Recompute every local branch, union and deletion with independent sets."""
    work = [[set(entry) for entry in row] for row in relations]
    events = result["events"]
    changed, conflict = False, any(not entry for row in work for entry in row)
    counts = Counter()
    expected_event_index = 0
    for index, book in enumerate(books):
        if conflict:
            break
        require(expected_event_index < len(events), "missing boundary event")
        event = events[expected_event_index]
        expected_event_index += 1
        vertices = book["internal"] + book["boundary"]
        require(event["book_index"] == index and event["vertices"] == vertices
                and event["mode"] == mode, "boundary event identity differs")
        local = [[work[a][b] for b in vertices] for a in vertices]
        require(decoded_matrix(event["input_relations"], len(vertices)) == local,
                "boundary local input differs")
        counts["book_checks"] += 1
        if mode == "domains":
            domains = [{a for a, b in local[i][i]} for i in range(2, len(vertices))]
            supported = [set() for _ in domains]
            palettes = []
            for palette in combinations(range(1, 5), 2):
                common = [domain & set(palette) for domain in domains]
                viable = all(common)
                palettes.append({"colors": list(palette), "supported": viable})
                counts["palette_checks"] += 1
                if viable:
                    for union, values in zip(supported, common):
                        union.update(values)
            require(event["palettes"] == palettes, "palette viability differs")
            allowed = [[set(entry) for entry in row] for row in local]
            for i, values in enumerate(supported, 2):
                allowed[i][i] = {(a, a) for a in values}
        else:
            colors = [[a, b] for a, _ in sorted(local[0][0])
                      for b, _ in sorted(local[1][1]) if (a, b) in local[0][1]]
            require([branch["colors"] for branch in event["branches"]] == colors,
                    "conditional branches omitted, reordered or added")
            allowed = [[set() for _ in vertices] for _ in vertices]
            for branch in event["branches"]:
                a, b = branch["colors"]
                conditioned = [[set(entry) for entry in row] for row in local]
                conditioned[0][0], conditioned[1][1] = {(a, a)}, {(b, b)}
                closure, branch_conflict = set_closure(conditioned)
                require(branch["status"] == ("conflict" if branch_conflict else "consistent"),
                        "conditional conflict status differs")
                counts["conditional_cases"] += 1
                counts["independent_conditional_closures"] += 1
                if not branch_conflict:
                    require(decoded_matrix(branch["relations"], len(vertices)) == closure,
                            "conditional closure differs")
                    for i, row in enumerate(closure):
                        for j, entry in enumerate(row):
                            allowed[i][j].update(entry)
        updates = []
        for i, a in enumerate(vertices):
            for j in range(i, len(vertices)):
                b = vertices[j]
                before = work[a][b]
                after = before & allowed[i][j]
                if after != before:
                    changed = True
                    removed = before - after
                    updates.append({"sides": [a, b], "before": encode_pairs(before),
                                    "after": encode_pairs(after), "removed": encode_pairs(removed)})
                    counts["relation_bits_removed"] += len(removed) * (1 if i == j else 2)
                    if i == j:
                        counts["domain_values_removed"] += len(removed)
                    work[a][b] = after
                    work[b][a] = {(y, x) for x, y in after}
        require(event["updates"] == updates, "boundary updates differ")
        conflict = any(not entry for row in work for entry in row)
        require(event["conflict"] is conflict, "boundary event conflict differs")
    require(expected_event_index == len(events), "extra boundary events after scan/conflict")
    require(result["changed"] is changed and result["conflict"] is conflict,
            "boundary scan flags differ")
    require(decoded_matrix(result["relations"], len(work)) == work, "boundary final matrix differs")
    for name in ("book_checks", "conditional_cases", "palette_checks",
                 "relation_bits_removed", "domain_values_removed"):
        require(result["statistics"][name] == counts[name], "boundary counter differs: " + name)
    return work, counts


def replay_joint_propagation(plane, adjacent, anchors, outcome, books, subsets):
    """Replay Hall, all global pair deletions, and each conditional book scan."""
    require(outcome["books"] == books and outcome["mode"] in MODES, "book cache or mode differs")
    require(outcome["backtracks"] == outcome["choices"] == 0
            and outcome["palette"] == [1, 2, 3, 4], "propagation changed commitments or palette")
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
        require(relations == decoded_matrix(phase["relation_input"], len(domains)),
                "global relation input differs")
        if hall_conflict:
            require(not phase["relation_trace"], "pair events after Hall conflict")
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
            stats["global_relation_events"] += 1
        conflict = hall_conflict or any(not entry for row in relations for entry in row)
        require(phase["relation_conflict"] is conflict, "global conflict differs")
        boundary = phase["boundary_filter"]
        if conflict:
            require(boundary is None, "boundary scan after global conflict")
        else:
            check_relational_fixed_point(relations)
            require(boundary is not None, "missing boundary scan")
            relations, counts = replay_boundary(relations, books, boundary, outcome["mode"])
            stats.update(counts)
            conflict = boundary["conflict"]
        domains = [{a for a, b in relations[i][i]} for i in range(len(domains))]
        if index + 1 < len(outcome["phases"]):
            require(not conflict and (boundary["changed"] or domains != hall_domains),
                    "continued propagation without a strict loss")
        else:
            require(conflict or (not boundary["changed"] and domains == hall_domains),
                    "propagation stopped before the joint fixed point")
        previous = relations
        stats["propagation_phases"] += 1
    expected = "conflict" if conflict else "solved" if all(len(d) == 1 for d in domains) else "underdetermined"
    require(outcome["status"] == expected and outcome["domains"] == [sorted(d) for d in domains],
            "propagation status or domains differ")
    require(decoded_matrix(outcome["relations"], len(domains)) == relations,
            "propagation final relations differ")
    require(outcome["hall_conflict"] == outcome["phases"][-1]["hall_conflict"],
            "propagation Hall certificate differs")
    metadata_totals = Counter()
    for phase in outcome["phases"]:
        if phase["boundary_filter"] is not None:
            metadata_totals.update(phase["boundary_filter"]["statistics"])
    require(outcome["statistics"] == dict(metadata_totals), "propagation statistics aggregation differs")
    for name in ("book_checks", "conditional_cases", "palette_checks",
                 "relation_bits_removed", "domain_values_removed"):
        require(outcome["statistics"].get(name, 0) == stats[name],
                "independently checked propagation counter differs: " + name)
    return [sorted(d) for d in domains], stats


def verify_new_run(geometry, result):
    """Independently check geometry, readiness, every active choice and final names.

    This checker does not mislabel a nonempty relation table as a completion.
    Every propagation deletion is independently replayed with Python sets.
    """
    plane, adjacent = independent_geometry(geometry)
    mode = result["mode"]
    require(mode in MODES and result["policy"] == "peer-batch-boundary-" + mode + "-pilot",
            "run mode/policy differs")
    model = build_whole_lines(geometry)
    contacts, _ = extract_whole_contacts(model)
    generations = derive_generations(contacts)
    levels = {}
    for line in model.lines:
        name, source = line["id"], generations[line["id"]]
        levels[name] = {"level": None if source["depth"] is None else source["depth"] + 1,
                        "parents": source["parents"], "endpoint_contacts": contacts[name],
                        "endpoints": line["endpoints"]}
    require(result["levels"] == levels, "generation levels differ")
    require(result["unranked_mothers"] == sorted(name for name, info in levels.items()
                                                if info["level"] is None), "unranked mothers differ")
    batches = independent_batches(model, levels)
    require(json_value(result["batch_geometry"]) == json_value(batches), "ready batches differ")
    units = current_segments(model)
    require(json_value(result["units"]) == json_value(units), "current segments differ")
    require(result["backtracks"] == 0 and result["old_colors_read"] is False,
            "production used a retry or archived colors")
    frame = next(line for line in model.lines if line["id"] == "frame")
    first = frame["spans"][0]["dart"]
    anchors = {int(dart): names for dart, names in result["initial_anchors_by_dart"].items()}
    require(anchors == {first: [1]} and plane.face_of_dart[first] == geometry["outerFace"],
            "outside-only initialization changed")
    trace, calls = result["trace"], result["propagation_phases"]
    require(len(calls) == len(trace) + 1 == result["choices"] + 1, "phase/choice count differs")
    books, subsets = independent_books(plane, adjacent), complete_subsets(adjacent)
    previous, statistics = None, Counter()
    for index, call in enumerate(calls):
        if index:
            step = trace[index - 1]
            require(plane.face_of_dart[step["dart"]] == step["side"], "choice dart/side differs")
            if index == 1:
                selected, initialization_mode, eligible = independent_initial_selection(
                    model, units, levels, contacts, previous, adjacent)
                require(step["choice_kind"] == "initial-retained-name" and step["symbol"] == 2,
                        "first retained normalization differs")
                require(result["initialization"] == {
                    "mode": initialization_mode, "eligible_mothers": eligible,
                    "mother": selected["mother"], "side": selected["side"], "dart": selected["dart"],
                    "frame_boundary_edges": selected["frame_boundary_edges"],
                    "domain_before": [2, 3, 4], "symbol": 2, "historical_frame_pair": [1, 2],
                    "coarse_split_pair_unordered": [2, 3] if eligible else None,
                    "birth_pair_is_not_a_final_profile_constraint": True,
                    "outside_dart": first, "outside_side": geometry["outerFace"],
                    "prebound_final_inner_anchor": False}, "initialization metadata differs")
            else:
                selected = independent_choice(model, units, levels, batches, previous, adjacent)
                require(step["choice_kind"] == "greedy-not-a-proved-safe-extension",
                        "later choice was presented as a guaranteed extension")
            for name, expected in selected.items():
                require(json_value(step[name]) == json_value(expected), "choice differs: " + name)
            require(step["domain"] == previous[step["side"]]
                    and step["symbol"] == min(step["domain"]), "greedy name/domain differs")
            audit_boundary(model, previous, step["side"], step["boundary"])
            anchors[step["dart"]] = [step["symbol"]]
        require(json_value(call["anchors_by_dart"]) == json_value(anchors), "phase anchors differ")
        outcome = call["outcome"]
        require(outcome["mode"] == mode, "phase mode differs from run mode")
        require(len(outcome["domains"]) == len(adjacent), "phase has wrong domain count")
        previous, counts = replay_joint_propagation(plane, adjacent, anchors, outcome, books, subsets)
        statistics.update(counts)
        if index < len(trace):
            require(outcome["status"] == "underdetermined", "choice follows a terminal phase")
    require(result["status"] in ("solved", "conflict"), "unexpected final status")
    require(json_value(result["anchors_by_dart"]) == json_value(anchors), "final anchors differ")
    for name in ("status", "domains", "relations", "hall_conflict"):
        require(result[name] == calls[-1]["outcome"][name], "final outcome differs: " + name)
    metadata_totals = Counter()
    for call in calls:
        metadata_totals.update(call["outcome"]["statistics"])
    require(result["statistics"] == dict(metadata_totals), "run statistics aggregation differs")
    legality = (check_coloring(plane, adjacent, result["colors"], anchors)
                if result["status"] == "solved" else None)
    if legality is None:
        require(result["colors"] is None, "a conflict must not supply a solution")
    return {"passed": True, "method": "independent-geometry-ready-schedule-and-set-proof-replay",
            "propagation_deletions_independently_replayed": True,
            "local_revision_work_counter_independently_replayed": False,
            "active_choices": len(trace), "final_legality": legality,
            "claim": "checked-complete-coloring" if legality else "checked-greedy-commitment-conflict",
            "statistics": dict(statistics)}


def summarize(records, fatal_records):
    """Retain every improvement, equality and regression on each declared cohort."""
    result = []
    for mode in MODES:
        for cohort in ("all", "frozen-failure", "prior-diagnostic-control"):
            chosen = [row for row in records if cohort == "all" or row["cohort"] == cohort]
            counts = Counter((row["baseline_status"], row["runs"][mode]["status"]) for row in chosen)
            result.append({"mode": mode, "cohort": cohort, "drawings": len(chosen),
                           "statuses": dict(Counter(row["runs"][mode]["status"] for row in chosen)),
                           "fixed_failures": counts[("conflict", "solved")],
                           "regressions": counts[("solved", "conflict")],
                           "regression_keys": [row["key"] for row in chosen
                                               if row["baseline_status"] == "solved"
                                               and row["runs"][mode]["status"] == "conflict"]})
    return {"full_trajectory_comparison": result,
            "frozen_first_fatal_candidates_excluded": {
                mode: sum(row["modes"][mode]["fatal_name_excluded"] for row in fatal_records)
                for mode in MODES},
            "frozen_failure_states": len(fatal_records),
            "full_corpus_run": False, "unseen_holdout": False}


def audit_fatal_state(detail, diagnosis):
    """Compare filters before the same archived fatal commitment, never retry it."""
    geometry, original = detail["geometry"], detail["outcome"]
    index = diagnosis["first_fatal_choice_index_one_based"] - 1
    step = original["trace"][index]
    frozen = original["propagation_phases"][index]
    anchors = {int(dart): values for dart, values in frozen["anchors_by_dart"].items()}
    plane, adjacent = independent_geometry(geometry)
    model = build_whole_lines(geometry)
    books = independent_books(plane, adjacent)
    require(find_boundary_books(model) == books, "production book geometry differs")
    witness = diagnosis["witness"]["colors"]
    legality = check_coloring(plane, adjacent, witness, anchors)
    witness_survives(witness, frozen["outcome"])
    local_oracles = []
    for book in books:
        scope = book["internal"] + book["boundary"]
        oracle = exhaustive_local_projection(frozen["outcome"]["relations"], scope)
        filtered = filter_boundary_books(frozen["outcome"]["relations"], [book], mode="joint")
        projected = [[filtered["relations"][a][b] for b in scope] for a in scope]
        require(all(actual & ~projected[i][j] == 0
                    for i, row in enumerate(oracle["projected_relations"])
                    for j, actual in enumerate(row)), "local filter removed an actual scoped assignment")
        oracle["producer_matches_exact_projection"] = projected == oracle["projected_relations"]
        local_oracles.append(oracle)
    modes = {}
    for mode in MODES:
        single = filter_boundary_books(frozen["outcome"]["relations"], books, mode=mode)
        single_domains = [[color for color in range(1, 5)
                           if row[side] & (1 << (5 * (color - 1)))]
                          for side, row in enumerate(single["relations"])]
        witness_survives(witness, {"domains": single_domains, "relations": single["relations"]})
        # A single scan and a full interleaved fixed point are reported separately.
        outcome = propagate_joint_boundary(model, anchors, books=books, mode=mode)
        _, proof_stats = replay_joint_propagation(
            plane, adjacent, anchors, outcome, books, complete_subsets(adjacent))
        survival = witness_survives(witness, outcome)
        modes[mode] = {"fatal_name_excluded": step["symbol"] not in outcome["domains"][step["side"]],
                       "fatal_side_domain_before": frozen["outcome"]["domains"][step["side"]],
                       "fatal_side_domain_after": outcome["domains"][step["side"]],
                       "single_scan_changed": single["changed"],
                       "single_scan_statistics": single["statistics"],
                       "known_completion_survives": survival,
                       "independent_proof_statistics": dict(proof_stats),
                       "outcome": outcome}
    return {"key": detail["key"], "aliases": detail["aliases"],
            "face_count": detail["face_count"], "first_fatal_choice_index_one_based": index + 1,
            "fatal_side": step["side"], "fatal_name": step["symbol"],
            "frozen_anchors_by_dart": anchors, "book_count": len(books),
            "known_completion": witness, "known_completion_legality": legality,
            "local_assignment_oracles": local_oracles, "modes": modes}


def build_report(report_path=REPORT, diagnosis_path=DIAGNOSIS):
    """Run both new policies once per fixed geometry and retain every transcript."""
    require(file_sha(report_path) == REPORT_SHA, "v4 archive is not the frozen evidence")
    require(file_sha(diagnosis_path) == DIAGNOSIS_SHA, "first-fatal diagnosis changed")
    archived, diagnosis = read_json(report_path), read_json(diagnosis_path)
    keys, failures, controls, diagnosed = select_inventory(archived, diagnosis)
    require(diagnosis["sources"] == [{"filename": report_path.name, "sha256": REPORT_SHA,
                                      "full_corpus_run": True, "failed_inventory_records": 9}],
            "first-fatal diagnosis references a different archive")
    hashes = source_hashes(archived)
    inventory = {row["key"]: row for row in archived["drawings"]}
    records, fatal_records, totals = [], [], Counter()
    began = perf_counter()
    # First inspect the nine fixed historical states. These checks cannot feed
    # witnesses, domains or a favorable order into either production trajectory.
    for number, key in enumerate(sorted(failures), 1):
        fatal_records.append(audit_fatal_state(archived["detailed_examples"][key], diagnosed[key]))
        print({"phase": "frozen-first-fatal", "checked": number, "total": 9,
               "excluded": {mode: fatal_records[-1]["modes"][mode]["fatal_name_excluded"]
                            for mode in MODES}}, flush=True)
    for number, key in enumerate(keys, 1):
        detail = archived["detailed_examples"][key]
        geometry = detail["geometry"]
        require(digest(geometry) == inventory[key]["geometry_sha256"], "archived geometry hash differs")
        _, adjacent = independent_geometry(geometry)
        row = {"key": key, "aliases": detail["aliases"], "face_count": len(adjacent),
               "geometry_sha256": digest(geometry), "geometry": geometry,
               "cohort": "frozen-failure" if key in failures else "prior-diagnostic-control",
               "baseline_status": detail["outcome"]["status"],
               "baseline_choices": detail["outcome"]["choices"], "runs": {}}
        for mode in MODES:
            started = perf_counter()
            result = restart_joint_boundary_names(geometry, mode=mode)
            elapsed = perf_counter() - started
            started = perf_counter()
            verification = verify_new_run(geometry, result)
            audit_seconds = perf_counter() - started
            totals.update(verification["statistics"])
            row["runs"][mode] = {"status": result["status"], "choices": result["choices"],
                                  "runtime_seconds_single_call": elapsed,
                                  "audit_seconds": audit_seconds,
                                  "statistics": result["statistics"],
                                  "verification": verification, "outcome": result}
            if mode == "domains":
                fields = ("status", "trace", "domains", "relations", "colors", "initialization")
                matches = all(json_value(result[name]) == json_value(detail["outcome"][name])
                              for name in fields)
                require(matches, "unary ablation differs from archived v4")
                row["runs"][mode]["ablation_matches_frozen_v4"] = True
        records.append(row)
        print({"phase": "new-full-trajectories", "checked": number, "total": len(keys),
               "cohort": row["cohort"], "baseline": row["baseline_status"],
               "statuses": {mode: row["runs"][mode]["status"] for mode in MODES},
               "seconds": round(perf_counter() - began, 1)}, flush=True)
    require(source_hashes(archived) == hashes, "experiment sources changed during execution")
    require(file_sha(report_path) == REPORT_SHA and file_sha(diagnosis_path) == DIAGNOSIS_SHA,
            "frozen input bytes changed during execution")
    return {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "experiment": "Geometry-certified book boundary filters on frozen v4 diagnostics",
            "full_corpus_run": False, "unseen_holdout": False,
            "input_evidence": [{"filename": report_path.name, "sha256": REPORT_SHA},
                               {"filename": diagnosis_path.name, "sha256": DIAGNOSIS_SHA}],
            "source_sha256": hashes, "source_sha256_end": hashes,
            "source_hashes_unchanged": True, "selected_keys": keys,
            "selection": {"rule": "All nine v4 failures plus all forty previously declared diagnostics",
                          "frozen_failure_keys": sorted(failures), "prior_diagnostic_keys": sorted(controls)},
            "production_attempts": len(records) * len(MODES), "baseline_newly_rerun": False,
            "archived_colors_used_by_production": False,
            "archived_colors_used_by_checker": True,
            "independent_proof_totals": dict(totals),
            "summary": summarize(records, fatal_records),
            "records": records, "fatal_states": fatal_records,
            "execution": {"wall_seconds": perf_counter() - began,
                          "timing_interpretation": "One call per mode; descriptive costs, not a speed benchmark"},
            "limits": [
                "The 49 inspected drawings are selected diagnostics, not the 7069-map full corpus or unseen holdout.",
                "Related history prefixes are not independent random samples.",
                "Excluding one old fatal name differs from completing a new greedy trajectory.",
                "Joint mode explicitly conditions on at most 12 internal color pairs per book scan.",
                "Conditional local closure is not whole-map search and does not make greedy choices universally safe.",
                "Full certificates are independently replayed; finite soundness tests are not a Four-Color proof.",
                "Single-call timings include transcript generation and cannot establish an algorithmic speedup."]}


def main():
    """Write an exclusive, hash-bound diagnostic experiment and a compact summary."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--diagnosis", type=Path, default=DIAGNOSIS)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    require(not sys.flags.optimize, "independent legacy checks require Python without -O")
    require(not args.output.exists() and not args.summary.exists()
            and args.output.resolve() != args.summary.resolve(), "choose two distinct new outputs")
    report = build_report(args.report, args.diagnosis)
    write_report(args.output, report)
    small = {name: value for name, value in report.items() if name not in ("records", "fatal_states")}
    small["report"] = {"filename": args.output.name, "sha256": file_sha(args.output)}
    write_report(args.summary, small)
    print(report["summary"], flush=True)


if __name__ == "__main__":
    main()

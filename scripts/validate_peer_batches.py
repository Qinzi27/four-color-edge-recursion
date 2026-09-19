"""Independent coarse-partition and ready-side proof replay for v4.

The production partition builder and scheduler are deliberately not imported.
Coarse cells are rebuilt by breadth-first reachability across inactive real
edges; their first singleton stage is compared with every recorded ready stage.
This certifies finite executions, not universal greedy extendibility.
"""

from collections import Counter, deque
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.closed_support import supported_cycle_units
from fourcolor.global_restart import current_segments
from fourcolor.whole_lines import build_whole_lines
from scripts.analyze_line_generations import derive_generations, extract_whole_contacts
from scripts.validate_frontier_restart import (
    complete_subsets, independent_geometry, json_value, verify_result,
)
from scripts.validate_relation_frontier import replay_propagation
from scripts.validate_staged_levels import audit_boundary, independent_initial_selection


POLICY = "peer-batch-ready-sides-v4"


def independent_batches(model, levels):
    """Compute partitions with BFS, without producer DSU or max-boundary code.

    The unknown bucket is merely a final activation stage, not an invented
    rooted generation. Real bridges and virtual island connectors never merge
    distinct sides and therefore cannot postpone a side's readiness.
    """
    unknown = [name for name, info in levels.items() if info["level"] is None]
    known_max = max(info["level"] for info in levels.values() if info["level"] is not None)
    unranked_stage = known_max + 1 if unknown else None
    stages = {name: unranked_stage if info["level"] is None else info["level"]
              for name, info in levels.items()}
    count = len(model.plane_map.faces)
    first_singleton = [None] * count
    records, previous_cells = [], None
    for stage in sorted(set(stages.values())):
        opposite = [set() for _ in range(count)]
        for edge, mother in model.edge_owner.items():
            first, second = model.plane_map.shores(edge)
            if stages[mother] > stage and first != second:
                opposite[first].add(second)
                opposite[second].add(first)
        unseen, cells = set(range(count)), []
        while unseen:
            start = min(unseen)
            unseen.remove(start)
            reached, pending = {start}, deque([start])
            while pending:
                current = pending.popleft()
                for following in sorted(opposite[current]):
                    if following in unseen:
                        unseen.remove(following)
                        reached.add(following)
                        pending.append(following)
            cells.append(sorted(reached))
        cells.sort()
        if previous_cells is not None:
            # Activation only refines cells; it never merges previously split ones.
            assert all(any(set(cell) <= set(parent) for parent in previous_cells)
                       for cell in cells)
        ready = sorted(cell[0] for cell in cells if len(cell) == 1)
        newly = [side for side in ready if first_singleton[side] is None]
        for side in newly:
            first_singleton[side] = stage
        records.append({"stage": stage,
                        "new_mothers": sorted(name for name, value in stages.items() if value == stage),
                        "active_mothers": sorted(name for name, value in stages.items() if value <= stage),
                        "coarse_cells": cells, "ready_sides": ready,
                        "newly_ready_sides": newly})
        previous_cells = cells
    assert all(stage is not None for stage in first_singleton)
    assert records[-1]["coarse_cells"] == [[side] for side in range(count)]
    return {"mother_stages": stages, "unranked_stage": unranked_stage,
            "stages": records, "side_ready_stage": first_singleton}


def independent_choice(model, units, levels, batches, domains, adjacent):
    """Reconstruct the least-ready-stage occurrence before all local tie keys.

    Eligibility is filtered BEFORE choosing a unit's most urgent occurrence.
    The q weight still counts every unresolved shore of that unit, including
    higher-stage ones: readiness changes scheduling, not current constraints.
    """
    ready = batches["side_ready_stage"]
    active = min(ready[side] for side, domain in enumerate(domains) if len(domain) > 1)
    eligible = {side for side, domain in enumerate(domains)
                if len(domain) > 1 and ready[side] == active}
    possible = {unit["mother"] for unit in units if unit["mother"] != "frame"
                and any(side in eligible for side, _ in unit["occurrences"])}

    def mother_key(name):
        """Reproduce only the stated geometry convention, not a selector call."""
        level = levels[name]["level"]
        points = tuple(sorted((point[1], point[0]) for point in levels[name]["endpoints"]))
        return level is None, level if level is not None else 0, points, name

    assert possible, "an unresolved side needs a real internal occurrence"
    mother = min(possible, key=mother_key)
    supports = supported_cycle_units(model, domains, units)
    rows, by_id = [], {unit["id"]: unit for unit in units}

    def score(side):
        """Count distinct unresolved neighbors without trusting recorded scores."""
        return 4 - len(domains[side]), sum(len(domains[n]) > 1 for n in adjacent[side])

    for unit in units:
        if unit["mother"] != mother:
            continue
        candidates = [(side, dart) for side, dart in unit["occurrences"] if side in eligible]
        if not candidates:
            continue
        side, dart = max(candidates, key=lambda pair: score(pair[0]))
        unresolved = [other for other, _ in unit["occurrences"] if len(domains[other]) > 1]
        q = sum(4 - len(domains[other]) for other in unresolved)
        rows.append({"unit": unit["id"], "mother": mother, "side": side, "dart": dart,
                     "unresolved_shores": unresolved, "urgency": score(side)[0],
                     "unresolved_neighbors": score(side)[1], "constraint_weight": q,
                     "including_named_weight": sum(4 - len(domains[other])
                                                   for other, _ in unit["occurrences"]),
                     "closed_support": supports[unit["id"]],
                     "priority": score(side) + (q, int(supports[unit["id"]]["supported"])),
                     "level": levels[mother]["level"], "parents": levels[mother]["parents"],
                     "selection_group": "unranked-peer" if levels[mother]["level"] is None else "rooted",
                     "ready_stage": ready[side], "active_stage": active,
                     "eligible_side_ids": sorted(eligible), "coarse_cell": [side]})
    highest = max(row["priority"] for row in rows)
    ties = sorted((row for row in rows if row["priority"] == highest),
                  key=lambda row: (by_id[row["unit"]]["t0"], row["dart"]))
    selected = {**ties[0], "tied_units": [row["unit"] for row in ties]}
    partition = next(record for record in batches["stages"] if record["stage"] == active)
    assert [selected["side"]] in partition["coarse_cells"]
    return selected


def verify_run(geometry, result):
    """Check all geometry stages, choices, deletions and terminal claims."""
    plane, adjacent = independent_geometry(geometry)
    model = build_whole_lines(geometry)
    contacts, _ = extract_whole_contacts(model)
    generations = derive_generations(contacts)
    assert result["policy"] == POLICY and result["backtracks"] == 0
    assert result["old_colors_read"] is False and result["local_budget"] is None
    assert result["status"] in ("solved", "conflict")
    levels = {}
    for line in model.lines:
        name, source = line["id"], generations[line["id"]]
        levels[name] = {"level": None if source["depth"] is None else source["depth"] + 1,
                        "parents": source["parents"], "endpoint_contacts": contacts[name],
                        "endpoints": line["endpoints"]}
    assert result["levels"] == levels
    assert result["unranked_mothers"] == sorted(name for name, info in levels.items()
                                               if info["level"] is None)
    batches = independent_batches(model, levels)
    assert json_value(result["batch_geometry"]) == json_value(batches)
    units = current_segments(model)
    assert json_value(result["units"]) == json_value(units)
    frame = next(line for line in model.lines if line["id"] == "frame")
    first = frame["spans"][0]["dart"]
    initial = {int(key): value for key, value in result["initial_anchors_by_dart"].items()}
    assert initial == {first: [1]} and plane.face_of_dart[first] == geometry["outerFace"]
    calls, trace = result["propagation_phases"], result["trace"]
    assert result["choices"] >= 1
    assert len(calls) == len(trace) + 1 == result["choices"] + 1
    anchors, stats, previous = dict(initial), Counter(), None
    cliques = complete_subsets(adjacent)
    for index, call in enumerate(calls):
        if index:
            step = trace[index - 1]
            assert plane.face_of_dart[step["dart"]] == step["side"]
            if index == 1:
                selected, mode, eligible = independent_initial_selection(
                    model, units, levels, contacts, previous, adjacent)
                assert step["choice_kind"] == "initial-retained-name"
                assert step["symbol"] == 2 and sorted(previous[selected["side"]]) == [2, 3, 4]
                assert result["initialization"] == {
                    "mode": mode, "eligible_mothers": eligible,
                    "mother": selected["mother"], "side": selected["side"], "dart": selected["dart"],
                    "frame_boundary_edges": selected["frame_boundary_edges"],
                    "domain_before": [2, 3, 4], "symbol": 2, "historical_frame_pair": [1, 2],
                    "coarse_split_pair_unordered": [2, 3] if eligible else None,
                    "birth_pair_is_not_a_final_profile_constraint": True,
                    "outside_dart": first, "outside_side": geometry["outerFace"],
                    "prebound_final_inner_anchor": False,
                }
            else:
                selected = independent_choice(model, units, levels, batches, previous, adjacent)
                assert step["choice_kind"] == "greedy-not-a-proved-safe-extension"
            for name, value in selected.items():
                assert json_value(step[name]) == json_value(value), name
            side = step["side"]
            assert step["domain"] == sorted(previous[side])
            assert step["symbol"] == min(previous[side])
            audit_boundary(model, previous, side, step["boundary"])
            anchors[step["dart"]] = [step["symbol"]]
        assert json_value(call["anchors_by_dart"]) == json_value(anchors)
        previous, counts = replay_propagation(plane, adjacent, anchors, call["outcome"], cliques)
        stats.update(counts)
        if index + 1 < len(calls):
            assert call["outcome"]["status"] == "underdetermined"
    last = calls[-1]["outcome"]
    for field in ("status", "domains", "relations", "hall_conflict"):
        assert result[field] == last[field]
    assert json_value(anchors) == json_value(result["anchors_by_dart"])
    legality = verify_result(geometry, result, (plane, adjacent)) if result["status"] == "solved" else None
    if legality:
        assert legality["passed"]
    else:
        assert result["colors"] is None
    return {"passed": True,
            "claim": "complete-proper-four-names" if legality else
                     "this-greedy-commitment-set-has-no-extension-not-map-impossibility",
            "method": "independent-bfs-coarse-batches-ready-scheduling-and-set-proof-replay",
            "final_legality": legality, **stats}

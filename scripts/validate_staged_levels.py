"""Independent initialization and proof replay for stage-anchored names.

The producer's first-mother and first-side selectors are deliberately not used.
This checker reconstructs frame adjacency and true endpoint eligibility from
geometry, then reuses the already independent v2 audit for subsequent choices.
Passing a finite certificate proves that run, not universal greedy completion.
"""

from collections import Counter
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
from scripts.validate_level_sides_peer import audit_choice
from scripts.validate_relation_frontier import replay_propagation


POLICY = "stage-anchored-level-sides-v3"


def frame_edges_by_side(model):
    """Use positive-length real frame edges, never point contact or ancestry."""
    by_side = {}
    frame = next(line for line in model.lines if line["id"] == "frame")
    outer = model.plane_map.face_of_dart[frame["spans"][0]["dart"]]
    for span in frame["spans"]:
        first, second = model.plane_map.shores(span["edge"])
        assert first != second and outer in (first, second)
        inside = second if first == outer else first
        by_side.setdefault(inside, []).append(span["edge"])
    return {side: sorted(edges) for side, edges in by_side.items()}


def independent_initial_selection(model, units, levels, contacts, domains, adjacent):
    """Reconstruct initialization without calling the production scheduler.

    A whole mother qualifies through its two TRUE endpoints. Intermediate
    T/X ports do not disqualify it or become substitute endpoints. The local
    urgency includes every unresolved side in q, while the selected side must
    share an actual edge with the frame.
    """
    frame = next(line for line in model.lines if line["id"] == "frame")
    shared_frame = frame_edges_by_side(model)
    eligible = []
    eligible_units = []
    for line in model.lines:
        name = line["id"]
        if name == "frame" or not all("frame" in port for port in contacts[name]):
            continue
        qualifying_units = [unit for unit in units if unit["mother"] == name
                            and any(model.plane_map.shores(edge)[0] !=
                                    model.plane_map.shores(edge)[1] for edge in unit["edges"])
                            and any(side in shared_frame and len(domains[side]) > 1
                                    for side, _ in unit["occurrences"])]
        if not qualifying_units:
            continue
        eligible_units.extend(qualifying_units)
        level = levels[name]["level"]
        points = tuple(sorted((point[1], point[0]) for point in line["endpoints"]))
        eligible.append(((level is None, level if level is not None else 0, points), name))
    supports = supported_cycle_units(model, domains, units)

    def complete_selection(unit, side, dart):
        """Rebuild all displayed selection values, not just the chosen dart."""
        unresolved = [s for s, _ in unit["occurrences"] if len(domains[s]) > 1]
        urgency = 4 - len(domains[side])
        residual = sum(len(domains[n]) > 1 for n in adjacent[side])
        q = sum(4 - len(domains[s]) for s in unresolved)
        mother = unit["mother"]
        return {"unit": unit["id"], "mother": mother, "side": side, "dart": dart,
                "unresolved_shores": unresolved, "urgency": urgency,
                "unresolved_neighbors": residual, "constraint_weight": q,
                "including_named_weight": sum(4 - len(domains[s]) for s, _ in unit["occurrences"]),
                "closed_support": supports[unit["id"]],
                "priority": (urgency, residual, q, int(supports[unit["id"]]["supported"])),
                "level": levels[mother]["level"], "parents": levels[mother]["parents"],
                "selection_group": "initial-retained", "frame_boundary_edges": shared_frame[side]}

    if not eligible:
        dart = frame["spans"][0]["dart"] ^ 1
        side = model.plane_map.face_of_dart[dart]
        unit = next(unit for unit in units if unit["mother"] == "frame" and dart // 2 in unit["edges"])
        selected = {**complete_selection(unit, side, dart), "tied_units": [unit["id"]]}
        return selected, "frame-interior-no-eligible-through-mother", []
    eligible.sort()
    mother = eligible[0][1]
    rows = []
    for unit in eligible_units:
        if unit["mother"] != mother:
            continue
        unknown = [(side, dart) for side, dart in unit["occurrences"] if len(domains[side]) > 1]
        candidates = [(side, dart) for side, dart in unknown if side in shared_frame]
        if not candidates:
            continue

        def urgency(side):
            """Priorities count distinct unresolved opposite shores."""
            return 4 - len(domains[side]), sum(len(domains[n]) > 1 for n in adjacent[side])

        side, dart = max(candidates, key=lambda item: urgency(item[0]))
        priority = urgency(side) + (sum(4 - len(domains[s]) for s, _ in unknown),
                                    int(supports[unit["id"]]["supported"]))
        rows.append((priority, unit["t0"], dart, side, unit["id"]))
    assert rows, "qualifying first mother has no eligible unresolved frame-adjacent side"
    best_priority = max(row[0] for row in rows)
    tied = sorted((row for row in rows if row[0] == best_priority), key=lambda row: (row[1], row[2]))
    best = tied[0]
    unit = next(unit for unit in units if unit["id"] == best[4])
    selected = {**complete_selection(unit, best[3], best[2]),
                "tied_units": [row[4] for row in tied]}
    return selected, "first-through-mother-retained-side", [name for _, name in eligible]


def audit_boundary(model, domains, side, boundary):
    """Check the complete current boundary independently of producer metadata."""
    expected = {}
    for line in model.lines:
        for span in line["spans"]:
            first, second = model.plane_map.shores(span["edge"])
            if first == second or side not in (first, second):
                continue
            neighbor = second if first == side else first
            expected[span["edge"]] = {
                "edge": span["edge"], "mother": line["id"],
                "interval": [span["t0"], span["t1"]],
                "neighbor": neighbor, "neighbor_domain": sorted(domains[neighbor]),
            }
    assert len(boundary["sources"]) == len(expected)
    assert {source["edge"]: source for source in boundary["sources"]} == expected
    forbidden = {row["neighbor_domain"][0] for row in expected.values() if len(row["neighbor_domain"]) == 1}
    local = set(range(1, 5)) - forbidden
    assert boundary["direct_forbidden"] == sorted(forbidden)
    assert boundary["local_candidates"] == sorted(local)
    assert set(domains[side]) <= local
    assert boundary["derived_exclusions"] == sorted(local - set(domains[side]))
    assert boundary["one_allowed"] is (1 in domains[side])


def verify_run(geometry, result):
    """Replay outside-only normalization and every later recorded deduction.

    Levels are derived independently from endpoint contact sets. The initial
    side is not copied from result metadata, nor inferred from the final colors.
    Conflict is certified only for the current irreversible commitments.
    """
    plane, adjacent = independent_geometry(geometry)
    model = build_whole_lines(geometry)
    contacts, _ = extract_whole_contacts(model)
    generations = derive_generations(contacts)
    assert result["policy"] == POLICY and result["backtracks"] == 0
    assert result["old_colors_read"] is False and result["local_budget"] is None
    assert result["status"] in ("solved", "conflict")
    assert set(result["levels"]) == set(generations)
    for line in model.lines:
        name = line["id"]
        source = generations[name]
        assert result["levels"][name] == {
            "level": None if source["depth"] is None else source["depth"] + 1,
            "parents": source["parents"], "endpoint_contacts": contacts[name],
            "endpoints": line["endpoints"],
        }
    assert result["unranked_mothers"] == sorted(
        name for name, source in generations.items() if source["depth"] is None)
    units = current_segments(model)
    assert json_value(result["units"]) == json_value(units)
    frame = next(line for line in model.lines if line["id"] == "frame")
    first = frame["spans"][0]["dart"]
    initial = {int(key): value for key, value in result["initial_anchors_by_dart"].items()}
    assert initial == {first: [1]}
    assert plane.face_of_dart[first] == geometry["outerFace"]
    assert result["choices"] >= 1
    calls, trace = result["propagation_phases"], result["trace"]
    assert len(calls) == len(trace) + 1 == result["choices"] + 1
    anchors, stats, previous = dict(initial), Counter(), None
    cliques = complete_subsets(adjacent)
    for index, call in enumerate(calls):
        if index:
            step = trace[index - 1]
            assert plane.face_of_dart[step["dart"]] == step["side"]
            if index == 1:
                selected, mode, eligible = independent_initial_selection(
                    model, units, result["levels"], contacts, previous, adjacent)
                for name, value in selected.items():
                    assert json_value(step[name]) == json_value(value), name
                side = selected["side"]
                assert sorted(previous[side]) == step["domain"] == [2, 3, 4]
                assert step["symbol"] == 2
                assert step["choice_kind"] == "initial-retained-name"
                expected_init = {
                    "mode": mode, "eligible_mothers": eligible,
                    "mother": selected["mother"], "side": side, "dart": selected["dart"],
                    "frame_boundary_edges": selected["frame_boundary_edges"],
                    "domain_before": [2, 3, 4], "symbol": 2,
                    "historical_frame_pair": [1, 2],
                    "coarse_split_pair_unordered": [2, 3] if eligible else None,
                    "birth_pair_is_not_a_final_profile_constraint": True,
                    "outside_dart": first, "outside_side": geometry["outerFace"],
                    "prebound_final_inner_anchor": False,
                }
                assert result["initialization"] == expected_init
                audit_boundary(model, previous, side, step["boundary"])
            else:
                assert step["choice_kind"] == "greedy-not-a-proved-safe-extension"
                audit_choice(model, units, result["levels"], previous, adjacent, step)
            assert step["symbol"] == min(previous[step["side"]])
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
            "method": "independent-stage-initialization-level-order-boundaries-and-set-proof-replay",
            "final_legality": legality, **stats}

"""Independent proof replay for optional-level / unranked-peer scheduling.

Unknown depth remains None; a scheduling group is not a mathematical equality.
This checker reconstructs stage order, current boundary bans and every filter
phase independently. Frozen v1 checker and algorithms remain unchanged.
"""

from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.closed_support import supported_cycle_units
from fourcolor.global_restart import current_segments
from fourcolor.level_sides_peer import POLICY
from fourcolor.whole_lines import build_whole_lines
from scripts.analyze_line_generations import derive_generations, extract_whole_contacts
from scripts.validate_frontier_restart import complete_subsets, independent_geometry, json_value, verify_result
from scripts.validate_relation_frontier import replay_propagation

def audit_choice(model, units, levels, domains, adjacent, step):
    """Reconstruct stage, local urgency and provenance without producer selectors."""
    available = []
    for line in model.lines:
        if line["id"] == "frame":
            continue
        if any(len(domains[s[face]]) > 1 for s in line["spans"]
               for face in ("left_side", "right_side")):
            points = tuple(sorted((p[1], p[0]) for p in line["endpoints"]))
            level = levels[line["id"]]["level"]
            available.append((level is None, level if level is not None else 0, points, line["id"]))
    mother = min(available)[3]
    assert step["selection_group"] == ("unranked-peer" if levels[mother]["level"] is None else "rooted")
    assert step["mother"] == mother and step["level"] == levels[mother]["level"]
    assert step["parents"] == levels[mother]["parents"]
    supports = supported_cycle_units(model, domains, units)
    rows = []
    for unit in units:
        if unit["mother"] != mother:
            continue
        unknown = [(s, d) for s, d in unit["occurrences"] if len(domains[s]) > 1]
        if not unknown:
            continue
        def score(side):
            """Independent arithmetic for the retained local urgency convention."""
            return 4 - len(domains[side]), sum(len(domains[n]) > 1 for n in adjacent[side])
        side, dart = max(unknown, key=lambda item: score(item[0]))
        priority = score(side) + (sum(4 - len(domains[s]) for s, _ in unknown),
                                   int(supports[unit["id"]]["supported"]))
        rows.append((priority, unit["t0"], dart, side, unit["id"]))
    highest = max(r[0] for r in rows)
    best = min((r for r in rows if r[0] == highest), key=lambda r: (r[1], r[2]))
    assert (step["dart"], step["side"], step["unit"]) == (best[2], best[3], best[4])
    assert tuple(step["priority"]) == highest
    side = step["side"]
    assert step["domain"] == sorted(domains[side]) and step["symbol"] == min(domains[side])
    span_by_edge = {s["edge"]: (line["id"], [s["t0"], s["t1"]])
                    for line in model.lines for s in line["spans"]}
    expected = {}
    for edge in model.edge_owner:
        a, b = model.plane_map.shores(edge)
        if a == b or side not in (a, b):
            continue
        neighbor = b if side == a else a
        name, interval = span_by_edge[edge]
        expected[edge] = {"edge": edge, "mother": name, "interval": interval,
                          "neighbor": neighbor, "neighbor_domain": sorted(domains[neighbor])}
    boundary = step["boundary"]
    assert len(boundary["sources"]) == len(expected)
    assert {s["edge"]: s for s in boundary["sources"]} == expected
    forbidden = {s["neighbor_domain"][0] for s in expected.values() if len(s["neighbor_domain"]) == 1}
    local = set(range(1, 5)) - forbidden
    assert boundary["direct_forbidden"] == sorted(forbidden)
    assert boundary["local_candidates"] == sorted(local)
    assert set(domains[side]) <= local
    assert boundary["derived_exclusions"] == sorted(local - set(domains[side]))
    assert boundary["one_allowed"] is (1 in domains[side])


def verify_run(geometry, result):
    """Replay every name and filter event, independently checking final legality."""
    plane, adjacent = independent_geometry(geometry)
    model = build_whole_lines(geometry)
    contacts, _ = extract_whole_contacts(model)
    independent = derive_generations(contacts)
    assert result["policy"] == POLICY and result["backtracks"] == 0
    assert result["old_colors_read"] is False
    assert set(result["levels"]) == set(independent)
    for name, item in independent.items():
        expected = None if item["depth"] is None else item["depth"] + 1
        assert result["levels"][name]["level"] == expected
        assert result["levels"][name]["parents"] == item["parents"]
        assert result["levels"][name]["endpoint_contacts"] == contacts[name]
    assert result["status"] in ("solved", "conflict")
    assert result["unranked_mothers"] == sorted(n for n, r in independent.items() if r["depth"] is None)
    assert result["local_budget"] is None
    units = current_segments(model)
    initial = {int(k): v for k, v in result["initial_anchors_by_dart"].items()}
    assert len(initial) == 2
    frame = next(line for line in model.lines if line["id"] == "frame")
    first = frame["spans"][0]["dart"]
    assert initial == {first: [1], first ^ 1: [2]}
    assert plane.face_of_dart[first] == geometry["outerFace"]
    anchors, stats = dict(initial), Counter()
    calls = result["propagation_phases"]
    assert len(calls) == len(result["trace"]) + 1 == result["choices"] + 1
    previous = None
    for index, call in enumerate(calls):
        if index:
            step = result["trace"][index - 1]
            assert plane.face_of_dart[step["dart"]] == step["side"]
            audit_choice(model, units, result["levels"], previous, adjacent, step)
            anchors[step["dart"]] = [step["symbol"]]
        assert json_value(call["anchors_by_dart"]) == json_value(anchors)
        previous, counts = replay_propagation(plane, adjacent, anchors, call["outcome"], complete_subsets(adjacent))
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
        assert result["status"] == "conflict" and result["colors"] is None
    return {"passed": True, "claim": "complete-proper-four-names" if legality else
            "this-greedy-commitment-set-has-no-extension-not-map-impossibility",
            "method": "independent-optional-level-peer-selection-boundaries-and-set-proof-replay",
            "final_legality": legality, **stats}



def mathematical_projection(result):
    """Remove only descriptive v2 metadata for exact rooted v1 comparisons."""
    projected = {k: v for k, v in json_value(result).items() if k not in ("policy", "scope")}
    projected["trace"] = [{k: v for k, v in step.items() if k != "selection_group"}
                          for step in projected["trace"]]
    return projected

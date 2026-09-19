"""Run one frozen level/current-side candidate on the six known regressions.

Old successful colors are diagnostics only. No old result enters the candidate.
Success is independently checked on all boundaries; failures retain and replay
the full necessary-condition certificate. This is not an unseen/full-corpus test.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.closed_support import supported_cycle_units
from fourcolor.frontier_restart import restart_frontier_names
from fourcolor.global_restart import current_segments
from fourcolor.level_sides import POLICY, restart_level_side_names
from fourcolor.relation_frontier import POLICY as BASELINE, restart_relation_frontier_names
from fourcolor.whole_lines import build_whole_lines
from scripts.analyze_line_generations import derive_generations, extract_whole_contacts
from scripts.validate_frontier_restart import (
    complete_subsets, file_sha, independent_geometry, json_value, read_json, verify_result,
)
from scripts.validate_global_restart import compact_result, digest, export_geometries, write_report
from scripts.validate_relation_frontier import independent_check, replay_propagation
from scripts.validate_relation_frontier_full import exact_run, require, source_hashes, validate_inventory

SOURCE = ROOT / "outputs/relation-frontier-full-2026-09-19.json.gz"
EXTRA_SOURCES = ("fourcolor/level_sides.py", "scripts/validate_level_sides.py",
                 "scripts/analyze_line_generations.py", "scripts/validate_relation_frontier.py")


def audit_choice(model, units, levels, domains, adjacent, step):
    """Reconstruct stage, local urgency and provenance without producer selectors."""
    available = []
    for line in model.lines:
        if line["id"] == "frame":
            continue
        if any(len(domains[s[face]]) > 1 for s in line["spans"]
               for face in ("left_side", "right_side")):
            points = tuple(sorted((p[1], p[0]) for p in line["endpoints"]))
            available.append((levels[line["id"]]["level"], points, line["id"]))
    mother = min(available)[2]
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
    if result["status"] == "outside_scope":
        assert result["unranked_mothers"] == sorted(n for n, r in independent.items() if r["depth"] is None)
        assert result["unranked_mothers"] and result["colors"] is None
        return {"passed": True, "claim": "unrooted-support-not-a-coloring-conflict"}
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
            "method": "independent-levels-stage-selection-boundaries-and-set-proof-replay",
            "final_legality": legality, **stats}


def build_report(source_path, manifest_path):
    """Freeze six known inputs and one policy before observing candidate outcomes."""
    source = read_json(source_path)
    rows = sorted((r for r in validate_inventory(source) if r["runs"][BASELINE]["status"] == "conflict"),
                  key=lambda r: (r["face_count"], r["key"]))
    require(len(rows) == 6, "expected the same six complete-library failures")
    hashes = source_hashes()
    require(hashes == source["source_sha256"] == source["source_sha256_end"], "frozen baseline changed")
    hashes.update({p: file_sha(ROOT / p) for p in EXTRA_SOURCES})
    manifest = {"source": {"filename": source_path.name, "sha256": file_sha(source_path)},
                "source_sha256": hashes, "selected_keys": [r["key"] for r in rows],
                "policy": POLICY, "selection": "all six known current-policy failures; faces/key sorted",
                "order": "frame anchors only; internal mothers ascending level then numerical endpoints(y,x); retained local urgency within a mother; min domain",
                "failed_run_retry": False, "full_corpus_run": False}
    write_report(manifest_path, manifest)
    records = []
    for saved, exported in zip(rows, export_geometries(rows)):
        require(exported["key"] == saved["key"] and exported["status"] == "geometry_ok", "export mismatch")
        geometry = exported["geometry"]
        require(digest(geometry) == saved["geometry_sha256"], "geometry drift")
        # Execute the new candidate BEFORE computing any old coloring witness.
        candidate = restart_level_side_names(geometry)
        check = verify_run(geometry, candidate)
        current = restart_relation_frontier_names(geometry)
        old = restart_frontier_names(geometry, "tight-hall")
        for result in (current, old):
            exact_run(compact_result(result), saved["runs"][result["policy"]])
        require(digest(current["propagation_phases"]) == saved["runs"][BASELINE]["propagation_phases_sha256"],
                "baseline propagation drift")
        baseline_check, old_check = independent_check(geometry, current), verify_result(geometry, old)
        require(baseline_check["passed"] and old_check["passed"], "old evidence invalid")
        # The older full solution is diagnostic only; never feed it to selection.
        last = candidate["trace"][-1] if candidate["trace"] else None
        diagnostic = {"last_choice": last,
                      "old_witness_agrees_with_earlier_choices": all(old["colors"][s["side"]] == s["symbol"]
                                                                     for s in candidate["trace"][:-1]),
                      "old_witness_last_side_name": old["colors"][last["side"]] if last else None}
        records.append({"key": saved["key"], "aliases": saved["aliases"], "face_count": saved["face_count"],
                        "document": saved["document"], "geometry": geometry, "geometry_sha256": digest(geometry),
                        "candidate": candidate, "candidate_check": check,
                        "baseline": compact_result(current), "baseline_check": baseline_check,
                        "old_success": compact_result(old), "old_success_check": old_check,
                        "diagnostic": diagnostic})
        print(json_value({"checked": len(records), "total": 6, "status": candidate["status"],
                          "choices": candidate["choices"], "key": saved["key"]}), flush=True)
    require(len(records) == len(rows), "incomplete six-map export")
    ending = source_hashes()
    ending.update({p: file_sha(ROOT / p) for p in EXTRA_SOURCES})
    require(ending == hashes and file_sha(source_path) == manifest["source"]["sha256"], "source changed")
    steps = [s for r in records for s in r["candidate"]["trace"]]
    summary = {"drawings": len(records), "statuses": dict(Counter(r["candidate"]["status"] for r in records)),
               "choices": len(steps), "active_one_choices": sum(s["symbol"] == 1 for s in steps),
               "direct_one_bans": sum(1 in s["boundary"]["direct_forbidden"] for s in steps),
               "derived_one_bans": sum(1 in s["boundary"]["derived_exclusions"] for s in steps),
               "checked_candidate_runs": sum(r["candidate_check"]["passed"] for r in records)}
    return {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            **manifest, "source_sha256_end": ending, "summary": summary, "records": records,
            "limits": ["Known-case developmental test; not a general or unseen success rate.",
                       "Existing filters already use actual adjacency, not permanent ancestral bans.",
                       "Whole-mother current-profile completion can name deep subdivisions early.",
                       "No policy substitution, new start line, recoloring rescue or backtracking on failure."]}


def main():
    """Use fresh portable outputs and retain old research evidence unchanged."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    outputs = (args.manifest, args.output, args.summary)
    if sys.flags.optimize or any(p.exists() for p in outputs) or len({p.resolve() for p in outputs}) != 3:
        parser.error("disable -O and select three distinct new output paths")
    report = build_report(args.source, args.manifest)
    write_report(args.output, report)
    small = {k: v for k, v in report.items() if k != "records"}
    small["report_sha256"] = file_sha(args.output)
    small["cases"] = [{"key": r["key"], "aliases": r["aliases"], "face_count": r["face_count"],
                       "status": r["candidate"]["status"], "choices": r["candidate"]["choices"]}
                      for r in report["records"]]
    write_report(args.summary, small)
    print(json_value({"complete": True, "summary": report["summary"], "sha256": small["report_sha256"]}))


if __name__ == "__main__":
    main()

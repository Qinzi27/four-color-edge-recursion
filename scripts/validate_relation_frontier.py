"""Audit the pair-filter restart on a predeclared diagnostic subset only.

No assignment search, alternate run, recoloring rescue, or new loop grouping is
used. Every deletion is independently replayed with Python sets, beginning at
the actual irreversible commitments. The selected failures are known cases,
not an unseen holdout and not an estimate for all plane maps.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.frontier_restart import restart_frontier_names
from fourcolor.relation_frontier import POLICY, restart_relation_frontier_names
from scripts.validate_frontier_restart import (
    EXISTING, HELDOUT, anchored_domains, complete_subsets, file_sha,
    independent_geometry, json_value, paired_counts, read_json, verify_result,
)
from scripts.validate_global_restart import compact_result, digest, export_geometries, write_report

BASELINE = "tight-hall"
SOURCE = ROOT / "outputs/frontier-restart-all-2026-09-19.json.gz"
EXAMPLES = (("guillotine-20261027", 6), ("heldout-guillotine-20261937", 6),
            ("guillotine-20261209", 9))


def decode(mask):
    """Interpret bits as positive-name pairs without the production decoder."""
    assert type(mask) is int and 0 <= mask < 65536
    return {(p // 4 + 1, p % 4 + 1) for p in range(16) if mask & (1 << p)}


def decoded_matrix(matrix, size):
    """Reject malformed certificates before replaying their relations."""
    assert len(matrix) == size and all(len(row) == size for row in matrix)
    return [[decode(mask) for mask in row] for row in matrix]


def check_hall_fixed_point(domains, adjacent, subsets):
    """Check all genuine size-2..4 clique implications, not drawn cycles."""
    assert all(domains)
    for a, neighbors in enumerate(adjacent):
        if len(domains[a]) == 1:
            assert all(not domains[a] & domains[b] for b in neighbors)
    for subset, common in subsets:
        union = set().union(*(domains[v] for v in subset))
        assert len(union) >= len(subset)
        # Production reserves subsets inside triangles/quads only.
        if len(union) == len(subset) and len(subset) < 4:
            assert all(not domains[v] & union for v in common)


def replay_hall(plane, adjacent, domains, phase, subsets):
    """Certify every Hall/unary change from this phase's independently known input."""
    work = [set(d) for d in domains]
    deficiency = None
    events = 0
    for event in phase["hall_trace"]:
        rule = event.get("rule", "singleton")
        assert deficiency is None and all(work), "events after an established conflict"
        if rule == "singleton":
            a, b = event["from_side"], event["to_side"]
            assert b in adjacent[a] and len(work[a]) == 1
            removed = ({event["removed"]} if isinstance(event["removed"], int)
                       else set(event["removed"]))
            assert removed == work[b] & work[a] and removed
            if "edge" in event:
                assert set(plane.shores(event["edge"])) == {a, b}
            work[b] -= removed
        elif rule in ("hall-reservation", "hall-deficiency"):
            clique, subset = event["clique"], event["subset"]
            assert len(clique) in (3, 4) and len(set(clique)) == len(clique)
            assert all(b in adjacent[a] for a, b in combinations(clique, 2))
            assert 2 <= len(subset) <= len(clique) and len(set(subset)) == len(subset)
            assert set(subset) <= set(clique)
            union = set().union(*(work[v] for v in subset))
            assert sorted(union) == event["union"]
            assert [sorted(work[v]) for v in subset] == event["subset_domains"]
            if rule == "hall-deficiency":
                assert len(union) < len(subset)
                deficiency = event
            else:
                other = event["to_side"]
                assert other in set(clique) - set(subset) and len(union) == len(subset)
                removed = work[other] & union
                assert removed and sorted(removed) == event["removed"]
                work[other] -= removed
        else:
            raise AssertionError("unknown Hall certificate rule: " + rule)
        events += 1
    assert [sorted(d) for d in work] == phase["hall_domains"]
    conflict = deficiency is not None or not all(work)
    expected = "conflict" if conflict else "solved" if all(len(d) == 1 for d in work) else "underdetermined"
    assert phase["hall_status"] == expected
    assert phase["hall_conflict"] == deficiency
    if not conflict:
        check_hall_fixed_point(work, adjacent, subsets)
    return work, conflict, events


def allowed_relations(domains, adjacent):
    """Build equality self-pairs, actual-edge inequalities, and unconstrained others."""
    return [[{(a, b) for a in domains[i] for b in domains[j]
              if (a == b if i == j else a != b if j in adjacent[i] else True)}
             for j in range(len(domains))] for i in range(len(domains))]


def check_relational_fixed_point(relations):
    """Every surviving pair must have every intermediate shore's support."""
    n = len(relations)
    rows = [[[{b for x, b in relations[i][j] if x == a} for a in range(1, 5)]
             for j in range(n)] for i in range(n)]
    for i in range(n):
        assert all(a == b for a, b in relations[i][i])
        for j in range(n):
            assert relations[i][j] and relations[j][i] == {(b, a) for a, b in relations[i][j]}
            for a, b in relations[i][j]:
                for k in range(n):
                    assert rows[i][k][a - 1] & rows[j][k][b - 1], (i, j, k, a, b)


def replay_propagation(plane, adjacent, commitments, outcome, subsets):
    """Verify the Hall/relation alternation without trusting narrowed domains."""
    domains = anchored_domains(plane, commitments)
    previous = None
    stats = Counter()
    phases = outcome["phases"]
    assert phases and outcome["backtracks"] == outcome["choices"] == 0
    assert outcome["palette"] == [1, 2, 3, 4]
    for index, phase in enumerate(phases):
        assert anchored_domains(plane, phase["hall_input_anchors"]) == domains
        if index == 0:
            assert json_value(phase["hall_input_anchors"]) == json_value(commitments)
        hall_domains, hall_conflict, events = replay_hall(plane, adjacent, domains, phase, subsets)
        stats["hall_events"] += events
        permitted = allowed_relations(hall_domains, adjacent)
        relations = (permitted if previous is None else
                     [[previous[i][j] & permitted[i][j] for j in range(len(domains))]
                      for i in range(len(domains))])
        assert relations == decoded_matrix(phase["relation_input"], len(domains))
        if hall_conflict:
            assert not phase["relation_trace"]
        for event in phase["relation_trace"]:
            assert all(rel for row in relations for rel in row), "relation events after empty relation"
            i, j, k = event["i"], event["j"], event["via"]
            before, left, right = relations[i][j], relations[i][k], relations[k][j]
            assert decode(event["before"]) == before
            assert decode(event["left"]) == left and decode(event["right"]) == right
            supported = {(a, b) for a, c in left for c2, b in right if c == c2}
            after = before & supported
            assert after != before and decode(event["after"]) == after
            assert decode(event["removed"]) == before - after
            relations[i][j] = after
            relations[j][i] = {(b, a) for a, b in after}
            stats["relation_events"] += 1
            stats["ordered_pair_deletions_replayed"] += len(before - after)
        conflict = hall_conflict or any(not rel for row in relations for rel in row)
        assert phase["relation_conflict"] is conflict
        domains = [{a for a, b in relations[i][i]} for i in range(len(domains))]
        if not conflict:
            check_relational_fixed_point(relations)
        if index + 1 < len(phases):
            assert not conflict and domains != hall_domains
        else:
            assert conflict or domains == hall_domains
        previous = relations
        stats["filter_phases"] += 1
    assert previous == decoded_matrix(outcome["relations"], len(domains))
    assert [sorted(d) for d in domains] == outcome["domains"]
    expected = "conflict" if conflict else "solved" if all(len(d) == 1 for d in domains) else "underdetermined"
    assert outcome["status"] == expected and outcome["hall_conflict"] == phases[-1]["hall_conflict"]
    return domains, stats


def independent_check(geometry, result):
    """Audit every commitment and deletion, then directly verify the final names."""
    plane, adjacent = independent_geometry(geometry)
    subsets = complete_subsets(adjacent)
    assert result["policy"] == POLICY and result["backtracks"] == 0
    assert result["old_colors_read"] is False and result["local_budget"] is None
    initial = {int(k): v for k, v in result["initial_anchors_by_dart"].items()}
    assert len(initial) == 2
    first = next(d for d, values in initial.items() if values == [1])
    assert initial[first ^ 1] == [2] and geometry["edges"][first // 2]["frame"]
    assert plane.face_of_dart[first] == geometry["outerFace"]
    anchors = dict(initial)
    propagations = result["propagation_phases"]
    assert len(propagations) == len(result["trace"]) + 1 == result["choices"] + 1
    stats = Counter()
    previous = None
    for index, record in enumerate(propagations):
        if index:
            step = result["trace"][index - 1]
            side, dart, symbol = step["side"], step["dart"], step["symbol"]
            assert plane.face_of_dart[dart] == side and len(previous[side]) > 1
            assert sorted(previous[side]) == step["domain"]
            used = {next(iter(d)) for d in previous if len(d) == 1}
            assert sorted(used) == step["used_names"]
            assert symbol == min(previous[side], key=lambda c: (c not in used, c))
            assert step["choice_kind"] == "greedy-not-a-proved-safe-extension"
            anchors[dart] = [symbol]
        assert json_value(record["anchors_by_dart"]) == json_value(anchors)
        previous, counts = replay_propagation(plane, adjacent, anchors, record["outcome"], subsets)
        stats.update(counts)
        if index + 1 < len(propagations):
            assert record["outcome"]["status"] == "underdetermined"
    last = propagations[-1]["outcome"]
    for field in ("status", "domains", "relations", "hall_conflict"):
        assert result[field] == last[field]
    assert json_value(anchors) == json_value(result["anchors_by_dart"])
    if result["status"] == "solved":
        assert verify_result(geometry, result, (plane, adjacent))["passed"]
    else:
        assert result["status"] == "conflict" and result["colors"] is None
    return {"passed": True, "method": "independent-set-Hall-and-composition-proof-replay",
            "claim": "complete-proper-four-names" if result["status"] == "solved" else
                     "current-greedy-commitments-have-no-extension-not-map-impossibility",
            "propagations": len(propagations), **stats}


def declared_selection(previous):
    """Fix known-case groups before executing any candidate result."""
    old = [r for r in previous["drawings"] if EXISTING in r["cohorts"]]
    assert len(old) == 6113
    regressions = sorted(r["key"] for r in old if r["runs"]["closed-support"]["status"] == "solved"
                         and r["runs"][BASELINE]["status"] != "solved")
    controls = sorted(r["key"] for r in old if r["runs"][BASELINE]["status"] == "solved")[:135]
    new_failures = sorted(r["key"] for r in previous["drawings"] if HELDOUT in r["cohorts"]
                          and r["runs"][BASELINE]["status"] != "solved")
    assert len(regressions) == len(controls) == 135 and len(new_failures) == 36
    named = {}
    for history, step in EXAMPLES:
        matched = [r["key"] for r in previous["drawings"] if any(
            a.get("history") == history and a.get("step") == step for a in r["aliases"])]
        assert len(matched) == 1, (history, step, matched)
        named[f"{history}/step-{step}"] = matched[0]
    groups = {"old-closed-success-hall-regressions": regressions,
              "old-hall-success-key-sorted-controls": controls,
              "previous-new-seeds-hall-failures-now-diagnostic": new_failures,
              "named-manual-diagnostics": sorted(set(named.values()))}
    all_keys = sorted(set().union(*map(set, groups.values())))
    by_key = {r["key"]: r for r in previous["drawings"]}
    return [by_key[key] for key in all_keys], groups, named


def build_report(source=SOURCE, limit=None):
    """Run fixed selection and retain new evidence without editing old reports."""
    input_sha = file_sha(source)
    previous = read_json(source)
    selected, groups, named = declared_selection(previous)
    selection_keys = [r["key"] for r in selected]
    files = ("fourcolor/relation_frontier.py", "fourcolor/relation_names.py",
             "fourcolor/frontier_restart.py", "fourcolor/global_restart.py",
             "fourcolor/closed_support.py", "fourcolor/whole_lines.py",
             "fourcolor/joint_lines.py", "fourcolor/weighted_lines.py",
             "fourcolor/embedding.py", "fourcolor/line_names.py", "web/engine.js",
             "scripts/restart-geometry.mjs", "scripts/validate_relation_frontier.py",
             "scripts/validate_frontier_restart.py", "scripts/validate_global_restart.py")
    hashes = {path: file_sha(ROOT / path) for path in files}
    if limit is not None:
        selected = selected[:limit]
    records, detailed = [], {}
    least_failure = None
    for start in range(0, len(selected), 30):
        chunk = selected[start:start + 30]
        for saved, exported in zip(chunk, export_geometries(chunk)):
            assert exported["key"] == saved["key"] and exported["status"] == "geometry_ok"
            geometry = exported["geometry"]
            assert digest(geometry) == saved["geometry_sha256"]
            began = perf_counter()
            old = restart_frontier_names(geometry, BASELINE)
            old_elapsed = perf_counter() - began
            old_verification = verify_result(geometry, old)
            assert old_verification["passed"]
            compact_old = json_value(compact_result(old))
            for field in ("status", "domains", "anchors_by_dart", "colors", "trace_sha256"):
                assert compact_old[field] == saved["runs"][BASELINE][field]
            began = perf_counter()
            result = restart_relation_frontier_names(geometry)
            elapsed = perf_counter() - began
            began = perf_counter()
            verification = independent_check(geometry, result)
            audit_elapsed = perf_counter() - began
            new = compact_result(result)
            new.update({"verification": verification, "runtime_seconds": elapsed,
                        "audit_seconds": audit_elapsed,
                        "propagation_phases_sha256": digest(result["propagation_phases"])})
            compact_old.update({"verification": old_verification, "runtime_seconds": old_elapsed})
            record = {field: saved[field] for field in ("key", "document", "aliases", "cohorts", "geometry_sha256", "face_count")}
            record.update({"diagnostic_groups": [g for g, keys in groups.items() if saved["key"] in keys],
                           "runs": {BASELINE: compact_old, POLICY: new}})
            records.append(record)
            if saved["key"] in named.values():
                detailed[saved["key"]] = {"geometry": geometry, "baseline": old, "outcome": result}
            if result["status"] != "solved":
                rank = (len(saved["document"]["strokes"]), saved["key"])
                if least_failure is None or rank < least_failure[0]:
                    least_failure = (rank, {"key": saved["key"], "geometry": geometry,
                                           "baseline": old, "outcome": result})
        print({"checked": len(records), "selected": len(selected),
               "solved": sum(r["runs"][POLICY]["status"] == "solved" for r in records)}, flush=True)
    end_hashes = {path: file_sha(ROOT / path) for path in files}
    assert hashes == end_hashes and input_sha == file_sha(source)
    summary = []
    for group in ("combined", *groups):
        rows = [r for r in records if group == "combined" or group in r["diagnostic_groups"]]
        summary.append({"group": group, "drawings": len(rows),
                        "baseline_status": dict(Counter(r["runs"][BASELINE]["status"] for r in rows)),
                        "candidate_status": dict(Counter(r["runs"][POLICY]["status"] for r in rows)),
                        "paired": paired_counts((r["runs"][BASELINE]["status"] == "solved",
                                                 r["runs"][POLICY]["status"] == "solved") for r in rows)})
    totals = Counter()
    for row in records:
        totals.update({k: v for k, v in row["runs"][POLICY]["verification"].items()
                       if type(v) is int})
    return {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "experiment": "Fixed known-case diagnostics for unchanged selection with stronger pair filtering",
            "input": {"filename": source.name, "sha256": input_sha},
            "policy": POLICY, "baseline_policy": BASELINE, "smoke_limit": limit,
            "full_declared_diagnostic_run": limit is None, "unseen_holdout": False,
            "source_sha256": hashes, "source_sha256_end": end_hashes, "source_hashes_unchanged": True,
            "declared_groups": groups, "declared_keys_sha256": digest(selection_keys),
            "declared_distinct_drawings": len(selection_keys), "drawings_checked": len(records),
            "baseline_exact_reproductions": len(records), "independent_checks": 2 * len(records),
            "replay_totals": dict(totals), "named_examples": named, "detailed_examples": detailed,
            "least_failure": least_failure[1] if least_failure else None,
            "summary": summary, "drawings": records,
            "limits": ["Selection uses known outcomes and is diagnostic, not an unseen holdout.",
                       "No inference about all 7069 prior drawings or all plane maps follows.",
                       "Groups overlap and their denominators are not additive.",
                       "Every non-success is a strategy failure; a conflict concerns its chosen commitments.",
                       "Four names are assumed; this is not a proof of the four-color upper bound.",
                       "Pair consistency is necessary, not sufficient for a complete assignment.",
                       "No assignment retries, oracle fallback, old colors, or new cycle grouping.",
                       "Runtime includes one sequential run only and is not a controlled speed benchmark."]}


def main():
    """Require two fresh evidence paths; keep smoke reports visibly separate."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.output.exists() or args.summary.exists() or args.output.resolve() == args.summary.resolve():
        parser.error("choose two distinct fresh output paths")
    if args.limit is not None and args.limit < 1:
        parser.error("smoke limit must be positive")
    report = build_report(args.source, args.limit)
    write_report(args.output, report)
    small = {key: value for key, value in report.items()
             if key not in ("drawings", "detailed_examples", "least_failure", "declared_groups")}
    small["output"] = {"filename": args.output.name, "sha256": file_sha(args.output)}
    small["least_failure_key"] = report["least_failure"]["key"] if report["least_failure"] else None
    write_report(args.summary, small)
    print(report["summary"], flush=True)


if __name__ == "__main__":
    main()

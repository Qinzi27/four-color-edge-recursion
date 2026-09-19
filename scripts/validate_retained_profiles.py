"""Recheck retained-side naming and the verified two-anchor strip extension.

Every complete history uses a declared deterministic policy. No production
coloring search or hidden fallback is used. The geometric line-name oracle is
independent of the rectangular naming model and checks every proposed state.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import random
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.inherited_names import initial_state, line_profiles, state_payload
from fourcolor.line_names import audit_line_names
from fourcolor.retained_profiles import attempt_profile_cut


def node_json(script, value=None):
    """Call a geometry-only Node helper and retain nonzero-exit diagnostics."""
    result = subprocess.run(["node", str(ROOT / "scripts" / script)], cwd=ROOT,
                            input=None if value is None else json.dumps(value),
                            text=True, encoding="utf-8", capture_output=True, check=True)
    return json.loads(result.stdout)


def strip_fixtures():
    """Forty independently seeded orders/directions on the proved strip family."""
    rows = []
    for seed in range(20260918, 20260958):
        rng = random.Random(seed)
        positions = list(range(30, 720, 30))
        rng.shuffle(positions)
        paths = [[[0, 200], [900, 200]]]
        for x in positions:
            path = [[x, 200], [x, 600]]
            paths.append(path if rng.randrange(2) else path[::-1])
        rows.append({"seed": seed, "cohort": "proved-strip-family", "family": "two-anchor-strip",
                     "paths": paths})
    return rows


def compact_event(event):
    """Keep replay inputs/witnesses, hashing repeated full mother profiles.

    Complete profiles remain in the teaching cases and are independently
    checked before serialization. Batch histories regenerate them exactly;
    duplicating before, after and changed copies would inflate the report.
    """
    repeated = {"line_profiles_before", "line_profiles_after", "profile_changes"}
    result = {key: value for key, value in event.items() if key not in repeated}
    if "line_profiles_after" in event:
        result["profiles_sha256"] = {
            key: sha256(json.dumps(event[key], sort_keys=True).encode()).hexdigest()
            for key in ("line_profiles_before", "line_profiles_after")}
        result["changed_mothers"] = [row["mother"] for row in event["profile_changes"]]
    return result


def main():
    """Save all successes, first blocks and out-of-scope cases without filtering."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("choose a new filename; previous research reports are preserved")
    certificates, results, runs = [], [], []

    def record_state(key, state):
        certificates.append({"key": key, **state_payload(state)})

    # Reconstruct the user's sketch with anchored straight lines. Hand-drawn
    # pen gaps are interpreted as closed/anchored by the accompanying explanation.
    state = initial_state()
    sketch_steps = []
    history = [([[0, 200], [900, 200]], "left"),
               ([[300, 200], [300, 600]], "right"),
               ([[600, 200], [600, 600]], "right")]
    for index, (path, inherit) in enumerate(history):
        outcome = attempt_profile_cut(state, path, inherit=inherit)
        assert outcome["status"] == "split", outcome
        state = outcome["state"]
        sketch_steps.append(outcome["event"])
        record_state(f"sketch/{index + 1}", state)
    bottom = sorted((s for s in state.sides if s.bounds[1] == 200), key=lambda s: s.bounds[0])
    assert [s.symbol for s in bottom] == [3, 4, 3]
    profiles = line_profiles(state)
    assert [span["pair"] for span in profiles["cut-1"]] == [(2, 3), (2, 4), (2, 3)]
    assert profiles["cut-2"][0]["pair"] == (4, 3)
    assert profiles["cut-3"][0]["pair"] == (3, 4)
    witnesses = []
    for inherit in ("left", "right"):
        frozen = attempt_profile_cut(state, [[450, 200], [450, 600]], inherit=inherit)
        synced = attempt_profile_cut(state, [[450, 200], [450, 600]], inherit=inherit, synchronize=True)
        assert frozen["status"] == "blocked_sync_required" and frozen["state"] is state
        assert synced["status"] == "split"
        assert max(side.symbol for side in frozen["proposed_state"].sides) == 5
        assert max(side.symbol for side in synced["state"].sides) == 4
        changed = [side.id for side in state.sides for other in synced["state"].sides
                   if side.id == other.id and side.symbol != other.symbol]
        assert len(changed) == 1
        witnesses.append({"inherit": inherit, "frozen_diagnostic": frozen["event"],
                          "synchronized": synced["event"], "changed_old_sides": changed,
                          "final": state_payload(synced["state"])})
        record_state(f"sketch/needs-sync/{inherit}", frozen["proposed_state"])
        record_state(f"sketch/synchronized/{inherit}", synced["state"])

    # Revisit the preceding three-parallel-line case under COMPLETE boundaries.
    parallel = initial_state()
    parallel_events = []
    for index, path in enumerate(([[300, 0], [300, 600]], [[600, 600], [600, 0]],
                                 [[450, 0], [450, 600]])):
        outcome = attempt_profile_cut(parallel, path)
        assert outcome["status"] == "split"
        parallel = outcome["state"]
        parallel_events.append(outcome["event"])
        record_state(f"parallel-corrected/{index + 1}", parallel)
    assert max(s.symbol for s in parallel.sides) == 4

    fixture_rows = node_json("inherited-fixtures.mjs")["records"] + strip_fixtures()
    for row in fixture_rows:
        for synchronize in (False, True):
            for inherit in ("left", "right"):
                current = initial_state()
                policy = "complete-boundary+verified-strip" if synchronize else "complete-boundary"
                key = f"{row['family']}/{row['seed']}/{policy}/{inherit}"
                events, status = [], "completed"
                for index, path in enumerate(row["paths"]):
                    outcome = attempt_profile_cut(current, path, inherit=inherit, synchronize=synchronize)
                    events.append({"step": index + 1, "status": outcome["status"],
                                   **compact_event(outcome["event"])})
                    if "proposed_state" in outcome:
                        record_state(f"{key}/{index + 1}", outcome["proposed_state"])
                    if outcome["status"] != "split":
                        assert outcome["state"] is current
                        status = outcome["status"]
                        break
                    current = outcome["state"]
                runs.append({"seed": row["seed"], "cohort": row["cohort"], "family": row["family"],
                             "policy": policy, "inherit": inherit, "status": status,
                             "planned_steps": len(row["paths"]), "committed_steps": len(current.cuts),
                             "events": events, "last_valid_state": state_payload(current)})

    # Batch to bound memory and process output; each batch is audited fully.
    for start in range(0, len(certificates), 128):
        batch = certificates[start:start + 128]
        output = node_json("inherited-oracle.mjs", batch)
        assert [r["key"] for r in output] == [r["key"] for r in batch]
        for record in output:
            assert not record["errors"], record
            audit = audit_line_names(record["rotation"], record["names"])
            assert audit.status == "consistent" and not record["edge_conflicts"], record["key"]
            assert len(audit.side_orbits) == record["face_count"]
            # Full certificates can be regenerated from histories; include a
            # deterministic checksum without duplicating thousands of edge lists.
            results.append({"key": record["key"], "status": audit.status,
                            "faces": record["face_count"], "edges": len(record["names"]),
                            "certificate_sha256": sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()})
    groups = []
    for cohort in ("baseline", "fresh-seeds", "proved-strip-family"):
        for policy in ("complete-boundary", "complete-boundary+verified-strip"):
            selected = [r for r in runs if r["cohort"] == cohort and r["policy"] == policy]
            groups.append({"cohort": cohort, "policy": policy, "runs": len(selected),
                           "outcomes": dict(Counter(r["status"] for r in selected)),
                           "committed_splits": sum(r["committed_steps"] for r in selected),
                           "synchronizations": sum(e.get("method") == "verified_strip_sync"
                                                   for r in selected for e in r["events"])})
    sources = ["fourcolor/inherited_names.py", "fourcolor/retained_profiles.py", "fourcolor/strip_chain.py",
               "fourcolor/line_names.py", "web/engine.js", "scripts/inherited-oracle.mjs",
               "scripts/inherited-fixtures.mjs", "scripts/construction-experiments.mjs",
               "scripts/validate_retained_profiles.py"]
    report = {"schema_version": 2, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Rectangular cuts, complete inherited boundary constraints, exact two-anchor strip synchronization only.",
              "limits": ["Proposal formalizes the supplied examples, not a fully specified universal user algorithm.",
                         "A proposed fifth name diagnoses frozen old names; it is not necessary for the map.",
                         "No hidden enumeration, backtracking, BFS, or global four-color oracle supplies production names.",
                         "Outside-scope geometry is not a naming failure; orientation policies run independently."],
              "storage": "Teaching witnesses retain full profiles; batch events retain replay data, changed mother IDs and profile hashes.",
              "seed_ranges": {"guillotine_baseline": [20260908, 20261067],
                              "guillotine_fresh": [20261201, 20261220], "strip": [20260918, 20260957]},
              "sketch": {"events": sketch_steps, "state": state_payload(state), "profiles": profiles,
                         "unordered_vertical_types": [[3, 4], [3, 4]], "middle_split": witnesses},
              "previous_example_corrected": {"events": parallel_events, "state": state_payload(parallel)},
              "summary": {"geometries": len(fixture_rows), "runs": len(runs), "groups": groups,
                          "independent_certificates": len(results), "all_certificates_consistent": True},
              "runs": runs, "oracle_checks": results,
              "source_sha256": {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in sources}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

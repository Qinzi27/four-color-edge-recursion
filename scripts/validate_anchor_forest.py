"""Continue whole histories with the explicit dual-anchor forest policy.

The previous immutable report is the matched control. Its 85 independently
certified first-block repairs are checkpoints, never inputs for naming choices.
Every proposed geometry is audited independently, including uncommitted fifth
name diagnostics. Full completion and number of local repairs stay separate.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.anchor_forest import attempt_forest_cut
from fourcolor.inherited_names import initial_state, state_payload
from fourcolor.line_names import audit_line_names
from scripts.audit_retained_blocks import rectangle_adjacency, dual_anchor_paths
from scripts.validate_retained_profiles import compact_event, node_json, strip_fixtures

BASE_POLICY = "complete-boundary+verified-strip"
NEW_POLICY = "complete-boundary+verified-strip+anchor-forest"
SOURCE_FILES = ["fourcolor/anchor_forest.py", "fourcolor/retained_profiles.py",
                "fourcolor/inherited_names.py", "fourcolor/strip_chain.py", "fourcolor/line_names.py",
                "scripts/audit_retained_blocks.py", "scripts/validate_retained_profiles.py",
                "scripts/validate_anchor_forest.py", "scripts/inherited-fixtures.mjs",
                "scripts/inherited-oracle.mjs", "scripts/construction-experiments.mjs", "web/engine.js"]


def source_hashes():
    """Check source stability across a run, including imported fixture helpers."""
    return {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def json_value(value):
    """Normalize immutable tuples to the portable report's JSON representation."""
    return json.loads(json.dumps(value))


def key(row):
    """Names refer to histories, not distinct final geometric maps."""
    return row["family"], row["seed"], row["inherit"]


def diagnose_stop(state, parent):
    """Read-only complete-adjacency classification, independent of selection."""
    adjacency = rectangle_adjacency(state)
    vertices = set(adjacency)
    missing_outside = sorted(vertices - {"outside"} - adjacency["outside"])
    anchor_checks, missing_by_anchor = [], []
    for side in state.sides:
        if side.id == parent or side.id in (parent + ".l", parent + ".r"):
            continue
        missing = sorted(vertices - {side.id} - adjacency[side.id])
        missing_by_anchor.append({"anchor": side.id, "symbol": side.symbol,
                                  "bounds": side.bounds, "missing_neighbors": missing})
        if not missing:
            paths = dual_anchor_paths(adjacency, side.id)
            anchor_checks.append({"anchor": side.id, "symbol": side.symbol,
                                  "linear_forest": paths is not None, "paths": paths})
    if missing_outside:
        reason = "outside_not_adjacent_to_every_side"
    elif not anchor_checks:
        reason = "no_uncut_second_common_anchor"
    elif not all(row["linear_forest"] for row in anchor_checks):
        # In a verified simple plane graph two adjacent universal anchors force
        # a linear forest. A counterexample here means a broken model/checker,
        # not just another ordinary class of unsupported input.
        raise AssertionError("planar common anchors have a non-forest residual")
    else:
        reason = "multiple_or_unhandled_anchors"
    return {"reason": reason, "missing_outside_neighbors": missing_outside,
            "missing_outside_bounds": [s.bounds for s in state.sides if s.id in missing_outside],
            "common_anchor_checks": anchor_checks, "missing_by_uncut_anchor": missing_by_anchor,
            "adjacency": {vertex: sorted(neighbors) for vertex, neighbors in sorted(adjacency.items())}}


def main():
    """Replay all declared histories once, without retrying names or directions."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=ROOT / "outputs/retained-profiles-2026-09-18-v2.json")
    parser.add_argument("--checkpoints", type=Path, default=ROOT / "outputs/retained-blocks-2026-09-18.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite evidence; choose a new report filename")
    initial_hashes = source_hashes()
    baseline_bytes, checkpoint_bytes = args.baseline.read_bytes(), args.checkpoints.read_bytes()
    baseline, checkpoints = json.loads(baseline_bytes), json.loads(checkpoint_bytes)
    assert baseline["schema_version"] == 2 and checkpoints["schema_version"] == 1
    assert checkpoints["input"]["sha256"] == sha256(baseline_bytes).hexdigest()
    for report in (baseline, checkpoints):
        for filename, digest in report["source_sha256"].items():
            assert sha256((ROOT / filename).read_bytes()).hexdigest() == digest, filename
    controls = {key(row): row for row in baseline["runs"] if row["policy"] == BASE_POLICY}
    certified = {(row["family"], row["seed"], row["requested_inherit"]): row
                 for row in checkpoints["records"] if row["certificate"] is not None}
    assert len(certified) == 85, "this experiment must retain all 85 saved checkpoints"
    fixtures = node_json("inherited-fixtures.mjs")["records"] + strip_fixtures()
    assert len(controls) == 2 * len(fixtures) == 440
    runs, certificates, checkpoints_checked = [], [], []
    prefix_steps = 0
    for fixture in fixtures:
        for inherit in ("left", "right"):
            run_key = fixture["family"], fixture["seed"], inherit
            control = controls[run_key]
            state, events, status = initial_state(), [], "completed"
            stem = "/".join(map(str, run_key))
            last_proposal, last_diagnosis = None, None
            for index, path in enumerate(fixture["paths"]):
                if index == control["committed_steps"]:
                    assert json_value(state_payload(state)) == control["last_valid_state"], stem
                outcome = attempt_forest_cut(state, path, inherit=inherit)
                event = {"step": index + 1, "status": outcome["status"], **compact_event(outcome["event"])}
                events.append(event)
                if index < control["committed_steps"]:
                    assert outcome["status"] == "split"
                    # The expanded rule must leave every successful old-policy
                    # prefix unchanged, including every ordered mother profile.
                    old = control["events"][index]
                    for field in ("cut", "parent", "s", "R", "t", "method", "new_line_pair", "profiles_sha256"):
                        assert json_value(event[field]) == old[field], (stem, index, field)
                    prefix_steps += 1
                if "proposed_state" in outcome:
                    proposed = outcome["proposed_state"]
                    certificates.append({"key": f"{stem}/{index + 1}",
                                         "committed": outcome["status"] == "split", **state_payload(proposed)})
                    if outcome["status"] != "split":
                        last_proposal = state_payload(proposed)
                        last_diagnosis = diagnose_stop(proposed, event["parent"])
                if "diagnostic_proposed_state" in outcome:
                    # Successful synchronization retains a separate frozen-mex
                    # proposal. Audit this too; it is not a committed result.
                    certificates.append({"key": f"{stem}/{index + 1}/before-sync-diagnostic",
                                         "committed": False,
                                         **state_payload(outcome["diagnostic_proposed_state"])})
                if run_key in certified and index == control["committed_steps"]:
                    assert outcome["status"] == "split", stem
                    assert outcome["event"]["method"] == "verified_anchor_forest_sync"
                    expected = certified[run_key]["certificate"]["state"]
                    assert json_value(state_payload(outcome["state"])) == expected, stem
                    checkpoints_checked.append(stem)
                if outcome["status"] != "split":
                    assert outcome["state"] is state
                    status = outcome["status"]
                    break
                state = outcome["state"]
            if control["status"] == "completed":
                assert status == "completed" and json_value(state_payload(state)) == control["last_valid_state"]
            assert len(state.cuts) >= control["committed_steps"]
            runs.append({"family": fixture["family"], "cohort": fixture["cohort"], "seed": fixture["seed"],
                         "inherit": inherit, "policy": NEW_POLICY, "planned_steps": len(fixture["paths"]),
                         "committed_steps": len(state.cuts), "status": status,
                         "baseline_status": control["status"], "baseline_committed_steps": control["committed_steps"],
                         "extra_committed_steps": len(state.cuts) - control["committed_steps"],
                         "previously_certified_first_block": run_key in certified,
                         "events": events, "last_valid_state": state_payload(state),
                         "last_proposed_state": last_proposal, "stop_diagnosis": last_diagnosis})
    assert len(checkpoints_checked) == len(set(checkpoints_checked)) == 85
    checks = []
    for start in range(0, len(certificates), 128):
        batch = certificates[start:start + 128]
        rows = node_json("inherited-oracle.mjs", batch)
        assert [r["key"] for r in rows] == [r["key"] for r in batch]
        for source, row in zip(batch, rows):
            assert not row["errors"] and not row["edge_conflicts"], row
            audit = audit_line_names(row["rotation"], row["names"])
            assert audit.status == "consistent"
            assert len(audit.side_orbits) == row["face_count"] == len(source["sides"]) + 1
            if source["committed"]:
                assert all(1 <= int(name) <= 4 for pair in row["names"] for name in pair)
            checks.append({"key": row["key"], "status": audit.status, "committed_four_names": source["committed"],
                           "face_count": row["face_count"], "edge_count": len(row["names"]),
                           "certificate_sha256": sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()})
    groups = []
    for cohort in ("baseline", "fresh-seeds", "proved-strip-family"):
        selected = [r for r in runs if r["cohort"] == cohort]
        groups.append({"cohort": cohort, "runs": len(selected),
                       "outcomes": dict(Counter(r["status"] for r in selected)),
                       "committed_steps": sum(r["committed_steps"] for r in selected),
                       "baseline_committed_steps": sum(r["baseline_committed_steps"] for r in selected),
                       "improved_runs": sum(r["extra_committed_steps"] > 0 for r in selected),
                       "extra_steps": sum(r["extra_committed_steps"] for r in selected),
                       "forest_synchronizations": sum(e["method"] == "verified_anchor_forest_sync"
                                                      for r in selected for e in r["events"])})
    followed = [r for r in runs if r["previously_certified_first_block"]]
    summary = {"history_fixtures": len(fixtures), "new_policy_runs": len(runs), "matched_control_runs": len(controls),
               "matched_successful_prefix_steps": prefix_steps, "groups": groups,
               "old_85_followup": {"checked": len(checkpoints_checked),
                                   "final_outcomes": dict(Counter(r["status"] for r in followed)),
                                   "extra_step_distribution": dict(sorted(Counter(r["extra_committed_steps"] for r in followed).items()))},
               "new_stop_reasons": dict(Counter(r["stop_diagnosis"]["reason"] for r in runs if r["stop_diagnosis"])),
               "independent_certificates": len(checks),
               "committed_four_name_certificates": sum(c["committed_four_names"] for c in checks),
               "uncommitted_diagnostic_certificates": sum(not c["committed_four_names"] for c in checks)}
    assert source_hashes() == initial_hashes, "source changed during experiment; rerun with a new output"
    report = {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Continuous rectangular histories with deterministic direct, strip, then dual-anchor-forest updates.",
              "limits": ["Finite histories, not a general four-color proof.",
                         "The 40 strip histories permute one final geometry; histories are not unique maps.",
                         "Names of non-anchor sides and the actual inherited child may change during canonical restart.",
                         "A rejected fifth-name diagnostic is not a committed fifth color or an impossibility claim.",
                         "No coloring enumeration, backtracking, retry of orientation or general solver supplies names."],
              "baseline": {"filename": args.baseline.name, "sha256": sha256(baseline_bytes).hexdigest()},
              "checkpoints": {"filename": args.checkpoints.name, "sha256": sha256(checkpoint_bytes).hexdigest()},
              "seed_ranges": baseline["seed_ranges"], "source_sha256": initial_hashes,
              "summary": summary, "runs": runs, "oracle_checks": checks}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Reproduce endpoint-only inheritance tests without backtracking or repairs.

Independent certificates use the browser's geometry builder plus the existing
line-rotation auditor, not the old browser construction naming implementation.
The complete-boundary alternatives are diagnostics only, never fallback steps.
"""

from argparse import ArgumentParser
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.inherited_names import (attempt_cut, choose_inherited_name,
                                      initial_state, line_profiles, state_payload)
from fourcolor.line_names import audit_line_names


def node_json(script, payload=None):
    """Run a portable Node geometry helper; propagate any nonzero exit."""
    process = subprocess.run(["node", str(ROOT / "scripts" / script)],
                             input=None if payload is None else json.dumps(payload),
                             capture_output=True, text=True, encoding="utf-8", cwd=ROOT, check=True)
    return json.loads(process.stdout)


def main():
    """Keep every attempted transition, fixed direction and independent audit."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite an existing research report; choose a new output")
    fixtures = node_json("inherited-fixtures.mjs")
    oracle_inputs, expected = [], {}

    def certificate(key, state, status):
        oracle_inputs.append({"key": key, **state_payload(state)})
        expected[key] = status

    # Direct symbolic examples supplied by the user, without geometric assumptions.
    examples = []
    for s, retained, new in ((2, [1], 3), (3, [1, 2], 4), (4, [1, 3], 2)):
        actual = choose_inherited_name(s, retained)
        assert actual == new
        examples.append({"inherited": s, "retained": retained, "new": actual})
    assert choose_inherited_name(4, [1, 2, 3]) == 5

    # A concrete realization of all three user naming transitions.
    illustration = initial_state()
    illustration_events = []
    for i, path in enumerate((((0, 200), (900, 200)), ((300, 200), (300, 600)),
                              ((0, 400), (300, 400)))):
        result = attempt_cut(illustration, path, "left")
        assert result["status"] == "split", result
        illustration = result["state"]
        illustration_events.append(result["event"])
        certificate(f"user-example/{i + 1}", illustration, "consistent")
    assert [e["new_name"] for e in illustration_events] == [3, 4, 2]

    # Counterexample has a reachable proper prefix, not an arbitrary precoloring.
    prefix = initial_state()
    prefix_events = []
    for i, path in enumerate((((300, 0), (300, 600)), ((600, 600), (600, 0)))):
        result = attempt_cut(prefix, path, "left")
        assert result["status"] == "split"
        prefix = result["state"]
        prefix_events.append(result["event"])
        certificate(f"parallel/prefix/{i + 1}", prefix, "consistent")
    counterexample = {"prefix": state_payload(prefix), "prefix_events": prefix_events,
                      "prefix_profiles": line_profiles(prefix), "attempts": []}
    for inherit in ("left", "right"):
        outcome = attempt_cut(prefix, ((450, 0), (450, 600)), inherit)
        assert outcome["status"] == "conflict" and outcome["state"] is prefix
        proposal = outcome["proposed_state"]
        counterexample["attempts"].append({"inherit": inherit, "event": outcome["event"],
                                           "proposed": state_payload(proposal)})
        certificate(f"parallel/failed/{inherit}", proposal, "conflict")
        # This explicitly labelled diagnostic certificate is NOT committed by the rule.
        changed_id = outcome["event"]["parent"] + (".r" if inherit == "left" else ".l")
        diagnostic = replace(proposal, sides=tuple(replace(s, symbol=4) if s.id == changed_id else s
                                                   for s in proposal.sides))
        certificate(f"parallel/diagnostic-four/{inherit}", diagnostic, "consistent")

    runs = []
    for row in fixtures["records"]:
        # Two independent complete attempts, never a best-of-two naming choice.
        for inherit in ("left", "right"):
            state = initial_state()
            events = []
            status = "completed"
            for index, path in enumerate(row["paths"]):
                outcome = attempt_cut(state, path, inherit)
                events.append({"step": index + 1, "status": outcome["status"], **outcome["event"]})
                if "proposed_state" in outcome:
                    certificate(f"seed/{row['seed']}/{inherit}/{index + 1}", outcome["proposed_state"],
                                "consistent" if outcome["status"] == "split" else "conflict")
                if outcome["status"] != "split":
                    status = outcome["status"]
                    break
                state = outcome["state"]
            runs.append({"seed": row["seed"], "cohort": row["cohort"], "family": row["family"],
                         "inherit": inherit, "planned_steps": len(row["paths"]),
                         "committed_steps": len(state.cuts), "status": status, "events": events,
                         "last_valid_state": state_payload(state)})

    oracle = node_json("inherited-oracle.mjs", oracle_inputs)
    assert len(oracle) == len(oracle_inputs)
    seen = set()
    for record in oracle:
        key = record["key"]
        assert key not in seen and key in expected
        seen.add(key)
        assert not record["errors"], record
        audit = audit_line_names(record["rotation"], record["names"])
        assert audit.status == expected[key], (key, audit, expected[key])
        assert bool(record["edge_conflicts"]) == (expected[key] == "conflict")
        record["line_name_audit"] = audit.status
        record["side_orbits"] = len(audit.side_orbits)
        assert len(audit.side_orbits) == record["face_count"]

    by_group = {}
    for cohort in ("baseline", "fresh-seeds"):
        for inherit in ("left", "right"):
            selected = [r for r in runs if r["cohort"] == cohort and r["inherit"] == inherit]
            by_group[f"{cohort}/{inherit}"] = dict(Counter(r["status"] for r in selected))
    sources = ["fourcolor/inherited_names.py", "fourcolor/line_names.py", "web/engine.js",
               "scripts/inherited-fixtures.mjs", "scripts/inherited-oracle.mjs",
               "scripts/construction-experiments.mjs", "scripts/validate_inherited_names.py"]
    report = {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Two local endpoint retained sides, other old names fixed; axis-aligned rectangular histories only.",
              "not_claimed": ["Four-Color Theorem proof", "refutation of unspecified global renaming",
                              "exhaustive planar-map coverage", "optimal ordering or orientation"],
              "rule": "t = min(positive integers minus (endpoint retained names union inherited name))",
              "baseline_seeds": [20260908, 20261067], "fresh_seeds": [20261201, 20261220],
              "local_bound": "At most two endpoint names plus one inherited name implies mex <= 4; it does not imply consistency.",
              "symbolic_examples": examples,
              "geometric_examples": {"events": illustration_events, "state": state_payload(illustration),
                                     "profiles": line_profiles(illustration)},
              "counterexample": counterexample,
              "summary": {"geometries": len(fixtures["records"]), "independent_fixed_direction_runs": len(runs),
                          "outcomes": dict(Counter(r["status"] for r in runs)), "groups": by_group,
                          "oracle_certificates": len(oracle),
                          "maximum_selected_name": max(e["new_name"] for r in runs for e in r["events"]
                                                       if "new_name" in e)},
              "runs": runs, "independent_oracle": oracle,
              "source_sha256": {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in sources}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

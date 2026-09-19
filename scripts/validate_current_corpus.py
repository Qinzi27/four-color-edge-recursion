"""Replay all declared histories and audit the separate static input inventory.

Declared policies are compared, with all failures retained. Static
drawings lacking a construction history receive topology checks, NOT a made-up
successful naming run. Frozen controls remain distinct from fresh restarts.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import gzip
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.current_names import attempt_current_cut
from fourcolor.embedding import PlaneMap
from fourcolor.inherited_names import state_payload
from fourcolor.interface_names import attempt_interface_cut
from fourcolor.local_reuse import attempt_local_cut
from scripts.audit_retained_blocks import independent_audits, unpack_state
from scripts.compare_local_marks import validate_state
from scripts.current_corpus import build_corpus
from scripts.validate_retained_profiles import compact_event

POLICIES = (
    {"key": "legacy-b3", "kind": "legacy", "budget": 3, "release": False},
    {"key": "pinned-b3", "kind": "current", "budget": 3, "release": False},
    {"key": "release-b3", "kind": "current", "budget": 3, "release": True},
    {"key": "release-b32-control", "kind": "current", "budget": 32, "release": True},
)

INTERFACE_POLICIES = (
    {"key": "interface-b3", "kind": "interface", "budget": 3, "release": True},
    {"key": "interface-b32-control", "kind": "interface", "budget": 32, "release": True},
)

STATIC_EXPORT = r"""
import fs from 'node:fs';
import {buildMap} from './web/engine.js';
// Geometry and rotation only: no marker chooser or coloring solver is called.
const rows=JSON.parse(fs.readFileSync(0,'utf8'));
console.log(JSON.stringify(rows.map(row=>{
  const m=buildMap(row.document);
  return {key:row.key,edges:m.edges.map(e=>({a:e.a,b:e.b,virtual:e.virtual})),
    rotation:m.rotation,faces:m.faces.map(f=>f.darts),faceOfDart:m.faceOfDart,original:m.original};
})));
"""


def digest(value):
    """Hash portable data; tuples and JSON lists serialize identically."""
    return sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def compact_current_event(event):
    """Keep IDs, restrictions and hashes; do not repeat every boundary segment.

    The full input paths and source hashes regenerate the original incidence
    records. Nested interface-repair events use the same profile compaction.
    """
    result = compact_event(event)
    if "endpoint_incidence" in result:
        original = result.pop("endpoint_incidence")
        result["endpoint_incidence_sha256"] = digest(original)
        result["endpoint_incidence_summary"] = [{
            "point": port["point"],
            "mothers": [{"id": item["id"], "position": item["position"]}
                        for item in port["incident_mothers"]],
            "side_ids": [side["id"] for side in port["incident_old_sides"]],
            "creates_color_constraint": False,
        } for port in original]
    if "after_shared_release_event" in result:
        result["after_shared_release_event"] = compact_current_event(result["after_shared_release_event"])
    return result


def audit_static_inputs(rows):
    """Independently rebuild face orbits for every static drawing, named or not."""
    checks = []
    for start in range(0, len(rows), 32):
        batch = rows[start:start + 32]
        process = subprocess.run(["node", "--input-type=module", "-e", STATIC_EXPORT], cwd=ROOT,
                                 input=json.dumps(batch), capture_output=True, text=True,
                                 encoding="utf-8", check=True)
        output = json.loads(process.stdout)
        if [r["key"] for r in output] != [r["key"] for r in batch]:
            raise AssertionError("static audit order/size changed")
        for row in output:
            plane = PlaneMap(tuple((str(e["a"]), str(e["b"])) for e in row["edges"]),
                             {str(i): tuple(ds) for i, ds in enumerate(row["rotation"])})
            if (plane.face_of_dart != tuple(row["faceOfDart"])
                    or plane.faces != tuple(tuple(f) for f in row["faces"])):
                raise AssertionError("static topology disagreement")
            original = row["original"]
            if original["vertices"] - original["edges"] + len(plane.faces) != 1 + original["components"]:
                raise AssertionError("static Euler identity failed")
            if any(e["virtual"] and len(set(plane.shores(i))) != 1 for i, e in enumerate(row["edges"])):
                raise AssertionError("virtual bridge incorrectly split a side")
            checks.append({"key": row["key"], "faces": len(plane.faces), "edges": len(plane.edges),
                           "topology_checked": True, "naming_claim": False, "certificate_sha256": digest(row)})
    return checks


def run_history(row, policy, emit_certificate):
    """One deterministic history; stop at the first failure, never change order."""
    base = {key: row[key] for key in ("key", "family", "cohort", "seed", "history_sha256", "aliases")}
    base.update({"policy": policy["key"], "planned_steps": len(row["paths"]), "steps": []})
    # An explicit zero-budget control remains zero even in the wide control.
    budget = 0 if row["max_old_sides"] == 0 else policy["budget"]
    base["max_old_sides"] = budget
    if row["initial_state"] is None:
        base.update({"status": "outside_scope", "reason": row["scope_hint"],
                     "committed_steps": 0, "final_state": None})
        return base
    state = unpack_state(row["initial_state"])
    stem = policy["key"] + "/" + row["key"]
    validate_state(state)
    emit_certificate(stem + "/initial", state)
    status, reason, changes = "completed", None, 0
    for index, path in enumerate(row["paths"], 1):
        before = state
        if policy["kind"] == "legacy":
            outcome = attempt_local_cut(state, path, max_old_sides=budget)
        elif policy["kind"] == "interface":
            outcome = attempt_interface_cut(state, path, max_old_sides=budget)
        else:
            outcome = attempt_current_cut(state, path, max_old_sides=budget, release=policy["release"])
        event = compact_current_event(outcome["event"])
        base["steps"].append({"step": index, "status": outcome["status"], "event": event})
        if outcome["status"] != "split":
            if outcome["state"] is not before:
                raise AssertionError("a rejected operation changed the committed state")
            status, reason = outcome["status"], event.get("reason")
            base["pending_path"] = path
            break
        state = outcome["state"]
        validate_state(state)
        if any(not 1 <= s.symbol <= 4 for s in state.sides):
            raise AssertionError("a submitted state contains a fifth name")
        changes += event["changed_old_count"]
        base["steps"][-1]["state_sha256"] = digest(state_payload(state))
        emit_certificate(stem + f"/{index}", state)
    base.update({"status": status, "reason": reason,
                 "committed_steps": sum(s["status"] == "split" for s in base["steps"]),
                 "old_side_change_events": changes, "final_state": state_payload(state)})
    return base


def build_report(include_interface=False):
    """Keep corpus provenance, side certificates, and matched policy comparisons."""
    corpus = build_corpus()
    policies = POLICIES + INTERFACE_POLICIES if include_interface else POLICIES
    sources = dict(corpus["source_sha256"])
    for name in ("scripts/validate_current_corpus.py", "fourcolor/current_names.py", "fourcolor/current_geometry.py",
                 "fourcolor/interface_names.py", "fourcolor/local_reuse.py", "fourcolor/retained_profiles.py", "fourcolor/anchor_forest.py",
                 "fourcolor/inherited_names.py", "fourcolor/line_names.py", "fourcolor/embedding.py",
                 "fourcolor/strip_chain.py", "scripts/audit_retained_blocks.py",
                 "scripts/inherited-oracle.mjs"):
        sources[name] = sha256((ROOT / name).read_bytes()).hexdigest()
    checks, buffer = [], []

    def flush():
        """Retain portable hashes rather than duplicate thousands of edge lists."""
        if not buffer:
            return
        independent_audits(buffer)
        for record in buffer:
            certificate = record["certificate"]
            audit = certificate["independent_audit"]
            checks.append({"key": record["key"], "state_sha256": digest(certificate["state"]),
                           "node_certificate_sha256": audit["node_certificate_sha256"],
                           "python_status": audit["python_status"]})
        buffer.clear()

    def emit(key, state):
        """Only legal initial or committed states are certified, never drafts."""
        buffer.append({"key": key, "certificate": {"state": state_payload(state)}})
        if len(buffer) >= 96:
            flush()

    runs, groups = [], []
    for policy in policies:
        selected = [run_history(row, policy, emit) for row in corpus["histories"]]
        runs.extend(selected)
        by_family = []
        for family in sorted({r["family"] for r in selected}):
            group = [r for r in selected if r["family"] == family]
            by_family.append({"family": family, "histories": len(group),
                              "outcomes": dict(Counter(r["status"] for r in group)),
                              "reasons": dict(Counter(r["reason"] for r in group if r["reason"]))})
        groups.append({"policy": policy["key"], "histories": len(selected),
                       "outcomes": dict(Counter(r["status"] for r in selected)),
                       "committed_splits": sum(r["committed_steps"] for r in selected),
                       "families": by_family})
        print(json.dumps(groups[-1], ensure_ascii=False), flush=True)
    flush()
    baseline = {r["history_sha256"]: r for r in runs if r["policy"] == "legacy-b3"}
    comparisons = []
    for policy in policies[1:]:
        matched = []
        for row in runs:
            if row["policy"] != policy["key"]:
                continue
            old = baseline[row["history_sha256"]]
            matched.append({"key": row["key"], "old_status": old["status"], "new_status": row["status"],
                            "old_steps": old["committed_steps"], "new_steps": row["committed_steps"],
                            "delta": row["committed_steps"] - old["committed_steps"]})
        comparisons.append({"policy": policy["key"],
                            "further": sum(r["delta"] > 0 for r in matched),
                            "earlier": sum(r["delta"] < 0 for r in matched),
                            "equal_depth": sum(r["delta"] == 0 for r in matched),
                            "old_complete_now_not": [r["key"] for r in matched
                                                     if r["old_status"] == "completed" and r["new_status"] != "completed"],
                            "matched": matched})
    static_checks = audit_static_inputs(corpus["static_inventory"])
    if any(sha256((ROOT / path).read_bytes()).hexdigest() != value for path, value in sources.items()):
        raise AssertionError("source changed during the formal run; use a new stable run")
    return {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "policies": policies, "corpus": corpus, "source_sha256": sources,
            "groups": groups, "runs": runs, "comparisons_to_legacy": comparisons,
            "independent_name_certificates": checks, "static_topology_checks": static_checks,
            "limits": ["All available DECLARED histories attempted; unsupported inputs explicitly retained.",
                       "Static topology checks are not successful naming or invented construction histories.",
                       "Budget3 policies are bounded proposals; budget32 is a separately labelled scope control.",
                       "Existing exploratory cases only; not held-out confirmation, a statistical success rate, or universal proof.",
                       "Failures, earlier blocks, and old-name controls are retained; no hidden search or order retry.",
                       "No browser default, website deployment, or GitHub content is changed by this script."]}


def main():
    """Create one new immutable evidence report; never overwrite previous runs."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-interface", action="store_true", help="Also test the separately derived shared-interface refinement")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; choose a new filename")
    report = build_report(include_interface=args.include_interface)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.suffix == ".gz":
        # Standard-library gzip keeps the corpus portable and under host file
        # limits; omit filename metadata so no private machine path is leaked.
        with args.output.open("xb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as stream:
                stream.write((json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
    else:
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    print(json.dumps({"independent_name_certificates": len(report["independent_name_certificates"]),
                      "static_topologies": len(report["static_topology_checks"]),
                      "matched_comparisons": [{k: v for k, v in r.items() if k != "matched"}
                                              for r in report["comparisons_to_legacy"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

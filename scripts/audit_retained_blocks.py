"""Audit first blocked states against the broader fixed-two-anchor theorem.

This is an independent ONE-STEP diagnostic, not a replacement for the saved
retained-profile policy. It reconstructs that policy's unbounded-mex proposal,
derives rectangular adjacency independently, and recognizes K2 joined to a
linear forest without requiring a straight geometric band. A unique unchanged
anchor and the exterior retain their old names. Each residual path starts at
its lexicographically smaller endpoint and alternates the two remaining names.
This canonical restart may change the requested inherited child and old names.
It scans graph structure, never enumerates or searches color assignments.

All generated certificates are checked through independent Node geometry and
Python line-rotation auditing. No continuation after the first block is run.
Input, original reports and production naming modules are never overwritten.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.inherited_names import RectSide, RectState, line_profiles, state_payload
from fourcolor.line_names import audit_line_names
from fourcolor.retained_profiles import attempt_profile_cut


POLICY = "complete-boundary+verified-strip"


def unpack_state(payload):
    """Restore immutable records; the production entry validates the old state."""
    return RectState(
        payload["width"], payload["height"],
        tuple(RectSide(side["id"], tuple(side["bounds"]), side["symbol"])
              for side in payload["sides"]),
        tuple(tuple(tuple(point) for point in cut) for cut in payload["cuts"]),
    )


def rectangle_adjacency(state):
    """Independently derive positive-length contacts, not point contacts.

    Coordinates in this report are exact integer rectangle coordinates. This
    diagnostic does not reuse the naming module's _shared/_adjacency helpers,
    does not merge equally named sides, and does not impose any name palette.
    """
    adjacency = {"outside": set(), **{side.id: set() for side in state.sides}}
    if len(adjacency) != len(state.sides) + 1:
        raise ValueError("side identities must be distinct from the exterior")

    def connect(first, second):
        adjacency[first].add(second)
        adjacency[second].add(first)

    for index, side in enumerate(state.sides):
        x0, y0, x1, y1 = side.bounds
        if x0 == 0 or y0 == 0 or x1 == state.width or y1 == state.height:
            connect("outside", side.id)
        for other in state.sides[index + 1:]:
            u0, v0, u1, v1 = other.bounds
            vertical = ((x1 == u0 or u1 == x0)
                        and min(y1, v1) > max(y0, v0))
            horizontal = ((y1 == v0 or v1 == y0)
                          and min(x1, u1) > max(x0, u0))
            if vertical or horizontal:
                connect(side.id, other.id)
    return adjacency


def dual_anchor_paths(adjacency, anchor):
    """Return canonical paths iff the COMPLETE graph is K2 join a forest.

    Both anchors must be universal and adjacent. Every residual component must
    have maximum degree two and exactly |V|-1 edges. An isolated side counts as
    a one-vertex path. Structural traversals here are not coloring DFS/search.
    """
    vertices = set(adjacency)
    if anchor == "outside" or anchor not in vertices:
        return None
    if (adjacency["outside"] != vertices - {"outside"}
            or adjacency[anchor] != vertices - {anchor}):
        return None
    anchors = {"outside", anchor}
    remaining, paths = vertices - anchors, []
    while remaining:
        first = next(iter(remaining))
        reached, queue, twice_edges = {first}, [first], 0
        for vertex in queue:
            neighbors = adjacency[vertex] - anchors
            if len(neighbors) > 2:
                return None
            twice_edges += len(neighbors)
            for neighbor in neighbors:
                if neighbor not in reached:
                    reached.add(neighbor)
                    queue.append(neighbor)
        if twice_edges != 2 * (len(reached) - 1):
            return None
        endpoints = [vertex for vertex in reached
                     if len(adjacency[vertex] - anchors) <= 1]
        vertex, previous, ordered = min(endpoints), None, []
        while True:
            ordered.append(vertex)
            onward = adjacency[vertex] - anchors
            if previous is not None:
                onward = onward - {previous}
            if not onward:
                break
            previous, vertex = vertex, next(iter(onward))
        if set(ordered) != reached:
            raise AssertionError("path traversal omitted a residual side")
        paths.append(ordered)
        remaining -= reached
    # Ordering the serialized components does not affect their chosen phases.
    return sorted(paths, key=lambda path: path[0])


def verify_assignment(adjacency, symbols, four_names=False):
    """Check every complete constraint independently of the naming policy."""
    if set(symbols) != set(adjacency) or symbols["outside"] != 1:
        raise AssertionError("assignment omits identities or changes exterior")
    if any(type(value) is not int or value < 1 for value in symbols.values()):
        raise AssertionError("names must be positive integers")
    if four_names and any(value > 4 for value in symbols.values()):
        raise AssertionError("canonical certificate exceeds four names")
    if any(symbols[first] == symbols[second]
           for first, neighbors in adjacency.items() for second in neighbors):
        raise AssertionError("a real boundary has equal opposing names")


def canonical_certificate(old, proposed, adjacency, candidate, parent_id, inherit):
    """Construct one canonical four-name result, not a choice among results."""
    anchor_id, anchor_symbol = candidate["id"], candidate["symbol"]
    remaining = sorted({1, 2, 3, 4} - {1, anchor_symbol})
    if len(remaining) != 2:
        raise AssertionError("the two fixed anchor names must differ")
    symbols = {"outside": 1, anchor_id: anchor_symbol}
    for path in candidate["new_paths"]:
        for index, side_id in enumerate(path):
            symbols[side_id] = remaining[index % 2]
    verify_assignment(adjacency, symbols, four_names=True)
    result = RectState(proposed.width, proposed.height,
                       tuple(RectSide(side.id, side.bounds, symbols[side.id])
                             for side in proposed.sides), proposed.cuts)
    old_symbols = {side.id: side.symbol for side in old.sides}
    changed = [{"id": side.id, "before": old_symbols[side.id], "after": side.symbol}
               for side in result.sides
               if side.id in old_symbols and side.symbol != old_symbols[side.id]]
    children = [("left", parent_id + ".l"), ("right", parent_id + ".r")]
    inherited = [label for label, side_id in children
                 if symbols[side_id] == old_symbols[parent_id]]
    actual_inherit = inherited[0] if len(inherited) == 1 else None
    return {
        "method": "canonical fixed-dual-anchor restart; no coloring enumeration",
        "scope": "one reconstructed blocked transition only; no later cuts executed",
        "inheritance_policy": "Only the two anchor names are fixed; requested inherit may change.",
        "anchors": {"outside": 1, anchor_id: anchor_symbol},
        "path_start_rule": "lexicographically smaller endpoint; isolated vertex starts itself",
        "phase_rule": "smallest remaining name at each path start, then alternate",
        "remaining_names": remaining,
        "paths": candidate["new_paths"],
        "symbols_by_side": symbols,
        "requested_inherit": inherit,
        "actual_inherit": actual_inherit,
        "requested_inherit_changed": actual_inherit != inherit,
        "changed_unsplit_old_sides": changed,
        "changed_unsplit_old_count": len(changed),
        "minimum_change_claim": False,
        "state": state_payload(result),
        "ordered_mother_profiles": line_profiles(result),
    }


def inspect_block(row):
    """Rebuild one saved first block, then classify its complete adjacency."""
    old = unpack_state(row["last_valid_state"])
    last = row["events"][-1]
    if (last["status"] != "blocked_sync_required"
            or last["step"] != row["committed_steps"] + 1):
        raise ValueError("input row does not end at its first uncommitted block")
    attempt = attempt_profile_cut(old, last["cut"], row["inherit"], synchronize=False)
    if attempt["status"] != "blocked_sync_required" or attempt["state"] is not old:
        raise AssertionError("reconstructed policy no longer matches saved block")
    event, proposed = attempt["event"], attempt["proposed_state"]
    for key in ("parent", "s", "R", "t"):
        if event[key] != last[key]:
            raise AssertionError(f"saved and reconstructed {key} disagree")
    old_adj, new_adj = rectangle_adjacency(old), rectangle_adjacency(proposed)
    for state, adjacency in ((old, old_adj), (proposed, new_adj)):
        verify_assignment(adjacency, {"outside": 1, **{s.id: s.symbol for s in state.sides}})
    candidates = []
    for anchor in old.sides:
        if anchor.id == event["parent"]:
            continue
        new_paths = dual_anchor_paths(new_adj, anchor.id)
        if new_paths is not None:
            candidates.append({"id": anchor.id, "symbol": anchor.symbol,
                               "bounds": anchor.bounds,
                               "old_paths": dual_anchor_paths(old_adj, anchor.id),
                               "new_paths": new_paths})
    candidates.sort(key=lambda candidate: candidate["id"])
    if not candidates:
        universal = new_adj["outside"] == set(new_adj) - {"outside"}
        classification = ("no_uncut_old_dual_anchor_linear_forest" if universal
                          else "outside_not_adjacent_to_every_side")
    else:
        classification = ("unique_dual_anchor_linear_forest" if len(candidates) == 1
                          else "multiple_anchors_not_chosen")
    record = {
        "key": f"{row['cohort']}/{row['seed']}/{row['inherit']}/{last['step']}",
        "seed": row["seed"], "cohort": row["cohort"], "family": row["family"],
        "source_policy": row["policy"], "requested_inherit": row["inherit"],
        "step": last["step"], "cut": event["cut"], "parent": event["parent"],
        "s": event["s"], "R": event["R"], "t": event["t"],
        "saved_sync_scope_reason": last.get("sync_scope_reason"),
        "last_valid_state": state_payload(old),
        "frozen_mex_proposal": state_payload(proposed),
        "old_adjacency": {key: sorted(value) for key, value in sorted(old_adj.items())},
        "proposed_adjacency": {key: sorted(value) for key, value in sorted(new_adj.items())},
        "classification": classification, "candidate_anchors": candidates,
        "certificate": None,
    }
    if len(candidates) == 1:
        record["certificate"] = canonical_certificate(
            old, proposed, new_adj, candidates[0], event["parent"], row["inherit"])
    return record


def independent_audits(records):
    """Check every new certificate using independent geometry and rotation."""
    selected = [record for record in records if record["certificate"] is not None]
    for start in range(0, len(selected), 64):
        batch = selected[start:start + 64]
        inputs = [{"key": record["key"], **record["certificate"]["state"]} for record in batch]
        process = subprocess.run(
            ["node", str(ROOT / "scripts" / "inherited-oracle.mjs")],
            cwd=ROOT, input=json.dumps(inputs), capture_output=True, text=True,
            encoding="utf-8", check=True,
        )
        results = json.loads(process.stdout)
        if [result["key"] for result in results] != [record["key"] for record in batch]:
            raise AssertionError("independent oracle changed batch order or size")
        for record, result in zip(batch, results):
            if result["errors"] or result["edge_conflicts"]:
                raise AssertionError({"key": record["key"], "oracle": result})
            audit = audit_line_names(result["rotation"], result["names"])
            expected_faces = len(record["certificate"]["state"]["sides"]) + 1
            if (audit.status != "consistent" or audit.conflicts
                    or len(audit.side_orbits) != expected_faces
                    or result["face_count"] != expected_faces
                    or any(not 1 <= int(name) <= 4 for pair in result["names"] for name in pair)):
                raise AssertionError(f"independent line audit failed: {record['key']}")
            # Full portable edge names and rotations allow a later audit without
            # trusting either the classifier or its positive outcome flag.
            record["certificate"]["independent_audit"] = {
                "node_geometry": result,
                "python_status": audit.status,
                "python_side_orbits": audit.side_orbits,
                "node_certificate_sha256": sha256(json.dumps(result, sort_keys=True).encode()).hexdigest(),
            }
    return len(selected)


def main():
    """Read one immutable report and exclusively create one new diagnostic."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; choose a new filename to preserve prior evidence")
    raw = args.input.read_bytes()
    source = json.loads(raw)
    if source.get("schema_version") != 2:
        parser.error("expected retained-profiles schema version 2")
    source_rows = [row for row in source["runs"]
                   if row["family"] == "guillotine" and row["policy"] == POLICY]
    blocked = [row for row in source_rows if row["status"] == "blocked_sync_required"]
    records = [inspect_block(row) for row in blocked]
    audited = independent_audits(records)
    eligible = [record for record in records if record["candidate_anchors"]]
    certified = [record for record in records if record["certificate"] is not None]
    groups = []
    for cohort, inherit in sorted({(record["cohort"], record["requested_inherit"]) for record in records}):
        group = [record for record in records
                 if (record["cohort"], record["requested_inherit"]) == (cohort, inherit)]
        groups.append({"cohort": cohort, "inherit": inherit, "blocked_runs": len(group),
                       "broader_family_runs": sum(bool(record["candidate_anchors"]) for record in group),
                       "one_step_certificates": sum(record["certificate"] is not None for record in group)})
    summary = {
        "selected_source_runs": len(source_rows),
        "selected_source_statuses": dict(Counter(row["status"] for row in source_rows)),
        "blocked_runs_audited": len(records),
        "broader_family_runs": len(eligible),
        "not_in_broader_family": len(records) - len(eligible),
        "unique_anchor_runs": len(certified),
        "multiple_anchor_runs": len(eligible) - len(certified),
        "single_path_runs": sum(len(record["candidate_anchors"][0]["new_paths"]) == 1 for record in certified),
        "multiple_path_runs": sum(len(record["candidate_anchors"][0]["new_paths"]) > 1 for record in certified),
        "same_anchor_matches_before_after": sum(record["candidate_anchors"][0]["old_paths"] is not None
                                                 for record in certified),
        "anchor_symbol_2_runs": sum(record["candidate_anchors"][0]["symbol"] == 2 for record in certified),
        "distinct_qualifying_seed_geometries": len({record["seed"] for record in eligible}),
        "canonical_inherit_changed_runs": sum(record["certificate"]["requested_inherit_changed"]
                                                for record in certified),
        "changed_unsplit_old_total": sum(record["certificate"]["changed_unsplit_old_count"]
                                          for record in certified),
        "node_and_python_certificates_passed": audited,
        "groups": groups,
    }
    files = ["scripts/audit_retained_blocks.py", "fourcolor/retained_profiles.py",
             "fourcolor/inherited_names.py", "fourcolor/strip_chain.py", "fourcolor/line_names.py",
             "scripts/inherited-oracle.mjs", "web/engine.js"]
    hashes = {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in files}
    result = {
        "schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "One-step diagnostic of saved first blocks under the broader fixed-dual-anchor theorem.",
        "input": {"filename": args.input.name, "sha256": sha256(raw).hexdigest(),
                  "schema_version": source["schema_version"]},
        "source_sha256": hashes,
        "input_report_matching_source_hashes": {
            name: hashes[name] == source["source_sha256"][name]
            for name in files if name in source.get("source_sha256", {})},
        "definitions": {
            "selection": "All guillotine runs of complete-boundary+verified-strip ending at their first block.",
            "recognition": "Complete rectangular side graph, exterior and one uncut old universal anchor, residual linear forest; no band requirement.",
            "canonical_naming": "Keep exterior 1 and unique anchor's old name; alternate other two names from lexicographically smaller endpoint of each path.",
            "multiplicity": "Runs are seed-and-inheritance-policy states, not necessarily distinct geometric maps.",
            "independence": "Rectangle adjacency is independently derived; Node rebuilds geometry/probes edge shores; Python independently rebuilds shore orbits from rotations.",
        },
        "limits": [
            "The main v2 experiment and its algorithm are unchanged.",
            "One-step certificates do not claim successful completion of any remaining construction history.",
            "Canonical restart may change the requested inherited side and any non-anchor old names; no minimum-change claim.",
            "Failure of recognition is not a proof that a four-name repair is impossible.",
            "Node and Python auditing reuse established geometry/rotation modules, not an independently reimplemented floating-point planarizer.",
            "No coloring enumeration, trial assignment, backtracking, or general four-color solver produces these certificates.",
        ],
        "summary": summary, "records": records,
    }
    # Exclusive creation also protects against a race after the early check.
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

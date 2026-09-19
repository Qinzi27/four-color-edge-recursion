"""Reproduce the user's marked A and two fixed-direction one-step repairs.

This bounded experiment does not change the production naming policy. The
chosen inheritance direction is part of each declared input, not a hidden
fallback. Both daughters' finite available-name sets are calculated once from
all actual old-boundary contacts; no assignments or histories are searched.
Historical names are provenance. A current mother-line profile is indexed by
position and directed shore, and is not a permanently accumulated ban list.
"""

from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.inherited_names import initial_state, line_profiles, state_payload
from fourcolor.retained_profiles import attempt_profile_cut
from scripts.audit_retained_blocks import (
    independent_audits, rectangle_adjacency, unpack_state, verify_assignment,
)


DEFAULT_INPUT = ROOT / "docs/figures/anchor-failures-2026-09-18/manifest.json"
PALETTE = frozenset((1, 2, 3, 4))


def audit_rectangle_state(state):
    """Independently check every positive-length contact, including outside."""
    adjacency = rectangle_adjacency(state)
    symbols = {"outside": 1, **{side.id: side.symbol for side in state.sides}}
    verify_assignment(adjacency, symbols, four_names=True)
    edges = [
        {"first": first, "second": second,
         "names": [symbols[first], symbols[second]]}
        for first in sorted(adjacency)
        for second in sorted(adjacency[first]) if first < second
    ]
    return {"status": "consistent", "outside_name": 1,
            "positive_length_edges": edges, "edge_count": len(edges),
            "adjacency": {key: sorted(value) for key, value in sorted(adjacency.items())}}


def daughter_domains(before, geometry, parent_id):
    """Derive each daughter's domain if the OTHER daughter inherits old s.

    The candidate's geometry is used, not its proposed or eventual name.
    Old neighbors exclude the sibling, whose inherited s is added separately.
    The two results are diagnostics, not calls to two coloring strategies.
    """
    adjacency = rectangle_adjacency(geometry)
    old_names = {"outside": 1, **{side.id: side.symbol for side in before.sides}}
    parent = next(side for side in before.sides if side.id == parent_id)
    children = [side for side in geometry.sides
                if side.id in (parent_id + ".l", parent_id + ".r")]
    if len(children) != 2:
        raise AssertionError("exactly two daughter identities are required")
    result = []
    for child in children:
        old_neighbors = sorted(adjacency[child.id] & (set(old_names) - {parent_id}))
        retained = sorted({old_names[key] for key in old_neighbors})
        # Screen coordinates have y down; geometric names avoid conflating
        # page-left/page-right with directed-left/directed-right shore labels.
        x0, y0, x1, y1 = child.bounds
        if (y0, y1) == (parent.bounds[1], parent.bounds[3]):
            location = "page_left" if x0 == parent.bounds[0] else "page_right"
        else:
            location = "page_top" if y0 == parent.bounds[1] else "page_bottom"
        result.append({
            "id": child.id, "bounds": child.bounds, "geometric_side": location,
            "directed_side": "left" if child.id.endswith(".l") else "right",
            "inherit_for_other_child": "right" if child.id.endswith(".l") else "left",
            "old_contacts": [{"id": key, "symbol": old_names[key]} for key in old_neighbors],
            "R": retained, "s": parent.symbol,
            "available_names": sorted(PALETTE - set(retained) - {parent.symbol}),
            "touches_outside": "outside" in old_neighbors,
        })
    return sorted(result, key=lambda row: row["geometric_side"])


def run_declared_steps(start, cuts, inherit):
    """Apply one explicitly declared direction to each cut without retrying."""
    state, steps = start, []
    initial_audit = audit_rectangle_state(state)
    for number, cut in enumerate(cuts, start=len(start.cuts) + 1):
        before = state
        attempt = attempt_profile_cut(before, cut, inherit=inherit, synchronize=False)
        if attempt["status"] != "split":
            raise AssertionError(f"declared step {number} failed: {attempt['status']}")
        state = attempt["state"]
        event = attempt["event"]
        if event["changed_old_sides"] or event["sync_attempted"]:
            raise AssertionError("the declared direct operation unexpectedly renamed old sides")
        steps.append({
            "step": number, "cut": cut, "inherit": inherit,
            "status": attempt["status"], "event": event,
            "state": state_payload(state),
            "rectangle_audit": audit_rectangle_state(state),
            "daughter_domains": daughter_domains(before, state, event["parent"]),
        })
    return {
        "initial_state": state_payload(start), "initial_rectangle_audit": initial_audit,
        "steps": steps, "final_state": state_payload(state),
        "final_profiles": line_profiles(state),
        "final_step_domains": steps[-1]["daughter_domains"],
        "inherit": inherit, "synchronize": False,
        "no_unsplit_old_side_renamed": True,
    }


def original_direction_control(case):
    """Retain the original fixed-direction failure as an uncommitted control."""
    before = unpack_state(case["current_committed_state"])
    attempt = attempt_profile_cut(before, case["pending_cut"],
                                  inherit=case["inherit"], synchronize=False)
    if attempt["status"] != "blocked_sync_required" or attempt["state"] is not before:
        raise AssertionError("the previously reported fixed-direction block changed")
    return {"inherit": case["inherit"], "status": attempt["status"],
            "state_unchanged": True, "s": attempt["event"]["s"],
            "R": attempt["event"]["R"], "t": attempt["event"]["t"],
            "scope": "Uncommitted frozen-direction diagnostic, not a fifth-name necessity."}


def build_report(inputpath=DEFAULT_INPUT, with_node_oracle=True):
    """Return a deterministic, portable report; do not write any files.

    Node rebuilds all nine committed states from strokes independently of the
    rectangle naming policy. Python's separate rotation audit then checks the
    returned shore-orbit labels. Disabling Node is explicit in the report.
    """
    source_path = Path(inputpath)
    raw = source_path.read_bytes()
    source = json.loads(raw)
    inputs = {case["case"]: case for case in source["cases"]}
    if set(inputs) != {"A", "B"}:
        raise ValueError("the diagram manifest must contain exactly A and B")
    a, b = inputs["A"], inputs["B"]
    old_a = unpack_state(a["current_committed_state"])
    old_b = unpack_state(b["current_committed_state"])
    cases = {
        "user_a_replay": run_declared_steps(
            initial_state(old_a.width, old_a.height),
            a["current_committed_state"]["cuts"] + [a["pending_cut"]], "left"),
        "original_a_reverse": run_declared_steps(old_a, [a["pending_cut"]], "left"),
        "b_reverse": run_declared_steps(old_b, [b["pending_cut"]], "right"),
    }
    cases["user_a_replay"]["interpretation"] = (
        "Replay A from the outside anchor; matches the user's marked final names. "
        "This does not preserve the prior program's intermediate naming history.")
    cases["original_a_reverse"]["interpretation"] = (
        "Preserve the published old A names; explicitly change only final inheritance. "
        "Its valid final names differ from the user's full replay.")
    cases["b_reverse"]["interpretation"] = (
        "Preserve B's old names; page-left child inherits 4, interior page-right child gets 1. "
        "Outside name 1 is a local boundary constraint, not a ban on all interior uses of 1.")
    for name, case in cases.items():
        source_case = b if name == "b_reverse" else a
        case["source_case"] = source_case["case"]
        case["seed"] = source_case["seed"]

    # The existing oracle runner mutates only these fresh certificate records.
    # Input states and all original experimental reports remain untouched.
    oracle_records, destinations = [], []
    for name, case in cases.items():
        oracle_records.append({"key": name + "/initial",
                               "certificate": {"state": case["initial_state"]}})
        destinations.append(case)
        for step in case["steps"]:
            oracle_records.append({"key": f"{name}/step-{step['step']}",
                                   "certificate": {"state": step["state"]}})
            destinations.append(step)
    audited = independent_audits(oracle_records) if with_node_oracle else 0
    if with_node_oracle:
        for record, destination in zip(oracle_records, destinations):
            destination["independent_audit"] = record["certificate"]["independent_audit"]

    files = ["scripts/validate_marked_cases.py", "scripts/audit_retained_blocks.py",
             "fourcolor/inherited_names.py", "fourcolor/retained_profiles.py",
             "fourcolor/line_names.py", "scripts/inherited-oracle.mjs", "web/engine.js"]
    result = {
        "schema_version": 1,
        "input": {"filename": source_path.name, "sha256": sha256(raw).hexdigest(),
                  "original_report": source["input"]},
        "source_sha256": {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in files},
        "definitions": {
            "current_record": "A mother ID, position interval, directed shore and current name; not a permanent ban.",
            "history_record": "Parent/child provenance and earlier names remain separate from current boundary restrictions.",
            "candidate_domain": "For daughter D newly named and other child inheriting s: {1,2,3,4} minus (R(D) union {s}).",
            "R": "Names of every old side sharing a positive-length boundary with D, including outside only when actually adjacent.",
            "direction": "Directed left/right uses screen y-down; page-left/page-right is recorded separately.",
        },
        "cases": cases,
        "original_direction_controls": {"A": original_direction_control(a),
                                        "B": original_direction_control(b)},
        "summary": {"declared_experiments": 3,
                    "successful_steps": sum(len(case["steps"]) for case in cases.values()),
                    "rectangle_states_audited": len(oracle_records),
                    "node_and_rotation_states_audited": audited,
                    "node_oracle_enabled": with_node_oracle},
        "limits": [
            "Three fixed finite experiments; no general four-colorability proof.",
            "No production-policy change, automatic direction retry, assignment enumeration or backtracking.",
            "The two domains are geometric diagnostics, not evidence that one is always nonempty.",
            "The user's marked drawing supplies the A interpretation; printed notes not fully formalized are not silently turned into rules.",
        ],
    }
    # JSON normalization makes function output and saved/reloaded reports equal.
    return json.loads(json.dumps(result, ensure_ascii=False))


def main():
    """Print the bounded summary and optionally exclusively create a report."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output is not None and args.output.exists():
        parser.error("output exists; choose a new filename to preserve prior evidence")
    report = build_report(args.input)
    if args.output is not None:
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

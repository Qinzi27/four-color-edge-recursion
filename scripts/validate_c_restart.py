"""Recompute case C from the outside anchor, without searching old histories.

This is a declared replay of one saved geometry, not a general minimum-color
algorithm. Explicit adjacent triples/quadruples certify minimality only for C.
The old fixed-right snapshot is retained as a valid but nonminimal control.
"""

from argparse import ArgumentParser
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.inherited_names import initial_state, state_payload
from scripts.audit_retained_blocks import independent_audits, rectangle_adjacency, unpack_state
from scripts.compare_local_marks import METHODS, compare_cut
from scripts.validate_marked_cases import audit_rectangle_state, run_declared_steps

SOURCE = ROOT / "outputs/anchor-forest-continuation-2026-09-18-v2.json"


def clique_bound(state, vertices):
    """Check a supplied clique, not enumerate cliques or color assignments.

    Every witnessed pair must share a positive-length boundary; corner-only
    contacts do not count. A proper assignment attaining this bound is minimal.
    """
    audit_rectangle_state(state)
    graph = rectangle_adjacency(state)
    if len(vertices) != len(set(vertices)) or not vertices:
        raise ValueError("a witness needs distinct vertices")
    pairs = list(combinations(vertices, 2))
    if any(v not in graph for v in vertices) or any(b not in graph[a] for a, b in pairs):
        raise ValueError("the supplied vertices are not pairwise adjacent")
    used = sorted({1} | {side.symbol for side in state.sides})
    return {"witness_vertices": list(vertices), "positive_length_pairs": pairs,
            "lower_bound_including_outside": len(vertices), "used_names": used,
            "attains_bound": len(used) == len(vertices)}


def build_report(source_path=SOURCE, with_node_oracle=True):
    """Replay exactly the original three cuts with a predeclared left shore.

    Directed left means page-up for a rightward cut, but page-right for a
    downward cut. It is an input convention, not a fallback chosen after failure.
    """
    source_path = Path(source_path)
    raw = source_path.read_bytes()
    matches = [row for row in json.loads(raw)["runs"]
               if (row["family"], row["seed"], row["inherit"])
               == ("guillotine", 20260960, "right")]
    if len(matches) != 1:
        raise ValueError("case C must have one exact composite source key")
    source = matches[0]
    old = unpack_state(source["last_valid_state"])
    pending = source["events"][-1]["cut"]
    if source["status"] != "blocked_sync_required" or len(old.cuts) != 2:
        raise ValueError("source is not the saved C third-step block")
    start = initial_state(old.width, old.height)
    control = run_declared_steps(start, old.cuts, "right")
    if unpack_state(control["final_state"]) != old:
        raise AssertionError("fixed-right replay no longer matches the saved snapshot")
    replay = run_declared_steps(start, list(old.cuts) + [pending], "left")
    before = unpack_state(replay["steps"][1]["state"])
    after = unpack_state(replay["final_state"])
    top, middle = "root.l", "root.r.l"
    witnesses = {
        "old_fixed_right": clique_bound(old, ["outside", top, middle]),
        "restarted_before": clique_bound(before, ["outside", top, middle]),
        "restarted_after": clique_bound(after, ["outside", top, middle + ".l", middle + ".r"]),
    }
    # Fail closed if a custom input or later implementation drifts from C;
    # the explanatory statements below must match the actual certificates.
    ordered_names = lambda state: [side.symbol for side in sorted(state.sides, key=lambda s: s.bounds[1])]
    if (ordered_names(old) != [3, 4, 2] or ordered_names(before) != [2, 3, 2]
            or not witnesses["restarted_before"]["attains_bound"]
            or not witnesses["restarted_after"]["attains_bound"]):
        raise AssertionError("case C no longer matches its stated minimality certificates")
    results = [compare_cut(before, pending, method) for method in METHODS]
    for result in results:
        if (result["status"] != "split" or result["used_stage"] != "M1_direct"
                or result["changed_old_count"] != 0 or result["repair"]["attempted"]
                or unpack_state(result["final_state"]) != after):
            raise AssertionError("normalized C should use the identical direct step in all methods")

    # Preserve portable oracle certificates; repeated outputs are certificates,
    # not distinct maps or evidence of a larger coverage than this single C.
    records = [{"key": "C/restart-initial", "certificate": {"state": state_payload(start)}}]
    records += [{"key": f"C/restart-{step['step']}", "certificate": {"state": step["state"]}}
                for step in replay["steps"]]
    records += [{"key": "C/normalized-" + result["method"],
                 "certificate": {"state": result["final_state"]}} for result in results]
    count = independent_audits(records) if with_node_oracle else 0
    files = [Path(__file__), ROOT / "scripts/validate_marked_cases.py",
             ROOT / "scripts/compare_local_marks.py", ROOT / "scripts/audit_retained_blocks.py",
             ROOT / "scripts/inherited-oracle.mjs", ROOT / "fourcolor/inherited_names.py",
             ROOT / "fourcolor/retained_profiles.py"]
    return {
        "schema_version": 1,
        "scope": "One declared C replay; no generic normalization, search, or four-color proof.",
        "source": {"filename": source_path.name, "sha256": sha256(raw).hexdigest(),
                   "family": "guillotine", "seed": 20260960, "inherit": "right"},
        "code_sha256": {p.relative_to(ROOT).as_posix(): sha256(p.read_bytes()).hexdigest()
                        for p in files},
        "fixed_right_control": control, "declared_left_replay": replay,
        "pending_cut": pending, "minimality_certificates": witnesses,
        "first_avoidable_extra_name_step": 2,
        "normalized_three_methods": results,
        "independent_certificate_count": count,
        "independent_oracle_status": "checked" if with_node_oracle else "explicitly_skipped",
        "independent_certificates": records if with_node_oracle else [],
        "interpretation": (
            "342 is proper but uses four names including outside, whereas 232 needs three. "
            "After the pending cut, a K4 certificate makes four necessary. The old C does "
            "not establish a repair requirement for the user's minimum-reuse starting rule."),
    }


def main():
    """Write a fresh report; preserve every earlier experiment and figure."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; select a fresh path")
    report = build_report(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"replay_steps": 3, "normalized_direct_methods": 3,
                      "independent_certificates": report["independent_certificate_count"]}))


if __name__ == "__main__":
    main()

"""Compare three whole-line priorities on the same fixed 255-map corpus.

Ten independent one-pass runs per policy/map: forward, reverse and eight fixed
random tie seeds. No run retries a failed choice or uses another run's answer.
Tests inspect all outcomes; successful outcomes are not selected for delivery
as if they were guaranteed by the rule. Existing output paths are refused.
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

from fourcolor.embedding import PlaneMap
from fourcolor.line_names import audit_line_names
from fourcolor.whole_lines import build_whole_lines
from fourcolor.weighted_lines import POLICIES, line_metadata, run_weighted_lines


TIE_SEEDS = tuple(range(20260918, 20260926))
VARIANTS = (("forward", None), ("reverse", None)) + tuple(("random", seed) for seed in TIE_SEEDS)


def independent_check(geometry: dict, result: dict) -> bool:
    """Check success or committed-state contradiction using a separate scan.

    This uses direct side adjacency reconstructed from the supplied rotation,
    not production weights, priorities or its propagation routine. An empty
    domain proves only that these COMMITTED choices have no completion.
    """
    plane = PlaneMap(tuple((str(e["a"]), str(e["b"])) for e in geometry["edges"]),
                     {str(v): tuple(ds) for v, ds in enumerate(geometry["rotation"])})
    domains = [set((1, 2, 3, 4)) for _ in plane.faces]
    for dart, candidates in result["anchors_by_dart"].items():
        domains[plane.face_of_dart[int(dart)]].intersection_update(candidates)
    changed = True
    while changed and all(domains):
        changed = False
        for edge in range(len(plane.edges)):
            left, right = plane.shores(edge)
            if left == right:
                continue
            for first, other in ((left, right), (right, left)):
                if len(domains[first]) == 1:
                    revised = domains[other] - domains[first]
                    if revised != domains[other]:
                        domains[other] = revised
                        changed = True
                if not domains[other]:
                    break
            if not all(domains):
                break
    if result["status"] == "conflict":
        return not all(domains)
    if result["status"] != "solved" or not all(len(d) == 1 for d in domains):
        return False
    colors = [next(iter(d)) for d in domains]
    if [[color] for color in colors] != result["domains"]:
        return False
    if not plane.check_coloring([color - 1 for color in colors]):
        return False
    names = tuple((str(colors[a]), str(colors[b])) for a, b in
                  (plane.shores(e) for e in range(len(plane.edges))))
    return audit_line_names(geometry["rotation"], names).status == "consistent"


def compact_result(result: dict) -> dict:
    """Keep every terminal outcome plus enough anchors for independent checks.

    Full traces are reproducible from geometry/policy/tie seed and their hashes.
    The explicit same-state counterexample below retains full branch traces.
    """
    payload = json.dumps(result["trace"], sort_keys=True, separators=(",", ":"))
    return {key: result[key] for key in ("status", "policy", "tie_break", "seed", "domains",
                                       "anchors_by_dart", "choices", "non_symmetry_choices",
                                       "random_draws", "backtracks")} | {
        "selected_lines": [step["line"] for step in result["trace"]],
        "trace_sha256": sha256(payload.encode("utf-8")).hexdigest(),
        "independently_checked": True,
    }


def same_state_counterexample(record: dict, model) -> dict:
    """Keep one equal-weight fork whose bad branch fails during that very line."""
    horizontal = "L:0,326>900,326"
    vertical = "L:722,110>722,326"
    bad = run_weighted_lines(model, "constraints", forced_prefix=("frame", horizontal))
    good = run_weighted_lines(model, "constraints", forced_prefix=("frame", vertical))
    assert bad["trace"][0] == good["trace"][0]
    assert bad["trace"][1]["weight"] == good["trace"][1]["weight"] == 7
    assert bad["trace"][1]["tied_lines"] == good["trace"][1]["tied_lines"]
    assert len(bad["trace"]) == 2 and bad["status"] == "conflict"
    assert good["status"] == "solved"
    assert independent_check(record["geometry"], bad)
    assert independent_check(record["geometry"], good)
    return {"map": record["id"], "policy": "constraints", "shared_prefix": ["frame"],
            "tied_weight": 7, "bad_first_line": horizontal, "good_first_line": vertical,
            "bad_branch": bad, "good_branch": good,
            "interpretation": "Same geometry, anchors and propagated domains before the fork. The bad branch's fixed-minimum assignments conflict within that selected whole line. This refutes order safety for the specified irreversible naming rule, not for unconstrained future renaming."}


def run_validation() -> dict:
    """Run all variants independently, preserving failures and exact seed bounds."""
    fixtures = json.loads(subprocess.check_output(
        ["node", str(ROOT / "scripts" / "whole-line-fixtures.mjs"), "--emit"], cwd=ROOT, encoding="utf-8"))
    records, fork = [], None
    for source in fixtures["records"]:
        model = build_whole_lines(source["geometry"])
        runs = []
        for policy in POLICIES:
            for tie, seed in VARIANTS:
                result = run_weighted_lines(model, policy, tie, seed)
                assert independent_check(source["geometry"], result), (source["id"], policy, tie, seed)
                runs.append(compact_result(result))
        records.append({"id": source["id"], "family": source["family"], "seed": source["seed"],
                        "document": source["document"], "geometry": source["geometry"], "runs": runs})
        if source["id"] == "guillotine-20260916":
            fork = same_state_counterexample(source, model)
    assert fork is not None
    summary = []
    for policy in POLICIES:
        variants = []
        for tie, seed in VARIANTS:
            selected = [(record, next(r for r in record["runs"] if r["policy"] == policy
                                      and r["tie_break"] == tie and r["seed"] == seed)) for record in records]
            count = Counter(run["status"] for _, run in selected)
            variants.append({"tie_break": tie, "seed": seed, "solved": count["solved"],
                             "conflict": count["conflict"],
                             "conflict_map_ids": [record["id"] for record, run in selected if run["status"] == "conflict"]})
        categories = Counter()
        sensitive = []
        for record in records:
            statuses = {r["status"] for r in record["runs"] if r["policy"] == policy}
            category = "all_tested_solved" if statuses == {"solved"} else "all_tested_conflict" if statuses == {"conflict"} else "order_sensitive"
            categories[category] += 1
            if category == "order_sensitive":
                sensitive.append(record["id"])
        random_counts = [v["solved"] for v in variants if v["tie_break"] == "random"]
        summary.append({"policy": policy, "maps": len(records), "runs": len(records) * len(VARIANTS),
                        "variants": variants, "random_solved_range": [min(random_counts), max(random_counts)],
                        "observed_map_categories": dict(categories), "order_sensitive_map_ids": sensitive})
    hashes = dict(fixtures["source_sha256"])
    for source in ("fourcolor/whole_lines.py", "fourcolor/weighted_lines.py", "fourcolor/embedding.py",
                   "fourcolor/line_names.py", "scripts/validate_weighted_lines.py"):
        hashes[source] = sha256((ROOT / source).read_bytes()).hexdigest()
    return {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "experiment": "Three whole-line weights, same fixed smallest-symbol rule, ten tie variants",
            "maps": len(records), "runs": len(records) * len(POLICIES) * len(VARIANTS),
            "geometry_seed_range": fixtures["seed_range"], "tie_seeds": list(TIE_SEEDS),
            "definitions": {
                "connections": "Number of distinct other real whole lines touching this line; frame counts once.",
                "constraints": "Sum of 4 minus domain size over distinct UNRESOLVED shore identities incident to the line.",
                "outer-layer": "Negative shortest line-contact distance from frame; disconnected lines tied below rooted ones. A proxy, not a unique mother genealogy.",
                "assignment": "Only exterior=1 and first adjacent interior=2 initially. Highest-weight whole line; t-increasing left-before-right profile; smallest candidate committed, then singleton propagation. Recompute weights between whole-line batches.",
                "ties": "Geometry-ID forward/reverse, or random only within highest-weight ties. No failed-run fallback.",
            },
            "limitations": ["Only the combined line-scheduling and irreversible minimum-symbol rule is tested.",
                            "Four is an explicit candidate palette, not a proved consequence of line naming.",
                            "Ten schedules per map are not all schedules. Reported ranges are descriptive, not success probabilities.",
                            "A conflict proves these committed choices have no completion, not that the map cannot be four-colored.",
                            "Exact same-state branch evidence is provided for constraints, not claimed for every policy."],
            "source_sha256": hashes, "summary": summary, "same_state_counterexample": fork, "records": records}


def main():
    """Save one immutable experiment report and print its compact outcome table."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; choose a new filename")
    report = run_validation()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    compact = [{"policy": r["policy"],
                "forward_solved": r["variants"][0]["solved"], "reverse_solved": r["variants"][1]["solved"],
                "random_solved_range": r["random_solved_range"], **r["observed_map_categories"]}
               for r in report["summary"]]
    print(json.dumps({"maps": report["maps"], "runs": report["runs"], "results": compact}, indent=2))


if __name__ == "__main__":
    main()

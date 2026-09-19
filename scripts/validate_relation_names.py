"""Compare the relation-name extension with identical-anchor old propagation.

No global coloring search supplies production names. Set-based proof replay and
full fixed-point checks audit the bit-matrix implementation independently.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.embedding import PlaneMap
from fourcolor.joint_lines import run_joint_lines
from fourcolor.line_names import audit_line_names
from fourcolor.relation_names import run_relation_names
from fourcolor.whole_lines import build_whole_lines
from scripts.validate_joint_lines import independent_check as check_joint


def _decode(mask):
    """Independent set-valued representation with zero-based names."""
    return {(position // 4, position % 4) for position in range(16) if mask & (1 << position)}


def independent_check(geometry, outcome):
    """Verify each composition deletion, symmetry claim and final certificate."""
    check_joint(geometry, outcome["base"])
    plane = PlaneMap(tuple((str(e["a"]), str(e["b"])) for e in geometry["edges"]),
                     {str(v): tuple(ds) for v, ds in enumerate(geometry["rotation"])})
    domains = [set(c - 1 for c in d) for d in outcome["base"]["domains"]]
    n = len(domains)
    adjacency = {frozenset(plane.shores(e)) for e in range(len(plane.edges))
                 if len(set(plane.shores(e))) == 2}
    relations = [[{(a, b) for a in domains[i] for b in domains[j]
                   if (a == b if i == j else a != b if frozenset((i, j)) in adjacency else True)}
                  for j in range(n)] for i in range(n)]
    assert relations == [[_decode(mask) for mask in row] for row in outcome["initial_relations"]]

    def check_closed():
        """Check every surviving pair's middle support via independent sets."""
        # Cache support sets once per matrix; production uses boolean masks.
        rows = [[[{b for x, b in relations[i][j] if x == a} for a in range(4)]
                 for j in range(n)] for i in range(n)]
        for i in range(n):
            for j in range(n):
                for a, b in relations[i][j]:
                    for k in range(n):
                        assert rows[i][k][a] & rows[j][k][b], (i, j, k, a, b)

    assert len(outcome["phases"]) == len(outcome["normalizations"]) + 1
    for index, phase in enumerate(outcome["phases"]):
        for event in phase:
            i, j, k = event["i"], event["j"], event["via"]
            before, left, right = relations[i][j], relations[i][k], relations[k][j]
            assert _decode(event["before"]) == before
            assert _decode(event["left"]) == left and _decode(event["right"]) == right
            supported = {(a, b) for a, c in left for c2, b in right if c == c2}
            after = before & supported
            assert after != before and _decode(event["after"]) == after
            assert _decode(event["removed"]) == before - after
            relations[i][j] = after
            relations[j][i] = {(b, a) for a, b in after}
        if index < len(outcome["normalizations"]):
            assert all(relations[i][j] for i in range(n) for j in range(n))
            check_closed()
            step = outcome["normalizations"][index]
            current = [{a for a, b in relations[i][i]} for i in range(n)]
            used = {next(iter(d)) for d in current if len(d) == 1}
            unused = set(range(4)) - used
            assert sorted(c + 1 for c in unused) == step["unused"]
            assert len(unused) > 1 and current[step["side"]] == unused
            for b in unused - {min(unused)}:
                a = min(unused)
                transform = lambda x: b if x == a else a if x == b else x
                assert all({(transform(x), transform(y)) for x, y in rel} == rel
                           for row in relations for rel in row)
            side, symbol = step["side"], step["symbol"] - 1
            assert symbol == min(unused) and plane.face_of_dart[step["dart"]] == side
            assert _decode(step["before"]) == relations[side][side]
            relations[side][side] = {(symbol, symbol)}
            assert _decode(step["after"]) == relations[side][side]
    assert relations == [[_decode(mask) for mask in row] for row in outcome["relations"]]
    final_domains = [sorted(a + 1 for a, b in relations[i][i]) for i in range(n)]
    assert final_domains == outcome["domains"]
    conflict = any(not rel for row in relations for rel in row)
    expected = "conflict" if conflict else "solved" if all(len(d) == 1 for d in final_domains) else "underdetermined"
    assert outcome["status"] == expected
    if not conflict:
        check_closed()
    if expected == "solved":
        colors = [d[0] for d in final_domains]
        assert plane.check_coloring([c - 1 for c in colors])
        names = tuple((str(colors[a]), str(colors[b])) for a, b in
                      (plane.shores(e) for e in range(len(plane.edges))))
        assert audit_line_names(geometry["rotation"], names).status == "consistent"
    for line in outcome["profiles"]:
        for span in line["spans"]:
            a, b = plane.face_of_dart[span["dart"]], plane.face_of_dart[span["dart"] ^ 1]
            assert (a, b) == (span["left_side"], span["right_side"])
            assert {(x - 1, y - 1) for x, y in span["pairs"]} == relations[a][b]
    assert outcome["backtracks"] == outcome["non_symmetry_choices"] == 0
    assert outcome["choices"] == len(outcome["normalizations"])
    return True


def _hash(value):
    """Hash a deterministic trace without duplicating it in every report row."""
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def old_policy_comparison():
    """Summarize actual saved runs; do not rank unlike method scopes together."""
    source = ROOT / "outputs/joint-lines-2026-09-18-v2.json"
    saved = json.loads(source.read_text(encoding="utf-8"))
    rows = []
    for symmetry in (False, True):
        for policy in ("connections", "constraints", "outer-layer"):
            runs = [run for record in saved["records"] for run in record["runs"]
                    if run["policy"] == policy and run["symbol_symmetry"] == symmetry]
            default = [run for run in runs if run["tie_break"] == "forward"]
            rows.append({"symbol_symmetry": symmetry, "policy": policy,
                "forward_checks": sum(r["line_checks"] for r in default),
                "forward_median_checks": median(r["line_checks"] for r in default),
                "all_ten_checks": sum(r["line_checks"] for r in runs),
                "all_ten_median_checks": median(r["line_checks"] for r in runs)})
    return {"source": str(source.relative_to(ROOT)), "sha256": sha256(source.read_bytes()).hexdigest(),
            "rows": rows, "interpretation": "constraints+forward has lowest default fixed-forward check count; not a universal best weight."}


def run_validation():
    """Run one chosen default method on baseline and prespecified fresh seeds."""
    fixtures = json.loads(subprocess.run(["node", "scripts/relation-fixtures.mjs"], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", check=True).stdout)
    records = []
    for source in fixtures["records"]:
        model = build_whole_lines(source["geometry"])
        runs = []
        for symmetry in (False, True):
            result = run_relation_names(model, symbol_symmetry=symmetry)
            independent_check(source["geometry"], result)
            anchors = dict(result["base"]["anchors_by_dart"])
            for step in result["normalizations"]:
                anchors[step["dart"]] = [step["symbol"]]
            old = run_joint_lines(model, anchors=anchors)
            check_joint(source["geometry"], old)
            assert all(set(new) <= set(prior) for new, prior in zip(result["domains"], old["domains"]))
            # Recompute the old relation projection at matching anchors by set
            # products; a missing pair can be new even with unchanged domains.
            n = len(result["domains"])
            adjacent = {frozenset(model.plane_map.shores(e)) for e in range(len(model.plane_map.edges))
                        if len(set(model.plane_map.shores(e))) == 2}
            extra_pairs = 0
            for i in range(n):
                for j in range(i + 1, n):
                    old_pairs = {(a - 1, b - 1) for a in old["domains"][i] for b in old["domains"][j]
                                 if frozenset((i, j)) not in adjacent or a != b}
                    new_pairs = _decode(result["relations"][i][j])
                    assert new_pairs <= old_pairs
                    extra_pairs += len(old_pairs - new_pairs)
            runs.append({"symbol_symmetry": symmetry, "status": result["status"],
                "domains": result["domains"], "relations": result["relations"],
                "normalizations": result["normalizations"], "anchors_by_dart": result["base"]["anchors_by_dart"],
                "revisions": result["revisions"], "extra_unary_removals_same_anchors":
                    sum(map(len, old["domains"])) - sum(map(len, result["domains"])),
                "extra_unordered_pair_removals_same_anchors": extra_pairs,
                "joint_status_same_anchors": old["status"],
                "trace_sha256": _hash(result["phases"]), "choices": result["choices"],
                "backtracks": 0, "non_symmetry_choices": 0, "independently_checked": True})
        records.append({key: source[key] for key in ("id", "cohort", "family", "seed", "document", "geometry")} | {"runs": runs})
    proof_path = ROOT / "outputs/weighted-counterexample-candidate-2026-09-18-v2.json"
    proof = json.loads(proof_path.read_text(encoding="utf-8"))["proof"]
    nine = build_whole_lines(proof["geometry"])
    cases = {}
    for tag, anchors in (("fresh", None), ("conditioned", {int(k): v for k, v in proof["same_state"]["anchors_by_dart"].items()})):
        result = run_relation_names(nine, anchors=anchors)
        independent_check(proof["geometry"], result)
        cases[tag] = result
    summary = []
    for cohort in ("baseline", "fresh-seeds"):
        for symmetry in (False, True):
            runs = [r for row in records if row["cohort"] == cohort for r in row["runs"]
                    if r["symbol_symmetry"] == symmetry]
            counts = Counter(r["status"] for r in runs)
            summary.append({"cohort": cohort, "maps": len(runs), "symbol_symmetry": symmetry,
                **{s: counts[s] for s in ("solved", "underdetermined", "conflict")},
                "maps_unary_improved": sum(r["extra_unary_removals_same_anchors"] > 0 for r in runs),
                "extra_unary_removals": sum(r["extra_unary_removals_same_anchors"] for r in runs),
                "maps_pairs_improved": sum(r["extra_unordered_pair_removals_same_anchors"] > 0 for r in runs),
                "extra_unordered_pairs_removed": sum(r["extra_unordered_pair_removals_same_anchors"] for r in runs)})
    hashes = dict(fixtures["source_sha256"])
    for path in ("fourcolor/relation_names.py", "fourcolor/joint_lines.py", "fourcolor/whole_lines.py",
                 "fourcolor/weighted_lines.py", "scripts/validate_relation_names.py",
                 "scripts/validate_joint_lines.py", "fourcolor/embedding.py", "fourcolor/line_names.py"):
        hashes[path] = sha256((ROOT / path).read_bytes()).hexdigest()
    return {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "policy": "constraints", "tie_break": "forward", "maps": len(records), "runs": 2 * len(records),
        "fresh_seed_range": fixtures["fresh_seed_range"], "source_sha256": hashes,
        "old_policy_comparison": old_policy_comparison(), "summary": summary, "records": records,
        "nine_line": {"source": str(proof_path.relative_to(ROOT)), "sha256": sha256(proof_path.read_bytes()).hexdigest(), **cases},
        "limitations": ["Relations for nonadjacent shores are compatibility records, not new lines.",
            "The input palette contains four symbols; path consistency does not prove global satisfiability.",
            "Unresolved domains can express genuinely different complete colorings, not only missing deductions.",
            "Extra pair counts use each unordered distinct shore pair once and do not count geometry spans repeatedly.",
            "No backtracking or global trial coloring supplies production names.",
            "Fresh seeds use the same generator families and are not representative of all plane maps."]}


def main():
    """Write an immutable report with enough geometry and hashes to reproduce."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; choose a new filename")
    report = run_validation()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, separators=(",", ":"))
        stream.write("\n")
    print(json.dumps({"maps": report["maps"], "runs": report["runs"], "summary": report["summary"]}, indent=2))


if __name__ == "__main__":
    main()

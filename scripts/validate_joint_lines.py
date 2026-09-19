"""Audit joint propagation on the preserved 255-map whole-line corpus.

Run both strict deduction and optional unused-symbol normalization under three
weights and ten tie schedules. Replay every removal independently; never call a
coloring search to supply a production name. Refuse to overwrite old reports.
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
from fourcolor.joint_lines import run_joint_lines
from fourcolor.line_names import audit_line_names
from fourcolor.weighted_lines import POLICIES
from fourcolor.whole_lines import build_whole_lines, propagate_candidates


VARIANTS = (("forward", None), ("reverse", None)) + tuple(
    ("random", seed) for seed in range(20260918, 20260926))
COUNTEREXAMPLE = "outputs/weighted-counterexample-candidate-2026-09-18-v2.json"


def independent_check(geometry: dict, result: dict) -> bool:
    """Replay proof steps from raw rotation, without the production propagator.

    Real primal edges witness inequalities, not colored points or guessed face
    adjacency. Nonempty terminal domains are also checked for complete rule
    closure. A closed multi-domain result is NOT a satisfiability certificate.
    """
    plane = PlaneMap(tuple((str(e["a"]), str(e["b"])) for e in geometry["edges"]),
                     {str(v): tuple(ds) for v, ds in enumerate(geometry["rotation"])})
    adjacency = set()
    neighbors = [set() for _ in plane.faces]
    for edge in range(len(plane.edges)):
        a, b = plane.shores(edge)
        if a != b:
            assert not geometry["edges"][edge].get("virtual", False)
            adjacency.add(tuple(sorted((a, b))))
            neighbors[a].add(b)
            neighbors[b].add(a)
    pairs = sorted(adjacency)

    def closed(domains):
        """Find an applicable deletion by a plain scan, independent of order."""
        for a, b in pairs:
            if len(domains[a]) == 1 and domains[a] & domains[b]:
                return False
            if len(domains[b]) == 1 and domains[b] & domains[a]:
                return False
            occupied = domains[a] | domains[b]
            if len(occupied) == 2 and any(domains[c] & occupied for c in neighbors[a] & neighbors[b]):
                return False
        return True

    domains = [set((1, 2, 3, 4)) for _ in plane.faces]
    for dart, values in result["anchors_by_dart"].items():
        domains[plane.face_of_dart[int(dart)]].intersection_update(values)
    assert [sorted(d) for d in domains] == result["initial_domains"]
    symmetry_count = 0
    for event in result["trace"]:
        assert all(domains), "no step may continue past a conflict"
        sources, target = event["sources"], event["target"]
        assert event["before"] == sorted(domains[target])
        assert event["source_domains"] == [sorted(domains[s]) for s in sources]
        witnesses = event["witness_edges"]
        rule = event["rule"]
        if rule == "singleton":
            assert len(sources) == len(witnesses) == 1
            source = sources[0]
            assert len(domains[source]) == 1
            assert set(plane.shores(witnesses[0])) == {source, target}
            assert source != target and tuple(sorted((source, target))) in adjacency
            forbidden = domains[source]
        elif rule == "pair-occupancy":
            assert len(sources) == 2 and len(witnesses) == 3
            a, b = sources
            assert len({a, b, target}) == 3
            for edge, endpoints in zip(witnesses, ((a, b), (a, target), (b, target))):
                assert set(plane.shores(edge)) == set(endpoints)
                assert tuple(sorted(endpoints)) in adjacency
            forbidden = domains[a] | domains[b]
            assert len(forbidden) == 2
        elif rule == "symbol-symmetry":
            assert result["symbol_symmetry"] and not sources and not witnesses
            assert closed(domains), "normalize only at a strict rule fixed point"
            used = {next(iter(d)) for d in domains if len(d) == 1}
            unused = {1, 2, 3, 4} - used
            assert len(unused) >= 2 and domains[target] == unused
            assert all(not (d & unused) or unused <= d for d in domains)
            assert event["used"] == sorted(used) and event["unused"] == sorted(unused)
            assert event["canonical_symbol"] == min(unused)
            assert plane.face_of_dart[event["dart"]] == target
            forbidden = unused - {min(unused)}
            symmetry_count += 1
        else:
            raise AssertionError("unknown trace rule")
        removed = domains[target] & forbidden
        assert removed and event["removed"] == sorted(removed)
        domains[target] -= removed
        assert event["after"] == sorted(domains[target])
    assert result["domains"] == [sorted(d) for d in domains]
    assert result["backtracks"] == result["non_symmetry_choices"] == 0
    assert result["choices"] == result["symmetry_choices"] == symmetry_count
    assert result["removed_candidates"] == sum(map(len, result["initial_domains"])) - sum(map(len, domains))
    expected = ("conflict" if not all(domains) else
                "solved" if all(len(d) == 1 for d in domains) else "underdetermined")
    assert result["status"] == expected
    if expected != "conflict":
        assert closed(domains)
    if expected == "solved":
        colors = [next(iter(d)) for d in domains]
        assert plane.check_coloring([c - 1 for c in colors])
        names = tuple((str(colors[a]), str(colors[b])) for a, b in
                      (plane.shores(e) for e in range(len(plane.edges))))
        assert audit_line_names(geometry["rotation"], names).status == "consistent"
    return True


def compact(result):
    """Keep terminal domains and deterministic trace hashes for every run."""
    keys = ("status", "domains", "anchors_by_dart", "policy", "tie_break", "seed",
            "symbol_symmetry", "choices", "symmetry_choices", "non_symmetry_choices",
            "backtracks", "removed_candidates", "random_draws")
    digest = lambda value: sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {key: result[key] for key in keys} | {
        "trace_sha256": digest(result["trace"]), "schedule_sha256": digest(result["schedule"]),
        "trace_rules": dict(Counter(e["rule"] for e in result["trace"])),
        "line_checks": len(result["schedule"]), "independently_checked": True}


def run_validation():
    """Compare all schedules, separating conditioned repair from fresh starts."""
    fixtures = json.loads(subprocess.run(
        ["node", "scripts/whole-line-fixtures.mjs", "--emit"], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", check=True).stdout)
    records = []
    for source in fixtures["records"]:
        model = build_whole_lines(source["geometry"])
        runs, strict_reference = [], None
        for symmetry in (False, True):
            for policy in POLICIES:
                for tie, seed in VARIANTS:
                    result = run_joint_lines(model, policy, tie, seed, symbol_symmetry=symmetry)
                    independent_check(source["geometry"], result)
                    if not symmetry:
                        if strict_reference is None:
                            strict_reference = result["domains"]
                        assert result["status"] != "conflict"
                        assert result["domains"] == strict_reference
                    # Isolate propagation strength at the SAME anchors. Do not
                    # compare two unrelated arbitrary representative choices.
                    anchors = dict(result["anchors_by_dart"])
                    for event in result["trace"]:
                        if event["rule"] == "symbol-symmetry":
                            anchors[event["dart"]] = [event["canonical_symbol"]]
                    baseline = propagate_candidates(model, anchors)
                    assert all(set(new) <= set(old) for new, old in zip(result["domains"], baseline["domains"]))
                    saved = compact(result)
                    saved["extra_removals_vs_singleton_same_anchors"] = (
                        sum(map(len, baseline["domains"])) - sum(map(len, result["domains"])))
                    saved["singleton_status_same_anchors"] = baseline["status"]
                    runs.append(saved)
        records.append({key: source[key] for key in ("id", "family", "seed", "document", "geometry")} | {"runs": runs})

    proof = json.loads((ROOT / COUNTEREXAMPLE).read_text(encoding="utf-8"))["proof"]
    model = build_whole_lines(proof["geometry"])
    initial = {int(d): values for d, values in proof["same_state"]["anchors_by_dart"].items()}
    conditioned, fresh = [], []
    for policy in POLICIES:
        for tie, seed in VARIANTS:
            repaired = run_joint_lines(model, policy, tie, seed, anchors=initial)
            independent_check(proof["geometry"], repaired)
            assert repaired["domains"] == [[c] for c in proof["certificate"]]
            conditioned.append(repaired)
            for symmetry in (False, True):
                result = run_joint_lines(model, policy, tie, seed, symbol_symmetry=symmetry)
                independent_check(proof["geometry"], result)
                fresh.append(result)

    summary = []
    for symmetry in (False, True):
        for policy in POLICIES:
            variants = []
            for tie, seed in VARIANTS:
                selected = [(row, next(r for r in row["runs"] if r["policy"] == policy
                             and r["symbol_symmetry"] == symmetry and r["tie_break"] == tie and r["seed"] == seed))
                            for row in records]
                counts = Counter(r["status"] for _, r in selected)
                variants.append({"tie_break": tie, "seed": seed,
                    **{name: counts[name] for name in ("solved", "underdetermined", "conflict")},
                    "extra_removals_vs_singleton_same_anchors": sum(r["extra_removals_vs_singleton_same_anchors"] for _, r in selected),
                    "solved_map_ids": [row["id"] for row, r in selected if r["status"] == "solved"]})
            summary.append({"symbol_symmetry": symmetry, "policy": policy, "variants": variants})
    hashes = dict(fixtures["source_sha256"])
    for source in ("fourcolor/joint_lines.py", "fourcolor/whole_lines.py", "fourcolor/weighted_lines.py",
                   "fourcolor/embedding.py", "fourcolor/line_names.py", "scripts/validate_joint_lines.py", COUNTEREXAMPLE):
        hashes[source] = sha256((ROOT / source).read_bytes()).hexdigest()
    return {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "maps": len(records), "runs": len(records) * 2 * len(POLICIES) * len(VARIANTS),
            "family_counts": dict(Counter(row["family"] for row in records)),
            "geometry_seed_range": fixtures["seed_range"], "tie_seeds": list(range(20260918, 20260926)),
            "strict_closure_order_invariance_checked": True,
            "source_sha256": hashes, "summary": summary, "records": records,
            "nine_line_case": {"source": COUNTEREXAMPLE, "geometry": proof["geometry"],
                "conditioned_initial_anchors": initial, "expected_certificate": proof["certificate"],
                "conditioned_runs": conditioned, "fresh_frame_runs": fresh},
            "limitations": [
                "Four candidate symbols are supplied, never deduced from these rules.",
                "Underdetermined does not imply satisfiable or uncolorable.",
                "The nine-line repair uses stated previous anchors; fresh-frame results are separate.",
                "Strict deductions preserve every completion; optional symmetry preserves existence modulo symbol permutation.",
                "Strict nonconflict closure is order-independent; symmetry choices need not be.",
                "Rule scans are not exhaustive coloring search; no trial naming or fallback solver is used.",
                "Corpus is finite: 160 guillotine, 40 nested-rings-and-bridges, 40 boundary-fan generated maps plus 15 gallery/targeted maps; not all planar maps."]}


def main():
    """Write a fresh reproducible report, never replace an earlier experiment."""
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
    # Keep console output compact; all 60 detailed variant records are saved.
    summary = [{"symbol_symmetry": row["symbol_symmetry"], "policy": row["policy"],
                "status_counts_observed": sorted({(r["solved"], r["underdetermined"], r["conflict"])
                                                  for r in row["variants"]}),
                "extra_removals_range": [min(r["extra_removals_vs_singleton_same_anchors"] for r in row["variants"]),
                                         max(r["extra_removals_vs_singleton_same_anchors"] for r in row["variants"])]}
               for row in report["summary"]]
    print(json.dumps({"maps": report["maps"], "runs": report["runs"], "summary": summary}, indent=2))


if __name__ == "__main__":
    main()

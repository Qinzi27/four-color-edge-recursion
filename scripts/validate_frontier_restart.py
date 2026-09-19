"""Compare fresh frontier policies on unchanged drawings, without fallback.

The existing restart inventory supplies every geometric prefix, including
prefixes after a failed naming. Forty declared new seeds are an optional,
separate cohort, not independent repetitions of the old prefix sample.
Successful names are checked directly; conflict claims are re-derived from
committed anchors by an independent, small-clique Hall checker. No assignment
search is called by this runner, and an uncertified conflict stops the audit.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.embedding import PlaneMap
from fourcolor.frontier_restart import POLICIES, restart_frontier_names
from fourcolor.global_restart import restart_line_names
from fourcolor.line_names import audit_line_names
from scripts.validate_global_restart import (
    build_corpus, compact_result, digest, export_geometries,
    restart_inventory, write_report,
)

BASELINE = "closed-support"
EXISTING = "existing-corpus"
HELDOUT = "new-seeds-20261901-20261940"
HELDOUT_SEEDS = tuple(range(20261901, 20261941))
DEFAULT_BASELINE = ROOT / "outputs/global-restart-all-2026-09-18-v2.json.gz"


def json_value(value):
    """Normalize integer JSON object keys before comparing stored reports."""
    return json.loads(json.dumps(value, ensure_ascii=False))


def file_sha(path):
    """Hash evidence bytes, including the original compressed report bytes."""
    return sha256(path.read_bytes()).hexdigest()


def read_json(path):
    """Read a plain or compressed report without editing its evidence."""
    payload = path.read_bytes()
    return json.loads(gzip.decompress(payload) if path.suffix == ".gz" else payload)


def independent_geometry(geometry):
    """Rebuild shore orbits and true inequalities independently of scheduling.

    Bridge darts share one shore and are NOT inequality edges. Virtual edges
    must be such bridges; otherwise the geometry contract itself has changed.
    """
    plane = PlaneMap(tuple((str(e["a"]), str(e["b"])) for e in geometry["edges"]),
                     {str(v): tuple(ds) for v, ds in enumerate(geometry["rotation"])})
    if tuple(geometry["faceOfDart"]) != plane.face_of_dart:
        raise AssertionError("Node/Python dart-side identities disagree")
    if {frozenset(f) for f in geometry["faces"]} != {frozenset(f) for f in plane.faces}:
        raise AssertionError("Node/Python side orbits disagree")
    outer = geometry["outerFace"]
    if type(outer) is not int or not 0 <= outer < len(plane.faces):
        raise AssertionError("missing or invalid exterior side identity")
    adjacent = [set() for _ in plane.faces]
    for i, edge in enumerate(geometry["edges"]):
        a, b = plane.shores(i)
        if edge.get("virtual") and a != b:
            raise AssertionError("virtual connector cannot separate two shores")
        if a != b:
            adjacent[a].add(b)
            adjacent[b].add(a)
    return plane, adjacent


def anchored_domains(plane, anchors):
    """Use ONLY final declared commitments, never production-filtered domains."""
    domains = [set(range(1, 5)) for _ in plane.faces]
    for raw_dart, allowed in anchors.items():
        dart = int(raw_dart)
        if str(dart) != str(raw_dart) or not 0 <= dart < len(plane.face_of_dart):
            raise AssertionError("invalid anchor dart")
        if not isinstance(allowed, (tuple, list)) or any(
                type(c) is not int or c not in (1, 2, 3, 4) for c in allowed):
            raise AssertionError("invalid anchor symbols")
        domains[plane.face_of_dart[dart]].intersection_update(allowed)
    return domains


def complete_subsets(adjacent):
    """Enumerate graph cliques of size 2..4 with common-neighbor witnesses.

    This recursive intersection enumerates constraint sets, never assignments.
    A set of shores around an arbitrary primal junction is not assumed to be
    a clique. Actual pairwise shared boundaries are necessary throughout.
    """
    subsets = []

    def extend(prefix, candidates):
        """Keep each increasing clique once, rather than copying solver lists."""
        for index, vertex in enumerate(candidates):
            chosen = prefix + (vertex,)
            if len(chosen) >= 2:
                common = set.intersection(*(adjacent[v] for v in chosen))
                subsets.append((chosen, tuple(sorted(common))))
            if len(chosen) < 4:
                extend(chosen, [v for v in candidates[index + 1:] if v in adjacent[vertex]])

    extend((), list(range(len(adjacent))))
    return subsets


def independent_hall(domains, adjacent):
    """Certify a necessary contradiction using fixed-point graph constraints.

    In a complete subset S, |union D(S)| < |S| is impossible. Equality reserves
    that union against every common neighbor. This derives the same sound
    mathematical conditions without reading the producer's cliques, trace,
    narrowed domains, conflict explanation, or propagation implementation.
    A nonempty fixed point is UNKNOWN, not a promise of colorability.
    """
    work = [set(d) for d in domains]
    subsets = complete_subsets(adjacent)
    reductions = 0
    rounds = 0
    while True:
        rounds += 1
        empty = next((v for v, d in enumerate(work) if not d), None)
        if empty is not None:
            return {"certified": True, "rule": "empty-domain", "side": empty,
                    "rounds": rounds, "reductions": reductions,
                    "domains_sha256": digest([sorted(d) for d in work])}
        changed = False
        # Scan all singleton constraints independently of the producer's queue.
        for a, neighbors in enumerate(adjacent):
            if len(work[a]) != 1:
                continue
            for b in sorted(neighbors):
                removed = work[b] & work[a]
                if removed:
                    work[b] -= removed
                    changed = True
                    reductions += len(removed)
                    if not work[b]:
                        return {"certified": True, "rule": "singleton-empty-domain",
                                "from_side": a, "side": b, "rounds": rounds,
                                "reductions": reductions,
                                "domains_sha256": digest([sorted(d) for d in work])}
        for subset, common in subsets:
            union = set().union(*(work[v] for v in subset))
            if len(union) < len(subset):
                return {"certified": True, "rule": "clique-hall-deficiency",
                        "subset": list(subset), "union": sorted(union),
                        "subset_domains": [sorted(work[v]) for v in subset],
                        "rounds": rounds, "reductions": reductions,
                        "domains_sha256": digest([sorted(d) for d in work])}
            if len(union) == len(subset):
                for other in common:
                    removed = work[other] & union
                    if removed:
                        work[other] -= removed
                        changed = True
                        reductions += len(removed)
                        if not work[other]:
                            return {"certified": True, "rule": "clique-hall-reservation-empty",
                                    "subset": list(subset), "union": sorted(union),
                                    "side": other, "rounds": rounds, "reductions": reductions,
                                    "domains_sha256": digest([sorted(d) for d in work])}
        if not changed:
            return {"certified": False, "rule": "nonempty-fixed-point-is-inconclusive",
                    "rounds": rounds, "reductions": reductions,
                    "domains_sha256": digest([sorted(d) for d in work])}


def verify_result(geometry, result, context=None):
    """Directly validate a success, or separately certify a claimed conflict.

    Success does NOT require reproducing the producer's propagation strength:
    a complete proper assignment and its line names are checked on their own.
    The finite Hall check on failures does not rescue the naming algorithm.
    """
    plane, adjacent = independent_geometry(geometry) if context is None else context
    if result["backtracks"] != 0 or result["old_colors_read"] is not False:
        raise AssertionError("no-backtracking/fresh-restart contract violated")
    if result["local_budget"] is not None:
        raise AssertionError("fresh restart must not inherit a local repair budget")
    anchored = anchored_domains(plane, result["anchors_by_dart"])
    if result["status"] == "conflict":
        if result.get("colors") is not None:
            raise AssertionError("a conflict must not claim a completed coloring")
        certificate = independent_hall(anchored, adjacent)
        return {"passed": certificate["certified"], "method": "independent-clique-hall",
                "claim": "committed-anchors-have-no-extension", "certificate": certificate}
    if result["status"] != "solved":
        raise AssertionError("unexpected incomplete algorithm status")
    colors = result["colors"]
    if not isinstance(colors, list) or len(colors) != len(plane.faces) or any(
            type(c) is not int or c not in (1, 2, 3, 4) for c in colors):
        raise AssertionError("incomplete or invalid four-name assignment")
    if colors[geometry["outerFace"]] != 1:
        raise AssertionError("the exterior shore must retain root name 1")
    if result["domains"] != [[c] for c in colors]:
        raise AssertionError("reported singleton domains and complete colors disagree")
    if any(colors[v] not in allowed for v, allowed in enumerate(anchored)):
        raise AssertionError("completed names violate a committed anchor")
    if not plane.check_coloring([c - 1 for c in colors]):
        raise AssertionError("opposite actual shores share a color")
    names = tuple((str(colors[a]), str(colors[b]))
                  for a, b in (plane.shores(i) for i in range(len(plane.edges))))
    audit = audit_line_names(geometry["rotation"], names)
    if audit.status != "consistent":
        raise AssertionError("complete ordered line names failed independent orbit audit")
    return {"passed": True, "method": "direct-coloring-and-line-orbits",
            "claim": "complete-proper-four-names", "line_names_sha256": digest(names),
            "shore_count": len(colors), "edge_count": len(names)}


def compact_frontier(result, verification):
    """Retain reproducible names and hashes, without huge repeated traces."""
    fields = ("status", "policy", "domains", "anchors_by_dart", "colors", "choices",
              "backtracks", "old_colors_read", "local_budget")
    compact = {key: result[key] for key in fields}
    compact.update({"trace_sha256": digest(result["trace"]),
                    "independent_check_passed": verification["passed"],
                    "verification": verification})
    if "propagation_trace" in result:
        compact["propagation_trace_sha256"] = digest(result["propagation_trace"])
    for key in ("hall_conflict", "hall_derivation_events_including_recomputations"):
        if key in result:
            compact[key] = result[key]
    return compact


def heldout_histories():
    """Generate the predeclared 40 seeds, once; never select by naming success."""
    source = """
import {generatedPaths} from './scripts/construction-experiments.mjs';
const rows=[];
for(let seed=20261901;seed<=20261940;seed++)
  rows.push({seed,paths:generatedPaths('guillotine',seed)});
process.stdout.write(JSON.stringify(rows));
"""
    completed = subprocess.run(["node", "--input-type=module", "-e", source], cwd=ROOT,
                               capture_output=True, text=True, encoding="utf-8", check=True)
    generated = json.loads(completed.stdout)
    if [r["seed"] for r in generated] != list(HELDOUT_SEEDS):
        raise AssertionError("heldout seed declaration changed")
    rows = []
    for row in generated:
        if len(row["paths"]) != 24:
            raise AssertionError("heldout source did not produce 24 cuts")
        key = "heldout-guillotine-" + str(row["seed"])
        result = {"key": key, "family": "guillotine", "cohort": HELDOUT,
                  "seed": row["seed"], "paths": row["paths"], "initial_state": None,
                  "initial_document": {"frame": {"width": 900, "height": 600}, "strokes": []},
                  "max_old_sides": 3,
                  "aliases": [{"key": key, "family": "guillotine", "cohort": HELDOUT,
                               "seed": row["seed"], "kind": "predeclared-generator-history",
                               "source": "scripts/construction-experiments.mjs::generatedPaths"}]}
        result["history_sha256"] = digest({field: result.get(field) for field in (
            "initial_state", "initial_document", "initial_names", "paths", "max_old_sides")})
        rows.append(result)
    return rows


def grouped_inventory(corpus, include_heldout):
    """Share geometry cache, but preserve old/new history denominators and aliases."""
    existing_keys = {row["key"] for row in corpus["histories"]}
    added = heldout_histories() if include_heldout else []
    if existing_keys & {row["key"] for row in added}:
        raise AssertionError("heldout history key collides with old history")
    combined = {**corpus, "histories": corpus["histories"] + added}
    records, histories, statics = restart_inventory(combined)
    groups = {row["key"]: EXISTING if row["key"] in existing_keys else HELDOUT for row in histories}
    for row in histories:
        row["cohort"] = groups[row["key"]]
    for row in statics:
        row["cohort"] = EXISTING
    for row in records:
        row["cohorts"] = sorted({EXISTING if alias["kind"] == "static" else groups[alias["history"]]
                                 for alias in row["aliases"]})
    return records, histories, statics


def paired_counts(pairs):
    """Report both improvements and regressions, never just the net change."""
    counts = Counter({"both_solved": 0, "improved": 0, "regressed": 0, "both_not_solved": 0})
    for baseline, candidate in pairs:
        counts["both_solved" if baseline and candidate else
               "improved" if candidate else "regressed" if baseline else "both_not_solved"] += 1
    return dict(counts)


def summarize_frontier(records, histories, statics, policies):
    """Keep per-prefix recovery, complete-history success, and final success apart."""
    by_key = {row["key"]: row for row in records}
    history_results = []
    history_index = {}
    for policy in policies:
        for row in histories:
            statuses = [by_key[key]["runs"][policy]["status"] for key in row["prefix_keys"]]
            failures = [i for i, status in enumerate(statuses) if status != "solved"]
            entry = {"key": row["key"], "policy": policy, "family": row["family"], "cohort": row["cohort"],
                     "statuses": statuses, "all_prefixes_solved": not failures,
                     "first_failed_prefix": failures[0] if failures else None,
                     "solved_again_after_failure": [i for i in range(1, len(statuses))
                                                    if statuses[i] == "solved" and statuses[i - 1] != "solved"],
                     "final_status": statuses[-1]}
            history_results.append(entry)
            history_index[(row["key"], policy)] = entry
    groups = ["combined"] + sorted({g for row in records for g in row["cohorts"]})
    summary, paired = [], []
    for group in groups:
        drawings = [r for r in records if group == "combined" or group in r["cohorts"]]
        sequences = [r for r in histories if group == "combined" or r["cohort"] == group]
        static_group = [r for r in statics if group == "combined" or r["cohort"] == group]
        for policy in policies:
            rows = [history_index[(r["key"], policy)] for r in sequences]
            families = {}
            for row in rows:
                family = families.setdefault(row["family"], {"histories": 0, "all_prefixes_solved": 0,
                                                             "final_status": Counter()})
                family["histories"] += 1
                family["all_prefixes_solved"] += row["all_prefixes_solved"]
                family["final_status"][row["final_status"]] += 1
            summary.append({"cohort": group, "policy": policy, "distinct_drawing_count": len(drawings),
                            "distinct_drawings": dict(Counter(r["runs"][policy]["status"] for r in drawings)),
                            "verification": dict(Counter(r["runs"][policy].get("verification", {}).get(
                                "method", "not-run") for r in drawings)),
                            "runtime_seconds": sum(r["runs"][policy].get("runtime_seconds", 0.0) for r in drawings),
                            "hall_active_drawings": sum(r["runs"][policy].get(
                                "hall_derivation_events_including_recomputations", 0) > 0 for r in drawings),
                            "hall_derivation_events_including_recomputations": sum(r["runs"][policy].get(
                                "hall_derivation_events_including_recomputations", 0) for r in drawings),
                            "hall_explicit_deficiency_drawings": sum(bool(r["runs"][policy].get("hall_conflict")) for r in drawings),
                            "history_count": len(rows),
                            "history_prefix_references": sum(len(r["prefix_keys"]) for r in sequences),
                            "all_prefixes": {"all_solved": sum(r["all_prefixes_solved"] for r in rows),
                                             "has_failure": sum(not r["all_prefixes_solved"] for r in rows)},
                            "history_final_status": dict(Counter(r["final_status"] for r in rows)),
                            "history_families": families, "static_count": len(static_group),
                            "static_status": dict(Counter(by_key[r["geometry_key"]]["runs"][policy]["status"]
                                                          for r in static_group))})
            if policy == BASELINE:
                continue
            paired.append({"cohort": group, "baseline": BASELINE, "candidate": policy,
                           "distinct_drawings": paired_counts((r["runs"][BASELINE]["status"] == "solved",
                                                               r["runs"][policy]["status"] == "solved")
                                                              for r in drawings),
                           "all_history_prefixes": paired_counts((history_index[(r["key"], BASELINE)]["all_prefixes_solved"],
                                                                 history_index[(r["key"], policy)]["all_prefixes_solved"])
                                                                for r in sequences),
                           "history_final": paired_counts((history_index[(r["key"], BASELINE)]["final_status"] == "solved",
                                                           history_index[(r["key"], policy)]["final_status"] == "solved")
                                                          for r in sequences),
                           "static_final": paired_counts((by_key[r["geometry_key"]]["runs"][BASELINE]["status"] == "solved",
                                                          by_key[r["geometry_key"]]["runs"][policy]["status"] == "solved")
                                                         for r in static_group)})
    return summary, history_results, paired


def build_report(limit=None, include_heldout=False, baseline_path=DEFAULT_BASELINE):
    """Run fresh names independently for every policy, preserving every outcome."""
    baseline_path = Path(baseline_path)
    baseline_sha = file_sha(baseline_path)
    previous = read_json(baseline_path)
    if previous.get("smoke_limit") is not None:
        raise AssertionError("baseline must be the complete frozen report")
    previous_by_key = {row["key"]: row for row in previous["drawings"]}
    for path, expected in previous["source_sha256"].items():
        if file_sha(ROOT / path) != expected:
            raise AssertionError("frozen baseline source changed: " + path)
    corpus = build_corpus()
    sources = dict(corpus["source_sha256"])
    files = set(previous["source_sha256"]) | {
        "fourcolor/frontier_restart.py", "scripts/validate_frontier_restart.py"}
    sources.update({path: file_sha(ROOT / path) for path in sorted(files)})
    records, histories, statics = grouped_inventory(corpus, include_heldout)
    original_scope = {"distinct_drawings": len(records), "histories": len(histories),
                      "history_prefix_references": sum(len(r["prefix_keys"]) for r in histories),
                      "static_references": len(statics)}
    existing = {r["key"] for r in records if EXISTING in r["cohorts"]}
    if existing != set(previous_by_key):
        raise AssertionError("old/new existing corpus geometry keys disagree")
    if limit is not None:
        records = records[:limit]
        available = {r["key"] for r in records}
        histories = [r for r in histories if set(r["prefix_keys"]) <= available]
        statics = [r for r in statics if r["geometry_key"] in available]
    policies = (BASELINE,) + tuple(POLICIES)
    checks, baseline_matches = 0, 0
    for start in range(0, len(records), 100):
        chunk = records[start:start + 100]
        for record, exported in zip(chunk, export_geometries(chunk)):
            if record["key"] != exported["key"]:
                raise AssertionError("geometry export order changed")
            record["geometry_status"], record["runs"] = exported["status"], {}
            if exported["status"] != "geometry_ok":
                record["errors"] = exported["errors"]
                record["runs"] = {p: {"status": "geometry_error"} for p in policies}
                continue
            geometry = exported["geometry"]
            context = independent_geometry(geometry)
            record.update({"geometry_sha256": digest(geometry), "topology_checked": True,
                           "face_count": len(context[0].faces),
                           "real_bridge_count": len(geometry["real_bridge_edge_ids"]),
                           "virtual_connector_count": len(geometry["virtual_bridge_edge_ids"])})
            if record["key"] in previous_by_key and record["geometry_sha256"] != previous_by_key[record["key"]]["geometry_sha256"]:
                raise AssertionError("frozen baseline geometry hash changed")
            for policy in policies:
                began = perf_counter()
                result = (restart_line_names(geometry, BASELINE) if policy == BASELINE
                          else restart_frontier_names(geometry, policy))
                elapsed = perf_counter() - began
                verification = verify_result(geometry, result, context)
                if not verification["passed"]:
                    raise AssertionError({"geometry_key": record["key"], "policy": policy,
                                          "reason": "uncertified conflict; audit stopped, no fallback",
                                          "verification": verification})
                record["runs"][policy] = compact_frontier(result, verification)
                record["runs"][policy]["runtime_seconds"] = elapsed
                checks += 1
                if policy == BASELINE and record["key"] in previous_by_key:
                    rerun = json_value(compact_result(result))
                    old = previous_by_key[record["key"]]["runs"][BASELINE]
                    fields = ("status", "domains", "anchors_by_dart", "colors", "trace_sha256")
                    if any(rerun[field] != old[field] for field in fields):
                        raise AssertionError("baseline result drift: " + record["key"])
                    baseline_matches += 1
        print(json.dumps({"drawings_checked": min(start + 100, len(records)), "total": len(records),
                          "independent_checks": checks, "baseline_matches": baseline_matches}), flush=True)
    summary, history_results, paired = summarize_frontier(records, histories, statics, policies)
    end_sources = {path: file_sha(ROOT / path) for path in sources}
    if sources != end_sources or file_sha(baseline_path) != baseline_sha:
        raise AssertionError("source or baseline evidence changed during experiment")
    return {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "experiment": "Independent no-fallback frontier naming at every geometric prefix",
            "smoke_limit": limit, "full_corpus_run": limit is None,
            "source_sha256": sources, "source_sha256_end": end_sources,
            "source_hashes_unchanged": True,
            "baseline_evidence": {"filename": baseline_path.name, "sha256": baseline_sha,
                                  "sources_matched": len(previous["source_sha256"]),
                                  "drawings_reproduced": baseline_matches,
                                  "fields": ["geometry_sha256", "status", "domains", "anchors_by_dart", "colors", "trace_sha256"]},
            "original_corpus_summary": corpus["summary"], "declared_scope": original_scope,
            "heldout_declaration": {"included": include_heldout, "seeds": list(HELDOUT_SEEDS),
                                    "family": "guillotine", "cuts_per_history": 24,
                                    "selection": "Consecutive seeds declared before outcomes; no filtering or retuning."},
            "independent_checks": checks, "policies": list(policies), "drawings": records,
            "histories": histories, "static_inputs": statics, "history_results": history_results,
            "summary": summary, "paired_comparisons": paired,
            "limits": ["Four is an input palette, not a proved upper bound derived by these algorithms.",
                       "No policy fallback, assignment enumeration, oracle repair, or earlier-name reuse.",
                       "A certified conflict concerns current greedy anchors, not impossibility of four-coloring the map.",
                       "Hall checks use genuine complete shore-adjacency subsets, not arbitrary primal cycles.",
                       "All-prefix completion and final-drawing success have separate denominators.",
                       "A common drawing is cached once; cohort drawing totals can overlap and are not additive.",
                       "Related prefixes and old/new samples from one generator are not independent statistical samples.",
                       "Existing corpus is exploratory; new declared seeds are same-generator heldout checks, not all planar maps.",
                       "Runtime seconds describe this single sequential machine run, excluding verification; they are not a controlled speed benchmark.",
                       "Hall derivation event totals include repeated derivations after each fresh commitment, not distinct deductions.",
                       "Geometry keys normalize stroke direction/order only, not collinear union or graph isomorphism.",
                       "Unsupported/geometry-error results remain explicit and are never counted as solved."]}


def main():
    """Write new portable reports exclusively; do not replace earlier evidence."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--include-heldout", action="store_true")
    parser.add_argument("--limit", type=int, help="Positive drawing limit for explicitly labeled smoke only")
    args = parser.parse_args()
    if args.output.exists() or args.summary.exists() or args.output.resolve() == args.summary.resolve():
        parser.error("choose two distinct new output paths")
    if args.limit is not None and args.limit < 1:
        parser.error("smoke limit must be positive")
    report = build_report(args.limit, args.include_heldout, args.baseline)
    write_report(args.output, report)
    keys = ("experiment", "smoke_limit", "full_corpus_run", "source_sha256", "source_sha256_end",
            "source_hashes_unchanged", "baseline_evidence", "original_corpus_summary", "declared_scope",
            "heldout_declaration", "independent_checks", "policies", "summary", "paired_comparisons", "limits")
    small = {key: report[key] for key in keys}
    small.update({"input": {"filename": args.output.name, "sha256": file_sha(args.output)},
                  "distinct_drawings": len(report["drawings"]),
                  "history_prefix_references": sum(len(r["prefix_keys"]) for r in report["histories"]),
                  "static_references": len(report["static_inputs"])})
    write_report(args.summary, small)
    print(json.dumps(small, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

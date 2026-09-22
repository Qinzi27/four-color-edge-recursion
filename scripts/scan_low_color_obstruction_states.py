"""Scan frozen guarded histories for a triangle-bipyramid domain obstruction.

This read-only analysis reconstructs true NEQ edges from saved geometric shores.
It neither runs a coloring producer nor asks an oracle. Only initialization and
event.after_phase are persistent states: a rejected trial is not reachable main
state, while an accepted trial is. The two ordinary initialization modes are
scanned; old externally locked diagnostic inputs are explicitly excluded.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from itertools import combinations
from pathlib import Path
from time import perf_counter
import gzip
import json
import platform


ROOT = Path(__file__).resolve().parents[1]
MODES = ("one-bounded-anchor", "legacy-frame-anchors")
MANIFEST_SHA256 = "8368881a0f963139e300ebf0b076548db1b181db02d05e68e12a92d59f7ad15c"
REPORT_SHA256 = "b882d137b5e0b1513ba5732fe6867a4174110c68d50a49709dd2d774f2b6de58"


def require(condition, message):
    """Reject malformed evidence even when Python assertions are disabled."""
    if not condition:
        raise ValueError(message)


def file_hash(path):
    """Hash the actual compressed bytes without loading large files at once."""
    result = sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            result.update(block)
    return result.hexdigest()


def digest(value):
    """Match the frozen portable JSON digest with no production-code import."""
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode("utf-8")).hexdigest()


def read_bound_json(path, expected):
    """Verify exactly the bytes that will be decoded, closing a read/hash race."""
    data = Path(path).read_bytes()
    require(sha256(data).hexdigest() == expected, f"byte hash differs: {Path(path).name}")
    return json.loads(gzip.decompress(data) if Path(path).suffix == ".gz" else data)


def project_path(name):
    """Resolve saved relative references within the project only."""
    require(isinstance(name, str) and not Path(name).is_absolute(), "nonportable saved path")
    path = (ROOT / name).resolve()
    path.relative_to(ROOT)
    return path


def portable(path):
    """Keep machine-specific absolute paths out of published results."""
    return Path(path).resolve().relative_to(ROOT).as_posix()


def check_hashes(hashes):
    """Verify the complete frozen source or input dependency list."""
    require(isinstance(hashes, dict) and hashes, "missing dependency hashes")
    for name, expected in hashes.items():
        require(file_hash(project_path(name)) == expected, f"dependency changed: {name}")


def raw_graph(geometry):
    """Use original real edge shores, excluding virtual links and true bridges.

    Saved Node planarization and global face identities are shared inputs; this
    function does not recompute geometric intersections or face walks.
    """
    n = len(geometry["faces"])
    face_of = geometry["faceOfDart"]
    require(len(face_of) == 2 * len(geometry["edges"]), "incomplete edge shores")
    edges, lines = set(), []
    for i, edge in enumerate(geometry["edges"]):
        if edge.get("virtual", False):
            continue
        a, b = face_of[2 * i:2 * i + 2]
        require(type(a) is int and type(b) is int and 0 <= a < n and 0 <= b < n,
                "invalid global face identity")
        lines.append({"id": f"E{i}", "left": f"S{a}", "right": f"S{b}",
                      "kind": "bridge" if a == b else "separator"})
        if a != b:
            edges.add(tuple(sorted((a, b))))
    return [f"S{i}" for i in range(n)], sorted(edges), lines


def triangle_bipyramids(n, edges):
    """Enumerate every induced K5 minus the apex edge, once per vertex set.

    For each nonadjacent apex pair, each three-clique in its common neighborhood
    supplies a rim. Additional edges to outside vertices remain unrestricted.
    """
    neighbors = [set() for _ in range(n)]
    for a, b in edges:
        require(type(a) is int and type(b) is int and 0 <= a < b < n,
                "raw edges must be sorted distinct vertex pairs")
        neighbors[a].add(b)
        neighbors[b].add(a)
    found = []
    for a, e in combinations(range(n), 2):
        if e in neighbors[a]:
            continue
        for rim in combinations(sorted(neighbors[a] & neighbors[e]), 3):
            if all(v in neighbors[u] for u, v in combinations(rim, 2)):
                found.append({"apices": [a, e], "rim": list(rim)})
    return found


def classify_domains(first, second):
    """Classify oriented apex domains under any permutation of four names.

    The strict apex signature has sizes 2/3, one shared name t, and the other
    first-apex name b below t. Rim domains are separately retained by the caller;
    matching this signature does not assert the complete external template.
    """
    a, e = set(first), set(second)
    require(a <= {1, 2, 3, 4} and e <= {1, 2, 3, 4}, "name outside palette")
    intersection = a & e
    strict = (len(a) == 2 and len(e) == 3 and len(intersection) == 1
              and min(a - intersection) < next(iter(intersection)))
    proper_both = bool(intersection) and intersection < a and intersection < e
    return {"intersection": sorted(intersection), "strict_apex_signature": strict,
            "proper_both": proper_both,
            "lowest_excluded_by_other": bool(a) and min(a) not in e}


def persistent_phases(result):
    """Return actual phase indices and their outgoing event, validating linkage."""
    phases, events = result["phases"], result["events"]
    require(result["probe"] is True and bool(phases), "guarded phases required")
    current, retained, allocated = 0, [], {0}
    for number, event in enumerate(events):
        require(event["before_phase"] == current, "disconnected event chain")
        retained.append((current, number))
        trial, after = event["trial_phase"], event["after_phase"]
        require(type(trial) is int and type(after) is int and
                current < trial < len(phases) and 0 <= after < len(phases), "bad phase reference")
        require(trial not in allocated and phases[trial]["kind"] == "trial", "reused/nontrial probe")
        allocated.add(trial)
        if event["kind"] == "reject":
            require(after > trial and after not in allocated and phases[after]["kind"] == "main"
                    and phases[trial]["outcome"]["status"] == "conflict", "rejection lacks failed trial")
            allocated.add(after)
        else:
            require(event["kind"] == "commit" and after == trial and
                    phases[trial]["outcome"]["status"] != "conflict", "invalid accepted trial")
        current = after
    require(current == result["final_phase"], "wrong final phase")
    require(allocated == set(range(len(phases))), "unreferenced or multiply used phase")
    retained.append((current, None))
    return retained


def scan_run(result, motifs, evidence_prefix, detail_limit=100):
    """Scan every persistent state, returning complete counts and bounded details."""
    sides = result["original_input"]["sides"]
    phases = persistent_phases(result)
    counts = Counter({"runs": 1, "persistent_phases": len(phases),
                      "motif_phase_pairs": len(motifs) * len(phases),
                      "strict_apex_matches": 0, "strict_full_rim_matches": 0,
                      "proper_intersection_matches": 0, "selected_bad_minimum_attempts": 0,
                      "refuted_bad_minimum_attempts": 0, "inconclusive_bad_commits": 0})
    matches = {name: [] for name in ("strict", "proper_intersection", "bad_minimum", "inconclusive_commit")}
    motif_statistics = []
    for motif_number, motif in enumerate(motifs):
        a, e = motif["apices"]
        signatures = Counter()
        for phase_number, next_event_number in phases:
            phase = result["phases"][phase_number]
            outcome = phase["outcome"]
            domains = outcome["domains"]
            require(outcome["side_order"] == sides and len(domains) == len(sides), "phase side identities differ")
            require(all(domain == sorted(set(domain)) for domain in domains), "noncanonical phase domain")
            da, de = domains[a], domains[e]
            intersection = sorted(set(da) & set(de))
            signature = json.dumps([da, de, intersection, outcome["status"]], separators=(",", ":"))
            signatures[signature] += 1
            event = result["events"][next_event_number] if next_event_number is not None else None
            for selected, other in ((a, e), (e, a)):
                flags = classify_domains(domains[selected], domains[other])
                strict, proper = flags["strict_apex_signature"], flags["proper_both"]
                # Count proper intersections once per unordered motif and phase.
                if proper and selected == a:
                    counts["proper_intersection_matches"] += 1
                if strict:
                    counts["strict_apex_matches"] += 1
                    if all(domains[i] == [1, 2, 3, 4] for i in motif["rim"]):
                        counts["strict_full_rim_matches"] += 1
                selected_now = event is not None and event["side"] == sides[selected]
                bad_minimum = proper and flags["lowest_excluded_by_other"] and selected_now
                inconclusive = False
                if bad_minimum:
                    require(event["symbol"] == min(domains[selected]), "selected symbol is not minimum")
                    counts["selected_bad_minimum_attempts"] += 1
                    if event["kind"] == "reject":
                        counts["refuted_bad_minimum_attempts"] += 1
                    trial = result["phases"][event["trial_phase"]]["outcome"]
                    inconclusive = (event["kind"] == "commit" and
                                    event["extension_claim"] == "inconclusive" and
                                    trial["status"] == "underdetermined")
                    if inconclusive:
                        counts["inconclusive_bad_commits"] += 1
                categories = (["strict"] if strict else []) + (
                    ["proper_intersection"] if proper and selected == a else []) + (
                    ["bad_minimum"] if bad_minimum else []) + (["inconclusive_commit"] if inconclusive else [])
                if not categories:
                    continue
                evidence = {**evidence_prefix, "phase": phase_number, "next_event": next_event_number,
                            "motif_index": motif_number, "selected_apex": sides[selected],
                            "other_apex": sides[other], "rim": [sides[i] for i in motif["rim"]],
                            "domains": {sides[i]: domains[i] for i in [a, e, *motif["rim"]]},
                            "intersection": intersection, "phase_status": outcome["status"],
                            "selected_now": selected_now, "event": event,
                            "trial_status": (result["phases"][event["trial_phase"]]["outcome"]["status"]
                                             if event is not None else None)}
                for category in categories:
                    if len(matches[category]) < detail_limit:
                        matches[category].append(evidence)
        motif_statistics.append({"apices": [sides[a], sides[e]], "rim": [sides[i] for i in motif["rim"]],
                                 "domain_intersection_histogram": [
                                     {"domains_and_intersection_and_status": json.loads(key), "phases": count}
                                     for key, count in sorted(signatures.items())]})
    return {"counts": dict(counts), "matches": matches, "motif_statistics": motif_statistics}


def scan_archive(manifest_path, report_path, checkpoint_dir, *, detail_limit=100):
    """Bind all archived bytes before scanning the complete ordinary guarded set."""
    start = perf_counter()
    require(type(detail_limit) is int and detail_limit >= 0, "invalid detail limit")
    manifest_path, report_path, checkpoint_dir = map(Path, (manifest_path, report_path, checkpoint_dir))
    own_sources = {portable(__file__): file_hash(__file__),
                   "tests/test_low_color_obstruction_states.py": file_hash(ROOT / "tests/test_low_color_obstruction_states.py")}
    manifest = read_bound_json(manifest_path, MANIFEST_SHA256)
    report = read_bound_json(report_path, REPORT_SHA256)
    require(report["manifest_sha256"] == MANIFEST_SHA256 and
            project_path(report["manifest_path"]) == manifest_path.resolve(), "manifest report binding differs")
    require(project_path(report["checkpoint_directory"]) == checkpoint_dir.resolve(), "wrong checkpoint directory")
    require(report["source_sha256"] == manifest["source_sha256"] and
            report["counts"] == manifest["counts"], "frozen declarations differ")
    check_hashes(manifest["source_sha256"])
    check_hashes(manifest["input_artifact_sha256"])
    parts = report["checkpoint_hashes"]
    require(len({p["filename"] for p in parts}) == len(parts), "duplicate checkpoint name")
    require(sorted(p.name for p in checkpoint_dir.glob("part-*.json.gz")) == [p["filename"] for p in parts],
            "checkpoint inventory differs")
    for part in parts:
        require(Path(part["filename"]).name == part["filename"], "nonlocal checkpoint name")
        require(file_hash(checkpoint_dir / part["filename"]) == part["sha256"], "checkpoint hash differs")
    saved_records, compact_records = manifest["records"], report["records"]
    require(len(saved_records) == len(compact_records) == manifest["counts"]["drawings"], "drawing coverage differs")
    counts, groups = Counter(), {mode: Counter() for mode in MODES}
    details = {name: [] for name in ("strict", "proper_intersection", "bad_minimum", "inconclusive_commit")}
    motif_records, offset, excluded_diagnostics = [], 0, []
    for part_number, part in enumerate(parts):
        rows = read_bound_json(checkpoint_dir / part["filename"], part["sha256"])
        require(len(rows) == part["drawings"], "checkpoint drawing count differs")
        for row_number, row in enumerate(rows):
            saved, compact = saved_records[offset], compact_records[offset]
            offset += 1
            require(not row.get("failed") and row["key"] == saved["key"] == compact["key"] and
                    row["geometry_sha256"] == saved["geometry_sha256"] == compact["geometry_sha256"] and
                    compact["checkpoint"] == part["filename"], "drawing evidence binding differs")
            require(digest(saved["geometry"]) == saved["geometry_sha256"], "geometry digest differs")
            sides, edges, lines = raw_graph(saved["geometry"])
            motifs = triangle_bipyramids(len(sides), edges)
            counts["drawings"] += 1
            counts["drawings_with_motif"] += bool(motifs)
            counts["induced_motifs"] += len(motifs)
            expected_pairs = [(scene["id"], policy) for scene in saved["scenarios"] for policy in manifest["policies"]]
            require([(r["scenario"], r["policy"]) for r in row["runs"]] == expected_pairs and
                    [(r["scenario"], r["policy"]) for r in compact["runs"]] == expected_pairs,
                    "scenario/policy coverage differs")
            scenes = {scene["id"]: scene for scene in saved["scenarios"]}
            row_statistics = []
            for run_number, (run, compact_run) in enumerate(zip(row["runs"], compact["runs"])):
                if run["policy"] != "guarded":
                    counts["plain_runs_excluded"] += 1
                    continue
                if run["scenario"] not in MODES:
                    excluded_diagnostics.append({"key": row["key"], "scenario": run["scenario"]})
                    continue
                result = run["outcome"]
                require(digest(result) == compact_run["outcome_sha256"], "full/compact outcome binding differs")
                original = result["original_input"]
                require(original["sides"] == sides and original["lines"] == lines and
                        original["anchors"] == scenes[run["scenario"]]["anchors"] and
                        not original.get("states") and not original.get("equal_names"), "nonordinary raw input")
                evidence_prefix = {"key": row["key"], "scenario": run["scenario"],
                                   "checkpoint": part["filename"], "checkpoint_row": row_number,
                                   "run_index": run_number, "policy": "guarded"}
                analysis = scan_run(result, motifs, evidence_prefix, detail_limit)
                counts.update(analysis["counts"])
                groups[run["scenario"]].update(analysis["counts"])
                if motifs:
                    row_statistics.append({"scenario": run["scenario"], "motifs": analysis["motif_statistics"]})
                for category, matches in analysis["matches"].items():
                    details[category].extend(matches[:max(0, detail_limit - len(details[category]))])
            if motifs:
                motif_records.append({"key": row["key"], "checkpoint": part["filename"],
                                      "true_edges": [[sides[a], sides[b]] for a, b in edges],
                                      "scenarios": row_statistics})
        counts["checkpoint_parts"] += 1
        if (part_number + 1) % 16 == 0 or part_number + 1 == len(parts):
            print(json.dumps({"scanned_drawings": counts["drawings"], "guarded_runs": counts["runs"],
                              "total_drawings": len(saved_records)}), flush=True)
    require(offset == len(saved_records) and counts["runs"] == 2 * len(saved_records), "ordinary guarded coverage incomplete")
    require(all(group["runs"] == len(saved_records) for group in groups.values()), "ordinary mode missing")
    check_hashes(manifest["source_sha256"])
    check_hashes(manifest["input_artifact_sha256"])
    check_hashes(own_sources)
    require(file_hash(manifest_path) == MANIFEST_SHA256 and file_hash(report_path) == REPORT_SHA256,
            "input changed during scan")
    return {"schema_version": 1, "status": "complete", "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "manifest_path": portable(manifest_path), "manifest_sha256": MANIFEST_SHA256,
            "report_path": portable(report_path), "report_sha256": REPORT_SHA256,
            "checkpoint_directory": portable(checkpoint_dir), "checkpoint_hashes": parts,
            "scanner_source_sha256": own_sources, "frozen_source_sha256": manifest["source_sha256"],
            "frozen_input_sha256": manifest["input_artifact_sha256"], "python": platform.python_version(),
            "counts": dict(counts), "groups": {mode: dict(group) for mode, group in groups.items()},
            "excluded_guarded_diagnostics": excluded_diagnostics, "detail_limit_per_category": detail_limit,
            "match_details": details, "all_motif_domain_histograms": motif_records,
            "producer_runs": 0, "oracle_runs": 0, "wall_seconds": perf_counter() - start,
            "scope": "Complete read-only scan of ordinary guarded archived persistent phases. Shared saved "
                     "planarization/global face IDs; no geometry reconstruction, propagation replay, or oracle "
                     "search. Histograms and match totals cover all motifs/states; first-N match details alone "
                     "are truncated. Strict apex signature does not require unrestricted rim domains; that "
                     "full-template subset is counted separately. Absence here is not a general reachability proof."}


def main():
    """Write a unique result only after the complete input-bound scan finishes."""
    parser = ArgumentParser(description=__doc__)
    for name in ("manifest", "report", "checkpoint-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--detail-limit", type=int, default=100)
    args = parser.parse_args()
    require(not args.output.exists(), "output exists; choose a new filename")
    result = scan_archive(args.manifest, args.report, args.checkpoint_dir, detail_limit=args.detail_limit)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, separators=(",", ":"))
        stream.write("\n")
    print(json.dumps({"status": result["status"], "counts": result["counts"],
                      "groups": result["groups"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

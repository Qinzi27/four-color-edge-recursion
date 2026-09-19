"""Restart on every drawn prefix, including prefixes after a naming failure.

Geometry is accumulated independently of names. Each current drawing is
canonicalized by its undirected stroke set, then named from scratch exactly
once per policy. Old precolors and local budgets are deliberately NOT imported.
This is a new experiment, not an extension of the frozen-color controls.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.global_restart import POLICIES, restart_line_names
from fourcolor.whole_lines import build_whole_lines
from scripts.current_corpus import build_corpus, history_document, stroke_set_key
from scripts.validate_weighted_lines import independent_check


def digest(value):
    """Hash portable JSON, not runtime object identities or machine paths."""
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode("utf-8")).hexdigest()


def canonical_document(document):
    """Normalize stroke order/direction without joining gaps or changing lines.

    This modest equivalence is not graph isomorphism. Do not retain old names,
    face IDs, source indices, or insertion order as accidental tie-break inputs.
    """
    strokes = sorted({tuple(sorted((tuple(s["a"]), tuple(s["b"])))) for s in document["strokes"]})
    return {"frame": dict(document.get("frame", {"width": 900, "height": 600})),
            "strokes": [{"a": list(a), "b": list(b)} for a, b in strokes]}


def restart_inventory(corpus):
    """Enumerate ALL prefixes rather than stopping geometry at a color failure."""
    inventory, histories, statics = {}, [], []

    def register(document, alias):
        """Cache only after canonicalizing geometry; keep every source alias."""
        document = canonical_document(document)
        key = stroke_set_key(document)
        if key not in inventory:
            inventory[key] = {"key": key, "document": document, "aliases": []}
        if inventory[key]["document"] != document:
            raise AssertionError("stroke-set hash collision")
        inventory[key]["aliases"].append(alias)
        return key

    for row in corpus["histories"]:
        prefixes = []
        for step in range(len(row["paths"]) + 1):
            document = history_document({**row, "paths": row["paths"][:step]})
            prefixes.append(register(document, {"kind": "history_prefix", "history": row["key"], "step": step}))
        histories.append({"key": row["key"], "family": row["family"], "seed": row["seed"],
                          "prefix_keys": prefixes, "original_history_sha256": row["history_sha256"],
                          "original_aliases": row["aliases"],
                          "initial_precolors_discarded": bool(row.get("initial_names")) or
                          bool(row.get("initial_state") and row["initial_state"]["cuts"]),
                          "local_budget_discarded": row["max_old_sides"]})
    for row in corpus["static_inventory"]:
        key = register(row["document"], {"kind": "static", "source": row["key"]})
        statics.append({"key": row["key"], "geometry_key": key, "family": row["family"],
                        "aliases": row["aliases"], "matching_history_keys": row["matching_history_keys"]})
    return list(inventory.values()), histories, statics


def export_geometries(records):
    """Use the geometry-only Node engine; old naming functions are never called."""
    result = subprocess.run(["node", str(ROOT / "scripts/restart-geometry.mjs")], cwd=ROOT,
                            input=json.dumps({"cases": [{"key": r["key"], "document": r["document"]}
                                                         for r in records]}),
                            capture_output=True, text=True, encoding="utf-8", check=True)
    exported = json.loads(result.stdout)
    if exported["coloring_performed"] or len(exported["results"]) != len(records):
        raise AssertionError("geometry-only export contract changed")
    return exported["results"]


def compact_result(result):
    """Preserve every status and names; deterministic traces can be regenerated."""
    compact = {k: result[k] for k in ("status", "policy", "domains", "anchors_by_dart", "colors",
                                     "choices", "backtracks", "old_colors_read", "local_budget")}
    compact.update({"trace_sha256": digest(result["trace"]), "independent_check_passed": True,
                    "same_mother_selections": sum(row.get("same_single_mother", False)
                                                  for row in result["trace"])})
    return compact


def summarize(records, histories, statics):
    """Do not conflate last-prefix success with success at EVERY prior prefix."""
    by_key = {record["key"]: record for record in records}
    summaries, history_results = [], []
    for policy in POLICIES:
        final_status, all_prefix, families = Counter(), Counter(), {}
        for row in histories:
            statuses = [by_key[key]["runs"][policy]["status"] for key in row["prefix_keys"]]
            failures = [step for step, status in enumerate(statuses) if status != "solved"]
            recoveries = [step for step in range(1, len(statuses))
                          if statuses[step] == "solved" and statuses[step - 1] != "solved"]
            entry = {"key": row["key"], "policy": policy, "statuses": statuses,
                     "all_prefixes_solved": not failures, "first_failed_prefix": failures[0] if failures else None,
                     "solved_again_after_failure": recoveries, "final_status": statuses[-1]}
            history_results.append(entry)
            final_status[statuses[-1]] += 1
            all_prefix["all_solved" if not failures else "has_failure"] += 1
            family = families.setdefault(row["family"], {"histories": 0, "all_prefixes_solved": 0,
                                                         "final_status": Counter()})
            family["histories"] += 1
            family["all_prefixes_solved"] += not failures
            family["final_status"][statuses[-1]] += 1
        summaries.append({"policy": policy,
                          "distinct_drawings": dict(Counter(r["runs"][policy]["status"] for r in records)),
                          "history_count": len(histories), "all_prefixes": dict(all_prefix),
                          "history_final_status": dict(final_status),
                          "history_families": families,
                          "static_count": len(statics),
                          "static_status": dict(Counter(by_key[r["geometry_key"]]["runs"][policy]["status"]
                                                        for r in statics))})
    return summaries, history_results


def build_report(limit=None):
    """Run one stable finite corpus, keeping unsupported geometry and conflicts."""
    corpus = build_corpus()
    records, histories, statics = restart_inventory(corpus)
    files = ("fourcolor/global_restart.py", "fourcolor/closed_support.py", "fourcolor/whole_lines.py", "fourcolor/weighted_lines.py",
             "fourcolor/line_names.py", "fourcolor/embedding.py", "scripts/current_corpus.py",
             "scripts/restart-geometry.mjs", "scripts/validate_global_restart.py",
             "scripts/validate_weighted_lines.py")
    sources = {**corpus["source_sha256"], **{p: sha256((ROOT / p).read_bytes()).hexdigest() for p in files}}
    if limit is not None:
        records = records[:limit]
        available = {r["key"] for r in records}
        histories = [r for r in histories if set(r["prefix_keys"]) <= available]
        statics = [r for r in statics if r["geometry_key"] in available]
    checks = 0
    for start in range(0, len(records), 100):
        chunk = records[start:start + 100]
        geometries = export_geometries(chunk)
        for record, exported in zip(chunk, geometries):
            if record["key"] != exported["key"]:
                raise AssertionError("geometry cases reordered")
            record["geometry_status"], record["runs"] = exported["status"], {}
            if exported["status"] != "geometry_ok":
                record["errors"] = exported["errors"]
                record["runs"] = {p: {"status": "geometry_error"} for p in POLICIES}
                continue
            geometry = exported["geometry"]
            record["geometry_sha256"] = digest(geometry)
            try:
                model = build_whole_lines(geometry)
            except ValueError as exc:
                record["runs"] = {p: {"status": "outside_scope", "reason": str(exc)} for p in POLICIES}
                continue
            # Independent topology reconstruction must agree with Node face
            # membership, regardless of face-index enumeration conventions.
            if {frozenset(face) for face in model.plane_map.faces} != {frozenset(f) for f in geometry["faces"]}:
                raise AssertionError("Python and Node disagree on side-continuation classes")
            record["topology_checked"] = True
            record["face_count"] = len(model.plane_map.faces)
            record["whole_mother_count"] = len(model.lines)
            record["real_bridge_count"] = len(geometry["real_bridge_edge_ids"])
            record["virtual_connector_count"] = len(geometry["virtual_bridge_edge_ids"])
            for policy in POLICIES:
                result = restart_line_names(geometry, policy)
                if not independent_check(geometry, result):
                    raise AssertionError((record["key"], policy, "independent name check failed"))
                record["runs"][policy] = compact_result(result)
                checks += 1
        print(json.dumps({"drawings_checked": min(start + 100, len(records)),
                          "total": len(records), "independent_checks": checks}), flush=True)
    summary, history_results = summarize(records, histories, statics)
    for path, expected in sources.items():
        if sha256((ROOT / path).read_bytes()).hexdigest() != expected:
            raise AssertionError("source changed during run: " + path)
    return {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "experiment": "Discard all names and rebuild priorities at EVERY geometric prefix",
            "smoke_limit": limit, "source_sha256": sources, "original_corpus_summary": corpus["summary"],
            "canonicalization": "Sorted unique undirected input strokes; no graph-isomorphism or collinear-union claim.",
            "independent_checks": checks, "drawings": records, "histories": histories,
            "static_inputs": statics, "history_results": history_results, "summary": summary,
            "definitions": {
                "shared-mother": "Internal interval: two endpoint other-mother sets equal the same singleton; then current bans; geometry tie. Frame root intervals do not receive this child preference.",
                "closed-support": "Current bans first, then both endpoint vertices on the same simple cycle of established primal support. Support contains frame and fully named real edges; virtual/target edges excluded. No same-mother condition.",
                "constraints": "Sum(4-|D|) over distinct unresolved shore classes of the selected unit.",
                "segment_selection": "One occurrence commitment, propagation, fresh weights; reuse first then smallest.",
                "whole-constraints": "Earlier whole-line batch rule, unchanged, retained as a separate control.",
                "old_colors": "Discarded even on frozen/precolored controls; compare geometry, not precolor extension.",
                "failure": "Retained as a status of this drawing. Subsequent geometric prefixes are still independently run."},
            "limits": ["Endpoint interpretation is explicit; not a confirmed universal interpretation of every sketch.",
                       "User clarified same-mother is not the most important priority; that earlier policy is a control, not the current proposed rule.",
                       "Internal mothers are straight runs; bent and internal closed mother identity is not reconstructed.",
                       "Four is an input palette. A solved output is verified, not a universal existence proof.",
                       "No fallback to another policy or color search after a failed run.",
                       "Exploratory existing corpus, repeated related prefixes, not independent statistical samples."]}


def write_report(path, report):
    """Exclusive portable output; gzip contains no source-machine filename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        if path.suffix == ".gz":
            with gzip.GzipFile(fileobj=stream, mode="wb", filename="", mtime=0) as archive:
                archive.write(payload)
        else:
            stream.write(payload)


def main():
    """Save all outcomes and a small self-contained summary; never overwrite."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--limit", type=int, help="Explicit smoke-only drawing limit; omit for full corpus")
    args = parser.parse_args()
    if args.output.exists() or args.summary.exists() or args.output.resolve() == args.summary.resolve():
        parser.error("choose two distinct new output paths")
    if args.limit is not None and args.limit < 1:
        parser.error("smoke limit must be positive")
    report = build_report(args.limit)
    write_report(args.output, report)
    small = {key: report[key] for key in ("experiment", "smoke_limit", "source_sha256", "original_corpus_summary",
                                         "independent_checks", "definitions", "limits", "summary")}
    small.update({"input": {"filename": args.output.name, "sha256": sha256(args.output.read_bytes()).hexdigest()},
                  "distinct_drawings": len(report["drawings"]),
                  "history_prefix_references": sum(len(r["prefix_keys"]) for r in report["histories"]),
                  "static_references": len(report["static_inputs"])})
    write_report(args.summary, small)
    print(json.dumps(small, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

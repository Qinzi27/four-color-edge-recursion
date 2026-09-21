"""Name a framed drawing once, checking structural proofs before reuse.

The input is a drawing export with frame/strokes. Other top-level fields,
including old names, are ignored. The geometry is rebuilt and every naming
decision is audited before a new output is written. A conflict is retained;
it does not trigger another policy or an exact solver.
"""

from argparse import ArgumentParser
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.structural_restart import restart_structural_names
from scripts.current_corpus import stroke_set_key
from scripts.name_peer_batch_map import reject_nonfinite
from scripts.validate_frontier_restart import file_sha, read_json
from scripts.validate_global_restart import canonical_document, digest, export_geometries, write_report
from scripts.validate_structural_restart import verify_run
from scripts.validate_structural_restart_full import SOURCE, SOURCE_SHA256, source_hashes


def run_document(document):
    """Run exactly one geometry-only attempt and an independent full audit."""
    if not isinstance(document, dict) or not isinstance(document.get("strokes"), list):
        raise ValueError("input requires a drawing object with a strokes array")
    canonical = canonical_document(document)
    key = stroke_set_key(canonical)
    exported = export_geometries([{"key": key, "document": canonical}])[0]
    if exported["status"] != "geometry_ok":
        raise ValueError("geometry rejected: " + json.dumps(exported.get("errors")))
    geometry = exported["geometry"]
    geometry_hash = digest(geometry)
    result = restart_structural_names(geometry)
    verification = verify_run(geometry, result)
    if digest(geometry) != geometry_hash:
        raise AssertionError("naming or auditing changed the geometry")
    return {"schema_version": 1, "document": canonical, "geometry_key": key,
            "geometry": geometry, "geometry_sha256": geometry_hash, "outcome": result,
            "verification": verification, "production_attempts": 1,
            "ignored_top_level_fields": sorted(set(document) - {"frame", "strokes"}),
            "scope": "One geometry-only greedy run with certified structural filtering; "
                     "inconclusive queries do not certify a safe extension."}


def main(argv=None):
    """Bind the implementation and refuse all implicit output replacement."""
    if sys.flags.optimize:
        raise SystemExit("independent proof replay requires Python without -O")
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("choose a new output; existing files are never overwritten")
    if file_sha(SOURCE) != SOURCE_SHA256:
        raise AssertionError("frozen baseline provenance differs")
    previous = read_json(SOURCE)

    def sources():
        """Reuse the frozen dependency inventory and include this adapter."""
        hashes = source_hashes(previous)
        for name in ("scripts/name_structural_map.py", "scripts/name_peer_batch_map.py"):
            hashes[name] = file_sha(ROOT / name)
        return hashes

    hashes, input_hash = sources(), file_sha(args.input)
    document = json.loads(args.input.read_text(encoding="utf-8-sig"), parse_constant=reject_nonfinite)
    report = run_document(document)
    ending = sources()
    if ending != hashes or file_sha(args.input) != input_hash or file_sha(SOURCE) != SOURCE_SHA256:
        raise AssertionError("input or implementation changed during execution")
    report.update(generated_at_utc=datetime.now(timezone.utc).isoformat(),
                  input_filename=args.input.name, input_sha256=input_hash,
                  source_sha256=hashes, source_sha256_end=ending)
    write_report(args.output, report)
    print(json.dumps({"status": report["outcome"]["status"],
                      "learned_pairs": report["outcome"]["learned_pairs"],
                      "verification": report["verification"]["passed"],
                      "output_filename": args.output.name}, ensure_ascii=False))
    return 0 if report["outcome"]["status"] == "solved" else 2


if __name__ == "__main__":
    sys.exit(main())

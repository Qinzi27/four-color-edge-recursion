"""Run one explicit boundary-filter pilot on a framed drawing JSON.

Only the drawing enters the algorithm. The full proof transcript is checked
independently and saved to a new file; a conflict never triggers a retry.
"""

from argparse import ArgumentParser
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.joint_boundary_restart import restart_joint_boundary_names
from scripts.current_corpus import stroke_set_key
from scripts.name_peer_batch_map import reject_nonfinite
from scripts.validate_frontier_restart import file_sha
from scripts.validate_global_restart import canonical_document, digest, export_geometries
from scripts.validate_joint_boundary import verify_new_run
from scripts.validate_peer_batches_full import source_hashes as frozen_source_hashes


def source_hashes():
    """Capture algorithm and independent checker code without machine paths."""
    hashes = frozen_source_hashes()
    for name in ("fourcolor/joint_boundary.py", "fourcolor/joint_boundary_restart.py",
                 "scripts/validate_joint_boundary.py", "scripts/name_joint_boundary_map.py",
                 "scripts/name_peer_batch_map.py"):
        hashes[name] = file_sha(ROOT / name)
    return hashes


def run_document(document, mode):
    """Create geometry from strokes, run once, then replay its certificates."""
    if not isinstance(document, dict) or not isinstance(document.get("strokes"), list):
        raise ValueError("input requires a drawing object with a strokes array")
    canonical = canonical_document(document)
    key = stroke_set_key(canonical)
    exported = export_geometries([{"key": key, "document": canonical}])[0]
    if exported["status"] != "geometry_ok":
        raise ValueError("geometry rejected: " + json.dumps(exported["errors"]))
    geometry = exported["geometry"]
    result = restart_joint_boundary_names(geometry, mode=mode)
    verification = verify_new_run(geometry, result)
    return {"schema_version": 1, "document": canonical, "geometry": geometry,
            "geometry_sha256": digest(geometry), "outcome": result,
            "verification": verification, "production_attempts": 1,
            "ignored_top_level_fields": sorted(set(document) - {"frame", "strokes"}),
            "scope": "One finite pilot using explicit local conditional checks in joint mode; "
                     "no full-map solver fallback or universal completeness claim."}


def main(argv=None):
    """Require a named mode and preserve previous outputs by exclusive creation."""
    if not __debug__:
        raise SystemExit("certificate checks require Python without -O")
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--mode", choices=("domains", "joint"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("refusing to overwrite an existing output; choose a new path")
    hashes, input_hash = source_hashes(), file_sha(args.input)
    document = json.loads(args.input.read_text(encoding="utf-8-sig"), parse_constant=reject_nonfinite)
    result = run_document(document, args.mode)
    if source_hashes() != hashes or file_sha(args.input) != input_hash:
        raise AssertionError("source or input changed during the run")
    result.update(generated_at_utc=datetime.now(timezone.utc).isoformat(),
                  input_filename=args.input.name, input_sha256=input_hash, source_sha256=hashes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"status": result["outcome"]["status"], "mode": args.mode,
                      "choices": result["outcome"]["choices"],
                      "verification": result["verification"]["passed"],
                      "output_filename": args.output.name}, ensure_ascii=False))
    return 0 if result["outcome"]["status"] == "solved" else 2


if __name__ == "__main__":
    sys.exit(main())

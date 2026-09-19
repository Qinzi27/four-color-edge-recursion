"""Name one drawn map with the frozen peer-batch rule, retaining its proof.

This small entry point needs Python and Node but no archived experiment file.
Only strokes and the frame enter the algorithm; supplied old colors are ignored.
A conflict is saved as a failed naming attempt, never as a fifth-color claim.
"""

from argparse import ArgumentParser
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.peer_batches import POLICY, restart_peer_batch_names
from fourcolor.whole_lines import build_whole_lines
from scripts.current_corpus import stroke_set_key
from scripts.validate_frontier_restart import file_sha
from scripts.validate_global_restart import canonical_document, digest, export_geometries
from scripts.validate_peer_batches import verify_run
from scripts.validate_peer_batches_full import source_hashes


def reject_nonfinite(value):
    """Reject JavaScript-style NaN/Infinity instead of inventing coordinates."""
    raise ValueError("Non-finite JSON number: " + value)


def run_document(document):
    """Build geometry, run exactly once, and verify without an archived answer."""
    if not isinstance(document, dict) or not isinstance(document.get("strokes"), list):
        raise ValueError("Input must be a drawing object with a strokes array.")
    canonical = canonical_document(document)
    key = stroke_set_key(canonical)
    exported = export_geometries([{"key": key, "document": canonical}])[0]
    if exported["status"] != "geometry_ok":
        raise ValueError("Geometry rejected: " + json.dumps(exported["errors"], ensure_ascii=False))
    geometry = exported["geometry"]
    result = restart_peer_batch_names(geometry)
    verification = verify_run(geometry, result)
    if not verification["passed"]:
        raise AssertionError("Independent certificate verification failed.")
    # A whole mother can have DIFFERENT names on successive intervals. Never
    # squeeze its current profile into one misleading global color pair.
    profiles = None
    if result["status"] == "solved":
        colors = result["colors"]
        profiles = [{"mother": mother["id"], "intervals": [
            {"edge": span["edge"], "dart": span["dart"],
             "t0": span["t0"], "t1": span["t1"],
             "left_side": span["left_side"], "right_side": span["right_side"],
             "left_name": colors[span["left_side"]], "right_name": colors[span["right_side"]]}
            for span in mother["spans"]]}
            for mother in build_whole_lines(geometry).lines]
    return {"schema_version": 1, "policy": POLICY, "key": key,
            "document": canonical, "geometry": geometry, "geometry_sha256": digest(geometry),
            "outcome": result, "verification": verification,
            "final_line_profiles": profiles, "production_attempts": 1,
            "old_colors_read": False,
            "ignored_top_level_fields": sorted(set(document) - {"frame", "strokes"}),
            "scope": "Current framed geometric adapter; deterministic finite experiment, "
                     "not a general four-color completeness proof."}


def main(argv=None):
    """Never overwrite input, an old certificate, or a failed attempt."""
    if not __debug__:
        raise SystemExit("Certificate checks require Python without -O.")
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Drawing JSON with strokes and optional frame.")
    parser.add_argument("--output", required=True, type=Path, help="New JSON certificate path.")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Refusing to overwrite an existing output; choose a new path.")
    hashes = {**source_hashes(), "scripts/name_peer_batch_map.py": file_sha(Path(__file__))}
    input_hash = file_sha(args.input)
    document = json.loads(args.input.read_text(encoding="utf-8-sig"), parse_constant=reject_nonfinite)
    result = run_document(document)
    if file_sha(args.input) != input_hash or hashes != {
            **source_hashes(), "scripts/name_peer_batch_map.py": file_sha(Path(__file__))}:
        raise AssertionError("Input or source changed during the run.")
    result.update(generated_at_utc=datetime.now(timezone.utc).isoformat(),
                  input_filename=args.input.name, input_sha256=input_hash, source_sha256=hashes)
    # Exclusive creation protects prior evidence, including a race after the
    # initial existence check. This path is supplied by the user, not hardcoded.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"status": result["outcome"]["status"],
                      "independent_certificate_checked": True,
                      "choices": result["outcome"]["choices"],
                      "output_filename": args.output.name}, ensure_ascii=False))
    return 0 if result["outcome"]["status"] == "solved" else 2


if __name__ == "__main__":
    sys.exit(main())

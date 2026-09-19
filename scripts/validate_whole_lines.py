"""Recompute the whole-line model on a fixed geometry corpus, without search.

Run ``python scripts/validate_whole_lines.py --output outputs/whole-lines.json``.
Node supplies existing browser geometry; Python independently reconstructs the
rotation orbits, checks manually supplied certificates, and propagates only
forced candidate removals. The output path must not already exist.
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

from fourcolor.line_names import audit_line_names
from fourcolor.whole_lines import (
    build_whole_lines, decode_profiles, encode_profiles,
    propagate_candidates, reverse_profile, restart_with_symbol_symmetry,
)


def candidate_anchors(model, roles, symbols, retained):
    """Translate explicit test anchors to line-shore occurrences, never points."""
    return {model.plane_map.faces[roles[role]][0]: [symbols[roles[role]]]
            for role in retained}


def validate_record(record):
    """Check topology, reversible representation, and a clearly partial restart."""
    geometry = record["geometry"]
    model = build_whole_lines(geometry)
    plane = model.plane_map
    assert list(plane.face_of_dart) == geometry["faceOfDart"]
    assert [list(face) for face in plane.faces] == geometry["faces"]
    owned = [span["edge"] for line in model.lines for span in line["spans"]]
    real = [i for i, edge in enumerate(geometry["edges"]) if not edge["virtual"]]
    assert len(owned) == len(set(owned)) and set(owned) == set(real)

    # Unique test tokens deliberately differ even along a common shore. This
    # proves no occurrence was silently merged; they are NOT coloring inputs.
    tokens = [f"occurrence-{d}" for d in range(2 * len(plane.edges))]
    encoded = encode_profiles(model, tokens)
    assert decode_profiles(model, encoded) == tokens
    for profile in encoded["lines"].values():
        reversed_twice = reverse_profile(reverse_profile(profile))
        for a, b in zip(profile, reversed_twice):
            assert all(a[k] == b[k] for k in ("dart", "left", "right"))
            assert all(abs(a[k] - b[k]) < 1e-12 for k in ("t0", "t1"))

    # An unlimited UNIQUE symbol per side is a consistency oracle only; it
    # must never be described as a four-symbol coloring success.
    labels = [f"side-{side}" for side in plane.face_of_dart]
    roundtrip = decode_profiles(model, encode_profiles(model, labels))
    pairs = tuple(zip(roundtrip[::2], roundtrip[1::2]))
    audit = audit_line_names(geometry["rotation"], pairs)
    assert audit.status == "consistent"
    assert audit.side_orbits == plane.faces

    frame = next(line for line in model.lines if line["id"] == "frame")
    assert all(span["left_side"] == geometry["outerFace"] for span in frame["spans"])
    # Global symbol symmetry allows outside=1 and ONE adjacent inside=2.
    # No third anchor, greedy choice, hidden oracle, or old name is supplied.
    initial = frame["spans"][0]["dart"]
    restart = propagate_candidates(model, {initial: [1], initial ^ 1: [2]})
    assert restart["status"] != "conflict"
    if restart["status"] == "solved":
        assert plane.check_coloring([domain[0] - 1 for domain in restart["domains"]])
    canonical_restart = restart_with_symbol_symmetry(model)
    assert canonical_restart["status"] != "conflict"
    if canonical_restart["status"] == "solved":
        assert plane.check_coloring([d[0] - 1 for d in canonical_restart["domains"]])

    result = {"id": record["id"], "family": record["family"], "seed": record["seed"],
              "document": record["document"], "geometry": geometry,
              "whole_line_count": len(model.lines), "atomic_real_edges": len(real),
              "virtual_edges": list(model.virtual_edges),
              "attachment_records": sum(len(line["events"]) for line in model.lines),
              "checks": {"independent_topology": True, "edge_coverage": True,
                         "profile_roundtrip": True, "reversal": True,
                         "unlimited_symbol_consistency": True},
              "fresh_restart": restart, "symmetry_reduced_restart": canonical_restart}
    if record["id"] in ("teaching-D", "D-before", "remote-before", "remote-after"):
        result["whole_lines"] = model.lines
    if "witnesses" in record:
        checked = {}
        for name, witness in record["witnesses"].items():
            colors = witness["colors"]
            python_valid = plane.check_coloring([c - 1 for c in colors])
            assert python_valid == witness["valid"]
            values = [str(colors[side]) for side in plane.face_of_dart]
            certificate = encode_profiles(model, values)
            recovered = decode_profiles(model, certificate)
            independent = audit_line_names(geometry["rotation"], tuple(zip(recovered[::2], recovered[1::2])))
            assert (independent.status == "consistent") == python_valid
            checked[name] = {**witness, "python_valid": python_valid,
                             "line_audit_status": independent.status, "profiles": certificate}
        result["witnesses"] = checked
    if record["id"] == "remote-after":
        witness = record["witnesses"]["side_switched"]
        roles, colors = witness["role_to_face"], witness["colors"]
        retained = ("external", "A", "R", "D")
        anchors = candidate_anchors(model, roles, colors, retained)
        propagation = propagate_candidates(model, anchors)
        assert propagation["status"] == "solved"
        assert [d[0] for d in propagation["domains"]] == colors
        frozen = dict(anchors)
        frozen[plane.faces[roles["west"]][0]] = [1]
        frozen_result = propagate_candidates(model, frozen)
        assert frozen_result["status"] == "conflict"
        result["adjustment_experiment"] = {
            "retained_roles": list(retained), "anchors_by_dart": anchors,
            "both_child_sides_released": propagation, "west_frozen_to_old_1": frozen_result,
            "interpretation": "Conditional repair experiment. Fresh whole-map restart is recorded separately; old names are not secretly retained there.",
            "proposed_downward_line_name": [colors[roles["east"]], colors[roles["west"]]],
        }
        assert canonical_restart["status"] == "solved"
        assert canonical_restart["domains"][roles["west"]] == [3]
        assert canonical_restart["domains"][roles["east"]] == [1]
    return result


def run_validation():
    """Generate all final drawings and save both positive and negative results."""
    data = json.loads(subprocess.check_output(
        ["node", str(ROOT / "scripts" / "whole-line-fixtures.mjs"), "--emit"],
        cwd=ROOT, encoding="utf-8"))
    records = [validate_record(record) for record in data["records"]]
    by_id = {record["id"]: record for record in records}
    mother_id = "L:0,180>900,180"
    old = next(line for line in by_id["D-before"]["whole_lines"] if line["id"] == mother_id)
    new = next(line for line in by_id["teaching-D"]["whole_lines"] if line["id"] == mother_id)
    assert old["endpoints"] == new["endpoints"]
    assert len(old["spans"]) == 3 and len(new["spans"]) == 4
    assert [event["point"] for event in new["events"] if 0 < event["t"] < 1] == [
        [300, 180], [450, 180], [600, 180]]
    sources = dict(data["source_sha256"])
    for source in ("fourcolor/whole_lines.py", "fourcolor/embedding.py",
                   "fourcolor/line_names.py", "scripts/validate_whole_lines.py"):
        sources[source] = sha256((ROOT / source).read_bytes()).hexdigest()
    return {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "experiment": "Whole-line continuity, ordered shore profiles and forced candidate propagation",
            "seed_range": data["seed_range"], "random_generator": data["random_generator"],
            "scope": "255 finite maps: 240 seeded generated, 7 gallery, 2 teaching, 6 targeted. Representation checks are NOT four-color solver successes.",
            "limitations": ["Interior continuation is maximal drawn collinear continuity; no unprovided bend policy is inferred.",
                            "Node geometry is shared with the website; Python independently checks the rotation topology and name certificates, not exact-arithmetic intersection geometry.",
                            "Four symbols are assumed for the candidate experiment, not proved sufficient by the representation.",
                            "Pure propagation makes no choices. The separate symmetry-reduced variant chooses only a representative under a proven global permutation symmetry, never a general candidate tie.",
                            "Neither variant enumerates assignments, backtracks or claims completeness."],
            "source_sha256": sources,
            "summary": {"maps_checked": len(records),
                        "whole_lines": sum(r["whole_line_count"] for r in records),
                        "atomic_real_edges": sum(r["atomic_real_edges"] for r in records),
                        "family_counts": dict(Counter(r["family"] for r in records)),
                        "representation_checks_passed": len(records),
                        "fresh_restart_status": dict(Counter(r["fresh_restart"]["status"] for r in records)),
                        "symmetry_reduced_restart_status": dict(Counter(r["symmetry_reduced_restart"]["status"] for r in records)),
                        "D_mother_identity_preserved": True,
                        "conditional_remote_repair_without_choices": True},
            "records": records}


def main():
    """Refuse to overwrite prior reports, including on reruns."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; choose a new filename to preserve evidence")
    report = run_validation()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Measure one fixed graph template against every frozen v4 failed commitment.

Only graph-template vertex mappings are searched, never color assignments.
The template is not integrated into v4 and no repaired coloring is attempted.
Coverage means a valid certificate excludes the recorded fatal name because an
already committed side has that name; it does not mean a complete map repair.
"""

from argparse import ArgumentParser
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.implicit_inequality import find_implicit_inequality, verify_implicit_inequality
from scripts.validate_frontier_restart import file_sha, independent_geometry, read_json
from scripts.validate_relation_frontier_full import require


def main():
    """Test all declared failures, binding both negative and positive outcomes."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "outputs/peer-batches-full-2026-09-19.json.gz")
    parser.add_argument("--diagnosis", type=Path, default=ROOT / "outputs/peer-batches-failure-diagnosis-2026-09-19.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "choose a new coverage output")
    report, diagnosis = read_json(args.report), read_json(args.diagnosis)
    report_sha, diagnosis_sha = file_sha(args.report), file_sha(args.diagnosis)
    require(report["full_corpus_run"] and report["policy"] == "peer-batch-ready-sides-v4", "not frozen full v4")
    require(diagnosis["sources"] == [{"filename": args.report.name, "sha256": report_sha,
                                     "full_corpus_run": True, "failed_inventory_records": len(report["failure_keys"])}],
            "diagnosis and full report differ")
    by_key = {row["key"]: row for row in diagnosis["records"]}
    require(set(by_key) == set(report["failure_keys"]), "failure coverage incomplete")
    files = ("fourcolor/implicit_inequality.py", "fourcolor/embedding.py",
             "scripts/check_implicit_inequality_failures.py", "tests/test_implicit_inequality.py")
    hashes = {name: file_sha(ROOT / name) for name in files}
    records = []
    for key in sorted(report["failure_keys"]):
        detail = report["detailed_examples"][key]
        result, geometry = detail["outcome"], detail["geometry"]
        proven = by_key[key]
        require(proven["first_fatal_choice_proved"], "first fatal index not yet proved")
        step_index = proven["first_fatal_choice_index_one_based"] - 1
        step = result["trace"][step_index]
        plane, adjacent = independent_geometry(geometry)
        commitments = result["propagation_phases"][step_index]["anchors_by_dart"]
        partners = sorted({plane.face_of_dart[int(dart)] for dart, names in commitments.items()
                           if names == [step["symbol"]]})
        searches, certificates = [], []
        for partner in partners:
            require(partner != step["side"], "candidate was already committed")
            require(step["side"] not in adjacent[partner], "direct inequality should already remove this name")
            for first, second in ((partner, step["side"]), (step["side"], partner)):
                certificate = find_implicit_inequality(geometry, first, second)
                searches.append({"ordered_target_sides": [first, second], "matched": certificate is not None})
                if certificate is not None:
                    verification = verify_implicit_inequality(geometry, certificate)
                    certificates.append({"committed_partner": partner, "certificate": certificate,
                                         "verification": verification})
        records.append({"key": key, "aliases": detail["aliases"], "face_count": detail["face_count"],
                        "first_fatal_choice_index_one_based": step_index + 1,
                        "fatal_side": step["side"], "fatal_name": step["symbol"],
                        "committed_same_name_partners": partners, "template_searches": searches,
                        "covered": bool(certificates), "certificates": certificates})
    require(file_sha(args.report) == report_sha and file_sha(args.diagnosis) == diagnosis_sha,
            "input evidence changed during coverage check")
    require({name: file_sha(ROOT / name) for name in files} == hashes, "template or checker code changed")
    covered = sum(row["covered"] for row in records)
    out = {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
           "report": {"filename": args.report.name, "sha256": report_sha},
           "diagnosis": {"filename": args.diagnosis.name, "sha256": diagnosis_sha},
           "source_sha256": hashes, "source_hashes_unchanged": True,
           "search_scope": "Both orientations of fatal side versus every previously committed side with the same name",
           "failure_records_checked": len(records), "fatal_choices_excluded_by_template": covered,
           "coverage_fraction": [covered, len(records)], "records": records,
           "production_attempts_added": 0, "applied_to_v4": False,
           "limits": ["Coverage excludes one recorded name, not a guarantee that the remaining choices complete a map.",
                      "Only the fixed nine-vertex nineteen-edge template is matched; no pattern expansion was used.",
                      "The searched assignments map graph vertices, not color names.",
                      "This one certified local implication is not a general four-coloring method."]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(out, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print({"failures_checked": len(records), "covered": covered, "production_attempts_added": 0}, flush=True)


if __name__ == "__main__":
    main()

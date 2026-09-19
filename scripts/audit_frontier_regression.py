"""Show an old valid coloring beside a witness exposing one new greedy error.

This is a diagnostic, not a production fallback. The second witness is ONLY
a global 3/4 permutation of the old valid coloring. No assignment search is
needed: it satisfies the new run's first commitment and the safe alternative
at its second commitment. The actual failing run is retained in the manifest.
"""

from argparse import ArgumentParser
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.frontier_restart import restart_frontier_names
from fourcolor.global_restart import restart_line_names
from scripts.render_anchor_failure_cases import Canvas, MUTED, LINE_ID
from scripts.render_frontier_restart import draw_adaptive
from scripts.render_global_restart import rectangular_payload
from scripts.validate_frontier_restart import read_json, verify_result
from scripts.validate_global_restart import export_geometries, digest, write_report


def main():
    """Select the smallest stored regression and validate every displayed name."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("choose a fresh output directory")
    report = read_json(args.input)
    regressions = sorted((r for r in report["drawings"] if "existing-corpus" in r["cohorts"]
                          and r["runs"]["closed-support"]["status"] == "solved"
                          and r["runs"]["tight-hall"]["status"] == "conflict"),
                         key=lambda r: (r["face_count"], len(r["document"]["strokes"]), r["key"]))
    record = regressions[0]
    if not any(a.get("history") == "guillotine-20261209" and a.get("step") == 9 for a in record["aliases"]):
        raise AssertionError("the documented minimal regression changed; review before drawing")
    geometry = export_geometries([record])[0]["geometry"]
    old = restart_line_names(geometry, "closed-support")
    new = restart_frontier_names(geometry, "tight-hall")
    for result in (old, new):
        saved = record["runs"][result["policy"]]
        if result["domains"] != saved["domains"] or digest(result["trace"]) != saved["trace_sha256"]:
            raise AssertionError("diagnostic no longer matches the formal report")
        if not verify_result(geometry, result)["passed"]:
            raise AssertionError("independent validation failed")
    if len(new["trace"]) != 2:
        raise AssertionError("this diagnostic concerns exactly two commitments")
    first, second = new["trace"]
    witness = deepcopy(new)
    witness["status"] = "solved"
    witness["policy"] = "diagnostic-global-permutation-NOT-production-output"
    witness["colors"] = [{3: 4, 4: 3}.get(c, c) for c in old["colors"]]
    witness["domains"] = [[c] for c in witness["colors"]]
    witness["anchors_by_dart"] = {**new["initial_anchors_by_dart"], first["dart"]: [first["symbol"]]}
    witness["trace"] = []
    witness["choices"] = 0
    check = verify_result(geometry, witness)
    if not check["passed"] or second["domain"] != [2, 4] or second["symbol"] != 2:
        raise AssertionError("the declared fork was not reproduced")
    if witness["colors"][second["side"]] != 4:
        raise AssertionError("the old-color permutation does not expose the safe alternative")
    # This witness proves that the first commitment retained an extension.
    # The separately re-derived conflict cert proves the second lost all of them.
    before = rectangular_payload(geometry, old, record["document"])
    after = rectangular_payload(geometry, witness, record["document"])
    args.output_dir.mkdir(parents=True)
    canvas = Canvas(1900, 1070, "msyh.ttc")
    canvas.text((55, 28), "旧图没有失去四色解：错在新策略的第 2 次主动落名", size=39)
    canvas.text((55, 95), "seed 20261209，第 9 刀｜完全相同的线网；两幅都是经过完整共边校验的合法结果。", size=26, color=MUTED)
    for i, payload in enumerate((before, after)):
        x = 55 + i * 945
        canvas.text((x, 165), "旧策略的合法结果（仍然有效）" if i == 0 else
                    "旧解整体交换3/4：保留新策略第1步", size=27)
        canvas.text((x, 214), "外侧1；内部数字表示当前线侧名", size=24, color=MUTED)
        draw_adaptive(canvas, payload, (x, 267), 0.9)
        if i == 1:
            side = next(s for s in payload["sides"] if s["id"] == str(second["side"]))
            x0, y0, x1, y1 = side["bounds"]
            canvas.line([(x + a * 0.9, 267 + b * 0.9) for a, b in
                         ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))], color=LINE_ID, width=6)
    canvas.text((55, 847), "第1步：下方中间侧取3仍可完成。第2步：蓝框侧候选为 {2,4}，程序抢先取2导致冲突。", size=27)
    canvas.text((55, 907), "右图证明保留第1步、取4有合法完成；右图只是诊断证据，没有被喂回生产算法。", size=27, color=LINE_ID)
    canvas.text((55, 968), "“新策略没有完成”不能写成“旧图不可四色”，也不能写成“用户的母线思想被证伪”。", size=26, color=MUTED)
    files = canvas.save(args.output_dir, "old-map-valid-new-choice-wrong")
    write_report(args.output_dir / "manifest.json", {
        "input": {"filename": args.input.name, "sha256": sha256(args.input.read_bytes()).hexdigest()},
        "regression_count": len(regressions), "record": record, "geometry": geometry,
        "old_result": old, "new_result": new, "first_fatal_commitment": 2,
        "first_commitment_extension": witness["colors"], "witness_check": check,
        "witness_origin": "Global 3/4 permutation of old solution; diagnostic only; not generated by new policy.",
        "new_conflict_check": verify_result(geometry, new), "files": files,
        "source_sha256": {p: sha256((ROOT / p).read_bytes()).hexdigest() for p in (
            "scripts/audit_frontier_regression.py", "scripts/render_frontier_restart.py",
            "fourcolor/frontier_restart.py", "scripts/validate_frontier_restart.py")}})
    print({"old_valid": True, "same_geometry": True, "first_fatal_commitment": 2,
           "safe_alternative": 4, "production_rule_changed": False})


if __name__ == "__main__":
    main()

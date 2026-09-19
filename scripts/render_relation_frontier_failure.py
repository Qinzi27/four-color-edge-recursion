"""Draw a verified regression without altering geometry or rescuing the policy.

The old valid coloring is explicitly a diagnostic witness, never an input to
the new rule. Reuse the project's exact rectangle/Canvas renderer; failed
current names are not drawn as if they formed a completed coloring.
"""

from argparse import ArgumentParser
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.frontier_restart import restart_frontier_names
from fourcolor.relation_frontier import POLICY, restart_relation_frontier_names
from scripts.render_anchor_failure_cases import Canvas, LINE_ID, MUTED
from scripts.render_frontier_restart import draw_adaptive
from scripts.render_global_restart import rectangular_payload
from scripts.validate_frontier_restart import read_json, verify_result, file_sha
from scripts.validate_global_restart import compact_result, digest, export_geometries, write_report
from scripts.validate_relation_frontier import independent_check
from scripts.validate_relation_frontier_full import exact_run


def main():
    """Retain both a lawful control and a blank map for manual naming."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--key", help="Exact recorded regression key; default smallest rectangular-history regression")
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("choose a fresh figure directory")
    report = read_json(args.input)
    if not report["full_corpus_run"] or report["smoke_limit"] is not None:
        parser.error("a complete full-library report is required")
    regressions = sorted((r for r in report["drawings"]
                          if r["runs"]["tight-hall"]["status"] == "solved"
                          and r["runs"][POLICY]["status"] == "conflict"
                          and any("guillotine" in a.get("history", "") for a in r["aliases"])),
                         key=lambda r: (r["face_count"], len(r["document"]["strokes"]), r["key"]))
    if not regressions:
        parser.error("no rectangular-history regression in the supplied report")
    record = next(r for r in regressions if r["key"] == args.key) if args.key else regressions[0]
    alias = next(a for a in record["aliases"] if "guillotine" in a.get("history", ""))
    geometry = export_geometries([record])[0]["geometry"]
    if digest(geometry) != record["geometry_sha256"]:
        raise AssertionError("figure geometry drifted")
    old = restart_frontier_names(geometry, "tight-hall")
    new = restart_relation_frontier_names(geometry)
    checks = {"baseline": verify_result(geometry, old), "candidate": independent_check(geometry, new)}
    for result in (old, new):
        exact_run(compact_result(result), record["runs"][result["policy"]])
    if digest(new["propagation_phases"]) != record["runs"][POLICY]["propagation_phases_sha256"]:
        raise AssertionError("figure proof trace drifted")
    if not checks["baseline"]["passed"] or not checks["candidate"]["passed"]:
        raise AssertionError("unverified figure state")
    payload = rectangular_payload(geometry, old, record["document"])
    last = new["trace"][-1]
    # If this complete witness survives all previous choices and pair records,
    # the last choice really is the first impossible commitment, not just the
    # last place where an already-existing impossibility became detectable.
    prior_witness = all(old["colors"][s["side"]] == s["symbol"] for s in new["trace"][:-1])
    pair_witness = all(
        call["outcome"]["relations"][i][j] & (1 << (4 * (a - 1) + b - 1))
        for call in new["propagation_phases"][:-1]
        for i, a in enumerate(old["colors"]) for j, b in enumerate(old["colors"]))
    first_fatal = len(new["trace"]) if prior_witness and pair_witness else None
    focus = next(s["bounds"] for s in payload["sides"] if int(s["id"]) == last["side"])

    def highlight(canvas, origin, scale):
        """Outline existing boundary segments only; this adds no drawn edge."""
        x0, y0, x1, y1 = focus
        canvas.line([(origin[0] + x * scale, origin[1] + y * scale)
                     for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))],
                    color=LINE_ID, width=6)

    label = f"{alias['history']}，第 {alias['step']} 刀"
    args.output_dir.mkdir(parents=True)
    canvas = Canvas(1900, 1040, "msyh.ttc")
    canvas.text((55, 28), "全库检验中的策略退步：同一张地图仍有合法四色标记", size=38)
    canvas.text((55, 96), label + "｜原坐标、原线段、完整拓扑；未简化或删线。", size=25, color=MUTED)
    for index, blank in enumerate((False, True)):
        x = 55 + index * 945
        canvas.text((x, 169), "上一版合法结果：全边检查通过" if not blank else "新规则仍受阻：留白供人工标记", size=28)
        canvas.text((x, 220), "外侧1；内部数字表示当前线侧名" if not blank else "蓝框为最后主动定名侧；? 表示待命名", size=25, color=MUTED)
        draw_adaptive(canvas, payload, (x, 280), 0.9, blank=blank)
        highlight(canvas, (x, 280), 0.9)
    if first_fatal:
        canvas.text((55, 861), f"旧合法解保留新规则前 {first_fatal-1} 次主动决定；第 {first_fatal} 次才出现不可延伸的选择。", size=28, color=LINE_ID)
        canvas.text((55, 918), f"该次候选 {last['domain']}，程序取 {last['symbol']}；旧合法解在同一侧取 {old['colors'][last['side']]}。", size=28)
    else:
        canvas.text((55, 866), "这里证明的是新策略退步，不代表用户的母线构造思想被证伪。", size=28, color=LINE_ID)
    canvas.text((55, 975), "左图只用于独立诊断，没有被输入新规则；未失败换算法、未回溯。", size=25, color=MUTED)
    files = canvas.save(args.output_dir, "regression-control-and-blank")
    manual = Canvas(1600, 1060, "msyh.ttc")
    manual.text((55, 28), "同一受阻图：可直接人工标记", size=40)
    manual.text((55, 101), label + "｜外侧固定1，内部可重新命名。", size=27, color=MUTED)
    draw_adaptive(manual, payload, (55, 232), 1.1, blank=True)
    highlight(manual, (55, 232), 1.1)
    for i, text in enumerate(("请标明：", "先选哪条母线", "先决定哪个局部侧", "哪些名字应保持联动", "哪一步应暂缓定名")):
        manual.text((1115, 270 + i * 70), text, size=27, color=LINE_ID if i == 0 else MUTED)
    manual.text((1115, 690), "蓝框：最后主动定名侧", size=25, color=LINE_ID)
    manual.text((55, 946), "原始几何与完整推导证书见同目录 manifest.json；图中没有省略任何线段。", size=26)
    files += manual.save(args.output_dir, "manual-blank")
    write_report(args.output_dir / "manifest.json", {
        "input": {"filename": args.input.name, "sha256": file_sha(args.input)},
        "selection": "Explicit recorded representative" if args.key else "Smallest rectangular-history regression by faces/strokes/key",
        "record": record, "geometry": geometry, "old_result": old, "new_result": new,
        "checks": checks, "first_fatal_commitment": first_fatal,
        "old_complete_witness_matches_prior_commitments": prior_witness,
        "old_complete_witness_pairs_survive_prior_filters": pair_witness,
        "geometry_transform": "Uniform scaling only; original screen x-right/y-down; no simplification",
        "alt_text": "The same rectangular line network shown with an independently checked older four-name solution and a blank annotation copy. The newer deterministic policy conflicts; this does not establish that the map needs five colors.",
        "files": files, "source_sha256": {p: file_sha(ROOT / p) for p in (
            "scripts/render_relation_frontier_failure.py", "scripts/render_frontier_restart.py",
            "scripts/render_global_restart.py", "scripts/render_anchor_failure_cases.py")}})
    print({"key": record["key"], "first_fatal_commitment": first_fatal, "files": len(files)}, flush=True)


if __name__ == "__main__":
    main()

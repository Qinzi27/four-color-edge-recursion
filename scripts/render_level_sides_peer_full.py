"""Render actual noncompletions from the frozen full-corpus experiment.

Reuse the project's exact geometry renderer. A color conflict stays blank for
manual annotation; lack of rooted inheritance is illustrated separately.
Neither diagram is a modified photograph or evidence for a fifth color.
"""

from argparse import ArgumentParser
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.render_anchor_failure_cases import Canvas, INK, LINE_ID, MUTED, draw_map, pillow_version
from scripts.render_frontier_restart import draw_adaptive
from scripts.render_global_restart import FILLS, rectangular_payload
from scripts.render_level_sides import contrast
from scripts.validate_frontier_restart import file_sha, json_value, read_json, verify_result
from scripts.validate_global_restart import digest, write_report
from fourcolor.level_sides_peer import POLICY, restart_level_peer_names
from scripts.validate_level_sides_peer import verify_run


def main():
    """Save new PNG/SVG pairs with matched geometry and full proof provenance."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--font", default="msyh.ttc")
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("use a fresh directory")
    report = read_json(args.input)
    if not report["full_corpus_run"] or report["policy"] != POLICY:
        parser.error("requires this candidate's full frozen report")
    by_key = {r["key"]: r for r in report["drawings"]}
    args.output_dir.mkdir(parents=True)
    files, evidence = [], []
    for status in ("conflict", "outside_scope"):
        detail = report["least_" + status]
        if detail is None:
            continue
        geometry = detail["geometry"]
        # Regenerate native integer dart keys before hashing: JSON serialization
        # converts them to strings and may change sort_keys ordering on reread.
        result = restart_level_peer_names(geometry)
        saved = by_key[detail["key"]]
        if json_value(result) != detail["outcome"]:
            raise AssertionError("illustrated rerun differs from stored certificate")
        if digest(geometry) != saved["geometry_sha256"] or digest(result) != saved["runs"][POLICY]["raw_result_sha256"]:
            raise AssertionError("figure source differs from the full report")
        if json_value(verify_run(geometry, result)) != detail["verification"]:
            raise AssertionError("figure proof replay differs")
        if result["status"] != status:
            raise AssertionError("wrong diagnostic kind")
        previous = detail["previous_result"]
        previous_legal = previous["status"] == "solved" and verify_result(geometry, previous)["passed"]
        label = "；".join(f"{a.get('history', a.get('static', 'case'))} / step {a.get('step', '-')}"
                         for a in detail["aliases"][:2])
        canvas = Canvas(1450, 1050, args.font)
        title = "新规则选色受阻：空白原图供人工标记" if status == "conflict" else "另一类未完成：双端继承等级无法启动"
        canvas.text((55, 28), title, size=38)
        canvas.text((55, 94), label, size=23, color=MUTED)
        canvas.text((55, 150), "外侧1；原始线网完整保留；数字是色名，母线等级不是颜色。", size=25)
        if status == "conflict":
            payload = rectangular_payload(geometry, result, detail["document"])
            draw_adaptive(canvas, payload, (55, 218), 1.15, blank=True)
            # Highlight only the recorded first commitment, not a fictitious
            # completed coloring. Unknown regions retain question marks.
            if result["trace"]:
                first = result["trace"][0]
                chosen = next(s for s in payload["sides"] if s["id"] == str(first["side"]))
                x0, y0, x1, y1 = chosen["bounds"]
                canvas.line([(55 + x * 1.15, 218 + y * 1.15)
                             for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))],
                            color=LINE_ID, width=5)
                canvas.text((1120, 680), "蓝框：首个落名位置", size=22, color=LINE_ID)
                canvas.text((1120, 725), f"候选 {first['domain']}", size=22)
                canvas.text((1120, 770), f"程序先取 {first['symbol']}", size=22)
                canvas.text((1120, 815), "本次随后受阻", size=22)
        else:
            payload = {"width": 900, "height": 600, "sides": [],
                       "cuts": [[s["a"], s["b"]] for s in detail["document"]["strokes"]]}
            draw_map(canvas, payload, (55, 218), 1.15)
        canvas.text((55, 945), "旧规则已有合法四色结果。" if previous_legal else "此状态不说明地图需要第五色。", size=27, color=LINE_ID)
        canvas.text((55, 996), "请标注母线先后及何时落名；图中没有预填失败状态的名字。" if status == "conflict" else
                    "这是几何准入范围不足，不是取色后的矛盾；本轮没有临时补规则。", size=25, color=MUTED)
        files.extend(canvas.save(args.output_dir, "least-" + status.replace("_", "-")))
        evidence.append({"key": detail["key"], "status": status, "aliases": detail["aliases"],
                         "geometry_sha256": digest(geometry), "raw_result_sha256": digest(result),
                         "previous_coloring_checked_again": bool(previous_legal), "payload": payload,
                         "unranked_mothers": result["unranked_mothers"]})
        if status == "conflict" and previous_legal:
            # A separate valid witness never goes into the candidate and is not
            # mislabeled as the new algorithm's result.
            witness = rectangular_payload(geometry, previous, detail["document"])
            colored = Canvas(1450, 1050, args.font)
            colored.text((55, 28), "同一张图：旧规则的合法结果（仅作对照）", size=38)
            colored.text((55, 97), "不是本轮新算法的输出，也没有作为新算法输入。外侧1。", size=26, color=MUTED)
            draw_adaptive(colored, witness, (55, 218), 1.15)
            colored.text((55, 955), "全部实际共边及线轨道已重新独立检查；这张图本身仍可合法四色标名。", size=25)
            files.extend(colored.save(args.output_dir, "least-conflict-old-valid-witness"))
    write_report(args.output_dir / "manifest.json", {
        "input": {"filename": args.input.name, "sha256": file_sha(args.input)}, "policy": POLICY,
        "files": files, "evidence": evidence, "pillow_version": pillow_version,
        "transform": "Original coordinates, uniform scale 1.15, x right/y down; no omitted lines",
        "palette": FILLS, "contrast_ink_on_fills": {str(k): contrast(INK, v) for k, v in FILLS.items()},
        "scope": "Research-screen diagnostics, not journal/accessibility certification",
        "alt_text": "Exact smallest noncompleted maps, separating greedy color conflict from unrooted geometric inheritance. Conflicts are blank for manual annotation; any valid old coloring is explicitly a separate comparator.",
        "source_sha256": {p: file_sha(ROOT / p) for p in (
            "scripts/render_level_sides_peer_full.py", "scripts/render_level_sides.py", "scripts/render_frontier_restart.py",
            "scripts/render_global_restart.py", "scripts/render_anchor_failure_cases.py")}})
    print({"figures": len(files) // 2, "directory": args.output_dir.name})


if __name__ == "__main__":
    main()

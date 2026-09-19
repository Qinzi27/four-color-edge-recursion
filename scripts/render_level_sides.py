"""Render the six verified level/current-side outputs using existing geometry.

This is a fresh code-native diagram, not an edit of the user's photograph.
All narrow strips and the original aspect ratio remain; numbers duplicate hue.
Each figure is bound to its checked input and coloring by the manifest hashes.
"""

from argparse import ArgumentParser
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.render_anchor_failure_cases import Canvas, INK, LINE_ID, MUTED, pillow_version
from scripts.render_frontier_restart import draw_adaptive
from scripts.render_global_restart import FILLS, rectangular_payload
from scripts.validate_frontier_restart import file_sha, read_json, verify_result
from scripts.validate_global_restart import digest, write_report


def contrast(first, second):
    """Calculate sRGB luminance contrast for foreground and categorical fills."""
    def luminance(color):
        values = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in values]
        return sum(v * w for v, w in zip(linear, (0.2126, 0.7152, 0.0722)))
    a, b = sorted((luminance(first), luminance(second)))
    return (b + 0.05) / (a + 0.05)


def main():
    """Create one six-panel overview plus full-size individual PNG/SVG pairs."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--font", default="msyh.ttc")
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("choose a new figure directory")
    report = read_json(args.input)
    if len(report["records"]) != 6 or report["summary"]["statuses"] != {"solved": 6}:
        parser.error("this labeled six-success figure requires six verified successes")
    args.output_dir.mkdir(parents=True)
    canvas = Canvas(1900, 2300, args.font)
    canvas.text((55, 28), "等级展开＋当前侧约束：六张旧受阻图全部完成", size=38)
    canvas.text((55, 92), "外侧1；保留原始坐标和全部窄条。数字为当前色名，不是母线等级。", size=26, color=MUTED)
    evidence, files = [], []
    for index, row in enumerate(report["records"]):
        geometry, result = row["geometry"], row["candidate"]
        if digest(geometry) != row["geometry_sha256"] or not verify_result(geometry, result)["passed"]:
            raise AssertionError("figure source is not independently valid")
        payload = rectangular_payload(geometry, result, row["document"])
        alias = next(a for a in row["aliases"] if a.get("history", "").startswith("guillotine-"))
        seed = alias["history"].removeprefix("guillotine-")
        title = f"{index + 1}. {seed} / 第{alias['step']}刀"
        x, y = 55 + 930 * (index % 2), 170 + 690 * (index // 2)
        canvas.text((x, y), title, size=29)
        canvas.text((x, y + 46), f"通过全部共边检查｜主动取名{result['choices']}次", size=24, color=MUTED)
        draw_adaptive(canvas, payload, (x, y + 100), 0.92)
        single = Canvas(1260, 980, args.font)
        single.text((55, 28), title + "：新候选规则合法完成", size=34)
        single.text((55, 87), "外侧1；按真实线段绘制，未删窄条；数字表示当前线侧名。", size=25, color=MUTED)
        draw_adaptive(single, payload, (55, 170), 1.2)
        if index == 0:
            # Match the exact narrow side highlighted in the user's manual case.
            x0, y0, x1, y1 = next(s["bounds"] for s in payload["sides"] if s["id"] == "15")
            single.line([(55 + x * 1.2, 170 + y * 1.2)
                         for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))],
                        color=LINE_ID, width=4)
            single.text((55, 913), f"蓝框：原受阻窄条，本次取{result['colors'][15]}；其他内部位置可复用1。", size=25, color=LINE_ID)
        else:
            single.text((55, 913), "固定一次运行，无回溯、无失败重试；未读取旧颜色。", size=25, color=MUTED)
        stem = f"case-{index + 1:02d}-{seed}-step{alias['step']}"
        files.extend(single.save(args.output_dir, stem))
        evidence.append({"key": row["key"], "geometry_sha256": row["geometry_sha256"],
                         "colors": result["colors"], "trace_sha256": digest(result["trace"]),
                         "payload": payload, "stem": stem})
    canvas.text((55, 2240), "六例定向验证，不是全图库通过或一般证明；同级方向与局部优先级是本轮固定约定。", size=25, color=MUTED)
    files.extend(canvas.save(args.output_dir, "six-completed"))
    write_report(args.output_dir / "manifest.json", {
        "input": {"filename": args.input.name, "sha256": file_sha(args.input)},
        "policy": report["policy"], "files": files, "evidence": evidence,
        "transform": "uniform scaling only; x-right/y-down; no omitted lines or regions",
        "palette": FILLS, "numeric_labels": True, "pillow_version": pillow_version,
        "contrast_ink_on_fills": {str(k): contrast(INK, v) for k, v in FILLS.items()},
        "scope": "Research-screen diagram, not a journal or accessibility certification",
        "alt_text": "Six exact rectangular maps newly colored with names 1 to 4. Each completed result passes all shared-boundary checks. The first map's previously blocked narrow strip now has name 3; internal name 1 is reused elsewhere.",
        "source_sha256": {p: file_sha(ROOT / p) for p in (
            "scripts/render_level_sides.py", "scripts/render_frontier_restart.py",
            "scripts/render_global_restart.py", "scripts/render_anchor_failure_cases.py")}})
    print({"figures": 7, "files": len(files), "directory": args.output_dir.name})


if __name__ == "__main__":
    main()

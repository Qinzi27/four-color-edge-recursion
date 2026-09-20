"""Render exact order-comparison traces from the saved research report.

Reuse the project's matched SVG/PNG Canvas. Coordinates in the lower schematic
illustrate containment, not measured geometry. No user's image is altered.
"""

from argparse import ArgumentParser
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.render_anchor_failure_cases import Canvas, MUTED, pillow_version

OUTER, INNER, GRID = "#B74400", "#00618A", "#E1E5EA"


def marker(canvas, xy, color, square=False):
    """Provide redundant shape encoding for readers with color-vision differences."""
    x, y = xy
    if square:
        canvas.draw.rectangle((x-4, y-4, x+4, y+4), fill=color)
        canvas.svg.append(f'<rect x="{x-4}" y="{y-4}" width="8" height="8" fill="{color}"/>')
    else:
        canvas.draw.ellipse((x-4, y-4, x+4, y+4), fill=color)
        canvas.svg.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{color}"/>')


def select(record, role, method="bfs"):
    """Use original labels and the smallest declared inner ID, never the best score."""
    root = record["case"]["outer"] if role == "outer" else record["case"]["inner_candidates"][0]
    return next(run for run in record["runs"] if run["root"] == root and
                run["method"] == method and run["label_seed"] is None)


def panel(canvas, record, x, title, ticks):
    """Plot linear, zero-based axes with an explicit distinct vertical range."""
    runs = [select(record, role) for role in ("outer", "inner")]
    n = record["case"]["n"]
    left, top, width, height = x + 65, 255, 465, 330
    canvas.text((x+285, 170), title, size=30, centered=True)
    for value in ticks:
        y = top + height * (1 - value / ticks[-1])
        canvas.line([(left, y), (left+width, y)], GRID, 2)
        canvas.text((left-16, y-13), str(value), size=20, centered=True)
    canvas.line([(left, top), (left, top+height), (left+width, top+height)], MUTED, 2)
    for step in sorted({1, n, (n+1)//2}):
        xx = left + width * (step-1)/(n-1)
        canvas.text((xx, top+height+12), str(step), size=22, centered=True)
    for run, color, square in zip(runs, (OUTER, INNER), (False, True)):
        points = [(left+width*i/(n-1), top+height*(1-row["labeled_states"]/ticks[-1]))
                  for i, row in enumerate(run["rows"])]
        for a, b in zip(points, points[1:]):
            canvas.line([a, b], color, 4, dashed=square)
        for point in points:
            marker(canvas, point, color, square)
    before, after = [run["summary"]["peak_labeled_states"] for run in runs]
    canvas.text((x+285, 650), f"峰值赋值数：{before} → {after}", size=28, centered=True)
    before, after = [run["summary"]["attempted_transitions"] for run in runs]
    canvas.text((x+285, 696), f"候选扩展次数：{before} → {after}", size=23, centered=True)


def rectangle(canvas, x, y, w, h):
    """A simple loop represents one real boundary, without coloring its region."""
    canvas.line([(x, y), (x+w, y), (x+w, y+h), (x, y+h), (x, y)], "#596774", 4)


def main():
    """Create new presentation artifacts with report/script hashes and semantics."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--palette-control", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--font", default="msyh.ttc")
    args = parser.parse_args()
    if any((args.output_dir/name).exists() for name in ("inside-out.png", "inside-out.svg", "manifest.json")):
        parser.error("output exists; choose a fresh directory")
    raw = args.input.read_bytes()
    report = json.loads(raw)
    if not report["passed"]:
        parser.error("requires a passing report")
    records = {row["case"]["key"]: row for row in report["results"]}
    control_raw = args.palette_control.read_bytes()
    control = json.loads(control_raw)
    if not control["passed"] or any(run["summary"]["peak_labeled_states"] != 2
                                   for entry in control["results"] if entry["family"] == "nested-jordan-tree"
                                   for run in entry["runs"]):
        parser.error("unexpected two-color control")
    canvas = Canvas(1900, 1570, args.font)
    canvas.text((55, 30), "从内侧起步：收益取决于分支结构和推进顺序", size=43)
    canvas.text((55, 102), "固定 4 种可用色名；原编号的广度优先（BFS）。纵轴是状态数，不是颜色数；各面板纵轴尺度不同。", size=25, color=MUTED)
    cases = (("nested-binary-depth-3", "15 面嵌套分支", [0, 100, 200, 300]),
             ("rectangular-cells-3x3", "3×3 格地图（含外面共 10 面）", [0, 200, 400, 600]),
             ("circle-rank-mask-7", "原图：三条蓝线齐全", [0, 4, 8, 12, 16]))
    for x, (key, title, ticks) in zip((40, 660, 1280), cases):
        panel(canvas, records[key], x, title, ticks)
    canvas.text((940, 760), "横轴：已处理的面数", size=24, centered=True, color=MUTED)
    canvas.line([(560, 814), (615, 814)], OUTER, 4)
    marker(canvas, (588, 814), OUTER)
    canvas.text((630, 798), "外面起步", size=25)
    canvas.line([(940, 814), (995, 814)], INNER, 4, dashed=True)
    marker(canvas, (968, 814), INNER, True)
    canvas.text((1010, 798), "最深面起步", size=25)
    canvas.line([(55, 870), (1845, 870)], GRID, 2)
    canvas.text((55, 900), "怎样改进推进顺序：先完成局部分支，再向外连接", size=34)
    canvas.text((55, 963), "下图是真实包含关系的示意：6 条独立闭环，共 7 个面。数字是面 ID。", size=24, color=MUTED)
    # Two disjoint parent loops, each containing two disjoint child loops.
    for x, parent, children in ((80, 1, (3, 4)), (400, 2, (5, 6))):
        rectangle(canvas, x, 1050, 275, 215)
        canvas.text((x+140, 1080), str(parent), size=30, centered=True)
        for xx, child in zip((x+27, x+160), children):
            rectangle(canvas, xx, 1140, 88, 84)
            canvas.text((xx+44, 1164), str(child), size=30, centered=True)
    canvas.text((380, 1286), "0：整个无界外面", size=26, centered=True)
    record = records["nested-binary-depth-2"]
    run = select(record, "inner", "min_frontier")
    if run["order"] != [3, 1, 4, 0, 2, 5, 6] or run["summary"]["peak_width"] != 1:
        parser.error("unexpected local-closure example")
    canvas.text((785, 1038), "可行顺序：3 → 1 → 4 → 0 → 2 → 5 → 6", size=32, color=INNER)
    canvas.text((785, 1110), "先完成左侧系统；每步最多保留 1 个对外边界面。", size=28)
    canvas.text((785, 1170), "精确最小峰值宽度：外面起步 2；最内起步 1。", size=28)
    canvas.text((785, 1230), "这给出了起点的真实优势，仍需选择合适的后续顺序。", size=27)
    canvas.text((55, 1370), "证据范围：63 图、1,917 次运行；完整状态诊断，不是线命名贪心算法的完备性证明。", size=26, color=MUTED)
    canvas.text((55, 1430), "关键对照：嵌套树若只用最少的 2 色，内外起点的状态峰值都为 2，候选扩展次数也相同。", size=28, color=INNER)
    canvas.text((55, 1488), "因此，边界宽度的差异真实存在；状态数收益还取决于允许多少色名。", size=27, color=MUTED)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = canvas.save(args.output_dir, "inside-out")
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input": {"filename": args.input.name, "sha256": sha256(raw).hexdigest()},
        "palette_control": {"filename": args.palette_control.name, "sha256": sha256(control_raw).hexdigest()},
        "source_sha256": {name: sha256((ROOT/name).read_bytes()).hexdigest() for name in
                          ("scripts/render_inside_out.py", "scripts/render_anchor_failure_cases.py")},
        "selection": "Three explicit examples; original-label BFS, smallest declared inner ID (not best score)",
        "axes": "Linear, zero-based y axes with different visible ranges; x is processed face count",
        "lower_diagram": "Schematic nested rectangles with face IDs; not vertex/color labels or measurements",
        "font": args.font, "pillow_version": pillow_version, "artifacts": artifacts,
    }
    with (args.output_dir/"manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"artifacts": artifacts}, ensure_ascii=False))


if __name__ == "__main__":
    main()

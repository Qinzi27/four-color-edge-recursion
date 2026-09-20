"""Plot certified contour repairs and a strict single-cycle descent obstruction.

All edge selections and obstruction counts come from the validation report.
Coordinates are new schematic layouts, not geometric measurements of a photo.
Reuse the repository's matched SVG/PNG primitives; Pillow is presentation-only.
"""

from argparse import ArgumentParser
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import cos, sin, pi
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.render_anchor_failure_cases import Canvas, MUTED, pillow_version

FIRST = "#973A79"
REMOVE = "#B74400"
ADD = "#007861"
GRAY = "#B8C0C8"
INK = "#25323D"


def circle(canvas, point, radius, fill):
    """Draw matching node markers with explicit radius and no inferred data."""
    x, y = point
    canvas.draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=fill)
    canvas.svg.append(f'<circle cx="{x:g}" cy="{y:g}" r="{radius:g}" fill="{fill}"/>')


def layout(kind, origin):
    """Fix equal angular spacing and record layout independently of edge cost."""
    count = 5 if kind == "prism5" else 8
    outer = [(origin[0] + 150*cos(-pi/2+2*pi*i/count),
              origin[1] + 150*sin(-pi/2+2*pi*i/count)) for i in range(count)]
    if kind == "wheel8":
        return outer + [origin]
    inner = [(origin[0] + 75*cos(-pi/2+2*pi*i/count),
              origin[1] + 75*sin(-pi/2+2*pi*i/count)) for i in range(count)]
    return outer + inner


def draw_graph(canvas, case, first, kind, origin, change=()):
    """Render first-layer membership, with optional addition/removal overlay."""
    points = layout(kind, origin)
    selected = set(first)
    for edge_id, (a, b) in enumerate(case["edges"]):
        canvas.line([points[a], points[b]], FIRST if edge_id in selected else GRAY,
                    6 if edge_id in selected else 3)
    for edge_id in change:
        a, b = case["edges"][edge_id]
        canvas.line([points[a], points[b]], REMOVE if edge_id in selected else ADD,
                    7, dashed=edge_id in selected)
    degrees = [0] * len(points)
    for edge_id in selected:
        a, b = case["edges"][edge_id]
        degrees[a] += 1
        degrees[b] += 1
    for v, point in enumerate(points):
        circle(canvas, point, 7 if degrees[v] == 0 else 4,
               REMOVE if degrees[v] == 0 else INK)
        if kind == "wheel8":
            dx, dy = point[0]-origin[0], point[1]-origin[1]
            label = (point[0]+dx*0.16, point[1]+dy*0.16-12)
            if v == 8:
                label = (point[0]+21, point[1]-34)
            canvas.text(label, str(v), size=23, centered=True)


def main():
    """Write a traceable, non-overwriting figure pair from passing evidence."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--font", default="msyh.ttc")
    args = parser.parse_args()
    names = ("circle-repair.png", "circle-repair.svg", "manifest.json")
    if any((args.output_dir / name).exists() for name in names):
        parser.error("Output exists; choose a fresh directory")
    raw = args.input.read_bytes()
    report = json.loads(raw)
    cases = report["show_cases"]
    prism, wheel = cases["prism5"], cases["wheel8"]
    if prism["q_trace"] != [2, 0] or wheel["q_trace"] != [2, 2, 0]:
        parser.error("Unexpected obstruction-count evidence")
    canvas = Canvas(1900, 1410, args.font)
    canvas.text((55, 30), "圈可以怎样重组：一个可证明的修复，以及一条失败的规则", size=42)
    canvas.text((55, 101), "粉线＝第一层 A；灰线＝其他已有边。q 是无法配对的奇分量数，q＝0 才能补出第二层。", size=26, color=MUTED)
    canvas.text((55, 160), "① 两圈＋奇数条径向连接：翻一个环带面就能修好", size=34)
    xs = (315, 950, 1585)
    titles = ("两个原圈：q＝2", "移出两段圈弧，加入两条径向边", "合为大圈：q＝0")
    for x, title in zip(xs, titles):
        canvas.text((x, 225), title, size=27, centered=True)
    draw_graph(canvas, prism, prism["initial_first_layer"], "prism5", (xs[0], 455))
    draw_graph(canvas, prism, prism["initial_first_layer"], "prism5", (xs[1], 455), prism["move"])
    draw_graph(canvas, prism, prism["final_first_layer"], "prism5", (xs[2], 455))
    canvas.text((xs[0], 635), "图示 k＝5；结论适用于任意奇数 k≥3", size=23, centered=True)
    canvas.text((xs[1], 635), "橙虚线：移出 A　　绿实线：加入 A", size=23, centered=True)
    canvas.text((xs[2], 635), "未细分、单位代价时：最少改 4 条边", size=23, centered=True)
    canvas.line([(55, 700), (1845, 700)], "#D4D9DE", 2)
    canvas.text((55, 735), "② 八轮缘轮图：需要跨过平台，或同时翻转两个面", size=34)
    titles = ("初始：q＝2", "先翻三角面 2–3–8：q 仍为 2", "再翻三角面 6–7–8：q＝0")
    for x, title in zip(xs, titles):
        canvas.text((x, 804), title, size=27, centered=True)
    for x, key in zip(xs, ("initial_first_layer", "intermediate_first_layer", "final_first_layer")):
        draw_graph(canvas, wheel, wheel[key], "wheel8", (x, 1035))
    canvas.text((xs[0], 1230), "全部 57 个单简单圈：没有严格改善", size=23, centered=True)
    canvas.text((xs[1], 1230), "奇孤点 7 仍在；连通大块也变成奇分量", size=23, centered=True)
    canvas.text((xs[2], 1230), "两面只共中心；最少净改动恰为 6 条边", size=23, centered=True)
    canvas.text((55, 1320), "边界：图类定理与明确反例；不代表任意地图都可局部修复。坐标仅作示意，不用于长度或权重测量。", size=25, color=MUTED)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = canvas.save(args.output_dir, "circle-repair")
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input": {"filename": args.input.name, "sha256": sha256(raw).hexdigest()},
        "source_sha256": {p: sha256((ROOT/p).read_bytes()).hexdigest() for p in
                          ("scripts/render_circle_repair.py", "scripts/render_anchor_failure_cases.py")},
        "coordinates": "schematic equal-angle y-down layouts; outer radius150, inner radius75; not edge costs",
        "semantics": "edge membership in A, not final face coloring; q is odd-component count",
        "font": args.font, "pillow_version": pillow_version, "artifacts": artifacts,
    }
    with (args.output_dir/"manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"artifacts": artifacts}, ensure_ascii=False))


if __name__ == "__main__":
    main()

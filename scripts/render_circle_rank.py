"""Render the verified circle/connector example as a schematic research figure.

This is a new diagram from declared coordinates, not an edit or pixel tracing of
the user's screenshot. Reuse the repository's shared SVG/PNG drawing primitives;
Pillow is needed only for this optional presentation script, not the core solver.
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


PINK = "#963572"
BLUE = "#0066AE"
GREEN = "#007861"
PALE_BLUE = "#D9E8F5"
PALE_GOLD = "#F6DEAA"
OUTSIDE = "#FFFFFF"


def polygon(canvas, points, fill):
    """Fill an explicitly supplied polygon in both formats before drawing edges."""
    canvas.draw.polygon(points, fill=fill)
    encoded = " ".join(f"{x:g},{y:g}" for x, y in points)
    canvas.svg.append(f'<polygon points="{encoded}" fill="{fill}" '
                      'fill-rule="evenodd"/>')


def draw_map(canvas, row, origin, scale, layer=None):
    """Use only recorded real edges; virtual face-bookkeeping links are omitted."""
    geometry = row["geometry"]

    def point(p):
        """Preserve the recorded y-down coordinate system and aspect ratio."""
        return origin[0] + p[0] * scale, origin[1] + p[1] * scale

    if layer is None:
        polygon(canvas, [point(p) for p in ((0, 0), (900, 0), (900, 600), (0, 600))], PALE_BLUE)
        if row["blue_mask"] == 7:
            face = row["role_face_ids"]["upper"]
            polygon(canvas, [point(p) for p in geometry["face_points"][face]], PALE_GOLD)
        # Island interiors are separate faces and share the exterior color.
        for role in ("left_island", "right_island"):
            face = row["role_face_ids"][role]
            polygon(canvas, [point(p) for p in geometry["face_points"][face]], OUTSIDE)

    selected = set(row["contour_edge_ids"][layer]) if layer else set()
    pink = set(row["contour_edge_ids"]["A_all_pink"])
    for edge_id, edge in enumerate(geometry["edges"]):
        if edge["virtual"]:
            continue
        color = (PINK if edge_id in pink else BLUE) if layer is None else "#BBC1C7"
        width = 4 if layer is None else 3
        if layer and edge_id in selected:
            color = PINK if layer == "A_all_pink" else GREEN
            width = 7
        canvas.line([point(geometry["vertices"][edge[k]]) for k in ("a", "b")], color, width)

    if layer is None:
        labels = {"left_island": (240, 265), "right_island": (660, 265),
                  "upper": (450, 100), "lower": (450, 475)}
        for role, p in labels.items():
            bits = row["role_bits"][role]
            color_id = 1 if bits == [0, 0] else (3 if bits == [1, 1] else 2)
            canvas.text(point(p), str(color_id), size=35, centered=True)
        canvas.text((origin[0], origin[1] - 38), "外面也计入着色：1", size=23, color=MUTED)
    return point


def main():
    """Create a matched SVG/PNG pair and source manifest without overwriting."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--font", default="msyh.ttc", help="CJK font name or path")
    args = parser.parse_args()
    for name in ("circle-rank.png", "circle-rank.svg", "manifest.json"):
        if (args.output_dir / name).exists():
            parser.error("Output already exists; choose a fresh directory")
    raw = args.input.read_bytes()
    report = json.loads(raw)
    rows = {row["blue_mask"]: row for row in report["results"]}
    if set(rows) != set(range(8)) or not all(row["passed"] for row in rows.values()):
        parser.error("Expected the complete passing eight-case report")
    canvas = Canvas(1900, 1370, args.font)
    canvas.text((55, 30), "先连通，再闭合：三条蓝线怎样把两色变成三色", size=43)
    canvas.text((55, 100), "按粉色为原边界、蓝色为新增边界、绿色为辅助圈理解；以下是拓扑示意，非原图描摹。", size=26, color=MUTED)
    panels = ((0, 55, "① 没有蓝线", "3 个连通分量 · 4 个面 · 最少 2 色"),
              (3, 680, "② 已有两条蓝线", "1 个连通分量 · 4 个面 · 最少 2 色"),
              (7, 1305, "③ 三条蓝线齐全", "1 个连通分量 · 5 个面 · 最少 3 色"))
    for mask, x, title, caption in panels:
        canvas.text((x, 165), title, size=30)
        draw_map(canvas, rows[mask], (x, 255), 0.6)
        canvas.text((x, 635), caption, size=24)
    canvas.text((55, 682), "两条蓝线都是桥：仍可绕过缺口，上下是同一个面。最后一条闭合后，三条蓝线才都成为面分界。", size=26)
    canvas.line([(55, 740), (1845, 740)], "#D3D7DC", 2)
    canvas.text((55, 775), "把圈作为二进制边界层：跨过该层，翻转对应的一位", size=34)
    canvas.text((55, 840), "层 A：三个粉圈的并集", size=28, color=PINK)
    canvas.text((680, 840), "层 B：上方面的完整边界", size=28, color=GREEN)
    draw_map(canvas, rows[7], (55, 900), 0.6, "A_all_pink")
    draw_map(canvas, rows[7], (680, 900), 0.6, "B_upper_boundary")
    canvas.text((1305, 850), "跨圈奇偶 → 色块身份", size=28)
    table = (("外面、两个小岛", "00 → 颜色 1"),
             ("下方背景", "10 → 颜色 2"),
             ("上方背景", "11 → 颜色 3"))
    for y, (name, bits) in zip((920, 1000, 1080), table):
        canvas.text((1305, y), name, size=25)
        canvas.text((1585, y), bits, size=25)
    canvas.text((1305, 1170), "独立环数 β = 4", size=25)
    canvas.text((1305, 1210), "边界层数 = 2，实际颜色数 = 3", size=25)
    canvas.text((55, 1300), "绿色描的是已有边的组合，不增加新边。两层最多表示四种颜色；本图只用到其中三种。", size=25, color=MUTED)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    records = canvas.save(args.output_dir, "circle-rank")
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "figure_kind": "schematic topology from an explicit eight-case geometry report",
        "assumption": "Pink and blue are map boundaries; green is an auxiliary contour",
        "coordinate_system": "arbitrary schematic units; y down; uniform scale 0.6",
        "photo_policy": "No screenshot pixels edited or traced; no metric measurements inferred",
        "input": {"filename": args.input.name, "sha256": sha256(raw).hexdigest()},
        "source_sha256": {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in
                          ("scripts/render_circle_rank.py", "scripts/render_anchor_failure_cases.py")},
        "cases": [0, 3, 7], "font": args.font, "pillow_version": pillow_version,
        "colors": {"pink_boundary": PINK, "blue_connector": BLUE, "green_layer": GREEN,
                   "face_1": OUTSIDE, "face_2": PALE_BLUE, "face_3": PALE_GOLD},
        "artifacts": records,
    }
    with (args.output_dir / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"output_directory": str(args.output_dir), "artifacts": records}, ensure_ascii=False))


if __name__ == "__main__":
    main()

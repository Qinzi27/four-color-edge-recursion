"""Render two actual stopped histories as exact diagrams for manual annotation.

This presentation-only script never chooses a new color or changes the recorded
experiment. Pillow is optional for this figure tool; the core remains stdlib-only.
SVG and PNG share the same drawing commands and preserve the source aspect ratio.
"""

from argparse import ArgumentParser
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
from math import hypot
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont, __version__ as pillow_version

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.audit_anchor_stops import classify


INK = "#202831"
MUTED = "#505B67"
NEW = "#B74400"
LINE_ID = "#00618A"
CASES = (
    ("A", 20260923, "right", "common_anchor_only_in_new_child",
     "新子侧可以接任公共锚；当前规则只接受未被切开的旧侧"),
    ("B", 20261027, "left", "outside_not_universal",
     "出现不接外圈的内部侧；外圈不再邻接每一个侧"),
)


class Canvas:
    """Emit matching raster/vector primitives without editing any source image."""

    def __init__(self, width, height, font_name):
        self.width, self.height = width, height
        self.font_name = font_name
        self.image = Image.new("RGB", (width, height), "white")
        self.draw = ImageDraw.Draw(self.image)
        self.svg = [f'<svg xmlns="http://www.w3.org/2000/svg" '
                    f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
                    '<rect width="100%" height="100%" fill="white"/>']

    def line(self, points, color=INK, width=4, dashed=False):
        """Use the same explicit dash segments in both output formats."""
        if dashed:
            start, end = points
            length = hypot(end[0] - start[0], end[1] - start[1])
            position = 0.0
            while position < length:
                stop = min(position + 14, length)
                part = [(start[0] + (end[0] - start[0]) * t / length,
                         start[1] + (end[1] - start[1]) * t / length)
                        for t in (position, stop)]
                self.line(part, color, width)
                position += 23
            return
        self.draw.line(points, fill=color, width=width)
        encoded = " ".join(f"{x:g},{y:g}" for x, y in points)
        self.svg.append(f'<polyline points="{encoded}" fill="none" '
                        f'stroke="{color}" stroke-width="{width}"/>')

    def text(self, xy, value, size=26, color=INK, centered=False):
        """Keep SVG labels searchable, with PNG as the font-stable preview."""
        font = ImageFont.truetype(self.font_name, size)
        x, y = xy
        self.draw.text((x, y), value, font=font, fill=color,
                       anchor="mt" if centered else "lt")
        anchor = "middle" if centered else "start"
        self.svg.append(f'<text x="{x:g}" y="{y:g}" font-size="{size}" '
                        f'font-family="Microsoft YaHei,Noto Sans CJK SC,sans-serif" '
                        f'text-anchor="{anchor}" dominant-baseline="text-before-edge" '
                        f'fill="{color}">{escape(value)}</text>')

    def save(self, directory, stem):
        """All target names are checked before rendering; never overwrite them."""
        png, svg = directory / f"{stem}.png", directory / f"{stem}.svg"
        with png.open("xb") as stream:
            self.image.save(stream, format="PNG")
        with svg.open("x", encoding="utf-8") as stream:
            stream.write("\n".join(self.svg + ["</svg>"]) + "\n")
        return [{"filename": path.name, "sha256": sha256(path.read_bytes()).hexdigest(),
                 "width_px": self.width, "height_px": self.height}
                for path in (png, svg)]


def draw_map(canvas, state, origin, scale, pending=None, names=False, ids=False):
    """Plot y-down recorded coordinates without stretching or inferred contacts."""
    def point(p):
        return origin[0] + p[0] * scale, origin[1] + p[1] * scale

    width, height = state["width"], state["height"]
    canvas.line([point(p) for p in ((0, 0), (width, 0), (width, height),
                                    (0, height), (0, 0))], width=5)
    for index, cut in enumerate(state["cuts"], 1):
        canvas.line([point(p) for p in cut])
        if ids:
            (x0, y0), (x1, y1) = cut
            if x0 == x1:
                # These are construction-line IDs, not endpoint or color names.
                pos = point((x0 + 12, y0 + (y1 - y0) * 0.08))
            else:
                pos = point((x0 + (x1 - x0) * 0.09, y0 - 34))
            canvas.text(pos, f"L{index}", size=23, color=LINE_ID)
    if names:
        for side in state["sides"]:
            x0, y0, x1, y1 = side["bounds"]
            x, y = point(((x0 + x1) / 2, (y0 + y1) / 2))
            canvas.text((x, y - 23), str(side["symbol"]), size=43, centered=True)
    if pending is not None:
        canvas.line([point(p) for p in pending], color=NEW, width=5, dashed=True)


def select_case(report, seed, inherit, expected_category):
    """Use the full composite key: strip histories can reuse a guillotine seed."""
    matches = [row for row in report["runs"] if row["family"] == "guillotine"
               and row["seed"] == seed and row["inherit"] == inherit]
    if len(matches) != 1:
        raise ValueError("Expected exactly one guillotine history for the selected key")
    row = matches[0]
    classification = classify(row)
    if classification["category"] != expected_category:
        raise ValueError("Selected history no longer has the documented stop category")
    old, proposed, event = row["last_valid_state"], row["last_proposed_state"], row["events"][-1]
    if row["status"] != "blocked_sync_required" or event["step"] != len(old["cuts"]) + 1:
        raise ValueError("Not the recorded first stopped step")
    if proposed["cuts"] != old["cuts"] + [event["cut"]]:
        raise ValueError("New geometry must be precisely old lines plus the pending line")
    if not all(1 <= side["symbol"] <= 4 for side in old["sides"]):
        raise ValueError("Only committed four-name values may be shown")
    return row, classification


def main():
    """Export labelled/blank pairs with input hashes and portable source records."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--font", default="msyh.ttc", help="A CJK font name or path")
    args = parser.parse_args()
    # Fail before any file write if the optional font is unavailable.
    font_family = ImageFont.truetype(args.font, 26).getname()
    filenames = [f"case-{letter.lower()}-{kind}.{extension}"
                 for letter, *_ in CASES for kind in ("overview", "blank")
                 for extension in ("png", "svg")] + ["manifest.json"]
    if any((args.output_dir / name).exists() for name in filenames):
        parser.error("Output exists; use a new output directory (no overwrites)")
    raw = args.input.read_bytes()
    source = json.loads(raw)
    selected = [(case, *select_case(source, case[1], case[2], case[3])) for case in CASES]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for (letter, seed, inherit, category, description), row, diagnosis in selected:
        state, event = row["last_valid_state"], row["events"][-1]
        step = event["step"]
        overview = Canvas(1900, 920, args.font)
        overview.text((60, 35), f"案例 {letter}  /  第 {step} 条内部线加入时停住", size=44)
        overview.text((60, 105), description, size=27, color=MUTED)
        overview.text((60, 167), "加线前：当前线侧名字（允许重命名）", size=29)
        overview.text((1010, 167), "加线后：空白图，请按你的规则标记", size=29)
        overview.text((60, 213), "外侧：1", size=23, color=MUTED)
        overview.text((1010, 213), "外侧：留给你标记", size=23, color=MUTED)
        draw_map(overview, state, (60, 260), 0.9, names=True, ids=True)
        draw_map(overview, state, (1010, 260), 0.9, pending=event["cut"])
        overview.line([(1010, 829), (1080, 829)], color=NEW, width=5, dashed=True)
        overview.text((1100, 815), f"新增 L{step}；其余实线为已有线", size=25)
        overview.text((60, 815), "L 是画线顺序编号；数字是侧名，不是端点名。", size=24, color=MUTED)
        overview.text((60, 871), f"记录：guillotine / seed {seed} / inherit {inherit}。只说明当前规则停住，不是四名不可能。",
                      size=24, color=MUTED)
        blank = Canvas(1200, 1050, args.font)
        blank.text((60, 38), f"案例 {letter}｜人工标记空白图", size=40)
        blank.text((60, 107), f"加入 L{step} 后，请填写线的两侧名字与母线继承关系。", size=26)
        blank.text((60, 163), "旧名不锁定；若更换锚或命名顺序，请用箭头说明。", size=25, color=MUTED)
        # A uniform scale keeps the exact 900:600 canvas ratio.
        draw_map(blank, state, (105, 265), 1.1, pending=event["cut"])
        blank.line([(105, 978), (175, 978)], color=NEW, width=5, dashed=True)
        blank.text((195, 964), f"新增 L{step}；实线为旧线。外侧名字也请标出。", size=26)
        files = overview.save(args.output_dir, f"case-{letter.lower()}-overview")
        files += blank.save(args.output_dir, f"case-{letter.lower()}-blank")
        records.append({"case": letter, "family": row["family"], "seed": seed,
                        "inherit": inherit, "stopped_step": step, "category": category,
                        "current_committed_state": state, "pending_cut": event["cut"],
                        "stop_structure": {key: diagnosis[key] for key in
                                           ("outside_missing", "outside_missing_bounds", "universal_old_ids")},
                        "new_child_anchor_ids": [c["id"] for c in diagnosis["universal_new_children"]],
                        "presentation": "Old names shown only before the cut; new geometry is blank. No diagnostic fifth name drawn.",
                        "files": files})
    manifest = {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "input": {"filename": args.input.name, "sha256": sha256(raw).hexdigest()},
                "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
                "pillow_version": pillow_version, "font_family": font_family,
                "coordinates": "Source x-right, y-down; exact uniform scaling, no geometric simplification.",
                "cases": records}
    with (args.output_dir / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"cases": len(records), "image_files": sum(len(r["files"]) for r in records),
                      "input_sha256": manifest["input"]["sha256"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

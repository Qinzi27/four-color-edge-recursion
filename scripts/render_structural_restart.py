"""Draw the actual v2 failure beside a checked structural naming completion.

Reuse the project's rectangle conversion and common raster/vector primitives.
The failed panel has side identities only; no inconsistent draft is filled as
if it were a complete coloring. This is a single-case rerun demonstration,
optionally hash-matched to a completed formal full-corpus report.
"""

from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path
import sys

from PIL import Image, ImageFont, __version__ as pillow_version

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.structural_restart import POLICY, restart_structural_names
from scripts.render_anchor_failure_cases import Canvas, INK, MUTED, NEW, LINE_ID
from scripts.render_frontier_restart import draw_adaptive
from scripts.render_global_restart import rectangular_payload
from scripts.validate_frontier_restart import file_sha, read_json
from scripts.validate_global_restart import digest, write_report
from scripts.validate_level_sides_peer import verify_run as verify_old_run
from scripts.validate_structural_restart import verify_run
from scripts.validate_structural_restart_full import SOURCE, SOURCE_SHA256, source_hashes

KEY = "8070783fd68de9a9dd22c6d4c8831a55c330290f4a30e2e9c8f6edb70af66132"
RENDER_SOURCES = (
    "scripts/render_structural_restart.py", "scripts/render_anchor_failure_cases.py",
    "scripts/render_frontier_restart.py", "scripts/render_global_restart.py",
)
CAPTION = (
    "同一张 guillotine-20261213 第17步地图的两种命名状态。左图仅标实际侧身份；"
    "旧v2在外侧S0取1、S1取2后，尝试给S10取2而冲突。右图由结构关系检查规则"
    "从该几何独立生成完整合法命名：先证明S1与S10异名，再给S10取3。"
    "橙色轮廓标记两张图中的同一对侧；浅色填充只辅助右图的数字名字。"
    "几何按同一比例绘制、没有删线；本图是单图演示，不是全库成功率或一般完备性证明。"
)


def require(condition, message):
    """Keep scientific evidence checks active independently of assertions."""
    if not condition:
        raise ValueError(message)


class IdentityLabels:
    """Adapt only blank labels while reusing the existing exact map renderer.

    ``draw_adaptive(blank=True)`` emits one question mark per rectangle. This
    adapter replaces those marks by declared side identities and fits their
    text width. All line, rectangle and SVG operations use the original Canvas.
    """

    def __init__(self, canvas, payload, scale):
        self.canvas, self.rows, self.scale = canvas, iter(payload["sides"]), scale

    def __getattr__(self, name):
        return getattr(self.canvas, name)

    def text(self, xy, value, size=26, color=INK, centered=False):
        """Replace only the explicitly blank adaptive label, not other text."""
        require(value == "?", "unexpected label from the blank rectangle renderer")
        side = next(self.rows)
        label = "S" + side["id"]
        width = (side["bounds"][2] - side["bounds"][0]) * self.scale - 8
        font = ImageFont.truetype(self.canvas.font_name, size)
        while font.getlength(label) > width and size > 8:
            size -= 1
            font = ImageFont.truetype(self.canvas.font_name, size)
        self.canvas.text(xy, label, size=size, color=color, centered=centered)


def highlight_sides(canvas, payload, origin, scale, show_id):
    """Outline the exact same two rectangles and retain the true boundaries."""
    for side in payload["sides"]:
        if side["id"] not in ("1", "10"):
            continue
        x0, y0, x1, y1 = side["bounds"]
        points = [(origin[0] + x * scale, origin[1] + y * scale)
                  for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))]
        canvas.line(points, color=NEW, width=5)
        if show_id:
            canvas.text((points[0][0] + 10, points[0][1] + 7), "S" + side["id"],
                        size=20, color=NEW)


def main():
    """Check the original input, rerun once, then save new PNG/SVG and evidence."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=SOURCE)
    parser.add_argument("--full-report", type=Path,
                        default=ROOT / "outputs/structural-restart-full-2026-09-21.json.gz")
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "docs/figures/structural-restart-2026-09-21")
    parser.add_argument("--font", default="msyh.ttc")
    args = parser.parse_args()
    require(not args.output_dir.exists(), "choose a fresh figure directory")
    require(file_sha(args.input) == SOURCE_SHA256, "not the frozen original v2 report")
    font_family = ImageFont.truetype(args.font, 24).getname()
    previous = read_json(args.input)
    hashes = source_hashes(previous)
    hashes.update({name: file_sha(ROOT / name) for name in RENDER_SOURCES})
    case = previous["least_conflict"]
    require(case["key"] == KEY and case["face_count"] == 19, "wrong displayed case")
    geometry, old = case["geometry"], case["outcome"]
    geometry_hash = digest(geometry)
    old_check = verify_old_run(geometry, old)
    require(old_check["passed"] and old["status"] == "conflict", "old failure did not verify")
    require(len(old["trace"]) == 1 and old["trace"][0]["side"] == 10
            and old["trace"][0]["symbol"] == 2, "old proposed same-name choice changed")
    current = restart_structural_names(geometry)
    current_check = verify_run(geometry, current)
    require(digest(geometry) == geometry_hash, "naming mutated the plotted geometry")
    require(current_check["passed"] and current["status"] == "solved", "new result is not verified complete")
    require((current["colors"][1], current["colors"][10]) == (2, 3), "highlighted actual names changed")
    require(current["events"][0]["kind"] == "learn_relation"
            and current["events"][0]["learned_pair"] == [1, 10], "displayed inequality was not learned")
    require(current["propagation_phases"][0]["anchors_by_dart"] ==
            current["propagation_phases"][1]["anchors_by_dart"], "refuted proposal was committed")
    matching = {"checked": False, "reason": "formal-full-report-not-yet-present"}
    if args.full_report.exists():
        formal = read_json(args.full_report)
        require(formal["full_corpus_run"] and formal["policy"] == POLICY, "comparison report is not formal full run")
        row = next(row for row in formal["drawings"] if row["key"] == KEY)
        require(row["geometry_sha256"] == geometry_hash, "formal geometry differs")
        require(row["runs"][POLICY]["full_transcript_sha256"] == digest(current),
                "single-case transcript differs from formal full run")
        matching = {"checked": True, "filename": args.full_report.name,
                    "sha256": file_sha(args.full_report), "full_transcript_sha256": digest(current)}
    blank = rectangular_payload(geometry, old, case["document"])
    colored = rectangular_payload(geometry, current, case["document"])
    require([(s["id"], s["bounds"]) for s in blank["sides"]] ==
            [(s["id"], s["bounds"]) for s in colored["sides"]], "panel geometry differs")
    canvas = Canvas(1640, 1010, args.font)
    canvas.text((55, 30), "先证明两个侧能否同名，再落下具体名字", size=39)
    canvas.text((55, 96), "guillotine-20261213，第17步｜同一几何、同一初始规范化｜回到线侧重新命名主线", size=25, color=MUTED)
    canvas.text((55, 153), "A  旧 v2：同名提议导致冲突", size=29)
    canvas.text((855, 153), "B  加入结构关系：完成合法命名", size=29)
    canvas.text((55, 205), "旧尝试：S1=2，S10=2 → 冲突", size=25, color=NEW)
    canvas.text((855, 205), "已证 c1≠c10；实际取 S1=2，S10=3", size=24, color=LINE_ID)
    canvas.text((55, 251), "外侧 S0 的名字为1；内部仅显示侧身份", size=23, color=MUTED)
    canvas.text((855, 251), "外侧名字为1；内部数字为实际名字", size=23, color=MUTED)
    origins, scale = ((55, 300), (855, 300)), 0.79
    draw_adaptive(IdentityLabels(canvas, blank, scale), blank, origins[0], scale, blank=True)
    draw_adaptive(canvas, colored, origins[1], scale)
    highlight_sides(canvas, blank, origins[0], scale, show_id=False)
    highlight_sides(canvas, colored, origins[1], scale, show_id=True)
    canvas.text((55, 806), "关键关系：S1 与 S10 没有直接共边，但整张线网迫使它们异名。", size=29, color=LINE_ID)
    canvas.text((55, 863), "左图保持未命名状态；右图从该几何实际生成，并逐条核验全部真实边界。", size=26)
    canvas.text((55, 916), "橙框仅标出同一对侧。两个面板等比例绘制；浅色与数字共同表示右图的名字。", size=24, color=MUTED)
    canvas.text((55, 959), "单图演示｜19个侧（含外侧），55条原边｜不据此主张一般完备性或原创性。", size=23, color=MUTED)
    require(all(file_sha(ROOT / name) == value for name, value in hashes.items()),
            "source changed while producing the checked figure")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    files = canvas.save(args.output_dir, "same-name-before-commit")
    with (args.output_dir / "caption.md").open("x", encoding="utf-8") as stream:
        stream.write(CAPTION + "\n")
    # Inspect actual saved file metadata, not only intended dimensions.
    with Image.open(args.output_dir / "same-name-before-commit.png") as raster:
        raster_metadata = {"size": list(raster.size), "mode": raster.mode, "format": raster.format}
    svg = (args.output_dir / "same-name-before-commit.svg").read_text(encoding="utf-8")
    require("<image" not in svg, "SVG should contain vector primitives only")
    manifest = {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "scope": "single-case-rerun-demonstration", "not_a_full_corpus_result": True,
                "input": {"filename": args.input.name, "sha256": SOURCE_SHA256},
                "key": KEY, "aliases": case["aliases"], "geometry_sha256": geometry_hash,
                "geometry": geometry, "document": case["document"],
                "old_result_sha256": digest(old), "old_failure_check": old_check,
                "new_policy": POLICY, "new_result": current, "new_result_sha256": digest(current),
                "new_result_check": current_check, "formal_full_report_match": matching,
                "drawings": {"left_blank_identity_only": blank, "right_actual_names": colored},
                "coordinates": "Exact uniform scale 0.79; original screen x-right/y-down; no simplification.",
                "palette": "Original project qualitative FILLS; labels repeat every actual name.",
                "source_sha256": hashes, "source_sha256_end": hashes,
                "files": files, "png_metadata": raster_metadata, "svg_embedded_rasters": 0,
                "font_family": font_family, "font_file_name": Path(args.font).name,
                "font_embedding": "SVG text remains searchable; CJK glyphs depend on the installed font.",
                "pillow_version": pillow_version, "python_version": sys.version.split()[0],
                "caption_zh": CAPTION, "alt_text_zh": CAPTION,
                "destination": "Research discussion; no publisher or print-size specification.",
                "statistical_uncertainty": "Not applicable: exact geometry and one checked naming transcript."}
    write_report(args.output_dir / "manifest.json", manifest)
    print({"files": files, "independent_check": current_check["passed"],
           "formal_full_report_match": matching, "png_metadata": raster_metadata})


if __name__ == "__main__":
    main()

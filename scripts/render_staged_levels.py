"""Render exact v3 evidence without changing geometry, labels or naming rules.

Reuse the established rectangle renderer and show numeric color names alongside
the qualitative fills. Failed attempts remain uncolored manual-annotation maps;
an older legal coloring is an explicitly separate archived witness, never v3's
answer. The manifest retains source hashes, exact geometry and proof checks.
"""

from argparse import ArgumentParser
from math import ceil
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.level_sides_peer import POLICY as BASELINE
from fourcolor.staged_levels import POLICY, restart_staged_level_names
from scripts.render_anchor_failure_cases import Canvas, INK, LINE_ID, MUTED, pillow_version
from scripts.render_frontier_restart import draw_adaptive
from scripts.render_global_restart import FILLS, rectangular_payload
from scripts.render_level_sides import contrast
from scripts.validate_frontier_restart import file_sha, json_value, read_json, verify_result
from scripts.validate_global_restart import digest, write_report
from scripts.validate_relation_frontier_full import require
from scripts.validate_staged_levels import verify_run

BLUE_KEY = "8070783fd68de9a9dd22c6d4c8831a55c330290f4a30e2e9c8f6edb70af66132"
DEFAULT_INPUT = ROOT / "outputs/staged-levels-full-2026-09-19.json.gz"
RENDER_SOURCES = ("scripts/render_staged_levels.py", "scripts/render_anchor_failure_cases.py",
                  "scripts/render_frontier_restart.py", "scripts/render_global_restart.py",
                  "scripts/render_level_sides.py")
ORIGIN, SCALE = (55, 220), 1.1


def checked_case(report, key):
    """Reproduce native dart keys and check every illustrated proof and hash."""
    detail = report["detailed_examples"][key]
    row = next(item for item in report["drawings"] if item["key"] == key)
    geometry = detail["geometry"]
    result = restart_staged_level_names(geometry)
    require(json_value(result) == detail["outcome"], "illustrated rerun differs from full certificate")
    require(digest(geometry) == row["geometry_sha256"], "illustration geometry hash changed")
    require(digest(result) == row["runs"][POLICY]["raw_result_sha256"], "illustration result hash changed")
    check = verify_run(geometry, result)
    require(check["passed"] and json_value(check) == detail["verification"], "illustration proof replay changed")
    payload = rectangular_payload(geometry, result, detail["document"])
    return detail, row, result, check, payload


def highlight_retained(canvas, payload, initialization):
    """Outline an existing side boundary, not a new dividing line."""
    chosen = next(side for side in payload["sides"] if int(side["id"]) == initialization["side"])
    x0, y0, x1, y1 = chosen["bounds"]
    canvas.line([(ORIGIN[0] + x * SCALE, ORIGIN[1] + y * SCALE)
                 for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))],
                color=LINE_ID, width=5)


def side_table(canvas, payload, blank):
    """Keep exact side IDs in a separate table so thin bands remain visible."""
    canvas.text((1090, 480), "侧号 → 当前色名" if not blank else "侧号 → 待人工标记", size=26)
    rows_per_column = ceil(len(payload["sides"]) / 2)
    spacing = min(38, 390 / max(rows_per_column, 1))
    font_size = min(24, max(12, int(spacing - 5)))
    for index, side in enumerate(payload["sides"]):
        column, row = divmod(index, rows_per_column)
        label = "?" if blank else str(side["symbol"])
        canvas.text((1090 + column * 205, 533 + row * spacing),
                    f"s{side['id']} → {label}", size=font_size)


def draw_preserving_thin_bands(canvas, payload, blank=False):
    """Keep very thin bands at their real size and put their names in the table.

    The established adaptive renderer has a 10-pixel minimum text size. For a
    band smaller than 18 pixels that label could cover its true boundaries.
    Retain the fill and original cuts but omit only that in-band duplicate;
    every exact ID/name/bounds record remains in the table and manifest.
    """
    broad, narrow = [], []
    for side in payload["sides"]:
        x0, y0, x1, y1 = side["bounds"]
        (broad if min(x1 - x0, y1 - y0) * SCALE >= 18 else narrow).append(side)
    if not blank:
        for side in narrow:
            x0, y0, x1, y1 = side["bounds"]
            x, y = ORIGIN[0] + x0 * SCALE, ORIGIN[1] + y0 * SCALE
            width, height = (x1 - x0) * SCALE, (y1 - y0) * SCALE
            fill = FILLS[side["symbol"]]
            canvas.draw.rectangle([(x, y), (x + width, y + height)], fill=fill)
            canvas.svg.append(f'<rect x="{x:g}" y="{y:g}" width="{width:g}" height="{height:g}" fill="{fill}"/>')
    draw_adaptive(canvas, {**payload, "sides": broad}, ORIGIN, SCALE, blank=blank)


def annotation_canvas(detail, result, payload, font, title, blank=False, witness=False):
    """Draw preserved coordinates and a clearly scoped initial retained 2."""
    canvas = Canvas(1550, 1120, font)
    initialization = result["initialization"]
    label = "；".join(f"{alias.get('history', alias.get('static', 'case'))} / step {alias.get('step', '-')}"
                     for alias in detail["aliases"][:2])
    canvas.text((55, 28), title, size=36)
    canvas.text((55, 92), label, size=24, color=MUTED)
    if witness:
        subtitle = "旧 v2 合法结果，仅作对照；不是 v3 输出，也未输入 v3。外侧1。"
    elif blank:
        subtitle = "v3 本次未完成：全部内侧留白；? 不是已提交色名。外侧1。"
    else:
        subtitle = "v3 独立重算成功：色名与填色双重标注；实际共边及线轨道核验通过。"
    canvas.text((55, 150), subtitle, size=24)
    draw_preserving_thin_bands(canvas, payload, blank=blank)
    highlight_retained(canvas, payload, initialization)
    canvas.text((1090, 227), "蓝框：v3 初始化选中侧", size=24, color=LINE_ID)
    canvas.text((1090, 277), f"初锚 s{initialization['side']} = 2", size=26, color=LINE_ID)
    if witness:
        old_symbol = next(side["symbol"] for side in payload["sides"]
                          if int(side["id"]) == initialization["side"])
        canvas.text((1090, 329), f"本张旧解该侧为 {old_symbol}", size=24)
    else:
        canvas.text((1090, 329), "只先固定外侧1与此处2", size=24)
    canvas.text((1090, 381), "侧号 sN 不是颜色/等级", size=22, color=MUTED)
    canvas.text((1090, 424), "极窄侧的色名见下表", size=22, color=MUTED)
    side_table(canvas, payload, blank)
    canvas.text((55, 924), f"初始化母线：{initialization['mother']}", size=25, color=LINE_ID)
    canvas.text((55, 974), "原始线段、交点和细带全部保留；只作统一缩放，未移动或合并边界。", size=25)
    canvas.text((55, 1024), "历史出生名(1,2)/(2,3)不等于最终整条母线所有分段的当前侧名。", size=25, color=MUTED)
    canvas.text((55, 1071), "这是有限案例证据，不是任意平面地图上算法必成功的证明。", size=23, color=MUTED)
    return canvas


def render_report(input_path, output_dir, font="msyh.ttc"):
    """Create fresh PNG/SVG artifacts only after checking all selected evidence."""
    require(not output_dir.exists(), "choose a fresh figure directory")
    report = read_json(input_path)
    require(report["full_corpus_run"] and report["smoke_limit"] is None and report["policy"] == POLICY,
            "renderer requires the complete frozen v3 report")
    require(report["source_sha256"] == report["source_sha256_end"], "full-run source drifted")
    require(all(file_sha(ROOT / name) == expected for name, expected in report["source_sha256"].items()),
            "current source differs from frozen full run")
    source_sha = dict(report["source_sha256"])
    source_sha.update({name: file_sha(ROOT / name) for name in RENDER_SOURCES})
    input_sha = file_sha(input_path)
    selections = [("blue-anchor-solved", BLUE_KEY)]
    if report["least_conflict"] is not None:
        selections.append(("least-conflict-blank", report["least_conflict"]["key"]))
    checked = [(kind, checked_case(report, key)) for kind, key in selections]
    require(checked[0][1][2]["status"] == "solved", "predeclared blue example is not solved")
    # Check fonts and all rectangle preconditions before making the output
    # directory. Unsupported shapes must not be approximated by bounding boxes.
    Canvas(10, 10, font).text((0, 0), "检", size=10)
    prepared, evidence = [], []
    for kind, (detail, row, result, check, payload) in checked:
        blank = result["status"] != "solved"
        title = "初始化修正后：原蓝框案例已完成" if not blank else "v3 仍受阻的最小案例：留白供人工标记"
        prepared.append((kind, annotation_canvas(detail, result, payload, font, title, blank=blank)))
        record = {"kind": kind, "key": detail["key"], "status": result["status"],
            "aliases": detail["aliases"], "document": detail["document"], "geometry": detail["geometry"],
            "geometry_sha256": digest(detail["geometry"]), "raw_result_sha256": digest(result),
            "result": result, "verification": check, "payload": payload,
            "alt_text": ("Exact original rectangular map with independently verified v3 color names and fills; "
                         "the blue outlined side is the initialization anchor 2." if not blank else
                         "Exact smallest v3 unsuccessful map left uncolored for manual annotation. "
                         "The blue outline marks only the initial retained 2, not a completed coloring.")}
        if blank:
            previous = row["runs"][BASELINE]
            if previous["status"] == "solved":
                old_check = verify_result(detail["geometry"], previous)
                require(old_check["passed"], "archived v2 comparison is not independently legal")
                old_payload = rectangular_payload(detail["geometry"], previous, detail["document"])
                prepared.append(("least-conflict-v2-valid-witness", annotation_canvas(
                    detail, result, old_payload, font, "同一受阻图：旧 v2 的合法对照（不是 v3 输出）", witness=True)))
                record.update(previous_policy=BASELINE, previous_result=previous,
                              previous_result_json_sha256=digest(previous),
                              previous_raw_result_sha256=previous["raw_result_sha256"],
                              previous_verification=old_check, previous_payload=old_payload)
        evidence.append(record)
    output_dir.mkdir(parents=True, exist_ok=False)
    files = [item for stem, canvas in prepared for item in canvas.save(output_dir, stem)]
    require(file_sha(input_path) == input_sha and all(file_sha(ROOT / name) == expected
            for name, expected in source_sha.items()), "figure sources changed during rendering")
    manifest = {"input": {"filename": input_path.name, "sha256": input_sha},
        "policy": POLICY, "files": files, "evidence": evidence,
        "source_sha256": source_sha, "full_run_source_sha256": report["source_sha256"],
        "font": Path(font).name, "pillow_version": pillow_version,
        "transform": "Original coordinates, uniform scale 1.1, x right/y down; no omitted lines",
        "palette": FILLS, "contrast_ink_on_fills": {str(k): contrast(INK, value) for k, value in FILLS.items()},
        "contrast_blue_on_white": contrast(LINE_ID, "#FFFFFF"),
        "scope": "Research-screen evidence diagrams; no journal or accessibility certification",
        "side_id_note": "Tables preserve every exact side ID; map numbers are color names only. Outside is 1.",
        "thin_band_note": "Bands are not enlarged. In-band duplicate labels are omitted below 18 rendered pixels to avoid covering boundaries; all bounds, names and side IDs remain in tables/payloads.",
        "comparison_note": "Any old v2 witness is archived and independently checked; it was never an input to v3."}
    write_report(output_dir / "manifest.json", manifest)
    return manifest


def main():
    """Render an explicitly frozen report to a new nonoverwriting directory."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--font", default="msyh.ttc")
    args = parser.parse_args()
    manifest = render_report(args.input, args.output_dir, args.font)
    print({"figures": len(manifest["files"]) // 2, "directory": args.output_dir.name,
           "keys": [row["key"] for row in manifest["evidence"]]}, flush=True)


if __name__ == "__main__":
    main()

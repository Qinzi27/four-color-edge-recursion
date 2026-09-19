"""Render exact coarse-batch geometry and independently replayed v4 outcomes.

The figure helpers are the project's existing Canvas / rectangle adapters.
This script never changes the candidate, reads old colors as solver inputs, or
turns a conflict into a colored answer. Pale readiness fills on the stage view
are explicitly NOT the four naming colors. Every source line remains visible.
"""

from argparse import ArgumentParser
from math import ceil
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.peer_batches import POLICY, restart_peer_batch_names
from fourcolor.staged_levels import POLICY as BASELINE
from fourcolor.whole_lines import build_whole_lines
from scripts.render_anchor_failure_cases import Canvas, INK, LINE_ID, MUTED, NEW, pillow_version
from scripts.render_frontier_restart import draw_adaptive
from scripts.render_global_restart import FILLS, rectangular_payload
from scripts.render_level_sides import contrast
from scripts.validate_frontier_restart import file_sha, json_value, read_json, verify_result
from scripts.validate_global_restart import digest, write_report
from scripts.validate_peer_batches import verify_run
from scripts.validate_relation_frontier_full import failure_rank, require


DEFAULT_INPUT = ROOT / "outputs/peer-batches-full-2026-09-19.json.gz"
OLD_INPUT = ROOT / "outputs/staged-levels-full-2026-09-19.json.gz"
OLD_SHA = "87250016644ba5c9c25573e0894af563eb451cd43915c11bad73927308af4910"
LEAST_OLD = "dc9cebec632a0762379de1441eea298761571ed5faf53f484d3672c4a6ce8739"
READY_FILL, UNFINISHED_FILL, GHOST = "#E4F0EC", "#F5F5F5", "#737B83"
SOURCES = ("scripts/render_peer_batches.py", "scripts/render_anchor_failure_cases.py",
           "scripts/render_frontier_restart.py", "scripts/render_global_restart.py",
           "scripts/render_level_sides.py")


def rectangle(canvas, bounds, fill):
    """Use the same exact rectangular primitive for raster and vector outputs."""
    x0, y0, x1, y1 = bounds
    canvas.draw.rectangle([(x0, y0), (x1, y1)], fill=fill)
    canvas.svg.append(f'<rect x="{x0:g}" y="{y0:g}" width="{x1-x0:g}" '
                      f'height="{y1-y0:g}" fill="{fill}"/>')


def transformed(bounds, origin, scale):
    """Apply uniform x-right/y-down scaling without altering the aspect ratio."""
    x0, y0, x1, y1 = bounds
    return (origin[0] + x0 * scale, origin[1] + y0 * scale,
            origin[0] + x1 * scale, origin[1] + y1 * scale)


def outline(canvas, side, origin, scale, color=NEW, width=5):
    """Highlight an existing boundary, never insert a new dividing line."""
    x0, y0, x1, y1 = transformed(side["bounds"], origin, scale)
    canvas.line([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)],
                color=color, width=width)


def exact_map(canvas, payload, origin, scale, blank=False):
    """Keep thin regions exact; use the complete side table for tiny labels.

    The established adaptive renderer supplies all exact cuts. Only duplicate
    in-region text is suppressed when either dimension is under 18 pixels;
    the actual region, fill, source coordinates and table entry remain intact.
    """
    broad = []
    for side in payload["sides"]:
        x0, y0, x1, y1 = side["bounds"]
        if min(x1 - x0, y1 - y0) * scale >= 18:
            broad.append(side)
        elif not blank:
            rectangle(canvas, transformed(side["bounds"], origin, scale), FILLS[side["symbol"]])
    draw_adaptive(canvas, {**payload, "sides": broad}, origin, scale, blank=blank)


def table(canvas, payload, origin, height=550, columns=2, column_width=190, blank=False):
    """Show every side ID and actual current name, including the narrowest."""
    count = ceil(len(payload["sides"]) / columns)
    spacing = min(38, height / max(count, 1))
    size = max(11, min(25, int(spacing - 5)))
    for index, side in enumerate(payload["sides"]):
        column, row = divmod(index, count)
        label = "?" if blank else str(side["symbol"])
        canvas.text((origin[0] + column * column_width, origin[1] + row * spacing),
                    f"s{side['id']} = {label}", size=size)


def checked_case(report, key):
    """Re-execute and independently audit the exact illustrated certificate."""
    detail = report["detailed_examples"][key]
    row = next(item for item in report["drawings"] if item["key"] == key)
    geometry = detail["geometry"]
    result = restart_peer_batch_names(geometry)
    require(json_value(result) == detail["outcome"], "illustrated v4 result changed")
    require(digest(geometry) == row["geometry_sha256"], "illustrated geometry changed")
    require(digest(result) == row["runs"][POLICY]["raw_result_sha256"], "illustrated result hash changed")
    verification = verify_run(geometry, result)
    require(json_value(verification) == detail["verification"], "illustration proof replay changed")
    try:
        payload = rectangular_payload(geometry, result, detail["document"])
    except ValueError:
        # General failed maps can be drawn as exact raw edges, never by
        # approximating nonrectangular faces as their bounding rectangles.
        payload = None
    return {"key": key, "aliases": detail["aliases"], "document": detail["document"],
            "geometry": geometry, "geometry_sha256": digest(geometry),
            "raw_result_sha256": digest(result), "result": result,
            "verification": verification, "payload": payload}


def coarse_stage_canvas(evidence, fatal_side, font):
    """Show the five active full mothers and retain future lines as grey dashes."""
    geometry, result, payload = (evidence[name] for name in ("geometry", "result", "payload"))
    require(payload is not None, "five-line stage illustration needs exact rectangles")
    stage = next(row for row in result["batch_geometry"]["stages"] if row["stage"] == 2)
    require(stage["new_mothers"] == [f"L:{x},0>{x},600" for x in (190, 274, 551, 708, 817)],
            "predeclared five-line geometry changed")
    model = build_whole_lines(geometry)
    outside = geometry["outerFace"]
    side_by_id = {int(side["id"]): side for side in payload["sides"]}
    coarse = [cell for cell in stage["coarse_cells"] if cell != [outside]]
    origin, scale = (50, 235), 1.2
    canvas = Canvas(1730, 1190, font)
    canvas.text((50, 30), "同级先展开：五条贯通母线，六个框内粗区域", size=38)
    canvas.text((50, 95), "原第16步受阻图｜这里只画几何阶段2，不把粗区域涂成最终色名。", size=25, color=MUTED)
    canvas.text((50, 150), "C = 粗区域编号；s = 最终侧编号。背景浅绿表示已就绪，不代表颜色2或3。", size=25)
    cell_rows = []
    for cell in coarse:
        bounds = [side_by_id[side]["bounds"] for side in cell]
        merged = (min(b[0] for b in bounds), min(b[1] for b in bounds),
                  max(b[2] for b in bounds), max(b[3] for b in bounds))
        summed_area = sum((b[2] - b[0]) * (b[3] - b[1]) for b in bounds)
        require(abs(summed_area - (merged[2] - merged[0]) * (merged[3] - merged[1])) < 1e-6,
                "coarse region is not an exact rectangular strip")
        cell_rows.append((merged, cell))
    cell_rows.sort()
    for index, (bounds, cell) in enumerate(cell_rows, 1):
        rectangle(canvas, transformed(bounds, origin, scale), READY_FILL if len(cell) == 1 else UNFINISHED_FILL)
        center = origin[0] + (bounds[0] + bounds[2]) * scale / 2
        canvas.text((center, 198), f"C{index}", size=24, centered=True)
        if len(cell) == 1:
            canvas.text((center, origin[1] + 260 * scale), f"s{cell[0]}", size=28, centered=True)
            canvas.text((center, origin[1] + 305 * scale), "就绪", size=22, centered=True)
    active = set(stage["active_mothers"])
    for line in model.lines:
        if line["id"] != "frame" and line["id"] not in active:
            canvas.line([(origin[0] + x * scale, origin[1] + y * scale) for x, y in line["endpoints"]],
                        color=GHOST, width=2, dashed=True)
    for line in model.lines:
        if line["id"] != "frame" and line["id"] in active:
            canvas.line([(origin[0] + x * scale, origin[1] + y * scale) for x, y in line["endpoints"]],
                        color=LINE_ID, width=5)
    width, height = payload["width"], payload["height"]
    canvas.line([(origin[0] + x * scale, origin[1] + y * scale)
                 for x, y in ((0, 0), (width, 0), (width, height), (0, height), (0, 0))], width=5)
    fatal = side_by_id[fatal_side]
    outline(canvas, fatal, origin, scale, NEW, 4)
    x0, y0, x1, y1 = fatal["bounds"]
    canvas.text((origin[0] + (x0 + x1) * scale / 2, origin[1] + (y0 + y1) * scale / 2 - 20),
                f"s{fatal_side}", size=24, color=NEW, centered=True)
    anchor = side_by_id[result["initialization"]["side"]]
    x0, y0, x1, y1 = anchor["bounds"]
    canvas.text((origin[0] + (x0 + x1) * scale / 2, origin[1] + (y0 + y1) * scale / 2 - 22),
                f"s{anchor['id']}", size=23, color=LINE_ID, centered=True)
    canvas.text((origin[0] + (x0 + x1) * scale / 2, origin[1] + (y0 + y1) * scale / 2 + 13),
                "初锚2", size=20, color=LINE_ID, centered=True)
    x = 1180
    for y, color, dashed, text in ((243, LINE_ID, False, "已激活：五条整母线"),
                                    (303, GHOST, True, "未激活：后续细分保留"),
                                    (363, NEW, False, f"橙框：旧致命侧 s{fatal_side}")):
        canvas.line([(x, y + 13), (x + 55, y + 13)], color=color, width=4, dashed=dashed)
        canvas.text((x + 75, y), text, size=24, color=color)
    canvas.text((x, 435), "第2阶段：s3、s4、s5、s6 就绪", size=24)
    canvas.text((x, 491), f"s{fatal_side} 的边界到第3阶段才齐全。", size=24)
    canvas.text((x, 547), "先处理右侧已就绪区域，", size=25, color=LINE_ID)
    canvas.text((x, 591), "再决定左侧更深分割的名字。", size=25, color=LINE_ID)
    canvas.text((x, 663), "初始化 s2 = 2 是唯一提前例外：", size=23)
    canvas.text((x, 707), "由外侧保持1的全局名字置换保证；", size=23)
    canvas.text((x, 751), "不强迫整个 C2 的后代同色。", size=23)
    canvas.text((x, 823), "同级不等于同色；粗区域不是最终侧。", size=22, color=MUTED)
    canvas.text((50, 1002), "r(F) = 最后一个真实共边激活的阶段。母线浅，不代表它沿线的每个最终侧都浅。", size=27)
    canvas.text((50, 1059), "全部线使用正式输入原坐标；灰虚线只表示暂未激活，没有删除或移动任何细线。", size=25, color=MUTED)
    canvas.text((50, 1111), "该判据证明几何就绪与分区细化，不证明后续每个最小候选都能延伸成完整配色。", size=24, color=MUTED)
    return canvas


def final_canvas(evidence, fatal_side, font):
    """Display only actual v4 terminal colors, with every side listed separately."""
    result, payload = evidence["result"], evidence["payload"]
    require(payload is not None, "selected original failure has nonrectangular sides")
    blank = result["status"] != "solved"
    canvas = Canvas(1570, 1150, font)
    canvas.text((55, 30), "同一第16步图：v4 实际重新标色" if not blank else "同一第16步图：v4 仍未完成", size=39)
    canvas.text((55, 96), "所有色名来自新算法本次完整运行；旧成功解从未作为输入。", size=25, color=MUTED)
    canvas.text((55, 151), "外侧1；图内数字是当前色名，右表 sN 才是侧编号。" if not blank else
                "外侧1；内部全部留白供标注，不把失败过程当作完成答案。", size=25)
    origin, scale = (55, 230), 1.1
    exact_map(canvas, payload, origin, scale, blank=blank)
    side = next(side for side in payload["sides"] if int(side["id"]) == fatal_side)
    outline(canvas, side, origin, scale, NEW, 4)
    canvas.text((1095, 236), f"橙框：旧致命位置 s{fatal_side}", size=25, color=NEW)
    if not blank:
        canvas.text((1095, 286), f"v4 最终色名：{side['symbol']}", size=27)
    canvas.text((1095, 341), "侧编号 → 当前色名", size=25)
    table(canvas, payload, (1095, 392), height=470, columns=2, column_width=205, blank=blank)
    canvas.text((55, 951), "细窄区域保持真实宽度；极窄区域省略图内重复数字，但其色名完整保留在右表。", size=25)
    canvas.text((55, 1003), f"状态：{result['status']}；主动落名 {result['choices']} 次；回溯 0；旧色输入 False。", size=25)
    canvas.text((55, 1055), "最终真实共边与全部推导证书独立核验；单张图完成不等于通用性已经证明。", size=25, color=MUTED)
    return canvas


def four_case_canvas(evidence, font):
    """Place four independently checked old-failure outcomes on one exact sheet."""
    canvas = Canvas(2510, 1910, font)
    canvas.text((50, 30), "四个原受阻前缀：新批量规则各自从头计算的实际结果", size=41)
    canvas.text((50, 101), "同一历史的第16、18、19、20步；每张图独立重启。色名配数字，所有细带保留真实宽度。", size=28, color=MUTED)
    for index, item in enumerate(evidence):
        column, row = index % 2, index // 2
        x, top = 50 + column * 1240, 185 + row * 830
        result, payload = item["result"], item["payload"]
        require(payload is not None, "old failure sheet requires exact rectangular sides")
        step = next(alias["step"] for alias in item["aliases"]
                    if alias.get("history") == "heldout-guillotine-20261936")
        blank = result["status"] != "solved"
        canvas.text((x, top), f"第 {step} 步  |  {result['status']}  |  {len(result['domains']) - 1} 个内侧", size=31)
        canvas.text((x, top + 47), "外侧1；图内数字为色名" if not blank else "外侧1；受阻图留白，不展示假完整答案", size=23, color=MUTED)
        exact_map(canvas, payload, (x, top + 94), 1.1, blank=blank)
        canvas.text((x + 1020, top + 88), "侧号=色名", size=23)
        table(canvas, payload, (x + 1020, top + 134), height=612, columns=1, blank=blank)
        canvas.text((x, top + 768), f"主动落名 {result['choices']} 次；独立证书与最终边界核验通过。" if not blank else
                    "已独立核验本次承诺冲突；不表示该图无法四色。", size=24, color=MUTED)
    canvas.text((50, 1854), "这些是已见回归案例。图集整体成功/退步以完整报告为准，不根据局部修复推出任意地图必成功。", size=27, color=MUTED)
    return canvas


def failure_canvas(evidence, font):
    """Leave the smallest actual new failure blank for the user's annotation."""
    result, payload, geometry = (evidence[name] for name in ("result", "payload", "geometry"))
    require(result["status"] == "conflict", "manual failure view cannot relabel a solved map")
    canvas = Canvas(1570, 1170, font)
    label = "; ".join(f"{alias.get('history', alias.get('static', 'case'))} / {alias.get('step', '-')}"
                      for alias in evidence["aliases"][:1])
    canvas.text((55, 30), "v4 新受阻图：完整线网留白，供人工标记", size=38)
    canvas.text((55, 99), label, size=25, color=MUTED)
    canvas.text((55, 157), "外侧1；内部 ? 不是当前已承诺的颜色。本图不说明需要第五色。", size=25)
    origin, scale = (55, 230), 1.1
    if payload is not None:
        exact_map(canvas, payload, origin, scale, blank=True)
        canvas.text((1095, 242), "侧编号 → 待填写", size=25)
        table(canvas, payload, (1095, 300), height=550, columns=2, blank=True)
    else:
        # Edges, not bounding boxes, preserve nonrectangular cases exactly.
        for edge in geometry["edges"]:
            if not edge.get("virtual"):
                points = [geometry["vertices"][edge[key]] for key in ("a", "b")]
                canvas.line([(origin[0] + x * scale, origin[1] + y * scale) for x, y in points],
                            width=5 if edge.get("frame") else 3)
        canvas.text((1095, 245), "此图含非矩形区域。", size=25)
        canvas.text((1095, 300), "按原始真实边逐条绘制，", size=24)
        canvas.text((1095, 348), "不使用矩形包围盒代替。", size=24)
    for index, text in enumerate(("请标出同级先处理的母线、保留侧与取名顺序。", "若有同步改名，请标明影响范围与触发条件。",
                                  "完整输入、各阶段粗区、失败推导链都保存在同目录 manifest.json。")):
        canvas.text((55, 951 + index * 55), text, size=25, color=LINE_ID if index == 0 else MUTED)
    return canvas


def archived_comparison_canvas(evidence, font):
    """Keep the archived legal v3 comparison visibly separate from v4 failure."""
    payload = evidence["previous_payload"]
    require(payload is not None, "archived comparison requires exact rectangular sides")
    require(evidence["previous_result"]["status"] == "solved", "archived comparison is not complete")
    canvas = Canvas(1570, 1170, font)
    canvas.text((55, 30), "同一新受阻图：v3 合法对照，不是 v4 输出", size=38)
    canvas.text((55, 99), "这是保留档案中的完整配色，已独立逐边核验；未输入 v4，也不是失败后的后备算法。", size=24, color=MUTED)
    canvas.text((55, 157), "外侧1；图内数字为旧 v3 色名。此图用于确认地图本身可以四色，不代替新规则结果。", size=24)
    exact_map(canvas, payload, (55, 230), 1.1)
    canvas.text((1095, 242), "侧号 → 旧 v3 合法色名", size=25)
    table(canvas, payload, (1095, 300), height=550, columns=2)
    canvas.text((55, 951), "对照说明：当前 v4 的这条承诺路径受阻，不代表此图没有合法四色命名。", size=26)
    canvas.text((55, 1006), "原始 document 已另存为 least-new-conflict-document.json，可用单图程序独立复现。", size=24, color=LINE_ID)
    canvas.text((55, 1061), "新规则的完整失败证书和旧规则的合法证据分开保存，不能把两者拼成一次成功运行。", size=25, color=MUTED)
    return canvas


def render_report(input_path, output_dir, font="msyh.ttc"):
    """Produce exclusive PNG/SVG files only from a complete hash-bound run."""
    require(not output_dir.exists(), "choose a new figure directory; no overwrites")
    report = read_json(input_path)
    require(report["policy"] == POLICY and report["full_corpus_run"] and report["smoke_limit"] is None,
            "figures require the complete v4 report")
    require(report["source_sha256"] == report["source_sha256_end"], "full-run source drifted")
    source_sha = {**report["source_sha256"], **{name: file_sha(ROOT / name) for name in SOURCES}}
    require(all(file_sha(ROOT / name) == expected for name, expected in source_sha.items()),
            "current sources differ from the full report")
    input_sha = file_sha(input_path)
    require(file_sha(OLD_INPUT) == OLD_SHA, "preserved v3 conflict archive changed")
    old = read_json(OLD_INPUT)
    old_failures = sorted((item for item in report["drawings"] if item["runs"][BASELINE]["status"] == "conflict"),
                          key=lambda item: (len(item["document"]["strokes"]), item["key"]))
    require(len(old_failures) == 4 and old_failures[0]["key"] == LEAST_OLD, "four original failure identities changed")
    cases = [checked_case(report, item["key"]) for item in old_failures]
    fatal_side = old["detailed_examples"][LEAST_OLD]["outcome"]["trace"][1]["side"]
    require(fatal_side == 13, "original first fatal location changed")
    Canvas(10, 10, font).text((0, 0), "检", size=10)
    prepared = [("stage2-five-mother-coarse-geometry", coarse_stage_canvas(cases[0], fatal_side, font)),
                ("step16-v4-actual-result", final_canvas(cases[0], fatal_side, font)),
                ("four-prior-failures-v4-results", four_case_canvas(cases, font))]
    regressions = [item for item in report["detailed_examples"].values()
                   if item["outcome"]["status"] == "conflict" and item["previous_result"]["status"] == "solved"]
    manual = None
    if regressions:
        manual = checked_case(report, min(regressions, key=failure_rank)["key"])
        candidate_row = next(item for item in report["drawings"] if item["key"] == manual["key"])
        archived_row = next(item for item in old["drawings"] if item["key"] == manual["key"])
        previous = candidate_row["runs"][BASELINE]
        require(previous == archived_row["runs"][BASELINE], "archived comparison changed in the v4 report")
        old_check = verify_result(manual["geometry"], previous)
        require(old_check["passed"] and previous["status"] == "solved", "old comparison is not legal")
        manual.update(previous_policy=BASELINE, previous_result=previous,
                      previous_verification=old_check,
                      previous_payload=rectangular_payload(manual["geometry"], previous, manual["document"]))
        prepared.append(("least-new-conflict-blank", failure_canvas(manual, font)))
        prepared.append(("least-new-conflict-v3-valid-comparison", archived_comparison_canvas(manual, font)))
    output_dir.mkdir(parents=True, exist_ok=False)
    files = [file for stem, canvas in prepared for file in canvas.save(output_dir, stem)]
    documents = []
    if manual:
        # Export only geometry, not the archived legal coloring or v4 anchors.
        document_path = output_dir / "least-new-conflict-document.json"
        write_report(document_path, manual["document"])
        documents.append({"filename": document_path.name, "sha256": file_sha(document_path),
                          "geometry_key": manual["key"], "content": "exact drawing document only, no colors"})
    require(file_sha(input_path) == input_sha and all(file_sha(ROOT / name) == expected
            for name, expected in source_sha.items()), "illustration source changed during rendering")
    manifest = {"schema_version": 1, "policy": POLICY,
        "input": {"filename": input_path.name, "sha256": input_sha},
        "old_conflict_source": {"filename": OLD_INPUT.name, "sha256": OLD_SHA},
        "files": files, "documents": documents, "evidence": cases + ([manual] if manual else []),
        "first_old_fatal_side": fatal_side, "smallest_new_conflict_key": manual["key"] if manual else None,
        "source_sha256": source_sha, "full_run_source_sha256": report["source_sha256"],
        "font": Path(font).name, "pillow_version": pillow_version,
        "palette": FILLS, "readiness_palette_not_color_names": {"ready": READY_FILL, "unfinished": UNFINISHED_FILL},
        "contrast_ink_on_fills": {str(symbol): contrast(INK, fill) for symbol, fill in FILLS.items()},
        "contrast_active_on_white": contrast(LINE_ID, "#FFFFFF"),
        "contrast_future_on_white": contrast(GHOST, "#FFFFFF"),
        "transform": "Exact source x-right/y-down coordinates, uniform 1.1 or 1.2 scale, no omitted real lines",
        "thin_region_policy": "No region enlargement. Duplicate in-map numbers omitted below 18px; every ID/name remains in full side tables and payloads.",
        "stage_view_semantics": "Pale green is geometric readiness, not a color name; dashed grey means an inactive but still present original mother.",
        "finite_evidence_scope": "Archived regressions, not unseen evidence or a universal four-color construction proof."}
    write_report(output_dir / "manifest.json", manifest)
    return manifest


def main():
    """Render the finalized report to a fresh folder, preserving all old images."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--font", default="msyh.ttc")
    args = parser.parse_args()
    manifest = render_report(args.input, args.output_dir, args.font)
    print({"figure_pairs": len(manifest["files"]) // 2,
           "cases_replayed": len(manifest["evidence"]),
           "smallest_new_conflict_key": manifest["smallest_new_conflict_key"]}, flush=True)


if __name__ == "__main__":
    main()

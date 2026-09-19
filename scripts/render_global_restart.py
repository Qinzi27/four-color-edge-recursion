"""Draw exact global-restart results, independently verified before rendering.

The old incremental stopped state is a labeled control, not a failed global
restart. A second figure preserves an actual new scheduling conflict beside an
explicitly separate successful control, never as a hidden algorithm fallback.
"""

from argparse import ArgumentParser
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.global_restart import restart_line_names, current_segments
from fourcolor.whole_lines import build_whole_lines
from scripts.render_anchor_failure_cases import Canvas, draw_map, MUTED, NEW, LINE_ID
from scripts.validate_global_restart import export_geometries, digest
from scripts.validate_weighted_lines import independent_check

FILLS = {1: "#EEEEEE", 2: "#CDE7F4", 3: "#FFE4AF", 4: "#DDCFE8"}


def rectangular_payload(geometry, result, document):
    """Convert only verified rectangular face orbits into diagram rectangles."""
    model = build_whole_lines(geometry)
    first = next(line for line in model.lines if line["id"] == "frame")["spans"][0]["dart"]
    outside = model.plane_map.face_of_dart[first]
    sides = []
    for i, face in enumerate(model.plane_map.faces):
        if i == outside:
            continue
        polygon = [geometry["vertices"][geometry["edges"][d // 2]["b" if d % 2 else "a"]] for d in face]
        x0, y0 = min(p[0] for p in polygon), min(p[1] for p in polygon)
        x1, y1 = max(p[0] for p in polygon), max(p[1] for p in polygon)
        area = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(polygon, polygon[1:] + polygon[:1]))) / 2
        if abs(area - (x1 - x0) * (y1 - y0)) > 1e-4:
            raise ValueError("this exact rectangle renderer cannot simplify a nonrectangular side")
        sides.append({"id": str(i), "bounds": [x0, y0, x1, y1],
                      "symbol": result["colors"][i] if result["status"] == "solved" else None})
    return {"width": 900, "height": 600, "sides": sides,
            "cuts": [[s["a"], s["b"]] for s in document["strokes"]]}


def draw_named(canvas, payload, origin, scale, pending=None, blank=False):
    """Use redundant numeric labels plus pale fills; retain exact geometry."""
    for side in payload["sides"]:
        x0, y0, x1, y1 = side["bounds"]
        a, b = (origin[0] + x0 * scale, origin[1] + y0 * scale), (origin[0] + x1 * scale, origin[1] + y1 * scale)
        if not blank:
            color = FILLS[side["symbol"]]
            canvas.draw.rectangle([a, b], fill=color)
            canvas.svg.append(f'<rect x="{a[0]:g}" y="{a[1]:g}" width="{b[0]-a[0]:g}" height="{b[1]-a[1]:g}" fill="{color}"/>')
    draw_map(canvas, payload, origin, scale, pending=pending)
    for side in payload["sides"]:
        x0, y0, x1, y1 = side["bounds"]
        label = "?" if blank else str(side["symbol"])
        canvas.text((origin[0] + (x0 + x1) * scale / 2, origin[1] + (y0 + y1) * scale / 2 - 16),
                    label, size=30, centered=True)


def main():
    """Save new figure artifacts and exact provenance without overwriting."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--font", default="msyh.ttc")
    parser.add_argument("--policy", default="closed-support", help="Explicit policy for the corrected step7 diagram")
    args = parser.parse_args()
    stems = ("recolored-step7", "priority-fork-step4", "current-port-weights", "still-blocked-step6")
    if any((args.output_dir / (stem + ext)).exists() for stem in stems for ext in (".png", ".svg")) or (args.output_dir / "manifest.json").exists():
        parser.error("choose a fresh output directory")
    raw = args.input.read_bytes()
    report = json.loads(gzip.decompress(raw))
    evidence = []

    def load(history_key, step, policy):
        """Rerun a displayed case and match the formal report's names and trace."""
        history = next(h for h in report["histories"] if h["key"] == history_key)
        record = next(r for r in report["drawings"] if r["key"] == history["prefix_keys"][step])
        geometry = export_geometries([record])[0]["geometry"]
        result = restart_line_names(geometry, policy)
        saved = record["runs"][policy]
        if result["domains"] != saved["domains"] or digest(result["trace"]) != saved["trace_sha256"]:
            raise AssertionError("figure no longer reproduces formal experiment")
        if not independent_check(geometry, result):
            raise AssertionError("illustrated names failed independent checking")
        payload = rectangular_payload(geometry, result, record["document"])
        evidence.append({"history": history_key, "step": step, "policy": policy,
                         "document": record["document"], "geometry_sha256": digest(geometry),
                         "result": result, "drawing": payload})
        return payload, result

    after, after_result = load("guillotine-20260908", 7, args.policy)
    if after_result["status"] != "solved":
        raise AssertionError("the selected policy did not solve the illustrated step")
    old_path = ROOT / "docs/figures/current-names-2026-09-18/manifest.json"
    old = json.loads(old_path.read_text(encoding="utf-8"))
    before = next(r["certificate"]["state"] for r in old["records"] if r["key"] == "still-blocked-before")
    # The pending line is identified by geometry rather than canonical order.
    before_cuts = {tuple(sorted(map(tuple, cut))) for cut in before["cuts"]}
    pending = next(cut for cut in after["cuts"] if tuple(sorted(map(tuple, cut))) not in before_cuts)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    canvas = Canvas(1900, 960, args.font)
    canvas.text((60, 30), "你的判断在这张图上成立：全图重新标色后，第 7 刀成功", size=39)
    canvas.text((60, 103), "左：旧增量规则留下的名字　｜　右：新增线网清空旧名，从外圈自动重算", size=27, color=MUTED)
    for i, payload in enumerate((before, after)):
        x = 60 + i * 950
        canvas.text((x, 180), "旧名控制：尚未加入虚线" if i == 0 else "新结果：四个名字，全边界校验通过", size=28)
        canvas.text((x, 224), "外侧固定 1；数字表示当前线侧名", size=24, color=MUTED)
        draw_named(canvas, payload, (x, 275), 0.9, pending=pending if i == 0 else None)
        if i == 1:
            canvas.line([(x + a * 0.9, 275 + b * 0.9) for a, b in pending], color=NEW, width=5)
    canvas.text((60, 850), f"右图由 {args.policy} 规则自动产生；未手工喂入名字，未沿用旧图的局部预算。", size=26, color=LINE_ID)
    history_result = next(r for r in report["history_results"] if r["key"] == "guillotine-20260908" and r["policy"] == args.policy)
    first_failure = history_result["first_failed_prefix"]
    note = (f"此图只展示第 7 刀；本条 24 刀历史首次新冲突在第 {first_failure} 刀，不能混称全程成功。"
            if first_failure is not None else "此图展示第 7 刀；本条声明历史的全部前缀也已成功，但不构成一般地图证明。")
    canvas.text((60, 900), note, size=25, color=MUTED)
    files = canvas.save(args.output_dir, stems[0])

    failed, failure = load("guillotine-20260943", 4, "shared-mother")
    successful, _ = load("guillotine-20260943", 4, "segment-constraints")
    if failure["status"] != "conflict":
        raise AssertionError("priority comparison no longer shows a conflict")
    fork = Canvas(1900, 980, args.font)
    fork.text((60, 30), "已澄清的过强解释｜同母线不应无条件压过其他约束", size=40)
    fork.text((60, 103), "seed 20260943，第 4 刀；两边都全图重启，左图仅保留为旧的绝对优先对照。", size=27, color=MUTED)
    for i, payload in enumerate((failed, successful)):
        x = 60 + i * 950
        fork.text((x, 177), "同母线绝对优先：未得到合法终态" if i == 0 else "当前约束数优先：得到合法四名结果", size=28)
        fork.text((x, 221), "空白问号供人工标记，不显示冲突草稿为彩图" if i == 0 else "这是独立对照，不是失败后的自动后备", size=22, color=MUTED)
        draw_named(fork, payload, (x, 275), 0.9, blank=i == 0)
        if i == 0:
            fork.line([(x + 305 * 0.9, 275), (x + 305 * 0.9, 815)], color=LINE_ID, width=6)
    fork.text((60, 850), "左图蓝线两端均接外圈；它先命名并立即承诺最小名，随后遇到空候选。", size=27, color=LINE_ID)
    fork.text((60, 900), "需区分：先分析这条线，是否等于立即固定其两侧名字？本图不否定更灵活的母线规则。", size=25, color=MUTED)
    files += fork.save(args.output_dir, stems[1])

    documents = [{"strokes": [{"a": [0, 300], "b": [900, 300]}]},
                 {"strokes": [{"a": [0, 300], "b": [900, 300]}, {"a": [450, 0], "b": [450, 600]}]}]
    ports = Canvas(1900, 850, args.font)
    ports.text((60, 30), "重算的是当前段的连接；不是把整条母线身份丢掉", size=42)
    port_records = []
    for i, document in enumerate(documents):
        geometry = export_geometries([{"key": str(i), "document": document}])[0]["geometry"]
        model = build_whole_lines(geometry)
        units = [u for u in current_segments(model) if u["mother"] == "L:0,300>900,300"]
        result = restart_line_names(geometry)
        if not independent_check(geometry, result):
            raise AssertionError("port example did not verify")
        port_records.append({"document": document, "horizontal_units": units, "result": result})
        x = 60 + i * 950
        ports.text((x, 130), "加线前：H 两端都是外圈母线" if i == 0 else "加线后：H 两段各只有一端接外圈", size=28)
        draw_named(ports, rectangular_payload(geometry, result, document), (x, 205), 0.85)
        ports.text((x, 743), "H：{外圈} — {外圈}" if i == 0 else "H左：{外圈} — {V}；H右：{V} — {外圈}", size=25, color=LINE_ID)
    files += ports.save(args.output_dir, stems[2])

    stopped, stopped_result = load("guillotine-20261027", 6, "closed-support")
    if stopped_result["status"] != "conflict":
        raise AssertionError("the manual annotation example no longer blocks")
    earlier, _ = load("guillotine-20261027", 5, "closed-support")
    previous_edges = {tuple(sorted(map(tuple, cut))) for cut in earlier["cuts"]}
    newest = next(cut for cut in stopped["cuts"] if tuple(sorted(map(tuple, cut))) not in previous_edges)
    manual = Canvas(1500, 980, args.font)
    manual.text((60, 30), "可继续人工标记｜整图重启后的真实未解例", size=40)
    manual.text((60, 102), "seed 20261027，第 6 刀；closed-support：当前约束优先，闭环只作辅助。", size=26, color=MUTED)
    manual.text((60, 169), "外侧固定 1；所有内侧留白，问号不是已提交名字。", size=27)
    draw_named(manual, stopped, (60, 230), 1.0, blank=True)
    manual.line([(60 + a, 230 + b) for a, b in newest], color=NEW, width=5)
    manual.text((1010, 267), "橙色实线：", size=26, color=NEW)
    manual.text((1010, 315), "已经加入的第6刀", size=26)
    manual.text((1010, 400), "几何完整保留；", size=26, color=MUTED)
    manual.text((1010, 448), "命名失败不删线。", size=26, color=MUTED)
    manual.text((1010, 533), "这是具体策略未解，", size=25, color=MUTED)
    manual.text((1010, 581), "不是需要第五色。", size=25, color=MUTED)
    manual.text((60, 887), "请标：先检查哪个闭环、先处理哪段线、何时固定名字；可一次重写全部旧名。", size=26, color=LINE_ID)
    files += manual.save(args.output_dir, stems[3])
    manifest = {"input": {"filename": args.input.name, "sha256": sha256(raw).hexdigest()},
                "old_control": {"filename": old_path.relative_to(ROOT).as_posix(), "sha256": sha256(old_path.read_bytes()).hexdigest()},
                "records": evidence, "port_examples": port_records, "files": files,
                "font": Path(args.font).name, "geometry_transform": "Exact uniform scaling; x-right/y-down; no geometry simplified.",
                "source_sha256": {p: sha256((ROOT / p).read_bytes()).hexdigest() for p in
                                  ("scripts/render_global_restart.py", "scripts/render_anchor_failure_cases.py", "fourcolor/global_restart.py", "fourcolor/closed_support.py")}}
    with (args.output_dir / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"files": len(files), "verified_cases": len(evidence) + len(port_records)}))


if __name__ == "__main__":
    main()

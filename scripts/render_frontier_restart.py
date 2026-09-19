"""Render verified successes and an actual remaining failure, without invention.

Reuse the project exact rectangle renderer. Geometry, names and trace hashes
must match the frozen report before any image is drawn; failed states stay
blank for annotation, never presented as a completed coloring.
"""

from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.frontier_restart import restart_frontier_names
from fourcolor.global_restart import restart_line_names
from scripts.render_anchor_failure_cases import Canvas, MUTED, LINE_ID, NEW, draw_map
from scripts.render_global_restart import rectangular_payload, FILLS
from scripts.validate_frontier_restart import read_json, verify_result, BASELINE, EXISTING, HELDOUT
from scripts.validate_global_restart import digest, export_geometries, write_report


def draw_adaptive(canvas, payload, origin, scale, blank=False):
    """Retain exact geometry and fit labels inside even the narrowest band.

    The optional PNG is an exact rendering of the same vector primitives,
    not an edit of an existing figure. Numeric labels duplicate fill meaning.
    """
    for side in payload["sides"]:
        x0, y0, x1, y1 = side["bounds"]
        a = (origin[0] + x0 * scale, origin[1] + y0 * scale)
        b = (origin[0] + x1 * scale, origin[1] + y1 * scale)
        if not blank:
            fill = FILLS[side["symbol"]]
            canvas.draw.rectangle([a, b], fill=fill)
            canvas.svg.append(f'<rect x="{a[0]:g}" y="{a[1]:g}" width="{b[0]-a[0]:g}" '
                              f'height="{b[1]-a[1]:g}" fill="{fill}"/>')
    draw_map(canvas, payload, origin, scale)
    for side in payload["sides"]:
        x0, y0, x1, y1 = side["bounds"]
        size = max(10, min(30, int((x1 - x0) * scale * 0.65), int((y1 - y0) * scale * 0.65)))
        canvas.text((origin[0] + (x0 + x1) * scale / 2,
                     origin[1] + (y0 + y1) * scale / 2 - size / 2),
                    "?" if blank else str(side["symbol"]), size=size, centered=True)


def main():
    """Save an exclusive pair of PNG/SVG diagrams with rerun certificates."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--policy", default="tight-hall")
    parser.add_argument("--failure-cohort", choices=(EXISTING, HELDOUT), default=EXISTING)
    parser.add_argument("--font", default="msyh.ttc")
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("use a fresh output directory")
    report = read_json(args.input)
    if not report["full_corpus_run"]:
        parser.error("figures require a full formal report, not a smoke sample")
    histories = {h["key"]: h for h in report["histories"]}
    drawings = {r["key"]: r for r in report["drawings"]}
    evidence = []

    def load(key, step, policy):
        """Match output and decision trace before reusing project drawing helpers."""
        row = drawings[histories[key]["prefix_keys"][step]]
        geometry = export_geometries([row])[0]["geometry"]
        result = (restart_line_names(geometry, policy) if policy == BASELINE else
                  restart_frontier_names(geometry, policy))
        saved = row["runs"][policy]
        if (result["domains"] != saved["domains"] or
                digest(result["trace"]) != saved["trace_sha256"] or
                digest(geometry) != row["geometry_sha256"]):
            raise AssertionError("illustrated rerun differs from frozen report")
        check = verify_result(geometry, result)
        if not check["passed"]:
            raise AssertionError("illustrated result was not independently verified")
        payload = rectangular_payload(geometry, result, row["document"])
        evidence.append({"history": key, "step": step, "policy": policy,
                         "geometry_key": row["key"], "document": row["document"],
                         "result": result, "verification": check, "drawing": payload})
        return payload, result

    previous, old = load("guillotine-20261027", 6, BASELINE)
    current, new = load("guillotine-20261027", 6, args.policy)
    if old["status"] != "conflict" or new["status"] != "solved":
        raise AssertionError("selected comparison no longer demonstrates the declared repair")
    args.output_dir.mkdir(parents=True)
    canvas = Canvas(1900, 1060, args.font)
    canvas.text((55, 28), "原第 6 刀失败图：新规则已自动完成四色命名", size=39)
    canvas.text((55, 95), "seed 20261027｜同一完整几何，两边均清空旧名后重启；不是手工喂入答案。", size=26, color=MUTED)
    for index, payload in enumerate((previous, current)):
        x = 55 + 945 * index
        canvas.text((x, 162), "旧规则：冲突，不能交付完整名字" if index == 0 else
                    f"新规则 {args.policy}：全边核验通过", size=27)
        canvas.text((x, 211), "外侧固定 1；内部数字是当前线侧名", size=24, color=MUTED)
        draw_adaptive(canvas, payload, (x, 265), 0.9, blank=index == 0)
    canvas.text((55, 841), "新增推理：先保留候选关系，再决定具体名字。", size=30, color=LINE_ID)
    canvas.text((55, 899), "若三个侧两两共边，前两个都只能取 {3,4}，则第三个不能再用3或4。", size=28)
    canvas.text((55, 956), "这是一条有前提的局部排除规则；单张图修好，不代表所有地图或后续步骤都完成。", size=26, color=MUTED)
    files = canvas.save(args.output_dir, "repaired-step6")

    failures = sorted((r for r in report["history_results"]
                       if r["policy"] == args.policy and r["cohort"] == args.failure_cohort
                       and r["family"] == "guillotine" and r["first_failed_prefix"] is not None),
                      key=lambda r: (r["first_failed_prefix"], r["key"]))
    if failures:
        failure = failures[0]
        key, step = failure["key"], failure["first_failed_prefix"]
        blank, stopped = load(key, step, args.policy)
        earlier, _ = load(key, step - 1, args.policy)
        before = {tuple(sorted(map(tuple, cut))) for cut in earlier["cuts"]}
        newest = next(cut for cut in blank["cuts"] if tuple(sorted(map(tuple, cut))) not in before)
        if stopped["status"] != "conflict":
            raise AssertionError("failure illustration was silently replaced by a success")
        manual = Canvas(1600, 1050, args.font)
        manual.text((55, 27), "新规则仍受阻的完整线网｜供人工标记", size=40)
        display_key = key.replace("heldout-guillotine-", "新种子 ").replace("guillotine-", "旧种子 ")
        manual.text((55, 100), f"{display_key}，第 {step} 刀｜{args.policy}｜这是具体策略失败，不是第五色证明。", size=25, color=MUTED)
        manual.text((55, 171), "外侧1；内部 ? 全部留白，不把失败过程的名字当成正确答案。", size=27)
        draw_adaptive(manual, blank, (55, 238), 1.0, blank=True)
        manual.line([(55 + x, 238 + y) for x, y in newest], color=NEW, width=5)
        manual.text((1005, 265), "橙色：最后加入的线", size=27, color=NEW)
        manual.text((1005, 340), "已对完整新图从头重标。", size=25)
        manual.text((1005, 413), "请优先标注：", size=27, color=LINE_ID)
        for i, note in enumerate(("① 先处理哪条母线", "② 先固定哪个局部侧", "③ 哪组名字应先保留", "④ 哪一步应延迟定名")):
            manual.text((1005, 465 + i * 56), note, size=27)
        manual.text((55, 894), "图中线位置、交点和外框均来自正式测试输入；没有删线或简化拓扑。", size=27, color=MUTED)
        manual.text((55, 958), "若你给出命名顺序，可以逐步和程序的候选表核对，找出仍缺少的约束。", size=27, color=LINE_ID)
        files += manual.save(args.output_dir, "remaining-failure")
    manifest = {"input": {"filename": args.input.name, "sha256": sha256(args.input.read_bytes()).hexdigest()},
                "records": evidence, "files": files, "font": Path(args.font).name,
                "geometry_transform": "Exact uniform scaling; screen x-right/y-down; no simplification.",
                "source_sha256": {p: sha256((ROOT / p).read_bytes()).hexdigest() for p in (
                    "scripts/render_frontier_restart.py", "scripts/render_global_restart.py",
                    "scripts/render_anchor_failure_cases.py", "scripts/validate_frontier_restart.py",
                    "fourcolor/frontier_restart.py")}}
    write_report(args.output_dir / "manifest.json", manifest)
    print({"verified_states": len(evidence), "files": len(files),
           "remaining_failure": failures[0]["key"] if failures else None})


if __name__ == "__main__":
    main()

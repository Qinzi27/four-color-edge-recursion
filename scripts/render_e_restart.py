"""Redraw E from its verified restart, not from the frozen-name control.

Coordinates and current names come from committed states. The saved history is
replayed and both illustrated states independently audited before any export.
Pillow is only a figure dependency; no core naming rule is modified here.
"""

from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_retained_blocks import independent_audits, unpack_state
from scripts.compare_local_marks import validate_state
from scripts.render_anchor_failure_cases import Canvas, draw_map, LINE_ID, MUTED, NEW
from scripts.validate_local_reuse import declared_cases, run_case


# Display letters identify geometric positions, not construction-history IDs.
LABELS = {
    (0, 0, 900, 123): "A", (0, 123, 312, 214): "F",
    (312, 123, 598, 214): "G", (598, 123, 900, 214): "B",
    (0, 214, 900, 471): "M", (0, 214, 454, 471): "L",
    (454, 214, 900, 471): "R", (0, 471, 199, 600): "E",
    (199, 471, 339, 600): "D", (339, 471, 900, 600): "C",
}


def checked_records(source):
    """Require exact replay agreement, then certify every displayed boundary."""
    recorded = next(row for row in source["runs"] if row["key"] == "E_restart")
    case = next(row for row in declared_cases() if row["key"] == "E_restart")
    replay = run_case(case)
    if not replay["all_declared_steps_completed"] or replay["committed_steps"] != 8:
        raise AssertionError("E must complete all eight declared cuts")
    for actual, saved in zip(replay["steps"], recorded["steps"]):
        # JSON stores tuple coordinates as lists; compare restored states.
        if unpack_state(actual["state"]) != unpack_state(saved["state"]):
            raise AssertionError("fresh replay disagrees with the source report")
        if actual["event"]["method"] != "reuse_first_direct":
            raise AssertionError("this figure describes direct steps only")
    if len(recorded["steps"]) != 8:
        raise AssertionError("source history must contain exactly eight steps")
    records = []
    for step in replay["steps"][-2:]:
        state = unpack_state(step["state"])
        graph = validate_state(state)
        display = {s.id: LABELS[s.bounds] for s in state.sides}
        names = {s.id: s.symbol for s in state.sides}
        g_id = next(v for v in graph if display.get(v) == "G")
        if "outside" in graph[g_id] or names[g_id] != 1:
            raise AssertionError("G must be an internal current side named1")
        neighbor_names = sorted({names[v] for v in graph[g_id]})
        if neighbor_names != [2, 3, 4]:
            raise AssertionError("unexpected complete G boundary in restarted E")
        records.append({
            "key": f"E_restart/step{step['construction_step']}",
            "certificate": {"state": step["state"]},
            "display_labels": display,
            "G_full_neighbors": {display[v]: names[v] for v in sorted(graph[g_id])},
            "G_minimum_available_name": min({1, 2, 3, 4} - set(neighbor_names)),
            "event": step["event"],
        })
    if independent_audits(records) != 2:
        raise AssertionError("both committed states require independent certificates")
    return records


def main():
    """Export a non-overwriting before/after image and its portable evidence."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--font", default="msyh.ttc")
    args = parser.parse_args()
    stem = "case-e-restarted"
    if any((args.output_dir / name).exists() for name in
           (stem + ".png", stem + ".svg", "manifest.json")):
        parser.error("output exists; choose a fresh directory")
    raw = args.input.read_bytes()
    records = checked_records(json.loads(raw))
    canvas = Canvas(1900, 980, args.font)
    canvas.text((60, 30), "案例 E 更正｜内部可以复用 1", size=44)
    canvas.text((60, 100), "按相同画线顺序从外圈重算；左右均为合法已提交状态，不是旧名草稿。",
                size=28, color=MUTED)
    for index, record in enumerate(records):
        x, y, scale = 60 + 950 * index, 260, 0.9
        state = record["certificate"]["state"]
        title = "第 7 步后：G 已取 1" if index == 0 else "第 8 步后：新线左 2、右 4"
        canvas.text((x, 175), title, size=32)
        canvas.text((x, 222), "外侧固定 1；字母仅标位置，数字为当前侧名", size=24, color=MUTED)
        draw_map(canvas, state, (x, y), scale)
        if index == 1:
            cut = state["cuts"][-1]
            canvas.line([(x + px * scale, y + py * scale) for px, py in cut],
                        color=NEW, width=5)
        for side in state["sides"]:
            x0, y0, x1, y1 = side["bounds"]
            label = record["display_labels"][side["id"]]
            canvas.text((x + (x0 + x1) * scale / 2, y + (y0 + y1) * scale / 2 - 18),
                        f"{label}: {side['symbol']}", size=32, centered=True,
                        color=LINE_ID if label == "G" else MUTED)
    canvas.text((60, 830), "G 的完整邻名为 {2, 3, 4}，不含 1；最小可用名就是 1。", size=28, color=LINE_ID)
    canvas.text((60, 880), "橙色实线：最后新增且已通过校验的线。两图等比例，几何与原例相同。", size=26, color=MUTED)
    canvas.text((60, 927), "其余名字也按统一规则重算，不能与冻结旧名图拼接；本例成功不等于一般证明。", size=25, color=MUTED)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    files = canvas.save(args.output_dir, stem)
    scripts = [Path(__file__), ROOT / "scripts/render_anchor_failure_cases.py",
               ROOT / "scripts/validate_local_reuse.py", ROOT / "fourcolor/local_reuse.py",
               ROOT / "scripts/audit_retained_blocks.py", ROOT / "scripts/compare_local_marks.py",
               ROOT / "scripts/inherited-oracle.mjs", ROOT / "web/engine.js",
               ROOT / "fourcolor/inherited_names.py", ROOT / "fourcolor/line_names.py"]
    manifest = {
        "schema_version": 1,
        "input": {"filename": args.input.name, "sha256": sha256(raw).hexdigest()},
        "source_case": "E_restart", "source_seed": 20260927,
        "fresh_replay_agrees_with_all_eight_saved_states": True,
        "independent_certificate_count": 2, "records": records,
        "transform": "Exact uniform scale0.9; source x-right/y-down; no source-image edits.",
        "font": Path(args.font).name,
        "code_sha256": {p.relative_to(ROOT).as_posix(): sha256(p.read_bytes()).hexdigest() for p in scripts},
        "files": files,
    }
    with (args.output_dir / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"exported": [f["filename"] for f in files],
                      "independent_certificates": 2}))


if __name__ == "__main__":
    main()

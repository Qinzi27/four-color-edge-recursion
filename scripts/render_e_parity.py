"""Render the exact E five-cycle obstruction as an explicitly uncommitted draft."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.inherited_names import attempt_cut
from scripts.audit_retained_blocks import rectangle_adjacency, unpack_state
from scripts.render_anchor_failure_cases import Canvas, draw_map, MUTED, LINE_ID


def main():
    """Reuse the exact-coordinate canvas; save new PNG/SVG and source metadata."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--font", default="msyh.ttc")
    args = parser.parse_args()
    if any((args.output_dir / name).exists() for name in
           ("case-e-five-cycle.png", "case-e-five-cycle.svg", "manifest.json")):
        parser.error("output exists; choose a fresh directory")
    raw = args.input.read_bytes()
    report = json.loads(raw)
    run = next(r for r in report["runs"] if r["key"] == "E_frozen_start")
    old, cut = unpack_state(run["initial_state"]), run["declared_cuts"][0]
    geometry = attempt_cut(old, cut)["proposed_state"]
    graph = rectangle_adjacency(geometry)
    cycle = ["A", "B", "M.l", "M.r", "F", "A"]
    if any(b not in graph[a] for a, b in zip(cycle, cycle[1:])):
        raise AssertionError("the illustrated cycle no longer matches the geometry")
    old_names = {side.id: side.symbol for side in old.sides}
    labels = {side.id: ("R" if side.id == "M.l" else "L" if side.id == "M.r" else side.id,
                        2 if side.id in ("M.l", "M.r") else old_names[side.id])
              for side in geometry.sides}
    canvas = Canvas(1650, 950, args.font)
    canvas.text((50, 30), "案例 E｜只坚持同一两名，会遇到一个五圈", size=44)
    canvas.text((50, 100), "展示的是保留旧名后的试分割，不是合法终态；这套旧名本来已使用最少四名。",
                size=28, color=MUTED)
    canvas.text((50, 180), "外侧固定 1；字母是侧身份，数字是当前名", size=27)
    draw_map(canvas, run["initial_state"], (50, 230), 1.0, pending=cut)
    for side in geometry.sides:
        x0, y0, x1, y1 = side.bounds
        label, name = labels[side.id]
        canvas.text((50 + (x0 + x1) / 2, 230 + (y0 + y1) / 2 - 18),
                    f"{label}: {name}", size=32, centered=True,
                    color=LINE_ID if side.id in cycle else MUTED)
    explanations = [
        (240, "局部五圈：侧与侧共边", 32),
        (305, "A — B — R — L — F — A", 32),
        (380, "若这五个侧都只允许用 2、3，", 27),
        (425, "沿五条邻接边交替，回到起点", 27),
        (470, "必然冲突。这不是第五色需求。", 27),
        (550, "至少其中一个侧要允许 1 或 4。", 27),
        (615, "虚线：新增线，尚未提交。", 27),
        (660, "当前 L=2、R=2，不能保留同名。", 27),
        (735, "可直接在图上另标你的命名方案。", 27),
    ]
    for y, text, size in explanations:
        canvas.text((1020, y), text, size=size, color=LINE_ID if y == 305 else MUTED)
    canvas.text((50, 882), "原坐标等比例绘制；五圈每一条共边已核验。限制的是此处固定两名，不是否定整体方法。",
                size=25, color=MUTED)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    files = canvas.save(args.output_dir, "case-e-five-cycle")
    scripts = [Path(__file__), ROOT / "scripts/render_anchor_failure_cases.py",
               ROOT / "scripts/audit_retained_blocks.py", ROOT / "fourcolor/inherited_names.py"]
    manifest = {
        "schema_version": 1, "input": {"filename": args.input.name, "sha256": sha256(raw).hexdigest()},
        "code_sha256": {p.relative_to(ROOT).as_posix(): sha256(p.read_bytes()).hexdigest() for p in scripts},
        "source_case": "E_frozen_start", "source_seed": 20260927,
        "old_state": run["initial_state"], "pending_cut": cut, "draft_labels": labels,
        "positive_length_cycle": cycle, "all_cycle_edges_checked": True,
        "transform": "Exact uniform scale 1.0; source x-right/y-down; no source-image edits.",
        "font": Path(args.font).name, "files": files,
    }
    with (args.output_dir / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"exported": [f["filename"] for f in files]}))


if __name__ == "__main__":
    main()

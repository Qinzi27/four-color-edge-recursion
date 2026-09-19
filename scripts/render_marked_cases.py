"""Draw verified A/B naming certificates, without editing the user's sketch.

Reuse the project's exact-geometry SVG/PNG primitives. Source names come only
from the fresh validation report; no colors are inferred from picture pixels.
"""

from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.render_anchor_failure_cases import Canvas, draw_map, MUTED, LINE_ID


def main():
    """Export a new comparison image and provenance; refuse overwriting files."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--font", default="msyh.ttc")
    args = parser.parse_args()
    names = ("marked-a-and-b.png", "marked-a-and-b.svg", "manifest.json")
    if any((args.output_dir / name).exists() for name in names):
        parser.error("Output already exists; use a new directory")
    raw = args.input.read_bytes()
    report = json.loads(raw)
    cases = report["cases"]
    a = cases["user_a_replay"]["final_state"]
    b = cases["b_reverse"]["final_state"]
    canvas = Canvas(1900, 1030, args.font)
    canvas.text((60, 30), "局部侧名更新：A 的手绘结果与 B 的延伸", size=44)
    canvas.text((60, 100), "按原坐标等比绘制；母线身份不变，分段名字随实际侧别更新。", size=28, color=MUTED)
    canvas.text((60, 170), "A｜按你的标注从头回放", size=32)
    canvas.text((1010, 170), "B｜旧名不动，内部新侧取 1", size=32)
    for state, x in ((a, 60), (b, 1010)):
        canvas.text((x, 216), "外侧：1", size=24, color=MUTED)
        draw_map(canvas, state, (x, 265), 0.9, names=False, ids=True)
        for side in state["sides"]:
            x0, y0, x1, y1 = side["bounds"]
            position = (x + (x0 + x1) * 0.45, 265 + (y0 + y1) * 0.45 - 24)
            canvas.text(position, str(side["symbol"]), size=45, centered=True,
                        color=LINE_ID if side["symbol"] == 1 else "#202831")
    canvas.text((60, 834), "横母线 L2 的最终局部名字（上 / 下）：", size=27)
    canvas.text((60, 880), "左段 (4,2) → 短中段 (3,2) → 右段 (3,4)", size=26, color=MUTED)
    canvas.text((1010, 834), "右内部侧的旧邻名只有 {2,3}，兄弟侧为 4。", size=27)
    canvas.text((1010, 880), "它不接外侧 1，因此可以复用名字 1。", size=27, color=LINE_ID)
    canvas.text((60, 963), "已验证的是这两个实例；局部成功不等于一般完备性。L 编号仅用于指认母线，不是颜色。",
                size=25, color=MUTED)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    files = canvas.save(args.output_dir, "marked-a-and-b")
    record = {"schema_version": 1,
              "input": {"filename": args.input.name, "sha256": sha256(raw).hexdigest()},
              "source_sha256": {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in
                                ("scripts/render_marked_cases.py", "scripts/render_anchor_failure_cases.py")},
              "transform": "Uniform source scale 0.9; source x-right/y-down; no geometry edits.",
              "cases": {"A": "user_a_replay", "B": "b_reverse"}, "files": files}
    with (args.output_dir / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"exported": [entry["filename"] for entry in files]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Export the real three-band local block and a blank annotation panel.

The source is the saved continuous-history report, not the hand-drawn image.
Only the committed old names are drawn; no hypothetical fifth name is shown.
"""

from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.render_anchor_failure_cases import Canvas, draw_map, MUTED, NEW


def main():
    """Preserve exact geometry and create fresh PNG/SVG with a manifest."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--font", default="msyh.ttc")
    args = parser.parse_args()
    if any((args.output_dir / name).exists() for name in
           ("case-c-local-block.png", "case-c-local-block.svg", "manifest.json")):
        parser.error("Output exists; choose a new directory")
    raw = args.input.read_bytes()
    report = json.loads(raw)
    selected = [row for row in report["runs"] if row["family"] == "guillotine"
                and row["seed"] == 20260960 and row["inherit"] == "right"]
    if len(selected) != 1:
        raise ValueError("Expected one exact source history")
    row = selected[0]
    old, event = row["last_valid_state"], row["events"][-1]
    if row["status"] != "blocked_sync_required" or event["step"] != 3:
        raise ValueError("Source is not the documented third-step stop")
    canvas = Canvas(1900, 960, args.font)
    canvas.text((60, 32), "案例 C｜只换继承侧仍然不够的局部例子", size=44)
    canvas.text((60, 105), "外侧 1；上、中、下为 3、4、2。中带新增竖线，两子侧旧邻名都是 {1,2,3}。",
                size=28, color=MUTED)
    canvas.text((60, 170), "加线前：旧名", size=30)
    canvas.text((1010, 170), "加线后：供人工标记", size=30)
    canvas.text((60, 218), "外侧：1", size=24, color=MUTED)
    canvas.text((1010, 218), "外侧：请标明", size=24, color=MUTED)
    draw_map(canvas, old, (60, 265), 0.9, names=True, ids=True)
    draw_map(canvas, old, (1010, 265), 0.9, pending=event["cut"])
    canvas.line([(1010, 850), (1080, 850)], color=NEW, width=5, dashed=True)
    canvas.text((1100, 835), "新增 L3；其余线不变", size=27)
    canvas.text((60, 835), "这只否定冻结旧名的一步选择，不是否定四名可行。", size=25, color=MUTED)
    canvas.text((60, 901), "来源：guillotine / seed 20260960 / 第3步；新线 (442,357) → (442,487)。",
                size=25, color=MUTED)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    files = canvas.save(args.output_dir, "case-c-local-block")
    provenance = {"schema_version": 1,
                  "input": {"filename": args.input.name, "sha256": sha256(raw).hexdigest()},
                  "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
                  "source_case": {"family": row["family"], "seed": row["seed"],
                                  "inherit": row["inherit"], "step": event["step"]},
                  "current_state": old, "pending_cut": event["cut"],
                  "transform": "Exact uniform scale 0.9, source x-right/y-down.", "files": files}
    with (args.output_dir / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(provenance, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"exported": [item["filename"] for item in files]}))


if __name__ == "__main__":
    main()

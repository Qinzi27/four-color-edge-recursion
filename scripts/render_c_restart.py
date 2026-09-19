"""Draw the corrected C replay from its verified report, with exact geometry."""

from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.render_anchor_failure_cases import Canvas, draw_map, MUTED


def main():
    """Create new PNG/SVG files and provenance, never replacing old C diagrams."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--font", default="msyh.ttc")
    args = parser.parse_args()
    filenames = ("case-c-restarted.png", "case-c-restarted.svg", "manifest.json")
    if any((args.output_dir / name).exists() for name in filenames):
        parser.error("output exists; select a fresh directory")
    raw = args.input.read_bytes()
    report = json.loads(raw)
    if report["independent_oracle_status"] != "checked":
        parser.error("use the independently checked C report")
    replay = report["declared_left_replay"]
    before, after = replay["steps"][1]["state"], replay["final_state"]
    canvas = Canvas(1900, 960, args.font)
    canvas.text((60, 32), "案例 C 更正｜先按最少复用从外圈重算", size=44)
    canvas.text((60, 105), "旧 3—4—2 合法但非最少；重算为 2—3—2 后，新竖线直接得到 (3,4)。",
                size=28, color=MUTED)
    canvas.text((60, 170), "加竖线前：上、中、下 = 2、3、2", size=30)
    canvas.text((1010, 170), "加竖线后：中左 4，中右继承 3", size=30)
    for x in (60, 1010):
        canvas.text((x, 218), "外侧：1", size=24, color=MUTED)
    draw_map(canvas, before, (60, 265), 0.9, names=True, ids=True)
    draw_map(canvas, after, (1010, 265), 0.9, names=True, ids=True)
    canvas.text((60, 835), "含外侧只需 3 种；上下不相邻，可同名 2。", size=25, color=MUTED)
    canvas.text((1010, 835), "R = {1,2}，继承名 s = 3，新名 t = 4。", size=25, color=MUTED)
    canvas.text((60, 901), "原几何与加线顺序不变；三步均直接命名，无修复旧侧、无配色搜索。本图仅验证案例 C。",
                size=25, color=MUTED)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    files = canvas.save(args.output_dir, "case-c-restarted")
    scripts = [Path(__file__), ROOT / "scripts/render_anchor_failure_cases.py"]
    manifest = {
        "schema_version": 1,
        "input": {"filename": args.input.name, "sha256": sha256(raw).hexdigest()},
        "code_sha256": {p.relative_to(ROOT).as_posix(): sha256(p.read_bytes()).hexdigest() for p in scripts},
        "source_case": report["source"], "before": before, "after": after,
        "transform": "Exact uniform scale 0.9; source x-right/y-down; no source-photo edits.",
        "semantics": "Numbers are side names; L1/L2/L3 are distinct geometric line identities.",
        "font": Path(args.font).name, "files": files,
    }
    with (args.output_dir / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"exported": [item["filename"] for item in files]}))


if __name__ == "__main__":
    main()

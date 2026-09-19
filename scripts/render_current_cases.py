"""Draw one verified repaired STEP and one still-blocked current-rule example."""

from argparse import ArgumentParser
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.interface_names import attempt_interface_cut
from fourcolor.inherited_names import state_payload
from scripts.audit_retained_blocks import independent_audits, unpack_state
from scripts.render_anchor_failure_cases import Canvas, draw_map, MUTED, NEW, LINE_ID
from scripts.validate_current_corpus import digest


def main():
    """Keep geometry exact, line styles explicit, and exports non-overwriting."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--font", default="msyh.ttc")
    args = parser.parse_args()
    stems = ("shared-interface-success", "still-blocked-20260908")
    targets = [stem + ext for stem in stems for ext in (".png", ".svg")] + ["manifest.json"]
    if any((args.output_dir / name).exists() for name in targets):
        parser.error("output exists; choose a fresh directory")
    raw = args.input.read_bytes()
    report = json.loads(gzip.decompress(raw) if args.input.suffix == ".gz" else raw)
    case = next(r for r in report["corpus"]["histories"] if r["key"] == "guillotine-20260911")
    source = next(r for r in report["runs"] if r["key"] == case["key"] and r["policy"] == "interface-b3")
    state, states, last = unpack_state(case["initial_state"]), [], None
    for index, cut in enumerate(case["paths"][:4]):
        last = attempt_interface_cut(state, cut)
        if last["status"] != "split":
            raise AssertionError("the illustrated four-step replay no longer succeeds")
        state = last["state"]
        if digest(state_payload(state)) != source["steps"][index]["state_sha256"]:
            raise AssertionError("illustrated state differs from the formal report")
        states.append(state_payload(state))
    if last["event"]["shared_release"]["before"] != 2 or last["event"]["shared_release"]["after"] != 4:
        raise AssertionError("the illustrated single interface release changed")
    stopped = next(r for r in report["runs"] if r["key"] == "guillotine-20260908" and r["policy"] == "interface-b3")
    retry = attempt_interface_cut(unpack_state(stopped["final_state"]), stopped["pending_path"])
    if retry["status"] != "blocked" or retry["event"]["reason"] != "no_safe_shared_interface_release":
        raise AssertionError("the selected still-blocked example changed")
    records = [{"key": "repair-before", "certificate": {"state": states[-2]}},
               {"key": "repair-after", "certificate": {"state": states[-1]}},
               {"key": "still-blocked-before", "certificate": {"state": stopped["final_state"]}}]
    independent_audits(records)
    canvas = Canvas(1900, 950, args.font)
    canvas.text((60, 30), "解除共同接口锁定｜一处升名即可继续", size=43)
    canvas.text((60, 100), "seed 20260911，第 4 刀：这是一步修复证据，不代表整条 24 刀历史全部完成。", size=27, color=MUTED)
    for index, payload in enumerate(states[-2:]):
        x, y, scale = 60 + index * 950, 245, 0.9
        canvas.text((x, 167), "之前：中栏 3 尚未分割" if index == 0 else "之后：左栏 2→4，新上 2、下 3", size=31)
        canvas.text((x, 212), "外侧固定 1；数字为当前线侧名", size=23, color=MUTED)
        draw_map(canvas, payload, (x, y), scale, names=True,
                 pending=states[-1]["cuts"][-1] if index == 0 else None)
        if index == 1:
            canvas.line([(x + a * scale, y + b * scale) for a, b in payload["cuts"][-1]], color=NEW, width=5)
    canvas.text((60, 820), "原共同禁名 {1, 2, 4} → {1, 4}；释放名字 2，只改一个未拆旧侧。", size=28, color=LINE_ID)
    canvas.text((60, 870), "左图虚线未提交；右图实线及全部名字已独立校验。实际坐标等比例，无几何简化。", size=26, color=MUTED)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    files = canvas.save(args.output_dir, stems[0])
    blocked = Canvas(1650, 960, args.font)
    blocked.text((60, 30), "仍受阻的例子｜共同接口不能单独释放", size=42)
    blocked.text((60, 100), "seed 20260908，第 7 刀；从外圈按当前规则重算，非旧命名截图。", size=27, color=MUTED)
    blocked.text((60, 177), "外侧 1；图中数字是加线前合法名字", size=27)
    draw_map(blocked, stopped["final_state"], (60, 230), 1.0, pending=stopped["pending_path"])
    for side in stopped["final_state"]["sides"]:
        x0, y0, x1, y1 = side["bounds"]
        blocked.text((60 + (x0 + x1) / 2, 230 + (y0 + y1) / 2 - 17),
                     str(side["symbol"]), size=32, centered=True)
    notes = ["待分母侧：3", "两子侧旧邻名均为", "{1, 2, 4}", "因此直接候选都为空。", "内部共同接口也没有", "合法的单侧换名动作。", "下一步需要联合改名，", "或更强的继承选择规则。", "这不是需要第五名的证明。"]
    for index, value in enumerate(notes):
        blocked.text((1020, 250 + index * 57), value, size=27,
                     color=LINE_ID if index in (2, 8) else MUTED)
    blocked.text((60, 886), "橙色虚线：待加入的第 7 刀，未提交。可在这张真实几何上人工标记完整修改方案。", size=26, color=MUTED)
    files += blocked.save(args.output_dir, stems[1])
    manifest = {"input": {"filename": args.input.name, "sha256": sha256(raw).hexdigest()},
                "source_policy": "interface-b3", "source_cases": [case["key"], stopped["key"]],
                "repair_event": last["event"], "stop_event": retry["event"],
                "records": records, "files": files, "font": Path(args.font).name,
                "transform": "Exact uniform scale0.9 in comparison and1.0 in stopped case; x-right/y-down.",
                "source_sha256": {p: sha256((ROOT / p).read_bytes()).hexdigest() for p in
                                  ("scripts/render_current_cases.py", "scripts/render_anchor_failure_cases.py",
                                   "fourcolor/interface_names.py", "fourcolor/current_names.py", "fourcolor/current_geometry.py")}}
    with (args.output_dir / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"image_files": len(files), "independent_states": len(records)}))


if __name__ == "__main__":
    main()

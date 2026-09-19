"""Validate fixed A--E construction histories under the local-reuse proposal.

This is a small, declared fixture set, not a random benchmark or completeness
claim. The core selects one action; rejected histories stop immediately. Every
accepted state is independently rebuilt from its actual strokes by Node and
audited through Python's line rotation checker. Existing reports are untouched.
"""

from argparse import ArgumentParser
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.inherited_names import RectSide, RectState, initial_state, state_payload
from fourcolor.local_reuse import attempt_local_cut
from scripts.audit_retained_blocks import independent_audits, unpack_state
from scripts.compare_local_marks import validate_state


MANIFEST = ROOT / "docs/figures/anchor-failures-2026-09-18/manifest.json"
C_REPORT = ROOT / "outputs/c-restart-2026-09-18-v2.json"

# Exact 900 x 600 teaching-D coordinates, expressing the public strip-chain
# theorem's K2 join P3. T and the exterior are the common fixed interfaces.
D_CUTS = (((0, 180), (900, 180)), ((300, 180), (300, 600)),
          ((600, 180), (600, 600)))
D_PENDING = ((450, 180), (450, 600))

# Exact E coordinates and old names transcribed from HARD_CASE-2026-09-18.md,
# sections 2 and 4. RectSide stores upper-left/lower-right, not width/height.
E_CUTS = (((0, 214), (900, 214)), ((0, 471), (900, 471)),
          ((0, 123), (900, 123)), ((312, 123), (312, 214)),
          ((339, 471), (339, 600)), ((199, 471), (199, 600)),
          ((598, 123), (598, 214)))
E_PENDING = ((454, 214), (454, 471))


def declared_cases():
    """Load fixed geometries, preserving original names separately from replay."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cases = []
    for row in manifest["cases"]:
        if row["case"] not in ("A", "B"):
            continue
        old = unpack_state(row["current_committed_state"])
        cases.append({"key": row["case"] + "_restart", "case": row["case"],
                      "source_seed": row["seed"],
                      "input_kind": "从外圈重新执行完整已声明画线顺序",
                      "start": initial_state(old.width, old.height),
                      "cuts": list(old.cuts) + [row["pending_cut"]],
                      "max_old_sides": 3})
    c_report = json.loads(C_REPORT.read_text(encoding="utf-8"))
    c_final = unpack_state(c_report["declared_left_replay"]["final_state"])
    cases.append({"key": "C_restart", "case": "C",
                  "source_seed": 20260960,
                  "input_kind": "从外圈重新执行完整已声明画线顺序",
                  "start": initial_state(c_final.width, c_final.height),
                  "cuts": list(c_final.cuts), "max_old_sides": 3})
    old_d = RectState(900, 600, (
        RectSide("T", (0, 0, 900, 180), 4),
        RectSide("A", (0, 180, 300, 600), 2),
        RectSide("M", (300, 180, 600, 600), 3),
        RectSide("D", (600, 180, 900, 600), 2)), D_CUTS)
    old_e = RectState(900, 600, (
        RectSide("A", (0, 0, 900, 123), 2),
        RectSide("B", (598, 123, 900, 214), 3),
        RectSide("M", (0, 214, 900, 471), 2),
        RectSide("C", (339, 471, 900, 600), 4),
        RectSide("D", (199, 471, 339, 600), 3),
        RectSide("E", (0, 471, 199, 600), 4),
        RectSide("F", (0, 123, 312, 214), 3),
        RectSide("G", (312, 123, 598, 214), 4)), E_CUTS)
    for key, old, pending in (("D", old_d, D_PENDING), ("E", old_e, E_PENDING)):
        cases.extend([
            {"key": key + "_frozen_start", "case": key,
             "source_seed": 20260927 if key == "E" else None,
             "input_kind": "保留已发表旧命名作起点；允许规则声明的局部修复",
             "start": old, "cuts": [pending], "max_old_sides": 3},
            {"key": key + "_restart", "case": key,
             "source_seed": 20260927 if key == "E" else None,
             "input_kind": "从外圈重新执行完整已声明画线顺序",
             "start": initial_state(), "cuts": list(old.cuts) + [pending],
             "max_old_sides": 3}])
    # This deliberately insufficient budget is a control on the very same D,
    # not an additional map and not evidence against unrestricted repair.
    cases.append({"key": "D_zero_budget_control", "case": "D",
                  "source_seed": None,
                  "input_kind": "同一D旧起点，事先声明零旧侧扩展预算",
                  "start": old_d, "cuts": [D_PENDING], "max_old_sides": 0})
    for case in cases:
        validate_state(case["start"])
    if len(cases) != 8:
        raise AssertionError("exactly the eight declared flows are required")
    return cases


def run_case(case):
    """Stop at the first rejected cut; never retry another pair or history."""
    state, steps = case["start"], []
    for offset, cut in enumerate(case["cuts"], 1):
        before = state
        result = attempt_local_cut(state, cut, max_old_sides=case["max_old_sides"])
        step = {"declared_step": offset, "construction_step": len(before.cuts) + 1,
                "cut": cut, "status": result["status"], "event": result["event"]}
        steps.append(step)
        if result["status"] != "split":
            if result["state"] != before:
                raise AssertionError("a rejection mutated the committed state")
            step["committed_state_unchanged"] = True
            break
        state = result["state"]
        validate_state(state)
        step["state"] = state_payload(state)
    success = sum(step["status"] == "split" for step in steps)
    return {"key": case["key"], "case": case["case"],
            "source_seed": case["source_seed"],
            "input_kind": case["input_kind"], "max_old_sides": case["max_old_sides"],
            "initial_state": state_payload(case["start"]),
            "declared_cuts": case["cuts"], "planned_steps": len(case["cuts"]),
            "committed_steps": success, "all_declared_steps_completed": success == len(case["cuts"]),
            "status": "completed" if success == len(case["cuts"]) else steps[-1]["status"],
            "steps": steps, "final_committed_state": state_payload(state)}


def build_report(with_node_oracle=True):
    """Construct a portable report; callers choose whether and where to write."""
    runs = [run_case(case) for case in declared_cases()]
    # These frozen starts already need four names: do NOT describe E's budget
    # rejection as another nonminimal C starting state. No clique search occurs.
    minimum_witnesses = []
    for key, clique in (("D_frozen_start", ["outside", "T", "A", "M"]),
                        ("E_frozen_start", ["outside", "M", "C", "D"])):
        run = next(run for run in runs if run["key"] == key)
        state = unpack_state(run["initial_state"])
        graph = validate_state(state)
        if any(b not in graph[a] for a in clique for b in clique if a != b):
            raise AssertionError("the stated four-name lower-bound witness is not a clique")
        minimum_witnesses.append({"key": key, "clique": clique,
                                  "minimum_names_including_outside": 4,
                                  "all_six_positive_length_adjacencies_checked": True})
    records = []
    for run in runs:
        records.append({"key": run["key"] + "/initial",
                        "certificate": {"state": run["initial_state"]}})
        records.extend({"key": run["key"] + "/" + str(step["declared_step"]),
                        "certificate": {"state": step["state"]}}
                       for step in run["steps"] if step["status"] == "split")
    count = independent_audits(records) if with_node_oracle else 0
    sources = [MANIFEST, C_REPORT, ROOT / "docs/HARD_CASE-2026-09-18.md",
               ROOT / "docs/STRIP_CHAIN_THEOREM-2026-09-18.md"]
    scripts = [Path(__file__), ROOT / "fourcolor/local_reuse.py",
               ROOT / "fourcolor/inherited_names.py", ROOT / "fourcolor/anchor_forest.py",
               ROOT / "fourcolor/retained_profiles.py", ROOT / "fourcolor/line_names.py",
               ROOT / "scripts/audit_retained_blocks.py", ROOT / "scripts/compare_local_marks.py",
               ROOT / "scripts/inherited-oracle.mjs", ROOT / "web/engine.js"]
    return {
        "schema_version": 1,
        "scope": "固定A至E五份几何，八个预先声明流程；无随机扩展或隐藏重试。",
        "inputs": [{"path": path.relative_to(ROOT).as_posix(),
                    "sha256": sha256(path.read_bytes()).hexdigest()} for path in sources],
        "source_sha256": {path.relative_to(ROOT).as_posix(): sha256(path.read_bytes()).hexdigest()
                          for path in scripts},
        "definitions": {
            "case_namespaces": "A/B/C是9月18日局部标记案例，D/E是闭合重命名交互图的案例；不是该旧交互图中的A/B/C。",
            "replay": "从外1内2重算全部已声明步骤；不是保持旧名字后只补最后一步。",
            "minimality": "本规则优先复用现有名字；不宣称求得一般图全局最少色数。",
            "budget": "双色局部扩展最多纳入的未拆旧侧数；不是图中总侧数。",
            "certificates": "初始及每个提交状态的独立几何证书数量；重复状态不算新地图。",
            "D_provenance": "教学D的900x600条带几何；结构为仓库条带链定理的K2 join P3。",
            "E_provenance": "HARD_CASE-2026-09-18.md第2节精确坐标与展示名字。",
        },
        "limits": ["拒绝只表示本固定规则或预算不适用，不代表不存在四色解。",
                   "从头结果与冻结旧命名结果分栏保留，不以旧策略困难偷换用户起点。",
                   "五份固定几何不能支持一般成功率、一般终止性或完整四色证明。"],
        "summary": {"geometry_count": 5, "declared_flow_count": len(runs),
                    "statuses": dict(Counter(run["status"] for run in runs)),
                    "committed_step_count": sum(run["committed_steps"] for run in runs),
                    "independent_certificate_count": count,
                    "independent_oracle_status": "checked" if with_node_oracle else "explicitly_skipped"},
        "runs": runs, "independent_certificates": records if with_node_oracle else [],
        "minimum_name_witnesses_for_frozen_starts": minimum_witnesses,
    }


def main():
    """Require a fresh user-selected output name and never overwrite evidence."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists; choose a fresh path")
    report = build_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()

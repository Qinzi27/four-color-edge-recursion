"""Render report-backed rectangle recoloring figures without rerunning research.

Example:
    python scripts/render_recoloring_obstruction.py \
        --input outputs/recoloring-obstructions-2026-09-21.json \
        --output-dir docs/figures/recoloring-obstructions-2026-09-21

Requires an already available Matplotlib environment.  The output directory
must not exist.  The report is read-only; all labels, geometry, target colors,
and cost values are taken from its family_records.  The figure illustrates a
specified legal initial coloring, not a history produced by the old greedy
policy.  This is a general research figure, not a journal-compliance claim.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform


def sha256(path: Path) -> str:
    """Hash exact artifact bytes for the manifest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def one_swap_target(record: dict) -> tuple[dict, list[str]]:
    """Validate the displayed target as one complete 1/3 Kempe exchange.

    This is a bounded witness check on supplied colors, not target or path
    search.  It does not mutate or replace any formal experiment result.
    """
    family = record["family"]
    problem = family["problem"]
    initial = problem["initial"]
    selected = next(row for row in family["certificate"]["targets"]
                    if row["residue_colors"] == [1, 2, 3])
    target = selected["target"]
    if selected["changed_old_sides"] != record["quotient"]["minimum_cost"]:
        raise ValueError("the displayed target is not a report-certified optimum")
    adjacency = {v: set() for v in initial}
    for u, v in problem["edges"]:
        adjacency[u].add(v)
        adjacency[v].add(u)
    component, pending = set(), ["v2"]
    while pending:
        v = pending.pop()
        if v in component:
            continue
        if initial[v] not in (1, 3):
            raise ValueError("invalid Kempe seed")
        component.add(v)
        pending.extend(u for u in adjacency[v]
                       if u not in component and initial[u] in (1, 3))
    if component.intersection(problem["fixed"]):
        raise ValueError("the displayed swap changes a fixed side")
    expected = {v: 4 - color if v in component else color
                for v, color in initial.items()}
    if target != expected:
        raise ValueError("target is not exactly the supplied complete component exchange")
    for u, v in problem["edges"] + [problem["daughters"]]:
        if target[u] == target[v]:
            raise ValueError("the displayed endpoint is not proper")
    changed_old = [v for v, weight in problem["weights"].items()
                   if weight and target[v] != initial[v]]
    if len(changed_old) != selected["changed_old_sides"]:
        raise ValueError("displayed changed-side count is inconsistent")
    return target, changed_old


def prepare_data(report: dict) -> dict:
    """Select m=2 geometry and all available growth values from a passed report."""
    if report.get("all_passed") is not True:
        raise ValueError("a successfully validated formal report is required")
    records = {row["m"]: row for row in report["family_records"]}
    if 2 not in records or any(m not in records for m in range(1, 9)):
        raise ValueError("the report must include m=2 and every m from 1 through 8")
    geometry_record = records[2]
    if geometry_record["geometry_audit"].get("passed") is not True:
        raise ValueError("the displayed geometry has not passed its formal audit")
    target, changed_old = one_swap_target(geometry_record)
    growth = []
    for m, row in sorted(records.items()):
        one_swap_target(row)
        growth.append({"m": m, "minimum_changed_old_sides": row["quotient"]["minimum_cost"],
                       "kempe_steps_of_verified_witness": 1,
                       "old_side_count": row["family"]["certificate"]["old_side_count"]})
    return {"geometry_m": 2, "family": geometry_record["family"],
            "displayed_target": target, "changed_old_sides": changed_old,
            "growth_all_report_parameters": growth,
            "growth_displayed_parameters": list(range(1, 9)),
            "scope": "specified legal initial colors; historical greedy reachability not established"}


def render(data: dict, destination: Path) -> list[Path]:
    """Draw exact rectangles and separate cost/step axes using scoped styling."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch, Rectangle
    from matplotlib.ticker import MaxNLocator

    # The three symbolic colors are unordered categories; printed color numbers
    # and old-change hatching carry the meaning even when hues are unavailable.
    palette = {0: "#F3F3F3", 1: "#56B4E9", 2: "#F0E442", 3: "#CC79A7"}
    family = data["family"]
    p = family["problem"]
    bounds = family["bounds"]
    initial, target = p["initial"], data["displayed_target"]
    changed_old = set(data["changed_old_sides"])
    rectangles = family["rectangles"]
    before = {v: box for v, box in rectangles.items() if v not in p["daughters"]}
    before["parent"] = family["parent_rectangle"]
    colors_before = {**initial, "parent": initial[p["daughters"][0]]}
    saved = []
    style = {"font.family": "DejaVu Sans", "font.size": 11,
             "axes.titlesize": 12, "axes.labelsize": 11,
             "svg.fonttype": "none", "figure.facecolor": "white",
             "savefig.facecolor": "white", "hatch.linewidth": 0.7}
    with plt.rc_context(style):
        fig, axes = plt.subplots(3, 1, figsize=(14, 8.6), layout="constrained")
        fig.suptitle("A real guillotine split can require many old color changes", fontsize=17)
        phases = [
            (before, colors_before, "A  Before the final cut: a proper parent coloring", False, False),
            (rectangles, initial, "B  Daughters inherit color 1: the new edge is the only conflict", False, True),
            (rectangles, target, "C  One complete 1/3 Kempe exchange: an optimum with 4 old sides changed", True, False),
        ]
        for ax, (boxes, colors, title, hatch_changes, conflict) in zip(axes, phases):
            ax.set_title(title, loc="left", pad=22)
            ax.set_facecolor(palette[0])
            for v, (xmin, xmax, ymin, ymax) in boxes.items():
                is_daughter = v in p["daughters"]
                hatch = "///" if hatch_changes and v in changed_old else None
                patch = Rectangle((xmin, ymin), xmax - xmin, ymax - ymin,
                                  facecolor=palette[colors[v]], edgecolor="#252525",
                                  linewidth=2.5 if is_daughter or v == "parent" else 1,
                                  hatch=hatch, zorder=2)
                ax.add_patch(patch)
                name = "parent" if v == "parent" else rf"$v_{{{family['index_by_side'][v]}}}$"
                ax.text((xmin+xmax)/2, (ymin+ymax)/2, f"{name}\nc={colors[v]}",
                        ha="center", va="center", fontsize=10, color="black", zorder=5,
                        bbox={"facecolor": palette[colors[v]], "edgecolor": "none", "pad": 0.1})
            if conflict:
                ax.plot([1, 1], [1, 2], color="#B2182B", linewidth=3,
                        linestyle=(0, (3, 2)), zorder=7)
                ax.annotate("same color", xy=(1, 1.93), xytext=(2.4, 2.35),
                            arrowprops={"arrowstyle": "->", "color": "#B2182B"},
                            fontsize=10, color="black", ha="center", clip_on=False)
            ax.text(1, 1.045, "Exterior r: color 0 (fixed)", transform=ax.transAxes,
                    ha="right", va="bottom", fontsize=10)
            ax.set(xlim=(bounds[0] - .25, bounds[1] + .25), ylim=(-.18, 2.18))
            ax.set_aspect("equal")
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)
        handles = [Patch(facecolor=palette[c], edgecolor="black", label=f"Color {c}")
                   for c in (1, 2, 3)]
        handles.extend([Patch(facecolor="white", edgecolor="black", hatch="///",
                              label="Changed old side (counted)"),
                        Patch(facecolor="white", edgecolor="black", linewidth=2.5,
                              label="Daughter side (cost 0)")])
        axes[-1].legend(handles=handles, loc="upper center", bbox_to_anchor=(.5, -.11),
                        ncol=5, frameon=False, fontsize=10)
        fig.supxlabel("m=2; exact rectangle geometry. Initial colors are specified, not asserted to arise from the old greedy policy.",
                      fontsize=11)
        for extension in ("png", "svg"):
            path = destination / f"guillotine-recoloring-m2.{extension}"
            fig.savefig(path, dpi=200, transparent=False)
            saved.append(path)
        plt.close(fig)

        selected = [row for row in data["growth_all_report_parameters"] if 1 <= row["m"] <= 8]
        ms = [row["m"] for row in selected]
        costs = [row["minimum_changed_old_sides"] for row in selected]
        steps = [row["kempe_steps_of_verified_witness"] for row in selected]
        fig, axes = plt.subplots(2, 1, figsize=(8, 6.6), sharex=True, layout="constrained",
                                 gridspec_kw={"height_ratios": [2, 1]})
        fig.suptitle("One swap does not mean few changed old sides", fontsize=16)
        axes[0].plot(ms, costs, marker="o", color="#0072B2", linewidth=1.8)
        axes[0].set(ylabel="Minimum changed old sides", ylim=(0, 17),
                    title="A  Exact endpoint cost: 2m")
        for m, cost in zip(ms, costs):
            axes[0].annotate(str(cost), (m, cost), xytext=(0, 7), textcoords="offset points",
                             ha="center", fontsize=10)
        axes[1].plot(ms, steps, marker="s", color="#A65E00", linewidth=1.8)
        axes[1].set(xlabel="Family parameter m", ylabel="Kempe steps", ylim=(0, 2),
                    title="B  Verified optimal-cost witness: 1 complete swap")
        for ax in axes:
            ax.set_xlim(.7, 8.3)
            ax.set_xticks(ms)
            ax.yaxis.set_major_locator(MaxNLocator(integer=True))
            ax.grid(axis="y", color="#DADADA", linewidth=.6)
            ax.spines[["top", "right"]].set_visible(False)
        fig.supxlabel("Separate count scales; exact constructed instances, with no sampling uncertainty.\nShown: m=1–8. All larger tested parameters remain in figure-data.json.",
                      fontsize=10)
        for extension in ("png", "svg"):
            path = destination / f"guillotine-recoloring-growth.{extension}"
            fig.savefig(path, dpi=200, transparent=False)
            saved.append(path)
        plt.close(fig)
    return saved


def main() -> None:
    """Require an existing formal report and reserve a new artifact directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.input.is_symlink() or not args.input.is_file():
        parser.error("--input must be a real report file")
    if args.output_dir.exists() or args.output_dir.is_symlink():
        parser.error("--output-dir must be new; existing artifacts are never overwritten")
    report_hash = sha256(args.input)
    data = prepare_data(json.loads(args.input.read_text(encoding="utf-8")))
    # Check the optional dependency before creating any output directory.
    import matplotlib
    args.output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = render(data, args.output_dir)
    data_path = args.output_dir / "figure-data.json"
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    caption = (
        "# 图示说明 / Figure description\n\n"
        "双行错缝矩形族 m=2。A 为最后一次切割前的合法初态；B 为两子侧继承父侧颜色后的状态，"
        "新增边 x=1 是唯一冲突；C 为一次完整 1/3 Kempe 交换后的合法最优终点。斜线标出4个改变颜色的旧侧，"
        "粗框标出成本为0的两个子侧。所有矩形接触固定色0的外侧。几何按真实整数坐标绘制。\n\n"
        "增长图将最少旧侧改色数2m与所展示见证的1次Kempe交换分为两个纵轴面板；不使用双轴叠图。"
        "这些是精确构造与证书数值，没有抽样误差或置信区间。显示m=1–8，更大正式参数保留在数据文件。\n\n"
        "范围：指定合法初色；没有证明旧贪心算法会生成这些初色。此图不声称新的四色定理证明或学术原创性。\n\n"
        "Alt text: Three exact two-row rectangular partitions show a proper parent coloring, the single conflict"
        " introduced when equally colored daughters are split, and a proper endpoint after one Kempe exchange."
        " Four old rectangles are hatched as changed. A companion pair of charts shows minimum old-side changes"
        " rising from 2 to 16 for m=1 through 8, while the verified witness uses one complete swap throughout.\n"
    )
    caption_path = args.output_dir / "figure-caption.md"
    caption_path.write_text(caption, encoding="utf-8")
    artifacts.extend([data_path, caption_path])
    if sha256(args.input) != report_hash:
        raise RuntimeError("formal report changed while figures were rendered")
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "input": {"name": args.input.name, "sha256": report_hash},
        "source": {"name": Path(__file__).name, "sha256": sha256(Path(__file__))},
        "python_version": platform.python_version(), "matplotlib_version": matplotlib.__version__,
        "destination": "general research explanation; publisher requirements unspecified",
        "geometry": "untransformed exact coordinates from the formal m=2 record",
        "transformations": ["merge the two daughter boxes to show the pre-cut parent",
                            "choose the supplied residue-color target [1,2,3] and verify its full Kempe component",
                            "display growth parameters 1 through 8; retain every formal parameter in figure-data.json"],
        "randomness": "none", "uncertainty": "none; exact constructed-instance certificates",
        "figure_sizes_inches": {"geometry": [14, 8.6], "growth": [8, 6.6]},
        "png_dpi": 200, "svg_text": "editable text; font appearance depends on reader fonts",
        "palette": {"1": "#56B4E9", "2": "#F0E442", "3": "#CC79A7"},
        "redundant_encodings": "numeric colors, vertex labels, changed-old hatching, daughter outlines",
        "scope": data["scope"],
        "artifacts": [{"name": p.name, "bytes": p.stat().st_size, "sha256": sha256(p)}
                      for p in artifacts],
    }
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output_directory": str(args.output_dir),
                      "artifacts": [p.name for p in artifacts] + [manifest_path.name]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Inventory existing inputs without using old naming results as new answers.

Histories are deduplicated by the complete initial state, ordered directed
paths and declared repair budget. A history, a frozen-name control, a final
drawing and a left/right policy run are deliberately different objects.
The Node helper below calls geometry generators only, never a coloring solver.
"""

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.inherited_names import initial_state, state_payload
from scripts.compare_local_marks import load_cases
from scripts.validate_local_reuse import declared_cases, MANIFEST, C_REPORT
from scripts.validate_retained_profiles import strip_fixtures


ANCHOR_REPORT = ROOT / "outputs/anchor-forest-continuation-2026-09-18-v2.json"
REDUCED_REPORT = ROOT / "outputs/weighted-counterexample-candidate-2026-09-18-v2.json"

NODE_FIXTURES = r"""
import {generatedPaths} from './scripts/construction-experiments.mjs';
import {wholeLineFixtures} from './scripts/whole-line-fixtures.mjs';
import {CONSTRUCTION_CASES} from './web/construction-cases.js';

const generated=[];
for(let i=0;i<240;i++) {
  const seed=20260908+i;
  const family=i<160?'guillotine':i<200?'nested-rings-and-bridges':'boundary-fan';
  generated.push({key:family+'-'+seed,family,seed,cohort:'baseline',
    paths:generatedPaths(family,seed)});
}
for(let i=0;i<60;i++) {
  const seed=20261201+i;
  const family=i<20?'guillotine':i<40?'nested-rings-and-bridges':'boundary-fan';
  generated.push({key:family+'-'+seed,family,seed,cohort:'fresh-seeds',
    paths:generatedPaths(family,seed)});
}
const construction=CONSTRUCTION_CASES.map(item=>({
  key:'construction-'+item.id,family:'construction-gallery',seed:null,
  cohort:'fixed-gallery',paths:item.steps.map(step=>step.points),
  old_expected_statuses:item.steps.map(step=>step.expectedStatus),
  supplied_seed:item.seed?item.seed():null
}));
const statics=wholeLineFixtures().records.map(row=>({
  key:row.id,family:row.family,seed:row.seed,cohort:'baseline',
  document:row.document
}));
for(const row of generated.filter(row=>row.cohort==='fresh-seeds')) {
  statics.push({...row,document:{schemaVersion:1,title:row.key,
    frame:{width:900,height:600},strokes:row.paths.flatMap(points=>
      points.slice(1).map((b,i)=>({a:points[i],b})))}});
}
// Reproduce the geometry-only prefix of export-web-cases.mjs exactly. The
// original final analyzeDrawing call is intentionally not invoked here.
let value=20260907;
const random=()=>((value=(Math.imul(1664525,value)+1013904223)>>>0)/2**32);
for(let n=0;n<30;n++) {
  const strokes=[];
  for(let i=0;i<3+n%10;i++) strokes.push({
    a:[0,Math.round((20+560*random())*1000)/1000],
    b:[900,Math.round((20+560*random())*1000)/1000]});
  statics.push({key:'seeded-lines-'+n,family:'static-random-lines',seed:20260907,
    cohort:'web-validation',sample_index:n,
    document:{title:`Seed 20260907 sample ${n}`,frame:{width:900,height:600},strokes}});
}
console.log(JSON.stringify({generated,construction,statics}));
"""


def _portable(value):
    """Copy tuples and nested records into ordinary JSON-compatible values."""
    return json.loads(json.dumps(value, ensure_ascii=False))


def _digest(value):
    """Hash portable content with stable object-key ordering."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
    return sha256(encoded).hexdigest()


def stroke_set_key(document):
    """Ignore stroke order/direction, NOT geometry segmentation or topology.

    This deliberately modest identity never calls differently segmented input
    the same map. It does identify the forty strip orders' shared final input.
    """
    strokes = sorted({tuple(sorted((tuple(item["a"]), tuple(item["b"]))))
                      for item in document["strokes"]})
    frame = document.get("frame", {"width": 900, "height": 600})
    return _digest({"frame": frame, "undirected_stroke_set": strokes})


def history_document(row):
    """Build final input strokes without inferring legality or selecting names."""
    if row.get("initial_document") is not None:
        result = _portable(row["initial_document"])
        strokes = result["strokes"]
    else:
        state = row["initial_state"]
        result = {"frame": {"width": state["width"], "height": state["height"]}}
        strokes = [{"a": cut[0], "b": cut[1]} for cut in state["cuts"]]
    for points in row["paths"]:
        strokes.extend({"a": a, "b": b} for a, b in zip(points, points[1:]))
    result["strokes"] = strokes
    return result


def build_corpus():
    """Return all declared histories plus a separate static/topological inventory.

    Former blocked reports supply neither names nor truncated paths to the
    baseline replay. Their A--E snapshots are separately marked controls.
    Nonrectangular histories remain in the replay list for explicit rejection.
    """
    raw = subprocess.run(["node", "--input-type=module", "-e", NODE_FIXTURES],
                         cwd=ROOT, capture_output=True, text=True,
                         encoding="utf-8", check=True)
    generated = json.loads(raw.stdout)
    initial = _portable(state_payload(initial_state()))
    histories, index = [], {}

    def add(row, source, source_kind="declared_history"):
        """Keep aliases instead of counting identical reports as fresh inputs."""
        row = _portable(row)
        row.setdefault("initial_state", initial)
        row.setdefault("max_old_sides", 3)
        row.setdefault("seed", None)
        row.setdefault("input_kind", source_kind)
        nonrectangular_path = any(len(points) != 2 or
                                 (points[0][0] != points[-1][0] and points[0][1] != points[-1][1])
                                 for points in row["paths"])
        row.setdefault("scope_hint", "nonrectangular_path_present" if nonrectangular_path
                       else "classify_anchors_and_single_rectangle_during_replay")
        key = _digest({field: row.get(field) for field in
                       ("initial_state", "initial_document", "initial_names",
                        "paths", "max_old_sides")})
        alias = {"key": row["key"], "source": source, "kind": source_kind,
                 "family": row["family"], "cohort": row["cohort"], "seed": row["seed"]}
        if key in index:
            index[key]["aliases"].append(alias)
            return
        row.update({"history_sha256": key, "aliases": [alias]})
        row["final_stroke_set_sha256"] = stroke_set_key(history_document(row))
        histories.append(row)
        index[key] = row

    for row in generated["generated"]:
        add(row, "scripts/construction-experiments.mjs::generatedPaths")
    for row in strip_fixtures():
        add({"key": f"two-anchor-strip-{row['seed']}", **row},
            "scripts/validate_retained_profiles.py::strip_fixtures")
    for row in generated["construction"]:
        seed = row.pop("supplied_seed")
        if seed is not None:
            row.update({"initial_state": None, "initial_document": seed["document"],
                        "initial_names": seed["names"],
                        "scope_hint": "nonrectangular_precolored_initial_state"})
        add(row, "web/construction-cases.js::CONSTRUCTION_CASES")
    for case in declared_cases():
        add({"key": case["key"], "family": "teaching-" + case["case"],
             "cohort": "fixed-restart" if not case["start"].cuts else "frozen-control",
             "seed": case["source_seed"], "initial_state": state_payload(case["start"]),
             "paths": case["cuts"], "max_old_sides": case["max_old_sides"],
             "input_kind": case["input_kind"]},
            "scripts/validate_local_reuse.py::declared_cases")
    for case in load_cases(MANIFEST, ANCHOR_REPORT):
        add({"key": case["case"] + "_frozen_start", "family": "teaching-" + case["case"],
             "cohort": "frozen-control", "seed": case["seed"],
             "initial_state": state_payload(case["state"]), "paths": [case["cut"]],
             "historical_inherit_only": case["original_inherit"]},
            "scripts/compare_local_marks.py::load_cases", "explicit_precolored_control")

    # The previous derivation's three small examples are explicit histories,
    # unlike arbitrary final strokes that might require reordered construction.
    examples = [
        ("user-three-inheritance-steps", [[[0, 200], [900, 200]],
            [[300, 200], [300, 600]], [[0, 400], [300, 400]]]),
        ("parallel-three-cuts", [[[300, 0], [300, 600]],
            [[600, 600], [600, 0]], [[450, 0], [450, 600]]]),
        ("user-sketch-with-final-cut", [[[0, 200], [900, 200]],
            [[300, 200], [300, 600]], [[600, 200], [600, 600]],
            [[450, 200], [450, 600]]]),
    ]
    for key, paths in examples:
        add({"key": key, "family": "symbolic-teaching", "cohort": "fixed-restart",
             "paths": paths}, "scripts/validate_inherited_names.py; scripts/validate_retained_profiles.py")

    # Identify truncated teaching checkpoints of longer historical inputs.
    # This link is explanatory, not a mechanism for choosing a favorable run.
    for row in histories:
        row["prefix_of"] = [other["key"] for other in histories
                            if other["initial_state"] == row["initial_state"]
                            and other["max_old_sides"] == row["max_old_sides"]
                            and len(row["paths"]) < len(other["paths"])
                            and other["paths"][:len(row["paths"])] == row["paths"]]

    static_rows = generated["statics"]
    reduced = json.loads(REDUCED_REPORT.read_text(encoding="utf-8"))
    static_rows.append({"key": "weighted-reduced-candidate", "family": "reduced-static",
                        "seed": None, "cohort": "targeted", "document": reduced["proof"]["document"]})
    static_inventory, static_index = [], {}
    for row in static_rows:
        row = {key: row[key] for key in ("key", "family", "seed", "cohort", "document")}
        key = stroke_set_key(row["document"])
        source = ("scripts/export-web-cases.mjs::geometry_prefix" if row["family"] == "static-random-lines"
                  else REDUCED_REPORT.relative_to(ROOT).as_posix() if row["family"] == "reduced-static"
                  else "scripts/relation-fixtures.mjs::added" if row["cohort"] == "fresh-seeds"
                  else "scripts/whole-line-fixtures.mjs::wholeLineFixtures")
        alias = {field: row[field] for field in ("key", "family", "seed", "cohort")}
        alias["source"] = source
        if key in static_index:
            static_index[key]["aliases"].append(alias)
            continue
        matches = [history["key"] for history in histories
                   if history["final_stroke_set_sha256"] == key]
        row.update({"stroke_set_sha256": key, "aliases": [alias],
                    "matching_history_keys": matches,
                    "classification": ("final_input_of_declared_history" if matches
                                       else "static_input_without_declared_replay"),
                    "replay_policy": "Do not invent an ordered legal history from final strokes."})
        static_inventory.append(row)
        static_index[key] = row

    files = [Path(__file__), MANIFEST, C_REPORT, ANCHOR_REPORT, REDUCED_REPORT]
    files += [ROOT / name for name in (
        "scripts/construction-experiments.mjs", "scripts/inherited-fixtures.mjs",
        "scripts/validate_retained_profiles.py", "scripts/validate_inherited_names.py",
        "scripts/validate_local_reuse.py", "scripts/compare_local_marks.py",
        "scripts/audit_retained_blocks.py", "fourcolor/inherited_names.py",
        "scripts/whole-line-fixtures.mjs", "scripts/relation-fixtures.mjs",
        "scripts/priority-experiments.mjs", "scripts/export-web-cases.mjs",
        "web/construction-cases.js", "web/cases.js", "web/engine.js",
        "docs/HARD_CASE-2026-09-18.md", "docs/STRIP_CHAIN_THEOREM-2026-09-18.md")]
    return {"schema_version": 1, "histories": histories, "static_inventory": static_inventory,
            "source_sha256": {path.relative_to(ROOT).as_posix(): sha256(path.read_bytes()).hexdigest()
                              for path in files},
            "summary": {
                "unique_declared_histories": len(histories),
                "history_aliases": sum(len(row["aliases"]) for row in histories),
                "source_history_counts_by_cohort": dict(Counter(alias["cohort"] for row in histories
                                                                 for alias in row["aliases"])),
                "history_counts_by_cohort": dict(Counter(row["cohort"] for row in histories)),
                "history_counts_by_family": dict(Counter(row["family"] for row in histories)),
                "distinct_history_terminal_stroke_sets": len({row["final_stroke_set_sha256"] for row in histories}),
                "static_source_records": len(static_rows),
                "static_distinct_stroke_sets": len(static_inventory),
                "static_without_declared_history": sum(not row["matching_history_keys"] for row in static_inventory),
            },
            "limits": [
                "160 baseline plus 20 fresh guillotine histories; 40 strip histories share one final drawing.",
                "80 baseline plus 40 fresh nonrectangular ring/fan histories are retained for explicit scope reporting.",
                "Left/right naming-policy outcomes are not additional drawings or current-policy histories.",
                "A/B/C/E are prefixes of existing seeded histories; fixed teaching tests are not independent random samples.",
                "Frozen-name controls and from-outside restarts are separate inputs, never pooled as independent maps.",
                "Stroke-set hashes ignore ordering/direction but not collinear subdivision; no graph-isomorphism claim.",
                "Abstract graph/parity, probability-noise, and exhaustive assignment tests are unit-test domains, not rectangle construction histories.",
            ]}


if __name__ == "__main__":
    # A read-only inventory command: no report or old experiment is overwritten.
    print(json.dumps(build_corpus()["summary"], ensure_ascii=False, indent=2))

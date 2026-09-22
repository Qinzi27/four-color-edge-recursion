"""Generate fixed, outcome-blind drawing histories for the low-color experiment.

The two construction families are sampled with new declared seeds, not claimed
to be previously unknown graph families. All prefixes are retained before any
naming algorithm runs. Input stroke-set deduplication is not graph isomorphism.
This module only generates drawings; it never runs propagation or an oracle.
"""

import json
from pathlib import Path
from random import Random
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.current_corpus import stroke_set_key
from scripts.validate_global_restart import canonical_document


SEEDS = tuple(range(20262201, 20262209))
STEPS = 8
FRAME = {"width": 900, "height": 600}
GUILLOTINE = "holdout-guillotine"
CHORDS = "holdout-full-chord-arrangement"
FAMILIES = (GUILLOTINE, CHORDS)
SOURCE_FILES = (
    "scripts/quaternary_low_color_inputs.py",
    "tests/test_quaternary_low_color_inputs.py",
    "scripts/construction-experiments.mjs",
    "scripts/current_corpus.py",
    "scripts/validate_global_restart.py",
)

NODE_GUILLOTINE = r"""
import {readFileSync} from 'node:fs';
import {generatedPaths} from './scripts/construction-experiments.mjs';
const input = JSON.parse(readFileSync(0, 'utf8'));
// Calling generatedPaths only generates coordinates. No construction/coloring
// method from the imported module is invoked to accept or reject a prefix.
console.log(JSON.stringify(input.seeds.map(seed => ({
  seed, paths: generatedPaths('guillotine', seed).slice(0, input.steps)
}))));
"""


def _guillotine_paths():
    """Reuse the old geometry-only generator without importing old results."""
    exported = subprocess.run(
        ["node", "--input-type=module", "-e", NODE_GUILLOTINE], cwd=ROOT,
        input=json.dumps({"seeds": SEEDS, "steps": STEPS}), capture_output=True,
        text=True, encoding="utf-8", check=True,
    )
    rows = json.loads(exported.stdout)
    if [row["seed"] for row in rows] != list(SEEDS):
        raise AssertionError("Guillotine generator changed the frozen seed order")
    if any(len(row["paths"]) != STEPS for row in rows):
        raise AssertionError("A declared history did not supply all eight cuts")
    return {row["seed"]: row["paths"] for row in rows}


def _chord_paths(seed):
    """Join distinct integer locations on opposite frame sides, in draw order.

    Each stroke is a full left-to-right chord. Sampling without replacement on
    each boundary excludes repeated endpoints and coincident strokes. Interior
    crossings are retained and noded by the geometry engine, never rejected for
    any coloring outcome. No general-position or intersection-count claim is
    inferred merely from this random construction.
    """
    random = Random(seed)
    left = random.sample(range(20, 581), STEPS)
    right = random.sample(range(20, 581), STEPS)
    return [[[0, y_left], [900, y_right]]
            for y_left, y_right in zip(left, right)]


def build_holdout():
    """Return every fixed prefix, its identity, and reconstructible provenance.

    Canonical documents remove only stroke direction, insertion order and exact
    duplicates. Ordered strokes are retained in each history so the actual
    construction is recoverable. A caller must compare keys with prior inputs
    and freeze these actual drawings before testing an algorithm.
    """
    guillotine = _guillotine_paths()
    records, index, histories = [], {}, []
    for seed in SEEDS:
        paths_by_family = {GUILLOTINE: guillotine[seed], CHORDS: _chord_paths(seed)}
        for family in FAMILIES:
            strokes = [{"a": list(a), "b": list(b)}
                       for a, b in paths_by_family[family]]
            prefix_keys = []
            for step in range(STEPS + 1):
                document = canonical_document({"frame": FRAME, "strokes": strokes[:step]})
                if len(document["strokes"]) != step:
                    raise AssertionError("A generated prefix lost a distinct stroke")
                key = stroke_set_key(document)
                alias = {"family": family, "seed": seed, "step": step}
                if key not in index:
                    row = {"key": key, "document": document,
                           "families": [], "aliases": []}
                    records.append(row)
                    index[key] = row
                row = index[key]
                if row["document"] != document:
                    raise AssertionError("Stroke-set hash collision")
                if family not in row["families"]:
                    row["families"].append(family)
                row["aliases"].append(alias)
                prefix_keys.append(key)
            histories.append({"id": f"{family}-{seed}", "family": family,
                              "seed": seed, "prefix_keys": prefix_keys,
                              "ordered_strokes": strokes})
    return {
        "records": records,
        "histories": histories,
        "generation": {
            "version": "quaternary-low-color-inputs-v1",
            "frame": dict(FRAME), "seeds": list(SEEDS),
            "families": list(FAMILIES), "cuts_per_history": STEPS,
            "steps_retained": list(range(STEPS + 1)),
            "history_count": len(histories),
            "prefix_references": sum(len(row["prefix_keys"]) for row in histories),
            "distinct_input_drawings": len(records),
            "guillotine": {
                "source": "scripts/construction-experiments.mjs::generatedPaths",
                "reuse": "first eight paths of generatedPaths('guillotine', seed)",
                "rng": "32-bit LCG: (1664525 * state + 1013904223) modulo 2**32",
                "eligible_cell": "both width and height at least 20 pixels",
                "selection": "uniform index of currently eligible rectangles",
                "axis": "vertical if next draw < 0.5, otherwise horizontal",
                "cut": "round(low + extent * (0.3 + 0.4 * next draw))",
                "scope": "one full-cell cut per stroke; no interior X crossings; no bridges or islands",
            },
            "chords": {
                "rng": "Python standard-library random.Random(seed)",
                "sampling": "sample eight y values without replacement for left, then for right",
                "integer_y_range_inclusive": [20, 580],
                "left_x": 0, "right_x": 900,
                "pairing": "same sampled-list index; retain that insertion order",
                "scope": "full chords; possible interior X or higher-order crossings and point-only face contacts; no bridges or islands",
                "general_position_assumed": False,
            },
            "deduplication": "canonical undirected input stroke set plus frame; not graph isomorphism or collinear segmentation equivalence",
            "outcome_filtering": False, "propagation_performed": False,
            "oracle_performed": False,
            "scope": "finite sampled new-seed histories in two known construction families; correlated prefixes are not independent samples or a universal success probability",
            "prior_input_overlap": "caller must compare actual keys with the frozen previous corpus before interpreting novelty",
            "source_files": list(SOURCE_FILES),
        },
    }

"""Declare coordinate-only fresh prefixes for conditional diamond inference.

All four histories and their empty-to-terminal prefixes are fixed before any
coloring. Fresh seeds in these known families do not create independent graph
families, and the runner must compare keys with every prior frozen inventory.
"""

import json
from pathlib import Path
from random import Random
import subprocess

from scripts.current_corpus import stroke_set_key
from scripts.quaternary_odd_cycle_eq_inputs import FRAME, NODE_GUILLOTINE
from scripts.validate_global_restart import canonical_document

ROOT = Path(__file__).resolve().parents[1]
VERSION = "quaternary-conditional-diamond-holdout-inputs-v1"
SEEDS = (20263011, 20263012)
STEPS = 5
GUILLOTINE = "conditional-diamond-holdout-guillotine"
CHORDS = "conditional-diamond-holdout-full-chord-arrangement"
RANDOM_FAMILIES = (GUILLOTINE, CHORDS)
SOURCE_PATHS = (
    "scripts/quaternary_conditional_diamond_inputs.py",
    "tests/test_quaternary_conditional_diamond_inputs.py",
    "scripts/quaternary_odd_cycle_eq_inputs.py",
    "scripts/construction-experiments.mjs",
    "scripts/current_corpus.py",
    "scripts/validate_global_restart.py",
    "scripts/quaternary_geometry_adapter.py",
    "scripts/audit_quaternary_geometry.py",
    "scripts/restart-geometry.mjs",
)


def guillotine_paths():
    """Reuse the existing coordinate routine with only the declared new seeds."""
    exported = subprocess.run(
        ["node", "--input-type=module", "-e", NODE_GUILLOTINE], cwd=ROOT,
        input=json.dumps({"seeds": SEEDS, "steps": STEPS}), capture_output=True,
        text=True, encoding="utf-8", check=True,
    )
    rows = json.loads(exported.stdout)
    if [row["seed"] for row in rows] != list(SEEDS):
        raise AssertionError("geometry generator changed the declared seed order")
    if any(len(row["paths"]) != STEPS for row in rows):
        raise AssertionError("a declared history did not supply five cuts")
    return {row["seed"]: row["paths"] for row in rows}


def chord_paths(seed):
    """Sample the two endpoint lists independently, retaining insertion order."""
    random = Random(seed)
    left = random.sample(range(20, 581), STEPS)
    right = random.sample(range(20, 581), STEPS)
    return [[[0, first], [900, second]] for first, second in zip(left, right)]


def build_conditional_diamond_holdout():
    """Return all declared prefixes, preserving aliases after stroke deduplication."""
    histories, records, by_key = [], [], {}
    guillotine = guillotine_paths()
    for seed in SEEDS:
        for family, paths in ((GUILLOTINE, guillotine[seed]), (CHORDS, chord_paths(seed))):
            history_id = f"{family}-{seed}"
            strokes = [{"a": list(a), "b": list(b)} for a, b in paths]
            prefix_keys = []
            for step in range(len(strokes) + 1):
                document = canonical_document({"frame": FRAME, "strokes": strokes[:step]})
                if len(document["strokes"]) != step:
                    raise AssertionError("a declared prefix lost a distinct stroke")
                key = stroke_set_key(document)
                alias = {"history": history_id, "family": family, "step": step, "seed": seed}
                if key not in by_key:
                    record = {"key": key, "document": document, "families": [], "aliases": []}
                    records.append(record)
                    by_key[key] = record
                record = by_key[key]
                if record["document"] != document:
                    raise AssertionError("canonical stroke-set hash collision")
                if family not in record["families"]:
                    record["families"].append(family)
                record["aliases"].append(alias)
                prefix_keys.append(key)
            histories.append({"id": history_id, "family": family, "seed": seed,
                              "prefix_keys": prefix_keys, "ordered_strokes": strokes,
                              "terminal_key": prefix_keys[-1]})
    return {
        "version": VERSION, "records": records, "histories": histories,
        "generation": {
            "frame": dict(FRAME), "seeds": list(SEEDS), "cuts_per_seed_history": STEPS,
            "families": list(RANDOM_FAMILIES), "history_count": len(histories),
            "seed_history_count": len(histories), "polygon_history_count": 0,
            "prefix_references": sum(len(row["prefix_keys"]) for row in histories),
            "distinct_input_drawings": len(records),
            "maximum_source_strokes": max(len(row["document"]["strokes"]) for row in records),
            "guillotine": {
                "source": "scripts/construction-experiments.mjs::generatedPaths",
                "reuse": "first five paths of generatedPaths('guillotine', seed)",
                "rng": "32-bit LCG: (1664525 * state + 1013904223) modulo 2**32",
                "scope": "new seeds in a known rectangular-split construction family",
            },
            "chords": {
                "rng": "Python standard-library random.Random(seed)",
                "sampling": "sample five integer y values without replacement for left, then right",
                "integer_y_range_inclusive": [20, 580], "left_x": 0, "right_x": 900,
                "pairing": "same sampled-list index, retain that insertion order",
                "general_position_assumed": False,
                "scope": "new seeds in a known complete-chord construction family",
            },
            "prefix_scope": "empty frame through every terminal stroke; all declared prefixes retained",
            "prefix_initialization": "fresh standard anchors on each prefix; no inherited states or colors",
            "deduplication": "canonical undirected input stroke set plus frame; not graph isomorphism",
            "all_insertion_orders": False, "outcome_filtering": False,
            "geometry_validation_performed_by_generator": False,
            "propagation_performed": False, "oracle_performed": False,
            "colors_inherited_between_prefixes": False,
            "face_budget_for_runner": 40, "source_stroke_budget_for_runner": 80,
            "scope": "finite declared held-out inputs; new seeds and correlated prefixes are not independent graph families or a universal success probability",
            "prior_input_overlap": "caller must compare actual stroke-set keys with every prior frozen manifest and bind the artifacts",
        },
        "direct_source_paths": list(SOURCE_PATHS),
    }

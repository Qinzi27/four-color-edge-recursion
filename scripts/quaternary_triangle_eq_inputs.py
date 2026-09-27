"""Declare fresh geometry histories without running naming or exact search.

New seeds in known construction families are not independent graph families.
The concentric-polygon construction adds a declared geometric shape family,
but its prefixes and different ring counts share strokes and are correlated.
Every prefix is retained before geometry validation or a coloring experiment.
"""

from math import cos, radians, sin
from pathlib import Path
from random import Random
import json
import subprocess

from scripts.current_corpus import stroke_set_key
from scripts.validate_global_restart import canonical_document


ROOT = Path(__file__).resolve().parents[1]
VERSION = "quaternary-triangle-eq-holdout-inputs-v1"
FRAME = {"width": 900, "height": 600}
SEEDS = tuple(range(20262331, 20262335))
STEPS = 6
GUILLOTINE = "eq-holdout-guillotine"
CHORDS = "eq-holdout-full-chord-arrangement"
POLYGONS = "eq-holdout-concentric-polygons"
RANDOM_FAMILIES = (GUILLOTINE, CHORDS)
POLYGON_SIDES = (3, 5)
RING_COUNTS = (1, 2, 3)
ANGLE_OFFSETS = (0, 30)
RADII = (220, 130, 60)
CENTER = (450, 300)
SOURCE_PATHS = (
    "scripts/quaternary_triangle_eq_inputs.py",
    "tests/test_quaternary_triangle_eq_inputs.py",
    "scripts/construction-experiments.mjs",
    "scripts/current_corpus.py",
    "scripts/validate_global_restart.py",
    "scripts/quaternary_geometry_adapter.py",
    "scripts/audit_quaternary_geometry.py",
    "scripts/restart-geometry.mjs",
)

# The imported JavaScript routine constructs coordinates only. In particular,
# no naming, propagation, repair, or exact-search entry point is invoked.
NODE_GUILLOTINE = r"""
import {readFileSync} from 'node:fs';
import {generatedPaths} from './scripts/construction-experiments.mjs';
const input = JSON.parse(readFileSync(0, 'utf8'));
console.log(JSON.stringify(input.seeds.map(seed => ({
  seed, paths: generatedPaths('guillotine', seed).slice(0, input.steps)
}))));
"""


def guillotine_paths():
    """Reuse the fixed geometry routine with the explicitly new seed list."""
    exported = subprocess.run(
        ["node", "--input-type=module", "-e", NODE_GUILLOTINE], cwd=ROOT,
        input=json.dumps({"seeds": SEEDS, "steps": STEPS}), capture_output=True,
        text=True, encoding="utf-8", check=True,
    )
    rows = json.loads(exported.stdout)
    if [row["seed"] for row in rows] != list(SEEDS):
        raise AssertionError("geometry generator changed the declared seed order")
    if any(len(row["paths"]) != STEPS for row in rows):
        raise AssertionError("a declared history did not supply six cuts")
    return {row["seed"]: row["paths"] for row in rows}


def chord_paths(seed):
    """Pair distinct boundary positions using the old construction rule."""
    random = Random(seed)
    left = random.sample(range(20, 581), STEPS)
    right = random.sample(range(20, 581), STEPS)
    return [[[0, first], [900, second]] for first, second in zip(left, right)]


def polygon_paths(sides, ring_count, angle_offset):
    """Draw each regular ring, then the spokes joining it to its predecessor.

    Coordinates use mathematical increasing angles in the literal x/y plane;
    the browser's screen convention does not change incidence. Rounding takes
    place once per shared vertex, so repeated endpoints use identical numbers.
    No segment is extended to the frame, and no crossing or coloring outcome
    changes the declared order, angle, radius, or eight-digit precision.
    """
    if sides not in POLYGON_SIDES or ring_count not in RING_COUNTS:
        raise ValueError("unsupported declared polygon or ring count")
    if angle_offset not in ANGLE_OFFSETS:
        raise ValueError("unsupported declared angle offset")
    rings = [
        [[round(CENTER[0] + radius * cos(radians(angle_offset + 360 * i / sides)), 8),
          round(CENTER[1] + radius * sin(radians(angle_offset + 360 * i / sides)), 8)]
         for i in range(sides)]
        for radius in RADII[:ring_count]
    ]
    paths = []
    for layer, ring in enumerate(rings):
        paths.extend([[list(ring[i]), list(ring[(i + 1) % sides])]
                      for i in range(sides)])
        if layer:
            paths.extend([[list(rings[layer - 1][i]), list(ring[i])]
                          for i in range(sides)])
    return paths


def build_eq_holdout():
    """Return all 20 declared histories and all canonical prefix records.

    Deduplication removes repeated literal stroke sets only. History aliases
    preserve every prefix reference, including nested terminal cases. Geometry
    failures and face-budget exclusions must be reported by the runner; this
    generator does not inspect geometry success or a coloring outcome.
    """
    histories, records, by_key = [], [], {}

    def add_history(history_id, family, paths, metadata):
        """Retain source order separately from canonical current geometry."""
        strokes = [{"a": list(a), "b": list(b)} for a, b in paths]
        prefix_keys = []
        for step in range(len(strokes) + 1):
            document = canonical_document({"frame": FRAME, "strokes": strokes[:step]})
            if len(document["strokes"]) != step:
                raise AssertionError("a declared prefix lost a distinct stroke")
            key = stroke_set_key(document)
            alias = {"history": history_id, "family": family, "step": step, **metadata}
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
        histories.append({"id": history_id, "family": family, **metadata,
                          "prefix_keys": prefix_keys, "ordered_strokes": strokes,
                          "terminal_key": prefix_keys[-1]})

    guillotine = guillotine_paths()
    for seed in SEEDS:
        for family, paths in ((GUILLOTINE, guillotine[seed]), (CHORDS, chord_paths(seed))):
            add_history(f"{family}-{seed}", family, paths, {"seed": seed})
    for sides in POLYGON_SIDES:
        for ring_count in RING_COUNTS:
            for angle_offset in ANGLE_OFFSETS:
                history_id = f"{POLYGONS}-n{sides}-rings{ring_count}-angle{angle_offset}"
                add_history(history_id, POLYGONS,
                            polygon_paths(sides, ring_count, angle_offset),
                            {"polygon_sides": sides, "ring_count": ring_count,
                             "angle_offset_degrees": angle_offset})

    return {
        "version": VERSION, "records": records, "histories": histories,
        "generation": {
            "frame": dict(FRAME), "seeds": list(SEEDS), "cuts_per_seed_history": STEPS,
            "families": [*RANDOM_FAMILIES, POLYGONS],
            "history_count": len(histories),
            "seed_history_count": len(SEEDS) * len(RANDOM_FAMILIES),
            "polygon_history_count": len(POLYGON_SIDES) * len(RING_COUNTS) * len(ANGLE_OFFSETS),
            "prefix_references": sum(len(row["prefix_keys"]) for row in histories),
            "distinct_input_drawings": len(records),
            "maximum_source_strokes": max(len(row["document"]["strokes"]) for row in records),
            "guillotine": {
                "source": "scripts/construction-experiments.mjs::generatedPaths",
                "reuse": "first six paths of generatedPaths('guillotine', seed)",
                "rng": "32-bit LCG: (1664525 * state + 1013904223) modulo 2**32",
                "scope": "new seeds in a known rectangular-split construction family",
            },
            "chords": {
                "rng": "Python standard-library random.Random(seed)",
                "sampling": "sample six integer y values without replacement for left, then right",
                "integer_y_range_inclusive": [20, 580],
                "left_x": 0, "right_x": 900,
                "pairing": "same sampled-list index, retain that insertion order",
                "general_position_assumed": False,
                "scope": "new seeds in a known complete-chord construction family",
            },
            "concentric_polygons": {
                "polygon_sides": list(POLYGON_SIDES), "ring_counts": list(RING_COUNTS),
                "angle_offsets_degrees": list(ANGLE_OFFSETS),
                "center": list(CENTER), "radii_outer_to_inner": list(RADII),
                "coordinate_decimal_places": 8,
                "coordinate_formula": "center + radius * (cos(theta), sin(theta)); theta=offset+360*i/n degrees",
                "construction_order": "complete outer ring; for each subsequent layer, complete inner ring then corresponding spokes",
                "spoke_order": "vertex indices 0 through n-1",
                "frame_attached": False,
                "source_strokes_formula": "polygon_sides * (2 * ring_count - 1)",
                "terminal_global_faces_expected": "polygon_sides * (ring_count - 1) + 3",
            },
            "prefix_scope": "empty frame through every terminal stroke; all declared prefixes retained",
            "deduplication": "canonical undirected input stroke set plus frame; not graph isomorphism",
            "all_insertion_orders": False,
            "outcome_filtering": False, "geometry_validation_performed_by_generator": False,
            "propagation_performed": False, "oracle_performed": False,
            "colors_inherited_between_prefixes": False,
            "face_budget_for_runner": 40, "source_stroke_budget_for_runner": 80,
            "scope": "finite declared held-out inputs; new seeds and correlated prefixes are not independent graph families or a universal success probability",
            "prior_input_overlap": "caller must compare actual stroke-set keys with prior frozen manifests and bind the artifacts",
        },
        "direct_source_paths": list(SOURCE_PATHS),
    }

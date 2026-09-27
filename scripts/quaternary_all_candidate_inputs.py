"""Declare new geometry prefixes for the all-candidate probing experiment.

This module constructs coordinates only. All declared prefixes survive into
the inventory even if a later geometry audit excludes one. New seeds and a
rotated copy of a known polygon family are not independent graph families.
Each prefix must receive fresh standard anchors in the experimental runner;
no colors, candidate exclusions, or learned equalities pass between prefixes.
"""

from math import cos, radians, sin
from pathlib import Path
from random import Random
import json
import subprocess

from scripts.current_corpus import stroke_set_key
from scripts.quaternary_odd_cycle_eq_inputs import CENTER, FRAME, NODE_GUILLOTINE, RADII
from scripts.validate_global_restart import canonical_document


ROOT = Path(__file__).resolve().parents[1]
VERSION = "quaternary-all-candidate-holdout-inputs-v1"
SEEDS = (20262601, 20262602)
STEPS = 5
GUILLOTINE = "all-candidate-holdout-guillotine"
CHORDS = "all-candidate-holdout-full-chord-arrangement"
POLYGONS = "all-candidate-holdout-concentric-polygons"
RANDOM_FAMILIES = (GUILLOTINE, CHORDS)
POLYGON_SIDES = (5, 6, 7)
RING_COUNTS = (2,)
ANGLE_OFFSETS = (17,)
SOURCE_PATHS = (
    "scripts/quaternary_all_candidate_inputs.py",
    "tests/test_quaternary_all_candidate_inputs.py",
    "scripts/quaternary_odd_cycle_eq_inputs.py",
    "scripts/construction-experiments.mjs",
    "scripts/current_corpus.py",
    "scripts/validate_global_restart.py",
    "scripts/quaternary_geometry_adapter.py",
    "scripts/audit_quaternary_geometry.py",
    "scripts/restart-geometry.mjs",
)


def guillotine_paths():
    """Call the frozen coordinate-only Node routine with the new declaration."""
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
    """Reuse the original endpoint sampling rule with five chords per seed."""
    random = Random(seed)
    left = random.sample(range(20, 581), STEPS)
    right = random.sample(range(20, 581), STEPS)
    return [[[0, first], [900, second]] for first, second in zip(left, right)]


def polygon_paths(sides, ring_count, angle_offset):
    """Use the frozen ring/spoke formula with an explicitly new parameter set.

    The older public helper validates its original parameter whitelist. This
    independent declaration repeats its coordinate formula without mutating
    that helper or its globals. Every vertex is rounded once to eight decimal
    places, retaining identical shared endpoints throughout the history.
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


def build_all_candidate_holdout():
    """Return all seven declared histories and their canonical input records.

    Literal stroke-set deduplication preserves aliases for every prefix. The
    caller must bind this declaration before coloring, independently validate
    geometry, and report overlap with all prior frozen input inventories.
    """
    histories, records, by_key = [], [], {}

    def add_history(history_id, family, paths, metadata):
        """Keep insertion order separately from canonical current geometry."""
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
                             "angle_offset_degrees": angle_offset,
                             "polygon_parity": "odd" if sides % 2 else "even"})

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
            "concentric_polygons": {
                "polygon_sides": list(POLYGON_SIDES), "ring_counts": list(RING_COUNTS),
                "angle_offsets_degrees": list(ANGLE_OFFSETS),
                "center": list(CENTER), "radii_outer_to_inner": list(RADII[:2]),
                "coordinate_decimal_places": 8,
                "coordinate_formula": "center + radius * (cos(theta), sin(theta)); theta=offset+360*i/n degrees",
                "construction_order": "complete outer ring; complete inner ring; corresponding spokes",
                "spoke_order": "vertex indices 0 through n-1", "frame_attached": False,
                "even_controls": [6], "odd_sizes": [5, 7],
                "control_scope": "even terminal polygon sizes do not rule out odd common-neighbor cycles elsewhere or in prefixes",
                "source_strokes_formula": "polygon_sides * (2 * ring_count - 1)",
                "terminal_global_faces_expected": "polygon_sides * (ring_count - 1) + 3",
                "scope": "rotation and polygon sizes in a known family, not an independent graph family",
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
            "prior_input_overlap": "caller must compare actual stroke-set keys with prior frozen manifests and bind the artifacts",
        },
        "direct_source_paths": list(SOURCE_PATHS),
    }

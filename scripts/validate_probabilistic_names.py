"""Compare three finite line-side probability baselines without dependencies.

This synthetic experiment is an ablation of known constraints, not a trained
Transformer, a new inference algorithm, or a benchmark of arbitrary plane maps.
Run with ``python scripts/validate_probabilistic_names.py``. Reports use exclusive
creation so an existing result is never silently overwritten.
"""

from argparse import ArgumentParser
from datetime import datetime, timezone
from hashlib import sha256
from itertools import product
import json
import math
from pathlib import Path
import platform
import random
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.embedding import PlaneMap
from fourcolor.examples import dangling_triangle_map, tetrahedron_map, triangle_map
from fourcolor.line_names import audit_line_names
from fourcolor.probabilistic_names import infer_names


SEED = 20260918
PALETTE_SIZE = 4
MODES = ("independent", "orbit", "joint")


def wheel_map(rim_size):
    """Construct a convex rim and central spokes with geometric CCW rotations."""
    points = [(math.cos(2 * math.pi * i / rim_size),
               math.sin(2 * math.pi * i / rim_size)) for i in range(rim_size)]
    points.append((0.0, 0.0))
    edges = tuple((i, (i + 1) % rim_size) for i in range(rim_size))
    edges += tuple((i, rim_size) for i in range(rim_size))
    rotations = {i: [] for i in range(rim_size + 1)}
    for edge_id, (u, v) in enumerate(edges):
        rotations[u].append(2 * edge_id)
        rotations[v].append(2 * edge_id + 1)
    for vertex, darts in rotations.items():
        def angle(dart):
            target = edges[dart // 2][1 - dart % 2]
            return math.atan2(points[target][1] - points[vertex][1],
                              points[target][0] - points[vertex][0])
        darts.sort(key=angle)
    # PlaneMap deliberately uses string vertex identities; dart IDs stay integers.
    return PlaneMap(edges=tuple((str(u), str(v)) for u, v in edges),
                    rotation={str(vertex): tuple(darts) for vertex, darts in rotations.items()})


def maps():
    """Six fixed embedded topologies; repeated noise samples are not new graphs."""
    bridge = PlaneMap(edges=(("A", "B"),), rotation={"A": (0,), "B": (1,)})
    return {"bridge": bridge, "triangle": triangle_map(),
            "dangling_triangle": dangling_triangle_map(),
            "tetrahedron": tetrahedron_map(), "wheel_4": wheel_map(4),
            "wheel_5": wheel_map(5)}


def oracle_configurations(plane_map):
    """Enumerate face labels independently of the line-side inference module.

    The oracle uses PlaneMap's existing dart-to-face relation and tests each
    separator directly. Bridges have one face on both shores and impose no
    inequality. This is an equivalent representation, not a weaker competitor.
    """
    labels = []
    for face_labels in product(range(PALETTE_SIZE), repeat=len(plane_map.faces)):
        if any(plane_map.face_of_dart[2 * e] != plane_map.face_of_dart[2 * e + 1]
               and face_labels[plane_map.face_of_dart[2 * e]]
               == face_labels[plane_map.face_of_dart[2 * e + 1]]
               for e in range(len(plane_map.edges))):
            continue
        labels.append(tuple(face_labels[plane_map.face_of_dart[d]]
                            for d in range(2 * len(plane_map.edges))))
    return tuple(labels)


def oracle_posterior(configurations, likelihoods):
    """Use ordinary products on these tiny inputs, independent of log-space code."""
    weights = [math.prod(likelihoods[d][color] for d, color in enumerate(labels))
               for labels in configurations]
    total = math.fsum(weights)
    if total <= 0:
        raise AssertionError("Generated ground truth must have positive likelihood")
    marginals = tuple(tuple(math.fsum(w for labels, w in zip(configurations, weights)
                                    if labels[d] == color) / total
                            for color in range(PALETTE_SIZE))
                      for d in range(len(likelihoods)))
    return marginals, math.log(total), max(weights) / total


def observation(rng, truth, error_rate, missing_rate):
    """Matched four-symbol substitution channel; missingness is independent.

    Each observed dart is an independent noisy measurement. Repeated readings
    of a side are deliberately independent here; real duplicate observations
    would need a different likelihood to avoid double-counting evidence.
    """
    observed, likelihoods = [], []
    for label in truth:
        if rng.random() < missing_rate:
            observed.append(None)
            likelihoods.append((1.0,) * PALETTE_SIZE)
            continue
        value = label
        if rng.random() < error_rate:
            value = rng.choice([c for c in range(PALETTE_SIZE) if c != label])
        observed.append(value)
        likelihoods.append(tuple(1 - error_rate if c == value
                                 else error_rate / (PALETTE_SIZE - 1)
                                 for c in range(PALETTE_SIZE)))
    return observed, tuple(likelihoods)


def metrics(result, truth, observed, rotation):
    """Separate marginal decisions from the model's full MAP configuration.

    Marginal argmax can violate a joint constraint even for exact inference.
    Full MAP is used only for legality and configuration recovery. Brier score
    is sum over classes, averaged over darts (not additionally divided by q).
    """
    predictions = [max(range(PALETTE_SIZE), key=lambda c: row[c])
                   for row in result.dart_marginals]
    hidden = [d for d, value in enumerate(observed) if value is None]
    scores = [sum((p - int(color == truth[d])) ** 2 for color, p in enumerate(row))
              for d, row in enumerate(result.dart_marginals)]
    names = tuple((str(result.map_labels[d]), str(result.map_labels[d + 1]))
                  for d in range(0, len(truth), 2))
    return {
        "marginal_top1_correct": sum(a == b for a, b in zip(predictions, truth)),
        "darts": len(truth), "brier_sum": sum(scores),
        "hidden_top1_correct": sum(predictions[d] == truth[d] for d in hidden),
        "hidden_darts": len(hidden), "hidden_brier_sum": sum(scores[d] for d in hidden),
        "map_legal": audit_line_names(rotation, names).status == "consistent",
        "map_exact_truth": tuple(result.map_labels) == tuple(truth),
    }


def summarize(records):
    """Pool dart-weighted errors; graph-level legality gives each case one vote."""
    summary = {}
    for mode in MODES:
        rows = [case["models"][mode] for case in records]
        darts = sum(row["darts"] for row in rows)
        hidden = sum(row["hidden_darts"] for row in rows)
        summary[mode] = {
            "cases": len(rows),
            "marginal_top1_accuracy": sum(r["marginal_top1_correct"] for r in rows) / darts,
            "mean_brier": sum(r["brier_sum"] for r in rows) / darts,
            "hidden_top1_accuracy": (sum(r["hidden_top1_correct"] for r in rows) / hidden
                                     if hidden else None),
            "hidden_mean_brier": (sum(r["hidden_brier_sum"] for r in rows) / hidden
                                  if hidden else None),
            "map_legal_fraction": sum(r["map_legal"] for r in rows) / len(rows),
            "map_exact_truth_fraction": sum(r["map_exact_truth"] for r in rows) / len(rows),
        }
    return summary


def boundary_witness():
    """Single marginals cannot distinguish equality from inequality at an interface."""
    result = {}
    for name, plane_map in (("same_side_bridge", maps()["bridge"]),
                            ("different_sides_triangle", triangle_map())):
        configurations = oracle_configurations(plane_map)
        p_equal = sum(labels[0] == labels[1] for labels in configurations) / len(configurations)
        marginal0 = [sum(labels[0] == c for labels in configurations) / len(configurations)
                     for c in range(PALETTE_SIZE)]
        marginal1 = [sum(labels[1] == c for labels in configurations) / len(configurations)
                     for c in range(PALETTE_SIZE)]
        result[name] = {"exact_probability_equal": p_equal,
                        "product_of_single_marginals_probability_equal":
                            sum(a * b for a, b in zip(marginal0, marginal1)),
                        "marginals": [marginal0, marginal1]}
    assert result["same_side_bridge"]["exact_probability_equal"] == 1
    assert result["different_sides_triangle"]["exact_probability_equal"] == 0
    return result


def run(seed, repeats):
    """Run paired ablations and require an independent posterior oracle match."""
    rng = random.Random(seed)
    cases, topology_records = [], {}
    max_error, max_logz_error = 0.0, 0.0
    for family, plane_map in maps().items():
        rotation = tuple(plane_map.rotation.values())
        configurations = oracle_configurations(plane_map)
        topology_records[family] = {
            "edges": len(plane_map.edges), "side_classes": len(plane_map.faces),
            "rotation": rotation, "proper_assignments": len(configurations),
            "joint_candidate_assignments": PALETTE_SIZE ** len(plane_map.faces),
        }
        for error_rate in (0.0, 0.15, 0.35):
            for repeat in range(repeats):
                truth = rng.choice(configurations)
                observed, likelihoods = observation(rng, truth, error_rate, 0.5)
                expected, expected_logz, expected_map_p = oracle_posterior(configurations, likelihoods)
                model_results = {}
                for mode in MODES:
                    inference = infer_names(rotation, likelihoods, mode=mode)
                    model_results[mode] = metrics(inference, truth, observed, rotation)
                    if mode == "joint":
                        error = max(abs(a - b) for row_a, row_b in
                                    zip(inference.dart_marginals, expected)
                                    for a, b in zip(row_a, row_b))
                        logz_error = abs(inference.log_partition - expected_logz)
                        map_weight = math.prod(likelihoods[d][c]
                                               for d, c in enumerate(inference.map_labels))
                        map_p = map_weight / math.exp(expected_logz)
                        assert error < 1e-10 and logz_error < 1e-10
                        assert abs(map_p - expected_map_p) < 1e-10
                        max_error, max_logz_error = max(max_error, error), max(max_logz_error, logz_error)
                cases.append({"family": family, "error_rate": error_rate, "repeat": repeat,
                              "truth_dart_labels": truth, "observed_dart_labels": observed,
                              "models": model_results})
    return {
        "schema_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(), "seed": seed,
        "palette_size": PALETTE_SIZE, "repeats_per_family_noise_level": repeats,
        "missing_rate": 0.5, "noise_rates": [0.0, 0.15, 0.35],
        "scope": "Six fixed plane maps, synthetic matched noise, no training or generalization claims.",
        "prior": "Uniform over all proper full side namings for each fixed topology.",
        "likelihood": "Independent dart observations; correct 1-epsilon, each wrong epsilon/3; missing is constant 1.",
        "models": {"independent": "Independent dart labels; topology ignored in probability.",
                   "orbit": "Exact same-side equality; separator inequalities omitted.",
                   "joint": "All same-side and separator constraints; bounded exact enumeration."},
        "oracle": {"method": "Independent face-coordinate exhaustive weighted sum",
                   "cases_compared": len(cases), "max_marginal_abs_error": max_error,
                   "max_log_partition_abs_error": max_logz_error,
                   "map_weight_checks_passed": len(cases)},
        "topologies": topology_records, "summary": summarize(cases),
        "by_noise": {str(e): summarize([c for c in cases if c["error_rate"] == e])
                     for e in (0.0, 0.15, 0.35)},
        "boundary_correlation_witness": boundary_witness(), "cases": cases,
        "source_sha256": {p: sha256((ROOT / p).read_bytes()).hexdigest()
                          for p in ("fourcolor/probabilistic_names.py", "fourcolor/line_names.py",
                                    "fourcolor/embedding.py", "fourcolor/examples.py",
                                    "scripts/validate_probabilistic_names.py")},
    }


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--repeats", type=int, default=12)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.repeats < 1 or args.repeats > 100:
        parser.error("--repeats must be in 1..100 for this bounded experiment")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = args.output or ROOT / "outputs" / f"probabilistic-names-{stamp}.json"
    if destination.exists():
        parser.error("output already exists; choose a fresh name")
    report = run(args.seed, args.repeats)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"cases": len(report["cases"]), "oracle": report["oracle"],
                      "summary": report["summary"]}, ensure_ascii=False, indent=2))
    print(f"Report written: {destination.name}")


if __name__ == "__main__":
    main()

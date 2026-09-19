"""Explore geometry-only mother-line generations without changing the colorer.

The selected six regressions and matched known-success controls are diagnostic
data, not an unseen prediction test. Only true endpoints of complete straight
mothers participate in generation inference. Internal T/X contacts remain
recorded but do not split a mother or become its inferred endpoint parents.
"""

from argparse import ArgumentParser
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.frontier_restart import restart_frontier_names
from fourcolor.relation_frontier import POLICY
from fourcolor.whole_lines import build_whole_lines
from scripts.validate_frontier_restart import file_sha, json_value, read_json, verify_result
from scripts.validate_global_restart import compact_result, digest, export_geometries, write_report
from scripts.validate_relation_frontier_full import exact_run, require, source_hashes, validate_inventory

SOURCE = ROOT / "outputs/relation-frontier-full-2026-09-19.json.gz"
CHOICES = ROOT / "outputs/minimum-names-full-2026-09-19.json.gz"


def derive_generations(contacts):
    """Find earliest double-end support rounds with AND/OR attachment semantics.

    Both ports require support (AND); at one port any established contacting
    mother suffices (OR). A synchronous round cannot cite another new line in
    that same round. Unreachable/cyclic support is left unranked, not repaired.
    Port counts expand shared ancestors repeatedly; distinct counts do not.
    Ambiguous minimum parents retain all choices and receive no invented count.
    """
    require("frame" in contacts, "an explicit frame root is required")
    require(all(len(ends) == 2 for ends in contacts.values()), "exactly two endpoint contact sets required")
    require(all(p in contacts and p != line for line, ends in contacts.items()
                for port in ends for p in port), "unknown or self endpoint parent")
    result = {line: {"depth": None, "parent_depths": None, "parents": [[], []],
                     "port_count": None, "distinct_count": None, "ancestor_ids": None}
              for line in contacts}
    result["frame"] = {"depth": 0, "parent_depths": None, "parents": [[], []],
                       "port_count": 0, "distinct_count": 0, "ancestor_ids": []}
    while True:
        additions = {}
        for line in sorted(contacts):
            if result[line]["depth"] is not None:
                continue
            known = [[p for p in set(port) if result[p]["depth"] is not None]
                     for port in contacts[line]]
            if not all(known):
                continue
            levels = [min(result[p]["depth"] for p in port) for port in known]
            parents = [sorted(p for p in port if result[p]["depth"] == level)
                       for port, level in zip(known, levels)]
            item = {"depth": 1 + max(levels), "parent_depths": levels,
                    "parents": parents, "port_count": None, "distinct_count": None,
                    "ancestor_ids": None}
            if all(len(port) == 1 for port in parents):
                p, q = (result[port[0]] for port in parents)
                if p["port_count"] is not None and q["port_count"] is not None:
                    ancestry = sorted({line} | set(p["ancestor_ids"]) | set(q["ancestor_ids"]))
                    item.update({"port_count": 1 + p["port_count"] + q["port_count"],
                                 "distinct_count": len(ancestry), "ancestor_ids": ancestry})
            additions[line] = item
        if not additions:
            return result
        result.update(additions)


def extract_whole_contacts(model):
    """Use real endpoint vertices, not current_segments' interior junction ports."""
    owners = defaultdict(set)
    for edge, line in model.edge_owner.items():
        for vertex in model.plane_map.edges[edge]:
            owners[vertex].add(line)
    contacts, details = {}, {}
    for line in model.lines:
        identifier = line["id"]
        if identifier == "frame":
            contacts[identifier] = [[], []]
            details[identifier] = {"endpoint_vertices": [], "endpoints": [], "interior_contacts": []}
            continue
        first, last = line["spans"][0]["dart"], line["spans"][-1]["dart"]
        endpoints = [model.plane_map.edges[first // 2][first % 2],
                     model.plane_map.edges[last // 2][1 - last % 2]]
        contacts[identifier] = [sorted(owners[v] - {identifier}) for v in endpoints]
        interior = sorted({port[0] for event in line["events"] if 1e-9 < event["t"] < 1 - 1e-9
                           for port in event["ports_ccw"] if port[0] != identifier})
        details[identifier] = {"endpoint_vertices": endpoints, "endpoints": line["endpoints"],
                               "interior_contacts": interior}
    return contacts, details


def line_features(model, old_colors):
    """Separate color-blind geometry features from diagnostic final color pairs."""
    contacts, details = extract_whole_contacts(model)
    generations = derive_generations(contacts)
    features = {}
    siblings = defaultdict(list)
    for line in model.lines:
        identifier = line["id"]
        profile = [{"t0": span["t0"], "t1": span["t1"],
                    "pair": [old_colors[span["left_side"]], old_colors[span["right_side"]]]}
                   for span in line["spans"]]
        types = sorted({tuple(sorted(span["pair"])) for span in profile})
        features[identifier] = {**generations[identifier], **details[identifier],
                                "endpoint_contacts": contacts[identifier],
                                "profile_in_old_valid_coloring": profile,
                                "unordered_pair_types": [list(pair) for pair in types],
                                "uniform_pair": list(types[0]) if len(types) == 1 else None,
                                "sibling_coordinate_index": None, "sibling_count": None}
        item = generations[identifier]
        if identifier != "frame" and item["depth"] is not None and all(len(p) == 1 for p in item["parents"]):
            siblings[tuple(p[0] for p in item["parents"])].append(identifier)
    for group in siblings.values():
        # Explicit display convention, not a rotation-invariant preferred order.
        group.sort(key=lambda name: tuple(tuple(p) for p in features[name]["endpoints"]))
        for index, identifier in enumerate(group, 1):
            features[identifier].update({"sibling_coordinate_index": index, "sibling_count": len(group)})
    return features


def history_names(record):
    """Use declared source histories, not the geometry's sorted stroke indices."""
    return sorted({a["history"] for a in record["aliases"]
                   if a.get("kind") == "history_prefix" and a["history"].startswith("guillotine-")})


def select_cases(source):
    """Fix six failures plus six equal-size success controls for each failure.

    Controls come from distinct old guillotine histories, excluding ALL known
    failure histories. Selection is key-sorted and outcome-aware by design:
    these are explanatory controls, not a success-rate or predictive estimate.
    """
    rows = validate_inventory(source)
    failures = sorted((r for r in rows if r["runs"][POLICY]["status"] == "conflict"),
                      key=lambda r: (r["face_count"], r["key"]))
    require(len(failures) == 6, "expected the frozen six known regressions")
    used_histories = set().union(*(set(history_names(r)) for r in failures))
    selected, matches = list(failures), {}
    for failure in failures:
        picked = []
        for row in rows:
            names = set(history_names(row))
            if (row["face_count"] != failure["face_count"] or not names or names & used_histories
                    or row["runs"][POLICY]["status"] != "solved"
                    or row["runs"]["tight-hall"]["status"] != "solved"):
                continue
            picked.append(row)
            used_histories.update(names)
            if len(picked) == 6:
                break
        require(len(picked) == 6, "not enough declared equal-size controls")
        selected.extend(picked)
        matches[failure["key"]] = [r["key"] for r in picked]
    require(len({r["key"] for r in selected}) == 42, "diagnostic inputs must be distinct")
    return selected, matches


def describe_trace(trace, model, features, minimum_audit=False):
    """Attach geometry-only measurements to old recorded naming occurrences.

    An active trace entry names one local shore, not necessarily an entire
    mother. Its mother depth therefore describes the location of a decision,
    not a measured time at which the whole parent line became fully named.
    """
    described = []
    for index, step in enumerate(trace, 1):
        mother = model.edge_owner[step["dart"] // 2]
        item = features[mother]
        described.append({"index": index, "mother": mother, "side": step["side"],
                          "dart": step["dart"], "symbol": step["chosen"] if minimum_audit else step["symbol"],
                          "domain": step["domain"], "depth": item["depth"],
                          "parent_depths": item["parent_depths"], "parents": item["parents"],
                          "port_count": item["port_count"], "distinct_count": item["distinct_count"],
                          "sibling_coordinate_index": item["sibling_coordinate_index"],
                          "sibling_count": item["sibling_count"]})
    return described


def first_difference(old, new, fields):
    """Do not confuse a different boundary occurrence with a different shore name."""
    for a, b in zip(old, new):
        if any(a[field] != b[field] for field in fields):
            classification = ("unranked" if a["depth"] is None or b["depth"] is None else
                              "old_shallower" if a["depth"] < b["depth"] else
                              "old_deeper" if a["depth"] > b["depth"] else "same_depth")
            return {"old": a, "current": b, "classification": classification}
    return {"old": None, "current": None,
            "classification": "identical_trace" if len(old) == len(new) else "one_trace_ends_first"}


def summarize(records):
    """Report descriptive patterns only; no selected-control success estimate."""
    groups = {}
    for name in ("six-regressions", "matched-known-successes"):
        rows = [r for r in records if r["group"] == name]
        pairs = [r["pair23_depths"] for r in rows]
        groups[name] = {"drawings": len(rows),
                       "all_whole_lines_ranked": sum(not r["unranked_lines"] for r in rows),
                       "first_occurrence_difference": dict(Counter(r["first_occurrence_difference"]["classification"]
                                                                     for r in rows)),
                       "first_commitment_difference": dict(Counter(r["first_commitment_difference"]["classification"]
                                                                     for r in rows)),
                       "uniform_23_at_multiple_depths": sum(len(p["uniform"]) > 1 for p in pairs),
                       "local_23_at_multiple_depths": sum(len(p["local"]) > 1 for p in pairs)}
    return groups


def build_report(source_path, choices_path, manifest_path):
    """Keep inputs frozen and emit the selection BEFORE examining feature values."""
    source, choices = read_json(source_path), read_json(choices_path)
    selected, matched = select_cases(source)
    hashes = source_hashes()
    require(hashes == source["source_sha256"] == source["source_sha256_end"], "original source changed")
    require(choices["full_corpus_run"] and choices["source"]["sha256"] == file_sha(source_path),
            "choice records refer to a different source")
    hashes["scripts/analyze_line_generations.py"] = file_sha(Path(__file__))
    inputs = [{"filename": p.name, "sha256": file_sha(p)} for p in (source_path, choices_path)]
    manifest = {"selected_keys": [r["key"] for r in selected], "matched_controls": matched,
                "selection": "six known regressions; six equal-face-count, distinct-old-guillotine-history successful controls per regression; key sorted",
                "source_sha256": hashes, "inputs": inputs, "coloring_policy_changed": False,
                "prospective_policy_test": False}
    require(not manifest_path.exists(), "choose a fresh selection manifest")
    write_report(manifest_path, manifest)
    by_key = {r["key"]: r for r in choices["records"]}
    failure_keys = {r["key"] for r in selected[:6]}
    exported_rows = export_geometries(selected)
    require(len(exported_rows) == len(selected), "geometry export coverage mismatch")
    records = []
    for saved, exported in zip(selected, exported_rows):
        require(exported["key"] == saved["key"] and exported["status"] == "geometry_ok",
                "geometry export mismatch")
        geometry = exported["geometry"]
        require(digest(geometry) == saved["geometry_sha256"], "geometry hash changed")
        old = restart_frontier_names(geometry, "tight-hall")
        exact_run(compact_result(old), saved["runs"]["tight-hall"])
        checked = verify_result(geometry, old)
        require(old["status"] == "solved" and checked["passed"], "old coloring is not a valid witness")
        current = by_key[saved["key"]]
        require(current["geometry_sha256"] == saved["geometry_sha256"], "stored choice geometry mismatch")
        for field in ("status", "trace_sha256", "propagation_phases_sha256"):
            require(current[field] == saved["runs"][POLICY][field], "stored current run drift")
        model = build_whole_lines(geometry)
        features = line_features(model, old["colors"])
        old_trace = describe_trace(old["trace"], model, features)
        new_trace = describe_trace(current["decisions"], model, features, minimum_audit=True)
        uniform = sorted({f["depth"] for name, f in features.items() if name != "frame"
                          and f["depth"] is not None and f["uniform_pair"] == [2, 3]})
        local = sorted({f["depth"] for name, f in features.items() if name != "frame"
                        and f["depth"] is not None and [2, 3] in f["unordered_pair_types"]})
        records.append({"key": saved["key"], "aliases": saved["aliases"], "face_count": saved["face_count"],
                        "group": "six-regressions" if saved["key"] in failure_keys else "matched-known-successes",
                        "geometry_sha256": saved["geometry_sha256"], "document": saved["document"],
                        "lines": features, "unranked_lines": [n for n, f in features.items() if f["depth"] is None],
                        "generation_counts": dict(Counter(f["depth"] for n, f in features.items()
                                                          if n != "frame" and f["depth"] is not None)),
                        "old_trace": old_trace, "current_trace": new_trace,
                        "old_witness_verification": checked,
                        "first_occurrence_difference": first_difference(old_trace, new_trace, ("dart", "side", "symbol")),
                        "first_commitment_difference": first_difference(old_trace, new_trace, ("side", "symbol")),
                        "pair23_depths": {"uniform": uniform, "local": local}})
    ending = source_hashes()
    ending["scripts/analyze_line_generations.py"] = file_sha(Path(__file__))
    require(ending == hashes, "analysis or solver code changed during run")
    require(inputs == [{"filename": p.name, "sha256": file_sha(p)} for p in (source_path, choices_path)],
            "input reports changed during run")
    return {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            **manifest, "source_sha256_end": ending, "records": records, "summary": summarize(records),
            "limits": ["Exploratory retrospective diagnosis on 42 outcome-selected maps, not a full-corpus policy test.",
                       "Generation is the earliest double-end geometric support, not unique historical ancestry.",
                       "Final valid colors label examples only; they are NOT inputs to generation/count functions.",
                       "Active naming occurrences are not completion times of whole mothers.",
                       "Geometric sibling order uses the current coordinate direction; it is not an invariant safe ordering.",
                       "A shallower successful choice association does not establish causal safety or universal completion."]}


def main():
    """Save a new portable report without editing production rules or old evidence."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--choices", type=Path, default=CHOICES)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    if any(p.exists() for p in (args.manifest, args.output, args.summary)):
        parser.error("choose fresh output paths")
    if len({p.resolve() for p in (args.manifest, args.output, args.summary)}) != 3:
        parser.error("output paths must differ")
    if sys.flags.optimize:
        parser.error("independent checks require Python without -O")
    report = build_report(args.source, args.choices, args.manifest)
    write_report(args.output, report)
    small = {k: v for k, v in report.items() if k != "records"}
    small["report_sha256"] = file_sha(args.output)
    write_report(args.summary, small)
    print(json_value({"complete": True, "summary": report["summary"], "sha256": small["report_sha256"]}))


if __name__ == "__main__":
    main()

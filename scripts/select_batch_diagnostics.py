"""Freeze an already-seen regression/tuning set for peer-batch experiments.

This script selects geometry only. It never runs a coloring algorithm, examines
its old color values, or imports the proposed peer-batch solver. Known failures
and earlier diagnostic cases are retained; successful controls are selected by
size and distinct drawing history with a deterministic hash tie-break. This is
not an unseen holdout and must not be presented as evidence of generality.
"""

from argparse import ArgumentParser
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "outputs/staged-levels-full-2026-09-19.json.gz"
POLICY = "stage-anchored-level-sides-v3"
SALT = "peer-batch-size-matched-control-v1"
COHORTS = ("existing-corpus", "new-seeds-20261901-20261940")


def digest(value):
    """Hash portable canonical JSON; no local paths or Python object IDs."""
    data = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    return sha256(data).hexdigest()


def file_sha(path):
    """Bind the exact evidence bytes used for this selection."""
    return sha256(path.read_bytes()).hexdigest()


def history_names(row):
    """A geometry can have several aliases; preserve all history membership."""
    return {alias["history"] for alias in row["aliases"]
            if alias.get("kind") == "history_prefix"}


def build_selection(source):
    """Apply the fixed selection rule without inspecting candidate outcomes."""
    with gzip.open(source, "rt", encoding="utf-8") as stream:
        report = json.load(stream)
    if report["policy"] != POLICY or not report["full_corpus_run"]:
        raise ValueError("expected the complete frozen stage-anchored v3 report")
    rows = report["drawings"]
    indexed = {row["key"]: row for row in rows}
    if len(rows) != len(indexed) or len(rows) != 7069:
        raise ValueError("frozen distinct drawing inventory changed")
    if report["source_sha256"] != report["source_sha256_end"]:
        raise ValueError("source report records source drift")
    failure_keys = {key for key, row in indexed.items()
                    if row["runs"][POLICY]["status"] != "solved"}
    prior_keys = set(report["diagnostic_keys"])
    if len(failure_keys) != 4 or len(prior_keys) != 7:
        raise ValueError("expected four current failures and seven prior cases")
    if failure_keys != set(report["failure_keys"]) or not prior_keys <= indexed.keys():
        raise ValueError("failure or diagnostic identity mismatch")
    failed_histories = {name for key in failure_keys
                        for name in history_names(indexed[key])}
    histories = [row for row in report["histories"]
                 if row["key"] in failed_histories]
    if len(histories) != 1 or len(histories[0]["prefix_keys"]) != 25:
        raise ValueError("expected the full 25-prefix failed history")
    history_keys = set(histories[0]["prefix_keys"])
    if not failure_keys <= history_keys:
        raise ValueError("failed history omitted a known failed geometry")

    roles = defaultdict(set)
    for key in failure_keys:
        roles[key].add("current-v3-failure")
    for key in prior_keys:
        roles[key].add("prior-seven-diagnostic")
    for key in history_keys:
        roles[key].add("complete-failed-history-prefix")

    # Keep successful controls independent of the failed history and of every
    # earlier explicit diagnostic's history. Distinct control histories are
    # enforced across all eight pairs, not just within one side-count pair.
    used_histories = failed_histories | {
        name for key in prior_keys for name in history_names(indexed[key])}
    reserved_histories = sorted(used_histories)
    controls = []
    for failure_key in sorted(failure_keys,
                              key=lambda key: (indexed[key]["face_count"], key)):
        failure = indexed[failure_key]
        for cohort in COHORTS:
            eligible = [row for row in rows
                        if row["key"] not in roles
                        and row["face_count"] == failure["face_count"]
                        and row["runs"][POLICY]["status"] == "solved"
                        and cohort in row["cohorts"]
                        and history_names(row)
                        and not history_names(row) & used_histories]
            if not eligible:
                raise ValueError("no eligible size-matched distinct-history control")

            def rank(row):
                """Use identities alone, never old trace, colors or solver time."""
                return digest([SALT, failure_key, cohort, row["key"]]), row["key"]

            chosen = min(eligible, key=rank)
            roles[chosen["key"]].add("size-matched-success-control")
            chosen_histories = history_names(chosen)
            used_histories.update(chosen_histories)
            controls.append({"failure_key": failure_key,
                             "control_key": chosen["key"],
                             "face_count": chosen["face_count"],
                             "cohort": cohort,
                             "control_histories": sorted(chosen_histories),
                             "eligible_count_before_selection": len(eligible),
                             "rank_sha256": rank(chosen)[0]})

    # No run dictionaries are copied into experimental geometry. A separate
    # reference_status label is for comparison only, never solver input.
    drawings = []
    for key in sorted(roles):
        row = indexed[key]
        drawings.append({field: row[field] for field in (
            "key", "document", "aliases", "cohorts", "geometry_sha256",
            "face_count", "real_bridge_count", "virtual_connector_count")})
        drawings[-1].update(roles=sorted(roles[key]),
                            reference_status=row["runs"][POLICY]["status"])
    content = {"selected_keys": [row["key"] for row in drawings],
               "roles": {key: sorted(value) for key, value in sorted(roles.items())},
               "controls": controls,
               "failed_histories": histories}
    theory_files = (
        "docs/STAGED_LEVEL_CONFLICTS-2026-09-19.md",
        "outputs/staged-levels-failure-diagnosis-2026-09-19.json",
    )
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "Already-seen diagnostic tuning and regression selection",
        "unseen_holdout": False,
        "production_solver_executed": False,
        "old_colors_read": False,
        "reference_policy": POLICY,
        "source_evidence": {"filename": source.name, "sha256": file_sha(source)},
        "selection_script_sha256": file_sha(Path(__file__)),
        "preserved_theory_evidence": {name: file_sha(ROOT / name) for name in theory_files},
        "selection_rule": {
            "core": "All four v3 failures, all seven prior diagnostics, all 25 failed-history prefixes",
            "control": "For each failure, same side count including outside; one solved control per cohort",
            "tie_break": "Minimum SHA256 of canonical JSON [salt, failure key, cohort, control key]",
            "salt": SALT,
            "excluded_histories_initially": reserved_histories,
            "exclude_repeated_control_histories": True,
            "inspect_colors_or_trajectories": False,
        },
        "counts": {
            "distinct_drawings": len(drawings),
            "current_failures": len(failure_keys),
            "prior_diagnostics": len(prior_keys),
            "failed_history_prefix_references": sum(len(row["prefix_keys"]) for row in histories),
            "successful_controls": len(controls),
            "reference_statuses": dict(Counter(row["reference_status"] for row in drawings)),
        },
        "selection_sha256": digest(content),
        **content,
        "drawings": drawings,
        "limits": [
            "All inputs have already been inspected; no unseen validation claim is justified.",
            "Controls are chosen using old solved status and geometry size, not candidate outcomes.",
            "Passing this set does not replace all 7069 drawings and 7678 historical-prefix references.",
            "Stored old status labels are audit metadata, not allowed inputs to the new solver.",
        ],
    }


def main():
    """Write new evidence exclusively so reruns cannot replace prior artifacts."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("choose a NEW output path")
    result = build_selection(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"output": args.output.name,
                      "counts": result["counts"],
                      "selection_sha256": result["selection_sha256"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()

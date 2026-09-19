"""Check publication-index safety and byte-identical scientific evidence.

This standard-library publication check is NOT a mathematical corpus audit.
It reads Git's index, checks staged evidence against local raw bytes, and binds
the frozen v4 report's declared source hashes to those same staged files. It
does not stage, commit, push, normalize, or rewrite any research artifact.
"""

from argparse import ArgumentParser
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
REPORT_NAME = "outputs/peer-batches-full-2026-09-19.json.gz"
FORBIDDEN_DIRECTORIES = {"_local", ".codex", ".agents", ".git", "node_modules", ".venv", "venv", "__pycache__"}
FORBIDDEN_FILES = {"outputs/retained-profiles-2026-09-18.json"}


def blob_oid(data):
    """Compute SHA-1 of Git's blob header and EXACT local bytes, before filters."""
    header = b"blob " + str(len(data)).encode("ascii") + b"\0"
    return hashlib.sha1(header + data).hexdigest()


def safe_relative_name(name):
    """Reject absolute paths and path traversal without reporting their values."""
    if not isinstance(name, str) or not name or "\\" in name:
        return False
    path = PurePosixPath(name)
    return (not path.is_absolute() and ".." not in path.parts and "." not in path.parts
            and not re.match(r"^[A-Za-z]:", name) and str(path) == name)


def forbidden_reason(name):
    """Publication excludes local machinery, private archives and env files."""
    path = PurePosixPath(name.lower())
    if any(part in FORBIDDEN_DIRECTORIES for part in path.parts):
        return "forbidden-directory"
    if path.suffix in {".zip", ".log", ".pyc", ".pyo"}:
        return "forbidden-file-extension"
    if path.name == ".env" or path.name.startswith(".env."):
        return "environment-file"
    if name.lower() in FORBIDDEN_FILES:
        return "excluded-large-original-report"
    return None


def git_bytes(root, *arguments):
    """Capture Git output; never echo a command or machine-specific stderr."""
    result = subprocess.run(["git", "-c", "safe.directory=" + str(root), *arguments],
                            cwd=root, capture_output=True, check=False)
    if result.returncode:
        # Git errors can contain full private paths; callers get a category only.
        raise RuntimeError("git-read-failed")
    return result.stdout


def parse_index(payload):
    """Parse NUL-delimited index records, retaining conflicts for clear rejection."""
    entries = []
    for record in payload.split(b"\0"):
        if not record:
            continue
        metadata, raw_name = record.split(b"\t", 1)
        mode, oid, stage = metadata.decode("ascii").split()
        name = raw_name.decode("utf-8")
        if not safe_relative_name(name) or not re.fullmatch(r"[0-9a-f]{40}", oid):
            raise ValueError("invalid-index-path-or-non-sha1-object-format")
        entries.append({"file": name, "mode": mode, "oid": oid, "stage": int(stage)})
    return entries


def inspect_archive(root):
    """Check every staged evidence file and every source declared by frozen v4."""
    entries = parse_index(git_bytes(root, "ls-files", "-s", "-z"))
    errors, indexed, checked = [], {}, set()
    counts = {"indexed_entries": len(entries), "staged_evidence_files": 0,
              "raw_evidence_bytes_checked": 0, "index_blob_comparisons": 0,
              "frozen_source_files": 0, "source_sha256_comparisons": 0}
    for entry in entries:
        name = entry["file"]
        reason = forbidden_reason(name)
        if reason:
            errors.append({"file": name, "category": reason})
        if entry["stage"] != 0:
            errors.append({"file": name, "category": "unmerged-index-entry"})
            continue
        if name in indexed:
            errors.append({"file": name, "category": "duplicate-index-entry"})
        indexed[name] = entry

    def local_bytes(name):
        """Read one in-project regular file, refusing symlink escape or absence."""
        path = root / name
        try:
            path.resolve().relative_to(root)
        except ValueError:
            errors.append({"file": name, "category": "working-file-outside-project"})
            return None
        if not path.is_file() or path.is_symlink():
            errors.append({"file": name, "category": "missing-or-nonregular-working-file"})
            return None
        return path.read_bytes()

    def compare_index(name, data):
        """A raw mismatch also catches accidental Git EOL/filter transformation."""
        if name not in indexed:
            errors.append({"file": name, "category": "required-file-not-in-index"})
            return
        entry = indexed[name]
        if entry["mode"] not in {"100644", "100755"}:
            errors.append({"file": name, "category": "nonregular-index-mode"})
        if name not in checked:
            counts["index_blob_comparisons"] += 1
            checked.add(name)
            if blob_oid(data) != entry["oid"]:
                errors.append({"file": name, "category": "index-versus-raw-working-bytes-mismatch"})

    for name in sorted(indexed):
        if not name.startswith(("outputs/", "docs/figures/")):
            continue
        counts["staged_evidence_files"] += 1
        data = local_bytes(name)
        if data is not None:
            counts["raw_evidence_bytes_checked"] += len(data)
            compare_index(name, data)

    frozen = local_bytes(REPORT_NAME)
    source_report = {"file": REPORT_NAME}
    if frozen is not None:
        compare_index(REPORT_NAME, frozen)
        source_report["sha256"] = hashlib.sha256(frozen).hexdigest()
        try:
            payload = json.loads(gzip.decompress(frozen))
            if not isinstance(payload, dict):
                raise ValueError("invalid-frozen-report-contract")
            hashes = payload["source_sha256"]
            valid = (payload.get("policy") == "peer-batch-ready-sides-v4"
                     and payload.get("full_corpus_run") is True
                     and payload.get("smoke_limit") is None
                     and isinstance(hashes, dict) and bool(hashes)
                     and hashes == payload.get("source_sha256_end"))
            if not valid:
                raise ValueError("invalid-frozen-report-contract")
        except (ValueError, KeyError, TypeError, OSError):
            errors.append({"file": REPORT_NAME, "category": "invalid-frozen-report-contract"})
            hashes = {}
        counts["frozen_source_files"] = len(hashes)
        for name, expected in sorted(hashes.items()):
            if not safe_relative_name(name) or not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
                errors.append({"file": REPORT_NAME, "field": "source_sha256", "category": "invalid-source-hash-entry"})
                continue
            data = local_bytes(name)
            if data is None:
                continue
            counts["source_sha256_comparisons"] += 1
            if hashlib.sha256(data).hexdigest() != expected:
                errors.append({"file": name, "category": "frozen-source-sha256-mismatch"})
            compare_index(name, data)
    head = git_bytes(root, "rev-parse", "--verify", "HEAD").decode("ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ValueError("invalid-head-commit")
    return {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "kind": "publication-index-and-raw-byte-check", "mathematical_full_audit": False,
            "read_only_repository_check": True, "passed": not errors, "head_commit": head,
            "counts": counts, "frozen_report": source_report, "errors": errors,
            "limits": ["Checks indexed publication paths, raw evidence bytes and the frozen report's source hashes.",
                       "Does not rerun mathematics, scan secrets, stage files, create commits or publish anything.",
                       "Untracked evidence is not implicitly included; the frozen report and all declared sources must be indexed."]}


def main():
    """Write a new relative-path report even on validation failure; exit nonzero."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="NEW report path inside this repository")
    args = parser.parse_args()
    output = args.output.resolve()
    try:
        output.relative_to(ROOT)
        if output.exists():
            raise FileExistsError("output-exists")
        report = inspect_archive(ROOT)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(json.dumps({"passed": report["passed"], **report["counts"], "error_count": len(report["errors"])},
                         ensure_ascii=False), flush=True)
        return 0 if report["passed"] else 1
    except Exception as error:
        # Do not print str(error): filesystem/Git exceptions may reveal usernames.
        # This also covers malformed gzip/index input without a path-bearing traceback.
        print(json.dumps({"passed": False, "category": type(error).__name__,
                          "message": "Publication check could not complete; no private paths are printed."}),
              flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

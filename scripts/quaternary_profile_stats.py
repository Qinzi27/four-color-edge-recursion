"""Export private-path-free cProfile records with auditable counter semantics.

Function records in ``pstats.Stats.stats`` are ``(cc, nc, tt, ct, callers)``:
cc is primitive calls, nc is total calls including recursion, tt is exclusive
self time, and ct includes descendants. Crucially, cProfile caller-edge tuples
reverse the first two fields: ``(nc, cc, tt, ct)``. Cumulative times overlap
along call chains and must never be summed as disjoint work categories.
"""

from collections import defaultdict
from copy import deepcopy
from hashlib import sha256
from math import fsum, isfinite
from pathlib import Path, PurePosixPath
import pstats
import re
import sysconfig


VERSION = "quaternary-cprofile-records-v1"
IDENTITY_FIELDS = ("file", "line", "function")
COUNTER_FIELDS = ("primitive_calls", "total_calls", "self_seconds", "cumulative_seconds")
EDGE_FIELDS = frozenset(IDENTITY_FIELDS + COUNTER_FIELDS)
ROW_FIELDS = EDGE_FIELDS | {"callers"}
ADDRESS = re.compile(r"0x[0-9a-fA-F]+")
REDACTED_FILE = re.compile(r"<external>/[0-9a-f]{20}\Z")


def _require(condition, message):
    """Fail closed even when Python assertions are disabled."""
    if not condition:
        raise ValueError(message)


def _token(value):
    """Give a stable opaque identity without storing private source text."""
    return sha256(value.encode("utf-8", errors="surrogatepass")).hexdigest()[:20]


def _has_control(value):
    """Reject line breaks and nonprinting separators in published identities."""
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _function_name(value):
    """Retain ordinary names, but redact path-like and address-bearing reprs."""
    _require(isinstance(value, str) and bool(value), "function must be a nonempty string")
    if "/" in value or "\\" in value or _has_control(value) or re.search(r"[A-Za-z]:", value):
        return "<redacted-function-" + _token(value) + ">"
    if ADDRESS.search(value):
        # The suffix prevents distinct native objects from collapsing after
        # their addresses are removed. The literal address is never exported.
        return ADDRESS.sub("<address>", value) + " [id-" + _token(value) + "]"
    return value


def _relative(path, root):
    """Return a normalized descendant path, or None for a different root."""
    try:
        value = path.relative_to(root).as_posix()
    except ValueError:
        return None
    return value if value != "." else None


def _file_name(value, root, standard_roots, package_roots):
    """Map code locations into repository, stdlib, generated, or opaque IDs."""
    _require(isinstance(value, str) and bool(value), "file must be a nonempty string")
    if value == "~":
        return "<builtins>"
    if value.startswith("<") and value.endswith(">"):
        label = value[1:-1]
        if re.fullmatch(r"[A-Za-z0-9_. -]+", label):
            return "<generated>/" + label
        return "<generated>/id-" + _token(value)
    path = Path(value)
    path = path.resolve() if path.is_absolute() else (root / path).resolve()
    relative = _relative(path, root)
    if relative is not None and not _has_control(relative) and ":" not in relative:
        return relative
    # Third-party site-packages can be physically below the stdlib directory;
    # do not label their implementation cost as standard-library cost.
    if not any(_relative(path, package) is not None for package in package_roots):
        for standard in standard_roots:
            relative = _relative(path, standard)
            if relative is not None and not _has_control(relative) and ":" not in relative:
                return "<stdlib>/" + relative
    return "<external>/" + _token(value)


def _identity(row):
    """Use the complete location, retaining separate same-named comprehensions."""
    return tuple(row[field] for field in IDENTITY_FIELDS)


def profile_rows(profiler, root):
    """Export all cProfile functions and caller edges in deterministic order.

    ``root`` is the repository root used to strip local machine paths. Unknown
    external locations are opaque IDs. No profiling, production execution,
    file I/O, or timing comparison is performed by this conversion function.
    """
    root = Path(root).resolve()
    configured = sysconfig.get_paths()
    standard_roots = sorted({Path(configured[key]).resolve() for key in ("stdlib", "platstdlib")
                             if configured.get(key)}, key=lambda p: (-len(str(p)), str(p)))
    package_roots = {Path(configured[key]).resolve() for key in ("purelib", "platlib")
                     if configured.get(key)} - set(standard_roots)
    stats = pstats.Stats(profiler).stats
    identities = {}
    for key in stats:
        file, line, function = key
        identities[key] = {"file": _file_name(file, root, standard_roots, package_roots),
                           "line": line, "function": _function_name(function)}
    rows = []
    for key, (primitive, total, self_time, cumulative, callers) in stats.items():
        row = {**identities[key], "primitive_calls": primitive, "total_calls": total,
               "self_seconds": self_time, "cumulative_seconds": cumulative, "callers": []}
        for caller, edge in callers.items():
            _require(caller in identities, "caller references an absent profiled function")
            _require(isinstance(edge, tuple) and len(edge) == 4,
                     "cProfile four-counter caller tuples are required")
            # cProfile stores caller edges as nc, cc, tt, ct, unlike its
            # function totals. A recursive synthetic test guards this order.
            edge_total, edge_primitive, edge_self, edge_cumulative = edge
            row["callers"].append({**identities[caller], "primitive_calls": edge_primitive,
                                   "total_calls": edge_total, "self_seconds": edge_self,
                                   "cumulative_seconds": edge_cumulative})
        row["callers"].sort(key=_identity)
        rows.append(row)
    rows.sort(key=_identity)
    validate_rows(rows)
    return rows


def _valid_file(value):
    """Recognize only canonical public file identities, never absolute paths."""
    if not isinstance(value, str) or not value or _has_control(value) or "\\" in value or ":" in value:
        return False
    if value == "<builtins>":
        return True
    if value.startswith("<external>/"):
        return REDACTED_FILE.fullmatch(value) is not None
    for prefix in ("<stdlib>/", "<generated>/"):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    else:
        if "<" in value or ">" in value:
            return False
    if not value or "<" in value or ">" in value:
        return False
    parts = value.split("/")
    return not PurePosixPath(value).is_absolute() and all(part not in ("", ".", "..") for part in parts)


def _validate_record(record, expected_fields):
    """Validate one function or edge without silently coercing literal types."""
    _require(isinstance(record, dict) and set(record) == expected_fields, "profile record schema differs")
    _require(_valid_file(record["file"]), "profile file identity is unsafe or noncanonical")
    _require(type(record["line"]) is int and record["line"] >= 0, "line must be a nonnegative integer")
    function = record["function"]
    _require(isinstance(function, str) and bool(function) and not _has_control(function)
             and "/" not in function and "\\" not in function
             and not re.search(r"[A-Za-z]:", function) and not ADDRESS.search(function),
             "function identity contains private or noncanonical text")
    for field in ("primitive_calls", "total_calls"):
        _require(type(record[field]) is int and record[field] >= 0, field + " must be a nonnegative integer")
    _require(record["primitive_calls"] <= record["total_calls"], "primitive calls exceed total calls")
    for field in ("self_seconds", "cumulative_seconds"):
        value = record[field]
        try:
            finite = type(value) in (int, float) and isfinite(value)
        except OverflowError:
            finite = False
        _require(finite and value >= 0,
                 field + " must be finite and nonnegative")
    tolerance = max(1e-12, 1e-9 * max(record["self_seconds"], record["cumulative_seconds"]))
    _require(record["self_seconds"] <= record["cumulative_seconds"] + tolerance,
             "self time exceeds cumulative time")


def validate_rows(rows):
    """Fail closed on malformed, reordered, duplicate, or unbound saved rows."""
    _require(isinstance(rows, list), "profile rows must be an array")
    keys = []
    edge_count = 0
    for row in rows:
        _validate_record(row, ROW_FIELDS)
        keys.append(_identity(row))
        _require(isinstance(row["callers"], list), "callers must be an array")
        callers = []
        for edge in row["callers"]:
            _validate_record(edge, EDGE_FIELDS)
            callers.append(_identity(edge))
        _require(len(set(callers)) == len(callers), "duplicate caller identity")
        _require(callers == sorted(callers), "caller identities are not sorted")
        edge_count += len(callers)
    _require(len(set(keys)) == len(keys), "duplicate function identity")
    _require(keys == sorted(keys), "function identities are not sorted")
    known = set(keys)
    for row in rows:
        _require(all(_identity(edge) in known for edge in row["callers"]), "caller reference is absent")
    return {"passed": True, "function_count": len(rows), "caller_edge_count": edge_count}


def summarize_rows(rows):
    """Aggregate disjoint self time; retain cumulative times only as rankings.

    Total calls count Python/native function invocations, including recursion;
    they are not algorithm decisions or independent graph cases. The complete
    rows remain the authoritative caller graph. Top rankings retain each row's
    caller edges so a large cumulative entry can be traced to its children.
    """
    checked = validate_rows(rows)
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["file"]].append(row)
    modules = [{"file": file, "function_count": len(items),
                "primitive_calls": sum(row["primitive_calls"] for row in items),
                "total_calls": sum(row["total_calls"] for row in items),
                "self_seconds": fsum(row["self_seconds"] for row in items)}
               for file, items in grouped.items()]
    modules.sort(key=lambda row: (-row["self_seconds"], row["file"]))
    return {"version": VERSION, "function_count": checked["function_count"],
            "caller_edge_count": checked["caller_edge_count"],
            "total_self_seconds": fsum(row["self_seconds"] for row in rows),
            "total_calls": sum(row["total_calls"] for row in rows),
            "primitive_calls": sum(row["primitive_calls"] for row in rows),
            "by_module": modules,
            "top_self": deepcopy(sorted(rows, key=lambda row: (-row["self_seconds"], _identity(row)))[:20]),
            "top_cumulative": deepcopy(sorted(rows, key=lambda row: (-row["cumulative_seconds"], _identity(row)))[:20]),
            "scope": "Self time is additive across disjoint function records. Cumulative time includes "
                     "descendants and overlaps along caller chains; do not sum cumulative rankings. "
                     "Profiler overhead is included, so these are diagnostic rather than unprofiled speed measurements."}

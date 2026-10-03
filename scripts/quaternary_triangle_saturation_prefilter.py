"""Skip impossible triangle searches while retaining the frozen evidence format.

For a fixed target class and excluded color q, a useful certificate requires
three physically adjacent EQ classes whose domains all exclude q. Fewer than
three such neighbors is a necessary-condition failure, so no old triple can
succeed. This optimization only avoids that enumeration; every surviving
search follows the old order, witnesses, stopping rule, and certificate format.
"""

import itertools
from math import comb

from scripts.quaternary_logical_neq_contacts import _validate_logical
from scripts.quaternary_triangle_saturation import (
    STATISTIC_KEYS, VERSION, _classes, _digest,
)


IMPLEMENTATION_VERSION = "quaternary-triangle-saturation-prefilter-v1"
WORK_STATISTIC_KEYS = (
    "eligible_palette_checks", "neighbor_membership_tests",
    "skipped_palette_checks", "triangles_skipped", "triangles_enumerated",
)


def find_triangle_saturations_prefilter(document, domains, equal_names, *, work_log=None):
    """Return exactly the old detector's evidence, plus optional work telemetry.

    ``statistics.triangles_examined`` deliberately counts the old equivalent
    work, including triples skipped by this implementation. Actual enumeration
    is exposed separately in the append-only ``work_log`` list. Its neighbor
    membership counter measures only the new prefilter, not tests inside the
    surviving old triple loop. With ``work_log=None``, the same prefilter runs
    without allocating or updating the optional work counters. No cross-call
    topology or result cache is used.

    Neither q's presence in the target domain nor three-element neighbor
    domains is required: those would incorrectly suppress empty-domain and
    conditional-conflict cases accepted by the frozen rule.
    """
    if work_log is not None and not isinstance(work_log, list):
        raise ValueError("work_log must be a list or None")
    sides, _ = _validate_logical(document)
    classes = _classes(sides, domains, equal_names)
    index = {side: i for i, side in enumerate(sides)}
    owner = {i: group for group, members in enumerate(classes) for i in members}
    witnesses = {}
    for line in document["lines"]:
        if line["kind"] != "separator":
            continue
        i, j = index[line["left"]], index[line["right"]]
        a, b = owner[i], owner[j]
        if a == b:
            raise ValueError("a physical separator cannot lie inside an equality class")
        for first, second, left, right in ((a, b, i, j), (b, a, j, i)):
            key, pair = (first, second), (left, right)
            if key not in witnesses or pair < witnesses[key]:
                witnesses[key] = pair
    adjacency = [{other for other in range(len(classes)) if (target, other) in witnesses}
                 for target in range(len(classes))]
    statistics = {key: 0 for key in STATISTIC_KEYS}
    work = {key: 0 for key in WORK_STATISTIC_KEYS} if work_log is not None else None
    certificates = []
    for target, group in enumerate(classes):
        statistics["classes_examined"] += 1
        certificate = None
        # The target's real quotient neighbors do not change between palettes.
        neighbors = sorted(adjacency[target])
        for excluded in (1, 2, 3, 4):
            statistics["palettes_examined"] += 1
            removed = [color for color in domains[group[0]] if color != excluded]
            if not removed:
                continue
            if work is not None:
                work["eligible_palette_checks"] += 1
                work["neighbor_membership_tests"] += len(neighbors)
            excluding_neighbors = sum(excluded not in domains[classes[i][0]]
                                      for i in neighbors)
            if excluding_neighbors < 3:
                # Every old triple fails a necessary membership condition.
                # Credit its old count to preserve literal evidence equality.
                skipped = comb(len(neighbors), 3)
                statistics["triangles_examined"] += skipped
                if work is not None:
                    work["triangles_skipped"] += skipped
                    work["skipped_palette_checks"] += 1
                continue
            for a, b, c in itertools.combinations(neighbors, 3):
                statistics["triangles_examined"] += 1
                if work is not None:
                    work["triangles_enumerated"] += 1
                if ((a, b) not in witnesses or (a, c) not in witnesses or (b, c) not in witnesses
                        or any(excluded in domains[classes[i][0]] for i in (a, b, c))):
                    continue
                edge_classes = ((a, b), (a, c), (b, c), (target, a), (target, b), (target, c))
                certificate = {
                    "target": sides[group[0]],
                    "triangle": [sides[classes[i][0]] for i in (a, b, c)],
                    "excluded_color": excluded, "removed_colors": removed,
                    "edges": [[sides[i], sides[j]] for i, j in
                              (witnesses[pair] for pair in edge_classes)],
                }
                break
            if certificate is not None:
                break
        if certificate is not None:
            certificates.append(certificate)
            statistics["certificates_found"] += 1
            statistics["physical_witness_edges"] += 6
    result = {
        "version": VERSION, "raw_document_sha256": _digest(document),
        "domains_sha256": _digest(domains), "equal_names_sha256": _digest(equal_names),
        "classes": [[sides[i] for i in group] for group in classes],
        "certificates": certificates, "statistics": statistics,
    }
    if work_log is not None:
        work_log.append({
            "implementation": IMPLEMENTATION_VERSION,
            "raw_document_sha256": result["raw_document_sha256"],
            "domains_sha256": result["domains_sha256"],
            "equal_names_sha256": result["equal_names_sha256"],
            "statistics": work,
        })
    return result

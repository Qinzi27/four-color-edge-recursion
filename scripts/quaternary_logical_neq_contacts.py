"""Add explicit logical NEQ to the frozen quaternary contact language.

The propagation body follows ``quaternary_contact_model.propagate_contacts``
with one additional binary constraint set, echo and solved-color check. The
old source stays unchanged. Logical pairs never become line records: physical
separators, bridges and point contacts retain their original identity/meaning.
"""

from copy import deepcopy

from fourcolor.relation_names import pairs, relation_closure, transpose
from scripts.quaternary_contact_model import (
    NameState, PALETTE, _require, _validate, relation_code,
)


MODEL = "quaternary-logical-neq-contact-relations-v1"


def _validate_logical(document):
    """Validate old fields independently of strict distinct-side NEQ pairs.

    Reversed and duplicate logical pairs are harmless set constraints and are
    retained literally in the evidence echo, as with supplied logical EQ.
    Self-pairs, unknown sides, malformed pairs and all unknown fields fail.
    This language accepts declared relations; their proof belongs to the raw
    learning envelope and its independent audit, not to contact parsing.
    """
    _require(isinstance(document, dict), "document must be an object")
    base = deepcopy(document)
    different = base.pop("different_names", [])
    sides, parsed = _validate(base)
    known = set(sides)
    _require(isinstance(different, list), "different_names must be an array")
    for pair in different:
        _require(isinstance(pair, list) and len(pair) == 2
                 and all(isinstance(side, str) and side in known for side in pair)
                 and pair[0] != pair[1],
                 "each logical inequality requires two distinct known side references")
    return sides, parsed


def propagate_logical_contacts(document):
    """Propagate real NEQ, declared logical EQ/NEQ and unary restrictions.

    This is the existing binary path-consistency operation with additional
    logical NEQ premises. It neither learns those premises nor performs color
    search. A nonempty fixed point is still not a global extension certificate.
    Supplied singleton words are restrictions, not newly proved conclusions.
    """
    sides, parsed = _validate_logical(document)
    original = deepcopy(document)
    anchors, n = document.get("anchors", {}), len(sides)
    index = {side: i for i, side in enumerate(sides)}
    domains, explicit, initial_states = [], {}, {}
    for side in sides:
        supplied = parsed.get(side, NameState.from_candidates(PALETTE))
        values = set(supplied.candidates)
        sources = []
        if supplied.anchored:
            sources.append({"source": "states", "name": supplied.candidates[0]})
        if side in anchors:
            sources.append({"source": "anchors", "name": anchors[side]})
            values.intersection_update({anchors[side]})
        explicit[side] = sources
        domains.append(sorted(values))
        initial_states[side] = NameState.from_candidates(values, anchored=bool(sources) and bool(values)).as_dict()
    unequal = {frozenset((index[line["left"]], index[line["right"]]))
               for line in document["lines"] if line["kind"] == "separator"}
    logical_unequal = {frozenset((index[first], index[second]))
                       for first, second in document.get("different_names", [])}
    equal = {frozenset((index[first], index[second]))
             for first, second in document.get("equal_names", [])}
    initial = [[sum(1 << (4 * (a - 1) + b - 1)
                    for a in domains[i] for b in domains[j]
                    if (i != j or a == b)
                    and (frozenset((i, j)) not in unequal or a != b)
                    and (frozenset((i, j)) not in logical_unequal or a != b)
                    and (frozenset((i, j)) not in equal or a == b))
                for j in range(n)] for i in range(n)]
    closure = relation_closure(initial)
    matrix = closure["relations"]
    final_domains = [[name for name in PALETTE if matrix[i][i] & (1 << (5 * (name - 1)))]
                     for i in range(n)]
    states = {side: NameState.from_candidates(final_domains[i],
              anchored=bool(explicit[side]) and bool(final_domains[i])).as_dict()
              for i, side in enumerate(sides)}
    status = ("conflict" if closure["conflict"] else "solved"
              if all(len(values) == 1 for values in final_domains) else "underdetermined")
    colors = None
    if status == "solved":
        # Recheck literal colors against every original type of premise, with
        # logical NEQ checked separately rather than inventing a physical line.
        colors = {side: final_domains[i][0] for i, side in enumerate(sides)}
        _require(all(colors[side] in domains[i] for i, side in enumerate(sides)), "invalid solved domain")
        _require(all(colors[side] == item["name"] for side in sides for item in explicit[side]),
                 "invalid solved anchor")
        _require(all(colors[line["left"]] != colors[line["right"]]
                     for line in document["lines"] if line["kind"] == "separator"),
                 "invalid solved separator")
        _require(all(colors[a] == colors[b] for a, b in document.get("equal_names", [])),
                 "invalid solved logical equality")
        _require(all(colors[a] != colors[b] for a, b in document.get("different_names", [])),
                 "invalid solved logical inequality")
    lines = []
    for line in document["lines"]:
        mask = matrix[index[line["left"]]][index[line["right"]]]
        reverse = transpose(mask)
        lines.append({**deepcopy(line), "allowed_pairs": pairs(mask), "relation_mask": mask,
                      "relation_code": relation_code(mask),
                      "reverse": {"left": line["right"], "right": line["left"],
                                  "allowed_pairs": pairs(reverse), "relation_mask": reverse,
                                  "relation_code": relation_code(reverse)}})
    return {"schema_version": 1, "model": MODEL, "status": status,
            "original_input": original, "side_order": sides, "initial_domains": domains,
            "initial_states": initial_states, "explicit_anchor_sources": explicit,
            "name_states": states, "domains": final_domains, "colors": colors,
            "initial_relations": initial, "relations": matrix, "trace": closure["trace"],
            "revisions": closure["revisions"], "lines": lines,
            "point_contacts": deepcopy(document.get("point_contacts", [])),
            "equal_names": deepcopy(document.get("equal_names", [])),
            "different_names": deepcopy(document.get("different_names", [])),
            "choices": 0, "backtracks": 0, "representatives_are_assignments": False,
            "scope": "Declared real contacts and logical EQ/NEQ only; no greedy choice, DFS, or recoloring. "
                     "Logical inequalities are distinct from physical edges. Singletons are checked "
                     "against all original constraints before solved. Nonempty binary relations "
                     "do not certify global extendibility."}

"""Four-name contact constraints with quaternary state codes and no choices.

The digits d1..d4 refer to names 1..4, from left to right: 0 is excluded,
1 remains a candidate, 2 is an unanchored singleton, and 3 is an explicit
anchor. A minimum representative is display information only. In particular,
0111 displays 2 while retaining names 2, 3, and 4.

This is a separate contact-language experiment. It neither edits nor replaces
the existing geometric restart policy. Declared line contacts are assumptions;
the input format does not itself certify a planar geometric realization.
"""

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fourcolor.relation_names import pairs, relation_closure, transpose


PALETTE = (1, 2, 3, 4)


def _quaternary(value, width):
    """Write a fixed-width base-four numeral with the most significant digit first."""
    return "".join(str((value >> (2 * place)) & 3) for place in reversed(range(width)))


@dataclass(frozen=True)
class NameState:
    """One canonical four-digit state, not an integer color assignment.

    Exactly twenty of the 256 integers are canonical: one empty domain, eleven
    domains with at least two candidates, four unanchored singletons and four
    anchored singletons. A singleton encoded using digit 1 is rejected rather
    than silently conflating candidate, derived and explicitly fixed states.
    Code 0000 is a legitimate empty-domain/conflict state, not a parser error.
    """

    code: int

    def __post_init__(self):
        if type(self.code) is not int or not 0 <= self.code <= 255:
            raise ValueError("name-state code must be an integer in 0..255")
        nonzero = [digit for digit in self.digits if digit]
        if nonzero and not ((len(nonzero) == 1 and nonzero[0] in (2, 3))
                            or (len(nonzero) >= 2 and set(nonzero) == {1})):
            raise ValueError("noncanonical state: use 0/1 for multiple candidates or one 2/3")

    @property
    def digits(self):
        """Return d1..d4 in color-name order, distinct from bit-mask order."""
        return tuple((self.code >> shift) & 3 for shift in (6, 4, 2, 0))

    @property
    def candidates(self):
        """Return every remaining name; a representative never removes others."""
        return tuple(name for name, digit in zip(PALETTE, self.digits) if digit)

    @property
    def candidate_mask(self):
        """Four-bit membership mask: bit zero means name 1, independently of d1."""
        return sum(1 << (name - 1) for name in self.candidates)

    @property
    def anchored(self):
        """Whether this encoded singleton is explicitly fixed, not merely derived."""
        return 3 in self.digits

    @property
    def minimum_representative(self):
        """A display value only; an empty domain has no representative."""
        return min(self.candidates) if self.candidates else None

    def to_quaternary(self):
        """Preserve leading zeroes; the code is always exactly four digits."""
        return _quaternary(self.code, 4)

    @classmethod
    def from_quaternary(cls, text):
        """Parse a canonical four-digit code without accepting signs or whitespace."""
        if not isinstance(text, str) or len(text) != 4 or any(c not in "0123" for c in text):
            raise ValueError("a state must contain exactly four base-four digits")
        return cls(int(text, 4))

    @classmethod
    def from_candidates(cls, values, anchored=False):
        """Normalize a name iterable; anchoring requires exactly one candidate.

        Repeated names do not create extra candidates. The boolean flag itself
        is checked strictly because bool is an int subclass in Python.
        """
        if type(anchored) is not bool:
            raise ValueError("anchored must be a boolean")
        try:
            raw = tuple(values)
        except TypeError as exc:
            raise ValueError("candidates must be an iterable of names 1..4") from exc
        if any(type(name) is not int or name not in PALETTE for name in raw):
            raise ValueError("candidate names must be integers 1..4, not booleans")
        names = set(raw)
        if anchored and len(names) != 1:
            raise ValueError("an explicit anchor requires exactly one name")
        marker = 3 if anchored else 2 if len(names) == 1 else 1
        return cls(sum(marker << (2 * (4 - name)) for name in names))

    def as_dict(self):
        """Expose JSON data while retaining the representation/assignment boundary."""
        return {"code": self.code, "quaternary": self.to_quaternary(),
                "candidates": list(self.candidates), "candidate_mask": self.candidate_mask,
                "representative": self.minimum_representative, "anchored": self.anchored}


def from_candidates(values, anchored=False):
    """Convenience constructor with the same semantics as NameState.from_candidates."""
    return NameState.from_candidates(values, anchored=anchored)


def relation_code(mask):
    """Pack a 16-bit pair relation into eight base-four digits.

    Bit 4*(left-1)+(right-1) records the ordered name pair. Unlike NameState's
    four digits, these eight digits are two-bit chunks, not eight color slots.
    """
    if type(mask) is not int or not 0 <= mask <= 65535:
        raise ValueError("a relation mask must be an integer in 0..65535")
    return _quaternary(mask, 8)


def _require(condition, message):
    """Input and final-certificate validation remain active under python -O."""
    if not condition:
        raise ValueError(message)


def _validate(document):
    """Accept only the declared contact language; never infer adjacency from points."""
    _require(isinstance(document, dict), "document must be an object")
    allowed = {"sides", "lines", "anchors", "states", "point_contacts", "equal_names"}
    _require(set(document) <= allowed and {"sides", "lines"} <= set(document),
             "document requires sides/lines and contains an unknown field")
    sides = document["sides"]
    _require(isinstance(sides, list) and bool(sides)
             and all(isinstance(side, str) and bool(side.strip()) for side in sides),
             "sides must be a nonempty list of nonempty string identities")
    _require(len(sides) == len(set(sides)), "duplicate side identity")
    known = set(sides)

    def known_side(side):
        return isinstance(side, str) and side in known

    lines = document["lines"]
    _require(isinstance(lines, list), "lines must be an array")
    identifiers = set()
    for line in lines:
        _require(isinstance(line, dict) and set(line) == {"id", "left", "right", "kind"},
                 "each line requires exactly id, left, right and kind")
        identifier = line["id"]
        _require(isinstance(identifier, str) and bool(identifier.strip())
                 and identifier not in identifiers, "invalid or duplicate line id")
        identifiers.add(identifier)
        _require(known_side(line["left"]) and known_side(line["right"]), "line has unknown side")
        _require(line["kind"] in ("separator", "bridge"), "unsupported line kind")
        same = line["left"] == line["right"]
        _require((line["kind"] == "bridge") == same,
                 "a bridge must have one shared side identity; a separator needs two distinct identities")
    anchors = document.get("anchors", {})
    _require(isinstance(anchors, dict), "anchors must map side identities to names")
    for side, name in anchors.items():
        _require(known_side(side) and type(name) is int and name in PALETTE,
                 "anchor needs a known side and integer name 1..4")
    states = document.get("states", {})
    _require(isinstance(states, dict), "states must map side identities to four-digit strings")
    parsed = {}
    for side, text in states.items():
        _require(known_side(side), "state has unknown side")
        parsed[side] = NameState.from_quaternary(text)
    contacts = document.get("point_contacts", [])
    _require(isinstance(contacts, list), "point_contacts must be an array")
    for contact in contacts:
        _require(isinstance(contact, dict) and set(contact) == {"sides"}
                 and isinstance(contact["sides"], list) and len(contact["sides"]) == 2
                 and all(known_side(side) for side in contact["sides"]),
                 "a point contact requires exactly two known side references")
    equal = document.get("equal_names", [])
    _require(isinstance(equal, list), "equal_names must be an array")
    for pair in equal:
        _require(isinstance(pair, list) and len(pair) == 2
                 and all(known_side(side) for side in pair),
                 "each logical equality requires two known side references")
    return list(sides), parsed


def propagate_contacts(document):
    """Propagate declared unary, separator and logical-equality constraints only.

    The original input, initial domains and complete shrinking relation trace
    support independent literal-color checking. An externally supplied digit 2
    is a provided singleton restriction; it is not a proof produced here.
    EQ does not merge physical side identities. Point contact creates no NEQ.
    Nonempty path-consistent relations can still lack a global coloring.
    """
    sides, parsed = _validate(document)
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
    equal = {frozenset((index[first], index[second]))
             for first, second in document.get("equal_names", [])}
    initial = [[sum(1 << (4 * (a - 1) + b - 1)
                    for a in domains[i] for b in domains[j]
                    if (i != j or a == b)
                    and (frozenset((i, j)) not in unequal or a != b)
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
        # Do not accept the singleton flag alone: recheck the actual input,
        # including external domains and logical equalities, without masks.
        colors = {side: final_domains[i][0] for i, side in enumerate(sides)}
        _require(all(colors[side] in domains[i] for i, side in enumerate(sides)), "invalid solved domain")
        _require(all(colors[side] == item["name"] for side in sides for item in explicit[side]),
                 "invalid solved anchor")
        _require(all(colors[line["left"]] != colors[line["right"]]
                     for line in document["lines"] if line["kind"] == "separator"),
                 "invalid solved separator")
        _require(all(colors[a] == colors[b] for a, b in document.get("equal_names", [])),
                 "invalid solved logical equality")
    lines = []
    for line in document["lines"]:
        mask = matrix[index[line["left"]]][index[line["right"]]]
        reverse = transpose(mask)
        lines.append({**deepcopy(line), "allowed_pairs": pairs(mask), "relation_mask": mask,
                      "relation_code": relation_code(mask),
                      "reverse": {"left": line["right"], "right": line["left"],
                                  "allowed_pairs": pairs(reverse), "relation_mask": reverse,
                                  "relation_code": relation_code(reverse)}})
    return {"schema_version": 1, "model": "quaternary-contact-relations-v1", "status": status,
            "original_input": original, "side_order": sides, "initial_domains": domains,
            "initial_states": initial_states, "explicit_anchor_sources": explicit,
            "name_states": states, "domains": final_domains, "colors": colors,
            "initial_relations": initial, "relations": matrix, "trace": closure["trace"],
            "revisions": closure["revisions"], "lines": lines,
            "point_contacts": deepcopy(document.get("point_contacts", [])),
            "equal_names": deepcopy(document.get("equal_names", [])),
            "choices": 0, "backtracks": 0, "representatives_are_assignments": False,
            "scope": "Declared contact constraints only; no greedy choice, DFS, or recoloring. "
                     "Singletons are checked against the original constraints before solved. "
                     "Underdetermined representatives are not a complete coloring, and nonempty "
                     "binary relations do not certify global extendibility."}

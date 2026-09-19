"""A deterministic renaming rule for the restricted side graph K2 join P_n.

Vertices here are *side-consistency classes*, not geometric vertices or
colors. A plane-map adapter would derive them from endpoint rotations and
side continuation first. An adjacency is an inequality constraint between
two classes; this module does not pretend that it is a particular primal
line segment, nor does it recognize this graph family from drawing data.

The internal palette is exactly {0, 1, 2, 3}; outside stays 0. Two adjacent
anchor classes are adjacent to every class of a nonempty path. Splitting
one path class into two consecutive classes preserves this special family.
The rule exchanges the two non-anchor symbols on the shorter resulting
path segment, ties going left. It never enumerates color assignments.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class SideClass:
    """An immutable identity and its current symbol; these are not synonyms."""

    side_id: str
    symbol: int

    def __post_init__(self) -> None:
        """Reject bools as symbols and blank/non-string class identities."""
        if not isinstance(self.side_id, str) or not self.side_id.strip():
            raise ValueError("side_id must be a nonblank string")
        if type(self.symbol) is not int or not 0 <= self.symbol <= 3:
            raise ValueError("internal symbols must be integers in 0..3")


@dataclass(frozen=True)
class StripChain:
    """A valid naming of the abstract side-adjacency graph K2 join P_n.

``outside`` and ``anchor`` are adjacent and both meet every chain class.
Only successive chain classes are adjacent to each other. The complete
graph family is implicit in this type, rather than supplied as unchecked
adjacency data. Input chain lists are copied into immutable tuples.
"""

    outside: SideClass
    anchor: SideClass
    chain: tuple[SideClass, ...]

    def __post_init__(self) -> None:
        """Validate all family constraints before a rule can be applied."""
        if not isinstance(self.outside, SideClass) or not isinstance(self.anchor, SideClass):
            raise ValueError("outside and anchor must be SideClass records")
        if isinstance(self.chain, (str, bytes)) or not isinstance(self.chain, Sequence):
            raise ValueError("chain must be a nonempty sequence of SideClass records")
        chain = tuple(self.chain)
        if not chain or any(not isinstance(side, SideClass) for side in chain):
            raise ValueError("chain must be a nonempty sequence of SideClass records")
        object.__setattr__(self, "chain", chain)
        sides = (self.outside, self.anchor) + chain
        if len({side.side_id for side in sides}) != len(sides):
            raise ValueError("all side class identities must be distinct")
        if self.outside.symbol != 0:
            raise ValueError("the fixed exterior must have internal symbol 0")
        if self.anchor.symbol == 0:
            raise ValueError("the two adjacent anchors must have different symbols")
        forbidden = {self.outside.symbol, self.anchor.symbol}
        if any(side.symbol in forbidden for side in chain):
            raise ValueError("every chain side must differ from both anchors")
        if any(left.symbol == right.symbol for left, right in zip(chain, chain[1:])):
            raise ValueError("successive chain sides must have different symbols")


@dataclass(frozen=True)
class StripSplit:
    """An atomic split-and-rename result, with immutable explanatory evidence.

``inherited_symbols`` is an uncommitted intermediate sequence: both children
inherit their parent's symbol, so the new separator initially violates its
inequality. Only ``after`` is a valid state. The parent identity is retired;
the two fresh child identities encode no color. ``changed_old_ids`` excludes
the split parent and counts only retained old side classes that were renamed.
"""

    before: StripChain
    after: StripChain
    split_index: int
    parent_id: str
    child_ids: tuple[str, str]
    swapped_segment: str
    swapped_ids: tuple[str, ...]
    changed_old_ids: tuple[str, ...]
    inherited_symbols: tuple[int, ...]


def split_strip_chain(
    state: StripChain,
    split_index: int,
    *,
    child_ids: Sequence[str] | None = None,
) -> StripSplit:
    """Split a one-based path position and rename the shorter whole segment.

Precondition: the geometric operation, if any, has already been certified
to replace path class i by consecutive classes i-left and i-right, keeping
both adjacent to both fixed anchors and introducing no other adjacency.
This function performs the abstract symbolic operation only.

For n old path classes, exactly min(i-1, n-i) *unsplit old* classes change.
This is minimal among every legal result with the same two anchor symbols.
The new children are not included in this change count. Time and returned
storage are O(n). No coloring enumeration, retry, or recursive search is used.
"""
    if not isinstance(state, StripChain):
        raise ValueError("state must be a validated StripChain")
    if type(split_index) is not int or not 1 <= split_index <= len(state.chain):
        raise ValueError("split_index must be a one-based integer chain position")
    parent = state.chain[split_index - 1]
    if child_ids is None:
        children = (parent.side_id + "/L", parent.side_id + "/R")
    else:
        if isinstance(child_ids, (str, bytes)) or not isinstance(child_ids, Sequence):
            raise ValueError("child_ids must contain two fresh nonblank strings")
        children = tuple(child_ids)
    if (len(children) != 2
            or any(not isinstance(value, str) or not value.strip() for value in children)
            or children[0] == children[1]):
        raise ValueError("child_ids must contain two distinct nonblank strings")
    old_ids = {side.side_id for side in (state.outside, state.anchor) + state.chain}
    if any(value in old_ids for value in children):
        raise ValueError("child identities must be fresh, not reused old identities")

    # The intermediate labels expose the sole new conflict. Do not create or
    # publish a StripChain for this invalid intermediate naming.
    index = split_index - 1
    inherited = (
        state.chain[:index]
        + (SideClass(children[0], parent.symbol), SideClass(children[1], parent.symbol))
        + state.chain[index + 1:]
    )
    left_cost, right_cost = index, len(state.chain) - split_index
    use_left = left_cost <= right_cost
    chosen = inherited[:split_index] if use_left else inherited[split_index:]
    chosen_ids = {side.side_id for side in chosen}
    free_symbols = tuple(symbol for symbol in range(4) if symbol not in (0, state.anchor.symbol))
    exchange = {free_symbols[0]: free_symbols[1], free_symbols[1]: free_symbols[0]}

    # Each record denotes a complete side-consistency class: a geometry adapter
    # must update every incident line-side record together, not just one label.
    updated = tuple(
        SideClass(side.side_id, exchange[side.symbol]) if side.side_id in chosen_ids else side
        for side in inherited
    )
    after = StripChain(state.outside, state.anchor, updated)
    changed = state.chain[:index] if use_left else state.chain[index + 1:]
    return StripSplit(
        before=state,
        after=after,
        split_index=split_index,
        parent_id=parent.side_id,
        child_ids=children,
        swapped_segment="left" if use_left else "right",
        swapped_ids=tuple(side.side_id for side in chosen),
        changed_old_ids=tuple(side.side_id for side in changed),
        inherited_symbols=tuple(side.symbol for side in inherited),
    )

"""Independent bounded checks for the restricted non-search strip-chain rule.

The test oracle explicitly constructs *side-adjacency* constraints and the
two possible alternating completions. It does not treat those constraints
as original geometric segments. Enumeration is confined to tests.
"""

from dataclasses import FrozenInstanceError
from itertools import permutations
import unittest

from fourcolor.strip_chain import SideClass, StripChain, split_strip_chain


def make_chain(length, palette=(0, 1, 2, 3)):
    """Build a fixture with identities independent of the internal symbols."""
    return StripChain(
        SideClass("outside", palette[0]),
        SideClass("fixed-neighbor", palette[1]),
        tuple(SideClass(f"side-{index + 1}", palette[2 + index % 2]) for index in range(length)),
    )


def independent_edges(length):
    """Return every edge of K2 join P_n using integer oracle vertex IDs."""
    return (
        [(0, 1)]
        + [(anchor, index + 2) for anchor in (0, 1) for index in range(length)]
        + [(index + 2, index + 3) for index in range(length - 1)]
    )


class StripChainTests(unittest.TestCase):
    """Check safety, determinism, minimality, immutable evidence, and scope."""

    def assert_independently_valid(self, state):
        """Check the actual graph constraints without production validation."""
        symbols = (state.outside.symbol, state.anchor.symbol) + tuple(side.symbol for side in state.chain)
        self.assertEqual(symbols[0], 0)
        self.assertTrue(all(type(symbol) is int and 0 <= symbol < 4 for symbol in symbols))
        for left, right in independent_edges(len(state.chain)):
            self.assertNotEqual(symbols[left], symbols[right])

    def test_all_positions_n_1_to_40_and_all_exterior_preserving_permutations(self):
        count = 0
        for nonouter in permutations((1, 2, 3)):
            palette = (0,) + nonouter
            for length in range(1, 41):
                state = make_chain(length, palette)
                for position in range(1, length + 1):
                    with self.subTest(length=length, position=position, palette=palette):
                        result = split_strip_chain(state, position)
                        self.assert_independently_valid(result.after)
                        self.assertEqual(result, split_strip_chain(state, position))
                        self.assertEqual(result.after.outside, state.outside)
                        self.assertEqual(result.after.anchor, state.anchor)
                        self.assertEqual(len(result.after.chain), length + 1)
                        self.assertEqual(result.parent_id, state.chain[position - 1].side_id)
                        self.assertEqual(result.swapped_segment, "left" if position - 1 <= length - position else "right")
                        self.assertEqual(len(result.changed_old_ids), min(position - 1, length - position))
                        self.assertEqual(len(result.swapped_ids), len(result.changed_old_ids) + 1)

                        # Only the freshly inserted separator conflicts in the
                        # uncommitted inherited sequence, before its atomic repair.
                        expected_inherited = tuple(side.symbol for side in state.chain)
                        expected_inherited = expected_inherited[:position] + expected_inherited[position - 1:]
                        self.assertEqual(result.inherited_symbols, expected_inherited)
                        equal_positions = tuple(index for index in range(length)
                                                if expected_inherited[index] == expected_inherited[index + 1])
                        self.assertEqual(equal_positions, (position - 1,))

                        # Independent completion oracle: with anchors fixed,
                        # all valid length-(n+1) paths are these two alternatives.
                        alternatives = tuple(tuple(palette[2 + (index + phase) % 2]
                                                   for index in range(length + 1)) for phase in (0, 1))
                        actual = tuple(side.symbol for side in result.after.chain)
                        self.assertIn(actual, alternatives)
                        costs = []
                        for alternative in alternatives:
                            costs.append(sum(
                                old.symbol != alternative[index if index < position - 1 else index + 1]
                                for index, old in enumerate(state.chain) if index != position - 1
                            ))
                        self.assertEqual(sorted(costs), sorted((position - 1, length - position)))
                        self.assertEqual(len(result.changed_old_ids), min(costs))

                        after_by_id = {side.side_id: side.symbol for side in result.after.chain}
                        changed = tuple(old.side_id for old in state.chain
                                        if old.side_id != result.parent_id and after_by_id[old.side_id] != old.symbol)
                        self.assertEqual(changed, result.changed_old_ids)
                        self.assertNotIn(result.parent_id, after_by_id)
                        self.assertTrue(set(result.child_ids).isdisjoint({side.side_id for side in state.chain}))
                        count += 1
        self.assertEqual(count, 4920)

    def test_small_explanatory_example_and_tie_goes_left(self):
        state = make_chain(3)
        result = split_strip_chain(state, 2)
        self.assertEqual(tuple(side.symbol for side in state.chain), (2, 3, 2))
        self.assertEqual(result.inherited_symbols, (2, 3, 3, 2))
        self.assertEqual(tuple(side.symbol for side in result.after.chain), (3, 2, 3, 2))
        self.assertEqual(result.changed_old_ids, ("side-1",))
        self.assertEqual(result.swapped_segment, "left")
        single = split_strip_chain(make_chain(1), 1)
        self.assertEqual(single.changed_old_ids, ())
        self.assertEqual(single.swapped_segment, "left")

    def test_repeated_splits_preserve_old_unsplit_identities(self):
        state = make_chain(1)
        for step in range(1, 41):
            position = 1 + (step * 7) % len(state.chain)
            parent_id = state.chain[position - 1].side_id
            result = split_strip_chain(state, position, child_ids=(f"child-{step}-a", f"child-{step}-b"))
            before_ids = {side.side_id for side in state.chain}
            after_ids = {side.side_id for side in result.after.chain}
            self.assertEqual(after_ids, before_ids - {parent_id} | set(result.child_ids))
            self.assert_independently_valid(result.after)
            state = result.after
        self.assertEqual(len(state.chain), 41)

    def test_rejects_invalid_class_identity_and_symbol(self):
        for side_id in (None, 1, True, "", " \n", [], {}):
            with self.subTest(side_id=side_id), self.assertRaises(ValueError):
                SideClass(side_id, 1)
        for symbol in (-1, 4, True, False, 1.0, "1", None, [], {}):
            with self.subTest(symbol=symbol), self.assertRaises(ValueError):
                SideClass("side", symbol)

    def test_rejects_all_18_nonzero_exterior_palette_permutations(self):
        checked = 0
        for palette in permutations(range(4)):
            if palette[0] != 0:
                with self.subTest(palette=palette), self.assertRaises(ValueError):
                    make_chain(2, palette)
                checked += 1
        self.assertEqual(checked, 18)

    def test_rejects_invalid_chains_and_anchor_conditions(self):
        state = make_chain(2)
        for chain in ((), [], None, "ab", b"ab", (side for side in state.chain),
                      (1,), (SideClass("x", 0),), (SideClass("x", 1),),
                      (SideClass("x", 2), SideClass("y", 2)),
                      (SideClass("x", 2), SideClass("x", 3)),
                      (SideClass("outside", 2),), (SideClass("fixed-neighbor", 2),)):
            with self.subTest(chain=chain), self.assertRaises(ValueError):
                StripChain(state.outside, state.anchor, chain)
        for outside, anchor in ((None, state.anchor), (state.outside, None),
                                (SideClass("outside", 1), state.anchor),
                                (state.outside, SideClass("fixed-neighbor", 0)),
                                (state.outside, SideClass("outside", 1))):
            with self.subTest(outside=outside, anchor=anchor), self.assertRaises(ValueError):
                StripChain(outside, anchor, state.chain)

    def test_rejects_invalid_split_requests_and_identity_collisions(self):
        state = make_chain(3)
        for position in (0, 4, -1, True, False, 1.0, "1", None, [], {}):
            with self.subTest(position=position), self.assertRaises(ValueError):
                split_strip_chain(state, position)
        for bad_state in (None, 0, "state", (), {}):
            with self.subTest(state=bad_state), self.assertRaises(ValueError):
                split_strip_chain(bad_state, 1)
        for child_ids in ("ab", b"ab", (), ("a",), ("a", "b", "c"),
                          ("a", "a"), ("", "b"), (1, "b"), (" ", "b"),
                          ("outside", "b"), ("fixed-neighbor", "b"), ("side-1", "b"),
                          (item for item in ("a", "b"))):
            with self.subTest(child_ids=child_ids), self.assertRaises(ValueError):
                split_strip_chain(state, 2, child_ids=child_ids)
        collision = StripChain(state.outside, state.anchor,
                               (SideClass("parent", 2), SideClass("parent/L", 3)))
        with self.assertRaises(ValueError):
            split_strip_chain(collision, 1)

    def test_inputs_are_copied_and_result_records_are_immutable(self):
        chain = [SideClass("a", 2), SideClass("b", 3)]
        state = StripChain(SideClass("outside", 0), SideClass("anchor", 1), chain)
        original = tuple(chain)
        children = ["new-left", "new-right"]
        result = split_strip_chain(state, 1, child_ids=children)
        chain.clear()
        children[0] = "changed-later"
        self.assertEqual(state.chain, original)
        self.assertEqual(result.child_ids, ("new-left", "new-right"))
        self.assertIs(result.before, state)
        self.assertIsInstance(result.after.chain, tuple)
        self.assertIsInstance(result.changed_old_ids, tuple)
        with self.assertRaises(FrozenInstanceError):
            result.after = state
        with self.assertRaises(FrozenInstanceError):
            state.chain = ()
        with self.assertRaises(FrozenInstanceError):
            state.outside.symbol = 1


if __name__ == "__main__":
    unittest.main()

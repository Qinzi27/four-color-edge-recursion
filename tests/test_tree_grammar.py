"""Check semantic boundaries of the literature grammar companion."""

from itertools import product
import unittest

from scripts.inspect_tree_grammar import (
    ALPHABET, MERGE, check_extensions, interval_oracle, parse, parse_words, trees,
)


class TreeGrammarTests(unittest.TestCase):
    """Distinguish local parsing, tree-pair compatibility, and face colors."""

    def test_local_success_is_not_common_word(self):
        """A word accepted by one tree can fail on another bracketing."""
        left, right = ((None, None), None), (None, (None, None))
        self.assertEqual(parse(left, (0, 1, 1)), 0)
        self.assertIsNone(parse(right, (0, 1, 1)))
        self.assertEqual(parse(left, (0, 1, 0)), 1)
        self.assertEqual(parse(right, (0, 1, 0)), 1)
        self.assertEqual(len(parse_words(left) & parse_words(right)), 6)

    def test_nonzero_total_does_not_remove_internal_obstruction(self):
        """The root XOR is nonzero for 011, but the right cherry is illegal."""
        right = (None, (None, None))
        self.assertNotEqual(1 ^ 2 ^ 2, 0)
        self.assertIsNone(interval_oracle(right, (0, 1, 1)))

    def test_rotation_preserves_labels_exactly_when_outer_labels_agree(self):
        """For an initially valid ((A,B),C), rotation needs label(A)=label(C)."""
        left, right = ((None, None), None), (None, (None, None))
        for a, b, c in product(ALPHABET, repeat=3):
            if parse(left, (a, b, c)) is not None:
                self.assertEqual(parse(right, (a, b, c)) is not None, a == c)

    def test_independent_oracle_on_all_small_words(self):
        """Compare a six-production parser with independently calculated cuts."""
        for n in range(1, 5):
            for tree in trees(n):
                for word in product(ALPHABET, repeat=n):
                    self.assertEqual(parse(tree, word), interval_oracle(tree, word))

    def test_paired_extension_operations(self):
        """Check both orientations, three extension rules, and small contexts."""
        self.assertTrue(check_extensions(4)["passed"])

    def test_face_palette_is_not_the_grammar_alphabet(self):
        """Four face display colors cannot be substituted as three symbols."""
        with self.assertRaises(ValueError):
            parse(((None, None), (None, None)), (1, 2, 3, 4))
        self.assertNotIn((0, 0), MERGE)
        self.assertEqual(MERGE[(1, 2)], 0)


if __name__ == "__main__":
    unittest.main()

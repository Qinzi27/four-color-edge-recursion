"""Audit the three-symbol tree grammar discussed by Cooper et al. (2012).

This standalone research companion enumerates small ordered full binary trees.
It is not the project's face-splitting algorithm and is never called by the web
app. Symbols 0, 1, 2 encode NONZERO group elements 01, 10, 11, respectively;
the grammar symbol 0 must not be confused with the group identity 00.
"""

from __future__ import annotations

from argparse import ArgumentParser
from datetime import datetime, timezone
from functools import lru_cache
from itertools import combinations_with_replacement, product
import json
from pathlib import Path
import platform


# A leaf is None; a branch is an ordered pair of child trees.
Tree = tuple["Tree", "Tree"] | None
ALPHABET = (0, 1, 2)
MERGE = {(0, 1): 2, (1, 0): 2, (0, 2): 1,
         (2, 0): 1, (1, 2): 0, (2, 1): 0}
GROUP_CODE = (1, 2, 3)
ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=None)
def trees(leaves: int) -> tuple[Tree, ...]:
    """Generate every ordered full binary tree with the stated leaf count."""
    if type(leaves) is not int or leaves < 1:
        raise ValueError("leaves must be a positive integer")
    if leaves == 1:
        return (None,)
    return tuple((left, right) for n in range(1, leaves)
                 for left in trees(n) for right in trees(leaves - n))


@lru_cache(maxsize=None)
def leaf_count(tree: Tree) -> int:
    """Count leaf POSITIONS, not distinct symbols or face identities."""
    return 1 if tree is None else leaf_count(tree[0]) + leaf_count(tree[1])


def bracket(tree: Tree) -> str:
    """Display tree structure using x for every leaf placeholder."""
    return "x" if tree is None else f"({bracket(tree[0])},{bracket(tree[1])})"


def parse(tree: Tree, word: tuple[int, ...]) -> int | None:
    """Return the forced root symbol, or None for an illegal local merge.

    The explicit six-production table is the primary implementation. Invalid
    input is different from a well-formed word that the tree cannot parse.
    """
    if len(word) != leaf_count(tree) or any(type(x) is not int or x not in ALPHABET for x in word):
        raise ValueError("word must have one symbol from 0,1,2 per leaf")
    symbols = iter(word)

    def visit(node: Tree) -> int | None:
        """Consume the left-to-right leaf sequence even after a failed branch."""
        if node is None:
            return next(symbols)
        left, right = visit(node[0]), visit(node[1])
        return MERGE.get((left, right))

    return visit(tree)


@lru_cache(maxsize=None)
def subtree_intervals(tree: Tree) -> tuple[tuple[int, int], ...]:
    """Record each subtree's half-open leaf interval for a separate oracle."""
    intervals = []

    def visit(node: Tree, first: int) -> int:
        """Find intervals without calculating any grammar labels."""
        last = first + 1 if node is None else visit(node[1], visit(node[0], first))
        intervals.append((first, last))
        return last

    visit(tree, 0)
    return tuple(intervals)


def interval_oracle(tree: Tree, word: tuple[int, ...]) -> int | None:
    """Check every subtree XOR by prefix sums, without the merge recurrence.

    A tree parses a word exactly when every subtree's total is nonzero in
    Z2 x Z2. A nonzero root alone is NOT sufficient.
    """
    prefix = [0]
    for symbol in word:
        prefix.append(prefix[-1] ^ GROUP_CODE[symbol])
    if any(prefix[end] ^ prefix[start] == 0 for start, end in subtree_intervals(tree)):
        return None
    return GROUP_CODE.index(prefix[-1])


@lru_cache(maxsize=None)
def parse_words(tree: Tree) -> frozenset[tuple[int, ...]]:
    """Keep all literal words; align both trees BEFORE quotienting color names."""
    return frozenset(w for w in product(ALPHABET, repeat=leaf_count(tree))
                     if parse(tree, w) is not None)


def canonical(word: tuple[int, ...]) -> tuple[int, ...]:
    """Choose the first-appearance representative under a global S3 action."""
    names = {}
    return tuple(names.setdefault(x, len(names)) for x in word)


def expand_leaf(tree: Tree, index: int) -> Tree:
    """Replace one leaf by a sibling pair (a cherry); leaf order is retained."""
    if not 0 <= index < leaf_count(tree):
        raise ValueError("leaf index out of range")
    if tree is None:
        return (None, None)
    n = leaf_count(tree[0])
    if index < n:
        return (expand_leaf(tree[0], index), tree[1])
    return (tree[0], expand_leaf(tree[1], index - n))


def duplicate_leaf(tree: Tree, index: int) -> Tree:
    """Implement the SHAPE operation in Proposition 11, not label copying.

    A left leaf in (x,S) becomes (x,(x,S)); a right leaf in (S,x) becomes
    ((S,x),x). The two x placeholders will generally receive different labels.
    """
    if tree is None or not 0 <= index < leaf_count(tree):
        raise ValueError("duplication requires a leaf with a parent")
    left, right = tree
    n = leaf_count(left)
    if left is None and index == 0:
        return (None, (None, right))
    if right is None and index == n:
        return ((left, None), None)
    if index < n:
        return (duplicate_leaf(left, index), right)
    return (left, duplicate_leaf(right, index - n))


def triplicate_leaf(tree: Tree, index: int) -> Tree:
    """Insert two same-orientation levels as in Theorem 18 (three leaves)."""
    return duplicate_leaf(duplicate_leaf(tree, index), index)


def check_extensions(max_leaves: int) -> dict:
    """Check Propositions 10/11 completely and Theorem 18's extension map.

    Counts after S3 quotient use n >= 2; the one-leaf case has a different
    stabilizer and does not have the same factor-of-two orbit count.
    """
    cases = 0
    for n in range(2, max_leaves + 1):
        for first, second in product(trees(n), repeat=2):
            old = parse_words(first) & parse_words(second)
            old_classes = {canonical(w) for w in old}
            for i in range(n):
                expanded = expand_leaf(first, i)
                expected = {w[:i] + (a, b) + w[i + 1:] for w in old
                            for (a, b), parent in MERGE.items() if parent == w[i]}
                symmetric = parse_words(expanded) & parse_words(expand_leaf(second, i))
                if symmetric != expected or len({canonical(w) for w in symmetric}) != 2 * len(old_classes):
                    raise AssertionError("synchronized cherry expansion failed")
                duplicated = duplicate_leaf(second, i)
                asymmetric = parse_words(expanded) & parse_words(duplicated)
                selected = set()
                for w in old:
                    candidates = {v for v in expected if v[:i] == w[:i]
                                  and v[i + 2:] == w[i + 1:]
                                  and MERGE[v[i:i + 2]] == w[i]
                                  and interval_oracle(duplicated, v) is not None}
                    if len(candidates) != 1:
                        raise AssertionError("duplication did not force one orientation")
                    selected.update(candidates)
                if asymmetric != selected or len({canonical(w) for w in asymmetric}) != len(old_classes):
                    raise AssertionError("asymmetric duplication failed")
                first_triple = triplicate_leaf(first, i)
                second_triple = triplicate_leaf(second, i)
                for w in old:
                    extended_word = w[:i] + (w[i],) * 3 + w[i + 1:]
                    for old_tree, new_tree in ((first, first_triple), (second, second_triple)):
                        expected_root = parse(old_tree, w)
                        if (parse(new_tree, extended_word) != expected_root
                                or interval_oracle(new_tree, extended_word) != expected_root):
                            raise AssertionError("triplication did not preserve the parse")
                cases += 1
    return {"base_leaves_min": 2, "base_leaves_max": max_leaves,
            "ordered_tree_pair_and_leaf_cases": cases,
            "operations_checked_per_case": 3,
            "triplication_scope": "forward map and root preservation, not all new parse words",
            "passed": True}


def audit(max_leaves: int = 7, extension_max: int = 5) -> dict:
    """Generate bounded evidence and small readable obstruction examples."""
    rows = []
    for n in range(1, max_leaves + 1):
        family = trees(n)
        words = tuple(product(ALPHABET, repeat=n))
        for tree in family:
            for word in words:
                if parse(tree, word) != interval_oracle(tree, word):
                    raise AssertionError("grammar and independent interval oracle disagree")
        pair_count, minimum = 0, None
        for first, second in combinations_with_replacement(family, 2):
            common = parse_words(first) & parse_words(second)
            if not common:
                raise AssertionError("tree pair has no common word within tested bounds")
            # Total XOR forces equal root labels whenever BOTH parses succeed.
            if any(parse(first, w) != parse(second, w) for w in common):
                raise AssertionError("common word root labels disagree")
            pair_count += 1
            minimum = len(common) if minimum is None else min(minimum, len(common))
        rows.append({"leaves": n, "ordered_tree_shapes": len(family),
                     "tree_word_checks": len(family) * len(words),
                     "unordered_pairs_including_self": pair_count,
                     "minimum_literal_common_words": minimum})
        print(f"PASS n={n}: trees={len(family)}, tree-word checks={len(family)*len(words)}, pairs={pair_count}")

    left, right = ((None, None), None), (None, (None, None))
    balanced, comb = ((None, None), (None, None)), (((None, None), None), None)
    examples = []
    for first, second, word in [(left, right, (0, 1, 1)), (left, right, (0, 1, 0)),
                                 (balanced, comb, (0, 1, 2, 0)), (balanced, comb, (0, 1, 0, 2))]:
        examples.append({"first": bracket(first), "second": bracket(second),
                         "word": list(word), "first_root": parse(first, word),
                         "second_root": parse(second, word)})
    return {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "python_version": platform.python_version(), "random_seed": None,
            "sampling": "exhaustive within stated bounds; no randomness",
            "scope": "Ordered binary tree grammar, not arbitrary face-split histories; finite checks are not a new four-color proof.",
            "source": {"doi": "10.1016/j.aam.2011.11.002", "arxiv": "1006.1324v2",
                       "sections": ["1", "2", "3", "4 Propositions 10-11", "6 Theorem 18"]},
            "symbol_to_nonzero_group_code": {"0": "01", "1": "10", "2": "11"},
            "oracle": "prefix XOR on every subtree leaf interval; no grammar-table recursion",
            "tree_families": rows, "extensions": check_extensions(extension_max),
            "examples": examples, "passed": True}


def main() -> None:
    """Write a new report without silently replacing any previous result."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--max-leaves", type=int, choices=range(2, 8), default=7)
    parser.add_argument("--extension-max", type=int, choices=range(2, 6), default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = args.output or ROOT / "outputs" / f"tree-grammar-rules-{stamp}.json"
    if output.exists():
        parser.error("output already exists; choose a new filename")
    report = audit(args.max_leaves, args.extension_max)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"PASS extension cases={report['extensions']['ordered_tree_pair_and_leaf_cases']}")
    print(f"Saved {output.name}")


if __name__ == "__main__":
    main()

"""Check input coverage, preserved provenance and honest history deduplication."""

import json
import unittest
from unittest.mock import patch

from scripts.current_corpus import build_corpus, stroke_set_key
from scripts.validate_current_corpus import (
    POLICIES, audit_static_inputs, digest, run_history,
)


class CurrentCorpusTests(unittest.TestCase):
    """No coloring method is called when collecting these fixtures."""

    @classmethod
    def setUpClass(cls):
        """Generate existing geometry once; never write an output report."""
        cls.corpus = build_corpus()
        cls.histories = cls.corpus["histories"]
        cls.by_key = {row["key"]: row for row in cls.histories}

    def test_inventory_is_json_portable_and_has_no_private_paths(self):
        """The corpus is a sharable source record, not a local machine log."""
        encoded = json.dumps(self.corpus, ensure_ascii=False)
        self.assertEqual(json.loads(encoded), self.corpus)
        self.assertNotIn("C:/Users", encoded)
        self.assertNotIn("C:\\\\Users", encoded)

    def test_guillotine_has_all_full_histories_not_old_blocked_prefixes(self):
        """All 180 generated rectangles retain every one of their 24 cuts."""
        rows = [row for row in self.histories if row["family"] == "guillotine"]
        self.assertEqual(len(rows), 180)
        self.assertEqual({row["seed"] for row in rows},
                         set(range(20260908, 20261068)) | set(range(20261201, 20261221)))
        self.assertEqual({len(row["paths"]) for row in rows}, {24})

    def test_strip_orders_are_histories_not_forty_distinct_final_drawings(self):
        """The same final strip drawing has forty stored ordered histories."""
        rows = [row for row in self.histories if row["family"] == "two-anchor-strip"]
        self.assertEqual(len(rows), 40)
        self.assertEqual(len({row["history_sha256"] for row in rows}), 40)
        self.assertEqual(len({row["final_stroke_set_sha256"] for row in rows}), 1)

    def test_duplicate_ring_seeds_keep_every_origin(self):
        """The generator's repeated start/gap parameters are not fresh samples."""
        rows = [row for row in self.histories if row["family"] == "nested-rings-and-bridges"]
        aliases = [alias for row in rows for alias in row["aliases"]]
        self.assertEqual(len(rows), 16)
        self.assertEqual(len(aliases), 60)
        self.assertEqual({alias["seed"] for alias in aliases},
                         set(range(20261068, 20261108)) | set(range(20261221, 20261241)))
        self.assertEqual(sum(alias["cohort"] == "fresh-seeds" for alias in aliases), 20)

    def test_gallery_nonrectangular_seed_is_not_silently_replaced_by_blank(self):
        """A supplied hexagon start cannot be represented as a RectState."""
        row = self.by_key["construction-hex-precolored"]
        self.assertIsNone(row["initial_state"])
        self.assertTrue(row["initial_document"]["strokes"])
        self.assertTrue(row["initial_names"])
        self.assertEqual(row["scope_hint"], "nonrectangular_precolored_initial_state")
        self.assertEqual(len([row for row in self.histories
                              if row["family"] == "construction-gallery"]), 13)

    def test_teaching_checkpoints_are_linked_to_existing_histories(self):
        """Prefixes and frozen old names are distinct provenance categories."""
        for letter, seed in (("A", 20260923), ("B", 20261027), ("C", 20260960), ("E", 20260927)):
            with self.subTest(case=letter):
                self.assertIn(f"guillotine-{seed}", self.by_key[letter + "_restart"]["prefix_of"])
                self.assertTrue(self.by_key[letter + "_frozen_start"]["initial_state"]["cuts"])

    def test_static_random_lines_are_not_given_invented_incremental_paths(self):
        """The old 30-line-family samples have drawings, not construction claims."""
        rows = [row for row in self.corpus["static_inventory"]
                if row["family"] == "static-random-lines"]
        self.assertEqual(len(rows), 30)
        for row in rows:
            self.assertNotIn("paths", row)
            self.assertEqual(row["classification"], "static_input_without_declared_replay")
            self.assertEqual(row["stroke_set_sha256"], stroke_set_key(row["document"]))

    def test_counts_distinguish_sources_histories_and_static_inputs(self):
        """Exact declared sizes protect against silently dropped families."""
        summary = self.corpus["summary"]
        self.assertEqual(summary["history_aliases"], 367)
        self.assertEqual(summary["unique_declared_histories"], 323)
        self.assertEqual(summary["static_source_records"], 346)
        self.assertEqual(summary["static_distinct_stroke_sets"], 302)
        self.assertEqual(summary["static_without_declared_history"], 43)

    def test_runner_preserves_unsupported_precolored_start_without_certifying_blank(self):
        """None means an unsupported seed, never permission to reset its names."""
        emitted = []
        row = self.by_key["construction-hex-precolored"]
        for policy in POLICIES:
            result = run_history(row, policy, lambda *args: emitted.append(args))
            self.assertEqual(result["status"], "outside_scope")
            self.assertIsNone(result["final_state"])
            self.assertEqual(result["steps"], [])
            self.assertEqual(result["committed_steps"], 0)
        self.assertEqual(emitted, [])

    def test_runner_zero_budget_control_does_not_inherit_wide_policy_budget(self):
        """A separately declared zero-budget case stays zero in every policy."""
        seen, emitted = [], []

        def reject(state, points, **options):
            """Observe arguments without making any coloring decision."""
            seen.append(options)
            return {"state": state, "status": "blocked", "event": {"reason": "test-only"}}

        row = self.by_key["D_zero_budget_control"]
        with patch("scripts.validate_current_corpus.attempt_current_cut", side_effect=reject):
            result = run_history(row, POLICIES[3], lambda *args: emitted.append(args))
        self.assertEqual(seen, [{"max_old_sides": 0, "release": True}])
        self.assertEqual(result["max_old_sides"], 0)
        self.assertEqual(json.loads(json.dumps(result["final_state"])), row["initial_state"])
        self.assertEqual(len(emitted), 1)  # Initial state only; rejected draft is not certified.
        self.assertNotIn("state_sha256", result["steps"][0])

    def test_runner_success_hashes_refer_to_states_not_event_presentations(self):
        """Display compaction may change event fields, but not committed names."""
        emitted = []
        row = self.by_key["E_restart"]
        result = run_history(row, POLICIES[2], lambda key, state: emitted.append((key, state)))
        from fourcolor.inherited_names import state_payload
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["committed_steps"], 8)
        self.assertEqual(len(emitted), 9)
        for number, step in enumerate(result["steps"], 1):
            self.assertEqual(emitted[number][0], "release-b3/E_restart/" + str(number))
            self.assertEqual(step["state_sha256"], digest(state_payload(emitted[number][1])))
        self.assertEqual(digest(result["final_state"]), result["steps"][-1]["state_sha256"])
        self.assertEqual(result["final_state"]["cuts"], tuple(tuple(tuple(p) for p in cut)
                                                           for cut in row["paths"]))

    def test_runner_static_audit_explicitly_makes_no_naming_claim(self):
        """A checked blank-map topology is not counted as a coloring success."""
        rows = [row for row in self.corpus["static_inventory"] if row["key"] == "gallery-blank"]
        checks = audit_static_inputs(rows)
        self.assertEqual(len(checks), 1)
        self.assertTrue(checks[0]["topology_checked"])
        self.assertIs(checks[0]["naming_claim"], False)
        self.assertEqual(checks[0]["faces"], 2)


if __name__ == "__main__":
    unittest.main()

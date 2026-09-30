"""Small controls only; the complete 4096-graph experiment runs after freezing."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from scripts import check_logical_neq_rule_soundness as rule


class LogicalNeqFiniteRuleTests(unittest.TestCase):
    """Verify declarations and saved proof binding using three existing controls."""

    @classmethod
    def setUpClass(cls):
        """The empty, full, and one-deletion graphs are unit calibration only."""
        inventory = rule.rule_inventory()
        cls.records = [inventory[0], inventory[-2], inventory[-1]]
        cls.report = rule._report(cls.records, rule._evaluate(cls.records))

    def check_small(self, report):
        """Limit every unit saved-check to exactly the three named controls."""
        with patch.object(rule, 'rule_inventory', return_value=self.records):
            return rule.check_saved_rule_soundness(report)

    def test_inventory_is_complete_distinct_and_contains_no_initial_colors(self):
        """Every 12-bit edge subset is declared before any learner invocation."""
        with patch.object(rule, 'learn_logical_inequalities', side_effect=AssertionError('learner')):
            inventory = rule.rule_inventory()
        self.assertEqual([item['edge_mask'] for item in inventory], list(range(4096)))
        self.assertEqual(len({rule._digest(item['document']) for item in inventory}), 4096)
        self.assertEqual(len(rule.BASE_EDGES), 12)
        self.assertTrue(all(set(item['document']) == {'sides', 'lines'} for item in inventory))

    def test_full_graph_has_nonvacuous_positive_and_empty_has_negative_witness(self):
        """The full six-vertex control has 24 literal legal assignments."""
        empty, _, full = self.report['per_graph']
        self.assertEqual(empty['legal_assignments'], 4096)
        self.assertEqual(empty['same_color_target_witness'], [1] * 6)
        self.assertEqual(full['legal_assignments'], 24)
        self.assertTrue(full['target_inequality_proved'])
        self.assertIsNone(full['same_color_target_witness'])
        self.assertIn(['v', 'w'], full['different_names'])
        self.assertEqual(self.report['graph_assignment_pairs'], 3 * 4096)

    def test_saved_replay_does_not_run_learner_or_any_coloring_search(self):
        """Stored complete query evidence suffices for independent replay."""
        with patch.object(rule, 'learn_logical_inequalities', side_effect=AssertionError('learner')), \
                patch('scripts.exact_extendibility_oracle.solve_exact', side_effect=AssertionError('oracle')):
            checked = self.check_small(self.report)
        self.assertTrue(checked['passed'])
        self.assertEqual(checked['learner_runs'], 0)

    def test_missing_query_and_forged_learning_hash_are_rejected(self):
        """All nonedge queries, including inconclusive ones, remain bound."""
        for change in (lambda row: row['learning']['queries'].pop(),
                       lambda row: row.__setitem__('learning_sha256', '0' * 64)):
            bad = deepcopy(self.report)
            change(bad['per_graph'][0])
            with self.subTest(change=change), self.assertRaises(AssertionError):
                self.check_small(bad)

    def test_proof_raw_edge_literal_witness_and_census_mutations_are_rejected(self):
        """A passed flag or plausible statistic cannot replace exact evidence."""
        mutations = [lambda item: item['per_graph'][0].__setitem__('legal_assignments', 4095),
                     lambda item: item['per_graph'][0]['same_color_target_witness'].__setitem__(0, 4),
                     lambda item: item.__setitem__('graph_assignment_pairs', 0),
                     lambda item: item['per_graph'][-1]['learning']['queries'][-1]['result'].__setitem__('status', 'inconclusive')]
        for change in mutations:
            bad = deepcopy(self.report)
            change(bad)
            with self.subTest(change=change), self.assertRaises((AssertionError, ValueError)):
                self.check_small(bad)


if __name__ == '__main__':
    unittest.main()

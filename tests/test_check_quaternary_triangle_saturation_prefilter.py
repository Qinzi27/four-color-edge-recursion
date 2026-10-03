"""Saved-evidence controls for exact prefilter accounting and first choices."""

from copy import deepcopy
from itertools import combinations
import unittest
from unittest.mock import patch

from scripts.check_quaternary_triangle_saturation import check_triangle_saturations
from scripts.check_quaternary_triangle_saturation_prefilter import (
    IMPLEMENTATION, WORK_KEYS, _triple_rank, check_prefilter_work,
)
from scripts.quaternary_triangle_saturation import find_triangle_saturations
from scripts.scan_low_color_obstruction_states import digest


def clique_document(sides):
    """Return a synthetic literal clique; no production archive is queried."""
    return {'sides': list(sides), 'lines': [
        {'id': str(i), 'left': a, 'right': b, 'kind': 'separator'}
        for i, (a, b) in enumerate(combinations(sides, 2))]}


def saved_telemetry(document, domains, equal_names, counts):
    """Bind manually derived work counts, independent of the new detector."""
    return {'implementation': IMPLEMENTATION,
            'raw_document_sha256': digest(document), 'domains_sha256': digest(domains),
            'equal_names_sha256': digest(equal_names), 'statistics': dict(zip(
                ('eligible_palette_checks', 'neighbor_membership_tests',
                 'skipped_palette_checks', 'triangles_skipped', 'triangles_enumerated'), counts))}


class PrefilterWorkCheckerTests(unittest.TestCase):
    """Valid mathematics alone cannot establish deterministic work telemetry."""

    def setUp(self):
        self.raw = clique_document(['T', 'A', 'B', 'C'])
        self.domains = [[1, 2, 3, 4]] + [[2, 3, 4] for _ in range(3)]
        self.equal = []
        self.evidence = find_triangle_saturations(self.raw, self.domains, self.equal)
        self.telemetry = saved_telemetry(self.raw, self.domains, self.equal,
                                       [13, 39, 12, 12, 1])

    def check(self, evidence=None, telemetry=None):
        """Replay the default fixture using already saved certificate records."""
        return check_prefilter_work(self.raw, self.domains, self.equal,
                                    self.evidence if evidence is None else evidence,
                                    self.telemetry if telemetry is None else telemetry)

    def test_one_certificate_and_twelve_skipped_palettes(self):
        before = deepcopy((self.raw, self.domains, self.equal, self.evidence, self.telemetry))
        result = self.check()
        self.assertTrue(result['passed'])
        self.assertEqual(result['certificates_checked'], 1)
        self.assertEqual(result['palette_checks_checked'], 13)
        self.assertEqual(result['statistics'], self.telemetry['statistics'])
        self.assertEqual((self.raw, self.domains, self.equal, self.evidence, self.telemetry), before)

    def test_empty_and_singleton_targets_and_checked_absence(self):
        for target, counts, certificates, palettes in [
                ([1], [15, 45, 15, 15, 0], 0, 16),
                ([], [3, 9, 0, 0, 3], 3, 7)]:
            domains = [target] + self.domains[1:]
            evidence = find_triangle_saturations(self.raw, domains, [])
            telemetry = saved_telemetry(self.raw, domains, [], counts)
            checked = check_prefilter_work(self.raw, domains, [], evidence, telemetry)
            self.assertEqual(checked['certificates_checked'], certificates)
            self.assertEqual(checked['palette_checks_checked'], palettes)

    def test_full_domains_and_degree_below_three_can_skip_zero_triples(self):
        for n in (1, 2, 3, 4):
            raw = clique_document([f'S{i}' for i in range(n)])
            domains = [[1, 2, 3, 4] for _ in range(n)]
            evidence = find_triangle_saturations(raw, domains, [])
            counts = [4 * n, 4 * n * (n - 1), 4 * n, 16 if n == 4 else 0, 0]
            checked = check_prefilter_work(raw, domains, [], evidence,
                                          saved_telemetry(raw, domains, [], counts))
            self.assertEqual(checked['certificates_checked'], 0)

    def test_lexicographic_rank_matches_literal_combinations(self):
        for n in range(3, 12):
            vertices = list(range(0, 2 * n, 2))
            for number, triple in enumerate(combinations(vertices, 3), 1):
                self.assertEqual(_triple_rank(vertices, triple), number)

    def test_first_triangle_is_required_even_when_alternative_is_valid(self):
        raw = clique_document(['T', 'A', 'B', 'C', 'D'])
        domains = [[1, 2, 3, 4]] + [[2, 3, 4] for _ in range(4)]
        evidence = find_triangle_saturations(raw, domains, [])
        telemetry = saved_telemetry(raw, domains, [], [5, 20, 0, 0, 17])
        self.assertTrue(check_prefilter_work(raw, domains, [], evidence, telemetry)['passed'])
        changed = deepcopy(evidence)
        row = changed['certificates'][0]
        row['triangle'] = ['A', 'B', 'D']
        row['edges'] = [['A', 'B'], ['A', 'D'], ['B', 'D'],
                        ['T', 'A'], ['T', 'B'], ['T', 'D']]
        self.assertTrue(check_triangle_saturations(raw, domains, [], changed)['passed'])
        with self.assertRaisesRegex(AssertionError, 'deterministic first'):
            check_prefilter_work(raw, domains, [], changed, telemetry)

    def test_first_palette_is_required_even_when_later_palette_is_valid(self):
        domains = [[1, 2, 3, 4]] + [[3, 4] for _ in range(3)]
        evidence = find_triangle_saturations(self.raw, domains, [])
        # Each other target sees only two neighbors excluding either 1 or 2.
        telemetry = saved_telemetry(self.raw, domains, [], [13, 39, 12, 12, 1])
        changed = deepcopy(evidence)
        changed['certificates'][0]['excluded_color'] = 2
        changed['certificates'][0]['removed_colors'] = [1, 3, 4]
        self.assertTrue(check_triangle_saturations(self.raw, domains, [], changed)['passed'])
        with self.assertRaisesRegex(AssertionError, 'deterministic first'):
            check_prefilter_work(self.raw, domains, [], changed, telemetry)

    def test_eq_classes_count_once_and_literal_witness_tie_break_is_required(self):
        raw = deepcopy(self.raw)
        raw['sides'].append('U')
        raw['lines'].append({'id': 'extra', 'left': 'U', 'right': 'A', 'kind': 'separator'})
        equal = [['T', 'U'], ['U', 'T'], ['T', 'T']]
        domains = self.domains + [[1, 2, 3, 4]]
        evidence = find_triangle_saturations(raw, domains, equal)
        telemetry = saved_telemetry(raw, domains, equal, [13, 39, 12, 12, 1])
        self.assertTrue(check_prefilter_work(raw, domains, equal, evidence, telemetry)['passed'])
        changed = deepcopy(evidence)
        changed['certificates'][0]['edges'][3] = ['U', 'A']
        self.assertTrue(check_triangle_saturations(raw, domains, equal, changed)['passed'])
        with self.assertRaisesRegex(AssertionError, 'physical witness'):
            check_prefilter_work(raw, domains, equal, changed, telemetry)

    def test_not_enough_excluding_neighbors_and_no_triangle_are_distinct(self):
        raw = deepcopy(self.raw)
        raw['lines'] = [line for line in raw['lines'] if
                        {line['left'], line['right']} != {'A', 'B'}]
        # T has three excluding neighbors, so its q=1 triple is actually
        # examined despite the missing physical A-B edge. All other palettes
        # skip; A/B have degree two and therefore skip zero old triples.
        evidence = find_triangle_saturations(raw, self.domains, [])
        telemetry = saved_telemetry(raw, self.domains, [], [16, 40, 15, 7, 1])
        self.assertTrue(check_prefilter_work(raw, self.domains, [], evidence, telemetry)['passed'])

    def test_every_work_counter_requires_exact_literal_nonnegative_integer(self):
        for key in WORK_KEYS:
            for value in (True, -1, 1.5, self.telemetry['statistics'][key] + 1):
                changed = deepcopy(self.telemetry)
                changed['statistics'][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(AssertionError):
                    self.check(telemetry=changed)

    def test_old_loose_counters_now_require_exact_reconstruction(self):
        for key in ('palettes_examined', 'triangles_examined'):
            changed = deepcopy(self.evidence)
            changed['statistics'][key] -= 1
            self.assertTrue(check_triangle_saturations(
                self.raw, self.domains, [], changed)['passed'])
            with self.subTest(key=key), self.assertRaisesRegex(AssertionError, 'legacy counters'):
                self.check(evidence=changed)

    def test_input_hash_implementation_and_field_coverage_are_bound(self):
        changes = [(key, '0' * 64) for key in
                   ('raw_document_sha256', 'domains_sha256', 'equal_names_sha256')]
        changes += [('implementation', 'different-version'), ('extra', True)]
        for key, value in changes:
            changed = deepcopy(self.telemetry)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(AssertionError):
                self.check(telemetry=changed)
        changed = deepcopy(self.telemetry)
        changed['statistics'].pop('triangles_enumerated')
        with self.assertRaises(AssertionError):
            self.check(telemetry=changed)

    def test_replay_never_calls_detector_propagation_or_search(self):
        with patch('scripts.quaternary_triangle_saturation.find_triangle_saturations',
                   side_effect=RuntimeError('old detector')), patch(
                       'scripts.quaternary_triangle_saturation_prefilter.find_triangle_saturations_prefilter',
                       side_effect=RuntimeError('new detector')), patch(
                       'scripts.quaternary_triangle_saturation_contacts.propagate_diamond_contacts',
                       side_effect=RuntimeError('propagation')), patch(
                           'scripts.exact_extendibility_oracle.solve_exact',
                           side_effect=RuntimeError('search')):
            result = self.check()
        self.assertEqual(result['detector_reruns'], 0)
        self.assertEqual(result['producer_reruns'], 0)


if __name__ == '__main__':
    unittest.main()

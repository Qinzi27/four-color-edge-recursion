"""Whole-line representation and non-branching propagation regression tests.

The fixed geometry corpus is generated once without a coloring solver. Human
remote-contact witnesses are checked independently with both PlaneMap and the
line-name auditor. Four is an explicit propagation palette, not a test result.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import unittest

from fourcolor.embedding import PlaneMap
from fourcolor.line_names import audit_line_names
from fourcolor.whole_lines import (
    build_whole_lines, decode_profiles, encode_profiles, propagate_candidates,
    restart_with_symbol_symmetry, reverse_profile,
)

ROOT = Path(__file__).resolve().parents[1]


def independent_plane(geometry: dict) -> PlaneMap:
    """Reconstruct the rotation system without consulting the whole-line model."""
    return PlaneMap(tuple((str(edge['a']), str(edge['b'])) for edge in geometry['edges']),
                    {str(i): tuple(darts) for i, darts in enumerate(geometry['rotation'])})


def names_for(plane: PlaneMap, colors: list[int]) -> tuple[tuple[str, str], ...]:
    """Express a supplied positive-integer witness as arbitrary symbolic pairs."""
    return tuple((str(colors[left]), str(colors[right]))
                 for left, right in (plane.shores(edge) for edge in range(len(plane.edges))))


class WholeLineTests(unittest.TestCase):
    """Junctions subdivide profiles but do not erase whole-source-line identity."""

    @classmethod
    def setUpClass(cls):
        """Generate 255 fixtures once in memory; do not write dated outputs."""
        process = subprocess.run(['node', 'scripts/whole-line-fixtures.mjs', '--emit'],
                                 cwd=ROOT, capture_output=True, text=True,
                                 encoding='utf-8', check=True)
        cls.fixtures = json.loads(process.stdout)
        cls.records = {row['id']: row for row in cls.fixtures['records']}
        cls.models = {key: build_whole_lines(row['geometry']) for key, row in cls.records.items()}
        cls.restarts = {key: restart_with_symbol_symmetry(model) for key, model in cls.models.items()}

    def test_fixed_corpus_retains_every_final_geometry(self):
        self.assertEqual(len(self.records), 255)
        self.assertEqual(self.fixtures['baseline_maps'], 252)
        generated = [row['seed'] for row in self.records.values() if row['seed'] is not None]
        self.assertEqual(generated, list(range(20260908, 20261148)))

    def test_all_real_edges_are_owned_exactly_once(self):
        for key, model in self.models.items():
            with self.subTest(map=key):
                geometry = self.records[key]['geometry']
                oracle = independent_plane(geometry)
                self.assertEqual(model.plane_map.faces, oracle.faces)
                self.assertEqual(model.plane_map.face_of_dart, oracle.face_of_dart)
                covered = [span['edge'] for line in model.lines for span in line['spans']]
                real = {i for i, edge in enumerate(geometry['edges']) if not edge['virtual']}
                self.assertEqual(set(covered), real)
                self.assertEqual(len(covered), len(set(covered)))
                self.assertEqual(set(model.edge_owner), real)
                for line in model.lines:
                    self.assertAlmostEqual(line['spans'][0]['t0'], 0)
                    self.assertAlmostEqual(line['spans'][-1]['t1'], 1)
                    for earlier, later in zip(line['spans'], line['spans'][1:]):
                        self.assertAlmostEqual(earlier['t1'], later['t0'])
                    for span in line['spans']:
                        self.assertEqual(span['dart'] // 2, span['edge'])
                        self.assertEqual(span['left_side'], oracle.face_of_dart[span['dart']])
                        self.assertEqual(span['right_side'], oracle.face_of_dart[span['dart'] ^ 1])
                        self.assertEqual(model.edge_owner[span['edge']], line['id'])

    def test_t_junction_preserves_mother_id_and_adds_profile_interval(self):
        line_id = 'L:0,180>900,180'
        before = next(line for line in self.models['D-before'].lines if line['id'] == line_id)
        after = next(line for line in self.models['teaching-D'].lines if line['id'] == line_id)
        self.assertEqual(before['endpoints'], [[0, 180], [900, 180]])
        self.assertEqual(before['endpoints'], after['endpoints'])
        self.assertEqual(len(before['spans']), 3)
        self.assertEqual(len(after['spans']), 4)
        self.assertNotIn(0.5, [span['t0'] for span in before['spans']])
        self.assertIn(0.5, [span['t0'] for span in after['spans']])
        self.assertEqual(before['sources'], after['sources'])
        event = next(event for event in after['events'] if event['point'] == [450, 180])
        ports = event['ports_ccw']
        self.assertEqual(sum(port[0] == line_id for port in ports), 2)
        self.assertEqual(len(ports), 3)
        self.assertEqual({port[1] for port in ports if port[0] == line_id}, {'+', '-'})
        self.assertIn('L:450,180>450,600', {port[0] for port in ports})

    def test_x_junction_keeps_both_complete_crossing_lines(self):
        model = self.models['gallery-grid']
        self.assertEqual(len(model.lines), 8)  # Four vertical, three horizontal, one frame.
        vertical = next(line for line in model.lines if line['id'] == 'L:180,0>180,600')
        horizontal = next(line for line in model.lines if line['id'] == 'L:0,150>900,150')
        self.assertEqual(len(vertical['spans']), 4)
        self.assertEqual(len(horizontal['spans']), 5)
        event = next(event for event in vertical['events'] if event['point'] == [180, 150])
        self.assertEqual(len(event['ports_ccw']), 4)
        for line in (vertical, horizontal):
            self.assertEqual({port[1] for port in event['ports_ccw'] if port[0] == line['id']}, {'+', '-'})

    def test_frame_is_one_closed_oriented_line(self):
        for key, model in self.models.items():
            with self.subTest(map=key):
                frame = [line for line in model.lines if line['id'] == 'frame']
                self.assertEqual(len(frame), 1)
                frame = frame[0]
                self.assertTrue(frame['closed'])
                self.assertEqual(frame['endpoints'][0], frame['endpoints'][1])
                self.assertEqual({span['edge'] for span in frame['spans']},
                                 {i for i, edge in enumerate(self.records[key]['geometry']['edges'])
                                  if edge['frame']})
                self.assertTrue(all(span['left_side'] == self.records[key]['geometry']['outerFace']
                                    for span in frame['spans']))
                self.assertTrue(all(not line['closed'] for line in model.lines if line['id'] != 'frame'))

    def test_virtual_connectors_are_not_mother_lines(self):
        saw_virtual = False
        for key, model in self.models.items():
            for edge in model.virtual_edges:
                saw_virtual = True
                with self.subTest(map=key, edge=edge):
                    self.assertNotIn(edge, model.edge_owner)
                    self.assertEqual(model.plane_map.shores(edge)[0], model.plane_map.shores(edge)[1])
                    self.assertTrue(self.records[key]['geometry']['edges'][edge]['virtual'])
        self.assertTrue(saw_virtual, 'The corpus must actually exercise virtual island connections')

    def test_arbitrary_per_dart_values_roundtrip_without_side_merging(self):
        for key, model in self.models.items():
            with self.subTest(map=key):
                # Deliberately distinct labels on one side: representation roundtrip
                # must not secretly impose a color assignment or merge intervals.
                values = [{'dart': dart, 'tag': f'label-{dart}', 'domain': [dart, dart + 1]}
                          for dart in range(2 * len(model.plane_map.edges))]
                encoded = encode_profiles(model, values)
                self.assertEqual(decode_profiles(model, encoded), values)
                self.assertEqual(set(encoded['virtual']), {str(edge) for edge in model.virtual_edges})
                for line in model.lines:
                    self.assertEqual(len(encoded['lines'][line['id']]), len(line['spans']))

    def test_reverse_twice_restores_values_and_approximate_positions(self):
        for key, model in self.models.items():
            values = list(range(2 * len(model.plane_map.edges)))
            encoded = encode_profiles(model, values)
            for line_id, profile in encoded['lines'].items():
                with self.subTest(map=key, line=line_id):
                    backwards = reverse_profile(profile)
                    self.assertEqual(backwards[0]['left'], profile[-1]['right'])
                    self.assertEqual(backwards[0]['right'], profile[-1]['left'])
                    self.assertEqual(backwards[0]['dart'], profile[-1]['dart'] ^ 1)
                    restored = reverse_profile(backwards)
                    self.assertEqual(len(restored), len(profile))
                    for actual, expected in zip(restored, profile):
                        for field in ('left', 'right', 'dart'):
                            self.assertEqual(actual[field], expected[field])
                        self.assertAlmostEqual(actual['t0'], expected['t0'], places=14)
                        self.assertAlmostEqual(actual['t1'], expected['t1'], places=14)

    def test_moved_interval_and_missing_line_are_rejected(self):
        model = self.models['teaching-D']
        encoded = encode_profiles(model, list(range(2 * len(model.plane_map.edges))))
        moved = deepcopy(encoded)
        moved['lines']['L:0,180>900,180'][0]['t1'] += 0.01
        with self.assertRaisesRegex(ValueError, 'geometry mismatch'):
            decode_profiles(model, moved)
        missing = deepcopy(encoded)
        del missing['lines']['L:0,180>900,180']
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            decode_profiles(model, missing)
        shortened = deepcopy(encoded)
        shortened['lines']['L:0,180>900,180'].pop()
        with self.assertRaisesRegex(ValueError, 'interval missing'):
            decode_profiles(model, shortened)

    def test_remote_witnesses_pass_two_independent_checks(self):
        for key in ('remote-before', 'remote-after'):
            record = self.records[key]
            plane = independent_plane(record['geometry'])
            for label, witness in record['witnesses'].items():
                with self.subTest(map=key, witness=label):
                    colors = witness['colors']
                    self.assertEqual(plane.check_coloring([symbol - 1 for symbol in colors]), witness['valid'])
                    audit = audit_line_names(tuple(plane.rotation.values()), names_for(plane, colors))
                    self.assertEqual(audit.status, 'consistent' if witness['valid'] else 'conflict')
                    self.assertEqual(audit.side_orbits, plane.faces)
                    conflicts = {edge for edge in range(len(plane.edges))
                                 if plane.shores(edge)[0] != plane.shores(edge)[1]
                                 and colors[plane.shores(edge)[0]] == colors[plane.shores(edge)[1]]}
                    self.assertEqual(conflicts, {item['edge'] for item in witness['conflictedges']})
        bad = self.records['remote-after']['witnesses']['endpoint_only']
        self.assertEqual(len(bad['conflictedges']), 1)
        self.assertEqual({bad['conflictedges'][0]['left_role'], bad['conflictedges'][0]['right_role']},
                         {'east', 'R'})

    def remote_anchors(self, roles: tuple[str, ...]) -> tuple[object, dict, dict]:
        """Translate known witness roles into explicit dart-domain anchors."""
        model = self.models['remote-after']
        witness = self.records['remote-after']['witnesses']['side_switched']
        role_faces = witness['role_to_face']
        anchors = {model.plane_map.faces[role_faces[role]][0]: [witness['colors'][role_faces[role]]]
                   for role in roles}
        return model, anchors, role_faces

    def test_remote_contact_forces_west_four_east_one_without_choices(self):
        model, anchors, roles = self.remote_anchors(('external', 'A', 'R', 'D'))
        outcome = propagate_candidates(model, anchors)
        self.assertEqual(outcome['status'], 'solved')
        self.assertEqual(outcome['domains'][roles['west']], [4])
        self.assertEqual(outcome['domains'][roles['east']], [1])
        self.assertEqual(outcome['backtracks'], 0)
        self.assertEqual(outcome['choices'], 0)
        self.assertEqual([domain[0] for domain in outcome['domains']],
                         self.records['remote-after']['witnesses']['side_switched']['colors'])
        self.assertTrue(outcome['trace'])

    def test_freezing_wrong_west_name_reports_conflict(self):
        model, anchors, roles = self.remote_anchors(('external', 'A', 'R', 'D'))
        anchors[model.plane_map.faces[roles['west']][0]] = [1]
        outcome = propagate_candidates(model, anchors)
        self.assertEqual(outcome['status'], 'conflict')
        self.assertTrue(any(not domain for domain in outcome['domains']))
        self.assertEqual(outcome['choices'], 0)

    def test_reset_to_outer_and_one_inner_anchor_stays_underdetermined(self):
        model, anchors, _ = self.remote_anchors(('external', 'A'))
        outcome = propagate_candidates(model, anchors)
        self.assertEqual(outcome['status'], 'underdetermined')
        self.assertTrue(any(len(domain) > 1 for domain in outcome['domains']))
        self.assertEqual(outcome['choices'], 0)
        self.assertEqual(outcome['backtracks'], 0)

    def test_empty_domain_and_conflicting_same_side_anchors_report_conflict(self):
        model, anchors, roles = self.remote_anchors(('external',))
        dart = next(iter(anchors))
        self.assertEqual(propagate_candidates(model, {dart: []})['status'], 'conflict')
        first, second = model.plane_map.faces[roles['external']][:2]
        self.assertNotEqual(first, second)
        self.assertEqual(propagate_candidates(model, {first: [1], second: [2]})['status'], 'conflict')

    def test_invalid_palette_and_out_of_palette_anchor_are_rejected(self):
        model, anchors, _ = self.remote_anchors(('external',))
        for palette in ((), (0,), (-1,), (True,), (1, True), (1.5,), ('1',)):
            with self.subTest(palette=palette), self.assertRaises(ValueError):
                propagate_candidates(model, anchors, palette=palette)
        with self.assertRaisesRegex(ValueError, 'outside supplied palette'):
            propagate_candidates(model, {next(iter(anchors)): [5]})

    def test_symmetry_restart_counts_and_every_complete_certificate(self):
        """Count finite outcomes without treating nonempty domains as solutions."""
        counts = {status: sum(result['status'] == status for result in self.restarts.values())
                  for status in ('solved', 'underdetermined', 'conflict')}
        self.assertEqual(counts, {'solved': 7, 'underdetermined': 248, 'conflict': 0})
        for key, result in self.restarts.items():
            with self.subTest(map=key):
                self.assertEqual(result['backtracks'], 0)
                self.assertEqual(result['choices'], len(result['symmetry_steps']))
                self.assertEqual(result['symmetry_choices'], result['choices'])
                self.assertEqual(result['non_symmetry_choices'], 0)
                if result['status'] == 'underdetermined':
                    self.assertTrue(any(len(domain) > 1 for domain in result['domains']))
                    continue
                self.assertTrue(all(len(domain) == 1 for domain in result['domains']))
                colors = [domain[0] for domain in result['domains']]
                oracle = independent_plane(self.records[key]['geometry'])
                self.assertTrue(oracle.check_coloring([symbol - 1 for symbol in colors]))
                self.assertEqual(audit_line_names(tuple(oracle.rotation.values()),
                                                 names_for(oracle, colors)).status, 'consistent')

    def test_each_symmetry_step_is_exactly_the_entire_unused_symbol_set(self):
        """Replay anchors to reject choices mixing used and unused symbols."""
        saw_symmetry_choice = False
        for key, model in self.models.items():
            with self.subTest(map=key):
                result = self.restarts[key]
                frame = next(line for line in model.lines if line['id'] == 'frame')
                first = frame['spans'][0]['dart']
                anchors = {first: [1], first ^ 1: [2]}
                for step in result['symmetry_steps']:
                    saw_symmetry_choice = True
                    state = propagate_candidates(model, anchors)
                    self.assertEqual(state['status'], 'underdetermined')
                    self.assertEqual(state['choices'], 0)
                    used = {domain[0] for domain in state['domains'] if len(domain) == 1}
                    unused = set(state['palette']) - used
                    self.assertGreater(len(unused), 1)
                    self.assertEqual(set(state['domains'][step['side']]), unused)
                    self.assertEqual(step['equivalent_unused_symbols'], sorted(unused))
                    self.assertEqual(step['canonical_symbol'], min(unused))
                    self.assertEqual(model.plane_map.face_of_dart[step['dart']], step['side'])
                    self.assertEqual(model.edge_owner[step['dart'] // 2], step['whole_line'])
                    self.assertTrue(set(state['domains'][step['side']]).isdisjoint(used))
                    anchors[step['dart']] = [step['canonical_symbol']]
                replayed = propagate_candidates(model, anchors)
                self.assertEqual(anchors, result['anchors_by_dart'])
                for field in ('status', 'domains', 'trace', 'backtracks', 'palette'):
                    self.assertEqual(replayed[field], result[field])
                if replayed['status'] == 'underdetermined':
                    used = {domain[0] for domain in replayed['domains'] if len(domain) == 1}
                    unused = set(replayed['palette']) - used
                    # Remaining uncertainty must not conceal another eligible
                    # unused-symbol-only domain that the restart forgot to process.
                    if len(unused) > 1:
                        self.assertTrue(all(set(domain) != unused for domain in replayed['domains']))
        self.assertTrue(saw_symmetry_choice)

    def test_remote_fresh_restart_uses_only_frame_and_canonical_symmetry(self):
        """Fresh names differ from the conditional witness by a global 3/4 swap."""
        result = self.restarts['remote-after']
        roles = self.records['remote-after']['witnesses']['side_switched']['role_to_face']
        self.assertEqual(result['status'], 'solved')
        expected = {'external': 1, 'A': 2, 'R': 3, 'D': 4, 'west': 3, 'east': 1}
        self.assertEqual({role: result['domains'][side][0] for role, side in roles.items()}, expected)
        self.assertEqual([domain[0] for domain in result['domains']], [1, 2, 3, 4, 3, 1])
        self.assertEqual(result['choices'], 1)
        self.assertEqual(result['symmetry_choices'], 1)
        self.assertEqual(result['non_symmetry_choices'], 0)
        self.assertEqual(len(result['anchors_by_dart']), 3)  # Two root anchors plus one canonical choice.
        self.assertEqual(self.records['remote-after']['witnesses']['side_switched']['colors'],
                         [1, 2, 4, 3, 4, 1])

    def test_symmetry_restart_is_deterministic_for_identical_geometry(self):
        """Re-running cannot silently search for a more favorable representative."""
        for key, model in self.models.items():
            with self.subTest(map=key):
                self.assertEqual(restart_with_symbol_symmetry(model), self.restarts[key])


if __name__ == '__main__':
    unittest.main()

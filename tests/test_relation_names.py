"""Independent ordered-pair soundness tests for relation/path consistency.

Bounded enumeration appears ONLY in these tests. Neither complete assignments
nor target colors are supplied to the production filter. Auxiliary relations
between nonadjacent sides must not be mistaken for additional drawn lines.
"""
from __future__ import annotations

from copy import deepcopy
from itertools import permutations, product
import json
from pathlib import Path
import random
import subprocess
import unittest
from unittest.mock import patch

from fourcolor.line_names import audit_line_names
from fourcolor.relation_names import (
    compose, initial_relations, pairs, relation_closure, run_relation_names, transpose,
)
from fourcolor.whole_lines import build_whole_lines

ROOT = Path(__file__).resolve().parents[1]
PALETTE = (1, 2, 3, 4)


def mask_of(values):
    """Encode independent test pairs without using the production encoder."""
    return sum(1 << (4 * (a - 1) + b - 1) for a, b in set(values))


def pair_set(mask):
    """Decode test masks into sets for plain relational algebra."""
    return {(a, b) for a in PALETTE for b in PALETTE if mask & (1 << (4 * (a - 1) + b - 1))}


def oracle_compose(left, right):
    """Ordinary set composition, independent of bit-row optimization."""
    return mask_of((a, b) for a, middle in pair_set(left)
                   for second, b in pair_set(right) if middle == second)


def domain_matrix(domains, unequal_edges):
    """Construct an abstract constraint matrix, not a geometric embedding."""
    edges = {frozenset(edge) for edge in unequal_edges}
    return [[mask_of((a, b) for a in first for b in second
                     if (a == b if i == j else a != b if frozenset((i, j)) in edges else True))
             for j, second in enumerate(domains)] for i, first in enumerate(domains)]


def domains_from_matrix(matrix):
    """Read diagonal candidates with no row-union approximation."""
    return [sorted(a for a, b in pair_set(row[i]) if a == b) for i, row in enumerate(matrix)]


def adjacency_edges(plane):
    """Ignore bridges and identify real separator constraints independently."""
    return {tuple(sorted(plane.shores(edge))) for edge in range(len(plane.edges))
            if plane.shores(edge)[0] != plane.shores(edge)[1]}


class RelationNameTests(unittest.TestCase):
    """Check relations, not only unary domain projections or solved flags."""

    @classmethod
    def setUpClass(cls):
        """Use the preserved corpus and small geometric examples, without writes."""
        source = subprocess.run(['node', 'scripts/whole-line-fixtures.mjs', '--emit'], cwd=ROOT,
                                capture_output=True, text=True, encoding='utf-8', check=True)
        cls.records = {row['id']: row for row in json.loads(source.stdout)['records']}
        chosen = ('teaching-D', 'D-before', 'teaching-E', 'gallery-dangling',
                  'gallery-tetrahedron', 'gallery-islands', 'remote-after')
        cls.models = {key: build_whole_lines(cls.records[key]['geometry']) for key in chosen}
        cls.proof = json.loads((ROOT / 'outputs/weighted-counterexample-candidate-2026-09-18-v2.json')
                              .read_text(encoding='utf-8'))['proof']
        cls.nine = build_whole_lines(cls.proof['geometry'])
        program = r'''
import {buildMap} from './web/engine.js';
const polygon=p=>p.map((a,i)=>({a,b:p[(i+1)%p.length]}));
const inputs={
 chain:polygon([[300,200],[600,200],[600,400],[300,400]]),
 two_islands:[...polygon([[100,200],[300,200],[300,400],[100,400]]),
              ...polygon([[600,200],[800,200],[800,400],[600,400]])],
};
console.log(JSON.stringify(Object.fromEntries(Object.entries(inputs).map(([key,strokes])=>{
 const m=buildMap({strokes});return [key,{vertices:m.vertices,edges:m.edges,rotation:m.rotation,
  faceOfDart:m.faceOfDart,faces:m.faces.map(f=>f.darts),outerFace:m.outerFace,original:m.original}];
}))));
'''
        small = subprocess.run(['node', '--input-type=module', '-e', program], cwd=ROOT,
                               capture_output=True, text=True, encoding='utf-8', check=True)
        cls.small_geometry = json.loads(small.stdout)
        cls.small = {key: build_whole_lines(geometry) for key, geometry in cls.small_geometry.items()}

    def replay_phase(self, matrix, trace):
        """Verify each recorded triple composition against plain set operations."""
        current = deepcopy(matrix)
        for event in trace:
            i, j, via = event['i'], event['j'], event['via']
            self.assertTrue(all(value for row in current for value in row))
            self.assertEqual(event['before'], current[i][j])
            self.assertEqual(event['left'], current[i][via])
            self.assertEqual(event['right'], current[via][j])
            after = current[i][j] & oracle_compose(current[i][via], current[via][j])
            self.assertEqual(event['after'], after)
            self.assertEqual(event['removed'], current[i][j] ^ after)
            self.assertNotEqual(event['removed'], 0)
            current[i][j] = after
            current[j][i] = mask_of((b, a) for a, b in pair_set(after))
        return current

    def check_fixed_point(self, matrix):
        """A nonempty terminal relation must have support through EVERY index."""
        for i, row in enumerate(matrix):
            for j, value in enumerate(row):
                self.assertEqual(matrix[j][i], mask_of((b, a) for a, b in pair_set(value)))
                for via in range(len(matrix)):
                    self.assertEqual(value & oracle_compose(matrix[i][via], matrix[via][j]), value)

    def check_run(self, model, outcome):
        """Replay interleaved strict closures and global binary-safe normalizations."""
        expected = domain_matrix(outcome['base']['domains'], adjacency_edges(model.plane_map))
        self.assertEqual(outcome['initial_relations'], expected)
        current = deepcopy(expected)
        self.assertEqual(len(outcome['phases']), len(outcome['normalizations']) + 1)
        for index, trace in enumerate(outcome['phases']):
            current = self.replay_phase(current, trace)
            if all(value for row in current for value in row):
                self.check_fixed_point(current)
            if index < len(outcome['normalizations']):
                event = outcome['normalizations'][index]
                domains = domains_from_matrix(current)
                used = {domain[0] for domain in domains if len(domain) == 1}
                unused = sorted(set(PALETTE) - used)
                self.assertGreater(len(unused), 1)
                self.assertEqual(event['unused'], unused)
                self.assertEqual(domains[event['side']], unused)
                self.assertEqual(event['symbol'], min(unused))
                # Unary invariance alone is insufficient: transform both names
                # in every adjacent AND nonadjacent compatibility relation.
                for values in permutations(unused):
                    mapping = dict(zip(unused, values))
                    for row in current:
                        for mask in row:
                            transformed = {(mapping.get(a, a), mapping.get(b, b)) for a, b in pair_set(mask)}
                            self.assertEqual(transformed, pair_set(mask))
                side = event['side']
                self.assertEqual(event['before'], current[side][side])
                self.assertEqual(event['after'], mask_of([(event['symbol'], event['symbol'])]))
                self.assertEqual(model.plane_map.face_of_dart[event['dart']], side)
                self.assertEqual(model.edge_owner[event['dart'] // 2], event['line'])
                current[side][side] = event['after']
        self.assertEqual(outcome['relations'], current)
        self.assertEqual(outcome['domains'], domains_from_matrix(current))
        self.assertEqual(outcome['choices'], len(outcome['normalizations']))
        self.assertEqual(outcome['non_symmetry_choices'], 0)
        self.assertEqual(outcome['backtracks'], 0)
        expected_status = ('conflict' if any(value == 0 for row in current for value in row)
                           else 'solved' if all(len(d) == 1 for d in outcome['domains']) else 'underdetermined')
        self.assertEqual(outcome['status'], expected_status)
        if outcome['status'] == 'solved':
            colors = [domain[0] for domain in outcome['domains']]
            self.assertTrue(model.plane_map.check_coloring([color - 1 for color in colors]))
            names = tuple((str(colors[left]), str(colors[right])) for left, right in
                          (model.plane_map.shores(edge) for edge in range(len(model.plane_map.edges))))
            self.assertEqual(audit_line_names(tuple(model.plane_map.rotation.values()), names).status, 'consistent')

    def test_relation_algebra_matches_plain_pair_sets(self):
        rng = random.Random(20260918)
        masks = [0, 1, 0x8421, 65535] + [rng.randrange(65536) for _ in range(64)]
        for index, left in enumerate(masks):
            right = masks[-index - 1]
            self.assertEqual({tuple(pair) for pair in pairs(left)}, pair_set(left))
            self.assertEqual(transpose(left), mask_of((b, a) for a, b in pair_set(left)))
            self.assertEqual(transpose(transpose(left)), left)
            self.assertEqual(compose(left, right), oracle_compose(left, right))

    def test_tiny_domain_enumeration_preserves_every_complete_assignment_pair(self):
        """Audit every legal pair of every solution, including non-edge pairs."""
        subsets = [{color for color in PALETTE if mask & (1 << (color - 1))} for mask in range(1, 16)]
        checked = 0
        for edges in (((0, 1), (1, 2)), ((0, 1), (1, 2), (0, 2))):
            for domains in product(subsets, repeat=3):
                before = domain_matrix(domains, edges)
                original = deepcopy(before)
                result = relation_closure(before)
                self.assertEqual(before, original)
                completions = [values for values in product(*domains)
                               if all(values[a] != values[b] for a, b in edges)]
                if completions:
                    self.assertFalse(result['conflict'])
                    for values in completions:
                        for i, a in enumerate(values):
                            for j, b in enumerate(values):
                                self.assertTrue(result['relations'][i][j] & mask_of([(a, b)]))
                if result['conflict']:
                    self.assertFalse(completions)
                self.assertEqual(self.replay_phase(before, result['trace']), result['relations'])
                checked += 1
        self.assertEqual(checked, 6750)

    def test_two_color_chain_derives_equal_names_for_nonadjacent_ends(self):
        matrix = domain_matrix([{1, 2}] * 3, ((0, 1), (1, 2)))
        self.assertEqual(pair_set(matrix[0][2]), {(1, 1), (1, 2), (2, 1), (2, 2)})
        result = relation_closure(matrix)
        self.assertFalse(result['conflict'])
        self.assertEqual(pair_set(result['relations'][0][2]), {(1, 1), (2, 2)})
        self.assertEqual(domains_from_matrix(result['relations']), [[1, 2]] * 3)
        self.check_fixed_point(result['relations'])
        model = self.small['chain']
        anchors = {face[0]: [1, 2] for face in model.plane_map.faces}
        geometric = run_relation_names(model, anchors=anchors)
        self.check_run(model, geometric)
        nonadjacent = next((i, j) for i in range(3) for j in range(i + 1, 3)
                           if (i, j) not in adjacency_edges(model.plane_map))
        i, j = nonadjacent
        self.assertEqual(pair_set(geometric['relations'][i][j]), {(1, 1), (2, 2)})

    def test_three_color_k4_is_nonempty_path_consistent_but_unsatisfiable(self):
        """This is an abstract constraint graph, deliberately not map geometry."""
        edges = [(i, j) for i in range(4) for j in range(i + 1, 4)]
        matrix = domain_matrix([{1, 2, 3}] * 4, edges)
        result = relation_closure(matrix)
        self.assertFalse(result['conflict'])
        self.assertTrue(all(mask for row in result['relations'] for mask in row))
        self.assertEqual(result['relations'], matrix)
        self.assertFalse(any(all(values[a] != values[b] for a, b in edges)
                             for values in product((1, 2, 3), repeat=4)))
        self.check_fixed_point(result['relations'])

    def test_bridges_only_use_diagonal_same_side_relations(self):
        model = self.models['gallery-dangling']
        outcome = run_relation_names(model)
        self.check_run(model, outcome)
        bridge_count = 0
        for edge in range(len(model.plane_map.edges)):
            left, right = model.plane_map.shores(edge)
            if left == right:
                bridge_count += 1
                self.assertTrue(all(a == b for a, b in pair_set(outcome['relations'][left][right])))
        self.assertGreater(bridge_count, 0)

    def test_t_mother_line_profiles_keep_identity_and_reverse_by_transpose(self):
        key = 'L:0,180>900,180'
        profiles = []
        for map_id in ('D-before', 'teaching-D'):
            model = self.models[map_id]
            outcome = run_relation_names(model)
            self.check_run(model, outcome)
            self.assertEqual([item['id'] for item in outcome['profiles']], [line['id'] for line in model.lines])
            profile = next(item for item in outcome['profiles'] if item['id'] == key)
            profiles.append(profile)
            whole = next(line for line in model.lines if line['id'] == key)
            self.assertEqual(len(profile['spans']), len(whole['spans']))
            for span, original in zip(profile['spans'], whole['spans']):
                self.assertEqual(span['dart'], original['dart'])
                self.assertEqual((span['t0'], span['t1']), (original['t0'], original['t1']))
                left, right = span['left_side'], span['right_side']
                listed = {tuple(pair) for pair in span['pairs']}
                self.assertEqual(listed, pair_set(outcome['relations'][left][right]))
                reverse_pairs = {(b, a) for a, b in listed}
                self.assertEqual(reverse_pairs, pair_set(outcome['relations'][right][left]))
                self.assertEqual(transpose(outcome['relations'][left][right]), outcome['relations'][right][left])
        self.assertEqual(len(profiles[0]['spans']), 3)
        self.assertEqual(len(profiles[1]['spans']), 4)

    def test_e_forces_g_one_and_nine_fresh_excludes_unsupported_one(self):
        e_model = self.models['teaching-E']
        e_result = run_relation_names(e_model)
        self.assertEqual(e_result['base']['domains'][9], [1, 3, 4])
        self.assertEqual(e_result['domains'][9], [1])
        self.check_run(e_model, e_result)
        fresh = run_relation_names(self.nine)
        self.assertEqual(fresh['base']['domains'][10], [1, 2, 3, 4])
        self.assertEqual(fresh['domains'][10], [2, 3, 4])
        self.assertEqual(fresh['status'], 'underdetermined')
        self.check_run(self.nine, fresh)

    def test_nine_conditioned_certificate_is_preserved_without_guessing(self):
        anchors = {int(dart): domain for dart, domain in self.proof['same_state']['anchors_by_dart'].items()}
        original = deepcopy(anchors)
        result = run_relation_names(self.nine, anchors=anchors)
        self.check_run(self.nine, result)
        self.assertEqual(result['status'], 'solved')
        self.assertEqual([domain[0] for domain in result['domains']], self.proof['certificate'])
        self.assertEqual(result['choices'], 0)
        self.assertEqual(result['base']['anchors_by_dart'], original)
        self.assertEqual(anchors, original)

    def test_explicit_empty_and_multivalued_anchors_are_honored(self):
        model = self.small['chain']
        empty = run_relation_names(model, anchors={})
        self.assertEqual(empty['base']['anchors_by_dart'], {})
        self.assertEqual(empty['domains'], [list(PALETTE)] * 3)
        self.assertEqual(empty['status'], 'underdetermined')
        anchors = {face[0]: [1, 2] for face in model.plane_map.faces}
        supplied = deepcopy(anchors)
        result = run_relation_names(model, anchors=anchors)
        self.assertEqual(result['base']['anchors_by_dart'], supplied)
        self.assertEqual(result['domains'], [[1, 2]] * 3)
        self.check_run(model, result)
        self.assertEqual(anchors, supplied)

    def test_optional_normalizations_preserve_every_binary_relation_symmetry(self):
        choices = 0
        for key in ('teaching-D', 'teaching-E', 'gallery-tetrahedron', 'gallery-islands', 'remote-after'):
            for policy in ('connections', 'constraints', 'outer-layer'):
                with self.subTest(map=key, policy=policy):
                    model = self.models[key]
                    result = run_relation_names(model, policy=policy, symbol_symmetry=True)
                    self.check_run(model, result)
                    choices += result['choices']
        self.assertGreater(choices, 0)

    def test_binary_asymmetry_blocks_normalization_even_with_invariant_unary_domains(self):
        """Inject a synthetic EXTRA non-edge relation only to audit the guard."""
        model = self.small['two_islands']
        geometry = self.small_geometry['two_islands']
        outer = geometry['outerFace']
        adjacent = adjacency_edges(model.plane_map)
        center = next(side for side in range(4)
                      if sum(side in edge for edge in adjacent) == 3)
        first, second = [side for side in range(4) if side not in (outer, center)]
        self.assertNotIn(tuple(sorted((first, second))), adjacent)
        domains = [[3, 4] for _ in range(4)]
        domains[outer], domains[center] = [1], [2]
        anchors = {model.plane_map.faces[side][0]: domain for side, domain in enumerate(domains)}
        matrix = initial_relations(model, domains)
        # The extra allowed-pair restriction is NOT implied by this drawing.
        # It is a deliberately synthetic compatibility input for this guard test.
        matrix[first][second] &= ~mask_of([(4, 3)])
        matrix[second][first] = transpose(matrix[first][second])
        strict = relation_closure(matrix)
        self.assertFalse(strict['conflict'])
        self.assertEqual(domains_from_matrix(strict['relations']), domains)
        swapped = {(7 - a, 7 - b) for a, b in pair_set(strict['relations'][first][second])}
        self.assertNotEqual(swapped, pair_set(strict['relations'][first][second]))
        with patch('fourcolor.relation_names.initial_relations', return_value=deepcopy(matrix)):
            result = run_relation_names(model, anchors=anchors, symbol_symmetry=True)
        self.assertEqual(result['status'], 'underdetermined')
        self.assertEqual(result['domains'], domains)
        self.assertEqual(result['normalizations'], [])
        self.assertEqual(result['choices'], 0)

    def test_invalid_matrices_are_rejected_and_empty_relations_are_conflicts(self):
        asymmetric = [[mask_of([(1, 1)]), mask_of([(1, 2)])],
                      [mask_of([(1, 2)]), mask_of([(2, 2)])]]
        invalid = ([], [[]], [[1, 2]], [[True]], [[1.0]], [[-1]], [[65536]],
                   [[mask_of([(1, 2)])]], asymmetric)
        for matrix in invalid:
            with self.subTest(matrix=matrix), self.assertRaises(ValueError):
                relation_closure(matrix)
        empty = relation_closure([[0]])
        self.assertTrue(empty['conflict'])
        self.assertEqual(empty['relations'], [[0]])
        self.assertEqual(empty['trace'], [])
        # A pair can be incompatible with its diagonal domains even if its
        # own mask is nonzero; repeated-index projection must discover this.
        unsupported = [[mask_of([(1, 1)]), mask_of([(2, 2)])],
                       [mask_of([(2, 2)]), mask_of([(2, 2)])]]
        self.assertTrue(relation_closure(unsupported)['conflict'])


if __name__ == '__main__':
    unittest.main()

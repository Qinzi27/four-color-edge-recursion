"""Soundness and fixed-point tests for whole-line joint candidate filtering.

Tiny assignment enumeration is an independent test oracle only. The production
rule is not given oracle completions, and an unresolved domain is never counted
as a coloring. All source/target relations are checked through genuine primal
separators, not point contact or visual proximity.
"""
from __future__ import annotations

from copy import deepcopy
from collections import deque
from itertools import permutations, product
import json
from pathlib import Path
import random
import subprocess
import unittest

from fourcolor.embedding import PlaneMap
from fourcolor.joint_lines import run_joint_lines
from fourcolor.line_names import audit_line_names
from fourcolor.whole_lines import build_whole_lines
from scripts.validate_joint_lines import independent_check

ROOT = Path(__file__).resolve().parents[1]
POLICIES = ('connections', 'constraints', 'outer-layer')
PALETTE = frozenset((1, 2, 3, 4))


def adjacency(plane):
    """Recover true side adjacency, omitting every same-side bridge."""
    neighbors = [set() for _ in plane.faces]
    for edge in range(len(plane.edges)):
        left, right = plane.shores(edge)
        if left != right:
            neighbors[left].add(right)
            neighbors[right].add(left)
    return neighbors


def anchored_domains(model, anchors):
    """Independently intersect all supplied dart occurrences of one side."""
    domains = [set(PALETTE) for _ in model.plane_map.faces]
    for dart, domain in anchors.items():
        domains[model.plane_map.face_of_dart[dart]].intersection_update(domain)
    return domains


def domain_anchors(model, domains):
    """Supply one explicit occurrence per side, including multivalued domains."""
    return {model.plane_map.faces[side][0]: sorted(domain) for side, domain in enumerate(domains)}


def simultaneous_closure(plane, domains):
    """Apply sound deletion rules in simultaneous rounds, without line priority."""
    neighbors = adjacency(plane)
    current = [set(domain) for domain in domains]
    while all(current):
        following = [set(domain) for domain in current]
        for source, domain in enumerate(current):
            if len(domain) == 1:
                for target in neighbors[source]:
                    following[target].difference_update(domain)
            for second in neighbors[source]:
                if source >= second:
                    continue
                occupied = domain | current[second]
                if len(occupied) == 2:
                    for target in neighbors[source] & neighbors[second]:
                        following[target].difference_update(occupied)
        if following == current:
            return current
        current = following
    return current


class JointLineTests(unittest.TestCase):
    """Separate conditional repair, complete restart and optional name symmetry."""

    @classmethod
    def setUpClass(cls):
        """Load pure geometry and fixed evidence without writing output files."""
        result = subprocess.run(['node', 'scripts/whole-line-fixtures.mjs', '--emit'], cwd=ROOT,
                                capture_output=True, text=True, encoding='utf-8', check=True)
        cls.records = {row['id']: row for row in json.loads(result.stdout)['records']}
        cls.models = {key: build_whole_lines(row['geometry']) for key, row in cls.records.items()}
        cls.proof = json.loads((ROOT / 'outputs/weighted-counterexample-candidate-2026-09-18-v2.json')
                              .read_text(encoding='utf-8'))['proof']
        cls.nine = build_whole_lines(cls.proof['geometry'])
        program = r'''
import {buildMap} from './web/engine.js';
const ring = [[300,200],[600,200],[600,400],[300,400]];
const inputs = {
  triangle: [{a:[450,0],b:[450,600]}],
  chain: ring.map((a,i)=>({a,b:ring[(i+1)%ring.length]})),
  bridge: [{a:[0,300],b:[200,300]}],
};
console.log(JSON.stringify(Object.fromEntries(Object.entries(inputs).map(([key,strokes]) => {
 const m=buildMap({strokes});
 return [key,{vertices:m.vertices,edges:m.edges,rotation:m.rotation,
   faceOfDart:m.faceOfDart,faces:m.faces.map(f=>f.darts),outerFace:m.outerFace,original:m.original}];
}))));
'''
        small = subprocess.run(['node', '--input-type=module', '-e', program], cwd=ROOT,
                               capture_output=True, text=True, encoding='utf-8', check=True)
        cls.small_geometry = json.loads(small.stdout)
        cls.small = {key: build_whole_lines(value) for key, value in cls.small_geometry.items()}

    def check_complete(self, model, outcome):
        """Validate a claimed solution independently of the joint rule."""
        self.assertEqual(outcome['status'], 'solved')
        self.assertTrue(all(len(domain) == 1 for domain in outcome['domains']))
        colors = [domain[0] for domain in outcome['domains']]
        plane = model.plane_map
        oracle = PlaneMap(plane.edges, plane.rotation)
        self.assertTrue(oracle.check_coloring([color - 1 for color in colors]))
        pairs = tuple((str(colors[left]), str(colors[right])) for left, right in
                      (oracle.shores(edge) for edge in range(len(oracle.edges))))
        self.assertEqual(audit_line_names(tuple(oracle.rotation.values()), pairs).status, 'consistent')

    def check_trace(self, model, outcome):
        """Replay sound premises, exact deletions and fair highest-dirty scheduling."""
        plane = model.plane_map
        domains = anchored_domains(model, outcome['anchors_by_dart'])
        self.assertEqual(outcome['initial_domains'], [sorted(domain) for domain in domains])
        neighbors = adjacency(plane)
        order = [line['id'] for line in model.lines]
        contacts = {line: set() for line in order}
        for turn in plane.rotation.values():
            incident = {model.edge_owner[dart // 2] for dart in turn if dart // 2 in model.edge_owner}
            for line in incident:
                contacts[line].update(incident - {line})
        sides = {line['id']: {plane.face_of_dart[dart]
                             for span in line['spans'] for dart in (span['dart'], span['dart'] ^ 1)}
                 for line in model.lines}
        depths, queue = {'frame': 0}, deque(['frame'])
        while queue:
            source = queue.popleft()
            for other in contacts[source]:
                if other not in depths:
                    depths[other] = depths[source] + 1
                    queue.append(other)
        dirty = set(order)
        rng = random.Random(outcome['seed'])
        cursor = random_draws = symmetry_choices = 0
        for scheduled in outcome['schedule']:
            self.assertTrue(all(domains), 'No constraint may run after a recorded empty domain')
            self.assertEqual(scheduled['trace_start'], cursor)
            symmetric = scheduled.get('phase') == 'symbol-symmetry'
            if symmetric:
                self.assertFalse(dirty, 'Symmetry must wait for the complete strict fixed point')
                self.assertEqual(simultaneous_closure(plane, domains), domains)
                used = {next(iter(domain)) for domain in domains if len(domain) == 1}
                unused = PALETTE - used
                candidates = {line for line in order if any(domains[side] == unused for side in sides[line])}
            else:
                candidates = dirty
            weights = {}
            for line in order:
                if line not in candidates:
                    continue
                if outcome['policy'] == 'connections':
                    weight = len(contacts[line])
                elif outcome['policy'] == 'constraints':
                    weight = sum(4 - len(domains[side]) for side in sides[line] if len(domains[side]) > 1)
                else:
                    weight = -depths[line] if line in depths else -len(order)
                weights[line] = weight
            highest = max(weights.values())
            ties = [line for line, weight in weights.items() if weight == highest]
            self.assertEqual(scheduled['weight'], highest)
            self.assertEqual(scheduled['tied_lines'], ties)
            if outcome['tie_break'] == 'reverse':
                chosen = ties[-1]
            elif outcome['tie_break'] == 'random' and len(ties) > 1:
                chosen = rng.choice(ties)
                random_draws += 1
            else:
                chosen = ties[0]
            self.assertEqual(scheduled['line'], chosen)
            if not symmetric:
                dirty.remove(chosen)
            for event in outcome['trace'][cursor:scheduled['trace_end']]:
                self.assertTrue(all(domains))
                self.assertEqual(event['line'], chosen)
                target, sources = event['target'], event['sources']
                self.assertEqual(event['before'], sorted(domains[target]))
                self.assertEqual(event['source_domains'], [sorted(domains[source]) for source in sources])
                witness_pairs = []
                for edge in event['witness_edges']:
                    left, right = plane.shores(edge)
                    self.assertNotEqual(left, right)
                    self.assertIn(edge, model.edge_owner)
                    witness_pairs.append(frozenset((left, right)))
                if event['rule'] == 'singleton':
                    self.assertFalse(symmetric)
                    self.assertEqual(len(sources), 1)
                    source = sources[0]
                    self.assertEqual(len(domains[source]), 1)
                    self.assertIn(target, neighbors[source])
                    self.assertEqual(witness_pairs, [frozenset((source, target))])
                    removable = domains[target] & domains[source]
                elif event['rule'] == 'pair-occupancy':
                    self.assertFalse(symmetric)
                    self.assertEqual(len(sources), 2)
                    first, second = sources
                    self.assertIn(second, neighbors[first])
                    self.assertIn(target, neighbors[first] & neighbors[second])
                    occupied = domains[first] | domains[second]
                    self.assertEqual(len(occupied), 2)
                    self.assertEqual(witness_pairs, [frozenset((first, second)),
                                                    frozenset((first, target)), frozenset((second, target))])
                    removable = domains[target] & occupied
                else:
                    self.assertEqual(event['rule'], 'symbol-symmetry')
                    self.assertTrue(symmetric)
                    self.assertTrue(outcome['symbol_symmetry'])
                    self.assertEqual(sources, [])
                    self.assertEqual(witness_pairs, [])
                    used = {next(iter(domain)) for domain in domains if len(domain) == 1}
                    unused = PALETTE - used
                    self.assertGreater(len(unused), 1)
                    self.assertEqual(event['used'], sorted(used))
                    self.assertEqual(event['unused'], sorted(unused))
                    self.assertEqual(domains[target], unused)
                    # Explicitly test every unused-symbol permutation on EVERY
                    # domain, not just equality at the selected target shore.
                    for permutation in permutations(sorted(unused)):
                        renaming = dict(zip(sorted(unused), permutation))
                        self.assertTrue(all({renaming.get(value, value) for value in domain} == domain
                                            for domain in domains))
                    self.assertEqual(event['canonical_symbol'], min(unused))
                    self.assertEqual(plane.face_of_dart[event['dart']], target)
                    self.assertEqual(model.edge_owner[event['dart'] // 2], chosen)
                    removable = unused - {min(unused)}
                    symmetry_choices += 1
                self.assertTrue(removable)
                self.assertEqual(event['removed'], sorted(removable))
                if event['witness_edges']:
                    self.assertEqual(model.edge_owner[event['witness_edges'][0]], chosen)
                domains[target].difference_update(removable)
                self.assertEqual(event['after'], sorted(domains[target]))
            if scheduled['trace_end'] > cursor:
                dirty = set(order)
            cursor = scheduled['trace_end']
        self.assertEqual(cursor, len(outcome['trace']))
        self.assertEqual(outcome['domains'], [sorted(domain) for domain in domains])
        self.assertEqual(outcome['choices'], symmetry_choices)
        self.assertEqual(outcome['symmetry_choices'], symmetry_choices)
        self.assertEqual(outcome['non_symmetry_choices'], 0)
        self.assertEqual(outcome['backtracks'], 0)
        self.assertEqual(outcome['random_draws'], random_draws)
        self.assertEqual(outcome['removed_candidates'], sum(len(event['removed']) for event in outcome['trace']))
        if outcome['status'] != 'conflict':
            self.assertFalse(dirty)
            self.assertEqual(simultaneous_closure(plane, domains), domains)

    def test_nine_line_same_state_repair_matches_supplied_certificate(self):
        """Reuse the exact nine-line common state, not its 24-line ancestor."""
        self.assertEqual(len(self.proof['document']['strokes']), 9)
        anchors = {int(dart): values for dart, values in self.proof['same_state']['anchors_by_dart'].items()}
        original = deepcopy(anchors)
        for policy in POLICIES:
            for tie in ('forward', 'reverse', 'random'):
                with self.subTest(policy=policy, tie=tie):
                    result = run_joint_lines(self.nine, policy=policy, tie_break=tie,
                                             seed=20260918 if tie == 'random' else None,
                                             anchors=anchors)
                    self.check_complete(self.nine, result)
                    self.check_trace(self.nine, result)
                    self.assertEqual([domain[0] for domain in result['domains']], self.proof['certificate'])
                    self.assertEqual(result['anchors_by_dart'], original)
                    self.assertEqual(result['non_symmetry_choices'], 0)
                    self.assertEqual(result['choices'], 0)
                    self.assertEqual(result['backtracks'], 0)
                    self.assertTrue(any(event['rule'] == 'pair-occupancy' for event in result['trace']))
        self.assertEqual(anchors, original)

    def test_nine_line_fresh_restart_is_not_the_conditional_repair(self):
        """Starting only from frame anchors must not import the saved old names."""
        result = run_joint_lines(self.nine)
        self.check_trace(self.nine, result)
        first = next(line for line in self.nine.lines if line['id'] == 'frame')['spans'][0]['dart']
        expected = {first: [1], first ^ 1: [2]}
        self.assertEqual(result['anchors_by_dart'], expected)
        self.assertEqual(result['choices'], 0)
        self.assertEqual(result['non_symmetry_choices'], 0)
        closure = simultaneous_closure(self.nine.plane_map, anchored_domains(self.nine, expected))
        self.assertEqual(result['domains'], [sorted(domain) for domain in closure])
        self.assertNotEqual(result['anchors_by_dart'], self.proof['same_state']['anchors_by_dart'])
        if result['status'] == 'solved':
            self.check_complete(self.nine, result)
        else:
            self.assertEqual(result['status'], 'underdetermined')
            self.assertTrue(any(len(domain) > 1 for domain in result['domains']))

    def test_nonadjacent_pair_cannot_delete_from_its_common_neighbor(self):
        """G--H--J permits G and J to share a name; they do not occupy two."""
        model = self.small['chain']
        neighbors = adjacency(model.plane_map)
        middle = next(side for side, row in enumerate(neighbors) if len(row) == 2)
        first, second = sorted(neighbors[middle])
        self.assertNotIn(second, neighbors[first])
        domains = [set(PALETTE) for _ in neighbors]
        domains[first] = domains[second] = {1, 2}
        result = run_joint_lines(model, anchors=domain_anchors(model, domains))
        self.assertEqual(result['domains'], [sorted(domain) for domain in domains])
        self.assertEqual(result['domains'][middle], [1, 2, 3, 4])
        self.assertEqual(result['status'], 'underdetermined')
        self.assertEqual(result['trace'], [])

    def test_pair_occupancy_and_singleton_rules_on_tiny_exhaustive_domains(self):
        """All 3375 three-side nonempty domains preserve every legal completion."""
        model = self.small['triangle']
        plane = model.plane_map
        self.assertEqual(len(plane.faces), 3)
        self.assertTrue(all(len(row) == 2 for row in adjacency(plane)))
        subsets = [set(color for color in PALETTE if mask & (1 << (color - 1))) for mask in range(1, 16)]
        full_solutions = list(permutations(sorted(PALETTE), 3))
        pair_events = singleton_events = 0
        for domains in product(subsets, repeat=3):
            anchors = domain_anchors(model, domains)
            result = run_joint_lines(model, anchors=anchors)
            solutions = [values for values in full_solutions
                         if all(value in domain for value, domain in zip(values, domains))]
            if solutions:
                self.assertNotEqual(result['status'], 'conflict', msg=str(domains))
                for values in solutions:
                    self.assertTrue(all(value in domain for value, domain in zip(values, result['domains'])))
            if result['status'] == 'solved':
                self.check_complete(model, result)
            closure = simultaneous_closure(plane, domains)
            if all(closure):
                self.assertEqual(result['domains'], [sorted(domain) for domain in closure])
            else:
                self.assertEqual(result['status'], 'conflict')
            self.assertEqual(result['choices'], 0)
            pair_events += sum(event['rule'] == 'pair-occupancy' for event in result['trace'])
            singleton_events += sum(event['rule'] == 'singleton' for event in result['trace'])
        self.assertGreater(pair_events, 0)
        self.assertGreater(singleton_events, 0)

    def test_two_fixed_distinct_sources_still_filter_their_common_neighbor(self):
        """A source line with no unresolved shore must still be scheduled."""
        model = self.small['triangle']
        domains = [{1}, {2}, set(PALETTE)]
        result = run_joint_lines(model, policy='constraints', anchors=domain_anchors(model, domains))
        self.assertEqual(result['domains'], [[1], [2], [3, 4]])
        self.assertEqual(result['status'], 'underdetermined')

    def test_bridge_same_side_is_not_an_inequality_or_pair_source(self):
        model = self.small['bridge']
        bridges = [edge for edge in range(len(model.plane_map.edges))
                   if model.plane_map.shores(edge)[0] == model.plane_map.shores(edge)[1]]
        self.assertTrue(bridges)
        result = run_joint_lines(model)
        self.check_complete(model, result)
        for event in result['trace']:
            self.assertTrue(all(edge not in bridges for edge in event['witness_edges']))
        self.assertEqual(result['choices'], 0)

    def test_none_and_empty_anchors_have_different_documented_meanings(self):
        model = self.small['triangle']
        unanchored = run_joint_lines(model, anchors={})
        self.assertEqual(unanchored['anchors_by_dart'], {})
        self.assertEqual(unanchored['domains'], [[1, 2, 3, 4]] * len(model.plane_map.faces))
        self.assertEqual(unanchored['trace'], [])
        self.assertEqual(unanchored['status'], 'underdetermined')
        anchored = run_joint_lines(model, anchors=None)
        self.assertEqual(len(anchored['anchors_by_dart']), 2)
        self.assertNotEqual(anchored['domains'], unanchored['domains'])

    def test_empty_domain_and_same_side_inconsistent_anchors_report_conflict(self):
        model = self.small['triangle']
        first, second = model.plane_map.faces[0][:2]
        for anchors in ({first: []}, {first: [1], second: [2]}):
            result = run_joint_lines(model, anchors=anchors)
            self.assertEqual(result['status'], 'conflict')
            self.assertTrue(any(not domain for domain in result['domains']))
            self.assertEqual(result['choices'], 0)

    def test_strict_fixed_point_is_independent_of_scheduling_order(self):
        """Compare a representative corpus against simultaneous rule closure."""
        selected = list(self.records)[:15] + ['guillotine-20260916', 'guillotine-20260927',
            'guillotine-20261001', 'nested-rings-and-bridges-20261068',
            'boundary-fan-20261108', 'remote-before', 'remote-after']
        for key in selected:
            model = self.models[key]
            first = next(line for line in model.lines if line['id'] == 'frame')['spans'][0]['dart']
            anchors = {first: [1], first ^ 1: [2]}
            closure = simultaneous_closure(model.plane_map, anchored_domains(model, anchors))
            self.assertTrue(all(closure))
            expected = [sorted(domain) for domain in closure]
            for policy in POLICIES:
                for tie in ('forward', 'reverse', 'random'):
                    with self.subTest(map=key, policy=policy, tie=tie):
                        outcome = run_joint_lines(model, policy=policy, tie_break=tie,
                                                  seed=314159 if tie == 'random' else None)
                        self.assertEqual(outcome['domains'], expected)
                        self.check_trace(model, outcome)
                        self.assertEqual(outcome['choices'], 0)
                        self.assertEqual(outcome['non_symmetry_choices'], 0)
                        self.assertEqual(outcome['backtracks'], 0)
                        if outcome['status'] == 'solved':
                            self.check_complete(model, outcome)

    def test_symmetry_is_blocked_by_any_asymmetric_domain(self):
        """A full-unused target is insufficient when another domain distinguishes names."""
        model = self.small['triangle']
        domains = [set(PALETTE), {1, 2}, set(PALETTE)]
        result = run_joint_lines(model, anchors=domain_anchors(model, domains), symbol_symmetry=True)
        self.assertEqual(result['domains'], [sorted(domain) for domain in domains])
        self.assertEqual(result['status'], 'underdetermined')
        self.assertEqual(result['symmetry_choices'], 0)
        self.assertFalse(any(event['rule'] == 'symbol-symmetry' for event in result['trace']))
        self.check_trace(model, result)

    def test_optional_safe_symmetry_is_separate_and_globally_valid(self):
        """All optional choices are checked as name-permutation representatives."""
        selected = ['gallery-grid', 'gallery-islands', 'gallery-dangling', 'teaching-D',
                    'teaching-E', 'remote-before', 'remote-after', 'guillotine-20260916']
        choices = 0
        for key in selected:
            model = self.models[key]
            for tie in ('forward', 'reverse', 'random'):
                with self.subTest(map=key, tie=tie):
                    result = run_joint_lines(model, tie_break=tie,
                                             seed=20260918 if tie == 'random' else None,
                                             symbol_symmetry=True)
                    self.check_trace(model, result)
                    choices += result['symmetry_choices']
                    if result['status'] == 'solved':
                        self.check_complete(model, result)
        self.assertGreater(choices, 0)
        simple = run_joint_lines(self.small['triangle'], symbol_symmetry=True)
        self.check_complete(self.small['triangle'], simple)
        self.check_trace(self.small['triangle'], simple)
        self.assertEqual(simple['symmetry_choices'], 1)

    def test_inputs_and_random_seed_validation(self):
        model = self.small['triangle']
        for kwargs in ({'policy': 'unknown'}, {'tie_break': 'unknown'},
                       {'tie_break': 'random'}, {'tie_break': 'random', 'seed': True},
                       {'symbol_symmetry': 1}, {'anchors': []},
                       {'anchors': {True: [1]}}, {'anchors': {-1: [1]}},
                       {'anchors': {0: [True]}}, {'anchors': {0: [5]}}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                run_joint_lines(model, **kwargs)
        first = run_joint_lines(self.nine, tie_break='random', seed=314159, symbol_symmetry=True)
        self.assertEqual(first, run_joint_lines(self.nine, tie_break='random', seed=314159, symbol_symmetry=True))

    def test_remote_six_side_oracle_preserves_strict_solutions_and_symmetry_existence(self):
        """Bounded TEST-ONLY enumeration independently audits 24 domain fixtures."""
        model = self.models['remote-after']
        plane = model.plane_map
        self.assertEqual(len(plane.faces), 6)
        # Enumerate once for this tiny map; no completion is fed to the rule.
        solutions = [values for values in product(sorted(PALETTE), repeat=6)
                     if plane.check_coloring([value - 1 for value in values])]
        self.assertTrue(solutions)
        rng = random.Random(20260918)
        domains_list = [[set(PALETTE) for _ in range(6)]]
        contradictory = [set(PALETTE) for _ in range(6)]
        left, right = next(plane.shores(edge) for edge in range(len(plane.edges))
                           if plane.shores(edge)[0] != plane.shores(edge)[1])
        contradictory[left] = contradictory[right] = {1}
        domains_list.append(contradictory)
        for _ in range(11):
            certificate = rng.choice(solutions)
            domains_list.append([{value} | {other for other in PALETTE if rng.random() < 0.45}
                                 for value in certificate])
        for _ in range(11):
            domains_list.append([{value for value in PALETTE if mask & (1 << (value - 1))}
                                 for mask in [rng.randrange(1, 16) for _ in range(6)]])
        self.assertEqual(len(domains_list), 24)
        satisfiable = unsatisfiable = 0
        for index, domains in enumerate(domains_list):
            before = {values for values in solutions if all(value in domain for value, domain in zip(values, domains))}
            satisfiable += bool(before)
            unsatisfiable += not before
            for policy in POLICIES:
                for symmetry in (False, True):
                    with self.subTest(fixture=index, policy=policy, symmetry=symmetry):
                        outcome = run_joint_lines(model, policy=policy, anchors=domain_anchors(model, domains),
                                                  symbol_symmetry=symmetry)
                        after = {values for values in solutions if all(
                            value in domain for value, domain in zip(values, outcome['domains']))}
                        self.assertEqual(bool(after), bool(before))
                        if not symmetry:
                            self.assertEqual(after, before, 'Strict deductions must preserve every labeled completion')
                        self.check_trace(model, outcome)
                        if outcome['status'] == 'solved':
                            self.check_complete(model, outcome)
        self.assertGreater(satisfiable, 0)
        self.assertGreater(unsatisfiable, 0)

    def test_independent_report_auditor_rejects_tampered_removal_proofs(self):
        """Changed premises, fabricated deletions and missing proof steps fail."""
        anchors = {int(dart): values for dart, values in self.proof['same_state']['anchors_by_dart'].items()}
        valid = run_joint_lines(self.nine, anchors=anchors)
        self.assertTrue(independent_check(self.proof['geometry'], valid))
        altered = deepcopy(valid)
        event = next(event for event in altered['trace'] if event['rule'] == 'pair-occupancy')
        event['removed'] = []
        bad_premise = deepcopy(valid)
        event = next(event for event in bad_premise['trace'] if event['rule'] == 'pair-occupancy')
        event['source_domains'][0] = []
        missing = deepcopy(valid)
        missing['trace'].pop()
        for description, result in (('empty removal', altered), ('false premise', bad_premise),
                                    ('missing step', missing)):
            with self.subTest(tamper=description), self.assertRaises(AssertionError):
                independent_check(self.proof['geometry'], result)


if __name__ == '__main__':
    unittest.main()

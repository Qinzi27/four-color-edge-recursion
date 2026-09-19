"""Independent trace replay for greedy, highest-weight WHOLE-line scheduling.

Weights are recomputed from geometric junction incidence and current domains,
without importing the implementation's metadata or priority helper. Complete
certificates are checked separately; retained conflicts are not solver failures
to be concealed by retrying another line or another symbol.
"""
from __future__ import annotations

from collections import deque
import json
from pathlib import Path
import random
import subprocess
import unittest

from fourcolor.embedding import PlaneMap
from fourcolor.line_names import audit_line_names
from fourcolor.whole_lines import build_whole_lines, propagate_candidates
from fourcolor.weighted_lines import POLICIES, run_weighted_lines

ROOT = Path(__file__).resolve().parents[1]


def metadata_oracle(model, geometry):
    """Derive whole-line contacts from vertex incidence, not saved line events."""
    order = [line['id'] for line in model.lines]
    contacts = {identifier: set() for identifier in order}
    for rotation in geometry['rotation']:
        lines = {model.edge_owner[dart // 2] for dart in rotation if dart // 2 in model.edge_owner}
        for identifier in lines:
            contacts[identifier].update(lines - {identifier})
    occurrences = {}
    for line in model.lines:
        seen, ordered = set(), []
        for span in line['spans']:
            for dart in (span['dart'], span['dart'] ^ 1):
                side = model.plane_map.face_of_dart[dart]
                if side not in seen:
                    seen.add(side)
                    ordered.append((side, dart))
        occurrences[line['id']] = ordered
    depths = {'frame': 0}
    queue = deque(['frame'])
    while queue:
        identifier = queue.popleft()
        for other in contacts[identifier]:
            if other not in depths:
                depths[other] = depths[identifier] + 1
                queue.append(other)
    return order, contacts, occurrences, depths


def weights_oracle(metadata, domains, policy):
    """Count distinct unknown sides once per line, independent of span count."""
    order, contacts, occurrences, depths = metadata
    weights = {}
    for identifier in order:
        unknown = {side for side, _ in occurrences[identifier] if len(domains[side]) > 1}
        if not unknown:
            continue
        if policy == 'connections':
            weights[identifier] = len(contacts[identifier])
        elif policy == 'constraints':
            weights[identifier] = sum(4 - len(domains[side]) for side in unknown)
        elif policy == 'outer-layer':
            weights[identifier] = -depths[identifier] if identifier in depths else -len(order)
        else:
            raise AssertionError('Unexpected test policy')
    return weights


def profile_signature(model, domains):
    """Compare geometric shore domains while ignoring harmless degree-2 cuts."""
    result = []
    for line in model.lines:
        spans = []
        for span in line['spans']:
            pair = (tuple(domains[span['left_side']]), tuple(domains[span['right_side']]))
            start, end = round(span['t0'], 10), round(span['t1'], 10)
            if spans and spans[-1][2] == pair and spans[-1][1] == start:
                spans[-1] = (spans[-1][0], end, pair)
            else:
                spans.append((start, end, pair))
        result.append((line['id'], tuple(spans)))
    return tuple(result)


class WeightedLineTests(unittest.TestCase):
    """Review both chosen order and irreversible within-line symbol decisions."""

    @classmethod
    def setUpClass(cls):
        """Generate one fixed corpus and three representation-only transforms."""
        fixture = subprocess.run(['node', 'scripts/whole-line-fixtures.mjs', '--emit'],
                                 cwd=ROOT, capture_output=True, text=True, encoding='utf-8', check=True)
        cls.records = {row['id']: row for row in json.loads(fixture.stdout)['records']}
        cls.models = {key: build_whole_lines(row['geometry']) for key, row in cls.records.items()}
        cls.metadata = {key: metadata_oracle(cls.models[key], row['geometry'])
                        for key, row in cls.records.items()}
        # Rebuild equal geometry through the actual input layer; no named state
        # or coloring routine is imported or used by this fixture transformation.
        program = r'''
import {wholeLineFixtures} from './scripts/whole-line-fixtures.mjs';
import {buildMap} from './web/engine.js';
const selected = new Set(['gallery-grid', 'teaching-D', 'remote-after']);
const rows = wholeLineFixtures().records.filter(row => selected.has(row.id)).map(row => {
  const doc = row.document;
  const docs = {
    reordered: {...doc, strokes: [...doc.strokes].reverse()},
    reversed: {...doc, strokes: doc.strokes.map(s => ({a:s.b,b:s.a}))},
    subdivided: {...doc, strokes: doc.strokes.flatMap(s => {
      const m=s.a.map((x,i)=>(x+s.b[i])/2); return [{a:s.a,b:m},{a:m,b:s.b}];
    })},
  };
  return {id:row.id, variants:Object.fromEntries(Object.entries(docs).map(([name,input]) => {
    const m=buildMap(input);
    return [name,{vertices:m.vertices,edges:m.edges,rotation:m.rotation,
      faceOfDart:m.faceOfDart,faces:m.faces.map(f=>f.darts),outerFace:m.outerFace,original:m.original}];
  }))};
});
console.log(JSON.stringify(rows));
'''
        variants = subprocess.run(['node', '--input-type=module', '-e', program], cwd=ROOT,
                                  capture_output=True, text=True, encoding='utf-8', check=True)
        cls.variants = json.loads(variants.stdout)

    def check_trace(self, key, outcome, forced_prefix=()):
        """Replay every decision and independently check line priority and RNG."""
        model, geometry = self.models[key], self.records[key]['geometry']
        metadata = self.metadata[key]
        _, _, occurrences, _ = metadata
        frame = next(line for line in model.lines if line['id'] == 'frame')
        first = frame['spans'][0]['dart']
        anchors = {first: [1], first ^ 1: [2]}
        state = propagate_candidates(model, anchors)
        rng = random.Random(outcome['seed'])
        random_draws = choices = non_symmetry = 0
        visited = set()
        for index, step in enumerate(outcome['trace']):
            self.assertEqual(state['status'], 'underdetermined')
            weights = weights_oracle(metadata, state['domains'], outcome['policy'])
            highest = max(weights.values())
            ties = [identifier for identifier, weight in weights.items() if weight == highest]
            self.assertEqual(step['weight'], highest)
            self.assertEqual(step['tied_lines'], ties)
            self.assertEqual(len(ties), len(set(ties)))
            self.assertIn(step['line'], ties)
            if index < len(forced_prefix):
                expected_line = forced_prefix[index]
            elif len(ties) == 1 or outcome['tie_break'] == 'forward':
                expected_line = ties[0]
            elif outcome['tie_break'] == 'reverse':
                expected_line = ties[-1]
            else:
                expected_line = rng.choice(ties)
                random_draws += 1
            self.assertEqual(step['line'], expected_line)
            self.assertNotIn(step['line'], visited)
            visited.add(step['line'])
            decision_index = 0
            for side, dart in occurrences[step['line']]:
                domain = state['domains'][side]
                if len(domain) <= 1:
                    continue
                self.assertLess(decision_index, len(step['decisions']))
                decision = step['decisions'][decision_index]
                used = {row[0] for row in state['domains'] if len(row) == 1}
                symmetry = set(domain) == {1, 2, 3, 4} - used
                self.assertEqual(decision, {'dart': dart, 'side': side, 'domain': domain,
                                           'symbol': min(domain), 'symmetry_only': symmetry})
                self.assertEqual(model.edge_owner[dart // 2], step['line'])
                anchors[dart] = [min(domain)]
                state = propagate_candidates(model, anchors)
                choices += 1
                non_symmetry += not symmetry
                decision_index += 1
                if state['status'] == 'conflict':
                    self.assertEqual(index, len(outcome['trace']) - 1)
                    break
            # A new scheduler step cannot interrupt the chosen whole line's
            # remaining unresolved profile, even if it crosses a T/X junction.
            self.assertEqual(decision_index, len(step['decisions']))
            self.assertGreater(decision_index, 0)
            if state['status'] != 'conflict':
                self.assertTrue(all(len(state['domains'][side]) == 1
                                    for side, _ in occurrences[step['line']]))
        self.assertEqual(outcome['anchors_by_dart'], anchors)
        self.assertEqual(outcome['status'], state['status'])
        self.assertEqual(outcome['domains'], state['domains'])
        self.assertIn(outcome['status'], ('solved', 'conflict'))
        self.assertEqual(outcome['choices'], choices)
        self.assertEqual(outcome['non_symmetry_choices'], non_symmetry)
        self.assertEqual(outcome['random_draws'], random_draws)
        self.assertEqual(outcome['backtracks'], 0)
        self.assertTrue(all(set(domain) <= {1, 2, 3, 4} for domain in outcome['domains']))
        if outcome['status'] == 'conflict':
            self.assertTrue(any(not domain for domain in state['domains']))
            self.assertEqual(outcome['conflict_propagation'], state['trace'])
            self.assertTrue(outcome['conflict_propagation'])
        else:
            self.assertEqual(outcome['conflict_propagation'], [])
            colors = [domain[0] for domain in state['domains']]
            oracle = PlaneMap(tuple((str(e['a']), str(e['b'])) for e in geometry['edges']),
                              {str(i): tuple(row) for i, row in enumerate(geometry['rotation'])})
            self.assertTrue(oracle.check_coloring([color - 1 for color in colors]))
            names = tuple((str(colors[left]), str(colors[right])) for left, right in
                          (oracle.shores(edge) for edge in range(len(oracle.edges))))
            self.assertEqual(audit_line_names(tuple(oracle.rotation.values()), names).status, 'consistent')
        return state

    def test_three_policies_both_fixed_tie_directions_all_255_maps(self):
        """Check all 1530 fixed-policy runs without omitting unsuccessful runs."""
        self.assertEqual(len(self.models), 255)
        self.assertEqual(POLICIES, ('connections', 'constraints', 'outer-layer'))
        conflicts = 0
        for key, model in self.models.items():
            for policy in POLICIES:
                for direction in ('forward', 'reverse'):
                    with self.subTest(map=key, policy=policy, direction=direction):
                        outcome = run_weighted_lines(model, policy, direction)
                        self.check_trace(key, outcome)
                        conflicts += outcome['status'] == 'conflict'
        self.assertGreater(conflicts, 0, 'The corpus must exercise retained conflicts, not only easy maps')

    def test_randomness_only_breaks_highest_weight_line_ties(self):
        """An independent seeded Random must consume exactly the same tie draws."""
        draws = 0
        for key, model in self.models.items():
            for policy in POLICIES:
                with self.subTest(map=key, policy=policy):
                    outcome = run_weighted_lines(model, policy, 'random', seed=20260918)
                    self.check_trace(key, outcome)
                    draws += outcome['random_draws']
        self.assertGreater(draws, 0)

    def test_same_state_highest_tie_can_solve_or_conflict(self):
        """A priority tie is not automatically an interchangeable safe choice."""
        key = 'guillotine-20260916'
        model = self.models[key]
        horizontal = 'L:0,326>900,326'
        vertical = 'L:722,110>722,326'
        failed = run_weighted_lines(model, 'constraints', forced_prefix=('frame', horizontal))
        solved = run_weighted_lines(model, 'constraints', forced_prefix=('frame', vertical))
        self.check_trace(key, failed, ('frame', horizontal))
        self.check_trace(key, solved, ('frame', vertical))
        self.assertEqual(failed['trace'][0], solved['trace'][0])
        for outcome in (failed, solved):
            self.assertEqual(outcome['trace'][1]['weight'], 7)
            self.assertEqual(outcome['trace'][1]['tied_lines'], [horizontal, vertical])
        self.assertEqual(failed['status'], 'conflict')
        self.assertEqual(len(failed['trace']), 2)
        self.assertEqual(solved['status'], 'solved')
        self.assertEqual([step['line'] for step in solved['trace']], ['frame', vertical, horizontal])

    def test_representation_changes_preserve_schedules_and_geometric_profiles(self):
        """Stroke order, direction, and degree-2 cuts cannot inflate line weights."""
        for row in self.variants:
            key, original = row['id'], self.models[row['id']]
            for name, geometry in row['variants'].items():
                changed = build_whole_lines(geometry)
                self.assertEqual([line['id'] for line in changed.lines],
                                 [line['id'] for line in original.lines])
                for policy in POLICIES:
                    for direction in ('forward', 'reverse', 'random'):
                        with self.subTest(map=key, transform=name, policy=policy, direction=direction):
                            options = {'seed': 314159} if direction == 'random' else {}
                            before = run_weighted_lines(original, policy, direction, **options)
                            after = run_weighted_lines(changed, policy, direction, **options)
                            self.assertEqual(before['status'], 'solved')
                            self.assertEqual(after['status'], before['status'])
                            self.assertEqual([(s['line'], s['weight'], s['tied_lines']) for s in before['trace']],
                                             [(s['line'], s['weight'], s['tied_lines']) for s in after['trace']])
                            self.assertEqual(profile_signature(original, before['domains']),
                                             profile_signature(changed, after['domains']))
                            self.assertEqual(after['random_draws'], before['random_draws'])

    def test_identical_inputs_and_seed_have_identical_outcomes(self):
        """The random policy is reproducible, without picking the best seed."""
        for key in ('gallery-grid', 'teaching-D', 'remote-after', 'guillotine-20260916'):
            for policy in POLICIES:
                for seed in (0, 7, 20260918):
                    with self.subTest(map=key, policy=policy, seed=seed):
                        model = self.models[key]
                        self.assertEqual(run_weighted_lines(model, policy, 'random', seed=seed),
                                         run_weighted_lines(model, policy, 'random', seed=seed))

    def test_bridges_and_repeated_side_occurrences_do_not_become_variables(self):
        """A same-side bridge contributes no inequality or duplicate unknown."""
        model = self.models['gallery-dangling']
        _, _, occurrences, _ = self.metadata['gallery-dangling']
        self.assertTrue(model.virtual_edges)
        for identifier, ordered in occurrences.items():
            self.assertEqual(len({side for side, _ in ordered}), len(ordered))
            self.assertIn(identifier, {line['id'] for line in model.lines})
        for policy in POLICIES:
            outcome = run_weighted_lines(model, policy, 'random', seed=7)
            self.assertEqual(outcome['status'], 'solved')
            self.assertEqual(outcome['trace'], [])
            self.assertEqual(outcome['choices'], 0)
            for edge in range(len(model.plane_map.edges)):
                left, right = model.plane_map.shores(edge)
                if left == right:
                    self.assertEqual(outcome['domains'][left], outcome['domains'][right])

    def test_invalid_inputs_and_lower_priority_forcing_are_rejected(self):
        """The test hook must not bypass priorities or continue past a conflict."""
        model = self.models['guillotine-20260916']
        for policy, direction in (('unknown', 'forward'), ('constraints', 'unknown')):
            with self.assertRaises(ValueError):
                run_weighted_lines(model, policy, direction)
        for seed in (None, True, 1.5, '7'):
            with self.assertRaises(ValueError):
                run_weighted_lines(model, 'constraints', 'random', seed=seed)
        with self.assertRaisesRegex(ValueError, 'highest-weight'):
            run_weighted_lines(model, 'constraints', forced_prefix=('L:0,326>900,326',))
        with self.assertRaisesRegex(ValueError, 'terminal state'):
            run_weighted_lines(model, 'constraints',
                               forced_prefix=('frame', 'L:0,326>900,326', 'frame'))


if __name__ == '__main__':
    unittest.main()

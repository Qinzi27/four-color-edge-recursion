"""Check a fixed geometric obstruction and its actual low-color histories.

The production rule remains frozen. Ordinary geometric initializations and
externally restricted domains are separate experiments with separate audits.
Raw complete assignments are used only after a producer finishes.
"""

from argparse import ArgumentParser
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from itertools import product
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_quaternary_geometry import audit_bounded_contacts, audit_geometry
from fourcolor.global_restart import current_segments
from fourcolor.level_sides import level_metadata
from fourcolor.whole_lines import build_whole_lines
from scripts.audit_quaternary_low_color import _selection, audit_low_color
from scripts.quaternary_contact_model import propagate_contacts
from scripts.quaternary_low_color import solve_low_color
from scripts.quaternary_geometry_adapter import adapt_exported_geometry
from scripts.validate_global_restart import digest, export_geometries, write_report
from scripts.validate_quaternary_contacts_v2 import read_report
from scripts.validate_quaternary_geometry import standard_scenarios
from scripts.validate_quaternary_low_color import sources as previous_sources

OLD_MANIFEST = 'outputs/quaternary-low-color-manifest-2026-09-22.json.gz'
OLD_REPORT = 'outputs/quaternary-low-color-2026-09-22.json.gz'
PROTOCOL = 'docs/QUATERNARY_REACHABILITY_PROTOCOL-2026-09-22.md'
NEW_SOURCES = (
    'scripts/check_quaternary_reachability.py', 'scripts/quaternary_bipyramid_inputs.py',
    'scripts/audit_bare_bipyramid.py', 'scripts/scan_low_color_obstruction_states.py',
    'tests/test_quaternary_reachability.py', 'tests/test_quaternary_bipyramid_inputs.py',
    'tests/test_bare_bipyramid.py', 'tests/test_low_color_obstruction_states.py', PROTOCOL,
    'scripts/quaternary_lifted_obstruction_inputs.py', 'scripts/audit_lifted_bipyramid.py',
    'tests/test_quaternary_lifted_obstruction_inputs.py', 'tests/test_lifted_bipyramid.py',
)


def require(condition, message):
    """Reject evidence drift even when Python assertions are disabled."""
    if not condition:
        raise AssertionError(message)


def checksum(path):
    """Bind exact bytes rather than assuming a stable filename."""
    return sha256(Path(path).read_bytes()).hexdigest()


def sources():
    """Keep all old producer/auditor files fixed and bind this new check."""
    from scripts.quaternary_bipyramid_inputs import SOURCE_PATHS
    from scripts.quaternary_lifted_obstruction_inputs import SOURCE_PATHS as LIFTED_SOURCES
    old = read_report(ROOT / OLD_MANIFEST)
    hashes = previous_sources()
    require(hashes == old['source_sha256'], 'old low-color sources changed')
    hashes.update({name: checksum(ROOT / name) for name in set(NEW_SOURCES) | set(SOURCE_PATHS) | set(LIFTED_SOURCES)})
    return hashes


def prepare(path):
    """Freeze the complete small inventory, without running a coloring rule."""
    from scripts.quaternary_bipyramid_inputs import build_targeted_inventory, identify_bipyramid
    from scripts.quaternary_lifted_obstruction_inputs import build_lifted_inventory, identify_lifted
    require(not path.exists(), 'manifest exists; use a new name')
    hashes = sources()
    inputs = {name: checksum(ROOT / name) for name in (OLD_MANIFEST, OLD_REPORT)}
    inventory = build_targeted_inventory()
    rows = []
    exported = export_geometries(inventory['records'])
    require(len(exported) == len(inventory['records']) == 64, 'wrong six-segment inventory')
    for original, value in zip(inventory['records'], exported):
        require(value['status'] == 'geometry_ok' and value['key'] == original['key'], 'invalid geometry')
        geometry = value['geometry']
        rows.append({**original, 'geometry': geometry, 'geometry_sha256': digest(geometry),
                     'scenarios': standard_scenarios(geometry, {'extra_scenarios': []})})
    base = next(row for row in rows if row['subset_mask'] == 63)
    mapping = identify_bipyramid(base['geometry'])
    lifted = build_lifted_inventory()
    lifted_rows = []
    exported_lifted = export_geometries(lifted['records'])
    require(len(exported_lifted) == len(lifted['records']), 'lifted export omitted an input')
    for original, value in zip(lifted['records'], exported_lifted):
        require(value['status'] == 'geometry_ok' and value['key'] == original['key'], 'invalid lifted geometry')
        geometry = value['geometry']
        lifted_rows.append({**original, 'geometry': geometry, 'geometry_sha256': digest(geometry),
                            'scenarios': standard_scenarios(geometry, {'extra_scenarios': []})})
    lifted_by_key = {r['key']: r for r in lifted_rows}
    lifted_mappings = {h['id']: identify_lifted(lifted_by_key[h['prefix_keys'][-1]]['geometry'])
                       for h in lifted['histories']}
    manifest = {'schema_version': 1, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
                'source_sha256': hashes, 'input_sha256': inputs, 'records': rows,
                'histories': inventory['histories'], 'generation': inventory['generation'],
                'base_key': base['key'], 'base_mapping': mapping,
                'lifted_records': lifted_rows, 'lifted_histories': lifted['histories'],
                'lifted_generation': lifted['generation'], 'lifted_mappings': lifted_mappings,
                'resources': {'decision_limit': 128, 'probe_limit': 512,
                              'assignment_limit': 262144, 'node_limit': 200000},
                'counts': {'drawings': 64, 'ordinary_runs': 128, 'histories': 720,
                           'prefix_references': 5040, 'bare_partial_assignments': 3125,
                           'lifted_drawings': len(lifted_rows), 'lifted_runs': 2*len(lifted_rows),
                           'lifted_histories': len(lifted['histories']),
                           'lifted_prefix_references': sum(len(h['prefix_keys']) for h in lifted['histories'])},
                'producer_runs_during_prepare': 0}
    require(hashes == sources() and all(checksum(ROOT / name) == value for name, value in inputs.items()),
            'sources or input archives changed during freeze')
    write_report(path, manifest)
    return manifest['counts']


def literal_solutions(document, commitments=None):
    """Enumerate raw NEQ/EQ, supplied domains and both sets of commitments.

    Nonzero domain digits denote admissible names, not weights or a preferred
    representative. The supplied document is validated separately by the
    contact audit; this enumeration does not import propagation conclusions.
    """
    solutions = []
    for values in product((1, 2, 3, 4), repeat=len(document['sides'])):
        colors = dict(zip(document['sides'], values))
        if any(colors[s] != c for s, c in document.get('anchors', {}).items()):
            continue
        if any(colors[s] != c for s, c in (commitments or {}).items()):
            continue
        if any(word[colors[s] - 1] == '0' for s, word in document.get('states', {}).items()):
            continue
        if any(colors[line['left']] == colors[line['right']]
               for line in document['lines'] if line['kind'] == 'separator'):
            continue
        if any(colors[a] != colors[b] for a, b in document.get('equal_names', [])):
            continue
        solutions.append(colors)
    return solutions


def check_projections(outcome, solutions):
    """Check raw solutions against every final unary and ordered-pair state."""
    for colors in solutions:
        require(outcome['status'] != 'conflict', 'a complete raw solution was lost')
        for i, a in enumerate(outcome['side_order']):
            require(colors[a] in outcome['domains'][i], 'raw unary projection removed')
            for j, b in enumerate(outcome['side_order']):
                require(outcome['relations'][i][j] & (1 << (4 * (colors[a]-1) + colors[b]-1)),
                        'raw binary projection removed')


def external_domain_control(geometry, drawing, mapping, resources):
    """Audit external-domain geometry separately from ordinary reachability.

    Exact event/document transitions remain checked even after the first unsafe
    commitment empties the legal solution set. Equality of two empty solution
    sets cannot establish that a subsequent transition obeyed the policy.
    Mother scheduling is checked with the frozen auditor's shared selector.
    """
    inner, outer = f"S{mapping['inner_apex']}", f"S{mapping['outer_apex']}"
    adapted = adapt_exported_geometry(geometry, states={inner: '1100', outer: '0111'}, drawing=drawing)
    geometric, _ = audit_geometry(geometry, adapted)
    document = adapted['contact_document']
    initial = propagate_contacts(document)
    trial_document = deepcopy(document)
    trial_document.setdefault('anchors', {})[inner] = 1
    trial = propagate_contacts(trial_document)
    # Finish actual mother scheduling before either assignment enumeration.
    run = solve_low_color(document, geometry=geometry, probe=True,
                          decision_limit=resources['decision_limit'], probe_limit=resources['probe_limit'])
    require(run['original_input'] == document and run['schema_version'] == 1 and
            run['policy'] == 'quaternary-low-color-conditional-propagation-v1' and
            run['schedule'] == 'mother-peer-with-frame-only-fallback-v1',
            'external original input or policy differs')
    require(run['probe'] is True and type(run['backtracks']) is int and run['backtracks'] == 0 and
            run['oracle_feedback_to_producer'] is False and run['old_colors_read'] is False,
            'external production contract differs')
    for name in ('decision_limit', 'probe_limit'):
        require(type(run[name]) is int and run[name] >= 0 and run[name] == resources[name],
                'external resource limit differs')
    phases = run['phases']
    require(isinstance(phases, list) and phases and phases[0]['kind'] == 'main' and
            phases[0]['document'] == document, 'external phase zero differs from raw input')
    sides = document['sides']
    index = {side: i for i, side in enumerate(sides)}
    model = build_whole_lines(geometry)
    context = model, current_segments(model), level_metadata(model)
    require(sides == [f'S{i}' for i in range(len(model.plane_map.faces))],
            'external scheduling side identities differ')
    local_checks = []
    for source, outcome in ((document, initial), (trial_document, trial)):
        trace = audit_bounded_contacts(source, outcome)
        solutions = literal_solutions(source)
        check_projections(outcome, solutions)
        local_checks.append({'document': source, 'outcome': outcome, 'audit': trace,
                             'literal_assignments_checked': 4 ** len(document['sides']),
                             'solutions': solutions})
    original_solutions = literal_solutions(document)
    committed, current, first_bad, events = dict(document.get('anchors', {})), 0, None, []
    consumed, choices, probes, rejections = 1, 0, 0, 0
    # Transition claims are rechecked from the raw solution set. Every phase's
    # trace is also replayed, including failed trials which are not persistent.
    phase_checks = [audit_bounded_contacts(p['document'], p['outcome']) for p in phases]
    check_projections(phases[0]['outcome'], original_solutions)
    for event_index, event in enumerate(run['events']):
        require(type(event['before_phase']) is int and event['before_phase'] == current,
                'discontinuous external-domain event')
        before_phase = phases[current]
        before_outcome = before_phase['outcome']
        require(before_outcome['status'] == 'underdetermined', 'external event after terminal phase')
        require(choices < run['decision_limit'] and probes < run['probe_limit'],
                'external event after resource exhaustion')
        require(before_phase['document'].get('anchors', {}) == committed,
                'external persistent anchors were withdrawn or added')
        before = [c for c in original_solutions if all(c[s] == v for s, v in committed.items())]
        side, color = event['side'], event['symbol']
        require(side in index and type(color) is int, 'invalid external choice identity')
        selected, expected_selection = _selection(sides, before_outcome['domains'], context)
        require(index[side] == selected, 'external side violates mother schedule')
        candidates = before_outcome['domains'][selected]
        require(len(candidates) > 1 and color == min(candidates),
                'external-domain choice is not low-color first')
        expected_selection.update(side_id=side, candidate_order=candidates)
        require(event['candidates_before'] == candidates and event['selection'] == expected_selection,
                'external selection metadata differs')
        require(side not in committed, 'external commitment attempts to overwrite an anchor')
        restricted = {**committed, side: color}
        trial_solutions = [c for c in before if c[side] == color]
        require(type(event['trial_phase']) is int and event['trial_phase'] == consumed and
                consumed < len(phases) and phases[consumed]['kind'] == 'trial',
                'external trial is omitted, reused or out of order')
        trial_index, trial_phase = consumed, phases[consumed]
        consumed += 1
        probes += 1
        expected = deepcopy(before_phase['document'])
        expected.setdefault('anchors', {})[side] = color
        require(expected == trial_phase['document'], 'wrong trial restriction')
        check_projections(trial_phase['outcome'], trial_solutions)
        if event['kind'] == 'reject':
            require(not trial_solutions and trial_phase['outcome']['status'] == 'conflict',
                    'candidate elimination lacks contradiction')
            require(event['extension_claim'] == 'refuted', 'external rejection overstates evidence')
            expected_after = deepcopy(before_phase['document'])
            remaining = [candidate for candidate in candidates if candidate != color]
            # Literal independent encoding: a retained singleton uses digit 2;
            # multiple admissible names use digit 1, and exclusions use digit 0.
            expected_after.setdefault('states', {})[side] = ''.join(
                ('2' if len(remaining) == 1 else '1') if name in remaining else '0'
                for name in (1, 2, 3, 4))
            require(consumed < len(phases) and phases[consumed]['kind'] == 'main' and
                    phases[consumed]['document'] == expected_after,
                    'external rejection changed more than the exact refuted candidate')
            current = consumed
            consumed += 1
            rejections += 1
        else:
            require(event['kind'] == 'commit' and trial_phase['outcome']['status'] != 'conflict',
                    'invalid accepted trial')
            expected_claim = ('complete-witness' if trial_phase['outcome']['status'] == 'solved'
                              else 'inconclusive')
            require(event['extension_claim'] == expected_claim, 'external commitment overstates evidence')
            current = trial_index
            choices += 1
            committed = restricted
            if before and not trial_solutions and first_bad is None:
                first_bad = {'event_index': event_index, 'event': event,
                             'before_solutions': before, 'after_solutions': trial_solutions}
        require(type(event['after_phase']) is int and event['after_phase'] == current,
                'external after_phase differs from exact event transition')
        require(phases[current]['document'].get('anchors', {}) == committed,
                'external post-event anchors changed')
        expected_solutions = [c for c in original_solutions if all(c[s] == v for s, v in committed.items())]
        actual = literal_solutions(phases[current]['document'])
        require(actual == expected_solutions, 'persistent learned domains altered raw solution set')
        check_projections(phases[current]['outcome'], expected_solutions)
        events.append({'event_index': event_index, 'kind': event['kind'],
                       'before_solutions': len(before), 'trial_solutions': len(trial_solutions),
                       'after_solutions': len(expected_solutions)})
    require(consumed == len(phases), 'external unreferenced propagation phases')
    require(type(run['final_phase']) is int and current == run['final_phase'], 'external final phase differs')
    require(all(type(run[name]) is int for name in ('choices', 'probes', 'rejections')) and
            (run['choices'], run['probes'], run['rejections']) == (choices, probes, rejections),
            'external event telemetry differs')
    final = phases[current]['outcome']
    for name in ('colors', 'domains', 'name_states'):
        require(run[name] == final[name], 'external final output differs: ' + name)
    if final['status'] == 'underdetermined':
        require(choices == run['decision_limit'] or probes == run['probe_limit'],
                'external unexplained early stop')
        expected_reason = ('decision-limit-exhausted' if choices == run['decision_limit']
                           else 'probe-limit-exhausted')
        require(run['status'] == 'incomplete' and run['reason'] == expected_reason,
                'external resource exhaustion mislabeled')
    else:
        expected_reason = ('complete-coloring-verified' if final['status'] == 'solved'
                           else 'propagation-conflict-under-current-commitments')
        require(run['status'] == final['status'] and run['reason'] == expected_reason,
                'external terminal status/reason differs')
    if final['colors'] is not None:
        require(final['colors'] in original_solutions and
                all(final['colors'][s] == v for s, v in committed.items()),
                'external final colors violate original domains or actual commitments')
    require(len(local_checks[0]['solutions']) == 6 and len(local_checks[1]['solutions']) == 0,
            'the actual embedded contact graph does not reproduce the declared domain obstruction')
    return {'geometry_audit': geometric, 'mapping': mapping, 'adapted': adapted,
            'local_checks': local_checks, 'mother_schedule_run': run, 'phase_audits': phase_checks,
            'event_solution_counts': events, 'first_bad_commitment': first_bad,
            'transition_audit': 'exact_phase_documents_complete_coverage_and_final_binding',
            'schedule_audit': 'shared_mother_peer_selector_with_explicit_frame_fallback',
            'scope': 'Externally supplied nonsingleton domains on genuine geometry; not generated '
                     'by ordinary single/two-anchor initialization. Literal enumeration and propagation '
                     'trace checks are independent of the producer; geometric mother scheduling uses '
                     'shared frozen helpers. No oracle feedback.'}


def run_population(saved_records, originals, resources, failure_path, manifest_hash):
    """Keep every declared input, including conflicts and incomplete results."""
    require(len(saved_records) == len(originals), 'input coverage changed')
    rows = []
    for saved, original in zip(saved_records, originals):
        require(all(saved[name] == value for name, value in original.items()), 'input record changed')
        require(saved['geometry_sha256'] == digest(saved['geometry']), 'saved geometry corrupted')
        require(saved['scenarios'] == standard_scenarios(saved['geometry'], {'extra_scenarios': []}),
                'initialization changed')
        runs = []
        for scenario in saved['scenarios']:
            adapted = result = audit = None
            try:
                adapted = adapt_exported_geometry(saved['geometry'], anchors=scenario['anchors'],
                                                  drawing=saved['document'])
                result = solve_low_color(adapted['contact_document'], geometry=saved['geometry'], probe=True,
                                         decision_limit=resources['decision_limit'],
                                         probe_limit=resources['probe_limit'])
                audit = audit_low_color(adapted['contact_document'], result, geometry=saved['geometry'],
                                        adapted=adapted, assignment_limit=resources['assignment_limit'],
                                        node_limit=resources['node_limit'])
            except Exception as error:
                write_report(failure_path, {'status': 'incomplete',
                             'manifest_sha256': manifest_hash, 'input': saved, 'scenario': scenario,
                             'adapted': adapted, 'result': result, 'audit': audit,
                             'completed_records': rows, 'error': str(error)})
                raise
            runs.append({'scenario': scenario['id'], 'adapted': adapted, 'result': result, 'audit': audit})
        rows.append({'key': saved['key'], 'runs': runs})
    return rows


def summarize_population(rows, declared_histories):
    """Separate completion, unsafe commitments, unknowns, and prefix coverage."""
    groups = {}
    for mode in ('one-bounded-anchor', 'legacy-frame-anchors'):
        runs = [r for row in rows for r in row['runs'] if r['scenario'] == mode]
        groups[mode] = {'runs': len(runs), 'statuses': dict(Counter(r['result']['status'] for r in runs)),
                        'choices': sum(r['result']['choices'] for r in runs),
                        'rejections': sum(r['result']['rejections'] for r in runs),
                        'safe': sum(r['audit']['commitment_counts']['safe'] for r in runs),
                        'unsafe': sum(r['audit']['commitment_counts']['unsafe'] for r in runs),
                        'unknown': sum(r['audit']['oracle_unknown'] for r in runs),
                        'first_bad_keys': [row['key'] for row in rows for r in row['runs']
                                           if r['scenario'] == mode and r['audit']['first_bad_commitment']]}
    index = {row['key']: row for row in rows}
    histories = {}
    for mode in groups:
        histories[mode] = {'histories': len(declared_histories), 'all_prefixes_solved': sum(
            all(next(r for r in index[key]['runs'] if r['scenario'] == mode)['result']['status'] == 'solved'
                for key in h['prefix_keys']) for h in declared_histories)}
    return groups, histories


def execute(manifest_path, output):
    """Run frozen populations before posterior oracles; preserve all outcomes."""
    from scripts.quaternary_bipyramid_inputs import build_targeted_inventory, identify_bipyramid
    from scripts.quaternary_lifted_obstruction_inputs import build_lifted_inventory, identify_lifted
    from scripts.audit_bare_bipyramid import audit_bare_bipyramid
    from scripts.audit_lifted_bipyramid import audit_lifted_bipyramid
    require(not output.exists(), 'result exists; choose a new name')
    manifest_hash = checksum(manifest_path)
    manifest = read_report(manifest_path)
    require(manifest['source_sha256'] == sources(), 'sources changed after freeze')
    require(all(checksum(ROOT / n) == v for n, v in manifest['input_sha256'].items()), 'old evidence changed')
    inventory, lifted = build_targeted_inventory(), build_lifted_inventory()
    require(manifest['histories'] == inventory['histories'] and manifest['generation'] == inventory['generation'],
            'declared histories changed')
    require(manifest['lifted_histories'] == lifted['histories']
            and manifest['lifted_generation'] == lifted['generation'], 'lifted histories changed')
    require(len(manifest['records']) == 64 and len(manifest['lifted_records']) == 93,
            'declared population sizes changed')
    require(manifest['resources'] == {'decision_limit': 128, 'probe_limit': 512,
                                    'assignment_limit': 262144, 'node_limit': 200000}, 'budget changed')
    rows = run_population(manifest['records'], inventory['records'], manifest['resources'],
                          output.with_suffix('.bare.failure.json'), manifest_hash)
    print('Completed bare geometry population (128 runs).', flush=True)
    lifted_rows = run_population(manifest['lifted_records'], lifted['records'], manifest['resources'],
                                 output.with_suffix('.lifted.failure.json'), manifest_hash)
    print('Completed lifted geometry population (186 runs).', flush=True)
    lifted_inputs = {r['key']: r for r in manifest['lifted_records']}
    mappings = {h['id']: identify_lifted(lifted_inputs[h['prefix_keys'][-1]]['geometry'])
                for h in manifest['lifted_histories']}
    require(mappings == manifest['lifted_mappings'], 'lifted mapping changed')
    base = next(row for row in manifest['records'] if row['key'] == manifest['base_key'])
    mapping = identify_bipyramid(base['geometry'])
    require(mapping == manifest['base_mapping'], 'base topology mapping changed')
    external = external_domain_control(base['geometry'], base['document'], mapping, manifest['resources'])
    bare, abstract_lifted = audit_bare_bipyramid(), audit_lifted_bipyramid()
    groups, histories = summarize_population(rows, manifest['histories'])
    lifted_groups, lifted_histories = summarize_population(lifted_rows, manifest['lifted_histories'])
    require(manifest_hash == checksum(manifest_path) and manifest['source_sha256'] == sources(),
            'sources or manifest drifted during execution')
    require(all(checksum(ROOT / n) == v for n, v in manifest['input_sha256'].items()), 'old input drifted')
    report = {'schema_version': 1, 'manifest_sha256': manifest_hash, 'source_sha256': manifest['source_sha256'],
              'counts': manifest['counts'], 'records': rows, 'ordinary_summary': groups,
              'history_summary': histories, 'base_mapping': mapping,
              'lifted_records': lifted_rows, 'lifted_summary': lifted_groups,
              'lifted_history_summary': lifted_histories, 'lifted_mappings': mappings,
              'abstract_lifted_audit': abstract_lifted,
              'external_domain_control': external, 'bare_bipyramid_audit': bare,
              'scope': 'Separate finite six-segment subsets/histories, 24-segment fixed representation '
                       'prefixes, bare-graph commitments, external domains and abstract input-order diagnostic. '
                       'No oracle feedback, no universal completion claim; population sizes are not summed '
                       'as globally unique geometries.'}
    write_report(output, report)
    return {'ordinary_summary': groups, 'history_summary': histories,
            'lifted_summary': lifted_groups, 'lifted_history_summary': lifted_histories,
            'external_mother_status': external['mother_schedule_run']['status'],
            'external_mother_first_bad_found': external['first_bad_commitment'] is not None,
            'bare_audit_keys': list(bare)}


def main():
    """Freeze and run using exclusive new evidence paths."""
    parser = ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prep = commands.add_parser('prepare')
    prep.add_argument('--manifest', type=Path, required=True)
    run = commands.add_parser('run')
    run.add_argument('--manifest', type=Path, required=True)
    run.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    value = prepare(args.manifest) if args.command == 'prepare' else execute(args.manifest, args.output)
    print(json.dumps(value, ensure_ascii=False))


if __name__ == '__main__':
    main()

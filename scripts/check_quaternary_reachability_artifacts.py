"""Recheck saved reachability evidence without rerunning a coloring producer.

The checker binds the manifest, raw drawings, exported geometry, histories,
propagation traces, actual commitments, all saved exact certificates, summaries,
and archived scanner provenance. It verifies certificates without oracle search.
The old archive scan is checked through hashes, coverage and saved histograms;
its full checkpoint scan is not rerun. All output paths are exclusive.
"""

from argparse import ArgumentParser
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_quaternary_geometry import audit_bounded_contacts, audit_geometry
from scripts.exact_extendibility_oracle import verify_exact_result
from scripts.check_quaternary_low_color_artifacts import (
    file_hash, portable, project_path, check_file_set, raw_contacts,
)
from scripts.scan_low_color_obstruction_states import (
    read_bound_json, persistent_phases, classify_domains,
)
from scripts.validate_global_restart import digest
from scripts.validate_quaternary_contacts_v2 import expected_state
from scripts.validate_quaternary_geometry import standard_scenarios
from scripts.quaternary_bipyramid_inputs import build_targeted_inventory, identify_bipyramid
from scripts.quaternary_lifted_obstruction_inputs import build_lifted_inventory, identify_lifted
from scripts.check_quaternary_reachability import (
    OLD_MANIFEST, OLD_REPORT, summarize_population, literal_solutions, check_projections,
)
from scripts.audit_lifted_bipyramid import lifted_document, literal_prefix_evidence
from scripts.audit_bare_bipyramid import literal_solutions as bare_solutions


def require(condition, message):
    """Raise rather than silently accepting evidence drift under optimized Python."""
    if not condition:
        raise AssertionError(message)


def same(actual, expected, message):
    """Compare JSON values without conflating booleans with integer identities."""
    require(json.dumps(actual, sort_keys=True, allow_nan=False)
            == json.dumps(expected, sort_keys=True, allow_nan=False), message)


def own_source_hashes():
    """Bind this checker, its tests and every imported project Python dependency."""
    paths = {Path(__file__).resolve(), ROOT / 'tests/test_quaternary_reachability_artifacts.py'}
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            path = Path(filename).resolve()
            if path.is_relative_to(ROOT) and path.suffix == '.py':
                paths.add(path)
    return {portable(path): file_hash(path) for path in sorted(paths)}


def check_transitions(document, result, stored_phase_audits):
    """Replay saved input mutations and trace certificates, never propagation."""
    same(result['original_input'], document, 'producer original input changed')
    require(result['probe'] is True and result['oracle_feedback_to_producer'] is False
            and result['backtracks'] == 0, 'guarded/no-feedback contract differs')
    persistent_phases(result)  # Ensures every allocated phase is referenced once.
    phases = result['phases']
    same(phases[0]['document'], document, 'initial phase differs')
    require(len(phases) == len(stored_phase_audits), 'phase audit coverage differs')
    for phase, stored in zip(phases, stored_phase_audits):
        same(audit_bounded_contacts(phase['document'], phase['outcome']), stored,
             'saved propagation trace audit differs')
    current, commits, rejects = 0, 0, 0
    for event in result['events']:
        side, color = event['side'], event['symbol']
        before = phases[current]
        require(before['outcome']['status'] == 'underdetermined'
                and event['before_phase'] == current, 'event skips current live phase')
        index = document['sides'].index(side)
        candidates = before['outcome']['domains'][index]
        same(event['candidates_before'], candidates, 'candidate record differs')
        require(len(candidates) > 1 and color == min(candidates), 'not a low-color unresolved choice')
        require(side not in before['document'].get('anchors', {}), 'overwritten commitment')
        trial_document = deepcopy(before['document'])
        trial_document.setdefault('anchors', {})[side] = color
        trial = phases[event['trial_phase']]
        same(trial['document'], trial_document, 'trial imports extra restrictions')
        if event['kind'] == 'reject':
            require(trial['outcome']['status'] == 'conflict'
                    and event['extension_claim'] == 'refuted', 'rejection lacks conflict')
            expected = deepcopy(before['document'])
            remaining = [c for c in candidates if c != color]
            expected.setdefault('states', {})[side] = expected_state(remaining, False)['quaternary']
            rejects += 1
        else:
            require(event['kind'] == 'commit' and trial['outcome']['status'] != 'conflict',
                    'invalid committed trial')
            expected = trial_document
            claim = 'complete-witness' if trial['outcome']['status'] == 'solved' else 'inconclusive'
            require(event['extension_claim'] == claim, 'commitment overclaims its trial')
            commits += 1
        current = event['after_phase']
        same(phases[current]['document'], expected, 'persistent input mutation differs')
    require(result['choices'] == commits and result['rejections'] == rejects
            and result['probes'] == len(result['events']), 'producer counters differ')
    final = phases[current]['outcome']
    for field in ('name_states', 'domains', 'colors'):
        same(result[field], final[field], 'final phase differs: ' + field)
    require(result['status'] == ('incomplete' if final['status'] == 'underdetermined'
                                else final['status']), 'final status differs')
    return len(phases)


def check_certificates(document, result, audit, resources):
    """Verify every exact certificate against raw NEQ and actual commitments."""
    require(audit['passed'] is True and audit['oracle_feedback_to_producer'] is False,
            'independent audit contract differs')
    require(not document.get('states') and not document.get('equal_names'),
            'exact raw audit requires original NEQ and singleton anchors')
    require(result['decision_limit'] == resources['decision_limit']
            and result['probe_limit'] == resources['probe_limit'], 'producer limits differ')
    sides = document['sides']
    index = {side: i for i, side in enumerate(sides)}
    edges = sorted({tuple(sorted((index[line['left']], index[line['right']])))
                    for line in document['lines'] if line['kind'] == 'separator'})
    phase_count = check_transitions(document, result, audit['phase_audits'])
    require(audit['phase_count'] == phase_count and audit['trace_steps_checked'] == sum(
        p['trace_steps_checked'] for p in audit['phase_audits']), 'trace counters differ')
    records, used, statuses, signatures = audit['oracle_records'], set(), Counter(), set()
    for record in records:
        raw = record['input']
        same(raw['edges'], [list(edge) for edge in edges], 'oracle graph differs')
        require(raw['n'] == len(sides), 'oracle vertex coverage differs')
        fixed = dict(raw['anchors'])
        same(raw['anchors'], [list(p) for p in sorted(fixed.items())], 'noncanonical oracle commitments')
        signature = tuple(sorted(fixed.items()))
        require(signature not in signatures, 'duplicated oracle signature')
        signatures.add(signature)
        require(record['result']['node_limit'] == resources['node_limit'], 'oracle budget differs')
        verified = verify_exact_result(len(sides), edges, fixed, record['result'])
        require(verified['passed'], 'exact certificate rejected')
        same(verified, record['verification'], 'saved exact verification differs')
        statuses[record['result']['status']] += 1

    def at(number, fixed):
        """A reference may contain no restrictions beyond cumulative promises."""
        require(type(number) is int and 0 <= number < len(records), 'invalid oracle reference')
        used.add(number)
        record = records[number]
        same(record['input']['anchors'], [list(p) for p in sorted(fixed.items())],
             'oracle commitment binding differs')
        return record

    committed = {index[side]: color for side, color in document.get('anchors', {}).items()}
    at(audit['initial_oracle_index'], committed)
    require(len(audit['steps']) == len(result['events']), 'event/step coverage differs')
    counts = {'safe': 0, 'unsafe': 0, 'unknown': 0, 'preexisting_unsat': 0}
    rejections, first_bad = {'exact_unsat': 0, 'unknown': 0}, None
    for number, (event, step) in enumerate(zip(result['events'], audit['steps'])):
        require(step['event_index'] == number, 'step order differs')
        for field in ('kind', 'side', 'symbol', 'before_phase', 'trial_phase', 'after_phase'):
            same(step[field], event[field], 'event/step identity differs')
        before = at(step['before_oracle_index'], committed)
        proposed = {**committed, index[event['side']]: event['symbol']}
        trial = at(step['trial_oracle_index'], proposed)
        b, t = before['result']['status'], trial['result']['status']
        if event['kind'] == 'reject':
            require(t != 'sat', 'rejected trial has a verified witness')
            extension = 'refuted'
            rejections['exact_unsat' if t == 'unsat' else 'unknown'] += 1
        else:
            extension = ('preexisting_unsat' if b == 'unsat' else
                         'unknown' if 'unknown' in (b, t) else 'unsafe' if t == 'unsat' else 'safe')
            counts[extension] += 1
            committed = proposed
        after = at(step['after_oracle_index'], committed)
        require(step['before_status'] == b and step['after_status'] == after['result']['status']
                and step['extendibility'] == extension, 'extendibility classification differs')
        if extension == 'unsafe' and first_bad is None:
            first_bad = {**step, 'event': event, 'before': before, 'after': after}
    require(used == set(range(len(records))), 'unreferenced oracle certificate')
    same(audit['commitment_counts'], counts, 'commitment totals differ')
    same(audit['rejection_counts'], rejections, 'rejection totals differ')
    same(audit['first_bad_commitment'], first_bad, 'first unsafe evidence differs')
    require(audit['oracle_unknown'] == statuses['unknown'], 'unknown count differs')
    return {'oracle_records': len(records), 'oracle_statuses': dict(statuses),
            'phases': phase_count, 'unsafe_commitments': counts['unsafe']}


def check_population(saved_rows, rows, originals, resources):
    """Bind every real drawing and scenario, including all bridge/island inputs."""
    require(len(saved_rows) == len(rows) == len(originals), 'population coverage differs')
    totals, oracle_statuses = Counter(), Counter()
    for saved, row, original in zip(saved_rows, rows, originals):
        same({name: saved[name] for name in original}, original, 'raw input drawing changed')
        require(saved['key'] == row['key'], 'drawing order/key differs')
        same(saved['scenarios'], standard_scenarios(saved['geometry'], {'extra_scenarios': []}),
             'initialization differs')
        sides, lines, _ = raw_contacts(saved)
        same([run['scenario'] for run in row['runs']], [s['id'] for s in saved['scenarios']],
             'scenario coverage differs')
        for scenario, run in zip(saved['scenarios'], row['runs']):
            adapted, result, audit = run['adapted'], run['result'], run['audit']
            same(adapted['drawing'], saved['document'], 'adapter original drawing differs')
            same(adapted['geometry'], saved['geometry'], 'adapter geometry differs')
            require(adapted['geometry_sha256'] == saved['geometry_sha256'], 'geometry hash differs')
            geometric, _ = audit_geometry(saved['geometry'], adapted)
            same(geometric, audit['geometry'], 'saved geometry verification differs')
            document = adapted['contact_document']
            require(document['sides'] == sides and document['lines'] == lines
                    and document['anchors'] == scenario['anchors']
                    and not document.get('states') and not document.get('equal_names'),
                    'producer raw constraints differ from frozen contacts')
            require(result['schedule'] == 'mother-peer-with-frame-only-fallback-v1', 'schedule label differs')
            checked = check_certificates(document, result, audit, resources)
            oracle_statuses.update(checked.pop('oracle_statuses'))
            totals.update(checked)
            totals['runs'] += 1
        totals['drawings'] += 1
    return {**dict(totals), 'oracle_statuses': dict(oracle_statuses)}


def check_scan(scan, manifest):
    """Bind the old read-only scan and independently sum saved motif histograms."""
    require(scan['status'] == 'complete' and scan['producer_runs'] == scan['oracle_runs'] == 0,
            'archive scan is incomplete or ran new producers')
    require(scan['manifest_path'] == OLD_MANIFEST and scan['report_path'] == OLD_REPORT,
            'scan references a different original corpus')
    require(scan['manifest_sha256'] == manifest['input_sha256'][OLD_MANIFEST]
            and scan['report_sha256'] == manifest['input_sha256'][OLD_REPORT], 'scan archive hashes differ')
    check_file_set(scan['scanner_source_sha256'], 'scanner source')
    check_file_set(scan['frozen_source_sha256'], 'scanner frozen source')
    check_file_set(scan['frozen_input_sha256'], 'scanner frozen input')
    old_manifest = read_bound_json(project_path(OLD_MANIFEST), scan['manifest_sha256'])
    old_report = read_bound_json(project_path(OLD_REPORT), scan['report_sha256'])
    same(scan['frozen_source_sha256'], old_manifest['source_sha256'], 'scanner source inventory differs')
    same(scan['frozen_input_sha256'], old_manifest['input_artifact_sha256'], 'scanner input inventory differs')
    same(scan['checkpoint_hashes'], old_report['checkpoint_hashes'], 'scanner checkpoints differ')
    require(scan['checkpoint_directory'] == old_report['checkpoint_directory'], 'scanner checkpoint path differs')
    checkpoint_dir = project_path(scan['checkpoint_directory'])
    expected_names = [part['filename'] for part in scan['checkpoint_hashes']]
    require(sorted(p.name for p in checkpoint_dir.glob('part-*.json.gz')) == expected_names,
            'scanner checkpoint inventory differs')
    for part in scan['checkpoint_hashes']:
        require(Path(part['filename']).name == part['filename']
                and file_hash(checkpoint_dir / part['filename']) == part['sha256'],
                'scanner checkpoint bytes changed')
    counts = scan['counts']
    require(counts['drawings'] == old_manifest['counts']['drawings']
            and counts['runs'] == 2 * counts['drawings']
            and counts['checkpoint_parts'] == len(scan['checkpoint_hashes']), 'scanner coverage differs')
    group_totals = Counter()
    for group in scan['groups'].values():
        require(group['runs'] == counts['drawings'], 'scanner ordinary mode incomplete')
        group_totals.update(group)
    for name, value in group_totals.items():
        require(counts[name] == value, 'scanner group total differs: ' + name)
    histograms = scan['all_motif_domain_histograms']
    require(len(histograms) == counts['drawings_with_motif'], 'motif drawing count differs')
    pairs, strict, proper, motifs = 0, 0, 0, 0
    for drawing in histograms:
        require(len(drawing['scenarios']) == 2, 'motif lacks an ordinary scenario')
        motifs += len(drawing['scenarios'][0]['motifs'])
        for scenario in drawing['scenarios']:
            for motif in scenario['motifs']:
                for row in motif['domain_intersection_histogram']:
                    a, e, intersection, _ = row['domains_and_intersection_and_status']
                    same(intersection, sorted(set(a) & set(e)), 'histogram intersection differs')
                    count = row['phases']
                    pairs += count
                    proper += count * classify_domains(a, e)['proper_both']
                    strict += count * (int(classify_domains(a, e)['strict_apex_signature'])
                                       + int(classify_domains(e, a)['strict_apex_signature']))
    require(motifs == counts['induced_motifs'] and pairs == counts['motif_phase_pairs']
            and proper == counts['proper_intersection_matches']
            and strict == counts['strict_apex_matches'], 'scanner histogram totals differ')
    return {'counts': counts, 'checkpoint_bytes_checked': len(expected_names),
            'histogram_totals_recomputed': True, 'full_archive_scan_reexecuted': False}


def check_artifacts(manifest_path, report_path, scan_path):
    """Verify all saved branches and produce a source-bound compact audit."""
    paths = list(map(Path, (manifest_path, report_path, scan_path)))
    hashes = [file_hash(path) for path in paths]
    manifest, report, scan = [read_bound_json(path, value) for path, value in zip(paths, hashes)]
    own = own_source_hashes()
    require(manifest['schema_version'] == report['schema_version'] == 1
            and report['manifest_sha256'] == hashes[0], 'manifest/report binding differs')
    same(report['source_sha256'], manifest['source_sha256'], 'source declaration differs')
    same(report['counts'], manifest['counts'], 'population declaration differs')
    check_file_set(manifest['source_sha256'], 'frozen source')
    check_file_set(manifest['input_sha256'], 'frozen input')
    ordinary, lifted = build_targeted_inventory(), build_lifted_inventory()
    for prefix, inventory in (('', ordinary), ('lifted_', lifted)):
        same(manifest[prefix + 'histories'], inventory['histories'], 'history inputs differ')
        same(manifest[prefix + 'generation'], inventory['generation'], 'generation description differs')
    resources = manifest['resources']
    same(resources, {'decision_limit': 128, 'probe_limit': 512,
                     'assignment_limit': 262144, 'node_limit': 200000}, 'resource limits differ')
    normal = check_population(manifest['records'], report['records'], ordinary['records'], resources)
    extra = check_population(manifest['lifted_records'], report['lifted_records'], lifted['records'], resources)
    groups, histories = summarize_population(report['records'], manifest['histories'])
    same(groups, report['ordinary_summary'], 'ordinary summary differs')
    same(histories, report['history_summary'], 'ordinary prefix summary differs')
    groups, histories = summarize_population(report['lifted_records'], manifest['lifted_histories'])
    same(groups, report['lifted_summary'], 'lifted summary differs')
    same(histories, report['lifted_history_summary'], 'lifted prefix summary differs')
    expected_counts = {'drawings': len(ordinary['records']), 'ordinary_runs': normal['runs'],
                       'histories': len(ordinary['histories']),
                       'prefix_references': sum(len(h['prefix_keys']) for h in ordinary['histories']),
                       'bare_partial_assignments': 3125, 'lifted_drawings': len(lifted['records']),
                       'lifted_runs': extra['runs'], 'lifted_histories': len(lifted['histories']),
                       'lifted_prefix_references': sum(len(h['prefix_keys']) for h in lifted['histories'])}
    same(manifest['counts'], expected_counts, 'declared coverage counts differ')
    base = next(row for row in manifest['records'] if row['key'] == manifest['base_key'])
    same(identify_bipyramid(base['geometry']), manifest['base_mapping'], 'base geometry roles differ')
    same(report['base_mapping'], manifest['base_mapping'], 'saved base roles differ')
    by_key = {row['key']: row for row in manifest['lifted_records']}
    mappings = {h['id']: identify_lifted(by_key[h['prefix_keys'][-1]]['geometry'])
                for h in manifest['lifted_histories']}
    same(mappings, manifest['lifted_mappings'], 'frozen lifted geometry roles differ')
    same(mappings, report['lifted_mappings'], 'saved lifted geometry roles differ')

    external = report['external_domain_control']
    same(external['mapping'], manifest['base_mapping'], 'external-domain geometry mapping differs')
    same(external['adapted']['geometry'], base['geometry'], 'external-domain geometry changed')
    same(external['adapted']['drawing'], base['document'], 'external-domain drawing changed')
    geometric, _ = audit_geometry(base['geometry'], external['adapted'])
    same(geometric, external['geometry_audit'], 'external geometry audit differs')
    document = external['adapted']['contact_document']
    inner = 'S' + str(manifest['base_mapping']['inner_apex'])
    outer = 'S' + str(manifest['base_mapping']['outer_apex'])
    same(document['states'], {inner: '1100', outer: '0111'}, 'external domain control changed')
    require(not document['anchors'], 'unexpected external-control anchor')
    for local in external['local_checks']:
        same(audit_bounded_contacts(local['document'], local['outcome']), local['audit'],
             'external local trace audit differs')
        same(literal_solutions(local['document']), local['solutions'], 'external full solutions differ')
    external_run = external['mother_schedule_run']
    check_transitions(document, external_run, external['phase_audits'])
    for phase in external_run['phases']:
        check_projections(phase['outcome'], literal_solutions(phase['document']))

    abstract = report['abstract_lifted_audit']
    same(abstract['document'], lifted_document(), 'abstract lifted graph/input order changed')
    abstract_checked = check_certificates(abstract['document'], abstract['result'], abstract['audit'], resources)
    same(literal_prefix_evidence(abstract['document']), abstract['independent_literal_enumeration'],
         'abstract lifted all-assignment evidence differs')
    require(abstract_checked['unsafe_commitments'] == 1
            and abstract['audit']['first_bad_commitment']['side'] == 'A', 'abstract obstruction differs')

    bare = report['bare_bipyramid_audit']
    solutions = bare_solutions()
    derived = Counter()
    for values in product(range(5), repeat=5):
        legal = [a for a in solutions if all(c == 0 or a[i] == c for i, c in enumerate(values))]
        if not legal:
            continue
        derived['extendible_partial_commitments'] += 1
        for i, color in enumerate(values):
            if color:
                continue
            for trial in (1, 2, 3, 4):
                derived['all_literal_trials'] += 1
                derived['extendible_trials' if any(a[i] == trial for a in legal)
                        else 'nonextendible_trials'] += 1
    require(bare['passed'] is True and bare['complete_assignments_enumerated'] == 1024
            and bare['complete_legal_assignments'] == 24
            and bare['counts']['partial_commitments_enumerated'] == 3125, 'bare population differs')
    for name, value in derived.items():
        require(bare['counts'][name] == value, 'bare literal count differs: ' + name)
    scan_checked = check_scan(scan, manifest)
    check_file_set(own, 'checker source')
    check_file_set(manifest['source_sha256'], 'frozen source')
    check_file_set(manifest['input_sha256'], 'frozen input')
    require([file_hash(path) for path in paths] == hashes, 'artifacts changed during check')
    return {'schema_version': 1, 'passed': True, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
            'artifact_sha256': {portable(path): value for path, value in zip(paths, hashes)},
            'checker_source_sha256': own, 'ordinary': normal, 'lifted': extra,
            'abstract_lifted': abstract_checked, 'bare_literal_population_rechecked': dict(derived),
            'archived_scan': scan_checked, 'producer_runs': 0, 'oracle_searches': 0,
            'scope': 'Saved geometry provenance/rotation, all propagation trace certificates, raw '
                'commitments and all stored SAT/UNSAT evidence reverified. Input inventories and '
                'summaries reconstructed. Node planarization and mother selector not rerun. '
                'Old scanner checkpoint bytes and histogram totals checked; complete archive '
                'scan not rerun. Bare candidate-trial propagation not rerun.'}


def main():
    """Only create a new output after every read-only verification succeeds."""
    parser = ArgumentParser(description=__doc__)
    for name in ('manifest', 'report', 'scan', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'output exists; choose a new filename')
    result = check_artifacts(args.manifest, args.report, args.scan)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, separators=(',', ':'))
        stream.write('\n')
    print(json.dumps({key: result[key] for key in ('passed', 'ordinary', 'lifted', 'abstract_lifted')},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()

"""Parallel scheduling of the frozen saved-artifact checks, with exact binding.

Every run is checked by its original frozen checker. Only in-memory results of
these completed calls are cached; external caches are never accepted. The
unchanged global checker then checks all headers, coverage and summaries, using
the cache only when every checker argument has the identical canonical digest.
"""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import validate_quaternary_all_candidate as experiment

PLAN = ROOT / 'outputs/quaternary-all-candidate-parallel-check-plan-2026-09-26.json'


def signature(policy, raw, envelope, audit, resources, geometry, adapted):
    """Bind every premise and saved output, not merely the reported result."""
    return experiment.digest({'policy': policy, 'raw': raw, 'envelope': envelope,
        'audit': audit, 'resources': resources, 'geometry': geometry, 'adapted': adapted})


def verify_record(job):
    """Invoke the frozen per-run checkers on one complete checkpoint."""
    number, record, reference, manifest_hash = job
    path = (ROOT / reference['path']).resolve()
    experiment.require(path.is_relative_to(ROOT / 'outputs'), 'checkpoint outside outputs')
    experiment.same(experiment.checksum(path), reference['sha256'], 'checkpoint bytes changed')
    saved = experiment.read_report(path)
    experiment.same(saved['manifest_sha256'], manifest_hash, 'checkpoint freeze differs')
    experiment.same(saved['record_sha256'], experiment.digest(record), 'checkpoint input differs')
    row = saved['row']
    experiment.same([row['key'], row['eligibility']], [record['key'], record['eligibility']], 'identity differs')
    experiment.same([(e['scenario'], e['policy']) for e in row['runs']],
        [(s['id'], p) for s in record['scenarios'] for p in experiment.POLICIES], 'coverage differs')
    geometry = record['export']['geometry'] if record['original']['kind'] == 'geometry' and record['eligibility'] == 'ready' else None
    checked = []
    for entry in row['runs']:
        if entry['execution'] != 'audited':
            continue  # The unchanged global checker records incompleteness.
        scenario = next(s for s in record['scenarios'] if s['id'] == entry['scenario'])
        adapted = (experiment.adapt_exported_geometry(geometry, anchors=scenario['anchors'],
                   drawing=record['original']['document']) if geometry is not None else None)
        raw = adapted['contact_document'] if adapted else record['original']['document']
        experiment.same(entry['raw_document'], raw, 'raw query differs')
        experiment.same(entry['adapted'], adapted, 'adaptation differs')
        checker = (experiment.check_odd_cycle_eq_artifacts if entry['policy'] == 'odd-cycle-eq'
                   else experiment.check_all_candidate_artifacts)
        result = checker(raw, entry['result'], entry['audit'], experiment.RESOURCES,
                         geometry=geometry, adapted=adapted)
        key = signature(entry['policy'], raw, entry['result'], entry['audit'],
                        experiment.RESOURCES, geometry, adapted)
        checked.append((key, result))
    return number, checked


def main():
    """Parallelize only independent verification, then run global binding."""
    plan = json.loads(PLAN.read_text(encoding='utf8'))
    experiment.same(experiment.checksum(Path(__file__)), plan['driver_sha256'], 'driver source drift')
    manifest_path, report_path = ROOT / plan['manifest'], ROOT / plan['report']
    experiment.same(experiment.checksum(manifest_path), plan['manifest_sha256'], 'manifest changed')
    experiment.same(experiment.checksum(report_path), plan['report_sha256'], 'report changed')
    manifest, report = experiment.bound_manifest(manifest_path), experiment.read_report(report_path)
    experiment.require(len(manifest['records']) == len(report['checkpoints']), 'checkpoint coverage differs')
    cache, deliveries, used = {}, {}, {}
    jobs = [(i, record, reference, plan['manifest_sha256']) for i, (record, reference) in
            enumerate(zip(manifest['records'], report['checkpoints']))]
    with ProcessPoolExecutor(max_workers=plan['workers']) as pool:
        futures = [pool.submit(verify_record, job) for job in jobs]
        completed = 0
        for future in as_completed(futures):
            number, checked = future.result()
            for key, result in checked:
                if key in cache:
                    experiment.same(cache[key], result, 'same arguments produced different checks')
                cache[key] = result
                deliveries[key] = deliveries.get(key, 0) + 1
            completed += 1
            print(json.dumps({'verified_checkpoints': completed, 'total': len(jobs), 'index': number}), flush=True)

    def cached(policy):
        """Reuse only an identical argument tuple already verified in this run."""
        def check(raw, envelope, audit, resources, *, geometry=None, adapted=None):
            key = signature(policy, raw, envelope, audit, resources, geometry, adapted)
            experiment.require(key in cache, 'global checker requested unverified evidence')
            used[key] = used.get(key, 0) + 1
            return cache[key]
        return check

    old_odd, old_all = experiment.check_odd_cycle_eq_artifacts, experiment.check_all_candidate_artifacts
    experiment.check_odd_cycle_eq_artifacts = cached('odd-cycle-eq')
    experiment.check_all_candidate_artifacts = cached('all-candidate')
    try:
        counts = experiment.check(manifest_path, report_path, ROOT / plan['output'])
    finally:
        experiment.check_odd_cycle_eq_artifacts = old_odd
        experiment.check_all_candidate_artifacts = old_all
    experiment.same(used, deliveries, 'global coverage differs from verified calls')
    experiment.same(manifest['source_sha256'], experiment.sources(), 'research source drift')
    experiment.write_report(ROOT / plan['execution_evidence'], {
        'passed': True, 'plan_sha256': experiment.checksum(PLAN),
        'driver_sha256': experiment.checksum(Path(__file__)), 'workers': plan['workers'],
        'frozen_checker_calls': sum(deliveries.values()), 'unique_argument_digests': len(cache),
        'global_cache_uses': sum(used.values()), 'counts': counts,
        'artifact_check_sha256': experiment.checksum(ROOT / plan['output']),
        'external_cache_read': False, 'producer_runs': 0, 'propagation_runs': 0, 'oracle_searches': 0})
    print(json.dumps(counts), flush=True)


if __name__ == '__main__':
    main()

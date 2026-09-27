"""Operational sharding of independent frozen cases; no algorithm changes.

Each case still runs both producers before either offline auditor. Write to an
exclusive temporary checkpoint, then atomically publish without overwriting.
The original sequential runner and final saved checker remain authoritative.
"""

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import validate_quaternary_all_candidate as experiment

PLAN = ROOT / 'outputs/quaternary-all-candidate-parallel-plan-2026-09-26-v2.json'


def main():
    """Process only the exact predeclared reverse-order shard."""
    plan = json.loads(PLAN.read_text(encoding='utf8'))
    experiment.same(experiment.checksum(Path(__file__)), plan['worker_sha256'], 'worker source drift')
    shard = next(item for item in plan['shards'] if item['id'] == sys.argv[1])
    manifest_path = ROOT / plan['manifest']
    experiment.same(experiment.checksum(manifest_path), plan['manifest_sha256'], 'manifest changed')
    manifest = experiment.bound_manifest(manifest_path)
    directory = ROOT / plan['checkpoint_directory']
    for number in reversed(range(shard['start_inclusive'], shard['stop_exclusive'])):
        row = manifest['records'][number]
        path = directory / f'{number:03d}-{row["key"][:12]}.json.gz'
        if path.exists():
            # The sequential process might currently be writing this path.
            # Never inspect, delete, overwrite, or truncate another writer.
            print(json.dumps({'shard': shard['id'], 'index': number, 'action': 'existing-path-skipped'}), flush=True)
            continue
        saved = experiment.run_record(row)
        temporary = directory / f'{path.name}.{shard["id"]}.pending.json.gz'
        experiment.write_report(temporary, {'manifest_sha256': plan['manifest_sha256'],
                                'record_sha256': experiment.digest(row), 'row': saved})
        try:
            # Windows rename is atomic and refuses an existing destination.
            temporary.rename(path)
            action = 'published'
        except FileExistsError:
            # Preserve the duplicate as operational evidence, never replace.
            action = 'duplicate-preserved'
        print(json.dumps({'shard': shard['id'], 'index': number, 'action': action,
                          'qualities': [experiment.quality(e) for e in saved['runs']]}), flush=True)
    experiment.same(manifest['source_sha256'], experiment.sources(), 'frozen source drift')


if __name__ == '__main__':
    main()

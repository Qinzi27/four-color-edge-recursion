"""Recheck saved geometry evidence without rerunning or changing the producer.

This post-run check binds files, coverage and exact certificates. It replays the
two historical commitment diagnostics through the independent auditor, but does
not claim to repeat full assignment enumeration for every saved scene.
"""

from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_quaternary_geometry import audit_run
from scripts.exact_extendibility_oracle import verify_exact_result
from scripts.validate_global_restart import digest, write_report
from scripts.validate_quaternary_contacts_v2 import read_report
from scripts.validate_quaternary_geometry import require, source_hashes, summarize


def checksum(path):
    """Hash exact saved bytes, including gzip framing."""
    return sha256(path.read_bytes()).hexdigest()


def check(manifest_path, report_path, checkpoint_dir):
    """Validate each stored scene and verify all SAT/UNSAT certificates again."""
    manifest, report = read_report(manifest_path), read_report(report_path)
    require(report['manifest_sha256'] == checksum(manifest_path), 'manifest bytes changed')
    require(report['source_sha256'] == manifest['source_sha256'] == source_hashes(),
            'frozen source hash mismatch')
    for name, expected in manifest['input_artifact_sha256'].items():
        require(checksum(ROOT / name) == expected, 'input hash mismatch: ' + name)
    require(not (checkpoint_dir / 'failure.json').exists(), 'failure record present')
    # Checkpoint concatenation must reproduce the entire saved report, in order.
    offset = 0
    expected_parts = {p['filename'] for p in report['checkpoint_hashes']}
    require({p.name for p in checkpoint_dir.glob('part-*.json.gz')} == expected_parts,
            'checkpoint inventory differs')
    for part in report['checkpoint_hashes']:
        path = checkpoint_dir / part['filename']
        require(checksum(path) == part['sha256'], 'checkpoint byte mismatch')
        rows = read_report(path)
        require(rows == report['records'][offset:offset + len(rows)], 'checkpoint data mismatch')
        offset += len(rows)
    require(offset == len(report['records']) == len(manifest['records']), 'drawing coverage differs')
    require(len({r['key'] for r in report['records']}) == offset, 'duplicate drawing')
    mode_counts, oracle_counts, diagnostics = Counter(), Counter(), []
    for frozen, saved in zip(manifest['records'], report['records']):
        require(frozen['key'] == saved['key'], 'drawing order or identity differs')
        require(frozen['geometry_sha256'] == saved['geometry_sha256'] == digest(frozen['geometry']),
                'geometry hash mismatch')
        require(len(frozen['scenarios']) == len(saved['runs']), 'scenario count differs')
        for scenario, run in zip(frozen['scenarios'], saved['runs']):
            require((scenario['id'], scenario['anchors']) == (run['id'], run['anchors']),
                    'scenario inputs differ')
            audit = run['audit']
            require(audit['passed'] and not audit['oracle_feedback_to_producer'], 'invalid audit scope')
            require(run['choices'] == run['backtracks'] == 0, 'unexpected active choices')
            require(run['status'] == 'solved' or run['colors'] is None, 'false completed coloring')
            exact = audit['oracle_input']
            verified = verify_exact_result(exact['n'], exact['edges'], dict(exact['anchors']), audit['oracle'])
            require(verified['passed'] and verified == audit['oracle_verification'],
                    'stored exact certificate failed recheck')
            mode_counts[run['id']] += 1
            oracle_counts[audit['oracle']['status']] += 1
        for detail in saved['detailed']:
            run = next(r for r in saved['runs'] if r['id'] == detail['id'])
            require(digest(detail['adapted']) == run['adapted_sha256']
                    and digest(detail['outcome']) == run['producer_sha256']
                    and detail['audit'] == run['audit'], 'detailed evidence differs')
            if 'first-commit' in detail['id']:
                # These two genuine historical states expose the commitment boundary.
                fresh = audit_run(frozen['geometry'], detail['adapted'], detail['outcome'],
                                  assignment_limit=manifest['resources']['assignment_limit'],
                                  node_limit=manifest['resources']['node_limit'])
                require(fresh == detail['audit'], 'historical audit replay differs')
                diagnostics.append({'id': detail['id'], 'producer_status': run['status'],
                                    'S10': run['name_states']['S10'],
                                    'oracle_status': fresh['oracle']['status'],
                                    'oracle_nodes': fresh['oracle']['nodes']})
    require(dict(mode_counts) == manifest['counts']['modes'], 'mode coverage differs')
    require(sum(mode_counts.values()) == manifest['counts']['scenarios'], 'total scenarios differ')
    require(summarize(report['records'], manifest) == report['summary'], 'summary differs')
    require(report['summary']['all_checks_passed'], 'formal check did not pass')
    return {'schema_version': 1, 'generated_at_utc': datetime.now(timezone.utc).isoformat(),
            'passed': True, 'checker_sha256': checksum(Path(__file__)),
            'manifest_sha256': checksum(manifest_path), 'report_sha256': checksum(report_path),
            'sources_checked': len(manifest['source_sha256']),
            'input_artifacts_checked': len(manifest['input_artifact_sha256']),
            'checkpoints_checked': len(expected_parts), 'drawings_checked': offset,
            'scenarios_checked': sum(mode_counts.values()), 'mode_counts': dict(mode_counts),
            'exact_certificates_reverified': dict(oracle_counts), 'diagnostics_replayed': diagnostics,
            'summary_recomputed': True,
            'scope': 'Saved-byte, coverage, detailed-output and exact-certificate recheck; '
                     'full independent propagation audit replayed for the two historical diagnostics. '
                     'No new producer run and no claim of repeating every full enumeration.'}


def main():
    """Require explicit input paths and an exclusive new output file."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--checkpoint-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'choose a new output path')
    result = check(args.manifest, args.report, args.checkpoint_dir)
    write_report(args.output, result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()

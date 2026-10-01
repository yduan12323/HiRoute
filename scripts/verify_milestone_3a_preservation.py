"""Check M1–M2 without writing inside their result directories."""
import argparse
import json
import subprocess
from datetime import datetime, timezone

from _common import ROOT, configs, sha256, verified_dataset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', default='results/milestone_3a/preservation_before.json')
    parser.add_argument('--capture', action='store_true', help='Exclusively capture a fresh local M1–M2 checkpoint')
    args = parser.parse_args()
    data, _ = configs()
    dataset = verified_dataset(data)
    if args.capture:
        graph_dir = ROOT/data['graph_dir']
        metadata = json.loads((graph_dir/'metadata.json').read_text())
        if any(sha256(graph_dir/n) != r['sha256'] for n,r in metadata['files'].items()):
            raise ValueError('Original graph fingerprint mismatch')
        paths = [ROOT/'RESEARCH_SPEC.md', ROOT/'docs/MILESTONE_1_REPORT.md', ROOT/'docs/MILESTONE_2_REPORT.md',
                 ROOT/data['instances_path'], ROOT/data['dataset']['manifest_path'],
                 *graph_dir.glob('*'), *(ROOT/'src/graph').glob('*.py'),
                 *[ROOT/'configs'/name for name in ['data.yaml','routing.yaml','envelope.yaml','semantic.yaml','experiment.yaml']],
                 *(ROOT/'results/milestone_1').rglob('*'), *(ROOT/'results/milestone_2').rglob('*')]
        snapshot = {'dataset_sha256': dataset['sha256'],
                    'git_commit': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                    'git_status': subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True),
                    'preserved_files': {str(p.relative_to(ROOT)):sha256(p) for p in paths if p.is_file()}}
        with (ROOT/args.checkpoint).open('x') as stream:
            json.dump(snapshot,stream,indent=2)
        print('Captured exclusive local preservation checkpoint')
        return
    checkpoint = json.loads((ROOT / args.checkpoint).read_text())
    changed = [name for name, digest in checkpoint['preserved_files'].items()
               if not (ROOT / name).is_file() or sha256(ROOT / name) != digest]
    if dataset['sha256'] != checkpoint['dataset_sha256']:
        changed.append(data['dataset']['raw_path'])
    result = {'passed': not changed, 'changed_files': changed,
              'verified_files': len(checkpoint['preserved_files']),
              'timestamp_utc': datetime.now(timezone.utc).isoformat(),
              'git_commit': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'git_status': subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True),
              'dataset_sha256': dataset['sha256']}
    (ROOT / 'results/milestone_3a/preservation_after.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    if changed:
        raise RuntimeError('Milestone 1–2 preservation failed')


if __name__ == '__main__':
    main()

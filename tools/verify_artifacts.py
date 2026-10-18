"""Explicit, read-only integrity check for independently held historical outputs."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='Existing artifact root; no downloads are performed')
    parser.add_argument('--prefix', required=True, help='Select indexed relative paths by prefix')
    parser.add_argument('--index', type=Path, required=True, help='External archive manifest JSON; never bundled with the source checkout')
    args = parser.parse_args(argv)
    rows = [r for r in json.loads(args.index.read_text())['files'] if r['path'].startswith(args.prefix)]
    if not rows:
        parser.error('Prefix selects no historical artifacts; consult the external manifest supplied with --index')
    root = args.root.resolve()
    errors = []
    for row in rows:
        path = (root / row['path']).resolve()
        if not path.is_relative_to(root):
            errors.append(f"Unsafe archive path: {row['path']}")
            continue
        if not path.is_file():
            errors.append(f"Missing: {row['path']}")
            continue
        h = hashlib.sha256()
        with path.open('rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''):
                h.update(chunk)
        if path.stat().st_size != row['bytes'] or h.hexdigest() != row['sha256']:
            errors.append(f"Integrity mismatch: {row['path']}")
    if errors:
        print('\n'.join(errors[:20]))
        print(f'{len(errors)} failures among {len(rows)} selected artifacts. Historical output is optional; for new experiments regenerate with docs/REPRODUCING.md. Never substitute a different snapshot.')
        return 1
    print(f'Verified {len(rows)} historical artifacts; no files changed.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())

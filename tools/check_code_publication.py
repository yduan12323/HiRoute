"""Reject generated data/results and oversized files in the publication index."""
from pathlib import Path
import subprocess
import json

ROOT = Path(__file__).resolve().parents[1]


def contains_generated_pool(value):
    if isinstance(value, dict):
        if isinstance(value.get('original_pool_prefix'), list):
            return True
        return any(contains_generated_pool(child) for child in value.values())
    if isinstance(value, list):
        return any(contains_generated_pool(child) for child in value)
    return False


def main():
    rows = subprocess.check_output(['git', 'ls-files', '--stage', '-z'], cwd=ROOT).split(b'\0')
    errors = []
    for row in rows:
        if not row:
            continue
        metadata, raw_path = row.split(b'\t', 1)
        path = raw_path.decode()
        if path.endswith('/.gitkeep'):
            continue
        if path.startswith(('artifacts/', 'results/', 'data/processed/', 'data/cache/', 'data/raw/osm/')):
            errors.append(f'Generated path in Git index: {path}')
        fixture_or_input = path.startswith(('tests/fixtures/', 'configs/inputs/'))
        # One task-scoped, small diagnostic table; existing 1 MiB cap still applies.
        small_diagnostic_table = path == 'docs/SEMANTICS_AND_PROFILE.jsonl'
        if not fixture_or_input and not small_diagnostic_table and path.endswith(('.log', '.parquet', '.npz', '.npy', '.bin', '.tar.gz', '.jsonl', '.xml', '.csv')):
            errors.append(f'Generated/binary output extension outside small input fixtures: {path}')
        oid = metadata.split()[1].decode()
        size = int(subprocess.check_output(['git', 'cat-file', '-s', oid], cwd=ROOT))
        if path.startswith('tests/fixtures/') and path.endswith('.json'):
            value = json.loads(subprocess.check_output(['git', 'cat-file', 'blob', oid], cwd=ROOT))
            if isinstance(value, dict) and {'results', 'evidence'}.intersection(value):
                errors.append(f'Generated oracle/trace output is not a source fixture: {path}')
        if path.startswith('docs/') and path.endswith('.json'):
            value = json.loads(subprocess.check_output(['git', 'cat-file', 'blob', oid], cwd=ROOT))
            if contains_generated_pool(value):
                errors.append(f'Processed real candidate pool embedded in documentation: {path}')
        if size > 1024 * 1024:
            errors.append(f'File exceeds 1 MiB publication budget ({size} bytes): {path}')
    if errors:
        print('\n'.join(errors))
        return 1
    print('Publication index contains no bulk data/results and no files over 1 MiB.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())

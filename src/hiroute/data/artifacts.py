"""Explicit external input manifests; never discover or substitute a dataset."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'duplicate JSON field: {key}')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError(f'nonfinite JSON: {value}')
    return json.loads(Path(path).read_text(), object_pairs_hook=unique, parse_constant=invalid)


def verify_manifest(root: Path, manifest: dict, required=('graph', 'catalog', 'bindings')) -> dict:
    """Check every listed file, including auxiliary evidence, without changing it."""
    if set(manifest) != {'schema', 'files'} or manifest['schema'] != 'hiroute.artifact_manifest.v1':
        raise ValueError('expected hiroute.artifact_manifest.v1 with schema and files')
    root = Path(root).resolve()
    rows, roles, paths, errors = [], set(), set(), []
    for item in manifest['files']:
        if set(item) != {'role', 'path', 'bytes', 'sha256'}:
            raise ValueError('artifact requires role, path, bytes and sha256')
        role, name = item['role'], item['path']
        if not isinstance(role, str) or not role or role in roles or name in paths:
            raise ValueError('duplicate or invalid artifact identity')
        if type(item['bytes']) is not int or item['bytes'] < 0:
            raise ValueError('invalid artifact byte count')
        sha = item['sha256']
        if not isinstance(sha, str) or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
            raise ValueError('invalid artifact SHA256')
        roles.add(role); paths.add(name)
        path = (root / name).resolve()
        status = 'verified'
        if Path(name).is_absolute() or not path.is_relative_to(root):
            status = 'unsafe_path'
        elif not path.is_file():
            status = 'missing'
        elif path.stat().st_size != item['bytes'] or digest(path) != sha:
            status = 'integrity_mismatch'
        if status != 'verified':
            errors.append({'role': role, 'path': name, 'status': status})
        rows.append({**item, 'resolved_path': str(path), 'status': status})
    errors.extend({'role': role, 'status': 'not_in_manifest'} for role in required if role not in roles)
    return dict(verified=not errors, root=str(root), files=rows, errors=errors)

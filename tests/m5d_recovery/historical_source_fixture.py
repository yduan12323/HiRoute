"""Authenticated historical source-hash input; never used to admit a real run."""
import json
from pathlib import Path

from experiments.mechanism_recovery_v1 import run as base

SOURCE_COMMIT = 'fcb3577c862f3e4ff9e731c9e633f0e638b26540'
SOURCE_SHA256 = 'c1a8ebc5a046b9ae402bb9337548d9b84037b9876853e99efa8b975263649547'


def historical_production_source():
    fixture = json.loads((Path(__file__).parent / 'fixtures/historical_production_source_96.json').read_text())
    production = fixture['production']
    # Explicit checks remain active under -OO; do not manufacture a passing pin.
    if (fixture['source_commit'] != SOURCE_COMMIT or
            fixture['production_src_sha256'] != SOURCE_SHA256 or
            len(production) != 96 or base.digest(production) != SOURCE_SHA256):
        raise ValueError('Historical production source fixture differs from immutable baseline')
    return production


def current_production_source(root):
    return {str(p.relative_to(root)): base.file_hash(p)
            for p in sorted((root / 'src').rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts and
            p.suffix not in ('.pyc', '.pyo') and
            not str(p.relative_to(root)).startswith(('src/hiroute.egg-info/','src/hiroute/'))}

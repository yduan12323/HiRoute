"""Bounded durable progress and conservative parser pushdown (no policy changes)."""
import json
import os
from pathlib import Path
import re
import tempfile

DENSE_FORMAT = 'pbf,pbf_dense_nodes=true'


def literal_exclusions(filters):
    """Push down only safe exact literals; multi-value matching stays downstream.

    Never turn `private` into `*private*`: osmium substrings are not Pyrosm's
    semicolon-delimited membership. Unknown expression syntax fails closed.
    """
    expressions = []
    for key, values in sorted(filters.items()):
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_:]+', key):
            raise ValueError('Unsupported filter key')
        if not isinstance(values, (list, tuple)):
            raise ValueError('Expected installed driving exclusion list')
        for value in sorted(set(values)):
            if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_:. -]+', value):
                raise ValueError('Unsupported exact filter literal')
            expressions.append('w/' + key + '=' + value)
    return expressions


def progress(path, stage, **details):
    """Replace one <=16 KiB progress record; fsync both file and directory."""
    path = Path(path)
    payload = json.dumps(dict(schema='hiroute.graph_progress.v1', stage=stage, **details),
                         sort_keys=True, allow_nan=False).encode() + b'\n'
    if len(payload) > 16384:
        raise ValueError('Progress record exceeds bound')
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    print(payload.decode().strip(), flush=True)

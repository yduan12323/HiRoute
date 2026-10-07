"""Lossless JSON container ownership and streaming canonical commitments.

These operations confer no mathematical acceptance. Only immutable scalar leaves
are shared when detaching. Freezing preserves repeated subtrees while detaching
all dictionaries, including externally backed mapping proxies.
"""
from fractions import Fraction
import hashlib
import json
import math
from types import MappingProxyType


def detach_json(value):
    if type(value) in (dict, MappingProxyType):
        if any(type(key) is not str for key in value):
            raise ValueError('JSON object keys must be strings')
        return {key: detach_json(child) for key, child in value.items()}
    if type(value) in (list, tuple):
        return [detach_json(child) for child in value]
    if type(value) in (str, int, bool, type(None)):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise ValueError('Unsupported or nonfinite JSON value')


def freeze_shared(value):
    memo, active = {}, set()
    def visit(item):
        if type(item) not in (dict, MappingProxyType, list, tuple):
            if type(item) in (str, int, bool, type(None)) or type(item) is float and math.isfinite(item):
                return item
            raise ValueError('Unsupported or nonfinite JSON value')
        key = id(item)
        if key in active:
            raise ValueError('Cyclic JSON container')
        if key in memo:
            return memo[key]
        active.add(key)
        if type(item) in (dict, MappingProxyType):
            if any(type(k) is not str for k in item):
                raise ValueError('JSON object keys must be strings')
            result = MappingProxyType({k: visit(v) for k, v in item.items()})
        else:
            children = tuple(visit(v) for v in item)
            result = item if type(item) is tuple and all(a is b for a,b in zip(item,children)) else children
        active.remove(key)
        memo[key] = result
        return result
    return visit(value)


def _default(value):
    if type(value) is MappingProxyType:
        return dict(value)
    if isinstance(value, Fraction):
        return str(value)
    raise TypeError('Unsupported canonical JSON value')


def canonical_chunks(value):
    """Exactly legacy canonical JSON, without newline, chunks <=64 KiB."""
    encoder = json.JSONEncoder(sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                               allow_nan=False, default=_default)
    for text in encoder.iterencode(value):
        for offset in range(0, len(text), 65536):
            yield text[offset:offset+65536].encode('ascii')


def stream_digest(value):
    digest = hashlib.sha256()
    for chunk in canonical_chunks(value):
        digest.update(chunk)
    return digest.hexdigest()


def query_digest(queries):
    digest = hashlib.sha256(b'[')
    for index, query in enumerate(queries):
        if index:
            digest.update(b',')
        for chunk in canonical_chunks(query):
            digest.update(chunk)
    digest.update(b']')
    return digest.hexdigest()

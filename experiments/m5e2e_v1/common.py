"""Small fail-closed identities, environment checks and immutable receipts."""
from __future__ import annotations
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

SCHEMA = 'hiroute.m5e2e.v1'
DOMAIN = 'real_map_microdomain_v1'
GIB = 1024 ** 3


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def load(path):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise ValueError('Duplicate JSON key: ' + k)
            result[k] = v
        return result
    return json.loads(Path(path).read_text(), object_pairs_hook=unique,
                      parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as f:
        f.write(canonical(value) + b'\n'); f.flush(); os.fsync(f.fileno())


def source_identity(source):
    source = Path(source).resolve()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(source), *args], text=True).strip()
    return dict(path=str(source), commit=git('rev-parse', 'HEAD'),
                tree=git('rev-parse', 'HEAD^{tree}'), dirty=bool(git('status', '--porcelain')))


def available_memory():
    try:
        fields = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
        return int(fields['MemAvailable'].split()[0]) * 1024
    except (OSError, KeyError, ValueError):
        return None


def installed_origins():
    origins = {}
    prefix = Path(sys.prefix).resolve()
    for name in ('timecut5', 'experiments.m5e2e_v1', 'validation.reference5',
                 'experiments.m6h_manifest_v1.supervisor'):
        module = importlib.import_module(name)
        origin = Path(module.__file__).resolve()
        origins[name] = dict(path=str(origin), installed=origin.is_relative_to(prefix),
                             sha256=file_hash(origin))
    return origins


def environment_admission(*, require_installed=True, available=None):
    """No safety relaxation for small machines or source-tree fallback."""
    memory = available_memory() if available is None else available
    reasons = []
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        reasons.append('unsupported_platform')
    if sys.version_info[:2] != (3, 11):
        reasons.append('requires_python_3_11')
    if memory is None or memory < 10 * GIB:
        reasons.append('insufficient_10GiB_host_reserve')
    origins = {}
    if require_installed:
        try:
            origins = installed_origins()
            if not all(row['installed'] for row in origins.values()):
                reasons.append('modules_not_installed')
        except (ImportError, OSError, TypeError) as exc:
            reasons.append('installation_incomplete:' + str(exc))
    return dict(status='READY' if not reasons else 'BLOCKED_INPUT_OR_ENVIRONMENT',
                reasons=reasons, platform=platform.platform(), machine=platform.machine(),
                python=sys.version, executable=sys.executable, memory_available_bytes=memory,
                host_reserve_bytes=10 * GIB, origins=origins,
                aggregate_memory_hard_limit=False,
                memory_control='inherited_per_process_AS_plus_sampled_tree_RSS_and_host_reserve')


def validate_domain(case):
    if case.get('domain_type') != DOMAIN or case.get('depth_mode') != 'declared_diagnostic_cap':
        raise ValueError('Not a declared E2E diagnostic domain')
    if case.get('H_ref') != 3 or case.get('case_id') not in ('E01', 'E02', 'E03'):
        raise ValueError('Unexpected case/depth')
    n = case.get('candidate_count')
    if type(n) is not int or not 0 <= n <= 4:
        raise ValueError('At most four real Sites permitted')


def verify_binding(path, expected):
    if file_hash(path) != expected:
        raise ValueError('Input identity mismatch: ' + str(path))


def installation_identity(source=None):
    import importlib.resources
    import importlib.metadata
    base=Path(importlib.import_module('experiments').__file__).resolve().parent.parent
    identity=load(base/'experiments/m5e2e_v1/source_identity.json')
    if identity.get('source_dirty') is not False:
        raise ValueError('Tools built from uncommitted source')
    if source is not None and identity['source_sha']!=source['commit']:
        raise ValueError('Installed tools not built from evaluated source')
    for relative,expected in identity['modules'].items():
        if file_hash(base/relative)!=expected:
            raise ValueError('Installed tools module changed: '+relative)
    for relative,expected in identity['production_modules'].items():
        if file_hash(base/relative)!=expected:
            raise ValueError('Installed production module differs: '+relative)
    return dict(source_sha=identity['source_sha'], tools_manifest_sha256=digest(identity),
        core_record_sha256=digest(importlib.metadata.distribution('hiroute').read_text('RECORD')),
        tools_record_sha256=digest(importlib.metadata.distribution('hiroute-e2e-tools').read_text('RECORD')),
        dependencies={d.metadata['Name']:d.version for d in importlib.metadata.distributions()},
        production_module_count=len(identity['production_modules']))

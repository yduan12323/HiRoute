"""Explicit root-reviewed recovery context; default and strict modes stay held."""
import hashlib
import json
import os
from pathlib import Path
from .contract import canonical
from .recovery_protocol import validate_protocol

# Only a reviewed SOURCE CHANGE can release this. Environment/CLI cannot.
ROOT_RELEASE = 'reviewed_disclosed_recovery_v1'
ROOT_REGISTRY_ADMISSION = {'gap_list_sha256': '3d4882dad7c0e761ad38ed7c53babc4460fa7abc0fee7aef82fc9c9db0b63077', 'purpose': 'new_map_correctness_and_performance_validation', 'registry_sha256': '6952853c9c25ee8e75a0db9dcc80465432d330e621b2ba0ea78a85c57c2e25be', 'schema': 'hiroute.m6h.recovered_exposure_registry.v1', 'strict_independent_holdout_claim': False}
ROOT_PREPROCESSING_SHA256 = '87d7d676810e81f4e43ca26ae1934bd47781e99250747f4c6fbf968859d64f5b'
ROOT_REGISTRY_BYTES_SHA256 = '6952853c9c25ee8e75a0db9dcc80465432d330e621b2ba0ea78a85c57c2e25be'
ROOT_CONTINUATION_ADMISSION_SHA256 = '443194eb0277bae3b8164d67809ee6814e133bc9a77290e81880c2704c40d191'
ENV = 'HIROUTE_DISCLOSED_RECOVERY_BINDING'


def load(binding):
    if ROOT_RELEASE != 'reviewed_disclosed_recovery_v1':
        raise PermissionError('Disclosed recovery root source/protocol release is held')
    if type(binding) is not dict or set(binding)!={'path','sha256'}:
        raise ValueError('Exact recovery configuration byte binding required')
    path=Path(binding['path'])
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError('Recovery config must be an absolute regular file')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=binding['sha256']:
        raise ValueError('Recovery config bytes changed')
    value=json.loads(raw)
    if canonical(value)!=raw:raise ValueError('Canonical recovery configuration required')
    if set(value)!={'protocol','repo','source','compiler','toolchain','exposure_binding',
                   'recovery_admission','preprocessing_config','transition_utc','continuation_admission'}:
        raise ValueError('Complete recovery configuration required')
    validate_protocol(value['protocol'])
    from .continuation import verify
    verify(value['continuation_admission'],expected_admission_sha256=ROOT_CONTINUATION_ADMISSION_SHA256)
    if value['recovery_admission']!=ROOT_REGISTRY_ADMISSION or ROOT_REGISTRY_ADMISSION is None:
        raise ValueError('Registry and gap list are not the root-reviewed admission')
    if value['preprocessing_config'].get('sha256')!=ROOT_PREPROCESSING_SHA256 or ROOT_PREPROCESSING_SHA256 is None:
        raise ValueError('Preprocessing configuration is not root-reviewed')
    if value['exposure_binding'].get('sha256')!=ROOT_REGISTRY_BYTES_SHA256 or ROOT_REGISTRY_BYTES_SHA256 is None:
        raise ValueError('Registry byte identity is not root-reviewed')
    from experiments.mechanism_recovery_v1 import run as base
    repo=Path(value['repo']).resolve()
    if repo!=Path(__file__).resolve().parents[2]:raise ValueError('Recovery repository differs')
    expected_names=set()
    for prefix in ('src','validation','scripts','experiments','configs'):
        expected_names.update(str(p.relative_to(repo)) for p in (repo/prefix).rglob('*')
            if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo'))
    expected_names.update(n for n in ('pyproject.toml','uv.lock','environment-linux-64.lock') if (repo/n).is_file())
    if set(value['source']['closure'])!=expected_names:
        raise ValueError('Incomplete or expanded recovery executable closure')
    for name,expected in value['source']['closure'].items():
        p=repo/name
        if p.resolve().is_relative_to(repo) is False or base.file_hash(p)!=expected:
            raise ValueError('Recovery source closure changed: '+name)
    for key in ('preprocessing_config','exposure_binding'):
        b=value[key]
        if type(b) is not dict or set(b)!={'path','sha256'}:
            raise ValueError('Exact external byte binding required: '+key)
        p=Path(b['path'])
        if not p.is_absolute() or p.is_symlink():raise ValueError('Absolute regular binding required')
        if base.file_hash(p)!=b['sha256']:raise ValueError('External recovery bytes changed: '+key)
    # Never parse the registry in owner/preprocessing processes. The separately
    # supervised validator authenticates semantic admission and exits before graph.
    return value


def activate(binding):
    value=load(binding)
    os.environ[ENV]=json.dumps(binding,sort_keys=True)
    return value


def require_active():
    # Held check before external path access, even if an environment is supplied.
    if ROOT_RELEASE != 'reviewed_disclosed_recovery_v1':
        raise PermissionError('M6 real launch held for reviewed disclosed recovery release')
    if ENV not in os.environ:raise PermissionError('Strict real launch remains held')
    return load(json.loads(os.environ[ENV]))


def preprocessing_config_path():
    return Path(require_active()['preprocessing_config']['path'])

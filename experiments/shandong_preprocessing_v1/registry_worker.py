"""One-shot existing exposure validation; invoke under the shared supervisor.

No registry object is returned to the parent. This validates supplied bytes and
schema only, not the truth or completeness of their claimed historical coverage.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from experiments.m6h_selection_v1.rules import validate_exposures
from experiments.m6h_manifest_v1.supervisor import _atomic


def validate(path, expected_sha256, expected_canonical_sha256, max_bytes, recovery_admission=None):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=max_bytes:
        raise ValueError('Registry file exceeds bound or is not regular')
    def bounded_hash():
        result=hashlib.sha256(); count=0
        with path.open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):
                count+=len(block)
                if count>max_bytes:raise ValueError('Registry grew beyond byte bound')
                result.update(block)
        return result
    h=bounded_hash()
    if h.hexdigest()!=expected_sha256:raise ValueError('Registry byte digest mismatch')
    def unique(pairs):
        obj={}
        for key,value in pairs:
            if key in obj:raise ValueError('Duplicate registry JSON key')
            obj[key]=value
        return obj
    with path.open('rb') as f:
        payload=f.read(max_bytes+1)
    if len(payload)>max_bytes:raise ValueError('Registry grew beyond byte bound')
    registry=json.loads(payload,object_pairs_hook=unique,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
    del payload
    canonical=hashlib.sha256()
    encoder=json.JSONEncoder(sort_keys=True,separators=(',',':'),allow_nan=False)
    for chunk in encoder.iterencode(registry):canonical.update(chunk.encode())
    if canonical.hexdigest()!=expected_canonical_sha256:raise ValueError('Registry canonical digest mismatch')
    if recovery_admission is None:
        pairs,inspected=validate_exposures(registry)
    else:
        from experiments.m6h_selection_v1.rules import validate_recovered_exposures
        pairs,inspected=validate_recovered_exposures(registry,recovery_admission)
    # Rehash prevents accepting a mutable file switched between hash and parse.
    h2=bounded_hash()
    if h2.hexdigest()!=expected_sha256:raise ValueError('Registry changed during validation')
    return dict(byte_sha256=h.hexdigest(),canonical_sha256=canonical.hexdigest(),
                exposure_pairs=len(pairs),inspected_endpoints=len(inspected))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--path',required=True);p.add_argument('--sha256',required=True)
    p.add_argument('--canonical-sha256',required=True);p.add_argument('--max-bytes',type=int,required=True)
    p.add_argument('--recovery-admission')
    a=p.parse_args()
    admission=None
    if a.recovery_admission:
        from experiments.m6h_manifest_v1.recovery_runtime import require_active
        active=require_active()
        admission=json.loads(a.recovery_admission)
        if admission!=active['recovery_admission']:raise ValueError('Registry worker admission differs')
    result=validate(a.path,a.sha256,a.canonical_sha256,a.max_bytes,recovery_admission=admission)
    _atomic(Path(os.environ['HIROUTE_WORKER_RECEIPT']),dict(status='COMPLETED',result=result))

if __name__=='__main__':main()

"""One original-process retry, or deterministic admission-only regressions.

No solver/data imports, no assertion/limit edits. Original test bytes are loaded
from the failed commit. Only post-run temporary-directory copying is added so
the original assertion cannot delete the receipt needed to explain its failure.
"""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
FAILED='0f486300d931558d072ce05a6fcc4c42d4b70027'
TEST='tests/m5d_recovery/test_m6h_held_manifest.py'
LOGICAL=('test_drift_stops_whole_queue',
         'test_resource_stop_before_drift_delivery_is_not_an_admitted_identity',
         'test_full_identity_and_replay')


def run(output,original=False):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    if original and (sys.platform!='linux' or sys.flags.optimize!=2):
        raise ValueError('the single original process retry requires Linux -OO')
    source=(subprocess.check_output(['git','show',FAILED+':'+TEST],cwd=ROOT)
            if original else (ROOT/TEST).read_bytes())
    path=output/'test_source.py';path.write_bytes(source)
    spec=importlib.util.spec_from_file_location('retained_drift_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    captures=[]
    real_temporary=module.tempfile.TemporaryDirectory
    class RetainedTemporary(real_temporary):
        def __exit__(self,*args):
            try:
                destination=output/f'retained-{len(captures):03d}'
                files=[p for p in Path(self.name).rglob('*') if p.is_file()]
                if sum(p.stat().st_size for p in files)>32*1024**2:
                    raise RuntimeError('diagnostic capture size exceeded')
                # Run is already terminal; this copy does not consume phase time.
                shutil.copytree(self.name,destination)
                captures.append(str(destination))
            finally:
                super().__exit__(*args)
            return False
    names=('test_drift_stops_whole_queue',) if original else LOGICAL
    suite=unittest.TestSuite(module.ContractTests(name) for name in names)
    stream=io.StringIO()
    with patch.object(module.tempfile,'TemporaryDirectory',RetainedTemporary):
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    ledgers=[]
    for directory in captures:
        for ledger_path in Path(directory).rglob('ledger.json'):
            ledger=json.loads(ledger_path.read_text())
            ledgers.append(dict(path=str(ledger_path),status=ledger['status'],
                stages=[dict(id=r['id'],status=r['status'],error=r.get('error'),
                    receipt_status=r.get('receipt',{}).get('status'),
                    reason=r.get('receipt',{}).get('reason'),
                    returncode=r.get('receipt',{}).get('returncode'),
                    cleanup_verified=r.get('receipt',{}).get('cleanup_verified'),
                    phase_entered_monotonic=r.get('receipt',{}).get('phase_entered_monotonic'))
                    for r in ledger['stages']]))
    summary=dict(mode='original_process_retry_once' if original else 'deterministic_admission_only',
        failed_source=FAILED,execution_source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        test_source_sha256=hashlib.sha256(source).hexdigest(),original_test_bytes_used=original,
        original_queue_assertions_and_limits_preserved=True,
        working_tree_dirty=bool(subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT)),
        sys_optimize=sys.flags.optimize,python=sys.version,platform=sys.platform,
        affinity=sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else None,
        imported_numeric_packages=[n for n in ('hiroute','timecut5','z3','numpy') if n in sys.modules],
        tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),passed=result.wasSuccessful(),
        output=stream.getvalue(),captures=captures,ledgers=ledgers,
        limits=dict(cpu=3,actor_cpu_s=1,startup_inclusive_wall_s=5,phase_s=.2,address_space_bytes=256*1024**2))
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(stream.getvalue(),flush=True)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('ledgers','captures','output')}),flush=True)
    return result.wasSuccessful()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    parser.add_argument('--original-process-retry',action='store_true')
    args=parser.parse_args()
    raise SystemExit(0 if run(args.output,args.original_process_retry) else 1)

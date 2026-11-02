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


def collect_ledgers(captures):
    """Read the queue ledger, not per-supervisor auxiliary ledger.json files."""
    ledgers=[]
    for directory in captures:
        path=Path(directory)/'run/ledger.json'
        ledger=json.loads(path.read_text())
        if not isinstance(ledger.get('stages'),list):
            raise ValueError('captured queue ledger lacks stages')
        ledgers.append(dict(path=str(path),status=ledger['status'],
            stages=[dict(id=r['id'],status=r['status'],error=r.get('error'),
                receipt_status=r.get('receipt',{}).get('status'),
                reason=r.get('receipt',{}).get('reason'),
                returncode=r.get('receipt',{}).get('returncode'),
                cleanup_verified=r.get('receipt',{}).get('cleanup_verified'),
                phase_entered_monotonic=r.get('receipt',{}).get('phase_entered_monotonic'))
                for r in ledger['stages']]))
    return ledgers


def original_assertion_conditions(ledger):
    return (ledger['status']=='INTEGRITY_FAILED' and
            all(s['status']=='BLOCKED_INTEGRITY_FAILED' for s in ledger['stages'][2:]))


def recover_existing(source_root,output):
    """Offline receipt recovery only; never executes a test or a worker."""
    root=Path(source_root);out=Path(output);out.mkdir(parents=True,exist_ok=False)
    captures=sorted(str(p) for p in root.glob('retained-*'))
    ledgers=collect_ledgers(captures)
    if len(ledgers)!=1:raise ValueError('ambiguous original retry capture')
    source=(root/'test_source.py').read_bytes()
    expected=subprocess.check_output(['git','show',FAILED+':'+TEST],cwd=ROOT)
    if source!=expected:raise ValueError('captured original test bytes differ')
    raw=json.loads((Path(captures[0])/'run/ledger.json').read_text())
    report=dict(mode='offline_receipts_only_no_test_execution',failed_source=FAILED,
        original_source_bytes_match=True,test_source_sha256=hashlib.sha256(source).hexdigest(),
        original_assertion_conditions_satisfied=original_assertion_conditions(raw),
        unittest_result_was_not_saved_before_collector_error=True,
        diagnostic_CI_status='failure',collector_error="KeyError: 'stages'",ledgers=ledgers)
    (out/'recovered.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return True


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
    # A later collector error must not erase the actual unittest outcome.
    (output/'unittest-result.json').write_text(json.dumps(dict(tests_run=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),passed=result.wasSuccessful(),
        output=stream.getvalue()),indent=2)+'\n')
    ledgers=collect_ledgers(captures)
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
    parser.add_argument('--summarize-existing')
    args=parser.parse_args()
    if args.summarize_existing and args.original_process_retry:
        parser.error('offline recovery cannot launch a retry')
    success=(recover_existing(args.summarize_existing,args.output) if args.summarize_existing
             else run(args.output,args.original_process_retry))
    raise SystemExit(0 if success else 1)

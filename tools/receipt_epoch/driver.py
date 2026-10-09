"""Pinned metadata-only CLI; bootstrap has no verifier imports before attestation."""
import argparse
import hashlib
import importlib.util
import importlib.abc
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def parser():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('operation', choices=('fingerprint','authenticate-retained','private-worker'))
    p.add_argument('--tool-root', type=Path, required=True)
    p.add_argument('--tool-commit', required=True)
    p.add_argument('--verifier-root', type=Path, required=True)
    p.add_argument('--verifier-commit', required=True)
    for name in ('tool-source-sha','verifier-source-sha','verifier-import-sha','python-realpath','python-sha'):
        p.add_argument('--'+name)
    p.add_argument('--policy',type=Path)
    p.add_argument('--policy-sha')
    p.add_argument('--prefix-handoff',type=Path)
    p.add_argument('--prefix-handoff-sha')
    p.add_argument('--retained-window-return',nargs=2,action='append',default=[],metavar=('FILE','SHA256'))
    p.add_argument('--audit-log',type=Path)
    return p


def package(args):
    """Precheck every tool source against its fixed Git object before loading it.

    The executing script is independently selected by the owning operator. This
    check prevents importing an unreviewed sibling origin/helper or package.
    """
    root = args.tool_root.absolute()
    commit = args.tool_commit
    if len(commit)!=40 or any(c not in '0123456789abcdef' for c in commit): raise ValueError('full tool commit required')
    directory = root/'tools/receipt_epoch'
    if Path(__file__).absolute() != directory/'driver.py': raise ValueError('CLI is outside selected tool checkout')
    expected = subprocess.check_output(['git','-C',str(root),'ls-tree','-rz','--name-only',commit,'--','tools/receipt_epoch'],timeout=10)
    names = sorted(name.decode() for name in expected.split(b'\0') if name.endswith(b'.py'))
    actual = sorted(p.relative_to(root).as_posix() for p in directory.rglob('*.py'))
    if actual != names: raise ValueError('tool bootstrap namespace differs from fixed commit')
    verified={}
    for name in names:
        path=root/name
        if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1: raise ValueError('tool bootstrap source alias')
        expected=subprocess.check_output(['git','-C',str(root),'show',commit+':'+name],timeout=10)
        if path.read_bytes()!=expected: raise ValueError('uncommitted tool bootstrap source: '+name)
        verified[name]=expected
    name='hiroute_receipt_epoch_review'
    class Loader(importlib.abc.Loader):
        def __init__(self,path,raw):self.path,self.raw=path,raw
        def create_module(self,spec):return None
        def exec_module(self,module):
            module.__file__=str(self.path)
            exec(compile(self.raw,str(self.path),'exec',dont_inherit=True,optimize=sys.flags.optimize),module.__dict__)
    class Finder(importlib.abc.MetaPathFinder):
        def find_spec(self,fullname,path=None,target=None):
            if fullname!=name and not fullname.startswith(name+'.'):return None
            relative='tools/receipt_epoch/'+(fullname[len(name)+1:].replace('.','/') if fullname!=name else '')
            for filename,is_package in ((relative+'/__init__.py',True),(relative+'.py',False)):
                filename=filename.replace('//','/')
                if filename in verified:
                    return importlib.util.spec_from_file_location(fullname,root/filename,
                        loader=Loader(root/filename,verified[filename]),
                        submodule_search_locations=[str((root/filename).parent)] if is_package else None)
            raise ImportError('unreviewed private tool import')
    sys.meta_path.insert(0,Finder())
    importlib.import_module(name)
    return name


def contract(args):
    fields=('tool_source_sha','verifier_source_sha','verifier_import_sha','python_realpath','python_sha')
    if any(getattr(args,key) is None for key in fields): raise ValueError('complete independent source/interpreter contract required')
    return dict(tool_root=str(args.tool_root.absolute()),tool_commit=args.tool_commit,
        verifier_root=str(args.verifier_root.absolute()),verifier_commit=args.verifier_commit,
        **{key:getattr(args,key) for key in fields})


def worker_argv(args):
    result=[sys.executable,'-I','-B',str(args.tool_root.absolute()/'tools/receipt_epoch/driver.py'),'private-worker']
    for key,value in contract(args).items(): result += ['--'+key.replace('_','-'),value]
    return result


def main():
    if not sys.flags.isolated: raise ValueError('run pinned metadata CLI with python -I -B')
    args=parser().parse_args()
    # A private empty prefix avoids loading inherited/shared bytecode. -B alone
    # disables writes but does not disable reading old .pyc files.
    with tempfile.TemporaryDirectory(prefix='hiroute-epoch-bootstrap-') as cache:
        sys.pycache_prefix=cache;sys.dont_write_bytecode=True
        name=package(args)
        origin=importlib.import_module(name+'.origin')
        if args.operation=='fingerprint':
            facts,_,_,_=origin.inspect(args.tool_root,args.tool_commit,args.verifier_root,args.verifier_commit,time.monotonic()+10)
            print(json.dumps(facts,sort_keys=True));return
        bound=origin.SourceBinding(contract(args))
        # Project imports use safe consumed source bytes from the approved
        # original checkout. Never add an unfiltered project root to sys.path,
        # where an untracked math.py could otherwise shadow the standard library.
        root=str(args.verifier_root.absolute());src=str(args.verifier_root.absolute()/'src')
        sys.path[:]=[entry for entry in sys.path if entry and
            Path(entry).absolute() not in (args.tool_root.absolute(),Path(__file__).absolute().parent)]
        sys.meta_path.insert(0,origin.VerifierFinder(root,bound._imported))
        sidecar=importlib.import_module(name+'.sidecar')
        if args.operation=='private-worker':
            sidecar.serve(sys.stdin.buffer,sys.stdout.buffer,origin=bound);return
        if any(value is None for value in (args.policy,args.policy_sha,args.prefix_handoff,args.prefix_handoff_sha,args.audit_log)):
            raise ValueError('policy, independently pinned actual prefix and exclusive audit-log required')
        from experiments.time_cut_v2.recorded_real.bootstrap_executor import validate_pinned_policy
        from experiments.time_cut_v2.recorded_real.archive_reader import _pairs,_nonfinite
        def pinned(path,sha,limit):
            origin.hex_value(sha,64)
            raw, row, _=origin.consume(path,limit=limit)
            origin.require(row['sha256']==sha,'independently pinned CLI input changed')
            return json.loads(raw,object_pairs_hook=_pairs,parse_constant=_nonfinite)
        policy=pinned(args.policy,args.policy_sha,65536)
        sources=validate_pinned_policy(policy,args.policy_sha)
        prefix=pinned(args.prefix_handoff,args.prefix_handoff_sha,sidecar.MAX_FRAME)
        # Only actual pointer pins are consumed. Passed/cold/cache status fields
        # have no authority: the new sidecar always fully reconciles this prefix.
        actual=prefix['actual']
        environment=dict(os.environ,PYTHONPATH=os.pathsep.join((root,src)),PYTHONNOUSERSITE='1')
        parent=None
        with args.audit_log.open('xb') as log:
            def event(value):
                raw=origin.canonical(value)+b'\n'
                origin.require(log.tell()+len(raw)<=16*1024**2,'metadata-only audit log cap')
                log.write(raw);log.flush();os.fsync(log.fileno())
                print(raw.decode(),end='',flush=True)
            try:
                parent=sidecar.Parent(worker_argv(args),cwd=root,env=environment,
                    expected_source_contract=bound.expected,
                    stderr_path=args.audit_log.with_name(args.audit_log.name+'.worker.stderr'))
                result=parent.call('establish',dict(actual=actual,code_pins=bound.pins,reviewed_sources=sources))
                event(dict(operation='establish',result=result,source_contract=bound.expected,actual=actual))
                for filename,sha in args.retained_window_return:
                    returned=pinned(Path(filename),sha,sidecar.MAX_FRAME)
                    origin.require(returned.get('status')=='registered','actual retained controller registration required')
                    new={key:returned[key] for key in ('registry','registration_return','runtime_return')}
                    metadata=pinned(Path(new['registry']['path']),new['registry']['sha256'],16*1024**2)
                    targets={key:new[key]['path'] for key in new}
                    targets['attempt']=metadata['entries'][-1]['attempt']
                    prepared=parent.call('prepare',dict(targets=targets))
                    event(dict(operation='prepare',result=prepared,retained_controller_return=dict(path=filename,sha256=sha)))
                    result=parent.call('cold',dict(token=prepared['token'],actual=new))
                    event(dict(operation='cold',result=result))
                parent.call('pause',{})
                parent.call('close',{})
                event(dict(operation='closed-at-safe-boundary',numerical_launches=0,collector_started=False,
                           disk_epoch_resume=False,final_independent_reconcile_required=True))
            except BaseException as error:
                event(dict(operation='failed-stopped',error_type=type(error).__name__,message=str(error),
                           child=parent.diagnostic() if parent is not None else None,automatic_retry=False))
                raise
            finally:
                if parent is not None: parent.invalidate()


if __name__=='__main__': main()

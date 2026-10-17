"""One explicit bounded stage; no automatic retry, overlap, or hidden next run."""
import fcntl,json,os,resource,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
from phase_supervisor import run,Limits,sha,atomic,PhaseWatchdog,identity_digest
ORDER=[('flat','search'),('flat','verify'),('hier','search'),('hier','verify')]


def main():
    if len(sys.argv)!=6 or sys.argv[3]!='--approved-manifest-sha256' or sys.argv[5]!='--exclusive-slot-granted':
        raise SystemExit('METHOD MODE --approved-manifest-sha256 HASH --exclusive-slot-granted')
    method,mode,approved=sys.argv[1],sys.argv[2],sys.argv[4]
    if (method,mode) not in ORDER:raise ValueError('Unknown method/stage')
    manifest=ROOT/'launch_manifest.json'
    if sha(manifest)!=approved:raise ValueError('Manifest differs from reviewed hash')
    spec=json.loads(manifest.read_bytes())
    if spec.get('schema')!='hiroute.combined_checkpoint_launch.v1' or spec.get('launchable') is not True:
        raise ValueError('Launch manifest not admitted')
    parent=(50,60) if mode=='search' else (20,25)
    resource.setrlimit(resource.RLIMIT_CPU,(parent[0],resource.getrlimit(resource.RLIMIT_CPU)[1]))
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    cpu_start=time.process_time()
    with (ROOT/'ledger.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        lp=ROOT/'ledger.json'
        ledger=json.loads(lp.read_bytes()) if lp.exists() else dict(schema='hiroute.combined_checkpoint_ledger.v1',
            manifest_sha256=approved,attempts=[],blocked=False,total_reserved_cpu_s=1160,
            preparation_cpu_debit_s=120,preparation_debit_kind='conservative allowance, not measured entire development cost')
        if ledger['manifest_sha256']!=approved or ledger['blocked'] or ledger['total_reserved_cpu_s']!=1160:
            raise ValueError('Invalid or blocked ledger')
        previous=[(a['method'],a['mode']) for a in ledger['attempts']]
        if len(previous)>=len(ORDER) or previous!=ORDER[:len(previous)] or (method,mode)!=ORDER[len(previous)] or any(a['state']!='finished' for a in ledger['attempts']):
            raise ValueError('Stages must be unique and sequential')
        reservation=370 if mode=='search' else 150
        ledger['attempts'].append(dict(method=method,mode=mode,state='reserved',reserved_cpu_s=reservation));atomic(lp,ledger)
        receipt=None;charged=None
        try:
            for name,digest in spec['source_sha256'].items():
                if sha(ROOT.parents[1]/name)!=digest:raise ValueError('Reviewed source changed: '+name)
            out=ROOT/(mode+'_'+method)
            if out.exists():raise ValueError('Fresh stage output required')
            identity=dict(method=method,manifest_sha256=approved,effective_query_sha256=spec['effective_exact_query_sha256'],
                domain_sha256=spec['domain_binding']['sparse_domain_sha256'],source_closure_sha256=identity_digest(spec['source_sha256']))
            watchdog=PhaseWatchdog(out/'exact_started.json',identity,180,120) if mode=='search' else None
            read_fd,write_fd=os.pipe()
            os.write(write_fd,json.dumps(dict(parent_pid=os.getpid(),manifest_sha256=approved,method=method,mode=mode)).encode());os.close(write_fd)
            try:
                receipt=run([sys.executable,str(ROOT/'worker.py'),str(out),approved,method,str(read_fd),mode],
                    output_dir=ROOT/('supervision_'+mode+'_'+method),
                    limits=Limits(wall_seconds=300 if mode=='search' else 120,cpu_seconds=295 if mode=='search' else 115,
                        address_space_bytes=8*1024**3,cpu=min(os.sched_getaffinity(0))),pass_fds=(read_fd,),
                    parent_cpu_limit=parent,phase_watchdog=watchdog,
                    extra_env={'MPLCONFIGDIR':str(ROOT/('cache_'+mode+'_'+method)/'mpl'),'XDG_CACHE_HOME':str(ROOT/('cache_'+mode+'_'+method)/'xdg')})
            finally:os.close(read_fd)
            charged=receipt['conservative_wait4_cpu_seconds']+time.process_time()-cpu_start
            reason=receipt['reason'];resource_censored=reason in ('preparation_wall_timeout','exact_wall_timeout','total_wall_timeout','wall_timeout','cpu_limit')
            if reason=='worker_failed' and (out/'error.json').exists():resource_censored=json.loads((out/'error.json').read_bytes()).get('type')=='MemoryError'
            result_name='exact_result.json' if mode=='search' else 'verification_result.json'
            if reason=='success' and not (out/result_name).is_file():raise ValueError('Successful worker lacks result')
            if mode=='search' and reason=='success' and receipt.get('phase_watchdog',{}).get('marker') is None:raise ValueError('Missing exact-start marker')
            result=json.loads((out/result_name).read_bytes()) if (out/result_name).is_file() else None
            witness_file=out/'witness_verification_result.json'
            partial_witness=json.loads(witness_file.read_bytes()) if witness_file.is_file() else None
            ledger['blocked']=charged>reservation or not receipt['cleanup_verified'] or (reason!='success' and not resource_censored)
            ledger['attempts'][-1].update(state='finished',receipt=receipt,charged_conservative_cpu_s=charged,
                status='resource_censored_incomplete' if resource_censored else reason,result=result,
                separately_verified_witness=partial_witness,layer_recovery_complete=bool(result and result.get('layer_status')=='same_domain_completed_layer_reconstructed'))
            atomic(lp,ledger)
            print(json.dumps(dict(method=method,mode=mode,status=ledger['attempts'][-1]['status'],blocked=ledger['blocked'],charged_cpu_s=charged)))
        except BaseException as error:
            ledger['blocked']=True
            ledger['attempts'][-1].update(state='failed',error=type(error).__name__+': '+str(error),
                receipt=receipt,charged_conservative_cpu_s=charged if charged is not None else reservation,
                charge_kind='measured_conservative_receipt_plus_parent' if charged is not None else 'full_reservation_debit_measurement_unavailable',
                observed_parent_cpu_s=time.process_time()-cpu_start)
            atomic(lp,ledger);raise

if __name__=='__main__':main()

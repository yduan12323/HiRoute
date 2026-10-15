"""One invocation admits one cold method. No automatic retry or hidden preflight."""
import sys,os,json,time,fcntl,resource,signal
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'optimized_od06_phase2/runner'))
from cloud_adapter import run,Limits,sha,atomic

def setup_state(out,success=False):
    phases=out/'phases.jsonl'
    entered=any(json.loads(line).get('stage')=='exact_engine_started' for line in phases.read_text().splitlines()) if phases.exists() else False
    required=['feasible_incumbent.json','landmark_certificate.json','runtime_policy.json']
    missing=[name for name in required if not (out/name).exists()]
    if (success or entered) and missing:raise ValueError('Required exact setup artifacts missing: '+','.join(missing))
    return dict(exact_entered=entered,setup_complete=not missing,missing=missing)

def compare_rows(first,second):
    astate=setup_state(first,(first/'exact_result.json').exists());bstate=setup_state(second,(second/'exact_result.json').exists())
    if not astate['setup_complete'] or not bstate['setup_complete']:
        return dict(initial_state_comparison='unavailable_preparation_censored',first=astate,second=bstate,terminal_comparison='unavailable')
    for fn,key in [('feasible_incumbent.json','initial_witness_cache_sha256'),('landmark_certificate.json',None),('runtime_policy.json','region_tree_sha256')]:
        va,vb=json.loads((first/fn).read_bytes()),json.loads((second/fn).read_bytes())
        if (va[key] if key else va)!=(vb[key] if key else vb):raise ValueError('Paired initial state mismatch: '+fn)
    terminal='unavailable_search_censored'
    if (first/'exact_result.json').exists() and (second/'exact_result.json').exists():
        a=json.loads((first/'exact_result.json').read_bytes());b=json.loads((second/'exact_result.json').read_bytes())
        fields=['status','key','primary_infimum','secondary_infimum','unattained_component']
        if {k:a[k] for k in fields}!={k:b[k] for k in fields}:raise ValueError('Completed FLAT/HIER terminal mismatch')
        terminal='equal'
    return dict(initial_state_comparison='equal',terminal_comparison=terminal)

def main():
    if len(sys.argv)!=4 or sys.argv[1] not in ('flat','hier') or sys.argv[2]!='--approved-manifest-sha256':raise SystemExit('Require METHOD --approved-manifest-sha256 REVIEWED_HASH')
    method,approved=sys.argv[1],sys.argv[3]
    start=time.process_time()
    resource.setrlimit(resource.RLIMIT_CPU,(50,resource.getrlimit(resource.RLIMIT_CPU)[1]))
    def controller_stop(signum,frame):raise RuntimeError('Controller signal stop: '+str(signum))
    for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGXCPU):signal.signal(sig,controller_stop)
    # Supervisor and worker share the same core, bounding aggregate CPU work
    # under the wall allowance rather than silently adding a second busy core.
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    # Lock and reserve BOTH method allowances before any source/input hashing.
    # Reading this small controller/spec is admission bookkeeping, not graph prep.
    with (ROOT/'exact_ledger.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        lp=ROOT/'exact_ledger.json'
        ledger=json.loads(lp.read_bytes()) if lp.exists() else dict(schema='hiroute.bounded_sparse_exact_ledger.v1',manifest_sha256=approved,phase_reserved_cpu_s=1340,preparation_cpu_debit_s=120,preparation_debit_kind='separate conservative allowance; not a measured full development CPU total',total_reserved_and_preparation_cpu_s=1460,method_reservations={'flat':670,'hier':670},attempts=[],blocked=False)
        if ledger.get('phase_reserved_cpu_s')!=1340 or ledger.get('method_reservations')!={'flat':670,'hier':670} or ledger.get('preparation_cpu_debit_s')!=120:raise ValueError('Reserved phase allowance differs')
        if ledger['manifest_sha256']!=approved or ledger.get('blocked') or any(x['state']!='finished' for x in ledger['attempts']) or any(x['method']==method for x in ledger['attempts']):raise ValueError('No valid unused reservation')
        if (method=='flat' and ledger['attempts']) or (method=='hier' and [x['method'] for x in ledger['attempts']]!=['flat']):raise ValueError('Protocol method ordering differs')
        ledger['attempts'].append(dict(method=method,state='reserved',reserved_cpu_s=670));atomic(lp,ledger)
        try:
            manifest=ROOT/'exact_manifest.json'
            if sha(manifest)!=approved:raise ValueError('Manifest differs from review approval')
            out=ROOT/('exact_'+method)
            cache=ROOT/('cache_'+method);cache.mkdir(exist_ok=False)
            guard_read,guard_write=os.pipe()
            os.write(guard_write,json.dumps(dict(parent_pid=os.getpid(),manifest_sha256=approved,method=method)).encode());os.close(guard_write)
            try:
                r=run([sys.executable,str(ROOT/'exact_worker.py'),str(out),approved,method,str(guard_read)],output_dir=ROOT/('supervision_'+method),limits=Limits(wall_seconds=600,cpu_seconds=595,address_space_bytes=8*1024**3,cpu=min(os.sched_getaffinity(0))),pass_fds=(guard_read,),parent_cpu_limit=(50,60),extra_env={'MPLCONFIGDIR':str(cache/'mpl'),'XDG_CACHE_HOME':str(cache/'xdg')})
            finally:os.close(guard_read)
            charged=r['conservative_wait4_cpu_seconds']+time.process_time()-start
            result_path=out/'exact_result.json'
            reason=r['reason']
            if reason=='success' and not result_path.exists():raise ValueError('Worker success without terminal result')
            # Only ordinary hard resource censoring permits the second row.
            resource_censor=reason in ('wall_timeout','cpu_limit')
            if reason=='worker_failed' and (out/'error.json').exists():resource_censor=json.loads((out/'error.json').read_bytes()).get('type')=='MemoryError'
            ledger['blocked']=charged>670 or not r['cleanup_verified'] or (reason!='success' and not resource_censor)
            ledger['attempts'][-1].update(state='finished',receipt=r,charged_conservative_cpu_s=charged,status='resource_censored_incomplete' if resource_censor else reason)
            ledger['attempts'][-1]['setup_state']=setup_state(out,reason=='success')
            if method=='hier':ledger['paired_comparison']=compare_rows(ROOT/'exact_flat',out)
            atomic(lp,ledger)
            print(json.dumps(dict(method=method,status=ledger['attempts'][-1]['status'],blocked=ledger['blocked'],charged_cpu_s=charged)))
        except BaseException as e:
            ledger['blocked']=True;ledger['attempts'][-1].update(state='failed',error=type(e).__name__+': '+str(e));atomic(lp,ledger);raise
if __name__=='__main__':main()

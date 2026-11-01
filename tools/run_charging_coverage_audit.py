"""One guarded data-only audit; retain cumulative preparation reservations."""
from contextlib import ExitStack
from dataclasses import asdict
import argparse,json,os,sys,time
from pathlib import Path
from hiroute.runtime import run_supervised
from profile_small_cases import mac_monitors


def main(a):
    cfg=json.loads(Path(a.config).read_text());limits=cfg['resources']
    root=Path(a.inputs).resolve().parent
    if not (root/'acquisition.json').exists():raise ValueError('completed acquisition receipt required')
    acquired=json.loads((root/'acquisition.json').read_text())
    output=Path(a.output).resolve()
    if output.exists():raise FileExistsError(output)
    receipt=root/(output.name+'.guard.json')
    if receipt.exists():raise FileExistsError(receipt)
    previous=list(root.glob('*.guard.json'))
    consumed=0.
    for p in previous:
        row=json.loads(p.read_text())
        if row.get('status') not in ('complete','failed'):raise ValueError('uncertain prior attempt; inspect before restart')
        consumed+=row['conservative_processing_cpu_charge_s']
    remaining=limits['processing_worker_cpu_cap_s']-consumed
    if remaining<=1:raise ValueError('original preparation CPU reservation exhausted')
    origin=acquired.get('preparation_started_unix_s')
    if not isinstance(origin,(int,float)):raise ValueError('recorded preparation start required; no wall-budget reset')
    elapsed=time.time()-origin
    wall=limits['preprocessing_wall_cap_s']-elapsed
    if wall<=0:raise ValueError('original preparation wall cap exhausted')
    import shutil
    if shutil.disk_usage(root).free<limits['disk_headroom_bytes']:raise ValueError('disk headroom insufficient')
    env={**os.environ,'PYTHONPATH':'src:tools',**{k:'1' for k in (
        'OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS',
        'NUMEXPR_NUM_THREADS','OSMIUM_POOL_THREADS')}}
    argv=[a.data_python,'-u','tools/audit_shandong_charging.py','--config',a.config,
        '--inputs',a.inputs,'--historical-inputs',a.historical_inputs,'--output',str(output)]
    with receipt.open('x') as f:json.dump(dict(status='pending',reserved_processing_cpu_s=remaining),f)
    with ExitStack() as stack:
        if sys.platform=='darwin':mac_monitors(stack)
        result=run_supervised(argv,timeout_s=wall,cpu_limit_s=remaining-1,
            memory_limit_bytes=limits['preprocessing_process_rss_cap_bytes'],
            host_min_available_bytes=limits['host_headroom_bytes'],memory_poll_s=.1,
            cwd=str(Path(__file__).resolve().parents[1]),env=env)
    (root/(output.name+'.stdout.log')).write_bytes(result.stdout)
    (root/(output.name+'.stderr.log')).write_bytes(result.stderr)
    summary=output/'summary.json'
    success=result.returncode==0 and summary.exists() and not any((result.timed_out,
        result.cpu_limited,result.memory_limited,result.host_headroom_limited))
    # Failed attempts lacking a completed worker CPU receipt consume their full
    # reservation; never reset accounting to manufacture a successful retry.
    actual=json.loads(summary.read_text()).get('preparation_cpu_s',0) if success else remaining
    charge=max(actual,result.cpu_peak_s)+1 if success else remaining
    row=dict(status='complete' if success else 'failed',returncode=result.returncode,
        conservative_processing_cpu_charge_s=charge,prior_processing_cpu_charge_s=consumed,
        setup_acquisition_cpu_precharge_s=limits['setup_acquisition_cpu_precharge_s'],
        conservative_preparation_cpu_charge_s=limits['setup_acquisition_cpu_precharge_s']+consumed+charge,
        remaining_preparation_cpu_s=max(0,limits['processing_worker_cpu_cap_s']-consumed-charge),
        supervisor={k:v for k,v in asdict(result).items() if k not in ('stdout','stderr')})
    receipt.write_text(json.dumps(row,indent=2)+'\n');print(json.dumps(row,sort_keys=True))
    if not success:raise SystemExit(1)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('config','inputs','historical-inputs','data-python','output'):p.add_argument('--'+key,required=True)
    main(p.parse_args())

"""Separate, one-shot consumer of an immutable historical selected-leg table.

Never rewrites producer receipts or weakens the old runner's same-source rule.
Preparation and execution are separate; execution requires the budget controller.
"""
import argparse
import ctypes
from contextlib import contextmanager
from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
import platform
import sys
import time

from run_shared_leg_pilot import (ROOT, atomic, convert, load, sha, source, receipt,
                                 physical, verify_paths)
from shared_pilot_budget import admit, total_spent

PRODUCER='721d3c401aafd937606e7c91046233b30f163388'
PINNED={
 'budget.json':'d2b622f757dea356a89e272bb303f818fedc5048f49b65e4db12e024cc502a3f',
 'admission.json':'b505704c4a838a62f8f8453988546ade344fa34dd2bcc38691b2a5918d1a3178',
 'config.json':'14a5c51cb86bae2bc9f2ec23c5887faba8a65b7d58e9ecb11c6ade913dfc8c55',
 'freeze.result.json':'31c94de7a7f94a05d1fb701d045358551cca0249c969c6392c5557706c315251',
 'generation.result.json':'b68cf852d135fcd1cf39c575e19c453d4613a93eed89cc73edfcbf0338a0d485',
 'validation.result.json':'3dba8eaaf3c1fcd17acb93cbc7e2ddd814790a232d4825da6a2c2faf4f06ac12',
 'physics.json':'1d6a01c6e0534a84d42e811e83fc05e9b2e2581acfd53fc38da7436ec4952424',
 'split-table/manifest.json':'aef97213706c4045760a5c53f1cd4a3d41e25b6961fef4b2f7ce15b7a961c7dd'}
THREAD_VARS=('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS')


def environment():
    import z3
    import z3.z3core
    libraries=[v for v in z3.z3core.Z3_get_version.__defaults__[0].f._objects.values() if isinstance(v,ctypes.CDLL)]
    if len(libraries)!=1:raise ValueError('cannot identify loaded Z3 library')
    library=Path(libraries[0]._name).resolve()
    return dict(python=sys.version,executable=str(Path(sys.executable).resolve()),
        executable_sha256=sha(Path(sys.executable).resolve()),platform=platform.platform(),
        z3=z3.get_version_string(),z3_module_sha256=sha(Path(z3.z3core.__file__)),
        z3_library_path=str(library),z3_library_sha256=sha(library))


def verify_identity(ad):
    current=source()
    if current.get('dirty') or current!=ad['consumer_source']:raise ValueError('consumer source changed or dirty')
    if environment()!=ad['consumer_environment']:raise ValueError('consumer environment changed')


def producer_chain(root,check=lambda:None):
    for name,expected in PINNED.items():
        check()
        if sha(root/name,check)!=expected:raise ValueError('producer identity changed: '+name)
    freeze=receipt(root,'freeze');gen=receipt(root,'generation');val=receipt(root,'validation')
    old=load(root/'admission.json')
    expected=dict(commit=PRODUCER,dirty=False)
    if any(r.get('source')!=expected for r in (freeze,gen,val,old)):raise ValueError('producer source chain')
    if freeze['admission_sha256']!=PINNED['admission.json']:raise ValueError('producer admission chain')
    if gen['completed_pairs']!=4225 or gen['table_sha256']!=PINNED['split-table/manifest.json']:raise ValueError('complete producer table')
    if val['table_sha256']!=gen['table_sha256'] or val['physics_sha256']!=PINNED['physics.json']:raise ValueError('validated producer identities')
    if (old['pair_denominator'],old['site_denominator'],old['actions'],val['derived_complete_H'])!=(4225,64,78,20):raise ValueError('frozen dimensions/depth')
    if old.get('holdout') is not False or old.get('road_selection_certified') is not False:raise ValueError('scope changed')
    return old,val


def validate_budget(d):
    if d['cap_CPU_s']!=600 or d['original_cap_CPU_s']!=28800:raise ValueError('budget ceilings changed')
    if Decimal(d['carried_research_CPU_s'])!=Decimal('18229.782734743'):raise ValueError('historical charge changed')
    if d.get('real_query_gate')!='BLOCKED until passing tiny tests and independent review':raise ValueError('unexpected admission gate')
    admit(d,'optimization',180,120,120)


def prepare(producer,stage_ledger,out,reviewed_commit):
    """Metadata-only preparation after independent review; does not load/solve."""
    producer,stage_ledger,out=producer.resolve(),stage_ledger.resolve(),out.resolve()
    if out.exists():raise ValueError('new output directory required')
    if out==producer or producer in out.parents:raise ValueError('producer must remain untouched')
    current=source()
    if current!=dict(commit=reviewed_commit,dirty=False):raise ValueError('reviewed clean consumer source required')
    old,val=producer_chain(producer)
    with (stage_ledger.parent/'controller.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        d=load(stage_ledger);validate_budget(d)
        out.mkdir()  # An incomplete preparation is not automatically reusable.
        snapshot=stage_ledger.read_bytes();(out/'parent-budget.json').write_bytes(snapshot)
        parent_digest=sha(out/'parent-budget.json')
        ad=dict(schema='hiroute.grounded_lookup_consumer.v1',producer_root=str(producer),
            producer_source=old['source'],producer_files=PINNED,
            consumer_source=current,consumer_environment=environment(),
            stage_ledger=str(stage_ledger),parent_budget_sha256=parent_digest,
            historical_result='UNKNOWN_NO_TERMINAL_RECEIPT',query='WD01/E18/schedule/N64',
            sites=64,actions=78,pairs=4225,complete_H=20,wall_s=120,
            holdout=False,real_attempts=1,upper_key=val['upper_replay']['key'])
        atomic(out/'consumer-admission.json',ad)
        for name in ('parent-budget.json','consumer-admission.json'):(out/name).chmod(0o444)
        continued=json.loads(snapshot)
        continued['consumer_admission_sha256']=sha(out/'consumer-admission.json')
        continued['parent_budget_sha256']=parent_digest
        # Close the predecessor before publishing the spendable continuation.
        d.update(state='closed_delegated_to_consumer',consumer_output=str(out),parent_budget_sha256=parent_digest)
        atomic(stage_ledger,d)
        continued['delegated_parent_sha256']=sha(stage_ledger)
        atomic(out/'budget.json',continued)
    return ad


class Clock:
    def __init__(self,out):
        self.start=time.monotonic();self.cpu=time.process_time();self.out=out;self.phases=[]
    def remaining(self):
        result=120-(time.monotonic()-self.start)
        if result<=0:raise TimeoutError('120-second end-to-end consumer deadline')
        return result
    def check(self):self.remaining()
    @contextmanager
    def phase(self,name):
        self.check();wall,cpu=time.monotonic(),time.process_time()
        item=dict(name=name,status='started');self.phases.append(item);atomic(self.out/'consumer-phases.json',self.phases)
        try:
            yield
            self.check()
        except BaseException:
            item['status']='interrupted';raise
        else:item['status']='completed'
        finally:
            item.update(elapsed_wall_s=time.monotonic()-wall,process_CPU_s=time.process_time()-cpu)
            atomic(self.out/'consumer-phases.json',self.phases)


def verify_controller(out,ad):
    d=load(out/'budget.json');parent=load(out/'parent-budget.json')
    if sha(out/'parent-budget.json')!=ad['parent_budget_sha256']:raise ValueError('parent charges changed')
    validate_budget(parent)
    if sha(out/'consumer-admission.json')!=d['consumer_admission_sha256']:raise ValueError('consumer admission changed')
    if sha(Path(ad['stage_ledger']))!=d['delegated_parent_sha256']:raise ValueError('delegated parent changed')
    for key in ('records','phase_charged_CPU_s','fixed_precharge_CPU_s','carried_research_CPU_s','allocations_CPU_s','cap_CPU_s','original_cap_CPU_s'):
        if d[key]!=parent[key]:raise ValueError('inherited accounting changed')
    active=d.get('active') or {}
    if (active.get('phase'),active.get('child_CPU_limit'),active.get('wall_limit'),active.get('reserved_CPU_s'))!=('optimization',120,120,180):raise ValueError('guarded optimization controller required')
    if active.get('pid')!=os.getpid() or active.get('controller_pid')!=os.getppid():raise ValueError('controller process identity')
    if active.get('controller_sha256')!=sha(ROOT/'tools/shared_pilot_budget.py'):raise ValueError('controller source identity')
    if any(os.environ.get(v)!='1' for v in THREAD_VARS):raise ValueError('single numerical worker required')
    return d


def load_verified_table(root,old,val,check):
    from split_leg_table import read,close
    table=read(root/'split-table',check=check)
    try:
        manifest=table._path_store.manifest
        expected=dict(source=old['source'],config_sha256=old['config_sha256'],
                      graph_sha256=old['graph_sha256'],candidate_domain_sha256=old['candidate_domain_sha256'])
        if manifest['provenance']!=expected:raise ValueError('table producer provenance')
        if {k:v for k,v in table._path_store.numeric.items() if k!='pairs'}!=old['header']:raise ValueError('frozen literal header changed')
        if (len(table.candidate_order),len(table.actions),len(table.pairs),len(table.sources),len(table.targets))!=(64,78,4225,65,65):raise ValueError('complete input dimensions')
        if table.payload_sha256!=val['table_sha256']:raise ValueError('table identity changed')
        parameters=physical(old['model'],table,old['schedule_recipe'])
        if parameters!=load(root/'physics.json'):raise ValueError('frozen physics changed')
        from exact_physical_adapter import table_relevant_depth
        depth,upper=table_relevant_depth(table,parameters,old['upper_witness'])
        if depth!=20 or convert(upper['key'])!=val['upper_replay']['key']:raise ValueError('complete depth/upper changed')
        return table,parameters
    except BaseException:
        close(table);raise


def raw_replay(table,old,pairs,check):
    from streaming_road_graph import connect
    db=connect(Path(old['graph_db']))
    def edge(eid):
        check();row=db.execute('SELECT u,v,t,l FROM edges WHERE eid=? COLLATE BINARY',(eid,)).fetchone()
        if row is None:raise ValueError('missing raw edge')
        return row
    try:return verify_paths(table,pairs,edge,check)
    finally:db.close()


def completed_result(result,comparison,output,ad,old,table):
    """Finalize only after the caller's complete input and witness verification.

    Producer identity comes from producer_chain, never a possibly absent copy
    in a later consumer admission. If that copy exists, disagreement is fatal.
    """
    producer_source=old['source']
    if producer_source!=dict(commit=PRODUCER,dirty=False):raise ValueError('validated producer source')
    if 'producer_source' in ad and ad['producer_source']!=producer_source:raise ValueError('admission producer mismatch')
    result.update(status='COMPLETE',comparison=comparison,output_path_checks=output,
                  source=ad['consumer_source'],producer_source=producer_source,table_sha256=table.payload_sha256)


def run(out):
    clock=Clock(out);table=None
    # Exclusive marker is never removed, including failures before solver entry.
    with (out/'optimization.started.json').open('x') as f:
        json.dump(dict(started_at=time.time(),source=source(),pid=os.getpid()),f)
    result=dict(mode='optimization',status='UNKNOWN',holdout=False,road_selection_certified=False)
    try:
        with clock.phase('consumer-and-producer-admission'):
            ad=load(out/'consumer-admission.json');verify_identity(ad);verify_controller(out,ad)
            if ad['producer_files']!=PINNED or ad['real_attempts']!=1 or ad['wall_s']!=120:raise ValueError('admission contract changed')
            root=Path(ad['producer_root']);old,val=producer_chain(root,clock.check)
        with clock.phase('full-input-load-and-validation'):
            table,parameters=load_verified_table(root,old,val,clock.check)
        with clock.phase('raw-input-and-upper-verification'):
            if sha(Path(old['graph_db']),clock.check)!=old['graph_db_sha256']:raise ValueError('raw graph changed')
            pairs=[*old['sample_pairs'],*((p.source,p.target) for p in table.literal_plan_legs(old['upper_witness']['plan'],1))]
            raw_replay(table,old,pairs,clock.check)
        from exact_physical_adapter import solve_real
        with clock.phase('independent-query'):
            comparison=solve_real(table,parameters,old['upper_witness'],out/'SMT',clock.remaining())
            atomic(out/'optimizer.returned.json',dict(comparison=comparison,final_raw_replay_complete=False))
        with clock.phase('final-verification'):
            output=[]
            if comparison['status']=='attained_optimum':
                output=raw_replay(table,old,[(p.source,p.target) for p in table.literal_plan_legs(comparison['witness']['plan'],1)],clock.check)
            # Recheck pinned producer receipts, all data-file hashes and DB after use.
            producer_chain(root,clock.check)
            manifest=table._path_store.manifest
            for name in ('numeric.json','paths.index.json','paths.bin'):
                if sha(root/'split-table'/name,clock.check)!=manifest['files'][name]['sha256']:raise ValueError('input changed during consumer')
            if sha(Path(old['graph_db']),clock.check)!=old['graph_db_sha256']:raise ValueError('raw graph changed during consumer')
            verify_identity(ad);clock.check()
            completed_result(result,comparison,output,ad,old,table)
    except Exception as exc:result.update(status='UNKNOWN',reason=repr(exc))
    finally:
        if table is not None:table._path_store.close()
    if time.monotonic()-clock.start>=120:result.update(status='UNKNOWN',reason='end-to-end deadline exhausted')
    result.update(body_wall_s=time.monotonic()-clock.start,body_CPU_s=time.process_time()-clock.cpu)
    atomic(out/'optimization.result.json',result)
    return 0 if result['status']=='COMPLETE' else 75


def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=('prepare','run'),required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--producer',type=Path)
    p.add_argument('--stage-ledger',type=Path);p.add_argument('--reviewed-commit')
    a=p.parse_args()
    if a.mode=='prepare':
        if not all((a.producer,a.stage_ledger,a.reviewed_commit)):p.error('preparation requires producer, stage ledger, reviewed commit')
        prepare(a.producer,a.stage_ledger,a.output,a.reviewed_commit);return 0
    return run(a.output)


if __name__=='__main__':raise SystemExit(main())

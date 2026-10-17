"""Read-only fixed24 reporting. Outputs are projections, never solver evidence."""
import argparse, collections, hashlib, json, math
from pathlib import Path
from fractions import Fraction
RECOVERY_SHA = '7ff41b1c55fdc29071d6e5172ca7a47b95c2d172c6f714527b538e025e0b81f8'
NUMERICAL_SHA = 'd5198948e126800a108d145c0d9bab8b493a165c2895e9b9e5fb824d4ce1abd0'
EXACT = {'attained_optimum','infimum_unattained_J','infimum_unattained_Q'}
def sha(b): return hashlib.sha256(b).hexdigest()
def number(v):
    if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0: raise ValueError('Invalid measurement')
    return v

def exact_schema(o):
    keys={'status','J','Q','H','Pi','J_attained','Q_attained'}
    if set(o)!=keys or o['status'] not in EXACT:raise ValueError('Invalid exact schema')
    def rational(x):
        if type(x) not in (str,int):raise ValueError('Invalid exact rational')
        try:v=Fraction(x)
        except (ValueError,ZeroDivisionError):raise ValueError('Invalid exact rational')
        if v<0:raise ValueError('Negative exact coordinate')
    rational(o['J'])
    if o['status']=='attained_optimum':
        rational(o['Q'])
        if type(o['H']) is not int or o['H']<0 or type(o['Pi']) is not list or len(o['Pi'])!=o['H'] or o['J_attained'] is not True or o['Q_attained'] is not True:raise ValueError('Invalid attained coordinates')
        for event in o['Pi']:
            if type(event) is not list or len(event)!=2 or type(event[0]) is not str or not event[0] or event[1] not in ('C','S','CS'):raise ValueError('Invalid exact event')
    elif o['status']=='infimum_unattained_J':
        if any(o[k] is not None for k in ('Q','H','Pi','Q_attained')) or o['J_attained'] is not False:raise ValueError('Invalid primary infimum')
    else:
        rational(o['Q'])
        if o['H'] is not None or o['Pi'] is not None or o['J_attained'] is not True or o['Q_attained'] is not False:raise ValueError('Invalid secondary infimum')

def normalize(identity, attempt, unknown=False, unknown_phase=None):
    r=dict(identity, denominator_included=True, status='pending', cleanup_verified=None, exact_outcome=None, wall_seconds=None, conservative_cpu_charge_seconds=None, transport_benefit='not_established',last_durable_phase=unknown_phase)
    receipt={}
    if attempt is not None:
        if attempt.get('row_id')!=identity['row_id']:raise ValueError('Attempt identity differs')
        r['reserved_cpu_seconds']=number(attempt['reserved_cpu_s'])
        receipt=attempt.get('receipt') or {}
        phase=(attempt.get('last_durable_phase') or {}).get('phase')
        if phase is not None:r['last_durable_phase']=phase
        for source,key in [('charged_conservative_cpu_s','conservative_cpu_charge_seconds'),('controller_cpu_s','controller_measured_cpu_seconds')]:
            if source in attempt:r[key]=number(attempt[source])
        if 'charged_conservative_cpu_s' in attempt:r['cpu_charge_kind']='wait4_plus_controller_conservative_not_unique_CPU'
        if 'wall_seconds' in receipt:r['wall_seconds']=number(receipt['wall_seconds'])
        if 'sampled_process_tree_peak_rss_bytes' in receipt:r['sampled_group_peak_rss_bytes']=number(receipt['sampled_process_tree_peak_rss_bytes'])
        if 'cleanup_verified' in receipt:r['cleanup_verified']=receipt['cleanup_verified'] is True
    if unknown:
        r.update(status='infrastructure_unknown',unknown_conservative_reservation_seconds=670)
        if r['conservative_cpu_charge_seconds'] is None:r.update(conservative_cpu_charge_seconds=670,cpu_charge_kind='full_reserved_allowance_not_measurement')
        return r
    if attempt is None or attempt['state']!='finished':return r
    if receipt.get('complete') is not True or not r['cleanup_verified'] or attempt.get('verification_failure') or attempt.get('controller_error'):
        r['status']='infrastructure_unknown';return r
    for key in ('wall_seconds','conservative_cpu_charge_seconds','controller_measured_cpu_seconds'):
        if r.get(key) is None:raise ValueError('Missing completed measurement')
    reason=receipt.get('reason')
    if reason in ('wall_timeout','cpu_limit'):r['status']='time_limit';r['limit_reason']=reason;return r
    if reason=='worker_failed' and (attempt.get('error') or {}).get('type')=='MemoryError':r['status']='memory_limit';return r
    s=attempt.get('status') or {}
    if reason!='success' or s.get('row_id')!=identity['row_id'] or s.get('denominator_included') is not True:raise ValueError('Unaccepted terminal receipt')
    outcome=s.get('exact_outcome')
    if outcome:
        if outcome.get('status') not in EXACT or outcome.get('status')!=s.get('status'):raise ValueError('Unaccepted exact status')
        if outcome['status']=='attained_optimum' and s.get('witness_independently_replayed') is not True:raise ValueError('Missing attained witness replay')
        exact_schema(outcome)
        r['exact_outcome']={k:outcome[k] for k in ['status','J','Q','H','Pi','J_attained','Q_attained']}
        r['comparison_binding']={k:s.get(k) for k in ['seed_j','certified_depth','prewarm_sha256']}
        r['status']=outcome['status']
    elif identity['component']=='sequential_feasible':
        
        if s.get('status') not in {'feasible','incumbent_search_failed','no_feasible_proposal'}:raise ValueError('Unknown construction status')
        r['status']='construction_'+s['status']
        r['construction_claim']='reported_by_worker_without_persisted_physical_witness'
    elif s.get('solver_started') is False:
        r['status']='seed_failure';r['global_infeasible']=False
    else:raise ValueError('Unknown numerical terminal')
    return r

def pairs(rows):
    groups={}
    for r in rows:
        if r['component'] not in ('full_universe','representative_repeat'):continue
        groups.setdefault((r['component'],r['ordinal'],r['candidate_count']),{})[r['method']]=r
    result=[]
    for key,g in sorted(groups.items()):
        a,b=g['flat'],g['hier'];x={'component':key[0],'ordinal':key[1],'candidate_count':key[2],'comparison':'unavailable','flat_over_hier_wall_ratio':None}
        if a['exact_outcome'] and b['exact_outcome']:
            binding=a.get('comparison_binding',{})
            if a['exact_outcome']!=b['exact_outcome'] or binding!=b.get('comparison_binding',{}):
                x['comparison']='mismatch'
            elif not binding or any(v is None for v in binding.values()): x['comparison']='binding_missing'
            else:
                x['comparison']='exact_agreement'
                if a['wall_seconds'] and b['wall_seconds']:x['flat_over_hier_wall_ratio']=a['wall_seconds']/b['wall_seconds']
                x['timing_scope']='same continuation configuration; descriptive, nonrandomized, not cross-host speedup'
        result.append(x)
    return result

def build(root, terminal=False):
    snapshots={}
    def load(rel):
        data=(root/rel).read_bytes();snapshots[rel]=data;return json.loads(data)
    numerical=load('fixed_supplement_work/ORIGINAL_NUMERICAL_MANIFEST.json')
    original=load('fixed_supplement_work/CLOUD_PHASE_PLAN.json')
    recovery=load('fixed_supplement_recovery_work/CLOUD_PHASE_PLAN.json')
    old=load('fixed_supplement_work/ledger.json');new=load('fixed_supplement_recovery_work/ledger.json')
    if sha(snapshots['fixed_supplement_work/ORIGINAL_NUMERICAL_MANIFEST.json'])!=NUMERICAL_SHA:raise ValueError('Numerical manifest changed')
    if sha(snapshots['fixed_supplement_recovery_work/CLOUD_PHASE_PLAN.json'])!=RECOVERY_SHA:raise ValueError('Recovery manifest changed')
    if new['manifest_sha256']!=RECOVERY_SHA or old['manifest_sha256']!=sha(snapshots['fixed_supplement_work/CLOUD_PHASE_PLAN.json']):raise ValueError('Ledger binding differs')
    p=recovery['recovery_provenance']
    if sha(snapshots['fixed_supplement_work/ledger.json'])!=p['original_ledger_sha256']:raise ValueError('Interrupted ledger changed')
    identities=numerical['rows']
    if len(identities)!=24 or len({r['row_id'] for r in identities})!=24 or original['rows']!=identities or recovery['rows']!=identities or recovery['allowed_row_indices']!=list(range(2,24)):raise ValueError('Frozen24 changed')
    byindex={}
    for ledger,allowed in [(old,{0,1}),(new,set(range(2,24)))]:
        for a in ledger['attempts']:
            i=a['index']
            if i not in allowed or i in byindex or a['row_id']!=identities[i]['row_id']:raise ValueError('Repeated or changed attempt')
            byindex[i]=a
    if p['excluded_uncertain_row_indices']!=[1] or p['uncertain_status']!='infrastructure_interrupted_outcome_unknown':raise ValueError('Recovery interruption differs')
    rows=[normalize(r,byindex.get(i),i==1,p['uncertain_row_last_phase'] if i==1 else None) for i,r in enumerate(identities)]
    pending=sum(r['status']=='pending' for r in rows)
    if terminal and pending:raise ValueError('Terminal report forbidden while rows pending')
    if terminal and (new.get('blocked') or any(r['status']=='infrastructure_unknown' for i,r in enumerate(rows) if i!=1)):
        raise ValueError('Additional execution or cleanup issue requires review')
    paired=pairs(rows)
    if terminal and any(p['comparison'] in ('mismatch','binding_missing') for p in paired):raise ValueError('Exact mismatch unresolved')
    # A stable byte snapshot is copied for reproduction; never modify execution inputs.
    report={'schema':'hiroute.fixed24.report.v2','mode':'terminal_accounting' if terminal else 'progress','denominator':24,'pending_rows':pending,
      'status_counts':dict(collections.Counter(r['status'] for r in rows)), 'rows':rows,'pairs':paired,
      'acceptance':'not_established','row1_cleanup':'previous execution namespace not attestable; preserved unknown','combined_checkpoint_trial':{'status':'pending_separate_evidence','included_in_fixed24':False},
      'historical_48h_accounting':{'status':'unreconciled_host_tail','altered':False},
      'continuation_accounting':{'original_planning_row_reservation_seconds':16080,'recovery_planning_row_reservation_seconds':14740,'reservation_overlap':'Do not add phase reservations: recovery covers original indices 2 through 23.',
       'preparation_conservative_allocations_seconds':[300,180],'row1_unknown_conservative_reservation_seconds':670,
       'known_row_conservative_charges_seconds':sum(r['conservative_cpu_charge_seconds'] or 0 for i,r in enumerate(rows) if i!=1),
       'measured_controller_CPU_seconds':sum(r.get('controller_measured_cpu_seconds',0) for r in rows),'unique_total_measured_CPU_seconds':None},
      'memory_scope':'8 GiB per-process address space only; no cgroup or aggregate RSS enforcement',
      'provenance':{'generator_sha256':sha(Path(__file__).read_bytes()),'source_snapshot_sha256':{k:sha(v) for k,v in snapshots.items()},'frozen_input_sha256':numerical['input_sha256'],'original_numerical_source_sha256':numerical['source_sha256']}}
    return report,snapshots

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--terminal',action='store_true');a=p.parse_args()
    report,snapshots=build(a.root,a.terminal)
    a.output.mkdir(parents=True,exist_ok=False)
    for rel,data in snapshots.items():
        path=a.output/'private_raw_snapshots'/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    (a.output/'public_report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
if __name__=='__main__':main()

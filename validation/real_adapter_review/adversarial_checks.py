"""Mock-only external review tests; no native routing, real data, or Stage C."""
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction as R
import hashlib,json,random,sys
from pathlib import Path
sys.path.insert(0,'/workspace/shared/navigation_audit/worktrees/HiRoute-m5-time-cut/src')
from timecut5.real_legs import ImmutableLegTable,restrict_frozen_tree,encode_binary64
from timecut5.real_adapter import (RealProblem,original_region_view,solve_bounded_real,
    solve_hierarchical_real,replay_real_witness)
from timecut5.bounded import _retag_anchor
from timecut5.probe import Interval
ROOT=Path('/workspace/shared/navigation_audit/worktrees/HiRoute-m5-time-cut')
OUT=Path(__file__).resolve().parent
BASE=json.loads((ROOT/'results/milestone_5_real_leg_contract/mock_solver_cases.json').read_text())
blob=lambda x:json.dumps(x,sort_keys=True,separators=(',',':')).encode()
def inputs(c):
    table=ImmutableLegTable.from_bytes(blob(c['table']),hashlib.sha256(blob(c['table'])).hexdigest())
    tree=restrict_frozen_tree(blob(c['original_tree']),hashlib.sha256(blob(c['original_tree'])).hexdigest(),list(table.sites))
    return c['query'],table,tree

def freeze_differential_cases():
    rng=random.Random(5072026)
    cases=[]
    for n in range(16):
        c=deepcopy(BASE[n%2]);q=c['query'];p=c['table']
        c['case_id']=f'adversarial_mock_{n:02d}'
        c.pop('independent_expected',None);c.pop('table_sha256',None);c.pop('original_tree_sha256',None)
        anchors=['road:o','road:x','road:y','road:z'];p['anchors']=anchors
        # Textual destination label is a legal semantic Site at another anchor.
        p['sites']=[dict(site_id='A',anchor_id='road:x',effects=[['C','CS','S'][n%3]]),
                    dict(site_id='road:z',anchor_id='road:x' if n%2==0 else 'road:y',effects=[['S','C','CS'][n%3]]),
                    dict(site_id='at_destination',anchor_id='road:z',effects=['C','S','CS'])]
        p['legs']=[]
        for a in anchors:
            for b in anchors:
                p['legs'].append(dict(source_anchor=a,target_anchor=b,reachable=True,
                    time_s=encode_binary64(0.0 if a==b else rng.choice([0.1,0.2,1.,2.,4.,9.])),
                    actual_length_m=encode_binary64(0.0 if a==b else rng.choice([0.1,1.,2.,4.,7.])),
                    label_direction='identity' if a==b else 'forward_from_source'))
        ids=[s['site_id'] for s in p['sites']]
        c['original_tree']=dict(site_ids=['omitted_original']+ids,regions=[
            dict(parent=-1,children=[1,2],members=[0,1,2,3]),
            dict(parent=0,children=[],members=[0]),
            dict(parent=0,children=[3,4],members=[1,2,3]),
            dict(parent=2,children=[],members=[1]),dict(parent=2,children=[],members=[2,3])])
        p['hierarchy_sha256']=hashlib.sha256(blob(c['original_tree'])).hexdigest()
        p['selection_certificate_sha256']=hashlib.sha256(c['case_id'].encode()).hexdigest()
        q.update(H_ref=2,initial_energy_kwh=[1,2,4,3][n%4],capacity_kwh=4,reserve_kwh=n%2,
                 overhead_s='1/2' if n%3==0 else 1,lambda_stop_s=n%3,
                 consumption_kwh_per_m='1/2' if n%4==0 else 1,
                 charging_segments=[[0,2,1,0],[2,4,3,-4]],
                 schedule={'a':n%6,'b':n%6+8,'D':n%3},initial_remaining_schedule=int(n%5!=0))
        cases.append(c)
    path=OUT/'adversarial_mock_cases.json';path.write_bytes(blob(cases)+b'\n')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    (OUT/'adversarial_mock_freeze.json').write_text(json.dumps(dict(sha256=digest,seed=5072026,
        scope='mock-only differential; not certified real-road export',case_count=len(cases)),indent=2)+'\n')
    return cases

def test_retag_inherited_domain():
    q,t,tr=inputs(BASE[0]);q=dict(q,H_ref=3);p=RealProblem(q,t)
    first=p.advance((p.initial_piece(),),'A','C')
    restricted=[]
    for piece in first:
        d=piece.domain.intersect(Interval(3,4))
        if d is not None:restricted.append(replace(piece,domain=d))
    second=p.advance(tuple(restricted),'A','C')
    third=p.advance(second,'B','S')
    checked=0
    for piece in p.finish(third):
        values={(piece.domain.lo+piece.domain.hi)/2}
        values.update(e for e in (piece.domain.lo,piece.domain.hi) if piece.domain.contains(e))
        for energy in values:
            for eps in (R(1),R(1,1000)):
                w=piece.at(energy).approach(eps)
                replay_real_witness(q,t,w)
                assert w.state.anchor==t.destination_anchor
                stops=[e for e in w.events if e.effect!='D' and e.effect!='initial']
                assert 3<=stops[0].departure_energy<=4
                assert tuple(e.site for e in stops)==('A','A','B')
                assert stops[1].departure_energy>stops[1].arrival_energy
                checked+=1
    assert checked>0
    return checked

def test_malformed_inputs():
    q,t,tr=inputs(BASE[0]);checks=0
    def rejects(call):
        nonlocal checks
        try:call()
        except (AssertionError,ValueError,TypeError,KeyError):checks+=1;return
        raise AssertionError('malformed input unexpectedly accepted')
    for key,val in [('H_ref',True),('H_ref',2.0),('initial_remaining_schedule',True),('initial_energy_kwh',2.0),
                    ('consumption_kwh_per_m',-1),('overhead_s',0),('minimum_energy_kwh',-1),
                    ('reserve_kwh',6),('lambda_stop_s',-1),('selection_certificate_sha256','0'*64),
                    ('hierarchy_sha256','0'*64),('destination','wrong'),('sites',{}),('edges',[])]:
        bad=dict(q);bad[key]=val;rejects(lambda bad=bad:RealProblem(bad,t))
    for edit in [
        lambda r:replace(r,regions=()),
        lambda r:replace(r,regions=(replace(r.regions[0],region_id=9),*r.regions[1:])),
        lambda r:replace(r,regions=(replace(r.regions[0],child_ids=(1,1)),*r.regions[1:])),
        lambda r:replace(r,regions=(replace(r.regions[0],child_ids=(0,2)),*r.regions[1:])),
        lambda r:replace(r,regions=(replace(r.regions[0],child_ids=(1,)),*r.regions[1:])),
        lambda r:replace(r,regions=(r.regions[0],replace(r.regions[1],site_ids=('A','B')),r.regions[2])),
        lambda r:replace(r,regions=(r.regions[0],replace(r.regions[1],parent_id=2),r.regions[2])),
        lambda r:replace(r,selected_site_ids=('A','A','B')),
        lambda r:replace(r,regions=(replace(r.regions[0],site_ids=('A','A','B')),*r.regions[1:]))]:
        bad=edit(tr);rejects(lambda bad=bad:original_region_view(t,bad))
    return checks

if __name__=='__main__':
    cases=freeze_differential_cases()
    print(json.dumps(dict(frozen_mock_cases=len(cases),retag_witnesses_checked=test_retag_inherited_domain(),
                         malformed_inputs_rejected=test_malformed_inputs()),indent=2))

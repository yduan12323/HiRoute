"""Independent loader/bound checks only; no optimizer, graph build, or real query."""
from __future__ import annotations
from copy import deepcopy
from fractions import Fraction as F
import hashlib,json,math,random,struct,sys
from pathlib import Path

ROOT=Path('/workspace/shared/navigation_audit/worktrees/HiRoute-m5-time-cut')
sys.path.insert(0,str(ROOT/'src'))
from timecut5.probe import State
from timecut5.real_legs import ImmutableLegTable,encode_binary64,decode_binary64,restrict_frozen_tree,weak_action_bound,SCHEMA,NUMERICS,TIE_POLICY

def digest(data):return hashlib.sha256(data).hexdigest()
def blob(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def fixture():
    anchors=['a','b','c','z']
    return dict(schema=SCHEMA,numerical_contract=NUMERICS,anchors=anchors,
        origin_anchor='a',destination_anchor='z',
        sites=[dict(site_id='one',anchor_id='b',effects=['C','S','CS']),
               dict(site_id='two',anchor_id='c',effects=['C','S','CS']),
               dict(site_id='three',anchor_id='b',effects=['CS'])],
        backend=dict(name='independent mock',tie_policy=TIE_POLICY,direction_policy='forward_per_source_v1',
                     source_sha256={'src/router.cpp':digest(b'router')}),
        source_sha256={'data/source':digest(b'source')},
        selection_certificate_sha256=digest(b'selection'),hierarchy_sha256=digest(b'tree'),
        legs=[dict(source_anchor=a,target_anchor=b,reachable=True,
                   time_s=encode_binary64(0.0 if a==b else float(1+i+j)),
                   actual_length_m=encode_binary64(0.0 if a==b else float(1+i+2*j)),
                   label_direction='identity' if a==b else 'forward_from_source')
              for i,a in enumerate(anchors) for j,b in enumerate(anchors)])
def load(p):
    data=blob(p);return ImmutableLegTable.from_bytes(data,digest(data))
def rejection(name,fn,failures):
    try:fn()
    except (ValueError,TypeError,KeyError):print('PASS rejection:',name)
    else:failures.append(name);print('FAIL accepted:',name)

failures=[]
p=fixture();p['sites'][0]['effects']='CS';rejection('string effects would split CS',lambda:load(p),failures)
p=fixture();p['anchors']='abcz';rejection('string anchors would split IDs',lambda:load(p),failures)
p=fixture();data=blob(p).replace(b'"origin_anchor":"a"',b'"origin_anchor":"z","origin_anchor":"a"')
rejection('duplicate JSON object keys',lambda:ImmutableLegTable.from_bytes(data,digest(data)),failures)

rng=random.Random(872031)
for i in range(500):
    v=struct.unpack('>d',rng.getrandbits(63).to_bytes(8,'big'))[0]
    if math.isfinite(v):assert decode_binary64(encode_binary64(v))==F(*v.as_integer_ratio())
print('PASS 500 seeded binary64 round trips (nonfinite skipped)')

p=fixture();table=load(p)
for i in range(600):
    tau=F(rng.randint(-10,50),rng.randint(1,8));start=F(rng.randint(-10,10));h=F(rng.randint(1,8));penalty=F(rng.randint(0,8));k=rng.randint(0,5)
    a=F(rng.randint(-10,50));d=F(rng.randint(0,12));b=a+100
    for effect in ('C','S','CS'):
        bound=weak_action_bound(table,State('a',1,k),['one','two','three'],effect,tau,start,h,penalty,(a,b,d))
        for sid in bound.site_ids:
            site=table.site(sid);tin=table.leg('a',site.anchor_id).time
            actual_arrival=tau+F(rng.randint(0,12))+tin+h+F(rng.randint(0,12))
            charge_duration=F(rng.randint(1,8),rng.randint(1,8))
            depart=actual_arrival+charge_duration if effect=='C' else max(a,actual_arrival)+d
            if effect=='CS':depart=max(depart,actual_arrival+charge_duration)
            onward_time=F(rng.randint(0,30));extra_stops=rng.randint(0,4)
            final=depart+onward_time-start+penalty*(k+1+extra_stops)
            assert bound.value<=final
print('PASS 1,800 seeded immediate-action bound cases across all retained actions')

# Accepted real tree is read and restricted only; no queries/search are run.
path=ROOT/'results/milestone_4r_b1/hierarchy.json';data=path.read_bytes()
expected='4c9cd924c9066630f961302ff249de8e6260ed553f8044f1d2fafe8632127805'
source=json.loads(data);selected=[source['site_ids'][0],source['site_ids'][-1]]
tree=restrict_frozen_tree(data,expected,selected)
assert len(tree.regions)==2047 and set(tree.regions[0].site_ids)==set(selected)
for i,row in enumerate(source['regions']):
    assert tree.regions[i].region_id==i and tree.regions[i].parent_id==row['parent']
    assert tree.regions[i].child_ids==tuple(row['children'])
    assert set(tree.regions[i].site_ids)==({source['site_ids'][j] for j in row['members']}&set(selected))
assert any(not r.site_ids for r in tree.regions)
print('PASS accepted 2,047-Region tree hash/topology/empty-child restriction')

print(json.dumps({'parser_failures':failures,'binary64_trials':500,'bound_cases':1800,'actual_tree_regions':len(tree.regions)},sort_keys=True))
sys.exit(bool(failures))

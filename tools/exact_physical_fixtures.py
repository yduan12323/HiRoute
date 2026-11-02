"""Frozen synthetic tiny inputs with analytic keys; not real-road producers."""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'comparison'))
from tiny_smt import canonical_legs
from exact_leg_fixtures import complete_payload
from exact_leg_table import ExactLegTable
from exact_physical_adapter import SCHEMA,FIELDS

IDS=('empty_prefix_terminal','alias_positive_charge','repeated_C_S_C','CS_overlap',
     'directed_unreachable','equality_attained','primary_unattained','secondary_unattained')


def edges(rows):return [dict(source=a,target=b,time_s=str(t),length_m=str(d),edge_id=a+'>'+b) for a,b,t,d in rows]
def physics(B=3,e=1,reserve=0,h=1,penalty=10,rate=1,schedule=None,curve=None,t0=0):
    return dict(schema=SCHEMA,departure_time_s=str(t0),initial_energy_kwh=str(e),capacity_kwh=str(B),
        minimum_energy_kwh='0',destination_reserve_kwh=str(reserve),stop_overhead_s=str(h),
        stop_penalty_s=str(penalty),consumption_kwh_per_m=str(rate),schedule=schedule,
        initial_remaining_schedule=int(schedule is not None),
        charging_curve=curve if curve is not None else [['0','1','1','0'],['1','2','2','-1'],['2',str(B),'3','-3']])
def curve_unit(B=3):return [['0','1','1','0'],['1','2','1','0'],['2',str(B),'1','0']]
def schedule(a,b,D):return dict(a=str(a),b=str(b),D=str(D))
def seed(plan,charges=(),wait='0'):return dict(plan=plan,charges=list(charges),initial_wait=wait)
def optimum(J,Q,H,plan):return dict(status='attained_optimum',key=[str(J),str(Q),H,plan])


def case(name):
    if name not in IDS:raise ValueError('not a frozen tiny case')
    if name=='empty_prefix_terminal':
        sites={};road=edges([('o','z',2,2)]);p=physics(B=6,e=6,curve=[])
        upper=seed([]);expected=optimum(2,0,0,[])
    elif name=='alias_positive_charge':
        sites={s:dict(anchor='o',effects=['C']) for s in ('alpha','omega')}
        road=edges([('o','z',1,6)])
        p=physics(B=6,e=0,penalty=4,curve=[['0','2','1','0'],['2','4','2','-2'],['4','6','3','-6']])
        upper=seed([['omega','C']],['6']);expected=optimum(18,6,1,[['alpha','C']])
    elif name=='repeated_C_S_C':
        sites={'c':dict(anchor='c',effects=['C']),'s':dict(anchor='s',effects=['S'])}
        road=edges([('o','c',1,1),('c','s',1,1),('s','c',1,1),('c','z',1,2)])
        p=physics(schedule=schedule(0,100,1));plan=[['c','C'],['s','S'],['c','C']]
        upper=seed(plan,['2','2']);expected=optimum(44,4,3,plan)
    elif name=='CS_overlap':
        sites={'p':dict(anchor='p',effects=['CS'])};road=edges([('o','p',1,1),('p','z',1,3)])
        p=physics(B=4,e=1,penalty=5,schedule=schedule(0,10,8));plan=[['p','CS']]
        upper=seed(plan,['3']);expected=optimum(16,3,1,plan)
    elif name=='directed_unreachable':
        sites={s:dict(anchor=s,effects=['S']) for s in ('a','dead')}
        road=edges([('o','a',1,1),('a','z',1,1),('o','dead',1,1)])
        p=physics(e=3,penalty=4,schedule=schedule(0,10,1),curve=[]);plan=[['a','S']]
        upper=seed(plan);expected=optimum(8,0,1,plan)
    elif name=='equality_attained':
        sites={'c':dict(anchor='c',effects=['C']),'s':dict(anchor='s',effects=['S'])}
        road=edges([('o','c',1,1),('c','s',1,2),('s','z',1,1)])
        p=physics(schedule=schedule(100,107,1),t0=100,curve=curve_unit());plan=[['c','C'],['s','S']]
        upper=seed(plan,['3']);expected=optimum(29,3,2,plan)
    else:
        effect='C' if name=='primary_unattained' else 'CS'
        sites={'c':dict(anchor='c',effects=[effect])}
        road=edges([('o','z',1,5),('o','c',1,1),('c','z',1,1)])
        p=physics(e=3,reserve=1,penalty=7,curve=curve_unit(),
            schedule=None if effect=='C' else schedule(0,10,4))
        upper=seed([['c',effect]],['1/2'])
        expected=(dict(status='primary_unattained',primary_infimum='10') if effect=='C' else
                  dict(status='secondary_unattained',primary_infimum='14',primary_value='14',secondary_infimum='0'))
    return dict(id=name,sites=sites,edges=road,physics=p,upper_witness=upper,expected=expected)


def tiny_table(fixture):
    sites=fixture['sites'];anchors=sorted({r['anchor'] for r in sites.values()})
    graph=dict(origin='o',destination='z',candidate_order=anchors,directed_edges=fixture['edges'])
    selected=canonical_legs(graph)  # Guarded <=6 nodes/12 edges/128 paths, never real graphs.
    payload=complete_payload('o','z',list(sites),sites)
    payload['graph_identity']='SYNTHETIC_TINY:'+hashlib.sha256(json.dumps(graph,sort_keys=True).encode()).hexdigest()
    for row in payload['pairs']:
        leg=selected.get((row['source'],row['target']))
        row.update(reachable=leg is not None,time_s=str(leg[0]) if leg else None,
            actual_length_m=str(leg[1]) if leg else None,nodes=list(leg[2]) if leg else [],edges=list(leg[3]) if leg else [])
    raw=(json.dumps(payload,sort_keys=True,separators=(',',':'))+'\n').encode();table=ExactLegTable.from_bytes(raw)
    certificate=dict(scope='synthetic tiny graph only',method='independent exhaustive simple paths with positive weights',
        graph_identity=payload['graph_identity'],table_sha256=table.payload_sha256,verified_pairs=len(table.pairs),
        real_graph=False,not_inferred_from_schema=True)
    return table,raw,certificate


def legacy_snapshot(fixture):
    """For separate concrete replay only; aliases are deliberately unsupported."""
    if any(s!=r['anchor'] for s,r in fixture['sites'].items()):return None
    p=fixture['physics']
    return dict({k:p[k] for k in FIELDS},schema='hiroute.problem_snapshot.v1',
        model_contract_id='hiroute.time_cut_v2.bounded',numerical_contract_id='exact_rational_inputs_v1',
        origin='o',destination='z',candidate_order=list(fixture['sites']),
        site_capabilities={s:r['effects'] for s,r in fixture['sites'].items()},
        charging_curve=p['charging_curve'],schedule=p['schedule'],
        initial_remaining_schedule=p['initial_remaining_schedule'],directed_edges=fixture['edges'],
        selected_leg_contract='positive_time_node_path_edge_path_tie_v1',depth_mode='unrestricted',depth_limit=0)


def semantics(result):
    def convert(value):
        if isinstance(value,dict):return {k:convert(v) for k,v in value.items()}
        if isinstance(value,(tuple,list)):return [convert(v) for v in value]
        from fractions import Fraction
        return str(value) if isinstance(value,Fraction) else value
    return {k:convert(result[k]) for k in ('status','key','primary_infimum','primary_value','secondary_infimum') if k in result}

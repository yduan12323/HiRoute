"""Regression reproductions for three independent review findings, now fixed."""
from timecut5.bounded import solve_bounded, replay_witness
from timecut5.hierarchy import solve_hierarchical
from timecut5.probe import Witness, State, Event
from validation.reference5.solver import solve_case
c=dict(H_ref=1,origin='o',destination='z',start_time_s=0,initial_energy_kwh=2,capacity_kwh=5,minimum_energy_kwh=0,reserve_kwh=0,consumption_kwh_per_m=1,overhead_s=1,lambda_stop_s=0,schedule={'a':0,'b':100,'D':1},sites={'z':['S']},charging_segments=[],edges=[dict(source='o',target='z',time_s=1,length_m=1)])
assert solve_case(c)['result']['status']=='infeasible_within_H_ref'
for f in [solve_bounded,solve_hierarchical]:
 for d in [False,True]:assert f(c,d).canonical()['result']['status']=='infeasible_within_H_ref'
c.update(sites={'x':['S']},edges=[dict(source='o',target='x',time_s=1,length_m=1),dict(source='x',target='z',time_s=1,length_m=1)])
w=solve_bounded(c).result.witness;c['H_ref']=0
try:replay_witness(c,w)
except (AssertionError,ValueError):pass
else:raise AssertionError('Overbound witness accepted')
c.update(H_ref=1,schedule=None,sites={'x':['C']},charging_segments=[[0,5,1,0]],edges=[dict(source='o',target='z',time_s=1,length_m=5),dict(source='o',target='x',time_s=1,length_m=1),dict(source='x',target='z',time_s=1,length_m=1)])
w=Witness(2,0,0,(),State('z',0,0),(Event('initial','o',0,0,2,2),Event('D','x',0,1,2,1),Event('D','z',1,2,1,0)))
assert solve_bounded(c).canonical()['result']['primary_infimum']==3
assert solve_hierarchical(c).canonical()['result']['primary_infimum']==3
try:solve_hierarchical(c,incumbent=w)
except (AssertionError,ValueError):pass
else:raise AssertionError('Illegal route-shaping incumbent accepted')
print('PASS: destination action excluded; overbound witness rejected; consecutive-drive incumbent rejected.')

"""Targeted independent rational reset expectations under v2 cut semantics."""
import argparse,hashlib,json,sys,time
from fractions import Fraction as Q
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--repo',required=True);p.add_argument('--output',required=True);a=p.parse_args();repo=Path(a.repo).resolve()
sys.path.insert(0,str(repo/'experiments/time_cut_v2/oracle'));sys.path.insert(0,str(repo/'src'))
from frontier_checks import Piece,Span,Aff,Adapter,to_public,independent_schedule,independent_reduce,verify_coverage
adapter=Adapter(repo);rows=[];start=time.monotonic()
def piece(lo,hi,m,c,rho,name,chi=True):return Piece(Span(Q(lo),Q(hi)),Aff(Q(m),Q(c)),chi,Q(rho),((name,'C'),),('arrival',1,1))
def check_schedule(name,source,a,b,d,h,expect):
 expected=independent_schedule(source,Q(a),Q(b),Q(d),Q(h));prod=[]
 for src in source:prod.extend(adapter.pwa.schedule_pwa(to_public(adapter,(src,)),'stop',Q(a),Q(b),Q(d),Q(h)))
 got=tuple(map(Piece.read,prod));stats=verify_coverage(expected,got)
 for energy,values in expect:
  exact=sorted((str(x.line(Q(energy))),str(x.rho)) for x in expected if x.domain.contains(Q(energy)))
  assert exact==values,(name,energy,exact,values)
 rows.append({'theme':name,'independent_formula':'max(a,t+h)+D on t<=b-h, with open-cut plateau attainment iff tau<a-h','expected_at':expect,'whole_domain':stats,'status':'passed'})
check_schedule('partial_waiting_gap_collapse',(piece(0,1,2,4,2,'A'),piece(0,1,0,5,1,'B')),6,10,0,1,[(0,[('6','1'),('6','2')]),(Q(1,2),[('6','1'),('6','2')]),(1,[('6','1'),('7','2')])])
check_schedule('no_waiting_plateau',(piece(0,1,0,7,2,'A'),piece(0,1,0,8,1,'B')),0,10,2,1,[(0,[('10','2'),('11','1')]),(1,[('10','2'),('11','1')])])
for name,source,winner in (
 ('equal_time_unequal_rho',(piece(0,1,0,5,0,'z'),piece(0,1,0,5,1,'a')),'z'),
 ('equal_time_equal_rho_tuple',(piece(0,1,0,5,0,'z'),piece(0,1,0,5,0,'a')),'a')):
 expected=independent_reduce(source);got=tuple(map(Piece.read,adapter.pwa.reduce_frontier(to_public(adapter,source))));stats=verify_coverage(expected,got,antichain=True)
 at_half=[v for v in expected if v.domain.contains(Q(1,2))];assert len(at_half)==1 and at_half[0].pi[0][0]==winner
 rows.append({'theme':name,'independent_expected_winner':winner,'independent_formula':'same time: smaller rho wins; if rho ties lexicographically smaller full prefix wins','whole_domain':stats,'status':'passed'})
source=(piece(0,2,0,0,0,'A'),piece(0,2,1,-1,1,'B'),piece(0,2,-2,3,2,'C'))
knots={Q(1),Q(4,3),Q(3,2)}
for energy in knots:
 values=[p.line(energy) for p in source]
 assert any(values[i]==values[j] for i in range(3) for j in range(i+1,3))
expected=independent_reduce(source);got=tuple(map(Piece.read,adapter.pwa.reduce_frontier(to_public(adapter,source))));stats=verify_coverage(expected,got,antichain=True)
rows.append({'theme':'multiple_crossings_different_rho','independent_formula':'pairwise affine crossings at 1, 4/3, 3/2; pointwise minimum classes under independent (time,rho,pi) preorder','knots':[str(x) for x in sorted(knots)],'whole_domain':stats,'status':'passed'})
receipt={'schema':'hiroute-v2-reset-gap-checks-v1','source_commit':'d51367ca5a8a109d3a76c35ebbc55ac4edc361bf','source_sha256':{n:hashlib.sha256((repo/n).read_bytes()).hexdigest() for n in ('src/timecut5/pwa.py','src/timecut5/probe.py','experiments/time_cut_v2/oracle/frontier_checks.py')},'rows':rows,'passed':len(rows),'elapsed_seconds':time.monotonic()-start}
Path(a.output).write_text(json.dumps(receipt,indent=2,sort_keys=True,default=str)+'\n');print(json.dumps({'passed':len(rows),'seconds':receipt['elapsed_seconds']}))

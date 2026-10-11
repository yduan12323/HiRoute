"""Frozen v2 D/S/three-way merge objects with independent whole-energy expected cuts."""
import argparse,hashlib,json,random,sys,time
from dataclasses import asdict
from fractions import Fraction as Q
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--repo',required=True);p.add_argument('--output',required=True);a=p.parse_args()
repo=Path(a.repo).resolve();sys.path.insert(0,str(repo/'experiments/time_cut_v2/oracle'));sys.path.insert(0,str(repo/'src'))
from frontier_checks import (Piece,Span,Aff,Adapter,to_public,independent_drive,independent_schedule,independent_reduce,verify_coverage,transform_public)
seed=20261011;rng=random.Random(seed);adapter=Adapter(repo);curve=adapter.probe.ChargingCurve(((Q(0),Q(6),Q(1),Q(0)),))
def pieces(min_count=2):
 result=[]
 for j in range(rng.randint(min_count,5)):
  lo=Q(rng.randint(0,6),2);hi=lo+Q(rng.randint(0,5),2)
  lc=rc=True if lo==hi else False
  if lo!=hi:lc=bool(rng.randrange(2));rc=bool(rng.randrange(2))
  result.append(Piece(Span(lo,hi,lc,rc),Aff(Q(rng.randint(-2,3)),Q(rng.randint(3,11))),bool(rng.randrange(2)),Q(rng.randint(0,3)),((chr(97+j),'C'),),('arrival',1,1)))
 return tuple(result)
def obj(x):
 return dict(domain=[str(x.domain.lo),str(x.domain.hi),x.domain.lc,x.domain.rc],line=[str(x.line.slope),str(x.line.intercept)],chi=x.chi,rho=str(x.rho),pi=x.pi,state=x.state)
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
records=[];counts={'Drive':0,'S':0,'three_way_merge':0,'whole_domain_checks':0,'open_cells':0,'singletons':0}
start=time.monotonic()
for kind in ('Drive','S','three_way_merge'):
 for index in range(50):
  source=pieces(3 if kind=='three_way_merge' else 1 if kind=='Drive' else 2);public=to_public(adapter,source);first=adapter.pwa.reduce_frontier(public)
  if kind in ('Drive','S'):
   effect='D' if kind=='Drive' else 'S'
   expected=independent_drive(source,Q(2),Q(1),Q(1,2)) if kind=='Drive' else independent_schedule(source,Q(6),Q(8),Q(2),Q(1))
   raw=transform_public(adapter,public,effect,curve);reduced_first=transform_public(adapter,first,effect,curve)
   outputs=(adapter.pwa.reduce_frontier(raw),adapter.pwa.reduce_frontier(reduced_first))
   targets=(independent_reduce(expected),)*2
  else:
   x,y,z=(public[:1],public[1:3],public[3:]);all_source=tuple(source)
   left=adapter.pwa.reduce_frontier(adapter.pwa.reduce_frontier(x+y)+z)
   right=adapter.pwa.reduce_frontier(x+adapter.pwa.reduce_frontier(y+z))
   outputs=(left,right,adapter.pwa.reduce_frontier(public))
   targets=(independent_reduce(all_source),)*3
  stats=[]
  for expected_out,actual_out in zip(targets,outputs):
   got=tuple(map(Piece.read,actual_out));v=verify_coverage(expected_out,got,antichain=True);stats.append(v);counts['whole_domain_checks']+=1
   for key in ('open_cells','singletons'):counts[key]+=v[key]
  row={'id':f'{kind}_{index:02d}','kind':kind,'input':[obj(v) for v in source],'input_sha256':digest([obj(v) for v in source]),'independent_expected_sha256':digest([[obj(v) for v in target] for target in targets]),'actual_sha256':digest([[obj(v) for v in map(Piece.read,out)] for out in outputs]),'whole_domain_checks':stats,'status':'passed'}
  records.append(row);counts[kind]+=1
receipt={'schema':'hiroute-v2-operator-increment-v1','seed':seed,'source_commit':'d51367ca5a8a109d3a76c35ebbc55ac4edc361bf','source_sha256':{n:hashlib.sha256((repo/n).read_bytes()).hexdigest() for n in ('src/timecut5/pwa.py','src/timecut5/probe.py','experiments/time_cut_v2/oracle/frontier_checks.py','experiments/time_cut_v2/oracle/oracle.py')},'counts':counts,'records':records,'elapsed_seconds':time.monotonic()-start,'status':'passed'}
Path(a.output).write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n');print(json.dumps({'counts':counts,'seconds':receipt['elapsed_seconds'],'status':'passed'}))

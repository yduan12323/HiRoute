"""Exact endpoint join feeding the unchanged interval-sweep certificate grammar.

Empty domains and different states cannot create dominance edges. Enumerate only
nonempty same-state intersections, preserving every occurrence's original index.
The v5 kernel remains an unchanged independent differential reference.
"""
import hashlib,heapq
from . import independent_oracle_v5 as sweep

KERNEL='interval-join-v1'
MAX_CANDIDATE_PAIRS=2000000
MAX_INTERVALS=450000
SweepResourceLimit=sweep.SweepResourceLimit

def overlapping_pairs(a,b=None):
 """Yield each nonempty same-state overlap once, with exact endpoint ordering.

At x: open ends depart, closed starts arrive, closed ends depart, open starts
arrive. Thus touching intervals pair only if both include x; a closed singleton
is active only between its start and end. Empty singleton domains never enter.
"""
 sides=(a,) if b is None else (a,b)
 if sum(map(len,sides))>sweep.MAX_PIECES:raise SweepResourceLimit('piece-count resource limit')
 events=[]
 for side,rows in enumerate(sides):
  for index,p in enumerate(rows):
   if not sweep._valid(p.lo,p.hi,p.lc,p.rc):continue
   events.append((p.lo,1 if p.lc else 3,side,index))
   events.append((p.hi,2 if p.rc else 0,side,index))
 active={};count=0
 for _,phase,side,index in sorted(events):
  p=sides[side][index];own=active.setdefault((side,p.state),set())
  if phase in (0,2):own.remove(index);continue
  other_side=0 if b is None else 1-side
  for other in sorted(active.get((other_side,p.state),())):
   if b is None:i,j=sorted((index,other));left,right=a[i],a[j]
   elif side==0:i,j=index,other;left,right=a[i],b[j]
   else:i,j=other,index;left,right=a[i],b[j]
   overlap=sweep._overlap(left,right)
   if overlap is None:raise ValueError('endpoint join emitted an empty domain')
   count+=1
   if count>MAX_CANDIDATE_PAIRS:raise SweepResourceLimit('overlap-pair resource limit')
   yield i,j,overlap
  own.add(index)

def _add_interval(events,interval,key):
 if interval is None:return
 events.intervals+=1
 if events.intervals>MAX_INTERVALS:raise SweepResourceLimit('interval-count resource limit')
 lo,hi,lc,rc=interval
 events.setdefault(lo,[[],[]])[0 if lc else 1].append((True,key))
 events.setdefault(hi,[[],[]])[1 if rc else 0].append((False,key))

class _CoverSweep(sweep._CoverSweep):
 def __init__(self,a,b):
  self.a,self.b=a,b;self.cells=sweep._arrangement(a+b);self.events=sweep._Events()
  self.active=[set(),set()];self.candidates=[[set() for _ in b],[set() for _ in a]]
  self.heaps=[[[] for _ in b],[[] for _ in a]];self.covers=[[None]*len(b),[None]*len(a)]
  self.dirty=[set(),set()];self.changed=True;self.vectors=None;self.encoded=None
  self.work=dict(cartesian_pairs=len(a)*len(b),pair_intersections=0,dominance_intervals=0,vector_states=0,certificate_cells=0)
  for side,rows in enumerate((a,b)):
   for i,p in enumerate(rows):
    if sweep._valid(p.lo,p.hi,p.lc,p.rc):_add_interval(self.events,(p.lo,p.hi,p.lc,p.rc),('support',side,i))
  for i,j,overlap in overlapping_pairs(a,b):
   self.work['pair_intersections']+=1;p,q=a[i],b[j]
   for direction,source,target,x,y in ((0,i,j,p,q),(1,j,i,q,p)):
    interval=sweep._dominance_interval(x,y,overlap)
    if interval is not None:
     _add_interval(self.events,interval,('edge',direction,source,target));self.work['dominance_intervals']+=1
  knots={lo for lo,hi,e in self.cells if lo==hi}
  if not set(self.events)<=knots:raise ValueError('dominance event missing from reference arrangement')
  self.work.update(registered_intervals=self.events.intervals,event_points=len(self.events))

def _equivalent(a,b,keep_certificate):
 a,b=list(a),list(b);current=_CoverSweep(a,b);h=hashlib.sha256();h.update(b'[')
 count=opens=0;certificates=[] if keep_certificate else None
 for c,arrays in current.rows():
  if count:h.update(b',')
  for chunk in sweep._row_bytes(c,arrays):h.update(chunk)
  if keep_certificate:certificates.append({k:list(v) if type(v) is list else v for k,v in c.items()})
  count+=1;opens+=not c['singleton']
 h.update(b']')
 result=dict(cells=count,open_cells=opens,singletons=count-opens,sha256=h.hexdigest())
 if keep_certificate:result['certificate']=certificates
 return result,current.work

def equivalent(a,b):return _equivalent(a,b,True)[0]
def equivalent_compact(a,b):return _equivalent(a,b,False)[0]
def equivalent_work(a,b):return _equivalent(a,b,False)

def antichain(pieces):
 pieces=list(pieces);cells=sweep._arrangement(pieces);events=sweep._Events();active={};heap=[]
 for i,j,overlap in overlapping_pairs(pieces):
  p,q=pieces[i],pieces[j]
  for x,y in ((p,q),(q,p)):_add_interval(events,sweep._dominance_interval(x,y,overlap),(i,j))
 if not set(events)<={lo for lo,hi,e in cells if lo==hi}:raise ValueError('antichain event missing from arrangement')
 def apply(rows):
  for add,pair in rows:
   count=active.get(pair,0)
   if add:
    active[pair]=count+1
    if not count:heapq.heappush(heap,pair)
   else:
    if not count:raise ValueError('inactive antichain edge removal')
    if count==1:del active[pair]
    else:active[pair]=count-1
  while heap and heap[0] not in active:heapq.heappop(heap)
 for lo,hi,e in cells:
  if lo==hi:apply(events.get(lo,([],[]))[0])
  if heap:
   i,j=heap[0];raise AssertionError(('not_antichain',str(e),pieces[i].dump(),pieces[j].dump()))
  if lo==hi:apply(events.get(lo,([],[]))[1])

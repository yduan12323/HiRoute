"""Exact dominance-interval sweep with unchanged v2 certificate cells.

Every dominance edge is active on one exact interval. The smallest original
covering index is maintained across the complete reference arrangement. No cell
is dropped; the compact API streams the identical full certificate JSON hash.
"""
from fractions import Fraction as F
import hashlib,heapq,json
from . import independent_oracle_v2 as reference

KERNEL='interval-sweep-v1'
MAX_PIECES=20000
MAX_PAIR_TESTS=2000000
MAX_LINE_PAIRS=500000
MAX_CELLS=1100000
MAX_INTERVALS=250000
MAX_ARRAY_BYTES=1024*1024
MAX_HASH_CHUNK=64*1024

class SweepResourceLimit(RuntimeError):
 """Incomplete computation, never a mathematical rejection or acceptance."""

class _Events(dict):
 def __init__(self):super().__init__();self.intervals=0

def _arrangement(pieces):
 if len(pieces)>MAX_PIECES:raise SweepResourceLimit('piece-count resource limit')
 n=len({(p.m,p.b) for p in pieces})
 if n*(n-1)//2>MAX_LINE_PAIRS:raise SweepResourceLimit('arrangement-pair resource limit')
 result=reference.arrangement(pieces)
 if len(result)>MAX_CELLS:raise SweepResourceLimit('arrangement-cell resource limit')
 return result


def _valid(lo,hi,lc,rc):return lo<hi or lo==hi and lc and rc

def _overlap(p,q):
 lo,hi=max(p.lo,q.lo),min(p.hi,q.hi)
 lc,rc=p.contains(lo) and q.contains(lo),p.contains(hi) and q.contains(hi)
 return (lo,hi,lc,rc) if _valid(lo,hi,lc,rc) else None

def _dominance_interval(p,q,overlap):
 if overlap is None or p.state!=q.state or p.rho>q.rho or p.rho==q.rho and p.pi>q.pi:return None
 lo,hi,lc,rc=overlap;d=F(p.m)-F(q.m);c=F(p.b)-F(q.b);closed=p.chi or not q.chi
 if d==0:return overlap if c<0 or c==0 and closed else None
 root=-c/d
 if d>0:
  if root<hi:hi,rc=root,closed
  elif root==hi:rc=rc and closed
 else:
  if root>lo:lo,lc=root,closed
  elif root==lo:lc=lc and closed
 return (lo,hi,lc,rc) if _valid(lo,hi,lc,rc) else None

def _add_interval(events,interval,key):
 if interval is None:return
 events.intervals+=1
 if events.intervals>MAX_INTERVALS:raise SweepResourceLimit('interval-count resource limit')
 lo,hi,lc,rc=interval
 events.setdefault(lo,[[],[]])[0 if lc else 1].append((True,key))
 events.setdefault(hi,[[],[]])[1 if rc else 0].append((False,key))

def _wire(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()

class _CoverSweep:
 def __init__(self,a,b):
  if len(a)*len(b)>MAX_PAIR_TESTS:raise SweepResourceLimit('coverage-pair resource limit')
  self.a,self.b=a,b;self.cells=_arrangement(a+b);self.events=_Events()
  self.active=[set(),set()];self.candidates=[[set() for _ in b],[set() for _ in a]]
  self.heaps=[[[] for _ in b],[[] for _ in a]];self.covers=[[None]*len(b),[None]*len(a)]
  self.dirty=[set(),set()];self.changed=True;self.vectors=None;self.encoded=None
  self.work=dict(pair_intersections=0,dominance_intervals=0,vector_states=0,certificate_cells=0)
  for side,rows in enumerate((a,b)):
   for i,p in enumerate(rows):
    if _valid(p.lo,p.hi,p.lc,p.rc):_add_interval(self.events,(p.lo,p.hi,p.lc,p.rc),('support',side,i))
  for i,p in enumerate(a):
   for j,q in enumerate(b):
    if p.state!=q.state:continue
    self.work['pair_intersections']+=1;overlap=_overlap(p,q)
    if overlap is None:continue
    for direction,source,target,x,y in ((0,i,j,p,q),(1,j,i,q,p)):
     interval=_dominance_interval(x,y,overlap)
     if interval is not None:
      _add_interval(self.events,interval,('edge',direction,source,target));self.work['dominance_intervals']+=1
  knots={lo for lo,hi,e in self.cells if lo==hi}
  if not set(self.events)<=knots:raise ValueError('dominance event missing from reference arrangement')
  self.work.update(registered_intervals=self.events.intervals,event_points=len(self.events))
 def apply(self,actions):
  for add,key in actions:
   if key[0]=='support':
    _,side,index=key;target=self.active[side]
    if add:
     if index in target:raise ValueError('duplicate support activation')
     target.add(index)
    else:target.remove(index)
    self.changed=True
   else:
    _,direction,source,target=key;active=self.candidates[direction][target]
    if add:
     if source in active:raise ValueError('duplicate dominance activation')
     active.add(source);heapq.heappush(self.heaps[direction][target],source)
    else:active.remove(source)
    self.dirty[direction].add(target)
  for direction in (0,1):
   for target in self.dirty[direction]:
    heap=self.heaps[direction][target];active=self.candidates[direction][target]
    while heap and heap[0] not in active:heapq.heappop(heap)
    first=heap[0] if heap else None
    if first!=self.covers[direction][target]:self.changed=True;self.covers[direction][target]=first
   self.dirty[direction].clear()
 def state(self):
  if self.changed:
   left,right=sorted(self.active[0]),sorted(self.active[1])
   forward=[self.covers[0][j] for j in right];reverse=[self.covers[1][i] for i in left]
   self.vectors=(left,right,forward,reverse)
   # These exact array bytes recur unchanged at irrelevant arrangement knots.
   self.encoded={name:_wire(value) for name,value in zip(
    ('left_support','right_support','left_covers_right','right_covers_left'),self.vectors)}
   if any(len(value)>MAX_ARRAY_BYTES for value in self.encoded.values()):raise SweepResourceLimit('support-array resource limit')
   self.changed=False;self.work['vector_states']+=1
  return self.vectors
 def rows(self):
  for lo,hi,e in self.cells:
   singleton=lo==hi
   if singleton:self.apply(self.events.get(lo,([],[]))[0])
   left,right,forward,reverse=self.state();self.work['certificate_cells']+=1
   c=dict(lo=str(lo),hi=str(hi),singleton=singleton,left_support=left,right_support=right,
    left_covers_right=forward,right_covers_left=reverse)
   if None in forward or None in reverse:
    raise AssertionError(dict(reason='continuation_cover',cell=c,left=[p.dump() for p in self.a],right=[p.dump() for p in self.b]))
   yield c,self.encoded
   if singleton:self.apply(self.events.get(lo,([],[]))[1])

def _row_bytes(c,arrays):
 # json.dumps(...,sort_keys=True,separators=(',',':')) field order exactly.
 yield b'{'
 for n,key in enumerate(sorted(c)):
  if n:yield b','
  token=_wire(key)+b':'
  for offset in range(0,len(token),MAX_HASH_CHUNK):yield token[offset:offset+MAX_HASH_CHUNK]
  value=arrays[key] if key in arrays else _wire(c[key])
  for offset in range(0,len(value),MAX_HASH_CHUNK):yield value[offset:offset+MAX_HASH_CHUNK]
 yield b'}'

def _equivalent(a,b,keep_certificate):
 a,b=list(a),list(b);sweep=_CoverSweep(a,b);h=hashlib.sha256();h.update(b'[')
 count=opens=0;certificates=[] if keep_certificate else None
 for c,arrays in sweep.rows():
  if count:h.update(b',')
  for chunk in _row_bytes(c,arrays):h.update(chunk)
  if keep_certificate:
   # Public materialized results never alias array ownership between cells.
   certificates.append({k:list(v) if type(v) is list else v for k,v in c.items()})
  count+=1;opens+=not c['singleton']
 h.update(b']')
 result=dict(cells=count,open_cells=opens,singletons=count-opens,sha256=h.hexdigest())
 if keep_certificate:result['certificate']=certificates
 return result,sweep.work

def equivalent(a,b):return _equivalent(a,b,True)[0]
def equivalent_compact(a,b):return _equivalent(a,b,False)[0]
def equivalent_work(a,b):return _equivalent(a,b,False)

def antichain(pieces):
 pieces=list(pieces)
 if len(pieces)*(len(pieces)-1)//2>MAX_PAIR_TESTS:raise SweepResourceLimit('antichain-pair resource limit')
 cells=_arrangement(pieces);events=_Events();active={};heap=[]
 for i,p in enumerate(pieces):
  for j in range(i+1,len(pieces)):
   q=pieces[j];overlap=_overlap(p,q)
   if overlap is None:continue
   for x,y in ((p,q),(q,p)):_add_interval(events,_dominance_interval(x,y,overlap),(i,j))
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

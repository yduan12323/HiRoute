"""Independent exact affine-cell semantics; standard-library only.

Version 2 preserves v1 mathematics and replaces its two assert statements with
unconditional checks so optimized Python cannot disable acceptance logic.
The original v1 file remains byte-for-byte frozen beside this module.

No imports of production, reference, projection, reduction, or envelope code.
Charge/CS use direct one-dimensional convex piecewise-linear minimization.
"""
from dataclasses import dataclass, replace
from fractions import Fraction as F
from itertools import combinations
import hashlib, json

@dataclass(frozen=True)
class Piece:
    lo: F
    hi: F
    lc: bool
    rc: bool
    m: F
    b: F
    chi: bool
    rho: F
    pi: tuple
    state: tuple
    def contains(self,e):
        return (self.lo < e or self.lo == e and self.lc) and (e < self.hi or e == self.hi and self.rc)
    def tau(self,e): return self.m*e+self.b
    def family(self): return self.state,self.rho,self.pi
    def dump(self):
        return dict(domain=[str(self.lo),str(self.hi),self.lc,self.rc],m=str(self.m),b=str(self.b),chi=self.chi,rho=str(self.rho),pi=self.pi,state=self.state)

def load(p):
    lo,hi,lc,rc=p['domain']
    return Piece(F(lo),F(hi),lc,rc,F(p['m']),F(p['b']),p['chi'],F(p['rho']),tuple(map(tuple,p['pi'])),tuple(p['state']))

def cells(knots):
    knots=sorted(set(knots))
    for i,e in enumerate(knots):
        yield e,e,e
        if i+1<len(knots): yield e,knots[i+1],(e+knots[i+1])/2

def intersection_knots(lines, lo, hi):
    return {(b2-b1)/(m1-m2) for (m1,b1),(m2,b2) in combinations(lines,2) if m1!=m2 and lo < (b2-b1)/(m1-m2) < hi}

def arrangement(pieces):
    if not pieces: return []
    knots={x for p in pieces for x in (p.lo,p.hi)}
    knots |= intersection_knots(sorted({(p.m,p.b) for p in pieces}), min(knots),max(knots))
    return list(cells(knots))

def dominates(a,b,e):
    ta,tb=a.tau(e),b.tau(e)
    return (a.state==b.state and (ta<tb or ta==tb and (a.chi or not b.chi))
            and a.rho<=b.rho and (a.rho<b.rho or a.pi<=b.pi))

def _certificate_cell(a,b,lo,hi,e):
    # arrangement() exhaustively enumerates every endpoint and pair root.
    # Its sorted adjacent open cells contain none of these breakpoints.
    aa=[(i,p) for i,p in enumerate(a) if p.contains(e)]
    bb=[(i,p) for i,p in enumerate(b) if p.contains(e)]
    forward=[next((i for i,p in aa if dominates(p,q,e)),None) for _,q in bb]
    reverse=[next((j for j,q in bb if dominates(q,p,e)),None) for _,p in aa]
    return dict(lo=str(lo),hi=str(hi),singleton=lo==hi,
                left_support=[i for i,_ in aa],right_support=[j for j,_ in bb],
                left_covers_right=forward,right_covers_left=reverse)

def equivalent(a,b):
    """Complete finite affine arrangement, sufficient mutual cut preorder.

    Support, chi, metadata and all affine signs are constant on open cells.
    Thus representatives decide whole cells; included singleton knots are exact.
    This is a sufficient continuation-equivalence certificate, not a complete
    decision procedure for all possible semantic continuation relations.
    """
    a,b=list(a),list(b)
    certificates=[]
    for lo,hi,e in arrangement(a+b):
        c=_certificate_cell(a,b,lo,hi,e)
        certificates.append(c)
        if None in c['left_covers_right'] or None in c['right_covers_left']:
            raise AssertionError(dict(reason='continuation_cover',cell=c,left=[p.dump() for p in a],right=[p.dump() for p in b]))
    encoded=json.dumps(certificates,sort_keys=True,separators=(',',':')).encode()
    return dict(cells=len(certificates),open_cells=sum(not c['singleton'] for c in certificates),singletons=sum(c['singleton'] for c in certificates),sha256=hashlib.sha256(encoded).hexdigest(),certificate=certificates)

def exact_family_equal(a,b):
    a,b=list(a),list(b)
    for lo,hi,e in arrangement(a+b):
        _certificate_cell(a,b,lo,hi,e)
        def signature(pieces):
            groups={}
            for p in pieces:
                if not p.contains(e):continue
                key=p.family();value=p.tau(e)
                if key not in groups or value<groups[key][0]:groups[key]=(value,p.chi)
                elif value==groups[key][0]:groups[key]=(value,groups[key][1] or p.chi)
            return groups
        if signature(a)!=signature(b):
            raise AssertionError(dict(reason='independent_operator_formula',cell=(str(lo),str(hi)),left=str(signature(a)),right=str(signature(b))))
    return len(arrangement(a+b))

def antichain(pieces):
    for lo,hi,e in arrangement(pieces):
        active=[p for p in pieces if p.contains(e)]
        for p,q in combinations(active,2):
            if dominates(p,q,e) or dominates(q,p,e):
                raise AssertionError(('not_antichain',str(e),p.dump(),q.dump()))

# A row (A,B,C,strict) means A*x <= B*y+C, strict changes <= to <.
def feasible(rows,y):
    lower=upper=None;ls=us=False
    for A,B,C,s in rows:
        v=B*y+C
        if A==0:
            if v<0 or v==0 and s:return False
        elif A<0:
            z=v/A
            if lower is None or z>lower:lower,ls=z,s
            elif z==lower:ls=ls or s
        else:
            z=v/A
            if upper is None or z<upper:upper,us=z,s
            elif z==upper:us=us or s
    return lower is None or upper is None or lower<upper or lower==upper and not(ls or us)

def region(source,rows,objectives,ylo,yhi,effect,site):
    """Independent finite analytic min-max over a bounded x interval.

    Minimum of convex max of affine functions occurs at an endpoint or a pair
    intersection. Every candidate x is affine in y. Roots of candidate-domain
    tests and all candidate objective comparisons give a complete partition.
    Strict feasibility is tested separately, including on each optimal face.
    """
    candidates={(B/A,C/A) for A,B,C,s in rows if A}
    for (a,d,c,s),(aa,dd,cc,ss) in combinations(objectives,2):
        if a!=aa:candidates.add(((dd-d)/(a-aa),(cc-c)/(a-aa)))
    candidates=sorted(candidates)
    values={(a*xm+d,a*xb+c) for xm,xb in candidates for a,d,c,s in objectives}
    tests={(A*xm-B,A*xb-C) for xm,xb in candidates for A,B,C,s in rows}
    tests|={(B,C) for A,B,C,s in rows if not A}
    knots={ylo,yhi}
    knots|={-b/m for m,b in tests if m and ylo < -b/m < yhi}
    knots|=intersection_knots(sorted(values),ylo,yhi)
    knots|=intersection_knots(candidates,ylo,yhi)
    output=[]
    for lo,hi,y in cells(knots):
        if not feasible(rows,y):continue
        opts=[]
        for xm,xb in candidates:
            x=xm*y+xb
            if not all(A*x<=B*y+C for A,B,C,s in rows):continue
            active=max(objectives,key=lambda f:f[0]*x+f[1]*y+f[2])
            a,d,c,s=active
            opts.append((a*x+d*y+c,a*xm+d,a*xb+c))
        if not opts:
            raise AssertionError(('no_closed_minimizer',str(y)))
        tau,m,b=min(opts)
        boundary=rows+[(a,m-d,b-c,s) for a,d,c,s in objectives]
        chi=feasible(boundary,y)
        state=(site,source.state[1] if effect=='C' else 0,source.state[2]+1)
        output.append(Piece(lo,hi,lo==hi,lo==hi,m,b,chi,source.rho,source.pi+((site,effect),),state))
    return output

def transform(pieces,op,params):
    pieces=list(pieces);result=[]
    if op=='merge':return pieces
    h=F(params.get('h',1));a=F(params.get('a',0));b=F(params.get('b',100));D=F(params.get('D',0));site=params.get('site','next')
    for p in pieces:
        if op=='D':
            c=F(params['consumption']);dt=F(params['duration']);floor=F(params['floor'])
            lo=max(p.lo-c,floor);hi=p.hi-c
            if lo>hi:continue
            lc=p.contains(lo+c);rc=p.rc
            if lo==hi and not(lc and rc):continue
            result.append(Piece(lo,hi,lc,rc,p.m,p.b+p.m*c+dt,p.chi,p.rho+c,p.pi,(site,p.state[1],p.state[2])))
        elif op=='S':
            if a>b:continue
            knots={p.lo,p.hi}
            if p.m:
                knots|={e for e in ((a-h-p.b)/p.m,(b-h-p.b)/p.m) if p.lo<e<p.hi}
            for lo,hi,e in cells(knots):
                if not p.contains(e):continue
                t=p.tau(e)
                if t>b-h or t==b-h and not p.chi:continue
                plateau=t+h<a
                m,c=(F(0),a+D) if plateau else (p.m,p.b+h+D)
                result.append(Piece(lo,hi,lo==hi,lo==hi,m,c,p.chi or plateau,p.rho,p.pi+((site,'S'),),(site,0,p.state[2]+1)))
        else:
            if op=='CS' and a>b:continue
            curve=[[F(x) for x in row] for row in params['curve']]
            for il,ih,im,ic in curve:
                for ol,oh,om,oc in curve:
                    rows=[(-F(1),F(0),-p.lo,not p.lc),(F(1),F(0),p.hi,not p.rc),(-F(1),F(0),-il,False),(F(1),F(0),ih,False),(F(1),F(1),F(0),True)]
                    objectives=[(p.m-im,om,p.b+h+oc-ic,not p.chi)]
                    if op=='CS':
                        rows.append((p.m,F(0),b-h-p.b,not p.chi))
                        objectives.extend([(F(0),F(0),a+D,False),(p.m,F(0),p.b+h+D,not p.chi)])
                    result.extend(region(p,rows,objectives,ol,oh,op,site))
    return result

def terminal_expected(pieces,penalty=F(0),reserve=F(0)):
    feasible_pieces=[]
    for p in pieces:
        lo=max(p.lo,reserve);hi=p.hi
        if lo>hi:continue
        lc=p.contains(lo);rc=p.rc
        if lo==hi and not(lc and rc):continue
        x=lo if p.m>0 else hi if p.m<0 else (lo+hi)/2
        included=(x>lo or lc) and (x<hi or rc)
        J=p.tau(x)+penalty*p.state[2]
        feasible_pieces.append((J,p,lo,hi,lc,rc,x,included and p.chi))
    if not feasible_pieces:return dict(status='infeasible')
    J=min(v[0] for v in feasible_pieces)
    face=[v for v in feasible_pieces if v[0]==J and v[7]]
    if not face:return dict(status='infimum_unattained',J=str(J),unattained_component='J')
    qrows=[]
    for _,p,lo,hi,lc,rc,x,ok in face:
        e=lo if p.m==0 else x
        attained=(e>lo or lc) and (e<hi or rc)
        qrows.append((e+p.rho,p,e,attained))
    Q=min(v[0] for v in qrows);winners=[v for v in qrows if v[0]==Q and v[3]]
    if not winners:return dict(status='infimum_unattained',J=str(J),Q=str(Q),unattained_component='Q')
    _,p,e,_=min(winners,key=lambda v:(v[1].state[2],v[1].pi))
    return dict(status='attained_optimum',J=str(J),Q=str(Q),H=p.state[2],pi=[list(v) for v in p.pi])

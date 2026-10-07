"""Opt-in per-cell exact-time reuse; v2 remains the unchanged reference.

Every affine cell, active input index, first-cover scan and certificate field is
identical to v2. Only repeated tau(e) evaluation inside pair scans is removed.
There is no cross-cell cache, approximate comparison or reordered support.
"""
import hashlib,json
from itertools import combinations
from . import independent_oracle_v2 as reference

KERNEL='tau-precompute-v1'

def _dominates(a,ta,b,tb):
    return (a.state==b.state and (ta<tb or ta==tb and (a.chi or not b.chi))
            and a.rho<=b.rho and (a.rho<b.rho or a.pi<=b.pi))

def _certificate_cell(a,b,lo,hi,e):
    # Keep each input occurrence, including duplicate pieces, at its old index.
    aa=[(i,p,p.tau(e)) for i,p in enumerate(a) if p.contains(e)]
    bb=[(i,p,p.tau(e)) for i,p in enumerate(b) if p.contains(e)]
    forward=[next((i for i,p,ta in aa if _dominates(p,ta,q,tb)),None) for _,q,tb in bb]
    reverse=[next((j for j,q,tb in bb if _dominates(q,tb,p,ta)),None) for _,p,ta in aa]
    return dict(lo=str(lo),hi=str(hi),singleton=lo==hi,
                left_support=[i for i,_,_ in aa],right_support=[j for j,_,_ in bb],
                left_covers_right=forward,right_covers_left=reverse)

def equivalent(a,b):
    a,b=list(a),list(b)
    certificates=[]
    for lo,hi,e in reference.arrangement(a+b):
        c=_certificate_cell(a,b,lo,hi,e)
        certificates.append(c)
        if None in c['left_covers_right'] or None in c['right_covers_left']:
            raise AssertionError(dict(reason='continuation_cover',cell=c,left=[p.dump() for p in a],right=[p.dump() for p in b]))
    encoded=json.dumps(certificates,sort_keys=True,separators=(',',':')).encode()
    return dict(cells=len(certificates),open_cells=sum(not c['singleton'] for c in certificates),singletons=sum(c['singleton'] for c in certificates),sha256=hashlib.sha256(encoded).hexdigest(),certificate=certificates)

def antichain(pieces):
    for lo,hi,e in reference.arrangement(pieces):
        active=[(p,p.tau(e)) for p in pieces if p.contains(e)]
        for (p,tp),(q,tq) in combinations(active,2):
            if _dominates(p,tp,q,tq) or _dominates(q,tq,p,tp):
                raise AssertionError(('not_antichain',str(e),p.dump(),q.dump()))

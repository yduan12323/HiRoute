"""Independent path and metadata checks shared with historical adapters."""
from fractions import Fraction as F
from pathlib import Path
import hashlib,json
from .exact_leg_table import unique

def load(path,limit=4*1024**2):
    if path.stat().st_size>limit:raise ValueError('bounded metadata size')
    return json.loads(path.read_text(),object_pairs_hook=unique)


def sha(path,check=lambda:None):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024**2),b''):check();h.update(block)
    return h.hexdigest()


def verify_paths(table,pairs,edge,check=lambda:None):
    result=[]
    for s,t in sorted(set(map(tuple,pairs))):
        check();p=table.pairs[s,t]
        if not p.reachable:
            result.append(dict(source=s,target=t,status='common_provider_unreachable_not_independent_cut'));continue
        duration=length=F(0)
        for eid,u,v in zip(p.edges,p.nodes,p.nodes[1:]):
            check();a,b,dt,ds=edge(eid)
            if (a,b)!=(u,v):raise ValueError('raw edge identity/connectivity mismatch')
            duration+=F(dt);length+=F(ds)
        if duration!=p.time or length!=p.length:raise ValueError('raw selected path totals mismatch')
        result.append(dict(source=s,target=t,status='exact_path_replay_pass',edges=len(p.edges)))
    return result



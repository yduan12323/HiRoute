"""Opt-in lossless work reuse over the unchanged independent v2 oracle.

Only exact_family_equal omits work that cannot influence its return/rejection:
the unused coverage certificate and the second construction of its arrangement.
All cells/signatures and error payloads are unchanged. Memoization belongs to one
caller; full ordered semantic bytes, not a digest or a partial key, identify it.
"""
from collections import OrderedDict
import json
from . import independent_oracle_v2 as reference


def exact_family_equal(a,b):
    a,b=list(a),list(b)
    arrangement=reference.arrangement(a+b)
    for lo,hi,e in arrangement:
        def signature(pieces):
            groups={}
            for p in pieces:
                if not p.contains(e):continue
                key=p.family();value=p.tau(e)
                if key not in groups or value<groups[key][0]:groups[key]=(value,p.chi)
                elif value==groups[key][0]:groups[key]=(value,groups[key][1] or p.chi)
            return groups
        left,right=signature(a),signature(b)
        if left!=right:
            raise AssertionError(dict(reason='independent_operator_formula',cell=(str(lo),str(hi)),left=str(left),right=str(right)))
    return len(arrangement)


def _wire(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')


class MemoizedOracle:
    """Bound stored serialized bytes and entry count; this is not a heap quota.

    Negative results are never cached. Each key contains both complete ordered
    input lists, including endpoint flags, attainment and all family metadata.
    Certificates are stored as immutable bytes and decoded afresh for each hit.
    Oversized entries bypass caching without changing validation.
    """
    def __init__(self,*,max_bytes=8*1024**2,max_entries=128,max_entry_bytes=1024**2):
        if any(type(x) is not int or x<0 for x in (max_bytes,max_entries,max_entry_bytes)):
            raise ValueError('nonnegative exact cache limits required')
        self.max_bytes=max_bytes;self.max_entries=max_entries;self.max_entry_bytes=max_entry_bytes
        self.cache=OrderedDict()
        self.stats=dict(hits=0,misses=0,oversized=0,evictions=0)
    @property
    def stored_bytes(self):
        # At most max_entries entries. Derive accounting from retained bytes so
        # interruption between any two mutations cannot leave a stale counter.
        return sum(len(key)+len(value) for key,value in self.cache.items())
    def __getattr__(self,name):
        return getattr(reference,name)
    def _call(self,kind,a,b,fn):
        a,b=list(a),list(b)
        try:key=_wire([kind,[p.dump() for p in a],[p.dump() for p in b]])
        except (ValueError,TypeError,OverflowError):
            # Caching must not add a serialization prerequisite to exact math.
            self.stats['key_bypasses']=self.stats.get('key_bypasses',0)+1
            return fn(a,b)
        size_key='max_key_bytes_'+kind
        self.stats[size_key]=max(self.stats.get(size_key,0),len(key))
        if key in self.cache:
            self.stats['hits']+=1;value=self.cache.pop(key);self.cache[key]=value
            return json.loads(value)
        self.stats['misses']+=1
        result=fn(a,b) # No failed validation result reaches the cache.
        value=_wire(result);size=len(key)+len(value)
        size_value='max_value_bytes_'+kind
        self.stats[size_value]=max(self.stats.get(size_value,0),len(value))
        if not self.max_entries or size>min(self.max_entry_bytes,self.max_bytes):
            self.stats['oversized']+=1;return result
        while self.cache and (len(self.cache)>=self.max_entries or self.stored_bytes+size>self.max_bytes):
            old_key,old_value=self.cache.popitem(last=False)
            self.stats['evictions']+=1
        self.cache[key]=value
        return result
    def exact_family_equal(self,a,b):return self._call('exact_family_equal',a,b,exact_family_equal)
    def equivalent(self,a,b):return self._call('equivalent',a,b,reference.equivalent)
    def snapshot(self):return dict(self.stats,entries=len(self.cache),serialized_bytes=self.stored_bytes,
        max_bytes=self.max_bytes,max_entries=self.max_entries,max_entry_bytes=self.max_entry_bytes)
